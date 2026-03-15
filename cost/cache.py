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

    async def get(
        self,
        provider: str,
        data_type: str,
        query_input: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Retrieve a cached response, or ``None`` if missing / expired."""
        try:
            return await self.db.cache_get(provider, data_type, query_input)
        except (OSError, ValueError, KeyError) as exc:
            logger.warning(
                "Cache GET failed for provider=%s data_type=%s: %s", provider, data_type, exc,
            )
            return None

    async def set(
        self,
        provider: str,
        data_type: str,
        query_input: dict[str, Any],
        response_data: dict[str, Any],
        found: bool,
        ttl_days: Optional[int] = None,
    ) -> None:
        """Store a response in the cache."""
        if ttl_days is None:
            ttl_days = _TTL_DAYS.get(data_type, _DEFAULT_TTL_DAYS)

        try:
            await self.db.cache_set(
                provider=provider,
                enrichment_type=data_type,
                query_input=query_input,
                response_data=response_data,
                found=found,
                ttl_days=ttl_days,
            )
        except (OSError, ValueError) as exc:
            logger.warning(
                "Cache SET failed for provider=%s data_type=%s: %s", provider, data_type, exc,
            )

    # ------------------------------------------------------------------
    # Invalidation
    # ------------------------------------------------------------------

    async def invalidate(
        self,
        provider: str,
        data_type: str,
        query_input: dict[str, Any],
    ) -> bool:
        """Invalidate a single cache entry by setting its expiry to now."""
        cache_key = self.db._make_cache_key(provider, data_type, query_input)
        try:
            async with self.db._connect() as conn:
                cursor = await conn.execute(
                    "UPDATE cache SET expires_at = CURRENT_TIMESTAMP WHERE cache_key = ?",
                    (cache_key,),
                )
                return cursor.rowcount > 0
        except OSError as exc:
            logger.warning(
                "Cache INVALIDATE failed for provider=%s data_type=%s: %s",
                provider, data_type, exc,
            )
            return False

    async def invalidate_domain(self, domain: str) -> int:
        """Invalidate all cache entries referencing *domain*."""
        domain_lower = domain.strip().lower()
        try:
            async with self.db._connect() as conn:
                cursor = await conn.execute(
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
        except OSError as exc:
            logger.warning(
                "Cache INVALIDATE_DOMAIN failed for domain=%s: %s", domain, exc,
            )
            return 0

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    async def purge_expired(self) -> int:
        """Delete all expired cache entries from the database."""
        try:
            count = await self.db.cache_purge_expired()
            if count:
                logger.info("Purged %d expired cache entries", count)
            return count
        except OSError as exc:
            logger.warning("Cache PURGE_EXPIRED failed: %s", exc)
            return 0

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    async def get_stats(self) -> dict[str, Any]:
        """Return aggregate cache statistics."""
        try:
            async with self.db._connect() as conn:
                cursor = await conn.execute(
                    """SELECT
                           COUNT(*) AS total,
                           SUM(CASE WHEN expires_at > CURRENT_TIMESTAMP THEN 1 ELSE 0 END) AS active,
                           SUM(CASE WHEN expires_at <= CURRENT_TIMESTAMP THEN 1 ELSE 0 END) AS expired,
                           COALESCE(SUM(hit_count), 0) AS total_hits,
                           SUM(CASE WHEN hit_count > 0 THEN 1 ELSE 0 END) AS entries_with_hits,
                           MIN(created_at) AS oldest,
                           MAX(created_at) AS newest
                       FROM cache"""
                )
                totals = await cursor.fetchone()

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

                cursor = await conn.execute(
                    """SELECT enrichment_type, COUNT(*) AS cnt
                       FROM cache
                       WHERE expires_at > CURRENT_TIMESTAMP
                       GROUP BY enrichment_type
                       ORDER BY cnt DESC"""
                )
                type_rows = await cursor.fetchall()
                by_type = {row["enrichment_type"]: row["cnt"] for row in type_rows}

                cursor = await conn.execute(
                    """SELECT provider, COUNT(*) AS cnt
                       FROM cache
                       WHERE expires_at > CURRENT_TIMESTAMP
                       GROUP BY provider
                       ORDER BY cnt DESC"""
                )
                provider_rows = await cursor.fetchall()
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
        except OSError as exc:
            logger.warning("Cache GET_STATS failed: %s", exc)
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
