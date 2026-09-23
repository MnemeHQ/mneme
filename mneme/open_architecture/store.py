"""
SQLite Research Store Adapter for O1A Open Architecture Benchmark.

Wraps the merged research_store.sql from PR #389. Does not replace or simplify the schema.
- SQLite only, no ORM
- PRAGMA foreign_keys = ON on every connection
- Historical runs are append-preserving
- Completed runs cannot be silently overwritten
- Machine predictions remain stored after human correction
- Multiple classifier executions may exist for the same candidate
- Runtime *.sqlite state is uncommitted
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


# ── Load Merged Schema DDL ─────────────────────────────────────────────────────

_SCHEMA_PATH = Path(__file__).parent.parent.parent / "benchmarks" / "open_architecture" / "schema" / "research_store.sql"

def _load_schema_ddl() -> str:
    return _SCHEMA_PATH.read_text(encoding="utf-8")


# ── Data Classes for Store Records ──────────────────────────────────────────────

@dataclass(frozen=True)
class RepositoryRecord:
    repo_id: str
    repository_url: str
    repository_identifier: str
    default_branch: str | None


@dataclass(frozen=True)
class TaxonomyVersionRecord:
    taxonomy_version: str
    created_at: str
    notes: str | None


@dataclass(frozen=True)
class ClassifierVersionRecord:
    classifier_version: str
    created_at: str
    notes: str | None


@dataclass(frozen=True)
class AnalysisRunRecord:
    run_id: str
    repo_id: str
    repo_commit_sha: str
    mneme_version: str
    mneme_commit_sha: str
    taxonomy_version: str
    classifier_version: str
    benchmark_schema_version: str
    configuration_hash: str
    started_at: str
    completed_at: str | None
    status: str


@dataclass(frozen=True)
class SourceDocumentRecord:
    source_id: str
    run_id: str
    path: str
    source_type: str | None
    content_hash: str | None
    metadata_json: str | None


@dataclass(frozen=True)
class DecisionCandidateRecord:
    candidate_id: str
    run_id: str
    source_id: str | None
    source_location: str | None
    raw_evidence_reference: str | None
    normalized_decision: str
    discovery_confidence: float | None
    discovery_metadata_json: str | None


@dataclass(frozen=True)
class CandidateClassificationRecord:
    classification_id: str
    candidate_id: str
    run_id: str
    classification: str
    classifier_version: str
    taxonomy_version: str
    confidence: float | None
    rationale: str | None
    created_at: str


@dataclass(frozen=True)
class CandidateDomainRecord:
    candidate_id: str
    run_id: str
    domain: str
    confidence: float | None
    classifier_version: str


@dataclass(frozen=True)
class CandidatePurposeRecord:
    candidate_id: str
    run_id: str
    purpose: str
    confidence: float | None
    classifier_version: str


@dataclass(frozen=True)
class CandidateAuthorityRecord:
    candidate_id: str
    run_id: str
    authority_status: str
    authority_evidence: str | None
    confidence: float | None


@dataclass(frozen=True)
class CandidateScopeRecord:
    scope_id: str
    candidate_id: str
    run_id: str
    scope_type: str
    scope_expression: str | None
    confidence: float | None
    evidence_reference: str | None


@dataclass(frozen=True)
class CandidateLifecycleRecord:
    candidate_id: str
    run_id: str
    lifecycle_status: str
    supersedes: str | None
    superseded_by: str | None
    effective_date: str | None
    expiration_if_any: str | None
    confidence: float | None


@dataclass(frozen=True)
class CandidateRelationshipRecord:
    relationship_id: str
    run_id: str
    source_candidate_id: str
    relationship_type: str
    target_candidate_id: str | None
    target_reference: str | None
    confidence: float | None
    evidence_reference: str | None


@dataclass(frozen=True)
class EnforcementAssessmentRecord:
    candidate_id: str
    run_id: str
    enforcement_potential: str
    candidate_rule: str | None
    confidence: float | None


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    candidate_id: str
    run_id: str
    evidence_type: str
    path: str | None
    source_location: str | None
    snippet_or_reference: str | None
    relationship: str | None
    metadata_json: str | None


@dataclass(frozen=True)
class ApplicabilityScenarioRecord:
    scenario_id: str
    repo_id: str
    description: str
    path: str | None
    component: str | None
    change_type: str | None
    dependencies_json: str | None
    api_context: str | None
    technology_context: str | None
    other_context: str | None
    validation_state: str


@dataclass(frozen=True)
class ScenarioExpectedDecisionRecord:
    scenario_id: str
    candidate_id: str


@dataclass(frozen=True)
class ScenarioResultRecord:
    result_id: str
    scenario_id: str
    run_id: str
    classifier_version: str
    applicability_version: str | None
    precision: float | None
    recall: float | None
    f1: float | None
    created_at: str
    error_records_json: str | None


@dataclass(frozen=True)
class ScenarioResultDecisionRecord:
    result_id: str
    candidate_id: str


@dataclass(frozen=True)
class HumanReviewRecord:
    review_id: str
    candidate_id: str
    machine_run_id: str
    verdict: str
    corrected_decision: str | None
    corrected_classification: str | None
    corrected_authority: str | None
    corrected_scope_json: str | None
    corrected_lifecycle_json: str | None
    corrected_domains_json: str | None
    corrected_purposes_json: str | None
    corrected_relationships_json: str | None
    corrected_enforcement_json: str | None
    corrections_json: str | None
    reviewer: str | None
    reviewed_at: str
    notes: str | None


@dataclass(frozen=True)
class ClassifierExecutionRecord:
    execution_id: str
    candidate_id: str
    run_id: str
    classifier_backend: str
    classifier_version: str
    model_identifier: str | None
    taxonomy_version: str
    task_type: str
    output_json: str
    confidence: float | None
    latency_ms: float | None
    cost_amount: float | None
    cost_currency: str | None
    escalated: int
    created_at: str


@dataclass(frozen=True)
class ClassifierDisagreementRecord:
    disagreement_id: str
    candidate_id: str
    task_type: str
    execution_a_id: str
    execution_b_id: str
    disagreement_json: str
    resolved_by_review_id: str | None
    created_at: str


# ── Store Implementation ────────────────────────────────────────────────────────

class ResearchStore:
    """SQLite-backed research store for O1A benchmark data.

    Wraps the merged research_store.sql from PR #389. All connections enforce foreign keys.
    Schema is initialized from the merged DDL.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        """Get or create database connection with foreign keys enabled."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> ResearchStore:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Context manager for explicit transactions."""
        conn = self.connect()
        conn.execute("BEGIN")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def initialize_schema(self) -> None:
        """Initialize the database schema from merged DDL."""
        conn = self.connect()
        conn.executescript(_load_schema_ddl())
        conn.commit()

    # ── Repositories ────────────────────────────────────────────────────────

    def upsert_repository(self, repo: RepositoryRecord) -> None:
        """Insert or update repository."""
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO repositories (repo_id, repository_url, repository_identifier, default_branch)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(repo_id) DO UPDATE SET
                repository_url = excluded.repository_url,
                repository_identifier = excluded.repository_identifier,
                default_branch = excluded.default_branch
            """,
            (repo.repo_id, repo.repository_url, repo.repository_identifier, repo.default_branch),
        )
        conn.commit()

    def get_repository(self, repo_id: str) -> RepositoryRecord | None:
        conn = self.connect()
        row = conn.execute("SELECT * FROM repositories WHERE repo_id = ?", (repo_id,)).fetchone()
        if row is None:
            return None
        return RepositoryRecord(**dict(row))

    def get_repository_by_identifier(self, identifier: str) -> RepositoryRecord | None:
        conn = self.connect()
        row = conn.execute("SELECT * FROM repositories WHERE repository_identifier = ?", (identifier,)).fetchone()
        if row is None:
            return None
        return RepositoryRecord(**dict(row))

    # ── Taxonomy Versions ────────────────────────────────────────────────────

    def upsert_taxonomy_version(self, tv: TaxonomyVersionRecord) -> None:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO taxonomy_versions (taxonomy_version, created_at, notes)
            VALUES (?, ?, ?)
            ON CONFLICT(taxonomy_version) DO UPDATE SET
                created_at = excluded.created_at,
                notes = excluded.notes
            """,
            (tv.taxonomy_version, tv.created_at, tv.notes),
        )
        conn.commit()

    # ── Classifier Versions ──────────────────────────────────────────────────

    def upsert_classifier_version(self, cv: ClassifierVersionRecord) -> None:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO classifier_versions (classifier_version, created_at, notes)
            VALUES (?, ?, ?)
            ON CONFLICT(classifier_version) DO UPDATE SET
                created_at = excluded.created_at,
                notes = excluded.notes
            """,
            (cv.classifier_version, cv.created_at, cv.notes),
        )
        conn.commit()

    # ── Analysis Runs ────────────────────────────────────────────────────────

    def create_analysis_run(self, run: AnalysisRunRecord) -> None:
        """Insert a new analysis run. Fails if run with same identity exists (completed runs cannot be silently overwritten)."""
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO analysis_runs (
                run_id, repo_id, repo_commit_sha, mneme_version, mneme_commit_sha,
                taxonomy_version, classifier_version, benchmark_schema_version,
                configuration_hash, started_at, completed_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id, run.repo_id, run.repo_commit_sha, run.mneme_version,
                run.mneme_commit_sha, run.taxonomy_version, run.classifier_version,
                run.benchmark_schema_version, run.configuration_hash,
                run.started_at, run.completed_at, run.status
            ),
        )
        conn.commit()

    def get_analysis_run(self, run_id: str) -> AnalysisRunRecord | None:
        conn = self.connect()
        row = conn.execute("SELECT * FROM analysis_runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return AnalysisRunRecord(**dict(row))

    def get_analysis_run_by_identity(
        self, repo_id: str, mneme_commit_sha: str, configuration_hash: str
    ) -> AnalysisRunRecord | None:
        """Get run by its unique identity (repo, mneme commit, config hash)."""
        conn = self.connect()
        row = conn.execute(
            "SELECT * FROM analysis_runs WHERE repo_id = ? AND mneme_commit_sha = ? AND configuration_hash = ?",
            (repo_id, mneme_commit_sha, configuration_hash),
        ).fetchone()
        if row is None:
            return None
        return AnalysisRunRecord(**dict(row))

    def update_analysis_run_status(self, run_id: str, status: str, completed_at: str | None = None) -> None:
        conn = self.connect()
        if completed_at is not None:
            conn.execute(
                "UPDATE analysis_runs SET status = ?, completed_at = ? WHERE run_id = ?",
                (status, completed_at, run_id),
            )
        else:
            conn.execute("UPDATE analysis_runs SET status = ? WHERE run_id = ?", (status, run_id))
        conn.commit()

    def list_analysis_runs(self, repo_id: str | None = None) -> list[AnalysisRunRecord]:
        conn = self.connect()
        if repo_id:
            rows = conn.execute("SELECT * FROM analysis_runs WHERE repo_id = ? ORDER BY started_at", (repo_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM analysis_runs ORDER BY started_at").fetchall()
        return [AnalysisRunRecord(**dict(row)) for row in rows]

    # ── Source Documents ─────────────────────────────────────────────────────

    def insert_source_document(self, src: SourceDocumentRecord) -> None:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO source_documents (source_id, run_id, path, source_type, content_hash, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (src.source_id, src.run_id, src.path, src.source_type, src.content_hash, src.metadata_json),
        )
        conn.commit()

    # ── Decision Candidates ──────────────────────────────────────────────────

    def insert_decision_candidate(self, cand: DecisionCandidateRecord) -> None:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO decision_candidates (
                candidate_id, run_id, source_id, source_location,
                raw_evidence_reference, normalized_decision,
                discovery_confidence, discovery_metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(candidate_id, run_id) DO UPDATE SET
                source_id = excluded.source_id,
                source_location = excluded.source_location,
                raw_evidence_reference = excluded.raw_evidence_reference,
                normalized_decision = excluded.normalized_decision,
                discovery_confidence = excluded.discovery_confidence,
                discovery_metadata_json = excluded.discovery_metadata_json
            """,
            (
                cand.candidate_id, cand.run_id, cand.source_id, cand.source_location,
                cand.raw_evidence_reference, cand.normalized_decision,
                cand.discovery_confidence, cand.discovery_metadata_json,
            ),
        )
        conn.commit()

    def get_decision_candidate(self, candidate_id: str, run_id: str | None = None) -> DecisionCandidateRecord | None:
        conn = self.connect()
        if run_id is not None:
            row = conn.execute("SELECT * FROM decision_candidates WHERE candidate_id = ? AND run_id = ?", (candidate_id, run_id)).fetchone()
        else:
            row = conn.execute("SELECT * FROM decision_candidates WHERE candidate_id = ? ORDER BY rowid DESC LIMIT 1", (candidate_id,)).fetchone()
        if row is None:
            return None
        return DecisionCandidateRecord(**dict(row))

    def list_decision_candidates(self, run_id: str) -> list[DecisionCandidateRecord]:
        conn = self.connect()
        rows = conn.execute("SELECT * FROM decision_candidates WHERE run_id = ? ORDER BY candidate_id", (run_id,)).fetchall()
        return [DecisionCandidateRecord(**dict(row)) for row in rows]

    # ── Candidate Classifications ─────────────────────────────────────────────

    def insert_candidate_classification(self, cc: CandidateClassificationRecord) -> None:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO candidate_classifications (
                classification_id, candidate_id, run_id, classification,
                classifier_version, taxonomy_version, confidence, rationale, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cc.classification_id, cc.candidate_id, cc.run_id, cc.classification,
                cc.classifier_version, cc.taxonomy_version, cc.confidence,
                cc.rationale, cc.created_at,
            ),
        )
        conn.commit()

    def list_candidate_classifications(self, candidate_id: str) -> list[CandidateClassificationRecord]:
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM candidate_classifications WHERE candidate_id = ? ORDER BY created_at",
            (candidate_id,)
        ).fetchall()
        return [CandidateClassificationRecord(**dict(row)) for row in rows]

    # ── Candidate Domains ─────────────────────────────────────────────────────

    def insert_candidate_domain(self, cd: CandidateDomainRecord) -> None:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO candidate_domains (candidate_id, run_id, domain, confidence, classifier_version)
            VALUES (?, ?, ?, ?, ?)
            """,
            (cd.candidate_id, cd.run_id, cd.domain, cd.confidence, cd.classifier_version),
        )
        conn.commit()

    def list_candidate_domains(self, candidate_id: str, run_id: str) -> list[CandidateDomainRecord]:
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM candidate_domains WHERE candidate_id = ? AND run_id = ?",
            (candidate_id, run_id)
        ).fetchall()
        return [CandidateDomainRecord(**dict(row)) for row in rows]

    # ── Candidate Purposes ─────────────────────────────────────────────────────

    def insert_candidate_purpose(self, cp: CandidatePurposeRecord) -> None:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO candidate_purposes (candidate_id, run_id, purpose, confidence, classifier_version)
            VALUES (?, ?, ?, ?, ?)
            """,
            (cp.candidate_id, cp.run_id, cp.purpose, cp.confidence, cp.classifier_version),
        )
        conn.commit()

    def list_candidate_purposes(self, candidate_id: str, run_id: str) -> list[CandidatePurposeRecord]:
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM candidate_purposes WHERE candidate_id = ? AND run_id = ?",
            (candidate_id, run_id)
        ).fetchall()
        return [CandidatePurposeRecord(**dict(row)) for row in rows]

    # ── Candidate Authority ─────────────────────────────────────────────────────

    def upsert_candidate_authority(self, ca: CandidateAuthorityRecord) -> None:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO candidate_authority (candidate_id, run_id, authority_status, authority_evidence, confidence)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(candidate_id, run_id) DO UPDATE SET
                authority_status = excluded.authority_status,
                authority_evidence = excluded.authority_evidence,
                confidence = excluded.confidence
            """,
            (ca.candidate_id, ca.run_id, ca.authority_status, ca.authority_evidence, ca.confidence),
        )
        conn.commit()

    # ── Candidate Scopes ────────────────────────────────────────────────────────

    def insert_candidate_scope(self, cs: CandidateScopeRecord) -> None:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO candidate_scopes (scope_id, candidate_id, run_id, scope_type, scope_expression, confidence, evidence_reference)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (cs.scope_id, cs.candidate_id, cs.run_id, cs.scope_type, cs.scope_expression, cs.confidence, cs.evidence_reference),
        )
        conn.commit()

    def list_candidate_scopes(self, candidate_id: str, run_id: str) -> list[CandidateScopeRecord]:
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM candidate_scopes WHERE candidate_id = ? AND run_id = ?",
            (candidate_id, run_id)
        ).fetchall()
        return [CandidateScopeRecord(**dict(row)) for row in rows]

    # ── Candidate Lifecycle ─────────────────────────────────────────────────────

    def upsert_candidate_lifecycle(self, cl: CandidateLifecycleRecord) -> None:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO candidate_lifecycle (
                candidate_id, run_id, lifecycle_status, supersedes, superseded_by,
                effective_date, expiration_if_any, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(candidate_id, run_id) DO UPDATE SET
                lifecycle_status = excluded.lifecycle_status,
                supersedes = excluded.supersedes,
                superseded_by = excluded.superseded_by,
                effective_date = excluded.effective_date,
                expiration_if_any = excluded.expiration_if_any,
                confidence = excluded.confidence
            """,
            (
                cl.candidate_id, cl.run_id, cl.lifecycle_status, cl.supersedes,
                cl.superseded_by, cl.effective_date, cl.expiration_if_any, cl.confidence,
            ),
        )
        conn.commit()

    # ── Candidate Relationships ─────────────────────────────────────────────────

    def insert_candidate_relationship(self, cr: CandidateRelationshipRecord) -> None:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO candidate_relationships (
                relationship_id, run_id, source_candidate_id, relationship_type,
                target_candidate_id, target_reference, confidence, evidence_reference
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cr.relationship_id, cr.run_id, cr.source_candidate_id, cr.relationship_type,
                cr.target_candidate_id, cr.target_reference, cr.confidence, cr.evidence_reference,
            ),
        )
        conn.commit()

    def list_candidate_relationships(self, source_candidate_id: str, run_id: str) -> list[CandidateRelationshipRecord]:
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM candidate_relationships WHERE source_candidate_id = ? AND run_id = ?",
            (source_candidate_id, run_id)
        ).fetchall()
        return [CandidateRelationshipRecord(**dict(row)) for row in rows]

    # ── Enforcement Assessments ─────────────────────────────────────────────────

    def upsert_enforcement_assessment(self, ea: EnforcementAssessmentRecord) -> None:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO enforcement_assessments (candidate_id, run_id, enforcement_potential, candidate_rule, confidence)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(candidate_id, run_id) DO UPDATE SET
                enforcement_potential = excluded.enforcement_potential,
                candidate_rule = excluded.candidate_rule,
                confidence = excluded.confidence
            """,
            (ea.candidate_id, ea.run_id, ea.enforcement_potential, ea.candidate_rule, ea.confidence),
        )
        conn.commit()

    # ── Evidence ────────────────────────────────────────────────────────────────

    def insert_evidence(self, ev: EvidenceRecord) -> None:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO evidence (evidence_id, candidate_id, run_id, evidence_type, path, source_location, snippet_or_reference, relationship, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ev.evidence_id, ev.candidate_id, ev.run_id, ev.evidence_type, ev.path, ev.source_location, ev.snippet_or_reference, ev.relationship, ev.metadata_json),
        )
        conn.commit()

    def list_evidence(self, candidate_id: str, run_id: str) -> list[EvidenceRecord]:
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM evidence WHERE candidate_id = ? AND run_id = ?",
            (candidate_id, run_id)
        ).fetchall()
        return [EvidenceRecord(**dict(row)) for row in rows]

    # ── Applicability Scenarios ─────────────────────────────────────────────────

    def insert_applicability_scenario(self, scn: ApplicabilityScenarioRecord) -> None:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO applicability_scenarios (
                scenario_id, repo_id, description, path, component, change_type,
                dependencies_json, api_context, technology_context, other_context, validation_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scn.scenario_id, scn.repo_id, scn.description, scn.path, scn.component,
                scn.change_type, scn.dependencies_json, scn.api_context, scn.technology_context,
                scn.other_context, scn.validation_state,
            ),
        )
        conn.commit()

    def get_applicability_scenario(self, scenario_id: str) -> ApplicabilityScenarioRecord | None:
        conn = self.connect()
        row = conn.execute("SELECT * FROM applicability_scenarios WHERE scenario_id = ?", (scenario_id,)).fetchone()
        if row is None:
            return None
        return ApplicabilityScenarioRecord(**dict(row))

    def list_applicability_scenarios(self, repo_id: str) -> list[ApplicabilityScenarioRecord]:
        conn = self.connect()
        rows = conn.execute("SELECT * FROM applicability_scenarios WHERE repo_id = ? ORDER BY scenario_id", (repo_id,)).fetchall()
        return [ApplicabilityScenarioRecord(**dict(row)) for row in rows]

    # ── Scenario Expected Decisions ────────────────────────────────────────────

    def insert_scenario_expected_decision(self, sed: ScenarioExpectedDecisionRecord) -> None:
        conn = self.connect()
        conn.execute(
            "INSERT INTO scenario_expected_decisions (scenario_id, candidate_id) VALUES (?, ?)",
            (sed.scenario_id, sed.candidate_id),
        )
        conn.commit()

    def list_scenario_expected_decisions(self, scenario_id: str) -> list[str]:
        conn = self.connect()
        rows = conn.execute("SELECT candidate_id FROM scenario_expected_decisions WHERE scenario_id = ?", (scenario_id,)).fetchall()
        return [row[0] for row in rows]

    # ── Scenario Results ────────────────────────────────────────────────────────

    def insert_scenario_result(self, sr: ScenarioResultRecord) -> None:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO scenario_results (
                result_id, scenario_id, run_id, classifier_version, applicability_version,
                precision, recall, f1, created_at, error_records_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sr.result_id, sr.scenario_id, sr.run_id, sr.classifier_version,
                sr.applicability_version, sr.precision, sr.recall, sr.f1,
                sr.created_at, sr.error_records_json,
            ),
        )
        conn.commit()

    def get_scenario_result(self, result_id: str) -> ScenarioResultRecord | None:
        conn = self.connect()
        row = conn.execute("SELECT * FROM scenario_results WHERE result_id = ?", (result_id,)).fetchone()
        if row is None:
            return None
        return ScenarioResultRecord(**dict(row))

    def list_scenario_results(self, scenario_id: str) -> list[ScenarioResultRecord]:
        conn = self.connect()
        rows = conn.execute("SELECT * FROM scenario_results WHERE scenario_id = ? ORDER BY created_at", (scenario_id,)).fetchall()
        return [ScenarioResultRecord(**dict(row)) for row in rows]

    # ── Scenario Result Decisions ──────────────────────────────────────────────

    def insert_scenario_result_decision(self, srd: ScenarioResultDecisionRecord) -> None:
        conn = self.connect()
        conn.execute(
            "INSERT INTO scenario_result_decisions (result_id, candidate_id) VALUES (?, ?)",
            (srd.result_id, srd.candidate_id),
        )
        conn.commit()

    def list_scenario_result_decisions(self, result_id: str) -> list[str]:
        conn = self.connect()
        rows = conn.execute("SELECT candidate_id FROM scenario_result_decisions WHERE result_id = ?", (result_id,)).fetchall()
        return [row[0] for row in rows]

    # ── Human Reviews ────────────────────────────────────────────────────────────

    def insert_human_review(self, hr: HumanReviewRecord) -> None:
        """Insert a human review. Machine predictions are preserved; human correction creates new review record."""
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO human_reviews (
                review_id, candidate_id, machine_run_id, verdict,
                corrected_decision, corrected_classification, corrected_authority,
                corrected_scope_json, corrected_lifecycle_json, corrected_domains_json,
                corrected_purposes_json, corrected_relationships_json, corrected_enforcement_json,
                corrections_json, reviewer, reviewed_at, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hr.review_id, hr.candidate_id, hr.machine_run_id, hr.verdict,
                hr.corrected_decision, hr.corrected_classification, hr.corrected_authority,
                hr.corrected_scope_json, hr.corrected_lifecycle_json, hr.corrected_domains_json,
                hr.corrected_purposes_json, hr.corrected_relationships_json, hr.corrected_enforcement_json,
                hr.corrections_json, hr.reviewer, hr.reviewed_at, hr.notes,
            ),
        )
        conn.commit()

    def get_human_review(self, review_id: str) -> HumanReviewRecord | None:
        conn = self.connect()
        row = conn.execute("SELECT * FROM human_reviews WHERE review_id = ?", (review_id,)).fetchone()
        if row is None:
            return None
        return HumanReviewRecord(**dict(row))

    def list_human_reviews(self, candidate_id: str) -> list[HumanReviewRecord]:
        conn = self.connect()
        rows = conn.execute("SELECT * FROM human_reviews WHERE candidate_id = ? ORDER BY reviewed_at", (candidate_id,)).fetchall()
        return [HumanReviewRecord(**dict(row)) for row in rows]

    # ── Classifier Executions ────────────────────────────────────────────────────

    def insert_classifier_execution(self, ce: ClassifierExecutionRecord) -> None:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO classifier_executions (
                execution_id, candidate_id, run_id, classifier_backend, classifier_version,
                model_identifier, taxonomy_version, task_type, output_json, confidence,
                latency_ms, cost_amount, cost_currency, escalated, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ce.execution_id, ce.candidate_id, ce.run_id, ce.classifier_backend,
                ce.classifier_version, ce.model_identifier, ce.taxonomy_version,
                ce.task_type, ce.output_json, ce.confidence, ce.latency_ms,
                ce.cost_amount, ce.cost_currency, ce.escalated, ce.created_at,
            ),
        )
        conn.commit()

    def list_classifier_executions(self, candidate_id: str) -> list[ClassifierExecutionRecord]:
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM classifier_executions WHERE candidate_id = ? ORDER BY created_at",
            (candidate_id,)
        ).fetchall()
        return [ClassifierExecutionRecord(**dict(row)) for row in rows]

    # ── Classifier Disagreements ────────────────────────────────────────────────

    def insert_classifier_disagreement(self, cd: ClassifierDisagreementRecord) -> None:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO classifier_disagreements (
                disagreement_id, candidate_id, run_id, task_type, execution_a_id, execution_b_id,
                disagreement_json, resolved_by_review_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cd.disagreement_id, cd.candidate_id, cd.run_id, cd.task_type,
                cd.execution_a_id, cd.execution_b_id, cd.disagreement_json,
                cd.resolved_by_review_id, cd.created_at,
            ),
        )
        conn.commit()

    def list_classifier_disagreements(self, candidate_id: str, run_id: str) -> list[ClassifierDisagreementRecord]:
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM classifier_disagreements WHERE candidate_id = ? AND run_id = ? ORDER BY created_at",
            (candidate_id, run_id)
        ).fetchall()
        return [ClassifierDisagreementRecord(**dict(row)) for row in rows]


# ── Helper Functions ─────────────────────────────────────────────────────────────

def now_iso() -> str:
    """Current UTC time in ISO 8601 format."""
    return datetime.utcnow().isoformat() + "Z"


def generate_id(prefix: str) -> str:
    """Generate a deterministic-ish ID with prefix."""
    import hashlib
    import os
    import time
    data = f"{prefix}{time.time()}{os.urandom(16).hex()}"
    return f"{prefix}{hashlib.sha256(data.encode()).hexdigest()[:32]}"