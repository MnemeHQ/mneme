"""
tests.open_architecture.test_stage_b_relationship_diagnostic_experiment — Tests for B-T1B.

Validates:
1. Exact frozen Stage B semantic hash is required fail-closed
2. Mutated reference corpus fails closed
3. Exactly 100 relationship references are analyzed
4. Exactly 19 expected tuples enter target attribution and sum to 19
5. Target attribution categories are mutually exclusive and exhaustive
6. Target-form taxonomy categories are mutually exclusive
7. Target-form precedence is deterministic
8. '2026' and other years are NOT parsed as ADR aliases
9. Version numbers are NOT parsed as ADR aliases
10. Work-item IDs are NOT parsed as ADR aliases
11. Explicit ADR aliases normalize correctly
12. ADR filenames normalize correctly
13. No arbitrary substring ADR extraction
14. Expected-target attribution sums to 19
15. Classifier-visible grounding uses only raw_evidence
16. No fuzzy matching occurs
17. Relationship-type x target-form cross-tab totals equal parsed prediction total
18. Expected-empty and expected-non-empty partitions reconcile with global totals
19. Truncation/failure accounting reconciles with 100 outcomes
20. No hypothetical tuple count is generated for truncated output
21. Diagnostic profile hash changes when target taxonomy changes
22. Diagnostic profile hash changes when ADR parsing changes
23. Diagnostic profile hash changes when decomposition rules change
24. Repeated runs emit byte-identical artifacts
25. Zero network/model calls occur
26. Frozen and canonical modules remain unmodified
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from mneme.open_architecture.harness import (
    FROZEN_BASELINE_CONFIG_HASH,
    FROZEN_BASELINE_ID,
    FROZEN_REFERENCE_CORPUS_HASH,
)
from mneme.open_architecture.stage_b_baseline import (
    FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH,
)
from mneme.open_architecture.stage_b_relationship_diagnostic_experiment import (
    B_T1B_DIAGNOSTIC_PROFILE,
    DECOMP_EXACT_TYPE_ALIAS_TARGET,
    DECOMP_EXACT_TYPE_EXACT_TARGET,
    DECOMP_NORMALIZATION_FAILURE,
    DECOMP_TARGET_NOT_PREDICTED_AND_NOT_VISIBLE,
    DECOMP_TARGET_NOT_PREDICTED_BUT_VISIBLE,
    DECOMP_WRONG_TYPE_ALIAS_TARGET,
    EXPERIMENT_ID,
    FROZEN_PARENT_MAIN_SHA,
    ORDERED_DECOMPOSITION_CATEGORIES,
    ORDERED_TARGET_FORMS,
    TARGET_FORM_ADR,
    TARGET_FORM_BARE_IDENTIFIER,
    TARGET_FORM_FREE_TEXT,
    TARGET_FORM_NULL,
    TARGET_FORM_PACKAGE,
    TARGET_FORM_PATH,
    TARGET_FORM_REPO_OR_URL,
    TARGET_FORM_WORK_ITEM,
    BT1BExperimentResult,
    classify_target_form,
    compute_b_t1b_profile_hash,
    execute_b_t1b_experiment,
    parse_adr_alias,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROVENANCE_DIR = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "baseline_stage_b"
OUTCOMES_PATH = PROVENANCE_DIR / "classifier_outcomes.jsonl"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "manifest.yaml"
REF_DIR = REPO_ROOT / "benchmarks" / "open_architecture" / "batch_01" / "reference_decisions"


# ── Target Form Taxonomy & Precedence Tests ───────────────────────────────────


class TestTargetFormTaxonomyAndPrecedence:
    def test_6_target_form_taxonomy_categories_mutually_exclusive(self):
        samples = [
            None,
            "",
            "   ",
            "0005",
            "ADR-0005",
            "ADR 0002 (0002-postgres.md)",
            "0005-evaluator.md",
            "SC-010",
            "WI-006",
            "FR-021",
            "Spike 009",
            "#123",
            "T014→T014a cycle",
            "@adrkit/core",
            "@modelcontextprotocol/server@2.0.0",
            "https://example.com/spec",
            "github.com/GSA-TTS/patterns",
            "docs/adr/NNNN-kebab.md",
            "packages/evaluator/src/index.ts",
            "bunfig.toml",
            "git",
            "Docker",
            "Postgres",
            "2026",
            "1999",
            "round-trip sync / conflict resolution",
            "external decision record systems",
        ]
        for s in samples:
            cat = classify_target_form(s)
            assert cat in ORDERED_TARGET_FORMS
            # Category must be a non-empty string and match exactly one
            matches = [c for c in ORDERED_TARGET_FORMS if c == cat]
            assert len(matches) == 1

    def test_7_target_form_precedence_deterministic(self):
        # 1. null_target wins over everything
        assert classify_target_form(None) == TARGET_FORM_NULL
        assert classify_target_form("") == TARGET_FORM_NULL
        assert classify_target_form("   ") == TARGET_FORM_NULL

        # 2. adr_identifier_like wins over bare_identifier or path
        assert classify_target_form("0005") == TARGET_FORM_ADR
        assert classify_target_form("ADR-0005") == TARGET_FORM_ADR
        assert classify_target_form("0005-evaluator.md") == TARGET_FORM_ADR
        assert classify_target_form("docs/adr/0005-evaluator.md") == TARGET_FORM_ADR

        # 3. work_item_like wins over bare_identifier
        assert classify_target_form("SC-010") == TARGET_FORM_WORK_ITEM
        assert classify_target_form("WI-006") == TARGET_FORM_WORK_ITEM
        assert classify_target_form("FR-021") == TARGET_FORM_WORK_ITEM
        assert classify_target_form("Spike 009") == TARGET_FORM_WORK_ITEM
        assert classify_target_form("#123") == TARGET_FORM_WORK_ITEM
        assert classify_target_form("T014→T014a cycle") == TARGET_FORM_WORK_ITEM

        # 4. package_identifier_like wins over path
        assert classify_target_form("@adrkit/core") == TARGET_FORM_PACKAGE
        assert classify_target_form("@modelcontextprotocol/server@2.0.0") == TARGET_FORM_PACKAGE

        # 5. repository_or_url_like wins over path
        assert classify_target_form("https://github.com/org/repo") == TARGET_FORM_REPO_OR_URL
        assert classify_target_form("github.com/GSA-TTS/patterns") == TARGET_FORM_REPO_OR_URL

        # 6. file_or_code_path_like
        assert classify_target_form("docs/EVALUATOR_RUBRIC.md") == TARGET_FORM_PATH
        assert classify_target_form("packages/evaluator/src/index.ts") == TARGET_FORM_PATH
        assert classify_target_form("bunfig.toml") == TARGET_FORM_PATH

        # 7. bare_identifier
        assert classify_target_form("git") == TARGET_FORM_BARE_IDENTIFIER
        assert classify_target_form("Postgres") == TARGET_FORM_BARE_IDENTIFIER
        assert classify_target_form("2026") == TARGET_FORM_BARE_IDENTIFIER
        assert classify_target_form("1999") == TARGET_FORM_BARE_IDENTIFIER

        # 8. free_text_phrase
        assert classify_target_form("external decision record systems") == TARGET_FORM_FREE_TEXT
        assert classify_target_form("Zod schema") == TARGET_FORM_FREE_TEXT


# ── ADR Alias Parser Contract Tests ───────────────────────────────────────────


class TestADRAliasParserContract:
    def test_8_years_not_parsed_as_adr_alias(self):
        assert parse_adr_alias("2026") is None
        assert parse_adr_alias("1999") is None
        assert parse_adr_alias("2026-09-13") is None
        assert parse_adr_alias("2024-01-01") is None

    def test_9_versions_not_parsed_as_adr_alias(self):
        assert parse_adr_alias("0.1.0") is None
        assert parse_adr_alias("v0.34") is None
        assert parse_adr_alias("1.2.3") is None
        assert parse_adr_alias("v2.0.0") is None

    def test_10_work_items_not_parsed_as_adr_alias(self):
        assert parse_adr_alias("WI-006") is None
        assert parse_adr_alias("SC-010") is None
        assert parse_adr_alias("FR-021") is None
        assert parse_adr_alias("DEC-123") is None
        assert parse_adr_alias("ISSUE-42") is None
        assert parse_adr_alias("Spike 009") is None

    def test_11_explicit_adr_aliases_normalize_correctly(self):
        assert parse_adr_alias("5") == "0005"
        assert parse_adr_alias("15") == "0015"
        assert parse_adr_alias("999") == "0999"
        assert parse_adr_alias("0005") == "0005"
        assert parse_adr_alias("0014") == "0014"
        assert parse_adr_alias("ADR-5") == "0005"
        assert parse_adr_alias("ADR 5") == "0005"
        assert parse_adr_alias("ADR-0005") == "0005"
        assert parse_adr_alias("ADR 0005") == "0005"
        assert parse_adr_alias("ADR 0002 (0002-postgres-role-split-rls.md)") == "0002"
        assert parse_adr_alias("ADR-0014 (0014-same-origin-api-gateway.md)") == "0014"
        assert parse_adr_alias("ADR-002 (Shadow Mode)") == "0002"

    def test_12_adr_filenames_normalize_correctly(self):
        assert parse_adr_alias("0005-evaluator.md") == "0005"
        assert parse_adr_alias("006-checker-independence.md") == "0006"
        assert parse_adr_alias("docs/adr/0005-evaluator.md") == "0005"
        assert parse_adr_alias("docs/adr/0001.md") == "0001"
        assert parse_adr_alias("ADR-006-checker-independence.md") == "0006"

    def test_13_no_arbitrary_substring_adr_extraction(self):
        assert parse_adr_alias("section 1") is None
        assert parse_adr_alias("max 500 chars") is None
        assert parse_adr_alias("contains 0005 in middle of sentence") is None
        assert parse_adr_alias("some random 1234 text") is None
        assert parse_adr_alias("something_else") is None
        assert parse_adr_alias(None) is None
        assert parse_adr_alias("") is None
        assert parse_adr_alias("   ") is None


# ── Experiment Execution & Acceptance Tests ────────────────────────────────────


@pytest.fixture(scope="module")
def experiment_result() -> BT1BExperimentResult:
    return execute_b_t1b_experiment()


class TestBT1BExperimentExecution:
    def test_1_frozen_evidence_hash_bound_and_matches(self, experiment_result: BT1BExperimentResult):
        assert experiment_result.experiment_id == EXPERIMENT_ID
        assert experiment_result.baseline_id == FROZEN_BASELINE_ID
        assert experiment_result.baseline_configuration_hash == FROZEN_BASELINE_CONFIG_HASH
        assert experiment_result.parent_main_sha == FROZEN_PARENT_MAIN_SHA
        assert experiment_result.reference_corpus_hash == FROZEN_REFERENCE_CORPUS_HASH
        assert experiment_result.semantic_content_hash == FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH
        assert experiment_result.experiment_profile_hash == "8e51e8c0e4f9bc0d78683350b6516664"

    def test_2_mutated_reference_corpus_fails_closed(self, tmp_path: Path):
        import shutil

        mutated_ref_dir = tmp_path / "mutated_reference_decisions"
        shutil.copytree(REF_DIR, mutated_ref_dir)

        target_file = mutated_ref_dir / "adrkit" / "ref-adrkit-001.jsonl"
        lines = target_file.read_text(encoding="utf-8").splitlines()
        first_rec = json.loads(lines[0])
        first_rec["raw_evidence"] = "Corrupted evidence text"
        target_file.write_text(json.dumps(first_rec) + "\n", encoding="utf-8")

        with pytest.raises(ValueError, match="Reference corpus hash mismatch"):
            execute_b_t1b_experiment(reference_corpus_dir=mutated_ref_dir)

    def test_3_exactly_100_relationship_references_analyzed(self, experiment_result: BT1BExperimentResult):
        assert len(experiment_result.reference_diagnostics) == 100
        ref_ids = [d.reference_id for d in experiment_result.reference_diagnostics]
        assert len(set(ref_ids)) == 100

    def test_4_and_14_exactly_19_expected_tuples_enter_target_attribution_and_sum_to_19(
        self, experiment_result: BT1BExperimentResult
    ):
        records = experiment_result.expected_target_records
        assert len(records) == 19

        summary = experiment_result.target_attribution_summary
        assert summary.total_expected_tuples == 19

        # Exact decomposition counts
        assert summary.exact_type_exact_target == 0
        assert summary.exact_type_alias_target == 8
        assert summary.wrong_type_alias_target == 10
        assert summary.target_not_predicted_but_visible == 0
        assert summary.target_not_predicted_and_not_visible == 1
        assert summary.normalization_failure == 0

        # Sum of mutually exclusive categories must equal exactly 19
        cat_sum = (
            summary.exact_type_exact_target
            + summary.exact_type_alias_target
            + summary.wrong_type_alias_target
            + summary.target_not_predicted_but_visible
            + summary.target_not_predicted_and_not_visible
            + summary.normalization_failure
        )
        assert cat_sum == 19

    def test_5_target_attribution_categories_mutually_exclusive_and_exhaustive(
        self, experiment_result: BT1BExperimentResult
    ):
        for rec in experiment_result.expected_target_records:
            assert rec.decomposition_category in ORDERED_DECOMPOSITION_CATEGORIES

    def test_15_classifier_visible_grounding_uses_only_raw_evidence(
        self, experiment_result: BT1BExperimentResult
    ):
        summary = experiment_result.target_attribution_summary
        assert summary.classifier_visible_target_count == 18
        assert summary.not_classifier_visible_target_count == 1

        # Locate the single invisible target: ref-gsa-agentic-coding-quickstart-005, target 0026
        invisible = [r for r in experiment_result.expected_target_records if not r.classifier_visible]
        assert len(invisible) == 1
        inv_rec = invisible[0]
        assert inv_rec.reference_id == "ref-gsa-agentic-coding-quickstart-005"
        assert inv_rec.expected_target_reference == "0026"
        assert inv_rec.decomposition_category == DECOMP_TARGET_NOT_PREDICTED_AND_NOT_VISIBLE

    def test_16_no_fuzzy_matching(self):
        # Verify no fuzzy matching library is imported or configured
        import mneme.open_architecture.stage_b_relationship_diagnostic_experiment as mod
        assert "difflib" not in dir(mod)
        assert "fuzzy" not in dir(mod)
        assert not B_T1B_DIAGNOSTIC_PROFILE["adr_alias_parser"]["fuzzy_matching"]

    def test_17_relationship_type_x_target_form_crosstab_totals_equal_parsed_total(
        self, experiment_result: BT1BExperimentResult
    ):
        g_vol = experiment_result.global_volume
        assert g_vol.total_predicted_tuples == 491

        crosstab_sum = sum(sum(tf_counts.values()) for tf_counts in g_vol.crosstab_type_by_form.values())
        assert crosstab_sum == 491

        type_counts_sum = sum(g_vol.relationship_type_counts.values())
        assert type_counts_sum == 491

        form_counts_sum = sum(g_vol.target_form_counts.values())
        assert form_counts_sum == 491

    def test_18_expected_empty_and_non_empty_partitions_reconcile_with_global(
        self, experiment_result: BT1BExperimentResult
    ):
        g_vol = experiment_result.global_volume
        e_vol = experiment_result.expected_empty_volume
        ne_vol = experiment_result.expected_non_empty_volume

        assert g_vol.reference_count == 100
        assert e_vol.reference_count == 87
        assert ne_vol.reference_count == 13
        assert g_vol.reference_count == e_vol.reference_count + ne_vol.reference_count

        assert g_vol.total_predicted_tuples == 491
        assert e_vol.total_predicted_tuples == 415
        assert ne_vol.total_predicted_tuples == 76
        assert g_vol.total_predicted_tuples == e_vol.total_predicted_tuples + ne_vol.total_predicted_tuples

        assert g_vol.successful_outcome_count == 99
        assert g_vol.failed_outcome_count == 1
        assert e_vol.failed_outcome_count == 1
        assert ne_vol.failed_outcome_count == 0

    def test_19_and_20_truncation_failure_accounting_reconciles_without_hypothetical_counts(
        self, experiment_result: BT1BExperimentResult
    ):
        trunc = experiment_result.truncation_diagnostics
        assert trunc.total_failed_outcomes == 1
        assert trunc.failed_candidate_ids == ["ref-helix-013"]
        assert trunc.failed_references_status["ref-helix-013"] == "expected_empty"
        assert trunc.parsed_tuple_contribution == 0
        assert trunc.expected_tuples_in_failed_outcomes == 0
        assert "lower bound" in trunc.sensitivity_statement.lower()

    def test_21_taxonomy_change_mutates_hash(self, experiment_result: BT1BExperimentResult):
        mut_profile = copy.deepcopy(B_T1B_DIAGNOSTIC_PROFILE)
        mut_profile["target_form_taxonomy"]["ordered_categories"].append("new_synthetic_category")
        h_mut = compute_b_t1b_profile_hash(diagnostic_profile=mut_profile)
        assert h_mut != experiment_result.experiment_profile_hash

    def test_22_adr_parser_change_mutates_hash(self, experiment_result: BT1BExperimentResult):
        mut_profile = copy.deepcopy(B_T1B_DIAGNOSTIC_PROFILE)
        mut_profile["adr_alias_parser"]["rule_a_bare_numeric"] = "altered_rule_definition"
        h_mut = compute_b_t1b_profile_hash(diagnostic_profile=mut_profile)
        assert h_mut != experiment_result.experiment_profile_hash

    def test_23_decomposition_rules_change_mutates_hash(self, experiment_result: BT1BExperimentResult):
        mut_profile = copy.deepcopy(B_T1B_DIAGNOSTIC_PROFILE)
        mut_profile["expected_target_decomposition"]["precedence"] = ["altered_order"]
        h_mut = compute_b_t1b_profile_hash(diagnostic_profile=mut_profile)
        assert h_mut != experiment_result.experiment_profile_hash

    def test_24_repeated_runs_emit_byte_identical_artifacts(self, tmp_path: Path):
        run1_dir = tmp_path / "run1"
        run2_dir = tmp_path / "run2"

        res1 = execute_b_t1b_experiment(output_dir=run1_dir)
        res2 = execute_b_t1b_experiment(output_dir=run2_dir)

        summary1 = (run1_dir / "b_t1b_summary.json").read_bytes()
        summary2 = (run2_dir / "b_t1b_summary.json").read_bytes()
        assert summary1 == summary2

        diag1 = (run1_dir / "b_t1b_diagnostics.jsonl").read_bytes()
        diag2 = (run2_dir / "b_t1b_diagnostics.jsonl").read_bytes()
        assert diag1 == diag2

        assert res1.experiment_profile_hash == res2.experiment_profile_hash

    def test_25_zero_network_or_model_calls(self, monkeypatch):
        import socket

        def _forbidden_connect(*args, **kwargs):
            raise AssertionError("Network connection attempted during offline diagnostic experiment!")

        monkeypatch.setattr(socket.socket, "connect", _forbidden_connect)
        res = execute_b_t1b_experiment()
        assert res.global_volume.reference_count == 100

    def test_26_frozen_canonical_modules_unmodified(self):
        # Verify that forbidden files are completely unmodified relative to parent main SHA
        import subprocess

        # 1. Check all changed files relative to parent main SHA
        proc = subprocess.run(
            ["git", "diff", "--name-only", FROZEN_PARENT_MAIN_SHA],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert proc.returncode == 0, f"git diff failed: {proc.stderr}"
        changed_files = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
        allowed_files = {
            "mneme/open_architecture/stage_b_relationship_diagnostic_experiment.py",
            "tests/open_architecture/test_stage_b_relationship_diagnostic_experiment.py",
            "scripts/run_test_battery.py",
        }
        unexpected = changed_files - allowed_files
        assert not unexpected, f"Forbidden files modified relative to parent main {FROZEN_PARENT_MAIN_SHA}: {unexpected}"

        # 2. Assert zero diff on forbidden paths explicitly
        forbidden_paths = [
            "mneme/open_architecture/harness.py",
            "mneme/open_architecture/classification.py",
            "mneme/open_architecture/stage_b_baseline.py",
            "mneme/open_architecture/stage_b_error_diagnostic_experiment.py",
            "mneme/open_architecture/classifiers",
            "benchmarks/open_architecture/batch_01/baseline_stage_b/classifier_outcomes.jsonl",
            "benchmarks/open_architecture/batch_01/reference_decisions",
            "benchmarks/open_architecture/batch_01/manifest.yaml",
            "benchmarks/open_architecture/batch_01/baseline.yaml",
        ]
        for fp in forbidden_paths:
            res = subprocess.run(
                ["git", "diff", "--exit-code", FROZEN_PARENT_MAIN_SHA, "--", fp],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            assert res.returncode == 0, f"Forbidden path {fp} modified relative to parent main!"
