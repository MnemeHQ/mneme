"""
benchmark_report.py — Format BenchmarkRunner results for terminal, Markdown, and JSON.

Three formatters:
  format_terminal(results) -> str   Plain-text terminal table (ASCII-only, Windows-safe)
  format_markdown(results) -> str   GitHub-flavoured Markdown table + summary
  format_json(results)     -> str   JSON with summary + per-scenario detail
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from mneme.benchmark import ScenarioResult, ScenarioVerdict


_WIDTH = 72


@dataclass
class BenchmarkSummary:
    """Aggregate statistics across a suite run.

    Layer 2 fields (passed / failed / weak / weak_retrieval / pass_rate)
    reflect enforcement outcomes. Layer 1 fields (mean_recall_at_k,
    mean_precision_at_k, irrelevant_injection_rate, k) reflect retrieval
    quality and are aggregated only over scenarios with a non-empty
    expected_protected_decision_ids — control scenarios contribute no
    recall denominator and would otherwise be vacuous-true.
    """
    total: int
    passed: int
    failed: int
    weak: int
    weak_retrieval: int
    pass_rate: float
    by_category: dict[str, dict[str, int]]
    # Layer 1 aggregates (v1.1 methodology §09).
    mean_recall_at_k: float = 0.0
    mean_precision_at_k: float = 0.0
    irrelevant_injection_rate: float = 0.0
    layer1_scored_count: int = 0
    k: int = 5


def compute_summary(results: list[ScenarioResult]) -> BenchmarkSummary:
    """Compute aggregate statistics from a list of results."""
    passed = sum(1 for r in results if r.verdict == ScenarioVerdict.PASS)
    failed = sum(1 for r in results if r.verdict == ScenarioVerdict.FAIL)
    weak = sum(1 for r in results if r.verdict == ScenarioVerdict.WEAK)
    weak_retrieval = sum(
        1 for r in results if r.verdict == ScenarioVerdict.WEAK_RETRIEVAL
    )
    checkable = passed + failed
    pass_rate = round(passed / checkable, 2) if checkable > 0 else 0.0

    by_category: dict[str, dict[str, int]] = {}
    for r in results:
        cat = r.category
        if cat not in by_category:
            by_category[cat] = {"pass": 0, "fail": 0, "total": 0}
        by_category[cat]["total"] += 1
        if r.verdict == ScenarioVerdict.PASS:
            by_category[cat]["pass"] += 1
        elif r.verdict == ScenarioVerdict.FAIL:
            by_category[cat]["fail"] += 1

    # Layer 1 aggregates: only scenarios that declare expected protected
    # decisions contribute. Vacuous-true (no expected) cases are excluded
    # to keep the means meaningful.
    governed = [r for r in results if r.layer1_expected_ids]
    if governed:
        mean_recall = sum(r.layer1_recall for r in governed) / len(governed)
        mean_precision = sum(r.layer1_precision for r in governed) / len(governed)
        injection_rate = sum(
            1 for r in governed if r.layer1_irrelevant_injection
        ) / len(governed)
    else:
        mean_recall = 0.0
        mean_precision = 0.0
        injection_rate = 0.0

    k_values = {r.layer1_k for r in results if r.layer1_k}
    k = next(iter(k_values)) if len(k_values) == 1 else (max(k_values) if k_values else 5)

    return BenchmarkSummary(
        total=len(results),
        passed=passed,
        failed=failed,
        weak=weak,
        weak_retrieval=weak_retrieval,
        pass_rate=pass_rate,
        by_category=by_category,
        mean_recall_at_k=round(mean_recall, 3),
        mean_precision_at_k=round(mean_precision, 3),
        irrelevant_injection_rate=round(injection_rate, 3),
        layer1_scored_count=len(governed),
        k=k,
    )


# ── Terminal ──────────────────────────────────────────────────────────────

def format_terminal(results: list[ScenarioResult]) -> str:
    """Format results as a readable terminal report."""
    lines: list[str] = []
    lines.append("=" * _WIDTH)
    lines.append("  Mneme Benchmark Report")
    lines.append("=" * _WIDTH)
    lines.append("")

    for r in results:
        lines.append(f"  {r.verdict.value:<5}  {r.name}")
        lines.append(f"         {r.explanation}")
        if r.baseline_triggers:
            lines.append(
                f"         baseline triggered: {', '.join(r.baseline_triggers[:4])}"
            )
        if r.layer1_expected_ids:
            lines.append(
                f"         layer1: recall@{r.layer1_k}={r.layer1_recall:.2f} "
                f"precision@{r.layer1_k}={r.layer1_precision:.2f} "
                f"irrelevant={'yes' if r.layer1_irrelevant_injection else 'no'}"
            )
        lines.append("")

    s = compute_summary(results)
    lines.append("-" * _WIDTH)
    lines.append(
        f"  Layer 2 (enforcement): {s.passed}/{s.passed + s.failed} violations caught"
        + (
            f"  ({s.weak} weak, {s.weak_retrieval} weak-retrieval)"
            if s.weak or s.weak_retrieval
            else ""
        )
    )
    lines.append(f"  Pass rate: {s.pass_rate:.0%}")
    if s.layer1_scored_count:
        lines.append("")
        lines.append(
            f"  Layer 1 (retrieval, n={s.layer1_scored_count}): "
            f"mean recall@{s.k}={s.mean_recall_at_k:.2f}  "
            f"mean precision@{s.k}={s.mean_precision_at_k:.2f}  "
            f"irrelevant injection rate={s.irrelevant_injection_rate:.0%}"
        )
    if s.by_category:
        lines.append("")
        lines.append("  By category:")
        for cat, counts in sorted(s.by_category.items()):
            lines.append(f"    {cat}: {counts['pass']}/{counts['total']} PASS")
    lines.append("=" * _WIDTH)

    return "\n".join(lines)


# ── Markdown ──────────────────────────────────────────────────────────────

def format_markdown(results: list[ScenarioResult]) -> str:
    """Format results as a GitHub-flavoured Markdown report."""
    lines: list[str] = []
    lines.append("## Mneme Benchmark Results")
    lines.append("")
    lines.append(
        "| Scenario | Verdict | Baseline | Enhanced | Recall@K | Precision@K | Irrelevant | Notes |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")

    for r in results:
        triggers = ", ".join(r.baseline_triggers[:3]) or "--"
        if r.layer1_expected_ids:
            recall_cell = f"{r.layer1_recall:.2f}"
            precision_cell = f"{r.layer1_precision:.2f}"
            irrelevant_cell = "yes" if r.layer1_irrelevant_injection else "no"
        else:
            recall_cell = precision_cell = irrelevant_cell = "--"
        lines.append(
            f"| {r.name} | {r.verdict.value} "
            f"| {r.baseline_violation_count} "
            f"| {r.enhanced_violation_count} "
            f"| {recall_cell} "
            f"| {precision_cell} "
            f"| {irrelevant_cell} "
            f"| {triggers} |"
        )

    s = compute_summary(results)
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(
        f"**Layer 2 (enforcement)** — {s.passed}/{s.passed + s.failed} "
        f"violations caught ({s.pass_rate:.0%} pass rate)."
    )
    if s.weak or s.weak_retrieval:
        lines.append("")
        lines.append(
            f"_{s.weak} WEAK (baseline too soft), "
            f"{s.weak_retrieval} WEAK_RETRIEVAL (retrieval missed target)._"
        )
    if s.layer1_scored_count:
        lines.append("")
        lines.append(
            f"**Layer 1 (retrieval, n={s.layer1_scored_count})** — "
            f"mean Recall@{s.k} {s.mean_recall_at_k:.2f}, "
            f"mean Precision@{s.k} {s.mean_precision_at_k:.2f}, "
            f"irrelevant injection rate {s.irrelevant_injection_rate:.0%}."
        )
    if s.by_category:
        lines.append("")
        lines.append("**By category:**")
        lines.append("")
        for cat, counts in sorted(s.by_category.items()):
            lines.append(f"- **{cat}**: {counts['pass']}/{counts['total']} PASS")

    return "\n".join(lines)


# ── JSON ──────────────────────────────────────────────────────────────────

def format_json(results: list[ScenarioResult]) -> str:
    """Format results as a JSON string suitable for CI or dashboards.

    Backwards-compatible: existing top-level scenario keys
    (verdict, baseline_violation_count, enhanced_violation_count, ...) are
    preserved. Layer 1 and Layer 2 are also exposed under namespaced
    `layer1` / `layer2` objects per the v1.1 methodology.
    """
    s = compute_summary(results)
    payload = {
        "summary": {
            "total": s.total,
            "passed": s.passed,
            "failed": s.failed,
            "weak": s.weak,
            "weak_retrieval": s.weak_retrieval,
            "pass_rate": s.pass_rate,
            "by_category": s.by_category,
            "layer1": {
                "k": s.k,
                "mean_recall_at_k": s.mean_recall_at_k,
                "mean_precision_at_k": s.mean_precision_at_k,
                "irrelevant_injection_rate": s.irrelevant_injection_rate,
                "scored_count": s.layer1_scored_count,
            },
            "layer2": {
                "passed": s.passed,
                "failed": s.failed,
                "weak": s.weak,
                "weak_retrieval": s.weak_retrieval,
                "pass_rate": s.pass_rate,
            },
        },
        "results": [
            {
                "name": r.name,
                "verdict": r.verdict.value,
                "baseline_violation_count": r.baseline_violation_count,
                "enhanced_violation_count": r.enhanced_violation_count,
                "baseline_triggers": r.baseline_triggers,
                "enhanced_triggers": r.enhanced_triggers,
                "explanation": r.explanation,
                "layer1": {
                    "k": r.layer1_k,
                    "retrieved_ids": r.layer1_retrieved_ids,
                    "expected_ids": r.layer1_expected_ids,
                    "acceptable_ids": r.layer1_acceptable_ids,
                    "recall_at_k": r.layer1_recall,
                    "precision_at_k": r.layer1_precision,
                    "irrelevant_injection": r.layer1_irrelevant_injection,
                },
                "layer2": {
                    "verdict": r.verdict.value,
                    "baseline_violation_count": r.baseline_violation_count,
                    "enhanced_violation_count": r.enhanced_violation_count,
                    "baseline_triggers": r.baseline_triggers,
                    "enhanced_triggers": r.enhanced_triggers,
                    "protected_decision_ids_hit": r.protected_decision_ids_hit,
                },
            }
            for r in results
        ],
    }
    return json.dumps(payload, indent=2)
