# Mneme

**Prevent LLMs from violating prior project decisions.**

Mneme is a lightweight decision-enforcement layer for AI-assisted development workflows.

Mneme makes AI coding behave like a consistent engineer, not a stateless assistant.

---

## Mneme for Claude Code

Architectural governance for [Claude Code](https://docs.anthropic.com/en/docs/claude-code).
Enforce ADRs and engineering constraints automatically — before drift reaches your repo.

```bash
pip install mneme
python scripts/install_claude_code.py        # project-scoped: writes to ./.claude/
# or: python scripts/install_claude_code.py --user   # writes to ~/.claude/
```

This installs a `PreToolUse` hook so every Edit / Write / MultiEdit is checked
against `.mneme/project_memory.json` in strict mode by default. See
[docs/integrations/claude-code.md](docs/integrations/claude-code.md) for
details, including retrieval behaviour and mode switching.

---

## The problem

LLMs drift in long-running projects. They forget prior architecture choices, reintroduce rejected technologies, and suggest changes that violate decisions already made by the team.

Mneme turns those decisions into structured, retrievable constraints that can be injected into LLM calls and checked against generated output.

## What Mneme is

**Mneme** is a portable project memory and evaluation nucleus for AI workflows.

This repository demonstrates the first core capability: injecting structured project memory into LLM/API calls so outputs stay consistent with prior project decisions.

```python
from mneme.memory_store import MemoryStore
from mneme.retriever import Retriever
from mneme.context_builder import format_context_packet
from mneme.llm_adapter import LLMAdapter

memory = MemoryStore("examples/project_memory.json").load()
packet = Retriever(memory).retrieve("Should we rebuild from scratch?")
response = LLMAdapter().complete(
    user="Should we rebuild from scratch?",
    system=format_context_packet(packet),
)
print(response.content)
```

## How it works

Mneme turns project memory into a structured context packet that is injected into every LLM call.

The pipeline is:

1. **Memory store** — structured project memory: rules, constraints, facts, decision examples
2. **Deterministic retrieval** — selects relevant items based on the input task
3. **Context packet** — builds a compact, structured representation of what the model needs to know
4. **Injection** — the context packet is passed as the system prompt
5. **Evaluation** (optional) — outputs are scored against the injected context to check alignment

This is intentionally simple:

* no vector database
* no long context windows
* no agent loops

The goal is not to give the model more information. It is to make it **respect prior decisions**.

---

## The flagship example

**Task**: "Should we rebuild the retrieval system from scratch with embeddings?"

**WITHOUT MNEME:**
```
We could consider rebuilding the system with a vector database and embedding
model. This would improve semantic matching and scale better long-term.
Sentence-transformers is a good option for generating embeddings...
```

**WITH MNEME:**
```
Do not rebuild from scratch. The project has an explicit rule to extend current
infrastructure before rebuilding (rule-001). Keyword scoring was chosen
intentionally -- it is deterministic, has no ML dependencies, and is easy to
debug. The team already declined adding sentence-transformers in v1. Extend
the current retriever instead.
```

**MNEME ALIGNMENT:**
```
  [OK]   rule-001: Extend current infrastructure before rebuilding
  [OK]   rule-002: Keep v1 retrieval deterministic
  [OK]   anti-001: Do not use langchain
  [OK]   dec-001: Declined. Kept keyword scoring.
  alignment_score: 1.00
```

Same model. Same question. Different answer -- because it has the project's actual decisions.

## What this repo demonstrates

A five-stage pipeline that runs locally in under two minutes:

```
project_memory.json -> MemoryStore -> Retriever -> ContextBuilder -> LLMAdapter -> Evaluator
```

1. **Load** structured project memory from a human-editable JSON file
2. **Retrieve** the rules and examples relevant to the current task
3. **Build** a context packet and inject it into the system prompt
4. **Call** the LLM (or dry-run without an API key)
5. **Evaluate** whether the response followed your rules

The demo runs each task twice -- once without memory (baseline) and once with memory injected -- so you can see the delta.

## Why not just RAG?

RAG retrieves **information**. Mneme retrieves **decisions**.

* Not retrieval of documents — retrieval of **decisions your project already made**
* Not long context — a **structured context packet** with only what is relevant to the query
* Not autonomy — **consistency enforcement**: the model is told what was decided, not asked to figure it out

| | RAG | Mneme |
|---|---|---|
| Input | Documents, chunks, embeddings | Rules, constraints, decision records |
| Goal | Inform the response | Shape the response |
| Output effect | Model knows more | Model follows your decisions |
| Evaluation | "Did it use the right source?" | "Did it respect the constraint?" |

Mneme is not a search engine for your docs. It is a structured rule system that tells the model what your project has already decided and checks whether it listened.

## Architecture

```
mneme-project-memory/
  mneme/
    schemas.py              Dataclasses: MemoryItem, Decision, DecisionExample, ContextPacket
    memory_store.py         Load project_memory.json; auto-migrate legacy rule/anti_pattern items
    retriever.py            v1: keyword overlap + tag match + priority weight (unchanged)
    decision_retriever.py   v2: field-weighted scoring over Decision records
    context_builder.py      format_context_packet (v1) + format_decisions/top-N (v2)
    conflict_detector.py    v2: post-response violation scanner
    pipeline.py             v2: MemoryStore -> DecisionRetriever -> inject -> LLM -> detect
    llm_adapter.py          Thin Anthropic API wrapper with dry-run mode
    evaluator.py            v1: deterministic alignment checker (unchanged)
    cli.py                  v2: add_decision / list_decisions / test_query commands
  examples/
    project_memory.json     20 items + 5 examples + 3 native decisions for this repo
    demo_tasks.json         3 decision-oriented tasks for the before/after demo
  demo.py                   CLI runner: baseline vs. Mneme-enhanced, with alignment scoring
```

### Memory item types

| Type | What it is | Evaluator behavior |
|------|-----------|-------------------|
| `rule` | Hard constraint -- must follow | Violation flagged |
| `anti_pattern` | Explicitly ruled out | Violation flagged |
| `preference` | Should-follow guideline | Surfaced in context |
| `fact` | Established truth (language, version, provider) | Surfaced in context |
| `architecture_decision` | ADR-style choice with rationale | Surfaced in context |
| `example` | Worked illustration or code snippet | Surfaced in context |

### Decision examples

Separate from items. Each one records a situation, what the project decided, and why:

```json
{
  "task": "A contributor proposed adding sentence-transformers for semantic retrieval in v1.",
  "decision": "Declined. Kept keyword scoring.",
  "rationale": "Heavy ML dependency that breaks the pip-install-in-30-seconds contract."
}
```

These are injected as prior decisions so the model learns how your project reasons, not just what it decided.

### Retrieval

Fully deterministic. Same query + same memory file = same output every time.

- **Keyword overlap**: +1.0 per query token found in item title/content
- **Tag match**: +1.5 per query token that exactly matches a tag
- **Priority scaling**: score multiplied by item weight (high=1.5, medium=1.0, low=0.5)
- **Rules always surface**: rules and anti-patterns are included regardless of query relevance
- **Fallback**: if no facts match, top 3 by weight are included so context is never empty

No embeddings. No vector store. Determinism is a feature, not a limitation.

### Evaluation

The evaluator checks the response against the rules that were actually injected (the `ContextPacket`), not the full memory file. Two checks:

1. **Rule check**: extracts forbidden terms from each rule/anti-pattern. A violation fires when a term appears with a positive recommendation signal and no negation nearby.
2. **Decision check**: for past decisions where the project said "no," checks whether the response recommends the declined subject anyway.

Score = fraction of checks passed. 1.00 = no violations detected.

The evaluator is deterministic, fast, and auditable. The upgrade path to a model-based judge is explicit in the code: replace two functions, keep everything else.

## v2: Decision enforcement layer

Mneme v0.2 adds structured `Decision` records, field-weighted retrieval, top-N
injection, post-response conflict detection, and a CLI — all additive. The v1
pipeline is unchanged. Legacy `rule` and `anti_pattern` items are auto-migrated
into `Decision` objects at load time; no changes needed to existing JSON files.

### Decision schema

```json
{
  "id": "mneme_storage_json",
  "decision": "Use JSON storage only",
  "rationale": "Avoid infra complexity and keep local-first.",
  "scope": ["storage", "backend"],
  "constraints": ["no postgres", "no external database"],
  "anti_patterns": ["introduce ORM", "add migration layer"]
}
```

Add a top-level `"decisions"` array alongside `"items"` and `"examples"` in
`project_memory.json`. All seven fields are optional except `id` and `decision`.

### Scoring formula

`DecisionRetriever` scores each decision with field-weighted keyword overlap
(deterministic, no ML, same query always returns the same ranking):

```
score =
    overlap(query, decision)      * 1.0
  + overlap(query, scope)         * 2.0
  + overlap(query, constraints)   * 1.5
  + overlap(query, anti_patterns) * 1.5
  + overlap(query, rationale)     * 0.5
```

### Top-N injection

Only the top-scoring decisions are injected. The default cap is
`DEFAULT_MAX_DECISIONS = 3`. Override per call:

```python
from mneme.pipeline import Pipeline

result = Pipeline("examples/project_memory.json", dry_run=True, max_decisions=5).run(query)
print(result.system_prompt)   # formatted block injected as system prompt
print(result.injected_decisions)  # list[Decision] actually sent
```

### Strict enforcement mode

By default `Pipeline` runs in `warn` mode: conflicts are surfaced on
`PipelineResult.conflicts` and the caller decides what to do. For pipelines
that should fail fast on any detected violation — e.g. a CI gate or a
scripted workflow — pass `enforcement_mode="strict"`:

```python
from mneme.pipeline import Pipeline
from mneme.schemas import MnemeConflictError

p = Pipeline(
    "examples/project_memory.json",
    dry_run=True,
    enforcement_mode="strict",
)

try:
    result = p.run("Should I switch storage to Postgres?")
except MnemeConflictError as err:
    # err.conflicts: list[Conflict] from ConflictDetector
    # err.result:    the partial PipelineResult, so you can still inspect
    #                the LLM response, the system prompt, and the injected
    #                decisions that produced the violation.
    for c in err.conflicts:
        print(c.violated_decision_id, "->", c.reason)
```

Strict mode runs the conflict detector on the response and raises if any
conflict is found. It does **not** retry, regenerate, or block the LLM call
upstream — that's a deliberate non-goal for this iteration.

### Conflict detection

`ConflictDetector` scans the LLM response for constraint and anti-pattern
violations **after** the call. It is a detector, not a blocker:

```python
from mneme.conflict_detector import ConflictDetector
conflicts = ConflictDetector().detect(response.content, injected_decisions)
# Conflict(violated_decision_id, reason, snippet) per match
```

A term is only flagged when it appears **without** a negation signal nearby.
`"Do not use Postgres"` is not a conflict. `"Switch to Postgres"` is.

### CLI

```bash
# List all decisions (native + auto-migrated legacy items)
mneme list_decisions --memory examples/project_memory.json

# Append a new decision (file write only — does not mutate a live Pipeline)
mneme add_decision --memory examples/project_memory.json \
    --id mneme_042 --decision "No GraphQL in v1" \
    --scope api --constraint "REST only" --anti-pattern "introduce graphql"

# Score a query and preview the injected block
mneme test_query --memory examples/project_memory.json \
    --query "should I add postgres?" --top 3

# Generate a Cursor rules file from the top-3 relevant decisions
mneme cursor generate --memory examples/project_memory.json \
    --query "working on storage layer" \
    --output .cursor/rules/mneme.mdc \
    --top 3

# Check a prompt file against decisions before sending it to an agent
mneme check --memory examples/project_memory.json \
    --input examples/prompt_violation.txt \
    --query "storage backend"

# strict mode (default): WARN→exit 1, FAIL→exit 2 — gates CI pipelines
mneme check --mode strict \
    --memory examples/project_memory.json \
    --input examples/prompt_violation.txt \
    --query "storage backend"

# warn mode: all verdicts exit 0 — logs violations without blocking
mneme check --mode warn \
    --memory examples/project_memory.json \
    --input examples/prompt_violation.txt \
    --query "storage backend"
```

---

## v0.4: Architectural compiler

Mneme v0.4 compiles a versioned corpus of ADR markdown files into a
deterministic active constraint set. ADRs are the source of truth; the
compiler is the deterministic rule for turning them into the constraints
the runtime injects.

```
ADR corpus  ->  parse  ->  validate  ->  resolve precedence
            ->  active constraint set  ->  Decision records  ->  runtime
```

### ADR frontmatter

```yaml
---
id: ADR-001
title: Use JSON file storage
status: accepted          # proposed | accepted | deprecated | superseded
priority: foundational    # foundational | normal | exception
date: 2026-01-10
scope: storage            # dotted path; empty string = global
supersedes: []
---

Body markdown follows.
```

### Corpus validation

`validate_corpus` aggregates every detected problem before raising — one
pass surfaces every error so maintainers fix the corpus once:

- required fields present
- ADR id format (`ADR-\d+`) and uniqueness
- valid `status` / `priority` enums
- ISO 8601 date
- scope grammar (lowercase dotted path, no leading/trailing dot)
- `supersedes` references resolve to known ADRs
- no supersession cycles (self / 2-node / N-node)

### Precedence resolution

Same-scope conflicts resolve via a deterministic hierarchy. The compiler
never silently picks a winner:

1. Explicit `supersedes` — referenced ADRs are removed (chain-aware)
2. Same scope, higher priority wins (foundational > normal > exception)
3. Same scope + priority, newer date wins
4. Otherwise → `ADRPrecedenceError`

Broader and narrower scopes coexist; output is sorted most-specific-first.

### Usage

```python
from mneme.adr_compiler import compile_adrs, adrs_to_decisions
from mneme.decision_retriever import DecisionRetriever

decisions = adrs_to_decisions(compile_adrs("docs/adr"))
retriever = DecisionRetriever(decisions)
```

The bridge into the existing `Decision` schema means the runtime pipeline
(retriever, conflict detector, context builder) consumes ADR-driven
corpora without code changes.

---

## Cursor workflow

Mneme generates a Cursor-compatible `.mdc` rules file from your project decisions.
The file is injected into Cursor AI's context so every code suggestion it makes
already knows your constraints.

```
project_memory.json
       │
       ▼
mneme cursor generate --query "working on storage layer"
       │
       ▼
.cursor/rules/mneme.mdc  ◄── Cursor reads this before generating code
```

**Command:**

```bash
mneme cursor generate \
  --memory examples/project_memory.json \
  --query "working on storage layer" \
  --output .cursor/rules/mneme.mdc \
  --top 3
```

**Output shape** (`.cursor/rules/mneme.mdc`):

```markdown
---
description: "Mneme decisions for: working on storage layer"
globs: "**/*"
alwaysApply: false
---

# Mneme Project Memory

> ⚠️ Generated by Mneme — do not edit manually.
> Source: examples/project_memory.json
> Query: working on storage layer
> Generated: 2026-04-24T12:00:00Z

## Decisions

### [mneme_storage_json] Use JSON storage only

**Why:** Avoid infra complexity and keep local-first.
**Scope:** storage, backend, persistence
**Constraints:**
- no postgres
- no external database
- no ORM

**Avoid:**
- introduce ORM
- add migration layer
- add sqlalchemy
```

Re-generate after adding or changing decisions. Commit `.cursor/rules/mneme.mdc`
alongside `project_memory.json` so the whole team gets the same constraints.

---

## Check before agent execution

`mneme check` validates a prompt or AI-generated suggestion against your project
decisions **before** it reaches a coding agent. It exits non-zero on violations
so it can gate CI pipelines or pre-commit hooks.

```
examples/prompt_violation.txt
       │
       ▼
mneme check --memory project_memory.json \
            --input  examples/prompt_violation.txt \
            --query  "storage backend"
       │
       ├── PASS (exit 0)  → proceed to agent
       ├── WARN (exit 1)  → constraint mention — review before proceeding
       └── FAIL (exit 2)  → anti-pattern match — blocked
```

**Try it with the included examples:**

```bash
# This prompt introduces sqlalchemy and a migration layer — FAIL (exit 2)
mneme check \
  --memory examples/project_memory.json \
  --input  examples/prompt_violation.txt \
  --query  "storage backend"
```

```
FAIL  [mneme_storage_json] anti_pattern "add migration layer" — trigger: migration
      Use JSON storage only
FAIL  [mneme_storage_json] anti_pattern "add sqlalchemy" — trigger: sqlalchemy
      Use JSON storage only

Result: FAIL
```

```bash
# This prompt extends the storage module within the JSON contract — PASS (exit 0)
mneme check \
  --memory examples/project_memory.json \
  --input  examples/prompt_clean.txt \
  --query  "storage backend"
```

```
Result: PASS
```

**What triggers each level:**

| Verdict | Trigger | `strict` exit | `warn` exit |
|---------|---------|:---:|:---:|
| `PASS`  | No violations in top-N decisions | 0 | 0 |
| `WARN`  | Input mentions a term forbidden by a `"no X"` constraint | 1 | 0 |
| `FAIL`  | Input contains a term from a decision's `anti_patterns` list | 2 | 0 |

Detection is deterministic — no ML, no LLM, no external calls. Same input
always returns the same verdict.

### Enforcement modes

`--mode strict` *(default)* — designed for CI gates and pre-commit hooks.
Any violation causes a non-zero exit that stops the pipeline.

```bash
# Gate a CI step: fail the build if the prompt violates decisions
mneme check --mode strict \
  --memory examples/project_memory.json \
  --input  prompt.txt \
  --query  "storage backend"
```

`--mode warn` — designed for observability and gradual adoption.
Violations are printed with full detail but the process always exits 0,
so existing scripts are never broken.

```bash
# Log violations without blocking the agent
mneme check --mode warn \
  --memory examples/project_memory.json \
  --input  prompt.txt \
  --query  "storage backend"
```

Both modes print the same structured output. Only the exit code differs.

---

## ADR import

Drop an existing ADR corpus into Mneme's enforceable memory:

```bash
mneme adr import docs/adr --memory .mneme/project_memory.json --dry-run
```

The default is dry-run: the preview shows the active set, the projected
graph status of every ADR, the constraints that would be persisted, and
any conflicts. Apply when you're satisfied:

```bash
mneme adr import docs/adr --memory .mneme/project_memory.json --apply
```

Conflict gates:
- `--update-existing` -- required to overwrite a decisions[] entry whose id
  matches an incoming ADR.
- `--approve-conflicts` -- required to proceed when two accepted ADRs in
  the corpus share a scope, priority, and date (an "active-active
  contradiction" the compiler refuses to resolve silently).

Supported ADR format: YAML frontmatter + markdown body. The body may
include an optional `## Constraints` section with directives:

```markdown
## Constraints
- FORBID_DEPENDENCY: mongodb
- FORBID_PATH: src/legacy/**
- REQUIRE_PATH: billing/**
```

Only `FORBID_DEPENDENCY` is currently end-to-end enforced (via
`mneme check`); `FORBID_PATH` and `REQUIRE_PATH` persist into Decisions
for retrieval visibility but glob-vs-changed-file enforcement is a
follow-up.

See [docs/integrations/adr-import.md](../docs/integrations/adr-import.md)
for the full reference.

---

## Quick demo

```bash
python -m mneme.cli list_decisions --memory examples/project_memory.json
python -m mneme.cli test_query --memory examples/project_memory.json --query "should I use Postgres?" --top 3
python demo.py --dry-run
```

---

## Quickstart

```bash
git clone https://github.com/mneme-project/mneme-project-memory
cd mneme-project-memory

# Core only
pip install -e .

# Core + API layer
pip install -e ".[api]"
```

```bash
# Set your Anthropic API key
cp .env.example .env
# Edit .env: ANTHROPIC_API_KEY=sk-ant-...
```

```bash
# Run the before/after demo (live API calls)
python demo.py

# Run without an API key (prints prompts, no API calls)
python demo.py --dry-run

# Run a single task
python demo.py --task task-001

# Inspect what Mneme would inject, without calling the LLM
python demo.py --context-only
```

### Requirements

- Python 3.11+
- `anthropic` >= 0.25.0
- `python-dotenv` >= 1.0.0

That is the entire dependency list.

## Example: project_memory.json

The included example describes this repo itself. Abbreviated:

```json
{
  "meta": {
    "name": "mneme-context-engine",
    "description": "Inject structured project memory into LLM API calls.",
    "version": "0.1.0"
  },
  "items": [
    {
      "id": "rule-001",
      "type": "rule",
      "title": "Extend current infrastructure before rebuilding",
      "content": "When adding capability, first ask whether an existing module can be extended.",
      "tags": ["architecture", "scope"],
      "priority": "high"
    },
    {
      "id": "anti-001",
      "type": "anti_pattern",
      "title": "Do not use langchain",
      "content": "langchain abstracts away the API surface this library is designed to control.",
      "tags": ["langchain", "forbidden"],
      "priority": "high"
    }
  ],
  "examples": [
    {
      "task": "A contributor proposed adding sentence-transformers for semantic retrieval in v1.",
      "decision": "Declined. Kept keyword scoring.",
      "rationale": "Heavy ML dependency. Breaks pip-install-in-30-seconds contract."
    }
  ]
}
```

The full file has 20 items and 5 decision examples. Edit it for your own project -- it is plain JSON, no tooling required.

## Demo tasks

| Task | What Mneme catches |
|------|--------------------|
| Rebuild from scratch? | rule-001 (extend over rebuild), dec-001 (embeddings declined) |
| Broaden v1 scope? | anti-002 (no agentic loops), rule-004 (narrow MVP) |
| Mix project + personal memory? | rule-003 (separate project from personal), dec-002 (per-project only) |

## Enforcement regression suite

Mneme ships with a deterministic regression suite that exercises the enforcement engine against hand-authored fixture responses.

Current scenario coverage:

- Storage backend drift
- Retrieval overengineering
- Framework abstraction creep
- Infrastructure scope creep
- Feature boundary violations

Run locally:

```bash
mneme benchmark examples/benchmarks/ --memory examples/project_memory.json
```

Reports are generated in:

- `examples/benchmarks/reports/RESULTS.md`
- `examples/benchmarks/reports/results.json`

### What this is — and what it isn't

This suite is a **regression test for the deterministic enforcer**, not a behavioral evaluation of LLM output. Each scenario consists of two hand-authored fixture responses — one that names a forbidden technology, one that doesn't — and the suite verifies that the enforcer flags the first and not the second. No LLM is invoked anywhere in the harness.

The suite is useful for catching regressions in retrieval and enforcement logic. It does **not** measure whether Mneme changes real model output. A behavioral evaluation harness — running real LLM samples under baseline and Mneme-injected conditions, with violation rates and confidence intervals — is on the roadmap but not yet built. Until it is, do not interpret a green regression suite as evidence that Mneme prevents violations in production.

## Why this matters

- **LLM calls are stateless.** Every API call starts from zero. Without explicit project context, the model gives plausible answers that routinely contradict your established decisions. Mneme makes the context explicit and the injection automatic.

- **Project memory is a structured artifact, not a blob.** Dumping raw notes into a system prompt does not scale. Mneme types each piece of memory (rule, anti-pattern, decision example), assigns priority, and retrieves only what is relevant. The context stays compact.

- **Evaluation closes the loop.** Injecting context is half the problem. The other half is knowing whether it worked. The evaluator checks the response against the rules that were injected and returns a score. This is the beginning of measurable LLM alignment at the project level.

## Roadmap

See the [Adoption and Enhancement Roadmap](../docs/roadmap/2026-04-24-adoption-and-enhancement-roadmap.md).

| Version | Capability |
|---------|-----------|
| **v0.1** | JSON-backed memory, keyword retrieval, deterministic evaluation, before/after demo |
| **v0.2** ✓ | Decision enforcement layer: `mneme check` (PASS/WARN/FAIL), Cursor rules generator, drift detection test harness |
| **v0.3** ✓ | Configurable enforcement modes (`strict` / `warn`); Claude Code hook + slash commands (v0.3.2) |
| **v0.4** ✓ | Architectural compiler: ADR frontmatter schema, corpus validation, deterministic precedence engine, Decision-bridge integration |
| **v1.0** | Multi-project support, memory versioning, embedding-based retrieval (opt-in) |
| **Beyond** | LLM-judge evaluator mode, learned retrieval ranking, cross-project memory |

## Use Mneme via API

Mneme now includes a minimal API layer so other workflows can call it directly.

### Endpoint

`POST /complete`

### What it does

The endpoint accepts:

* a `question`
* a project memory input, either as:

  * an inline JSON object, or
  * a path to a local JSON file

Mneme then:

1. loads the memory
2. retrieves relevant rules, facts, and examples
3. builds a compact context packet
4. injects that context into the LLM call
5. returns the answer plus a summary of what context was used

### Run locally

```bash
# Install with API extras
pip install -e ".[api]"

uvicorn app.api:app --reload
```

### Request shape

```json
{
  "question": "Should we rebuild from scratch?",
  "memory": "examples/project_memory.json"
}
```

You can also pass memory inline:

```json
{
  "question": "Should we broaden scope in v1?",
  "memory": {
    "meta": {
      "name": "mneme",
      "description": "Portable project memory and evaluation nucleus for AI workflows."
    },
    "items": [
      {
        "id": "rule-001",
        "type": "rule",
        "title": "Extend before rebuild",
        "content": "Prefer extending existing infrastructure over rebuilding from scratch in v1.",
        "tags": ["architecture", "mvp"],
        "priority": "high"
      }
    ],
    "examples": []
  }
}
```

### Example with curl

```bash
curl -X POST http://127.0.0.1:8000/complete \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Should we rebuild from scratch?",
    "memory": "examples/project_memory.json"
  }'
```

### Example response

```json
{
  "answer": "No. Extend the current system rather than rebuilding it. Prior project rules favor reuse, narrow scope, and deterministic iteration in v1.",
  "context_summary": {
    "rules": 3,
    "constraints": 2,
    "facts": 4,
    "examples": 2
  }
}
```

### Context summary fields

* `rules` — hard project rules injected into the call
* `constraints` — anti-patterns, boundaries, and soft preferences
* `facts` — relevant project facts and architecture decisions
* `examples` — prior decision examples included in context

### Why this matters

This is the first API surface for Mneme.

It turns Mneme from a local demo into a callable decision-consistency layer that can sit between an external workflow and an LLM. A pipeline can now send a question plus project memory and get back an answer shaped by prior project decisions rather than generic model behavior.

### Current scope

This API is intentionally minimal:

* no auth
* no database
* no persistence layer
* no multi-project serving

It exists to prove the core Mneme loop in the simplest usable form:
**project memory → retrieval → context injection → answer**

---

## Status

This is the first public module of **Mneme**. It is a narrow, intentional wedge: one capability, demonstrated clearly, with a clean upgrade path.

Mneme is a portable project memory and evaluation nucleus for AI workflows. This repo is where it starts.

## License

MIT
