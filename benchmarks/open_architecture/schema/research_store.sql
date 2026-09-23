PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS repositories (
    repo_id TEXT PRIMARY KEY,
    repository_url TEXT NOT NULL,
    repository_identifier TEXT NOT NULL UNIQUE,
    default_branch TEXT
);

CREATE TABLE IF NOT EXISTS taxonomy_versions (
    taxonomy_version TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS classifier_versions (
    classifier_version TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL REFERENCES repositories(repo_id),
    repo_commit_sha TEXT NOT NULL,
    mneme_version TEXT NOT NULL,
    mneme_commit_sha TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL REFERENCES taxonomy_versions(taxonomy_version),
    classifier_version TEXT NOT NULL REFERENCES classifier_versions(classifier_version),
    benchmark_schema_version TEXT NOT NULL,
    configuration_hash TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_analysis_runs_repo ON analysis_runs(repo_id);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_versions ON analysis_runs(classifier_version, taxonomy_version);

CREATE TABLE IF NOT EXISTS source_documents (
    source_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id),
    path TEXT NOT NULL,
    source_type TEXT,
    content_hash TEXT,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS decision_candidates (
    candidate_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id),
    source_id TEXT REFERENCES source_documents(source_id),
    source_location TEXT,
    raw_evidence_reference TEXT,
    normalized_decision TEXT NOT NULL,
    discovery_confidence REAL,
    discovery_metadata_json TEXT,
    PRIMARY KEY (candidate_id, run_id)
);

CREATE TABLE IF NOT EXISTS candidate_classifications (
    classification_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id),
    classification TEXT NOT NULL CHECK (
        classification IN ('prescriptive','advisory','descriptive','historical','ambiguous')
    ),
    classifier_version TEXT NOT NULL REFERENCES classifier_versions(classifier_version),
    taxonomy_version TEXT NOT NULL REFERENCES taxonomy_versions(taxonomy_version),
    confidence REAL,
    rationale TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (candidate_id, run_id) REFERENCES decision_candidates(candidate_id, run_id)
);

CREATE TABLE IF NOT EXISTS candidate_domains (
    candidate_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id),
    domain TEXT NOT NULL,
    confidence REAL,
    classifier_version TEXT NOT NULL REFERENCES classifier_versions(classifier_version),
    PRIMARY KEY(candidate_id, run_id, domain),
    FOREIGN KEY (candidate_id, run_id) REFERENCES decision_candidates(candidate_id, run_id)
);

CREATE TABLE IF NOT EXISTS candidate_purposes (
    candidate_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id),
    purpose TEXT NOT NULL,
    confidence REAL,
    classifier_version TEXT NOT NULL REFERENCES classifier_versions(classifier_version),
    PRIMARY KEY(candidate_id, run_id, purpose),
    FOREIGN KEY (candidate_id, run_id) REFERENCES decision_candidates(candidate_id, run_id)
);

CREATE TABLE IF NOT EXISTS candidate_authority (
    candidate_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id),
    authority_status TEXT NOT NULL CHECK (
        authority_status IN ('candidate','explicitly_accepted','superseded','rejected','unknown')
    ),
    authority_evidence TEXT,
    confidence REAL,
    PRIMARY KEY(candidate_id, run_id),
    FOREIGN KEY (candidate_id, run_id) REFERENCES decision_candidates(candidate_id, run_id)
);

CREATE TABLE IF NOT EXISTS candidate_scopes (
    scope_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id),
    scope_type TEXT NOT NULL,
    scope_expression TEXT,
    confidence REAL,
    evidence_reference TEXT,
    FOREIGN KEY (candidate_id, run_id) REFERENCES decision_candidates(candidate_id, run_id)
);

CREATE TABLE IF NOT EXISTS candidate_lifecycle (
    candidate_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id),
    lifecycle_status TEXT NOT NULL CHECK (
        lifecycle_status IN ('active','superseded','deprecated','temporary','unknown')
    ),
    supersedes TEXT,
    superseded_by TEXT,
    effective_date TEXT,
    expiration_if_any TEXT,
    confidence REAL,
    PRIMARY KEY(candidate_id, run_id),
    FOREIGN KEY (candidate_id, run_id) REFERENCES decision_candidates(candidate_id, run_id)
);

CREATE TABLE IF NOT EXISTS candidate_relationships (
    relationship_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id),
    source_candidate_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL CHECK (
        relationship_type IN ('requires','prohibits','depends_on','refines','conflicts_with','supersedes','exception_to')
    ),
    target_candidate_id TEXT,
    target_reference TEXT,
    confidence REAL,
    evidence_reference TEXT,
    FOREIGN KEY (source_candidate_id, run_id) REFERENCES decision_candidates(candidate_id, run_id)
);

CREATE TABLE IF NOT EXISTS enforcement_assessments (
    candidate_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id),
    enforcement_potential TEXT NOT NULL CHECK (
        enforcement_potential IN (
            'deterministic_rule','contextual_guidance','warning','block',
            'not_mechanically_enforceable','unknown'
        )
    ),
    candidate_rule TEXT,
    confidence REAL,
    PRIMARY KEY(candidate_id, run_id),
    FOREIGN KEY (candidate_id, run_id) REFERENCES decision_candidates(candidate_id, run_id)
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id),
    evidence_type TEXT NOT NULL,
    path TEXT,
    source_location TEXT,
    snippet_or_reference TEXT,
    relationship TEXT,
    metadata_json TEXT,
    FOREIGN KEY (candidate_id, run_id) REFERENCES decision_candidates(candidate_id, run_id)
);

CREATE TABLE IF NOT EXISTS applicability_scenarios (
    scenario_id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL REFERENCES repositories(repo_id),
    description TEXT NOT NULL,
    path TEXT,
    component TEXT,
    change_type TEXT,
    dependencies_json TEXT,
    api_context TEXT,
    technology_context TEXT,
    other_context TEXT,
    validation_state TEXT NOT NULL DEFAULT 'unreviewed'
);

CREATE TABLE IF NOT EXISTS scenario_expected_decisions (
    scenario_id TEXT NOT NULL REFERENCES applicability_scenarios(scenario_id),
    candidate_id TEXT NOT NULL,
    PRIMARY KEY(scenario_id, candidate_id)
);

CREATE TABLE IF NOT EXISTS scenario_results (
    result_id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL REFERENCES applicability_scenarios(scenario_id),
    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id),
    classifier_version TEXT NOT NULL REFERENCES classifier_versions(classifier_version),
    applicability_version TEXT,
    precision REAL,
    recall REAL,
    f1 REAL,
    created_at TEXT NOT NULL,
    error_records_json TEXT
);

CREATE TABLE IF NOT EXISTS scenario_result_decisions (
    result_id TEXT NOT NULL REFERENCES scenario_results(result_id),
    candidate_id TEXT NOT NULL,
    PRIMARY KEY(result_id, candidate_id)
);

CREATE TABLE IF NOT EXISTS human_reviews (
    review_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    machine_run_id TEXT NOT NULL REFERENCES analysis_runs(run_id),
    verdict TEXT NOT NULL CHECK (
        verdict IN ('correct','partially_correct','incorrect','ambiguous')
    ),
    corrected_decision TEXT,
    corrected_classification TEXT,
    corrected_authority TEXT,
    corrected_scope_json TEXT,
    corrected_lifecycle_json TEXT,
    corrected_domains_json TEXT,
    corrected_purposes_json TEXT,
    corrected_relationships_json TEXT,
    corrected_enforcement_json TEXT,
    corrections_json TEXT,
    reviewer TEXT,
    reviewed_at TEXT NOT NULL,
    notes TEXT,
    FOREIGN KEY (candidate_id, machine_run_id) REFERENCES decision_candidates(candidate_id, run_id)
);

CREATE TABLE IF NOT EXISTS classifier_executions (
    execution_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id),
    classifier_backend TEXT NOT NULL,
    classifier_version TEXT NOT NULL,
    model_identifier TEXT,
    taxonomy_version TEXT NOT NULL REFERENCES taxonomy_versions(taxonomy_version),
    task_type TEXT NOT NULL,
    output_json TEXT NOT NULL,
    confidence REAL,
    latency_ms REAL,
    cost_amount REAL,
    cost_currency TEXT,
    escalated INTEGER NOT NULL DEFAULT 0 CHECK (escalated IN (0,1)),
    created_at TEXT NOT NULL,
    FOREIGN KEY (candidate_id, run_id) REFERENCES decision_candidates(candidate_id, run_id)
);

CREATE INDEX IF NOT EXISTS idx_classifier_exec_candidate
ON classifier_executions(candidate_id, run_id);

CREATE INDEX IF NOT EXISTS idx_classifier_exec_backend
ON classifier_executions(classifier_backend, classifier_version);

CREATE TABLE IF NOT EXISTS classifier_disagreements (
    disagreement_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    execution_a_id TEXT NOT NULL REFERENCES classifier_executions(execution_id),
    execution_b_id TEXT NOT NULL REFERENCES classifier_executions(execution_id),
    disagreement_json TEXT NOT NULL,
    resolved_by_review_id TEXT REFERENCES human_reviews(review_id),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reviews_candidate ON human_reviews(candidate_id, machine_run_id);
CREATE INDEX IF NOT EXISTS idx_scenario_results_scenario ON scenario_results(scenario_id);
