"""
mneme.open_architecture.stage_b_relationship_selectivity_diagnostics — B-T1D Arm D Diagnosis.

Implements the deterministic residual-error diagnosis and preregistered hypothesis
evaluation for O1A B-T1D Arm D evaluated against Batch 01 v0.2-grounding.

Diagnostic Purpose:
Evaluates whether relationship emission selectivity (Arm D) causally reduced
unsupported over-generation relative to frozen Arm B without compromising target
entity recall or type discrimination on genuinely non-empty references.

Architecture & Boundary Invariants:
- Research-only diagnostic: does NOT alter benchmark scoring formulas or contracts.
- Does NOT rerun Arm D or invoke live model/network APIs.
- Reuses committed frozen data: v0.2 references, Arm D outcomes, provenance, score,
  and frozen Arm B control metrics.
- Uses explicit exceptions (no assert statements) in research-runtime validation code.
- Deterministic: byte-identical diagnostics across runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mneme.open_architecture.classification import (
    normalize_relationships,
)
from mneme.open_architecture.harness import (
    FrozenReferenceDecision,
    load_reference_corpus,
)
from mneme.open_architecture.stage_b_baseline import (
    FrozenClassifierOutcome,
)
from mneme.open_architecture.stage_b_relationship_residual_analysis import (
    ADJUDICATED_ONTOLOGY_GAP_REFERENCE_IDS,
    BEHAVIOUR_CONFLICTING_TYPE_EXTRA,
    BEHAVIOUR_DEPENDS_ON_OVERPRODUCTION,
    BEHAVIOUR_EXTRA_RELATIONSHIP,
    BEHAVIOUR_TARGET_BOUNDARY_ANOMALY,
    BEHAVIOUR_WRONG_TYPE_RECOVERY,
    ORDERED_EVIDENCE_CONTEXT_TAGS,
    ORDERED_PREDICTION_BEHAVIOUR_TAGS,
    ORDERED_STRUCTURAL_CLASSES,
    STRUCTURAL_EXACT_EXPECTED_PLUS_EXTRAS,
    STRUCTURAL_EXPECTED_EMPTY_FALSE_POSITIVE,
    STRUCTURAL_PURE_TYPE_CONFUSION,
    STRUCTURAL_TYPE_CONFUSION_PLUS_EXTRAS,
    classify_reference_structure,
    diagnose_predicted_tuple,
)
from mneme.open_architecture.stage_b_relationship_selectivity_experiment import (
    ARM_D_ID,
    B_T1D_PROFILE_D_HASH,
    CONTROL_ARM_B_OUTCOMES_SEMANTIC_HASH,
    CONTROL_ARM_B_PROFILE_HASH,
    EXPERIMENT_ID,
    FROZEN_EXECUTION_REFERENCE_CORPUS_HASH,
    FROZEN_SCORING_REFERENCE_CORPUS_HASH,
    load_treatment_run,
    recompute_arm_b_v02_control_metrics,
    validate_b_t1d_reference_corpus,
)

FROZEN_EXECUTION_COMMIT_SHA: str = "dcca4d7b2ca9674cd12b55a717f741dbe90da420"
FROZEN_ARM_D_OUTCOMES_SEMANTIC_HASH: str = (
    "sha256:ae1fbd24f6b36099d3c58006886503f6ba14bf5fd7cfa9bfb93c4befaabbedc0"
)

FROZEN_ARM_D_STAGE_B_COMPOSITE: float = 0.5934313272250952
FROZEN_ARM_D_STRICT_RELATIONSHIP_ACCURACY: float = 0.6100000000000001

CAUSAL_INFERENCE_LIMITATION: str = (
    "The preregistered H1-H5 comparisons are evaluated against the frozen historical "
    "Arm B outcomes. Arm D was executed later than Arm B using the same model identifier "
    "and frozen request/evidence contract, but the experiment did not include a "
    "contemporaneous fresh Arm B execution. Therefore, directional preregistered "
    "Arm-B-relative comparisons can be evaluated exactly, but the observed differences "
    "must not be described as definitive causal proof that the selectivity prompt alone "
    "produced the change; temporal provider/model-serving drift remains a possible confound."
)


def validate_arm_d_diagnostic_inputs(
    v02_refs: list[FrozenReferenceDecision],
    arm_d_outcomes: list[FrozenClassifierOutcome],
    sidecar: Any,
    score_data: dict[str, Any],
) -> None:
    """Validate all frozen Arm D inputs fail-closed before diagnostic derivation."""
    validate_b_t1d_reference_corpus(v02_refs)

    if len(arm_d_outcomes) != 100:
        raise ValueError(f"Expected 100 Arm D outcomes, got {len(arm_d_outcomes)}")

    unique_ids = {o.candidate_id for o in arm_d_outcomes}
    if len(unique_ids) != 100:
        raise ValueError(f"Expected 100 unique candidate IDs in Arm D outcomes, got {len(unique_ids)}")

    error_outcomes = [o for o in arm_d_outcomes if o.escalated or "error" in o.output]
    if error_outcomes:
        raise ValueError(f"Arm D contains unexpected escalated/error outcomes: {len(error_outcomes)}")

    if sidecar.treatment_semantic_content_hash != FROZEN_ARM_D_OUTCOMES_SEMANTIC_HASH:
        raise ValueError(
            f"Arm D semantic outcome hash mismatch: expected {FROZEN_ARM_D_OUTCOMES_SEMANTIC_HASH!r}, "
            f"got {sidecar.treatment_semantic_content_hash!r}"
        )

    if sidecar.treatment_profile_hash != B_T1D_PROFILE_D_HASH:
        raise ValueError(
            f"Arm D profile hash mismatch: expected {B_T1D_PROFILE_D_HASH!r}, "
            f"got {sidecar.treatment_profile_hash!r}"
        )

    if sidecar.execution_mneme_commit_sha != FROZEN_EXECUTION_COMMIT_SHA:
        raise ValueError(
            f"Arm D execution SHA mismatch: expected {FROZEN_EXECUTION_COMMIT_SHA!r}, "
            f"got {sidecar.execution_mneme_commit_sha!r}"
        )

    if sidecar.scoring_reference_corpus_hash != FROZEN_SCORING_REFERENCE_CORPUS_HASH:
        raise ValueError(
            f"Arm D scoring corpus hash mismatch: expected {FROZEN_SCORING_REFERENCE_CORPUS_HASH!r}, "
            f"got {sidecar.scoring_reference_corpus_hash!r}"
        )

    if score_data.get("strict_relationship_accuracy") != FROZEN_ARM_D_STRICT_RELATIONSHIP_ACCURACY:
        raise ValueError(
            f"Arm D score strict accuracy mismatch: expected {FROZEN_ARM_D_STRICT_RELATIONSHIP_ACCURACY}, "
            f"got {score_data.get('strict_relationship_accuracy')}"
        )

    if score_data.get("stage_b_semantic_score") != FROZEN_ARM_D_STAGE_B_COMPOSITE:
        raise ValueError(
            f"Arm D score composite mismatch: expected {FROZEN_ARM_D_STAGE_B_COMPOSITE}, "
            f"got {score_data.get('stage_b_semantic_score')}"
        )


def run_stage_b_relationship_selectivity_diagnostics(
    v02_refs: list[FrozenReferenceDecision],
    arm_d_outcomes: list[FrozenClassifierOutcome],
    arm_b_control_metrics: dict[str, Any],
    score_data: dict[str, Any],
) -> dict[str, Any]:
    """Execute complete deterministic residual diagnosis and hypothesis evaluation for Arm D."""
    refs_map = {r.reference_decision_id: r for r in v02_refs}
    outcomes_map = {o.candidate_id: o for o in arm_d_outcomes}

    passing_references: list[str] = []
    failing_records: list[dict[str, Any]] = []

    structural_counts: dict[str, int] = {sc: 0 for sc in ORDERED_STRUCTURAL_CLASSES}
    evidence_context_counts: dict[str, int] = {ec: 0 for ec in ORDERED_EVIDENCE_CONTEXT_TAGS}
    prediction_behaviour_counts: dict[str, int] = {pb: 0 for pb in ORDERED_PREDICTION_BEHAVIOUR_TAGS}
    extra_evidence_contexts: dict[str, int] = {ec: 0 for ec in ORDERED_EVIDENCE_CONTEXT_TAGS}

    total_expected_targets = 0
    recovered_target_entities = 0
    exact_type_exact_target = 0
    wrong_type_recovery = 0

    predicted_tuple_count = 0
    exact_tuple_count = 0
    missing_tuple_count = 0
    extra_tuple_count = 0
    expected_empty_extra_count = 0

    extra_depends_on = 0
    conflicting_type_extras = 0
    target_boundary_anomalies = 0

    target_type_confusion_matrix: dict[str, dict[str, int]] = {}

    expected_empty_ref_ids: list[str] = []
    expected_non_empty_ref_ids: list[str] = []

    # Evaluate all 100 reference decisions
    for rid in sorted(refs_map.keys()):
        ref = refs_map[rid]
        outcome = outcomes_map[rid]

        exp_set = {(r["relationship_type"], r.get("target_reference")) for r in ref.relationships}
        exp_targets_dict = {
            r.get("target_reference"): r["relationship_type"]
            for r in ref.relationships
            if r.get("target_reference") is not None
        }

        norm_rels = normalize_relationships(outcome.output.get("relationships", []))
        pred_set = {(r.relationship_type, r.target_reference) for r in norm_rels}
        pred_targets_dict = {
            r.target_reference: r.relationship_type
            for r in norm_rels
            if r.target_reference is not None
        }

        predicted_tuple_count += len(norm_rels)

        is_empty = len(exp_set) == 0
        if is_empty:
            expected_empty_ref_ids.append(rid)
        else:
            expected_non_empty_ref_ids.append(rid)

        # Target attribution & confusion matrix
        for r in ref.relationships:
            total_expected_targets += 1
            et = r["relationship_type"]
            er = r.get("target_reference")

            if et not in target_type_confusion_matrix:
                target_type_confusion_matrix[et] = {}

            if (et, er) in pred_set:
                recovered_target_entities += 1
                exact_type_exact_target += 1
                target_type_confusion_matrix[et][et] = (
                    target_type_confusion_matrix[et].get(et, 0) + 1
                )
            elif er in pred_targets_dict:
                recovered_target_entities += 1
                wrong_type_recovery += 1
                pt = pred_targets_dict[er]
                target_type_confusion_matrix[et][pt] = (
                    target_type_confusion_matrix[et].get(pt, 0) + 1
                )
            else:
                target_type_confusion_matrix[et]["unrecovered"] = (
                    target_type_confusion_matrix[et].get("unrecovered", 0) + 1
                )

        is_exact = (exp_set == pred_set)
        if is_exact:
            passing_references.append(rid)
            continue

        # Process failing reference
        sc = classify_reference_structure(exp_set, pred_set)
        structural_counts[sc] += 1

        exact_tuples = sorted(list(exp_set & pred_set))
        missing_tuples = sorted(list(exp_set - pred_set))
        extra_tuples = sorted(list(pred_set - exp_set))

        exact_tuple_count += len(exact_tuples)
        missing_tuple_count += len(missing_tuples)
        extra_tuple_count += len(extra_tuples)
        if is_empty:
            expected_empty_extra_count += len(extra_tuples)

        recovered_targets = sorted(list(set(exp_targets_dict.keys()) & set(pred_targets_dict.keys())))

        wrong_type_mappings: list[dict[str, Any]] = []
        conflicting_type_extra_mappings: list[dict[str, Any]] = []

        for targ, e_type in sorted(exp_targets_dict.items()):
            if targ in pred_targets_dict:
                if (e_type, targ) in pred_set:
                    for p_type, p_targ in sorted(pred_set):
                        if p_targ == targ and p_type != e_type:
                            conflicting_type_extra_mappings.append({
                                "conflicting_predicted_type": p_type,
                                "expected_type": e_type,
                                "target_reference": targ,
                            })
                else:
                    wrong_type_mappings.append({
                        "expected_type": e_type,
                        "predicted_type": pred_targets_dict[targ],
                        "target_reference": targ,
                    })

        tuple_diagnostics: list[dict[str, Any]] = []
        ref_context_counts: dict[str, int] = {}
        ref_behaviour_counts: dict[str, int] = {}

        is_ontology_gap = rid in ADJUDICATED_ONTOLOGY_GAP_REFERENCE_IDS

        for r in norm_rels:
            diag = diagnose_predicted_tuple(
                rel_type=r.relationship_type,
                target_ref=r.target_reference,
                evidence_ref=r.evidence_reference,
                expected_tuples=exp_set,
                expected_targets=exp_targets_dict,
                all_predicted_tuples=pred_set,
                reference_id=rid,
                raw_evidence=ref.raw_evidence,
            )
            tuple_diagnostics.append(diag)

            c_tag = diag["evidence_context_tag"]
            evidence_context_counts[c_tag] = evidence_context_counts.get(c_tag, 0) + 1
            ref_context_counts[c_tag] = ref_context_counts.get(c_tag, 0) + 1

            for b_tag in diag["prediction_behaviour_tags"]:
                prediction_behaviour_counts[b_tag] = (
                    prediction_behaviour_counts.get(b_tag, 0) + 1
                )
                ref_behaviour_counts[b_tag] = ref_behaviour_counts.get(b_tag, 0) + 1

            if diag["tuple_role"] in ("extra_tuple", "conflicting_type_extra", "wrong_type_target"):
                extra_evidence_contexts[c_tag] = extra_evidence_contexts.get(c_tag, 0) + 1
                if BEHAVIOUR_DEPENDS_ON_OVERPRODUCTION in diag["prediction_behaviour_tags"]:
                    extra_depends_on += 1
                if BEHAVIOUR_CONFLICTING_TYPE_EXTRA in diag["prediction_behaviour_tags"]:
                    conflicting_type_extras += 1
                if BEHAVIOUR_TARGET_BOUNDARY_ANOMALY in diag["prediction_behaviour_tags"]:
                    target_boundary_anomalies += 1

        record = {
            "adjudicated_ontology_gap": is_ontology_gap,
            "conflicting_type_extra_mappings": conflicting_type_extra_mappings,
            "exact_tuples": [list(t) for t in exact_tuples],
            "expected_tuples": [list(t) for t in sorted(list(exp_set))],
            "extra_tuples": [list(t) for t in extra_tuples],
            "missing_tuples": [list(t) for t in missing_tuples],
            "per_tuple_diagnostics": tuple_diagnostics,
            "predicted_tuples": [list(t) for t in sorted(list(pred_set))],
            "recovered_target_entities": recovered_targets,
            "reference_id": rid,
            "reference_structural_class": sc,
            "repository": ref.repository,
            "summary_counts": {
                "conflicting_type_extra_count": len(conflicting_type_extra_mappings),
                "evidence_context_counts": dict(sorted(ref_context_counts.items())),
                "exact_tuple_count": len(exact_tuples),
                "extra_tuple_count": len(extra_tuples),
                "missing_tuple_count": len(missing_tuples),
                "multi_relationship_overgeneration": len(extra_tuples) > 1,
                "prediction_behaviour_counts": dict(sorted(ref_behaviour_counts.items())),
                "total_predicted_tuples": len(norm_rels),
                "wrong_type_target_count": len(wrong_type_mappings),
            },
            "wrong_type_target_mappings": wrong_type_mappings,
        }
        failing_records.append(record)

    # Derived exact counts
    strict_exact_count = len(passing_references)
    expected_empty_exact_count = len(set(passing_references) & set(expected_empty_ref_ids))
    expected_empty_fp_count = len(expected_empty_ref_ids) - expected_empty_exact_count
    non_empty_exact_count = len(set(passing_references) & set(expected_non_empty_ref_ids))
    missing_target_entities = total_expected_targets - recovered_target_entities

    # Validate against frozen score
    if strict_exact_count != 61:
        raise ValueError(f"Derived strict exact count mismatch: expected 61, got {strict_exact_count}")
    if len(failing_records) != 39:
        raise ValueError(f"Derived failing reference count mismatch: expected 39, got {len(failing_records)}")
    if sum(structural_counts.values()) != 39:
        raise ValueError(f"Structural class counts must sum to 39, got {sum(structural_counts.values())}")
    if total_expected_targets != 18:
        raise ValueError(f"Total expected targets mismatch: expected 18, got {total_expected_targets}")

    # Primary Hypotheses Evaluation (H1-H5)
    h1_pass = (strict_exact_count / 100.0) > (arm_b_control_metrics["strict_exact_references"] / 100.0)
    h2_pass = expected_empty_exact_count > arm_b_control_metrics["expected_empty_exact"]
    h3_pass = expected_empty_fp_count < arm_b_control_metrics["expected_empty_fp_references"]
    h4_pass = expected_empty_extra_count < arm_b_control_metrics["expected_empty_extra_tuples"]
    h5_pass = extra_tuple_count < arm_b_control_metrics["total_extra_tuples"]

    primary_hypotheses: list[dict[str, Any]] = [
        {
            "comparator": ">",
            "control_arm_b_baseline": arm_b_control_metrics["strict_exact_references"] / 100.0,
            "hypothesis_id": "H1",
            "metric": "strict_relationship_accuracy",
            "observed_value": strict_exact_count / 100.0,
            "passed": h1_pass,
        },
        {
            "comparator": ">",
            "control_arm_b_baseline": arm_b_control_metrics["expected_empty_exact"],
            "hypothesis_id": "H2",
            "metric": "expected_empty_exact_matches",
            "observed_value": expected_empty_exact_count,
            "passed": h2_pass,
        },
        {
            "comparator": "<",
            "control_arm_b_baseline": arm_b_control_metrics["expected_empty_fp_references"],
            "hypothesis_id": "H3",
            "metric": "expected_empty_false_positive_references",
            "observed_value": expected_empty_fp_count,
            "passed": h3_pass,
        },
        {
            "comparator": "<",
            "control_arm_b_baseline": arm_b_control_metrics["expected_empty_extra_tuples"],
            "hypothesis_id": "H4",
            "metric": "expected_empty_extra_tuples",
            "observed_value": expected_empty_extra_count,
            "passed": h4_pass,
        },
        {
            "comparator": "<",
            "control_arm_b_baseline": arm_b_control_metrics["total_extra_tuples"],
            "hypothesis_id": "H5",
            "metric": "total_extra_relationship_tuples",
            "observed_value": extra_tuple_count,
            "passed": h5_pass,
        },
    ]

    # Preservation Conditions Evaluation (P1-P5)
    p1_pass = recovered_target_entities == 18
    p2_pass = exact_type_exact_target >= arm_b_control_metrics["exact_type_exact_target"]
    p3_pass = missing_target_entities == 0
    p4_pass = non_empty_exact_count >= 3
    p5_pass = target_boundary_anomalies <= arm_b_control_metrics["target_boundary_anomalies"]

    preservation_conditions: list[dict[str, Any]] = [
        {
            "comparator": "==",
            "condition_id": "P1",
            "control_threshold": 18,
            "metric": "target_entity_recovery",
            "observed_value": recovered_target_entities,
            "passed": p1_pass,
        },
        {
            "comparator": ">=",
            "condition_id": "P2",
            "control_threshold": arm_b_control_metrics["exact_type_exact_target"],
            "metric": "exact_type_exact_target_recovery",
            "observed_value": exact_type_exact_target,
            "passed": p2_pass,
        },
        {
            "comparator": "==",
            "condition_id": "P3",
            "control_threshold": 0,
            "metric": "missing_target_entities",
            "observed_value": missing_target_entities,
            "passed": p3_pass,
        },
        {
            "comparator": ">=",
            "condition_id": "P4",
            "control_threshold": 3,
            "metric": "non_empty_strict_exact_matches",
            "observed_value": non_empty_exact_count,
            "passed": p4_pass,
        },
        {
            "comparator": "<=",
            "condition_id": "P5",
            "control_threshold": arm_b_control_metrics["target_boundary_anomalies"],
            "metric": "target_boundary_anomalies",
            "observed_value": target_boundary_anomalies,
            "passed": p5_pass,
        },
    ]

    all_primary_passed = all(h["passed"] for h in primary_hypotheses)
    all_preservation_passed = all(p["passed"] for p in preservation_conditions)

    # Extra-only evidence context comparison
    arm_b_extra_contexts = arm_b_control_metrics["extra_tuple_evidence_contexts"]
    extra_context_comparison = {
        "arm_b_baseline": dict(sorted(arm_b_extra_contexts.items())),
        "arm_d_observed": dict(sorted(extra_evidence_contexts.items())),
        "delta": {
            k: extra_evidence_contexts.get(k, 0) - arm_b_extra_contexts.get(k, 0)
            for k in ORDERED_EVIDENCE_CONTEXT_TAGS
        },
    }

    return {
        "adjudicated_ontology_gap_references": 1,
        "all_preservation_conditions_passed": all_preservation_passed,
        "all_primary_hypotheses_passed": all_primary_passed,
        "arm_id": ARM_D_ID,
        "artifact_type": "b_t1d_arm_d_residual_diagnostics",
        "causal_inference_limitation": CAUSAL_INFERENCE_LIMITATION,
        "control_arm_b_baseline": {
            "control_arm_b_profile_hash": CONTROL_ARM_B_PROFILE_HASH,
            "control_arm_b_semantic_hash": CONTROL_ARM_B_OUTCOMES_SEMANTIC_HASH,
            "expected_empty_exact": arm_b_control_metrics["expected_empty_exact"],
            "expected_empty_extra_tuples": arm_b_control_metrics["expected_empty_extra_tuples"],
            "expected_empty_fp_references": arm_b_control_metrics["expected_empty_fp_references"],
            "strict_exact_references": arm_b_control_metrics["strict_exact_references"],
            "total_extra_tuples": arm_b_control_metrics["total_extra_tuples"],
        },
        "evidence_context_aggregate_counts": dict(sorted(evidence_context_counts.items())),
        "execution_mneme_commit_sha": FROZEN_EXECUTION_COMMIT_SHA,
        "experiment_id": EXPERIMENT_ID,
        "extra_only_evidence_context_comparison": extra_context_comparison,
        "failing_records": failing_records,
        "failing_references": len(failing_records),
        "model_calls": 0,
        "network_calls": 0,
        "observed_metrics": {
            "conflicting_type_extras": conflicting_type_extras,
            "exact_type_exact_target": exact_type_exact_target,
            "expected_empty_exact": expected_empty_exact_count,
            "expected_empty_extra_tuples": expected_empty_extra_count,
            "expected_empty_fp": expected_empty_fp_count,
            "extra_depends_on": extra_depends_on,
            "missing_target_entities": missing_target_entities,
            "non_empty_exact": non_empty_exact_count,
            "strict_exact_references": strict_exact_count,
            "target_boundary_anomalies": target_boundary_anomalies,
            "target_entities_recovered": recovered_target_entities,
            "total_extra_tuples": extra_tuple_count,
            "total_predicted_tuples": predicted_tuple_count,
            "wrong_type_recovery": wrong_type_recovery,
        },
        "passing_references": len(passing_references),
        "population_counts": {
            "expected_empty_references": len(expected_empty_ref_ids),
            "expected_non_empty_references": len(expected_non_empty_ref_ids),
            "total_expected_tuples": total_expected_targets,
            "total_references": len(refs_map),
        },
        "prediction_behaviour_counts": dict(sorted(prediction_behaviour_counts.items())),
        "preservation_conditions": preservation_conditions,
        "primary_hypotheses": primary_hypotheses,
        "score_artifact_metrics": {
            "composite_score": score_data["stage_b_semantic_score"],
            "strict_relationship_accuracy": score_data["strict_relationship_accuracy"],
        },
        "scoring_reference_corpus_hash": FROZEN_SCORING_REFERENCE_CORPUS_HASH,
        "source_outcomes_semantic_hash": FROZEN_ARM_D_OUTCOMES_SEMANTIC_HASH,
        "structural_residual_counts": dict(sorted(structural_counts.items())),
        "target_attribution_totals": {
            "conflicting_type_extra": conflicting_type_extras,
            "exact_type_exact_target": exact_type_exact_target,
            "missing_target_entities": missing_target_entities,
            "target_entity_recovered_any_type": recovered_target_entities,
            "total_expected_tuples": total_expected_targets,
            "wrong_type_recovery": wrong_type_recovery,
        },
        "target_type_confusion_matrix": {
            k: dict(sorted(v.items())) for k, v in sorted(target_type_confusion_matrix.items())
        },
        "treatment_profile_hash": B_T1D_PROFILE_D_HASH,
    }


def write_stage_b_relationship_selectivity_diagnostics(
    repo_root: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    """Generate and write benchmarks/open_architecture/batch_01/treatments/b_t1d/arm_d/diagnostics.json."""
    root = (
        repo_root
        if repo_root is not None
        else Path(__file__).resolve().parent.parent.parent
    )

    v02_dir = (
        root
        / "benchmarks"
        / "open_architecture"
        / "batch_01"
        / "revisions"
        / "batch_01_v0.2-grounding"
        / "reference_decisions"
    )
    run_dir = (
        root
        / "benchmarks"
        / "open_architecture"
        / "batch_01"
        / "treatments"
        / "b_t1d"
        / "arm_d"
    )
    score_file = run_dir / "stage_b_score.json"
    arm_b_residual_file = (
        root
        / "benchmarks"
        / "open_architecture"
        / "batch_01"
        / "treatments"
        / "b_t1c"
        / "arm_b"
        / "residual_error_decomposition_v0.2_grounding.json"
    )
    arm_b_outcomes_file = (
        root
        / "benchmarks"
        / "open_architecture"
        / "batch_01"
        / "treatments"
        / "b_t1c"
        / "arm_b"
        / "outcomes.jsonl"
    )

    if not score_file.is_file():
        raise FileNotFoundError(f"Missing score file: {score_file}")

    refs = load_reference_corpus(v02_dir)
    expected_ids = {r.reference_decision_id for r in refs}

    outcomes, sidecar = load_treatment_run(run_dir, expected_ids)
    score_data = json.loads(score_file.read_text(encoding="utf-8"))

    # Fail-closed input validation
    validate_arm_d_diagnostic_inputs(refs, outcomes, sidecar, score_data)

    # Recompute Arm B control metrics
    from mneme.open_architecture.stage_b_relationship_treatment_experiment import load_treatment_outcomes
    arm_b_outcomes = load_treatment_outcomes(arm_b_outcomes_file, expected_reference_ids=expected_ids)
    arm_b_metrics = recompute_arm_b_v02_control_metrics(refs, arm_b_outcomes, arm_b_residual_file)

    diag_result = run_stage_b_relationship_selectivity_diagnostics(
        v02_refs=refs,
        arm_d_outcomes=outcomes,
        arm_b_control_metrics=arm_b_metrics,
        score_data=score_data,
    )

    out_file = (
        output_path
        if output_path is not None
        else run_dir / "diagnostics.json"
    )

    out_file.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(diag_result, indent=2, sort_keys=True) + "\n"
    out_file.write_bytes(serialized.encode("utf-8"))
    return out_file
