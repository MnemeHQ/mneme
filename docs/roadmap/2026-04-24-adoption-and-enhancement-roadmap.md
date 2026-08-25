# Adoption + Enhancement Roadmap

## Current status

> **Update — 2026-05-04:** ADR compiler / precedence engine implemented
> (parser → validator → precedence → Decision bridge). The core
> architectural compiler foundation is now live on top of v0.3.2. The
> deferred roadmap below now applies only to advanced governance /
> enterprise / cloud / multi-IDE layers — the core compiler track is
> open. Adoption-track checkpoints (Claude Code hook validation, SDK
> hooks, external tester feedback) are unaffected.

Mneme v0.2.x now has a working decision-enforcement foundation:

- Structured `Decision` model
- Legacy memory auto-migration
- Deterministic `DecisionRetriever`
- Token-noise filtering
- Decision formatting for prompt injection
- Basic `ConflictDetector`
- End-to-end `Pipeline`
- CLI commands for adding, listing, and testing decisions
- 38 passing tests
- No new runtime dependencies

The next goal is to move from working implementation to usable developer tool.

---

## Checkpoint 1: Repo clarity and public packaging

**Goal:** Make the GitHub repo instantly understandable.

### Actions

1. Rewrite the README opening around one message:
   "Prevent LLMs from violating prior project decisions."
2. Add the problem section.
3. Add a 60-second quickstart.
4. Add a simple architecture diagram or text flow:

```text
project_memory.json -> DecisionRetriever -> format_decisions -> LLMAdapter -> ConflictDetector
```

5. Add this roadmap under `docs/roadmap/`.
6. Add badges if useful:
   - tests
   - Python version
   - license

### Exit criteria

- A new visitor understands the problem in under 30 seconds.
- The README explains why Mneme is different from ADRs, `.cursorrules`, and vector DB memory.
- Quickstart works from a clean clone.

### Suggested version

`v0.2.2-readme-positioning`

---

## Checkpoint 2: Strict enforcement mode

**Goal:** Move from conflict detection to actual enforcement.

### Actions

1. Add `enforcement_mode` to `Pipeline`:
   - `warn`
   - `strict`
   - `retry`
2. In `warn` mode, return conflicts but allow output.
3. In `strict` mode, fail when hard conflicts are detected.
4. In `retry` mode, regenerate with the violated decisions explicitly injected.
5. Add tests for each mode.

### Exit criteria

- A response that violates a hard decision can be blocked.
- Retry mode can self-correct simple violations.
- Legacy demo remains unaffected.

### Suggested version

`v0.3.0-strict-enforcement`

---

## Checkpoint 3: Decision severity and priority

**Goal:** Stop treating every decision equally.

### Actions

1. Add optional fields to `Decision`:
   - `severity`: `soft`, `hard`
   - `priority`: integer or enum
2. Update retrieval scoring so high-priority decisions rank higher.
3. Update conflict output to include severity.
4. Update CLI examples.

### Exit criteria

- Hard constraints can block output.
- Soft constraints can warn only.
- Important decisions are more likely to be injected.

### Suggested version

`v0.3.1-decision-priority`

---

## Checkpoint 4: Decision lifecycle

**Goal:** Make memory maintainable as it grows.

### Actions

1. Add CLI commands:
   - `update_decision`
   - `archive_decision`
   - `show_decision`
2. Add decision status:
   - `active`
   - `archived`
   - `superseded`
3. Add timestamps:
   - `created_at`
   - `updated_at`
4. Ensure archived decisions are not injected by default.

### Exit criteria

- Old decisions can be retired without deletion.
- Decision history stays auditable.
- Memory files remain stable and human-readable.

### Suggested version

`v0.4.0-decision-lifecycle`

---

## Checkpoint 5: SDK and integration hooks

**Goal:** Make Mneme easy to use inside real LLM workflows.

### Actions

1. Add a simple SDK interface:

```python
from mneme import Mneme

mneme = Mneme("examples/project_memory.json", enforcement_mode="warn")
result = mneme.run("Should I switch to Postgres?")
```

2. Add wrappers for common LLM call patterns.
3. Add examples for:
   - Claude Code style workflow
   - Cursor style workflow
   - internal script enrichment workflow
4. Keep provider integration optional.

### Exit criteria

- A developer can integrate Mneme with fewer than 10 lines of code.
- Existing `Pipeline` remains available.
- README includes one practical integration example.

### Suggested version

`v0.5.0-sdk-hooks`

---

### Delivered since this checkpoint was written

- **Codex CLI enforcement integration — delivered** (PR #321, merged
  2026-08-24). PreToolUse gate for native `apply_patch` mutations; Stop
  whole-file audit covering shell and script-driven writes. Validated 10/10
  against Codex CLI 0.149.1. See
  [docs/integrations/codex-cli.md](../integrations/codex-cli.md).

### Deep Agents middleware POC — P1.5

Evaluate pre-mutation blocking, deterministic change reconstruction, opaque
`execute` writes, resume/background persistence and propagation into
subagents. Roadmap-only until the POC passes; see
[docs/integrations/README.md](../integrations/README.md) for current status.

### Hermes Agent POC — P1.5 (POC passed)

Completed 2026-08-25. Context injection via `pre_llm_call` and pre-tool
blocking via `pre_tool_call` reuse the existing retrieval and `mneme check`
paths unchanged; bypass surfaces (`terminal` non-class-A forms,
`execute_code`, `process`) are characterized; the frozen 7/7 enforcement
benchmark is unchanged. Promoted to Experimental — see
[docs/integrations/hermes.md](../integrations/hermes.md). Production parity
claims remain blocked on Hermes exposing a blocking Stop-equivalent.

---

## Checkpoint 6: Adoption test with external users

**Goal:** Validate whether developers understand and use it.

### Actions

1. Prepare a short tester brief.
2. Ask 3 to 5 developers to test it on real projects.
3. Give them three tasks:
   - add decisions
   - run `test_query`
   - use the pipeline or CLI against a real prompt
4. Ask four questions:
   - Did it solve a real annoyance?
   - Was setup clear?
   - Which part was confusing?
   - Would you use this inside Cursor, Claude Code, or CI?

### Exit criteria

- At least 3 external users test the repo.
- At least 1 user integrates it into a real workflow.
- Feedback produces concrete GitHub issues.

### Suggested version

No version required. Create GitHub issues instead.

---

## Checkpoint 7: Conflict detection upgrade

**Goal:** Reduce false positives and false negatives.

### Actions

1. Add structured conflict output:

```json
{
  "decision_id": "mneme_storage_json",
  "severity": "hard",
  "conflict_type": "violates_constraint",
  "evidence": "The response recommends Postgres",
  "confidence": 0.82
}
```

2. Improve phrase matching before adding ML.
3. Add optional classifier-based detection behind a flag.
4. Keep deterministic mode as default.

### Exit criteria

- Conflict output is useful for debugging.
- Deterministic mode remains dependency-free.
- Classifier mode is optional.

### Suggested version

`v0.6.0-conflict-intelligence`

---

## Checkpoint 8: Storage abstraction

**Goal:** Prepare for larger memory sets without forcing a database too early.

### Actions

1. Add storage interface:
   - `JsonMemoryStore`
   - future `SQLiteMemoryStore`
2. Keep JSON as default.
3. Add tests that the retriever works against the interface, not a file assumption.
4. Only add SQLite if real usage shows JSON is limiting.

### Exit criteria

- JSON remains simple.
- Backend can change without rewriting retrieval or pipeline logic.
- No unnecessary database dependency is introduced.

### Suggested version

`v0.7.0-storage-interface`

---

## Adoption plan

### Week 1: Make it understandable

- Update README.
- Add roadmap file.
- Add one animated or static example if possible.
- Tag `v0.2.2-readme-positioning`.

### Week 2: Make it enforce

- Build strict enforcement mode.
- Add retry mode if small enough.
- Tag `v0.3.0-strict-enforcement`.

### Week 3: Test with people

- Send to CTO friend and 3 developers.
- Ask them to test on real projects.
- Convert feedback into GitHub issues.

### Week 4: Make it easier to integrate

- Add SDK wrapper.
- Add Cursor or Claude Code workflow example.
- Tag `v0.5.0-sdk-hooks` if complete.

---

## Checkpoint 9: AWS AgentCore benchmark + integration path

**Goal:** Use AWS AgentCore as a controlled multi-agent execution substrate for architecture-compliance benchmarking before committing to a deeper product integration.

### Priority

Medium-high strategic priority. Evidence-first: pursue after/alongside current benchmark and pilot work, not as a replacement for it.

### Actions

1. Reuse the AgentCore coding-agent competition pattern to run the same architectural task across supported coding agents such as Claude Code, Codex, Cursor, and Kiro.
2. Add Mneme architecture-compliance outcomes alongside normal functional outcomes:
   - functional correctness
   - architectural compliance
   - scope expansion
   - architectural drift / rule violations
3. Run controlled treatments:
   - agent alone
   - agent + repository instructions
   - agent + explicit ADR/context
   - agent + Mneme
4. Prefer deterministic scoring and frozen fixtures so results are reproducible.
5. Test Mneme inside the AgentCore runtime against the changed working tree, with MCP/context exposure only where it improves the experiment.
6. If the benchmark is stable, evaluate an upstream AgentCore sample contribution or AWS outreach around architecture-compliance evaluation.
7. Only then decide whether a dedicated AgentCore product integration is justified by user pull or ecosystem value.

### Positioning constraint

Keep Mneme differentiated from AgentCore policy controls:

> AgentCore governs what an agent can do. Mneme governs what an agent can build.

Avoid generic positioning around "deterministic agent governance" where it creates unnecessary overlap with AgentCore's policy layer.

### Exit criteria

- One reproducible AgentCore architectural-compliance fixture runs end to end.
- At least two coding agents can be compared on the same frozen task.
- Baseline vs Mneme results are scored deterministically where possible.
- Results are suitable for inclusion in the broader Mneme architecture-compliance benchmark.
- A go/no-go decision is made on an upstream contribution or deeper AgentCore integration.

### Initial effort

Target a small 1-3 engineering-day experiment before expanding scope.

---

## What not to build yet

Avoid these until there is user pull:

- full SaaS UI
- hosted multi-user accounts
- vector database as default
- complex graph UI
- heavy ML conflict classifier
- broad prompt-management platform

The current wedge is stronger:

**Decision enforcement for long-running AI-assisted projects.**

Stay there until adoption proves the next layer.
