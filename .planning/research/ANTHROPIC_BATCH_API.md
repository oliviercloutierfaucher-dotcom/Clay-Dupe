# Anthropic API Research: Batch API, Prompt Caching & Email Generation

> **Research Date:** 2026-03-08
> **Sources:** Anthropic official documentation (platform.claude.com/docs), GitHub (anthropics/anthropic-sdk-python)
> **Purpose:** Architecture decisions for bulk personalized email generation using Claude

---

## Table of Contents

1. [Message Batches API](#1-message-batches-api)
2. [Prompt Caching](#2-prompt-caching)
3. [Pricing & Cost Calculations](#3-pricing--cost-calculations)
4. [Python SDK Usage](#4-python-sdk-usage)
5. [Production Architecture for Email Generation](#5-production-architecture-for-email-generation)
6. [Cost Optimization Strategies](#6-cost-optimization-strategies)
7. [Recommended Architecture](#7-recommended-architecture)

---

## 1. Message Batches API

### 1.1 How It Works — Full Lifecycle

```
Create Batch → System processes asynchronously → Poll status → Retrieve results
```

1. You submit a batch containing multiple Messages API requests
2. Each request is processed **independently** (can mix request types)
3. Processing is asynchronous — most batches complete within **1 hour**
4. You poll for status or check the Console
5. Results are available as JSONL, streamed back in memory-efficient chunks

### 1.2 Request Format

Each batch is an **array of request objects** (NOT JSON Lines for input — that's only the output format). Each request object has:

- `custom_id` — unique string identifier for matching results to inputs
- `params` — standard Messages API parameters (model, max_tokens, messages, system, etc.)

### 1.3 Creating a Batch

**Endpoint:** `POST https://api.anthropic.com/v1/messages/batches`

**Authentication Headers:**
```
x-api-key: $ANTHROPIC_API_KEY
anthropic-version: 2023-06-01
content-type: application/json
```

**Request Body:**
```json
{
    "requests": [
        {
            "custom_id": "email-001",
            "params": {
                "model": "claude-haiku-4-5",
                "max_tokens": 1024,
                "system": "You are an expert B2B email writer...",
                "messages": [
                    {"role": "user", "content": "Write a personalized email to John Smith, CTO at Acme Corp..."}
                ]
            }
        },
        {
            "custom_id": "email-002",
            "params": {
                "model": "claude-haiku-4-5",
                "max_tokens": 1024,
                "system": "You are an expert B2B email writer...",
                "messages": [
                    {"role": "user", "content": "Write a personalized email to Jane Doe, VP Sales at Beta Inc..."}
                ]
            }
        }
    ]
}
```

**Python SDK:**
```python
import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

client = anthropic.Anthropic()

message_batch = client.messages.batches.create(
    requests=[
        Request(
            custom_id="email-001",
            params=MessageCreateParamsNonStreaming(
                model="claude-haiku-4-5",
                max_tokens=1024,
                system="You are an expert B2B email writer...",
                messages=[
                    {"role": "user", "content": "Write email to John Smith..."}
                ],
            ),
        ),
        # ... more requests
    ]
)
print(message_batch.id)  # e.g., "msgbatch_01HkcTjaV5uDC8jWR4ZsDV8d"
```

**Create Response:**
```json
{
  "id": "msgbatch_01HkcTjaV5uDC8jWR4ZsDV8d",
  "type": "message_batch",
  "processing_status": "in_progress",
  "request_counts": {
    "processing": 2,
    "succeeded": 0,
    "errored": 0,
    "canceled": 0,
    "expired": 0
  },
  "ended_at": null,
  "created_at": "2024-09-24T18:37:24.100435Z",
  "expires_at": "2024-09-25T18:37:24.100435Z",
  "cancel_initiated_at": null,
  "results_url": null
}
```

### 1.4 Polling for Completion

**Endpoint:** `GET https://api.anthropic.com/v1/messages/batches/{batch_id}`

**Status Values:**
- `in_progress` — still processing
- `canceling` — cancellation initiated, waiting for finalization
- `ended` — all requests completed (or expired/canceled)

**Python SDK Polling:**
```python
import time

message_batch = None
while True:
    message_batch = client.messages.batches.retrieve("msgbatch_01HkcTjaV5uDC8jWR4ZsDV8d")
    if message_batch.processing_status == "ended":
        break
    print(f"Batch is still processing... {message_batch.request_counts}")
    time.sleep(60)
```

### 1.5 Retrieving Results

Results are available at `results_url` as JSONL (each line is a JSON object). The SDK provides a streaming iterator:

**Python SDK:**
```python
for result in client.messages.batches.results("msgbatch_01HkcTjaV5uDC8jWR4ZsDV8d"):
    match result.result.type:
        case "succeeded":
            print(f"Success! {result.custom_id}")
            email_text = result.result.message.content[0].text
        case "errored":
            if result.result.error.type == "invalid_request":
                print(f"Validation error {result.custom_id}")
            else:
                print(f"Server error {result.custom_id}")
        case "expired":
            print(f"Request expired {result.custom_id}")
        case "canceled":
            print(f"Canceled {result.custom_id}")
```

**JSONL Result Format:**
```jsonl
{"custom_id":"email-002","result":{"type":"succeeded","message":{"id":"msg_014VwiXbi91y3JMjcpyGBHX5","type":"message","role":"assistant","model":"claude-haiku-4-5","content":[{"type":"text","text":"Subject: ..."}],"stop_reason":"end_turn","stop_sequence":null,"usage":{"input_tokens":11,"output_tokens":36}}}}
{"custom_id":"email-001","result":{"type":"succeeded","message":{"id":"msg_01FqfsLoHwgeFbguDgpz48m7","type":"message","role":"assistant","model":"claude-haiku-4-5","content":[{"type":"text","text":"Subject: ..."}],"stop_reason":"end_turn","stop_sequence":null,"usage":{"input_tokens":10,"output_tokens":34}}}}
```

### 1.6 Partial Failure Handling

Each request in a batch is processed **independently**. A batch can have a mix of results:

| Result Type | Description | Billed? |
|-------------|-------------|---------|
| `succeeded` | Request completed successfully, includes message | Yes |
| `errored` | Request failed (invalid request OR server error) | No |
| `canceled` | User canceled batch before this request was processed | No |
| `expired` | Batch hit 24-hour expiration before this request was processed | No |

The `request_counts` object on the batch shows how many requests are in each state. **You are only billed for succeeded requests.**

Error types within `errored`:
- `invalid_request` — request body is malformed, must fix before retrying
- Other errors — server errors, can retry directly

### 1.7 Rate Limits

**Batch API has its own rate limits, separate from the standard Messages API, shared across all models:**

| Tier | RPM (API endpoints) | Max batch requests in processing queue | Max batch requests per batch |
|------|---------------------|----------------------------------------|------------------------------|
| Tier 1 | 50 | 100,000 | 100,000 |
| Tier 2 | 1,000 | 200,000 | 100,000 |
| Tier 3 | 2,000 | 300,000 | 100,000 |
| Tier 4 | 4,000 | 500,000 | 100,000 |

**Additional constraints:**
- Max batch size: **100,000 requests** OR **256 MB**, whichever is reached first
- A "batch request" = one individual request within a batch
- Queue limit is across ALL active batches (not per-batch)

### 1.8 Latency

- **SLA:** 24 hours maximum. Batches expire if not completed within 24 hours.
- **Typical:** Most batches complete within **1 hour**
- **Variable:** Processing may be slowed based on current demand and request volume
- If demand is high, more requests may expire after 24 hours

### 1.9 Cancellation

You can cancel a batch that is currently processing:

```python
client.messages.batches.cancel("msgbatch_01HkcTjaV5uDC8jWR4ZsDV8d")
```

- Status changes to `canceling` immediately
- Eventually transitions to `ended`
- May contain partial results for requests processed before cancellation
- Unprocessed requests get `canceled` result type

### 1.10 Result Availability

- Results are available for **29 days** after creation
- After 29 days, you can still view the batch metadata but results are no longer downloadable
- Batches are scoped to a **Workspace** — visible to all API keys in that workspace

### 1.11 custom_id for Tracking

- **CRITICAL:** Results may be returned in **any order** — not necessarily matching input order
- Always use `custom_id` to map results back to inputs
- Must be unique within a batch
- Use meaningful IDs like `contact-{contact_id}-step-{step_number}` for email generation

---

## 2. Prompt Caching

### 2.1 How It Works

Prompt caching stores KV cache representations and cryptographic hashes of cached content (not raw text). When a subsequent request matches a cached prefix, the system reuses the cached computation instead of reprocessing.

**Cache ordering hierarchy:** `tools` → `system` → `messages`

### 2.2 What Gets Cached

**Cacheable:**
- Tool definitions in `tools` array
- System message content blocks
- Text messages in `messages.content` (user and assistant turns)
- Images and documents in user turns
- Tool use and tool results

**Not cacheable:**
- Thinking blocks cannot be directly cached with `cache_control` (but ARE cached alongside other content in assistant turns)
- Sub-content blocks (like citations)
- Empty text blocks

### 2.3 Two Implementation Methods

#### Method 1: Automatic Caching (Recommended for most cases)

Add `cache_control` at the top level of the request:

```python
response = client.messages.create(
    model="claude-haiku-4-5",
    max_tokens=1024,
    cache_control={"type": "ephemeral"},  # <-- top-level
    system="You are an AI assistant...",
    messages=[{"role": "user", "content": "..."}],
)
```

The system automatically applies cache breakpoint to the last cacheable block and moves it forward as conversations grow.

#### Method 2: Explicit Cache Breakpoints (Fine-grained control)

Place `cache_control` on individual content blocks:

```python
response = client.messages.create(
    model="claude-haiku-4-5",
    max_tokens=1024,
    system=[
        {
            "type": "text",
            "text": "You are an expert B2B email writer. Follow these guidelines...",
            "cache_control": {"type": "ephemeral"}  # <-- on this block
        }
    ],
    messages=[
        {"role": "user", "content": "Write an email to John Smith..."}
    ],
)
```

**Up to 4 explicit `cache_control` breakpoints allowed per request.**

### 2.4 Cache TTL

| TTL Option | Duration | Write Cost | When to Use |
|------------|----------|------------|-------------|
| Default (`"ephemeral"`) | 5 minutes | 1.25x base input | Rapid-fire requests (real-time API) |
| Extended (`"ephemeral"`, `"ttl": "1h"`) | 1 hour | 2x base input | Batch processing, less frequent requests |

**Cache is refreshed (TTL reset) at no additional cost each time cached content is used.**

Syntax for 1-hour TTL:
```json
{
    "cache_control": {
        "type": "ephemeral",
        "ttl": "1h"
    }
}
```

### 2.5 Pricing

**Cache read = 0.1x base input price (90% discount)**

| Model | Base Input | 5m Cache Write | 1h Cache Write | Cache Read | Output |
|-------|-----------|----------------|----------------|------------|--------|
| Claude Haiku 4.5 | $1/MTok | $1.25/MTok | $2/MTok | $0.10/MTok | $5/MTok |
| Claude Haiku 3.5 | $0.80/MTok | $1/MTok | $1.60/MTok | $0.08/MTok | $4/MTok |
| Claude Sonnet 4.x | $3/MTok | $3.75/MTok | $6/MTok | $0.30/MTok | $15/MTok |

**Break-even:**
- 5-minute cache: Pays for itself after **1 cache read** (1.25x write + 0.1x read = 1.35x vs 2x uncached)
- 1-hour cache: Pays for itself after **2 cache reads** (2x write + 2×0.1x read = 2.2x vs 3x uncached)

### 2.6 Minimum Cacheable Token Counts

| Model | Minimum Tokens |
|-------|---------------|
| Claude Haiku 4.5 | 4,096 tokens |
| Claude Haiku 3.5 | 2,048 tokens |
| Claude Sonnet 4.x | 2,048 tokens |
| Claude Opus 4.6, 4.5 | 4,096 tokens |

**IMPORTANT:** If your cached prefix is shorter than the minimum, caching will not activate.

### 2.7 Combining Batch API + Prompt Caching

**Yes, they stack.** The 50% batch discount applies on top of prompt caching pricing.

From the docs: *"These multipliers stack with other pricing modifiers, including the Batch API discount."*

**Recommendation for batches:** Use the **1-hour cache TTL** since batches can take over 5 minutes to process. From the docs: *"Since batches can take longer than 5 minutes to process, consider using the 1-hour cache duration with prompt caching for better cache hit rates when processing batches with shared context."*

### 2.8 Cache-Aware Rate Limits

**Cached input tokens (cache reads) do NOT count towards ITPM rate limits** for most models (except those marked with † — only Haiku 3.5 and Haiku 3).

This means with prompt caching, your effective throughput is much higher:
- Example: 2M ITPM limit + 80% cache hit rate = effectively 10M total input tokens per minute

**Haiku 4.5 cache reads do NOT count towards ITPM** — this is ideal for our use case.

### 2.9 Cache Invalidation

Changes that invalidate cache:
- Modifying tool definitions → invalidates everything
- Changing web search/citations toggle → invalidates system & message caches
- Changing tool_choice → invalidates message cache
- Adding/removing images → invalidates message cache

**For email generation:** Keep the system prompt and tools identical across all requests to maximize cache hits.

### 2.10 Tracking Cache Performance

```python
response = client.messages.create(...)

# Check cache usage
print(f"Cache write tokens: {response.usage.cache_creation_input_tokens}")
print(f"Cache read tokens: {response.usage.cache_read_input_tokens}")
print(f"Uncached input tokens: {response.usage.input_tokens}")

# Total input = cache_read + cache_creation + input_tokens
total = (response.usage.cache_read_input_tokens +
         response.usage.cache_creation_input_tokens +
         response.usage.input_tokens)
```

---

## 3. Pricing & Cost Calculations

### 3.1 Complete Pricing Table (Batch + Caching)

**Claude Haiku 4.5 — Recommended for Volume Email Generation:**

| Cost Category | Standard | Batch (50% off) |
|--------------|----------|-----------------|
| Base input | $1.00/MTok | $0.50/MTok |
| 5m cache write | $1.25/MTok | $0.625/MTok |
| 1h cache write | $2.00/MTok | $1.00/MTok |
| Cache read | $0.10/MTok | $0.05/MTok |
| Output | $5.00/MTok | $2.50/MTok |

**Claude Haiku 3.5 — Even Cheaper, Still Good Quality:**

| Cost Category | Standard | Batch (50% off) |
|--------------|----------|-----------------|
| Base input | $0.80/MTok | $0.40/MTok |
| 5m cache write | $1.00/MTok | $0.50/MTok |
| 1h cache write | $1.60/MTok | $0.80/MTok |
| Cache read | $0.08/MTok | $0.04/MTok |
| Output | $4.00/MTok | $2.00/MTok |

### 3.2 Model IDs

| Model | Model ID | Best For |
|-------|----------|----------|
| Claude Haiku 4.5 | `claude-haiku-4-5` | Best quality/cost ratio for email gen |
| Claude Haiku 3.5 | `claude-3-5-haiku-20241022` | Cheapest option, still good |
| Claude Sonnet 4.6 | `claude-sonnet-4-6` | Higher quality when needed |

### 3.3 Token Estimation for Emails

**Rough estimates (English text):**
- 1 token ≈ 4 characters ≈ 0.75 words
- 120-word email ≈ **160 output tokens**
- System prompt (tone, structure, compliance) ≈ **500-1,500 tokens**
- Cached prefix (ICP context, portfolio, value props) ≈ **1,000-3,000 tokens**
- Dynamic per-email data (name, title, company, enrichment) ≈ **200-500 tokens**

**Per-email token breakdown:**

| Component | Tokens | Pricing Category |
|-----------|--------|-----------------|
| System prompt + ICP context | ~2,000 | Cache read (after first) |
| Dynamic contact data | ~300 | Base input |
| Email output | ~160 | Output |

### 3.4 Cost Calculations

#### Using Claude Haiku 4.5 + Batch API + Prompt Caching (1h TTL)

**Per email (after first cache write):**
- Cache read (2,000 tokens): 2,000 × $0.05/MTok = $0.0001
- Uncached input (300 tokens): 300 × $0.50/MTok = $0.00015
- Output (160 tokens): 160 × $2.50/MTok = $0.0004
- **Total per email: ~$0.00065**

**First email (cache write):**
- Cache write (2,000 tokens): 2,000 × $1.00/MTok = $0.002
- Uncached input (300 tokens): 300 × $0.50/MTok = $0.00015
- Output (160 tokens): 160 × $2.50/MTok = $0.0004
- First email total: ~$0.00255

#### Volume Costs (Haiku 4.5 + Batch + 1h Cache)

| Volume | Cost Estimate | Notes |
|--------|--------------|-------|
| 1,000 emails | **$0.65** | Single step |
| 4,000 emails (4-step sequence × 1,000 contacts) | **$2.60** | 4 cache writes (1 per step) |
| 10,000 emails | **$6.50** | Single step |
| 10,000 emails (4-step × 2,500 contacts) | **$6.50** | 4 cache writes |

#### Comparison: Without Caching or Batching

| Volume | No optimization | Batch only | Batch + Cache |
|--------|----------------|------------|---------------|
| 1,000 emails | $2.80 | $1.40 | $0.65 |
| 4,000 emails | $11.20 | $5.60 | $2.60 |
| 10,000 emails | $28.00 | $14.00 | $6.50 |

**Savings: ~77% with Batch + Cache vs. no optimization**

### 3.5 Haiku vs Sonnet Decision

| Factor | Haiku 4.5 | Sonnet 4.x |
|--------|-----------|------------|
| Cost per 1,000 emails (batch+cache) | ~$0.65 | ~$2.60 |
| Quality | Good for templated emails | Better for nuanced personalization |
| Speed | Faster | Slower |
| **Recommendation** | Default for volume | Use for high-value prospects only |

**Strategy:** Generate with Haiku 4.5 by default. Offer Sonnet as a "premium quality" option for key accounts or when users request higher quality.

---

## 4. Python SDK Usage

### 4.1 Installation

```bash
pip install anthropic
```

### 4.2 Synchronous Client

```python
import anthropic

client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var
# or
client = anthropic.Anthropic(api_key="sk-ant-...")
```

### 4.3 Async Client

```python
import anthropic

client = anthropic.AsyncAnthropic()

# Use with await
response = await client.messages.create(
    model="claude-haiku-4-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}]
)
```

### 4.4 Batch Operations — Complete Workflow

```python
import anthropic
import time
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

client = anthropic.Anthropic()

# 1. Build requests
requests = []
for contact in contacts:
    requests.append(
        Request(
            custom_id=f"contact-{contact['id']}-step-1",
            params=MessageCreateParamsNonStreaming(
                model="claude-haiku-4-5",
                max_tokens=1024,
                system=[{
                    "type": "text",
                    "text": SYSTEM_PROMPT,  # Same across all emails
                    "cache_control": {"type": "ephemeral", "ttl": "1h"}
                }],
                messages=[{
                    "role": "user",
                    "content": f"""Write a personalized email to:
                    Name: {contact['name']}
                    Title: {contact['title']}
                    Company: {contact['company']}
                    Industry: {contact['industry']}
                    Pain points: {contact['pain_points']}"""
                }],
            ),
        )
    )

# 2. Create batch
message_batch = client.messages.batches.create(requests=requests)
print(f"Created batch: {message_batch.id}")

# 3. Poll for completion
while True:
    batch = client.messages.batches.retrieve(message_batch.id)
    print(f"Status: {batch.processing_status}, "
          f"Succeeded: {batch.request_counts.succeeded}, "
          f"Processing: {batch.request_counts.processing}")
    if batch.processing_status == "ended":
        break
    time.sleep(30)

# 4. Retrieve results
results = {}
failed = []
for result in client.messages.batches.results(message_batch.id):
    if result.result.type == "succeeded":
        results[result.custom_id] = result.result.message.content[0].text
    elif result.result.type == "errored":
        failed.append({
            "custom_id": result.custom_id,
            "error": result.result.error
        })
    elif result.result.type == "expired":
        failed.append({
            "custom_id": result.custom_id,
            "error": "expired"
        })

print(f"Succeeded: {len(results)}, Failed: {len(failed)}")

# 5. Retry failed items
if failed:
    retry_requests = [r for r in requests
                      if r.custom_id in [f["custom_id"] for f in failed
                                          if f.get("error") != "invalid_request"]]
    if retry_requests:
        retry_batch = client.messages.batches.create(requests=retry_requests)
        # ... poll and retrieve retry results
```

### 4.5 Error Handling Patterns

```python
from anthropic import (
    APIError,
    APIConnectionError,
    RateLimitError,
    APIStatusError,
)

try:
    response = client.messages.create(...)
except RateLimitError as e:
    # 429 - rate limited
    retry_after = e.response.headers.get("retry-after", 60)
    time.sleep(int(retry_after))
    # retry...
except APIConnectionError as e:
    # Network issues
    print(f"Connection error: {e}")
except APIStatusError as e:
    # 4xx or 5xx errors
    print(f"API error {e.status_code}: {e.message}")
except APIError as e:
    # Base class for all API errors
    print(f"API error: {e}")
```

### 4.6 SDK Built-in Retries

The SDK has built-in retry logic with exponential backoff:

```python
client = anthropic.Anthropic(
    max_retries=3,  # Default is 2
    timeout=600.0,  # Timeout in seconds
)
```

---

## 5. Production Architecture for Email Generation

### 5.1 Recommended Approach: Batch API (Primary)

For generating 1,000+ emails, the **Batch API is the clear winner:**

| Approach | 1,000 emails | Cost | Latency | Complexity |
|----------|-------------|------|---------|------------|
| Sequential API calls | Possible | Full price | ~17 min (1s each) | Low |
| Parallel with semaphore | Possible | Full price | ~5 min | Medium |
| **Batch API** | **Best** | **50% off** | **< 1 hour** | **Low** |

### 5.2 Implementation Pattern

```
User creates campaign
    → Backend builds batch requests (system prompt + per-contact data)
    → Submit batch to Anthropic API
    → Store batch_id in database
    → Background job polls for completion
    → On completion, stream results and store emails as drafts
    → User reviews/approves/edits drafts
    → Approved emails queued for sending
```

### 5.3 Prompt Structure for Maximum Caching

```python
SYSTEM_PROMPT = """You are an expert B2B email copywriter for {company_name}.

## Tone & Voice
- Professional but conversational
- Confident, not pushy
- Value-focused, not feature-focused

## Email Structure
1. Subject line (compelling, under 50 chars)
2. Opening line (personalized, reference something specific about their company)
3. Value proposition (1-2 sentences connecting their pain to our solution)
4. Social proof (brief, relevant case study or metric)
5. CTA (clear, low-friction ask)
6. Sign-off

## Compliance Rules
- No misleading claims
- No fake urgency
- Include opt-out language if required
- CAN-SPAM compliant

## Company Portfolio
{company_portfolio_description}

## Ideal Customer Profile
{icp_description}

## Value Propositions
{value_propositions}
"""

# This system prompt is ~1,500-3,000 tokens and will be cached
# across ALL email generations in the batch.
```

**Per-email dynamic content (NOT cached):**
```python
USER_PROMPT = f"""Write a personalized cold email for step {step_number} of our outreach sequence.

## Contact Information
- Name: {contact.first_name} {contact.last_name}
- Title: {contact.title}
- Company: {contact.company_name}
- Industry: {contact.industry}
- Company Size: {contact.employee_count} employees
- Location: {contact.location}

## Enrichment Data
{contact.enrichment_summary}

## Previous Emails in Sequence
{previous_emails_context if step_number > 1 else "This is the first email."}

Generate ONLY the email. No explanations or metadata.
"""
```

### 5.4 Handling Failures Gracefully

```python
def process_batch_with_retries(requests, max_retries=3):
    all_results = {}
    remaining = requests

    for attempt in range(max_retries):
        if not remaining:
            break

        batch = client.messages.batches.create(requests=remaining)

        # Poll for completion
        while True:
            status = client.messages.batches.retrieve(batch.id)
            if status.processing_status == "ended":
                break
            time.sleep(30)

        # Process results
        retryable = []
        for result in client.messages.batches.results(batch.id):
            if result.result.type == "succeeded":
                all_results[result.custom_id] = result.result.message.content[0].text
            elif result.result.type == "errored":
                if result.result.error.type != "invalid_request":
                    # Server error — retryable
                    retryable.append(result.custom_id)
                else:
                    # Invalid request — log and skip
                    logger.error(f"Invalid request: {result.custom_id}")
            elif result.result.type == "expired":
                retryable.append(result.custom_id)

        # Build retry list
        remaining = [r for r in requests if r.custom_id in retryable]
        if remaining:
            logger.info(f"Retrying {len(remaining)} failed requests (attempt {attempt + 2})")
            time.sleep(5)  # Brief pause before retry

    return all_results
```

### 5.5 Progress Tracking

```python
import time

def generate_emails_with_progress(requests, on_progress=None):
    batch = client.messages.batches.create(requests=requests)
    total = len(requests)

    while True:
        status = client.messages.batches.retrieve(batch.id)
        completed = (status.request_counts.succeeded +
                     status.request_counts.errored +
                     status.request_counts.canceled +
                     status.request_counts.expired)

        if on_progress:
            on_progress({
                "batch_id": batch.id,
                "total": total,
                "completed": completed,
                "succeeded": status.request_counts.succeeded,
                "errored": status.request_counts.errored,
                "processing": status.request_counts.processing,
                "percent": round(completed / total * 100, 1),
            })

        if status.processing_status == "ended":
            break
        time.sleep(15)

    return batch.id
```

### 5.6 Database Storage Pattern

```python
# Store generated emails as drafts
def store_batch_results(batch_id, campaign_id):
    for result in client.messages.batches.results(batch_id):
        if result.result.type == "succeeded":
            # Parse custom_id: "contact-{id}-step-{n}"
            parts = result.custom_id.split("-")
            contact_id = parts[1]
            step = int(parts[3])

            email_text = result.result.message.content[0].text

            # Extract subject and body (assuming model outputs "Subject: ...\n\n...")
            lines = email_text.strip().split("\n", 1)
            subject = lines[0].replace("Subject: ", "").strip()
            body = lines[1].strip() if len(lines) > 1 else email_text

            # Store as draft
            db.email_drafts.insert({
                "campaign_id": campaign_id,
                "contact_id": contact_id,
                "step": step,
                "subject": subject,
                "body": body,
                "status": "draft",  # draft → approved → sent
                "tokens_used": {
                    "input": result.result.message.usage.input_tokens,
                    "output": result.result.message.usage.output_tokens,
                },
                "created_at": datetime.utcnow(),
            })
```

### 5.7 Human Review Flow

```
1. GENERATE  →  Batch API creates all emails as "draft" status
2. REVIEW    →  User sees drafts in UI, can approve/edit/regenerate individual emails
3. APPROVE   →  Status changes to "approved"
4. SEND      →  Approved emails queued for delivery via email provider
```

For regeneration of individual emails, use the standard Messages API (not batch) for instant results:

```python
async def regenerate_single_email(contact, step, feedback=None):
    """Regenerate a single email with optional user feedback."""
    messages = [
        {"role": "user", "content": build_email_prompt(contact, step)}
    ]

    if feedback:
        messages.extend([
            {"role": "assistant", "content": previous_email_text},
            {"role": "user", "content": f"Please revise this email. Feedback: {feedback}"}
        ])

    response = await async_client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    return response.content[0].text
```

---

## 6. Cost Optimization Strategies

### 6.1 Combined Discount Calculation

**Batch API (50% off) + Prompt Caching (90% off reads) = up to 95% savings on cached input**

For cached input tokens with Batch API:
- Standard: $1.00/MTok
- Batch discount: $0.50/MTok
- Cache read with batch: $0.05/MTok (0.1x of $0.50)

**That's $0.05/MTok vs $1.00/MTok = 95% savings on cached input tokens.**

### 6.2 Minimizing Token Usage

1. **Keep system prompts concise** — every token counts for the cache write cost
2. **Avoid redundant examples** in system prompt — one good example > three mediocre ones
3. **Structure enrichment data efficiently** — use key-value format, not prose
4. **Set appropriate max_tokens** — for a 120-word email, `max_tokens: 512` is plenty (the model will stop at `end_turn` anyway, and `max_tokens` does NOT affect rate limits)

### 6.3 A/B Testing Prompts

```python
# Create two batches with different system prompts
batch_a = client.messages.batches.create(
    requests=[Request(
        custom_id=f"variant-a-{c['id']}",
        params=MessageCreateParamsNonStreaming(
            model="claude-haiku-4-5",
            max_tokens=512,
            system=PROMPT_VARIANT_A,
            messages=[{"role": "user", "content": build_prompt(c)}],
        ),
    ) for c in sample_contacts[:50]]  # Test on 50 contacts
)

batch_b = client.messages.batches.create(
    requests=[Request(
        custom_id=f"variant-b-{c['id']}",
        params=MessageCreateParamsNonStreaming(
            model="claude-haiku-4-5",
            max_tokens=512,
            system=PROMPT_VARIANT_B,
            messages=[{"role": "user", "content": build_prompt(c)}],
        ),
    ) for c in sample_contacts[:50]]
)

# Cost for A/B test of 50 contacts × 2 variants = 100 emails ≈ $0.065
```

### 6.4 When to Use Sonnet vs Haiku

| Scenario | Model | Reasoning |
|----------|-------|-----------|
| Standard outreach (1,000+ emails) | Haiku 4.5 | Cost-effective, good quality |
| Enterprise/high-value prospects | Sonnet 4.x | Better nuance, worth 4x cost |
| Follow-up sequences (steps 2-4) | Haiku 4.5 | Shorter, simpler emails |
| Initial cold email (step 1) | Haiku 4.5 or Sonnet | First impression matters most |
| Email revision/rewrite | Sonnet 4.x | Better at incorporating feedback |

---

## 7. Recommended Architecture

### 7.1 For Our Platform: Hybrid Approach

```
BULK GENERATION (Batch API):
┌─────────────────────────────────────────────────┐
│ User creates campaign with N contacts           │
│   → Build batch of N requests                   │
│   → System prompt (cached, 1h TTL)              │
│   → Per-contact dynamic data (uncached)         │
│   → Submit to Batch API                         │
│   → Background job polls every 30s              │
│   → On completion, store drafts in DB           │
│   → Notify user via WebSocket/polling           │
└─────────────────────────────────────────────────┘

SINGLE REGENERATION (Standard API):
┌─────────────────────────────────────────────────┐
│ User clicks "Regenerate" on a draft             │
│   → Standard Messages API (instant response)    │
│   → Prompt caching still helps (5min TTL)       │
│   → Update draft in DB                          │
│   → Return new email to UI immediately          │
└─────────────────────────────────────────────────┘
```

### 7.2 Configuration Constants

```python
# Model selection
DEFAULT_EMAIL_MODEL = "claude-haiku-4-5"
PREMIUM_EMAIL_MODEL = "claude-sonnet-4-6"

# Batch settings
MAX_BATCH_SIZE = 10_000          # Stay well under 100K limit
BATCH_POLL_INTERVAL_SECONDS = 30
BATCH_MAX_RETRIES = 3

# Cache settings
CACHE_TTL_BATCH = "1h"          # Use 1h for batches
CACHE_TTL_REALTIME = "5m"       # Default 5m for single regenerations

# Token limits
MAX_TOKENS_EMAIL = 512          # 120-word email needs ~160 tokens
MAX_TOKENS_SUBJECT = 64         # Subject line generation

# Cost tracking
ESTIMATED_CACHE_TOKENS = 2000   # System prompt + ICP context
ESTIMATED_INPUT_TOKENS = 300    # Per-email dynamic data
ESTIMATED_OUTPUT_TOKENS = 160   # Email output
```

### 7.3 Batch Size Strategy

For 1,000 contacts × 4-step sequence = 4,000 total emails:

**Option A: One batch per step (RECOMMENDED)**
- Batch 1: 1,000 emails for step 1 (all contacts)
- Batch 2: 1,000 emails for step 2 (all contacts)
- Batch 3: 1,000 emails for step 3 (all contacts)
- Batch 4: 1,000 emails for step 4 (all contacts)
- **Why:** Each step has a different system prompt variation; better cache utilization per batch

**Option B: All at once**
- One batch of 4,000 emails
- Mixed system prompts per step reduce cache effectiveness
- Harder to manage partial failures per step

### 7.4 Key Implementation Notes

1. **Validation first:** Test each unique request shape against the standard Messages API before batching — batch validation errors are returned asynchronously and harder to debug
2. **custom_id convention:** Use `{campaign_id}-{contact_id}-step{n}` for easy result mapping
3. **Idempotency:** Store batch_id in DB immediately after creation; if process crashes, you can resume polling
4. **Results are JSONL, not JSON array** — stream them, don't load all into memory
5. **29-day result retention** — download and store results in your DB promptly
6. **Workspace scoping** — batches are visible to all API keys in the workspace

---

## Sources

- [Batch Processing Documentation](https://platform.claude.com/docs/en/docs/build-with-claude/batch-processing)
- [Create a Message Batch API Reference](https://docs.anthropic.com/en/api/creating-message-batches)
- [Retrieve Message Batch Results](https://docs.anthropic.com/en/api/retrieving-message-batch-results)
- [Prompt Caching Documentation](https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching)
- [Pricing Documentation](https://platform.claude.com/docs/en/docs/about-claude/pricing)
- [Rate Limits Documentation](https://platform.claude.com/docs/en/api/rate-limits)
- [Anthropic Python SDK (GitHub)](https://github.com/anthropics/anthropic-sdk-python)
- [Message Batches API Announcement](https://www.anthropic.com/news/message-batches-api)
- [Prompt Caching Announcement](https://www.anthropic.com/news/prompt-caching)
