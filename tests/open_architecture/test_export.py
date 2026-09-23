"""
tests.open_architecture.test_export — Tests for portable research export, import, and bundle hashing.

Covers:
- DecisionCandidate JSONL export and import round-trip
- ApplicabilityScenario JSONL export and import round-trip
- Malformed JSONL line rejection
- Deterministic bundle content hash invariant:
  - Identical semantic results produce identical bundle_content_sha256 regardless of
    run_id, timestamps, latency_ms, or cost measurements.
  - Semantic changes (different candidate, different statement, different scenario) change hash.
- Complete export_bundle directory structure verification.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mneme.open_architecture.candidates import ExtractedCandidate, LineSpan
from mneme.open_architecture.classification import ClassifierResult, ClassifierTaskType
from mneme.open_architecture.discovery import DiscoveredSourceDocument
from mneme.open_architecture.export import (
    compute_bundle_content_hash,
    export_bundle,
    export_candidates_jsonl,
    export_scenarios_jsonl,
    import_candidates_jsonl,
    import_scenarios_jsonl,
)
from mneme.open_architecture.gds_evaluation import GoverningDecisionSetResult
from mneme.open_architecture.manifest import RepositoryConfig
from mneme.open_architecture.orchestrator import OpenArchitectureRunResult
from mneme.open_architecture.run_metadata import RunMetadata
from mneme.open_architecture.schemas import (
    ApplicabilityScenario,
    ChangeContext,
    DecisionCandidate,
    Scope,
)


# ── Fixtures & Helpers ─────────────────────────────────────────────────────────


def _make_candidate(cand_id: str = "cand-" + "a" * 32, decision: str = "Use SQLite") -> DecisionCandidate:
    return DecisionCandidate(
        candidate_id=cand_id,
        repository="mbeacom/adrkit",
        source_file="docs/adr/ADR-001.md",
        source_location="L1-L5",
        raw_statement=decision,
        normalized_decision=decision,
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


def _make_scenario(scenario_id: str = "scn-001") -> ApplicabilityScenario:
    return ApplicabilityScenario(
        scenario_id=scenario_id,
        repository="mbeacom/adrkit",
        description="Test scenario",
        change_context=ChangeContext(
            path="storage.py",
            component="storage",
            change_type="modify",
            dependencies=("sqlite3",),
            api=None,
            technology="Python",
            other_context=None,
        ),
        expected_governing_decision_ids=("cand-" + "a" * 32,),
        mneme_governing_decision_ids=(),
        human_notes=None,
        validation_state="unreviewed",
    )


def _make_run_result(
    *,
    run_id: str = "run-001",
    started_at: str = "2026-01-01T00:00:00Z",
    completed_at: str = "2026-01-01T00:05:00Z",
    executed_at: str = "2026-01-01T00:02:00Z",
    latency_ms: float = 12.5,
    cost_amount: float | None = 0.005,
    decision_text: str = "Use SQLite",
    scenario_desc: str = "Test scenario",
    classifier_output: dict | None = None,
) -> OpenArchitectureRunResult:
    cand_id = "cand-" + "a" * 32
    meta = RunMetadata(
        run_id=run_id,
        batch_id="batch-01",
        repo_id="adrkit",
        repo_commit_sha="a" * 40,
        mneme_version="0.9.2",
        mneme_commit_sha="b" * 40,
        benchmark_schema_version="0.1",
        taxonomy_version="0.1",
        classifier_version="0.1.0",
        classifier_backend="static",
        classifier_model="static/test",
        extractor_id="heuristic",
        extractor_version="0.1",
        scenario_content_hash="scenariohash123",
        retrieval_policy="score_gt_zero",
        configuration_hash="confighash123",
        started_at=started_at,
        completed_at=completed_at,
        status="completed",
    )
    config = RepositoryConfig(
        id="adrkit",
        github="mbeacom/adrkit",
        commit_sha="a" * 40,
        primary_test="test",
        validation_status="reviewed",
    )
    doc = DiscoveredSourceDocument(
        relative_path="docs/adr/ADR-001.md",
        source_type="adr",
        content_hash="sha256:" + "1" * 64,
        content="# Decision",
        metadata={"byte_length": 10},
    )
    extracted = ExtractedCandidate(
        candidate_id=cand_id,
        repository_identifier="mbeacom/adrkit",
        repository_commit_sha="a" * 40,
        source_path="docs/adr/ADR-001.md",
        source_content_hash="sha256:" + "1" * 64,
        source_location=LineSpan(1, 5),
        raw_statement=decision_text,
        discovery_confidence=0.9,
    )
    composed = _make_candidate(cand_id=cand_id, decision=decision_text)
    classifier_res = ClassifierResult(
        task_type=ClassifierTaskType.DECISION_CLASSIFICATION,
        backend_id="static",
        classifier_version="0.1.0",
        model_identifier="static/test",
        taxonomy_version="0.1",
        candidate_id=cand_id,
        output=classifier_output or {"classification": "prescriptive"},
        confidence=0.9,
        latency_ms=latency_ms,
        cost_amount=cost_amount,
        cost_currency="USD",
        executed_at=executed_at,
    )
    scenario = _make_scenario(scenario_id="scn-001")
    if scenario_desc != "Test scenario":
        scenario = ApplicabilityScenario(
            scenario_id="scn-001",
            repository="mbeacom/adrkit",
            description=scenario_desc,
            change_context=scenario.change_context,
            expected_governing_decision_ids=scenario.expected_governing_decision_ids,
            mneme_governing_decision_ids=(),
            human_notes=None,
            validation_state="unreviewed",
        )
    gds = GoverningDecisionSetResult(
        scenario_id="scn-001",
        query="query",
        retrieved_ids=(cand_id,),
        retrieval_scores=(1.5,),
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
        incomplete_candidates=(),
        classifier_results=(classifier_res,),
        scenarios=(scenario,),
        gds_results=(gds,),
        suite_metrics={"macro_precision": 1.0, "macro_recall": 1.0, "macro_f1": 1.0},
        diagnostics=(),
    )


# ── JSONL Import / Export Tests ────────────────────────────────────────────────


class TestJsonlImportExport:
    def test_candidates_jsonl_round_trip(self, tmp_path: Path):
        c1 = _make_candidate("cand-" + "b" * 32, "Decision B")
        c2 = _make_candidate("cand-" + "a" * 32, "Decision A")

        out_file = tmp_path / "candidates.jsonl"
        export_candidates_jsonl([c1, c2], out_file)

        # Lines must be sorted by candidate_id
        lines = [line.strip() for line in out_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(lines) == 2
        d1 = json.loads(lines[0])
        d2 = json.loads(lines[1])
        assert d1["candidate_id"] == "cand-" + "a" * 32
        assert d2["candidate_id"] == "cand-" + "b" * 32

        # Round trip
        imported = import_candidates_jsonl(out_file)
        assert len(imported) == 2
        assert imported[0] == c2
        assert imported[1] == c1

    def test_scenarios_jsonl_round_trip(self, tmp_path: Path):
        s1 = _make_scenario("scn-b")
        s2 = _make_scenario("scn-a")

        out_file = tmp_path / "scenarios.jsonl"
        export_scenarios_jsonl([s1, s2], out_file)

        lines = [line.strip() for line in out_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(lines) == 2
        assert json.loads(lines[0])["scenario_id"] == "scn-a"
        assert json.loads(lines[1])["scenario_id"] == "scn-b"

        imported = import_scenarios_jsonl(out_file)
        assert len(imported) == 2
        assert imported[0] == s2
        assert imported[1] == s1

    def test_malformed_candidate_jsonl_rejected(self, tmp_path: Path):
        out_file = tmp_path / "bad_candidates.jsonl"
        out_file.write_text('{"candidate_id": "c1", "bad_json": true}\n', encoding="utf-8")

        with pytest.raises(ValueError, match="Malformed DecisionCandidate"):
            import_candidates_jsonl(out_file)

    def test_malformed_scenario_jsonl_rejected(self, tmp_path: Path):
        out_file = tmp_path / "bad_scenarios.jsonl"
        out_file.write_text('{"scenario_id": "s1", "bad": 123}\n', encoding="utf-8")

        with pytest.raises(ValueError, match="Malformed ApplicabilityScenario"):
            import_scenarios_jsonl(out_file)


# ── Bundle Content Hashing Tests ──────────────────────────────────────────────


class TestBundleContentHashing:
    def test_bundle_content_hash_invariance_across_volatile_telemetry(self):
        """Invariance: Two runs with identical semantic results have IDENTICAL bundle_content_sha256

        even if run_id, timestamps, latency_ms, or cost measurements differ.
        """
        run1 = _make_run_result(
            run_id="run-aaa-111",
            started_at="2026-01-01T10:00:00Z",
            completed_at="2026-01-01T10:05:00Z",
            executed_at="2026-01-01T10:02:00Z",
            latency_ms=10.0,
            cost_amount=0.01,
        )
        run2 = _make_run_result(
            run_id="run-bbb-222",
            started_at="2026-09-23T22:30:00Z",
            completed_at="2026-09-23T22:35:00Z",
            executed_at="2026-09-23T22:31:00Z",
            latency_ms=45.0,
            cost_amount=0.08,
        )

        h1 = compute_bundle_content_hash(run1)
        h2 = compute_bundle_content_hash(run2)

        assert h1 == h2
        assert h1.startswith("sha256:")
        assert len(h1) == 71  # 'sha256:' + 64 hex

    def test_bundle_content_hash_changes_on_semantic_difference(self):
        """Changing candidate text or semantic output changes the content hash."""
        run1 = _make_run_result(decision_text="Use SQLite database")
        run2 = _make_run_result(decision_text="Use PostgreSQL database")

        h1 = compute_bundle_content_hash(run1)
        h2 = compute_bundle_content_hash(run2)

        assert h1 != h2

    def test_bundle_content_hash_changes_on_scenario_difference(self):
        """Changing scenario content changes the bundle content hash."""
        run1 = _make_run_result(scenario_desc="Original description")
        run2 = _make_run_result(scenario_desc="Modified description")

        h1 = compute_bundle_content_hash(run1)
        h2 = compute_bundle_content_hash(run2)

        assert h1 != h2

    def test_bundle_content_hash_changes_on_classifier_output_difference(self):
        """Changing classifier semantic output changes the bundle content hash."""
        run1 = _make_run_result(classifier_output={"classification": "prescriptive"})
        run2 = _make_run_result(classifier_output={"classification": "advisory"})

        h1 = compute_bundle_content_hash(run1)
        h2 = compute_bundle_content_hash(run2)

        assert h1 != h2


# ── Complete Export Bundle Tests ──────────────────────────────────────────────


class TestExportBundle:
    def test_export_bundle_creates_all_files(self, tmp_path: Path):
        run = _make_run_result()
        bundle_dir = tmp_path / "bundle_output"

        res_path = export_bundle(run, bundle_dir)
        assert res_path == bundle_dir

        expected_files = [
            "bundle.json",
            "sources.jsonl",
            "candidates.jsonl",
            "classifier-executions.jsonl",
            "scenarios.jsonl",
            "gds-results.jsonl",
            "report.json",
            "report.md",
        ]
        for fname in expected_files:
            p = bundle_dir / fname
            assert p.is_file(), f"Missing expected bundle artifact: {fname}"

        # Verify bundle.json content
        bundle_meta = json.loads((bundle_dir / "bundle.json").read_text(encoding="utf-8"))
        assert "bundle_content_sha256" in bundle_meta
        assert bundle_meta["counts"]["composed_candidates"] == 1
        assert bundle_meta["status"] == "completed"

        # Verify candidates.jsonl
        cand_lines = (bundle_dir / "candidates.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(cand_lines) == 1
        assert json.loads(cand_lines[0])["candidate_id"] == "cand-" + "a" * 32

        # Verify scenarios.jsonl
        scn_lines = (bundle_dir / "scenarios.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(scn_lines) == 1
        assert json.loads(scn_lines[0])["scenario_id"] == "scn-001"
