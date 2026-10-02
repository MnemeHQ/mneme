"""
mneme.open_architecture.gds_calibration_experiment — O1A Stage C GDS Calibration Experiment.

Implements the research-only Governing Decision Set (GDS) calibration evaluation
over the frozen Batch 01 reference decision corpus and applicability scenarios.

Evaluates exactly three profiles:
1. B0: Canonical query rendering with frozen baseline 'score_gt_zero' selection.
2. C-T1A: Canonical query rendering with calibrated 'relative_80' selection.
3. B3: Query noise treatment (structural label suppression + 5 frozen function
   words suppressed) with calibrated 'relative_80' selection.

Architecture and Boundary Invariants:
- Research-only sidecar: does NOT modify or parameterize canonical DecisionRetriever,
  ConflictDetector, Enforcer, projection.py, gds_evaluation.py, or harness.py.
- Consumes the exact scores produced by the existing frozen DecisionRetriever unchanged.
- Preserves the frozen 100 reference decisions, 50 scenarios, and manifest identities.
- Preserves incoming DecisionRetriever order strictly (no re-sorting, no secondary keys,
  no decision.id tie-breaking, no deduplication).
- Zero model/API calls.
- Zero canonical authority writes (no MemoryStore, DecisionProposal, DecisionIndex mutations).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mneme.decision_retriever import DecisionRetriever, ScoredDecision
from mneme.open_architecture.baseline import (
    BaselineConfig,
    validate_baseline_freeze,
)
from mneme.open_architecture.export import compute_reference_corpus_content_hash
from mneme.open_architecture.gds_evaluation import render_scenario_query
from mneme.open_architecture.harness import (
    FrozenReferenceDecision,
    import_scenarios_jsonl,
    load_reference_corpus,
)
from mneme.open_architecture.manifest import Manifest, RepositoryConfig
from mneme.open_architecture.metrics import GoverningDecisionSetMetrics, compute_suite_metrics
from mneme.open_architecture.orchestrator import _compute_scenario_content_hash
from mneme.open_architecture.projection import project_candidates_to_decisions
from mneme.open_architecture.schemas import ApplicabilityScenario

EXPERIMENT_ID: str = "o1a-c-gds-calibration"
FROZEN_BASELINE_ID: str = "o1a-batch-01-baseline"
FROZEN_PARENT_MAIN_SHA: str = "134fbae5675697396ac50beb3728d66d1f1c463f"
FROZEN_REFERENCE_CORPUS_HASH: str = "0455bd66aae52551c35b37a63c2d185f"
FROZEN_SCENARIO_CORPUS_HASH: str = "2ff8751955fd64a33316aca6692dc803"
FROZEN_MANIFEST_CONFIG_HASH: str = "4af7e5794011b43d39682cdfeac9f54e"
FROZEN_BASELINE_CONFIG_HASH: str = "31e18dc1e2bd9ad30bec86dce1a9295a"

# Frozen selection policies and constants
POLICY_SCORE_GT_ZERO: str = "score_gt_zero"
POLICY_RELATIVE_80: str = "relative_80"
EVALUATED_POLICIES: tuple[str, ...] = (
    POLICY_SCORE_GT_ZERO,
    POLICY_RELATIVE_80,
)

RELATIVE_THRESHOLD_RATIO: float = 0.80
SELECTION_EPSILON: float = 1e-9

# Evaluated profiles
PROFILE_B0: str = "B0"
PROFILE_C_T1A: str = "C-T1A"
PROFILE_B3: str = "B3"
EVALUATED_PROFILES: tuple[str, ...] = (
    PROFILE_B0,
    PROFILE_C_T1A,
    PROFILE_B3,
)

# Registered structural prefixes stripped in B3 query treatment
FROZEN_STRUCTURAL_PREFIXES: tuple[str, ...] = (
    "path: ",
    "component: ",
    "change_type: ",
    "dependencies: ",
    "api: ",
    "technology: ",
)

# Frozen high-frequency English function words suppressed in B3 query treatment
FROZEN_FUNCTION_WORDS: frozenset[str] = frozenset({
    "from",
    "that",
    "when",
    "with",
    "without",
})

# Frozen approved Batch 01 repositories and commit SHAs
FROZEN_REPOSITORY_SHAS: dict[str, str] = {
    "adrkit": "471457da29638ecca6119b35180c2845bf989cac",
    "gsa_agentic_coding_quickstart": "8e6160c63acc35bd48d0a3844e133ea3ad52a464",
    "helix": "37d994370deba2512588b5c4efb7f03483e7308b",
    "archlint": "185837e93565718d8e1ea653236cd70ca0a89e3a",
    "modonome": "7a4d5244dcb6879b6aa646105b39297aa6d0a5a2",
}


# ── Decision Selection Logic ───────────────────────────────────────────────────


def select_decisions_for_policy(
    canonical_scored: list[ScoredDecision],
    policy: str,
) -> tuple[str, ...]:
    """Select governing decision IDs from canonically ordered retrieval results.

    Consumes the ScoredDecision sequence exactly in the order returned by the
    frozen canonical DecisionRetriever.retrieve(). Preserves incoming equal-score
    order without re-sorting, secondary keys, or decision.id tie-breaking.
    Does not deduplicate inside selection.

    Args:
        canonical_scored: Scored decisions in exact order returned by DecisionRetriever.
        policy: One of 'score_gt_zero' or 'relative_80'.

    Returns:
        Tuple of selected decision IDs in canonical retrieval order.
    """
    if not canonical_scored:
        return ()

    top_score = canonical_scored[0].score
    if top_score <= 0:
        return ()

    if policy == POLICY_SCORE_GT_ZERO:
        return tuple(sd.decision.id for sd in canonical_scored if sd.score > 0)

    elif policy == POLICY_RELATIVE_80:
        threshold = top_score * RELATIVE_THRESHOLD_RATIO - SELECTION_EPSILON
        return tuple(
            sd.decision.id
            for sd in canonical_scored
            if sd.score >= threshold and sd.score > 0
        )

    else:
        raise ValueError(f"Unknown selection policy: {policy!r}")


# ── Query Transformation Logic ─────────────────────────────────────────────────


def suppress_structural_labels(query_text: str) -> str:
    """Remove registered structural field prefixes while strictly preserving their values.

    Transforms lines starting with 'path: ', 'component: ', etc. to their value alone.
    Prose description and other lines are preserved verbatim.
    """
    lines: list[str] = []
    for line in query_text.splitlines():
        trimmed = line.strip()
        matched = False
        for pfx in FROZEN_STRUCTURAL_PREFIXES:
            if trimmed.startswith(pfx):
                lines.append(trimmed[len(pfx):].strip())
                matched = True
                break
        if not matched:
            lines.append(line)
    return "\n".join(lines)


def transform_query_for_b3(query_text: str) -> str:
    """Transform canonical scenario query for the B3 research treatment.

    Strips registered structural prefixes while preserving their values,
    and suppresses the five frozen high-frequency function words:
    'from', 'that', 'when', 'with', 'without'.
    """
    cleaned = suppress_structural_labels(query_text)
    pattern = r"\b(from|that|when|with|without)\b"
    return re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)


# ── Data Models ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ScenarioCalibrationResult:
    scenario_id: str
    repository: str
    expected_governing_decision_ids: tuple[str, ...]
    profile: str
    selected_decision_ids: tuple[str, ...]
    retrieved_ids: tuple[str, ...]
    retrieval_scores: tuple[float, ...]
    precision: float
    recall: float
    f1: float
    exact_set_match: bool
    false_positive_ids: tuple[str, ...]
    false_negative_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "repository": self.repository,
            "expected_governing_decision_ids": list(self.expected_governing_decision_ids),
            "profile": self.profile,
            "selected_decision_ids": list(self.selected_decision_ids),
            "retrieved_ids": list(self.retrieved_ids),
            "retrieval_scores": list(self.retrieval_scores),
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "exact_set_match": self.exact_set_match,
            "false_positive_ids": list(self.false_positive_ids),
            "false_negative_ids": list(self.false_negative_ids),
        }


@dataclass(frozen=True)
class RepoCalibrationSummary:
    repo_id: str
    repository_identifier: str
    macro_precision: float
    macro_recall: float
    macro_f1: float
    exact_set_matches: int
    total_scenarios: int
    total_false_positives: int
    total_false_negatives: int
    mean_predicted_set_size: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_id": self.repo_id,
            "repository_identifier": self.repository_identifier,
            "macro_precision": self.macro_precision,
            "macro_recall": self.macro_recall,
            "macro_f1": self.macro_f1,
            "exact_set_matches": self.exact_set_matches,
            "total_scenarios": self.total_scenarios,
            "total_false_positives": self.total_false_positives,
            "total_false_negatives": self.total_false_negatives,
            "mean_predicted_set_size": self.mean_predicted_set_size,
        }


@dataclass(frozen=True)
class ProfileAggregateMetrics:
    profile: str
    selection_policy: str
    query_treatment: str
    macro_precision: float
    macro_recall: float
    macro_f1: float
    exact_set_matches: int
    total_scenarios: int
    total_false_positives: int
    total_false_negatives: int
    total_expected_decisions: int
    total_predicted_decisions: int
    mean_predicted_set_size: float
    per_repository: dict[str, RepoCalibrationSummary]

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "selection_policy": self.selection_policy,
            "query_treatment": self.query_treatment,
            "macro_precision": self.macro_precision,
            "macro_recall": self.macro_recall,
            "macro_f1": self.macro_f1,
            "exact_set_matches": self.exact_set_matches,
            "total_scenarios": self.total_scenarios,
            "total_false_positives": self.total_false_positives,
            "total_false_negatives": self.total_false_negatives,
            "total_expected_decisions": self.total_expected_decisions,
            "total_predicted_decisions": self.total_predicted_decisions,
            "mean_predicted_set_size": self.mean_predicted_set_size,
            "per_repository": {
                r: s.to_dict() for r, s in sorted(self.per_repository.items())
            },
        }


@dataclass(frozen=True)
class GDSCalibrationExperimentResult:
    experiment_id: str
    baseline_id: str
    parent_main_sha: str
    reference_corpus_hash: str
    scenario_corpus_hash: str
    manifest_config_hash: str
    baseline_config_hash: str
    experiment_profile_hash: str
    profiles: dict[str, ProfileAggregateMetrics]
    scenario_evaluations: list[ScenarioCalibrationResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "baseline_id": self.baseline_id,
            "parent_main_sha": self.parent_main_sha,
            "reference_corpus_hash": self.reference_corpus_hash,
            "scenario_corpus_hash": self.scenario_corpus_hash,
            "manifest_config_hash": self.manifest_config_hash,
            "baseline_config_hash": self.baseline_config_hash,
            "experiment_profile_hash": self.experiment_profile_hash,
            "profiles": {
                p: s.to_dict() for p, s in sorted(self.profiles.items())
            },
        }


# ── Profile Hash Computation ───────────────────────────────────────────────────


def compute_experiment_profile_hash(
    *,
    experiment_id: str = EXPERIMENT_ID,
    baseline_id: str = FROZEN_BASELINE_ID,
    parent_main_sha: str = FROZEN_PARENT_MAIN_SHA,
    reference_corpus_hash: str = FROZEN_REFERENCE_CORPUS_HASH,
    scenario_corpus_hash: str = FROZEN_SCENARIO_CORPUS_HASH,
    manifest_config_hash: str = FROZEN_MANIFEST_CONFIG_HASH,
    baseline_config_hash: str = FROZEN_BASELINE_CONFIG_HASH,
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
        "structural_prefixes": list(structural_prefixes),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


# ── Execution Logic ────────────────────────────────────────────────────────────


def _evaluate_scenario_for_profile(
    retriever: DecisionRetriever,
    scenario: ApplicabilityScenario,
    profile: str,
) -> ScenarioCalibrationResult:
    """Evaluate a single scenario under a specified calibration profile."""
    canonical_query = render_scenario_query(scenario)

    if profile == PROFILE_B0:
        query_used = canonical_query
        policy = POLICY_SCORE_GT_ZERO
    elif profile == PROFILE_C_T1A:
        query_used = canonical_query
        policy = POLICY_RELATIVE_80
    elif profile == PROFILE_B3:
        query_used = transform_query_for_b3(canonical_query)
        policy = POLICY_RELATIVE_80
    else:
        raise ValueError(f"Unknown profile: {profile!r}")

    scored = retriever.retrieve(query_used)
    selected = select_decisions_for_policy(scored, policy)

    expected = scenario.expected_governing_decision_ids
    expected_set = set(expected)
    selected_set = set(selected)

    metrics = GoverningDecisionSetMetrics.compute(expected, selected)
    exact_match = (selected_set == expected_set)
    fps = tuple(d for d in selected if d not in expected_set)
    fns = tuple(d for d in expected if d not in selected_set)

    retrieved_ids = tuple(s.decision.id for s in scored)
    retrieval_scores = tuple(s.score for s in scored)

    return ScenarioCalibrationResult(
        scenario_id=scenario.scenario_id,
        repository=scenario.repository,
        expected_governing_decision_ids=expected,
        profile=profile,
        selected_decision_ids=selected,
        retrieved_ids=retrieved_ids,
        retrieval_scores=retrieval_scores,
        precision=metrics.precision,
        recall=metrics.recall,
        f1=metrics.f1,
        exact_set_match=exact_match,
        false_positive_ids=fps,
        false_negative_ids=fns,
    )


def execute_gds_calibration_experiment(
    *,
    manifest_path: str | Path | None = None,
    baseline_path: str | Path | None = None,
    reference_corpus_dir: str | Path | None = None,
    scenarios_path: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> GDSCalibrationExperimentResult:
    """Execute O1A Stage C GDS Calibration Experiment.

    Evaluates the three frozen profiles (B0, C-T1A, B3) over the Batch 01 corpus.
    Fails closed if inputs, baseline, or hashes differ from pinned identities.
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

    # 1. Validate baseline freeze and manifest
    baseline_cfg = BaselineConfig.load(baseline_p)
    manifest = Manifest.load(manifest_p)
    validate_baseline_freeze(baseline_cfg, manifest)

    if baseline_cfg.baseline_id != FROZEN_BASELINE_ID:
        raise ValueError(
            f"Baseline ID mismatch: got '{baseline_cfg.baseline_id}', expected '{FROZEN_BASELINE_ID}'"
        )

    # 2. Validate reference and scenario corpus hashes fail-closed
    ref_hash = compute_reference_corpus_content_hash(ref_dir)
    if ref_hash != FROZEN_REFERENCE_CORPUS_HASH:
        raise ValueError(
            f"Reference corpus hash mismatch: got '{ref_hash}', expected '{FROZEN_REFERENCE_CORPUS_HASH}'"
        )

    all_refs = load_reference_corpus(ref_dir)
    all_scenarios = import_scenarios_jsonl(scen_p)

    scen_hash = _compute_scenario_content_hash(all_scenarios)
    if scen_hash != FROZEN_SCENARIO_CORPUS_HASH:
        raise ValueError(
            f"Scenario corpus hash mismatch: got '{scen_hash}', expected '{FROZEN_SCENARIO_CORPUS_HASH}'"
        )

    profile_hash = compute_experiment_profile_hash()

    # 3. Evaluate each repository across the 50 scenarios for each profile
    scenario_evaluations: list[ScenarioCalibrationResult] = []
    profile_results: dict[str, list[ScenarioCalibrationResult]] = {
        p: [] for p in EVALUATED_PROFILES
    }
    repo_profile_results: dict[str, dict[str, list[ScenarioCalibrationResult]]] = {
        repo.id: {p: [] for p in EVALUATED_PROFILES} for repo in manifest.repositories
    }

    for repo_cfg in manifest.repositories:
        expected_sha = FROZEN_REPOSITORY_SHAS.get(repo_cfg.id)
        if expected_sha is None or repo_cfg.commit_sha != expected_sha:
            raise ValueError(
                f"Repository '{repo_cfg.id}' SHA {repo_cfg.commit_sha} does not match expected {expected_sha}"
            )

        repo_refs = [r for r in all_refs if r.repository == repo_cfg.github]
        if len(repo_refs) != 20:
            raise ValueError(f"Expected 20 references for '{repo_cfg.id}', got {len(repo_refs)}")

        repo_scenarios = [s for s in all_scenarios if s.repository == repo_cfg.github]
        if len(repo_scenarios) != 10:
            raise ValueError(f"Expected 10 scenarios for '{repo_cfg.id}', got {len(repo_scenarios)}")

        candidates = [r.to_decision_candidate() for r in repo_refs]
        projected = project_candidates_to_decisions(candidates)
        retriever = DecisionRetriever(projected)

        for scn in repo_scenarios:
            for prof in EVALUATED_PROFILES:
                res = _evaluate_scenario_for_profile(retriever, scn, prof)
                scenario_evaluations.append(res)
                profile_results[prof].append(res)
                repo_profile_results[repo_cfg.id][prof].append(res)

    # 4. Compute aggregate metrics per profile and per repository
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

    experiment_result = GDSCalibrationExperimentResult(
        experiment_id=EXPERIMENT_ID,
        baseline_id=FROZEN_BASELINE_ID,
        parent_main_sha=FROZEN_PARENT_MAIN_SHA,
        reference_corpus_hash=FROZEN_REFERENCE_CORPUS_HASH,
        scenario_corpus_hash=FROZEN_SCENARIO_CORPUS_HASH,
        manifest_config_hash=FROZEN_MANIFEST_CONFIG_HASH,
        baseline_config_hash=FROZEN_BASELINE_CONFIG_HASH,
        experiment_profile_hash=profile_hash,
        profiles=profile_summaries,
        scenario_evaluations=scenario_evaluations,
    )

    # 5. Persist artifact if output_dir specified
    if output_dir is not None:
        summary_path = Path(output_dir) / "gds_calibration_summary.json"
        summary_path.write_text(
            json.dumps(experiment_result.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return experiment_result
