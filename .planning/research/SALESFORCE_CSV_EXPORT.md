# Salesforce CSV Export Research — Comprehensive Guide

**Date:** 2026-03-08
**Purpose:** Define the exact CSV format for a B2B enrichment tool that exports enriched contacts in a Salesforce-ready, Outreach-ready, and HubSpot-ready format.

---

## Table of Contents

1. [Salesforce Lead Object — All Standard Fields](#1-salesforce-lead-object--all-standard-fields)
2. [Salesforce Account Object — All Standard Fields](#2-salesforce-account-object--all-standard-fields)
3. [Salesforce Contact Object — All Standard Fields](#3-salesforce-contact-object--all-standard-fields)
4. [Required Fields for Record Creation](#4-required-fields-for-record-creation)
5. [Data Import Wizard — How It Works](#5-data-import-wizard--how-it-works)
6. [Data Loader — How It Works & Differences](#6-data-loader--how-it-works--differences)
7. [Field Mapping Rules](#7-field-mapping-rules)
8. [CSV Formatting Requirements](#8-csv-formatting-requirements)
9. [Duplicate Detection on Import](#9-duplicate-detection-on-import)
10. [Common Custom Fields in Sales Orgs](#10-common-custom-fields-in-sales-orgs)
11. [Best Practices for CSV Export Tools](#11-best-practices-for-csv-export-tools)
12. [User CSV Column Mapping to Salesforce Fields](#12-user-csv-column-mapping-to-salesforce-fields)
13. [Outreach.io CSV Import Format](#13-outreachio-csv-import-format)
14. [HubSpot CSV Import Format](#14-hubspot-csv-import-format)
15. [Competitive Landscape — Tools That Do This Today](#15-competitive-landscape--tools-that-do-this-today)

---

## 1. Salesforce Lead Object — All Standard Fields

The Lead object represents a prospect or potential customer. Below is the **complete list of standard fields** with API names and data types.

### Core Identity Fields

| Field Label | API Name | Data Type | Notes |
|---|---|---|---|
| Salutation | `Salutation` | Picklist | Mr., Mrs., Ms., Dr., Prof. |
| First Name | `FirstName` | String(40) | |
| Last Name | `LastName` | String(80) | **REQUIRED** |
| Middle Name | `MiddleName` | String(40) | Must be enabled in org |
| Suffix | `Suffix` | String(40) | Must be enabled in org |
| Name | `Name` | String | Compound of Salutation + First + Last (read-only) |
| Title | `Title` | String(128) | Job title |
| Company | `Company` | String(255) | **REQUIRED** |
| Email | `Email` | Email | |
| Phone | `Phone` | Phone | |
| Mobile Phone | `MobilePhone` | Phone | |
| Fax | `Fax` | Phone | |
| Website | `Website` | URL | |

### Address Fields

| Field Label | API Name | Data Type | Notes |
|---|---|---|---|
| Street | `Street` | Textarea(255) | Multi-line supported |
| City | `City` | String(40) | |
| State/Province | `State` | String(80) | Or `StateCode` for picklist |
| Zip/Postal Code | `PostalCode` | String(20) | |
| Country | `Country` | String(80) | Or `CountryCode` for picklist |
| Latitude | `Latitude` | Double | |
| Longitude | `Longitude` | Double | |
| Geocode Accuracy | `GeocodeAccuracy` | Picklist | |

### Classification Fields

| Field Label | API Name | Data Type | Notes |
|---|---|---|---|
| Lead Source | `LeadSource` | Picklist | Web, Phone Inquiry, Partner Referral, etc. |
| Status | `Status` | Picklist | Open, Contacted, Qualified, etc. (org-specific) |
| Industry | `Industry` | Picklist | Standard picklist (Agriculture, Banking, etc.) |
| Rating | `Rating` | Picklist | Hot, Warm, Cold |
| Annual Revenue | `AnnualRevenue` | Currency | |
| Number of Employees | `NumberOfEmployees` | Integer | |
| Description | `Description` | Textarea(32000) | Long text area |

### System & Ownership Fields

| Field Label | API Name | Data Type | Notes |
|---|---|---|---|
| Lead Owner | `OwnerId` | Reference(User/Queue) | 15 or 18-char Salesforce ID |
| Record Type | `RecordTypeId` | Reference | 15 or 18-char ID |
| Created Date | `CreatedDate` | DateTime | Read-only |
| Created By | `CreatedById` | Reference | Read-only |
| Last Modified Date | `LastModifiedDate` | DateTime | Read-only |
| Last Modified By | `LastModifiedById` | Reference | Read-only |
| System Modstamp | `SystemModstamp` | DateTime | Read-only |
| Last Activity Date | `LastActivityDate` | Date | Read-only |
| Last Viewed Date | `LastViewedDate` | DateTime | Read-only |
| Last Referenced Date | `LastReferencedDate` | DateTime | Read-only |

### Conversion Fields

| Field Label | API Name | Data Type | Notes |
|---|---|---|---|
| Is Converted | `IsConverted` | Boolean | Read-only |
| Converted Date | `ConvertedDate` | Date | Read-only |
| Converted Account | `ConvertedAccountId` | Reference | Read-only |
| Converted Contact | `ConvertedContactId` | Reference | Read-only |
| Converted Opportunity | `ConvertedOpportunityId` | Reference | Read-only |
| Is Unread By Owner | `IsUnreadByOwner` | Boolean | |

### Email/Campaign Fields

| Field Label | API Name | Data Type | Notes |
|---|---|---|---|
| Email Bounced Reason | `EmailBouncedReason` | String(255) | |
| Email Bounced Date | `EmailBouncedDate` | DateTime | |
| Jigsaw Contact ID | `Jigsaw` | String(20) | Data.com key (deprecated) |
| Clean Status | `CleanStatus` | Picklist | Data.com clean status |
| Company D-U-N-S Number | `CompanyDunsNumber` | String(9) | |
| DandBCompanyId | `DandbCompanyId` | Reference | Data.com company |

---

## 2. Salesforce Account Object — All Standard Fields

The Account object represents an organization or company.

### Core Fields

| Field Label | API Name | Data Type | Notes |
|---|---|---|---|
| Account Name | `Name` | String(255) | **REQUIRED** |
| Account Number | `AccountNumber` | String(40) | |
| Account Site | `Site` | String(80) | Location label (HQ, Branch) |
| Parent Account | `ParentId` | Reference(Account) | |
| Type | `Type` | Picklist | Prospect, Customer, Partner, etc. |
| Industry | `Industry` | Picklist | Standard SF industry picklist |
| Description | `Description` | Textarea(32000) | |

### Contact Information

| Field Label | API Name | Data Type | Notes |
|---|---|---|---|
| Phone | `Phone` | Phone | |
| Fax | `Fax` | Phone | |
| Website | `Website` | URL | |

### Address Fields (Billing)

| Field Label | API Name | Data Type | Notes |
|---|---|---|---|
| Billing Street | `BillingStreet` | Textarea(255) | |
| Billing City | `BillingCity` | String(40) | |
| Billing State/Province | `BillingState` | String(80) | Or `BillingStateCode` |
| Billing Zip/Postal Code | `BillingPostalCode` | String(20) | |
| Billing Country | `BillingCountry` | String(80) | Or `BillingCountryCode` |
| Billing Latitude | `BillingLatitude` | Double | |
| Billing Longitude | `BillingLongitude` | Double | |
| Billing Geocode Accuracy | `BillingGeocodeAccuracy` | Picklist | |

### Address Fields (Shipping)

| Field Label | API Name | Data Type | Notes |
|---|---|---|---|
| Shipping Street | `ShippingStreet` | Textarea(255) | |
| Shipping City | `ShippingCity` | String(40) | |
| Shipping State/Province | `ShippingState` | String(80) | |
| Shipping Zip/Postal Code | `ShippingPostalCode` | String(20) | |
| Shipping Country | `ShippingCountry` | String(80) | |
| Shipping Latitude | `ShippingLatitude` | Double | |
| Shipping Longitude | `ShippingLongitude` | Double | |
| Shipping Geocode Accuracy | `ShippingGeocodeAccuracy` | Picklist | |

### Classification Fields

| Field Label | API Name | Data Type | Notes |
|---|---|---|---|
| Annual Revenue | `AnnualRevenue` | Currency | |
| Number of Employees | `NumberOfEmployees` | Integer | |
| Ownership | `Ownership` | Picklist | Public, Private, Subsidiary, etc. |
| Ticker Symbol | `TickerSymbol` | String(20) | |
| SIC Code | `Sic` | String(20) | |
| SIC Description | `SicDesc` | String(80) | |
| NAICS Code | `NaicsCode` | String(8) | |
| NAICS Description | `NaicsDesc` | String(120) | |
| Year Started | `YearStarted` | String(4) | |
| D-U-N-S Number | `DunsNumber` | String(9) | |
| Tradestyle | `Tradestyle` | String(255) | |
| Account Source | `AccountSource` | Picklist | Same values as LeadSource |
| Rating | `Rating` | Picklist | Hot, Warm, Cold |

### System & Ownership Fields

| Field Label | API Name | Data Type | Notes |
|---|---|---|---|
| Account Owner | `OwnerId` | Reference(User) | |
| Record Type | `RecordTypeId` | Reference | |
| Created Date | `CreatedDate` | DateTime | Read-only |
| Last Modified Date | `LastModifiedDate` | DateTime | Read-only |
| Last Activity Date | `LastActivityDate` | Date | Read-only |
| Clean Status | `CleanStatus` | Picklist | |
| DandBCompanyId | `DandbCompanyId` | Reference | |
| Jigsaw | `Jigsaw` | String(20) | |

---

## 3. Salesforce Contact Object — All Standard Fields

The Contact object represents a person associated with an Account.

### Core Identity Fields

| Field Label | API Name | Data Type | Notes |
|---|---|---|---|
| Salutation | `Salutation` | Picklist | |
| First Name | `FirstName` | String(40) | |
| Last Name | `LastName` | String(80) | **REQUIRED** |
| Middle Name | `MiddleName` | String(40) | Must be enabled |
| Suffix | `Suffix` | String(40) | Must be enabled |
| Name | `Name` | String | Compound (read-only) |
| Account Name | `AccountId` | Reference(Account) | Links Contact to Account |
| Title | `Title` | String(128) | |
| Department | `Department` | String(80) | |
| Birthdate | `Birthdate` | Date | |
| Reports To | `ReportsToId` | Reference(Contact) | |
| Assistant | `AssistantName` | String(40) | |
| Asst. Phone | `AssistantPhone` | Phone | |
| Description | `Description` | Textarea(32000) | |

### Contact Information

| Field Label | API Name | Data Type | Notes |
|---|---|---|---|
| Email | `Email` | Email | |
| Phone | `Phone` | Phone | |
| Home Phone | `HomePhone` | Phone | |
| Mobile | `MobilePhone` | Phone | |
| Other Phone | `OtherPhone` | Phone | |
| Fax | `Fax` | Phone | |

### Mailing Address

| Field Label | API Name | Data Type | Notes |
|---|---|---|---|
| Mailing Street | `MailingStreet` | Textarea(255) | |
| Mailing City | `MailingCity` | String(40) | |
| Mailing State/Province | `MailingState` | String(80) | |
| Mailing Zip/Postal Code | `MailingPostalCode` | String(20) | |
| Mailing Country | `MailingCountry` | String(80) | |
| Mailing Latitude | `MailingLatitude` | Double | |
| Mailing Longitude | `MailingLongitude` | Double | |

### Other Address

| Field Label | API Name | Data Type | Notes |
|---|---|---|---|
| Other Street | `OtherStreet` | Textarea(255) | |
| Other City | `OtherCity` | String(40) | |
| Other State/Province | `OtherState` | String(80) | |
| Other Zip/Postal Code | `OtherPostalCode` | String(20) | |
| Other Country | `OtherCountry` | String(80) | |
| Other Latitude | `OtherLatitude` | Double | |
| Other Longitude | `OtherLongitude` | Double | |

### Classification & System Fields

| Field Label | API Name | Data Type | Notes |
|---|---|---|---|
| Lead Source | `LeadSource` | Picklist | Same values as Lead.LeadSource |
| Contact Owner | `OwnerId` | Reference(User) | |
| Record Type | `RecordTypeId` | Reference | |
| Email Bounced Reason | `EmailBouncedReason` | String(255) | |
| Email Bounced Date | `EmailBouncedDate` | DateTime | |
| Do Not Call | `DoNotCall` | Boolean | |
| Has Opted Out of Email | `HasOptedOutOfEmail` | Boolean | |
| Has Opted Out of Fax | `HasOptedOutOfFax` | Boolean | |
| Jigsaw Contact ID | `Jigsaw` | String(20) | |
| Clean Status | `CleanStatus` | Picklist | |
| Created Date | `CreatedDate` | DateTime | Read-only |
| Last Modified Date | `LastModifiedDate` | DateTime | Read-only |
| Last Activity Date | `LastActivityDate` | Date | Read-only |

---

## 4. Required Fields for Record Creation

### Lead (Minimum Required)
| Field | API Name | Notes |
|---|---|---|
| Last Name | `LastName` | Always required |
| Company | `Company` | Always required (can be made optional in some orgs) |

**De facto required for usability:** `Email`, `Status` (defaults to first picklist value if omitted)

### Account (Minimum Required)
| Field | API Name | Notes |
|---|---|---|
| Account Name | `Name` | Only required field |

### Contact (Minimum Required)
| Field | API Name | Notes |
|---|---|---|
| Last Name | `LastName` | Only required field |

**Note:** If org has validation rules or required custom fields, additional fields become mandatory. Record Type-specific required fields may also apply.

---

## 5. Data Import Wizard — How It Works

### Overview
- Built-in Salesforce tool, accessible from Setup
- No installation required
- GUI-based, step-by-step wizard

### Supported Objects
- Accounts, Contacts, Leads, Solutions, Campaign Members
- Custom Objects
- Person Accounts

### Supported Operations
- **Insert** — Create new records
- **Update** — Modify existing records (requires ID or external ID)
- **Upsert** — Insert or update based on matching field

### Limitations
- **50,000 records max** per import
- **90 fields max** per import file
- **100 MB max** file size
- **400 KB max** per individual record (~4,000 characters)
- **32 KB max** for notes/description fields (truncated beyond this)
- No Delete operation
- No Export operation

### Process
1. Select the object to import
2. Upload CSV file
3. Auto-mapping attempts to match CSV headers to SF fields
4. Review/adjust field mappings manually
5. Start import
6. Receive email confirmation when complete

### Field Mapping Behavior
- Auto-matches CSV column headers to Salesforce field **labels** (not API names)
- Case-insensitive matching
- Unmapped fields are silently skipped (unless required)
- Manual mapping available for unmatched fields

---

## 6. Data Loader — How It Works & Differences

### Overview
- Separate desktop application (must be downloaded and installed)
- More powerful, supports more objects and operations
- Uses Bulk API or SOAP API under the hood

### Key Differences from Import Wizard

| Feature | Import Wizard | Data Loader |
|---|---|---|
| Max Records | 50,000 | 5,000,000 (Bulk API) |
| Supported Objects | Limited standard + custom | All standard + custom |
| Operations | Insert, Update, Upsert | Insert, Update, Upsert, Delete, Export, Hard Delete |
| Field Mapping | Auto-match by label | Manual mapping or saved .sdl files |
| Installation | None (built-in) | Requires download/install |
| Automation | No | Yes (CLI, scheduled) |
| API Used | SOAP API | SOAP or Bulk API |
| Trigger/Workflow | Always fires | Can be configured |
| Duplicate Rules | Respects active rules | Can bypass with API settings |

### Data Loader Field Mapping
- Uses **API names** (not labels) for field mapping
- Mapping saved as `.sdl` files (reusable)
- CSV column headers should match API names for auto-mapping
- Case-sensitive for API names

---

## 7. Field Mapping Rules

### Import Wizard Mapping
- Maps CSV column **headers** to Salesforce field **labels**
- Auto-mapping is best-effort; similar names get matched
- **Best practice:** Use exact Salesforce field labels as CSV headers for auto-mapping
- Example: Column "First Name" auto-maps to `FirstName`, "Company" maps to `Company`

### Data Loader Mapping
- Maps CSV column **headers** to Salesforce **API names**
- **Best practice:** Use exact API names as CSV headers
- Example: Column "FirstName" maps to `FirstName`, "NumberOfEmployees" maps to `NumberOfEmployees`

### Universal Mapping Tips
- For **Import Wizard**: Use human-readable field labels (e.g., "First Name", "Lead Source")
- For **Data Loader**: Use API names (e.g., "FirstName", "LeadSource")
- For **maximum compatibility**: Use API names as headers (works with Data Loader; Import Wizard can still map manually)

### Address Field Mapping
Addresses must be **separate fields** — Salesforce does not accept a single combined address string:
```
Street, City, State, PostalCode, Country  (5 separate columns)
```

For **Lead** CSV:
```
Street, City, State, PostalCode, Country
```

For **Account** CSV (Billing):
```
BillingStreet, BillingCity, BillingState, BillingPostalCode, BillingCountry
```

For **Contact** CSV (Mailing):
```
MailingStreet, MailingCity, MailingState, MailingPostalCode, MailingCountry
```

---

## 8. CSV Formatting Requirements

### File Format
- **Encoding:** UTF-8 (mandatory). No BOM required, but UTF-8 BOM is tolerated.
- **Delimiter:** Comma (`,`)
- **Line endings:** CRLF or LF both accepted
- **Quoting:** Fields containing commas, newlines, or quotes must be enclosed in double quotes. Embedded quotes escaped as `""`
- **Header row:** Required as first row

### Data Type Formats

| Data Type | Format | Example |
|---|---|---|
| Date | `YYYY-MM-DD` | `2026-03-08` |
| DateTime | `YYYY-MM-DDThh:mm:ssZ` (ISO 8601) | `2026-03-08T14:30:00Z` |
| Currency | Numeric, no currency symbol | `50000` or `50000.00` |
| Integer | Whole number, no commas | `250` |
| Boolean | `true` / `false` or `1` / `0` | `true` |
| Picklist | Exact match to picklist value | `Hot` (not `hot` or `HOT`) |
| Multi-Select Picklist | Semicolon-separated | `Value1;Value2;Value3` |
| Email | Standard email format | `john@example.com` |
| URL | Full URL preferred | `https://www.example.com` |
| Phone | String (any format) | `+1 (555) 123-4567` |
| Percent | Numeric (no % symbol) | `75` (means 75%) |
| ID / Reference | 15 or 18-character Salesforce ID | `001XXXXXXXXXXXXXXX` |

### Picklist Field Standard Values

**Industry** (standard picklist values):
```
Agriculture, Apparel, Banking, Biotechnology, Chemicals, Communications,
Construction, Consulting, Education, Electronics, Energy, Engineering,
Entertainment, Environmental, Finance, Food & Beverage, Government,
Healthcare, Hospitality, Insurance, Machinery, Manufacturing, Media,
Not For Profit, Recreation, Retail, Shipping, Technology,
Telecommunications, Transportation, Utilities, Other
```

**Lead Source** (standard picklist values):
```
Web, Phone Inquiry, Partner Referral, Purchased List, Other
```
(Most orgs customize this heavily)

**Lead Status** (standard picklist values):
```
Open - Not Contacted, Working - Contacted, Closed - Converted, Closed - Not Converted
```
(Most orgs customize this heavily)

**Rating**:
```
Hot, Warm, Cold
```

### Record Type via CSV
- Use `RecordTypeId` column with the 15/18-char Record Type ID
- Alternative: Some tools support `RecordType.Name` or `RecordType.DeveloperName`
- Data Import Wizard does NOT support Record Type assignment via CSV (it's set globally for the import)
- Data Loader DOES support per-row Record Type via `RecordTypeId` column

### Owner Assignment via CSV
- Use `OwnerId` column with User ID (15/18-char)
- Data Import Wizard: Does NOT support per-row owner assignment
- Data Loader: Supports `OwnerId` column
- If `OwnerId` is omitted, records are owned by the importing user
- **Important:** Cannot assign to inactive users

---

## 9. Duplicate Detection on Import

### Components
1. **Matching Rules** — Define HOW duplicates are identified (which fields to compare)
2. **Duplicate Rules** — Define WHAT HAPPENS when a match is found (block, alert, allow)

### Matching Types
- **Exact Matching:** Fields must be identical (e.g., email address)
- **Fuzzy Matching:** Catches similar but not identical values (spelling variations, formatting)

### Standard Matching Rules (Out-of-Box)

**Lead Matching:**
- Standard Lead Matching Rule: Matches on Email, or Company+Name combination
- Fields compared: Email, FirstName, LastName, Company, Phone, Street, City, PostalCode

**Account Matching:**
- Standard Account Matching Rule: Matches on Account Name, or Account Name + City/State/Billing
- Fields compared: Name, BillingStreet, BillingCity, BillingState, BillingPostalCode, Website, Phone

**Contact Matching:**
- Standard Contact Matching Rule: Matches on Email, or Name+Account combination
- Fields compared: Email, FirstName, LastName, AccountId, Phone, MailingStreet

### Behavior During CSV Import
- **Data Import Wizard:** Respects active duplicate rules. Can be configured to block or allow duplicates.
- **Data Loader (SOAP API):** Respects duplicate rules by default. Can be overridden with `allowDuplicates` header.
- **Data Loader (Bulk API):** Does NOT enforce duplicate rules by default.

### Recommendations for Export Tool
- Include `Email` field — it's the primary dedup key across all platforms
- Include `Website` / domain — helps with Account-level dedup
- Consider including an external ID field (e.g., `External_ID__c`) for upsert operations

---

## 10. Common Custom Fields in Sales Orgs

These are fields that nearly every B2B sales org adds. Our export tool should support mapping to these:

### Lead Custom Fields (Common)
| Field Label | Typical API Name | Type | Notes |
|---|---|---|---|
| Lead Score | `Lead_Score__c` | Number | From marketing automation |
| Lead Grade | `Lead_Grade__c` | Picklist | A, B, C, D |
| Technology Stack | `Tech_Stack__c` | Text | Technologies used |
| Company Domain | `Company_Domain__c` | URL/Text | Website domain (dedup key) |
| LinkedIn URL | `LinkedIn_URL__c` | URL | Personal LinkedIn |
| Company LinkedIn | `Company_LinkedIn__c` | URL | Company LinkedIn page |
| SDR Owner | `SDR_Owner__c` | Lookup(User) | |
| Territory | `Territory__c` | Text/Picklist | |
| Enrichment Source | `Enrichment_Source__c` | Text | Where data came from |
| Last Enriched Date | `Last_Enriched_Date__c` | DateTime | |
| Revenue Range | `Revenue_Range__c` | Picklist | $1M-$5M, $5M-$10M, etc. |
| Employee Range | `Employee_Range__c` | Picklist | 1-50, 51-200, etc. |
| Vertical / Segment | `Vertical__c` | Picklist | Industry sub-segment |
| Buying Stage | `Buying_Stage__c` | Picklist | |
| ICP Fit Score | `ICP_Fit_Score__c` | Number | Ideal Customer Profile match |

### Account Custom Fields (Common)
| Field Label | Typical API Name | Type | Notes |
|---|---|---|---|
| Domain | `Domain__c` | URL/Text | Primary dedup key for many orgs |
| Company LinkedIn | `Company_LinkedIn_URL__c` | URL | |
| Technologies | `Technologies__c` | Long Text | |
| Funding Stage | `Funding_Stage__c` | Picklist | Seed, Series A, etc. |
| Total Funding | `Total_Funding__c` | Currency | |
| ICP Tier | `ICP_Tier__c` | Picklist | Tier 1, Tier 2, Tier 3 |
| Target Account | `Target_Account__c` | Boolean | |
| Vertical | `Vertical__c` | Picklist | |
| Region | `Region__c` | Picklist | |
| Year Founded | `Year_Founded__c` | Number/Text | When org was established |

---

## 11. Best Practices for CSV Export Tools

### Column Naming Strategy

**Recommendation:** Use Salesforce **field labels** as column headers (not API names). Reasons:
1. Import Wizard auto-maps based on labels
2. Data Loader users can easily create their own mappings
3. More readable for non-technical users

However, provide an option to switch to API names for Data Loader users.

**Optimal header names for auto-mapping:**

| Our Column Header | SF Lead API Name | SF Account API Name | SF Contact API Name |
|---|---|---|---|
| First Name | `FirstName` | — | `FirstName` |
| Last Name | `LastName` | — | `LastName` |
| Title | `Title` | — | `Title` |
| Email | `Email` | — | `Email` |
| Phone | `Phone` | `Phone` | `Phone` |
| Mobile Phone | `MobilePhone` | — | `MobilePhone` |
| Company | `Company` | `Name` | — |
| Website | `Website` | `Website` | — |
| Industry | `Industry` | `Industry` | — |
| Street | `Street` | `BillingStreet` | `MailingStreet` |
| City | `City` | `BillingCity` | `MailingCity` |
| State/Province | `State` | `BillingState` | `MailingState` |
| Zip/Postal Code | `PostalCode` | `BillingPostalCode` | `MailingPostalCode` |
| Country | `Country` | `BillingCountry` | `MailingCountry` |
| Number of Employees | `NumberOfEmployees` | `NumberOfEmployees` | — |
| Annual Revenue | `AnnualRevenue` | `AnnualRevenue` | — |
| Description | `Description` | `Description` | `Description` |
| Lead Source | `LeadSource` | `AccountSource` | `LeadSource` |
| Lead Status | `Status` | — | — |
| Rating | `Rating` | `Rating` | — |
| Lead Owner | `OwnerId` | `OwnerId` | `OwnerId` |

### Address Formatting
- **Always separate** into Street, City, State, PostalCode, Country
- Never combine into a single field
- State/Province can be full name ("California") or code ("CA") — depends on org setting (State & Country picklists enabled or not)
- Country can be full name ("United States") or ISO code ("US")

### Owner Assignment
- `OwnerId` requires a Salesforce User ID (15/18 char)
- Our tool should export owner **name** or **email** for human readability
- Include a note that OwnerId must be looked up for Data Loader imports
- Import Wizard does NOT support per-row owner assignment

### Record Types
- Export `Record Type` as a human-readable name
- Include a note that `RecordTypeId` (18-char ID) is needed for Data Loader
- Import Wizard sets Record Type globally, not per-row

### Maximum Rows
- Keep exports under **50,000 rows** for Import Wizard compatibility
- For larger exports, split into multiple files
- Data Loader can handle up to 5,000,000 rows

### Character Encoding
- **Always export as UTF-8**
- Include BOM (Byte Order Mark) for Excel compatibility on Windows
- Excel on Windows may misinterpret UTF-8 without BOM (accented characters garbled)

---

## 12. User CSV Column Mapping to Salesforce Fields

The user provided this exact CSV format:

```
Company Name | Website | Quality | Year Established | Number of Employees | Description |
First Name | Last Name | Title | Email | Portfolio | Vertical |
Account Owner | Lead Owner | City | Province / Country
```

### Mapping Table

| User Column | SF Lead Field | SF Lead API Name | SF Account Field | SF Account API Name | Notes |
|---|---|---|---|---|---|
| **Company Name** | Company | `Company` | Account Name | `Name` | Required for Lead |
| **Website** | Website | `Website` | Website | `Website` | Standard field |
| **Quality** | Rating | `Rating` | Rating | `Rating` | Map to Hot/Warm/Cold picklist, or custom field `Quality__c` |
| **Year Established** | — | — | Year Started | `YearStarted` | No standard Lead field; use custom `Year_Established__c` on Lead |
| **Number of Employees** | No. of Employees | `NumberOfEmployees` | Employees | `NumberOfEmployees` | Standard field on both |
| **Description** | Description | `Description` | Description | `Description` | Standard field, max 32KB |
| **First Name** | First Name | `FirstName` | — | — | Standard Lead/Contact field |
| **Last Name** | Last Name | `LastName` | — | — | Required for Lead/Contact |
| **Title** | Title | `Title` | — | — | Standard Lead/Contact field |
| **Email** | Email | `Email` | — | — | Standard Lead/Contact field |
| **Portfolio** | — | — | — | — | Custom field: `Portfolio__c` (no standard equivalent) |
| **Vertical** | — | — | — | — | Custom field: `Vertical__c` (no standard equivalent) |
| **Account Owner** | — | — | Account Owner | `OwnerId` | Needs SF User ID for import |
| **Lead Owner** | Lead Owner | `OwnerId` | — | — | Needs SF User ID for import |
| **City** | City | `City` | Billing City | `BillingCity` | Standard field |
| **Province / Country** | — | — | — | — | **MUST SPLIT** into State + Country (separate fields) |

### Critical Issues with Current Format

1. **"Province / Country" must be split** into two separate columns:
   - `State` (or `BillingState` / `MailingState`) for province
   - `Country` (or `BillingCountry` / `MailingCountry`) for country
   - Salesforce requires these as separate fields

2. **Missing "Street" field** — Consider adding for complete address data

3. **Missing "Postal Code" field** — Important for territory assignment and dedup

4. **"Quality" needs mapping** — Either map to standard `Rating` field (Hot/Warm/Cold) or create custom picklist

5. **"Year Established"** — No standard Lead field. Maps to Account `YearStarted`. For Lead import, needs custom field.

6. **"Portfolio" and "Vertical"** — These are custom fields. Users will need to create `Portfolio__c` and `Vertical__c` in their Salesforce org.

7. **Owner fields contain names, not IDs** — Salesforce requires User IDs for owner assignment. The export should include owner names for readability but document that IDs are needed for import.

### Recommended Improved CSV Format

```csv
Company Name,Website,Quality,Year Established,Number of Employees,Description,First Name,Last Name,Title,Email,Portfolio,Vertical,Account Owner,Lead Owner,City,State/Province,Country,Street,Postal Code,Phone,Mobile Phone,Lead Source,Lead Status,Industry
```

---

## 13. Outreach.io CSV Import Format

### Overview
- Accepts `.csv` files only
- **Max 100,000 rows** per import
- **Must be UTF-8 encoded** (Save As > "CSV UTF-8 (Comma-delimited)")
- Email address is the **primary unique identifier** (one prospect per email)
- Auto-maps CSV column headers to Outreach fields when names match

### Standard Prospect Fields (for CSV)

| Outreach Field | CSV Column Header | Notes |
|---|---|---|
| First Name | `First Name` | |
| Last Name | `Last Name` | |
| Middle Name | `Middle Name` | |
| Nickname | `Nickname` | |
| Title | `Title` | Job title |
| Occupation | `Occupation` | Alternative to Title |
| Email | `Email` | **Primary identifier** |
| Work Phone | `Work Phone` | |
| Home Phone | `Home Phone` | |
| Mobile Phone | `Mobile Phone` | |
| Address City | `Address City` | |
| Address State | `Address State` | |
| Address Country | `Address Country` | |
| Address Street | `Address Street` | |
| Address Street 2 | `Address Street 2` | |
| Address Zip | `Address Zip` | |
| LinkedIn | `LinkedIn` | LinkedIn URL |
| Gender | `Gender` | |
| Source | `Source` | |
| Tags | `Tags` | Semicolon-separated |
| Account | `Account` or `Account name` | Must match existing Account name in Outreach |
| Campaign Name | `Campaign Name` | |
| Region | `Region` | |
| Score | `Score` | |
| Custom 1-35 | `Custom 1` through `Custom 35` | Expandable to 100 |
| Personal Note 1 | `Personal Note 1` | |
| Personal Note 2 | `Personal Note 2` | |
| External ID | `External ID` | For CRM sync |
| External Source | `External Source` | |
| External Owner | `External Owner` | |
| Time Zone | `Time Zone` | EDT, CDT, PDT format |

### Account Fields (for CSV)

| Outreach Field | CSV Column Header |
|---|---|
| Account Name | `Name` or `Account Name` |
| Domain | `Domain` |
| Company Type | `Company Type` |
| Industry | `Industry` |
| Locality | `Locality` |
| Natural Name | `Natural Name` |

### Duplicate Handling Options
- **Skip** — Does not update records that already exist
- **Overwrite Existing Fields** — Replaces existing info
- **Update Missing Fields** — Only fills in blank fields

### Key Gotcha
- Map company column to `Account` or `Account name` (NOT `Company`)
- Accounts must exist in Outreach before associating prospects
- Import prospects first, then assign to accounts separately if accounts don't exist

---

## 14. HubSpot CSV Import Format

### Overview
- Accepts `.csv`, `.xlsx`, `.xls` files
- No explicit row limit (but large files take longer)
- UTF-8 encoding required for foreign characters
- Email is the **unique identifier** for contacts
- Company domain name is the **unique identifier** for companies

### Default Contact Properties (Key Fields)

| HubSpot Property | Internal Name | Notes |
|---|---|---|
| First name | `firstname` | |
| Last name | `lastname` | |
| Email | `email` | **Unique identifier** |
| Phone number | `phone` | |
| Mobile phone number | `mobilephone` | |
| Fax number | `fax` | |
| Job title | `jobtitle` | |
| Company name | `company` | Text field (not association) |
| Industry | `industry` | |
| City | `city` | |
| State/Region | `state` | |
| Country/Region | `country` | |
| Postal code | `zip` | |
| Street address | `address` | |
| Website URL | `website` | |
| LinkedIn URL | `hs_linkedin_url` | |
| Annual revenue | `annualrevenue` | |
| Lead status | `hs_lead_status` | |
| Lifecycle stage | `lifecyclestage` | |
| Contact owner | `hubspot_owner_id` | Requires HubSpot owner ID |
| Description | `description` | |
| Employment Role | `hs_employment_role` | |
| Employment Seniority | `hs_employment_seniority` | |

### Default Company Properties (Key Fields)

| HubSpot Property | Internal Name | Notes |
|---|---|---|
| Company name | `name` | |
| Company domain name | `domain` | **Unique identifier** |
| Phone number | `phone` | |
| Industry | `industry` | |
| Annual revenue | `annualrevenue` | |
| Number of employees | `numberofemployees` | |
| City | `city` | |
| State/Region | `state` | |
| Country/Region | `country` | |
| Postal code | `zip` | |
| Street address | `address` | |
| Street address 2 | `address2` | |
| Website URL | `website` | |
| Description | `description` | |
| Year founded | `founded_year` | |
| Type | `type` | |
| LinkedIn company page | `linkedin_company_page` | |
| Facebook company page | `facebook_company_page` | |
| Twitter handle | `twitterhandle` | |
| Owner | `hubspot_owner_id` | |
| Lifecycle stage | `lifecyclestage` | |
| Lead status | `hs_lead_status` | |
| Target account | `hs_target_account` | |

### Multi-Value Fields
- Multiple emails: Use "Additional email addresses" column, separated by semicolons
- Multiple domains: Use "Additional domains" column, separated by semicolons

### Association via Import
- To associate contacts with companies in a single import, include both contact fields AND company fields in one CSV
- HubSpot uses Company domain name to match/create companies
- Use "Company domain name" column to link contacts to companies

---

## 15. Competitive Landscape — Tools That Do This Today

### Clay.com
- Exports enriched data as CSV
- Column names reflect the enrichment blocks added (not standardized to SF field names)
- Has direct Salesforce integration (push to CRM)
- User must manually map Clay columns to SF fields when doing CSV export
- Supports push to Salesforce, HubSpot, Outreach natively via integrations

### Apollo.io
- CSV export uses headers like: First Name, Last Name, Title, Company, Email, Phone, etc.
- Generally uses human-readable labels similar to Salesforce field labels
- Direct CRM push available

### ZoomInfo
- CSV export with standardized column names
- Fields: First Name, Last Name, Job Title, Company Name, Email Address, Phone Number, etc.
- Has Salesforce-specific export format option

### Clearbit (now part of HubSpot)
- Enrichment data maps directly to HubSpot properties
- For Salesforce, writes to standard and custom fields via integration

### Lusha
- CSV export for contacts
- Fields: First Name, Last Name, Email, Phone, Company, Title, etc.
- Direct Salesforce/HubSpot push

### Common Pattern Across Tools
Most enrichment tools use these column headers for CSV exports:
```
First Name, Last Name, Title, Company, Email, Phone, LinkedIn URL,
City, State, Country, Industry, Number of Employees, Annual Revenue,
Website, Description
```

This closely mirrors Salesforce Lead field labels, making import straightforward.

---

## Summary — Recommended CSV Export Strategy

### For Maximum Compatibility Across Platforms

Use these column headers (they map cleanly to Salesforce, HubSpot, and Outreach):

```csv
First Name,Last Name,Title,Email,Phone,Mobile Phone,Company,Website,Industry,Description,Street,City,State/Province,Postal Code,Country,Number of Employees,Annual Revenue,Lead Source,Lead Status,Rating,LinkedIn URL,Year Founded
```

### Platform-Specific Export Modes

Our tool should offer three export presets:

#### 1. Salesforce Lead Import
```csv
FirstName,LastName,Title,Email,Phone,MobilePhone,Company,Website,Industry,Description,Street,City,State,PostalCode,Country,NumberOfEmployees,AnnualRevenue,LeadSource,Status,Rating
```

#### 2. Salesforce Account + Contact Import (two files)

**accounts.csv:**
```csv
Name,Website,Industry,Description,BillingStreet,BillingCity,BillingState,BillingPostalCode,BillingCountry,NumberOfEmployees,AnnualRevenue,AccountSource,Rating,YearStarted
```

**contacts.csv:**
```csv
FirstName,LastName,Title,Email,Phone,MobilePhone,AccountId,Department,LeadSource,MailingStreet,MailingCity,MailingState,MailingPostalCode,MailingCountry
```

#### 3. HubSpot Contact Import
```csv
firstname,lastname,jobtitle,email,phone,mobilephone,company,website,industry,city,state,country,zip,address,annualrevenue,hs_lead_status,lifecyclestage
```

#### 4. Outreach Prospect Import
```csv
First Name,Last Name,Title,Email,Work Phone,Mobile Phone,Account,Address Street,Address City,Address State,Address Zip,Address Country,LinkedIn,Source,Tags
```

### Custom Field Strategy
For custom fields like Portfolio, Vertical, Quality:
- Include them in the CSV with clear column headers
- Document that users need to create matching custom fields in Salesforce (with `__c` suffix)
- Suggest API names: `Portfolio__c`, `Vertical__c`, `Quality__c`

### The "Province / Country" Problem
**This MUST be split into separate columns.** Every platform (Salesforce, HubSpot, Outreach) requires State/Province and Country as separate fields. The current combined format will cause import failures.
