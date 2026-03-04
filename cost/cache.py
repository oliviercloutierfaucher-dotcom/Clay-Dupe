"""Cache manager with per-data-type TTL policies.

Wraps Database.cache_get(), cache_set(), and cache_purge_expired() with
intelligent TTL assignment based on enrichment data type and provides
domain-level invalidation and usage statistics.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from data.database import Database

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TTL policies (days) per data type
# ---------------------------------------------------------------------------

_TTL_DAYS: dict[str, int] = {
    "email_lookup": 90,
    "domain_pattern": 365,
    "catch_all_status": 90,
    "company_data": 180,
    "linkedin_url": 365,
    "verification": 30,
    "domain_lookup": 365,
}

_DEFAULT_TTL_DAYS: int = 30


class CacheManager:
    """High-level cache facade around the Database cache layer.

    Automatically selects the correct TTL based on the ``data_type``
    parameter and exposes helpers for invalidation and statistics.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def get(
        self,
        provider: str,
        data_type: str,
        query_input: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Retrieve a cached response, or ``None`` if missing / expired.

        Parameters
        ----------
        provider:
            Provider name (e.g. ``"apollo"``).
        data_type:
            Logical data type (e.g. ``"email_lookup"``, ``"company_data"``).
            Used purely for the cache key -- the TTL is enforced at write
            time and the database ``expires_at`` column handles expiry.
        query_input:
            The original query parameters used as part of the cache key.
        """
        try:
            return self.db.cache_get(provider, data_type, query_input)
        except Exception:
            logger.exception(
                "Cache GET failed for provider=%s data_type=%s", provider, data_type,
            )
            return None

    def set(
        self,
        provider: str,
        data_type: str,
        query_input: dict[str, Any],
        response_data: dict[str, Any],
        found: bool,
        ttl_days: Optional[int] = None,
    ) -> None:
        """Store a response in the cache.

        If *ttl_days* is not provided the TTL is looked up from the
        per-data-type policy table.  Unfound results use the same TTL so
        that repeated misses for the same query are also cached (negative
        caching).

        Parameters
        ----------
        provider:
            Provider name string.
        data_type:
            Logical data type -- drives the default TTL.
        query_input:
            Query parameters forming the cache key.
        response_data:
            The response payload to cache.
        found:
            Whether the lookup produced a positive result.
        ttl_days:
            Explicit TTL override.  When ``None`` the data-type default is
            used.
        """
        if ttl_days is None:
            ttl_days = _TTL_DAYS.get(data_type, _DEFAULT_TTL_DAYS)

        try:
            self.db.cache_set(
                provider=provider,
                enrichment_type=data_type,
                query_input=query_input,
                response_data=response_data,
                found=found,
                ttl_days=ttl_days,
            )
        except Exception:
            logger.exception(
                "Cache SET failed for provider=%s data_type=%s", provider, data_type,
            )

    # ------------------------------------------------------------------
    # Invalidation
    # ------------------------------------------------------------------

    def invalidate(
        self,
        provider: str,
        data_type: str,
        query_input: dict[str, Any],
    ) -> bool:
        """Invalidate a single cache entry by setting its expiry to now.

        Returns ``True`` if a matching row was found and updated,
        ``False`` otherwise.
        """
        cache_key = self.db._make_cache_key(provider, data_type, query_input)
        try:
            with self.db._connect() as conn:
                cursor = conn.execute(
                    "UPDATE cache SET expires_at = CURRENT_TIMESTAMP WHERE cache_key = ?",
                    (cache_key,),
                )
                return cursor.rowcount > 0
        except Exception:
            logger.exception(
                "Cache INVALIDATE failed for provider=%s data_type=%s",
                provider,
                data_type,
            )
            return False

    def invalidate_domain(self, domain: str) -> int:
        """Invalidate **all** cache entries whose ``query_input`` references
        *domain* (case-insensitive substring match on the stored JSON).

        This is useful when a domain changes MX configuration or a catch-all
        status flip is detected and all previously cached lookups for that
        domain should be discarded.

        Returns the number of rows invalidated.
        """
        domain_lower = domain.strip().lower()
        try:
            with self.db._connect() as conn:
                # The response_data / query column stores JSON; we do a LIKE
                # match against the cache table's stored enrichment_type and
                # the raw cache_key can't help here, so we match on the
                # response_data column which contains the serialised
                # query_input echoed back, or on a dedicated column if
                # available.  The safest portable approach is to match against
                # the entire row's text representation since the schema stores
                # the query_hash but not the raw query_input text.  Instead
                # we expire rows where the provider-specific data references
                # the domain.
                cursor = conn.execute(
                    """UPDATE cache
                       SET expires_at = CURRENT_TIMESTAMP
                       WHERE lower(response_data) LIKE ?
                          OR lower(cache_key) IN (
                              SELECT lower(cache_key) FROM cache
                              WHERE lower(response_data) LIKE ?
                          )""",
                    (f"%{domain_lower}%", f"%{domain_lower}%"),
                )
                count = cursor.rowcount
                if count:
                    logger.info(
                        "Invalidated %d cache entries for domain=%s", count, domain,
                    )
                return count
        except Exception:
            logger.exception(
                "Cache INVALIDATE_DOMAIN failed for domain=%s", domain,
            )
            return 0

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def purge_expired(self) -> int:
        """Delete all expired cache entries from the database.

        Returns the number of rows purged.
        """
        try:
            count = self.db.cache_purge_expired()
            if count:
                logger.info("Purged %d expired cache entries", count)
            return count
        except Exception:
            logger.exception("Cache PURGE_EXPIRED failed")
            return 0

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate cache statistics.

        Returns a dict with:
        - ``total_entries``: number of rows in the cache table.
        - ``active_entries``: non-expired rows.
        - ``expired_entries``: rows past their ``expires_at``.
        - ``total_hits``: sum of all ``hit_count`` values.
        - ``hit_rate``: percentage of entries that have been hit at least once.
        - ``by_type``: breakdown of active entries per ``enrichment_type``.
        - ``by_provider``: breakdown of active entries per ``provider``.
        - ``oldest_entry``: ISO timestamp of the earliest ``created_at``.
        - ``newest_entry``: ISO timestamp of the latest ``created_at``.
        """
        try:
            with self.db._connect() as conn:
                # Total and active/expired counts
                totals = conn.execute(
                    """SELECT
                           COUNT(*) AS total,
                           SUM(CASE WHEN expires_at > CURRENT_TIMESTAMP THEN 1 ELSE 0 END) AS active,
                           SUM(CASE WHEN expires_at <= CURRENT_TIMESTAMP THEN 1 ELSE 0 END) AS expired,
                           COALESCE(SUM(hit_count), 0) AS total_hits,
                           SUM(CASE WHEN hit_count > 0 THEN 1 ELSE 0 END) AS entries_with_hits,
                           MIN(created_at) AS oldest,
                           MAX(created_at) AS newest
                       FROM cache"""
                ).fetchone()

                total = totals["total"] or 0
                active = totals["active"] or 0
                expired = totals["expired"] or 0
                total_hits = totals["total_hits"] or 0
                entries_with_hits = totals["entries_with_hits"] or 0
                oldest = totals["oldest"]
                newest = totals["newest"]

                hit_rate = (
                    round(entries_with_hits / total * 100, 1) if total > 0 else 0.0
                )

                # Breakdown by enrichment_type (active only)
                type_rows = conn.execute(
                    """SELECT enrichment_type, COUNT(*) AS cnt
                       FROM cache
                       WHERE expires_at > CURRENT_TIMESTAMP
                       GROUP BY enrichment_type
                       ORDER BY cnt DESC"""
                ).fetchall()
                by_type = {row["enrichment_type"]: row["cnt"] for row in type_rows}

                # Breakdown by provider (active only)
                provider_rows = conn.execute(
                    """SELECT provider, COUNT(*) AS cnt
                       FROM cache
                       WHERE expires_at > CURRENT_TIMESTAMP
                       GROUP BY provider
                       ORDER BY cnt DESC"""
                ).fetchall()
                by_provider = {row["provider"]: row["cnt"] for row in provider_rows}

            return {
                "total_entries": total,
                "active_entries": active,
                "expired_entries": expired,
                "total_hits": total_hits,
                "hit_rate": hit_rate,
                "by_type": by_type,
                "by_provider": by_provider,
                "oldest_entry": oldest,
                "newest_entry": newest,
            }
        except Exception:
            logger.exception("Cache GET_STATS failed")
            return {
                "total_entries": 0,
                "active_entries": 0,
                "expired_entries": 0,
                "total_hits": 0,
                "hit_rate": 0.0,
                "by_type": {},
                "by_provider": {},
                "oldest_entry": None,
                "newest_entry": None,
            }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_ttl(data_type: str) -> int:
        """Return the configured TTL in days for a given data type."""
        return _TTL_DAYS.get(data_type, _DEFAULT_TTL_DAYS)

    @staticmethod
    def list_ttl_policies() -> dict[str, int]:
        """Return a copy of the full TTL policy table."""
        return dict(_TTL_DAYS)
