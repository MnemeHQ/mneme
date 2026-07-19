"""Tests for benchmark report output (terminal, Markdown, JSON)."""
import json

from mneme.benchmark import ScenarioResult, ScenarioVerdict
from mneme.benchmark_report import (
    format_terminal,
    format_markdown,
    format_json,
    BenchmarkSummary,
    compute_summary,
)


def _results(verdicts: list[str]) -> list[ScenarioResult]:
    # Alternate categories so by_category tests have something to verify.
    cats = ["architecture", "scope", "anti_pattern"]
    return [
        ScenarioResult(
            name=f"scenario_{i}",
            category=cats[i % len(cats)],
            verdict=ScenarioVerdict(v),
            baseline_violation_count=1 if v not in ("WEAK", "WEAK_RETRIEVAL") else 0,
            enhanced_violation_count=1 if v == "FAIL" else 0,
            explanation=f"Explanation for {v}.",
        )
        for i, v in enumerate(verdicts)
    ]


# ── Summary computation ────────────────────────────────────────────────────

def test_summary_counts_correctly():
    results = _results(["PASS", "PASS", "FAIL", "WEAK"])
    s = compute_summary(results)
    assert isinstance(s, BenchmarkSummary)
    assert s.total == 4
    assert s.passed == 2
    assert s.failed == 1
    assert s.weak == 1


def test_summary_pass_rate():
    results = _results(["PASS", "PASS", "PASS", "FAIL"])
    s = compute_summary(results)
    assert s.pass_rate == 0.75  # 3 of 4


def test_summary_all_pass():
    results = _results(["PASS", "PASS", "PASS"])
    s = compute_summary(results)
    assert s.pass_rate == 1.0


# ── Terminal output ────────────────────────────────────────────────────────

def test_terminal_contains_scenario_names():
    results = _results(["PASS", "FAIL"])
    out = format_terminal(results)
    assert "scenario_0" in out
    assert "scenario_1" in out


def test_terminal_shows_verdict_labels():
    results = _results(["PASS", "FAIL", "WEAK"])
    out = format_terminal(results)
    assert "PASS" in out
    assert "FAIL" in out
    assert "WEAK" in out


def test_terminal_shows_summary_line():
    results = _results(["PASS", "PASS", "FAIL"])
    out = format_terminal(results)
    assert "2/3" in out or "2 / 3" in out


# ── Markdown output ────────────────────────────────────────────────────────

def test_markdown_contains_table():
    results = _results(["PASS", "FAIL"])
    md = format_markdown(results)
    assert "|" in md
    assert "scenario_0" in md


def test_markdown_has_summary_section():
    results = _results(["PASS"])
    md = format_markdown(results)
    assert "## Summary" in md or "**" in md


# ── JSON output ───────────────────────────────────────────────────────────

def test_json_output_is_valid():
    results = _results(["PASS", "FAIL"])
    raw = format_json(results)
    data = json.loads(raw)  # must not raise
    assert "summary" in data
    assert "results" in data


def test_json_contains_all_results():
    results = _results(["PASS", "FAIL", "WEAK"])
    data = json.loads(format_json(results))
    assert len(data["results"]) == 3
    names = {r["name"] for r in data["results"]}
    assert "scenario_0" in names


def test_json_summary_fields():
    results = _results(["PASS", "PASS"])
    data = json.loads(format_json(results))
    s = data["summary"]
    assert s["total"] == 2
    assert s["passed"] == 2
    assert s["pass_rate"] == 1.0
    assert "weak_retrieval" in s
    assert "by_category" in s


# ── Layer 1 aggregation ────────────────────────────────────────────────────

def _result_with_layer1(
    name: str,
    *,
    verdict: str = "PASS",
    expected_ids: list[str] | None = None,
    recall: float = 1.0,
    precision: float = 1.0,
    irrelevant_injection: bool = False,
    k: int = 5,
) -> ScenarioResult:
    return ScenarioResult(
        name=name,
        category="test",
        verdict=ScenarioVerdict(verdict),
        baseline_violation_count=1 if verdict not in ("WEAK", "WEAK_RETRIEVAL") else 0,
        enhanced_violation_count=1 if verdict == "FAIL" else 0,
        explanation=f"Explanation for {name}.",
        layer1_k=k,
        layer1_expected_ids=expected_ids if expected_ids is not None else ["d1"],
        layer1_recall=recall,
        layer1_precision=precision,
        layer1_irrelevant_injection=irrelevant_injection,
    )


def test_summary_layer1_means_across_governed_scenarios():
    """Mean recall/precision/injection rate computed only over governed runs."""
    results = [
        _result_with_layer1("a", recall=1.0, precision=1.0, irrelevant_injection=False),
        _result_with_layer1("b", recall=0.5, precision=0.5, irrelevant_injection=True),
        _result_with_layer1("c", recall=0.0, precision=1.0, irrelevant_injection=False),
    ]
    s = compute_summary(results)
    assert s.layer1_scored_count == 3
    assert s.mean_recall_at_k == round(1.5 / 3, 3)
    assert s.mean_precision_at_k == round(2.5 / 3, 3)
    assert s.irrelevant_injection_rate == round(1 / 3, 3)


def test_summary_layer1_excludes_scenarios_without_expected_ids():
    """Scenarios with empty expected_ids (controls) don't dilute Layer 1 means."""
    results = [
        _result_with_layer1("a", recall=0.5, precision=0.5, irrelevant_injection=True),
        # Control: empty expected_ids → excluded from Layer 1 aggregation.
        _result_with_layer1("ctrl", expected_ids=[]),
    ]
    s = compute_summary(results)
    assert s.layer1_scored_count == 1
    assert s.mean_recall_at_k == 0.5
    assert s.mean_precision_at_k == 0.5
    assert s.irrelevant_injection_rate == 1.0


def test_summary_layer1_zero_when_no_governed_scenarios():
    """No governed scenarios → Layer 1 aggregates are all zero."""
    results = [_result_with_layer1("ctrl", expected_ids=[])]
    s = compute_summary(results)
    assert s.layer1_scored_count == 0
    assert s.mean_recall_at_k == 0.0
    assert s.mean_precision_at_k == 0.0
    assert s.irrelevant_injection_rate == 0.0


def test_summary_k_reflects_runner_top_k():
    """Summary.k is taken from results when uniform."""
    results = [
        _result_with_layer1("a", k=5),
        _result_with_layer1("b", k=5),
    ]
    assert compute_summary(results).k == 5


def test_terminal_includes_layer1_aggregate_line():
    results = [
        _result_with_layer1("a", recall=1.0, precision=0.5, irrelevant_injection=True),
    ]
    out = format_terminal(results)
    assert "Layer 1" in out
    assert "Layer 2" in out
    assert "recall@5" in out


def test_terminal_omits_layer1_per_scenario_for_control():
    """A scenario with no expected_ids should not show a Layer 1 line."""
    results = [_result_with_layer1("ctrl", expected_ids=[])]
    out = format_terminal(results)
    assert "layer1: recall" not in out


def test_markdown_includes_layer1_columns():
    results = [
        _result_with_layer1("a", recall=1.0, precision=0.5, irrelevant_injection=True),
    ]
    md = format_markdown(results)
    assert "Recall@K" in md
    assert "Precision@K" in md
    assert "Irrelevant" in md


def test_markdown_summary_mentions_layer1_aggregates():
    results = [
        _result_with_layer1("a", recall=0.8, precision=0.6, irrelevant_injection=False),
    ]
    md = format_markdown(results)
    assert "Layer 1" in md
    assert "Layer 2" in md


def test_json_per_scenario_namespaces_layer1_and_layer2():
    results = [
        _result_with_layer1(
            "a",
            recall=0.5,
            precision=0.75,
            irrelevant_injection=True,
        ),
    ]
    data = json.loads(format_json(results))
    r = data["results"][0]
    # Existing keys preserved (backward compat).
    assert r["verdict"] == "PASS"
    assert r["baseline_violation_count"] == 1
    # Layer 1 namespaced.
    assert r["layer1"]["recall_at_k"] == 0.5
    assert r["layer1"]["precision_at_k"] == 0.75
    assert r["layer1"]["irrelevant_injection"] is True
    assert r["layer1"]["k"] == 5
    # Layer 2 namespaced (mirror of existing top-level keys).
    assert r["layer2"]["verdict"] == "PASS"


def test_json_summary_namespaces_layer1():
    results = [
        _result_with_layer1("a", recall=1.0, precision=1.0),
        _result_with_layer1("b", recall=0.0, precision=0.0, irrelevant_injection=True),
    ]
    data = json.loads(format_json(results))
    s = data["summary"]
    assert s["layer1"]["k"] == 5
    assert s["layer1"]["mean_recall_at_k"] == 0.5
    assert s["layer1"]["mean_precision_at_k"] == 0.5
    assert s["layer1"]["irrelevant_injection_rate"] == 0.5
    assert s["layer1"]["scored_count"] == 2
    assert s["layer2"]["pass_rate"] == 1.0
