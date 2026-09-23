"""Tests for O1A SQLite Research Store (wraps merged research_store.sql)."""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
from pathlib import Path
import pytest

from mneme.open_architecture.store import (
    RESEARCH_STORE_SCHEMA_VERSION,
    ResearchStoreSchemaCompatibilityError,
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


class TestSchemaCompatibilityGuard:
    # 1. fresh ResearchStore initializes successfully
    def test_fresh_store_initializes_successfully(self, tmp_path: Path):
        db_path = tmp_path / "fresh.sqlite"
        store = ResearchStore(db_path)
        store.initialize_schema()
        assert db_path.is_file()
        conn = store.connect()
        user_ver = conn.execute("PRAGMA user_version").fetchone()[0]
        assert user_ver == RESEARCH_STORE_SCHEMA_VERSION

    # 2. corrected ResearchStore can reopen successfully
    def test_corrected_store_reopens_successfully(self, tmp_path: Path):
        db_path = tmp_path / "reopen.sqlite"
        store = ResearchStore(db_path)
        store.initialize_schema()
        store.close()

        # Reopen with new instance
        store2 = ResearchStore(db_path)
        conn = store2.connect()
        assert conn is not None
        store2.close()

    # 3. repeated initialize_schema() is idempotent
    def test_repeated_initialize_schema_is_idempotent(self, tmp_path: Path):
        db_path = tmp_path / "idempotent.sqlite"
        store = ResearchStore(db_path)
        store.initialize_schema()
        # Second call must succeed without error
        store.initialize_schema()
        # Third call must succeed without error
        store.initialize_schema()
        store.close()

    # 4. a fixture using the old candidate_id PRIMARY KEY schema is rejected
    # 5. rejection has a clear actionable error
    # 6. incompatible DB is not mutated or deleted
    def test_old_single_pk_schema_rejected_fail_closed(self, tmp_path: Path):
        old_db_path = tmp_path / "old_schema.sqlite"
        conn = sqlite3.connect(old_db_path)
        # Create table using old single-column candidate_id PK
        conn.execute("""
            CREATE TABLE decision_candidates (
                candidate_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                source_id TEXT,
                source_location TEXT,
                raw_evidence_reference TEXT,
                normalized_decision TEXT NOT NULL,
                discovery_confidence REAL,
                discovery_metadata_json TEXT
            );
        """)
        conn.execute("""
            INSERT INTO decision_candidates VALUES (
                'cand-old-1', 'run-old-1', NULL, 'L1', 'raw', 'Old decision', 1.0, NULL
            );
        """)
        conn.commit()
        conn.close()

        hash_before = hashlib.sha256(old_db_path.read_bytes()).hexdigest()
        size_before = old_db_path.stat().st_size

        store = ResearchStore(old_db_path)
        with pytest.raises(ResearchStoreSchemaCompatibilityError) as exc_info:
            store.initialize_schema()

        err_msg = str(exc_info.value)
        # 5. Rejection has clear actionable error
        assert "incompatible pre-O1A2 development schema" in err_msg
        assert "decision_candidates" in err_msg
        assert "composite primary key ('candidate_id', 'run_id')" in err_msg
        assert "Recreate the local research database" in err_msg

        # 6. Incompatible DB is not deleted and not mutated
        assert old_db_path.is_file()
        assert old_db_path.stat().st_size == size_before
        assert hashlib.sha256(old_db_path.read_bytes()).hexdigest() == hash_before

        # Verify old row is intact
        conn_check = sqlite3.connect(old_db_path)
        row = conn_check.execute("SELECT candidate_id, normalized_decision FROM decision_candidates").fetchone()
        conn_check.close()
        assert row == ("cand-old-1", "Old decision")

    # 7. corrected composite candidate PK is detected correctly
    def test_composite_candidate_pk_detected_correctly(self, tmp_path: Path):
        db_path = tmp_path / "composite.sqlite"
        store = ResearchStore(db_path)
        store.initialize_schema()

        conn = store.connect()
        info = conn.execute("PRAGMA table_info(decision_candidates)").fetchall()
        pk_cols = [r["name"] for r in sorted([r for r in info if r["pk"] > 0], key=lambda r: r["pk"])]
        assert pk_cols == ["candidate_id", "run_id"]
        store.close()

    # 8. multi-run candidate coexistence test still passes
    def test_multi_run_candidate_coexistence(self, tmp_path: Path):
        db_path = tmp_path / "multi_run.sqlite"
        store = ResearchStore(db_path)
        store.initialize_schema()

        store.upsert_repository(RepositoryRecord("repo-1", "https://github.com/org/repo", "org/repo", "main"))
        store.upsert_taxonomy_version(TaxonomyVersionRecord("0.1", now_iso(), "test"))
        store.upsert_classifier_version(ClassifierVersionRecord("0.1", now_iso(), "test"))

        # Run 1
        store.create_analysis_run(AnalysisRunRecord(
            run_id="run-1", repo_id="repo-1", repo_commit_sha="a"*40,
            mneme_version="0.9.2", mneme_commit_sha="b"*40,
            taxonomy_version="0.1", classifier_version="0.1",
            benchmark_schema_version="0.1", configuration_hash="hash1",
            started_at=now_iso(), completed_at=None, status="completed",
        ))
        # Run 2
        store.create_analysis_run(AnalysisRunRecord(
            run_id="run-2", repo_id="repo-1", repo_commit_sha="a"*40,
            mneme_version="0.9.2", mneme_commit_sha="b"*40,
            taxonomy_version="0.1", classifier_version="0.1",
            benchmark_schema_version="0.1", configuration_hash="hash2",
            started_at=now_iso(), completed_at=None, status="completed",
        ))

        # Same candidate ID in both runs
        cand1 = DecisionCandidateRecord("cand-shared", "run-1", None, "L1-5", "stmt", "Dec 1", 0.9, None)
        cand2 = DecisionCandidateRecord("cand-shared", "run-2", None, "L1-5", "stmt", "Dec 2", 0.95, None)

        store.insert_decision_candidate(cand1)
        store.insert_decision_candidate(cand2)

        # Both records coexist
        cands_run1 = store.list_decision_candidates("run-1")
        cands_run2 = store.list_decision_candidates("run-2")
        assert len(cands_run1) == 1
        assert len(cands_run2) == 1
        assert cands_run1[0].candidate_id == "cand-shared"
        assert cands_run2[0].candidate_id == "cand-shared"
        assert cands_run1[0].normalized_decision == "Dec 1"
        assert cands_run2[0].normalized_decision == "Dec 2"
        store.close()

    # 9. foreign-key enforcement remains enabled
    def test_foreign_keys_remain_enabled(self, tmp_path: Path):
        db_path = tmp_path / "fk_test.sqlite"
        store = ResearchStore(db_path)
        store.initialize_schema()

        conn = store.connect()
        fk_on = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk_on == 1

        # Attempting insert with non-existent foreign key must fail
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO analysis_runs VALUES ('r1', 'nonexistent_repo', 'sha', 'v', 'sha', '0.1', '0.1', '0.1', 'h', 't', NULL, 'running')"
            )
        store.close()

    # 10. no canonical Mneme persistence behavior is involved
    def test_no_canonical_persistence_involved(self, tmp_path: Path):
        db_path = tmp_path / "research_only.sqlite"
        store = ResearchStore(db_path)
        store.initialize_schema()

        # Verify no .mneme/ directory created
        assert not (tmp_path / ".mneme").exists()

        # Verify no canonical tables exist
        conn = store.connect()
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "decisions" not in tables
        assert "decision_index" not in tables
        assert "project_memory" not in tables
        store.close()
