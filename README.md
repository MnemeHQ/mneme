# Mneme HQ

**Architectural decisions, enforced on every AI call.**

Mneme HQ is the architectural governance layer for AI-assisted development.

<a href="https://www.youtube.com/watch?v=LaJqeJrKkgg" target="_blank">
  <img 
    src="https://i.ytimg.com/vi/LaJqeJrKkgg/maxresdefault.jpg" 
    alt="From ADR to CI: Enforcing Architecture in GitHub Actions" 
    width="100%"
    style="border-radius: 8px;"
  />
</a>

<p align="center">
  ▶ <a href="https://www.youtube.com/watch?v=4Yg43V9amao" target="_blank"><b>Governed Python Agent Demo</b></a>
  &nbsp;·&nbsp;
  <a href="https://mnemehq.com/demo/adr-compiler/" target="_blank">ADR Import Demo →</a>
  &nbsp;·&nbsp;
  <a href="https://mnemehq.com/pilot/" target="_blank"><b>Request a pilot →</b></a>
</p>


> **Current phase: Layer 1 — validation.** Mechanism is frozen at commit [`e73ff7d`](https://github.com/mnemeHQ/mneme/commit/e73ff7d). Local-repo, single-developer, project-scoped governance. Layer 2 (multi-repo, team sync, org policy distribution) is intentionally deferred. See [docs/architecture/current-phase.md](docs/architecture/current-phase.md) and [docs/architecture/layer1-freeze-e73ff7d.md](docs/architecture/layer1-freeze-e73ff7d.md).

---

## Current Status

- **Layer 1 frozen at `e73ff7d`** — retrieval mechanics, enforcement semantics, and benchmark methodology are pinned. No behavioral change without an explicit charter amendment.
- **Benchmark methodology stabilized** — two-layer scoring, deterministic retrieval, structured-fixture path, regression pins. Suite at 7/7 PASS, recall@3 = 1.00, recall@1 = 5/5 = 1.00.
- **Validating with design partners** — real-world drift prevention and design-partner feedback are the open Layer 1 exit criteria.
- **Local-repo governance only** — no multi-developer coordination, no remote policy store, no cross-repo synchronization in Layer 1.
- **Layer 2 intentionally deferred** — team governance, shared policy packs, deeper IDE integrations, CI enforcement evolution, org-wide distribution.

## What Mneme Is

Local-repo, single-developer, project-scoped architectural governance for AI-assisted code generation. Specifically:

- A way to **encode architectural decisions** as structured records in `project_memory.json`.
- A **deterministic retriever** that selects relevant decisions for any given prompt or task.
- A **pre-flight enforcer** that flags violations before the LLM generates output.
- A **reproducible benchmark** that makes every change to retrieval or enforcement visible.

The wedge is intentionally narrow: explicit recorded decisions, deterministically retrieved, enforced before generation.

## What Mneme Is Not

These are not on Mneme's roadmap. Not "later" — *not Mneme*:

- **Generalized agent memory.** Not a vector store, not a conversational memory system.
- **Autonomous planning.** No multi-step agent loops, no tool-use orchestration.
- **Prompt optimization.** Mneme does not rewrite prompts; it blocks ones that violate governance.
- **Long-term conversational memory.** Not a chat history system.
- **Enterprise workflow orchestration.** Not a workflow engine.
- **Deployment governance, runtime observability.** Not an APM, not a release-pipeline policy tool.
- **Code-generation quality scoring.** Mneme does not rate output quality; it checks whether generation violated a recorded decision.
- **Auto-fixing code.** Mneme blocks. The human or model fixes.

## Architectural Principles

The freeze is governed by three load-bearing principles. Every feature is judged against them:

- **Deterministic > clever.** Same memory plus same query produces byte-identical retrieval order on every run. A simpler retriever that gives the same answer twice is preferred to a smarter retriever that does not.
- **Auditable > autonomous.** Every block records which decision matched, which rule triggered, which term in the input fired it. A human can reconstruct any verdict from the artifacts.
- **Prevention before review.** Mneme runs *before* the LLM generates output, not after. The intervention point is the prompt boundary.

Mneme is built around a broader architectural governance model for AI-assisted development. See the [concepts hub](https://mnemehq.com/concepts/) for definitions including governance before generation, verification contracts, architectural drift, and governance infrastructure.

## Benchmark Philosophy

The benchmark is a **regression and integrity instrument**, not a generalization claim. Its job is to make every change to retrieval or enforcement visible and reproducible — so a regression cannot land silently, a PASS cannot be coincidence, and external numbers cannot drift away from what the code does.

- **Canned LLM responses, fixed retrieval, rule-text matching.** No live model calls in the suite. Run-to-run model variance cannot leak into verdicts.
- **Two-layer scoring.** Layer 1 (retrieval) and Layer 2 (enforcement) recorded independently per scenario. The `WEAK_RETRIEVAL` verdict explicitly flags coincidental passes.
- **recall@1 reported, never optimized.** It is the sharpest tuning dial under fixed methodology, deliberately excluded from pass/fail to prevent overfitting to a small suite.
- **K=3 canonical.** The enforcer reads the top-3 retrieved decisions and only those. K is a property of the system, not a benchmark parameter.

Full methodology philosophy: [/docs/benchmark-methodology/](https://mnemehq.com/docs/benchmark-methodology/). Full methodology spec: [/benchmark/](https://mnemehq.com/benchmark/).

## Current Scope

Contributor guidance: changes to `decision_retriever.py`, `enforcer.py`, `benchmark.py`, or any benchmark fixture are charter-level changes and require the freeze doc's amendment procedure. Docs, tooling, integrations, site, and examples proceed normally with `[memory]` prefix discipline for `project_memory.json` edits.

---

## Demo videos

Watch short demos of Mneme running in realistic AI-assisted development workflows:

- [Governed Python Agent Demo](https://www.youtube.com/watch?v=4Yg43V9amao) — the core product loop: violation caught, context injected, agent retries compliant
- [ADR Import Demo](https://www.youtube.com/watch?v=lMkq-RoKeD4) — compile ADRs into an executable governance corpus
- [Architectural Drift Demo](https://www.youtube.com/watch?v=xkXJqSnXBJ8) — drift at AI speed, caught before it compounds
- [GitHub Actions Governance Demo](https://www.youtube.com/watch?v=LaJqeJrKkgg) — enforce architecture in CI from ADR to gate
- [Dependency Policy Demo](https://www.youtube.com/watch?v=pBJSpN8d9FU) — project memory as enforcement policy

For the full demo library, see [mnemehq.com/demo](https://mnemehq.com/demo/) or the [YouTube channel](https://www.youtube.com/@MnemeHQ).

---

## The problem

LLMs start every call from zero. They forget prior architecture choices, reintroduce rejected technologies, and suggest changes that contradict decisions your team already made. This happens whether you are using a direct API completion, an IDE coding assistant, an agent framework, or a managed agent platform.

Mneme helps teams prevent [architectural drift](https://mnemehq.com/concepts/architectural-drift/) by enforcing [governance before generation](https://mnemehq.com/concepts/governance-before-generation/).

Mneme HQ turns those decisions into structured, retrievable constraints that can be injected into LLM calls and checked against generated output.

## What Mneme HQ is

**Mneme HQ** is the architectural governance layer for AI-assisted development.

This repository demonstrates the first core capability: injecting structured architectural decisions into LLM calls so outputs stay consistent with prior engineering decisions.

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

## Works with

- Direct LLM API integrations
- IDE coding assistants (Cursor, Copilot, Cline)
- Agent frameworks (LangChain, CrewAI, AutoGen)
- Managed agent platforms
- Internal prompt pipelines

## How it works

Mneme HQ turns architectural decisions into structured context packets injected into every LLM call.

The pipeline is:

1. **Decision store** — structured architectural decisions: rules, constraints, anti-patterns, decision records
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

**WITHOUT Mneme HQ:**
```
We could consider rebuilding the system with a vector database and embedding
model. This would improve semantic matching and scale better long-term.
Sentence-transformers is a good option for generating embeddings...
```

**WITH Mneme HQ:**
```
Do not rebuild from scratch. The project has an explicit rule to extend current
infrastructure before rebuilding (rule-001). Keyword scoring was chosen
intentionally -- it is deterministic, has no ML dependencies, and is easy to
debug. The team already declined adding sentence-transformers in v1. Extend
the current retriever instead.
```

**Mneme HQ ALIGNMENT:**
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

The demo runs each task twice -- once without governance (baseline) and once with the decision corpus enforced -- so you can see the delta.

## Why not just RAG?

RAG retrieves **information**. Mneme HQ retrieves **decisions**.

* Not retrieval of documents — retrieval of **decisions your project already made**
* Not long context — a **structured context packet** with only what is relevant to the query
* Not autonomy — **consistency enforcement**: the model is told what was decided, not asked to figure it out

| | RAG | Mneme HQ |
|---|---|---|
| Input | Documents, chunks, embeddings | Rules, constraints, decision records |
| Goal | Inform the response | Shape the response |
| Output effect | Model knows more | Model follows your decisions |
| Evaluation | "Did it use the right source?" | "Did it respect the constraint?" |

Mneme HQ is not a search engine for your docs. It is a structured rule system that tells the model what your project has already decided and checks whether it listened.

## Architecture

Mneme HQ uses structured project memory as the retrieval mechanism, but its purpose is governance: enforcing architectural decisions and preventing drift during AI-assisted development.

```
mneme/
  schemas.py              Dataclasses: MemoryItem, Decision, DecisionExample, ContextPacket
  memory_store.py         Load project_memory.json; auto-migrate legacy rule/anti_pattern items
  retriever.py            v1: keyword overlap + tag match + priority weight (unchanged)
  decision_retriever.py   v2: field-weighted scoring over Decision records
  context_builder.py      format_context_packet (v1) + format_decisions/top-N (v2)
  conflict_detector.py    v2: post-response violation scanner
  pipeline.py             v2: MemoryStore -> DecisionRetriever -> inject -> LLM -> detect
  adr_schema.py           v0.4: ADR dataclass, status/priority enums, errors
  adr_parser.py           v0.4: YAML frontmatter parser
  adr_compiler.py         v0.4: validate_corpus, resolve_precedence, compile_adrs
  cursor_generator.py     v0.3: Cursor rules generator
  enforcer.py             v0.3: configurable enforcement modes (strict / warn)
  llm_adapter.py          Thin Anthropic API wrapper with dry-run mode
  evaluator.py            v1: deterministic alignment checker (unchanged)
  cli.py                  v2: add_decision / list_decisions / test_query / check
examples/
  project_memory.json     20 items + 5 examples + 3 native decisions for this repo
  demo_tasks.json         3 decision-oriented tasks for the before/after demo
demo.py                   CLI runner: baseline vs. Mneme-enhanced, with alignment scoring
```

### Decision item types

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

Mneme HQ v0.2 added structured `Decision` records, field-weighted retrieval, top-N
injection, post-response conflict detection, and a CLI, all additive. The v1
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
    --id adr-042 --decision "No GraphQL in v1" \
    --scope api --constraint "REST only" --anti-pattern "introduce graphql"

# Score a query and preview the injected block
mneme test_query --memory examples/project_memory.json \
    --query "should I add postgres?" --top 3
```

---

## v0.4: Architectural compiler

Mneme HQ v0.4 compiles a versioned corpus of ADR markdown files into a
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

## Repo-level enforcement: `.mneme/` and `mneme check`

This repository governs itself with Mneme. The canonical enforcement memory
lives at `.mneme/project_memory.json` and is the source of truth for repo-level
governance. Repo-level instructions for contributors and AI assistants live in
the root `CLAUDE.md`.

`mneme check` is the CLI entry point for running a governance pass over a
diff or a working tree. It supports two modes:

* `--mode warn`: surfaces violations without failing
* `--mode strict`: fails on any violation

```bash
# Run a warn-mode check before opening a PR
mneme check --mode warn
```

The PR workflow runs `mneme check --mode warn` automatically, so contributors
see governance feedback on every pull request without it blocking merges
during the warn-first rollout.

---

## Mneme for Claude Code

Architectural governance for [Claude Code](https://docs.anthropic.com/en/docs/claude-code).
Enforce ADRs and engineering constraints automatically — before drift reaches your repo.

```bash
pip install mneme-hq
python scripts/install_claude_code.py        # project-scoped: writes to ./.claude/
# or: python scripts/install_claude_code.py --user   # writes to ~/.claude/
```

This installs a `PreToolUse` hook so every Edit / Write / MultiEdit is checked
against `.mneme/project_memory.json` in strict mode by default. See
[docs/integrations/claude-code.md](docs/integrations/claude-code.md) for
details, including retrieval behaviour and mode switching.

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

See [docs/integrations/adr-import.md](docs/integrations/adr-import.md)
for the full reference.

---

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
git clone https://github.com/mnemeHQ/mneme
cd mneme

# Core only
pip install -e .
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

# Inspect what Mneme HQ would inject, without calling the LLM
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
    "description": "Enforce architectural decisions on every LLM API call.",
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

| Task | What Mneme HQ catches |
|------|--------------------|
| Rebuild from scratch? | rule-001 (extend over rebuild), dec-001 (embeddings declined) |
| Broaden v1 scope? | anti-002 (no agentic loops), rule-004 (narrow MVP) |
| Mix project + personal memory? | rule-003 (separate project from personal), dec-002 (per-project only) |

## Why this matters

- **Contradiction prevention.** LLM calls are stateless. Every call starts from zero, so models routinely propose changes that contradict decisions your team already made: reintroducing rejected technologies, rebuilding what was meant to be extended, suggesting patterns the project has explicitly ruled out. Mneme HQ injects the relevant prior decisions on every call so the model's output aligns with established architecture instead of drifting away from it.

- **Architectural continuity at AI velocity.** AI-assisted development has increased code output without increasing review capacity. The bottleneck is not generation; it is keeping generated code consistent with the architecture the team agreed on. Mneme HQ enforces that consistency at generation time, before the diff lands in review, which reduces the review burden and keeps architectural drift from compounding.

- **Measurable enforcement, not vibes.** Injecting context is half the problem. The other half is knowing whether it worked. The evaluator checks each response against the decisions that were actually injected and returns a deterministic alignment score. Anti-patterns and constraint violations are flagged explicitly. This turns "did the AI follow our decisions?" from a subjective judgment into something you can track, score, and regress-test.

## Roadmap

See the [Adoption and Enhancement Roadmap](docs/roadmap/2026-04-24-adoption-and-enhancement-roadmap.md).

| Version | Capability |
|---------|-----------|
| **v0.1** ✓ | JSON-backed decision corpus, keyword retrieval, deterministic evaluation, before/after demo |
| **v0.2** ✓ | Decision enforcement layer: structured `Decision`, field-weighted retrieval, conflict detector, CLI |
| **v0.3** ✓ | Configurable enforcement modes (`strict` / `warn`); Cursor rules generator; Claude Code hook + slash commands (v0.3.2) |
| **v0.4** ✓ | Architectural compiler: ADR frontmatter schema, corpus validation, deterministic precedence engine, Decision-bridge integration |
| **v0.5** ✓ | Repo-level governance: `.mneme/` canonical enforcement memory, `mneme check`, GitHub PR workflow integration (warn mode) |
| **Layer 1 freeze** ✓ | v1.1 stabilization complete at `e73ff7d`: deterministic retrieval pinned, two-layer benchmark methodology, structured-fixture path, charter discipline. See [docs/architecture/layer1-freeze-e73ff7d.md](docs/architecture/layer1-freeze-e73ff7d.md). |
| **Layer 1 validation** | Real-world drift prevention, design-partner feedback, governance wedge validation. Open exit criteria. |

### Layer 2 — intentionally deferred

The following are out of scope for Layer 1 and require the Layer 1 exit criteria to be met before they are promoted into the roadmap:

- Multi-project / multi-repo support, cross-project memory, memory versioning across projects.
- Team governance, shared policy packs, org-wide policy distribution.
- Strict-mode CI rollout beyond the current single-repo scope.
- LLM-judge evaluator mode (substitutes deterministic enforcement with a model judge — incompatible with the "deterministic > clever" charter principle in Layer 1).
- Learned retrieval ranking (incompatible with "no auto-learning").
- Deeper IDE integrations (LSP, JetBrains).

These are listed so they cannot be re-derived as "missing." The freeze doc's "Intentionally NOT Solved" section enumerates work that is not on Mneme's roadmap at all.

## Status

Mneme is in **Layer 1 — validation phase**. The mechanism is frozen at commit [`e73ff7d`](https://github.com/mnemeHQ/mneme/commit/e73ff7d): deterministic retrieval, pre-flight enforcement, two-layer benchmark methodology, charter discipline. The freeze artifact is at [docs/architecture/layer1-freeze-e73ff7d.md](docs/architecture/layer1-freeze-e73ff7d.md); the orientation doc is at [docs/architecture/current-phase.md](docs/architecture/current-phase.md).

What remains in Layer 1 is **validation**, not extension. Layer 1 exit criteria are met when the wedge is validated against real repos with design partners; the open criteria are real-world drift prevention, design-partner validation, and governance wedge validation. Layer 2 (multi-repo, team sync, org policy distribution) opens only after exit.

The Mneme positioning is intentional: narrow scope, explicit governance boundaries, reproducible benchmark methodology. Not eval-score inflation. Not a coding-benchmark leaderboard play. Architectural continuity, governance reliability, deterministic enforcement.

## Infrastructure

See [docs/ops/mneme-hq-gcp.md](docs/ops/mneme-hq-gcp.md) for GCP project setup, BigQuery datasets, environment variable conventions, and data export links.

## License

MIT
