"""
mneme.open_architecture.batch_01_closure — Authoritative Batch 01 Top-Level Closure Manifest.

Append-only integrity manifest binding the frozen Stage A discovery baseline,
Stage B semantic classification closure, and Stage C governing decision set closure
for O1A Batch 01.

Binds:
- Batch 01 status: CLOSED / FROZEN
- Stage A summary artifact: benchmarks/open_architecture/batch_01/stage_a/stage_a_summary.json
  and its SHA-256 content digest.
- Stage B closure artifact: benchmarks/open_architecture/batch_01/stage_b/stage_b_closure.json
  and its SHA-256 content digest (accepted endpoint: B-T1D / Arm D).
- Stage C closure artifact: benchmarks/open_architecture/batch_01/stage_c/stage_c_closure.json
  and its SHA-256 content digest (accepted endpoint: B3).
- Authoritative manifest.yaml and baseline.yaml configuration hashes.
- Authoritative reference and scenario corpora identities.
- Mneme execution commit SHA at closure: 8f2a9281bc5e54ccacac12577c04d2ce1694cfb9 (PR #436 merged).

Methodology & Architecture Invariants:
- Research-only: zero writes to canonical Mneme state (.mneme/, DecisionIndex,
  MemoryStore, DecisionProposal, canonical authority, etc.).
- Stage Independence: Stage A discovery metrics, Stage B semantic metrics, and
  Stage C GDS metrics remain strictly separate; they are never collapsed or averaged
  into a single benchmark score.
- Deterministic fail-closed validation: verifies all stage artifact content hashes,
  manifest/baseline configuration hashes, and accepted endpoint declarations upon loading.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from mneme.open_architecture.baseline import BaselineConfig
from mneme.open_architecture.manifest import Manifest

# ── Frozen Constants ────────────────────────────────────────────────────────────

FROZEN_BATCH_01_CLOSURE_MNEME_SHA: str = "8f2a9281bc5e54ccacac12577c04d2ce1694cfb9"

FROZEN_STAGE_A_ARTIFACT_SHA256: str = (
    "a554d2fc9c3ff7e84f616387b25e257c0d0019b43c80250c7c9ec890af5e62f6"
)
FROZEN_STAGE_B_ARTIFACT_SHA256: str = (
    "3ced430b70fd0eda336ac4fee7c8e012b4eb3cc0e902ea769118a52939ec16b5"
)
FROZEN_STAGE_C_ARTIFACT_SHA256: str = (
    "5cd49ea6c8282113b59db654ca05953711a080f130cb1136f195a2423318af29"
)

FROZEN_MANIFEST_CONFIG_HASH: str = "4af7e5794011b43d39682cdfeac9f54e"
FROZEN_BASELINE_CONFIG_HASH: str = "31e18dc1e2bd9ad30bec86dce1a9295a"
FROZEN_REFERENCE_CORPUS_V0_1_HASH: str = "0455bd66aae52551c35b37a63c2d185f"
FROZEN_SCORING_REFERENCE_CORPUS_V0_2_HASH: str = "700a569e24bf90707ba14ff65eea2ab5"
FROZEN_SCENARIO_CORPUS_HASH: str = "2ff8751955fd64a33316aca6692dc803"

ACCEPTED_STAGE_B_ENDPOINT: str = "B-T1D / Arm D"
ACCEPTED_STAGE_C_ENDPOINT: str = "B3"
HEADLINE_METRIC: str = "governing_decision_set_f1"


def compute_file_sha256(path: Path) -> str:
    """Compute hex SHA-256 digest of file bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_batch_01_closure(
    repo_root: Path | str | None = None,
    *,
    mneme_execution_sha: str = FROZEN_BATCH_01_CLOSURE_MNEME_SHA,
) -> dict[str, Any]:
    """Construct deterministic Batch 01 closure manifest binding all frozen stage evidence.

    Fails closed if:
    - manifest.yaml, baseline.yaml, or any of the 3 stage artifacts is missing.
    - Any configuration hash or stage artifact SHA-256 deviates from frozen values.
    - Any stage accepted endpoint or status fails validation.
    """
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent.parent
    b01_dir = root / "benchmarks" / "open_architecture" / "batch_01"

    manifest_path = b01_dir / "manifest.yaml"
    baseline_path = b01_dir / "baseline.yaml"
    stage_a_path = b01_dir / "stage_a" / "stage_a_summary.json"
    stage_b_path = b01_dir / "stage_b" / "stage_b_closure.json"
    stage_c_path = b01_dir / "stage_c" / "stage_c_closure.json"

    for p, name in [
        (manifest_path, "manifest.yaml"),
        (baseline_path, "baseline.yaml"),
        (stage_a_path, "stage_a_summary.json"),
        (stage_b_path, "stage_b_closure.json"),
        (stage_c_path, "stage_c_closure.json"),
    ]:
        if not p.is_file():
            raise FileNotFoundError(f"Missing required Batch 01 closure source: {name} at {p}")

    # 1. Authoritative manifest and baseline validation
    manifest = Manifest.load(manifest_path)
    if manifest.headline_metric != HEADLINE_METRIC:
        raise ValueError(
            f"Manifest headline metric mismatch: expected {HEADLINE_METRIC!r}, "
            f"got {manifest.headline_metric!r}"
        )
    manifest_hash = manifest.configuration_hash()
    if manifest_hash != FROZEN_MANIFEST_CONFIG_HASH:
        raise ValueError(
            f"Manifest configuration hash mismatch: expected {FROZEN_MANIFEST_CONFIG_HASH!r}, "
            f"got {manifest_hash!r}"
        )

    baseline = BaselineConfig.load(baseline_path)
    baseline_hash = baseline.configuration_hash()
    if baseline_hash != FROZEN_BASELINE_CONFIG_HASH:
        raise ValueError(
            f"Baseline configuration hash mismatch: expected {FROZEN_BASELINE_CONFIG_HASH!r}, "
            f"got {baseline_hash!r}"
        )

    # 2. Stage artifact cryptographic digest verification
    stage_a_sha256 = compute_file_sha256(stage_a_path)
    if stage_a_sha256 != FROZEN_STAGE_A_ARTIFACT_SHA256:
        raise ValueError(
            f"Stage A artifact SHA-256 mismatch: expected {FROZEN_STAGE_A_ARTIFACT_SHA256!r}, "
            f"got {stage_a_sha256!r}"
        )

    stage_b_sha256 = compute_file_sha256(stage_b_path)
    if stage_b_sha256 != FROZEN_STAGE_B_ARTIFACT_SHA256:
        raise ValueError(
            f"Stage B artifact SHA-256 mismatch: expected {FROZEN_STAGE_B_ARTIFACT_SHA256!r}, "
            f"got {stage_b_sha256!r}"
        )

    stage_c_sha256 = compute_file_sha256(stage_c_path)
    if stage_c_sha256 != FROZEN_STAGE_C_ARTIFACT_SHA256:
        raise ValueError(
            f"Stage C artifact SHA-256 mismatch: expected {FROZEN_STAGE_C_ARTIFACT_SHA256!r}, "
            f"got {stage_c_sha256!r}"
        )

    # 3. Load stage data and verify structural declarations
    stage_a_data = json.loads(stage_a_path.read_text(encoding="utf-8"))
    stage_b_data = json.loads(stage_b_path.read_text(encoding="utf-8"))
    stage_c_data = json.loads(stage_c_path.read_text(encoding="utf-8"))

    if stage_b_data.get("closure_status") != "closed_frozen":
        raise ValueError(
            f"Stage B closure status must be 'closed_frozen', got {stage_b_data.get('closure_status')!r}"
        )
    if (
        stage_b_data.get("closure_declaration", {}).get("accepted_endpoint")
        != ACCEPTED_STAGE_B_ENDPOINT
    ):
        raise ValueError(
            f"Stage B accepted endpoint mismatch: expected {ACCEPTED_STAGE_B_ENDPOINT!r}, "
            f"got {stage_b_data.get('closure_declaration', {}).get('accepted_endpoint')!r}"
        )

    if stage_c_data.get("closure_status") != "closed_frozen":
        raise ValueError(
            f"Stage C closure status must be 'closed_frozen', got {stage_c_data.get('closure_status')!r}"
        )
    if (
        stage_c_data.get("closure_declaration", {}).get("accepted_endpoint")
        != ACCEPTED_STAGE_C_ENDPOINT
    ):
        raise ValueError(
            f"Stage C accepted endpoint mismatch: expected {ACCEPTED_STAGE_C_ENDPOINT!r}, "
            f"got {stage_c_data.get('closure_declaration', {}).get('accepted_endpoint')!r}"
        )

    # 4. Construct complete, append-only Batch 01 closure manifest
    return {
        "artifact_type": "batch_01_closure_manifest",
        "artifact_version": "0.1",
        "baseline_id": baseline.baseline_id,
        "batch_id": manifest.batch_id,
        "closure_declaration": {
            "methodology_invariant": (
                "Stages remain discrete and independent: Stage A dynamic discovery, "
                "Stage B semantic classification, and Stage C governing decision set retrieval. "
                "Per O1A benchmark methodology, stages are never collapsed or averaged into an "
                "overall benchmark score."
            ),
            "production_readiness": (
                "Research benchmark closure only; not declared a production-ready system."
            ),
            "scope": (
                "O1A Batch 01 benchmark program is formally closed and frozen across all three stages "
                "(Stage A Discovery, Stage B Semantic Classification, and Stage C Governing Decision Set). "
                "No further treatments, tunings, or calibrations are accepted for Batch 01. Any future "
                "research must occur under a new benchmark version, new batch, or explicitly reopened "
                "programme rather than mutating Batch 01."
            ),
            "status": "CLOSED / FROZEN",
        },
        "closure_status": "CLOSED / FROZEN",
        "corpora_identities": {
            "baseline_configuration_hash": baseline_hash,
            "manifest_configuration_hash": manifest_hash,
            "reference_corpus_v0_1_hash": FROZEN_REFERENCE_CORPUS_V0_1_HASH,
            "reference_corpus_v0_2_grounding_hash": FROZEN_SCORING_REFERENCE_CORPUS_V0_2_HASH,
            "scenario_corpus_hash": FROZEN_SCENARIO_CORPUS_HASH,
        },
        "dataset": {
            "decisions_per_repository": manifest.targets.decisions_per_repository,
            "repositories": sorted(r.id for r in manifest.repositories),
            "repository_count": len(manifest.repositories),
            "scenarios_per_repository": manifest.targets.scenarios_per_repository,
            "total_reference_decisions": manifest.targets.decisions_total,
            "total_scenarios": manifest.targets.scenarios_total,
        },
        "headline_metric": manifest.headline_metric,
        "mneme_execution_sha": mneme_execution_sha,
        "provenance_sources": {
            "baseline_config": "benchmarks/open_architecture/batch_01/baseline.yaml",
            "manifest": "benchmarks/open_architecture/batch_01/manifest.yaml",
            "stage_a_summary": "benchmarks/open_architecture/batch_01/stage_a/stage_a_summary.json",
            "stage_b_closure": "benchmarks/open_architecture/batch_01/stage_b/stage_b_closure.json",
            "stage_c_closure": "benchmarks/open_architecture/batch_01/stage_c/stage_c_closure.json",
        },
        "stages": {
            "stage_a": {
                "artifact_path": "benchmarks/open_architecture/batch_01/stage_a/stage_a_summary.json",
                "artifact_sha256": stage_a_sha256,
                "extractor": {
                    "confidence": stage_a_data["extractor"]["config"]["confidence"],
                    "id": stage_a_data["extractor"]["id"],
                    "keyword_count": len(stage_a_data["extractor"]["config"]["keywords"]),
                    "max_lines": stage_a_data["extractor"]["config"]["max_lines"],
                    "min_lines": stage_a_data["extractor"]["config"]["min_lines"],
                    "version": stage_a_data["extractor"]["version"],
                },
                "matching_contract": stage_a_data["matching_contract"]["contract_id"],
                "reference_corpus_hash": stage_a_data["reference_corpus_hash"],
                "stage_name": "Stage A — Dynamic Discovery",
                "status": "BASELINE_FROZEN",
                "summary_metrics": {
                    "discovered_documents": stage_a_data["aggregate"]["total_discovered_documents"],
                    "extracted_candidates": stage_a_data["aggregate"]["total_extracted_candidates"],
                    "macro_f1": stage_a_data["aggregate"]["macro_f1"],
                    "macro_precision": stage_a_data["aggregate"]["macro_precision"],
                    "macro_recall": stage_a_data["aggregate"]["macro_recall"],
                    "matched_candidates": stage_a_data["aggregate"]["total_matched_candidates"],
                    "matched_references": stage_a_data["aggregate"]["total_matched_references"],
                    "missed_source_references": sum(
                        len(r["missed_source_reference_ids"])
                        for r in stage_a_data["repositories"].values()
                    ),
                    "reference_decisions": stage_a_data["aggregate"]["total_reference_decisions"],
                },
            },
            "stage_b": {
                "accepted_endpoint": stage_b_data["closure_declaration"]["accepted_endpoint"],
                "accepted_mixed_semantic_hash": stage_b_data["cryptographic_hashes"][
                    "accepted_mixed_semantic_hash"
                ],
                "arm_d_outcomes_semantic_hash": stage_b_data["cryptographic_hashes"][
                    "arm_d_outcomes_semantic_hash"
                ],
                "arm_d_treatment_profile_hash": stage_b_data["cryptographic_hashes"][
                    "arm_d_treatment_profile_hash"
                ],
                "arm_id": stage_b_data["endpoint_identity"]["arm_id"],
                "artifact_path": "benchmarks/open_architecture/batch_01/stage_b/stage_b_closure.json",
                "artifact_sha256": stage_b_sha256,
                "experiment_id": stage_b_data["endpoint_identity"]["experiment_id"],
                "scoring_reference_corpus_hash": stage_b_data["corpora"][
                    "scoring_reference_corpus_hash"
                ],
                "stage_name": "Stage B — Semantic Classification",
                "status": stage_b_data["closure_declaration"]["status"],
                "summary_metrics": {
                    "authority_accuracy": stage_b_data["endpoint_scorecard"]["macro_task_averages"][
                        "authority_accuracy"
                    ],
                    "decision_classification_accuracy": stage_b_data["endpoint_scorecard"][
                        "macro_task_averages"
                    ]["decision_classification_accuracy"],
                    "domain_micro_f1": stage_b_data["endpoint_scorecard"]["macro_task_averages"][
                        "domain_micro_f1"
                    ],
                    "enforcement_classification_accuracy": stage_b_data["endpoint_scorecard"][
                        "macro_task_averages"
                    ]["enforcement_classification_accuracy"],
                    "lifecycle_accuracy": stage_b_data["endpoint_scorecard"]["macro_task_averages"][
                        "lifecycle_accuracy"
                    ],
                    "preservation_conditions_passed": stage_b_data["endpoint_rationale"][
                        "all_preservation_conditions_passed"
                    ],
                    "purpose_micro_f1": stage_b_data["endpoint_scorecard"]["macro_task_averages"][
                        "purpose_micro_f1"
                    ],
                    "relationship_accuracy": stage_b_data["endpoint_scorecard"]["macro_task_averages"][
                        "relationship_accuracy"
                    ],
                    "relationship_exact_matches": stage_b_data["endpoint_scorecard"][
                        "relationship_exact_matches"
                    ],
                    "scope_accuracy": stage_b_data["endpoint_scorecard"]["macro_task_averages"][
                        "scope_accuracy"
                    ],
                    "stage_b_semantic_score": stage_b_data["endpoint_scorecard"][
                        "stage_b_semantic_score"
                    ],
                    "strict_relationship_accuracy": stage_b_data["endpoint_scorecard"][
                        "strict_relationship_accuracy"
                    ],
                },
                "total_assembled_outcomes": stage_b_data["dataset"]["total_outcomes"],
            },
            "stage_c": {
                "accepted_endpoint": stage_c_data["closure_declaration"]["accepted_endpoint"],
                "artifact_path": "benchmarks/open_architecture/batch_01/stage_c/stage_c_closure.json",
                "artifact_sha256": stage_c_sha256,
                "experiment_id": stage_c_data["endpoint_identity"]["experiment_id"],
                "headline_metric": stage_c_data["headline_metric"],
                "profile": stage_c_data["endpoint_identity"]["profile"],
                "scenario_corpus_hash": stage_c_data["corpora_and_inputs"]["scenario_corpus_hash"],
                "selection_policy": stage_c_data["b3_profile_definition"]["selection_policy"],
                "stage_c_experiment_profile_hash": stage_c_data["corpora_and_inputs"][
                    "stage_c_experiment_profile_hash"
                ],
                "stage_name": "Stage C — Governing Decision Set",
                "status": stage_c_data["closure_declaration"]["status"],
                "summary_metrics": {
                    "end_to_end_exact_set_matches": stage_c_data["accepted_endpoint_scorecard"][
                        "end_to_end_metrics"
                    ]["exact_set_matches"],
                    "end_to_end_macro_f1": stage_c_data["accepted_endpoint_scorecard"][
                        "end_to_end_metrics"
                    ]["macro_f1"],
                    "end_to_end_macro_precision": stage_c_data["accepted_endpoint_scorecard"][
                        "end_to_end_metrics"
                    ]["macro_precision"],
                    "end_to_end_macro_recall": stage_c_data["accepted_endpoint_scorecard"][
                        "end_to_end_metrics"
                    ]["macro_recall"],
                    "human_reference_exact_set_matches": stage_c_data["accepted_endpoint_scorecard"][
                        "human_reference_metrics"
                    ]["exact_set_matches"],
                    "human_reference_macro_f1": stage_c_data["accepted_endpoint_scorecard"][
                        "human_reference_metrics"
                    ]["macro_f1"],
                    "total_false_negatives": stage_c_data["accepted_endpoint_scorecard"][
                        "end_to_end_metrics"
                    ]["total_false_negatives"],
                    "total_false_positives": stage_c_data["accepted_endpoint_scorecard"][
                        "end_to_end_metrics"
                    ]["total_false_positives"],
                    "total_scenarios": stage_c_data["accepted_endpoint_scorecard"]["end_to_end_metrics"][
                        "total_scenarios"
                    ],
                },
            },
        },
    }


def write_batch_01_closure(
    target_path: Path | str | None = None,
    repo_root: Path | str | None = None,
    *,
    mneme_execution_sha: str = FROZEN_BATCH_01_CLOSURE_MNEME_SHA,
) -> Path:
    """Generate and write the authoritative batch_01_closure.json artifact."""
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent.parent
    dest = (
        Path(target_path)
        if target_path is not None
        else root
        / "benchmarks"
        / "open_architecture"
        / "batch_01"
        / "batch_01_closure.json"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    closure_data = build_batch_01_closure(root, mneme_execution_sha=mneme_execution_sha)
    serialized = json.dumps(closure_data, indent=2, sort_keys=True) + "\n"
    dest.write_text(serialized, encoding="utf-8", newline="\n")
    return dest


__all__ = [
    "FROZEN_BATCH_01_CLOSURE_MNEME_SHA",
    "FROZEN_STAGE_A_ARTIFACT_SHA256",
    "FROZEN_STAGE_B_ARTIFACT_SHA256",
    "FROZEN_STAGE_C_ARTIFACT_SHA256",
    "FROZEN_MANIFEST_CONFIG_HASH",
    "FROZEN_BASELINE_CONFIG_HASH",
    "FROZEN_REFERENCE_CORPUS_V0_1_HASH",
    "FROZEN_SCORING_REFERENCE_CORPUS_V0_2_HASH",
    "FROZEN_SCENARIO_CORPUS_HASH",
    "ACCEPTED_STAGE_B_ENDPOINT",
    "ACCEPTED_STAGE_C_ENDPOINT",
    "HEADLINE_METRIC",
    "compute_file_sha256",
    "build_batch_01_closure",
    "write_batch_01_closure",
]
