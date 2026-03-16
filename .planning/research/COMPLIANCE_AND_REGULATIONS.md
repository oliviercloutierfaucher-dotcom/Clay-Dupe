# Legal Compliance for B2B Cold Email Outreach & Data Enrichment

> **Research Date:** 2026-03-08
> **Jurisdictions Covered:** United States, Canada, United Kingdom, European Union
> **Purpose:** Comprehensive compliance reference for building a self-hosted B2B data enrichment and outreach platform

---

## Table of Contents

1. [United States Regulations](#1-united-states-regulations)
   - [CAN-SPAM Act](#11-can-spam-act)
   - [State-Level Privacy Laws (CCPA/CPRA and Beyond)](#12-state-level-privacy-laws)
   - [FTC Guidelines](#13-ftc-guidelines)
2. [Canada (CASL)](#2-canada-casl)
3. [UK/EU (GDPR + PECR)](#3-ukeu-gdpr--pecr)
   - [GDPR Article 6 — Legal Basis](#31-gdpr-article-6--legal-basis-for-b2b-cold-email)
   - [UK PECR](#32-uk-pecr)
   - [Data Storage and Enrichment Under GDPR](#33-data-storage-and-enrichment-under-gdpr)
   - [Right to Be Forgotten](#34-right-to-be-forgotten--right-to-erasure)
   - [Data Processing Records (Article 30)](#35-data-processing-records-article-30)
   - [GDPR Fines and Enforcement Trends](#36-gdpr-fines-and-enforcement-trends-2025-2026)
4. [Practical Compliance for Enrichment Tools](#4-practical-compliance-for-enrichment-tools)
   - [How Major Vendors Handle Compliance](#41-how-major-vendors-handle-compliance)
   - [What Our Tool Must Implement](#42-what-our-tool-must-implement)
5. [Best Practices for a Self-Hosted Tool](#5-best-practices-for-a-self-hosted-tool)
6. [Email Sending Compliance](#6-email-sending-compliance)
7. [Jurisdiction Comparison Matrix](#7-jurisdiction-comparison-matrix)
8. [Sources](#8-sources)

---

## 1. United States Regulations

### 1.1 CAN-SPAM Act

The CAN-SPAM Act (Controlling the Assault of Non-Solicited Pornography And Marketing Act of 2003) is the primary US federal law governing commercial email.

#### Key Principle: CAN-SPAM is an OPT-OUT Law

Unlike CASL or GDPR, CAN-SPAM **allows sending commercial emails without prior consent**. Recipients must be given the ability to opt out, but you do not need permission before sending the first email. This applies equally to B2B and B2C emails.

#### Mandatory Requirements for Every Commercial Email

| Requirement | Details |
|---|---|
| **Accurate Header Information** | The "From," "To," and routing information must be truthful and identify the person/business initiating the message |
| **Non-Deceptive Subject Lines** | Subject lines must accurately reflect the content of the email body |
| **Identify as Advertisement** | The message must clearly and conspicuously disclose that it is a commercial solicitation |
| **Valid Physical Postal Address** | Every email must include the sender's current valid physical mailing address (can be a PO Box or registered commercial mail receiving agency) |
| **Clear Opt-Out Mechanism** | Every email must include a clear, conspicuous mechanism for opting out of future emails |
| **Honor Opt-Outs Within 10 Business Days** | Once a recipient unsubscribes, you must stop emailing them within 10 business days |
| **No Opt-Out Fee or Barriers** | You cannot require the recipient to pay a fee, provide information beyond their email address, or take any step other than a single reply email or visiting a single web page to opt out |
| **No Selling/Transferring Opt-Out Addresses** | You cannot sell or transfer email addresses of people who have opted out |
| **Monitor Third Parties** | If you hire another company to handle your email marketing, you are still legally responsible for compliance |

#### What Is Prohibited

- Using false or misleading header information
- Using deceptive subject lines
- Failing to include an opt-out mechanism
- Failing to honor opt-out requests within 10 business days
- Sending from harvested email addresses obtained via automated means (scraping)
- Using automated tools to generate email addresses by combining names and domains
- Relaying messages through open relays or proxies without permission

#### Penalties

- **Civil penalties: Up to $51,744 per individual non-compliant email** (adjusted for inflation as of 2025)
- No maximum cap on total fines -- a campaign of 1,000 non-compliant emails could result in $51+ million in penalties
- **Criminal penalties** for aggravated violations: accessing others' computers to send spam, registering email accounts/domains with false information, relaying messages through unauthorized computers
- Both the company sending the email AND the company whose product is promoted can be held liable

#### B2B vs. B2C Treatment

CAN-SPAM does **not** differentiate between B2B and B2C emails. All commercial electronic messages are subject to the same requirements regardless of whether they target consumers or businesses. The only distinction is for "transactional or relationship" messages (e.g., order confirmations, warranty information), which are exempt from most CAN-SPAM requirements.

---

### 1.2 State-Level Privacy Laws

#### California (CCPA/CPRA)

The California Consumer Privacy Act (CCPA), as amended by the California Privacy Rights Act (CPRA), is the most comprehensive US state privacy law and the only state law that explicitly applies to B2B contact data.

**Critical Change (January 1, 2023):** The temporary B2B and employee data exemptions expired. Personal information exchanged in B2B contexts -- including business email addresses -- is now fully subject to CPRA.

**Impact on B2B Data Enrichment:**

| Requirement | Details |
|---|---|
| **Right to Know** | California residents can request what data you've collected about them, even in a B2B context |
| **Right to Delete** | They can request deletion of their personal information |
| **Right to Correct** | They can request correction of inaccurate data |
| **Right to Opt-Out of Sale/Sharing** | Must provide a "Do Not Sell or Share My Personal Information" link |
| **Right to Limit Use of Sensitive Data** | Must provide a "Limit the Use of My Sensitive Personal Information" option |
| **Global Privacy Control (GPC)** | Must recognize and honor GPC browser signals as valid opt-out requests |
| **Data Minimization** | Only collect data reasonably necessary and proportionate to the stated purpose |

**2026 Updates (Effective January 1, 2026):**
- Enhanced requirements for automated decision-making technology
- Mandatory opt-out confirmations
- Expanded compliance requirements for data brokers
- Stricter rules on cross-context behavioral advertising

**Applicability Thresholds:** CCPA/CPRA applies to for-profit businesses that do business in California AND meet one of:
- Annual gross revenue > $25 million
- Buy, sell, or share personal information of 100,000+ California residents/households/devices
- Derive 50%+ of annual revenue from selling/sharing California residents' personal information

#### Other State Privacy Laws (as of 2026)

**19 states** have enacted comprehensive privacy laws. Key ones affecting B2B data enrichment:

| State | Law | B2B Coverage | Effective Date |
|---|---|---|---|
| **California** | CCPA/CPRA | Full coverage of B2B contact data | Active (exemptions expired Jan 2023) |
| **Colorado** | CPA | Business representatives get full rights as data subjects | Active |
| **Virginia** | VCDPA | Amendments effective 2026 | Active, amendments July 2026 |
| **Connecticut** | CTDPA | Major overhaul effective July 2026 | Active, amendments July 2026 |
| **Texas** | TDPSA | Large companies doing business in Texas | Active (July 2024) |
| **Indiana** | IDPA | Amendments effective 2026 | Active |
| **Utah** | UCPA | Amendments effective 2026 | Active |
| **Kentucky** | KCDPA | Amendments effective 2026 | Active |
| **Oregon** | OCPA | Amendments effective 2026 | Active |

**Key Takeaway:** While California is the most impactful for B2B data, Colorado also grants full data subject rights to business representatives. The trend is toward more states removing B2B exemptions.

#### State-Level Do Not Call Lists

12 states maintain their own DNC lists in addition to the federal registry:
Colorado, Florida, Indiana, Louisiana, Massachusetts, Mississippi, Missouri, Oklahoma, Pennsylvania, Tennessee, Texas, and Wyoming.

Three states (Colorado, Mississippi, Pennsylvania) allow **businesses** to register their numbers on state DNC lists.

---

### 1.3 FTC Guidelines

#### Commercial Email Enforcement

The FTC is the primary enforcement agency for CAN-SPAM. Key enforcement principles:

- The FTC can pursue enforcement actions against both the sender and the company whose product/service is promoted
- Penalties are $51,744 per violation (per email)
- The FTC has pursued enforcement actions against companies using deceptive subject lines, misleading sender information, and non-functional unsubscribe mechanisms

#### Telemarketing Sales Rule (TSR) -- 2025 Changes

**Critical 2025 Update:** The FTC extended the Telemarketing Sales Rule to cover B2B telemarketing calls. Previously, most B2B communications were exempt.

- B2B calls are now subject to misrepresentation prohibitions
- Heightened recordkeeping requirements apply to B2B telemarketers
- Civil penalties of $51,744+ per violation
- Effective January 9, 2025

**Relevance to Outreach Tools:** If your platform supports phone outreach in addition to email, the TSR now directly applies to B2B cold calling.

---

## 2. Canada (CASL)

### 2.1 Overview

Canada's Anti-Spam Legislation (CASL) is **the strictest anti-spam law in the world**. It is fundamentally different from CAN-SPAM.

### 2.2 Key Differences from CAN-SPAM

| Aspect | CAN-SPAM (US) | CASL (Canada) |
|---|---|---|
| **Consent Model** | Opt-out (can email without permission) | **Opt-in (must have consent BEFORE sending)** |
| **Penalties** | $51,744 per email | **$1M per violation (individual) / $10M per violation (business)** |
| **B2B Treatment** | Same as B2C | Same as B2C -- no B2B exemption |
| **Enforcement** | FTC | CRTC (Canadian Radio-television and Telecommunications Commission) |
| **Record Keeping** | No specific requirement | Must keep consent records for 3 years after relationship ends |
| **Private Right of Action** | No | Yes (individuals can sue) |

### 2.3 Consent Requirements

CASL requires either **express consent** or **implied consent** before sending a commercial electronic message (CEM).

#### Express Consent

Obtained when the recipient explicitly agrees to receive messages. Must include:
- The purpose for which consent is sought
- The name and contact information of the person seeking consent
- A statement that consent can be withdrawn at any time

Express consent does not expire (valid until withdrawn).

#### Implied Consent for B2B

Implied consent is the primary mechanism for B2B cold email in Canada. It is available in these specific scenarios:

**1. Existing Business Relationship (EBR)**
| Scenario | Implied Consent Duration |
|---|---|
| Recipient purchased a product/service, signed a contract, or completed a transaction | **2 years** from date of transaction |
| Recipient made an inquiry or submitted an application | **6 months** from date of inquiry |

**2. Conspicuous Publication (Main Avenue for Cold Email)**

This is the most relevant provision for B2B cold outreach. ALL THREE conditions must be met:

1. The recipient's email address is **publicly posted** (company website, professional directory, LinkedIn profile, etc.)
2. The publication is **not accompanied by a statement** that they do not wish to receive unsolicited commercial messages
3. Your message is **directly relevant** to the recipient's business role, functions, or duties

**Example:** If you find a VP of Sales' email on their company's "Team" page and you sell sales software, implied consent likely exists. If you sell office furniture, it likely does not.

**3. Referral**
If someone refers a contact to you, you have implied consent for **one message only**, and you must name the person who referred them.

### 2.4 Mandatory Email Content Requirements Under CASL

Every commercial email sent to Canadian recipients must include:
- Sender's name (or the name of the business on whose behalf the message is sent)
- Sender's mailing address and either a phone number, email address, or web address
- A functioning unsubscribe mechanism
- Unsubscribe requests must be honored within **10 business days**

### 2.5 Penalties and Enforcement

- **Individuals:** Up to $1 million CAD per violation
- **Businesses:** Up to $10 million CAD per violation
- **Private right of action:** Individuals can sue for $200 per violation (capped at $1M per day)

**Recent Enforcement (2025):**
- 153 Notices to Produce
- 123 Warning Letters
- 5 Preservation Demands
- 1 Notice of Violation

The CRTC is actively monitoring and enforcing CASL compliance.

### 2.6 Impact on Enrichment Tools

For Canadian contacts, enrichment tools must:
- Track the source of the email address (to prove "conspicuous publication")
- Document the relevance to the recipient's business role
- Flag contacts that lack a valid consent basis
- Maintain consent records for 3 years after the relationship ends
- Implement implied consent expiration (auto-expire after 2 years for EBR, 6 months for inquiries)

---

## 3. UK/EU (GDPR + PECR)

### 3.1 GDPR Article 6 -- Legal Basis for B2B Cold Email

Under GDPR, you need a lawful basis to process personal data. For B2B cold email, the relevant legal basis is **Legitimate Interest** under Article 6(1)(f).

#### How Legitimate Interest Applies to B2B Prospecting

You can send cold emails to business professionals in the EU without prior consent IF you can demonstrate:

1. **Genuine Business Interest (Purpose Test):** Your company has a concrete commercial goal -- acquiring new clients, developing a market, etc.
2. **Necessity Test:** Email is a necessary and proportionate channel for reaching the prospect (as opposed to alternatives)
3. **Balancing Test:** Your commercial interest does not override the prospect's fundamental rights and freedoms

#### Legitimate Interest Assessment (LIA) -- Required Documentation

Before sending any B2B cold email in the EU, you must conduct and document a Legitimate Interest Assessment. The LIA must cover:

| Element | What to Document |
|---|---|
| **Purpose** | Why you are emailing this specific person (e.g., they are a decision-maker in your target market) |
| **Necessity** | Why email is the appropriate channel (vs. other means) |
| **Balancing** | Why the prospect's rights don't override your interest (e.g., the email is relevant to their professional role, you provide an easy opt-out, data is minimal) |
| **Safeguards** | What measures you've implemented (easy opt-out, data minimization, retention limits) |

**Template Legitimate Interest Assessment:**

> **Processing Activity:** B2B prospecting via email
>
> **Purpose:** To contact business professionals about [product/service] relevant to their professional role
>
> **Necessity:** Email is the standard channel for B2B communication; the data processed is limited to professional contact information
>
> **Balancing:** The prospect is contacted in their professional capacity. The data used is business contact information typically expected to be used for such purposes. An easy opt-out is provided in every message. Data is retained for a maximum of [X] months. The prospect is informed of their rights on first contact.
>
> **Safeguards:** Opt-out mechanism in every email, data retention policy of [X] months, right to erasure honored within 30 days, processing records maintained per Article 30.

#### Country-Specific Variations Within the EU

| Country | B2B Cold Email Approach |
|---|---|
| **France** | Allowed under legitimate interest for B2B. CNIL's August 2026 changes require explicit opt-in for B2C only. |
| **Germany** | **Most restrictive.** Generally requires prior consent even for B2B email under its ePrivacy implementation (UWG). |
| **Italy** | Generally allows B2B under legitimate interest, but stricter enforcement |
| **Spain** | Allows B2B under legitimate interest with proper documentation |
| **Netherlands** | Allows B2B cold email to corporate addresses; individual addresses need consent |

**Critical Warning:** Germany's Unfair Competition Act (UWG) effectively prohibits unsolicited commercial email even in B2B contexts without prior consent. **Do not cold email German business contacts without express consent.**

---

### 3.2 UK PECR

The Privacy and Electronic Communications Regulations (PECR) work alongside UK GDPR to regulate direct marketing by electronic means.

#### B2B Corporate Email -- The Key Distinction

**PECR does NOT require consent for emails sent to corporate subscribers.**

| Recipient Type | Consent Required? | Example |
|---|---|---|
| **Corporate subscriber** (company email: info@company.co.uk, sales@company.co.uk) | **No** -- can email freely | Generic company addresses |
| **Individual at a company** (john.smith@company.co.uk) | Yes -- UK GDPR applies | Named person at corporate address |
| **Sole trader / partnership** | Yes -- treated as individual | One-person businesses |

**Who qualifies as a "corporate subscriber":**
- Limited companies
- LLPs (Limited Liability Partnerships)
- Other incorporated bodies
- Contacted via generic business addresses

**Important Caveat:** Even when PECR doesn't require consent (corporate subscriber), UK GDPR still applies to **named individuals**. So emailing john.smith@company.co.uk requires a lawful basis under UK GDPR (typically legitimate interest).

#### Soft Opt-In (Primarily B2C)

The "soft opt-in" exemption under PECR allows marketing without explicit consent when:
1. Contact details were collected during a sale or negotiation of a sale
2. An opt-out was offered at the point of collection AND in every subsequent message
3. Marketing is only about your own **similar** products and services

This is primarily useful for existing customer marketing, not cold outreach.

#### Mandatory Requirements for All B2B Emails (UK)

Regardless of corporate subscriber status:
- **Identify yourself** as the sender
- **Provide an opt-out** in every message
- **Honor opt-outs** -- the right to object to direct marketing is absolute

#### 2025-2026 Changes: Data Use and Access Act (DUAA)

The DUAA 2025 amends PECR, primarily extending the "soft opt-in" exception to charities. No significant changes to B2B cold email rules as of March 2026.

---

### 3.3 Data Storage and Enrichment Under GDPR

#### What Data Can You Legally Store?

Under GDPR, you can store and process personal data for B2B enrichment purposes if you have a lawful basis (typically legitimate interest). The data must be:

- **Adequate:** Sufficient for the stated purpose
- **Relevant:** Directly related to the purpose
- **Limited:** No more than what is necessary (data minimization principle)

**Typically permissible B2B enrichment data:**
- Full name
- Business email address
- Job title / role
- Company name
- Company size / industry
- Business phone number
- LinkedIn profile URL
- Company website

**Higher risk / requires strong justification:**
- Personal email addresses
- Personal phone numbers
- Home address
- Salary information
- Age / date of birth

#### Data Retention Limits

| Prospect Status | Maximum Retention Period |
|---|---|
| Active prospect (currently in outreach) | Duration of active sales cycle |
| Inactive prospect (no interaction) | **3 years maximum** from last contact (CNIL guidance) |
| Customer | Contractual duration + accounting obligations (typically 10 years for invoices) |
| Opted-out contact | Delete active data; keep minimum suppression record only |

#### Obligations on First Contact

When you email a prospect whose data you obtained from a third-party source (e.g., enrichment tool), you **must inform them** on first contact:
- Your identity and contact details
- The purposes of processing
- The legal basis (legitimate interest)
- Their rights (access, rectification, erasure, objection)
- The source of their data
- How long you will retain their data

---

### 3.4 Right to Be Forgotten / Right to Erasure

Under GDPR Article 17, individuals can request deletion of their personal data when:
- They object to prospecting
- The data is no longer needed for its original purpose
- They withdraw consent
- The data was unlawfully processed

#### Implementation Requirements

| Step | Action | Timeline |
|---|---|---|
| 1 | Acknowledge the request | Immediately |
| 2 | Verify the requester's identity | Within 3 days |
| 3 | Process deletion across ALL systems | Within **30 days** |
| 4 | Confirm deletion to the requester | Within 30 days |
| 5 | Propagate to third parties | "Without undue delay" |

#### Suppression List Best Practice

When processing a deletion request:
1. **Delete** all active data (CRM records, email lists, prospecting databases)
2. **Retain** a minimal suppression record containing ONLY the email address (or minimum identifier needed) to **prevent accidental re-enrollment**
3. **Document** the request: date received, date processed, action taken
4. **Propagate** the deletion to all systems -- CRM, email platform, enrichment tools, spreadsheets

**A partial update (deleting from one system but not others) can still be considered a compliance failure.**

#### Handling with Third-Party Enrichment

If you use third-party enrichment tools, corrections and deletions must propagate across ALL systems. You must:
- Notify enrichment providers of deletion requests
- Ensure the contact is not re-enriched from external sources
- Document the chain of deletion

---

### 3.5 Data Processing Records (Article 30)

GDPR Article 30 requires maintaining Records of Processing Activities (ROPA). For a B2B enrichment and outreach tool, you must document:

#### For Controllers (You, the User)

| Field | What to Record |
|---|---|
| Controller details | Name, contact details, DPO contact |
| Purposes of processing | "B2B sales prospecting," "Lead enrichment," "Email marketing" |
| Categories of data subjects | Business contacts, decision-makers, prospects |
| Categories of personal data | Name, business email, job title, company, phone |
| Recipients | Internal sales team, email service providers, CRM, enrichment APIs |
| International transfers | Any data transferred outside EU/UK (e.g., to US-based enrichment APIs) |
| Retention periods | Per the retention schedule above |
| Security measures | Encryption, access controls, audit logs |

#### For Processors (The Enrichment Tool Itself)

| Field | What to Record |
|---|---|
| Processor details | Name and contact details |
| Controller details | Each customer using the tool |
| Categories of processing | Data enrichment, email verification, company lookup |
| International transfers | If data is sent to non-EU servers |
| Security measures | Technical and organizational safeguards |

**ROPA must be kept current and updated whenever processing activities change.**

---

### 3.6 GDPR Fines and Enforcement Trends (2025-2026)

#### Overall Landscape

- Annual GDPR fines have stabilized at approximately **EUR 1.2 billion per year** (2025 and 2026)
- Cumulative total since May 2018: **EUR 7.1 billion**
- Average of **400+ data breach notifications per day** (22% year-on-year increase)
- Spain leads in volume of fines: **1,021 fines totaling ~EUR 120.75 million** (as of September 2025)

#### Major 2025 Enforcement Actions

| Entity | Fine | Reason |
|---|---|---|
| TikTok | EUR 530M | Illegal transfer of EEA user data to China |
| Google LLC | EUR 200M | Inserting ads disguised as emails in Gmail inboxes |
| Google Ireland | EUR 125M | Cookie consent violations during account creation |
| Vodafone Germany | EUR 45M | Poor data protection controls and security flaws |

#### Enforcement Priorities Relevant to B2B Outreach

Regulators are specifically targeting:
- **Non-compliant email marketing** practices
- **Inadequate consent collection** mechanisms
- **Difficult unsubscribe procedures**
- International data transfers
- Transparency failures
- AI-related data processing

#### Maximum Penalty Exposure

- **Up to 4% of global annual revenue** or EUR 20 million, whichever is greater
- Both administrative fines and compensation claims from individuals

---

## 4. Practical Compliance for Enrichment Tools

### 4.1 How Major Vendors Handle Compliance

#### Clay

- Claims GDPR and CCPA compliance
- Supports CCPA do-not-call lists
- **Critical limitation:** Clay uses a "waterfall enrichment" model with multiple third-party data providers, each with their own sourcing practices
- **Clay does not own its data** -- compliance responsibility falls on the user to ensure each integrated data source is compliant
- Users must manage compliance based on how they source and use data across connected providers

#### Apollo.io

- Complies with EU/UK GDPR
- Complies with EU-US Data Privacy Framework, UK Extension, and Swiss-US DPF
- Complies with CCPA/CPRA
- Provides a Data Processing Agreement (DPA)
- Offers opt-out and data deletion mechanisms
- Publishes a privacy policy with data rights information
- Provides transparency about data collection (public sources, user contributions, partnerships)

#### Cognism

- **Most compliance-focused vendor** in the market
- Screens telephone database against **15 Do Not Call registries** worldwide (UK, USA, Canada, Australia, Germany, France, Spain, Ireland, Belgium, Croatia, Portugal, Italy, Sweden, Norway, and more)
- All business contacts are **notified of their entrance into the database**
- Contacts flagged on national DNC lists can be **surfaced or suppressed** at administrator discretion
- Builds GDPR and CCPA compliance into core data collection methodology
- Maintains audit-ready metadata documenting data sourcing and consent

#### Dropcontact (GDPR-Compliant Model)

- **No database approach:** Dropcontact never stores, sells, or reuses emails or personal information
- Data is processed in real-time using proprietary algorithms (input: first name + last name + company name)
- Results are generated on the fly and immediately returned -- no data is retained
- **Only B2B enrichment tool audited by the CNIL** (France's data protection authority)
- All personal data destroyed within 1 month after service completion
- This "structural GDPR compliance" eliminates database-related risks entirely

---

### 4.2 What Our Tool Must Implement

Based on analysis of all four jurisdictions and vendor approaches, our self-hosted tool must implement:

#### Opt-Out / Unsubscribe Management

| Feature | Requirement |
|---|---|
| Global suppression list | Centralized list that prevents re-enrollment of opted-out contacts |
| One-click unsubscribe | RFC 8058 List-Unsubscribe and List-Unsubscribe-Post headers |
| Visible footer opt-out | Clear unsubscribe link in every email |
| Processing timeline | Honor opt-outs within 10 business days (CAN-SPAM/CASL) or 2 days (Gmail/Yahoo) |
| Cross-channel sync | Opt-out in one channel suppresses across ALL channels |
| Audit trail | Log every opt-out with timestamp and source |

#### Data Retention and Deletion

| Feature | Requirement |
|---|---|
| Configurable retention periods | Allow users to set retention by jurisdiction (e.g., 3 years EU, indefinite US) |
| Automatic data expiration | Auto-flag or delete records that exceed retention period |
| Right to erasure workflow | Accept, process, and confirm deletion requests within 30 days |
| Suppression-on-delete | Keep minimum identifier on suppression list when deleting |
| Cascade deletion | Propagate deletions across all connected systems |
| Deletion audit log | Record all deletion requests, actions, and confirmations |

#### Consent Tracking

| Feature | Requirement |
|---|---|
| Per-contact legal basis | Record the lawful basis for each contact (legitimate interest, implied consent, express consent) |
| Consent source tracking | Document where/how consent was obtained |
| Consent timestamps | Record when consent was given or implied |
| Consent expiration | Auto-expire implied consent per CASL rules (6 months for inquiries, 2 years for EBR) |
| Consent withdrawal | Process and propagate consent withdrawals immediately |

#### DNC (Do Not Contact) List Checking

| Feature | Requirement |
|---|---|
| Federal DNC Registry (US) | Check against the National Do Not Call Registry (updated every 31 days minimum) |
| State DNC lists | Check against 12 state-level DNC lists |
| TPS/CTPS (UK) | Check against Telephone Preference Service lists |
| International DNC | Support DNC checking for target countries |
| Internal DNC list | Maintain company-specific suppression lists |
| Real-time screening | Flag DNC contacts before outreach, not after |

#### Region-Based Compliance Rules

| Feature | Requirement |
|---|---|
| Auto-detect country | Determine contact jurisdiction from email domain, phone number, company HQ, or explicit country field |
| Jurisdiction-specific rules | Apply appropriate compliance rules based on detected jurisdiction |
| Germany blocking | Flag/block cold email to German contacts without express consent |
| CASL consent check | Verify implied consent basis exists before emailing Canadian contacts |
| GDPR first-contact notice | Auto-include data source and rights information when emailing EU contacts for the first time |
| Compliance warnings | Surface warnings in the UI when actions may violate jurisdiction-specific rules |

---

## 5. Best Practices for a Self-Hosted Tool

### 5.1 Compliance Features to Build

**Priority 1 -- Must Have (Legal Requirement):**
1. Global suppression/DNC list with real-time checking
2. One-click unsubscribe mechanism (RFC 8058)
3. Opt-out processing within 10 business days
4. Right to erasure workflow (30-day SLA)
5. Data retention policies with auto-expiration
6. Per-contact legal basis tracking
7. Physical address in every email
8. Accurate sender identification
9. Consent record keeping (timestamps, sources)
10. Processing records (Article 30 ROPA)

**Priority 2 -- Should Have (Risk Mitigation):**
1. Country/jurisdiction auto-detection
2. Jurisdiction-specific compliance warnings in UI
3. Germany consent gate (block cold email without express consent)
4. CASL implied consent validator
5. GDPR first-contact data notice template
6. Deletion cascade across connected systems
7. Audit trail for all compliance-relevant actions
8. Data source tracking for enriched contacts

**Priority 3 -- Nice to Have (Best Practice):**
1. Legitimate Interest Assessment (LIA) templates
2. Compliance dashboard/reporting
3. Automated consent expiration reminders
4. Cross-border data transfer documentation
5. DPA (Data Processing Agreement) template for users
6. Compliance mode toggle (strict EU mode, moderate US mode, etc.)

### 5.2 Suppression / DNC List Implementation

```
Suppression List Schema:
- email (primary key, hashed for privacy)
- source: "user_unsubscribe" | "bounce" | "complaint" | "manual" | "erasure_request" | "dnc_registry"
- date_added: timestamp
- reason: free text
- jurisdiction: "US" | "CA" | "UK" | "EU" | "global"
- added_by: user ID
- expires: timestamp (null = permanent)
```

**Processing Rules:**
1. Check suppression list BEFORE every send
2. Check suppression list BEFORE enrichment (don't re-enrich deleted contacts)
3. Sync suppression list across all sending domains/mailboxes
4. Never allow removal of suppression entries without compliance officer approval
5. Import/export suppression lists for portability

### 5.3 Data Retention Policies

**Recommended Defaults:**

| Data Category | US | Canada | UK/EU |
|---|---|---|---|
| Active prospect | No limit | Until consent expires | Duration of active outreach |
| Inactive prospect | No limit | 6 months (inquiry) / 2 years (EBR) | 3 years from last contact |
| Opted-out contact | Suppress only | Suppress only | Suppress only (minimum data) |
| Enrichment data | No limit | Same as contact | Same as contact |
| Consent records | 3 years recommended | 3 years after relationship ends | Duration of processing + 3 years |
| Email send logs | 3 years recommended | 3 years | 3 years |

### 5.4 Per-Contact Consent / Legal Basis Tracking

Every contact record should include:

```
Consent Record:
- contact_id: reference
- legal_basis: "legitimate_interest" | "implied_consent_publication" | "implied_consent_ebr" | "express_consent" | "none"
- basis_details: "Email found on company website team page, relevant to recipient's VP Sales role"
- consent_date: timestamp
- consent_source: "website_form" | "public_directory" | "business_card" | "referral" | "enrichment_api"
- consent_expires: timestamp (null = no expiration)
- jurisdiction: "US" | "CA" | "UK" | "EU_FR" | "EU_DE" | etc.
- lia_completed: boolean (for GDPR contacts)
- first_contact_notice_sent: boolean (for GDPR contacts)
- status: "active" | "opted_out" | "deleted" | "expired"
```

### 5.5 Cross-Border Data Handling

When a US-based tool enriches contacts from EU/UK/Canada:

| Scenario | Requirements |
|---|---|
| **US tool processing EU data** | Requires appropriate transfer mechanism: EU-US Data Privacy Framework certification, Standard Contractual Clauses (SCCs), or Binding Corporate Rules |
| **US tool processing UK data** | UK Extension to EU-US DPF, or UK International Data Transfer Agreement/Addendum |
| **US tool processing Canadian data** | PIPEDA adequacy -- generally permitted, but CASL consent rules still apply |
| **Self-hosted (on-premise)** | If data stays within user's infrastructure, transfer mechanisms may not apply, but jurisdictional processing rules still do |

**Self-hosted advantage:** By keeping data within the user's own infrastructure, many cross-border transfer concerns are eliminated. However, if the tool calls external enrichment APIs that process data outside the contact's jurisdiction, transfer mechanisms are still required.

### 5.6 Compliance Warnings in the UI

The tool should display contextual warnings at key interaction points:

| Trigger | Warning |
|---|---|
| Adding a contact with .de email domain | "German contacts generally require express consent for cold email under UWG. Verify consent before sending." |
| Adding a contact with .ca email domain | "Canadian contacts require implied or express consent under CASL. Verify consent basis before sending." |
| Sending first email to EU contact | "GDPR requires informing this contact of data source, processing purposes, and their rights on first contact." |
| Contact has no legal basis recorded | "No legal basis recorded for this contact. Select a lawful basis before processing." |
| Contact approaching retention limit | "This contact's data is approaching the configured retention limit. Review or delete." |
| Implied consent approaching expiration | "Implied consent for this CASL contact expires in [X] days. Obtain express consent or cease communication." |
| Bulk import without consent metadata | "Imported contacts lack consent/legal basis metadata. Assign legal basis before outreach." |

---

## 6. Email Sending Compliance

### 6.1 Technical Authentication Requirements

As of 2025-2026, ALL major email providers (Google, Yahoo, Microsoft) enforce:

| Protocol | Purpose | Requirement |
|---|---|---|
| **SPF** (Sender Policy Framework) | Specifies which servers can send email for your domain | Required -- publish SPF record in DNS |
| **DKIM** (DomainKeys Identified Mail) | Adds a digital signature to verify email authenticity | Required -- configure DKIM keys |
| **DMARC** (Domain-based Message Authentication, Reporting, and Conformance) | Tells inbox providers what to do with failed authentication | Required -- minimum p=none, recommended p=quarantine or p=reject |
| **List-Unsubscribe** | RFC 8058 one-click unsubscribe header | Required for all marketing/commercial emails |
| **List-Unsubscribe-Post** | Companion header for one-click unsubscribe | Required alongside List-Unsubscribe |

**Implementation Timeline for New Domains:**
- Day 1-2: Publish SPF, DKIM, DMARC records. Add List-Unsubscribe headers.
- Day 1-14: Begin warmup, ramp from 10-20 emails/day to target volume.
- Day 14+: Monitor deliverability metrics and adjust.

### 6.2 Email Warmup and Compliance

Email warmup is not a legal requirement but is essential for deliverability (which indirectly affects compliance -- undelivered opt-out confirmations could create liability).

| Phase | Daily Volume | Duration |
|---|---|---|
| **Week 1** | 5-10 emails per inbox | Days 1-7 |
| **Week 2** | 15-25 emails per inbox | Days 8-14 |
| **Week 3** | 25-40 emails per inbox | Days 15-21 |
| **Week 4+** | 40-50 emails per inbox (maximum recommended) | Days 22+ |

**Key Rules:**
- Never blast high volume from a new domain on day one
- Maintain predictable daily volumes
- Use dedicated sending domains (not your primary business domain)
- Monitor bounce rates and spam complaints throughout warmup

### 6.3 Sending Limits and Spam Filter Thresholds

#### ISP-Enforced Limits (2025-2026)

| Provider | Threshold | Requirements |
|---|---|---|
| **Google (Gmail)** | 5,000+ emails/day triggers bulk sender rules | Spam complaint rate < 0.3% (target < 0.1%), bounce rate < 2%, SPF+DKIM+DMARC required |
| **Yahoo** | 5,000+ emails/day triggers bulk sender rules | Same as Google + one-click unsubscribe honored within 2 days |
| **Microsoft (Outlook/Hotmail/Live)** | 5,000+ emails/day (enforced since May 2025) | SPF+DKIM+DMARC required, functional unsubscribe, compliant sending practices |

#### Recommended Sending Limits for Cold Email

| Metric | Recommended Limit |
|---|---|
| Emails per inbox per day | 40-50 maximum |
| New contacts per day (cold) | 30-40 per inbox |
| Spam complaint rate | Below 0.1% (hard limit: 0.3%) |
| Bounce rate | Below 0.5% (hard limit: 2%) |
| Inboxes per domain | 3-5 maximum |
| Sending domains | Multiple (rotate, don't overuse one domain) |

### 6.4 Bounce Management and List Hygiene

| Action | Requirement |
|---|---|
| **Hard bounces** | Remove immediately and permanently -- add to suppression list |
| **Soft bounces** | Retry 2-3 times, then suppress if persistent |
| **Spam complaints** | Remove immediately, add to suppression list, investigate root cause |
| **List verification** | Verify email lists before sending (use verification API) |
| **Regular hygiene** | Clean lists every 2-6 months |
| **Re-engagement** | Send re-engagement campaign to contacts inactive for 90-180 days before removing |
| **Invalid addresses** | Never send to known invalid addresses (role-based, disposable, etc.) |

### 6.5 Unsubscribe Best Practices

1. **Include both:** RFC 8058 List-Unsubscribe header AND visible footer unsubscribe link
2. **One-click:** Unsubscribe must work in a single action (no login required, no surveys before unsubscription takes effect)
3. **Processing time:** Honor within 2 days (Yahoo requirement) even though CAN-SPAM allows 10 business days
4. **Confirmation:** Send a single confirmation that unsubscribe was processed (do not use this as a marketing opportunity)
5. **Global effect:** Unsubscribe from one campaign = unsubscribe from ALL campaigns (unless you offer granular preferences AND the recipient specifically chooses partial unsubscribe)
6. **Never re-subscribe:** Once unsubscribed, never add back without explicit new consent
7. **Test regularly:** Verify unsubscribe links work across all sending domains and rotation setups

---

## 7. Jurisdiction Comparison Matrix

| Feature | US (CAN-SPAM) | Canada (CASL) | UK (PECR + UK GDPR) | EU (GDPR + ePrivacy) |
|---|---|---|---|---|
| **Consent Model** | Opt-out | Opt-in | Opt-out for corporate subscribers; opt-in for individuals | Opt-in (legitimate interest allowed for B2B) |
| **Can You Cold Email B2B?** | Yes | Only with implied/express consent | Yes (corporate addresses); need lawful basis for named individuals | Yes, under legitimate interest (except Germany) |
| **Physical Address Required?** | Yes | Yes (mailing address + phone/email/web) | Identify yourself | Identify yourself + data controller details |
| **Unsubscribe Required?** | Yes | Yes | Yes | Yes |
| **Opt-Out Honor Timeline** | 10 business days | 10 business days | Promptly | Without undue delay |
| **Max Penalty (per violation)** | $51,744 | $10M CAD (business) | 4% global revenue or GBP 17.5M | 4% global revenue or EUR 20M |
| **Consent Records Required?** | No (recommended) | Yes (3 years) | Yes (demonstrate compliance) | Yes (demonstrate compliance) |
| **Data Retention Limits?** | No federal limit | Implied consent expires | GDPR: purpose limitation | GDPR: purpose limitation (3 years guidance) |
| **Right to Erasure?** | CCPA only (California) | Limited | Yes (GDPR Article 17) | Yes (GDPR Article 17) |
| **Data Source Disclosure?** | No | No | Yes (on first contact) | Yes (on first contact) |
| **DNC Registry?** | Federal + 12 states | National DNC List | TPS/CTPS | Varies by country |
| **Private Right of Action?** | No | Yes ($200/violation) | Yes (compensation claims) | Yes (compensation claims) |
| **B2B Exemption?** | N/A (same rules) | None | Corporate subscribers exempt from PECR consent | Legitimate interest basis for B2B |
| **Strictness Ranking** | 4th (least strict) | 2nd | 3rd | 1st (strictest, especially Germany) |

---

## 8. Sources

### US Regulations
- [CAN-SPAM Act: A Compliance Guide for Business | FTC](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business)
- [Cold Email Laws in 2026 | Email Ferret](https://emailferret.io/blog/cold-email-laws-2026)
- [CAN-SPAM Act Compliance Guide for B2B Businesses | RevNew](https://revnew.com/blog/can-spam-act-compliance-guide)
- [Is Cold Email Legal 2026? | GrowLeads](https://growleads.io/blog/is-cold-email-legal-gdpr-can-spam-2026/)
- [Cold Email Compliance 101 | OutreachBloom](https://outreachbloom.com/cold-email-compliance)
- [USA Email Marketing Rules Under CAN-SPAM | GDPR Local](https://gdprlocal.com/usa-e-mail-marketing-rules/)
- [CAN-SPAM Act Laws and Requirements | Termly](https://termly.io/resources/articles/can-spam-act/)

### CCPA/CPRA and State Privacy Laws
- [California Consumer Privacy Act | CA DOJ](https://oag.ca.gov/privacy/ccpa)
- [When Does CPRA Apply to B2B Communications? | TermsFeed](https://www.termsfeed.com/blog/b2b-ccpa-cpra/)
- [CCPA Requirements 2026 | SecurePrivacy](https://secureprivacy.ai/blog/ccpa-requirements-2026-complete-compliance-guide)
- [CPRA Exemptions Explained | CookieYes](https://www.cookieyes.com/blog/cpra-exemptions/)
- [US State Privacy Laws Overview | IAPP](https://iapp.org/resources/article/us-state-privacy-laws-overview)
- [US Data Privacy Laws 2026 | Osano](https://www.osano.com/us-data-privacy-laws)
- [Data Privacy Laws 2026 | Ketch](https://www.ketch.com/blog/posts/us-privacy-laws-2026)

### FTC and Telemarketing Sales Rule
- [Complying with the Telemarketing Sales Rule | FTC](https://www.ftc.gov/business-guidance/resources/complying-telemarketing-sales-rule)
- [FTC Announces TSR Amendment for B2B | Hudson Cook](https://www.hudsoncook.com/article/ftc-announces-telemarketing-sales-rule-amendment-regulating-b2b-telemarketing/)
- [TSR Changes Remove B2B Exception | National Law Review](https://natlawreview.com/article/telemarketing-sales-rule-changes-remove-exception-business-business-calls-and)

### Canada (CASL)
- [CASL Guidance on Implied Consent | CRTC](https://crtc.gc.ca/eng/com500/guide.htm)
- [CASL Compliance Guide 2026 | SendCheckIt](https://sendcheckit.com/blog/casl-compliance-guide)
- [CASL Cold Email Compliance Guide 2026 | Prospeo](https://prospeo.io/s/casl-cold-email)
- [Canada's Anti-Spam Legislation | ISED](https://ised-isde.canada.ca/site/canada-anti-spam-legislation/en/canadas-anti-spam-legislation)
- [CASL FAQ | Deloitte Canada](https://www.deloitte.com/ca/en/services/consulting-risk/perspectives/canada-anti-spam-law-casl-faq.html)
- [About CASL | Mailchimp](https://mailchimp.com/help/about-the-canada-anti-spam-law-casl/)

### UK/EU GDPR and PECR
- [When Can We Rely on Legitimate Interests? | ICO](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/legitimate-interests/when-can-we-rely-on-legitimate-interests/)
- [GDPR & B2B Data Enrichment Legal Guide 2026 | Derrick](https://derrick-app.com/en/gdpr-data-enrichment/)
- [GDPR and Cold Email Compliance | IsColdemailLegal](https://iscoldemaillegal.com/blog/gdpr-cold-email-compliance/)
- [Consent vs Legitimate Interest in B2B | Derrick](https://derrick-app.com/en/consent-vs-legitimate-interest-b2b-2/)
- [GDPR Cold Email Strategy 2025 | GDPR Local](https://gdprlocal.com/gdpr-cold-email/)
- [GDPR Legitimate Interest: Article 6(1)(f) | GDPR Local](https://gdprlocal.com/gdpr-legitimate-interest/)
- [Electronic Mail Marketing | ICO](https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/guide-to-pecr/electronic-and-telephone-marketing/electronic-mail-marketing/)
- [B2B Cold Outreach in the UK | Hybrid Legal](https://www.hybridlegal.co.uk/blog/using-business-emails-for-b2b-cold-outreach-in-the-uk-what-you-can-and-cant-do)
- [B2B vs B2C Email Marketing Rules UK | SmartSMSSolutions](https://smartsmssolutions.com/resources/blog/uk/b2b-b2c-email-marketing-rules-uk)
- [GDPR Cold Email UK 2026 | PrawnMail](https://prawnmail.co.uk/gdpr-cold-email-uk/)

### GDPR Enforcement and Fines
- [GDPR Enforcement and Data Breach Landscape 2025-2026 | ComplianceHub](https://compliancehub.wiki/gdpr-enforcement-and-data-breach-landscape-a-synthesis-of-2025-2026-trends/)
- [Biggest GDPR Fines of 2025 | Skillcast](https://www.skillcast.com/blog/biggest-gdpr-fines-2025)
- [Top GDPR Fines 2025-2026 | DSALTA](https://www.dsalta.com/resources/articles/gdpr-fines-2025-2026-lessons-how-to-avoid)
- [DLA Piper GDPR Fines Survey January 2026](https://www.dlapiper.com/en/insights/publications/2026/01/dla-piper-gdpr-fines-and-data-breach-survey-january-2026)
- [GDPR Enforcement Tracker](https://www.enforcementtracker.com/)

### Right to Erasure and Data Retention
- [GDPR Data Subject Rights 2026 | Derrick](https://derrick-app.com/en/gdpr-data-subject-rights-2/)
- [Art. 17 GDPR Right to Erasure | GDPR-Info](https://gdpr-info.eu/art-17-gdpr/)
- [B2B Data Enrichment & GDPR Compliance Guide | Cleanlist](https://www.cleanlist.ai/blog/2026-03-02-b2b-data-enrichment-compliance-guide)
- [Art. 30 GDPR Records of Processing | GDPR-Info](https://gdpr-info.eu/art-30-gdpr/)
- [Article 30 Documentation | ICO](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/accountability-and-governance/documentation/what-do-we-need-to-document-under-article-30-of-the-gdpr/)

### Vendor Compliance Approaches
- [Cognism Compliance](https://www.cognism.com/compliance)
- [Cognism vs Clay 2026](https://www.cognism.com/cognism-vs-clay)
- [Apollo DPA](https://www.apollo.io/dpa)
- [Apollo Privacy Policy](https://www.apollo.io/privacy-policy)
- [Dropcontact GDPR Compliance](https://support.dropcontact.com/article/189-gdpr-compliance)
- [Dropcontact Data Privacy & Security](https://support.dropcontact.com/article/315-dropcontact-data-privacy-security-overview)

### Email Deliverability and Technical Compliance
- [Cold Email Deliverability 2026 | Instantly](https://instantly.ai/blog/how-to-achieve-90-cold-email-deliverability-in-2025/)
- [SPF DKIM DMARC Setup for Cold Email 2026 | Prospeo](https://prospeo.io/s/spf-dkim-dmarc-setup-cold-email)
- [DMARC DKIM SPF 2026 Technical Guide | DataInnovation](https://datainnovation.io/en/blog/dmarc-dkim-spf-in-2026-the-no-bs-technical-guide-for-email-senders/)
- [Microsoft Outlook Bulk Sender Requirements 2025](https://techcommunity.microsoft.com/blog/microsoftdefenderforoffice365blog/strengthening-email-ecosystem-outlook%E2%80%99s-new-requirements-for-high%E2%80%90volume-senders/4399730)
- [Email Deliverability 2026 Compliance | ExactVerify](https://www.exactverify.com/blog/email-deliverability-compliance-guide)
- [Cold Email Deliverability Best Practices 2025 | EA Partners](https://www.ea.partners/insights/cold-email-deliverability-best-practices-2025)

### DNC and Suppression Lists
- [Best Tools for Managing DNC Lists | PossibleNOW](https://www.possiblenow.com/resources/do-not-call-solutions/best-tools-for-managing-do-not-contact-lists/)
- [How to Track Consent Alongside DNC Requests | PossibleNOW](https://www.possiblenow.com/resources/do-not-call-solutions/how-to-track-consent-alongside-dnc-requests/)
- [DNC Compliance 2025 | ClickPoint](https://blog.clickpointsoftware.com/scrub-leads-against-federal-and-state-dnc-lists)
