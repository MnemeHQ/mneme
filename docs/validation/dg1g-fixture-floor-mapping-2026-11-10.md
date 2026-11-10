# DG1G fixture-floor mapping: partial coverage record (2026-11-10)

> **Partial fixture-coverage record, not a closeout.** Maps every ADR-031 §13
> fixture and every #497 governance-of-governance control to the exact test or
> validation record that pins it, and classifies each as **supported**,
> **partial**, **missing**, **blocked** or **unevaluated**. ADR-031 §11 does
> not allow DG1G closeout before the full sequence is complete, so **DG1G and
> DG1 remain open**. This record authorizes no new test, enforcement change,
> waiver, charter, freeze amendment or release.
> **Anchor:** `main` at `b5e0e1dd`. Basis:
> [DG1 post-C3a reconciliation](dg1-post-c3a-reconciliation-2026-11-09.md)
> (#781) §5–§6; [ADR-031](../adr/ADR-031-decision-governance-semantics.md)
> §13; tracker [#497](https://github.com/MnemeHQ/mneme/issues/497).

## 0. Summary

| Classification | Count | Items |
|---|---|---|
| supported | 11 | §13 fixtures F1–F9, F11, F12 |
| partial | 2 | F10 (ADR-029 §6), G3 host-boundary control |
| missing | 0 | none beyond the partials |
| blocked | 1 | F13 waiver fixtures (DG1B2 has no qualifying case) |
| unevaluated | 2 | G1 self-authorization control (host side), G2 authorized-transition control |

Two obligations are kept separate (§4): the **ADR-031 §13 fixture floor**
(owned by DG1) and the roadmap's **cross-cutting four-layer acceptance test**
(P0, owned outside DG1). The second can supply evidence for DG1G but is not a
DG1G gate without an explicit architectural decision.

## 1. Classification rules

- **supported:** at least one committed test asserts the fixture's property
  directly and runs in the gate battery.
- **partial:** the property is evidenced, but not by a DG1-mapped test, or
  only one side of a control is pinned.
- **missing:** no test or record pins the property.
- **blocked:** the property cannot be tested until an evidence-gated slice
  exists.
- **unevaluated:** a test or run is possible but has not been performed; it
  is never counted as passed.

Test IDs are relative to `tests/`. "Gate" means the test file is in
`GATE_PATHS` of `scripts/run_test_battery.py`; a file listed in
`GATE_EXCLUSIONS` runs only in the `main` battery and is cited as
supplementary evidence, never as the basis of a "supported" classification.

This is a **fixture-to-test mapping**, not a complete inventory: where a row
cites a whole suite or a range (F12, F12a), the named test IDs are
representative, and the suite as a whole is the pinning evidence.

## 2. ADR-031 §13 fixture floor

| # | §13 fixture | Pinned by (test IDs) | Gate | Class |
|---|---|---|---|---|
| F1 | 0.10.0 parity | `test_dg1c_effective_resolver.py::test_parity_with_projection_for_adr_corpora`, `::test_parity_with_projection_for_canonical_memory`, `::test_parity_with_projection_for_migrated_memory`, `::test_persisted_v1_supersession_conflict_keeps_projection_parity`, `::test_persisted_v1_dangling_supersedes_keeps_projection_parity`; C2/C3a goldens `test_dg1f_c2_golden_parity.py`, `test_dg1f_c3a_golden_parity.py` | yes | supported |
| F2 | different-scope co-governance | `test_adr_precedence.py::test_different_scopes_both_active` | yes | supported (pre-DG1 test; mapped here) |
| F3 | broader/narrower coexistence | `test_adr_precedence.py::test_nested_scopes_coexist_no_conflict`, `::test_output_sorted_by_specificity_descending_then_priority` | yes | supported (pre-DG1 tests; mapped here) |
| F4 | same-scope priority resolution | `test_dg1p_date_not_authority.py::test_priority_resolves_regardless_of_date`; `test_adr_precedence.py::test_same_scope_higher_priority_wins`, `::test_same_scope_exception_loses_to_normal` | yes | supported |
| F5 | same-scope ambiguity, no date tiebreak | `test_dg1p_date_not_authority.py::test_newer_date_never_wins_a_same_priority_tie`, `::test_partial_resolution_skips_only_the_tied_scope`, `::test_import_reports_a_date_only_tie_without_suggesting_date`, `::test_decision_mcp_adr_dir_refuses_a_date_only_tie`; `test_adr_precedence.py::test_same_scope_same_priority_different_dates_is_ambiguous` | yes | supported |
| F6 | supersession | `test_dg1c_effective_resolver.py::test_repo_corpus_resolves_the_superseded_adrs_with_explicit_supersessors`, `::test_superseded_by_status_alone_needs_no_relationship`, `::test_supersession_declared_by_a_non_effective_decision_is_not_in_force`, `::test_active_target_of_in_force_supersession_stays_effective_with_finding`, `::test_dangling_supersedes_is_reported_without_changing_the_effective_set`; `test_dg1p_date_not_authority.py::test_explicit_supersession_resolves_a_tie_even_when_older`; `test_adr_precedence.py::test_explicit_supersedes_removes_target`, `::test_explicit_supersedes_wins_over_priority`, `::test_chain_of_supersedes_only_keeps_terminal_record` | yes | supported |
| F7 | lifecycle exclusion with honest `lifecycle_inactive` cause | `test_dg1c_effective_resolver.py::test_ineffective_causes_follow_lifecycle_and_never_guess`, `::test_unknown_lifecycle_fails_closed`; `test_dg1f_c2_lifecycle_consolidation.py::test_5_widening_the_authority_moves_every_consumer` | yes | supported |
| F8 | input-order invariance | `test_dg1c_effective_resolver.py::test_input_order_invariance`; `test_dg1d_change_resolution.py::test_change_set_is_input_order_invariant`; `test_dg1b1_decision_applicability.py::test_resolution_is_invariant_to_record_order`, `::test_label_set_is_order_and_duplicate_invariant` | yes | supported |
| F9 | irrelevant-decision invariance; context-path invariance for the parity resolver | `test_dg1c_effective_resolver.py::test_irrelevant_decision_invariance`, `::test_context_invariance_for_v1_semantics`; `test_dg1b1_decision_applicability.py::test_irrelevant_context_labels_do_not_change_the_result` | yes | supported |
| F10 | configured versus execution-observed evidence (ADR-029 §6) | no DG1-mapped test. Evidence: [#761 audit](adr029-evidence-completeness-audit-2026-11-08.md) (E-1, E-8), [Verification step 3](verification-step3-e2e-fixture-2026-11-09.md), [step 4](verification-step4-independent-review-2026-11-09.md); supplementary, main-only (`GATE_EXCLUSIONS`): `test_adr034_g2_1_harness.py::test_observed_disposition` (numeric path only) | no | **partial** |
| F11 | canonical rule identity through enforcement; section-less fail-closed evidence | `test_dg1e_evidence_identity.py::test_runtime_rule_id_equals_persisted_rule_id`, `::test_canonical_memory_trace_carries_complete_evidence_identity`, `::test_check_json_reports_canonical_identity`, `::test_adr_dir_view_uses_canonical_rule_ids_without_version_identity`, `::test_section_less_memory_has_rule_identity_but_fails_closed`, `::test_legacy_prose_violation_identity_is_incomplete`, `::test_verdicts_do_not_depend_on_evidence_identity` | yes | supported |
| F12 | snapshot A → B change explanations | all 14 tests in `test_dg1d_change_resolution.py`, incl. `test_dg1d_change_resolution.py::test_supersession_moves_governance_and_rules`, `::test_version_evolution_reports_version_and_rule_changes`, `::test_persisted_snapshots_report_deprecation_and_retired_rules`, `::test_resolutions_from_different_semantics_are_not_comparable`; applicability: `test_dg1b1_functional_acceptance.py::test_f10_resolve_change_reports_governed_scope_change` | yes | supported |
| F12a | applicability fixtures (added with DG1B1) | `test_dg1b1_decision_applicability.py` (62), the twelve F1–F12 tests in `test_dg1b1_functional_acceptance.py` (from `test_dg1b1_functional_acceptance.py::test_f1_v1_decision_is_globally_eligible` to `::test_f12_runtime_projection_and_enforcement_inputs_unchanged`); three-state context `test_dg1f_c2_lifecycle_consolidation.py::test_1_unknown_context_conservatively_includes_and_never_claims_a_match`, `::test_1b_context_states_are_distinct_and_validated` | yes | supported |
| F13 | waiver fixtures, incl. expiry at an explicit `as_of` and out-of-scope waivers | none | n/a | **blocked** (DG1B2: no verified, decision-version-bound waiver case) |

Notes:

- F12a is counted with F12 in §0 (applicability fixtures are added by their
  slice under §13; they are supported).
- **F10 gap, precisely:** the evidence distinctions (configured, execution
  observed, relevant enforcement observed) are established and reviewed by
  the Verification track, but no test in the DG1 suite asserts that a DG1
  resolution or evidence identity never upgrades configured evidence to
  observed. Closing it needs a DG1-mapped test, which this record does not
  authorize.

## 3. #497 governance-of-governance controls

| # | Control (#497, 7 Nov intake) | CI side | Host side | Class |
|---|---|---|---|---|
| G1 | Self-authorization negative: a change alters its own memory, rule, waiver, authority source or instructions and introduces a violation | pinned: CI1 live V2/V3/V3a (#540); C4 `test_adr033_c4_ci_gate.py::test_symlink_and_submodule_on_protected_paths_are_policy_refusals_not_mode`, `::test_valid_trusted_surface_entries_protect_their_paths`, `::test_path_refusals`; R0 S7 records `.mneme/` changes merge only through the human bypass | not tested: no host test of a change that alters its own governance inputs (the related wrong-source observation is recorded under G3) | **unevaluated** (host side) |
| G2 | Authorized transition positive: a distinct human approves a governance revision or waiver through the accepted path; a previous PASS cannot be reused for a new authority state | background only: C4 and R0 S7 record a procedural human bypass for `.mneme/` changes. That is not a positive test of an authorized, version-bound transition; no test binds approver identity, decision version, scope and effective time | none | **unevaluated** |
| G3 | Host boundary: missing local declaration, removed hook, changed tool configuration or altered workflow is never an authoritative PASS | partial: C4 O4/O5 (missing or malformed base memory → UNEVALUATED), `test_adr033_c4_ci_gate.py::test_unnormalizable_path_is_refused_for_every_status_and_mode`; R0 S7 records the R6 administrator-credential exposure | partial, with a **known bounded host risk**: [T-08 D6 C4](dg1f-t08-d6-mneme-memory-c4-live-2026-10-16.md) observed a wrong-source **false complete PASS** (an uncommitted `.claude/settings.local.json` `env.MNEME_MEMORY` redirected enforcement to another repository's memory). The same record shows the agent's attempted local-settings edit was denied by the host, so no agent-controlled bypass is established. Also: ADR-033 availability (opt-in), `test_dg1f_g4_cli_memory_failures.py` (corrupt memory is an operational error); hook removal and administrator bypass remain possible | **partial** |

Ownership (unchanged from #497): DG1 owns canonical decision and waiver
authority and lifecycle; CI1 (#540) owns protected source, host credentials,
merged revision and trusted enforcement. The host-side gaps belong to T-08
and CI1, not to a DG1 implementation slice.

## 4. Two obligations, two owners

| Obligation | Owner | Relation to DG1G |
|---|---|---|
| ADR-031 §13 fixture floor (§2) | DG1 | required for any future DG1G closeout |
| Roadmap four-layer acceptance test (Governance → Guidance → Enforcement → Verification, P0) | cross-cutting, outside DG1; the Verification track holds the bounded enforcement-evidence slice | may supply evidence for DG1G; **not** a DG1G gate unless an explicit architectural decision makes it one; this record does not duplicate the Verification track |

## 5. What would be needed before any DG1G closeout (not authorized here)

1. DG1B2 delivered under its own evidence gate, with F13 waiver fixtures.
2. A DG1-mapped test for F10.
3. A decision, with CI1 and T-08, on the host-side G1–G3 controls.
4. The remaining ADR-031 §11 sequence complete or explicitly scoped by an
   ADR-031 decision.

Until then every entry above keeps its classification; nothing UNEVALUATED or
BLOCKED is counted as passed.

## 6. Non-claims

No DG1G, DG1F or DG1 completion is claimed. No test was added. All 56 cited
test IDs were checked to exist by collection at the anchor, and every cited
test file was run locally on Windows at the anchor: 745 passed, 5 skipped,
0 failed. Gate membership was read from `GATE_PATHS` and `GATE_EXCLUSIONS` in
`scripts/run_test_battery.py`: every file cited for a supported fixture is in
the gate; `test_adr034_g2_1_harness.py` is main-only and cited only as
supplementary F10 evidence. The CI and host evidence cited for §3 is from
the linked records, not re-run here.
