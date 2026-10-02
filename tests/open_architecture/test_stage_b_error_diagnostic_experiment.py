"""
tests.open_architecture.test_stage_b_error_diagnostic_experiment — Tests for B-T1A Diagnostics.

Validates:
1. Exact frozen Stage B evidence hash is required fail-closed
2. Exactly 100 references are diagnosed
3. Scope and relationship diagnostics exist for all 100 references
4. Existing baseline exact scope/relationship metrics (0.0) are reproduced
5. Diagnostic PRF calculations are deterministic
6. Conservative scope-expression canonicalization obeys its narrow contract
7. No fuzzy matching occurs
8. Zero network/model calls occur
9. Two runs produce byte-identical summary JSON and JSONL artifacts
10. Fail-closed output directory checks
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mneme.open_architecture.harness import (
    FROZEN_BASELINE_ID,
    FROZEN_REFERENCE_CORPUS_HASH,
)
from mneme.open_architecture.stage_b_baseline import (
    FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH,
)
from mneme.open_architecture.stage_b_error_diagnostic_experiment import (
    EXPERIMENT_ID,
    FROZEN_PARENT_MAIN_SHA,
    BT1AExperimentResult,
    canonicalize_scope_expression,
    execute_b_t1a_experiment,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROVENANCE_DIR = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "baseline_stage_b"
OUTCOMES_PATH = PROVENANCE_DIR / "classifier_outcomes.jsonl"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "manifest.yaml"
REF_DIR = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "reference_decisions"


# ── Canonicalizer Narrow Contract Tests ────────────────────────────────────────


class TestScopeCanonicalizerContract:
    def test_replaces_backslashes(self):
        assert canonicalize_scope_expression("docs\\adr\\0001.md") == "docs/adr/0001.md"

    def test_collapses_repeated_slashes(self):
        assert canonicalize_scope_expression("docs//adr///0001.md") == "docs/adr/0001.md"

    def test_strips_leading_dot_slash(self):
        assert canonicalize_scope_expression("./docs/adr") == "docs/adr"
        assert canonicalize_scope_expression("./src/foo/bar.go") == "src/foo/bar.go"

    def test_strips_trailing_slash_except_root(self):
        assert canonicalize_scope_expression("docs/adr/") == "docs/adr"
        assert canonicalize_scope_expression("packages/core/") == "packages/core"
        assert canonicalize_scope_expression("/") == "/"

    def test_none_and_empty_preserved(self):
        assert canonicalize_scope_expression(None) is None
        assert canonicalize_scope_expression("") == ""

    def test_whitespace_preserved_not_stripped(self):
        # Leading and trailing whitespace must NOT be stripped by narrow canonicalizer
        assert canonicalize_scope_expression("  docs/adr  ") == "  docs/adr  "
        assert canonicalize_scope_expression(" packages/core ") == " packages/core "
        assert canonicalize_scope_expression("   ") == "   "

    def test_no_fuzzy_or_glob_expansion(self):
        # Glob patterns and filenames must be preserved verbatim without expansion
        assert canonicalize_scope_expression("docs/adr/*.md") == "docs/adr/*.md"
        assert canonicalize_scope_expression("packages/**") == "packages/**"
        assert canonicalize_scope_expression("affects[].entity") == "affects[].entity"
        assert canonicalize_scope_expression("mbeacom/adrkit") == "mbeacom/adrkit"


# ── Experiment Execution & Acceptance Tests ────────────────────────────────────


@pytest.fixture(scope="module")
def experiment_result() -> BT1AExperimentResult:
    return execute_b_t1a_experiment()


class TestBT1AExperimentExecution:
    def test_1_frozen_evidence_hash_bound_and_matches(self, experiment_result: BT1AExperimentResult):
        from mneme.open_architecture.harness import FROZEN_BASELINE_CONFIG_HASH
        assert experiment_result.experiment_id == EXPERIMENT_ID
        assert experiment_result.baseline_id == FROZEN_BASELINE_ID
        assert experiment_result.baseline_configuration_hash == FROZEN_BASELINE_CONFIG_HASH
        assert experiment_result.parent_main_sha == FROZEN_PARENT_MAIN_SHA
        assert experiment_result.reference_corpus_hash == FROZEN_REFERENCE_CORPUS_HASH
        assert experiment_result.semantic_content_hash == FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH
        assert experiment_result.experiment_profile_hash == "8aa524b37dcd5ff946f6d1b001fe7edc"

    def test_profile_hash_sensitivity_to_diagnostic_rules(self, experiment_result: BT1AExperimentResult):
        import copy
        from mneme.open_architecture.stage_b_error_diagnostic_experiment import (
            B_T1A_DIAGNOSTIC_PROFILE,
            compute_b_t1a_profile_hash,
        )

        # 1. Deterministic repeated computation
        h1 = compute_b_t1a_profile_hash()
        h2 = compute_b_t1a_profile_hash()
        assert h1 == h2 == experiment_result.experiment_profile_hash

        # 2. Mutating scope canonicalization changes the profile hash
        mut_scope = copy.deepcopy(B_T1A_DIAGNOSTIC_PROFILE)
        mut_scope["scope"]["canonicalization"].append("strip_whitespace")
        h_mut_scope = compute_b_t1a_profile_hash(diagnostic_profile=mut_scope)
        assert h_mut_scope != experiment_result.experiment_profile_hash

        # 3. Mutating relationship target decomposition changes the profile hash
        mut_rel = copy.deepcopy(B_T1A_DIAGNOSTIC_PROFILE)
        mut_rel["relationships"]["target_decomposition"] = "altered_rule"
        h_mut_rel = compute_b_t1a_profile_hash(diagnostic_profile=mut_rel)
        assert h_mut_rel != experiment_result.experiment_profile_hash

    def test_target_decomposition_invariant_holds(self, experiment_result: BT1AExperimentResult):
        g_rel = experiment_result.global_relationship_diagnostics
        assert g_rel.expected_relationship_tuples == 19
        assert g_rel.expected_tuples_with_type_present == 18
        assert g_rel.exact_tuple_matches == 0
        assert g_rel.correct_type_wrong_target_tuples == 18
        assert g_rel.missing_relationship_type_tuples == 1

        # Global invariant: expected == exact + wrong_target + missing_type
        assert (
            g_rel.expected_relationship_tuples
            == g_rel.exact_tuple_matches + g_rel.correct_type_wrong_target_tuples + g_rel.missing_relationship_type_tuples
        )
        assert (
            g_rel.expected_tuples_with_type_present
            == g_rel.exact_tuple_matches + g_rel.correct_type_wrong_target_tuples
        )

        # Per-repository invariant
        for repo_id, r in experiment_result.per_repository_relationship.items():
            assert (
                r.expected_relationship_tuples
                == r.exact_tuple_matches + r.correct_type_wrong_target_tuples + r.missing_relationship_type_tuples
            )
            assert (
                r.expected_tuples_with_type_present
                == r.exact_tuple_matches + r.correct_type_wrong_target_tuples
            )

        # Per-reference invariant
        for d in experiment_result.reference_relationship_diagnostics:
            assert (
                d.expected_relationship_tuples
                == d.exact_tuple_matches + d.correct_type_wrong_target_tuples + d.missing_relationship_type_tuples
            )
            assert (
                d.expected_tuples_with_type_present
                == d.exact_tuple_matches + d.correct_type_wrong_target_tuples
            )

    def test_reference_corpus_hash_mutation_fails_closed(self, tmp_path: Path):
        import shutil

        # Copy reference corpus to temp dir
        mutated_ref_dir = tmp_path / "mutated_reference_decisions"
        shutil.copytree(REF_DIR, mutated_ref_dir)

        # Mutate one reference decision
        target_file = mutated_ref_dir / "adrkit" / "ref-adrkit-001.jsonl"
        lines = target_file.read_text(encoding="utf-8").splitlines()
        first_rec = json.loads(lines[0])
        first_rec["normalized_decision"] = "Corrupted semantic decision text"
        target_file.write_text(json.dumps(first_rec) + "\n", encoding="utf-8")

        with pytest.raises(ValueError, match="Reference corpus hash mismatch"):
            execute_b_t1a_experiment(reference_corpus_dir=mutated_ref_dir)

    def test_2_and_3_exactly_100_references_diagnosed_with_both_dimensions(
        self, experiment_result: BT1AExperimentResult
    ):
        assert len(experiment_result.reference_scope_diagnostics) == 100
        assert len(experiment_result.reference_relationship_diagnostics) == 100

        scope_ids = [d.reference_id for d in experiment_result.reference_scope_diagnostics]
        rel_ids = [d.reference_id for d in experiment_result.reference_relationship_diagnostics]

        assert len(set(scope_ids)) == 100
        assert len(set(rel_ids)) == 100
        assert scope_ids == rel_ids

    def test_4_baseline_exact_accuracy_reproduced(self, experiment_result: BT1AExperimentResult):
        # Both scope and relationship exact accuracy must be 0.0, reproducing baseline
        assert experiment_result.global_scope_diagnostics.baseline_exact_accuracy == 0.0
        assert experiment_result.global_relationship_diagnostics.baseline_exact_accuracy == 0.0

        for repo_id in ["adrkit", "archlint", "gsa_agentic_coding_quickstart", "helix", "modonome"]:
            assert experiment_result.per_repository_scope[repo_id].baseline_exact_accuracy == 0.0
            assert experiment_result.per_repository_relationship[repo_id].baseline_exact_accuracy == 0.0

    def test_5_deterministic_prf_metrics(self, experiment_result: BT1AExperimentResult):
        g_scope = experiment_result.global_scope_diagnostics
        assert g_scope.total_references == 100
        assert abs(g_scope.exact_tuple_micro_precision - 0.102389) < 1e-4
        assert abs(g_scope.exact_tuple_micro_recall - 0.262009) < 1e-4
        assert abs(g_scope.exact_tuple_micro_f1 - 0.147239) < 1e-4
        assert abs(g_scope.canonical_tuple_micro_f1 - 0.179141) < 1e-4
        assert abs(g_scope.scope_type_only_micro_f1 - 0.481262) < 1e-4

        g_rel = experiment_result.global_relationship_diagnostics
        assert g_rel.total_references == 100
        assert g_rel.expected_empty_count == 87
        assert g_rel.predicted_empty_count == 0
        assert g_rel.false_positives_on_empty == 86
        assert abs(g_rel.type_only_micro_recall - 0.923077) < 1e-4

    def test_6_mismatch_category_integrity(self, experiment_result: BT1AExperimentResult):
        s_cats = experiment_result.global_scope_diagnostics.mismatch_category_counts
        assert sum(s_cats.values()) == 100
        assert s_cats["mixed_mismatch"] == 75
        assert s_cats["over_prediction"] == 13
        assert s_cats["wrong_scope_type"] == 11
        assert s_cats["correct_type_wrong_expression"] == 1

        r_cats = experiment_result.global_relationship_diagnostics.mismatch_category_counts
        assert sum(r_cats.values()) == 100
        assert r_cats["false_positive_on_empty"] == 86
        assert r_cats["mixed_mismatch"] == 12
        assert r_cats["wrong_relationship_type"] == 1
        assert r_cats["normalization_failure"] == 1

    def test_7_no_network_or_model_calls(self, monkeypatch):
        import socket

        def _forbidden_connect(*args, **kwargs):
            raise AssertionError("Network connection attempted during offline diagnostic experiment!")

        monkeypatch.setattr(socket.socket, "connect", _forbidden_connect)
        res = execute_b_t1a_experiment()
        assert res.global_scope_diagnostics.total_references == 100

    def test_8_artifact_emission_and_determinism(self, tmp_path: Path):
        run1_dir = tmp_path / "run1"
        run2_dir = tmp_path / "run2"

        res1 = execute_b_t1a_experiment(output_dir=run1_dir)
        res2 = execute_b_t1a_experiment(output_dir=run2_dir)

        summary1 = (run1_dir / "b_t1a_summary.json").read_bytes()
        summary2 = (run2_dir / "b_t1a_summary.json").read_bytes()
        assert summary1 == summary2

        diag1 = (run1_dir / "b_t1a_diagnostics.jsonl").read_bytes()
        diag2 = (run2_dir / "b_t1a_diagnostics.jsonl").read_bytes()
        assert diag1 == diag2

        assert res1.experiment_profile_hash == res2.experiment_profile_hash

    def test_9_non_empty_output_dir_fails_closed(self, tmp_path: Path):
        out_dir = tmp_path / "existing"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "marker.txt").write_text("exists", encoding="utf-8")

        with pytest.raises(ValueError, match="exists and is non-empty"):
            execute_b_t1a_experiment(output_dir=out_dir)

    def test_10_all_five_repositories_present(self, experiment_result: BT1AExperimentResult):
        expected_repos = {"adrkit", "archlint", "gsa_agentic_coding_quickstart", "helix", "modonome"}
        assert set(experiment_result.per_repository_scope.keys()) == expected_repos
        assert set(experiment_result.per_repository_relationship.keys()) == expected_repos

    def test_11_sampling_categories_present(self, experiment_result: BT1AExperimentResult):
        expected_cats = {
            "clear_explicit",
            "scoped",
            "lifecycle_or_supersession",
            "ambiguous_or_conflicting",
            "enforcement_potential",
            "unusual_or_difficult",
        }
        assert set(experiment_result.per_sampling_category_scope.keys()) == expected_cats
        assert set(experiment_result.per_sampling_category_relationship.keys()) == expected_cats
