# DG1F Runtime Convergence — Architecture Readiness and Charter Inputs

**Status (reconciled 2026-10-14):** historical DG1F preflight and remaining-gates inventory, **not** an implementation charter or authorization for C1b, waivers, or additional runtime consumers. C1a has subsequently been accepted and merged.
**Original source anchor:** `main` at `6da5cae269ef532faf969e1f5cbad5342d92b246` (DG1B1, PR #487); §2 retains that point-in-time inventory where noted.
**Reconciliation evidence:** ADR-031 sequencing amendment #492 (`c1816aa5`), C1 charter #493 (`96ec857e`), C1a freeze amendment #494 (`6e02f4ee`), and accepted C1a implementation #495 (`d1aa0d8c9ed5395fb4cf814f2c3703f081c9ad46`).
**Governing decisions:** [ADR-031](../adr/ADR-031-decision-governance-semantics.md) §4, §6–§7, §10–§12; [ADR-017](../adr/ADR-017-enforcement-scope-vs-retrieval-scope.md); [ADR-020](../adr/ADR-020-explicit-path-applicability-for-typed-rules.md); [ADR-029](../adr/ADR-029-enforcement-evidence-binding-semantics.md); [ADR-030](../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md); [Layer 1 freeze](../architecture/layer1-freeze-e73ff7d.md) and the [DG1B1 charter](2026-10-08-dg1b1-decision-applicability-charter.md).

## 1. Why this preflight exists

At the original source anchor, DG1B1 had introduced canonical `required_labels` and `resolve_effective(index, GovernanceContext)`, without changing runtime enforcement. This preflight documented the boundary that subsequently received **narrow, report-only** authorization.

**Sequence gate — resolved for C1a only:** ADR-031 §11 was amended by #492 to permit an applicability-only DG1F increment before DG1B2. Full waiver-aware convergence still follows evidence-gated DG1B2; the amendment does not waive canonical-target binding or authorize other runtime surfaces.

**Freeze gate — fulfilled for C1a only:** The C1 charter #493 merged before the matching `[layer1-freeze]` amendment #494, and the independently reviewed report-only implementation #495 then merged. The exception permits an opt-in, NON-AUTHORITATIVE `mneme check --applicability-preview LABEL` diagnostic. It does **not** permit decisions to be removed from enforcement, trusted caller context, persisted context declarations, or other DG1F consumers. C1b requires separate charter/freeze authorization.

## 2. Observed implementation boundary (original DG1B1 source anchor, with C1a annotations)

| Surface | Verified current path | What DG1F must not assume |
|---|---|---|
| Canonical authority | `mneme/decision_index_persistence.py` loads canonical v1/v2 state; v2 carries optional, exact, project-local `required_labels`. | Labels do not come from retrieval metadata or source text. |
| Shared resolution | `mneme/decision_governance.py:resolve_effective(index, GovernanceContext)` evaluates lifecycle, then set containment of required labels, with `not_applicable` cause. | A missing label is **not** evidence that a particular nonmatching platform was positively established. |
| Existing runtime projection | `mneme/decision_projection.py:project_canonical_index` projects lifecycle-active decisions only and currently ignores DG1B1 applicability. | Changing that global load-time projection without an evaluation context could silently discard constraints. |
| Memory loading | At the source anchor, `MemoryStore.load` verified and projected canonical authority. **C1a now additionally exposes the same validated in-memory canonical snapshot via `MemoryStore.canonical_index` for the preview**, without a second file read. | No globally authoritative label context is established by a memory load. |
| CLI enforcement | `_cmd_check` still executes `DecisionRetriever.retrieve` → `check_prompt` on the unchanged enforcement corpus. **Since #495, a separate opt-in stderr-only preview calls `resolve_effective` after the enforcement result is computed**, using caller-supplied labels for display. | Preview labels have **no authority**; retrieval score, paths, OS and caller arguments cannot gate enforcement. |
| Enforcement scope | `mneme/enforcer.py` has separate retrieval-gated and corpus-wide literal-rule tiers per ADR-017; ADR-020 path selectors remain rule-level. | A DG1F change must not turn typed enforcement back into a top-K-only operation. |
| Other consumers | ADR-031 §11 identifies duplicated `active` tests in protection candidate selection, activation precheck, Audit aggregation and readiness; the DG1B1 charter additionally names hooks and MCP. | Their individual inputs, trust boundaries, and behavior require a per-surface inventory before any authorization to converge them. |

This remains a starting inventory, **not** a claim that every consumer has been audited. Except for the explicitly annotated C1a changes, the table describes the original #487-era baseline and must not be read as a fresh end-to-end audit.

## 3. Resolved C1a choices and remaining architectural gates

### A. Sequencing relative to DG1B2 — resolved for C1a

The decision is recorded in **ADR-031 §11 as amended by #492**: applicability-only DG1F may precede evidence-gated DG1B2. C1a used that exception with the separate charter #493 and freeze amendment #494, then merged as #495. This does **not** authorize C1b enforcement exclusion or full waiver-aware DG1F convergence; the default later sequencing remains in force.

### B. Deterministic and trustworthy context supply

**C1a resolved only the diagnostic interface:** `--applicability-preview LABEL` supplies opaque, unauthenticated, caller-asserted labels **for stderr display, never exclusion**. A preview can show `not_applicable` but must not change the enforcement corpus, JSON verdict, stdout, hook behavior or exit code.

**C1b remains blocked on trust:** As fixed in the merged C1 charter §3, any actual exclusion requires a canonical context declaration plus **independently verifiable approved revision, protection against unreviewed substitution, and controlled context selection**. Command-line labels, environment, hook/MCP arguments, file/path/OS heuristics, retrieval, LLM output and Data Engine observations cannot establish enforcement authority. The resolver's absent-label result alone is not proof of a positively established nonmatch.

The charter distinguishes invalid/conflicting context over otherwise valid canonical authority (**do not exclude; preserve protection and surface the condition**) from invalid/unreadable canonical memory (**operational failure; enforcement coverage unknown**). These are **C1b design constraints, not delivered C1b behavior**. Blocking-seam validation is separately required before any end-to-end fail-closed claim.

### C. Resolver findings and ambiguity

DG1C reports governance-integrity findings such as `dangling_supersedes` and `supersession_lifecycle_conflict`. **C1a preview** treats unresolved findings as incomplete and reports `PREVIEW UNAVAILABLE` without changing enforcement. Their safe handling in any **future authoritative exclusion** remains separately gated by C1b; do not fabricate a winner or silently treat incomplete evaluation as a PASS.

### D. Scope and output contracts per consumer

**C1a's bounded consumer is complete:** `mneme check` gained only an opt-in, stderr-only NON-AUTHORITATIVE diagnostic (PR #495). It does not alter `mneme.check/v1`, enforcement or any hook/MCP contract. **All other consumers remain unapproved** and require their own context provenance, failure handling, surface-specific authorization and parity evidence. Converge one consumer at a time.

- Distinguish guidance retrieval from authoritative decision selection (ADR-017, ADR-031 §4).
- Apply ADR-020 rule selectors **after** decision effectiveness; do not conflate them.
- Preserve ADR-030 version/rule identity and ADR-029 current-run evidence semantics.
- An MCP addition to the ADR-027 tool contract is **not** implicitly approved by DG1F (ADR-031 §5).
- Any change to Audit, readiness or protection needs an explicit, surface-specific contract; totals or eligibility must not shift accidentally.

## 4. Acceptance evidence: delivered C1a versus deferred C1b

**C1a completed:** the merged charter §5a defines five independent report-only acceptance gates. PR #495 implemented an offline `tests/test_dg1f_c1a_preview.py` suite using the pinned GSA-TTS ADR-0028 fixture and registered it in the PR gate. Independent review reported **25 passing C1a tests and 138 related regression tests**; PR CI recorded **2,799 passed, 6 skipped**. The review verified no enforcement change, additive stderr-only NON-AUTHORITATIVE output, spoofed-label non-interference, no second canonical-memory read, and compatibility with strict/warn and human/JSON modes. Neither the frozen benchmark fixtures nor methodology changed. These results validate C1a **only**, not trusted-context enforcement or exclusions.

**Deferred C1b/remaining DG1F acceptance candidates (not authorization):** Reuse the committed offline GSA-TTS ADR-0028 fixture and `tests/test_dg1b1_functional_acceptance.py` under separately approved charters. The following items are candidates; the binding C1b gates are in the merged C1 charter §5b:

1. **Parity:** with no applicability declared, old and new evaluations use the same decisions, rules, verdicts and evidence identities.
2. **Matching context:** with explicitly supplied `platform:windows`, the Windows-only decision reaches rule applicability and enforcement.
3. **Confirmed nonmatch:** with an explicitly supplied and trustworthy `platform:linux` context, only the Windows-restricted decision is excluded; global decisions remain protected.
4. **Unavailable/invalid context:** must not produce a silent PASS by filtering out an otherwise active, constrained decision. The exact outcome requires choice B.
5. **Lifecycle:** superseded/deprecated/inactive decisions never regain authority through matching labels.
6. **Independence:** retrieval scores/top-K cannot determine governing decisions; ADR-020 path applicability stays separate and unchanged.
7. **Reproducibility:** context, effective IDs, cause codes, rule IDs and enforcement outcome can be replayed without a model or live network.
8. **Regression:** existing Layer 1 canonical benchmark fixtures and methodology stay unchanged; add a separately authorized acceptance suite for any behavior-changing tests.

DG1B1 acceptance F12 recorded **pre-C1a runtime non-interference**; it was not a runtime exclusion test. Likewise, C1a's report-only success is **not** proof that C1b enforcement exclusion, trusted-context provenance, waiver semantics or blocking-seam safety have been implemented.

## 5. Readiness and next authorized step

- [x] DG1B1 accepted and merged (#487); canonical resolver and migration available.
- [x] ADR-031 §8a extension namespacing accepted and implemented (#490 / #487).
- [x] The bounded DG1F-before-DG1B2 sequence exception merged (#492).
- [x] C1a-specific behavioral charter merged (#493) and Layer 1 freeze amendment merged (#494).
- [x] C1a report-only CLI preview implemented, independently reviewed and squash-merged (#495).
- [ ] Reconcile the **merged C1 charter's pre-merge status wording** in a separate docs-only change; do not silently reinterpret its prospective C1b provisions.
- [ ] Inventory each **additional** enforcement consumer's authoritative context source, entry point and fail-safe behavior before seeking new authorization.
- [ ] For any C1b exclusion, separately design and validate a review-gated canonical context declaration, independently verifiable approved revision, substitution protection, controlled context selection, and blocking-seam behavior. Require a **new behavioral charter and freeze amendment** before runtime implementation.
- [ ] DG1B2 waivers remain evidence- and canonical-target-binding-gated (ADR-031 §12); remaining DG1F consumers and DG1G remain deferred.

**Non-goals of this document:** this reconciliation does not authorize C1b or any runtime filter, trusted context selection, waiver implementation, new schema or persisted fields, changes to DecisionRetriever/ConflictDetector/MCP/hooks/Audit/readiness/protection, benchmark-methodology changes, or release/merge approval. C1a's already-merged preview flag is recorded as historical fact, not broadened here.
