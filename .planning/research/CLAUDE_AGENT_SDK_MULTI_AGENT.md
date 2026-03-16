# Claude Agent SDK — Multi-Agent Orchestration Research

**Date**: 2026-03-08
**SDK Package**: `claude-agent-sdk` (Python) / `@anthropic-ai/claude-agent-sdk` (TypeScript)
**Formerly**: Claude Code SDK (renamed September 2025)

---

## 1. SDK Overview

The Claude Agent SDK exposes the same tools, agent loop, and context management that power Claude Code as a programmable library. It provides built-in tools (Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch) so agents can work autonomously without you implementing tool execution.

### Installation

```bash
# Python
pip install claude-agent-sdk

# TypeScript
npm install @anthropic-ai/claude-agent-sdk
```

### Authentication

```bash
export ANTHROPIC_API_KEY=your-api-key

# Also supports:
# Amazon Bedrock: CLAUDE_CODE_USE_BEDROCK=1
# Google Vertex AI: CLAUDE_CODE_USE_VERTEX=1
# Microsoft Azure: CLAUDE_CODE_USE_FOUNDRY=1
```

---

## 2. Core API — Two Interfaces

### 2a. `query()` — One-shot sessions

Creates a new session per call. Best for independent, parallelizable tasks.

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions

async def main():
    async for message in query(
        prompt="Find and fix the bug in auth.py",
        options=ClaudeAgentOptions(allowed_tools=["Read", "Edit", "Bash"]),
    ):
        print(message)

asyncio.run(main())
```

**Signature:**
```python
async def query(
    *,
    prompt: str | AsyncIterable[dict[str, Any]],
    options: ClaudeAgentOptions | None = None,
    transport: Transport | None = None
) -> AsyncIterator[Message]
```

### 2b. `ClaudeSDKClient` — Persistent sessions

Maintains conversation context across multiple exchanges. Supports interrupts.

```python
async with ClaudeSDKClient() as client:
    await client.query("Read the auth module")
    async for message in client.receive_response():
        print(message)

    # Follow-up with full context
    await client.query("Now find all callers")
    async for message in client.receive_response():
        print(message)
```

| Feature             | `query()`              | `ClaudeSDKClient`          |
|---------------------|------------------------|----------------------------|
| Session             | New each time          | Reuses same session        |
| Conversation        | Single exchange        | Multi-turn with context    |
| Interrupts          | No                     | Yes                        |
| Parallel-friendly   | **Yes** (independent)  | Per-client sequential      |
| Use case            | One-off / parallel     | Interactive / follow-ups   |

---

## 3. ClaudeAgentOptions — Full Configuration

Key fields for multi-agent orchestration:

```python
ClaudeAgentOptions(
    # Tools
    allowed_tools=["Read", "Edit", "Bash", "Agent"],  # Auto-approve these
    disallowed_tools=["Write"],                         # Always deny these

    # Subagents
    agents={                                            # Programmatic subagent defs
        "reviewer": AgentDefinition(...)
    },

    # Model
    model="claude-sonnet-4-20250514",                  # Primary model
    fallback_model="claude-haiku-4-20250514",          # Fallback on failure

    # Limits
    max_turns=50,                                       # Max agentic turns
    max_budget_usd=5.0,                                # Budget cap per session

    # Permissions
    permission_mode="acceptEdits",                     # Auto-accept file edits
    # or "bypassPermissions" for full autonomy

    # Context
    cwd="/path/to/project",                            # Working directory
    system_prompt="You are an expert...",              # Custom system prompt
    setting_sources=["project"],                       # Load CLAUDE.md files

    # Sessions
    resume="session-id-here",                          # Resume prior session
    fork_session=True,                                 # Fork instead of continue

    # Hooks
    hooks={
        "PostToolUse": [HookMatcher(matcher="Edit|Write", hooks=[log_fn])]
    },

    # MCP servers
    mcp_servers={
        "playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}
    },

    # Thinking
    thinking={"type": "adaptive"},                     # or {"type": "enabled", "budget_tokens": 10000}
    effort="high",                                     # low/medium/high/max
)
```

---

## 4. Subagents — Built-in Parallelization

Subagents are separate agent instances spawned by a main agent for focused subtasks. They provide:

1. **Context isolation** — Each subagent has its own context window; only final results return to parent
2. **Parallelization** — Multiple subagents run concurrently
3. **Specialized instructions** — Each gets its own system prompt and expertise
4. **Tool restrictions** — Limit what each subagent can do

### Defining Subagents Programmatically

```python
from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition

async for message in query(
    prompt="Review the auth module for security issues",
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Grep", "Glob", "Agent"],  # Agent tool required!
        agents={
            "code-reviewer": AgentDefinition(
                description="Expert code reviewer for quality and security.",
                prompt="Analyze code quality and suggest improvements...",
                tools=["Read", "Glob", "Grep"],        # Read-only
                model="sonnet",                          # Cost-effective for focused work
            ),
            "test-runner": AgentDefinition(
                description="Runs and analyzes test suites.",
                prompt="Run tests and provide analysis...",
                tools=["Bash", "Read", "Grep"],          # Can execute commands
            ),
        },
    ),
):
    if hasattr(message, "result"):
        print(message.result)
```

### AgentDefinition Fields

| Field         | Type                                    | Required | Description                        |
|---------------|-----------------------------------------|----------|------------------------------------|
| `description` | `str`                                   | Yes      | When to use this agent             |
| `prompt`      | `str`                                   | Yes      | System prompt / role definition    |
| `tools`       | `list[str] | None`                      | No       | Allowed tools (inherits all if omitted) |
| `model`       | `"sonnet" | "opus" | "haiku" | "inherit"` | No    | Model override                     |

### Key Constraints

- **Subagents cannot spawn their own subagents** (no nesting)
- Subagents don't inherit parent conversation history
- Subagents DO inherit project CLAUDE.md (via `settingSources`)
- Only the final message returns to the parent
- On Windows, long prompts may fail (8191 char cmd limit)

### Detecting Subagent Invocation

```python
async for message in query(prompt="...", options=options):
    if hasattr(message, "content") and message.content:
        for block in message.content:
            if getattr(block, "type", None) == "tool_use" and block.name in ("Task", "Agent"):
                print(f"Subagent invoked: {block.input.get('subagent_type')}")

    if hasattr(message, "parent_tool_use_id") and message.parent_tool_use_id:
        print("  (running inside subagent)")
```

---

## 5. Programmatic Parallel Agent Orchestration

### Pattern 1: asyncio.gather() with query()

The most direct way to run 20+ agents in parallel. Each `query()` call is independent.

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

async def analyze_file(filepath: str) -> str:
    """Run one agent per file."""
    result = ""
    async for msg in query(
        prompt=f"Review {filepath} for security vulnerabilities",
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Grep"],
            max_turns=50,
            max_budget_usd=1.0,
        ),
    ):
        if isinstance(msg, ResultMessage):
            result = msg.result or ""
    return result

async def main():
    files = [
        "src/auth.py", "src/payments.py", "src/users.py",
        "src/api.py", "src/database.py", "src/middleware.py",
        # ... up to 20+ files
    ]

    # Run ALL agents in parallel
    results = await asyncio.gather(
        *[analyze_file(f) for f in files],
        return_exceptions=True  # Don't fail all if one fails
    )

    # Aggregate results
    for filepath, result in zip(files, results):
        if isinstance(result, Exception):
            print(f"FAILED {filepath}: {result}")
        else:
            print(f"=== {filepath} ===\n{result}\n")

asyncio.run(main())
```

### Pattern 2: Semaphore-based Rate Limiting

Control concurrency to stay within API rate limits:

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

# Limit to N concurrent agents
CONCURRENCY_LIMIT = 10
semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

async def rate_limited_agent(task: dict) -> dict:
    async with semaphore:
        result = ""
        async for msg in query(
            prompt=task["prompt"],
            options=ClaudeAgentOptions(
                allowed_tools=task.get("tools", ["Read", "Grep"]),
                max_budget_usd=task.get("budget", 1.0),
                model=task.get("model", "claude-sonnet-4-20250514"),
            ),
        ):
            if isinstance(msg, ResultMessage):
                result = msg.result or ""
        return {"task_id": task["id"], "result": result}

async def orchestrate(tasks: list[dict]) -> list[dict]:
    results = await asyncio.gather(
        *[rate_limited_agent(t) for t in tasks],
        return_exceptions=True,
    )
    return [r for r in results if not isinstance(r, Exception)]
```

### Pattern 3: Dynamic Agent Factory

Create agents with different configurations based on task type:

```python
def create_agent_options(task_type: str) -> ClaudeAgentOptions:
    configs = {
        "security": ClaudeAgentOptions(
            allowed_tools=["Read", "Grep", "Glob"],
            model="claude-opus-4-20250514",      # Best model for security
            max_budget_usd=5.0,
            system_prompt="You are a security expert...",
        ),
        "style": ClaudeAgentOptions(
            allowed_tools=["Read", "Grep"],
            model="claude-haiku-4-20250514",     # Fast/cheap for style
            max_budget_usd=0.50,
        ),
        "tests": ClaudeAgentOptions(
            allowed_tools=["Read", "Bash", "Grep"],
            model="claude-sonnet-4-20250514",    # Balanced for tests
            permission_mode="acceptEdits",
            max_budget_usd=2.0,
        ),
    }
    return configs.get(task_type, configs["style"])
```

### Pattern 4: Orchestrator with Task Queue (Production)

For 20+ agents, use a proper task queue with Redis:

```
Orchestrator Agent (Opus)
    -> Task Decomposition
    -> Redis Task Queue
    -> Worker Agents (Sonnet/Haiku) x 10-20
    -> Results Aggregation
    -> Final Synthesis (Opus)
```

Key components:
- **Meta-agent** breaks requirements into parallel-executable tasks with dependency tracking
- **Workers** are spawned as separate processes or async tasks
- **File locking** (Redis NX) prevents race conditions on shared files
- **Topological sorting** ensures task dependency ordering

---

## 6. Agent Teams (Experimental)

A higher-level coordination system where multiple Claude Code instances work together with inter-agent communication. **Disabled by default.**

### Enable

```json
// settings.json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

### Key Differences from Subagents

| Feature        | Subagents                         | Agent Teams                           |
|----------------|-----------------------------------|---------------------------------------|
| Communication  | Report results back to parent     | Teammates message each other directly |
| Coordination   | Parent manages all work           | Shared task list, self-coordination   |
| Context        | Own window, results to caller     | Own window, fully independent         |
| Best for       | Focused tasks (result only)       | Complex collaborative work            |
| Token cost     | Lower (results summarized)        | Higher (each is separate instance)    |

### Architecture

- **Team lead**: Main session that creates team, spawns teammates, coordinates
- **Teammates**: Independent Claude Code instances working on tasks
- **Task list**: Shared task list with states (pending, in progress, completed)
- **Mailbox**: Direct messaging between agents

### Best Practices

- Start with 3-5 teammates (coordination overhead increases with more)
- 5-6 tasks per teammate is optimal
- Run Opus for lead, Sonnet for teammates to cut costs
- Avoid file conflicts — each teammate owns different files
- Use `TeammateIdle` and `TaskCompleted` hooks for quality gates

---

## 7. Rate Limits and Scaling Considerations

### API Rate Limits by Tier

| Tier | Deposit | RPM | ITPM (Sonnet 4.x) | OTPM (Sonnet 4.x) |
|------|---------|-----|--------------------|--------------------|
| 1    | $5      | 50  | 30,000             | 8,000              |
| 2    | $40     | 1,000 | 450,000          | 90,000             |
| 3    | $200    | 2,000 | 800,000          | 160,000            |
| 4    | $400    | 4,000 | 2,000,000        | 400,000            |

**Opus 4.x** shares the same limits as Sonnet 4.x per tier.
**Haiku 4.5** gets higher throughput (e.g., Tier 4: 4,000,000 ITPM).

### Practical Implications for Multi-Agent

- **Tier 1 (50 RPM)**: Can run ~2-3 agents comfortably (each makes ~15-20 RPM)
- **Tier 2 (1,000 RPM)**: Can run 20-50 agents with rate limiting
- **Tier 3+ (2,000+ RPM)**: Can run 50+ agents comfortably
- **A single 5-agent workflow can exhaust Tier 1 limits in 60 seconds**

### Rate Limit Optimization Strategies

1. **Prompt caching**: Cached input tokens do NOT count toward ITPM limits. With 80% cache hit rate, effective throughput is 5x.
2. **Model mixing**: Run Opus for orchestrator, Sonnet/Haiku for workers
3. **Semaphore concurrency control**: Cap concurrent agents below your RPM limit
4. **Exponential backoff**: On 429 errors, use `retry-after` header
5. **Token bucket awareness**: Limits use token bucket algorithm (continuous replenishment, not fixed windows)
6. **Budget caps**: Set `max_budget_usd` per agent to prevent runaway costs

### Rate Limit Response Headers

```
anthropic-ratelimit-requests-remaining
anthropic-ratelimit-tokens-remaining
anthropic-ratelimit-input-tokens-remaining
anthropic-ratelimit-output-tokens-remaining
retry-after
```

### Message Batches API (Alternative for Scale)

For non-real-time workloads, the Batches API allows up to:
- Tier 4: 500,000 batch requests in processing queue
- 100,000 requests per batch
- 50% cost reduction on input tokens

---

## 8. Cost Management

### Tracking Costs Programmatically

```python
from claude_agent_sdk import ResultMessage

async for msg in query(prompt="...", options=options):
    if isinstance(msg, ResultMessage):
        print(f"Cost: ${msg.total_cost_usd:.4f}")
        print(f"Input tokens: {msg.usage.get('input_tokens', 0)}")
        print(f"Output tokens: {msg.usage.get('output_tokens', 0)}")
        print(f"Cache read: {msg.usage.get('cache_read_input_tokens', 0)}")
        print(f"Duration: {msg.duration_ms}ms")
```

### Budget Control

```python
# Per-agent budget cap
options = ClaudeAgentOptions(
    max_budget_usd=2.0,    # Hard cap at $2
    max_turns=30,           # Also limit turns
)
```

### Cost Optimization Pattern: Opus Orchestrator + Sonnet Workers

```python
# Orchestrator: complex reasoning
orchestrator_options = ClaudeAgentOptions(
    model="claude-opus-4-20250514",
    max_budget_usd=10.0,
    agents={
        "worker": AgentDefinition(
            description="General worker",
            prompt="Execute the assigned task...",
            model="sonnet",  # Workers use cheaper model
        )
    }
)
```

---

## 9. Production Patterns

### Result Message Types

```python
from claude_agent_sdk import (
    UserMessage,           # User input
    AssistantMessage,      # Claude response (with content blocks)
    SystemMessage,         # System metadata
    ResultMessage,         # Final result with cost/usage
    StreamEvent,           # Partial streaming (opt-in)
    TaskStartedMessage,    # Background task started
    TaskProgressMessage,   # Task progress update
    TaskNotificationMessage, # Task completed/failed/stopped
)
```

### Content Block Types

```python
from claude_agent_sdk import TextBlock, ThinkingBlock, ToolUseBlock, ToolResultBlock
```

### Custom MCP Tools (In-Process)

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool("lookup_customer", "Look up customer by ID", {"customer_id": str})
async def lookup_customer(args):
    # Your business logic here
    data = await db.get_customer(args["customer_id"])
    return {"content": [{"type": "text", "text": json.dumps(data)}]}

server = create_sdk_mcp_server("business-tools", tools=[lookup_customer])

options = ClaudeAgentOptions(
    mcp_servers={"business": server},
    allowed_tools=["mcp__business__lookup_customer"],
)
```

### Scaling with Modal (Containerized Agents)

The `modal-claude-agent-sdk-python` package runs agents in secure, scalable Modal containers:

```python
from modal_agents_sdk import query, ModalAgentOptions
import modal

options = ModalAgentOptions(
    gpu="A10G",
    memory=16384,
    secrets=[modal.Secret.from_name("anthropic-key")],
    allowed_tools=["Read", "Write", "Bash"],
)

async for message in query("Analyze this dataset", options=options):
    print(message)
```

Features: GPU support, persistent volumes, custom Docker images, network isolation, auto-scaling.

---

## 10. Complete Multi-Agent Example: 20-File Parallel Review

```python
import asyncio
import json
from dataclasses import dataclass
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

@dataclass
class ReviewResult:
    filepath: str
    findings: str
    cost_usd: float
    duration_ms: int
    success: bool

CONCURRENCY = 10  # Match to your API tier
semaphore = asyncio.Semaphore(CONCURRENCY)

async def review_file(filepath: str) -> ReviewResult:
    async with semaphore:
        try:
            result_text = ""
            cost = 0.0
            duration = 0
            async for msg in query(
                prompt=f"Review {filepath} for bugs, security issues, and code quality. Be concise.",
                options=ClaudeAgentOptions(
                    allowed_tools=["Read", "Grep", "Glob"],
                    model="claude-sonnet-4-20250514",
                    max_budget_usd=1.0,
                    max_turns=20,
                    cwd="/path/to/project",
                ),
            ):
                if isinstance(msg, ResultMessage):
                    result_text = msg.result or ""
                    cost = msg.total_cost_usd or 0.0
                    duration = msg.duration_ms

            return ReviewResult(filepath, result_text, cost, duration, True)
        except Exception as e:
            return ReviewResult(filepath, str(e), 0.0, 0, False)

async def parallel_code_review(files: list[str]) -> list[ReviewResult]:
    results = await asyncio.gather(*[review_file(f) for f in files])

    # Summary
    total_cost = sum(r.cost_usd for r in results)
    total_time = max(r.duration_ms for r in results)  # Wall clock (parallel)
    failures = [r for r in results if not r.success]

    print(f"Reviewed {len(files)} files in {total_time/1000:.1f}s (wall clock)")
    print(f"Total cost: ${total_cost:.2f}")
    print(f"Failures: {len(failures)}")

    return results

# Usage
asyncio.run(parallel_code_review([
    "src/auth.py", "src/api.py", "src/models.py", "src/utils.py",
    "src/database.py", "src/cache.py", "src/middleware.py", "src/routes.py",
    "src/validators.py", "src/serializers.py", "src/permissions.py",
    "src/logging.py", "src/config.py", "src/tasks.py", "src/workers.py",
    "src/events.py", "src/notifications.py", "src/integrations.py",
    "src/monitoring.py", "src/migrations.py",
]))
```

---

## 11. TypeScript Equivalents

### Basic Query

```typescript
import { query } from "@anthropic-ai/claude-agent-sdk";

for await (const message of query({
  prompt: "Fix the bug in auth.py",
  options: {
    allowedTools: ["Read", "Edit", "Bash"],
    agents: {
      "code-reviewer": {
        description: "Expert code reviewer.",
        prompt: "Analyze code quality...",
        tools: ["Read", "Glob", "Grep"],
        model: "sonnet"
      }
    }
  }
})) {
  if ("result" in message) console.log(message.result);
}
```

### Parallel Agents in TypeScript

```typescript
import { query } from "@anthropic-ai/claude-agent-sdk";

async function reviewFile(filepath: string): Promise<string> {
  let result = "";
  for await (const msg of query({
    prompt: `Review ${filepath} for issues`,
    options: { allowedTools: ["Read", "Grep"] }
  })) {
    if ("result" in msg) result = msg.result;
  }
  return result;
}

// Run 20 agents in parallel
const files = ["auth.py", "api.py", /* ... */];
const results = await Promise.all(files.map(f => reviewFile(f)));
```

---

## 12. Key Takeaways

1. **`query()` is the parallel primitive** — each call is independent, works perfectly with `asyncio.gather()` / `Promise.all()`
2. **Subagents provide in-session parallelism** — Claude decides when to parallelize, you define capabilities
3. **Agent Teams provide inter-agent communication** — experimental, higher token cost, best for collaborative work
4. **Rate limits are the main bottleneck** — Tier 2+ needed for 20+ agents. Use semaphores.
5. **Prompt caching is critical** — cached tokens don't count toward ITPM, effectively multiplying throughput 5x
6. **Model mixing saves money** — Opus for orchestration, Sonnet/Haiku for workers
7. **Budget caps prevent runaway costs** — always set `max_budget_usd` and `max_turns`
8. **Modal provides containerized scaling** — for production workloads needing GPU, isolation, auto-scaling
9. **Message Batches API** — for non-real-time, high-volume workloads at 50% input cost reduction
10. **Each agent spawns a CLI subprocess** — resource overhead is real; monitor CPU/memory

---

## Sources

- [Agent SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Agent SDK Python Reference](https://platform.claude.com/docs/en/agent-sdk/python)
- [Subagents in the SDK](https://platform.claude.com/docs/en/agent-sdk/subagents)
- [Agent Teams Documentation](https://code.claude.com/docs/en/agent-teams)
- [Rate Limits](https://platform.claude.com/docs/en/api/rate-limits)
- [Building Agents with the Claude Agent SDK (Anthropic Blog)](https://claude.com/blog/building-agents-with-the-claude-agent-sdk)
- [Multi-Agent Orchestration: Running 10+ Claude Instances in Parallel](https://dev.to/bredmond1019/multi-agent-orchestration-running-10-claude-instances-in-parallel-part-3-29da)
- [Claude Agent SDK Demos (GitHub)](https://github.com/anthropics/claude-agent-sdk-demos)
- [Python SDK Repository](https://github.com/anthropics/claude-agent-sdk-python)
- [TypeScript SDK Repository](https://github.com/anthropics/claude-agent-sdk-typescript)
- [Modal Claude Agent SDK](https://github.com/sshh12/modal-claude-agent-sdk-python)
- [Claude Agent SDK: Subagents, Sessions and Why It's Worth It](https://www.ksred.com/the-claude-agent-sdk-what-it-is-and-why-its-worth-understanding/)
