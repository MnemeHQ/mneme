# DG1-S closeout evidence record (2026-11-18)

> **DRAFT — for independent review and owner acceptance.** This is the
> closeout evidence record required by [ADR-031 §11a.4](../adr/ADR-031-decision-governance-semantics.md).
> After independent review, owner acceptance and merge it closes **DG1-S only**.
> It does **not** close DG1, DG1G or ADR-031 §11, and it is not a release.
>
> **Pinned subject:** `MnemeHQ/mneme` `main` at
> `13fae565557953288ffb70052f092d91601fc89d`, tree
> `60c929a0bbf854daca59d1de7436b6665c15394d`.
> **Change scope:** docs-only. No runtime code, tests, ADR text, tracker,
> roadmap, freeze contract or release metadata is changed by this record.

## 0. Claim and scope

DG1-S is the intermediate **Decision Governance Semantic Foundation**
milestone defined by ADR-031 §11a. This record is its §11a.4 closeout
evidence. It records:

- the merged DG1-S slices and their exact squash commits;
- the supporting capabilities that are delivered but are **not** part of the
  DG1-S semantic claim;
- the ADR-031 §13 F1–F13 fixture coverage, gate membership and F13's
  resolver-only limitation;
- validation newly executed at the pinned commit, separated from historical
  acceptance evidence;
- merged-versus-released status;
- the obligations that DG1-S leaves open;
- every §11a non-claim.

DG1-S closes only after independent review and owner acceptance of this
record. DG1 and DG1G remain open after that closure.

## 1. Pinned subject

| Item | Value |
|---|---|
| Repository | `MnemeHQ/mneme` |
| Branch | `main` |
| Commit | `13fae565557953288ffb70052f092d91601fc89d` |
| Tree | `60c929a0bbf854daca59d1de7436b6665c15394d` |
| Commit date | `2026-11-18T19:01:10-05:00` |
| Merge | PR #837, `2026-11-19T00:01:10Z`; accepted head `efdadcc300818fd7bca78ba6f176720c72c87b88`; squash tree equals accepted tree |
| ADR-031 §11a | merged at this commit |
| Latest release tag | `v0.11.0` (`619d5405e80da61788448a7a0eeacc7c5eb3d0c0`) |

The accepted head `efdadcc3` and the squash commit `13fae565` have the same
tree. The evidence below is pinned to `13fae565`.

## 2. Delivered DG1-S slices

| Slice | Merged PR | Squash commit | Delivered |
|---|---|---|---|
| DG1A | #466 | `fe1c457b258ac7a427f0834edd241c6b30e8e1a1` | accepted ADR-031 contract; v1 compatibility characterization |
| DG1C | #468 | `ab6ca5672e6fcc2f1c0b606551ea1fa8fbf99d2f` | `resolve_effective`, `ResolutionTrace`, governance-integrity findings |
| DG1E | #469 | `3625cf1641185051b6065f9d8c2ce56eb87a7ae6` | canonical ADR-030 §7 `rule_id` through enforcement; `decision_version_id`; fail-closed evidence identity |
| DG1D | #469 | `3625cf1641185051b6065f9d8c2ce56eb87a7ae6` | `resolve_change`; `DecisionChangeSet` over two supplied snapshots |
| DG1P | #470 | `6f26fc3167c3a8b364d9819d87f07f93be825635` | ADR `date` removed as precedence authority; import ambiguity report |
| DG1B1 | #487 | `6da5cae269ef532faf969e1f5cbad5342d92b246` | decision-applicability semantics under `mneme.decision-index/v2`; `not_applicable`; explicit v1→v2 migration |
| DG1B2a | #787 | `804591ae867abba269b67fb1587e1e2efd2efdc8` | canonical waiver records; `waived` cause; waiver trace/findings; authority operations; read-only listing; no authoritative consumer acts on a waiver |

DG1E and DG1D were delivered in the same PR and squash commit. All seven
slices are merged on `main` at the pinned commit.

### 2.1 DG1B2a acceptance evidence

DG1B2a was accepted under:

- evidence packet #783, squash `27c9222378da040cea61d9748488efb7df751e20`;
- behavioral charter #784, squash `412a1e462c774f13b8be80432571ba515e1793e5`;
- Layer 1 freeze amendment #785, squash `3594259a21f5c18bcefe6bbe8ef3caab85d88ce6`;
- implementation #787, squash `804591ae867abba269b67fb1587e1e2efd2efdc8`.

The DG1B2a completion record for #787 (tracker #497) states 81 charter §4
tests, unchanged C2/C3a goldens on Windows and Linux, a green gate battery,
the frozen Layer 1 benchmark at 7/7, and that `mneme-hq==0.11.0` refuses
waiver memory. Those claims are historical acceptance evidence. The current
pinned run re-executes the same 81 tests (see §5), but does not re-attest the
original independent review.

DG1B2a delivers the §12 **record** semantics only. DG1B2b — any authoritative
consumer acting on a waiver — remains deferred.

## 3. Supporting capabilities (not §11 convergence)

| Capability | Merged PR | Squash commit | Status |
|---|---|---|---|
| DG1F-C1a report-only preview | #495 | `d1aa0d8c9ed5395fb4cf814f2c3703f081c9ad46` | shipped in `v0.11.0`; non-authoritative; stderr only |
| DG1F-C2 lifecycle authority | #770 | `b719dc965088226216574a9b187b6f5e767ea003` | merged, unreleased; one lifecycle authority; three-state `GovernanceContext` |
| DG1F-C3a reporting consumers | #777 | `8dcb1ef9bc2e46ffc76df4049adcf3918103d988` | merged, unreleased; `mneme audit`, setup readiness and `protect list` only |

C1a, C2 and C3a are **delivered supporting capabilities**. They are not part
of the DG1-S semantic claim and do **not** complete ADR-031 §11 resolver-result
convergence. C3a covers three reporting consumers only; no enforcement input
changes. The remaining §11 consumers are listed in §8.

### 3.1 C2 and C3a golden parity

The historical completion records for C2 (#770) and C3a (#777) report
pre-change goldens captured before production code, byte-identical reproduction
on Windows and Linux, mutation testing, and the frozen benchmark at 7/7.
Those records remain the historical acceptance evidence.

At the pinned commit, this record re-executes the C2 and C3a golden-parity test
files as part of the §13 fixture suite in §5. The current run is new validation
of the same tree; it does not rewrite the historical completion records.

## 4. ADR-031 §13 fixture coverage F1–F13

Source: [`docs/validation/dg1g-fixture-floor-mapping-2026-11-10.md`](dg1g-fixture-floor-mapping-2026-11-10.md),
read at the pinned commit.

| Fixture | Mapping status | Gate-pinned test file(s) |
|---|---|---|
| F1 0.10.0 parity | supported | `test_dg1c_effective_resolver.py`; `test_dg1f_c2_golden_parity.py`; `test_dg1f_c3a_golden_parity.py` |
| F2 different-scope co-governance | supported | `test_adr_precedence.py` |
| F3 broader/narrower coexistence | supported | `test_adr_precedence.py` |
| F4 same-scope priority resolution | supported | `test_adr_precedence.py`; `test_dg1p_date_not_authority.py` |
| F5 same-scope ambiguity, no date tiebreak | supported | `test_adr_precedence.py`; `test_dg1p_date_not_authority.py` |
| F6 supersession | supported | `test_adr_precedence.py`; `test_dg1c_effective_resolver.py`; `test_dg1p_date_not_authority.py` |
| F7 lifecycle exclusion with honest `lifecycle_inactive` | supported | `test_dg1c_effective_resolver.py`; `test_dg1f_c2_lifecycle_consolidation.py` |
| F8 input-order invariance | supported | `test_dg1b1_decision_applicability.py`; `test_dg1c_effective_resolver.py`; `test_dg1d_change_resolution.py` |
| F9 irrelevant-decision and context-path invariance | supported | `test_dg1b1_decision_applicability.py`; `test_dg1c_effective_resolver.py` |
| F10 configured vs execution-observed evidence | supported | `test_dg1g_f10_evidence_distinction.py` (gate); `test_adr034_g2_1_harness.py` (main-only supplementary) |
| F11 canonical rule identity; section-less fail-closed evidence | supported | `test_dg1e_evidence_identity.py` |
| F12 snapshot A→B change explanations | supported | `test_dg1d_change_resolution.py`; `test_dg1b1_functional_acceptance.py` |
| F12a applicability fixtures | supported | `test_dg1b1_decision_applicability.py`; `test_dg1b1_functional_acceptance.py`; `test_dg1f_c2_lifecycle_consolidation.py` |
| F13 waiver fixtures | supported | `test_dg1b2a_canonical_waivers.py` |

**Result:** 13/13 §13 fixtures are classified **supported** at the pinned
commit. F12a is counted with F12, per the mapping. The mapping remains a
fixture-coverage record, not a DG1G closeout.

### 4.1 Gate membership verification

The whole mapping, not only §13, cites 27 explicit `file::test` references
across 11 test files. At the pinned commit:

- 27/27 explicit references resolve by `pytest --collect-only`; 0 missing
  (731 tests are collected across those 11 files, including parameterized
  variants). This count includes the §3 G1/G3 references and the main-only
  F10 supplementary file; it is **not** the §13 fixture-only count.
- Across the full F1–F13 table, 13 unique test files are cited. Twelve are in
  `GATE_PATHS` and not in `GATE_EXCLUSIONS`; one,
  `tests/test_adr034_g2_1_harness.py`, is in `GATE_EXCLUSIONS` as
  “main-only: benchmark tooling (ADR-034 G2-1 §8.D scoring harness)”. It is
  cited only as supplementary F10 evidence under the mapping's own rule, not
  as the basis of a supported classification.

### 4.2 F13 is resolver-only

F13 pins the DG1B2a **resolver** semantics: waiver matching, expiry at an
explicit `as_of`, out-of-scope waivers, revocation, version binding, lifecycle
ordering and change reporting. It does **not** exercise any runtime consumer
acting on a waiver.

At the pinned commit, the `waived` cause is produced only by
`mneme/decision_governance.py`; no enforcement, hook, CI or MCP path consumes
it. The C1a preview may display the resolver's non-authoritative output. The
mapping records the same limitation, and no F13 test upgrades it into runtime
waiver coverage. F13's file, `tests/test_dg1b2a_canonical_waivers.py`, is in
`GATE_PATHS` and not in `GATE_EXCLUSIONS`; its 81 tests passed at the pinned
commit.

### 4.3 F10 caveat

F10 is pinned by the DG1-mapped
`test_dg1g_f10_evidence_distinction.py`. The mapping records that F10 pins
existing behavior only and does not add the full-identity comparison for
`relevant_enforcement_per_rule`, which remains a consumer obligation. This
record carries that caveat and does not claim more.

### 4.4 Representative test IDs

The full test-ID list is in the mapping. This table provides at least one
representative node ID per fixture, with its gate status, so the record is
self-contained for the §11a.4 audit.

| Fixture | Representative node ID | Gate |
|---|---|---|
| F1 | `tests/test_dg1c_effective_resolver.py::test_parity_with_projection_for_adr_corpora` | `GATE_PATHS` |
| F2 | `tests/test_adr_precedence.py::test_different_scopes_both_active` | `GATE_PATHS` |
| F3 | `tests/test_adr_precedence.py::test_nested_scopes_coexist_no_conflict` | `GATE_PATHS` |
| F4 | `tests/test_dg1p_date_not_authority.py::test_priority_resolves_regardless_of_date` | `GATE_PATHS` |
| F5 | `tests/test_dg1p_date_not_authority.py::test_newer_date_never_wins_a_same_priority_tie` | `GATE_PATHS` |
| F6 | `tests/test_dg1c_effective_resolver.py::test_repo_corpus_resolves_the_superseded_adrs_with_explicit_supersessors` | `GATE_PATHS` |
| F7 | `tests/test_dg1c_effective_resolver.py::test_ineffective_causes_follow_lifecycle_and_never_guess` | `GATE_PATHS` |
| F8 | `tests/test_dg1c_effective_resolver.py::test_input_order_invariance` | `GATE_PATHS` |
| F9 | `tests/test_dg1c_effective_resolver.py::test_irrelevant_decision_invariance` | `GATE_PATHS` |
| F10 | `tests/test_dg1g_f10_evidence_distinction.py::test_a_dg1_outputs_have_no_observation_channel` | `GATE_PATHS` |
| F10 supplementary | `tests/test_adr034_g2_1_harness.py::test_observed_disposition` | `GATE_EXCLUSIONS` (main-only) |
| F11 | `tests/test_dg1e_evidence_identity.py::test_runtime_rule_id_equals_persisted_rule_id` | `GATE_PATHS` |
| F12 | `tests/test_dg1d_change_resolution.py::test_supersession_moves_governance_and_rules` | `GATE_PATHS` |
| F12a | `tests/test_dg1b1_functional_acceptance.py::test_f1_v1_decision_is_globally_eligible` | `GATE_PATHS` |
| F12a | `tests/test_dg1b1_functional_acceptance.py::test_f12_runtime_projection_and_enforcement_inputs_unchanged` | `GATE_PATHS` |
| F13 | `tests/test_dg1b2a_canonical_waivers.py::test_2_time_bound_waiver_applies_only_inside_window` | `GATE_PATHS` |
| F13 | `tests/test_dg1b2a_canonical_waivers.py::test_3_labels_not_matching_or_not_supplied_leave_decision_effective` | `GATE_PATHS` |

## 5. Validation at the pinned commit

### 5.1 Newly executed for this record

Environment: Windows 11 (`Windows-11-10.0.26300-SP0`), CPython `3.12.10`
(64-bit), at `13fae565`. The local runs below were executed on 2026-11-18.

| Validation | Result |
|---|---|
| DG1 suite (16 `tests/test_dg1*.py` files) | **384 passed** in 76.04s |
| DG1B2a file (`tests/test_dg1b2a_canonical_waivers.py`) | **81 passed** in 3.95s |
| §13 gate-cited fixture files (12 files, excluding the main-only F10 supplementary file) | **317 passed** in 58.39s |
| Frozen Layer 1 benchmark (`python scripts/run_test_battery.py benchmark`) | **7/7 PASS**; Layer 2 100%; Layer 1 n=5 mean recall@3 1.00, mean precision@3 0.33, irrelevant injection 100%; anti_pattern 2/2, architecture 2/2, scope 3/3 |

The 12-file fixture run covers the gate-cited F1–F13 files. It is a
newly executed local run, not a re-citation of an older result.

### 5.2 Local gate-battery attempt — not counted as a pass

`python scripts/run_test_battery.py gate` collected the full gate set but did
not complete cleanly:

| Result | Count |
|---|---|
| passed | 5,213 |
| skipped | 14 |
| setup errors | 9 |
| total collected | 5,236 |

All 9 errors are in `tests/open_architecture/test_structural_extraction_experiment.py`
and `tests/open_architecture/test_stage_a_baseline.py`. Every error is a
`subprocess.TimeoutExpired` / `GitUnavailableError` caused by the 60-second
`git clone` of `https://github.com/mbeacom/adrkit.git` in the test setup. No
DG1 test or §13 fixture test failed. This local run is recorded as an
environmental limitation, **not** as a gate pass.

### 5.3 CI at the pinned commit and the tree-identical accepted head

**Pinned commit `13fae565` — GitHub Actions `tests` run
[`44425568986`](https://github.com/MnemeHQ/mneme/actions/runs/44425568986):**

- `main (full canonical suite)`: **success**; 5,957 passed, 20 skipped,
  3 xfailed in 304.77s.
- `pytest (langchain extra)`: **success**; 80 passed.
- `gate (PR battery)`: skipped on the push event, as designed; the gate runs
  on pull requests.

**Accepted head `efdadcc3` — PR #837 `gate (PR battery)` run
[`44422906632`](https://github.com/MnemeHQ/mneme/actions/runs/44422906632):**

- **success**; 5,227 passed, 9 skipped in 180.60s; 5,236 collected.
- The accepted head and the pinned commit have the same tree
  (`60c929a0bbf854daca59d1de7436b6665c15394d`), so this is gate evidence for
  the pinned content.

The closeout claim therefore relies on CI for the full gate/main suite and on
the clean local DG1, DG1B2a, §13 fixture and benchmark runs. The local
open_architecture network timeouts are disclosed and are not counted as a
pass.

## 6. Merged versus released

| Slice / capability | Merged | Released |
|---|---|---|
| DG1A, DG1C, DG1E, DG1D, DG1P, DG1B1 | yes | **yes, `v0.11.0`** |
| DG1F-C1a | yes | **yes, `v0.11.0`** |
| DG1F-C2 (#770) | yes | **no** |
| DG1F-C3a (#777) | yes | **no** |
| DG1B2a (#787) | yes | **no** |

`v0.11.0` is the latest release tag at the pinned commit. No tag contains C2,
C3a or DG1B2a. DG1-S closure is a contract milestone, not a release claim.
C2/C3a/B2a remain merged but unreleased; any release remains a separate
reviewed process.

## 7. What DG1-S does not include

DG1-S is the semantic foundation only. It does not include, and this record
does not claim:

- DG1F-C1b trusted applicability exclusion;
- DG1B2b waiver-aware enforcement;
- resolver-result convergence for the remaining §11 consumers;
- the #497 G1–G3 governance-of-governance controls;
- the deferred precedence-reason / `precedence_lost` feature;
- final DG1G or DG1 closeout;
- any release.

## 8. Open obligations

The following remain open after DG1-S. They are obligations for final DG1G and
DG1 closeout, not conditions of DG1-S.

| Obligation | Current state | Owner / evidence |
|---|---|---|
| **DG1F-C1b — trusted applicability exclusion** | Deferred for the local/runtime applicability-exclusion path. No persisted canonical context declaration, controlled context selection or blocking-seam validation for that path; C1a's caller labels remain preview-only. The trusted CI gate has approved-revision and anti-substitution controls, but not the context declaration C1b requires. | DG1 + CI1/T-08 trust prerequisites; C1 charter §3/§5b; tracker #497 |
| **DG1B2b — waiver-aware enforcement** | Not ready. Trusted labels are a hard blocker; no runtime-suppression case; evaluator pin predates v2 waiver memory; full-corpus exclusion and rank-invariance evidence absent. `as_of` is not a hard blocker for untimed waivers. | DG1 + CI R0 for the evaluator pin; [B2b readiness](../plans/2026-11-10-dg1b2b-readiness-assessment.md); tracker #497 |
| **Remaining ADR-031 §11 resolver consumers** | Open or explicitly deferred: `protect status`/`protect validate`; `protect activate` and the persistence protection-install check; CI evidence-matching APIs; enforcement inputs (`mneme check`, hooks, CI gates, MCP) where C1b/B2b apply; explanation output; C3b. `audit_with_github_claim` and other list-taking APIs remain outside the convergence claim by contract unless that contract changes. | Per-consumer output-contract decision or charter + freeze; [tracker #497 (C3a completion record)](https://github.com/MnemeHQ/mneme/issues/497); post-C3a reconciliation §3 |
| **G1 self-authorization negative** | CI side pinned; host side **unevaluated**. | CI1 #540 / T-08; tracker #497 |
| **G2 authorized transition positive** | **Unevaluated**; DG1B2a pins requester/approver distinctness only as unauthenticated string claims. | CI1 #540 / T-08; tracker #497 |
| **G3 host boundary** | **Partial, bounded.** T-08 G3 live batch #793; P2-first reassessment #822; Phase 2 readiness #823 is not ready/blocked. | T-08; tracker #497 |
| **Deferred precedence reason / `precedence_lost`** | Deferred under the 2026-11-08 erratum. Not part of DG1-S or the §13 floor. | ADR-031 erratum; tracker #497 |
| **Final DG1G / DG1 closeout** | Open. Requires the full §11 sequence and final §13 floor; G1–G3 must be resolved or explicitly dispositioned; any evidence-gated slice without a qualifying case needs an explicit later ADR-031 disposition. Silence is not closure. | DG1 / owner |

## 9. Non-claims

This record does **not** claim:

- DG1, DG1G or ADR-031 §11 completion;
- that DG1-S is accepted before the owner accepts this record;
- that C1b trusted applicability exists;
- that B2b waiver-aware enforcement exists;
- that any remaining resolver consumer is converged;
- that G1, G2 or G3 is closed or passed;
- that any runtime consumer acts on a waiver;
- that F13 is runtime waiver coverage;
- that the `waived` cause is an enforcement input;
- that waivers are authenticated, globally scoped, rule-scoped or path-scoped;
- that `--adr-dir` has evidence identity;
- that section-less memory is reconciled with canonical memory;
- that `precedence_lost` exists or is scheduled;
- that C2/C3a/B2a are released;
- that a trusted `as_of` source or trusted label source exists;
- that this record authorizes a new authoritative consumer, MCP tool, CLI
  enforcement flag or explanation-output contract;
- that this record authorizes a context declaration, a CLI writer for
  applicability, an evaluator-pin change, a version bump or release notes;
- that this record changes the G1–G3 status or ownership;
- that this record authorizes any T-08 Phase 2 item: B1, I3, rows 3–5, or
  `boundary`/`shadowed` population;
- that C2 adds a new `resolve_effective` consumer, or that C1a changes
  stdout, the `mneme.check/v1` payload or exit codes;
- that this record changes tracker #497, the roadmap, a freeze contract or
  release metadata;
- that DG1-S authorizes runtime exclusions, schema or semantic-feature
  changes, a release or T-08 Phase 2 changes;
- that this record adds any fixture, test requirement, charter or Layer 1
  freeze amendment.

## 10. Evidence index

- [ADR-031 §11a](../adr/ADR-031-decision-governance-semantics.md)
- [DG1G fixture-floor mapping](dg1g-fixture-floor-mapping-2026-11-10.md)
- [DG1B2 waiver evidence packet](dg1b2-waiver-evidence-packet-2026-11-10.md)
- [DG1B2b readiness assessment](../plans/2026-11-10-dg1b2b-readiness-assessment.md)
- [DG1 post-C3a reconciliation](dg1-post-c3a-reconciliation-2026-11-09.md)
- [DG1 v0.11.0 architecture reconciliation](dg1-v0110-architecture-reconciliation-2026-11-08.md)
- [T-08 G3 host-boundary live record](t08-g3-host-boundary-live-2026-11-11.md)
- [T-08 G3 re-assessment after P2-first](t08-g3-reassessment-p2-first-2026-11-17.md)
- [T-08 Phase 2 readiness](../plans/2026-11-17-t08-phase2-readiness-assessment.md)
- [CI R0 S7 closure](ci-r0-s7-closure-2026-11-03.md)
- [PR #837 — ADR-031 §11a](https://github.com/MnemeHQ/mneme/pull/837)
- [PR #838 — this closeout record](https://github.com/MnemeHQ/mneme/pull/838)
- [Tracker #497](https://github.com/MnemeHQ/mneme/issues/497)
- [CI1 tracker #540](https://github.com/MnemeHQ/mneme/issues/540)

## 11. Review and acceptance

- **Independent review:** PR #838; the exact reviewed head and verdict are
  recorded in that PR's conversation.
- **Owner acceptance:** required before merge. This draft does not claim it.
- **Effect of acceptance:** after independent review, owner acceptance and
  merge, this record is the DG1-S §11a.4 closeout evidence. DG1 and DG1G
  remain open.
- **No automatic closure:** this record does not close DG1-S by itself, and it
  does not authorize any work listed in §8.
