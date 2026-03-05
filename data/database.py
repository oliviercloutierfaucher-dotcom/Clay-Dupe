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
)

if sys.version_info < (3, 11):
    raise RuntimeError(
        f"Clay-Dupe requires Python >= 3.11, got {sys.version_info.major}.{sys.version_info.minor}"
    )


class Database:
    def __init__(self, db_path: str = "clay_dupe.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Execute schema.sql to create tables (sync — runs once at startup)."""
        schema_path = Path(__file__).parent / "schema.sql"
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(schema_path.read_text())
            conn.commit()
        finally:
            conn.close()

    @asynccontextmanager
    async def _connect(self):
        """Async context manager for DB connections. WAL mode, FK ON, busy_timeout=5000."""
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
        finally:
            await conn.close()

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
                        apollo_id, enriched_at, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        company.id, company.name, company.domain, company.industry,
                        industry_tags_json, company.employee_count, company.employee_range,
                        revenue, ebitda, company.founded_year,
                        company.description, company.city, company.state, company.country,
                        company.full_address, company.linkedin_url, company.website_url,
                        company.phone, source, company.apollo_id,
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

    async def search_companies(self, **filters) -> list[Company]:
        """Search companies with dynamic filters.

        Supported filters: industry, country, employee_min, employee_max,
        ebitda_min, ebitda_max.
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

        where = " AND ".join(clauses) if clauses else "1=1"
        sql = "SELECT * FROM companies WHERE " + where + " ORDER BY name"

        async with self._connect() as conn:
            cursor = await conn.execute(sql, params)
            rows = await cursor.fetchall()
            return [self._row_to_company(r) for r in rows]

    # ------------------------------------------------------------------
    # Person Operations
    # ------------------------------------------------------------------

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
        """Bulk insert campaign rows."""
        async with self._connect() as conn:
            for i, row_data in enumerate(rows):
                row_id = str(uuid.uuid4())
                await conn.execute(
                    """INSERT INTO campaign_rows
                       (id, campaign_id, row_number, input_data, status)
                       VALUES (?, ?, ?, ?, 'pending')""",
                    (row_id, campaign_id, i + 1, json.dumps(row_data)),
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
