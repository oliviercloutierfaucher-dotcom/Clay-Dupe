"""SQLite database manager — central data access layer.

Uses WAL mode for concurrent reads and provides all CRUD operations
for companies, people, campaigns, enrichment results, credits, cache,
email patterns, catch-all status, audit logging, and dashboard stats.

All public methods are async and use aiosqlite for non-blocking I/O.
For synchronous callers (Streamlit, tests), use ``run_sync(db.method(...))``
from :mod:`data.sync`.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional

import aiosqlite

from config.settings import ProviderName
from data.models import (
    Company, Person, EnrichmentResult, Campaign, CreditUsage,
    CacheEntry, EmailPattern, EnrichmentType, VerificationStatus, CampaignStatus,
    EmailTemplate, GeneratedEmail,
)

if sys.version_info < (3, 11):
    raise RuntimeError(
        f"Clay-Dupe requires Python >= 3.11, got {sys.version_info.major}.{sys.version_info.minor}"
    )


class Database:
    def __init__(self, db_path: str = "clay_dupe.db"):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None
        self._write_lock = asyncio.Lock()
        self._init_db()

    def _init_db(self):
        """Execute schema.sql to create tables (sync — runs once at startup).

        Uses executescript for the main DDL, then runs ALTER TABLE migrations
        individually so duplicate-column errors on existing DBs are ignored.
        """
        schema_path = Path(__file__).parent / "schema.sql"
        schema_text = schema_path.read_text()

        # Split schema into main DDL and ALTER TABLE migrations
        # Find the "Schema migrations" section marker
        marker = "-- Schema migrations"
        if marker in schema_text:
            main_ddl, migrations_section = schema_text.split(marker, 1)
        else:
            main_ddl = schema_text
            migrations_section = ""

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(main_ddl)

            # Run migration statements individually (ALTER TABLE may fail on existing DBs)
            if migrations_section:
                for statement in migrations_section.split(";"):
                    # Strip comments and whitespace to find actual SQL
                    lines = [l for l in statement.strip().splitlines()
                             if l.strip() and not l.strip().startswith("--")]
                    stmt = "\n".join(lines).strip()
                    if not stmt:
                        continue
                    try:
                        conn.execute(stmt)
                    except sqlite3.OperationalError as e:
                        if "duplicate column name" in str(e).lower():
                            continue
                        raise
            conn.commit()
        finally:
            conn.close()

    async def _get_connection(self) -> aiosqlite.Connection:
        """Return the singleton connection, opening it lazily on first use."""
        if self._conn is None:
            self._conn = await aiosqlite.connect(self.db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA foreign_keys=ON")
            await self._conn.execute("PRAGMA busy_timeout=5000")
        return self._conn

    @asynccontextmanager
    async def _connect(self):
        """Async context manager reusing a singleton DB connection. WAL mode, FK ON, busy_timeout=5000.

        Serializes all writes through ``_write_lock`` to prevent SQLITE_BUSY
        errors when multiple coroutines write concurrently.
        """
        async with self._write_lock:
            conn = await self._get_connection()
            try:
                yield conn
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    async def close(self):
        """Close the singleton connection for clean shutdown."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Helpers: Row -> Model conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_company(row) -> Company:
        """Convert a Row to a Company model."""
        d = dict(row)
        if isinstance(d.get("industry_tags"), str):
            try:
                d["industry_tags"] = json.loads(d["industry_tags"])
            except (json.JSONDecodeError, TypeError):
                d["industry_tags"] = []
        return Company.model_validate(d)

    @staticmethod
    def _row_to_person(row) -> Person:
        """Convert a Row to a Person model."""
        d = dict(row)
        return Person.model_validate(d)

    @staticmethod
    def _row_to_campaign(row) -> Campaign:
        """Convert a Row to a Campaign model."""
        d = dict(row)
        for field in ("enrichment_types", "waterfall_order", "column_mapping", "cost_by_provider"):
            if isinstance(d.get(field), str):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return Campaign.model_validate(d)

    @staticmethod
    def _row_to_enrichment_result(row) -> EnrichmentResult:
        """Convert a Row to an EnrichmentResult model."""
        d = dict(row)
        for field in ("query_input", "result_data"):
            if isinstance(d.get(field), str):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        d["found"] = bool(d.get("found", False))
        d["from_cache"] = bool(d.get("from_cache", False))
        return EnrichmentResult.model_validate(d)

    # ------------------------------------------------------------------
    # Cache Operations
    # ------------------------------------------------------------------

    @staticmethod
    def _make_cache_key(provider: str, enrichment_type: str, query_input: dict) -> str:
        """SHA-256 of normalized JSON (sort keys, lowercase string values)."""

        def _normalize(obj):
            if isinstance(obj, str):
                return obj.lower()
            if isinstance(obj, dict):
                return {k.lower(): _normalize(v) for k, v in sorted(obj.items())}
            if isinstance(obj, (list, tuple)):
                return [_normalize(i) for i in obj]
            return obj

        normalized = {
            "provider": provider.lower() if isinstance(provider, str) else str(provider).lower(),
            "enrichment_type": enrichment_type.lower() if isinstance(enrichment_type, str) else str(enrichment_type).lower(),
            "query_input": _normalize(query_input),
        }
        raw = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()

    async def cache_get(self, provider: str, enrichment_type: str, query_input: dict) -> Optional[dict]:
        """Return cached response if not expired, increment hit_count."""
        cache_key = self._make_cache_key(provider, enrichment_type, query_input)
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM cache WHERE cache_key = ? AND expires_at > CURRENT_TIMESTAMP",
                (cache_key,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            await conn.execute(
                "UPDATE cache SET hit_count = hit_count + 1 WHERE cache_key = ?",
                (cache_key,),
            )
            try:
                return json.loads(row["response_data"])
            except (json.JSONDecodeError, TypeError):
                return {}

    async def cache_set(
        self,
        provider: str,
        enrichment_type: str,
        query_input: dict,
        response_data: dict,
        found: bool,
        ttl_days: int = 30,
    ) -> None:
        """Insert or replace cache entry."""
        cache_key = self._make_cache_key(provider, enrichment_type, query_input)
        query_hash = hashlib.sha256(
            json.dumps(query_input, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        expires_at = (datetime.utcnow() + timedelta(days=ttl_days)).isoformat()
        prov = provider if isinstance(provider, str) else provider.value
        etype = enrichment_type if isinstance(enrichment_type, str) else enrichment_type.value

        async with self._connect() as conn:
            await conn.execute(
                """INSERT OR REPLACE INTO cache
                   (cache_key, provider, enrichment_type, query_hash,
                    response_data, found, expires_at, hit_count, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP)""",
                (
                    cache_key,
                    prov,
                    etype,
                    query_hash,
                    json.dumps(response_data),
                    int(found),
                    expires_at,
                ),
            )

    async def cache_purge_expired(self) -> int:
        """Delete expired entries, return count deleted."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                "DELETE FROM cache WHERE expires_at < CURRENT_TIMESTAMP"
            )
            return cursor.rowcount

    async def cache_evict(self, max_rows: int = 50_000) -> int:
        """Evict expired entries and enforce a row-count cap.

        1. Delete all expired rows.
        2. If the table still exceeds *max_rows*, delete the oldest
           (by created_at) entries until the cap is met.

        Returns total rows deleted.
        """
        total_deleted = 0
        async with self._connect() as conn:
            # 1. Purge expired
            cursor = await conn.execute(
                "DELETE FROM cache WHERE expires_at < CURRENT_TIMESTAMP"
            )
            total_deleted += cursor.rowcount

            # 2. Enforce row-count cap
            cursor = await conn.execute("SELECT COUNT(*) FROM cache")
            count = (await cursor.fetchone())[0]
            if count > max_rows:
                excess = count - max_rows
                await conn.execute(
                    """DELETE FROM cache WHERE cache_key IN (
                        SELECT cache_key FROM cache
                        ORDER BY created_at ASC
                        LIMIT ?
                    )""",
                    (excess,),
                )
                total_deleted += excess
        return total_deleted

    async def wal_checkpoint(self) -> None:
        """Run a WAL checkpoint to keep the WAL file bounded."""
        async with self._connect() as conn:
            await conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    # ------------------------------------------------------------------
    # Company Operations
    # ------------------------------------------------------------------

    async def upsert_company(self, company: Company) -> Company:
        """Upsert a company by domain (select-then-insert/update for partial index compat)."""
        now = datetime.utcnow().isoformat()
        industry_tags_json = json.dumps(company.industry_tags)
        revenue = float(company.revenue_usd) if company.revenue_usd is not None else None
        ebitda = float(company.ebitda_usd) if company.ebitda_usd is not None else None
        source = company.source_provider.value if company.source_provider else None
        enriched = company.enriched_at.isoformat() if company.enriched_at else None

        async with self._connect() as conn:
            existing = None
            if company.domain:
                cursor = await conn.execute(
                    "SELECT * FROM companies WHERE domain = ?",
                    (company.domain.strip().lower(),),
                )
                existing = await cursor.fetchone()

            if existing:
                await conn.execute(
                    """UPDATE companies SET
                        name = COALESCE(?, name),
                        industry = COALESCE(?, industry),
                        industry_tags = CASE WHEN ? IS NOT NULL AND ? != '[]' THEN ? ELSE industry_tags END,
                        employee_count = COALESCE(?, employee_count),
                        employee_range = COALESCE(?, employee_range),
                        revenue_usd = COALESCE(?, revenue_usd),
                        ebitda_usd = COALESCE(?, ebitda_usd),
                        founded_year = COALESCE(?, founded_year),
                        description = COALESCE(?, description),
                        city = COALESCE(?, city),
                        state = COALESCE(?, state),
                        country = COALESCE(?, country),
                        full_address = COALESCE(?, full_address),
                        linkedin_url = COALESCE(?, linkedin_url),
                        website_url = COALESCE(?, website_url),
                        phone = COALESCE(?, phone),
                        source_provider = COALESCE(?, source_provider),
                        apollo_id = COALESCE(?, apollo_id),
                        source_type = COALESCE(?, source_type),
                        icp_score = COALESCE(?, icp_score),
                        status = COALESCE(?, status),
                        sf_account_id = COALESCE(?, sf_account_id),
                        sf_status = COALESCE(?, sf_status),
                        sf_instance_url = COALESCE(?, sf_instance_url),
                        enriched_at = COALESCE(?, enriched_at),
                        updated_at = ?
                    WHERE domain = ?""",
                    (
                        company.name, company.industry,
                        industry_tags_json, industry_tags_json, industry_tags_json,
                        company.employee_count, company.employee_range,
                        revenue, ebitda, company.founded_year,
                        company.description, company.city, company.state, company.country,
                        company.full_address, company.linkedin_url, company.website_url,
                        company.phone, source, company.apollo_id,
                        company.source_type, company.icp_score, company.status,
                        company.sf_account_id, company.sf_status, company.sf_instance_url,
                        enriched, now, company.domain.strip().lower(),
                    ),
                )
                cursor = await conn.execute(
                    "SELECT * FROM companies WHERE domain = ?",
                    (company.domain.strip().lower(),),
                )
            else:
                await conn.execute(
                    """INSERT INTO companies
                       (id, name, domain, industry, industry_tags, employee_count,
                        employee_range, revenue_usd, ebitda_usd, founded_year,
                        description, city, state, country, full_address,
                        linkedin_url, website_url, phone, source_provider,
                        apollo_id, source_type, icp_score, status,
                        sf_account_id, sf_status, sf_instance_url,
                        enriched_at, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        company.id, company.name, company.domain, company.industry,
                        industry_tags_json, company.employee_count, company.employee_range,
                        revenue, ebitda, company.founded_year,
                        company.description, company.city, company.state, company.country,
                        company.full_address, company.linkedin_url, company.website_url,
                        company.phone, source, company.apollo_id,
                        company.source_type, company.icp_score, company.status,
                        company.sf_account_id, company.sf_status, company.sf_instance_url,
                        enriched, now, now,
                    ),
                )
                cursor = await conn.execute(
                    "SELECT * FROM companies WHERE id = ?", (company.id,)
                )
            row = await cursor.fetchone()
            return self._row_to_company(row)

    async def get_company_by_domain(self, domain: str) -> Optional[Company]:
        """Fetch a company by its domain."""
        domain = domain.strip().lower()
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM companies WHERE domain = ?", (domain,)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_company(row)

    async def update_company_sf_status(
        self, domain: str, sf_account_id: str, sf_instance_url: str
    ) -> None:
        """Update SF fields for the company matching the given domain."""
        domain = domain.strip().lower()
        now = datetime.utcnow().isoformat()
        async with self._connect() as conn:
            await conn.execute(
                """UPDATE companies SET
                    sf_account_id = ?,
                    sf_status = 'in_sf',
                    sf_instance_url = ?,
                    updated_at = ?
                WHERE domain = ?""",
                (sf_account_id, sf_instance_url, now, domain),
            )

    async def get_companies_by_sf_status(
        self, sf_status: Optional[str] = None
    ) -> list[Company]:
        """Return companies filtered by sf_status. If None, return all."""
        async with self._connect() as conn:
            if sf_status is not None:
                cursor = await conn.execute(
                    "SELECT * FROM companies WHERE sf_status = ?",
                    (sf_status,),
                )
            else:
                cursor = await conn.execute("SELECT * FROM companies")
            rows = await cursor.fetchall()
            return [self._row_to_company(r) for r in rows]

    async def search_companies(self, **filters) -> list[Company]:
        """Search companies with dynamic filters.

        Supported filters: industry, country, employee_min, employee_max,
        ebitda_min, ebitda_max, status, source_type, min_icp_score.
        """
        clauses: list[str] = []
        params: list = []

        if "industry" in filters and filters["industry"] is not None:
            clauses.append("industry = ?")
            params.append(filters["industry"])

        if "country" in filters and filters["country"] is not None:
            clauses.append("country = ?")
            params.append(filters["country"])

        if "employee_min" in filters and filters["employee_min"] is not None:
            clauses.append("employee_count >= ?")
            params.append(filters["employee_min"])

        if "employee_max" in filters and filters["employee_max"] is not None:
            clauses.append("employee_count <= ?")
            params.append(filters["employee_max"])

        if "ebitda_min" in filters and filters["ebitda_min"] is not None:
            clauses.append("ebitda_usd >= ?")
            params.append(filters["ebitda_min"])

        if "ebitda_max" in filters and filters["ebitda_max"] is not None:
            clauses.append("ebitda_usd <= ?")
            params.append(filters["ebitda_max"])

        if "status" in filters and filters["status"] is not None:
            clauses.append("status = ?")
            params.append(filters["status"])

        if "source_type" in filters and filters["source_type"] is not None:
            clauses.append("source_type = ?")
            params.append(filters["source_type"])

        if "min_icp_score" in filters and filters["min_icp_score"] is not None:
            clauses.append("icp_score >= ?")
            params.append(filters["min_icp_score"])

        where = " AND ".join(clauses) if clauses else "1=1"
        sql = "SELECT * FROM companies WHERE " + where + " ORDER BY name"

        async with self._connect() as conn:
            cursor = await conn.execute(sql, params)
            rows = await cursor.fetchall()
            return [self._row_to_company(r) for r in rows]

    # ------------------------------------------------------------------
    # ICP Profile Operations
    # ------------------------------------------------------------------

    async def save_icp_profile(
        self, profile_id: str, name: str, config: dict, is_default: bool = False,
    ) -> None:
        """Insert or update an ICP profile."""
        now = datetime.utcnow().isoformat()
        config_json = json.dumps(config)
        async with self._connect() as conn:
            await conn.execute(
                """INSERT INTO icp_profiles (id, name, config, is_default, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                       config = excluded.config,
                       is_default = excluded.is_default,
                       updated_at = excluded.updated_at""",
                (profile_id, name, config_json, int(is_default), now, now),
            )

    async def get_icp_profiles(self) -> list[dict]:
        """Return all ICP profiles as dicts with parsed config."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM icp_profiles ORDER BY name"
            )
            rows = await cursor.fetchall()
            results = []
            for r in rows:
                d = dict(r)
                if isinstance(d.get("config"), str):
                    try:
                        d["config"] = json.loads(d["config"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                d["is_default"] = bool(d.get("is_default", 0))
                results.append(d)
            return results

    async def delete_icp_profile(self, profile_id: str) -> None:
        """Delete an ICP profile by ID."""
        async with self._connect() as conn:
            await conn.execute(
                "DELETE FROM icp_profiles WHERE id = ?", (profile_id,)
            )

    # ------------------------------------------------------------------
    # Person Operations
    # ------------------------------------------------------------------

    async def get_person(self, person_id: str) -> Optional[Person]:
        """Get a person by ID."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM people WHERE id = ?", (person_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_person(row)

    async def upsert_person(self, person: Person) -> Person:
        """Upsert a person.

        Check existing by email first, then by (lower(first_name),
        lower(last_name), lower(company_domain)). If exists: UPDATE
        non-null fields with COALESCE. If new: INSERT.
        """
        now = datetime.utcnow().isoformat()
        source = person.source_provider.value if person.source_provider else None
        enriched = person.enriched_at.isoformat() if person.enriched_at else None
        email_status = person.email_status.value if person.email_status else "unknown"

        async with self._connect() as conn:
            existing = None

            # Check by email first
            if person.email:
                cursor = await conn.execute(
                    "SELECT * FROM people WHERE email = ?",
                    (person.email.lower(),),
                )
                existing = await cursor.fetchone()

            # Then check by name + domain
            if existing is None and person.first_name and person.last_name and person.company_domain:
                cursor = await conn.execute(
                    """SELECT * FROM people
                       WHERE lower(first_name) = ? AND lower(last_name) = ?
                       AND lower(company_domain) = ?""",
                    (
                        person.first_name.lower(),
                        person.last_name.lower(),
                        person.company_domain.lower(),
                    ),
                )
                existing = await cursor.fetchone()

            if existing:
                existing_id = existing["id"]
                await conn.execute(
                    """UPDATE people SET
                        first_name = COALESCE(?, first_name),
                        last_name = COALESCE(?, last_name),
                        full_name = COALESCE(?, full_name),
                        title = COALESCE(?, title),
                        seniority = COALESCE(?, seniority),
                        department = COALESCE(?, department),
                        company_id = COALESCE(?, company_id),
                        company_name = COALESCE(?, company_name),
                        company_domain = COALESCE(?, company_domain),
                        email = COALESCE(?, email),
                        email_status = CASE WHEN ? != 'unknown' THEN ? ELSE email_status END,
                        personal_email = COALESCE(?, personal_email),
                        phone = COALESCE(?, phone),
                        mobile_phone = COALESCE(?, mobile_phone),
                        linkedin_url = COALESCE(?, linkedin_url),
                        city = COALESCE(?, city),
                        state = COALESCE(?, state),
                        country = COALESCE(?, country),
                        source_provider = COALESCE(?, source_provider),
                        apollo_id = COALESCE(?, apollo_id),
                        enriched_at = COALESCE(?, enriched_at),
                        updated_at = ?
                    WHERE id = ?""",
                    (
                        person.first_name, person.last_name, person.full_name,
                        person.title, person.seniority, person.department,
                        person.company_id, person.company_name, person.company_domain,
                        person.email, email_status, email_status,
                        person.personal_email, person.phone, person.mobile_phone,
                        person.linkedin_url, person.city, person.state, person.country,
                        source, person.apollo_id, enriched, now, existing_id,
                    ),
                )
                cursor = await conn.execute(
                    "SELECT * FROM people WHERE id = ?", (existing_id,)
                )
                row = await cursor.fetchone()
                return self._row_to_person(row)
            else:
                # INSERT new person
                person_id = person.id
                await conn.execute(
                    """INSERT INTO people
                       (id, first_name, last_name, full_name, title, seniority,
                        department, company_id, company_name, company_domain,
                        email, email_status, personal_email, phone, mobile_phone,
                        linkedin_url, city, state, country, source_provider,
                        apollo_id, enriched_at, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        person_id, person.first_name, person.last_name, person.full_name,
                        person.title, person.seniority, person.department,
                        person.company_id, person.company_name, person.company_domain,
                        person.email, email_status, person.personal_email,
                        person.phone, person.mobile_phone, person.linkedin_url,
                        person.city, person.state, person.country,
                        source, person.apollo_id, enriched, now, now,
                    ),
                )
                cursor = await conn.execute(
                    "SELECT * FROM people WHERE id = ?", (person_id,)
                )
                row = await cursor.fetchone()
                return self._row_to_person(row)

    async def get_person_by_email(self, email: str) -> Optional[Person]:
        """Fetch a person by email address."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM people WHERE email = ?", (email.strip().lower(),)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_person(row)

    async def get_person_by_name_domain(
        self, first_name: str, last_name: str, domain: str,
    ) -> Optional[Person]:
        """Fetch a person by (first_name, last_name, company_domain)."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                """SELECT * FROM people
                   WHERE lower(first_name) = ? AND lower(last_name) = ?
                   AND lower(company_domain) = ?""",
                (first_name.strip().lower(), last_name.strip().lower(), domain.strip().lower()),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_person(row)

    async def get_persons_by_name_domain_batch(
        self, lookups: list[tuple[str, str, str]],
    ) -> dict[tuple[str, str, str], Person]:
        """Batch lookup persons by (first_name, last_name, domain).

        Returns a dict mapping each matching (first, last, domain) key
        (all lowered/stripped) to the corresponding Person object.
        Only persons with a non-null email are included.
        """
        if not lookups:
            return {}

        results: dict[tuple[str, str, str], Person] = {}
        async with self._connect() as conn:
            # Normalise keys and build OR conditions in batches of 50
            # to stay well within SQLite's variable limit.
            normalised = [
                (fn.strip().lower(), ln.strip().lower(), d.strip().lower())
                for fn, ln, d in lookups
            ]
            batch_size = 50
            for i in range(0, len(normalised), batch_size):
                batch = normalised[i : i + batch_size]
                conditions = []
                params: list[str] = []
                for fn, ln, d in batch:
                    conditions.append(
                        "(lower(first_name) = ? AND lower(last_name) = ? AND lower(company_domain) = ?)"
                    )
                    params.extend([fn, ln, d])
                where_clause = " OR ".join(conditions)
                cursor = await conn.execute(
                    f"SELECT * FROM people WHERE email IS NOT NULL AND ({where_clause})",
                    params,
                )
                rows = await cursor.fetchall()
                for row in rows:
                    person = self._row_to_person(row)
                    key = (
                        (person.first_name or "").strip().lower(),
                        (person.last_name or "").strip().lower(),
                        (person.company_domain or "").strip().lower(),
                    )
                    results[key] = person
        return results

    async def search_people(self, **filters) -> list[Person]:
        """Search people with dynamic filters.

        Supported filters: company_domain, email_status, has_email (bool), country.
        """
        clauses: list[str] = []
        params: list = []

        if "company_domain" in filters and filters["company_domain"] is not None:
            clauses.append("company_domain = ?")
            params.append(filters["company_domain"].lower())

        if "email_status" in filters and filters["email_status"] is not None:
            status_val = filters["email_status"]
            if isinstance(status_val, VerificationStatus):
                status_val = status_val.value
            clauses.append("email_status = ?")
            params.append(status_val)

        if "has_email" in filters and filters["has_email"] is not None:
            if filters["has_email"]:
                clauses.append("email IS NOT NULL AND email != ''")
            else:
                clauses.append("(email IS NULL OR email = '')")

        if "country" in filters and filters["country"] is not None:
            clauses.append("country = ?")
            params.append(filters["country"])

        where = " AND ".join(clauses) if clauses else "1=1"
        sql = "SELECT * FROM people WHERE " + where + " ORDER BY full_name"

        async with self._connect() as conn:
            cursor = await conn.execute(sql, params)
            rows = await cursor.fetchall()
            return [self._row_to_person(r) for r in rows]

    # ------------------------------------------------------------------
    # Campaign Operations
    # ------------------------------------------------------------------

    async def create_campaign(self, campaign: Campaign) -> Campaign:
        """Insert a new campaign."""
        now = datetime.utcnow().isoformat()
        enrichment_types_json = json.dumps([e.value for e in campaign.enrichment_types])
        waterfall_json = json.dumps([p.value for p in campaign.waterfall_order])
        column_mapping_json = json.dumps(campaign.column_mapping)
        cost_by_provider_json = json.dumps(campaign.cost_by_provider)
        started = campaign.started_at.isoformat() if campaign.started_at else None
        completed = campaign.completed_at.isoformat() if campaign.completed_at else None

        async with self._connect() as conn:
            await conn.execute(
                """INSERT INTO campaigns
                   (id, name, description, input_file, input_row_count,
                    enrichment_types, waterfall_order, column_mapping, status,
                    total_rows, enriched_rows, found_rows, failed_rows, skipped_rows,
                    total_credits_used, estimated_cost_usd, cost_by_provider,
                    created_at, started_at, completed_at, created_by, last_processed_row)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    campaign.id, campaign.name, campaign.description,
                    campaign.input_file, campaign.input_row_count,
                    enrichment_types_json, waterfall_json, column_mapping_json,
                    campaign.status.value, campaign.total_rows,
                    campaign.enriched_rows, campaign.found_rows,
                    campaign.failed_rows, campaign.skipped_rows,
                    campaign.total_credits_used, campaign.estimated_cost_usd,
                    cost_by_provider_json, now, started, completed,
                    campaign.created_by, campaign.last_processed_row,
                ),
            )
            cursor = await conn.execute(
                "SELECT * FROM campaigns WHERE id = ?", (campaign.id,)
            )
            row = await cursor.fetchone()
            return self._row_to_campaign(row)

    async def update_campaign_status(self, campaign_id: str, status: CampaignStatus, **kwargs) -> None:
        """Update campaign status plus any extra fields."""
        now = datetime.utcnow().isoformat()
        status_val = status.value if isinstance(status, CampaignStatus) else status

        sets = ["status = ?"]
        params: list = [status_val]

        # Automatically set timestamps based on status
        if status_val == CampaignStatus.RUNNING.value:
            sets.append("started_at = COALESCE(started_at, ?)")
            params.append(now)
        elif status_val in (CampaignStatus.COMPLETED.value, CampaignStatus.FAILED.value, CampaignStatus.CANCELLED.value):
            sets.append("completed_at = ?")
            params.append(now)

        # Handle arbitrary extra fields — whitelist maps Python names to SQL columns
        _ALLOWED_COLUMNS = {
            "enriched_rows": "enriched_rows = ?",
            "found_rows": "found_rows = ?",
            "failed_rows": "failed_rows = ?",
            "skipped_rows": "skipped_rows = ?",
            "total_credits_used": "total_credits_used = ?",
            "estimated_cost_usd": "estimated_cost_usd = ?",
            "last_processed_row": "last_processed_row = ?",
            "total_rows": "total_rows = ?",
            "cost_by_provider": "cost_by_provider = ?",
        }
        for key, value in kwargs.items():
            col_clause = _ALLOWED_COLUMNS.get(key)
            if col_clause is not None:
                sets.append(col_clause)
                params.append(json.dumps(value) if key == "cost_by_provider" else value)

        params.append(campaign_id)
        sql = "UPDATE campaigns SET " + ", ".join(sets) + " WHERE id = ?"

        async with self._connect() as conn:
            await conn.execute(sql, params)

    async def get_campaign(self, campaign_id: str) -> Optional[Campaign]:
        """Fetch a single campaign by ID."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM campaigns WHERE id = ?", (campaign_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_campaign(row)

    async def get_recent_campaigns(self, limit: int = 10) -> list[Campaign]:
        """Get recent campaigns ordered by created_at DESC."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM campaigns ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            rows = await cursor.fetchall()
            return [self._row_to_campaign(r) for r in rows]

    # ------------------------------------------------------------------
    # Campaign Row Operations
    # ------------------------------------------------------------------

    async def create_campaign_rows(self, campaign_id: str, rows: list[dict]) -> None:
        """Bulk insert campaign rows using executemany for performance."""
        if not rows:
            return
        values_list = [
            (str(uuid.uuid4()), campaign_id, i + 1, json.dumps(row_data))
            for i, row_data in enumerate(rows)
        ]
        async with self._connect() as conn:
            await conn.executemany(
                """INSERT INTO campaign_rows
                   (id, campaign_id, row_number, input_data, status)
                   VALUES (?, ?, ?, ?, 'pending')""",
                values_list,
            )

    async def update_campaign_row(
        self, row_id: str, status: str, person_id: str = None, error: str = None
    ) -> None:
        """Update a single campaign row's status and optional fields."""
        now = datetime.utcnow().isoformat()
        async with self._connect() as conn:
            await conn.execute(
                """UPDATE campaign_rows SET
                    status = ?,
                    person_id = COALESCE(?, person_id),
                    error_message = ?,
                    processed_at = ?
                   WHERE id = ?""",
                (status, person_id, error, now, row_id),
            )

    async def get_pending_rows(self, campaign_id: str, limit: int = 100) -> list[dict]:
        """Get pending rows for a campaign."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                """SELECT * FROM campaign_rows
                   WHERE campaign_id = ? AND status = 'pending'
                   ORDER BY row_number
                   LIMIT ?""",
                (campaign_id, limit),
            )
            rows = await cursor.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                if isinstance(d.get("input_data"), str):
                    try:
                        d["input_data"] = json.loads(d["input_data"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                result.append(d)
            return result

    async def get_failed_rows(self, campaign_id: str, limit: int = 100) -> list[dict]:
        """Get failed rows for a campaign (for retry on resume)."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                """SELECT * FROM campaign_rows
                   WHERE campaign_id = ? AND status = 'failed'
                   ORDER BY row_number
                   LIMIT ?""",
                (campaign_id, limit),
            )
            rows = await cursor.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                if isinstance(d.get("input_data"), str):
                    try:
                        d["input_data"] = json.loads(d["input_data"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                result.append(d)
            return result

    async def get_campaign_row_stats(self, campaign_id: str) -> dict:
        """Get per-status counts for a campaign's rows."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                """SELECT status, COUNT(*) as cnt
                   FROM campaign_rows
                   WHERE campaign_id = ?
                   GROUP BY status""",
                (campaign_id,),
            )
            rows = await cursor.fetchall()
            stats = {"pending": 0, "processing": 0, "complete": 0, "failed": 0}
            for r in rows:
                stats[r["status"]] = r["cnt"]
            return stats

    async def reset_stuck_rows(self, campaign_id: str) -> int:
        """Reset rows stuck in 'processing' back to 'pending'. Returns count."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                "UPDATE campaign_rows SET status = 'pending', processed_at = NULL "
                "WHERE campaign_id = ? AND status = 'processing'",
                (campaign_id,),
            )
            return cursor.rowcount

    # ------------------------------------------------------------------
    # Enrichment Results
    # ------------------------------------------------------------------

    async def save_enrichment_result(self, result: EnrichmentResult) -> None:
        """Insert an enrichment result."""
        async with self._connect() as conn:
            await conn.execute(
                """INSERT INTO enrichment_results
                   (id, person_id, company_id, campaign_id, enrichment_type,
                    query_input, source_provider, result_data, found,
                    confidence_score, verification_status, cost_credits,
                    cost_usd, response_time_ms, found_at, waterfall_position,
                    from_cache)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.id, result.person_id, result.company_id,
                    result.campaign_id, result.enrichment_type.value,
                    json.dumps(result.query_input), result.source_provider.value,
                    json.dumps(result.result_data), int(result.found),
                    result.confidence_score, result.verification_status.value,
                    result.cost_credits, result.cost_usd, result.response_time_ms,
                    result.found_at.isoformat() if result.found_at else None,
                    result.waterfall_position, int(result.from_cache),
                ),
            )

    async def save_enrichment_atomic(
        self,
        result: EnrichmentResult,
        provider: str,
        credits: float,
        found: bool,
    ) -> None:
        """Save enrichment result and record credit usage in one transaction.

        Uses BEGIN IMMEDIATE to prevent concurrent budget races.
        """
        today = date.today().isoformat()
        prov = provider if isinstance(provider, str) else provider.value
        usage_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        async with self._connect() as conn:
            await conn.execute("BEGIN IMMEDIATE")

            # 1. Record credit usage
            await conn.execute(
                """INSERT INTO credit_usage
                   (id, provider, date, credits_used, api_calls_made,
                    successful_lookups, failed_lookups, updated_at)
                   VALUES (?, ?, ?, ?, 1, ?, ?, ?)
                   ON CONFLICT(provider, date) DO UPDATE SET
                       credits_used = credit_usage.credits_used + excluded.credits_used,
                       api_calls_made = credit_usage.api_calls_made + 1,
                       successful_lookups = credit_usage.successful_lookups + excluded.successful_lookups,
                       failed_lookups = credit_usage.failed_lookups + excluded.failed_lookups,
                       updated_at = excluded.updated_at""",
                (usage_id, prov, today, credits,
                 1 if found else 0, 0 if found else 1, now),
            )

            # 2. Save enrichment result
            await conn.execute(
                """INSERT INTO enrichment_results
                   (id, person_id, company_id, campaign_id, enrichment_type,
                    query_input, source_provider, result_data, found,
                    confidence_score, verification_status, cost_credits,
                    cost_usd, response_time_ms, found_at, waterfall_position,
                    from_cache)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.id, result.person_id, result.company_id,
                    result.campaign_id, result.enrichment_type.value,
                    json.dumps(result.query_input), result.source_provider.value,
                    json.dumps(result.result_data), int(result.found),
                    result.confidence_score, result.verification_status.value,
                    result.cost_credits, result.cost_usd, result.response_time_ms,
                    result.found_at.isoformat() if result.found_at else None,
                    result.waterfall_position, int(result.from_cache),
                ),
            )
            # conn auto-commits on context manager exit

    async def get_enrichment_results(self, **filters) -> list[EnrichmentResult]:
        """Search enrichment results with dynamic filters.

        Supported filters: campaign_id, person_id, source_provider, found.
        """
        clauses: list[str] = []
        params: list = []

        if "campaign_id" in filters and filters["campaign_id"] is not None:
            clauses.append("campaign_id = ?")
            params.append(filters["campaign_id"])

        if "person_id" in filters and filters["person_id"] is not None:
            clauses.append("person_id = ?")
            params.append(filters["person_id"])

        if "source_provider" in filters and filters["source_provider"] is not None:
            prov = filters["source_provider"]
            if isinstance(prov, ProviderName):
                prov = prov.value
            clauses.append("source_provider = ?")
            params.append(prov)

        if "found" in filters and filters["found"] is not None:
            clauses.append("found = ?")
            params.append(int(filters["found"]))

        where = " AND ".join(clauses) if clauses else "1=1"
        sql = "SELECT * FROM enrichment_results WHERE " + where + " ORDER BY found_at DESC"

        async with self._connect() as conn:
            cursor = await conn.execute(sql, params)
            rows = await cursor.fetchall()
            return [self._row_to_enrichment_result(r) for r in rows]

    # ------------------------------------------------------------------
    # Credit Usage
    # ------------------------------------------------------------------

    async def record_credit_usage(self, provider: str, credits: float, found: bool) -> None:
        """Upsert credit usage for today's date."""
        today = date.today().isoformat()
        prov = provider if isinstance(provider, str) else provider.value
        usage_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        async with self._connect() as conn:
            await conn.execute(
                """INSERT INTO credit_usage
                   (id, provider, date, credits_used, api_calls_made,
                    successful_lookups, failed_lookups, updated_at)
                   VALUES (?, ?, ?, ?, 1, ?, ?, ?)
                   ON CONFLICT(provider, date) DO UPDATE SET
                    credits_used = credit_usage.credits_used + excluded.credits_used,
                    api_calls_made = credit_usage.api_calls_made + 1,
                    successful_lookups = credit_usage.successful_lookups + excluded.successful_lookups,
                    failed_lookups = credit_usage.failed_lookups + excluded.failed_lookups,
                    updated_at = excluded.updated_at""",
                (
                    usage_id, prov, today, credits,
                    1 if found else 0,
                    0 if found else 1,
                    now,
                ),
            )

    async def get_credit_usage(self, provider: str, days: int = 30) -> list[dict]:
        """Get daily credit usage for last N days."""
        prov = provider if isinstance(provider, str) else provider.value
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        async with self._connect() as conn:
            cursor = await conn.execute(
                """SELECT * FROM credit_usage
                   WHERE provider = ? AND date >= ?
                   ORDER BY date DESC""",
                (prov, cutoff),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_daily_usage(self, provider: str, date_str: str) -> dict:
        """Get credit usage for a specific provider and date."""
        prov = provider if isinstance(provider, str) else provider.value

        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM credit_usage WHERE provider = ? AND date = ?",
                (prov, date_str),
            )
            row = await cursor.fetchone()
            if row is None:
                return {
                    "provider": prov,
                    "date": date_str,
                    "credits_used": 0.0,
                    "api_calls_made": 0,
                    "successful_lookups": 0,
                    "failed_lookups": 0,
                }
            return dict(row)

    # ------------------------------------------------------------------
    # Email Patterns
    # ------------------------------------------------------------------

    async def get_domain_patterns(self, domain: str) -> list[dict]:
        """Return all email patterns for a domain."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM email_patterns WHERE domain = ? ORDER BY confidence DESC",
                (domain.lower(),),
            )
            rows = await cursor.fetchall()
            results = []
            for r in rows:
                d = dict(r)
                if isinstance(d.get("examples"), str):
                    try:
                        d["examples"] = json.loads(d["examples"])
                    except (json.JSONDecodeError, TypeError):
                        d["examples"] = []
                results.append(d)
            return results

    async def record_pattern(
        self, domain: str, pattern: str, email: str, confidence: float
    ) -> None:
        """Upsert an email pattern, increment sample_count, append to examples."""
        domain = domain.lower()
        pattern_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM email_patterns WHERE domain = ? AND pattern = ?",
                (domain, pattern),
            )
            existing = await cursor.fetchone()

            if existing:
                # Update existing: increment sample_count, append example, update confidence
                examples = []
                if existing["examples"]:
                    try:
                        examples = json.loads(existing["examples"])
                    except (json.JSONDecodeError, TypeError):
                        examples = []

                if email not in examples:
                    examples.append(email)

                await conn.execute(
                    """UPDATE email_patterns SET
                        confidence = ?,
                        sample_count = sample_count + 1,
                        examples = ?,
                        updated_at = ?
                       WHERE id = ?""",
                    (confidence, json.dumps(examples), now, existing["id"]),
                )
            else:
                await conn.execute(
                    """INSERT INTO email_patterns
                       (id, domain, pattern, confidence, sample_count, examples,
                        discovered_at, updated_at)
                       VALUES (?, ?, ?, ?, 1, ?, ?, ?)""",
                    (
                        pattern_id, domain, pattern, confidence,
                        json.dumps([email]), now, now,
                    ),
                )

    async def deduplicate_patterns(self) -> int:
        """Remove duplicate email patterns per domain.

        Keeps the row with the highest sample_count for each
        (domain, pattern) pair and deletes the rest.  Returns the
        number of rows deleted.  The UNIQUE(domain, pattern) constraint
        prevents future duplicates, but this cleans up any legacy data.
        """
        async with self._connect() as conn:
            cursor = await conn.execute(
                """DELETE FROM email_patterns
                   WHERE id NOT IN (
                       SELECT id FROM (
                           SELECT id, ROW_NUMBER() OVER (
                               PARTITION BY domain, pattern
                               ORDER BY sample_count DESC, updated_at DESC
                           ) AS rn
                           FROM email_patterns
                       ) WHERE rn = 1
                   )"""
            )
            return cursor.rowcount

    # ------------------------------------------------------------------
    # Catch-All Cache
    # ------------------------------------------------------------------

    async def get_catch_all_status(self, domain: str) -> Optional[bool]:
        """Check domain_catch_all table. Return None if not checked or expired >90 days."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM domain_catch_all WHERE domain = ?",
                (domain.lower(),),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            # Check if expired (>90 days)
            checked_at = row["checked_at"]
            if checked_at:
                try:
                    checked_dt = datetime.fromisoformat(checked_at)
                    if datetime.utcnow() - checked_dt > timedelta(days=90):
                        return None
                except (ValueError, TypeError):
                    pass
            return bool(row["is_catch_all"])

    async def set_catch_all_status(self, domain: str, is_catch_all: bool) -> None:
        """Set or update catch-all status for a domain."""
        now = datetime.utcnow().isoformat()
        async with self._connect() as conn:
            await conn.execute(
                """INSERT OR REPLACE INTO domain_catch_all
                   (domain, is_catch_all, checked_at)
                   VALUES (?, ?, ?)""",
                (domain.lower(), int(is_catch_all), now),
            )

    # ------------------------------------------------------------------
    # Dashboard Stats
    # ------------------------------------------------------------------

    async def get_dashboard_stats(self) -> dict:
        """Single query returning dashboard statistics."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM people WHERE email IS NOT NULL AND email != ''"
            )
            total_enriched = (await cursor.fetchone())[0]

            cursor = await conn.execute("SELECT COUNT(*) FROM people")
            total_people = (await cursor.fetchone())[0]
            email_find_rate = (
                round(total_enriched / total_people * 100, 1) if total_people > 0 else 0.0
            )

            cursor = await conn.execute("SELECT COUNT(*) FROM campaigns")
            total_campaigns = (await cursor.fetchone())[0]

            cutoff = (date.today() - timedelta(days=30)).isoformat()
            cursor = await conn.execute(
                "SELECT COALESCE(SUM(credits_used), 0.0) FROM credit_usage WHERE date >= ?",
                (cutoff,),
            )
            cost_30d = (await cursor.fetchone())[0]

            return {
                "total_enriched": total_enriched,
                "email_find_rate": email_find_rate,
                "total_campaigns": total_campaigns,
                "cost_30d": cost_30d,
            }

    # ------------------------------------------------------------------
    # Audit Log
    # ------------------------------------------------------------------

    async def log_action(
        self,
        action: str,
        entity_type: str = None,
        entity_id: str = None,
        details: dict = None,
        user_id: str = None,
    ) -> None:
        """Write an entry to the audit log."""
        async with self._connect() as conn:
            await conn.execute(
                """INSERT INTO audit_log
                   (user_id, action, entity_type, entity_id, details)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    user_id,
                    action,
                    entity_type,
                    entity_id,
                    json.dumps(details) if details else "{}",
                ),
            )

    # ------------------------------------------------------------------
    # Provider Domain Stats
    # ------------------------------------------------------------------

    async def record_provider_domain_attempt(
        self, provider: str, domain: str, hit: bool,
    ) -> None:
        """Record a provider attempt for a domain (hit or miss)."""
        async with self._connect() as conn:
            await conn.execute(
                """INSERT INTO provider_domain_stats
                   (provider, domain, attempts, hits, last_attempt)
                   VALUES (?, ?, 1, ?, ?)
                   ON CONFLICT(provider, domain) DO UPDATE SET
                       attempts = provider_domain_stats.attempts + 1,
                       hits = provider_domain_stats.hits + ?,
                       last_attempt = ?""",
                (
                    provider.lower(),
                    domain.lower(),
                    int(hit),
                    datetime.utcnow().isoformat(),
                    int(hit),
                    datetime.utcnow().isoformat(),
                ),
            )

    async def should_skip_provider_for_domain(
        self,
        provider: str,
        domain: str,
        min_attempts: int = 5,
    ) -> bool:
        """Return True if the provider has 0 hits over min_attempts for this domain."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                """SELECT attempts, hits FROM provider_domain_stats
                   WHERE provider = ? AND domain = ?""",
                (provider.lower(), domain.lower()),
            )
            row = await cursor.fetchone()
            if row is None:
                return False
            return row["attempts"] >= min_attempts and row["hits"] == 0

    # ------------------------------------------------------------------
    # Email Template Operations
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_email_template(row) -> EmailTemplate:
        """Convert a Row to an EmailTemplate model."""
        d = dict(row)
        d["is_default"] = bool(d.get("is_default", False))
        return EmailTemplate.model_validate(d)

    @staticmethod
    def _row_to_generated_email(row) -> GeneratedEmail:
        """Convert a Row to a GeneratedEmail model."""
        d = dict(row)
        return GeneratedEmail.model_validate(d)

    async def save_email_template(self, template: EmailTemplate) -> EmailTemplate:
        """Insert or replace an email template."""
        now = datetime.utcnow().isoformat()
        async with self._connect() as conn:
            await conn.execute(
                """INSERT OR REPLACE INTO email_templates
                   (id, name, description, system_prompt, user_prompt_template,
                    sequence_step, is_default, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    template.id,
                    template.name,
                    template.description,
                    template.system_prompt,
                    template.user_prompt_template,
                    template.sequence_step,
                    int(template.is_default),
                    template.created_at.isoformat() if template.created_at else now,
                    now,
                ),
            )
        return template

    async def get_email_templates(self) -> list[EmailTemplate]:
        """Return all email templates."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM email_templates ORDER BY sequence_step, name"
            )
            rows = await cursor.fetchall()
            return [self._row_to_email_template(r) for r in rows]

    async def get_email_template(self, template_id: str) -> Optional[EmailTemplate]:
        """Return a single email template by ID."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM email_templates WHERE id = ?", (template_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_email_template(row)

    async def delete_email_template(self, template_id: str) -> None:
        """Delete an email template by ID."""
        async with self._connect() as conn:
            await conn.execute(
                "DELETE FROM email_templates WHERE id = ?", (template_id,)
            )

    # ------------------------------------------------------------------
    # Generated Email Operations
    # ------------------------------------------------------------------

    async def save_generated_email(self, email: GeneratedEmail) -> GeneratedEmail:
        """Insert or replace a generated email."""
        now = datetime.utcnow().isoformat()
        async with self._connect() as conn:
            await conn.execute(
                """INSERT OR REPLACE INTO generated_emails
                   (id, campaign_id, template_id, person_id, company_id,
                    sequence_step, subject, body, status, user_note,
                    input_tokens, output_tokens, cost_usd, generated_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    email.id,
                    email.campaign_id,
                    email.template_id,
                    email.person_id,
                    email.company_id,
                    email.sequence_step,
                    email.subject,
                    email.body,
                    email.status,
                    email.user_note,
                    email.input_tokens,
                    email.output_tokens,
                    email.cost_usd,
                    email.generated_at.isoformat() if email.generated_at else now,
                    now,
                ),
            )
        return email

    async def get_generated_emails(
        self, campaign_id: str, status: Optional[str] = None,
    ) -> list[GeneratedEmail]:
        """Return generated emails for a campaign, optionally filtered by status."""
        if status:
            query = "SELECT * FROM generated_emails WHERE campaign_id = ? AND status = ? ORDER BY generated_at"
            params: tuple = (campaign_id, status)
        else:
            query = "SELECT * FROM generated_emails WHERE campaign_id = ? ORDER BY generated_at"
            params = (campaign_id,)
        async with self._connect() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            return [self._row_to_generated_email(r) for r in rows]

    async def update_email_status(self, email_id: str, status: str) -> None:
        """Update the status of a generated email."""
        now = datetime.utcnow().isoformat()
        async with self._connect() as conn:
            await conn.execute(
                "UPDATE generated_emails SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, email_id),
            )

    async def update_email_content(
        self, email_id: str, subject: str, body: str,
    ) -> None:
        """Update the subject and body of a generated email (inline edit)."""
        now = datetime.utcnow().isoformat()
        async with self._connect() as conn:
            await conn.execute(
                "UPDATE generated_emails SET subject = ?, body = ?, updated_at = ? WHERE id = ?",
                (subject, body, now, email_id),
            )

    async def seed_default_templates(self) -> None:
        """Insert default starter templates if none with is_default=True exist."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM email_templates WHERE is_default = 1"
            )
            count = (await cursor.fetchone())[0]
            if count > 0:
                return

        # Import here to avoid circular imports
        from data.email_engine import STARTER_TEMPLATES
        for tmpl in STARTER_TEMPLATES:
            await self.save_email_template(tmpl)

    async def get_person_with_company(
        self, person_id: str,
    ) -> tuple[Person, Optional[Company]]:
        """Return a person and their associated company (if any).

        Looks up company via company_id first, then falls back to
        company_domain lookup.
        """
        person = await self.get_person(person_id)
        if person is None:
            raise ValueError(f"Person not found: {person_id}")

        company = None
        if person.company_id:
            async with self._connect() as conn:
                cursor = await conn.execute(
                    "SELECT * FROM companies WHERE id = ?", (person.company_id,)
                )
                row = await cursor.fetchone()
                if row:
                    company = self._row_to_company(row)
        if company is None and person.company_domain:
            company = await self.get_company_by_domain(person.company_domain)

        return person, company
