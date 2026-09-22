"""Tests for O1A Governing Decision Set metrics."""

from __future__ import annotations

import pytest

from mneme.open_architecture.metrics import (
    GoverningDecisionSetMetrics,
    compute_suite_metrics,
)


class TestGoverningDecisionSetMetrics:
    def test_both_empty(self):
        """Both expected and predicted empty -> precision=1.0, recall=1.0, f1=1.0"""
        metrics = GoverningDecisionSetMetrics.compute([], [])
        assert metrics.expected_count == 0
        assert metrics.predicted_count == 0
        assert metrics.overlap_count == 0
        assert metrics.precision == 1.0
        assert metrics.recall == 1.0
        assert metrics.f1 == 1.0

    def test_expected_empty_predicted_nonempty(self):
        """Expected empty, predicted non-empty -> precision=0.0, recall=1.0, f1=0.0"""
        metrics = GoverningDecisionSetMetrics.compute([], ["ADR-001", "ADR-002"])
        assert metrics.expected_count == 0
        assert metrics.predicted_count == 2
        assert metrics.overlap_count == 0
        assert metrics.precision == 0.0
        assert metrics.recall == 1.0
        assert metrics.f1 == 0.0

    def test_expected_nonempty_predicted_empty(self):
        """Expected non-empty, predicted empty -> precision=1.0, recall=0.0, f1=0.0"""
        metrics = GoverningDecisionSetMetrics.compute(["ADR-001", "ADR-002"], [])
        assert metrics.expected_count == 2
        assert metrics.predicted_count == 0
        assert metrics.overlap_count == 0
        assert metrics.precision == 1.0
        assert metrics.recall == 0.0
        assert metrics.f1 == 0.0

    def test_perfect_match(self):
        """Perfect match -> precision=1.0, recall=1.0, f1=1.0"""
        metrics = GoverningDecisionSetMetrics.compute(
            ["ADR-001", "ADR-002"], ["ADR-001", "ADR-002"]
        )
        assert metrics.expected_count == 2
        assert metrics.predicted_count == 2
        assert metrics.overlap_count == 2
        assert metrics.precision == 1.0
        assert metrics.recall == 1.0
        assert metrics.f1 == 1.0

    def test_partial_overlap(self):
        """Partial overlap -> standard formulas"""
        metrics = GoverningDecisionSetMetrics.compute(
            ["ADR-001", "ADR-002", "ADR-003"],  # Expected 3
            ["ADR-001", "ADR-002", "ADR-004"]   # Predicted 3, overlap 2
        )
        assert metrics.expected_count == 3
        assert metrics.predicted_count == 3
        assert metrics.overlap_count == 2
        assert metrics.precision == 2/3
        assert metrics.recall == 2/3
        assert metrics.f1 == 2/3

    def test_false_positives_only(self):
        """False positives only -> precision=0.0, recall=0.0, f1=0.0"""
        metrics = GoverningDecisionSetMetrics.compute(
            ["ADR-001"],
            ["ADR-002", "ADR-003"]  # None match
        )
        assert metrics.expected_count == 1
        assert metrics.predicted_count == 2
        assert metrics.overlap_count == 0
        assert metrics.precision == 0.0
        assert metrics.recall == 0.0
        assert metrics.f1 == 0.0

    def test_subset_predicted(self):
        """Predicted is subset of expected"""
        metrics = GoverningDecisionSetMetrics.compute(
            ["ADR-001", "ADR-002", "ADR-003"],
            ["ADR-001", "ADR-002"]
        )
        assert metrics.overlap_count == 2
        assert metrics.precision == 1.0
        assert metrics.recall == 2/3

    def test_superset_predicted(self):
        """Predicted is superset of expected"""
        metrics = GoverningDecisionSetMetrics.compute(
            ["ADR-001", "ADR-002"],
            ["ADR-001", "ADR-002", "ADR-003", "ADR-004"]
        )
        assert metrics.overlap_count == 2
        assert metrics.precision == 0.5
        assert metrics.recall == 1.0

    def test_to_dict(self):
        metrics = GoverningDecisionSetMetrics.compute(
            ["ADR-001", "ADR-002"], ["ADR-001"]
        )
        d = metrics.to_dict()
        assert d["expected_count"] == 2
        assert d["predicted_count"] == 1
        assert d["overlap_count"] == 1
        assert d["precision"] == 1.0
        assert d["recall"] == 0.5
        assert d["f1"] == 2/3


class TestComputeSuiteMetrics:
    def test_empty_suite(self):
        result = compute_suite_metrics([])
        assert result == {"macro_precision": 0.0, "macro_recall": 0.0, "macro_f1": 0.0}

    def test_single_scenario(self):
        m = GoverningDecisionSetMetrics.compute(["ADR-001"], ["ADR-001"])
        result = compute_suite_metrics([m])
        assert result["macro_precision"] == 1.0
        assert result["macro_recall"] == 1.0
        assert result["macro_f1"] == 1.0

    def test_multiple_scenarios(self):
        m1 = GoverningDecisionSetMetrics.compute(["ADR-001"], ["ADR-001"])  # 1,1,1
        m2 = GoverningDecisionSetMetrics.compute([], ["ADR-002"])        # 0,1,0
        m3 = GoverningDecisionSetMetrics.compute(["ADR-003"], [])            # 1,0,0
        result = compute_suite_metrics([m1, m2, m3])
        # Macro averages
        assert result["macro_precision"] == (1.0 + 0.0 + 1.0) / 3
        assert result["macro_recall"] == (1.0 + 1.0 + 0.0) / 3
        assert result["macro_f1"] == (1.0 + 0.0 + 0.0) / 3

    def test_no_overall_score(self):
        """Verify no single overall O1A score is returned."""
        m = GoverningDecisionSetMetrics.compute(["ADR-001"], ["ADR-001"])
        result = compute_suite_metrics([m])
        # Should only have component metrics, no "overall" or "o1a_score"
        assert "overall" not in result
        assert "o1a_score" not in result
        assert set(result.keys()) == {"macro_precision", "macro_recall", "macro_f1"}