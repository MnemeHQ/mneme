"""
mneme.open_architecture.stage_c_end_to_end_experiment — O1A Stage B → Stage C End-to-End Evaluation.

Implements the research-only bridge between frozen accepted Stage B semantic
classifier outcomes (700 B0 non-relationship + 100 Arm D relationship outcomes)
and Stage C Governing Decision Set (GDS) evaluation via canonical DecisionRetriever.

Architecture and Boundary Invariants:
- Research-only sidecar: does NOT modify canonical DecisionRetriever,
  ConflictDetector, Enforcer, projection.py, gds_evaluation.py, or harness.py.
- Preserves frozen `ref-*` candidate identities and immutable reference text
  (candidate_id, repository, source_file, source_location, raw_statement, normalized_decision).
- Overlays normalized Stage B classifier predictions onto DecisionCandidate fields
  using authoritative normalization functions from classification.py.
- Consumes the exact scores produced by the existing frozen DecisionRetriever.
- Evaluates the three frozen profiles (B0, C-T1A, B3) over both the isolated
  human-reference baseline and the end-to-end Stage B → Stage C predictions.
- Zero model/API/network calls (pure offline deterministic replay).
- Zero canonical authority writes (no MemoryStore, DecisionProposal, DecisionIndex mutations).
- Fails closed on missing, duplicate, escalated, or invalid outcomes.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mneme.decision_retriever import DecisionRetriever
from mneme.open_architecture.classification import (
    ClassifierTaskType,
    normalize_authority,
    normalize_classification,
    normalize_domains,
    normalize_enforcement_potential,
    normalize_lifecycle,
    normalize_purposes,
    normalize_relationships,
    normalize_scopes,
)
from mneme.open_architecture.gds_calibration_experiment import (
    EVALUATED_PROFILES,
    FROZEN_FUNCTION_WORDS,
    FROZEN_STRUCTURAL_PREFIXES,
    POLICY_RELATIVE_80,
    POLICY_SCORE_GT_ZERO,
    PROFILE_B0,
    PROFILE_B3,
    PROFILE_C_T1A,
    RELATIVE_THRESHOLD_RATIO,
    SELECTION_EPSILON,
    ProfileAggregateMetrics,
    RepoCalibrationSummary,
    ScenarioCalibrationResult,
    _evaluate_scenario_for_profile,
    select_decisions_for_policy,
    transform_query_for_b3,
)
from mneme.open_architecture.harness import (
    FROZEN_BASELINE_CONFIG_HASH,
    FROZEN_BASELINE_ID,
    FROZEN_MANIFEST_CONFIG_HASH,
    FROZEN_REFERENCE_CORPUS_HASH,
    FROZEN_SCENARIO_CORPUS_HASH,
    FrozenReferenceDecision,
    SEMANTIC_TASK_TYPES,
    import_scenarios_jsonl,
    load_reference_corpus,
    preflight_batch_01,
)
from mneme.open_architecture.manifest import Manifest
from mneme.open_architecture.metrics import GoverningDecisionSetMetrics, compute_suite_metrics
from mneme.open_architecture.projection import project_candidates_to_decisions
from mneme.open_architecture.schemas import DecisionCandidate
from mneme.open_architecture.stage_b_baseline import (
    FROZEN_CLASSIFIER_BACKEND,
    FROZEN_CLASSIFIER_VERSION,
    FROZEN_MODEL_IDENTIFIER,
    FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH,
    FROZEN_TAXONOMY_VERSION,
    FrozenClassifierOutcome,
    compute_stage_b_semantic_content_hash,
    load_stage_b_outcomes,
)
from mneme.open_architecture.stage_b_relationship_selectivity_diagnostics import (
    FROZEN_ARM_D_OUTCOMES_SEMANTIC_HASH,
)
from mneme.open_architecture.stage_b_relationship_selectivity_experiment import (
    ARM_D_ID,
    build_mixed_stage_b_outcomes,
    load_treatment_run,
)

EXPERIMENT_ID: str = "o1a-stage-c-end-to-end"
FROZEN_PARENT_MAIN_SHA: str = "d04a5c832421d68d3aa1d7e32127fc0564eca8fa"

# Expected semantic content hash for the accepted 800 mixed outcomes (700 B0 + 100 Arm D)
ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH: str = (
    "sha256:662de96721513ab1fd0d6e2d55eb7c037dedcb04c75b441b610aa3a57e236b8a"
)


# ── Loading Accepted Stage B Outcomes ──────────────────────────────────────────


def load_accepted_stage_b_replay_outcomes(
    repo_root: Path | str | None = None,
) -> list[FrozenClassifierOutcome]:
    """Load and validate the accepted mixed Stage B replay outcomes (700 B0 + 100 Arm D).

    Fails closed if:
    - Frozen B0 outcomes fail validation against FROZEN_STAGE_B_SEMANTIC_CONTENT_HASH.
    - Arm D treatment run fails validation against FROZEN_ARM_D_OUTCOMES_SEMANTIC_HASH.
    - Mixed assembly fails validation or count != 800.
    - Semantic content hash does not match ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH.
    """
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent.parent
    b0_path = root / "benchmarks" / "open_architecture" / "batch_01" / "baseline_stage_b" / "classifier_outcomes.jsonl"
    arm_d_dir = root / "benchmarks" / "open_architecture" / "batch_01" / "treatments" / "b_t1d" / "arm_d"
    ref_dir = root / "benchmarks" / "open_architecture" / "batch_01" / "reference_decisions"

    refs = load_reference_corpus(ref_dir)
    expected_ids = {r.reference_decision_id for r in refs}

    b0_outcomes = load_stage_b_outcomes(b0_path)
    arm_d_outcomes, arm_d_sidecar = load_treatment_run(arm_d_dir, expected_ids)

    if arm_d_sidecar.treatment_semantic_content_hash != FROZEN_ARM_D_OUTCOMES_SEMANTIC_HASH:
        raise ValueError(
            f"Arm D outcomes hash mismatch: expected {FROZEN_ARM_D_OUTCOMES_SEMANTIC_HASH!r}, "
            f"got {arm_d_sidecar.treatment_semantic_content_hash!r}"
        )

    mixed = build_mixed_stage_b_outcomes(b0_outcomes, arm_d_outcomes)

    computed_hash = compute_stage_b_semantic_content_hash(mixed)
    if computed_hash != ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH:
        raise ValueError(
            f"Mixed Stage B outcomes semantic hash mismatch: "
            f"expected {ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH!r}, got {computed_hash!r}"
        )

    return mixed


# ── Stage B → DecisionCandidate Composition ────────────────────────────────────


def compose_classified_candidate(
    reference: FrozenReferenceDecision,
    outcomes_by_task: dict[ClassifierTaskType, FrozenClassifierOutcome],
) -> DecisionCandidate:
    """Compose a DecisionCandidate from immutable reference evidence and Stage B predictions.

    Preserves:
    - candidate_id (ref-* identity)
    - repository
    - source_file provenance
    - source_location provenance
    - raw_statement (exact raw evidence)
    - normalized_decision (immutable ground-truth decision text)

    Overlays normalized classifier predictions:
    - classification <- normalize_classification(task: decision_classification)[0]
    - decision_domains <- normalize_domains(task: domains)
    - decision_purposes <- normalize_purposes(task: purposes)
    - authority_status <- normalize_authority(task: authority)
    - authority_evidence <- evidence from authority task output
    - scopes <- normalize_scopes(task: scope)
    - lifecycle_status <- normalize_lifecycle(task: lifecycle)
    - relationships <- normalize_relationships(task: relationships)
    - enforcement_potential <- normalize_enforcement_potential(task: enforcement_potential)
    - candidate_rule <- candidate_rule from enforcement_potential task output

    Fails closed if:
    - Any of the 8 required semantic tasks is missing.
    - Any outcome has candidate_id != reference.reference_decision_id.
    - Any outcome is escalated or contains an error.
    - Normalization fails on any dimension.
    """
    ref_id = reference.reference_decision_id

    # Verify all 8 tasks are present
    missing_tasks = [t for t in SEMANTIC_TASK_TYPES if t not in outcomes_by_task]
    if missing_tasks:
        raise ValueError(
            f"Reference {ref_id} missing required task outcomes: {[t.value for t in missing_tasks]}"
        )

    for task_type, outcome in outcomes_by_task.items():
        if outcome.candidate_id != ref_id:
            raise ValueError(
                f"Candidate ID mismatch for task {task_type.value}: "
                f"expected {ref_id!r}, got {outcome.candidate_id!r}"
            )
        if outcome.escalated:
            raise ValueError(f"Task {task_type.value} for candidate {ref_id} was escalated")
        if "error" in outcome.output:
            raise ValueError(
                f"Task {task_type.value} for candidate {ref_id} contains error: {outcome.output['error']}"
            )

    # 1. Classification
    c_out = outcomes_by_task[ClassifierTaskType.DECISION_CLASSIFICATION]
    norm_class = normalize_classification(c_out.output.get("classification"))[0]

    # 2. Domains
    d_out = outcomes_by_task[ClassifierTaskType.DOMAINS]
    norm_domains = normalize_domains(d_out.output.get("domains"))

    # 3. Purposes
    p_out = outcomes_by_task[ClassifierTaskType.PURPOSES]
    norm_purposes = normalize_purposes(p_out.output.get("purposes"))

    # 4. Authority
    a_out = outcomes_by_task[ClassifierTaskType.AUTHORITY]
    norm_auth = normalize_authority(a_out.output.get("authority"))
    auth_evidence = a_out.output.get("evidence")

    # 5. Scopes
    s_out = outcomes_by_task[ClassifierTaskType.SCOPE]
    norm_scopes = normalize_scopes(s_out.output.get("scopes", []))

    # 6. Lifecycle
    l_out = outcomes_by_task[ClassifierTaskType.LIFECYCLE]
    norm_lc = normalize_lifecycle(l_out.output.get("lifecycle"))

    # 7. Relationships
    r_out = outcomes_by_task[ClassifierTaskType.RELATIONSHIPS]
    norm_rels = normalize_relationships(r_out.output.get("relationships", []))

    # 8. Enforcement potential
    e_out = outcomes_by_task[ClassifierTaskType.ENFORCEMENT_POTENTIAL]
    norm_enf = normalize_enforcement_potential(e_out.output.get("enforcement_potential"))
    cand_rule = e_out.output.get("candidate_rule")

    return DecisionCandidate(
        candidate_id=reference.reference_decision_id,
        repository=reference.repository,
        source_file=reference.source_file,
        source_location=reference.source_location,
        raw_statement=reference.raw_evidence,
        normalized_decision=reference.normalized_decision,
        classification=norm_class,
        decision_domains=norm_domains,
        decision_purposes=norm_purposes,
        authority_status=norm_auth,
        authority_evidence=auth_evidence,
        scopes=norm_scopes,
        lifecycle_status=norm_lc,
        relationships=norm_rels,
        enforcement_potential=norm_enf,
        candidate_rule=cand_rule,
        confidence=None,
        human_validation_status="ambiguous",
        human_corrections=None,
    )


def compose_classified_candidates(
    references: list[FrozenReferenceDecision],
    outcomes: list[FrozenClassifierOutcome],
) -> list[DecisionCandidate]:
    """Compose classified DecisionCandidates for a list of reference decisions.

    Fails closed on:
    - Duplicate (candidate_id, task_type) keys.
    - Reference IDs not matching outcome candidate IDs.
    - Any reference lacking exactly 8 tasks.
    - Total outcome count != len(references) * 8.
    """
    by_ref: dict[str, dict[ClassifierTaskType, FrozenClassifierOutcome]] = {}
    seen_keys: set[tuple[str, str]] = set()

    for o in outcomes:
        key = (o.candidate_id, o.task_type.value)
        if key in seen_keys:
            raise ValueError(f"Duplicate outcome for {key}")
        seen_keys.add(key)
        by_ref.setdefault(o.candidate_id, {})[o.task_type] = o

    expected_ref_ids = {r.reference_decision_id for r in references}
    observed_ref_ids = set(by_ref.keys())

    if expected_ref_ids != observed_ref_ids:
        missing = expected_ref_ids - observed_ref_ids
        extra = observed_ref_ids - expected_ref_ids
        raise ValueError(
            f"Candidate ID mismatch between references and outcomes: "
            f"missing={sorted(missing)}, extra={sorted(extra)}"
        )

    composed: list[DecisionCandidate] = []
    for ref in references:
        task_map = by_ref[ref.reference_decision_id]
        cand = compose_classified_candidate(ref, task_map)
        composed.append(cand)

    composed.sort(key=lambda c: c.candidate_id)
    return composed


# ── Data Models ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProfileComparisonDelta:
    """Explicit delta between isolated-human baseline and end-to-end Stage B → Stage C."""

    profile: str
    human_macro_precision: float
    end_to_end_macro_precision: float
    delta_macro_precision: float
    human_macro_recall: float
    end_to_end_macro_recall: float
    delta_macro_recall: float
    human_macro_f1: float
    end_to_end_macro_f1: float
    delta_macro_f1: float
    human_false_positives: int
    end_to_end_false_positives: int
    delta_false_positives: int
    human_false_negatives: int
    end_to_end_false_negatives: int
    delta_false_negatives: int
    human_exact_set_matches: int
    end_to_end_exact_set_matches: int
    delta_exact_set_matches: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "human_macro_precision": self.human_macro_precision,
            "end_to_end_macro_precision": self.end_to_end_macro_precision,
            "delta_macro_precision": self.delta_macro_precision,
            "human_macro_recall": self.human_macro_recall,
            "end_to_end_macro_recall": self.end_to_end_macro_recall,
            "delta_macro_recall": self.delta_macro_recall,
            "human_macro_f1": self.human_macro_f1,
            "end_to_end_macro_f1": self.end_to_end_macro_f1,
            "delta_macro_f1": self.delta_macro_f1,
            "human_false_positives": self.human_false_positives,
            "end_to_end_false_positives": self.end_to_end_false_positives,
            "delta_false_positives": self.delta_false_positives,
            "human_false_negatives": self.human_false_negatives,
            "end_to_end_false_negatives": self.end_to_end_false_negatives,
            "delta_false_negatives": self.delta_false_negatives,
            "human_exact_set_matches": self.human_exact_set_matches,
            "end_to_end_exact_set_matches": self.end_to_end_exact_set_matches,
            "delta_exact_set_matches": self.delta_exact_set_matches,
        }


@dataclass(frozen=True)
class StageCEndToEndExperimentResult:
    """Immutable result of the Stage B → Stage C end-to-end evaluation."""

    experiment_id: str
    baseline_id: str
    parent_main_sha: str
    reference_corpus_hash: str
    scenario_corpus_hash: str
    manifest_config_hash: str
    baseline_config_hash: str
    stage_b_mixed_semantic_hash: str
    experiment_profile_hash: str
    isolated_human_baseline: dict[str, ProfileAggregateMetrics]
    end_to_end_predictions: dict[str, ProfileAggregateMetrics]
    profile_comparisons: dict[str, ProfileComparisonDelta]
    end_to_end_scenario_evaluations: list[ScenarioCalibrationResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "baseline_id": self.baseline_id,
            "parent_main_sha": self.parent_main_sha,
            "reference_corpus_hash": self.reference_corpus_hash,
            "scenario_corpus_hash": self.scenario_corpus_hash,
            "manifest_config_hash": self.manifest_config_hash,
            "baseline_config_hash": self.baseline_config_hash,
            "stage_b_mixed_semantic_hash": self.stage_b_mixed_semantic_hash,
            "experiment_profile_hash": self.experiment_profile_hash,
            "isolated_human_baseline": {
                p: s.to_dict() for p, s in sorted(self.isolated_human_baseline.items())
            },
            "end_to_end_predictions": {
                p: s.to_dict() for p, s in sorted(self.end_to_end_predictions.items())
            },
            "profile_comparisons": {
                p: d.to_dict() for p, d in sorted(self.profile_comparisons.items())
            },
            "end_to_end_scenario_evaluations": [
                s.to_dict() for s in self.end_to_end_scenario_evaluations
            ],
        }


# ── Profile Hash Computation ───────────────────────────────────────────────────


def compute_end_to_end_profile_hash(
    *,
    experiment_id: str = EXPERIMENT_ID,
    baseline_id: str = FROZEN_BASELINE_ID,
    parent_main_sha: str = FROZEN_PARENT_MAIN_SHA,
    reference_corpus_hash: str = FROZEN_REFERENCE_CORPUS_HASH,
    scenario_corpus_hash: str = FROZEN_SCENARIO_CORPUS_HASH,
    manifest_config_hash: str = FROZEN_MANIFEST_CONFIG_HASH,
    baseline_config_hash: str = FROZEN_BASELINE_CONFIG_HASH,
    stage_b_mixed_semantic_hash: str = ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH,
    profiles: tuple[str, ...] = EVALUATED_PROFILES,
    relative_ratio: float = RELATIVE_THRESHOLD_RATIO,
    epsilon: float = SELECTION_EPSILON,
    function_words: frozenset[str] = FROZEN_FUNCTION_WORDS,
    structural_prefixes: tuple[str, ...] = FROZEN_STRUCTURAL_PREFIXES,
) -> str:
    """Compute deterministic SHA-256 digest binding all experiment parameters."""
    payload = {
        "baseline_config_hash": baseline_config_hash,
        "baseline_id": baseline_id,
        "epsilon": epsilon,
        "experiment_id": experiment_id,
        "function_words": sorted(function_words),
        "manifest_config_hash": manifest_config_hash,
        "parent_main_sha": parent_main_sha,
        "profiles": list(profiles),
        "reference_corpus_hash": reference_corpus_hash,
        "relative_ratio": relative_ratio,
        "scenario_corpus_hash": scenario_corpus_hash,
        "stage_b_mixed_semantic_hash": stage_b_mixed_semantic_hash,
        "structural_prefixes": list(structural_prefixes),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


# ── Evaluation Helper ──────────────────────────────────────────────────────────


def _evaluate_candidate_corpus(
    manifest: Manifest,
    all_candidates: list[DecisionCandidate],
    all_scenarios: list[Any],
) -> tuple[dict[str, ProfileAggregateMetrics], list[ScenarioCalibrationResult]]:
    """Evaluate a candidate corpus across the 50 scenarios for B0, C-T1A, and B3."""
    scenario_evaluations: list[ScenarioCalibrationResult] = []
    profile_results: dict[str, list[ScenarioCalibrationResult]] = {
        p: [] for p in EVALUATED_PROFILES
    }
    repo_profile_results: dict[str, dict[str, list[ScenarioCalibrationResult]]] = {
        repo.id: {p: [] for p in EVALUATED_PROFILES} for repo in manifest.repositories
    }

    for repo_cfg in manifest.repositories:
        repo_cands = [c for c in all_candidates if c.repository == repo_cfg.github]
        if len(repo_cands) != 20:
            raise ValueError(f"Expected 20 candidates for '{repo_cfg.id}', got {len(repo_cands)}")

        repo_scenarios = [s for s in all_scenarios if s.repository == repo_cfg.github]
        if len(repo_scenarios) != 10:
            raise ValueError(f"Expected 10 scenarios for '{repo_cfg.id}', got {len(repo_scenarios)}")

        projected = project_candidates_to_decisions(repo_cands)
        retriever = DecisionRetriever(projected)

        for scn in repo_scenarios:
            for prof in EVALUATED_PROFILES:
                res = _evaluate_scenario_for_profile(retriever, scn, prof)
                scenario_evaluations.append(res)
                profile_results[prof].append(res)
                repo_profile_results[repo_cfg.id][prof].append(res)

    profile_summaries: dict[str, ProfileAggregateMetrics] = {}

    for prof in EVALUATED_PROFILES:
        res_list = profile_results[prof]
        metrics_list = [
            GoverningDecisionSetMetrics.compute(
                r.expected_governing_decision_ids, r.selected_decision_ids
            )
            for r in res_list
        ]
        suite_agg = compute_suite_metrics(metrics_list)

        exact_matches = sum(1 for r in res_list if r.exact_set_match)
        total_fps = sum(len(r.false_positive_ids) for r in res_list)
        total_fns = sum(len(r.false_negative_ids) for r in res_list)
        total_exp = sum(len(r.expected_governing_decision_ids) for r in res_list)
        total_pred = sum(len(r.selected_decision_ids) for r in res_list)
        mean_pred = total_pred / len(res_list) if res_list else 0.0

        repo_summaries: dict[str, RepoCalibrationSummary] = {}
        for repo_cfg in manifest.repositories:
            r_list = repo_profile_results[repo_cfg.id][prof]
            r_metrics = [
                GoverningDecisionSetMetrics.compute(
                    r.expected_governing_decision_ids, r.selected_decision_ids
                )
                for r in r_list
            ]
            r_agg = compute_suite_metrics(r_metrics)
            r_exact = sum(1 for r in r_list if r.exact_set_match)
            r_fps = sum(len(r.false_positive_ids) for r in r_list)
            r_fns = sum(len(r.false_negative_ids) for r in r_list)
            r_pred = sum(len(r.selected_decision_ids) for r in r_list)
            r_mean_pred = r_pred / len(r_list) if r_list else 0.0

            repo_summaries[repo_cfg.id] = RepoCalibrationSummary(
                repo_id=repo_cfg.id,
                repository_identifier=repo_cfg.github,
                macro_precision=r_agg["macro_precision"],
                macro_recall=r_agg["macro_recall"],
                macro_f1=r_agg["macro_f1"],
                exact_set_matches=r_exact,
                total_scenarios=len(r_list),
                total_false_positives=r_fps,
                total_false_negatives=r_fns,
                mean_predicted_set_size=r_mean_pred,
            )

        if prof == PROFILE_B0:
            sel_pol = POLICY_SCORE_GT_ZERO
            q_treat = "canonical_query"
        elif prof == PROFILE_C_T1A:
            sel_pol = POLICY_RELATIVE_80
            q_treat = "canonical_query"
        else:
            sel_pol = POLICY_RELATIVE_80
            q_treat = "structural_label_and_function_word_suppressed"

        profile_summaries[prof] = ProfileAggregateMetrics(
            profile=prof,
            selection_policy=sel_pol,
            query_treatment=q_treat,
            macro_precision=suite_agg["macro_precision"],
            macro_recall=suite_agg["macro_recall"],
            macro_f1=suite_agg["macro_f1"],
            exact_set_matches=exact_matches,
            total_scenarios=len(res_list),
            total_false_positives=total_fps,
            total_false_negatives=total_fns,
            total_expected_decisions=total_exp,
            total_predicted_decisions=total_pred,
            mean_predicted_set_size=mean_pred,
            per_repository=repo_summaries,
        )

    return profile_summaries, scenario_evaluations


# ── Execution Logic ────────────────────────────────────────────────────────────


def execute_stage_c_end_to_end_experiment(
    *,
    manifest_path: str | Path | None = None,
    baseline_path: str | Path | None = None,
    reference_corpus_dir: str | Path | None = None,
    scenarios_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    stage_b_outcomes: list[FrozenClassifierOutcome] | None = None,
) -> StageCEndToEndExperimentResult:
    """Execute O1A Stage B → Stage C End-to-End Evaluation.

    Evaluates both:
    1. Isolated human-reference baseline (reproducing frozen B0, C-T1A, B3 metrics).
    2. End-to-end Stage B → Stage C evaluation using candidates composed from
       frozen accepted Stage B predictions (700 B0 + 100 Arm D).

    Fails closed if preflight, hashes, or inputs deviate from pinned identities.
    Fails closed if output_dir exists and is non-empty.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent

    manifest_p = (
        Path(manifest_path)
        if manifest_path
        else repo_root / "benchmarks" / "open_architecture" / "batch_01" / "manifest.yaml"
    )
    baseline_p = (
        Path(baseline_path)
        if baseline_path
        else repo_root / "benchmarks" / "open_architecture" / "batch_01" / "baseline.yaml"
    )
    ref_dir = (
        Path(reference_corpus_dir)
        if reference_corpus_dir
        else repo_root / "benchmarks" / "open_architecture" / "batch_01" / "reference_decisions"
    )
    scen_p = (
        Path(scenarios_path)
        if scenarios_path
        else repo_root / "benchmarks" / "open_architecture" / "batch_01" / "scenarios" / "scenarios.jsonl"
    )

    if output_dir is not None:
        out_path = Path(output_dir)
        if out_path.exists() and any(out_path.iterdir()):
            raise ValueError(f"Output directory '{out_path}' exists and is non-empty")
        out_path.mkdir(parents=True, exist_ok=True)

    # 1. Authoritative preflight verification
    preflight_batch_01(
        baseline_path=baseline_p,
        manifest_path=manifest_p,
        reference_corpus_dir=ref_dir,
        scenarios_path=scen_p,
    )

    manifest = Manifest.load(manifest_p)
    all_refs = load_reference_corpus(ref_dir)
    all_scenarios = import_scenarios_jsonl(scen_p)

    # 2. Load accepted Stage B replay outcomes (or use supplied validated list)
    if stage_b_outcomes is None:
        stage_b_outcomes = load_accepted_stage_b_replay_outcomes(repo_root)
    else:
        computed_hash = compute_stage_b_semantic_content_hash(stage_b_outcomes)
        if computed_hash != ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH:
            raise ValueError(
                f"Supplied Stage B outcomes semantic hash mismatch: "
                f"expected {ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH!r}, got {computed_hash!r}"
            )

    mixed_semantic_hash = compute_stage_b_semantic_content_hash(stage_b_outcomes)
    profile_hash = compute_end_to_end_profile_hash(
        stage_b_mixed_semantic_hash=mixed_semantic_hash
    )

    # 3. Evaluate isolated human reference baseline
    human_candidates = [r.to_decision_candidate() for r in all_refs]
    human_baseline, _ = _evaluate_candidate_corpus(manifest, human_candidates, all_scenarios)

    # 4. Compose end-to-end candidates and evaluate
    e2e_candidates = compose_classified_candidates(all_refs, stage_b_outcomes)
    e2e_predictions, e2e_scen_evals = _evaluate_candidate_corpus(
        manifest, e2e_candidates, all_scenarios
    )

    # 5. Compute deltas between human baseline and end-to-end predictions
    profile_comparisons: dict[str, ProfileComparisonDelta] = {}
    for prof in EVALUATED_PROFILES:
        h = human_baseline[prof]
        e = e2e_predictions[prof]
        profile_comparisons[prof] = ProfileComparisonDelta(
            profile=prof,
            human_macro_precision=h.macro_precision,
            end_to_end_macro_precision=e.macro_precision,
            delta_macro_precision=e.macro_precision - h.macro_precision,
            human_macro_recall=h.macro_recall,
            end_to_end_macro_recall=e.macro_recall,
            delta_macro_recall=e.macro_recall - h.macro_recall,
            human_macro_f1=h.macro_f1,
            end_to_end_macro_f1=e.macro_f1,
            delta_macro_f1=e.macro_f1 - h.macro_f1,
            human_false_positives=h.total_false_positives,
            end_to_end_false_positives=e.total_false_positives,
            delta_false_positives=e.total_false_positives - h.total_false_positives,
            human_false_negatives=h.total_false_negatives,
            end_to_end_false_negatives=e.total_false_negatives,
            delta_false_negatives=e.total_false_negatives - h.total_false_negatives,
            human_exact_set_matches=h.exact_set_matches,
            end_to_end_exact_set_matches=e.exact_set_matches,
            delta_exact_set_matches=e.exact_set_matches - h.exact_set_matches,
        )

    result = StageCEndToEndExperimentResult(
        experiment_id=EXPERIMENT_ID,
        baseline_id=FROZEN_BASELINE_ID,
        parent_main_sha=FROZEN_PARENT_MAIN_SHA,
        reference_corpus_hash=FROZEN_REFERENCE_CORPUS_HASH,
        scenario_corpus_hash=FROZEN_SCENARIO_CORPUS_HASH,
        manifest_config_hash=FROZEN_MANIFEST_CONFIG_HASH,
        baseline_config_hash=FROZEN_BASELINE_CONFIG_HASH,
        stage_b_mixed_semantic_hash=mixed_semantic_hash,
        experiment_profile_hash=profile_hash,
        isolated_human_baseline=human_baseline,
        end_to_end_predictions=e2e_predictions,
        profile_comparisons=profile_comparisons,
        end_to_end_scenario_evaluations=e2e_scen_evals,
    )

    # 6. Persist artifact if output_dir specified
    if output_dir is not None:
        summary_path = Path(output_dir) / "stage_c_end_to_end_summary.json"
        summary_path.write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return result


__all__ = [
    "EXPERIMENT_ID",
    "FROZEN_PARENT_MAIN_SHA",
    "ACCEPTED_STAGE_B_MIXED_SEMANTIC_HASH",
    "load_accepted_stage_b_replay_outcomes",
    "compose_classified_candidate",
    "compose_classified_candidates",
    "ProfileComparisonDelta",
    "StageCEndToEndExperimentResult",
    "compute_end_to_end_profile_hash",
    "execute_stage_c_end_to_end_experiment",
]
