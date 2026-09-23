"""
tests.open_architecture.test_reporting — Tests for research reporting.

Covers:
- Machine-readable JSON report generation
- Human-readable Markdown report generation
- Metric reporting rules: separate macro_precision, macro_recall, macro_f1 (no single overall score)
- Scenario and incomplete candidate breakdown reporting
"""

from __future__ import annotations

import json
from pathlib import Path

from mneme.open_architecture.candidates import ExtractedCandidate, LineSpan
from mneme.open_architecture.discovery import DiscoveredSourceDocument
from mneme.open_architecture.gds_evaluation import GoverningDecisionSetResult
from mneme.open_architecture.manifest import RepositoryConfig
from mneme.open_architecture.orchestrator import (
    IncompleteCandidateRecord,
    OpenArchitectureRunResult,
)
from mneme.open_architecture.reporting import (
    generate_report,
    render_markdown_report,
)
from mneme.open_architecture.run_metadata import RunMetadata
from mneme.open_architecture.schemas import DecisionCandidate, Scope


def _make_dummy_result() -> OpenArchitectureRunResult:
    meta = RunMetadata(
        run_id="run-report-01",
        batch_id="batch-01",
        repo_id="adrkit",
        repo_commit_sha="a" * 40,
        mneme_version="0.9.2",
        mneme_commit_sha="b" * 40,
        benchmark_schema_version="0.1",
        taxonomy_version="0.1",
        classifier_version="0.1.0",
        configuration_hash="conf123",
        started_at="2026-01-01T00:00:00Z",
        completed_at="2026-01-01T00:05:00Z",
        status="completed",
    )
    config = RepositoryConfig("adrkit", "mbeacom/adrkit", "a" * 40, "test", "reviewed")
    doc = DiscoveredSourceDocument("docs/adr/ADR-001.md", "adr", "sha256:" + "1" * 64, "# ADR", {})
    cand_id = "cand-" + "a" * 32
    extracted = ExtractedCandidate(
        cand_id, "mbeacom/adrkit", "a" * 40, "docs/adr/ADR-001.md", "sha256:" + "1" * 64,
        LineSpan(1, 5), "Use SQLite", 0.9,
    )
    composed = DecisionCandidate(
        candidate_id=cand_id,
        repository="mbeacom/adrkit",
        source_file="docs/adr/ADR-001.md",
        source_location="L1-L5",
        raw_statement="Use SQLite",
        normalized_decision="Use SQLite",
        classification="prescriptive",
        decision_domains=("persistence",),
        decision_purposes=("standardize",),
        authority_status="candidate",
        authority_evidence=None,
        scopes=(Scope("repository", "storage"),),
        lifecycle_status="active",
        relationships=(),
        enforcement_potential="deterministic_rule",
        candidate_rule=None,
        confidence=0.9,
        human_validation_status="unreviewed",
        human_corrections=None,
    )
    incomplete = IncompleteCandidateRecord(
        candidate_id="cand-incomplete-002",
        source_path="docs/adr/ADR-002.md",
        raw_statement="Ambiguous text",
        missing_or_failed_dimensions=("classification",),
        errors={"classification": "Invalid classification value"},
    )
    gds = GoverningDecisionSetResult(
        scenario_id="scn-001",
        query="query",
        retrieved_ids=(cand_id,),
        retrieval_scores=(2.0,),
        predicted_governing_decision_ids=(cand_id,),
        expected_governing_decision_ids=(cand_id,),
        precision=1.0,
        recall=1.0,
        f1=1.0,
        expected_count=1,
        predicted_count=1,
        overlap_count=1,
    )
    return OpenArchitectureRunResult(
        run_metadata=meta,
        repository_config=config,
        discovered_documents=(doc,),
        extracted_candidates=(extracted,),
        composed_candidates=(composed,),
        incomplete_candidates=(incomplete,),
        classifier_results=(),
        scenarios=(),
        gds_results=(gds,),
        suite_metrics={"macro_precision": 1.0, "macro_recall": 1.0, "macro_f1": 1.0},
        diagnostics=(),
    )


class TestReporting:
    def test_generate_report_schema_and_contents(self):
        result = _make_dummy_result()
        report = generate_report(result)

        assert report["report_schema"] == "o1a.report/v1"
        assert report["provenance"]["repository"] == "mbeacom/adrkit"
        assert report["provenance"]["status"] == "completed"
        assert report["inventory"]["discovered_documents"] == 1
        assert report["inventory"]["composed_candidates"] == 1
        assert report["inventory"]["incomplete_candidates"] == 1
        assert report["inventory"]["scenarios_evaluated"] == 1

        # Metrics must NOT collapse into a single overall score
        metrics = report["metrics"]
        assert "macro_precision" in metrics
        assert "macro_recall" in metrics
        assert "macro_f1" in metrics
        assert "overall_score" not in metrics
        assert metrics["macro_f1"] == 1.0

        # Scenario summaries
        assert len(report["scenarios"]) == 1
        assert report["scenarios"][0]["scenario_id"] == "scn-001"
        assert report["scenarios"][0]["f1"] == 1.0

        # Incomplete summaries
        assert len(report["incomplete_candidates"]) == 1
        assert report["incomplete_candidates"][0]["candidate_id"] == "cand-incomplete-002"

    def test_render_markdown_report_formatting(self):
        result = _make_dummy_result()
        md = render_markdown_report(result)

        assert "# O1A Analysis Report: mbeacom/adrkit" in md
        assert "## Provenance" in md
        assert "## Evidence Inventory" in md
        assert "## Headline Metrics: Governing Decision Set (GDS)" in md
        assert "- **Macro F1 (Headline):** 1.0000" in md
        assert "No single aggregate score is computed" in md
        assert "## Scenario Evaluations" in md
        assert "`scn-001`" in md
        assert "## Incomplete Candidate Diagnostics" in md
        assert "`cand-incomplete-002`" in md
