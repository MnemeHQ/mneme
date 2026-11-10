# DG1 after C3a: programme reconciliation (2026-11-09)

> Read-only reconciliation of the DG1 programme against
> [ADR-031](../adr/ADR-031-decision-governance-semantics.md) §§11–13 and
> tracker [#497](https://github.com/MnemeHQ/mneme/issues/497), after DG1F-C2
> and DG1F-C3a. It updates the
> [v0.11.0 reconciliation](dg1-v0110-architecture-reconciliation-2026-11-08.md)
> (#762), separates contractual obligations from deferred work and from
> defects, and names the smallest defensible next DG1 decision. It changes no
> code, test, ADR or freeze state, does not reopen C2 or C3a, does not prepare
> a release, and authorizes nothing.
> **Anchor:** `main` at `98943303` (#779). Runtime code is identical to
> `8dcb1ef9` (#777); C2 and C3a are merged and unreleased.

## 0. Summary

- **No defect found.** Every gap open on `main` is either an explicitly
  deferred obligation, an evidence-gated slice, or a recorded limitation with
  an owner. Nothing contradicts ADR-031 or a merged charter.
- **Delivered since #762:** the `precedence_lost` erratum (#763); single
  lifecycle authority and three-state context (C2, #770); resolver-result
  consumption by three reporting consumers (C3a, #777); C3b feasibility,
  deferred (#779); architecture and roadmap docs corrected (#780).
- **Remaining ADR-031 obligations:** §11 convergence for the remaining
  consumers; §12 waivers (DG1B2, evidence-gated); §13 DG1G fixture floor and
  closeout. Plus the deferred precedence-reason feature (§2/§3 erratum).
- **Evidence-gated, not actionable now:** C1b (needs a case, a context
  declaration and a trusted context source), DG1B2 (needs a verified,
  decision-version-bound waiver case), C3b (needs a consumer).
- **Smallest defensible next DG1 decision (§6):** a **DG1G fixture-floor
  mapping record**: map each ADR-031 §13 fixture to the existing test that
  pins it, and list exactly the fixtures that are supported, missing,
  blocked or unevaluated. It is read-only, needs no charter or freeze
  amendment, and is a partial fixture-coverage record, not a closeout. DG1G
  and DG1 stay open. No implementation increment is recommended now.

## 1. Delivered since the v0.11.0 reconciliation

| Item | PR | Squash | Status |
|---|---|---|---|
| v0.11.0 reconciliation | #762 | `e3f8c449` | merged |
| ADR-031 `precedence_lost` erratum | #763 | `23f022c9` | merged |
| C2 charter / freeze / implementation | #764 / #767 / #770 | `00b9781d` / `58ce4b49` / `b719dc96` | merged, unreleased |
| C3 feasibility | #773 | `7af4645a` | merged |
| C3a charter / freeze / implementation | #774 / #775 / #777 | `5a1fdb20` / `d05ff16c` / `8dcb1ef9` | merged, unreleased |
| C3b feasibility (deferred by owner) | #779 | `98943303` | merged, docs only |
| Architecture and roadmap correction | #780 | `0d181689` | merged |

Completion records for C2 and C3a are on #497.

## 2. Status of the v0.11.0 reconciliation gaps

| ID (#762) | Gap | Status now | Class |
|---|---|---|---|
| G-1 | No runtime consumer uses the resolver; duplicated lifecycle checks | **Partly closed.** One lifecycle authority (C2). Three reporting consumers use the resolver result (C3a). Other consumers open (§3). | obligation (§11) |
| G-2 | Legacy section-less memory enforces superseded decisions; Audit excludes them | **Unchanged by design**, pinned by C2/C3a goldens. Fix needs a legacy-memory deprecation decision. | deferred, not a defect |
| G-3 | Whether integrity findings block | **Decided for C2/C3a:** findings never exclude or fail a consumer. Open for any future enforcement consumer. | decided (scoped) |
| G-4 | `precedence_lost` scheduling contradiction | **Closed** by the erratum (#763); the feature itself is deferred (§4). | closed / deferred |
| G-5 | Resolver could not express "context not supplied" | **Closed** by C2 (three-state context). | closed |
| G-6 | No persisted context declaration; no CLI writer for applicability | Open. | evidence-gated (C1b) |
| G-7 | Host memory source untrusted (T-08 D6 C4) | Open. | evidence-gated (C1b / T-08) |
| G-8 | Trusted CI gate evaluator pinned pre-0.11.0 | Open: still `0b74d410`. | CI R0 owner, not DG1 |
| G-9 | No verified waiver case | Open. | evidence-gated (DG1B2) |
| G-10 | Doc drift (resolver docstring, roadmap) | **Closed** (#770 docstring, #780 docs). | closed |
| G-11 | Governance-of-governance controls (#497, 7 Nov) | Open; host side unresolved; authorized-transition control untested. | DG1G obligation |

## 3. ADR-031 §11 convergence: consumer map

| Consumer | Uses resolver result | Next step | Gate |
|---|---|---|---|
| `mneme check --applicability-preview` | yes (C1a, report-only) | none | shipped |
| `mneme audit`, setup readiness, `protect list` | yes (C3a) | none | merged, unreleased |
| authenticated memory entry point (C3b) | n/a: not built | revisit when a consumer exists | owner deferral (#779) |
| `audit_with_github_claim(decisions, …)` and other list-taking library APIs | no, by contract | none: they report on caller lists | outside the convergence claim |
| `protect status`, `protect validate` | no | read-only assessment; a resolver cause instead of "not found" is a message change | charter + freeze; output-contract decision |
| `protect activate` and the persistence protection-install check | no | only after status/validate | authority write path; charter + freeze |
| CI evidence-matching APIs | no | low value at parity | charter + freeze |
| enforcement inputs (`mneme check`, hooks, CI gates, MCP) | no | parity changes nothing; anything more is C1b | C1b prerequisites |
| explanation output (causes, `superseded_by`, findings) | no | output-contract decision | owner decision |

**Assessment.** The remaining consumers either add no value at parity
(evidence APIs, enforcement inputs), need an output-contract decision
(protect status/validate, explanation output), sit on an authority write path
(activate), or are evidence-gated (C1b). None is a cheap parity increment like
C3a, so no further §11 implementation is recommended until an output or
consumer need is decided.

## 4. ADR-031 §12, §13 and the deferred precedence reason

- **§12 waivers (DG1B2):** semantics fixed, implementation evidence-gated.
  No verified waiver case exists (#497, Data Engine #36 handoff). Not
  actionable.
- **§2/§3 precedence reason (`precedence_lost`):** deferred as a future,
  evidence-gated v2 semantic feature (#763 erratum, #497 item). Not part of
  the §13 floor.
- **§13 DG1G fixture floor:** see §5.

## 5. DG1G fixture floor (ADR-031 §13), current mapping

| §13 fixture | Pinned by | State |
|---|---|---|
| 0.10.0 parity | `test_dg1c_effective_resolver.py` parity tests | pinned |
| different-scope co-governance | `test_adr_precedence.py::test_different_scopes_both_active` | pinned (pre-DG1 test; needs explicit DG1G mapping) |
| broader/narrower coexistence | `test_adr_precedence.py::test_nested_scopes_coexist_no_conflict` | pinned (pre-DG1 test; needs explicit DG1G mapping) |
| same-scope priority | `test_dg1p_date_not_authority.py`, `test_adr_precedence.py` | pinned |
| same-scope ambiguity, no date tiebreak | `test_dg1p_date_not_authority.py` | pinned |
| supersession; honest `lifecycle_inactive` | `test_dg1c_effective_resolver.py` | pinned |
| input-order, irrelevant-decision, context-path invariance | `test_dg1c_effective_resolver.py`, `test_dg1b1_decision_applicability.py` | pinned |
| canonical rule identity through enforcement | `test_dg1e_evidence_identity.py` | pinned |
| section-less fail-closed evidence | `test_dg1e_evidence_identity.py` | pinned |
| configured vs execution-observed evidence (ADR-029 §6) | documented by the Verification track ([#761 audit](adr029-evidence-completeness-audit-2026-11-08.md), [step 3](verification-step3-e2e-fixture-2026-11-09.md), [step 4](verification-step4-independent-review-2026-11-09.md)); ADR-034 harness tests | **evidence exists; no DG1-mapped test** |
| snapshot A → B change explanations | `test_dg1d_change_resolution.py` | pinned |
| applicability fixtures | `test_dg1b1_*` (incl. functional acceptance F1–F12), C2 three-state tests | pinned |
| waiver fixtures (incl. `as_of` expiry, out-of-scope) | none | **blocked by DG1B2** |
| #497 governance-of-governance controls (self-authorization negative, authorized-transition positive, host boundary) | CI side: CI1 V2/V3, C4 O8; host side: none | **partly pinned** |
| four-layer end-to-end acceptance (roadmap P0, cross-cutting; owned outside DG1) | Verification step 3 fixture covers a subset | **not an ADR-031 §13 fixture**; can supply evidence for DG1G, but is not a DG1G gate without an explicit architectural decision |

Current DG1 test count: 296 tests in `tests/test_dg1*.py` at the anchor.

## 6. Smallest defensible next DG1 decision

**Recommendation: a DG1G fixture-floor mapping record** (read-only, docs
only).

- Map each §13 fixture and each #497 governance-of-governance control to the
  exact test or validation record that pins it, as in §5, but at test-id
  granularity.
- State exactly what is missing: the ADR-029 §6 DG1-mapped fixture, the host
  governance-of-governance controls, and the waiver fixtures (blocked by
  DG1B2, marked UNEVALUATED).
- Keep two obligations and their owners separate: the ADR-031 §13 fixture
  floor (DG1) and the roadmap's cross-cutting Governance → Guidance →
  Enforcement → Verification acceptance test (P0, outside DG1). The latter can
  supply evidence for DG1G but is not imposed as a DG1G gate here, and the
  mapping does not duplicate the Verification track.
- **No partial closeout.** ADR-031 §11 does not allow DG1G closeout before the
  full sequence is complete. While DG1B2 stays evidence-gated, the record is a
  partial fixture-coverage record with waiver fixtures UNEVALUATED, never
  silently passed; DG1G and DG1 remain open.

**Why this, not an implementation increment:** every remaining §11 consumer
needs an output-contract decision, an authority-path charter or C1b evidence
(§3); DG1B2 has no case; and any future DG1G closeout needs the fixture floor
mapped precisely first. The mapping record needs no charter or
freeze amendment and turns DG1G from a heading into a checklist.

**Not recommended now:** further §11 parity increments (no value at parity),
C1b and DG1B2 (evidence-gated), C3b (no consumer), a release (owner hold),
reopening C2 or C3a.

## 7. Non-claims

This record does not claim DG1, DG1F or DG1G completion, does not change any
verdict, and approves no implementation, charter, freeze amendment or
release. Test counts are from local collection at the anchor. G-8 belongs to
CI R0 and is listed only for completeness.
