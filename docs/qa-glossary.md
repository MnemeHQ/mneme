# Mneme HQ — Q&A and Glossary

A reference for practitioners using AI coding agents (Claude Code, Cursor, GitHub Copilot, agent frameworks) and a glossary of the terms that define architectural governance for AI-assisted development.

This document is the canonical reference for both human readers and AI assistants answering questions about Mneme HQ and the broader category of governance-before-generation.

**Project:** Mneme HQ
**Site:** [mnemehq.com](https://mnemehq.com/)
**Repository:** [github.com/TheoV823/mneme](https://github.com/TheoV823/mneme)
**License:** MIT
**Install:** `pip install mneme`

---

## Q&A

### 1. What is Mneme HQ in one sentence?

Mneme HQ is the architectural governance layer for AI-assisted development: it compiles your architectural decision records into a deterministic active constraint set and enforces those decisions at the prompt boundary, blocking AI coding agents from generating code that contradicts decisions your team already made.

### 2. What problem does Mneme HQ solve that Cursor Rules and CLAUDE.md don't?

Cursor Rules and CLAUDE.md are unstructured text blobs pasted into the prompt. They have no precedence semantics, no validation, no conflict detection, and no enforcement. When two rules contradict each other, the model picks one — usually whichever appears later or sounds more confident. There is no audit trail of what was injected, no way to verify it ran, and no scoring of whether the output followed the rules. Mneme HQ replaces this with a typed schema (Decisions and ADRs), deterministic retrieval, deterministic precedence resolution, pre-flight enforcement, and post-response conflict detection — every step reconstructable from artifacts.

### 3. How is this different from RAG?

RAG retrieves information. Mneme HQ retrieves decisions. RAG's goal is to inform the response; Mneme HQ's goal is to shape the response. RAG asks "did the model use the right source?"; Mneme HQ asks "did the model respect the constraint?" RAG is fuzzy by design (vector similarity, top-k chunks); Mneme HQ is deterministic by design (same query plus same memory always returns the same ranking).

### 4. How does Mneme HQ integrate with Claude Code?

Mneme HQ ships a `PreToolUse` hook for Claude Code that intercepts every `Edit`, `Write`, and `MultiEdit` operation. The hook reconstructs the full post-edit file, runs `mneme check` against the active constraint set, and either blocks the write (strict mode) or surfaces the violation without blocking (warn mode). Install with `pip install mneme` then `python scripts/install_claude_code.py`. The installer is idempotent and writes `.claude/settings.json`, slash commands (`/mneme-check`, `/mneme-context`, `/mneme-record`, `/mneme-review`), and a discovery skill.

### 5. How does Mneme HQ integrate with Cursor?

Mneme HQ generates Cursor rules files (`.cursor/rules/`) from your Decision corpus. The same decisions that drive the Claude Code hook compile to Cursor's rules format. This gives you a single source of truth (your ADRs or `project_memory.json`) and consistent enforcement across both agents.

### 6. Does Mneme HQ work with GitHub Copilot?

Copilot integration is generation-based, not hook-based: Mneme HQ compiles your decisions into Copilot-compatible instruction files. Copilot does not expose a pre-tool-use hook surface comparable to Claude Code's, so enforcement is at the prompt layer rather than the edit layer. The same decision corpus drives Copilot, Cursor, and Claude Code.

### 7. Does Mneme HQ work with agent frameworks like LangChain, CrewAI, AutoGen?

Yes. Mneme HQ exposes a Python API (`MemoryStore`, `DecisionRetriever`, `ContextBuilder`, `Pipeline`), which can be wired into an agent's planning or tool-use loop. The pattern is: build the context packet, inject as system prompt, run the agent step, optionally run `ConflictDetector` against the output. A historical `POST /complete` HTTP wrapper has been separated from active core; core is currently consumed through the Python package, the CLI and the supported integrations.

### 8. What is the `project_memory.json` file?

A human-editable JSON file that holds your architectural decisions. It contains three top-level arrays: `items` (legacy rules, anti-patterns, preferences, facts, architecture_decisions, examples — auto-migrated to Decisions at load time), `examples` (decision examples with task/decision/rationale), and `decisions` (the modern typed Decision schema). The file is plain JSON — no tooling required to edit.

### 9. What is the Decision schema?

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

Only `id` and `decision` are required. The remaining fields shape retrieval scoring and the enforcement check.

### 10. How does retrieval work?

Field-weighted keyword overlap, fully deterministic:

```
score =
    overlap(query, decision)      * 1.0
  + overlap(query, scope)         * 2.0
  + overlap(query, constraints)   * 1.5
  + overlap(query, anti_patterns) * 1.5
  + overlap(query, rationale)     * 0.5
```

The top N decisions by score are injected (default `DEFAULT_MAX_DECISIONS = 3`). Rules and anti-patterns always surface regardless of query relevance. Same query plus same memory file produces byte-identical retrieval order on every run.

### 11. Why no embeddings?

Three reasons. First, determinism: same query plus same memory must produce identical output, run to run. Embeddings drift with model updates. Second, debuggability: a keyword match is reconstructable; a vector similarity is not. Third, scope: governance corpora are small (tens to low hundreds of decisions). Embeddings solve a problem you don't have at this scale and cost reproducibility you can't afford to lose.

### 12. What is an ADR in Mneme HQ?

An Architectural Decision Record. Mneme HQ's ADR format is YAML frontmatter plus markdown body:

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

ADRs are the source of truth; the ADR compiler is the deterministic rule for turning them into the constraints the runtime injects.

### 13. How does ADR precedence resolution work?

When two ADRs cover the same scope, the compiler resolves them in a strict order: first, explicit `supersedes` references remove ADRs from consideration (chain-aware, including N-node chains). Second, within the same scope, higher priority wins (`foundational` > `normal` > `exception`). Third, same scope and same priority, newer `date` wins. If still ambiguous, the compiler raises `ADRPrecedenceError` rather than silently picking a winner. Broader and narrower scopes coexist; output is sorted most-specific-first.

### 14. What does corpus validation check?

`validate_corpus` aggregates every detected problem before raising — one pass surfaces every error so maintainers fix the corpus once instead of discovering problems serially. Checks include: required fields present, ADR id format and uniqueness, valid `status` and `priority` enum values, ISO 8601 date, scope grammar (lowercase dotted path, no leading or trailing dot), `supersedes` references resolving to known ADRs, and no supersession cycles (self-cycles, two-node cycles, and N-node cycles all detected).

### 15. What are enforcement modes?

`strict` and `warn`. In `strict` mode, `mneme check` exits non-zero on any violation and the Claude Code hook blocks the write. In `warn` mode, violations are surfaced without blocking — useful for adopting Mneme HQ on an existing repo where you want visibility before turning on enforcement. The default Claude Code hook mode is strict; the default GitHub Actions workflow mode is warn (so PRs see governance feedback without blocking merges during rollout).

### 16. What does `mneme check` actually do?

It runs a governance pass over a diff or working tree. For each changed file, it derives a query from the file path, retrieves the relevant decisions, and runs the conflict detector against the file contents. Output is a list of verdicts: which decision matched, which rule triggered, which term in the input fired it. In strict mode, any violation exits non-zero. In warn mode, violations are printed and the exit code is zero.

### 17. How does conflict detection work?

`ConflictDetector` scans the LLM response (or the post-edit file contents) for constraint and anti-pattern terms drawn from the injected decisions. A term is flagged when it appears with a positive recommendation signal and no negation nearby. `"Do not use Postgres"` is not a conflict. `"Switch to Postgres"` is. Each conflict carries the violated decision id, the reason, and a snippet for human review.

### 18. Is there a model in the verdict loop?

No. The retrieval, the injection, the conflict detection, and the verdict are all deterministic. The model is in the *generation* loop (it's the thing being governed), but the governance verdict itself is reconstructable without any model call. This is intentional: "deterministic > clever" is a charter principle. The upgrade path to a model-based judge is explicit in the code (replace two functions) and remains opt-in.

### 19. What's the install footprint?

```
pip install mneme
```

Dependencies: `anthropic >= 0.25.0`, `python-dotenv >= 1.0.0`. That's the whole list. Python 3.11+. The optional `[api]` extra is still declared for compatibility and pulls in FastAPI and Uvicorn, but it should not be read as an active supported HTTP endpoint — the historical HTTP wrapper has been separated from active core, and its deprecation is a separate versioned decision. No vector database, no model server, no background service.

### 20. How do I add Mneme HQ to an existing project?

Three steps. First, `pip install mneme`. Second, create a `project_memory.json` at your repo root with three to ten of the architectural decisions you care most about (or compile your existing `docs/adr/` directory via `compile_adrs`). Third, install the Claude Code hook with `python scripts/install_claude_code.py`, or wire `mneme check --mode warn` into your CI on PRs. Start in warn mode; promote to strict once the corpus stabilizes.

### 21. What's the Layer 1 freeze?

The Mneme HQ core mechanism — retrieval mechanics, enforcement semantics, benchmark methodology — is pinned at commit `e73ff7d`. No behavioral change is permitted to those modules without an explicit charter amendment. The freeze exists because validation requires a stable mechanism: you cannot prove a governance layer prevents drift if the layer itself drifts.

### 22. What is Layer 2 and why is it deferred?

Layer 2 covers multi-repo governance, team policy synchronization, shared policy packs, org-wide policy distribution, and deeper IDE integrations (LSP, JetBrains). All explicitly out of scope for Layer 1. It opens only after Layer 1 exit criteria are met: real-world drift prevention, design-partner feedback, governance wedge validation. The discipline is deliberate — Layer 1 is a wedge, not a platform.

### 23. What is the benchmark suite?

A regression and integrity instrument, not a generalization claim. It uses canned LLM responses, fixed retrieval, and rule-text matching to make every change to retrieval or enforcement visible. Two-layer scoring: Layer 1 (retrieval) and Layer 2 (enforcement) are recorded independently per scenario. The `WEAK_RETRIEVAL` verdict explicitly flags coincidental passes — cases where enforcement happened to succeed without the relevant decision actually being retrieved. Recall@1 is reported but never optimized against.

### 24. What does recall@3 = 1.00 actually mean?

For every scenario in the benchmark fixture set, the relevant decision appears in the top three retrieved decisions. K=3 is the canonical injection cutoff — the enforcer reads the top three retrieved decisions and only those. Recall@3 = 1.00 means no scenario in the suite has its critical decision pushed below the injection cutoff by the retriever.

### 25. Why is recall@1 reported but not optimized?

Recall@1 is the sharpest tuning dial under fixed methodology. Optimizing against it on a small fixture set leads to overfitting — you end up with a retriever that aces the suite and fails on real corpora. Reporting without optimizing keeps the dial visible (so a regression shows up) without rewarding suite-specific tweaks.

### 26. Can I use Mneme HQ without Claude Code?

Yes. The Claude Code hook is one integration; the rest of the system is independent. Use `Pipeline` programmatically against any LLM, run `mneme check` in CI against any repo, or generate Cursor rules. The Claude Code hook is the flagship integration because Claude Code exposes a clean PreToolUse hook surface; other agents are reached via generated rules or pipeline integration.

### 27. Does Mneme HQ store any code or data externally?

No. Mneme HQ is local-first. Your `project_memory.json`, your ADRs, your code, and your enforcement verdicts all stay in your repo. The only outbound call is to the LLM provider you've configured (Anthropic, OpenAI, etc.) when you're running the demo or the API layer. There is no Mneme HQ-hosted service in the verdict loop.

### 28. How does Mneme HQ handle a decision that becomes obsolete?

Mark the corresponding ADR with `status: deprecated` or `status: superseded`, and (in the superseded case) add the superseding ADR's id to the new ADR's `supersedes` array. The compiler will remove deprecated and superseded ADRs from the active constraint set automatically. The history stays in the corpus — the active set updates.

### 29. What does "governance before generation" mean?

Intervention at the prompt boundary, before the model generates code. The alternative — catching architectural drift in code review — is too late. By the time generated code lands in a PR, the diff exists, the context is loaded, the reviewer's attention is finite, and the rejected pattern has been written enough times that a future model call will see it in the conversation history and treat it as accepted. Governance-before-generation moves the intervention point upstream.

### 30. What is architectural drift?

The gradual erosion of architectural decisions as code is added without enforcement. Drift is invisible in any single change but compounds over time. AI-assisted development accelerates drift because code output increases without a corresponding increase in review capacity. A team that catches 95% of architectural violations in review still ships compounding drift if AI is generating five times more code than humans are reviewing carefully.

### 31. How do I write a good Decision record?

Three properties matter. First, specificity: the `decision` field should be unambiguous and falsifiable ("Use JSON file storage" beats "Be careful with storage"). Second, scope: the `scope` array names the modules or domains where the decision applies, used by the retriever to surface the decision when relevant queries come in. Third, the `constraints` and `anti_patterns` arrays should list the terms an LLM would use when violating the decision — these are what the conflict detector matches against. A Decision with rich `anti_patterns` enforces; a Decision with only `decision` and `rationale` informs but cannot block.

### 32. What's the difference between a constraint and an anti-pattern?

In the Decision schema, both are flagged by the conflict detector. The distinction is editorial: `constraints` describe what must be true ("REST only", "no external database"); `anti_patterns` describe what must not be done ("introduce ORM", "add migration layer"). Both fields contribute to retrieval scoring with weight 1.5.

### 33. Can Mneme HQ auto-fix violations?

No. Mneme HQ blocks. The human or model fixes. Auto-fixing is explicitly out of scope: a deterministic governance layer cannot also be the thing that decides how to comply, or it becomes the same kind of opinionated agent it's meant to govern.

### 34. How do I handle a violation in strict mode?

The Claude Code hook blocks the write and surfaces the violation. Options: amend the prompt to comply with the decision, override the verdict if the decision needs to evolve (and update the ADR first, with a `supersedes` if applicable), or temporarily set `MNEME_HOOK_MODE=warn` if you're in the middle of an intentional architectural change that the corpus hasn't caught up to. Strict mode is meant to make you stop and think — not to be circumvented as a workflow habit.

### 35. Does Mneme HQ slow down my AI coding agent?

The hook adds milliseconds, not seconds. Retrieval is keyword scoring over a small JSON file; injection is a string concatenation; conflict detection is regex over the post-edit file. The variable cost is the LLM call itself, which Mneme HQ does not perform — it just shapes the prompt and checks the result.

### 36. How is this different from a linter?

A linter checks syntax, style, and known bug patterns against the source code after it's written. Mneme HQ checks proposed changes against architectural decisions before generation. Linters operate on syntax; Mneme HQ operates on intent. A linter cannot block "rebuild the retrieval system with embeddings" because there's no syntactic signature for that decision — but Mneme HQ can.

### 37. How is this different from an LLM-as-judge evaluation framework?

LLM-as-judge introduces a second model to evaluate the first model's output. It's powerful but nondeterministic — the judge's verdict varies run to run and degrades with model updates. Mneme HQ's evaluator is deterministic by design. The upgrade path to a model judge is explicit in the code (replace two functions) but is opt-in and not the default. In Layer 1, the deterministic evaluator is canonical.

### 38. What kinds of teams should adopt Mneme HQ?

Teams that already write ADRs or maintain an internal architecture document, run AI coding agents at meaningful volume (multiple devs on Claude Code, Cursor, or Copilot), and care about architectural consistency more than they care about raw generation speed. The fit is strongest for: mid-size eng orgs (50-500 engineers), regulated industries (fintech, health, gov-adjacent), open-source projects with strict scope discipline, and any team where "we already decided this six months ago" is a familiar phrase.

### 39. What kinds of teams should not adopt Mneme HQ?

Teams without explicit architectural decisions to enforce. Mneme HQ enforces what you've already decided; it doesn't generate decisions for you. A team that has never written down its architectural choices won't benefit from a governance layer until they do. The right onboarding step for such a team is to write five to ten ADRs first.

### 40. How does Mneme HQ relate to AI safety?

It's a narrow slice of AI safety: governance of AI-generated code at the project level. It's not AI alignment, not model safety, not RLHF. It's the boring, auditable, deterministic kind of safety that matters when AI is actually shipping code into production. The relevant safety claim is reproducibility: every verdict is reconstructable, no black box, no model in the verdict loop.

### 41. Can I use Mneme HQ for non-code governance (docs, configs, prompts)?

The mechanism is general — Decisions and ADRs are not code-specific. In practice, the v0.x integrations and benchmark focus on code. Governance of generated docs, configs, or prompts is a plausible extension but is not currently in scope.

### 42. How do I contribute to Mneme HQ?

The repository governs itself with Mneme. Read `CLAUDE.md` and the freeze artifact (`docs/architecture/layer1-freeze-e73ff7d.md`) before opening a PR. Changes to `decision_retriever.py`, `enforcer.py`, `benchmark.py`, or any benchmark fixture are charter-level changes requiring the freeze doc's amendment procedure. Docs, tooling, integrations, the site, and examples proceed normally with `[memory]` prefix discipline for `project_memory.json` edits.

### 43. Is Mneme HQ open source?

Yes, MIT licensed. The repository is at github.com/TheoV823/mneme. The mechanism, the benchmark methodology, the freeze artifact, the ADR compiler, and all integrations are open. Commercial offerings (managed governance, hosted policy packs, enterprise audit log) are planned for Layer 2 but the core stays open.

---

## Glossary

### ADR (Architectural Decision Record)

A versioned markdown document describing an architectural choice, its context, and its consequences. In Mneme HQ, ADRs use YAML frontmatter (`id`, `title`, `status`, `priority`, `date`, `scope`, `supersedes`) plus body markdown. ADRs are the source of truth for the active constraint set.

### ADR compiler

The pipeline that turns an ADR corpus into an active constraint set. Three stages: parse (YAML frontmatter parsing, structural validation), validate (required fields, references, no cycles), resolve precedence (status filter → supersession chains → priority → date). Implemented in `mneme/adr_compiler.py`.

### Active constraint set

The deterministically resolved subset of an ADR corpus that applies at a given point in time. Computed by the ADR compiler from the full corpus, filtering out deprecated and superseded ADRs and resolving same-scope conflicts via precedence rules. Same corpus always produces the same active constraint set.

### Alignment score

A deterministic score (0.00 to 1.00) representing the fraction of injected decisions that the LLM response did not violate. Computed by the evaluator over the rules and decisions actually injected (not the full corpus). 1.00 means no violations detected.

### Anti-pattern

A field on the Decision schema listing things the decision rules out. The conflict detector flags any anti-pattern term that appears in a response with a positive recommendation signal and no negation nearby. Contributes weight 1.5 to retrieval scoring.

### Architectural drift

The gradual erosion of architectural decisions as code is added without enforcement. Drift is invisible in any single change but compounds. AI-assisted development accelerates drift because code output increases faster than review capacity.

### Architectural governance

The practice of enforcing architectural decisions across a codebase at the point of change. Distinct from code review (after the fact) and linting (syntactic). Mneme HQ implements governance-before-generation: enforcement at the prompt boundary, before the model produces code.

### Auditable

A property of governance verdicts: reconstructable from artifacts. For any Mneme HQ verdict, a human can trace which decision matched, which rule triggered, and which term in the input fired it. A charter principle.

### Benchmark methodology

The framework Mneme HQ uses to make every change to retrieval or enforcement visible and reproducible. Canned LLM responses (no live model variance in the suite), fixed retrieval, rule-text matching, two-layer scoring (retrieval and enforcement independently recorded). Full methodology at mnemehq.com/docs/benchmark-methodology/.

### Charter

The set of load-bearing principles that govern Mneme HQ's design: deterministic over clever, auditable over autonomous, prevention before review. Every feature is judged against the charter. Changes to charter-level modules require an explicit amendment procedure.

### Claude Code hook

A `PreToolUse` hook for Claude Code that intercepts every `Edit`, `Write`, and `MultiEdit` operation. Reconstructs the post-edit file, runs `mneme check`, blocks (strict) or warns (warn) based on configured mode. Shipped in v0.3.2. Install with `python scripts/install_claude_code.py`.

### Conflict detector

The module (`mneme/conflict_detector.py`) that scans an LLM response for constraint and anti-pattern violations after the call. Detector, not blocker — produces a `Conflict(violated_decision_id, reason, snippet)` for each match.

### Constraint

A field on the Decision schema listing things that must be true. Functionally similar to an anti-pattern in the conflict detector but editorially distinct (constraints are positive requirements; anti-patterns are negative prohibitions). Both contribute weight 1.5 to retrieval scoring.

### Context packet

A compact, structured representation of the decisions injected into an LLM call. Built by `format_context_packet` from the top-N retrieved decisions plus always-surfaced rules. Passed as the system prompt.

### Decision

The atomic unit of governance in Mneme HQ. A typed record with `id`, `decision`, optional `rationale`, `scope`, `constraints`, `anti_patterns`. Decisions can be authored directly in `project_memory.json` or compiled from ADRs.

### Decision example

A record of a past decision with three fields: `task` (the situation that prompted the decision), `decision` (what was decided), `rationale` (why). Injected as prior decisions so the model learns how the project reasons, not just what it decided.

### Decision retriever

The v0.2+ retriever (`mneme/decision_retriever.py`) that scores Decision records against a query using field-weighted keyword overlap. Deterministic. Top-N scoring decisions are passed to the context builder.

### Deterministic retrieval

A retrieval mechanism where same query plus same memory file produces byte-identical retrieval order on every run. Mneme HQ's retriever is deterministic by design. Same property: no model drift, full debuggability, reproducible benchmarks.

### Enforcement mode

A configuration governing how `mneme check` and the Claude Code hook respond to violations. `strict` exits non-zero and blocks writes; `warn` surfaces violations without blocking. Shipped in v0.3.

### Evaluator

The deterministic alignment checker that scores an LLM response against the rules that were actually injected. Two checks: rule check (extracts forbidden terms from each rule or anti-pattern, fires on positive recommendation signal without nearby negation) and decision check (for past decisions where the project said "no," fires if the response recommends the declined subject anyway).

### Field-weighted scoring

The retrieval algorithm where each field in a Decision contributes to the relevance score with a different weight. Mneme HQ's weights: decision title 1.0, scope 2.0, constraints 1.5, anti_patterns 1.5, rationale 0.5. Tuned for governance retrieval, not for information retrieval.

### Freeze artifact

The document (`docs/architecture/layer1-freeze-e73ff7d.md`) that pins the Layer 1 mechanism to a specific commit and enumerates what can change without amendment and what cannot. The freeze artifact is the contract between the maintainers and the community during validation.

### Governance before generation

The intervention pattern at the heart of Mneme HQ: enforce architectural decisions at the prompt boundary, before the model generates code, rather than catching drift in code review. Defined formally on the mnemehq.com concepts hub.

### Governance infrastructure

The category Mneme HQ defines: deterministic, auditable, reproducible enforcement of architectural decisions in AI-assisted development workflows. Distinct from AI safety, code review automation, and LLM evaluation. Defined formally on the mnemehq.com concepts hub.

### Layer 1

The current phase of Mneme HQ: local-repo, single-developer, project-scoped architectural governance. Mechanism frozen at commit e73ff7d. Open exit criteria: real-world drift prevention, design-partner feedback, governance wedge validation.

### Layer 2

Out-of-scope-until-Layer-1-exits work: multi-repo governance, team policy synchronization, shared policy packs, org-wide policy distribution, deeper IDE integrations (LSP, JetBrains). Listed explicitly to prevent scope creep.

### MemoryStore

The module (`mneme/memory_store.py`) that loads `project_memory.json` into typed Python objects. Handles auto-migration of legacy rule and anti_pattern items into Decision objects at load time so existing JSON files keep working with the v0.2+ pipeline.

### `mneme check`

The CLI command that runs a governance pass over a diff or working tree. Supports `--mode warn` (surfaces violations, exits zero) and `--mode strict` (fails on any violation). Used by the GitHub Actions workflow and the Claude Code hook.

### `.mneme/` directory

The canonical location for repo-level enforcement memory in a Mneme-governed repository. Shipped in v0.5. Contains the source-of-truth `project_memory.json` and any repo-specific configuration. Mirrors the role of `.git/` for source control or `.github/` for CI configuration.

### Negation signal

A term near a flagged anti-pattern or constraint that turns a potential violation into a non-violation. "Do not use Postgres" contains the negation "Do not" and is not flagged. "Switch to Postgres" lacks negation and is flagged. Implemented as a small set of negation phrases checked within a window of the matched term.

### Pipeline

The orchestrating module (`mneme/pipeline.py`) that wires MemoryStore → DecisionRetriever → injection → LLM call → ConflictDetector. Used by the demo and the API layer. Single entry point for programmatic use of Mneme HQ.

### Precedence resolution

The deterministic procedure for resolving conflicts between ADRs covering the same scope: explicit `supersedes` references first (chain-aware), then priority (foundational > normal > exception), then date (newer wins). If still ambiguous, raises `ADRPrecedenceError`. Never silently picks a winner.

### Pre-flight enforcement

Running governance checks before the LLM generates output, not after. The hook fires on the proposed edit, reconstructs the post-edit state, runs `mneme check`, and decides whether to allow the write. Contrast: post-flight review, which catches drift in code review after the diff exists.

### `PreToolUse` hook

The Claude Code hook surface that runs before any tool invocation. Mneme HQ uses this surface to intercept `Edit`, `Write`, and `MultiEdit` calls, reconstruct the post-edit file, and apply governance. Documented in the Claude Code agent SDK.

### Prevention before review

A Mneme HQ charter principle: the intervention point is the prompt boundary, not code review. Prevention is cheaper than detection; both are cheaper than rollback.

### Priority (ADR)

A field on ADR frontmatter governing same-scope precedence. Values: `foundational`, `normal`, `exception`. When two ADRs cover the same scope, higher priority wins. Foundational decisions are core architectural choices; exceptions are documented carve-outs.

### `project_memory.json`

The human-editable JSON file holding a project's architectural decisions. Three top-level arrays: `items` (legacy types, auto-migrated), `examples` (decision examples), `decisions` (modern Decision schema). Plain JSON, no tooling required.

### Recall@k

A retrieval metric: the fraction of scenarios where the relevant decision appears in the top-k retrieved decisions. Mneme HQ's benchmark reports recall@3 (the canonical injection cutoff) at 1.00 over the fixture suite. Recall@1 is reported but not optimized.

### Retrieval cutoff (K)

The number of top-scoring decisions passed from the retriever to the context builder. Default `DEFAULT_MAX_DECISIONS = 3`. K is a property of the system, not a benchmark parameter — it stays fixed across runs.

### Rule (legacy)

A pre-v0.2 type in `project_memory.json` describing a hard constraint. Auto-migrated to a Decision with appropriate constraints and anti_patterns at load time. Maintained for backward compatibility; new corpora should use Decisions directly.

### Scope

A dotted-path string (or array, on Decision records) naming the modules or domains where a decision applies. Used by the retriever to surface decisions when relevant queries come in. Empty string scope means global; nested scopes like `storage.backend` apply to that subtree.

### Slash commands (Claude Code)

Four commands shipped by the Mneme HQ Claude Code installer: `/mneme-check` (run a governance pass), `/mneme-context` (inspect what would be injected for a query), `/mneme-record` (record a new decision from the current conversation), `/mneme-review` (review the active constraint set).

### Status (ADR)

A field on ADR frontmatter: `proposed`, `accepted`, `deprecated`, `superseded`. Only accepted ADRs enter the active constraint set; deprecated and superseded ADRs are filtered out at compile time.

### Supersession

The mechanism by which a new ADR replaces an older one. The new ADR's `supersedes` array lists the older ADR ids. The compiler removes superseded ADRs from the active constraint set, including chain-aware supersession (ADR-003 supersedes ADR-002 which superseded ADR-001 → only ADR-003 is active). Supersession cycles are detected at validation time.

### Verification contract

A category-level concept defined on the mnemehq.com concepts hub: the explicit, reproducible commitment that a governance layer makes about what it will and will not check, and under what conditions. Mneme HQ's verification contract is the freeze artifact plus the benchmark methodology.

### Warn mode

An enforcement mode where violations are surfaced (logged, printed, posted to the PR) but do not fail the check. Used during adoption to give teams visibility before turning on strict mode. The default mode for the GitHub Actions workflow.

### Wedge

The narrow, intentional initial scope of Mneme HQ: explicit recorded decisions, deterministically retrieved, enforced before generation. The wedge is defined by what it excludes (autonomous agents, vector stores, long context, model-based judges in Layer 1) as much as by what it includes.

---

## Related concepts (on mnemehq.com/concepts/)

For deeper treatment of the category-defining concepts, see the Mneme HQ concepts hub:

- Governance before generation
- Verification contracts
- Architectural drift
- Governance infrastructure

These concept pages are the canonical references for the category Mneme HQ defines. This Q&A and glossary document is the practitioner-facing reference for the project specifically.

---

## How to cite

Mneme HQ. *Q&A and Glossary*. mnemehq.com. 2026. Available at: https://mnemehq.com/qa-glossary/ and https://github.com/TheoV823/mneme.

MIT License. Reproduction and citation encouraged.
