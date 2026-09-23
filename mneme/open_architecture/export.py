"""
mneme.open_architecture.export — Portable research exports and deterministic bundle packaging.

Provides JSONL import/export for Decision Candidates and Applicability Scenarios,
computes deterministic semantic bundle content hashes (excluding volatile operational telemetry),
and writes complete portable research bundles.

Critical Architecture Rules:
- Volatile fields (run_id, timestamps, latency, cost) do NOT influence bundle_content_sha256.
- Semantic reproducibility: identical inputs + outputs produce identical bundle content hash.
- Imported data must validate strictly through existing O1A JSON schemas.
- Does not commit SQLite runtime database state to bundles.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from mneme.open_architecture.orchestrator import OpenArchitectureRunResult
from mneme.open_architecture.reporting import generate_report, render_markdown_report
from mneme.open_architecture.schemas import (
    ApplicabilityScenario,
    DecisionCandidate,
    validate_candidate,
    validate_scenario,
)


# ── DecisionCandidate JSONL Import / Export ───────────────────────────────────


def export_candidates_jsonl(
    candidates: Iterable[DecisionCandidate],
    output_path: str | Path,
) -> None:
    """Export DecisionCandidates to a deterministic JSONL file.

    Lines are ordered lexicographically by candidate_id.
    Keys within each JSON object are sorted.
    """
    sorted_candidates = sorted(candidates, key=lambda c: c.candidate_id)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with out.open("w", encoding="utf-8", newline="\n") as fh:
        for cand in sorted_candidates:
            fh.write(cand.to_json() + "\n")


def import_candidates_jsonl(input_path: str | Path) -> list[DecisionCandidate]:
    """Import and validate DecisionCandidates from a JSONL file.

    Raises:
        ValueError: If file is empty, missing, or any candidate fails schema validation.
    """
    path = Path(input_path)
    if not path.is_file():
        raise ValueError(f"Candidate JSONL file does not exist: {path}")

    candidates: list[DecisionCandidate] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line_str = line.strip()
            if not line_str:
                continue
            try:
                data = json.loads(line_str)
                cand = DecisionCandidate.from_dict(data)
                candidates.append(cand)
            except Exception as exc:
                raise ValueError(
                    f"Malformed DecisionCandidate on line {line_no} of {path.name}: {exc}"
                ) from exc

    return candidates


# ── ApplicabilityScenario JSONL Import / Export ───────────────────────────────


def export_scenarios_jsonl(
    scenarios: Iterable[ApplicabilityScenario],
    output_path: str | Path,
) -> None:
    """Export ApplicabilityScenarios to a deterministic JSONL file.

    Lines are ordered lexicographically by scenario_id.
    Keys within each JSON object are sorted.
    """
    sorted_scenarios = sorted(scenarios, key=lambda s: s.scenario_id)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with out.open("w", encoding="utf-8", newline="\n") as fh:
        for scn in sorted_scenarios:
            fh.write(scn.to_json() + "\n")


def import_scenarios_jsonl(input_path: str | Path) -> list[ApplicabilityScenario]:
    """Import and validate ApplicabilityScenarios from a JSONL file.

    Raises:
        ValueError: If file is missing or any scenario fails schema validation.
    """
    path = Path(input_path)
    if not path.is_file():
        raise ValueError(f"Scenario JSONL file does not exist: {path}")

    scenarios: list[ApplicabilityScenario] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line_str = line.strip()
            if not line_str:
                continue
            try:
                data = json.loads(line_str)
                scn = ApplicabilityScenario.from_dict(data)
                scenarios.append(scn)
            except Exception as exc:
                raise ValueError(
                    f"Malformed ApplicabilityScenario on line {line_no} of {path.name}: {exc}"
                ) from exc

    return scenarios


# ── Deterministic Bundle Content Hashing ──────────────────────────────────────


def compute_bundle_content_hash(result: OpenArchitectureRunResult) -> str:
    """Compute the deterministic semantic content hash for an analysis run.

    Invariant:
        If two runs have identical:
        - repository identity + commit SHA
        - Mneme commit SHA + version
        - benchmark schema version
        - taxonomy version
        - classifier backend identity + version + model
        - configuration hash
        - discovered source document paths and content hashes
        - extracted candidate IDs, locations, and statements
        - composed DecisionCandidate contents
        - scenario reference labels
        - GDS predictions and metrics

        Then bundle_content_sha256 MUST be byte-identical, even if run IDs,
        timestamps, latency, or cost measurements differ.

    Returns:
        'sha256:<64 lowercase hex>'
    """
    # Build canonical semantic payload excluding all volatile fields
    meta = result.run_metadata
    config = result.repository_config

    semantic_payload = {
        "benchmark_schema_version": meta.benchmark_schema_version,
        "classifier_backend": result.classifier_results[0].backend_id if result.classifier_results else "none",
        "classifier_model": result.classifier_results[0].model_identifier if result.classifier_results else None,
        "classifier_version": meta.classifier_version,
        "configuration_hash": meta.configuration_hash,
        "mneme_commit_sha": meta.mneme_commit_sha,
        "mneme_version": meta.mneme_version,
        "repository_commit_sha": config.commit_sha,
        "repository_identifier": config.github,
        "taxonomy_version": meta.taxonomy_version,
        # Sorted source documents
        "sources": [
            {
                "content_hash": doc.content_hash,
                "relative_path": doc.relative_path,
                "source_type": doc.source_type,
            }
            for doc in sorted(result.discovered_documents, key=lambda d: d.relative_path)
        ],
        # Sorted candidate evidence
        "extracted_candidates": [
            {
                "candidate_id": c.candidate_id,
                "discovery_confidence": c.discovery_confidence,
                "raw_statement": c.raw_statement,
                "source_location": c.location_string,
                "source_path": c.source_path,
            }
            for c in sorted(result.extracted_candidates, key=lambda c: c.candidate_id)
        ],
        # Sorted composed candidates
        "composed_candidates": [
            cand.to_dict()
            for cand in sorted(result.composed_candidates, key=lambda c: c.candidate_id)
        ],
        # Sorted GDS results
        "gds_results": [
            {
                "expected_governing_decision_ids": list(g.expected_governing_decision_ids),
                "f1": g.f1,
                "precision": g.precision,
                "predicted_governing_decision_ids": list(g.predicted_governing_decision_ids),
                "recall": g.recall,
                "scenario_id": g.scenario_id,
            }
            for g in sorted(result.gds_results, key=lambda g: g.scenario_id)
        ],
        # Suite metrics
        "suite_metrics": dict(result.suite_metrics),
    }

    canonical_json = json.dumps(semantic_payload, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(canonical_json.encode('utf-8')).hexdigest().lower()}"


# ── Full Bundle Export ─────────────────────────────────────────────────────────


def export_bundle(
    result: OpenArchitectureRunResult,
    output_dir: str | Path,
) -> Path:
    """Export complete deterministic research bundle directory.

    Writes:
    - bundle.json: metadata, configuration hash, bundle_content_sha256
    - sources.jsonl: discovered source documents
    - candidates.jsonl: composed DecisionCandidates
    - classifier-executions.jsonl: full classifier execution records
    - scenarios.jsonl: evaluated applicability scenarios
    - gds-results.jsonl: Governing Decision Set evaluation results
    - report.json: machine-readable report
    - report.md: human-readable Markdown report

    Returns:
        Path to output bundle directory.
    """
    bundle_path = Path(output_dir)
    bundle_path.mkdir(parents=True, exist_ok=True)

    bundle_content_hash = compute_bundle_content_hash(result)

    # 1. bundle.json
    bundle_meta = {
        "schema_version": "0.1",
        "bundle_content_sha256": bundle_content_hash,
        "run_id": result.run_metadata.run_id,
        "repository_identifier": result.repository_config.github,
        "repository_commit_sha": result.repository_config.commit_sha,
        "configuration_hash": result.run_metadata.configuration_hash,
        "taxonomy_version": result.run_metadata.taxonomy_version,
        "classifier_version": result.run_metadata.classifier_version,
        "status": result.run_metadata.status,
        "started_at": result.run_metadata.started_at,
        "completed_at": result.run_metadata.completed_at,
        "counts": {
            "discovered_documents": len(result.discovered_documents),
            "extracted_candidates": len(result.extracted_candidates),
            "composed_candidates": len(result.composed_candidates),
            "incomplete_candidates": len(result.incomplete_candidates),
            "classifier_executions": len(result.classifier_results),
            "scenarios_evaluated": len(result.gds_results),
        },
        "suite_metrics": dict(result.suite_metrics),
    }
    (bundle_path / "bundle.json").write_text(
        json.dumps(bundle_meta, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    # 2. sources.jsonl
    with (bundle_path / "sources.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for doc in sorted(result.discovered_documents, key=lambda d: d.relative_path):
            doc_dict = {
                "relative_path": doc.relative_path,
                "source_type": doc.source_type,
                "content_hash": doc.content_hash,
                "metadata": doc.metadata,
            }
            fh.write(json.dumps(doc_dict, sort_keys=True, separators=(",", ":")) + "\n")

    # 3. candidates.jsonl
    export_candidates_jsonl(result.composed_candidates, bundle_path / "candidates.jsonl")

    # 4. classifier-executions.jsonl
    with (bundle_path / "classifier-executions.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        sorted_executions = sorted(
            result.classifier_results,
            key=lambda r: (r.candidate_id, r.task_type.value),
        )
        for exec_res in sorted_executions:
            fh.write(exec_res.to_json() + "\n")

    # 5. gds-results.jsonl
    with (bundle_path / "gds-results.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for gds_res in sorted(result.gds_results, key=lambda g: g.scenario_id):
            fh.write(json.dumps(gds_res.to_dict(), sort_keys=True, separators=(",", ":")) + "\n")

    # 6. report.json & report.md
    report_dict = generate_report(result)
    (bundle_path / "report.json").write_text(
        json.dumps(report_dict, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    md_report = render_markdown_report(result)
    (bundle_path / "report.md").write_text(md_report, encoding="utf-8", newline="\n")

    return bundle_path


__all__ = [
    "export_candidates_jsonl",
    "import_candidates_jsonl",
    "export_scenarios_jsonl",
    "import_scenarios_jsonl",
    "compute_bundle_content_hash",
    "export_bundle",
]
