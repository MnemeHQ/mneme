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

## Amendment — authorize ADR-033 C2a PreToolUse availability routing (2026-10-20)

> This is an authorization for **routing, classification and diagnostics at one
> boundary**. It does not authorize any availability refusal, verifier,
> enrollment or revocation, fail-closed enforcement, or any change to other
> boundaries.

**Change:** at the Claude Code direct-write boundary (`Edit|Write|MultiEdit`,
`handle_event` in `mneme/integrations/claude_code/hook.py`), detect a local
`.mneme/availability.json` declaration before the memory early return. Without
a declaration, behavior is byte-identical to `main`. With one, run today's
check path unchanged and emit a diagnostic that names
`AUTHORIZATION_UNVERIFIABLE(VERIFIER_CONFIG_MISSING)`, the evaluation state,
and any SS-3 mismatch or partial-evaluation violations.

**Sections referenced:** the Freeze Anchor **Status** clause ("No behavioral
change to retrieval or enforcement without an explicit charter amendment") and
the Amendment Procedure below.

**Rationale (Amendment Procedure §3(b)).** A distinct behavioral charter was
**already merged** before this amendment:
[Reliable Enforcement C2a PreToolUse availability routing charter](../plans/2026-10-20-reliable-enforcement-c2a-availability-routing-charter.md),
PR [#574](https://github.com/MnemeHQ/mneme/pull/574), squash `c49d7008`, under
accepted [ADR-033](../adr/ADR-033-opt-in-fail-closed-enforcement.md) (PR
[#483](https://github.com/MnemeHQ/mneme/pull/483), squash `78459d1a`). Charter
§9 requires this amendment before implementation. No behavior change is
retroactively justified.

**Governing authority:** accepted ADR-033, ADR-021 (fail-open transport
policy), ADR-017, ADR-020, ADR-029, ADR-030, ADR-031; the merged C1 (#260)
verdict-consistency and T-08 slice-1 charters; the merged C2a charter.

### Authorized change — C2a only (charter §3)

- **Declaration detection** (charter §3.1): before the memory early return in
  `handle_event`, walk up from the T-08 slice-1 start directory to the first
  ancestor containing `.mneme/`, and look for `.mneme/availability.json`
  there, whether or not memory exists. `MNEME_MEMORY` is not consulted for
  this.
- **Declaration format v1** (charter §3.2): the three required keys only;
  unknown keys preserved and ignored; any other content is "present but
  invalid".
- **Verifier interface** (charter §3.3) whose only implementation returns
  `AUTHORIZATION_UNVERIFIABLE(VERIFIER_CONFIG_MISSING)`, with no network
  access and no git configuration read. Other outcomes are reachable only
  through a test seam.
- **Evaluation-state classifier** (charter §3.4) built on `assess_verdict`,
  internal only.
- **Historical payloads and mixed partial results** (charter §§3.5, 3.6):
  diagnostics on the declaration path only.
- **Diagnostics** (charter §3.7) on the existing stderr channel, claimed as
  emitted, not delivered.
- **The charter §4 regression matrix**, including byte-identical default-open
  parity (P1) and no network activity (P2).

No other code path is authorized. **No C2a code path may produce an
availability refusal.**

### Explicitly preserved (unchanged)

This restates merged charter §5.

1. **No declaration → today's behavior,** byte-identical output, the same exit
   codes, and zero network activity.
2. **Default fail-open (ADR-021)** for every untrusted, incomplete,
   missing-memory or error outcome. A trusted complete strict `FAIL` still
   blocks exactly as today.
3. **The `mneme check` CLI,** its output, exit codes, the `mneme.check/v1`
   payload, and the malformed-memory crash path (CI1.4 §7 condition 4).
4. **`find_memory`,** `MNEME_MEMORY` precedence and T-08 slice-1 selection.
5. **strict/warn semantics** and the #260 coherence rules in `assess_verdict`.
6. **Bash, SessionStart and Stop** behavior.
7. **Canonical decision authority** (ADR-030 §1). The declaration holds no
   decisions or rules.
8. **Frozen benchmark fixtures and methodology; `.mneme/project_memory.json`.**

### Not authorized by this amendment

- Any availability refusal; any verifier that contacts a remote or reads git
  configuration; any enrollment, issuance or revocation command; the C2b
  declaration fields. These belong to a C2b charter and its own amendment.
- Live host validation (ADR-033 gate C3) and CI implementation (gate C4).
- Any change to other boundaries or integrations, CI workflows, rulesets or
  Actions policy.
- Any claim that a diagnostic is delivered or that a repository is protected
  by C2a. The Architecture A limitation stands: **deleting the local
  declaration can silently disable opt-in fail-closed protection.**

The existing DG1B1, DG1F-C1a, #260 and T-08 slice-1 freeze amendments remain
unchanged.

---

## Amendment — authorize ADR-033 C2b verified availability authorization (2026-10-21)

> This authorizes **one verifier, one declaration extension, three authority
> commands and one refusal route at one boundary**. It does not authorize
> Architecture B, any cache, credential use, forge API, CI change, or any
> change to other boundaries.

**Change:** at the Claude Code direct-write boundary (`Edit|Write|MultiEdit`,
`handle_event` in `mneme/integrations/claude_code/hook.py`), replace the C2a
verifier stub with a live verifier of the remote default-branch tip, per
charter §§3-5. Refuse a supported direct write with an operational
UNEVALUATED diagnostic only when authorization is verified as `AUTHORIZED`
and a charter §5.3 R3-R6 condition holds. Add
`mneme availability status|authorize|revoke` per charter §6. Without a local
declaration, behavior is byte-identical to `main`.

**Sections referenced:** the Freeze Anchor **Status** clause ("No behavioral
change to retrieval or enforcement without an explicit charter amendment") and
the Amendment Procedure below.

**Rationale (Amendment Procedure §3(b)).** A distinct behavioral charter was
**already merged** before this amendment:
[Reliable Enforcement C2b verified availability authorization charter](../plans/2026-10-21-reliable-enforcement-c2b-availability-authorization-charter.md),
PR [#587](https://github.com/MnemeHQ/mneme/pull/587), squash `90dc7cab`,
accepted with every §16 decision pinned. It sits under accepted
[ADR-033](../adr/ADR-033-opt-in-fail-closed-enforcement.md) (PR
[#483](https://github.com/MnemeHQ/mneme/pull/483), squash `78459d1a`) and
follows C2a (PR [#576](https://github.com/MnemeHQ/mneme/pull/576), squash
`72b6d04a`). Charter §14 requires this amendment before implementation. No
behavior change is retroactively justified.

**Governing authority:** accepted ADR-033 (Architecture A), ADR-021, ADR-022,
ADR-029, ADR-030; the merged C1 (#260) verdict-consistency, T-08 slice-1, C2a
and C2b charters.

### Authorized change — C2b only (charter §§3-9)

- **Verifier** (charter §3): runs only when a local declaration is present.
  `origin` URL from the repository's own config file; HTTPS only; Git run in
  a temporary bare repository with a constructed environment (no system or
  global config, proxies, `insteadOf`, credential helpers or remote-tracking
  refs); revision is the live remote `HEAD` symref tip, fetched by object id;
  one 15-second budget; reasons from ADR-033 §4.3's closed set; no persistent
  cache.
- **Declaration extension** (charter §4): additive `repository` and
  `authority.events` fields on `mneme.availability/v1`; hash-chained,
  append-only events ordered by position, never by timestamps; activation
  evidence bound by `activated_at` and the protected decision set; review
  fields recorded as attested, never presented as verified.
- **State resolution** (charter §5): `AUTHORIZED` and `REVOKED` from the tip's
  event list; first-parent history walked only when the tip has no
  declaration, for `VERIFIED_ABSENT` or RR-7 `EVIDENCE_INVALID`; local
  relation `MATCH|BEHIND|DIVERGES|INVALID`; routing R0-R8.
- **Authority operations** (charter §6): `mneme availability status` is
  read-only. `authorize` and `revoke` require their respective live
  authorization preconditions and interactive TTY confirmation. Only the
  mutating commands write `.mneme/availability.json`. None commits, pushes,
  merges or modifies canonical memory.
- **Hook integration** (charter §7): the default verifier replaced; one
  `local_relation` input added to `routing_refuses`; the verifier seam stays
  test-only; the in-process benchmark transport documented as unsupported
  under `AUTHORIZED`.
- **Diagnostics** (charter §8): operational UNEVALUATED refusals that never
  carry `architectural decision violated` or submitted content, claimed as
  emitted, not delivered.
- **The charter §9 regression matrix** (V1-V18, H1-H15, A1-A5) and the
  charter §12 acceptance evidence, including the latency measurement.

No other code path is authorized. **The only new refusals are charter §5.3
R3-R6 under a verified `AUTHORIZED` baseline.**

### Explicitly preserved (unchanged)

This restates merged charter §10.

1. **No declaration → today's behavior,** byte-identical output, the same exit
   codes, and zero verifier calls.
2. **`REVOKED`, `VERIFIED_ABSENT` and `AUTHORIZATION_UNVERIFIABLE` never
   refuse on availability.** A trusted complete strict `FAIL` still blocks
   exactly as today under every authorization state.
3. **The `mneme check` CLI,** its output, exit codes, the `mneme.check/v1`
   payload, and the malformed-memory crash path (CI1.4 §7 condition 4).
4. **`find_memory`,** `MNEME_MEMORY` precedence, T-08 slice-1 selection, and
   C2a declaration discovery and policy-root rule.
5. **strict/warn semantics,** `assess_verdict`, `DecisionRetriever`,
   `ConflictDetector` and ADR-020 applicability.
6. **Bash, SessionStart and Stop** behavior (ADR-021).
7. **Canonical decision authority** (ADR-030 §1), `setup → active` and
   `mneme protect activate`. The declaration holds no decisions or rules.
8. **Frozen benchmark fixtures and methodology; `.mneme/project_memory.json`.**

### Not authorized by this amendment

- Architecture B: any host enrollment record, high-water mark or other trusted
  state outside the repository; any persistent cache.
- Any verification trigger other than the local declaration.
- Credential helpers, tokens, SSH or any non-HTTPS verifier transport; forge
  API calls.
- Refusals outside `PreToolUse` `Edit|Write|MultiEdit`; Bash class-A handling.
- Live host validation (ADR-033 gate C3) and CI implementation (gate C4).
- Any change to other boundaries or integrations, CI workflows, rulesets or
  Actions policy.
- Any claim beyond charter §13. C2b's evidence is hook-level only, and the
  Architecture A limitation stands: **deleting the local declaration can
  silently disable opt-in fail-closed protection.**

The existing DG1B1, DG1F-C1a, #260, T-08 slice-1 and C2a freeze amendments
remain unchanged.

## Amendment — authorize ADR-034 G1 whole-file numeric audit (2026-10-22)

> This authorizes **one new typed rule, `FORBID_NUMERIC_ABOVE`, evaluated only
> as a whole-file Python audit (G1)**, together with the schema, CLI and
> result-consumer extensions it needs and explicit `ConflictDetector`
> noncoverage diagnostics. It does not authorize pre-write numeric
> enforcement, CI, agent orchestration, or any availability-policy change.

**Change:** implement `FORBID_NUMERIC_ABOVE` exactly as specified by the
accepted behavioral charter:

- authoring, canonical persistence and identity under schema v2 with the
  `numeric_upper_bound_rule` semantic feature (§4);
- the deterministic matcher (§5);
- per-rule matcher status, evidence binding, and an additive
  `mneme.check/v1` payload (§6);
- the `mneme check --source-file` complete-source audit transport, under the
  single ADR-020 policy root (§3);
- consumer-trust adaptation in the Claude Code hook, the Agent SDK and
  LangChain, so that trusted violations stay actionable alongside matcher
  incompleteness (§6);
- `ConflictDetectionResult.noncoverage`, which does not change
  `evaluation_complete` (§7).

Checks that involve no numeric rule must produce byte-identical
`mneme.check/v1` payloads and exit codes.

**Sections referenced:** the Freeze Anchor **Status** clause ("No behavioral
change to retrieval or enforcement without an explicit charter amendment") and
the Amendment Procedure below.

**Rationale (Amendment Procedure §3(b)).** Two charter-level decisions were
**already made** before this amendment:

- [ADR-034](../adr/ADR-034-static-numeric-upper-bound-typed-rule.md), accepted
  as a design contract with its evaluation criteria frozen (PR
  [#594](https://github.com/MnemeHQ/mneme/pull/594), squash `2298c946`). Its
  held-out corpus v1 is frozen (PR
  [#600](https://github.com/MnemeHQ/mneme/pull/600), squash `e2998742`).
- The distinct
  [ADR-034 G1 behavioral charter](../plans/2026-10-22-adr-034-g1-behavioral-charter.md),
  accepted by the owner after two architecture reviews and merged (PR
  [#602](https://github.com/MnemeHQ/mneme/pull/602), squash `83af67ba`).

Charter §1 and §9 require this amendment before implementation. No behavior
change is retroactively justified.

**Pinned regressions:** charter §8.C items 1–9. They cover:

- old-reader and downgrade refusal;
- golden rule IDs;
- the R1–R18 numeric vectors;
- byte-identical no-numeric payloads;
- the hook, Agent SDK and LangChain mixed-result matrix, including the
  closed-availability refusal;
- `ConflictDetector` noncoverage with `evaluation_complete` unchanged.

Held-out scoring (§8.D) runs only after the implementation commit is frozen,
under a separate owner authorization.

**Recorded operating consequence (charter §6, F2).** At the edit gate, any
applicable numeric rule yields `MATCHER_UNEVALUATED` /
`INCOMPLETE_SOURCE_INPUT`, so a repository with an authorized closed
availability declaration (ADR-033/C2b) refuses every nonempty edit on an
APPLIED numeric path as `EVALUATION_INCOMPLETE`. **`FORBID_NUMERIC_ABOVE` must
not be activated on such paths until a separate G2 authorization.**

### Not authorized by this amendment

- Pre-write numeric denial or any G2 edit-gate numeric evaluation.
- CI integration or workflow changes.
- Any ADR-033 availability-policy change, or any exception added for numeric
  rules.
- Agent orchestration, MCP enforcement, or new numeric forms (keyword
  matching, exclusive bounds, unit conversion, constant propagation) or other
  languages.
- Changes to `DecisionRetriever` ranking, `ConflictDetector` response-text
  matching, governance authority, or memory import of ADR-034.
- Any enforcement or production claim before independent held-out scoring
  passes.
- Implementation by any session or person with access to the held-out corpus,
  its answer key, or the corpus-author or orchestrating session transcripts.

The existing DG1B1, DG1F-C1a, #260, T-08 slice-1, C2a and C2b freeze
amendments remain unchanged.

---

## Amendment — authorize ADR-033 C2b Amendment 1: UNVERIFIABLE diagnostic delivery (2026-10-22)

> This authorizes **one additional stdout output at one boundary**. It does
> not authorize any refusal, permission or exit-code change, any other
> availability state, `systemMessage`, or any warn-mode change beyond the
> charter's 17.3 append.

**Change:** at the Claude Code direct-write boundary (`handle_event`, the
`emit_availability` path in `mneme/integrations/claude_code/`), when a local
declaration is present, authorization is `AUTHORIZATION_UNVERIFIABLE` and the
hook exits 0, write exactly one stdout object
`{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": <17.2 text>}}`.
In the warn-mode `defer` case, append the 17.2 text to the existing
`permissionDecisionReason` instead, still as one object. Exit codes, stderr
and permission behavior are unchanged. Without a declaration, behavior is
byte-identical to `main`.

**Sections referenced:** the Freeze Anchor **Status** clause ("No behavioral
change to retrieval or enforcement without an explicit charter amendment") and
the Amendment Procedure below.

**Rationale (Amendment Procedure §3(b)).** A distinct charter amendment was
**already merged** before this amendment:
[C2b charter section 17](../plans/2026-10-21-reliable-enforcement-c2b-availability-authorization-charter.md),
PR [#605](https://github.com/MnemeHQ/mneme/pull/605), squash `faec11cb`. It
follows the C3 Batch R evidence record
([#601](https://github.com/MnemeHQ/mneme/pull/601), squash `be88c133`;
R-1 Edit-2, finding F-R2) and the F-R2 assessment
([#604](https://github.com/MnemeHQ/mneme/pull/604), squash `f774dbde`), whose
Option 1 the owner accepted on 2026-10-22, under accepted
[ADR-033](../adr/ADR-033-opt-in-fail-closed-enforcement.md). Charter §17.8
requires this amendment before implementation. No behavior change is
retroactively justified.

**Governing authority:** accepted ADR-033 §4.3 ("a visible proceed") and §7
(no submitted content in diagnostics); the merged C2a and C2b charters,
including C2b section 17.

### Authorized change — C2b Amendment 1 only (charter §§17.2-17.4)

- **Trigger** (17.2): a local declaration is present, the verification result
  is `AUTHORIZATION_UNVERIFIABLE` (any reason), and the hook exits 0 on that
  invocation.
- **Output** (17.2): exactly one stdout JSON object with
  `hookSpecificOutput.hookEventName = "PreToolUse"` and `additionalContext`
  set to the fixed, factual, ASCII-only 17.2 text (reason code; one extra
  sentence on an SS-3 mismatch). No `permissionDecision`, no
  `permissionDecisionReason`, no `systemMessage`. The text never contains
  submitted content, decision text, rule values, triggers or paths, and never
  states or implies the edit was checked, verified, compliant or safe.
- **Warn-mode `defer` case** (17.3): one object only. The existing warn-mode
  object is kept as it is, with the 17.2 text appended to
  `permissionDecisionReason` on a new line, and no `additionalContext`.
  Delivery to the model is not claimed for this case.
- **The charter §17.4 regression matrix** (A1-A10), including byte-identical
  no-declaration parity (C2a P1/P2) and unchanged refusals.

No other code path is authorized.

### Explicitly preserved (unchanged)

This restates merged charter §17.6.

1. **No declaration → today's behavior,** byte-identical output, the same exit
   codes, and zero verifier calls.
2. **ADR-033 Architecture A, including F-R1:** an unverifiable baseline still
   produces no availability refusal. There is no cache, no retry, no grace
   window and no Architecture B.
3. **All refusals and exit codes** (C2b §5.3), **every existing stderr line,**
   and **permission behavior.** No permission decision is added, removed or
   altered.
4. **`AUTHORIZED`, `REVOKED` and `VERIFIED_ABSENT`** outputs.
5. **Warn-mode output,** except the 17.3 append.
6. **`mneme check`,** the verifier, the declaration schema, and the
   `mneme availability` commands.
7. **Bash, SessionStart and Stop** behavior (ADR-021).
8. **Frozen benchmark fixtures and methodology; `.mneme/project_memory.json`.**

### Not authorized by this amendment

- Any `systemMessage` (user-facing) output.
- `additionalContext` for any state other than `AUTHORIZATION_UNVERIFIABLE`.
- Any warn-mode change beyond the 17.3 append, including the separate finding
  F-W1 (`defer` semantics).
- Any claim that F-R2 is closed before the charter §17.5 live proof on Claude
  Code 2.1.303. That proof, and its harness change, are authorized
  separately.
- Any C3 run, R-1 re-run or C4 work. The #601 record is never rewritten.

The existing DG1B1, DG1F-C1a, #260, T-08 slice-1, C2a, C2b and ADR-034 G1
freeze amendments remain unchanged.

---

## Amendment — record the ADR-034 G1 F-1 conformance correction (#613) (2026-10-22)

> This is a **record**, not a new authorization. It states that #613 brought
> shipped behavior into line with the ADR-034 G1 amendment above, after this
> document's description of that amendment's charter became inaccurate. It
> authorizes no further behavior.

**What happened.** The ADR-034 G1 amendment authorizes implementing
`FORBID_NUMERIC_ABOVE` "exactly as specified by the accepted behavioral
charter", citing that charter at squash `83af67ba`. That charter's §3 item 4
conditioned the non-source result on "an APPLIED numeric rule". It therefore
let `mneme check --input <file>` without `--target-path` return a clean PASS
when the input file's own path was EXCLUDED, which contradicts accepted
ADR-034 §6 ("never a clean result"). Held-out scoring found this as F-1
([results record](../validation/adr-034-g1-heldout-scoring-2026-10-22.md),
#612, squash `f25f0e84`).

PR [#613](https://github.com/MnemeHQ/mneme/pull/613) (squash `b0dc1a14`),
owner-approved, corrected it:

- in `mneme/enforcer.py` and `mneme/cli.py`, for `--input` without
  `--target-path`, every numeric rule yields `MATCHER_UNEVALUATED` /
  `INCOMPLETE_SOURCE_INPUT`, whatever the input path's applicability;
- in the shared trust validator (`mneme/integrations/claude_code/hook.py`,
  also used by the Agent SDK and LangChain), that record is accepted on an
  EXCLUDED or UNKNOWN trace only in that case, and contradictory payloads stay
  untrusted;
- a dated erratum to the charter's §3 item 4 records the correction.

**Sections referenced:** the ADR-034 G1 amendment above, the Freeze Anchor
**Status** clause, and the Amendment Procedure below.

**Rationale (Amendment Procedure §3(a) and §3(b)).**

- **(a)** The G1 amendment's description of the authorized behavior relied on
  charter text that was defective against ADR-034 §6, the governing contract.
  This record corrects that description.
- **(b)** The charter correction was already made, in the §3 item 4 erratum
  merged with #613.

**On Amendment Procedure §4.** #613 merged before this record. This entry
does not justify a new behavioral change after the fact. The corrected
behavior is the behavior ADR-034 §6 already required, and the G1 amendment
already authorized implementing ADR-034. Whether that reading satisfies §4 is
the owner's decision when merging this record.

**Verification (from #613, not re-run here):** public regression tests only.
The F-1 behavior has **no** blind held-out evidence. G1 stays FAIL, and sealed
v1 is not re-scored. Independent validation of the corrected implementation
is planned separately as ADR-034 M4.

### Explicitly preserved (unchanged by #613)

1. `--input` **with** `--target-path`: APPLIED is non-source, and EXCLUDED
   stays EXCLUDED with no matcher record.
2. `--source-file` behavior.
3. `FORBID_LITERAL` behavior and identities.
4. Payloads and exit codes of checks involving no numeric rule, which stay
   byte-identical.
5. Gate surfaces (hook, Agent SDK, LangChain): they always pass
   `--target-path`, so their behavior is unchanged.

### Recorded consequence

With numeric rules in memory, `mneme check --input` without `--target-path`
exits 2 for every input file, including a decision's own policy source. This
repository's memory contains no numeric rule today.

### Not authorized by this record

- Any behavior beyond #613 as merged.
- G2 pre-write numeric evaluation, CI integration, any ADR-033
  availability-policy change, or new numeric forms.
- Any blind-validation, enforcement or production claim for the corrected
  implementation.
- Re-scoring or reuse of sealed v1.

The existing DG1B1, DG1F-C1a, #260, T-08 slice-1, C2a, C2b, ADR-034 G1 and
C2b Amendment 1 freeze amendments remain unchanged.

---

## Amendment — authorize ADR-034 G2-1 pre-write numeric check for new-file Write (2026-10-24)

> This authorizes **one bounded G2 slice**: a pre-write
> `FORBID_NUMERIC_ABOVE` check for a Claude Code `Write` that creates a new
> `.py` file whose target path the checker has verified absent. It covers
> the new check input, hook routing, consumer-trust rules and evidence the
> slice needs. It does not authorize existing-file delta attribution, CI,
> other mutation surfaces, any availability-policy change, or any
> enforcement claim before independent validation passes.

**Change:** implement exactly what the accepted
[ADR-034 G2-1 behavioral charter](../plans/2026-10-24-adr-034-g2-1-behavioral-charter.md)
specifies:

- **The new check input (§3).** `mneme check --proposed-new-file <carrier>
  --target-path <P>`, a third member of the required input group.
  - The checker establishes ADR-034 §6a preconditions 1–4 itself: verified
    absence, no link components, inside the policy root, `.py`.
  - If any of those fail, the result is the legacy `--input` result,
    byte-identical.
  - An invalid UTF-8 carrier (precondition 5) is an operational error.
  - The input has its own target-binding guard.
  - The subject is relabelled `proposed_new_source` only when a numeric rule
    is `APPLIED`. Otherwise the result is byte-identical to `--input` on the
    same carrier.
- **Claude Code `PreToolUse` routing for `Write` only (§4).**
  - A dedicated `lstat` absence probe, a `.py` target, and content that
    encodes strictly as UTF-8 are all required.
  - One checker call per event.
  - The routed carrier holds exactly `content.encode("utf-8")`, written in
    binary mode. This is the authorized, routed-only correction of today's
    text-mode line-ending handling (ADR-034 §7a). No hook-level historical
    parity is claimed for routed events whose content contains CR.
  - Routed diagnostic wording comes through a keyword-only caller option
    whose default keeps today's text.
  - Every unrouted event is unchanged.
- **Consumer trust (§5).**
  - A keyword-only `expected_input` parameter on the shared `assess_verdict`.
    Its default keeps every existing caller's coherent results unchanged:
    the Agent SDK/LangChain, `antigravity`, `codex_cli`, `hermes`, `kiro`,
    and the hook's own unrouted, Stop, Bash and rename calls.
  - Subject-kind / matcher-reason coherence rules.
  - Digest and path joins for routed events.
- **Evidence (§6).**
  - A host-event binding record per routed event, with a **mandatory** pinned
    host identity (version and SHA-256 of the executable).
  - If G2C-O2 adopts it, a validation-only `MNEME_HOOK_EVIDENCE_LOG` seam
    that is inert when unset.

**Byte-identical guarantees.** Whenever no `FORBID_NUMERIC_ABOVE` rule is
`APPLIED`, `mneme.check/v1` payloads and exit codes stay byte-identical. That
includes checks with no numeric rule, as the ADR-034 G1 amendment above
already requires. The same holds for every unrouted hook event and for every
other integration's coherent results.

**Sections referenced:** the Freeze Anchor **Status** clause ("No behavioral
change to retrieval or enforcement without an explicit charter amendment"),
the ADR-034 G1 amendment above (including its recorded F2 operating
consequence), and the Amendment Procedure below.

**Rationale (Amendment Procedure §3(b)).** Every charter-level decision was
**already made** before this amendment:

- **The G2 design proposal,** reviewed twice and merged (PR
  [#630](https://github.com/MnemeHQ/mneme/pull/630), squash `97143065`).
- **The ADR-034 amendment.** §6a and §7a, with owner rulings G2-O1 to G2-O6,
  accepted and folded into
  [ADR-034](../adr/ADR-034-static-numeric-upper-bound-typed-rule.md),
  including the reconciliation of precondition 5 and the routed carrier (PR
  [#631](https://github.com/MnemeHQ/mneme/pull/631), squash `f0c16773`).
- **The G2-1 behavioral charter,** accepted by the owner after two
  architecture reviews, with rulings G2C-O1 to G2C-O6 (PR
  [#634](https://github.com/MnemeHQ/mneme/pull/634), squash `673b8ee0`).

Charter §1 and §9 require this amendment before implementation. No behavior
change is retroactively justified.

**Pinned regressions:** charter §8.C items 1–10. They cover:

- legacy-parity goldens;
- the preconditions, including permission errors and invalid UTF-8;
- the binding guard;
- numeric outcomes on `proposed_new_source`;
- hook routing, including the race and H1 cases;
- the expected-input and coherence trust rules, across every
  `assess_verdict` consumer;
- the hook outcome matrix under availability `open` and AUTHORIZED `closed`;
- evidence, including the mandatory host identity;
- untouched surfaces;
- the byte contract (LF, CRLF, lone CR, byte-order mark, non-ASCII, empty).

**Separate authorizations.** These each still need their own owner
authorization:

- the pinned live host characterization (§8.B);
- the independent validation corpus, harness and scoring (§8.D), which run
  only after the implementation commit is frozen.

Implementation and corpus authoring are done by separate sessions. Neither
gets the other's private evaluation material.

**Recorded operating consequences.**

- **The F2 restriction stays in force.** Under an AUTHORIZED closed
  availability declaration, a new in-scope file that lacks a declared source
  is still refused as `EVALUATION_INCOMPLETE`, and any edit to an existing
  file on an APPLIED numeric path is refused as before. G2-1 narrows F2 only
  for verified-new files that contain every declared source.
  `FORBID_NUMERIC_ABOVE` must still not be activated on closed-availability
  paths.
- **The unrouted defect is not fixed here.** On Windows, the unrouted path's
  text-mode carrier doubles CRLF line breaks. This is a pre-existing finding,
  recorded for a separate reviewed fix.

### Not authorized by this amendment

- Existing-file `Write`, `Edit`, `MultiEdit`, deletion or rename numeric
  evaluation, or any existing-file delta attribution.
- Bash (including class-A heredoc new-file writes) or Stop/session-delta
  numeric evaluation.
- Agent SDK, LangChain, `antigravity`, `codex_cli`, `hermes`, `kiro` or MCP
  pre-write coverage. Those integrations change only through the
  default-preserving validator parameter and the default-preserving
  diagnostic option.
- CI integration or workflow changes.
- Any ADR-033 availability-policy change, or any exception added for numeric
  rules.
- A fix to the unrouted carrier's CRLF handling.
- Changes to the M4 matcher semantics, `DecisionRetriever` ranking,
  `ConflictDetector`, `FORBID_LITERAL` semantics, persistence or rule
  identity. No new numeric forms or other languages.
- `MNEME_HOOK_EVIDENCE_LOG` as a supported user option or as a production
  evidence store.
- Activating `FORBID_NUMERIC_ABOVE` in this repository's memory, or
  importing ADR-034 into it.
- Any enforcement, "relevant enforcement observed" or production claim
  before §8.D passes.
- Implementation by any session or person with access to the G2 validation
  corpus, its answer key, or the corpus author's transcripts.

The existing DG1B1, DG1F-C1a, #260, T-08 slice-1, C2a, C2b, ADR-034 G1 and
C2b Amendment 1 freeze amendments, and the G1 F-1 record, remain unchanged.

---

## Amendment — record G2-1 charter §5.1 erratum: explicit `source_file` expected input (2026-10-24)

> This is a **record of a narrow owner ruling (G2C-R1)**. It adds one
> validator value and one test adapter within the G2-1 authorization above,
> and corrects that amendment's description of default callers. It
> authorizes nothing else.

**What happened.** The G2-1 amendment above says the shared
`assess_verdict` default "keeps every existing caller's coherent results
unchanged" and lists those callers. The list, and charter §5.1's premise that
no current consumer sends `--source-file`, both left out an existing caller:
the ADR-034 M4 scoring child, `benchmarks/adr034_m4/m4_child.py` (`trust`
command). It applies the default validator to G1 `--source-file` payloads
(`complete_source_file`). The G2-1 implementation PR
([#637](https://github.com/MnemeHQ/mneme/pull/637), draft) found this as
3 failures in `tests/test_adr034_m4_harness.py`.

**Ruling (charter §5.1 erratum, option (c)).**

- **New value, explicit only.** `assess_verdict` gains
  `expected_input="source_file"`, which accepts only `complete_source_file`,
  and only when the caller requests it explicitly. The caller decides from
  its own invocation, never from the payload.
- **Defaults unchanged.** The default `"input"` stays strict: no subject, or
  `unverified_input`. Routed writes keep `"proposed_new_file"`.
- **M4 untouched.** The M4 instrument (`benchmarks/adr034_m4/`, its corpus,
  criteria, pins and results) is not changed. M4's PASS (#628) stands for
  the build it pinned.
- **Current-build regression.** A separately identified post-M4
  compatibility adapter under `tests/` covers current builds. It is never M4
  blind scoring or G2 validation evidence.
- **Historical tests kept.** The existing M4 end-to-end tests that call the
  trust validator through the unmodified child are marked as historical
  pinned-build validation, with a reason that cites the erratum. They are
  not deleted and not edited to pass.

**Sections referenced:** the ADR-034 G2-1 amendment above, the Freeze Anchor
**Status** clause, and the Amendment Procedure below.

**Rationale (Amendment Procedure §3(a) and §3(b)).**

- **(a)** The G2-1 amendment's list of default callers, and the charter
  premise it relied on, are defective against the repository as merged.
  This record corrects that description.
- **(b)** The owner ruling was already made and is recorded as a dated
  erratum in charter §5.1, merged with this record.

No implemented behavior is justified after the fact. #637 is a draft, and the
ruling is recorded before the implementation changes.

**Consequence for the default caller.** On post-G2 builds, the unmodified M4
child's default call treats `complete_source_file` payloads as untrusted. This
is accepted. M4 is closed, its instrument is pinned, and current-build
coverage moves to the compatibility adapter.

### Not authorized by this record

- Any change to `benchmarks/adr034_m4/`, the M4 corpus, criteria, pins or
  results, or any re-scoring of M4.
- Adding `complete_source_file` to the default `expected_input`, or letting a
  payload select its own trusted input kind.
- Counting the compatibility adapter as blind validation or G2 evidence.
- Anything else beyond the G2-1 amendment above.

The existing DG1B1, DG1F-C1a, #260, T-08 slice-1, C2a, C2b, ADR-034 G1,
C2b Amendment 1 and ADR-034 G2-1 freeze amendments, and the G1 F-1 record,
remain unchanged.

---

## Amendment — authorize the ADR-034 D1 evidence-validator and D2 matcher changes (2026-10-26)

> This authorizes **two bounded implementation changes**, each specified by
> an ADR-034 amendment that is already merged: D1, per-rule attribution of
> relevant enforcement (§7b), and D2, function-source resolution by Python
> lexical scoping (§3a). Each change is delivered as its own reviewed PR. It
> authorizes no validation claim, no symbol-source change and no other
> behavior.

**Change 1, D1 (ADR-034 §7b).**
- **Where:** `relevant_enforcement_observed()` and the evidence record in
  `mneme/integrations/claude_code/hook.py`.
- **What:**
  - per-rule relevance is authoritative, and the event-level value is
    existential: at least one applied numeric rule is relevantly enforced;
  - record-wide `evaluation_complete` is kept as a separate fact;
  - the common host, event, subject, digest, target and provenance bindings
    stay in place;
  - a rule never inherits another rule's relevance.
- **Unchanged:** the hook's blocking decisions, exit codes,
  availability handling, the strict/warn dispositions and the
  `mneme.check/v1` payloads.
- **Pinned regressions:** every row of the §7b table, plus the existing G2-1
  evidence and tamper tests.

**Change 2, D2 (ADR-034 §3a).**
- **Where:** function (`call`) source resolution in
  `mneme/numeric_rule.py`.
- **What:**
  - each direct bare-name call site is resolved by Python lexical scoping;
  - a binding no call site resolves to has no effect;
  - a call site that resolves to another binding is `UNKNOWN` /
    `AMBIGUOUS_BINDING`;
  - module-level rebinding, `global`, escape and undecidable or dynamic
    resolution stay `AMBIGUOUS_BINDING` and are never clean;
  - class-body execution order, and any binding static analysis cannot
    establish, **fail closed**.
- **Outcome boundary:** D2 may change a strict-mode refusal or warn-mode
  defer solely because corrected function-source resolution changes a
  previously unevaluated result into a recognized numeric violation. This is
  an authorized consequence of the matcher change, **not** permission to
  change the hook's blocking logic, exit-code mapping, availability handling
  or strict/warn policy. D1 remains evidence-only.
- **Pinned regressions:**
  - scope-resolution cases: class body versus method, parameter, nested
    function, enclosing scope, comprehension, `global`/`nonlocal`, dynamic
    constructs, and the D2 shapes;
  - the public M4 R1–R18 vectors and the G1 regression suite;
  - golden rule IDs, and payloads for checks with no numeric rule, which
    stay byte-identical.

**Sections referenced:** the Freeze Anchor **Status** clause, the ADR-034 G1
and G2-1 amendments above, and the Amendment Procedure below.
- The G1 amendment and the G2-1 amendment both state that M4 matcher
  semantics are not authorized for change.
- Change 2 is an explicit, narrow exception to that, for the function source
  only.

**Rationale (Amendment Procedure §3(b)).** Every charter-level decision was
**already made**:
- **Validation result:** the G2-1 blind validation results record (#666,
  squash `cec27ea9`, verdict FAIL) diagnosed D1 and D2.
- **The rulings:** the owner ruled on both, and they were merged as ADR-034
  amendments:
  - §7b, PR [#668](https://github.com/MnemeHQ/mneme/pull/668), squash
    `78d1d684`;
  - §3a, PR [#669](https://github.com/MnemeHQ/mneme/pull/669), squash
    `4175722e`.

Neither change is justified after the fact. Both are still to be
implemented.

**Recorded consequences.**
- **M4 and G1.** After Change 2, the matcher's recognition boundary differs
  from the build M4 validated. That includes the effect of interpretation
  AMB-07: a same-named parameter makes only the call sites in its own
  function `UNKNOWN`. M4's PASS (#628) remains evidence for its pinned build
  only. A post-change G1 audit claim is **not** covered by M4, and any new
  blind G1 claim needs its own validation.
- **G2-1.** The G2-1 FAIL stays final. A later PASS needs a new
  pre-registration that adopts §3a and §7b, plus a newly authored,
  independently held-out corpus.
- **Pinned harnesses.** The pinned `benchmarks/adr034_m4/` and
  `benchmarks/adr034_g2_1/` harnesses are not modified.

### Not authorized by this amendment

- Any change to the `symbol` source's resolution. Under §3a that stays
  undecided.
- Any independent change to hook blocking logic, exit-code mapping,
  strict/warn policy or availability policy (ADR-033), beyond the hook
  outcomes necessarily resulting from D2's scoped matcher recognition.
  No change to `FORBID_LITERAL`, `DecisionRetriever`, `ConflictDetector`,
  persistence or rule identity.
- Any change to the pinned M4 or G2-1 harnesses or evidence, or re-scoring
  of any sealed or revealed corpus.
- Implementation by any session or person with access to the G2-1 held-out
  corpus content, its answer key, or the scorer's diagnosis evidence beyond
  the merged results record.
- Any enforcement, "relevant enforcement observed" or production claim, or
  any G1 or G2-1 validation claim, for the changed builds.

The existing DG1B1, DG1F-C1a, #260, T-08 slice-1, C2a, C2b, ADR-034 G1,
C2b Amendment 1 and ADR-034 G2-1 freeze amendments, the G1 F-1 record and
the G2-1 §5.1 erratum record remain unchanged.

---

## Amendment Procedure

This document is frozen at `e73ff7d`. To amend it:

1. Open a PR titled `[layer1-freeze] <change>`.
2. Reference the specific section being amended.
3. Include a rationale anchored to one of: (a) a defect in this document's description of shipped behavior; (b) a charter amendment that has *already* been made elsewhere; (c) the close of an exit criterion.
4. Do **not** amend this document to retroactively justify a behavioral change. Behavioral changes get their own charter.

This procedure is the protection against premature roadmap expansion. The freeze is only meaningful if it is harder to move than the next attractive idea.
