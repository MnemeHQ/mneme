"""Tests for O1A SQLite Research Store (wraps merged research_store.sql)."""

from __future__ import annotations

import tempfile
import pytest

from mneme.open_architecture.store import (
    ResearchStore,
    RepositoryRecord,
    TaxonomyVersionRecord,
    ClassifierVersionRecord,
    AnalysisRunRecord,
    DecisionCandidateRecord,
    CandidateClassificationRecord,
    CandidateDomainRecord,
    CandidatePurposeRecord,
    CandidateAuthorityRecord,
    CandidateScopeRecord,
    CandidateLifecycleRecord,
    CandidateRelationshipRecord,
    EnforcementAssessmentRecord,
    EvidenceRecord,
    ApplicabilityScenarioRecord,
    ScenarioExpectedDecisionRecord,
    ScenarioResultRecord,
    ScenarioResultDecisionRecord,
    HumanReviewRecord,
    ClassifierExecutionRecord,
    ClassifierDisagreementRecord,
    generate_id,
    now_iso,
)


class TestResearchStore:
    @pytest.fixture
    def store(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db_path = f.name
        store = ResearchStore(db_path)
        store.initialize_schema()
        # Pre-populate required reference data for FK constraints
        store.upsert_taxonomy_version(TaxonomyVersionRecord("0.1", now_iso(), "test"))
        store.upsert_taxonomy_version(TaxonomyVersionRecord("0.2", now_iso(), "test"))
        store.upsert_classifier_version(ClassifierVersionRecord("0.1", now_iso(), "test"))
        store.upsert_classifier_version(ClassifierVersionRecord("0.2", now_iso(), "test"))
        yield store
        store.close()
        import os
        os.unlink(db_path)

    def test_schema_initialization_merged(self, store):
        conn = store.connect()
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        # All 22 merged tables must exist
        expected = {
            "repositories", "taxonomy_versions", "classifier_versions", "analysis_runs",
            "source_documents", "decision_candidates", "candidate_classifications",
            "candidate_domains", "candidate_purposes", "candidate_authority",
            "candidate_scopes", "candidate_lifecycle", "candidate_relationships",
            "enforcement_assessments", "evidence", "applicability_scenarios",
            "scenario_expected_decisions", "scenario_results", "scenario_result_decisions",
            "human_reviews", "classifier_executions", "classifier_disagreements"
        }
        assert expected.issubset(tables)

    def test_foreign_keys_enabled(self, store):
        conn = store.connect()
        result = conn.execute("PRAGMA foreign_keys").fetchone()
        assert result[0] == 1

    def test_upsert_repository(self, store):
        repo = RepositoryRecord(
            repo_id="test-repo",
            repository_url="https://github.com/test/repo",
            repository_identifier="test/repo",
            default_branch="main",
        )
        store.upsert_repository(repo)
        retrieved = store.get_repository("test-repo")
        assert retrieved is not None
        assert retrieved.repository_identifier == "test/repo"

    def test_create_analysis_run(self, store):
        store.upsert_repository(RepositoryRecord("test-repo", "url", "test/repo", "main"))
        run = AnalysisRunRecord(
            run_id="run-test", repo_id="test-repo", repo_commit_sha="a"*40,
            mneme_version="0.9.1", mneme_commit_sha="b"*40,
            taxonomy_version="0.1", classifier_version="0.1",
            benchmark_schema_version="0.1", configuration_hash="config123",
            started_at=now_iso(), completed_at=None, status="running"
        )
        store.create_analysis_run(run)
        retrieved = store.get_analysis_run("run-test")
        assert retrieved is not None
        assert retrieved.run_id == "run-test"

    def test_duplicate_analysis_run_fails(self, store):
        store.upsert_repository(RepositoryRecord("test-repo", "url", "test/repo", "main"))
        run = AnalysisRunRecord(
            run_id="run-dup", repo_id="test-repo", repo_commit_sha="a"*40,
            mneme_version="0.9.1", mneme_commit_sha="b"*40,
            taxonomy_version="0.1", classifier_version="0.1",
            benchmark_schema_version="0.1", configuration_hash="config123",
            started_at=now_iso(), completed_at=None, status="running"
        )
        store.create_analysis_run(run)
        # Same run_id should fail
        with pytest.raises(Exception):
            store.create_analysis_run(run)

    def test_decision_candidate_crud(self, store):
        store.upsert_repository(RepositoryRecord("test-repo", "url", "test/repo", "main"))
        store.create_analysis_run(AnalysisRunRecord(
            run_id="run-cand", repo_id="test-repo", repo_commit_sha="a"*40,
            mneme_version="0.9.1", mneme_commit_sha="b"*40,
            taxonomy_version="0.1", classifier_version="0.1",
            benchmark_schema_version="0.1", configuration_hash="config1",
            started_at=now_iso(), completed_at=None, status="running"
        ))
        cand = DecisionCandidateRecord(
            candidate_id="cand-test", run_id="run-cand", source_id=None,
            source_location=None, raw_evidence_reference=None,
            normalized_decision="Test decision", discovery_confidence=None,
            discovery_metadata_json=None
        )
        store.insert_decision_candidate(cand)
        retrieved = store.get_decision_candidate("cand-test")
        assert retrieved is not None
        assert retrieved.normalized_decision == "Test decision"

    def test_candidate_classifications_multiple_per_candidate(self, store):
        store.upsert_repository(RepositoryRecord("test-repo", "url", "test/repo", "main"))
        store.create_analysis_run(AnalysisRunRecord(
            run_id="run-class", repo_id="test-repo", repo_commit_sha="a"*40,
            mneme_version="0.9.1", mneme_commit_sha="b"*40,
            taxonomy_version="0.1", classifier_version="0.1",
            benchmark_schema_version="0.1", configuration_hash="config2",
            started_at=now_iso(), completed_at=None, status="running"
        ))
        store.insert_decision_candidate(DecisionCandidateRecord(
            candidate_id="cand-class", run_id="run-class", source_id=None,
            source_location=None, raw_evidence_reference=None,
            normalized_decision="Test", discovery_confidence=None, discovery_metadata_json=None
        ))
        cc1 = CandidateClassificationRecord(
            classification_id="class-1", candidate_id="cand-class", run_id="run-class",
            classification="prescriptive", classifier_version="0.1", taxonomy_version="0.1",
            confidence=0.8, rationale="test", created_at=now_iso()
        )
        cc2 = CandidateClassificationRecord(
            classification_id="class-2", candidate_id="cand-class", run_id="run-class",
            classification="advisory", classifier_version="0.2", taxonomy_version="0.1",
            confidence=0.7, rationale="test2", created_at=now_iso()
        )
        store.insert_candidate_classification(cc1)
        store.insert_candidate_classification(cc2)
        classifications = store.list_candidate_classifications("cand-class")
        assert len(classifications) == 2

    def test_candidate_domains_multiple_per_candidate(self, store):
        store.upsert_repository(RepositoryRecord("test-repo", "url", "test/repo", "main"))
        store.create_analysis_run(AnalysisRunRecord(
            run_id="run-dom", repo_id="test-repo", repo_commit_sha="a"*40,
            mneme_version="0.9.1", mneme_commit_sha="b"*40,
            taxonomy_version="0.1", classifier_version="0.1",
            benchmark_schema_version="0.1", configuration_hash="config3",
            started_at=now_iso(), completed_at=None, status="running"
        ))
        store.insert_decision_candidate(DecisionCandidateRecord(
            candidate_id="cand-dom", run_id="run-dom", source_id=None,
            source_location=None, raw_evidence_reference=None,
            normalized_decision="Test", discovery_confidence=None, discovery_metadata_json=None
        ))
        store.insert_candidate_domain(CandidateDomainRecord(
            candidate_id="cand-dom", run_id="run-dom", domain="persistence",
            confidence=0.9, classifier_version="0.1"
        ))
        store.insert_candidate_domain(CandidateDomainRecord(
            candidate_id="cand-dom", run_id="run-dom", domain="api_interface",
            confidence=0.7, classifier_version="0.1"
        ))
        domains = store.list_candidate_domains("cand-dom", "run-dom")
        assert len(domains) == 2

    def test_candidate_authority_upsert(self, store):
        store.upsert_repository(RepositoryRecord("test-repo", "url", "test/repo", "main"))
        store.create_analysis_run(AnalysisRunRecord(
            run_id="run-auth", repo_id="test-repo", repo_commit_sha="a"*40,
            mneme_version="0.9.1", mneme_commit_sha="b"*40,
            taxonomy_version="0.1", classifier_version="0.1",
            benchmark_schema_version="0.1", configuration_hash="config4",
            started_at=now_iso(), completed_at=None, status="running"
        ))
        store.insert_decision_candidate(DecisionCandidateRecord(
            candidate_id="cand-auth", run_id="run-auth", source_id=None,
            source_location=None, raw_evidence_reference=None,
            normalized_decision="Test", discovery_confidence=None, discovery_metadata_json=None
        ))
        store.upsert_candidate_authority(CandidateAuthorityRecord(
            candidate_id="cand-auth", run_id="run-auth",
            authority_status="candidate", authority_evidence=None, confidence=0.8
        ))
        # Update to explicitly_accepted
        store.upsert_candidate_authority(CandidateAuthorityRecord(
            candidate_id="cand-auth", run_id="run-auth",
            authority_status="explicitly_accepted", authority_evidence="human review", confidence=0.9
        ))

    def test_human_reviews_preserve_machine_predictions(self, store):
        """Machine predictions remain stored after human correction."""
        store.upsert_repository(RepositoryRecord("test-repo", "url", "test/repo", "main"))
        store.create_analysis_run(AnalysisRunRecord(
            run_id="run-hr", repo_id="test-repo", repo_commit_sha="a"*40,
            mneme_version="0.9.1", mneme_commit_sha="b"*40,
            taxonomy_version="0.1", classifier_version="0.1",
            benchmark_schema_version="0.1", configuration_hash="config5",
            started_at=now_iso(), completed_at=None, status="running"
        ))
        store.insert_decision_candidate(DecisionCandidateRecord(
            candidate_id="cand-hr", run_id="run-hr", source_id=None,
            source_location=None, raw_evidence_reference=None,
            normalized_decision="Test", discovery_confidence=None, discovery_metadata_json=None
        ))
        # Insert multiple classifier executions (machine predictions)
        for i in range(3):
            store.insert_classifier_execution(ClassifierExecutionRecord(
                execution_id=f"exec-{i}", candidate_id="cand-hr", run_id="run-hr",
                classifier_backend="test", classifier_version=f"0.{i}",
                model_identifier=None, taxonomy_version="0.1", task_type="classification",
                output_json=f'{{"class": "prescriptive"}}', confidence=0.8,
                latency_ms=None, cost_amount=None, cost_currency=None,
                escalated=0, created_at=now_iso()
            ))
        # Human review
        store.insert_human_review(HumanReviewRecord(
            review_id="review-1", candidate_id="cand-hr", machine_run_id="run-hr",
            verdict="partially_correct", corrected_decision="Corrected decision",
            corrected_classification="advisory", corrected_authority=None,
            corrected_scope_json=None, corrected_lifecycle_json=None,
            corrected_domains_json=None, corrected_purposes_json=None,
            corrected_relationships_json=None, corrected_enforcement_json=None,
            corrections_json=None, reviewer="human1", reviewed_at=now_iso(), notes=None
        ))
        # Verify all machine executions still exist
        executions = store.list_classifier_executions("cand-hr")
        assert len(executions) == 3
        # Verify human review exists
        reviews = store.list_human_reviews("cand-hr")
        assert len(reviews) == 1
        assert reviews[0].verdict == "partially_correct"

    def test_applicability_scenario_crud(self, store):
        store.upsert_repository(RepositoryRecord("test-repo", "url", "test/repo", "main"))
        scn = ApplicabilityScenarioRecord(
            scenario_id="scn-test", repo_id="test-repo", description="Test",
            path="src/test.py", component="storage", change_type="modification",
            dependencies_json='["dep1"]', api_context=None, technology_context="Python",
            other_context=None, validation_state="unreviewed"
        )
        store.insert_applicability_scenario(scn)
        retrieved = store.get_applicability_scenario("scn-test")
        assert retrieved is not None
        assert retrieved.description == "Test"

    def test_scenario_expected_decisions(self, store):
        store.upsert_repository(RepositoryRecord("test-repo", "url", "test/repo", "main"))
        store.create_analysis_run(AnalysisRunRecord(
            run_id="run-test", repo_id="test-repo", repo_commit_sha="a"*40,
            mneme_version="0.9.1", mneme_commit_sha="b"*40,
            taxonomy_version="0.1", classifier_version="0.1",
            benchmark_schema_version="0.1", configuration_hash="config1",
            started_at=now_iso(), completed_at=None, status="running"
        ))
        store.insert_applicability_scenario(ApplicabilityScenarioRecord(
            scenario_id="scn-exp", repo_id="test-repo", description="Test",
            path=None, component=None, change_type=None, dependencies_json=None,
            api_context=None, technology_context=None, other_context=None,
            validation_state="unreviewed"
        ))
        # Insert decision candidates first (FK constraint)
        store.insert_decision_candidate(DecisionCandidateRecord(
            candidate_id="cand-1", run_id="run-test", source_id=None,
            source_location=None, raw_evidence_reference=None,
            normalized_decision="Decision 1", discovery_confidence=None, discovery_metadata_json=None
        ))
        store.insert_decision_candidate(DecisionCandidateRecord(
            candidate_id="cand-2", run_id="run-test", source_id=None,
            source_location=None, raw_evidence_reference=None,
            normalized_decision="Decision 2", discovery_confidence=None, discovery_metadata_json=None
        ))
        store.insert_scenario_expected_decision(ScenarioExpectedDecisionRecord(
            scenario_id="scn-exp", candidate_id="cand-1"
        ))
        store.insert_scenario_expected_decision(ScenarioExpectedDecisionRecord(
            scenario_id="scn-exp", candidate_id="cand-2"
        ))
        expected = store.list_scenario_expected_decisions("scn-exp")
        assert len(expected) == 2
        assert "cand-1" in expected
        assert "cand-2" in expected

    def test_scenario_results(self, store):
        store.upsert_repository(RepositoryRecord("test-repo", "url", "test/repo", "main"))
        store.create_analysis_run(AnalysisRunRecord(
            run_id="run-sr", repo_id="test-repo", repo_commit_sha="a"*40,
            mneme_version="0.9.1", mneme_commit_sha="b"*40,
            taxonomy_version="0.1", classifier_version="0.1",
            benchmark_schema_version="0.1", configuration_hash="config6",
            started_at=now_iso(), completed_at=None, status="running"
        ))
        store.insert_applicability_scenario(ApplicabilityScenarioRecord(
            scenario_id="scn-sr", repo_id="test-repo", description="Test",
            path=None, component=None, change_type=None, dependencies_json=None,
            api_context=None, technology_context=None, other_context=None,
            validation_state="unreviewed"
        ))
        # Insert decision candidate first (FK constraint)
        store.insert_decision_candidate(DecisionCandidateRecord(
            candidate_id="cand-1", run_id="run-sr", source_id=None,
            source_location=None, raw_evidence_reference=None,
            normalized_decision="Decision 1", discovery_confidence=None, discovery_metadata_json=None
        ))
        store.insert_scenario_result(ScenarioResultRecord(
            result_id="res-1", scenario_id="scn-sr", run_id="run-sr",
            classifier_version="0.1", applicability_version="0.1",
            precision=0.8, recall=0.7, f1=0.75, created_at=now_iso(),
            error_records_json=None
        ))
        store.insert_scenario_result_decision(ScenarioResultDecisionRecord(
            result_id="res-1", candidate_id="cand-1"
        ))
        results = store.list_scenario_results("scn-sr")
        assert len(results) == 1
        decisions = store.list_scenario_result_decisions("res-1")
        assert decisions == ["cand-1"]


class TestHelpers:
    def test_generate_id_format(self):
        id1 = generate_id("test-")
        assert id1.startswith("test-")
        assert len(id1) > 10

    def test_now_iso_format(self):
        ts = now_iso()
        assert ts.endswith("Z")
        assert "T" in ts