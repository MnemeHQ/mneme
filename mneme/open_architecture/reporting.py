"""
mneme.open_architecture.reporting — Baseline research reporting.

Generates machine-readable (JSON) and human-readable (Markdown) reports
from OpenArchitectureRunResult.

Reporting Rules:
- No single overall O1A score: reports separate precision, recall, and Governing Decision Set F1.
- Complete transparency: report fully interpreted, incomplete, and extracted counts.
- Deterministic output: no marketing language, speculation, or subjective conclusions.
"""

from __future__ import annotations

import json
from typing import Any

from mneme.open_architecture.orchestrator import OpenArchitectureRunResult


def generate_report(result: OpenArchitectureRunResult) -> dict[str, Any]:
    """Generate structured machine-readable report dictionary."""
    meta = result.run_metadata
    config = result.repository_config

    scenario_summaries = []
    for gds in sorted(result.gds_results, key=lambda g: g.scenario_id):
        scenario_summaries.append(
            {
                "scenario_id": gds.scenario_id,
                "expected_count": gds.expected_count,
                "predicted_count": gds.predicted_count,
                "overlap_count": gds.overlap_count,
                "precision": gds.precision,
                "recall": gds.recall,
                "f1": gds.f1,
                "expected_ids": list(gds.expected_governing_decision_ids),
                "predicted_ids": list(gds.predicted_governing_decision_ids),
            }
        )

    # Incomplete candidate breakdowns
    incomplete_summaries = [inc.to_dict() for inc in result.incomplete_candidates]

    return {
        "report_schema": "o1a.report/v1",
        "provenance": {
            "run_id": meta.run_id,
            "status": meta.status,
            "repository": config.github,
            "commit_sha": config.commit_sha,
            "mneme_version": meta.mneme_version,
            "mneme_commit_sha": meta.mneme_commit_sha,
            "taxonomy_version": meta.taxonomy_version,
            "classifier_version": meta.classifier_version,
            "benchmark_schema_version": meta.benchmark_schema_version,
            "configuration_hash": meta.configuration_hash,
            "started_at": meta.started_at,
            "completed_at": meta.completed_at,
        },
        "inventory": {
            "discovered_documents": len(result.discovered_documents),
            "extracted_candidates": len(result.extracted_candidates),
            "composed_candidates": len(result.composed_candidates),
            "incomplete_candidates": len(result.incomplete_candidates),
            "scenarios_evaluated": len(result.gds_results),
            "classifier_executions": len(result.classifier_results),
        },
        "metrics": {
            "headline_metric": "governing_decision_set_f1",
            "macro_precision": result.suite_metrics.get("macro_precision", 0.0),
            "macro_recall": result.suite_metrics.get("macro_recall", 0.0),
            "macro_f1": result.suite_metrics.get("macro_f1", 0.0),
        },
        "scenarios": scenario_summaries,
        "incomplete_candidates": incomplete_summaries,
    }


def render_markdown_report(result: OpenArchitectureRunResult) -> str:
    """Render human-readable Markdown baseline report."""
    report = generate_report(result)
    p = report["provenance"]
    inv = report["inventory"]
    m = report["metrics"]

    lines: list[str] = []
    lines.append(f"# O1A Analysis Report: {p['repository']}")
    lines.append("")
    lines.append("## Provenance")
    lines.append(f"- **Repository:** `{p['repository']}` (`{p['commit_sha']}`)")
    lines.append(f"- **Mneme:** `{p['mneme_version']}` (`{p['mneme_commit_sha']}`)")
    lines.append(f"- **Configuration Hash:** `{p['configuration_hash']}`")
    lines.append(f"- **Taxonomy Version:** `{p['taxonomy_version']}`")
    lines.append(f"- **Classifier Version:** `{p['classifier_version']}`")
    lines.append(f"- **Run Status:** `{p['status']}`")
    lines.append("")
    lines.append("## Evidence Inventory")
    lines.append(f"- **Discovered Documents:** {inv['discovered_documents']}")
    lines.append(f"- **Extracted Candidates:** {inv['extracted_candidates']}")
    lines.append(f"- **Composed Decision Candidates:** {inv['composed_candidates']}")
    lines.append(f"- **Incomplete Candidates:** {inv['incomplete_candidates']}")
    lines.append(f"- **Scenarios Evaluated:** {inv['scenarios_evaluated']}")
    lines.append(f"- **Classifier Executions:** {inv['classifier_executions']}")
    lines.append("")
    lines.append("## Headline Metrics: Governing Decision Set (GDS)")
    lines.append(f"- **Macro Precision:** {m['macro_precision']:.4f}")
    lines.append(f"- **Macro Recall:** {m['macro_recall']:.4f}")
    lines.append(f"- **Macro F1 (Headline):** {m['macro_f1']:.4f}")
    lines.append("")
    lines.append("> Note: O1A reports separate component metrics. No single aggregate score is computed.")
    lines.append("")

    if report["scenarios"]:
        lines.append("## Scenario Evaluations")
        lines.append("| Scenario ID | Expected | Predicted | Overlap | Precision | Recall | F1 |")
        lines.append("|-------------|----------|-----------|---------|-----------|--------|----|")
        for sc in report["scenarios"]:
            lines.append(
                f"| `{sc['scenario_id']}` | {sc['expected_count']} | {sc['predicted_count']} | "
                f"{sc['overlap_count']} | {sc['precision']:.2f} | {sc['recall']:.2f} | {sc['f1']:.2f} |"
            )
        lines.append("")

    if report["incomplete_candidates"]:
        lines.append("## Incomplete Candidate Diagnostics")
        for inc in report["incomplete_candidates"]:
            lines.append(f"### `{inc['candidate_id']}` ({inc['source_path']})")
            lines.append(f"- **Missing / Failed Dimensions:** {', '.join(inc['missing_or_failed_dimensions'])}")
            for dim, err in inc["errors"].items():
                lines.append(f"  - `{dim}`: {err}")
        lines.append("")

    return "\n".join(lines)


__all__ = [
    "generate_report",
    "render_markdown_report",
]
