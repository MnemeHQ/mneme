"""
mneme.open_architecture.gds_evaluation — Governing Decision Set evaluation for O1A.

Renders deterministic scenario queries, runs the existing frozen DecisionRetriever,
and computes Governing Decision Set metrics using the existing metrics implementation.

This module does NOT:
- Modify DecisionRetriever behavior (weights, tokenization, fallback, sorting)
- Invoke ConflictDetector, Enforcer, Audit, or any enforcement surface
- Persist results (no ResearchStore writes)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from mneme.decision_retriever import DecisionRetriever, ScoredDecision
from mneme.open_architecture.metrics import GoverningDecisionSetMetrics, compute_suite_metrics
from mneme.open_architecture.schemas import ApplicabilityScenario
from mneme.open_architecture.projection import project_candidates_to_decisions
from mneme.schemas import Decision


# ── Scenario Query Renderer ────────────────────────────────────────────────────


def render_scenario_query(scenario: ApplicabilityScenario) -> str:
    """Render a deterministic query string from an ApplicabilityScenario.

    Includes available scenario evidence in a fixed documented order:
    1. description
    2. path
    3. component
    4. change type
    5. dependencies
    6. API context
    7. technology context
    8. other/free-form context

    Requirements:
    - Deterministic: same scenario -> byte-identical query
    - No LLM, no semantic rewriting, no synonym expansion
    - No hidden extra context
    - Null optional fields handled deterministically
    - Dependencies serialized in deterministic order
    """
    parts: list[str] = []

    # 1. description (always present per schema validation)
    if scenario.description:
        parts.append(scenario.description.strip())

    ctx = scenario.change_context

    # 2. path
    if ctx.path:
        parts.append(f"path: {ctx.path.strip()}")

    # 3. component
    if ctx.component:
        parts.append(f"component: {ctx.component.strip()}")

    # 4. change type
    if ctx.change_type:
        parts.append(f"change_type: {ctx.change_type.strip()}")

    # 5. dependencies (deterministic ordering)
    if ctx.dependencies:
        deps = sorted(set(str(d) for d in ctx.dependencies if d))
        if deps:
            parts.append("dependencies: " + ", ".join(deps))

    # 6. API context
    if ctx.api:
        parts.append(f"api: {ctx.api.strip()}")

    # 7. technology context
    if ctx.technology:
        parts.append(f"technology: {ctx.technology.strip()}")

    # 8. other/free-form context
    if ctx.other_context:
        parts.append(ctx.other_context.strip())

    # Join with newline separator for clear separation
    return "\n".join(parts)


# ── GDS Evaluation Result Model ────────────────────────────────────────────────


@dataclass(frozen=True)
class GoverningDecisionSetResult:
    """Immutable result of a single scenario's GDS evaluation.

    JSON-compatible and deterministically serializable.
    """
    scenario_id: str
    query: str
    retrieved_ids: tuple[str, ...]          # All retrieved decision IDs (score > 0), in rank order
    retrieval_scores: tuple[float, ...]      # Corresponding scores
    predicted_governing_decision_ids: tuple[str, ...]  # Predicted governing set (score > 0)
    expected_governing_decision_ids: tuple[str, ...]  # Human reference labels
    precision: float
    recall: float
    f1: float
    expected_count: int
    predicted_count: int
    overlap_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "query": self.query,
            "retrieved_ids": list(self.retrieved_ids),
            "retrieval_scores": list(self.retrieval_scores),
            "predicted_governing_decision_ids": list(self.predicted_governing_decision_ids),
            "expected_governing_decision_ids": list(self.expected_governing_decision_ids),
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "expected_count": self.expected_count,
            "predicted_count": self.predicted_count,
            "overlap_count": self.overlap_count,
        }


# ── Single Scenario Evaluation ─────────────────────────────────────────────────


def evaluate_governing_decisions(
    candidates: list[Any],
    scenario: ApplicabilityScenario,
) -> GoverningDecisionSetResult:
    """Evaluate Governing Decision Set for a single scenario.

    Uses the existing frozen DecisionRetriever unchanged.
    Predicted governing set = all retrieved decisions with score > 0.
    No hidden top-K truncation.

    Args:
        candidates: List of DecisionCandidate objects (or compatible objects
                    with the required fields for projection)
        scenario: ApplicabilityScenario with expected governing decision IDs

    Returns:
        GoverningDecisionSetResult with metrics and full traceability.

    Raises:
        ValueError: If duplicate candidate IDs exist in projection input.
    """
    # Project candidates to temporary Decisions (validation happens here)
    projected_decisions = project_candidates_to_decisions(candidates)

    # Render deterministic query from scenario
    query = render_scenario_query(scenario)

    # Use frozen DecisionRetriever
    retriever = DecisionRetriever(projected_decisions)
    scored = retriever.retrieve(query)

    # Predicted governing set = all decisions with score > 0
    # No hidden top-K truncation - all positive scores count
    predicted = tuple(sd.decision.id for sd in scored if sd.score > 0)
    retrieved_ids = tuple(sd.decision.id for sd in scored)
    retrieval_scores = tuple(sd.score for sd in scored)

    # Expected governing decision IDs (immutable reference truth)
    expected = scenario.expected_governing_decision_ids

    # Compute metrics using existing O1A metrics
    metrics = GoverningDecisionSetMetrics.compute(expected, predicted)

    return GoverningDecisionSetResult(
        scenario_id=scenario.scenario_id,
        query=query,
        retrieved_ids=retrieved_ids,
        retrieval_scores=retrieval_scores,
        predicted_governing_decision_ids=predicted,
        expected_governing_decision_ids=expected,
        precision=metrics.precision,
        recall=metrics.recall,
        f1=metrics.f1,
        expected_count=metrics.expected_count,
        predicted_count=metrics.predicted_count,
        overlap_count=metrics.overlap_count,
    )


# ── Batch Evaluation ───────────────────────────────────────────────────────────


def evaluate_governing_decisions_batch(
    candidates: list[Any],
    scenarios: list[ApplicabilityScenario],
) -> tuple[GoverningDecisionSetResult, ...]:
    """Evaluate GDS for multiple scenarios against the same candidate corpus.

    Args:
        candidates: DecisionCandidate corpus
        scenarios: List of ApplicabilityScenario objects

    Returns:
        Tuple of GoverningDecisionSetResult (preserves input order)
    """
    results: list[GoverningDecisionSetResult] = []
    for scenario in scenarios:
        results.append(evaluate_governing_decisions(candidates, scenario))
    return tuple(results)


# ── Suite-Level Aggregation ───────────────────────────────────────────────────


def compute_suite_gds_metrics(
    results: Iterable[GoverningDecisionSetResult],
) -> dict[str, float]:
    """Compute macro-averaged GDS metrics across scenarios.

    Uses existing compute_suite_metrics for consistency.
    """
    # Convert to metric objects for the existing aggregator
    from mneme.open_architecture.metrics import GoverningDecisionSetMetrics

    metrics_list = [
        GoverningDecisionSetMetrics(
            expected_count=r.expected_count,
            predicted_count=r.predicted_count,
            overlap_count=r.overlap_count,
            precision=r.precision,
            recall=r.recall,
            f1=r.f1,
        )
        for r in results
    ]

    return compute_suite_metrics(metrics_list)


__all__ = [
    "render_scenario_query",
    "GoverningDecisionSetResult",
    "evaluate_governing_decisions",
    "evaluate_governing_decisions_batch",
    "compute_suite_gds_metrics",
]