# Mneme HQ — Q&A and Glossary

A reference for practitioners using AI coding agents (Claude Code, Cursor, GitHub Copilot, agent frameworks), with a glossary of the terms Mneme HQ uses.

This file is the source for [mnemehq.com/qa-glossary/](https://mnemehq.com/qa-glossary/). Capability statements here must agree with the code, the CLI help and the integration docs. Correct them here first, then on the site.

**Project:** Mneme HQ  
**Site:** [mnemehq.com](https://mnemehq.com/)  
**Repository:** [github.com/MnemeHQ/mneme](https://github.com/MnemeHQ/mneme)  
**License:** MIT  
**Install:** `pipx install "mneme-hq>=0.9.2"`  
**Last updated:** 2026-10-02

---

## Q&A

### What is Mneme HQ?

#### 1. What is Mneme HQ in one sentence?

Mneme HQ is the decision and control layer for agentic software development, starting with architecture: it compiles your architectural decision records into a deterministic active constraint set, supplies those decisions to AI coding agents as context, and checks each proposed change against them before it is written.

#### 2. What's the install footprint?

```
pipx install "mneme-hq>=0.9.2"
```

Three runtime dependencies: `anthropic >= 0.25.0`, `python-dotenv >= 1.0.0` and `PyYAML >= 6.0`. Python 3.11 or later. No vector database, no model server, no background service. Optional extras add the MCP server (`mcp`) and the LangChain and LangGraph integration (`langchain`). The `[api]` extra is still declared for compatibility and pulls in FastAPI and Uvicorn, but the historical HTTP wrapper has been separated from the active core, so do not read it as a supported endpoint.

#### 3. How do I add Mneme HQ to an existing project?

Three steps. First, install the CLI with `pipx install "mneme-hq>=0.9.2"`. Second, create the decision corpus: `mneme init` scaffolds an empty `.mneme/project_memory.json`. Add the three to ten architectural decisions you care most about, or import an existing ADR directory:

```
mneme adr import docs/adr \
  --memory .mneme/project_memory.json \
  --apply
```

Without `--apply` the import is a preview and writes nothing. Third, turn on enforcement. In Claude Code, load the plugin from a Mneme checkout with `claude --plugin-dir ./integrations/claude-code-plugin`. In CI, run the check on each changed file:

```
mneme check \
  --memory .mneme/project_memory.json \
  --input src/storage/store.py \
  --query "storage layer" \
  --mode warn
```

Use `--mode warn` while the corpus settles, then drop the flag, because strict is the default. The [GitHub Actions integration](https://mnemehq.com/integrations/github-actions/) has a reference workflow.

#### 4. Does Mneme HQ store any code or data externally?

No. Mneme HQ is local-first. Your `.mneme/project_memory.json`, your ADRs, your code and your enforcement verdicts stay in your repository. `mneme check` and the Claude Code hook reach a verdict without calling a model or any Mneme HQ-hosted service. The one outbound model call in the package is the built-in LLM adapter, which uses Anthropic's API and runs only when you use the demo or call `Pipeline` yourself.

#### 5. What does "governance before generation" mean?

It means a decision reaches the agent before the code exists, instead of a reviewer finding the conflict afterwards. Mneme HQ applies it at two points. Before generation, the relevant decisions are retrieved and placed in the model's context, as a context packet or as generated Cursor rules. Before a change lands, the Claude Code hook checks the proposed mutation and can block it before it is written.

Code review is too late for this job. By the time generated code reaches a pull request, the diff exists, the reviewer's attention is finite, and the rejected pattern is already in the conversation history, where a later model call can read it as accepted. The full argument is on the [governance before generation](https://mnemehq.com/concepts/governance-before-generation/) concept page.

#### 6. What is architectural drift?

The gradual erosion of architectural decisions as code is added without enforcement. Drift is invisible in any single change but compounds over time. AI-assisted development accelerates drift because code output increases without a corresponding increase in review capacity. A team that catches 95% of architectural violations in review still ships compounding drift if AI is generating five times more code than humans are reviewing carefully.

#### 7. What kinds of teams should adopt Mneme HQ?

Teams that already write ADRs or keep an architecture document, have several developers using AI coding agents on the same codebase (Claude Code, Cursor, Copilot), and care more about architectural consistency than raw generation speed. The fit is strongest in regulated industries (fintech, health, government-adjacent), open-source projects with strict scope discipline, and any team where "we already decided this six months ago" is a familiar phrase.

Enforcement is scoped to one repository at a time, so adoption starts with a single repo. Distributing policy across an organization is Layer 2 work and is not shipped.

#### 8. What kinds of teams should not adopt Mneme HQ?

Teams without explicit architectural decisions to enforce. Mneme HQ enforces what you've already decided; it doesn't generate decisions for you. A team that has never written down its architectural choices won't benefit until it does. The right first step for such a team is to write five to ten ADRs.

#### 9. How does Mneme HQ relate to AI safety?

It's a narrow slice of AI safety: governance of AI-generated code at the project level. It's not AI alignment, not model safety, not RLHF. It's the boring, auditable, deterministic kind of safety that matters when AI is actually shipping code into production. The relevant safety claim is reproducibility: every verdict is reconstructable, no black box, no model in the verdict loop.

#### 10. Can I use Mneme HQ for non-code governance (docs, configs, prompts)?

The mechanism is general: Decisions and ADRs are not code-specific. The shipped integrations and the benchmark focus on code. Governing generated docs, configs or prompts is a plausible extension but is not in scope today.

#### 11. How do I contribute to Mneme HQ?

The repository enforces its own decisions with Mneme HQ. Read `CLAUDE.md` and the freeze artifact (`docs/architecture/layer1-freeze-e73ff7d.md`) before opening a PR. The retriever (`decision_retriever.py`), the enforcer (`enforcer.py`), the benchmark (`benchmark.py`) and the benchmark fixtures are frozen: changing their behavior requires the amendment procedure in the freeze document. Docs, tooling, integrations and examples follow the normal PR process. If you need to change the repository's own `.mneme/project_memory.json`, put `[memory]` at the start of the commit message and PR title.

#### 12. Is Mneme HQ open source?

Yes, MIT licensed. The repository is at [github.com/MnemeHQ/mneme](https://github.com/MnemeHQ/mneme). The mechanism, the benchmark methodology, the freeze artifact, the ADR compiler and the integrations are all in it. Commercial offerings (managed governance, hosted policy packs, an enterprise audit log) are planned for Layer 2 and are not shipped; the core stays open.

### Integrations

#### 13. How does Mneme HQ integrate with Claude Code?

Mneme HQ ships a Claude Code plugin whose hooks run at three points in a session.

`PreToolUse` covers `Edit`, `Write`, `MultiEdit` and `Bash`. For the three file tools, the hook reconstructs the file as it would be after the edit and runs `mneme check` on the lines the edit introduces, before the proposed mutation is written. In strict mode, the default, a violation blocks the write; in warn mode it is reported and the write proceeds. Bash coverage is intentionally narrower: only shell mutations that can be reconstructed deterministically (today, a quoted here-document redirected to a file) are checked before the command runs. Other shell commands are not blocked in advance.

`SessionStart` records a baseline of the repository, and `Stop` checks everything that changed during the session against it. That session-delta check is what catches mutations that escaped the pre-execution gate, such as files written by an arbitrary shell command.

Install in two steps: `pipx install "mneme-hq>=0.9.2"` for the runtime, then load the plugin from a Mneme checkout with `claude --plugin-dir ./integrations/claude-code-plugin`. The plugin provides four namespaced commands (`/mneme:context`, `/mneme:check`, `/mneme:record`, `/mneme:review`) and a discovery skill. A legacy flat integration with hyphenated commands (`/mneme-check` and its siblings) still exists, installed by `python scripts/install_claude_code.py`; it needs a git clone because `scripts/` is not shipped in the wheel.

#### 14. How does Mneme HQ integrate with Cursor?

Mneme HQ generates a Cursor rules file from your decision corpus:

```
mneme cursor generate \
  --memory .mneme/project_memory.json \
  --query "working on storage layer"
```

The output goes to `.cursor/rules/mneme.mdc` by default. Cursor reads the file as context, so this path informs the agent rather than blocking a write; pair it with `mneme check` in CI when you need a gate. The same corpus drives the Claude Code hook, so both agents work from one source of truth.

#### 15. Does Mneme HQ work with GitHub Copilot?

Not through a dedicated integration. Copilot does not expose a pre-tool-use hook comparable to Claude Code's, and Mneme HQ does not currently generate Copilot instruction files. Two things do work today. `mneme check` in CI evaluates a change the same way whichever tool wrote it, so Copilot-authored code that contradicts a recorded decision is caught there. And the decision corpus is plain JSON that you own, so you can adapt it by hand into Copilot's custom instructions. The [Copilot integration page](https://mnemehq.com/integrations/copilot/) tracks the current status.

#### 16. Does Mneme HQ work with agent frameworks like LangChain, CrewAI, AutoGen?

Yes, through the Python API. `MemoryStore`, `DecisionRetriever`, `ContextBuilder` and `Pipeline` can be wired into an agent's planning or tool-use loop: build the context packet, inject it as the system prompt, run the agent step, then optionally run `ConflictDetector` on the output. A LangChain and LangGraph integration ships as the optional `langchain` extra. The historical `POST /complete` HTTP wrapper has been separated from the active core and is not a supported endpoint.

#### 17. Can I use Mneme HQ without Claude Code?

Yes. The Claude Code hook is one integration and the rest of the system is independent of it. Run `mneme check` in CI against any repository, generate Cursor rules, or call `Pipeline` from your own code. The built-in LLM adapter that `Pipeline` uses currently targets Anthropic's API. Claude Code gets the deepest integration because it exposes a hook that runs before a tool call; other agents are reached through generated rules, the Python API or the CI check.

### ADRs and decisions

#### 18. What is the `project_memory.json` file?

A human-editable JSON file that holds your architectural decisions. Its canonical location is `.mneme/project_memory.json`. It contains three top-level arrays: `items` (legacy rules, anti-patterns, preferences, facts, architecture_decisions and examples, auto-migrated to Decisions at load time), `examples` (decision examples with task, decision and rationale), and `decisions` (the typed Decision schema). The file is plain JSON, so no tooling is required to edit it.

#### 19. What is the Decision schema?

```
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

#### 20. How does retrieval work?

Field-weighted keyword overlap, fully deterministic. With `q` as the query text:

```
score =
    1.0 * overlap(q, decision)
  + 2.0 * overlap(q, scope)
  + 1.5 * overlap(q, constraints)
  + 1.5 * overlap(q, anti_patterns)
  + 0.5 * overlap(q, rationale)
```

The top N decisions by score are injected (default `DEFAULT_MAX_DECISIONS = 3`). Rules and anti-patterns always surface regardless of query relevance. The same query and the same memory file produce a byte-identical retrieval order on every run.

#### 21. Why no embeddings?

Three reasons. First, determinism: same query plus same memory must produce identical output, run to run. Embeddings drift with model updates. Second, debuggability: a keyword match is reconstructable; a vector similarity is not. Third, scope: governance corpora are small (tens to low hundreds of decisions). Embeddings solve a problem you don't have at this scale and cost reproducibility you can't afford to lose.

#### 22. What is an ADR in Mneme HQ?

An Architectural Decision Record. Mneme HQ's ADR format is YAML frontmatter plus a markdown body:

```
---
id: ADR-001
title: Use JSON file storage
status: accepted
priority: foundational
date: 2026-01-10
scope: storage
supersedes: []
---

Body markdown follows.
```

`status` is one of `proposed`, `accepted`, `deprecated` or `superseded`. `priority` is `foundational`, `normal` or `exception`. `scope` is a dotted path, and an empty string means global. ADRs are the source of truth; the ADR compiler is the deterministic rule for turning them into the constraints the runtime injects.

#### 23. How does ADR precedence resolution work?

When two ADRs cover the same scope, the compiler resolves them in a strict order: first, explicit `supersedes` references remove ADRs from consideration (chain-aware, including N-node chains). Second, within the same scope, higher priority wins (`foundational` > `normal` > `exception`). Third, same scope and same priority, newer `date` wins. If still ambiguous, the compiler raises `ADRPrecedenceError` rather than silently picking a winner. Broader and narrower scopes coexist; output is sorted most-specific-first.

#### 24. What does corpus validation check?

`validate_corpus` collects every problem it finds before raising, so one pass surfaces every error and maintainers fix the corpus once instead of discovering problems one at a time. Checks include: required fields present, ADR id format and uniqueness, valid `status` and `priority` enum values, ISO 8601 date, scope grammar (lowercase dotted path, no leading or trailing dot), `supersedes` references resolving to known ADRs, and no supersession cycles (self-cycles, two-node cycles and N-node cycles are all detected).

#### 25. How does Mneme HQ handle a decision that becomes obsolete?

Write a new ADR for the replacement decision and list the old ADR's id in the new ADR's `supersedes` array, then set the old ADR to `status: superseded`. If a decision is retired with no replacement, set it to `status: deprecated`. The compiler removes deprecated and superseded ADRs from the active constraint set automatically. The history stays in the corpus; only the active set changes. See supersession.

#### 26. How do I write a good Decision record?

Three properties matter. First, specificity: the `decision` field should be unambiguous and falsifiable ("Use JSON file storage" beats "Be careful with storage"). Second, scope: the `scope` array names the modules or domains where the decision applies, and the retriever uses it to surface the decision when a relevant query comes in. Third, the `constraints` and `anti_patterns` arrays should list the terms an LLM would use when violating the decision, because these are what the conflict detector matches against. A Decision with rich `anti_patterns` enforces; a Decision with only `decision` and `rationale` informs but cannot block.

#### 27. What's the difference between a constraint and an anti-pattern?

In the Decision schema, both are flagged by the conflict detector. The distinction is editorial: `constraints` describe what must be true ("REST only", "no external database"); `anti_patterns` describe what must not be done ("introduce ORM", "add migration layer"). Both fields contribute to retrieval scoring with weight 1.5.

### Enforcement

#### 28. What are enforcement modes?

`strict` and `warn`. `strict` is the default for both `mneme check` and the Claude Code hook: a WARN verdict exits 1, a FAIL verdict exits 2, and the hook blocks the proposed write. In `warn` mode every verdict exits 0 and violations are reported without blocking, which is useful when you adopt Mneme HQ on an existing repository and want visibility before you turn enforcement on. Set the CLI's mode with `--mode` and the hook's with the `MNEME_HOOK_MODE` environment variable.

#### 29. What does `mneme check` actually do?

It checks one input file against your decision corpus. You give it the memory file, the file to check (a prompt, a draft, a generated file or a diff) and a query that describes the work:

```
mneme check \
  --memory .mneme/project_memory.json \
  --input src/storage/store.py \
  --query "storage layer" \
  --mode strict
```

It retrieves the decisions relevant to the query, runs the enforcer over the input, and prints each violation with the decision that matched and the term that triggered it. Rules built on unambiguous literal terms apply across the whole corpus whatever the query says. `--memory`, `--input` and `--query` are all required. Add `--json` for a machine-readable verdict, and `--target-path` when the input is a diff and your rules are path-scoped. The [CLI reference](https://mnemehq.com/docs/cli/) lists every flag and exit code.

#### 30. How does conflict detection work?

`ConflictDetector` scans the LLM response (or the content a proposed edit introduces) for constraint and anti-pattern terms drawn from the injected decisions. A term is flagged when it appears with a positive recommendation signal and no negation nearby. "Do not use Postgres" is not a conflict. "Switch to Postgres" is. Each conflict carries the violated decision id, the reason, and a snippet for human review.

#### 31. Is there a model in the verdict loop?

No. The retrieval, the injection, the conflict detection and the verdict are all deterministic. The model is in the *generation* loop (it's the thing being governed), but the verdict itself is reconstructable without any model call. This is intentional: deterministic over clever is one of the project's charter principles. The upgrade path to a model-based judge is explicit in the code (replace two functions) and remains opt-in.

#### 32. Can Mneme HQ auto-fix violations?

No. Mneme HQ blocks. The human or model fixes. Auto-fixing is explicitly out of scope: a deterministic governance layer cannot also be the thing that decides how to comply, or it becomes the same kind of opinionated agent it's meant to govern.

#### 33. How do I handle a violation in strict mode?

The Claude Code hook blocks the write and names the decision that was violated. There are two legitimate responses. If the decision still stands, change the request so the output complies. If the decision itself should change, update the record first (write a new ADR that supersedes the old one), then retry. When you are part-way through an intentional architectural change that the corpus has not caught up with, you can set `MNEME_HOOK_MODE=warn` temporarily. There is no per-verdict override: strict mode is meant to make you stop and think, not to be bypassed as a habit.

#### 34. Does Mneme HQ slow down my AI coding agent?

Very little. Retrieval is keyword scoring over a small JSON file and conflict detection is pattern matching over the proposed change. Both run locally, with no model call and no network round trip. The slow part of an agent step is the model call itself, which Mneme HQ does not make.

### Benchmarks

#### 35. What's the Layer 1 freeze?

The core mechanism (retrieval mechanics, enforcement semantics, benchmark methodology) is pinned at commit `e73ff7d`. Behavior in those modules cannot change without the amendment procedure written into the freeze artifact. The freeze exists because validation needs a stable mechanism: you cannot show that a tool prevents drift if the tool itself keeps changing.

#### 36. What is Layer 2 and why is it deferred?

Layer 2 covers multi-repo governance, team policy synchronization, shared policy packs, org-wide policy distribution, and deeper IDE integrations (LSP, JetBrains). All of it is out of scope for Layer 1. Layer 2 opens only after the Layer 1 exit criteria are met: evidence that Mneme HQ prevents drift on real repositories, feedback from design partners, and confirmation that the narrow starting scope is the right one. The discipline is deliberate. Layer 1 is a narrow starting point, not a platform.

#### 37. What is the benchmark suite?

A regression and integrity instrument, not a generalization claim. It uses canned LLM responses, fixed retrieval and rule-text matching to make every change to retrieval or enforcement visible. Each scenario is scored in two stages that are recorded independently: a retrieval score (was the expected decision retrieved?) and an enforcement verdict (was the violation caught?). The `WEAK_RETRIEVAL` verdict flags coincidental passes, where enforcement happened to succeed without the relevant decision being retrieved. Recall@1 is reported but never optimized against.

The benchmark code and the [methodology page](https://mnemehq.com/docs/benchmark-methodology/) label the two scoring stages Layer 1 and Layer 2. That numbering is unrelated to the product phases of the same name.

#### 38. What does recall@3 = 1.00 actually mean?

For every scenario in the benchmark fixture set, the relevant decision appears in the top three retrieved decisions. K=3 is the canonical retrieval cutoff: the top three decisions are the ones injected and the ones whose multi-term rules are applied. Unambiguous literal rules are enforced across the whole corpus regardless of the cutoff. Recall@3 = 1.00 means no scenario in the suite has its critical decision pushed below the cutoff by the retriever.

#### 39. Why is recall@1 reported but not optimized?

Recall@1 is the metric that responds most to tuning. Optimizing for it on a small fixture set leads to overfitting: you end up with a retriever that aces the suite and fails on real corpora. Reporting it without optimizing for it keeps the number visible, so a regression shows up, without rewarding suite-specific tweaks.

### Comparisons

#### 40. What problem does Mneme HQ solve that Cursor Rules and CLAUDE.md don't?

Cursor Rules and CLAUDE.md are unstructured text pasted into the prompt. They have no precedence semantics, no validation, no conflict detection and no enforcement. When two rules contradict each other, the model picks one, usually whichever appears later or sounds more confident. There is no audit trail of what was injected, no way to verify it ran, and no scoring of whether the output followed the rules. Mneme HQ replaces this with a typed schema (Decisions and ADRs), deterministic retrieval, deterministic precedence resolution, a check on each proposed change before it is written, and conflict detection on model output. Every step is reconstructable from artifacts.

#### 41. How is this different from RAG?

RAG retrieves information. Mneme HQ retrieves decisions. RAG's goal is to inform the response; Mneme HQ's goal is to shape the response. RAG asks "did the model use the right source?"; Mneme HQ asks "did the model respect the constraint?" RAG is fuzzy by design (vector similarity, top-k chunks); Mneme HQ is deterministic by design (same query plus same memory always returns the same ranking).

#### 42. How is this different from a linter?

A linter checks syntax, style and known bug patterns in source code. Mneme HQ checks a proposed change against the architectural decisions your team recorded, before the change is written. Linters operate on syntax; Mneme HQ operates on recorded decisions. A linter has no rule for "we decided not to rebuild retrieval on embeddings" unless someone writes one. Mneme HQ matches the constraint and anti-pattern terms listed in the decision record itself.

#### 43. How is this different from an LLM-as-judge evaluation framework?

LLM-as-judge introduces a second model to evaluate the first model's output. It's powerful but nondeterministic: the judge's verdict varies run to run and shifts with model updates. Mneme HQ's evaluator is deterministic by design. The upgrade path to a model judge is explicit in the code (replace two functions) but is opt-in and not the default. In Layer 1, the deterministic evaluator is canonical.

---

## Glossary

### Active constraint set

The deterministically resolved subset of an ADR corpus that applies at a given point in time. The ADR compiler computes it from the full corpus by filtering out deprecated and superseded ADRs and resolving same-scope conflicts through precedence resolution. The same corpus always produces the same active constraint set.

### ADR (Architectural Decision Record)

A versioned markdown document describing an architectural choice, its context and its consequences. In Mneme HQ, ADRs use YAML frontmatter (`id`, `title`, `status`, `priority`, `date`, `scope`, `supersedes`) plus body markdown. ADRs are the source of truth for the active constraint set.

### ADR compiler

The pipeline that turns an ADR corpus into an active constraint set. Three stages: parse (YAML frontmatter parsing, structural validation), validate (required fields, references, no cycles), and resolve precedence (status filter, then supersession chains, then priority, then date). Implemented in `mneme/adr_compiler.py`.

### Alignment score

A deterministic score (0.00 to 1.00) representing the fraction of injected decisions that the LLM response did not violate. Computed by the evaluator over the rules and decisions actually injected, not the full corpus. 1.00 means no violations detected.

### Anti-pattern

A field on the Decision schema listing things the decision rules out. The conflict detector flags any anti-pattern term that appears in a response with a positive recommendation signal and no negation signal nearby. Contributes weight 1.5 to retrieval scoring. Compare constraint.

### Architectural drift

The gradual erosion of architectural decisions as code is added without enforcement. Drift is invisible in any single change but compounds. AI-assisted development accelerates drift because code output increases faster than review capacity. Covered in depth on the [architectural drift](https://mnemehq.com/concepts/architectural-drift/) concept page.

### Architectural governance

The practice of enforcing architectural decisions across a codebase at the point of change. Distinct from code review (after the fact) and linting (syntactic). Mneme HQ applies it by supplying decisions to the agent as context before generation and by checking each proposed change before it is written. See governance before generation.

### Auditable

A property of enforcement verdicts: reconstructable from artifacts. For any Mneme HQ verdict, a human can trace which decision matched, which rule triggered, and which term in the input fired it. One of the charter principles.

### Benchmark methodology

The framework Mneme HQ uses to make every change to retrieval or enforcement visible and reproducible: canned LLM responses (no live model variance in the suite), fixed retrieval, rule-text matching, and two-stage scoring in which a retrieval score and an enforcement verdict are recorded independently. The full methodology is at [mnemehq.com/docs/benchmark-methodology/](https://mnemehq.com/docs/benchmark-methodology/). See also recall@k.

### Charter

The design principles Mneme HQ is held to: deterministic over clever, auditable over autonomous, prevention before review. Every feature is judged against them. Changing the frozen core modules requires the amendment procedure in the freeze artifact.

### Claude Code hook

The enforcement hooks shipped in the Mneme HQ Claude Code plugin. The `PreToolUse` hook covers `Edit`, `Write`, `MultiEdit` and `Bash`: for file edits, the content an edit introduces is checked before the proposed mutation is written, and Bash is checked before execution only for shell mutations that can be reconstructed deterministically. `SessionStart` records a repository baseline and `Stop` checks the session's changes against it, which catches mutations that escaped the pre-execution gate. The mode defaults to strict; see enforcement mode. Setup is described in the Claude Code question.

### Conflict detector

The module (`mneme/conflict_detector.py`) that scans an LLM response for constraint and anti-pattern violations after the call. It detects rather than blocks, and produces a `Conflict(violated_decision_id, reason, snippet)` for each match.

### Constraint

A field on the Decision schema listing things that must be true. It behaves like an anti-pattern in the conflict detector but is editorially distinct: constraints are positive requirements, anti-patterns are prohibitions. Both contribute weight 1.5 to retrieval scoring.

### Context packet

A compact, structured representation of the decisions injected into an LLM call. Built by `format_context_packet` from the top-N retrieved decisions plus always-surfaced rules, and passed as the system prompt. See retrieval cutoff (K).

### Decision

The atomic unit of the decision corpus. A typed record with `id`, `decision`, and optional `rationale`, `scope`, `constraints` and `anti_patterns`. Decisions can be authored directly in `project_memory.json` or imported from ADRs.

### Decision and control layer

What Mneme HQ is: the decision and control layer for agentic software development. It holds the decisions a team has already made and applies them to what AI coding agents propose, starting with architectural decisions in a repository. Governance is the outcome this produces, not the name of the category. Today Mneme HQ applies the idea to one class of decision: architecture.

### Decision example

A record of a past decision with three fields: `task` (the situation that prompted the decision), `decision` (what was decided) and `rationale` (why). Injected as prior decisions so the model learns how the project reasons, not just what it decided.

### Decision retriever

The retriever (`mneme/decision_retriever.py`) that scores Decision records against a query using field-weighted scoring. Deterministic. The top-N scoring decisions are passed to the context builder.

### Deterministic retrieval

A retrieval mechanism in which the same query and the same memory file produce a byte-identical retrieval order on every run. Mneme HQ's retriever is deterministic by design, which gives stable results across model updates, full debuggability and reproducible benchmarks.

### Enforcement mode

The setting that governs how `mneme check` and the Claude Code hook respond to violations. `strict`, the default for both, exits non-zero and blocks the proposed write; `warn` reports violations without blocking.

### Evaluator

The deterministic alignment checker that scores an LLM response against the rules that were actually injected. Two checks: a rule check (extracts forbidden terms from each rule or anti-pattern, fires on a positive recommendation signal without nearby negation) and a decision check (for past decisions where the project said "no", fires if the response recommends the declined subject anyway). Produces the alignment score.

### Field-weighted scoring

The retrieval algorithm in which each field of a Decision contributes to the relevance score with a different weight. Mneme HQ's weights: decision title 1.0, scope 2.0, constraints 1.5, anti_patterns 1.5, rationale 0.5. Tuned for retrieving decisions, not for general information retrieval. Worked through in How does retrieval work?

### Freeze artifact

The document (`docs/architecture/layer1-freeze-e73ff7d.md`) that pins the Layer 1 mechanism to a specific commit and lists what can change without amendment and what cannot. It is the contract between the maintainers and the community during validation.

### Governance before generation

The intervention pattern Mneme HQ is built on: a recorded decision reaches the agent before the code exists, rather than being discovered as drift in code review. Decisions are placed in the model's context before it generates, and each proposed change is checked before it is written. Defined formally on the [governance before generation](https://mnemehq.com/concepts/governance-before-generation/) concept page.

### Layer 1

The current phase of Mneme HQ: local-repo, project-scoped enforcement of architectural decisions. The core mechanism is frozen at commit `e73ff7d` (see freeze artifact). Open exit criteria: evidence of drift prevention on real repositories, design-partner feedback, and confirmation that the narrow starting scope is the right one.

### Layer 2

Work that stays out of scope until Layer 1 exits: multi-repo governance, team policy synchronization, shared policy packs, org-wide policy distribution, and deeper IDE integrations (LSP, JetBrains). Listed explicitly to prevent scope creep. Not to be confused with the second scoring stage of the benchmark.

### MemoryStore

The module (`mneme/memory_store.py`) that loads `project_memory.json` into typed Python objects. It migrates legacy rule and anti_pattern items into Decision objects at load time, so older JSON files keep working.

### `mneme check`

The CLI command that checks an input file against the decision corpus. `--memory`, `--input` and `--query` are required, for example `mneme check --memory .mneme/project_memory.json --input src/storage/store.py --query "storage layer"`. `--mode strict` is the default and exits non-zero on a violation; `--mode warn` reports violations and exits zero. Used in CI and by the Claude Code hook. Full reference in the [CLI docs](https://mnemehq.com/docs/cli/).

### `.mneme/` directory

The canonical location for a repository's decision corpus. It contains the source-of-truth `project_memory.json` and any repo-specific configuration. It plays the role that `.git/` plays for source control or `.github/` for CI configuration.

### Negation signal

A term near a flagged anti-pattern or constraint that turns a potential violation into a non-violation. "Do not use Postgres" contains the negation "Do not" and is not flagged. "Switch to Postgres" has no negation and is flagged. Implemented as a small set of negation phrases checked within a window of the matched term. Used by the conflict detector.

### Pipeline

The orchestrating module (`mneme/pipeline.py`) that wires MemoryStore, decision retriever, injection, the LLM call and the conflict detector together. Used by the demo, and the single entry point for programmatic use of Mneme HQ. Its built-in LLM adapter currently targets Anthropic's API.

### Pre-flight enforcement

Checking a proposed change before it is written or applied, rather than after. The Claude Code hook fires on the proposed edit, reconstructs the post-edit state, runs `mneme check` on what the edit introduces and decides whether to allow the write. The contrast is post-flight review, which finds drift in code review after the diff exists.

### Precedence resolution

The deterministic procedure for resolving conflicts between ADRs covering the same scope: explicit `supersedes` references first (chain-aware), then priority (foundational > normal > exception), then date (newer wins). If the result is still ambiguous, it raises `ADRPrecedenceError`. It never silently picks a winner.

### `PreToolUse` hook

The Claude Code hook surface that runs before a tool call. Mneme HQ registers it for `Edit`, `Write`, `MultiEdit` and `Bash`. For the file tools it reconstructs the post-edit file and checks the introduced content before the proposed mutation is written. For `Bash` it checks only shell mutations it can reconstruct deterministically; everything else passes through to the `Stop` session-delta check described under Claude Code hook.

### Prevention before review

A Mneme HQ charter principle: intervene before a change lands, not in code review. Prevention is cheaper than detection, and both are cheaper than rollback.

### Priority (ADR)

A field on ADR frontmatter governing same-scope precedence. Values: `foundational`, `normal`, `exception`. When two ADRs cover the same scope, higher priority wins. Foundational decisions are core architectural choices; exceptions are documented carve-outs. See precedence resolution.

### `project_memory.json`

The human-editable JSON file holding a project's architectural decisions, kept at `.mneme/project_memory.json` (see `.mneme/` directory). Three top-level arrays: `items` (legacy types, auto-migrated), `examples` (decision examples) and `decisions` (the Decision schema). Plain JSON, no tooling required.

### Recall@k

A retrieval metric: the fraction of scenarios where the relevant decision appears in the top-k retrieved decisions. Mneme HQ's benchmark reports recall@3 over the fixture suite, because three is the canonical retrieval cutoff. Recall@1 is reported but not optimized (why).

### Retrieval cutoff (K)

The number of top-scoring decisions passed from the retriever to the context builder. Default `DEFAULT_MAX_DECISIONS = 3`. K is a property of the system, not a benchmark parameter, and stays fixed across runs. Unambiguous literal rules are enforced across the whole corpus regardless of K.

### Rule (legacy)

An older record type in `project_memory.json` describing a hard constraint. It is migrated to a Decision with matching constraints and anti_patterns at load time. Kept for backward compatibility; new corpora should use Decisions directly.

### Scope

A dotted-path string (or an array, on Decision records) naming the modules or domains where a decision applies. The retriever uses it to surface decisions when a relevant query comes in. An empty string means global; nested scopes like `storage.backend` apply to that subtree.

### Slash commands (Claude Code)

Four namespaced commands provided by the Mneme HQ Claude Code plugin: `/mneme:context` (inspect what would be injected for a query), `/mneme:check` (run an enforcement check), `/mneme:record` (record a new decision from the current conversation) and `/mneme:review` (review the active constraint set). The hyphenated forms (`/mneme-check` and its siblings) belong to the legacy flat integration.

### Status (ADR)

A field on ADR frontmatter: `proposed`, `accepted`, `deprecated`, `superseded`. Only accepted ADRs enter the active constraint set; deprecated and superseded ADRs are filtered out at compile time.

### Supersession

The mechanism by which a new ADR replaces an older one. The new ADR's `supersedes` array lists the ids of the older ADRs it replaces. The compiler removes superseded ADRs from the active constraint set and follows chains: if ADR-003 supersedes ADR-002, which superseded ADR-001, only ADR-003 is active. Supersession cycles are detected at validation time.

### Verification contract

The explicit, reproducible commitment an enforcement layer makes about what it will and will not check, and under what conditions. Mneme HQ's verification contract is the freeze artifact plus the benchmark methodology. Defined on the [verification contracts](https://mnemehq.com/concepts/verification-contracts/) concept page.

### Warn mode

An enforcement mode in which violations are reported but do not fail the check or block a write. Used during adoption to give a team visibility before it turns on strict mode. Opt in with `--mode warn` on the CLI or `MNEME_HOOK_MODE=warn` for the Claude Code hook; strict is the default for both.

### Wedge

The narrow, intentional starting scope of Mneme HQ: explicit recorded decisions, deterministically retrieved, and checked before a change is written. The wedge is defined as much by what it leaves out (autonomous agents, vector stores, long context, model-based judges in Layer 1) as by what it includes.

---

## Related concepts (on mnemehq.com/concepts/)

For the longer argument behind these terms, see the concept pages:

- [Governance before generation](https://mnemehq.com/concepts/governance-before-generation/)
- [Verification contracts](https://mnemehq.com/concepts/verification-contracts/)
- [Architectural drift](https://mnemehq.com/concepts/architectural-drift/)
- [All concepts](https://mnemehq.com/concepts/)

The concept pages carry the reasoning. This document is the practitioner reference for the product.

---

## How to cite

Mneme HQ. *Q&A and Glossary*. mnemehq.com. 2026. Available at: https://mnemehq.com/qa-glossary/ and https://github.com/MnemeHQ/mneme.

MIT License. Reproduction and citation encouraged.
