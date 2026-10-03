"""
mneme.open_architecture.stage_b_closure — Authoritative Batch 01 Stage B Closure and Endpoint Declaration.

Declares B-T1D / Arm D as the final, accepted, frozen Stage B semantic classification
endpoint for O1A Batch 01.

Binds:
- Batch 01 Stage B closure status: CLOSED / FROZEN
- Accepted endpoint: B-T1D / Arm D (relationship selectivity)
- Mneme execution commit SHA at closure: 7e17fb1640a0144468d47d6ece2791c44b1bfbc2 (PR #434 merged)
- Reference corpora distinctions:
  - Historical baseline corpus: batch_01_v0.1 (0455bd66aae52551c35b37a63c2d185f)
  - Final Stage B scoring corpus: batch_01_v0.2-grounding (700a569e24bf90707ba14ff65eea2ab5)
- Cryptographic content hashes:
  - Arm D treatment profile hash: d66bb19c9e4c64e835a6191293a95570
  - Arm D outcomes semantic hash: sha256:ae1fbd24f6b36099d3c58006886503f6ba14bf5fd7cfa9bfb93c4befaabbedc0
  - Accepted mixed Stage B semantic hash (700 B0 + 100 Arm D): sha256:662de96721513ab1fd0d6e2d55eb7c037dedcb04c75b441b610aa3a57e236b8a
- Frozen scores:
  - Stage B semantic composite: 0.5934313272250952
  - Strict relationship accuracy: 0.6100000000000001 (61 / 100 exact matches)
- Complete semantic scorecard across all 8 evaluated dimensions and 5 repositories.
- Endpoint rationale and hypothesis outcome summary from committed evidence.

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

# ── Frozen Constants ────────────────────────────────────────────────────────────

FROZEN_STAGE_B_CLOSURE_MNEME_SHA: str = "7e17fb1640a0144468d47d6ece2791c44b1bfbc2"
FROZEN_HISTORICAL_BASELINE_CORPUS_HASH: str = "0455bd66aae52551c35b37a63c2d185f"
FROZEN_SCORING_REFERENCE_CORPUS_HASH: str = "700a569e24bf90707ba14ff65eea2ab5"
FROZEN_ARM_D_PROFILE_HASH: str = "d66bb19c9e4c64e835a6191293a95570"
FROZEN_ARM_D_OUTCOMES_SEMANTIC_HASH: str = (
    "sha256:ae1fbd24f6b36099d3c58006886503f6ba14bf5fd7cfa9bfb93c4befaabbedc0"
)
ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH: str = (
    "sha256:662de96721513ab1fd0d6e2d55eb7c037dedcb04c75b441b610aa3a57e236b8a"
)
ACCEPTED_STAGE_B_SEMANTIC_SCORE: float = 0.5934313272250952
ACCEPTED_STRICT_RELATIONSHIP_ACCURACY: float = 0.6100000000000001
ACCEPTED_RELATIONSHIP_EXACT_MATCHES: int = 61

# Evaluated task dimensions comprising the Stage B composite
STAGE_B_EVALUATED_TASKS: tuple[str, ...] = (
    "decision_classification_accuracy",
    "domain_micro_f1",
    "purpose_micro_f1",
    "authority_accuracy",
    "scope_accuracy",
    "lifecycle_accuracy",
    "relationship_accuracy",
    "enforcement_classification_accuracy",
)


def build_stage_b_closure(
    repo_root: Path | str | None = None,
    *,
    mneme_execution_sha: str = FROZEN_STAGE_B_CLOSURE_MNEME_SHA,
) -> dict[str, Any]:
    """Construct deterministic Stage B Batch 01 closure artifact binding all frozen evidence.

    Fails closed if:
    - Arm D score artifact, provenance, diagnostics, or revision metadata are missing.
    - Any cryptographic hash or composite score deviates from frozen constants.
    """
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent.parent
    b_t1d_dir = (
        root
        / "benchmarks"
        / "open_architecture"
        / "batch_01"
        / "treatments"
        / "b_t1d"
        / "arm_d"
    )
    score_path = b_t1d_dir / "stage_b_score.json"
    provenance_path = b_t1d_dir / "provenance.json"
    diagnostics_path = b_t1d_dir / "diagnostics.json"
    revision_path = (
        root
        / "benchmarks"
        / "open_architecture"
        / "batch_01"
        / "revisions"
        / "batch_01_v0.2-grounding"
        / "revision.json"
    )

    if not score_path.is_file():
        raise FileNotFoundError(f"Missing required Arm D score artifact: {score_path}")
    if not provenance_path.is_file():
        raise FileNotFoundError(f"Missing required Arm D provenance artifact: {provenance_path}")
    if not diagnostics_path.is_file():
        raise FileNotFoundError(f"Missing required Arm D diagnostics artifact: {diagnostics_path}")
    if not revision_path.is_file():
        raise FileNotFoundError(f"Missing required v0.2-grounding revision artifact: {revision_path}")

    score_data = json.loads(score_path.read_text(encoding="utf-8"))
    prov_data = json.loads(provenance_path.read_text(encoding="utf-8"))
    diag_data = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    rev_data = json.loads(revision_path.read_text(encoding="utf-8"))

    # Fail-closed validation of frozen cryptographic identities
    if score_data.get("treatment_profile_hash") != FROZEN_ARM_D_PROFILE_HASH:
        raise ValueError(
            f"Treatment profile hash mismatch: expected {FROZEN_ARM_D_PROFILE_HASH!r}, "
            f"got {score_data.get('treatment_profile_hash')!r}"
        )
    if prov_data.get("treatment_profile_hash") != FROZEN_ARM_D_PROFILE_HASH:
        raise ValueError(
            f"Provenance treatment profile hash mismatch: expected {FROZEN_ARM_D_PROFILE_HASH!r}, "
            f"got {prov_data.get('treatment_profile_hash')!r}"
        )
    if score_data.get("source_outcomes_semantic_hash") != FROZEN_ARM_D_OUTCOMES_SEMANTIC_HASH:
        raise ValueError(
            f"Arm D outcomes semantic hash mismatch: expected {FROZEN_ARM_D_OUTCOMES_SEMANTIC_HASH!r}, "
            f"got {score_data.get('source_outcomes_semantic_hash')!r}"
        )
    if score_data.get("scoring_reference_corpus_hash") != FROZEN_SCORING_REFERENCE_CORPUS_HASH:
        raise ValueError(
            f"Scoring reference corpus hash mismatch: expected {FROZEN_SCORING_REFERENCE_CORPUS_HASH!r}, "
            f"got {score_data.get('scoring_reference_corpus_hash')!r}"
        )
    if rev_data.get("base_corpus_hash") != FROZEN_HISTORICAL_BASELINE_CORPUS_HASH:
        raise ValueError(
            f"Base corpus hash mismatch in revision: expected {FROZEN_HISTORICAL_BASELINE_CORPUS_HASH!r}, "
            f"got {rev_data.get('base_corpus_hash')!r}"
        )
    if rev_data.get("new_corpus_hash") != FROZEN_SCORING_REFERENCE_CORPUS_HASH:
        raise ValueError(
            f"New corpus hash mismatch in revision: expected {FROZEN_SCORING_REFERENCE_CORPUS_HASH!r}, "
            f"got {rev_data.get('new_corpus_hash')!r}"
        )

    # Validate scores
    comp_score = score_data.get("stage_b_semantic_score")
    if comp_score != ACCEPTED_STAGE_B_SEMANTIC_SCORE:
        raise ValueError(
            f"Stage B semantic composite mismatch: expected {ACCEPTED_STAGE_B_SEMANTIC_SCORE!r}, "
            f"got {comp_score!r}"
        )
    rel_acc = score_data.get("strict_relationship_accuracy")
    if rel_acc != ACCEPTED_STRICT_RELATIONSHIP_ACCURACY:
        raise ValueError(
            f"Strict relationship accuracy mismatch: expected {ACCEPTED_STRICT_RELATIONSHIP_ACCURACY!r}, "
            f"got {rel_acc!r}"
        )

    # Compute macro task averages across 5 repositories
    repo_scores = score_data["repository_scores"]
    all_repo_keys = sorted(repo_scores.keys())

    all_metric_keys = [
        "decision_classification_accuracy",
        "domain_macro_f1",
        "domain_macro_precision",
        "domain_macro_recall",
        "domain_micro_f1",
        "domain_micro_precision",
        "domain_micro_recall",
        "authority_accuracy",
        "scope_accuracy",
        "lifecycle_accuracy",
        "relationship_accuracy",
        "enforcement_classification_accuracy",
        "prescriptive_intent_f1",
        "prescriptive_intent_precision",
        "prescriptive_intent_recall",
        "purpose_macro_f1",
        "purpose_macro_precision",
        "purpose_macro_recall",
        "purpose_micro_f1",
        "purpose_micro_precision",
        "purpose_micro_recall",
    ]

    macro_task_averages: dict[str, float] = {}
    for m in all_metric_keys:
        vals = [repo_scores[r]["metrics"][m] for r in all_repo_keys]
        macro_task_averages[m] = sum(vals) / len(vals)

    # Build comprehensive closure dictionary
    return {
        "artifact_type": "stage_b_batch_01_closure",
        "artifact_version": "0.1",
        "batch_id": "o1a-batch-01",
        "classifier": {
            "backend_id": prov_data.get("classifier_backend", "anthropic"),
            "classifier_version": prov_data.get("classifier_version", "0.1"),
            "model_identifier": prov_data.get("model_identifier", "claude-sonnet-4-6"),
            "taxonomy_version": prov_data.get("taxonomy_version", "0.1"),
        },
        "closure_declaration": {
            "accepted_endpoint": "B-T1D / Arm D",
            "closure_scope": (
                "Batch 01 Stage B semantic classification endpoint is frozen. "
                "No later Batch 01 Stage B treatment is accepted. Any future Stage B research "
                "must occur under a new benchmark version, new batch, or explicitly reopened "
                "programme rather than mutating Batch 01."
            ),
            "production_readiness": (
                "Research endpoint only; not declared a solved, optimal, or production-ready classifier."
            ),
            "status": "CLOSED / FROZEN",
        },
        "closure_status": "closed_frozen",
        "corpora": {
            "corpus_revision_rationale": (
                "Revision batch_01_v0.2-grounding corrected an external-knowledge grounding defect "
                "in ref-gsa-agentic-coding-quickstart-005 relationships. Stage A baseline evaluated "
                "on v0.1; final Stage B scoring evaluated on v0.2-grounding."
            ),
            "historical_baseline_corpus_version": "batch_01_v0.1",
            "historical_baseline_reference_corpus_hash": FROZEN_HISTORICAL_BASELINE_CORPUS_HASH,
            "scoring_corpus_version": "batch_01_v0.2-grounding",
            "scoring_reference_corpus_hash": FROZEN_SCORING_REFERENCE_CORPUS_HASH,
        },
        "cryptographic_hashes": {
            "accepted_mixed_semantic_hash": ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH,
            "arm_d_outcomes_semantic_hash": FROZEN_ARM_D_OUTCOMES_SEMANTIC_HASH,
            "arm_d_treatment_profile_hash": FROZEN_ARM_D_PROFILE_HASH,
            "control_arm_b_profile_hash": prov_data.get("control_arm_b_profile_hash"),
            "control_arm_b_semantic_hash": prov_data.get("control_arm_b_semantic_hash"),
        },
        "dataset": {
            "composition": {
                "arm_d_relationship_outcomes": 100,
                "b0_non_relationship_outcomes": 700,
                "total_assembled_outcomes": 800,
            },
            "tasks_per_reference": 8,
            "total_outcomes": 800,
            "total_references": 100,
        },
        "endpoint_identity": {
            "arm_id": "treatment_d",
            "endpoint_name": "B-T1D / Arm D",
            "experiment_id": "b-t1d-relationship-selectivity",
            "purpose": "relationship_selectivity",
        },
        "endpoint_rationale": {
            "all_preservation_conditions_passed": diag_data.get(
                "all_preservation_conditions_passed", True
            ),
            "all_primary_hypotheses_passed": diag_data.get(
                "all_primary_hypotheses_passed", False
            ),
            "causal_inference_limitation": diag_data.get("causal_inference_limitation", ""),
            "key_findings": {
                "expected_empty_exact_matches": "Maintained 56/88 expected-empty exact matches.",
                "expected_empty_false_positives": "Maintained 32 expected-empty false-positive references.",
                "extra_tuples_reduction": (
                    "Reduced expected-empty extra tuples from 86 to 75, and total extra tuples from 105 to 86."
                ),
                "preservation_conditions": "All 5 preregistered preservation conditions (P1-P5) passed.",
                "primary_hypotheses": "Not all preregistered primary hypotheses passed (H1, H4, H5 passed; H2, H3 failed).",
                "strict_relationship_accuracy": (
                    f"Improved from B0 (0.00) and Arm B (0.59) to {ACCEPTED_RELATIONSHIP_EXACT_MATCHES}/100 "
                    f"({ACCEPTED_STRICT_RELATIONSHIP_ACCURACY})."
                ),
                "target_entity_recovery": "Maintained 18/18 (100%) target entity recovery.",
            },
            "summary": (
                "B-T1D Arm D achieved the highest validated semantic composite and relationship accuracy "
                "in Batch 01 while passing all preservation conditions."
            ),
        },
        "endpoint_scorecard": {
            "macro_task_averages": macro_task_averages,
            "per_repository": repo_scores,
            "relationship_exact_matches": ACCEPTED_RELATIONSHIP_EXACT_MATCHES,
            "stage_b_semantic_score": ACCEPTED_STAGE_B_SEMANTIC_SCORE,
            "strict_relationship_accuracy": ACCEPTED_STRICT_RELATIONSHIP_ACCURACY,
        },
        "mneme_execution_sha": mneme_execution_sha,
        "provenance_sources": {
            "arm_d_diagnostics": "benchmarks/open_architecture/batch_01/treatments/b_t1d/arm_d/diagnostics.json",
            "arm_d_outcomes": "benchmarks/open_architecture/batch_01/treatments/b_t1d/arm_d/outcomes.jsonl",
            "arm_d_provenance": "benchmarks/open_architecture/batch_01/treatments/b_t1d/arm_d/provenance.json",
            "arm_d_score": "benchmarks/open_architecture/batch_01/treatments/b_t1d/arm_d/stage_b_score.json",
            "baseline_b0_outcomes": "benchmarks/open_architecture/batch_01/baseline_stage_b/classifier_outcomes.jsonl",
            "baseline_b0_provenance": "benchmarks/open_architecture/batch_01/baseline_stage_b/stage_b_provenance.json",
            "v0_2_grounding_revision": "benchmarks/open_architecture/batch_01/revisions/batch_01_v0.2-grounding/revision.json",
        },
    }


def write_stage_b_closure(
    target_path: Path | str | None = None,
    repo_root: Path | str | None = None,
    *,
    mneme_execution_sha: str = FROZEN_STAGE_B_CLOSURE_MNEME_SHA,
) -> Path:
    """Generate and write the authoritative stage_b_closure.json artifact."""
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent.parent
    dest = (
        Path(target_path)
        if target_path is not None
        else root
        / "benchmarks"
        / "open_architecture"
        / "batch_01"
        / "stage_b"
        / "stage_b_closure.json"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    closure_data = build_stage_b_closure(root, mneme_execution_sha=mneme_execution_sha)
    serialized = json.dumps(closure_data, indent=2, sort_keys=True) + "\n"
    dest.write_text(serialized, encoding="utf-8", newline="\n")
    return dest


__all__ = [
    "FROZEN_STAGE_B_CLOSURE_MNEME_SHA",
    "FROZEN_HISTORICAL_BASELINE_CORPUS_HASH",
    "FROZEN_SCORING_REFERENCE_CORPUS_HASH",
    "FROZEN_ARM_D_PROFILE_HASH",
    "FROZEN_ARM_D_OUTCOMES_SEMANTIC_HASH",
    "ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH",
    "ACCEPTED_STAGE_B_SEMANTIC_SCORE",
    "ACCEPTED_STRICT_RELATIONSHIP_ACCURACY",
    "ACCEPTED_RELATIONSHIP_EXACT_MATCHES",
    "STAGE_B_EVALUATED_TASKS",
    "build_stage_b_closure",
    "write_stage_b_closure",
]
