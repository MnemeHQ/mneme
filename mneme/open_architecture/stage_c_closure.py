"""
mneme.open_architecture.stage_c_closure — Authoritative Batch 01 Stage C Closure and Endpoint Declaration.

Declares profile B3 as the final, accepted, frozen Stage C Governing Decision Set (GDS)
endpoint for O1A Batch 01.

Binds:
- Batch 01 Stage C closure status: CLOSED / FROZEN
- Accepted endpoint: B3 (relative_80 selection policy + B3 transformed query)
- Headline metric: governing_decision_set_f1
- Mneme execution commit SHA at closure: fcc36a60b9ec95014eb8931c3bac6bfee418e781 (PR #435 merged)
- Corpora and input cryptographic hashes:
  - Scenario corpus hash: 2ff8751955fd64a33316aca6692dc803 (50 scenarios)
  - Reference corpus hash: 0455bd66aae52551c35b37a63c2d185f (100 reference decisions)
  - Baseline configuration hash: 31e18dc1e2bd9ad30bec86dce1a9295a
  - Manifest configuration hash: 4af7e5794011b43d39682cdfeac9f54e
  - Accepted Stage B mixed semantic hash: sha256:662de96721513ab1fd0d6e2d55eb7c037dedcb04c75b441b610aa3a57e236b8a
  - Stage C experiment profile hash: 5f031434a95ea94c53255901b1ada39e
- Exact B3 profile definition:
  - selection_policy: relative_80 (relative_threshold_ratio: 0.80, selection_epsilon: 1e-9)
  - query_treatment: B3 transformed query (suppress registered structural prefixes and registered function words)
  - registered_structural_prefixes: path, component, change_type, dependencies, api, technology
  - suppressed_function_words: from, that, when, with, without
- Accepted B3 scorecard metrics:
  - End-to-end macro F1: 0.6506666666666666
  - End-to-end macro precision: 0.6023333333333334
  - End-to-end macro recall: 0.79
  - End-to-end exact set matches: 22 / 50
  - Human-reference macro F1: 0.7110952380952381
  - Human-reference exact set matches: 26 / 50
- Profile evaluations comparison (B0, C-T1A, B3) under both human reference and end-to-end.
- Endpoint rationale, recall-precision trade-off disclosure, and research limitations.

Architecture & Boundary Invariants:
- Research-only: zero writes to canonical Mneme state (.mneme/, DecisionIndex,
  MemoryStore, DecisionProposal, canonical authority, etc.).
- Offline validation: derives closure record deterministically from committed evidence
  without model, network, or external API calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mneme.open_architecture.gds_calibration_experiment import (
    FROZEN_FUNCTION_WORDS,
    FROZEN_STRUCTURAL_PREFIXES,
    POLICY_RELATIVE_80,
    PROFILE_B3,
    RELATIVE_THRESHOLD_RATIO,
    SELECTION_EPSILON,
)
from mneme.open_architecture.manifest import Manifest

# ── Frozen Constants ────────────────────────────────────────────────────────────

FROZEN_STAGE_C_CLOSURE_MNEME_SHA: str = "fcc36a60b9ec95014eb8931c3bac6bfee418e781"
FROZEN_BASELINE_ID: str = "o1a-batch-01-baseline"
FROZEN_STAGE_C_EXPERIMENT_ID: str = "o1a-stage-c-end-to-end"
FROZEN_SCENARIO_CORPUS_HASH: str = "2ff8751955fd64a33316aca6692dc803"
FROZEN_REFERENCE_CORPUS_HASH: str = "0455bd66aae52551c35b37a63c2d185f"
FROZEN_BASELINE_CONFIG_HASH: str = "31e18dc1e2bd9ad30bec86dce1a9295a"
FROZEN_MANIFEST_CONFIG_HASH: str = "4af7e5794011b43d39682cdfeac9f54e"
ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH: str = (
    "sha256:662de96721513ab1fd0d6e2d55eb7c037dedcb04c75b441b610aa3a57e236b8a"
)
FROZEN_STAGE_C_EXPERIMENT_PROFILE_HASH: str = "5f031434a95ea94c53255901b1ada39e"

ACCEPTED_STAGE_C_ENDPOINT: str = "B3"
HEADLINE_METRIC: str = "governing_decision_set_f1"

# Frozen B3 headline metrics
ACCEPTED_B3_END_TO_END_MACRO_F1: float = 0.6506666666666666
ACCEPTED_B3_END_TO_END_PRECISION: float = 0.6023333333333334
ACCEPTED_B3_END_TO_END_RECALL: float = 0.79
ACCEPTED_B3_EXACT_SET_MATCHES: int = 22

ACCEPTED_B3_HUMAN_MACRO_F1: float = 0.7110952380952381
ACCEPTED_B3_HUMAN_PRECISION: float = 0.6711904761904762
ACCEPTED_B3_HUMAN_RECALL: float = 0.84
ACCEPTED_B3_HUMAN_EXACT_SET_MATCHES: int = 26


def build_stage_c_closure(
    repo_root: Path | str | None = None,
    *,
    mneme_execution_sha: str = FROZEN_STAGE_C_CLOSURE_MNEME_SHA,
) -> dict[str, Any]:
    """Construct deterministic Stage C Batch 01 closure artifact binding all frozen evidence.

    Fails closed if:
    - Stage C end-to-end summary artifact is missing.
    - Any cryptographic hash or composite score deviates from frozen constants.
    """
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent.parent
    e2e_summary_path = (
        root
        / "benchmarks"
        / "open_architecture"
        / "batch_01"
        / "stage_c"
        / "stage_c_end_to_end_summary.json"
    )

    if not e2e_summary_path.is_file():
        raise FileNotFoundError(f"Missing required Stage C summary artifact: {e2e_summary_path}")

    manifest_path = (
        root
        / "benchmarks"
        / "open_architecture"
        / "batch_01"
        / "manifest.yaml"
    )
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing required Batch 01 manifest: {manifest_path}")

    manifest = Manifest.load(manifest_path)
    if manifest.headline_metric != HEADLINE_METRIC:
        raise ValueError(
            f"Authoritative manifest headline metric mismatch: expected {HEADLINE_METRIC!r}, "
            f"got {manifest.headline_metric!r}"
        )
    computed_manifest_hash = manifest.configuration_hash()
    if computed_manifest_hash != FROZEN_MANIFEST_CONFIG_HASH:
        raise ValueError(
            f"Manifest configuration hash mismatch: expected {FROZEN_MANIFEST_CONFIG_HASH!r}, "
            f"got {computed_manifest_hash!r}"
        )

    e2e_data = json.loads(e2e_summary_path.read_text(encoding="utf-8"))

    # Fail-closed validation of experiment and baseline identities
    if e2e_data.get("experiment_id") != FROZEN_STAGE_C_EXPERIMENT_ID:
        raise ValueError(
            f"Stage C experiment_id mismatch: expected {FROZEN_STAGE_C_EXPERIMENT_ID!r}, "
            f"got {e2e_data.get('experiment_id')!r}"
        )
    if e2e_data.get("baseline_id") != FROZEN_BASELINE_ID:
        raise ValueError(
            f"Baseline ID mismatch: expected {FROZEN_BASELINE_ID!r}, "
            f"got {e2e_data.get('baseline_id')!r}"
        )

    # Fail-closed validation of frozen cryptographic identities
    if e2e_data.get("baseline_config_hash") != FROZEN_BASELINE_CONFIG_HASH:
        raise ValueError(
            f"Baseline config hash mismatch: expected {FROZEN_BASELINE_CONFIG_HASH!r}, "
            f"got {e2e_data.get('baseline_config_hash')!r}"
        )
    if e2e_data.get("manifest_config_hash") != FROZEN_MANIFEST_CONFIG_HASH:
        raise ValueError(
            f"Manifest config hash mismatch: expected {FROZEN_MANIFEST_CONFIG_HASH!r}, "
            f"got {e2e_data.get('manifest_config_hash')!r}"
        )
    if e2e_data.get("scenario_corpus_hash") != FROZEN_SCENARIO_CORPUS_HASH:
        raise ValueError(
            f"Scenario corpus hash mismatch: expected {FROZEN_SCENARIO_CORPUS_HASH!r}, "
            f"got {e2e_data.get('scenario_corpus_hash')!r}"
        )
    if e2e_data.get("reference_corpus_hash") != FROZEN_REFERENCE_CORPUS_HASH:
        raise ValueError(
            f"Reference corpus hash mismatch: expected {FROZEN_REFERENCE_CORPUS_HASH!r}, "
            f"got {e2e_data.get('reference_corpus_hash')!r}"
        )
    if e2e_data.get("stage_b_mixed_semantic_hash") != ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH:
        raise ValueError(
            f"Stage B mixed semantic hash mismatch: expected {ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH!r}, "
            f"got {e2e_data.get('stage_b_mixed_semantic_hash')!r}"
        )
    if e2e_data.get("experiment_profile_hash") != FROZEN_STAGE_C_EXPERIMENT_PROFILE_HASH:
        raise ValueError(
            f"Experiment profile hash mismatch: expected {FROZEN_STAGE_C_EXPERIMENT_PROFILE_HASH!r}, "
            f"got {e2e_data.get('experiment_profile_hash')!r}"
        )

    # Validate B3 scores
    b3_e2e = e2e_data.get("end_to_end_predictions", {}).get("B3", {})
    if b3_e2e.get("macro_f1") != ACCEPTED_B3_END_TO_END_MACRO_F1:
        raise ValueError(
            f"B3 end-to-end macro F1 mismatch: expected {ACCEPTED_B3_END_TO_END_MACRO_F1!r}, "
            f"got {b3_e2e.get('macro_f1')!r}"
        )
    if b3_e2e.get("exact_set_matches") != ACCEPTED_B3_EXACT_SET_MATCHES:
        raise ValueError(
            f"B3 exact set matches mismatch: expected {ACCEPTED_B3_EXACT_SET_MATCHES!r}, "
            f"got {b3_e2e.get('exact_set_matches')!r}"
        )

    b3_human = e2e_data.get("isolated_human_baseline", {}).get("B3", {})
    if b3_human.get("macro_f1") != ACCEPTED_B3_HUMAN_MACRO_F1:
        raise ValueError(
            f"B3 human macro F1 mismatch: expected {ACCEPTED_B3_HUMAN_MACRO_F1!r}, "
            f"got {b3_human.get('macro_f1')!r}"
        )

    b3_comp = e2e_data.get("profile_comparisons", {}).get("B3", {})

    # Build comprehensive closure dictionary
    return {
        "accepted_endpoint_scorecard": {
            "comparison_deltas": b3_comp,
            "end_to_end_metrics": {
                "exact_set_matches": b3_e2e.get("exact_set_matches"),
                "macro_f1": b3_e2e.get("macro_f1"),
                "macro_precision": b3_e2e.get("macro_precision"),
                "macro_recall": b3_e2e.get("macro_recall"),
                "mean_predicted_set_size": b3_e2e.get("mean_predicted_set_size"),
                "total_expected_decisions": b3_e2e.get("total_expected_decisions"),
                "total_false_negatives": b3_e2e.get("total_false_negatives"),
                "total_false_positives": b3_e2e.get("total_false_positives"),
                "total_predicted_decisions": b3_e2e.get("total_predicted_decisions"),
                "total_scenarios": b3_e2e.get("total_scenarios"),
            },
            "human_reference_metrics": {
                "exact_set_matches": b3_human.get("exact_set_matches"),
                "macro_f1": b3_human.get("macro_f1"),
                "macro_precision": b3_human.get("macro_precision"),
                "macro_recall": b3_human.get("macro_recall"),
                "mean_predicted_set_size": b3_human.get("mean_predicted_set_size"),
                "total_expected_decisions": b3_human.get("total_expected_decisions"),
                "total_false_negatives": b3_human.get("total_false_negatives"),
                "total_false_positives": b3_human.get("total_false_positives"),
                "total_predicted_decisions": b3_human.get("total_predicted_decisions"),
                "total_scenarios": b3_human.get("total_scenarios"),
            },
            "per_repository": {
                "end_to_end": b3_e2e.get("per_repository", {}),
                "human_reference": b3_human.get("per_repository", {}),
            },
            "profile": ACCEPTED_STAGE_C_ENDPOINT,
        },
        "artifact_type": "stage_c_batch_01_closure",
        "artifact_version": "0.1",
        "b3_profile_definition": {
            "profile_id": PROFILE_B3,
            "query_transformation_function": "transform_query_for_b3",
            "query_treatment": (
                "B3 transformed query: strip registered structural prefixes while strictly "
                "preserving their values, and suppress five registered high-frequency function words."
            ),
            "registered_structural_prefixes": list(FROZEN_STRUCTURAL_PREFIXES),
            "relative_threshold_ratio": RELATIVE_THRESHOLD_RATIO,
            "selection_epsilon": SELECTION_EPSILON,
            "selection_policy": POLICY_RELATIVE_80,
            "suppressed_function_words": sorted(FROZEN_FUNCTION_WORDS),
        },
        "baseline_id": e2e_data.get("baseline_id", FROZEN_BASELINE_ID),
        "batch_id": "o1a-batch-01",
        "closure_declaration": {
            "accepted_endpoint": ACCEPTED_STAGE_C_ENDPOINT,
            "closure_scope": (
                "Batch 01 Stage C Governing Decision Set evaluation is frozen. "
                "No later Batch 01 Stage C treatment or calibration profile is accepted. "
                "Any future Stage C research must occur under a new benchmark version, new batch, "
                "or explicitly reopened programme rather than mutating Batch 01."
            ),
            "production_readiness": (
                "Research benchmark endpoint only; not declared a globally optimal or "
                "production-ready retrieval policy."
            ),
            "status": "CLOSED / FROZEN",
        },
        "closure_status": "closed_frozen",
        "corpora_and_inputs": {
            "baseline_configuration_hash": FROZEN_BASELINE_CONFIG_HASH,
            "baseline_id": e2e_data.get("baseline_id", FROZEN_BASELINE_ID),
            "manifest_configuration_hash": computed_manifest_hash,
            "reference_corpus_hash": FROZEN_REFERENCE_CORPUS_HASH,
            "scenario_corpus_hash": FROZEN_SCENARIO_CORPUS_HASH,
            "stage_b_mixed_semantic_hash": ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH,
            "stage_c_experiment_profile_hash": FROZEN_STAGE_C_EXPERIMENT_PROFILE_HASH,
        },
        "dataset": {
            "decisions_per_repository": 20,
            "scenarios_per_repository": 10,
            "total_reference_decisions": 100,
            "total_scenarios": 50,
        },
        "endpoint_identity": {
            "endpoint_name": ACCEPTED_STAGE_C_ENDPOINT,
            "experiment_id": "o1a-stage-c-end-to-end",
            "profile": ACCEPTED_STAGE_C_ENDPOINT,
            "purpose": "governing_decision_set_retrieval",
        },
        "endpoint_rationale": {
            "headline_metric": HEADLINE_METRIC,
            "key_comparisons": {
                "end_to_end_predictions": {
                    "B0": {
                        "exact_set_matches": "0 / 50",
                        "false_negatives": 0,
                        "false_positives": 945,
                        "macro_f1": 0.10225974025974026,
                        "macro_precision": 0.05405263157894737,
                        "macro_recall": 1.0,
                    },
                    "B3": {
                        "exact_set_matches": "22 / 50",
                        "false_negatives": 13,
                        "false_positives": 46,
                        "macro_f1": 0.6506666666666666,
                        "macro_precision": 0.6023333333333334,
                        "macro_recall": 0.79,
                    },
                    "C-T1A": {
                        "exact_set_matches": "18 / 50",
                        "false_negatives": 11,
                        "false_positives": 69,
                        "macro_f1": 0.6033809523809524,
                        "macro_precision": 0.5358571428571429,
                        "macro_recall": 0.81,
                    },
                },
                "human_reference_calibration": {
                    "B0": {
                        "exact_set_matches": "0 / 50",
                        "false_negatives": 0,
                        "false_positives": 930,
                        "macro_f1": 0.10372841193893825,
                        "macro_precision": 0.054865497076023395,
                        "macro_recall": 1.0,
                    },
                    "B3": {
                        "exact_set_matches": "26 / 50",
                        "false_negatives": 10,
                        "false_positives": 45,
                        "macro_f1": 0.7110952380952381,
                        "macro_precision": 0.6711904761904762,
                        "macro_recall": 0.84,
                    },
                    "C-T1A": {
                        "exact_set_matches": "19 / 50",
                        "false_negatives": 11,
                        "false_positives": 69,
                        "macro_f1": 0.6211587301587301,
                        "macro_precision": 0.5560238095238096,
                        "macro_recall": 0.82,
                    },
                },
            },
            "research_limitations": (
                "Research benchmark endpoint only. Not demonstrated to be globally optimal. "
                "Does not constitute production-readiness evidence. The experiment demonstrates "
                "empirical association within Batch 01, not definitive causal proof that the B3 "
                "query transform components alone produced the gain."
            ),
            "selection_summary": (
                "B3 achieved the highest macro F1 on the declared headline metric under both "
                "human-reference calibration (0.711095) and accepted Stage B end-to-end evaluation "
                "(0.650667), with the highest exact governing set match count (22/50)."
            ),
            "tradeoff_disclosure": (
                "End-to-end B3 recall is 0.79 vs C-T1A recall 0.81 (-0.02 recall trade-off for "
                "reducing false positives from 69 to 46, improving precision from 0.535857 to "
                "0.602333, and improving exact sets from 18 to 22). B3 is accepted on headline "
                "metric and overall F1 balance, not because it dominates every individual dimension."
            ),
        },
        "headline_metric": manifest.headline_metric,
        "mneme_execution_sha": mneme_execution_sha,
        "profile_evaluations_comparison": {
            "end_to_end": e2e_data.get("end_to_end_predictions", {}),
            "human_reference": e2e_data.get("isolated_human_baseline", {}),
            "profile_comparisons": e2e_data.get("profile_comparisons", {}),
        },
        "provenance_sources": {
            "baseline_config": "benchmarks/open_architecture/batch_01/baseline.yaml",
            "baseline_manifest": "benchmarks/open_architecture/batch_01/manifest.yaml",
            "scenarios": "benchmarks/open_architecture/batch_01/scenarios/scenarios.jsonl",
            "stage_b_closure": "benchmarks/open_architecture/batch_01/stage_b/stage_b_closure.json",
            "stage_c_end_to_end_summary": "benchmarks/open_architecture/batch_01/stage_c/stage_c_end_to_end_summary.json",
        },
    }


def write_stage_c_closure(
    target_path: Path | str | None = None,
    repo_root: Path | str | None = None,
    *,
    mneme_execution_sha: str = FROZEN_STAGE_C_CLOSURE_MNEME_SHA,
) -> Path:
    """Generate and write the authoritative stage_c_closure.json artifact."""
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent.parent
    dest = (
        Path(target_path)
        if target_path is not None
        else root
        / "benchmarks"
        / "open_architecture"
        / "batch_01"
        / "stage_c"
        / "stage_c_closure.json"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    closure_data = build_stage_c_closure(root, mneme_execution_sha=mneme_execution_sha)
    serialized = json.dumps(closure_data, indent=2, sort_keys=True) + "\n"
    dest.write_text(serialized, encoding="utf-8", newline="\n")
    return dest


__all__ = [
    "FROZEN_STAGE_C_CLOSURE_MNEME_SHA",
    "FROZEN_BASELINE_ID",
    "FROZEN_STAGE_C_EXPERIMENT_ID",
    "FROZEN_SCENARIO_CORPUS_HASH",
    "FROZEN_REFERENCE_CORPUS_HASH",
    "FROZEN_BASELINE_CONFIG_HASH",
    "FROZEN_MANIFEST_CONFIG_HASH",
    "ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH",
    "FROZEN_STAGE_C_EXPERIMENT_PROFILE_HASH",
    "ACCEPTED_STAGE_C_ENDPOINT",
    "HEADLINE_METRIC",
    "ACCEPTED_B3_END_TO_END_MACRO_F1",
    "ACCEPTED_B3_END_TO_END_PRECISION",
    "ACCEPTED_B3_END_TO_END_RECALL",
    "ACCEPTED_B3_EXACT_SET_MATCHES",
    "ACCEPTED_B3_HUMAN_MACRO_F1",
    "ACCEPTED_B3_HUMAN_PRECISION",
    "ACCEPTED_B3_HUMAN_RECALL",
    "ACCEPTED_B3_HUMAN_EXACT_SET_MATCHES",
    "build_stage_c_closure",
    "write_stage_c_closure",
]
