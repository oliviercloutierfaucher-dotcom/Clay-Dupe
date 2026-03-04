"""SQLite database manager — central data access layer.

Uses WAL mode for concurrent reads and provides all CRUD operations
for companies, people, campaigns, enrichment results, credits, cache,
email patterns, catch-all status, audit logging, and dashboard stats.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional

from config.settings import ProviderName
from data.models import (
    Company, Person, EnrichmentResult, Campaign, CreditUsage,
    CacheEntry, EmailPattern, EnrichmentType, VerificationStatus, CampaignStatus,
)


class Database:
    def __init__(self, db_path: str = "clay_dupe.db"):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _connect(self):
        """Context manager for DB connections. WAL mode, FK ON, busy_timeout=5000."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Execute schema.sql to create tables."""
        schema_path = Path(__file__).parent / "schema.sql"
        with self._connect() as conn:
            conn.executescript(schema_path.read_text())

    # ------------------------------------------------------------------
    # Helpers: Row -> Model conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_company(row: sqlite3.Row) -> Company:
        """Convert an sqlite3.Row to a Company model."""
        d = dict(row)
        # Deserialize JSON fields
        if isinstance(d.get("industry_tags"), str):
            try:
                d["industry_tags"] = json.loads(d["industry_tags"])
            except (json.JSONDecodeError, TypeError):
                d["industry_tags"] = []
        return Company.model_validate(d)

    @staticmethod
    def _row_to_person(row: sqlite3.Row) -> Person:
        """Convert an sqlite3.Row to a Person model."""
        d = dict(row)
        return Person.model_validate(d)

    @staticmethod
    def _row_to_campaign(row: sqlite3.Row) -> Campaign:
        """Convert an sqlite3.Row to a Campaign model."""
        d = dict(row)
        for field in ("enrichment_types", "waterfall_order", "column_mapping", "cost_by_provider"):
            if isinstance(d.get(field), str):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return Campaign.model_validate(d)

    @staticmethod
    def _row_to_enrichment_result(row: sqlite3.Row) -> EnrichmentResult:
        """Convert an sqlite3.Row to an EnrichmentResult model."""
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

    def cache_get(self, provider: str, enrichment_type: str, query_input: dict) -> Optional[dict]:
        """Return cached response if not expired, increment hit_count."""
        cache_key = self._make_cache_key(provider, enrichment_type, query_input)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM cache WHERE cache_key = ? AND expires_at > CURRENT_TIMESTAMP",
                (cache_key,),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE cache SET hit_count = hit_count + 1 WHERE cache_key = ?",
                (cache_key,),
            )
            try:
                return json.loads(row["response_data"])
            except (json.JSONDecodeError, TypeError):
                return {}

    def cache_set(
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

        with self._connect() as conn:
            conn.execute(
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

    def cache_purge_expired(self) -> int:
        """Delete expired entries, return count deleted."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM cache WHERE expires_at < CURRENT_TIMESTAMP"
            )
            return cursor.rowcount

    # ------------------------------------------------------------------
    # Company Operations
    # ------------------------------------------------------------------

    def upsert_company(self, company: Company) -> Company:
        """ON CONFLICT(domain) DO UPDATE with COALESCE for all fields."""
        now = datetime.utcnow().isoformat()
        industry_tags_json = json.dumps(company.industry_tags)
        revenue = float(company.revenue_usd) if company.revenue_usd is not None else None
        ebitda = float(company.ebitda_usd) if company.ebitda_usd is not None else None
        source = company.source_provider.value if company.source_provider else None
        enriched = company.enriched_at.isoformat() if company.enriched_at else None

        with self._connect() as conn:
            conn.execute(
                """INSERT INTO companies
                   (id, name, domain, industry, industry_tags, employee_count,
                    employee_range, revenue_usd, ebitda_usd, founded_year,
                    description, city, state, country, full_address,
                    linkedin_url, website_url, phone, source_provider,
                    apollo_id, enriched_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(domain) DO UPDATE SET
                    name = COALESCE(excluded.name, companies.name),
                    industry = COALESCE(excluded.industry, companies.industry),
                    industry_tags = CASE
                        WHEN excluded.industry_tags IS NOT NULL AND excluded.industry_tags != '[]'
                        THEN excluded.industry_tags
                        ELSE companies.industry_tags
                    END,
                    employee_count = COALESCE(excluded.employee_count, companies.employee_count),
                    employee_range = COALESCE(excluded.employee_range, companies.employee_range),
                    revenue_usd = COALESCE(excluded.revenue_usd, companies.revenue_usd),
                    ebitda_usd = COALESCE(excluded.ebitda_usd, companies.ebitda_usd),
                    founded_year = COALESCE(excluded.founded_year, companies.founded_year),
                    description = COALESCE(excluded.description, companies.description),
                    city = COALESCE(excluded.city, companies.city),
                    state = COALESCE(excluded.state, companies.state),
                    country = COALESCE(excluded.country, companies.country),
                    full_address = COALESCE(excluded.full_address, companies.full_address),
                    linkedin_url = COALESCE(excluded.linkedin_url, companies.linkedin_url),
                    website_url = COALESCE(excluded.website_url, companies.website_url),
                    phone = COALESCE(excluded.phone, companies.phone),
                    source_provider = COALESCE(excluded.source_provider, companies.source_provider),
                    apollo_id = COALESCE(excluded.apollo_id, companies.apollo_id),
                    enriched_at = COALESCE(excluded.enriched_at, companies.enriched_at),
                    updated_at = excluded.updated_at""",
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
            # Fetch the final row (may have merged fields from existing record)
            if company.domain:
                row = conn.execute(
                    "SELECT * FROM companies WHERE domain = ?", (company.domain,)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM companies WHERE id = ?", (company.id,)
                ).fetchone()
            return self._row_to_company(row)

    def get_company_by_domain(self, domain: str) -> Optional[Company]:
        """Fetch a company by its domain."""
        domain = domain.strip().lower()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM companies WHERE domain = ?", (domain,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_company(row)

    def search_companies(self, **filters) -> list[Company]:
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
        sql = f"SELECT * FROM companies WHERE {where} ORDER BY name"

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_company(r) for r in rows]

    # ------------------------------------------------------------------
    # Person Operations
    # ------------------------------------------------------------------

    def upsert_person(self, person: Person) -> Person:
        """Upsert a person.

        Check existing by email first, then by (lower(first_name),
        lower(last_name), lower(company_domain)). If exists: UPDATE
        non-null fields with COALESCE. If new: INSERT.
        """
        now = datetime.utcnow().isoformat()
        source = person.source_provider.value if person.source_provider else None
        enriched = person.enriched_at.isoformat() if person.enriched_at else None
        email_status = person.email_status.value if person.email_status else "unknown"

        with self._connect() as conn:
            existing = None

            # Check by email first
            if person.email:
                existing = conn.execute(
                    "SELECT * FROM people WHERE email = ?",
                    (person.email.lower(),),
                ).fetchone()

            # Then check by name + domain
            if existing is None and person.first_name and person.last_name and person.company_domain:
                existing = conn.execute(
                    """SELECT * FROM people
                       WHERE lower(first_name) = ? AND lower(last_name) = ?
                       AND lower(company_domain) = ?""",
                    (
                        person.first_name.lower(),
                        person.last_name.lower(),
                        person.company_domain.lower(),
                    ),
                ).fetchone()

            if existing:
                existing_id = existing["id"]
                conn.execute(
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
                row = conn.execute(
                    "SELECT * FROM people WHERE id = ?", (existing_id,)
                ).fetchone()
                return self._row_to_person(row)
            else:
                # INSERT new person
                person_id = person.id
                conn.execute(
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
                row = conn.execute(
                    "SELECT * FROM people WHERE id = ?", (person_id,)
                ).fetchone()
                return self._row_to_person(row)

    def get_person_by_email(self, email: str) -> Optional[Person]:
        """Fetch a person by email address."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM people WHERE email = ?", (email.strip().lower(),)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_person(row)

    def search_people(self, **filters) -> list[Person]:
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
        sql = f"SELECT * FROM people WHERE {where} ORDER BY full_name"

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_person(r) for r in rows]

    # ------------------------------------------------------------------
    # Campaign Operations
    # ------------------------------------------------------------------

    def create_campaign(self, campaign: Campaign) -> Campaign:
        """Insert a new campaign."""
        now = datetime.utcnow().isoformat()
        enrichment_types_json = json.dumps([e.value for e in campaign.enrichment_types])
        waterfall_json = json.dumps([p.value for p in campaign.waterfall_order])
        column_mapping_json = json.dumps(campaign.column_mapping)
        cost_by_provider_json = json.dumps(campaign.cost_by_provider)
        started = campaign.started_at.isoformat() if campaign.started_at else None
        completed = campaign.completed_at.isoformat() if campaign.completed_at else None

        with self._connect() as conn:
            conn.execute(
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
            row = conn.execute(
                "SELECT * FROM campaigns WHERE id = ?", (campaign.id,)
            ).fetchone()
            return self._row_to_campaign(row)

    def update_campaign_status(self, campaign_id: str, status: CampaignStatus, **kwargs) -> None:
        """Update campaign status plus any extra fields."""
        now = datetime.utcnow().isoformat()
        status_val = status.value if isinstance(status, CampaignStatus) else status

        sets = ["status = ?", "updated_at = ?"]
        params: list = [status_val, now]

        # Automatically set timestamps based on status
        if status_val == CampaignStatus.RUNNING.value:
            sets.append("started_at = COALESCE(started_at, ?)")
            params.append(now)
        elif status_val in (CampaignStatus.COMPLETED.value, CampaignStatus.FAILED.value, CampaignStatus.CANCELLED.value):
            sets.append("completed_at = ?")
            params.append(now)

        # Handle arbitrary extra fields
        allowed_fields = {
            "enriched_rows", "found_rows", "failed_rows", "skipped_rows",
            "total_credits_used", "estimated_cost_usd", "last_processed_row",
            "total_rows", "cost_by_provider",
        }
        for key, value in kwargs.items():
            if key in allowed_fields:
                if key == "cost_by_provider":
                    sets.append(f"{key} = ?")
                    params.append(json.dumps(value))
                else:
                    sets.append(f"{key} = ?")
                    params.append(value)

        params.append(campaign_id)
        sql = f"UPDATE campaigns SET {', '.join(sets)} WHERE id = ?"

        with self._connect() as conn:
            conn.execute(sql, params)

    def get_campaign(self, campaign_id: str) -> Optional[Campaign]:
        """Fetch a single campaign by ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM campaigns WHERE id = ?", (campaign_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_campaign(row)

    def get_recent_campaigns(self, limit: int = 10) -> list[Campaign]:
        """Get recent campaigns ordered by created_at DESC."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM campaigns ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [self._row_to_campaign(r) for r in rows]

    # ------------------------------------------------------------------
    # Campaign Row Operations
    # ------------------------------------------------------------------

    def create_campaign_rows(self, campaign_id: str, rows: list[dict]) -> None:
        """Bulk insert campaign rows."""
        with self._connect() as conn:
            for i, row_data in enumerate(rows):
                row_id = str(uuid.uuid4())
                conn.execute(
                    """INSERT INTO campaign_rows
                       (id, campaign_id, row_number, input_data, status)
                       VALUES (?, ?, ?, ?, 'pending')""",
                    (row_id, campaign_id, i + 1, json.dumps(row_data)),
                )

    def update_campaign_row(
        self, row_id: str, status: str, person_id: str = None, error: str = None
    ) -> None:
        """Update a single campaign row's status and optional fields."""
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """UPDATE campaign_rows SET
                    status = ?,
                    person_id = COALESCE(?, person_id),
                    error_message = ?,
                    processed_at = ?
                   WHERE id = ?""",
                (status, person_id, error, now, row_id),
            )

    def get_pending_rows(self, campaign_id: str, limit: int = 100) -> list[dict]:
        """Get pending rows for a campaign."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM campaign_rows
                   WHERE campaign_id = ? AND status = 'pending'
                   ORDER BY row_number
                   LIMIT ?""",
                (campaign_id, limit),
            ).fetchall()
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

    # ------------------------------------------------------------------
    # Enrichment Results
    # ------------------------------------------------------------------

    def save_enrichment_result(self, result: EnrichmentResult) -> None:
        """Insert an enrichment result."""
        with self._connect() as conn:
            conn.execute(
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

    def get_enrichment_results(self, **filters) -> list[EnrichmentResult]:
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
        sql = f"SELECT * FROM enrichment_results WHERE {where} ORDER BY found_at DESC"

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_enrichment_result(r) for r in rows]

    # ------------------------------------------------------------------
    # Credit Usage
    # ------------------------------------------------------------------

    def record_credit_usage(self, provider: str, credits: float, found: bool) -> None:
        """Upsert credit usage for today's date."""
        today = date.today().isoformat()
        prov = provider if isinstance(provider, str) else provider.value
        usage_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        with self._connect() as conn:
            conn.execute(
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

    def get_credit_usage(self, provider: str, days: int = 30) -> list[dict]:
        """Get daily credit usage for last N days."""
        prov = provider if isinstance(provider, str) else provider.value
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM credit_usage
                   WHERE provider = ? AND date >= ?
                   ORDER BY date DESC""",
                (prov, cutoff),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_daily_usage(self, provider: str, date_str: str) -> dict:
        """Get credit usage for a specific provider and date."""
        prov = provider if isinstance(provider, str) else provider.value

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM credit_usage WHERE provider = ? AND date = ?",
                (prov, date_str),
            ).fetchone()
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

    def get_domain_patterns(self, domain: str) -> list[dict]:
        """Return all email patterns for a domain."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM email_patterns WHERE domain = ? ORDER BY confidence DESC",
                (domain.lower(),),
            ).fetchall()
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

    def record_pattern(
        self, domain: str, pattern: str, email: str, confidence: float
    ) -> None:
        """Upsert an email pattern, increment sample_count, append to examples."""
        domain = domain.lower()
        pattern_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM email_patterns WHERE domain = ? AND pattern = ?",
                (domain, pattern),
            ).fetchone()

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

                conn.execute(
                    """UPDATE email_patterns SET
                        confidence = ?,
                        sample_count = sample_count + 1,
                        examples = ?,
                        updated_at = ?
                       WHERE id = ?""",
                    (confidence, json.dumps(examples), now, existing["id"]),
                )
            else:
                conn.execute(
                    """INSERT INTO email_patterns
                       (id, domain, pattern, confidence, sample_count, examples,
                        discovered_at, updated_at)
                       VALUES (?, ?, ?, ?, 1, ?, ?, ?)""",
                    (
                        pattern_id, domain, pattern, confidence,
                        json.dumps([email]), now, now,
                    ),
                )

    # ------------------------------------------------------------------
    # Catch-All Cache
    # ------------------------------------------------------------------

    def get_catch_all_status(self, domain: str) -> Optional[bool]:
        """Check domain_catch_all table. Return None if not checked or expired >90 days."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM domain_catch_all WHERE domain = ?",
                (domain.lower(),),
            ).fetchone()
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

    def set_catch_all_status(self, domain: str, is_catch_all: bool) -> None:
        """Set or update catch-all status for a domain."""
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO domain_catch_all
                   (domain, is_catch_all, checked_at)
                   VALUES (?, ?, ?)""",
                (domain.lower(), int(is_catch_all), now),
            )

    # ------------------------------------------------------------------
    # Dashboard Stats
    # ------------------------------------------------------------------

    def get_dashboard_stats(self) -> dict:
        """Single query returning dashboard statistics."""
        with self._connect() as conn:
            # Total enriched people (those with an email found)
            total_enriched = conn.execute(
                "SELECT COUNT(*) FROM people WHERE email IS NOT NULL AND email != ''"
            ).fetchone()[0]

            # Email find rate
            total_people = conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
            email_find_rate = (
                round(total_enriched / total_people * 100, 1) if total_people > 0 else 0.0
            )

            # Total campaigns
            total_campaigns = conn.execute(
                "SELECT COUNT(*) FROM campaigns"
            ).fetchone()[0]

            # Cost in last 30 days
            cutoff = (date.today() - timedelta(days=30)).isoformat()
            cost_row = conn.execute(
                "SELECT COALESCE(SUM(credits_used), 0.0) FROM credit_usage WHERE date >= ?",
                (cutoff,),
            ).fetchone()
            cost_30d = cost_row[0]

            return {
                "total_enriched": total_enriched,
                "email_find_rate": email_find_rate,
                "total_campaigns": total_campaigns,
                "cost_30d": cost_30d,
            }

    # ------------------------------------------------------------------
    # Audit Log
    # ------------------------------------------------------------------

    def log_action(
        self,
        action: str,
        entity_type: str = None,
        entity_id: str = None,
        details: dict = None,
        user_id: str = None,
    ) -> None:
        """Write an entry to the audit log."""
        with self._connect() as conn:
            conn.execute(
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
