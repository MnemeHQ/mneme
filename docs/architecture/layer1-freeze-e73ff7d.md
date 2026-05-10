# Mneme Layer 1 Freeze

> Architectural checkpoint, governance boundary, and benchmark contract.
> This document defines what Mneme **is** at the close of Layer 1, and — equally important — what it deliberately **is not**.
> It exists to prevent the project from absorbing every adjacent AI-governance idea before the core wedge is validated.

---

## Freeze Anchor

| | |
|---|---|
| **Freeze commit** | `e73ff7d444b654d01ae45ccc9785e5efe5fc46ac` |
| **Freeze date** | 2026-05-10 |
| **Benchmark version** | v1.1, stabilization complete through Step 3C |
| **Scope statement** | Local-repo, single-developer, project-scoped architectural governance for AI-assisted code generation |
| **Status** | Frozen. No behavioral change to retrieval or enforcement without an explicit charter amendment. |

### Step 3C closure trail
| PR | SHA | What it locked |
|---|---|---|
| #19 | `0b1bb7a` | Charter freeze: 11-decision retrieval pool, K=3, methodology surface as non-goals |
| #20 | `8d7a398` | Stage 0 — deterministic retrieval tie-order pin (insertion order via stable sort) |
| #21 | `096b8be` | Stage 1 — `anti_pattern.content` migration symmetry (constraints/anti_patterns reach the enforcer) |
| #22 | `e73ff7d` | H1 — pinning of migrated anti-pattern enforcement behavior |

### Final Layer 1 benchmark numbers (frozen)
- Suite verdict: **7/7 PASS**
- recall@3 = **1.00**
- recall@1 = **5/5 = 1.00**
- precision@3 = **0.333** (structurally pinned, see §Benchmark Methodology)
- irrelevant injection rate = **100%** (structurally pinned, see §Benchmark Methodology)

---

## Purpose of Layer 1

Layer 1 exists to prove a narrow, falsifiable claim:

> **Explicit, recorded architectural decisions can be retrieved deterministically and enforced *before* an LLM generates code that would violate them.**

Everything in Layer 1 is in service of that claim. Specifically, Layer 1 is trying to demonstrate:

- **Architectural governance before generation.** Decisions intercept the prompt path; they do not review output after the fact.
- **Deterministic decision retrieval.** Given a fixed memory and a fixed query, the same decisions surface in the same order every time.
- **Governance continuity inside a single local repo.** A developer working in one repo can encode architectural intent once and have it apply consistently across AI-assisted sessions.
- **Constraint enforcement for AI-assisted development.** "Don't add Pydantic," "no second LLM provider in v1," "JSON storage only" — rules expressed as data, evaluated as data, blocked at prompt time.

Layer 1 is **not** trying to demonstrate:

- An enterprise governance platform.
- Autonomous agents or multi-step planning.
- Distributed orchestration of memory across teams or repos.
- A generalized memory system for arbitrary LLM applications.
- Long-term conversational memory.
- Code-generation quality scoring or auto-fix.

The wedge is intentionally narrow. The freeze protects that narrowness.

---

## What Shipped

Concrete, end-to-end capabilities present at `e73ff7d`:

### Core retrieval and enforcement
- **`DecisionRetriever`** ([decision_retriever.py](mneme-project-memory/mneme/decision_retriever.py)) — deterministic bag-of-tokens scoring across five Decision fields with fixed weights (`scope`=2.0, `constraints`=1.5, `anti_patterns`=1.5, `decision`=1.0, `rationale`=0.5). Stopword filter, `len >= 4` token floor, insertion-order tiebreak.
- **`check_prompt`** ([enforcer.py](mneme-project-memory/mneme/enforcer.py)) — pre-flight enforcement. `anti_patterns` matches → `FAIL` (severity 2). `no <X>` constraints → `WARN` (severity 1). Word-boundary matching, rule-text stopword filter, top-K-only.
- **`ConflictDetector`** ([conflict_detector.py](mneme-project-memory/mneme/conflict_detector.py)) — structural conflict detection across decisions.
- **CLI enforcement** ([cli.py](mneme-project-memory/mneme/cli.py)) — `mneme check` with exit codes 0/1/2 mapping to PASS/WARN/FAIL.
- **`warn` and `strict` enforcement modes** — gating policy at the CLI boundary.

### Benchmark harness
- **Two-layer scoring** ([benchmark.py](mneme-project-memory/mneme/benchmark.py)) — Layer 1 (retrieval) and Layer 2 (enforcement) recorded independently per scenario.
- **Five-verdict semantics** — `PASS`, `FAIL`, `WEAK`, `WEAK_RETRIEVAL`, `MALFORMED`. `WEAK_RETRIEVAL` exists specifically to flag *coincidental* passes where the enhanced response was clean but the intended decision was never retrieved.
- **Structured fixtures with TXT fallback** — JSON path preferred; missing JSON sibling emits a `UserWarning` rather than silently succeeding.
- **Suite-level metrics** ([benchmark_report.py](mneme-project-memory/mneme/benchmark_report.py)) — mean recall@K, mean precision@K, irrelevant-injection rate, aggregated only over scenarios that declare `expected_protected_decision_ids`.

### Governance fixtures
Seven shipped scenarios under [examples/benchmarks/](mneme-project-memory/examples/benchmarks/):

| Category | Scenario |
|---|---|
| Architecture | `storage_backend_violation` (JSON-only storage vs. Postgres+SQLAlchemy) |
| Scope | `feature_boundary_violation` (multi-agent loops ruled out in v1) |
| Scope | `infra_scope_creep_violation` |
| Scope | `openai_provider_violation` (v1 Anthropic-only) |
| Anti-pattern | `pydantic_dependency_creep` (stdlib dataclasses preference) |
| Anti-pattern | `framework_abstraction_violation` |
| Retrieval | `retrieval_complexity_violation` |

### Editor/IDE adjacency
- **Cursor rules export** ([cursor_generator.py](mneme-project-memory/mneme/cursor_generator.py)) — emits `.cursor/rules` from the same memory.
- **Claude Code hook** ([integrations/claude_code/hook.py](mneme-project-memory/mneme/integrations/claude_code/hook.py)) — pre-prompt enforcement integrated with the Claude Code agent harness.

### ADR-aware governance workflow
- **ADR parser, validator, compiler** ([adr_parser.py](mneme-project-memory/mneme/adr_parser.py), [adr_compiler.py](mneme-project-memory/mneme/adr_compiler.py), [adr_schema.py](mneme-project-memory/mneme/adr_schema.py)) — Architecture Decision Records under `docs/adr/` are parseable, validatable, and reconcilable against `project_memory.json`.

---

## Benchmark Methodology

The benchmark methodology is the most opinionated part of the freeze. Read this section before proposing any benchmark change.

### Philosophy

Layer 1's benchmark is a **regression and integrity instrument**, not a generalization claim. Its job is to make every change to retrieval or enforcement *visible* and *reproducible*, so that:

1. A regression cannot land silently.
2. A PASS cannot be coincidence.
3. The numbers reported externally cannot drift away from what the code actually does.

### Why the benchmark is deterministic

LLMs are nondeterministic by default. The Mneme benchmark deliberately collapses that nondeterminism:

- Scenarios use **canned LLM responses** (`with_mneme.txt` / `with_mneme.json`, `without_mneme.txt` / `without_mneme.json`). The benchmark does not call a live model.
- Retrieval is bag-of-tokens with **stable sort and explicit tiebreak** (Stage 0, `8d7a398`). Same memory + same query → byte-identical retrieval order.
- Enforcement is rule-text matching against retrieved decisions; no probabilistic scoring.

This is a deliberate choice. A benchmark that varies between runs cannot detect a regression in the part of the system Mneme actually owns: **retrieval and enforcement against governed decisions.**

### Why recall@1 is reported, not promoted

- recall@1 is the sharpest tuning dial under fixed methodology.
- Promoting it into the suite headline would make tuning weights to move recall@1 a continuous temptation.
- With seven scenarios and an eleven-decision pool, any further tuning would fit the suite, not the world.
- recall@1 is therefore tracked and reported transparently but **not** part of pass/fail or any external scorecard.

### Why K=3 is canonical

- The enforcer reads the top-K retrieved decisions and only those (`enforcer._top_nonzero`).
- K=3 is hard-coded as `DEFAULT_MAX_DECISIONS` and asserted by the benchmark runner.
- Varying K would change the enforcement surface, not just the metric.
- K is therefore a property of the system, not a benchmark parameter, and is frozen.

### Why precision is intentionally constrained

Two structural facts pin precision@3 below ~0.33 in the current suite:

1. Most shipped scenarios declare `acceptable_decision_ids: []`. The "relevant set" used by precision is therefore typically just the expected ID(s), often a single decision.
2. K=3 with one expected ID gives a precision ceiling of `1/3 ≈ 0.333`.

Precision and irrelevant-injection-rate are therefore **not** Layer 1 quality signals today. They are placeholder telemetry for a later methodology that will populate `acceptable_decision_ids` properly.

The freeze does not pretend otherwise.

### Why benchmark expansion is frozen

- Adding scenarios to push a metric is overfitting at this suite size.
- Adding adversarial or paraphrase scenarios is a charter-level methodology change.
- Adding scenarios designed to make a known-good decision PASS is the exact failure mode `rule-bench-retrieval-coupling` was written to prevent.
- The next legitimate benchmark work is data-only: populating `acceptable_decision_ids` on the existing seven scenarios.

### Why synthetic scenarios are acceptable at this stage

- Layer 1 proves a *mechanism*, not a *distribution*.
- Synthetic, hand-authored scenarios make the mechanism falsifiable: every PASS records the retrieved IDs and the triggering rule, and a reviewer can verify the chain end-to-end.
- Real-world distribution evidence is the job of the next phase (design-partner validation), not the benchmark.

### Categories covered

- **Architecture** — storage backend boundary.
- **Scope** — provider boundary, feature boundary, infrastructure boundary.
- **Anti-patterns** — dependency creep, framework abstraction.
- **Retrieval** — retrieval complexity rules.

These four categories are the Layer 1 surface. Adding a fifth category requires a charter amendment.

---

## Charter Discipline

These principles are load-bearing. They constrain what Mneme will and will not do, regardless of how attractive a feature looks.

### Mneme is governance-first
The product exists to *enforce* recorded architectural decisions, not to discover them, summarize them, or generate them. Every feature is judged against "does this make governance more reliable?"

### Explicit recorded decisions only
Every enforced rule is a Decision in `project_memory.json` with an explicit `id`. There is no implicit policy, no inferred rule, no convention-based enforcement. If it's not written down, it's not governed.

### No passive memory ingestion
Mneme does not watch your repo, scrape commits, or learn from your code. Memory is edited deliberately and reviewed under the `[memory]` PR convention.

### No auto-learning
Mneme does not adjust weights, infer new constraints, or update its own configuration based on what it observes. Determinism is the contract.

### No hidden vector magic
The retriever is bag-of-tokens with documented weights. There are no embeddings in the freeze. If embeddings ever land, they will be optional, additive, and traceable on a per-match basis.

### Deterministic > clever
A simpler retriever that gives the same answer twice is preferred to a smarter retriever that gives different answers. The Step 3C tiebreak pin is the canonical expression of this principle.

### Auditable > autonomous
Every block records: which decision matched, which rule triggered, which term in the input fired it, what the score was, and why this decision was in the top-K. A human can reconstruct any verdict from the artifacts.

### Prevention before review
Mneme runs *before* the LLM generates output, not after. There is no "review the diff" loop in the Layer 1 wedge. The intervention point is the prompt boundary.

---

## Known Limitations

These are real and acknowledged. The freeze does not paper over them.

- **Local and project-scoped only.** Memory lives in a single repo's `.mneme/project_memory.json`. There is no team sync.
- **No remote policy store.** No central server, no shared rule library across repos.
- **Bag-of-tokens retrieval.** Synonyms, paraphrases, and renamed concepts will not match unless the rule text is updated. No semantic ranking.
- **Small benchmark surface.** Seven scenarios, eleven-decision pool. Strong as a regression instrument; not a generalization claim.
- **Sparse `acceptable_decision_ids`.** Most shipped scenarios leave this empty, which structurally pins precision@3 and irrelevant-injection-rate.
- **No CI-native policy lineage.** ADR-to-decision lineage is parseable but not enforced as a CI gate.
- **No IDE-native inline enforcement.** Cursor rules export and Claude Code hook are the integrations; there is no language-server-protocol or live-decoration story.
- **No semantic ADR graph.** ADRs are validated against memory but not cross-linked as a graph.
- **No automatic remediation.** A FAIL surfaces what was violated, not how to fix it.
- **`"no X"` constraints are the only constraint shape parsed by the enforcer.** Other constraint phrasings are silently ignored at enforcement time. This narrow constraint grammar is a deliberate Layer 1 simplification, not an unnoticed parser weakness — it preserves deterministic, inspectable enforcement semantics. Richer constraint shapes are a Layer 2 question.

---

## Deferred Work

Intentionally deferred — listed so they cannot be re-derived as "missing."

- **ADR lineage and versioning.** ADR supersession chains, decision provenance graphs.
- **Repo retrospectives.** Looking back over a repo's history to surface latent governance.
- **Branch-drift analysis.** Detecting when a long-running branch has diverged from governing decisions.
- **Team governance.** Multi-developer coordination on shared memory.
- **Shared policy packs.** Ready-made governance bundles (e.g., a "Python service" pack).
- **MCP / API layer.** Programmatic access for external tooling.
- **Deeper IDE integrations.** LSP, JetBrains, Vim/Neovim, language-server-style inline diagnostics.
- **CI enforcement evolution.** GitHub Actions integration beyond the current CLI invocation.
- **Policy compiler.** Higher-level policy DSL that compiles down to `project_memory.json`.
- **Org-wide governance.** Cross-repo policy distribution.

Each of these is plausibly valuable. None of them are in scope for Layer 1. Promoting any of them requires the wedge to be validated first.

---

## Intentionally NOT Solved

These are *not* on the deferred list. They are not Mneme's problem and pulling them in would dilute the wedge.

- **Generalized agent memory.** Mneme is not a vector store, not a conversational memory, not an "AI memory" product.
- **Autonomous planning.** No multi-step agent loops, no tool-use orchestration.
- **Prompt optimization.** Mneme does not rewrite prompts to be "better"; it blocks ones that violate governance.
- **Long-term conversational memory.** Not a chat history system.
- **Enterprise workflow orchestration.** Not a workflow engine.
- **Deployment governance.** Not a release-pipeline policy tool.
- **Runtime observability.** Not an APM, not a tracing layer.
- **Code-generation quality scoring.** Mneme does not rate the quality of generated code; it checks whether generation violated a recorded decision.
- **Auto-fixing code.** Mneme does not edit your code, ever. It blocks; the human or LLM fixes.

If a feature request maps onto this list, the answer is no — not "later," not "out of scope for now," but **not Mneme.**

---

## Design Partner Readiness

### Ready for
- Small-team or single-developer validation in real repos.
- Local repo governance trials with hand-authored decisions.
- Architectural drift prevention testing on AI-assisted workflows.
- Evaluation as part of an AI-assisted development setup (Claude Code, Cursor).
- Benchmark reproducibility audits — every PASS is reconstructible, the suite runs byte-identically.

### Not ready for
- Enterprise rollout.
- Org-wide policy enforcement.
- Compliance certification (SOC 2, ISO 27001, etc.).
- Multi-repo governance.
- Production-critical gating without human review of decisions.

The discipline shown by Step 3C — refusing to promote recall@1, pinning the tie-order, splitting symmetry into its own PR — is the credibility artifact. The benchmark numbers are evidence of that discipline, not the headline.

---

## Exit Criteria for Layer 1

Layer 1 exits when **all** of the following are true:

1. **Benchmark integrity stabilized.** Achieved at `e73ff7d`. Two-layer scoring, deterministic retrieval, structured-fixture path, regression pins.
2. **Deterministic enforcement validated.** Achieved at `e73ff7d`. recall@1=1.00 with explicit tie-order pinning; reproducible byte-for-byte.
3. **Real-world drift prevention demonstrated.** Open. Requires evidence from at least one external repo where a governed decision blocked a violation a developer would otherwise have shipped.
4. **Design-partner validation complete.** Open. Requires structured feedback from at least one team using Mneme on their own memory through the Claude Code or Cursor integration.
5. **Governance wedge validated.** Open. Requires evidence that "explicit recorded decisions, deterministically enforced, before generation" is a wedge users will adopt repeatedly.

Items 1 and 2 are met at the freeze. Items 3, 4, and 5 are the work of the next phase.

### Layer 2 transition

When Layer 1 exit criteria are all met, Layer 2 opens up:

- **Shared governance.** Multi-developer coordination on a single memory.
- **Remote sync.** Memory distributed beyond a single repo.
- **IDE/runtime integration.** Inline enforcement with real-time decision surfacing.
- **Org policy distribution.** Cross-repo, cross-team policy packs.

Layer 2 is **not** a continuation of Layer 1's benchmark work. It is a separate phase with its own charter, its own methodology, and its own freeze when it lands.

---

## Amendment Procedure

This document is frozen at `e73ff7d`. To amend it:

1. Open a PR titled `[layer1-freeze] <change>`.
2. Reference the specific section being amended.
3. Include a rationale anchored to one of: (a) a defect in this document's description of shipped behavior; (b) a charter amendment that has *already* been made elsewhere; (c) the close of an exit criterion.
4. Do **not** amend this document to retroactively justify a behavioral change. Behavioral changes get their own charter.

This procedure is the protection against premature roadmap expansion. The freeze is only meaningful if it is harder to move than the next attractive idea.
