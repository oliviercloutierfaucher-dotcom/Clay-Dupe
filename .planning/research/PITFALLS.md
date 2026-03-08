# Pitfalls Research

**Domain:** B2B prospecting platform -- adding Salesforce integration, AI email generation, multi-source company sourcing to existing Python enrichment engine
**Researched:** 2026-03-07
**Confidence:** MEDIUM-HIGH (Salesforce/SQLite pitfalls well-documented; AI email generation is a fast-moving space with less stable best practices)

---

## Critical Pitfalls

### Pitfall 1: Salesforce OAuth Token Lifecycle Mismanagement

**What goes wrong:**
Access tokens expire (typically 2 hours), refresh tokens can be revoked or expire based on Connected App policy, and since Spring 2024, Salesforce issues NEW refresh tokens on each refresh (revoking the old one). If you store a refresh token and don't update it after each refresh, the next refresh call fails with `invalid_grant` and the user must re-authenticate manually.

**Why it happens:**
Developers treat OAuth tokens like API keys -- store once, use forever. Salesforce's token rotation policy is unusual and not obvious from basic tutorials. Additionally, Streamlit's stateless session model means tokens stored in `st.session_state` vanish when the tab closes, so you need persistent token storage.

**How to avoid:**
- Store tokens in SQLite (encrypted at rest) with an `updated_at` timestamp, not in session state
- After every token refresh, persist the new refresh token immediately BEFORE using the new access token
- Use `simple-salesforce` with explicit `session_id` + `instance_url` rather than username/password flow for production
- Set Connected App refresh token policy to "Refresh token is valid until revoked" to avoid silent expiration
- Implement a token health check on app startup that proactively refreshes if token age > 1 hour

**Warning signs:**
- `invalid_grant` errors appearing in logs after days of working fine
- Users reporting they need to "reconnect Salesforce" periodically
- Token refresh works in development but fails in production (different Connected App policies)

**Phase to address:**
Phase 1 (Salesforce Integration) -- must be the first thing built and tested, as every subsequent Salesforce feature depends on reliable auth.

---

### Pitfall 2: SQLite Write Contention When Adding Concurrent Workflows

**What goes wrong:**
v1.0 was designed for one operation at a time. v2.0 introduces concurrent write paths: background Salesforce sync writing cached accounts, enrichment campaigns writing results, company sourcing writing new records, and AI email generation writing drafts -- all hitting the same SQLite database. Even with WAL mode, SQLite has a single-writer lock. Under concurrent writes, one process gets `database is locked` errors.

**Why it happens:**
Each new feature adds its own write path independently. Developers test each feature in isolation where it works fine. The contention only appears when features run simultaneously, which is the normal production pattern.

**How to avoid:**
- Serialize ALL writes through a single async write queue (a dedicated `asyncio.Queue` processed by one writer coroutine) -- this is the standard SQLite concurrency pattern
- Set `busy_timeout` to 5000ms minimum (the default is 0, which fails immediately on lock contention)
- Keep write transactions short -- INSERT results immediately, do not hold transactions open during API calls
- Use `BEGIN IMMEDIATE` for write transactions to fail fast rather than deadlock
- If write contention becomes measurable (>100ms average wait), that is the signal to evaluate PostgreSQL -- but for team-size workloads with a write queue, SQLite handles it

**Warning signs:**
- Sporadic `sqlite3.OperationalError: database is locked` in logs
- Enrichment campaigns that "sometimes fail" on certain rows but succeed on retry
- Salesforce sync timing out because it cannot acquire the write lock

**Phase to address:**
Phase 1 (Infrastructure) -- implement the write queue before adding any new write-heavy features. Retrofit existing enrichment writes to use it.

---

### Pitfall 3: AI Email Hallucination Producing Verifiably False Claims

**What goes wrong:**
LLMs hallucinate facts about companies and people roughly 15% of the time. Real-world examples: AI claims a prospect wrote an article they never wrote, invents product names the company does not make, fabricates partnership announcements, states a newsletter has been running for three years when it has not. In B2B prospecting for niche industrial/A&D/medical device companies, a single hallucinated claim in a cold email destroys credibility permanently.

**Why it happens:**
Developers prompt the LLM with enriched company data and ask it to "personalize" the email. The LLM fills gaps in the data with plausible-sounding but fabricated specifics. The enriched data from Apollo/Datagma may be incomplete (missing recent news, outdated product info), and the LLM compensates by inventing details.

**How to avoid:**
- Constrain the prompt to ONLY use data fields explicitly provided -- use structured output (JSON mode or function calling) to enforce which fields the LLM can reference
- Implement a "fact anchor" template: every personalized claim must cite which input field it came from (e.g., `{company.industry}`, `{person.title}`)
- Add a post-generation validation step that checks every proper noun and specific claim in the output against the input data
- Never ask the LLM to "research" or "find information about" the company -- it will hallucinate
- Use temperature 0.3-0.5, not higher -- creativity in cold emails means hallucination risk
- Provide explicit negative instructions: "Do NOT mention any facts, products, articles, or events not provided in the input data"

**Warning signs:**
- Generated emails mention specific products, articles, or events not in the enrichment data
- Emails reference the prospect's "recent LinkedIn post" when no LinkedIn content was scraped
- All emails for companies in the same industry contain suspiciously specific but similar "personalization"

**Phase to address:**
Phase 2 (AI Email Generation) -- build validation into the generation pipeline from day one, not as a retrofit.

---

### Pitfall 4: Salesforce Duplicate Detection That Misses Matches

**What goes wrong:**
Naive dedup (exact match on email or company name) misses obvious duplicates: "IBM" vs "International Business Machines", "john@ibm.com" vs "j.smith@ibm.com" (same person, different email), companies with multiple domains. The platform flags a prospect as "new" when they already exist in Salesforce, leading to duplicate outreach -- the exact problem the tool is supposed to prevent.

**Why it happens:**
Salesforce stores data as users entered it -- inconsistent formatting, abbreviations, legal names vs DBAs. The enrichment data from Apollo/Icypeas may use different formatting than what is in Salesforce. Exact string matching seems "safe" but catches less than 60% of real duplicates in practice.

**How to avoid:**
- Match on MULTIPLE fields with a scoring system: domain match (highest weight), normalized company name (fuzzy, threshold 85%), email exact match, phone match, LinkedIn URL match
- Normalize company names before comparison: strip "Inc.", "LLC", "Corp.", "Ltd.", lowercase, remove punctuation
- Use domain as the primary dedup key for company matching -- it is the most stable identifier across systems
- For contacts, match on (normalized_email OR (first_name + last_name + company_domain)) -- catches people who changed email addresses
- Cache Salesforce accounts/contacts locally with daily refresh to avoid per-prospect API calls -- Salesforce rate limits make real-time checking infeasible at batch scale
- Surface "uncertain" matches (score 50-85%) for human review rather than auto-skipping

**Warning signs:**
- Users report that "Salesforce check passed" but the prospect was already in their CRM
- Dedup rate is suspiciously low (<5% when the team has been prospecting in the same verticals for months)
- Matching works for exact email but misses company-level duplicates entirely

**Phase to address:**
Phase 1 (Salesforce Integration) -- dedup logic is the core value proposition of the Salesforce integration. Get this right before moving to other features.

---

### Pitfall 5: Streamlit OAuth Callback Breaking in Production

**What goes wrong:**
Salesforce OAuth requires a redirect callback URL. Streamlit has no native route handling -- it is a single-page app that reruns the entire script on every interaction. OAuth callback URLs either do not work, lose session state on redirect, or break when Streamlit is behind a reverse proxy (Railway, Fly.io) where the external URL differs from the internal URL.

**Why it happens:**
Streamlit was designed for data dashboards, not web applications with OAuth flows. The `st.session_state` resets on page reload. Third-party OAuth components (`streamlit-oauth`) exist but are fragile and poorly maintained. Developers assume OAuth "just works" like in Flask/FastAPI, then discover Streamlit's execution model is fundamentally different.

**How to avoid:**
- Do NOT implement OAuth callback in Streamlit itself. Instead, use a one-time setup flow:
  1. Build a tiny FastAPI endpoint (or CLI command) that handles the OAuth dance and stores tokens in SQLite
  2. In Streamlit, just read the stored tokens from SQLite and test if they are valid
  3. If tokens are invalid, show a "Reconnect Salesforce" button that launches the setup flow
- Alternative: use Salesforce's JWT Bearer flow (no redirect needed) -- requires uploading a certificate to the Connected App but eliminates the callback problem entirely
- For Railway/Fly.io: ensure `SALESFORCE_CALLBACK_URL` is configurable via environment variable, not hardcoded to localhost

**Warning signs:**
- OAuth works on localhost but fails on deployed URL
- "Connection lost" after Salesforce redirect because Streamlit session state is wiped
- Users stuck in an OAuth loop -- redirect works but state is not captured back in Streamlit

**Phase to address:**
Phase 1 (Salesforce Integration) -- this is an architectural decision that must be made before writing any Salesforce code. The wrong choice requires a full rewrite.

---

### Pitfall 6: AI-Generated Emails Triggering Spam Filters

**What goes wrong:**
AI-generated cold emails have identifiable linguistic patterns that modern spam filters specifically detect. By 2025, 51% of spam is AI-generated, so Google and Microsoft have trained filters on AI writing patterns. Emails land in spam even with correct SPF/DKIM/DMARC configuration on the sending domain.

**Why it happens:**
LLMs produce characteristic language patterns: "I was impressed by...", "I noticed your company...", "I'd love to connect...", "innovative", "leverage". They over-use certain transitional phrases and produce unnaturally smooth text. Testing of major AI personalization tools shows 85-95% of "personalized" content is templates with 3-5 fields swapped in, which filters detect as pattern-repetitive.

**How to avoid:**
- Keep emails SHORT: 3-5 sentences maximum. AI tends to over-elaborate; cold email best practice is under 100 words
- Provide explicit banned phrases in the prompt: "impressed", "fascinated", "innovative", "leverage", "synergy", "I noticed that", "I came across"
- Generate multiple variants per template and let the user pick/edit -- never auto-send AI output
- Add a spam-score heuristic check: word count >150 = warning, exclamation marks >1 = warning, ALL CAPS words = warning, >2 links = warning
- Structure the prompt to produce a "busy executive writing to a peer" tone, not a "sales rep writing to a lead" tone
- Include CAN-SPAM compliance elements: unsubscribe mechanism, physical address ($51,744 per violation per email)

**Warning signs:**
- Open rates below 15% on emails that passed technical deliverability checks (SPF/DKIM/DMARC all pass)
- Reading 10 generated emails back-to-back and they all feel identical despite different prospect data
- Emails consistently exceed 150 words

**Phase to address:**
Phase 2 (AI Email Generation) -- build spam-awareness into prompt engineering and add output validation before any emails are generated.

---

### Pitfall 7: Company Sourcing Producing Duplicate and Stale Records

**What goes wrong:**
Sourcing companies from Apollo search, CSV import, and manual add creates duplicate company records in the local database. "Acme Corp" from Apollo and "ACME Corporation" from CSV are stored as separate companies, enriched separately (wasting credits), and generate separate prospect lists with conflicting data.

**Why it happens:**
Each source has its own identifier scheme (Apollo has `apollo_id`, CSV has none, manual add has none). Without a dedup step at ingestion, every source creates new rows. The existing `Company` model has `normalize_domain` but no company-level dedup logic that uses it during insert.

**How to avoid:**
- Implement company dedup at INGESTION time, not post-hoc
- Primary dedup key: normalized domain (already have `normalize_domain` in the Company model -- use it as a unique constraint)
- Secondary dedup: fuzzy company name match when domain is missing or does not match (threshold: 90% similarity using `rapidfuzz` or `thefuzz`)
- On duplicate detection: merge data from new source into existing record (prefer newer data for mutable fields like `employee_count`, keep original for immutable fields like `founded_year`)
- Add a `sources` list field to the Company model that tracks which data sources contributed to each record
- For CSV imports: preview detected duplicates BEFORE committing the import, let user choose merge vs skip vs create-new

**Warning signs:**
- Same company appearing multiple times in prospect lists with slight name variations
- Enrichment credit usage higher than expected because duplicates are independently enriched
- Company data contradicts itself (different employee counts for what is clearly the same company)

**Phase to address:**
Phase 1 (Company Sourcing) -- dedup must be built into the ingestion pipeline from the start, not bolted on after duplicates already exist.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Storing Salesforce tokens in `.env` file | Quick setup, no encryption code needed | Tokens rotate -- `.env` becomes stale within hours, no multi-user support | Never in production. Development/testing only |
| Exact-match-only Salesforce dedup | Simple to implement, fast to query | Misses 40%+ of real duplicates, undermines the core value proposition | Never -- fuzzy matching is table stakes for this feature |
| No write queue for SQLite | Fewer abstractions, simpler code | `database is locked` errors when Salesforce sync + enrichment + import run concurrently | Only if app stays single-operation (v1.0 model), which v2.0 explicitly breaks |
| Hardcoding OpenAI as the only LLM provider | Faster to build, simpler config | Vendor lock-in, no fallback when OpenAI is down, no cost optimization across providers | MVP only -- add provider abstraction early |
| Sending AI emails without human review step | Faster workflow, fewer clicks | Hallucinated content sent to real prospects, spam complaints, CAN-SPAM legal exposure | Never -- always require human approval before send |
| Caching Salesforce data only in Streamlit session state | No schema changes, no migration | Lost on tab close, lost on page reload, no persistence across sessions | Never -- use SQLite for Salesforce cache |
| Single API version hardcoded for Salesforce | No version negotiation code | Breaks silently when Salesforce deprecates that API version (they deprecate ~3 versions per year) | Never -- use `simple-salesforce` which auto-negotiates |

---

## Integration Gotchas

Common mistakes when connecting to external services in v2.0.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Salesforce REST API | Hardcoding API version (e.g., `/services/data/v58.0/`) | Use `simple-salesforce` which auto-negotiates version, or query `/services/data/` for latest |
| Salesforce SOQL | Building queries with string concatenation from user/enrichment data | Use `simple-salesforce`'s `sf.query()` with proper escaping; never format company names into SOQL strings |
| Salesforce bulk queries | Querying accounts one-by-one per prospect during enrichment | Bulk query all accounts/contacts once daily, cache to SQLite, match against local cache |
| Salesforce OAuth | Implementing redirect callback inside Streamlit | Use a separate FastAPI endpoint or JWT Bearer flow -- Streamlit cannot handle OAuth callbacks |
| OpenAI API | No timeout or retry logic on LLM calls | Use `httpx` with 30s timeout, retry on 429/500/503 with exponential backoff (match existing `BaseProvider` pattern) |
| OpenAI API | Sending full company descriptions in prompt (2000+ tokens of noise) | Extract only 5-10 relevant fields for personalization, keep prompts under 500 input tokens |
| OpenAI API | Using `temperature=1.0` for "creative" emails | Use `temperature=0.3-0.5` -- creativity in cold emails means hallucination and spam risk |
| Apollo company search | Not paginating results beyond first page | Apollo returns max 100 per page -- implement cursor-based pagination for broad ICP searches |
| CSV import | Trusting column headers without data validation | Fuzzy-match columns (existing v1.0 pattern works), but also validate data types and reject rows missing domain AND company name |
| Multi-source merge | Overwriting existing data with newer source unconditionally | Merge strategy: keep non-null values from each source, prefer source with higher data completeness |

---

## Performance Traps

Patterns that work at small scale but fail as v2.0 usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Real-time Salesforce dedup per prospect | Enrichment slows to 1-2 contacts/second due to Salesforce API latency | Cache Salesforce accounts locally with daily refresh, match against cache | >50 prospects per batch |
| Unbounded concurrent OpenAI requests | 429 rate limit errors, incomplete email batches | Use `aiometer` (already in stack) to limit to 3-5 concurrent LLM calls | >10 concurrent email generations |
| Loading entire Salesforce org into memory | Memory spike, OOM on orgs with tens of thousands of accounts | Stream results with `sf.query_all_iter()`, write directly to SQLite in batches | >10K accounts in Salesforce |
| Generating emails synchronously in Streamlit UI | UI freezes for 30+ seconds, Streamlit script timeout | Generate async in background, poll for completion, show progress bar | >5 emails generated at once |
| Full-table scan for company dedup during import | 1000-company CSV import takes minutes | Add composite index on `(domain)` and `(name)` with normalization, use covering indexes | >500 companies in database |
| Salesforce API calls counting against daily limit during development/testing | Hit 100K daily limit, production sync blocked | Use Salesforce sandbox for development; monitor API usage via `sf.limits()` call | Depends on org edition, typically 100K-150K calls/day |

---

## Security Mistakes

Domain-specific security issues for v2.0 features.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Storing Salesforce refresh tokens in plaintext SQLite | Token theft gives full read access to entire CRM -- accounts, contacts, opportunities, revenue data | Encrypt tokens at rest using `cryptography.fernet` with key from environment variable |
| Passing prospect PII (name, email, company) to OpenAI without DPA | GDPR violation if prospects are EU-based; potential data use for model training | Review OpenAI's data processing terms; use API (not ChatGPT) which has zero-retention by default; document data flows |
| AI prompt injection via enrichment data | Malicious company description in Apollo/CSV data could hijack email generation prompt -- output arbitrary content or exfiltrate data in email body | Sanitize all enrichment data before including in LLM prompts: strip control characters, limit field lengths to 200 chars, escape special characters |
| SOQL injection via crafted company/person names | Attacker-crafted company name imported via CSV could exfiltrate Salesforce data or modify records | Use `simple-salesforce` parameterized queries exclusively; never string-format SOQL with user-supplied data |
| Exposing Salesforce instance URL or org ID in Streamlit UI | Reveals org type, edition, and potential attack surface to anyone with UI access | Store server-side only; never render Salesforce metadata in the frontend; use settings not session state |
| OpenAI API key in client-side code or logs | Key theft allows unlimited LLM usage on your account | Store in `.env` only; verify key never appears in Streamlit source or browser dev tools; scrub from log output |

---

## UX Pitfalls

Common user experience mistakes when adding these v2.0 features.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No visibility into Salesforce match confidence | Users cannot tell if a "duplicate" is a strong or weak match, leading to distrust | Show match score and which fields matched (email, domain, name) -- let user override decisions |
| AI email generation with no editing step | Users accidentally send emails with hallucinated content to real prospects | Always present emails in an editable text area with explicit "Review and Approve" workflow |
| Salesforce connection status not visible | Users run enrichment not knowing Salesforce dedup is disconnected, defeating the purpose | Show persistent connection indicator in sidebar (green=connected, yellow=token expiring, red=disconnected) |
| Company source not shown in list view | Users cannot tell if a company came from Apollo search, CSV import, or manual entry | Add source badge/icon to company list view -- provenance matters for data trust |
| Bulk email generation with no preview step | Users generate 200 emails and discover the tone/template is wrong, wasting time and LLM credits | Generate 3-5 sample emails first, get user approval on tone and content, then generate the rest |
| No undo for "skip as Salesforce duplicate" | User incorrectly marks a prospect as duplicate, loses the record with no recovery | Add "restore skipped" action, log all skip decisions with match details and timestamp |
| Mixing stale CSV data with fresh API data without indicator | Users trust outdated CSV-sourced company data alongside real-time Apollo data | Show data freshness indicator (e.g., "sourced 3 months ago from CSV") next to each company record |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Salesforce OAuth:** Token refresh works -- but does it persist the NEW refresh token after each refresh? Test by waiting 2+ hours, refreshing, then refreshing again with the stored token
- [ ] **Salesforce dedup:** Works for exact email match -- but test with company name variations ("IBM" vs "International Business Machines"), different email formats for same person, companies with multiple domains
- [ ] **AI emails:** Generates personalized emails -- but read 20 generated emails back-to-back. Do they all sound the same despite different data? (Template fatigue = spam filter signal)
- [ ] **AI emails:** Content looks good -- but does every factual claim trace back to an input data field? Check 10 emails for hallucinated products, articles, or events
- [ ] **AI emails:** Emails generate -- but do they include unsubscribe link and physical address? (CAN-SPAM: $51,744 per violation per email)
- [ ] **Company sourcing:** CSV import works -- but import the same CSV twice. Are there zero new duplicate rows?
- [ ] **Company sourcing:** Apollo search works -- but does it paginate? Test with a broad ICP query returning >100 results
- [ ] **Salesforce sync:** Queries accounts successfully -- but what happens with a 50K-account org? Does it timeout, OOM, or gracefully paginate?
- [ ] **Write concurrency:** Each feature works in isolation -- but run Salesforce sync + enrichment campaign + CSV import simultaneously. Any `database is locked` errors?
- [ ] **Token expiry:** Everything works today -- but simulate token expiry (revoke token in Salesforce), then verify the app detects this and prompts re-auth gracefully instead of silently failing dedup checks
- [ ] **Deployed OAuth:** Works on localhost -- but test the full OAuth flow on the deployed Railway/Fly.io URL with the production callback URL

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Salesforce token expires silently, dedup checks skipped | MEDIUM | Detect by auditing enrichment logs for missing SF checks; re-run affected contacts through dedup; add token health monitoring |
| Hallucinated email content sent to real prospect | HIGH | No technical recovery -- reputational damage is done. Apologize manually. Add mandatory human review to prevent recurrence |
| Duplicate companies created across sources | MEDIUM | Run dedup migration script: group by normalized domain, merge records, update foreign keys (person.company_id), deduplicate enrichment results. Prevent with ingestion-time dedup |
| SQLite database locked during concurrent operations | LOW | Implement write queue, set `busy_timeout=5000`, replay failed writes from audit trail. Immediate fix: restart app |
| Spam-flagged sending domain due to AI email patterns | HIGH | Domain reputation takes 2-4 weeks to recover. Warm up a new domain. Prevent with spam scoring before send |
| Salesforce API daily limit exhausted | MEDIUM | Wait 24 hours (limit resets) or contact Salesforce for temporary increase. Prevent with local caching and bulk API usage |
| SOQL injection via crafted import data | HIGH | Audit all SOQL queries for string formatting; switch to parameterized; scan Salesforce audit trail for unauthorized data access |
| Prompt injection via malicious enrichment data | MEDIUM | Review all generated emails for anomalous content; sanitize the source data; add input sanitization to LLM pipeline |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| OAuth token lifecycle mismanagement | Phase 1: Salesforce Integration | Token works after 24+ hours without manual re-auth; new refresh token persisted after each refresh |
| SQLite write contention | Phase 1: Infrastructure prep | Run 3 concurrent write workflows (SF sync + enrichment + import), zero `database is locked` errors in 10-minute test |
| Streamlit OAuth callback failure | Phase 1: Salesforce Integration | OAuth flow works on deployed URL (Railway/Fly.io), not just localhost |
| Salesforce dedup missing matches | Phase 1: Salesforce Integration | Test with 20 known-duplicate pairs using name variations; hit >90% match rate |
| Company dedup at ingestion | Phase 1: Company Sourcing | Import identical CSV twice, verify zero new duplicate company rows created |
| AI hallucination in emails | Phase 2: AI Email Generation | Generate 50 emails; automated check verifies every proper noun traces to input data |
| Spam filter triggers | Phase 2: AI Email Generation | 10 sample emails all score below 5.0 on SpamAssassin-style heuristic check |
| CAN-SPAM compliance | Phase 2: AI Email Generation | Every generated email template includes unsubscribe mechanism and physical address |
| Prompt injection via enrichment data | Phase 2: AI Email Generation | Insert adversarial company description; verify email output is not hijacked or contains injected instructions |
| Salesforce API rate limits | Phase 1: Salesforce Integration | Sync 10K accounts without hitting daily limit (use bulk API + local cache) |
| Salesforce token encryption | Phase 1: Salesforce Integration | Verify tokens are not readable in plaintext from SQLite database file |

---

## Sources

- [Salesforce OAuth Refresh Token invalid_grant -- Nango](https://nango.dev/blog/salesforce-oauth-refresh-token-invalid-grant) -- token rotation behavior since Spring 2024
- [Salesforce API Request Limits](https://developer.salesforce.com/docs/atlas.en-us.salesforce_app_limits_cheatsheet.meta/salesforce_app_limits_cheatsheet/salesforce_app_limits_platform_api.htm) -- daily rate limits by edition
- [Salesforce OAuth 2.0 Flows -- Beyond The Cloud](https://blog.beyondthecloud.dev/blog/salesforce-oauth-2-0-flows-integrate-in-the-right-way) -- JWT Bearer flow as redirect-free alternative
- [SQLite Concurrent Writes and "database is locked"](https://tenthousandmeters.com/blog/sqlite-concurrent-writes-and-database-is-locked-errors/) -- write contention root cause analysis
- [Streamlit OAuth Component](https://github.com/dnplus/streamlit-oauth) -- OAuth callback limitations in Streamlit
- [Streamlit Session State docs](https://docs.streamlit.io/develop/concepts/architecture/session-state) -- session lifetime and loss on tab close
- [AI Cold Email Is Killing Cold Email -- Rui Nunes](https://ruinunes.com/ai-cold-email/) -- 15% hallucination rate data, 51% of spam is AI-generated
- [Instantly.ai AI Email Personalization](https://instantly.ai/blog/ai-powered-cold-email-personalization-safe-patterns-prompt-examples-workflow-for-founders/) -- safe prompt patterns, banned phrases
- [FastCompany: AI Email Spam Mistakes](https://www.fastcompany.com/91037962/the-mistakes-that-send-your-ai-generated-cold-emails-straight-to-spam) -- spam trigger analysis
- [OWASP LLM01: Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) -- #1 LLM security risk, mitigation strategies
- [Entity Resolution Challenges -- Sheshbabu](https://www.sheshbabu.com/posts/entity-resolution-challenges/) -- company name matching, DBA vs legal name issues
- [simple-salesforce on PyPI](https://pypi.org/project/simple-salesforce/) -- Python Salesforce library with auto-versioning
- [Salesforce Connected App Token Policy](https://help.salesforce.com/s/articleView?id=sf.connected_app_manage_oauth.htm&language=en_US&type=5) -- refresh token expiration settings

---
*Pitfalls research for: Clay-Dupe v2.0 -- Salesforce integration, AI email generation, multi-source company sourcing*
*Researched: 2026-03-07*
