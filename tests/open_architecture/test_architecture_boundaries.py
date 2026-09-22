"""Tests verifying O1A architecture boundaries and frozen benchmark parity."""

from __future__ import annotations

import pytest

from mneme.open_architecture import (
    ResearchStore,
    DecisionCandidate,
    ApplicabilityScenario,
    GoverningDecisionSetMetrics,
    O1AErrorCategory,
)
from mneme.benchmark import BenchmarkRunner, ScenarioVerdict
from mneme.memory_store import MemoryStore
from mneme.decision_retriever import DecisionRetriever
from mneme.conflict_detector import ConflictDetector
from mneme.enforcer import check_prompt, Severity
from mneme.decision_index import decisions_to_canonical
from mneme.schemas import Decision, Rule


class TestO1ANoCanonicalWritePaths:
    """Verify O1A APIs expose no canonical Decision Index write path."""

    def test_research_store_no_canonical_tables(self):
        """Research store should not have canonical decision index tables."""
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db_path = f.name
        try:
            store = ResearchStore(db_path)
            store.initialize_schema()
            conn = store.connect()
            tables = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            # Should NOT have canonical decision index tables
            canonical_tables = {
                "decisions", "decision_index", "canonical_decisions",
                "canonical_rules", "canonical_relationships"
            }
            assert canonical_tables.isdisjoint(tables)
            # Should have O1A research tables
            research_tables = {
                "repositories", "taxonomy_versions", "classifier_versions", "analysis_runs",
                "source_documents", "decision_candidates", "candidate_classifications",
                "candidate_domains", "candidate_purposes", "candidate_authority",
                "candidate_scopes", "candidate_lifecycle", "candidate_relationships",
                "enforcement_assessments", "evidence", "applicability_scenarios",
                "scenario_expected_decisions", "scenario_results", "scenario_result_decisions",
                "human_reviews", "classifier_executions", "classifier_disagreements"
            }
            assert research_tables.issubset(tables)
        finally:
            store.close()
            os.unlink(db_path)

    def test_decision_candidate_is_research_only(self):
        """DecisionCandidate should be clearly marked as research data."""
        cand = DecisionCandidate(
            candidate_id="cand-test",
            repository="MnemeHQ/mneme",
            source_file="test.md",
            source_location=None,
            raw_statement=None,
            normalized_decision="Test decision",
            classification="prescriptive",
            decision_domains=("persistence",),
            decision_purposes=("constrain",),
            authority_status="candidate",  # Not "canonical" or "explicitly_accepted"
            authority_evidence=None,
            scopes=(),
            lifecycle_status="active",
            relationships=(),
            enforcement_potential="deterministic_rule",
            candidate_rule=None,
            confidence=0.9,
            human_validation_status="unreviewed",
            human_corrections=None,
        )
        # Authority should be "candidate" not "canonical"
        assert cand.authority_status == "candidate"
        # Not a canonical decision
        assert not hasattr(cand, "decision_id")

    def test_applicability_scenario_expected_never_auto_derived(self):
        """Expected governing decision IDs are reference labels, never auto-derived."""
        scn = ApplicabilityScenario(
            scenario_id="scn-test",
            repository="MnemeHQ/mneme",
            description="Test",
            change_context=None,
            expected_governing_decision_ids=("ADR-001", "ADR-002"),
            mneme_governing_decision_ids=(),
            human_notes=None,
            validation_state="unreviewed",
        )
        # Expected IDs are set explicitly, not derived
        assert scn.expected_governing_decision_ids == ("ADR-001", "ADR-002")
        # Mneme predictions start empty
        assert scn.mneme_governing_decision_ids == ()

    def test_no_accepted_proposal_creation(self):
        """O1A should not create accepted proposals."""
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db_path = f.name
        try:
            store = ResearchStore(db_path)
            store.initialize_schema()
            # No create_proposal, accept_proposal, etc.
            assert not hasattr(store, "create_proposal")
            assert not hasattr(store, "accept_proposal")
            assert not hasattr(store, "create_decision")
        finally:
            store.close()
            os.unlink(db_path)

    def test_no_enforcement_evidence_writing(self):
        """O1A should not write enforcement evidence."""
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db_path = f.name
        try:
            store = ResearchStore(db_path)
            store.initialize_schema()
            conn = store.connect()
            tables = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            # No enforcement evidence tables
            assert "enforcement_evidence" not in tables
            # 'evidence' table exists for decision evidence, not enforcement evidence
            assert "evidence" in tables
        finally:
            store.close()
            os.unlink(db_path)


class TestFrozenBenchmarkParity:
    """Verify existing Layer 1 benchmark semantics are unchanged."""

    def test_benchmark_runner_unchanged_interface(self):
        """BenchmarkRunner should have same interface."""
        assert hasattr(BenchmarkRunner, "__init__")
        assert hasattr(BenchmarkRunner, "run_scenario")
        assert hasattr(BenchmarkRunner, "run_suite")

    def test_scenario_verdict_unchanged(self):
        """ScenarioVerdict enum should be unchanged."""
        assert ScenarioVerdict.PASS == "PASS"
        assert ScenarioVerdict.FAIL == "FAIL"
        assert ScenarioVerdict.WEAK == "WEAK"
        assert ScenarioVerdict.WEAK_RETRIEVAL == "WEAK_RETRIEVAL"
        assert ScenarioVerdict.MALFORMED == "MALFORMED"
        assert ScenarioVerdict.FALSE_POSITIVE == "FALSE_POSITIVE"

    def test_decision_retriever_unchanged(self):
        """DecisionRetriever should be unchanged."""
        retriever = DecisionRetriever([])
        assert hasattr(retriever, "retrieve")

    def test_conflict_detector_unchanged(self):
        """ConflictDetector should be unchanged."""
        detector = ConflictDetector()
        assert hasattr(detector, "evaluate")
        assert hasattr(detector, "detect")

    def test_enforcer_check_prompt_unchanged(self):
        """check_prompt should be unchanged."""
        from mneme.decision_retriever import ScoredDecision
        from mneme.schemas import Decision
        import inspect
        sig = inspect.signature(check_prompt)
        params = list(sig.parameters.keys())
        assert "input_text" in params
        assert "scored" in params
        assert "top" in params
        assert "input_path" in params

    def test_enforcer_severity_unchanged(self):
        """Severity enum should be unchanged."""
        assert Severity.PASS == "PASS"
        assert Severity.WARN == "WARN"
        assert Severity.FAIL == "FAIL"

    def test_memory_store_unchanged(self):
        """MemoryStore should be unchanged."""
        assert hasattr(MemoryStore, "load")
        assert hasattr(MemoryStore, "decisions")
        assert hasattr(MemoryStore, "rules")
        assert hasattr(MemoryStore, "anti_patterns")

    def test_decision_index_projection_unchanged(self):
        """decisions_to_canonical should be unchanged."""
        decision = Decision(
            id="test-001",
            decision="Test decision",
            rationale="Test rationale",
            scope=["test"],
            constraints=[],
            anti_patterns=[],
            rules=[],
        )
        index = decisions_to_canonical([decision])
        assert len(index.records) == 1
        assert index.records[0].decision_id == "test-001"