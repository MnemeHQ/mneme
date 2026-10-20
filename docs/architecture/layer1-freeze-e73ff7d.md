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


> **Note (2026-08-24):** This section records the integration surface at the freeze commit. For current support status, see [docs/integrations/README.md](../integrations/README.md).

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

### Why benchmark expansion is frozen (amended 2026-08-24)

- Adding scenarios to push a metric is overfitting at this suite size.
- Adding adversarial or paraphrase scenarios is a charter-level methodology change.
- Adding scenarios designed to make a known-good decision PASS is the exact failure mode `rule-bench-retrieval-coupling` was written to prevent.
- The next legitimate benchmark work is data-only: populating `acceptable_decision_ids` on the existing seven scenarios.

**Authorized exception (2026-08-24).** By merged charter [#318](https://github.com/MnemeHQ/mneme/pull/318) ([charter document](../plans/2026-08-24-benchmark-fpr-charter.md)), a **separate enforcement-quality regression suite** is authorized alongside — never inside — the canonical suite, to measure enforcement false negatives and false positives after the observed dogfood defect fixed in #317:

- Scenario metadata `scenario_type: violation | benign` (absent → violation internally; unknown value → MALFORMED).
- A sixth verdict `FALSE_POSITIVE`, defined for benign scenarios only; it is a failing benchmark condition (exit 1). Violation-scenario verdict logic is unchanged.
- An exposure contract (`expected_exposed_decision_ids`): a benign PASS counts only when the governing rule was in actual enforcement scope; exposure telemetry is recorded outside Layer 1 objects.
- Partitioned reporting: violation catch rate vs false-positive rate, rendered separately from legacy aggregates; canonical terminal/Markdown/JSON output remains byte-for-byte unchanged (new fields emit only for scenarios explicitly declaring `scenario_type`).
- A dedicated frozen fixture memory for the suite; initial set is three violation guards + four benign controls, each incident-traceable.
- MALFORMED remains exit-0 suite-wide; uncheckable scenarios are counted and rendered, never silently dropped from visibility.

Unchanged by this exception: the canonical seven fixtures (byte-identical), the historical 7/7 headline, retrieval methodology, K=3, Layer 1 metric formulas and aggregation filters. New scenarios beyond incident-traceable regressions or documented governance gaps require their own charter.

### Why synthetic scenarios are acceptable at this stage

- Layer 1 proves a *mechanism*, not a *distribution*.
- Synthetic, hand-authored scenarios make the mechanism falsifiable: every PASS records the retrieved IDs and the triggering rule, and a reviewer can verify the chain end-to-end.
- Real-world distribution evidence is the job of the next phase (design-partner validation), not the benchmark.

### Categories covered (amended 2026-08-24)

- **Architecture** — storage backend boundary.
- **Scope** — provider boundary, feature boundary, infrastructure boundary.
- **Anti-patterns** — dependency creep, framework abstraction.
- **Retrieval** — retrieval complexity rules.

These four categories are the Layer 1 surface. Adding a fifth category requires a charter amendment.

The enforcement-quality suite authorized above is **not** a fifth Layer 1 category and does not extend this surface: it partitions Layer 2 enforcement quality (violation catch rate vs false-positive rate) into its own suite with its own fixture memory and opt-in reporting.

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

## Amendment — authorize DG1B1 decision applicability (2026-10-13)

> This section records a freeze amendment made under the Amendment Procedure
> below. It authorizes a future slice; it changes no current behavior.

**Change:** authorize implementation of the **DG1B1 decision applicability**
slice.

**Sections referenced:** the Freeze Anchor **Status** clause ("No behavioral
change to retrieval or enforcement without an explicit charter amendment") and
the Amendment Procedure below.

**Rationale (Amendment Procedure §3(b)).** A charter amendment has *already*
been made elsewhere. The [DG1B1 decision applicability
charter](../plans/2026-10-08-dg1b1-decision-applicability-charter.md) merged
first (PR #473), supplying the evidence and scope that ADR-031 §7 requires
before any context-dependent governance may be implemented. This amendment
authorizes the slice that merged charter opens; it does not itself change
behavior, and it is not used to retroactively justify a behavioral change.

**Governing authority:** accepted [ADR-031 — Decision Governance
Semantics](../adr/ADR-031-decision-governance-semantics.md) §4, §6–§8 and §11.

### What this amendment authorizes

DG1B1 is limited to canonical decision applicability, schema v2 migration,
validation, shared resolver semantics, and tests:

- the first persisted decision-applicability semantic — optional exact
  project-local `required_labels`, resolved by deterministic set containment as
  defined by the merged charter §2.1;
- the `mneme.decision-index/v2` schema and its **explicit** v1 → v2 migration
  (ADR-031 §8); no reader or writer migrates implicitly;
- v2 validation: closed semantic key sets, declared `semantic_features`
  (unsupported features rejected), one non-semantic `extensions` point, no
  speculative fields, and 0.10.x/v1 reader refusal of a v2 document;
- the shared resolver (`resolve_effective` / `resolve_change`) gaining the
  `not_applicable` cause for a lifecycle-active decision whose declared
  `required_labels` are absent from `GovernanceContext.labels`, while absent
  applicability preserves v1 global eligibility; and
- characterization, validation and mutation tests for the above.

The exact public authoring UX is not authorized here (merged charter §4).

### Explicitly preserved (unchanged by DG1B1)

1. **Existing `DecisionRetriever` behavior.** Five-field scoring and weights
   (`scope`=2.0, `constraints`=1.5, `anti_patterns`=1.5, `decision`=1.0,
   `rationale`=0.5), tokenization, stopword filter, the `len >= 4` token floor,
   K=3, and insertion-order tie-break are unchanged. Retrieval score never
   becomes applicability authority.
2. **Existing `ConflictDetector` behavior.** Structural conflict detection and
   its violation semantics are unchanged.
3. **Current runtime enforcement inputs.** Which decisions the CLI, enforcer,
   `ConflictDetector`, protection, Audit, readiness, hooks and MCP surfaces
   consume is unchanged. No runtime consumer reads decision applicability in
   DG1B1.
4. **ADR-020 rule applicability.** Typed-rule include/exclude path selectors
   remain rule-level and repository-path-only; ADR-020 semantics stay
   independent of decision applicability.
5. **Canonical authority and evidence identity.** [ADR-030](../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md)
   canonical persistence, version identity and stable rule lineage remain the
   sole durable authority, and [ADR-029](../adr/ADR-029-enforcement-evidence-binding-semantics.md)
   evidence binding with its fail-closed identity chain is unchanged. DG1B1
   adds no authority path beyond the explicit, validate-before-mutate
   Mneme-owned operation the merged charter permits.
6. **Existing benchmark methodology.** The canonical seven fixtures, the
   enforcement-quality suite, K=3, the Layer 1/2 metric formulas, aggregation
   filters, and byte-identical output remain frozen and unchanged.

### Not authorized by this amendment

- **DG1F runtime consumer convergence.** No CLI, enforcer, `ConflictDetector`,
  protection, Audit, readiness, hook or MCP surface may consume the new
  resolver result under this amendment. That requires its own merged charter
  where enforcement inputs change (ADR-031 §7).
- **DG1B2 waivers.** Waiver semantics remain separately gated on evidence and
  canonical target-binding (ADR-031 §12); v2 pre-creates no waiver field.
- **Data Engine.** The Data Engine is a separate repository and is not modified
  by this amendment or by DG1B1.

---

## Amendment — authorize DG1F-C1a report-only applicability preview (2026-10-13)

> This is an authorization for a **future, bounded implementation**, not a
> statement that CLI behavior has changed. It does not authorize applicability
> exclusions, trusted-context persistence, or broader DG1F convergence.

**Change:** Permit an **opt-in, report-only** applicability preview in
`mneme check` (DG1F-C1a) while keeping the enforced decision set, verdicts,
stdout, machine-readable JSON, exit codes and hook behavior unchanged.

**Sections referenced:** the Freeze Anchor **Status** clause ("No behavioral
change to retrieval or enforcement without an explicit charter amendment"),
the frozen retrieval / enforcement / benchmark invariants, and the Amendment
Procedure below.

**Rationale (Amendment Procedure §3(b)).** A distinct behavioral charter was
**already merged** before this amendment:
[DG1F-C1 applicability-only CLI charter](../plans/2026-10-13-dg1f-applicability-only-charter.md),
PR [#493](https://github.com/MnemeHQ/mneme/pull/493), squash
`96ec857e`. ADR-031 §11 (as amended by merged PR #492) permits a bounded
applicability-only DG1F increment before evidence-gated DG1B2. DG1B1 (#487)
supplied the canonical resolver and accepted real-repository offline case, but
not runtime consumption. This amendment authorizes **C1a only** under that
previously merged charter; no behavior change is retroactively justified.

**Governing authority:** accepted
[ADR-031](../adr/ADR-031-decision-governance-semantics.md) §4/§6–§7/§11,
[ADR-017](../adr/ADR-017-enforcement-scope-vs-retrieval-scope.md),
[ADR-020](../adr/ADR-020-explicit-path-applicability-for-typed-rules.md),
[ADR-029](../adr/ADR-029-enforcement-evidence-binding-semantics.md),
[ADR-030](../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md),
and the merged DG1F-C1 charter §2/§5a.

### Permitted C1a change — only `mneme check`

- Add an explicitly **opt-in**, repeatable
  `--applicability-preview <label>` CLI argument. Its labels are **caller
  assertions for display only**, never enforcement context or evidence of
  authority. They are not authenticated.
- For the preview only, use the *existing* canonical
  `resolve_effective(index, GovernanceContext(labels=...))`, over the same
  validated canonical memory snapshot as the ordinary CLI check, to show
  decision effectiveness and `not_applicable` causes. The preview does not
  become a second resolver or precedence path; absent applicability remains
  globally eligible.
- Render preview information **only on stderr**, explicitly marked
  **NON-AUTHORITATIVE**. If preview computation is unavailable, emit
  `PREVIEW UNAVAILABLE` on stderr. A preview failure never changes the
  ordinary enforcement verdict or exit code; ordinary enforcement failures
  retain their current handling.
- **Non-interference is mandatory.** For the same check input, compare the
  no-preview and preview invocations: the enforced decision corpus, rule
  evaluations, violations, retrieval ranking, **stdout**, complete
  `mneme.check/v1` JSON payload, exit codes and hook behavior must be
  identical. No decision is dropped because of preview labels. Keep
  ADR-017 enforcement tiers, ADR-020 rule-path selection, and canonical
  version/rule/evidence identities unchanged.
- No opt-in preserves all existing output and behavior, including for v1 and
  section-less memory. Preview unavailability on those inputs does not rewrite
  or implicitly migrate them.

### Validation gate for the later implementation PR

Before C1a implementation can merge, demonstrate the **five independent
acceptance requirements in the merged DG1F charter §5a**, including:
(1) exact default parity across v1/v2/section-less memory; (2) unchanged
enforcement, stdout, JSON, exit codes and hook outcomes with and without
preview; (3) stderr-only NON-AUTHORITATIVE and PREVIEW UNAVAILABLE output,
including error isolation; (4) spoofed labels cannot disable protection; and
(5) strict/warn, human/JSON, existing regressions and Layer 1 benchmark
compatibility. Reuse the committed, pinned GSA-TTS ADR-0028 test fixture;
add tests **outside** the frozen canonical benchmark fixture/methodology.
Pass full existing gate and applicable CI before any implementation merge.

### Explicitly not authorized

1. **DG1F-C1b enforcement exclusion.** No label source (argv, env, OS, source
   text, hook/MCP inputs, Data Engine or local file assertions) can exclude an
   otherwise active decision. The merged charter requires a separately
   authorized persisted canonical-context semantic and independently
   verifiable approved revision, substitution protection, controlled context
   selection, an additional behavioral charter/freeze amendment, and
   blocking-seam validation before C1b.
2. Any change to `DecisionRetriever` scoring, top-K / tie order, enforcement
   rule matching, `ConflictDetector`, ADR-020 applicability, typed rules,
   protection, Audit, readiness, hooks, MCP, or benchmark fixtures/methodology.
3. New persisted fields or schema, new authority writers, implicit v1→v2
   migration, new waiver representation/semantics, Data Engine changes,
   extra CLI/MCP capabilities beyond the bounded non-authoritative preview,
   or claims of end-to-end fail-closed enforcement.

The existing DG1B1 freeze amendment remains unchanged; its DG1F prohibition
still governs **all runtime consumers other than this specifically authorized
C1a preview**.

---

## Amendment — authorize the #260 verdict-consistency correction (2026-10-14)

> This is an authorization for a **bounded defect correction**, not a statement
> that behavior has changed. It does not authorize availability policy,
> fail-closed enforcement, applicability exclusions, or waivers.

**Change:** Permit the **verdict-consistency correction** (issue #260)
implemented in PR #484: an integration trusts a checker result only when the
payload envelope, violation records, aggregate, requested `mode` and process
exit code are mutually coherent, and otherwise **fails open** with a diagnostic.
This changes *which results Mneme trusts*, not the fail-open policy.

**Sections referenced:** the Freeze Anchor **Status** clause ("No behavioral
change to retrieval or enforcement without an explicit charter amendment") and
the Amendment Procedure below.

**Rationale (Amendment Procedure §3(b)).** A distinct behavioral charter was
**already merged** before this amendment:
[Reliable Enforcement C1 — verdict-consistency defect-correction charter](../plans/2026-10-14-reliable-enforcement-c1-verdict-consistency-charter.md),
PR [#503](https://github.com/MnemeHQ/mneme/pull/503), squash `272632ca`. That
charter authorizes only the #484 correction and explicitly preserves the items
below; this amendment supplies the Layer 1 freeze authorization it requires. No
behavior change is retroactively justified.

**Governing authority:** accepted
[ADR-021](../adr/ADR-021-shell-preflight-and-stop-session-delta.md) (fail-open
transport policy),
[ADR-017](../adr/ADR-017-enforcement-scope-vs-retrieval-scope.md),
[ADR-020](../adr/ADR-020-explicit-path-applicability-for-typed-rules.md),
[ADR-023](../adr/ADR-023-canonical-decision-index-and-runtime-projection-boundary.md),
[ADR-029](../adr/ADR-029-enforcement-evidence-binding-semantics.md),
[ADR-030](../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md),
[ADR-031](../adr/ADR-031-decision-governance-semantics.md), and the merged C1
charter.

### Authorized change — verdict trust only

- Trust a checker result only when the requested `mode`, the violation records,
  the aggregate verdict/violation agreement, and the process exit code are
  mutually coherent; an incoherent result **fails open** with a diagnostic that
  never echoes proposed content.
- Route every shipped consumer of `parse_verdict` through the coherence wrapper
  with the mode it requested; an unhashable verdict value no longer raises.

### Explicitly preserved (unchanged)

1. **Fail-open policy (ADR-021).** Every untrusted, unparseable, incomplete or
   contradictory result still fails open; no fail-closed or availability-strict
   mode is introduced.
2. **strict/warn semantics (ADR-017, ADR-020)** for coherent verdicts.
3. **Canonical authority (ADR-023, ADR-030) and evidence identity (ADR-029,
   ADR-031).**
4. **Retrieval, `ConflictDetector`, enforcer, rule matching.**
5. **`mneme.check/v1` payload and CLI exit codes.**
6. **Frozen benchmark fixtures and methodology.**
7. **`.mneme/project_memory.json`.**

### Not authorized by this amendment

- ADR-033 availability states or any availability policy; the proposed
  ADR-033 / C0 charter (#483) remains separate and proposed.
- Missing-memory eligibility/witness changes.
- Fail-closed enforcement, new schema, CLI/MCP surface, or new engine.
- DG1F-C1b applicability exclusion; DG1B2 waivers.
- Any claim that a returned block is honoured by the host harness.

The existing DG1B1 and DG1F-C1a freeze amendments remain unchanged.

---

## Amendment — authorize T-08 direct-write target-path memory anchoring, slice 1 (2026-10-15)

> This is an authorization for a **bounded defect correction at one
> boundary**, not a statement that behavior has changed. It does not authorize
> discovery-semantics changes, availability policy, fail-closed enforcement,
> or any other T-08 follow-up.

**Change:** Permit **slice 1** of the T-08 correction: at the Claude Code
direct-write boundary (`Edit|Write|MultiEdit`, `handle_event` in
`mneme/integrations/claude_code/hook.py`), the **existing, unmodified**
`find_memory` walk starts at the resolved target's directory instead of the
hook payload `cwd`. This changes *where the existing walk starts at one
boundary*, not how memory is discovered.

**Sections referenced:** the Freeze Anchor **Status** clause ("No behavioral
change to retrieval or enforcement without an explicit charter amendment") and
the Amendment Procedure below.

**Rationale (Amendment Procedure §3(b)).** A distinct behavioral charter was
**already merged** before this amendment:
[T-08 direct-write target-path memory anchoring (slice 1) defect-correction charter](../plans/2026-10-15-t08-target-path-memory-resolution-charter.md),
PR [#514](https://github.com/MnemeHQ/mneme/pull/514), squash `dcaee389`. It
rests on the live-confirmed T-08 defect recorded in the
[T-08 evidence record](../validation/dg1f-t08-cwd-memory-selection-2026-10-15.md)
(PR [#513](https://github.com/MnemeHQ/mneme/pull/513), squash `98dc4771`): a
session rooted in a sibling repository let a forbidden edit land in a
protected repository, governed by the sibling's memory with a complete PASS
and no diagnostic. Charter §10 requires this amendment before implementation.
This amendment authorizes **slice 1 only** (charter §3) under that previously
merged charter; no behavior change is retroactively justified.

**Governing authority:** accepted
[ADR-021](../adr/ADR-021-shell-preflight-and-stop-session-delta.md) (fail-open
transport policy),
[ADR-017](../adr/ADR-017-enforcement-scope-vs-retrieval-scope.md),
[ADR-020](../adr/ADR-020-explicit-path-applicability-for-typed-rules.md)
(policy root and rule-path applicability),
[ADR-023](../adr/ADR-023-canonical-decision-index-and-runtime-projection-boundary.md),
[ADR-029](../adr/ADR-029-enforcement-evidence-binding-semantics.md),
[ADR-030](../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md),
[ADR-031](../adr/ADR-031-decision-governance-semantics.md), the merged C1
verdict-consistency charter (#260), and the merged T-08 slice-1 charter.

### Authorized change — direct-write walk start only

- In `handle_event`, replace the start directory of the existing
  `find_memory` call (today `Path(event.cwd or ".")`) with the parent directory
  of the resolved target. Resolve the target exactly as `_resolve_target` does
  today (a relative `file_path` is anchored to the payload `cwd`; that is path
  resolution, not memory selection), then fully resolve it with
  `Path(target).resolve()` (non-strict) so a final-component symlink is
  followed.
- Pass the same resolved target to `mneme check` as `--target-path`, as today.
- When no target resolves (no `file_path`, or a relative target with an empty
  payload `cwd`), behavior is unchanged from `main`.
- Add the charter §7.1 offline tests, including the containment property
  (the selected memory's policy root is an ancestor of the resolved target)
  and the characterization cases asserted unchanged from `main`.

No other code path is authorized.

### Explicitly preserved (unchanged)

This restates merged charter §6.

1. **Default fail-open (ADR-021).** Every untrusted, incomplete,
   missing-memory or error outcome still fails open; no fail-closed or
   availability behavior is introduced.
2. **The #260 coherence rules (PR #484).** `assess_verdict` stays the only
   gate through which a result is trusted; its rules are unchanged and the
   #484 test set stays green unmodified.
3. **Discovery semantics (`find_memory`).** `find_memory` is not modified.
   `MNEME_MEMORY` precedence is unchanged: when set, it wins exactly as today,
   regardless of the start directory. The parent-directory fallback outside a
   repository is unchanged. Nested-memory behavior is unchanged: the nearest
   `.mneme/project_memory.json` walking up from the start directory governs,
   with no repository-root detection and no outermost-memory rule.
4. **strict/warn semantics (ADR-017, ADR-020)** and path-selector semantics.
5. **The `mneme check` CLI, its exit codes, and the `mneme.check/v1`
   payload.** No new field.
6. **Bash, SessionStart and Stop** memory selection and behavior.
7. **Canonical decision authority and evidence identity** (ADR-023, ADR-029,
   ADR-030, ADR-031); retrieval, `ConflictDetector`, the enforcer, rule
   matching.
8. **Frozen benchmark fixtures and methodology; `.mneme/project_memory.json`.**

### Not authorized by this amendment

- **Charter §8 deferred items D1–D7:** D1 Bash class-A preflight; D2
  SessionStart/Stop baseline and per-file memory; D3 the `mneme check`
  out-of-policy-root outcome, any `mneme.check/v1` field for it, and the
  matching #260 coherence extension; D4 nested-memory policy; D5
  repository-boundary or parent-directory-fallback removal; D6 `MNEME_MEMORY`
  precedence; D7 other integrations that select memory from `cwd` or a project
  directory. Each needs its own charter (or reviewed charter amendment) and its
  own `[layer1-freeze]` amendment.
- **ADR-033** acceptance or change; the proposed ADR-033 / C0 charter (#483)
  remains separate and proposed.
- Any fail-closed enforcement, availability state or availability policy,
  operational refusal, or missing-memory eligibility, witness or declaration.
- Hook registration or coverage changes; any new schema, CLI flag, MCP surface
  or engine.
- Any claim of host prevention beyond the configuration re-probed under
  charter §7.2 (Claude Code 2.1.202 on Windows, `claude -p`, the L4 setup),
  and any claim about the agent-steered `cd` pivot.

The existing DG1B1, DG1F-C1a and #260 freeze amendments remain unchanged.

---

## Amendment Procedure

This document is frozen at `e73ff7d`. To amend it:

1. Open a PR titled `[layer1-freeze] <change>`.
2. Reference the specific section being amended.
3. Include a rationale anchored to one of: (a) a defect in this document's description of shipped behavior; (b) a charter amendment that has *already* been made elsewhere; (c) the close of an exit criterion.
4. Do **not** amend this document to retroactively justify a behavioral change. Behavioral changes get their own charter.

This procedure is the protection against premature roadmap expansion. The freeze is only meaningful if it is harder to move than the next attractive idea.
