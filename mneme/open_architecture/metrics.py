"""
Governing Decision Set Metrics for O1A Open Architecture Benchmark.

Implements precision, recall, F1 for expected set E and predicted set P.
Edge-case semantics are explicitly pinned with tests.

No single overall O1A score is computed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class GoverningDecisionSetMetrics:
    """Metrics for one scenario's governing decision set comparison.

    Expected set E = benchmark reference labels (ground truth)
    Predicted set P = Mneme's predicted governing decision IDs
    """

    expected_count: int
    predicted_count: int
    overlap_count: int
    precision: float
    recall: float
    f1: float

    @classmethod
    def compute(cls, expected: Iterable[str], predicted: Iterable[str]) -> GoverningDecisionSetMetrics:
        """Compute metrics from expected and predicted decision ID sets.

        Edge cases:
        - Both empty: precision=1.0, recall=1.0, f1=1.0 (vacuous truth)
        - Expected empty, predicted non-empty: precision=0.0, recall=1.0, f1=0.0
        - Expected non-empty, predicted empty: precision=1.0, recall=0.0, f1=0.0
        - Perfect match: precision=1.0, recall=1.0, f1=1.0
        - Partial overlap: standard formulas
        - False positives only: precision=0.0, recall=1.0, f1=0.0
        """
        expected_set = set(expected)
        predicted_set = set(predicted)

        expected_count = len(expected_set)
        predicted_count = len(predicted_set)
        overlap = expected_set & predicted_set
        overlap_count = len(overlap)

        # Precision: |E ∩ P| / |P|
        if predicted_count == 0:
            precision = 1.0  # Vacuous: nothing predicted, nothing wrong
        else:
            precision = overlap_count / predicted_count

        # Recall: |E ∩ P| / |E|
        if expected_count == 0:
            recall = 1.0  # Vacuous: nothing expected, nothing missed
        else:
            recall = overlap_count / expected_count

        # F1: harmonic mean
        if precision + recall == 0:
            f1 = 0.0
        else:
            f1 = 2 * precision * recall / (precision + recall)

        return cls(
            expected_count=expected_count,
            predicted_count=predicted_count,
            overlap_count=overlap_count,
            precision=precision,
            recall=recall,
            f1=f1,
        )

    def to_dict(self) -> dict[str, float | int]:
        return {
            "expected_count": self.expected_count,
            "predicted_count": self.predicted_count,
            "overlap_count": self.overlap_count,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
        }


def compute_suite_metrics(
    scenario_metrics: list[GoverningDecisionSetMetrics],
) -> dict[str, float]:
    """Compute aggregate metrics across scenarios.

    Returns macro-averaged precision, recall, F1.
    No single overall O1A score - returns component metrics only.
    """
    if not scenario_metrics:
        return {"macro_precision": 0.0, "macro_recall": 0.0, "macro_f1": 0.0}

    n = len(scenario_metrics)
    macro_precision = sum(m.precision for m in scenario_metrics) / n
    macro_recall = sum(m.recall for m in scenario_metrics) / n
    macro_f1 = sum(m.f1 for m in scenario_metrics) / n

    return {
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "macro_f1": macro_f1,
    }