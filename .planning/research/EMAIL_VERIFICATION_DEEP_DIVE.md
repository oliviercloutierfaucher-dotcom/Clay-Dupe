# Email Verification & Deliverability — Deep Research Report

**Date:** 2026-03-08
**Purpose:** Comprehensive technical reference for B2B email verification and deliverability intelligence

---

## Table of Contents

1. [Email Verification Methods](#1-email-verification-methods)
2. [How Top Verification Services Work](#2-how-top-verification-services-work)
3. [Verification API Providers & Pricing](#3-verification-api-providers--pricing)
4. [Self-Hosted Verification](#4-self-hosted-verification)
5. [Catch-All Domain Deep Dive](#5-catch-all-domain-deep-dive)
6. [Deliverability Intelligence](#6-deliverability-intelligence)
7. [Bounce Types & Handling](#7-bounce-types--handling)
8. [Architecture Recommendations](#8-architecture-recommendations)

---

## 1. Email Verification Methods

### 1.1 Syntax Validation (Layer 1)

**What it does:** Checks if the email address conforms to RFC 5322 / RFC 5321 format before any network calls.

**Key rules:**
- Total address cannot exceed **254 characters**
- Local part (before @) cannot exceed **64 characters**
- Individual domain labels cannot exceed **63 characters**
- Valid special characters in local part: `!#$%&'*+-/=?^_\`{|}~`
- Plus addressing (user+tag@domain.com) is valid and must not be rejected
- Quoted strings and comments are technically valid per RFC but rarely seen in practice

**Common typo detection patterns:**
- Domain misspellings: `gmial.com`, `gmal.com`, `yahooo.com`, `hotmal.com`
- Double dots: `user..name@domain.com`
- Missing TLD: `user@domain`
- Spaces in address
- Leading/trailing whitespace

**Practical approach:** Full RFC 5322 regex compliance is impractical in production (the compliant regex spans hundreds of characters). Most systems apply a balanced subset:
```
^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$
```

**False rejection risk:** Overly strict regex rejects up to 20% of legitimate addresses when special characters and plus addressing are not accounted for.

---

### 1.2 DNS / MX Record Checking (Layer 2)

**What it does:** Verifies the domain has valid mail exchange (MX) records — meaning the domain is configured to receive email.

**How MX records work:**
- MX records are DNS records that specify which mail servers accept email for a domain
- Each MX record has two parts: a **hostname** (the mail server) and a **priority number** (lower = higher priority)
- Multiple MX records enable primary/backup mail servers and load balancing
- When sending email, the sending server queries DNS for MX records of the recipient domain

**Technical implementation:**
```
# Command-line check
nslookup -type=mx example.com
dig example.com MX

# Python with dnspython
import dns.resolver
answers = dns.resolver.resolve('example.com', 'MX')
for rdata in answers:
    print(f'Host: {rdata.exchange}, Priority: {rdata.preference}')
```

**What to check:**
1. Domain exists in DNS (not NXDOMAIN)
2. MX records exist and point to valid hostnames
3. MX hostnames resolve to IP addresses (A/AAAA records)
4. Fallback: if no MX record, check for A record (RFC 5321 allows direct delivery)

**Common failures:**
- Domain does not exist (NXDOMAIN) — immediate invalid
- No MX records AND no A record — cannot receive email
- MX points to `localhost` or `0.0.0.0` — domain explicitly rejects email
- Expired/parked domains with no mail infrastructure

---

### 1.3 SMTP Verification (Layer 3) — The Core Technique

**What it does:** Connects to the recipient's mail server and simulates sending an email up to the RCPT TO command, without actually delivering a message.

**Step-by-step SMTP handshake verification:**

```
Step 1: DNS Lookup
  → Resolve MX records for recipient domain
  → Connect to highest-priority mail server on port 25

Step 2: Initial Connection
  → Server responds: 220 mx.example.com ESMTP ready

Step 3: HELO/EHLO
  → Client sends: EHLO verifier.yourdomain.com
  → Server responds: 250 mx.example.com Hello

Step 4: MAIL FROM
  → Client sends: MAIL FROM:<>
  → Server responds: 250 OK
  (Empty sender = bounce message / verification probe)

Step 5: RCPT TO (The Key Step)
  → Client sends: RCPT TO:<target@example.com>
  → Server responds with one of:
     • 250 OK — Address exists (VALID)
     • 550 User unknown — Address doesn't exist (INVALID)
     • 450/451/452 — Temporary error (UNKNOWN/RETRY)
     • 550 Mailbox disabled — Disabled account (INVALID)

Step 6: QUIT
  → Client sends: QUIT
  → No actual email is sent
```

**VRFY Command (Legacy):**
- `VRFY username` asks the server to confirm if a mailbox exists
- Defined in RFC 5321 but **disabled on most modern servers** (security risk)
- RFC 2505 recommends disabling VRFY to prevent directory harvest attacks
- Most verification services use RCPT TO instead of VRFY

**Greylisting impact on verification:**
- **What it is:** Server temporarily rejects (4xx) emails from unknown senders, expecting legitimate servers to retry
- Greylisting checks a "triplet": sending IP + sender address + recipient address
- First attempt returns 450/451 ("try again later")
- Typical delay: 1-15 minutes (15 minutes is most common default)
- **Impact on verification:** Basic tools mark greylisted addresses as "unknown"
- **How good services handle it:** ZeroBounce uses a 37-minute anti-greylisting process; Verifalia's high-quality profile does up to 3 additional passes; extreme-quality does 9 passes

**Tarpitting impact:**
- **What it is:** Server deliberately slows down SMTP responses to deter bulk senders
- Unlike greylisting, tarpitting delays every step of the conversation
- Forces verification tools to maintain long-lived connections
- Can cause timeouts in verification services that don't handle it

**Risks of SMTP verification:**
- **IP blacklisting:** High-volume SMTP probes look like directory harvest attacks
- **Rate limiting:** Mail servers limit connections per IP per time window
- **Reputation damage:** Your verification IP can land on Spamhaus, Barracuda, SORBS
- **False positives:** Some servers accept all RCPT TO during SMTP but bounce later
- **Resource intensive:** Each verification requires a TCP connection and multi-step conversation

---

### 1.4 Catch-All Detection (Layer 4)

**How it works:** Send RCPT TO with a known-invalid random address (e.g., `xq7k2m9p@domain.com`). If the server accepts it, the domain is catch-all.

**Detection method:**
```
RCPT TO:<definitely-invalid-random-string@domain.com>
→ 250 OK = Catch-all domain (accepts everything)
→ 550 = Not catch-all (rejects invalid addresses)
```

**See Section 5 for deep dive on catch-all domains.**

---

### 1.5 Disposable Email Detection (Layer 5)

**What it detects:** Temporary/throwaway email addresses from services like Guerrilla Mail, Mailinator, TempMail, etc.

**Detection methods:**
1. **Domain blacklist matching:** Compare domain against known disposable email domain lists
   - Open-source list: [disposable-email-domains](https://github.com/disposable-email-domains/disposable-email-domains) on GitHub
   - Commercial services track 125,000+ disposable domains
   - Some services monitor 2,000+ throwaway email providers
   - Lists require constant updating as new services appear daily

2. **Real-time analysis + ML:** Commercial services use machine learning to identify new disposable patterns before they appear on blacklists

3. **DNS pattern analysis:** Some disposable services share infrastructure patterns detectable via DNS

**B2B relevance:** Disposable emails are a strong signal of spam/fraud — any B2B contact using a disposable domain should be immediately filtered out.

---

### 1.6 Role-Based Email Detection (Layer 6)

**What it detects:** Generic/functional email addresses not tied to a specific person.

**Common role-based prefixes:**
```
info@, sales@, support@, admin@, webmaster@, contact@,
help@, billing@, abuse@, postmaster@, noreply@, office@,
hr@, marketing@, press@, media@, legal@, compliance@,
team@, hello@, careers@, jobs@, feedback@
```

**Should these be filtered in B2B outreach?**
- **YES, generally filter them out.** Role-based addresses:
  - Generate complaints at **3-5x higher rates** than personal addresses
  - Often serve multiple people (no clear decision-maker)
  - Rarely provide valid opt-ins
  - Platforms like Mailchimp and Pipedrive restrict sending to them
  - Lower reply rates compared to personalized outreach

- **Exception:** In some cases (small businesses, specific departments), role-based addresses may be the only available contact. Mark as "risky" rather than invalid.

---

### 1.7 Free Email Provider Detection (Layer 7)

**What it detects:** Personal email providers (Gmail, Yahoo, Hotmail/Outlook, AOL, etc.) vs. business domains.

**Common free providers to detect:**
```
gmail.com, yahoo.com, hotmail.com, outlook.com, aol.com,
icloud.com, mail.com, protonmail.com, zoho.com, yandex.com,
gmx.com, live.com, msn.com, me.com, fastmail.com
```

**B2B filtering guidance:**
- In B2B outreach, personal email addresses are generally a negative signal
- **Exception:** Solopreneurs, freelancers, and early-stage founders often use Gmail
- Best practice: Flag as "personal email" but don't auto-reject — let the user decide
- Free tools without verification deliver 20-30% bounce rates; verified lists maintain <2%

---

## 2. How Top Verification Services Work

### 2.1 ZeroBounce

**Accuracy:** 99.6%

**Verification process:**
1. Syntax validation and error checking
2. Domain/MX record verification
3. SMTP mailbox verification
4. Catch-all detection with **AI scoring** (unique differentiator)
5. Spam trap detection
6. Disposable email detection
7. Toxic domain identification
8. Abuse email detection

**Key technology:**
- **Anti-greylisting:** Deploys a comprehensive **37-minute verification process** to handle greylisted servers
- **AI catch-all scoring:** Uses artificial intelligence to score catch-all email addresses, providing probability-based insight
- Detects **30+ email address types** including spam traps, toxic domains, and abuse addresses
- Infrastructure backed by Cloudflare with Advanced DDoS and firewall protection
- Real-time API validates emails at form submission

**Strengths:** Highest number of detected email types, AI-powered catch-all scoring, robust anti-greylisting

---

### 2.2 NeverBounce

**Accuracy:** 99.9% (claimed)

**Verification process:**
- Identifies 30+ types of problematic emails
- Bulk and real-time verification
- Integrates with 80+ platforms

**Key technology:**
- Focuses on high-speed bulk verification
- Strong integration ecosystem
- API-first architecture

**Strengths:** Speed, integrations, high claimed accuracy

---

### 2.3 Findymail

**Accuracy:** <5% bounce rate guaranteed (actual tested: 1.1-1.33% hard bounce rate)

**Verification process:**
1. Syntax validation
2. DNS record verification
3. SMTP server verification
4. Catch-all verification (unique — verifies emails other tools mark as "risky")
5. Disposable email detection
6. Inbox availability check without sending a message

**Key technology:**
- Simulates email delivery and gets status response from recipient server
- **Advanced catch-all handling:** Verifies catch-all emails that other tools refuse to verify
- Delivers **23% more valid emails** than competitors by resolving catch-all addresses
- Bounce guarantee: If bounce rate exceeds 5%, provides refund or credit return

**Strengths:** Industry-leading catch-all verification, bounce rate guarantee, highest valid email yield

---

### 2.4 Dropcontact

**Accuracy:** 98% for standard emails, 85% for catch-all domains

**Verification process:**
1. Real-time algorithmic email generation (not database-based)
2. Multi-method verification using proprietary algorithms
3. Smart company domain matching
4. Built-in verification for generated addresses
5. Catch-all domain handling

**Key technology:**
- **No database:** Generates and validates emails in real-time using proprietary algorithms
- **100% GDPR compliant:** No personal data stored or resold; processing on EU-based servers
- Only needs: website + first name + last name to find and verify an email
- No reliance on non-compliant third-party providers

**Strengths:** GDPR compliance, real-time generation (not stale data), strong catch-all handling

---

### 2.5 Icypeas

**Accuracy:** <2.5% bounce rate

**Verification process:**
1. Email discovery from open sources only
2. Multi-method verification
3. Catch-all email validation (unique capability)
4. Professional data only (never personal)

**Key technology:**
- Validates catch-all emails — a differentiator that minimizes bounces
- Uses only open sources for email discovery
- Provides opt-out system for data subjects
- Trusted by Clay, Lemlist, Apollo, Instantly

**Benchmarking:** Icypeas conducted a benchmark studying 17 email verifiers including ZeroBounce, NeverBounce, and BriteVerify on a standardized test of 100 email addresses.

**Strengths:** Catch-all validation, open-source data approach, Clay integration

---

### 2.6 Snov.io

**Accuracy:** 98% (1.72% bounce rate for "valid" status emails)

**7-Tier Verification Process:**
1. **Syntax check** — RFC compliance validation
2. **Gibberish detection** — Identifies random character strings
3. **Domain check** — Verifies domain exists and is active
4. **MX record check** — Confirms mail server configuration
5. **SMTP ping** — Super-accurate mailbox verification
6. **Greylisting bypass** — Handles servers with greylisting enabled
7. **Catch-all detection** — Identifies accept-all domains

**Key technology:**
- Dedicated greylisting bypass mechanism
- Combined email finder + verifier in one platform
- Real-time and bulk verification modes

**Strengths:** Comprehensive 7-layer approach, built-in greylisting bypass, integrated prospecting

---

### 2.7 Emailable

**Key differentiators:**
- **Typo suggestion engine:** Identifies typos and suggests the best alternative
- **Domain health check:** Confirms domain is live and correctly configured
- **Speed:** Fastest verification results in benchmarks
- Strong agency workflows with client segmentation

---

### 2.8 EmailListVerify

**Key differentiators:**
- Detailed validation with role-based and catch-all detection
- Quality scoring per address
- Spam trap detection and domain health analysis
- Disposable/temporary email identification
- Pricing starts at **$0.004 per email** (very competitive)
- 10,000 emails verified in ~75 minutes

---

## 3. Verification API Providers & Pricing

### 3.1 Pricing Comparison Table

| Provider | Free Tier | Pay-As-You-Go | 10K Emails | 100K Emails | Notes |
|----------|-----------|---------------|------------|-------------|-------|
| **ZeroBounce** | 100 free/month | $16/2,000 | ~$75 | ~$400 | AI catch-all scoring |
| **NeverBounce** | Free trial only | $8/1,000 | ~$40-50 | ~$150 | 99.9% accuracy claim |
| **Emailable** | 250 free | Pay-as-you-go | ~$30 | ~$200 | Fastest results |
| **MillionVerifier** | None | $37/10,000 | $37 | ~$149 | **Cheapest**, credits never expire |
| **EmailListVerify** | 100 free | $0.004/email | ~$40 | ~$169 | Budget-friendly |
| **Snov.io** | 50 free/month | Part of plans | Included | Included | Combined finder+verifier |
| **Icypeas** | Free verifier tool | API pricing | Varies | Varies | Clay integration |
| **Findymail** | Free verifier | Credit-based | Varies | Varies | Bounce guarantee |
| **Dropcontact** | Trial available | Subscription | ~EUR 49/mo | ~EUR 99/mo | GDPR compliant |

### 3.2 Best Value Analysis

- **Cheapest bulk verification:** MillionVerifier ($37/10K, credits never expire)
- **Best free tier:** ZeroBounce (100/month recurring) or Emailable (250 one-time)
- **Best for agencies:** ZeroBounce or Emailable (client segmentation, reporting)
- **Best accuracy:** ZeroBounce (99.6%), NeverBounce (99.9% claimed)
- **Best catch-all handling:** Findymail or Icypeas
- **Best GDPR compliance:** Dropcontact (only fully GDPR-compliant option)

---

## 4. Self-Hosted Verification

### 4.1 Can We Do SMTP Verification Ourselves?

**Yes, but with significant caveats.**

Self-hosted SMTP verification is technically feasible but comes with operational complexity that commercial services abstract away.

### 4.2 Technical Requirements

**Infrastructure:**
- **Dedicated IP address** — Shared hosting means shared reputation; one neighbor's spam blacklists everyone
- **PTR (reverse DNS) record** — Must match your sending hostname; many servers reject connections without valid PTR
- **Forward-Confirmed Reverse DNS (FCrDNS):** A record (hostname -> IP) and PTR record (IP -> hostname) must match
- **HELO hostname** must match PTR record
- **Port 25 access** — Many cloud providers (AWS, GCP, Azure) block outbound port 25 by default
- **SPF/DKIM/DMARC** on your verification domain

**Rate limiting requirements:**
- Limit connections per domain: 1-2 concurrent connections max
- Limit queries per minute: 10-20 per domain
- Implement exponential backoff on temporary failures
- Rotate across multiple IPs for high volume

### 4.3 Risks of Self-Hosted Verification

| Risk | Severity | Mitigation |
|------|----------|------------|
| **IP blacklisting** | HIGH | Dedicated IPs, low volume, monitoring via Spamhaus/Barracuda |
| **Rate limiting by target servers** | HIGH | Per-domain throttling, distributed verification |
| **ISP port 25 blocking** | MEDIUM | Use cloud providers that allow port 25, or use SOCKS proxies |
| **Greylisting false negatives** | MEDIUM | Implement retry logic with 15-37 minute delays |
| **Catch-all false positives** | MEDIUM | Secondary pattern-based analysis |
| **Honeypot/spam trap hits** | HIGH | Never verify purchased/scraped lists |
| **Maintenance overhead** | MEDIUM | Keeping blacklists, disposable domain lists updated |

### 4.4 Open Source Tools

#### Reacher (Rust) — Most Production-Ready
- **Repository:** [github.com/reacherhq/check-if-email-exists](https://github.com/reacherhq/check-if-email-exists)
- **Language:** Rust (high performance, memory safe)
- **Features:** SMTP verification, MX checking, catch-all detection, disposable detection
- **Deployment:** Docker container with built-in proxy for port 25
- **Limits:** 60/minute, 10,000/day per instance
- **Architecture:** Stateless — horizontally scalable via multiple containers
- **License:** AGPL-3.0 (open source) or Commercial ($749/month for unlimited)
- **Self-host setup:** Docker image on Docker Hub, installable in ~20 minutes
- **Port 25 solution:** Pre-configured proxy in Dockerfile resolves ISP port 25 restrictions

#### Truemail (Ruby)
- **Repository:** [github.com/truemail-rb/truemail](https://github.com/truemail-rb/truemail)
- **Language:** Ruby
- **Features:** Regex validation, DNS/MX checking, SMTP verification
- **Verification layers:** Configurable — regex only, DNS only, or full SMTP
- **License:** MIT (fully free for commercial use)
- **Best for:** Ruby/Rails applications needing integrated email validation

#### check-if-email-exists (Rust)
- Same codebase as Reacher's core library
- Available as a Rust crate on [crates.io](https://crates.io/crates/check-if-email-exists)
- Can be embedded directly in Rust applications
- HTTP backend available for API-style usage

### 4.5 Python Libraries for Self-Hosted Verification

| Library | Features | SMTP Check | Notes |
|---------|----------|------------|-------|
| **email-validator** | Syntax + DNS/MX | No | Most popular; Python 3.8+; robust syntax validation |
| **py3-validate-email** | Syntax + blacklist + SMTP | Yes | Full SMTP verification; checks blacklisted domains |
| **dns-smtp-email-validator** | Format + domain + MX + SMTP | Yes | Multi-level validation with server communication |
| **dnspython** | DNS/MX only | No | Low-level DNS library; build custom MX checking |
| **validate_email** | Syntax + MX + SMTP | Yes | Older library; less maintained |

**Recommended Python stack for self-hosted verification:**
```python
# Layer 1: Syntax — email-validator
from email_validator import validate_email, EmailNotValidError

# Layer 2: DNS/MX — dnspython
import dns.resolver

# Layer 3: SMTP — py3-validate-email or custom smtplib
from validate_email import validate_email as smtp_validate

# Layer 4-7: Disposable/role/catch-all — custom logic + domain lists
```

### 4.6 Self-Hosted vs. API: Decision Matrix

| Factor | Self-Hosted | API Service |
|--------|-------------|-------------|
| **Cost at scale** | Lower (infrastructure only) | Higher (per-email pricing) |
| **Setup complexity** | High | Low (API key) |
| **Accuracy** | Lower (no AI, limited greylisting handling) | Higher (97-99.9%) |
| **Catch-all handling** | Basic | Advanced (AI scoring) |
| **IP reputation risk** | You bear it | Provider handles it |
| **Maintenance** | Ongoing | None |
| **Greylisting handling** | Must implement retry logic | Built-in |
| **Spam trap detection** | Very difficult to self-host | Included |

**Recommendation:** Use a **hybrid approach** — self-hosted for Layers 1-2 (syntax + DNS) and API for Layers 3+ (SMTP, catch-all, spam traps). This reduces API costs by ~40% while maintaining accuracy.

---

## 5. Catch-All Domain Deep Dive

### 5.1 What Are Catch-All Domains?

A catch-all (or "accept-all") domain is configured to accept email sent to ANY address at that domain, whether the mailbox exists or not. If someone sends to `nonexistent@catchall-domain.com`, the server accepts it instead of bouncing.

### 5.2 Prevalence in B2B

**Statistics vary but are significant:**
- **15-28%** of B2B domains are configured as catch-all (conservative estimate)
- **Up to 30%** of contacts in B2B outbound lists belong to catch-all domains
- **40-60%** of B2B email addresses may be on catch-all domains (broader estimates)
- Large enterprises are more likely to use catch-all configurations as a security/compliance measure

**Why companies use catch-all:**
- Prevent lost emails due to typos
- Route unknown addresses to IT/admin for review
- Security monitoring (detect phishing attempts)
- Legacy configurations that were never updated

### 5.3 How Verification Services Handle Catch-All

**Standard approach (most tools):**
1. Send RCPT TO with a random invalid address
2. If server accepts it (250 OK), domain is catch-all
3. Mark ALL addresses on that domain as "accept-all" or "risky"
4. Cannot determine individual address validity

**Advanced approaches:**

| Service | Catch-All Method | Accuracy |
|---------|-----------------|----------|
| **Findymail** | Proprietary verification of individual catch-all addresses | Delivers 23% more valid emails |
| **Dropcontact** | Real-time algorithmic validation | 85% accuracy on catch-all |
| **ZeroBounce** | AI scoring model | Probability score per address |
| **Icypeas** | Catch-all email validation | Unique validation capability |
| **Apollo** | 7-step process differentiating valid/invalid on catch-all | Pattern-based |
| **Allegrow** | Signal-based verification | Detects silent bounces |

### 5.4 Pattern-Based Verification on Catch-All Domains

**Does it work?** Partially.

**How it works:**
1. Identify the company's email pattern (e.g., `first.last@`, `firstlast@`, `flast@`)
2. Cross-reference the contact's name against the detected pattern
3. If the address matches the pattern AND the person is confirmed at the company, probability of validity increases

**Limitations:**
- Pattern detection requires multiple known-valid addresses at the domain
- People with common names may have modified addresses (`john.smith2@`)
- Departed employees' addresses may still be accepted by catch-all but not monitored
- No way to confirm actual inbox activity

### 5.5 Should Catch-All Emails Be Marked as "Risky"?

**Yes — but with nuance:**

| Classification | Bounce Risk | Recommendation |
|----------------|-------------|----------------|
| Verified valid (non-catch-all) | <2% | Send confidently |
| Catch-all + pattern match + confirmed employee | ~10-15% | Send with monitoring |
| Catch-all + pattern match only | ~20-30% | Send cautiously, limit volume |
| Catch-all + no pattern match | ~30-50% | Do not send or deprioritize |
| Unverifiable / unknown | ~40-60% | Do not send |

### 5.6 Impact on Deliverability

- Catch-all addresses carry **30-50% higher bounce risk**
- Even when accepted by the server, emails may go to a black hole (never read)
- High catch-all percentage in a campaign degrades sender reputation over time
- **Best practice:** Keep catch-all percentage below 10-15% of total send volume
- Use engagement tracking (opens/clicks) to clean catch-all addresses post-send

---

## 6. Deliverability Intelligence

### 6.1 What is Email Deliverability?

Email deliverability is the ability of an email to reach the recipient's inbox (not spam folder, not bounced). It is measured by:

- **Inbox placement rate:** % of emails landing in primary inbox
- **Bounce rate:** % of emails that fail to deliver
- **Spam rate:** % of emails landing in spam/junk folder
- **Complaint rate:** % of recipients marking email as spam

### 6.2 Factors Affecting B2B Email Deliverability

| Factor | Impact | Control Level |
|--------|--------|---------------|
| **Sender reputation** | Critical | High |
| **Email authentication (SPF/DKIM/DMARC)** | Critical | High |
| **List quality / bounce rate** | Critical | High |
| **Email content / spam triggers** | High | High |
| **Sending volume consistency** | High | High |
| **Engagement metrics** | High | Medium |
| **Recipient server policies** | Medium | None |
| **IP reputation** | High | Medium |
| **Domain age** | Medium | Low |
| **Blacklist status** | Critical | Medium |

### 6.3 Sender Reputation

**What it is:** A score assigned by ISPs/email providers (Google, Microsoft, Yahoo) based on your sending behavior. It determines whether your emails reach inbox or spam.

**Key reputation signals:**
- Bounce rate (hard bounces are most damaging)
- Spam complaint rate
- Spam trap hits
- Sending volume consistency
- Engagement rates (opens, clicks, replies)
- Authentication status (SPF/DKIM/DMARC)
- Blacklist presence

**Two types of reputation:**
1. **IP reputation:** Based on the sending IP address
2. **Domain reputation:** Based on the sending domain (increasingly more important)

**Monitoring tools:**
- Google Postmaster Tools (Gmail reputation)
- Microsoft SNDS (Outlook/Hotmail reputation)
- Sender Score by Validity
- Spamhaus, Barracuda, SORBS blacklist checks

### 6.4 Email Authentication: SPF, DKIM, DMARC

#### SPF (Sender Policy Framework)
- **What:** DNS TXT record listing authorized sending IP addresses
- **How:** Recipient server checks if sending IP is in the domain's SPF record
- **Record format:** `v=spf1 include:_spf.google.com ip4:203.0.113.0/24 -all`
- **Alignment:** The envelope sender domain (MAIL FROM) must match
- **Limit:** Max 10 DNS lookups per SPF record

#### DKIM (DomainKeys Identified Mail)
- **What:** Cryptographic signature attached to email headers
- **How:** Sending server signs email with private key; recipient verifies with public key in DNS
- **Ensures:** Message integrity (not altered in transit) and sender authenticity
- **Record:** DNS TXT record at `selector._domainkey.domain.com` containing public key

#### DMARC (Domain-based Message Authentication, Reporting & Conformance)
- **What:** Policy that tells recipient servers how to handle SPF/DKIM failures
- **How:** Checks "alignment" — the domain in From: header must match SPF or DKIM domain
- **Policies:**
  - `p=none` — Monitor only, deliver everything (start here)
  - `p=quarantine` — Send failures to spam
  - `p=reject` — Block failures entirely
- **Reports:** DMARC generates aggregate and forensic reports showing authentication results
- **Best practice:** Start with `p=none`, monitor reports, gradually move to `quarantine` then `reject`

#### How They Work Together
```
Email arrives at recipient server:
  1. SPF check: Is the sending IP authorized? (WHERE it came from)
  2. DKIM check: Is the signature valid? (WHAT was sent — integrity)
  3. DMARC check: Do SPF/DKIM domains align with From header? (WHO sent it)
  4. DMARC policy: What to do if checks fail? (none/quarantine/reject)
```

### 6.5 Email Warmup — Technical Details

**What it is:** Gradually increasing email sending volume from a new IP/domain to build sender reputation with ISPs.

**How it works technically:**
1. Warmup tools automate email exchanges with a network of real mailboxes
2. Emails are sent, opened, replied to, and moved out of spam — mimicking genuine engagement
3. ISPs observe positive sending patterns and gradually increase trust

**Warmup timeline (4 stages):**

| Stage | Days | Volume | Activity |
|-------|------|--------|----------|
| **Building trust** | 1-7 | 5-20/day | Small exchanges, high engagement rate |
| **Scaling safely** | 8-21 | 20-100/day | Gradually increase, maintain engagement |
| **Full capacity** | 22-30 | 100-200+/day | Reach target volume |
| **Maintenance** | Ongoing | Target volume | Continue warmup alongside real sends |

**Technical requirements:**
- Dedicated domain and IP for cold outreach
- SPF, DKIM, DMARC properly configured
- Warmup tool (Lemwarm, Warmup Inbox, Mailreach, Instantly)
- 2-4 weeks minimum before real outreach

### 6.6 Healthy Bounce Rate Benchmarks

| Metric | Excellent | Acceptable | Concerning | Critical |
|--------|-----------|------------|------------|----------|
| **Hard bounce rate** | <0.5% | <2% | 2-5% | >5% |
| **Soft bounce rate** | <1% | <3% | 3-5% | >5% |
| **Total bounce rate** | <1% | <3% | 3-5% | >5% |
| **Spam complaint rate** | <0.05% | <0.1% | 0.1-0.3% | >0.3% |

**B2B cold email targets:**
- **Target:** <2% total bounce rate
- **Acceptable:** <3% for new lists
- **Red flag:** >5% indicates list quality issues
- Free tools without verification: 20-30% bounce rates
- Verified lists with top tools: <1.5% bounce rates

---

## 7. Bounce Types & Handling

### 7.1 Hard Bounces

**Definition:** Permanent delivery failures. The email will never be deliverable to this address.

**SMTP codes:** 5xx (500, 550, 551, 552, 553, 554)

**Common causes:**
| Cause | SMTP Code | Example |
|-------|-----------|---------|
| Invalid/non-existent mailbox | 550 | `550 User unknown` |
| Domain doesn't exist | 550 | `550 No such domain` |
| Blocked by recipient | 550 | `550 Blocked` |
| Mailbox disabled | 550 | `550 Mailbox disabled` |
| Invalid domain DNS | 550 | `550 DNS failure` |
| Policy rejection | 554 | `554 Message rejected` |

**How to handle:**
1. **Immediately remove** from all sending lists
2. **Never retry** — address is permanently invalid
3. **Log the bounce** with reason code and timestamp
4. **Update CRM/database** — mark contact as invalid
5. **Monitor patterns** — high hard bounce rate on a batch = bad data source

### 7.2 Soft Bounces

**Definition:** Temporary delivery failures. The email may be deliverable on a future attempt.

**SMTP codes:** 4xx (421, 450, 451, 452)

**Common causes:**
| Cause | SMTP Code | Example |
|-------|-----------|---------|
| Mailbox full | 452 | `452 Mailbox full` |
| Server temporarily down | 421 | `421 Service not available` |
| Message too large | 452 | `452 Message too large` |
| Greylisting | 450/451 | `451 Try again later` |
| Rate limiting | 421 | `421 Too many connections` |
| Temporary policy block | 450 | `450 Temporarily deferred` |
| DNS timeout | 451 | `451 DNS resolution failed` |

**How to handle:**
1. **Retry delivery** — ESPs typically retry 3-5 times over 24-72 hours
2. **Monitor patterns** — Same address soft bouncing 3+ times = likely permanent issue
3. **Convert to hard bounce** — After 3-5 consecutive soft bounces, treat as invalid
4. **Segment risky addresses** — Soft-bouncing addresses should be flagged for review

### 7.3 Impact on Sender Reputation

```
Bounce Rate Impact Chain:
  High bounce rate
    → ISP flags sender as low-quality
      → Lower inbox placement
        → More emails to spam
          → Lower engagement
            → Even lower reputation
              → Eventually: domain/IP blocked
```

**Thresholds that trigger ISP action:**
- **Google:** Spam complaint rate >0.3% triggers warnings; >0.5% causes filtering
- **Microsoft:** Hard bounce rate >5% degrades reputation significantly
- **General rule:** Keep hard bounce rate under 2% to maintain good standing

### 7.4 System Architecture for Bounce Handling

```
Email Sent → Delivery Attempted
                ↓
    ┌────────────────────────┐
    │   Delivery Response    │
    ├────────────────────────┤
    │ 250 OK     → Delivered │
    │ 4xx        → Soft Bounce → Retry Queue (max 3-5 attempts)
    │ 5xx        → Hard Bounce → Suppress List (permanent)
    │ No response→ Timeout    → Retry once, then Unknown
    └────────────────────────┘
                ↓
    ┌────────────────────────┐
    │   Post-Send Actions    │
    ├────────────────────────┤
    │ Hard bounce: Remove from list, update CRM
    │ Soft bounce (repeated): Flag for review
    │ Delivered but bounced later (async): Process webhook
    │ Spam complaint: Immediate suppress
    └────────────────────────┘
```

---

## 8. Architecture Recommendations

### 8.1 Recommended Multi-Layer Verification Pipeline

For the GPO platform, implement a **waterfall verification architecture**:

```
Input: Raw email address
  │
  ▼
Layer 1: Syntax Validation (local, instant)
  │ ✗ → INVALID (malformed)
  ▼
Layer 2: DNS/MX Check (local, <1s)
  │ ✗ → INVALID (no mail server)
  ▼
Layer 3: Disposable Domain Check (local, instant)
  │ ✗ → INVALID (throwaway)
  ▼
Layer 4: Role-Based Check (local, instant)
  │ ✗ → RISKY (flag but don't reject)
  ▼
Layer 5: Free Provider Check (local, instant)
  │ ✗ → FLAG (personal email, not business)
  ▼
Layer 6: SMTP Verification (API or self-hosted, 1-37s)
  │ ✗ → INVALID
  │ ? → UNKNOWN (greylisting/timeout)
  ▼
Layer 7: Catch-All Detection (API, 1-5s)
  │ catch-all → RISKY (with confidence score)
  ▼
Output: VALID / INVALID / RISKY / UNKNOWN
```

### 8.2 Cost Optimization Strategy

1. **Layers 1-5 are free** (local checks) — eliminate ~20-30% of bad emails before any API call
2. **Layer 6-7 via API** — only pay for emails that pass initial filters
3. **Cache results** — email verification results are valid for 30-90 days
4. **Bulk vs. real-time:** Use bulk verification for list imports, real-time for form submissions
5. **Provider waterfall:** Use cheapest provider first (MillionVerifier), escalate unknowns to premium (ZeroBounce)

### 8.3 Recommended Provider Strategy

| Use Case | Primary | Fallback | Reason |
|----------|---------|----------|--------|
| **Bulk list cleaning** | MillionVerifier | EmailListVerify | Cost efficiency |
| **Real-time verification** | ZeroBounce | Emailable | Speed + accuracy |
| **Catch-all resolution** | Findymail or Icypeas | Dropcontact | Specialized capability |
| **Self-hosted base layer** | Reacher (Docker) | py3-validate-email | Reduce API dependency |
| **GDPR-compliant markets** | Dropcontact | — | Only fully compliant option |

### 8.4 Key Metrics to Track

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Verification accuracy | >98% | <95% |
| Hard bounce rate (post-verification) | <1% | >2% |
| Catch-all percentage in campaigns | <15% | >25% |
| Verification latency (real-time) | <3s | >10s |
| API cost per verified email | <$0.005 | >$0.01 |
| List-level invalidity rate | <10% | >20% |

---

## Sources

### SMTP Verification & Technical
- [SMTP Server - VRFY and EXPN Commands](http://www.smtp-server.com/simple_mail_verifying.htm)
- [Callback Verification - Wikipedia](https://en.wikipedia.org/wiki/Callback_verification)
- [SMTP Commands and Responses - Mailtrap](https://mailtrap.io/blog/smtp-commands-and-responses/)
- [RFC 6647 - Email Greylisting](https://datatracker.ietf.org/doc/html/rfc6647)
- [Email Greylisting - Verifalia](https://verifalia.com/help/email-validations/what-is-greylisting-or-graylisting)
- [Email Greylisting Guide - MailerCheck](https://www.mailercheck.com/articles/email-greylisting)
- [Greylisting Verification Results - BulkEmailChecker](https://bulkemailchecker.com/blog/email-greylisting-verification-unknown-results/)

### Catch-All Domains
- [Catch-All Email Verification Guide - Allegrow](https://www.allegrow.co/knowledge-base/catch-all-email-verification-guide-for-b2b)
- [Best Catch-All Email Verifiers 2026 - Allegrow](https://www.allegrow.co/knowledge-base/comparison-best-catch-all-email-verifiers)
- [Catch-All Emails: Risky or Worth It? - Findymail](https://www.findymail.com/blog/what-are-catch-all-emails/)
- [What is Catch-All Email? - Enrichley](https://enrichley.com/blog/what-is-catch-all-email)
- [Catch-All Email 2026 - Derrick App](https://derrick-app.com/en/catch-all-email-2)
- [How Apollo Verifies Emails](https://knowledge.apollo.io/hc/en-us/articles/10826699994381-How-Apollo-Verifies-Emails)

### Verification Services
- [ZeroBounce Email Validation](https://www.zerobounce.net/)
- [ZeroBounce Documentation](https://www.zerobounce.net/docs)
- [NeverBounce vs ZeroBounce Comparison - Mailfloss](https://mailfloss.com/neverbounce-vs-zerobounce/)
- [ZeroBounce 2026 Review - Bouncer](https://www.usebouncer.com/zerobounce-email-validation/)
- [Findymail Email Verifier](https://www.findymail.com/email-verifier/)
- [Findymail Review 2025](https://www.findyourbestai.com/blog/findymail-review-2025)
- [Dropcontact Email Verifier](https://www.dropcontact.com/email-verifier)
- [Dropcontact GDPR Compliance](https://support.dropcontact.com/article/189-gdpr-compliance)
- [Icypeas Email Verifier](https://www.icypeas.com/free-tools/email-verifier)
- [Icypeas Benchmark - Email Verifiers](https://www.icypeas.com/product/benchmark-email-verifiers)
- [Snov.io Email Verification](https://snov.io/email-verifier)
- [How Snov.io Verifies Emails](https://snov.io/knowledgebase/how-email-verification-works/)
- [Emailable vs EmailListVerify](https://emailable.com/compare/emaillistverify/)

### Pricing
- [ZeroBounce Pricing](https://www.zerobounce.net/email-validation-pricing)
- [NeverBounce Pricing](https://www.neverbounce.com/pricing)
- [Reacher Pricing](https://app.reacher.email/en/pricing)
- [Email Verification APIs 2026 Benchmark - DEV Community](https://dev.to/jamessib/email-verification-apis-compared-2026-benchmark-with-real-pricing-381k)

### Self-Hosted / Open Source
- [Reacher - Open Source Email Verification](https://reacher.email/)
- [check-if-email-exists - GitHub](https://github.com/reacherhq/check-if-email-exists)
- [Reacher Self-Host Guide](https://help.reacher.email/self-host-guide)
- [Reacher Install Docs](https://docs.reacher.email/self-hosting/install)
- [Truemail Ruby - GitHub](https://github.com/truemail-rb/truemail)
- [Truemail Documentation](https://truemail-rb.org/)
- [Open-Source Email Verification Tools - Bouncer](https://www.usebouncer.com/open-source-email-verification/)

### Python Libraries
- [email-validator - PyPI](https://pypi.org/project/email-validator/)
- [py3-validate-email - PyPI](https://pypi.org/project/py3-validate-email/1.0.4/)
- [dns-smtp-email-validator - PyPI](https://pypi.org/project/dns-smtp-email-validator/)
- [python-email-validator - GitHub](https://github.com/JoshData/python-email-validator)

### Email Authentication
- [DMARC, DKIM, SPF Explained - Cloudflare](https://www.cloudflare.com/learning/email-security/dmarc-dkim-spf/)
- [SPF, DKIM, DMARC Made Simple - Valimail](https://www.valimail.com/blog/dmarc-dkim-spf-explained/)
- [Email Authentication - Microsoft](https://learn.microsoft.com/en-us/defender-office-365/email-authentication-about)

### Deliverability & Bounce Handling
- [Hard Bounce vs Soft Bounce - MailReach](https://www.mailreach.co/blog/hard-bounce-vs-soft-bounce)
- [Email Bounce Rate 2026 - MailReach](https://www.mailreach.co/blog/email-bounce-rate)
- [Email Warmup Guide - Emelia](https://emelia.io/hub/email-warm-up)
- [Email Warmup Process - Instantly](https://instantly.ai/blog/email-warmup-process/)
- [Email Deliverability Guide - Warmup Inbox](https://www.warmupinbox.com/blog/cold-emailing/email-deliverability-guide/)
- [Reduce Email Bounce Rates - Smartlead](https://www.smartlead.ai/blog/how-to-reduce-email-bounce-rates-for-cold-outreach)

### Disposable & Role-Based Emails
- [Disposable Email Domains List - GitHub](https://github.com/disposable-email-domains/disposable-email-domains)
- [Role-Based Email Addresses - Smart Domain Check](https://www.smartdomaincheck.com/blog/role-based-email-addresses-what-to-know)
- [Role-Based Emails Kill Deliverability - Mailfloss](https://mailfloss.com/role-based-emails-hurt-deliverability/)
- [Detecting Role Accounts & Disposable Addresses - Gamalogic](https://blog.gamalogic.com/detecting-role-accounts-disposable-and-catch-all-addresses-in-prospect-lists/)

### DNS & Infrastructure
- [PTR Records and Email Sending 2026 - Mailtrap](https://mailtrap.io/blog/ptr-records/)
- [Improving Deliverability with MX, SPF, PTR - GlockApps](https://glockapps.com/tutorials/improving-email-deliverability-using-mx-spf-ptr-records/)
- [Email Syntax Validation - BillionVerify](https://billionverify.com/blog/email-syntax-validation)
- [RFC-Compliant Email Validation - Opreto](https://www.opreto.com/blog/rfc-compliant-email-address-validation/)
