-- Clay-Dupe schema — Wave 1B
-- Full SQLite DDL: tables, indexes, triggers.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ============================================================
-- 1. companies
-- ============================================================
CREATE TABLE IF NOT EXISTS companies (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    domain            TEXT,
    industry          TEXT,
    industry_tags     TEXT DEFAULT '[]',       -- JSON array
    employee_count    INTEGER,
    employee_range    TEXT,
    revenue_usd       REAL,
    ebitda_usd        REAL,
    founded_year      INTEGER,
    description       TEXT,
    city              TEXT,
    state             TEXT,
    country           TEXT,
    full_address      TEXT,
    linkedin_url      TEXT,
    website_url       TEXT,
    phone             TEXT,
    source_provider   TEXT,
    apollo_id         TEXT,
    source_type       TEXT DEFAULT 'apollo_search',
    icp_score         INTEGER,
    status            TEXT DEFAULT 'new',
    enriched_at       TIMESTAMP,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uix_companies_domain
    ON companies(domain) WHERE domain IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_companies_name
    ON companies(name);

CREATE INDEX IF NOT EXISTS ix_companies_apollo_id
    ON companies(apollo_id) WHERE apollo_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_companies_industry
    ON companies(industry);

CREATE INDEX IF NOT EXISTS ix_companies_country
    ON companies(country);

CREATE INDEX IF NOT EXISTS ix_companies_employee_count
    ON companies(employee_count);

CREATE INDEX IF NOT EXISTS ix_companies_ebitda_usd
    ON companies(ebitda_usd);

CREATE INDEX IF NOT EXISTS ix_companies_icp_filter
    ON companies(country, employee_count, ebitda_usd);

CREATE INDEX IF NOT EXISTS ix_companies_status
    ON companies(status);

CREATE INDEX IF NOT EXISTS ix_companies_icp_score
    ON companies(icp_score);

CREATE INDEX IF NOT EXISTS ix_companies_source_type
    ON companies(source_type);

-- ============================================================
-- 1b. icp_profiles
-- ============================================================
CREATE TABLE IF NOT EXISTS icp_profiles (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    config          TEXT NOT NULL,              -- JSON object
    is_default      BOOLEAN DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 2. people
-- ============================================================
CREATE TABLE IF NOT EXISTS people (
    id                TEXT PRIMARY KEY,
    first_name        TEXT NOT NULL,
    last_name         TEXT NOT NULL,
    full_name         TEXT,
    title             TEXT,
    seniority         TEXT,
    department        TEXT,
    company_id        TEXT REFERENCES companies(id) ON DELETE SET NULL,
    company_name      TEXT,
    company_domain    TEXT,
    email             TEXT,
    email_status      TEXT DEFAULT 'unknown',
    personal_email    TEXT,
    phone             TEXT,
    mobile_phone      TEXT,
    linkedin_url      TEXT,
    city              TEXT,
    state             TEXT,
    country           TEXT,
    source_provider   TEXT,
    apollo_id         TEXT,
    enriched_at       TIMESTAMP,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uix_people_email
    ON people(email) WHERE email IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uix_people_name_domain
    ON people(lower(first_name), lower(last_name), lower(company_domain))
    WHERE company_domain IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_people_company_id
    ON people(company_id);

CREATE INDEX IF NOT EXISTS ix_people_company_domain
    ON people(company_domain);

CREATE INDEX IF NOT EXISTS ix_people_linkedin_url
    ON people(linkedin_url) WHERE linkedin_url IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_people_email_status
    ON people(email_status);

CREATE INDEX IF NOT EXISTS ix_people_full_name
    ON people(full_name);

CREATE INDEX IF NOT EXISTS ix_people_apollo_id
    ON people(apollo_id) WHERE apollo_id IS NOT NULL;

-- ============================================================
-- 3. campaigns  (defined before enrichment_results which references it)
-- ============================================================
CREATE TABLE IF NOT EXISTS campaigns (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    description         TEXT,
    input_file          TEXT,
    input_row_count     INTEGER DEFAULT 0,
    enrichment_types    TEXT DEFAULT '["email"]',   -- JSON array
    waterfall_order     TEXT,                        -- JSON array
    column_mapping      TEXT DEFAULT '{}',           -- JSON object
    status              TEXT DEFAULT 'created',
    total_rows          INTEGER DEFAULT 0,
    enriched_rows       INTEGER DEFAULT 0,
    found_rows          INTEGER DEFAULT 0,
    failed_rows         INTEGER DEFAULT 0,
    skipped_rows        INTEGER DEFAULT 0,
    total_credits_used  REAL DEFAULT 0.0,
    estimated_cost_usd  REAL,
    cost_by_provider    TEXT DEFAULT '{}',           -- JSON object
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at          TIMESTAMP,
    completed_at        TIMESTAMP,
    created_by          TEXT,
    last_processed_row  INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_campaigns_status
    ON campaigns(status);

CREATE INDEX IF NOT EXISTS ix_campaigns_created_at
    ON campaigns(created_at DESC);

-- ============================================================
-- 4. enrichment_results
-- ============================================================
CREATE TABLE IF NOT EXISTS enrichment_results (
    id                  TEXT PRIMARY KEY,
    person_id           TEXT REFERENCES people(id) ON DELETE CASCADE,
    company_id          TEXT REFERENCES companies(id) ON DELETE CASCADE,
    campaign_id         TEXT REFERENCES campaigns(id) ON DELETE SET NULL,
    enrichment_type     TEXT NOT NULL,
    query_input         TEXT DEFAULT '{}',           -- JSON object
    source_provider     TEXT NOT NULL,
    result_data         TEXT DEFAULT '{}',           -- JSON object
    found               BOOLEAN DEFAULT 0,
    confidence_score    REAL,
    verification_status TEXT DEFAULT 'unknown',
    cost_credits        REAL DEFAULT 0.0,
    cost_usd            REAL,
    response_time_ms    INTEGER,
    found_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    waterfall_position  INTEGER,
    from_cache          BOOLEAN DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_enrichment_results_person_id
    ON enrichment_results(person_id);

CREATE INDEX IF NOT EXISTS ix_enrichment_results_company_id
    ON enrichment_results(company_id);

CREATE INDEX IF NOT EXISTS ix_enrichment_results_campaign_id
    ON enrichment_results(campaign_id);

CREATE INDEX IF NOT EXISTS ix_enrichment_results_source_provider
    ON enrichment_results(source_provider);

CREATE INDEX IF NOT EXISTS ix_enrichment_results_enrichment_type
    ON enrichment_results(enrichment_type);

CREATE INDEX IF NOT EXISTS ix_enrichment_results_found
    ON enrichment_results(found);

CREATE INDEX IF NOT EXISTS ix_enrichment_results_provider_found_at
    ON enrichment_results(source_provider, found, found_at);

CREATE INDEX IF NOT EXISTS ix_enrichment_results_found_at
    ON enrichment_results(found_at DESC);

CREATE INDEX IF NOT EXISTS ix_enrichment_results_campaign_found
    ON enrichment_results(campaign_id, found);

CREATE INDEX IF NOT EXISTS ix_enrichment_results_person_position
    ON enrichment_results(campaign_id, person_id, waterfall_position)
    WHERE found = 1;

-- ============================================================
-- 5. campaign_rows
-- ============================================================
CREATE TABLE IF NOT EXISTS campaign_rows (
    id              TEXT PRIMARY KEY,
    campaign_id     TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    row_number      INTEGER NOT NULL,
    person_id       TEXT REFERENCES people(id) ON DELETE SET NULL,
    input_data      TEXT DEFAULT '{}',               -- JSON object
    status          TEXT DEFAULT 'pending',
    error_message   TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at    TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_campaign_rows_campaign_row
    ON campaign_rows(campaign_id, row_number);

CREATE INDEX IF NOT EXISTS ix_campaign_rows_campaign_status
    ON campaign_rows(campaign_id, status);

-- ============================================================
-- 6. credit_usage
-- ============================================================
CREATE TABLE IF NOT EXISTS credit_usage (
    id                  TEXT PRIMARY KEY,
    provider            TEXT NOT NULL,
    date                TEXT NOT NULL,               -- YYYY-MM-DD
    credits_used        REAL DEFAULT 0.0,
    credits_remaining   REAL,
    api_calls_made      INTEGER DEFAULT 0,
    successful_lookups  INTEGER DEFAULT 0,
    failed_lookups      INTEGER DEFAULT 0,
    cost_usd            REAL,
    budget_limit        REAL,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(provider, date)
);

CREATE INDEX IF NOT EXISTS ix_credit_usage_provider_date
    ON credit_usage(provider, date DESC);

CREATE INDEX IF NOT EXISTS ix_credit_usage_date_provider
    ON credit_usage(date DESC, provider);

-- ============================================================
-- 7. cache
-- ============================================================
CREATE TABLE IF NOT EXISTS cache (
    cache_key       TEXT PRIMARY KEY,
    provider        TEXT NOT NULL,
    enrichment_type TEXT NOT NULL,
    query_hash      TEXT NOT NULL,
    response_data   TEXT NOT NULL,                   -- JSON object
    found           BOOLEAN DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at      TIMESTAMP NOT NULL,
    hit_count       INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_cache_provider_type
    ON cache(provider, enrichment_type);

CREATE INDEX IF NOT EXISTS ix_cache_expires_at
    ON cache(expires_at);

-- Composite index for fast cache lookups by provider + type + hash with expiry filter.
CREATE INDEX IF NOT EXISTS ix_cache_lookup
    ON cache(provider, enrichment_type, query_hash, expires_at);

-- Trigger: after inserting a new cache row, delete up to 100 expired rows.
CREATE TRIGGER IF NOT EXISTS trg_cache_cleanup
AFTER INSERT ON cache
BEGIN
    DELETE FROM cache
    WHERE cache_key IN (
        SELECT cache_key FROM cache
        WHERE expires_at < CURRENT_TIMESTAMP
        LIMIT 100
    );
END;

-- ============================================================
-- 8. email_patterns
-- ============================================================
CREATE TABLE IF NOT EXISTS email_patterns (
    id              TEXT PRIMARY KEY,
    domain          TEXT NOT NULL,
    pattern         TEXT NOT NULL,
    confidence      REAL DEFAULT 0.0,
    sample_count    INTEGER DEFAULT 0,
    examples        TEXT DEFAULT '[]',               -- JSON array
    discovered_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(domain, pattern)
);

CREATE INDEX IF NOT EXISTS ix_email_patterns_domain
    ON email_patterns(domain);

-- ============================================================
-- 9. domain_catch_all
-- ============================================================
CREATE TABLE IF NOT EXISTS domain_catch_all (
    domain          TEXT PRIMARY KEY,
    is_catch_all    BOOLEAN,
    checked_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 10. audit_log
-- ============================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id         TEXT,
    action          TEXT NOT NULL,
    entity_type     TEXT,
    entity_id       TEXT,
    details         TEXT DEFAULT '{}'                -- JSON object
);

CREATE INDEX IF NOT EXISTS ix_audit_log_timestamp
    ON audit_log(timestamp DESC);

CREATE INDEX IF NOT EXISTS ix_audit_log_user_timestamp
    ON audit_log(user_id, timestamp DESC);

-- ============================================================
-- 11. provider_domain_stats — track hit/miss rates per provider per domain
-- ============================================================
CREATE TABLE IF NOT EXISTS provider_domain_stats (
    provider        TEXT NOT NULL,
    domain          TEXT NOT NULL,
    attempts        INTEGER DEFAULT 0,
    hits            INTEGER DEFAULT 0,
    last_attempt    TEXT,
    PRIMARY KEY (provider, domain)
);

-- ============================================================
-- 12. email_templates
-- ============================================================
CREATE TABLE IF NOT EXISTS email_templates (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    system_prompt   TEXT NOT NULL,
    user_prompt_template TEXT NOT NULL,
    sequence_step   INTEGER DEFAULT 1,
    is_default      BOOLEAN DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 13. generated_emails
-- ============================================================
CREATE TABLE IF NOT EXISTS generated_emails (
    id              TEXT PRIMARY KEY,
    campaign_id     TEXT REFERENCES campaigns(id) ON DELETE CASCADE,
    template_id     TEXT REFERENCES email_templates(id) ON DELETE SET NULL,
    person_id       TEXT REFERENCES people(id) ON DELETE CASCADE,
    company_id      TEXT REFERENCES companies(id) ON DELETE SET NULL,
    sequence_step   INTEGER DEFAULT 1,
    subject         TEXT,
    body            TEXT,
    status          TEXT DEFAULT 'draft',
    user_note       TEXT,
    input_tokens    INTEGER DEFAULT 0,
    output_tokens   INTEGER DEFAULT 0,
    cost_usd        REAL DEFAULT 0.0,
    generated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_generated_emails_campaign
    ON generated_emails(campaign_id);
CREATE INDEX IF NOT EXISTS ix_generated_emails_person
    ON generated_emails(person_id);
CREATE INDEX IF NOT EXISTS ix_generated_emails_status
    ON generated_emails(status);
CREATE INDEX IF NOT EXISTS ix_generated_emails_campaign_status
    ON generated_emails(campaign_id, status);

-- ============================================================
-- Schema migrations
-- ============================================================

-- Phase 11: Salesforce integration (sf_status values: "in_sf" or NULL)
ALTER TABLE companies ADD COLUMN sf_account_id TEXT;
ALTER TABLE companies ADD COLUMN sf_status TEXT;
ALTER TABLE companies ADD COLUMN sf_instance_url TEXT;
CREATE INDEX IF NOT EXISTS ix_companies_sf_status ON companies(sf_status);
