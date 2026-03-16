# Outreach.io CSV Import — Complete Format Reference

> Research date: 2026-03-08
> Sources: Outreach Support docs, Outreach Developer Portal, Prospeo guide, Salesloft/Apollo/Instantly docs

---

## Table of Contents

1. [CSV Import Mechanics](#1-csv-import-mechanics)
2. [Prospect Fields — Complete List](#2-prospect-fields--complete-list)
3. [Account Fields](#3-account-fields)
4. [Custom Fields](#4-custom-fields)
5. [Sequence Integration](#5-sequence-integration)
6. [Duplicate Handling](#6-duplicate-handling)
7. [Outreach REST API Alternative](#7-outreach-rest-api-alternative)
8. [Common Quirks and Gotchas](#8-common-quirks-and-gotchas)
9. [Comparison: Salesloft, Apollo, Instantly](#9-comparison-salesloft-apollo-instantly)
10. [Universal CSV Strategy](#10-universal-csv-strategy)

---

## 1. CSV Import Mechanics

### File Requirements

| Requirement | Value |
|---|---|
| File format | `.csv` only (no XLSX, TSV, etc.) |
| Encoding | **UTF-8** mandatory — Save as "CSV UTF-8 (Comma-delimited) (.csv)" in Excel |
| Maximum rows | **100,000** per import |
| Date format | `YYYY-MM-DD` |
| Phone format | **E.164** recommended (e.g., `+14155551234`) |
| Primary key | **Email address** — one Prospect per unique email |

### Import Workflow (UI)

1. Navigate to Prospects > Import
2. Upload `.csv` file
3. Outreach auto-maps columns that 1:1 match field names
4. Review and manually adjust any unmapped columns
5. Choose duplicate handling strategy (Skip / Overwrite / Update Missing)
6. Choose owner assignment
7. Submit import

### What You Can Import via CSV

- **Prospects** (contacts/people)
- **Accounts** (companies)
- **Purchases** (mapped to accounts)

> There is NO "Contact" object separate from "Prospect" in Outreach. The terms are used interchangeably. Outreach uses "Prospect" as its primary person entity.

---

## 2. Prospect Fields — Complete List

### Identity Fields

| CSV Column Name | API Field Name | Type | Notes |
|---|---|---|---|
| First Name | `firstName` | string | |
| Last Name | `lastName` | string | |
| Middle Name | `middleName` | string | |
| Nickname | `nickname` | string | |
| Title | `title` | string | Job title |
| Occupation | `occupation` | string | |
| Company | `company` | string | Plain text company name (NOT for account linking) |

### Email Fields

| CSV Column Name | API Field Name | Type | Notes |
|---|---|---|---|
| Email | `emails` | array | **Primary key** for dedup. First email = primary |

> Outreach stores multiple emails as an array. In CSV, the first email column maps to primary email.

### Phone Fields

| CSV Column Name | API Field Name | Type | Notes |
|---|---|---|---|
| Home Phones | `homePhones` | array | E.164 format recommended |
| Mobile Phones | `mobilePhones` | array | E.164 format recommended |
| Work Phones | `workPhones` | array | E.164 format recommended |
| Other Phones | `otherPhones` | array | E.164 format recommended |
| VoIP Phones | `voipPhones` | array | E.164 format recommended |

### Address Fields

| CSV Column Name | API Field Name | Type | Notes |
|---|---|---|---|
| Address Street | `addressStreet` | string | |
| Address Street 2 | `addressStreet2` | string | |
| Address City | `addressCity` | string | |
| Address State | `addressState` | string | |
| Address Zip | `addressZip` | string | |
| Address Country | `addressCountry` | string | |

### Social & Web Fields

| CSV Column Name | API Field Name | Type | Notes |
|---|---|---|---|
| LinkedIn URL | `linkedInUrl` | string | Full profile URL |
| LinkedIn Slug | `linkedInSlug` | string | Just the slug portion |
| LinkedIn ID | `linkedInId` | string | Numeric LinkedIn member ID |
| LinkedIn Connections | `linkedInConnections` | integer | |
| Twitter URL | `twitterUrl` | string | |
| Twitter Username | `twitterUsername` | string | |
| GitHub URL | `githubUrl` | string | |
| GitHub Username | `githubUsername` | string | |
| Facebook URL | `facebookUrl` | string | |
| Stack Overflow URL | `stackOverflowUrl` | string | |
| Stack Overflow ID | `stackOverflowId` | string | |
| Quora URL | `quoraUrl` | string | |
| AngelList URL | `angelListUrl` | string | |
| Website URL 1 | `websiteUrl1` | string | |
| Website URL 2 | `websiteUrl2` | string | |
| Website URL 3 | `websiteUrl3` | string | |

### Education & Career Fields

| CSV Column Name | API Field Name | Type | Notes |
|---|---|---|---|
| School | `school` | string | |
| Graduation Date | `graduationDate` | date | YYYY-MM-DD |
| Job Start Date | `jobStartDate` | date | YYYY-MM-DD |
| Specialties | `specialties` | string | |

### Engagement & Status Fields

| CSV Column Name | API Field Name | Type | Notes |
|---|---|---|---|
| Tags | `tags` | array | Semicolon-separated in CSV |
| Source | `source` | string | Lead source |
| Score | `score` | number | Lead score |
| Opted Out | `optedOut` | boolean | true/false |
| Preferred Contact | `preferredContact` | string | |
| Region | `region` | string | |
| Time Zone | `timeZone` | string | |
| Time Zone IANA | `timeZoneIana` | string | IANA tz identifier |

### Notes Fields

| CSV Column Name | API Field Name | Type | Notes |
|---|---|---|---|
| Personal Note 1 | `personalNote1` | string | |
| Personal Note 2 | `personalNote2` | string | |
| Campaign Name | `campaignName` | string | |

### Account Association Fields

| CSV Column Name | API Field Name | Type | Notes |
|---|---|---|---|
| Account | (relationship) | string | **Must use "Account" or "Account name"** |

> CRITICAL: Do NOT map to "Company" for account association. Mapping to "Company" populates the plain-text company field but creates ZERO account associations, with NO error message.

### Owner Fields

| CSV Column Name | API Field Name | Type | Notes |
|---|---|---|---|
| Owner | (relationship) | string | Outreach user email or name |

---

## 3. Account Fields

### Required Fields for Account Import

| Field | Required? | Notes |
|---|---|---|
| Account Name | **Yes** | Primary identifier |
| Custom ID | **Yes** | Used for deduplication |

### Standard Account Fields (API)

| CSV Column Name | API Field Name | Type |
|---|---|---|
| Account Name | `name` | string |
| Domain | `domain` | string |
| Company Type | `companyType` | string |
| Description | `description` | string |
| Industry | `industry` | string |
| Founded At | `foundedAt` | date |
| Locality | `locality` | string |
| Named | `named` | boolean |
| Natural Name | `naturalName` | string |
| Number of Employees | `numberOfEmployees` | integer |
| Revenue Range | `revenueRange` | string |
| Website URL | `websiteUrl` | string |
| LinkedIn URL | `linkedInUrl` | string |
| LinkedIn Slug | `linkedInSlug` | string |
| Tags | `tags` | array |
| Custom 1-N | `custom1`...`customN` | varies |

### Linking Prospects to Accounts

- Accounts **must already exist** before importing prospects that reference them
- Two-step process: (1) Import accounts CSV, (2) Import prospects CSV with "Account" column
- The "Account" column value must match the Account Name in Outreach exactly
- Domain is NOT used as a linking key in CSV import (only Account Name or Custom ID)

---

## 4. Custom Fields

### Naming Convention

Custom fields in Outreach use a **numbered convention** in the API:

```
custom1, custom2, custom3, ... custom24+
```

- Prospect custom fields: `custom1` through `custom24` (expandable)
- Account custom fields: `custom1` through `custom24` (expandable)
- In templates/variables: `{{prospect.custom1}}`, `{{account.custom1}}`

### Custom Field Configuration

- Admins create custom fields in Settings with a **display label** (e.g., "Lead Score Source")
- The internal API name remains `customN` and cannot be changed
- Field type is set at creation and **cannot be changed** afterward
- Available types: Text, Number, Date, Dropdown/Picklist, Checkbox, URL

### CSV Import of Custom Fields

- During CSV import mapping, custom fields appear by their **display label**, not `customN`
- Your CSV column header should match the display label for auto-mapping
- If it doesn't auto-map, you manually select the custom field from the dropdown during the mapping step

### Discovering Custom Fields

Use the API endpoint to see all configured custom fields:
```
GET https://api.outreach.io/api/v2/types
Authorization: Bearer <token>
```

This returns all `customXXX` fields with their type, label, options, and constraints.

---

## 5. Sequence Integration

### Can You Add to Sequence During CSV Import?

**No.** Outreach CSV import is a two-step process:

1. **Step 1**: Import prospects via CSV (creates/updates prospect records)
2. **Step 2**: Add prospects to sequence from the Prospect List View or via API

> This is a key difference from Salesloft, which allows a "Cadence" column in CSV imports.

### Adding Prospects to Sequences (Post-Import)

**Via UI:**
1. Go to Prospects list
2. Filter/select the recently imported prospects (use tags to identify them)
3. Select all > "Add to Sequence"
4. Choose sequence, mailbox, and starting step

**Via API (sequenceState):**
```json
POST /api/v2/sequenceStates
{
  "data": {
    "type": "sequenceState",
    "relationships": {
      "prospect": { "data": { "type": "prospect", "id": <prospect_id> } },
      "sequence": { "data": { "type": "sequence", "id": <sequence_id> } },
      "mailbox":  { "data": { "type": "mailbox",  "id": <mailbox_id> } }
    }
  }
}
```

### Sequence Step Mapping

- When adding via UI, you can choose which step to start from
- When adding via API, the prospect starts at step 1 by default
- You can move prospects to a specific step via UI: select prospect in sequence > "Move to Step"
- The API `sequenceState` resource tracks current step position

### Mailbox Assignment

- Each prospect added to a sequence must be assigned a **mailbox** (sending email account)
- During bulk UI add, you select the mailbox
- Via API, you specify the mailbox ID in the sequenceState relationship
- Mailbox = the Outreach user's connected email account

### Tags Strategy for Sequence Import

Since CSV import doesn't directly add to sequences, use tags as a bridge:
1. Add a unique tag column in your CSV (e.g., `import-2026-03-08-campaign-x`)
2. Import CSV with the tag
3. Filter prospects by that tag
4. Bulk add filtered prospects to your target sequence

---

## 6. Duplicate Handling

### Primary Key

**Email address** is the primary deduplication key. Outreach allows one Prospect per unique email.

### Duplicate Options During Import

| Option | Behavior |
|---|---|
| **Skip** | Does not update existing records; new records only |
| **Overwrite Existing Fields** | Replaces existing field values with CSV values |
| **Update Missing Fields** | Only fills in fields that are currently blank |

### Configurable Duplicate Settings

Admins can configure duplicate handling behavior at the org level:
- Settings > Manage > Prospect Duplicate Management
- Choose how the system identifies duplicates (by email)
- Configure whether to merge, skip, or prompt

### What About Name + Company Matching?

Outreach does NOT deduplicate by name + company. **Email is the only dedup key.** If a prospect has no email, Outreach will create a new record every time.

---

## 7. Outreach REST API Alternative

### Authentication

- **OAuth 2.0** standard flow
- Two credential sets: (1) API key + secret (app), (2) User credentials
- Scopes: `prospects.read`, `prospects.write`, `prospects.delete`, `prospects.all`
- Token sent in `Authorization: Bearer <token>` header

### Rate Limits

| Limit | Value |
|---|---|
| API requests | **10,000 per hour** per user |
| Bulk batch items | **5,000,000 max daily** (refreshed incrementally) |
| Response header | `X-RateLimit-Remaining` |
| Over-limit response | HTTP `429` |

### Prospect CRUD Endpoints

```
GET    /api/v2/prospects          — List prospects
GET    /api/v2/prospects/:id      — Get single prospect
POST   /api/v2/prospects          — Create prospect
PATCH  /api/v2/prospects/:id      — Update prospect
DELETE /api/v2/prospects/:id      — Delete prospect
```

### Bulk API

```
POST /api/v2/batches/actions/<bulkActionName>
```

- Supports bulk upsert of prospects and accounts
- Requires scopes: `batches.read`, `batches.write`, `prospects.write`
- Batch data retained for 30 days for review
- Track batch state: progressing, finished, failed

### Adding to Sequence via API

```
POST /api/v2/sequenceStates
```
- Requires: prospect ID, sequence ID, mailbox ID
- Can finish a prospect in sequence via: `POST /api/v2/sequenceStates/:id/actions/finish`
- Can pause via: `POST /api/v2/sequenceStates/:id/actions/pause`

### Webhooks

```
POST /api/v2/webhooks
```
- Subscribe to events: `prospect.created`, `prospect.updated`, `sequenceState.created`, etc.
- Resource + action based subscriptions
- Can subscribe to import `finished` events for batch monitoring

### Schema Discovery

```
GET https://api.outreach.io/api/v2/schema.json        — JSON Schema
GET https://api.outreach.io/api/v2/schema/openapi.json — OpenAPI/Swagger
GET https://api.outreach.io/api/v2/types               — Custom fields list
```

---

## 8. Common Quirks and Gotchas

### Critical Issues

| Issue | Details |
|---|---|
| **"Company" vs "Account" mapping** | Mapping CSV column to "Company" populates a text field. Mapping to "Account" or "Account name" creates the association. NO error if you get this wrong. |
| **Accounts must pre-exist** | CSV import of prospects does NOT auto-create Account records. Import accounts first. |
| **Truncated field values** | If CSV import truncates text, check for Excel auto-formatting or field length limits. |
| **Trailing whitespace** | Trailing spaces in column values break field matching. Trim all values. |
| **Empty columns** | Remove extra empty columns from CSV before import. |

### Encoding Issues

| Issue | Fix |
|---|---|
| Garbled accented characters | Ensure UTF-8 encoding (not ANSI, not Windows-1252) |
| Excel default save | Use "Save As" > "CSV UTF-8 (Comma-delimited)" specifically |
| BOM marker | Some tools add a BOM; Outreach generally handles it but test first |

### Phone Number Formatting

- **Use E.164 format**: `+[country code][number]` — e.g., `+14155551234`
- Local formats (e.g., `(415) 555-1234`) may work but are not recommended
- E.164 ensures correct Click-to-Dial and international calling

### Multi-Value Fields

- **Tags**: Semicolon-separated in CSV (e.g., `tag1;tag2;tag3`)
- **Emails**: Multiple emails can be imported; first = primary
- **Phones**: Each phone type is a separate column

### Opt-Out / Unsubscribe Handling

- If a prospect is opted out in Outreach and you reimport them, the opt-out status is **preserved** (import does not override opt-out)
- You cannot mass opt-in prospects via CSV import
- Opt-out is respected across email AND calls (granular opt-out available)
- Reimporting an opted-out prospect with "Overwrite" does NOT clear the opt-out flag

### Time Zone Handling

- Use IANA time zone identifiers (e.g., `America/New_York`)
- Outreach can infer time zone from address if not provided (`timeZoneInferred`)
- Time zone affects sequence step scheduling

---

## 9. Comparison: Salesloft, Apollo, Instantly

### Feature Comparison Table

| Feature | Outreach | Salesloft | Apollo | Instantly |
|---|---|---|---|---|
| **File format** | CSV only | CSV only | CSV only | CSV only |
| **Encoding** | UTF-8 | UTF-8 | UTF-8 | UTF-8 |
| **Max rows** | 100,000 | 5,000 | 10,000 (recommended) | No hard limit documented |
| **Primary key** | Email | Email | Email | Email |
| **Person entity name** | Prospect | Person/People | Contact | Lead |
| **Company entity** | Account | Account | Account | N/A (flat) |
| **Sequence in CSV** | No (two-step) | Yes (Cadence ID column) | Yes (Sequence column) | Yes (direct to campaign) |
| **Custom fields format** | `custom1`...`customN` (labeled) | Custom fields by label | Custom fields by label | Up to 50 custom variables |
| **Phone format** | E.164 recommended | E.164 recommended | Standard | Standard |
| **Date format** | YYYY-MM-DD | YYYY-MM-DD | YYYY-MM-DD | YYYY-MM-DD |
| **Duplicate handling** | Skip / Overwrite / Update Missing | Skip / Update | Skip / Update | Overwrite |
| **Tags in CSV** | Yes (semicolon-separated) | Yes | Yes (semicolon-separated) | No native tags |
| **Account linking in CSV** | Account Name column | Account Name column | Company Website (domain) | N/A |
| **Owner assignment** | Yes | Yes (SL Owner column) | Yes | N/A |

### Salesloft Specifics

- Uses "People" not "Prospects"
- **Can add to Cadence via CSV**: Include a "Cadence" column with the Team Cadence ID number
- Cadence ID found in Cadence Settings page
- Only Team Cadences supported (not Personal)
- Max 5,000 people per CSV import
- Column headers should match Salesloft field names exactly

### Apollo Specifics

- Uses "Contacts" not "Prospects"
- Required columns: First Name, Last Name, Email
- Recommended: LinkedIn URL, Company Name, Company Website
- Multi-select values: semicolon-separated (`;`)
- Checkbox fields: `True` / `False`
- Company website: domain only, no `www.` prefix
- Max ~10,000 rows recommended
- Can add to Sequence during import

### Instantly Specifics

- Uses "Leads" — flat structure, no separate Account object
- **Email column must be first** in the CSV
- Column names must start with capital letters
- Column names max 20 characters
- Max 50 custom variables per upload
- Predefined variables: Email, First Name, Last Name, Job Title, Company Name, Personalization, Phone, Website, Location, LinkedIn
- Leads are added directly to campaigns (sequences) during upload
- Charges 0.25 credits per lead if email verification is enabled during upload

---

## 10. Universal CSV Strategy

### Recommended Column Set (Cross-Platform Compatible)

These columns work across Outreach, Salesloft, Apollo, and Instantly with minimal renaming:

```csv
Email,First Name,Last Name,Title,Company,Phone,LinkedIn URL,Website,City,State,Country,Tags
```

### Platform-Specific Columns to Add

| Platform | Extra Columns |
|---|---|
| **Outreach** | Account (must match existing account name), Source, Mobile Phones, Work Phones |
| **Salesloft** | Cadence (Team Cadence ID), SL Owner |
| **Apollo** | Company Website (domain only, no www), Sequence |
| **Instantly** | Personalization (custom snippet), Company Name |

### Export Preset Strategy

**Option A: Single Universal CSV + Platform Column Mapping Guide**
- Export one CSV with all available fields
- Each platform ignores columns it doesn't recognize
- Users map during import

**Option B: Platform-Specific Presets (Recommended)**
- `export_outreach.csv` — Outreach-optimized column names
- `export_salesloft.csv` — Salesloft-optimized column names with Cadence column
- `export_apollo.csv` — Apollo-optimized with domain-only website
- `export_instantly.csv` — Instantly-optimized with Email as first column, capitalized headers

### Column Name Mapping Table

| Our Field | Outreach | Salesloft | Apollo | Instantly |
|---|---|---|---|---|
| email | Email | Email Address | Contact Email | Email |
| first_name | First Name | First Name | First Name | First Name |
| last_name | Last Name | Last Name | Last Name | Last Name |
| title | Title | Title | Title | Job Title |
| company_name | Company | Company | Company Name | Company Name |
| phone | Work Phones | Phone | Phone | Phone |
| mobile_phone | Mobile Phones | Mobile Phone | Mobile Phone | (custom var) |
| linkedin_url | LinkedIn URL | LinkedIn URL | Contact LinkedIn URL | LinkedIn |
| website | Website URL 1 | Website | Company Website | Website |
| street | Address Street | Street | Street | (custom var) |
| city | Address City | City | City | Location |
| state | Address State | State | State | (custom var) |
| zip | Address Zip | Zip | Zip | (custom var) |
| country | Address Country | Country | Country | (custom var) |
| company_domain | (Account domain) | (Account domain) | Company Website | Website |
| tags | Tags | Tags | Tags | (not supported) |
| owner | Owner | SL Owner | Owner | (not supported) |

### Pre-Export Checklist

1. Encode as UTF-8
2. Trim whitespace from all values
3. Remove duplicate rows (by email)
4. Format phones as E.164 (`+14155551234`)
5. Format dates as `YYYY-MM-DD`
6. Remove empty columns
7. Ensure Email column has a value for every row
8. For Outreach: ensure Account names match existing accounts exactly
9. For Apollo: strip `www.` from company website domains
10. For Instantly: put Email as first column, capitalize all column headers

---

## Sources

- [Outreach CSV Import — Official Support](https://support.outreach.io/hc/en-us/articles/221467927-How-To-Bulk-Create-Prospects-and-Accounts-in-Outreach-via-CSV-File)
- [Outreach Account Assignment via CSV](https://support.outreach.io/hc/en-us/articles/26291884649115-How-to-assign-and-associate-accounts-to-prospects-when-importing-a-CSV-file)
- [Outreach Import Accounts via CSV](https://support.outreach.io/hc/en-us/articles/115000177114-Import-Accounts-via-CSV)
- [Outreach Duplicate Prevention](https://support.outreach.io/hc/en-us/articles/13067664181787-How-does-Outreach-prevent-duplicate-Prospects)
- [Outreach Custom Fields](https://support.outreach.io/hc/en-us/articles/219124908-How-To-Add-a-Custom-Field-in-Outreach)
- [Outreach Custom Field Format](https://support.outreach.io/hc/en-us/articles/14525801124763-How-are-Custom-Fields-formatted-in-Outreach)
- [Outreach Variables Overview](https://support.outreach.io/hc/en-us/articles/226680368-Outreach-Variables-Overview)
- [Outreach Add to Sequence](https://support.outreach.io/hc/en-us/articles/360046382774-How-To-Add-Prospects-to-an-Outreach-Sequence)
- [Outreach Sequence States](https://support.outreach.io/hc/en-us/articles/211861917-Outreach-Sequence-States-Overview)
- [Outreach Opt-Out FAQ](https://support.outreach.io/hc/en-us/articles/360041469193-Outreach-Unsubscribe-and-Opt-Out-FAQs)
- [Outreach Phone Formatting](https://support.outreach.io/hc/en-us/articles/4559007096347-Recommended-Phone-Number-Formatting)
- [Outreach REST API Overview](https://developers.outreach.io/api/)
- [Outreach API — Prospect Reference](https://developers.outreach.io/api/reference/tag/Prospect/)
- [Outreach API — Sequence State](https://developers.outreach.io/api/reference/tag/Sequence-State/)
- [Outreach API — Bulk API](https://developers.outreach.io/api/bulk-api/)
- [Outreach API — Webhooks](https://developers.outreach.io/api/reference/tag/Webhook/)
- [Outreach API — OAuth](https://developers.outreach.io/api/oauth/)
- [Outreach API — Common Patterns](https://developers.outreach.io/api/common-patterns/)
- [Outreach Data Dictionary — Prospects](https://developers.outreach.io/data-sharing/data-dictionary-v1/prospects/)
- [Prospeo CSV Import Guide (2026)](https://prospeo.io/s/csv-import-outreach)
- [Salesloft CSV Import](https://help.salesloft.com/s/article/Import-People-from-a-CSV)
- [Apollo CSV Import](https://knowledge.apollo.io/hc/en-us/articles/4409161532045-Import-a-CSV-of-Contacts)
- [Instantly CSV Import](https://help.instantly.ai/en/articles/6254215-how-to-upload-leads-with-a-csv-file)
