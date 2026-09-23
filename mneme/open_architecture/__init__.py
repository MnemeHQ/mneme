"""
mneme.open_architecture — Open Architecture (O1A) Research/Evaluation Harness Kernel.

This package provides the foundational infrastructure for the O1A benchmark harness.
It is a RESEARCH/EVALUATION HARNESS ONLY and is completely separate from:

- The existing Layer 1 `mneme benchmark`
- Canonical Decision Index writer
- DecisionProposal authority path
- Enforcement features
- D1B canonical persistence
- Retrieval redesign

Research data remains completely separate from authoritative project decisions.

The O1A harness MUST NOT write:
- .mneme/project_memory.json
- decision_index
- canonical decisions
- accepted proposals
- protection rules
- enforcement evidence

An inferred candidate is never authoritative or enforceable.

Submodules:
- manifest: Manifest model and validation (merged PR #389 Batch 01 structure)
- schemas: Decision Candidate & Applicability Scenario validation/serialization (merged JSON schemas)
- store: SQLite research store adapter (wraps merged research_store.sql)
- run_metadata: Reproducible run metadata with deterministic configuration hashing
- metrics: Governing Decision Set metrics (precision, recall, F1)
- errors: Bounded error taxonomy (15 categories)
"""

from mneme.open_architecture.manifest import (
    Manifest,
    RepositoryConfig,
    TargetsConfig,
    SamplingConfig,
)

from mneme.open_architecture.schemas import (
    DecisionCandidate,
    Scope,
    Relationship,
    ApplicabilityScenario,
    ChangeContext,
    validate_candidate,
    validate_scenario,
)

from mneme.open_architecture.store import (
    RESEARCH_STORE_SCHEMA_VERSION,
    ResearchStoreSchemaCompatibilityError,
    ResearchStore,
    RepositoryRecord,
    TaxonomyVersionRecord,
    ClassifierVersionRecord,
    AnalysisRunRecord,
    SourceDocumentRecord,
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

from mneme.open_architecture.run_metadata import (
    RunMetadata,
    get_environment_fingerprint,
)

from mneme.open_architecture.metrics import (
    GoverningDecisionSetMetrics,
    compute_suite_metrics,
)

from mneme.open_architecture.errors import (
    O1AErrorCategory,
    O1AError,
    VALID_ERROR_CATEGORIES,
    ERROR_CATEGORY_DESCRIPTIONS,
    validate_error_category,
    get_error_description,
)

from mneme.open_architecture.execution import (
    RepositoryCheckout,
    materialize_repository,
    RepositoryExecutionError,
    MissingCommitShaError,
    MalformedCommitShaError,
    GitUnavailableError,
    RepositoryCloneError,
    CommitUnavailableError,
    CheckoutError,
    ResolvedShaMismatchError,
    DirtyWorkingTreeError,
    RepositoryOriginMismatchError,
)

from mneme.open_architecture.discovery import (
    DOCUMENTATION_EXTENSIONS,
    DEFAULT_MAX_DOCUMENT_BYTES,
    DiscoveredSourceDocument,
    SourceDiscoveryDiagnostic,
    DiscoveryResult,
    discover_sources,
)

from mneme.open_architecture.candidates import (
    LineSpan,
    ExtractedCandidate,
    CandidateExtractor,
    HeuristicExtractor,
    build_decision_candidate,
)

from mneme.open_architecture.classification import (
    ClassifierTaskType,
    VALID_TASK_TYPES,
    ClassifierTask,
    ClassifierResult,
    SemanticClassifier,
    NormalizationError,
    normalize_classification,
    normalize_domains,
    normalize_purposes,
    normalize_authority,
    normalize_scopes,
    normalize_lifecycle,
    normalize_relationships,
    normalize_enforcement_potential,
    StaticClassifier,
    build_source_context,
    execute_classifier_batch,
)

from mneme.open_architecture.projection import (
    project_candidate_to_decision,
    project_candidates_to_decisions,
)

from mneme.open_architecture.gds_evaluation import (
    render_scenario_query,
    GoverningDecisionSetResult,
    evaluate_governing_decisions,
    evaluate_governing_decisions_batch,
    compute_suite_gds_metrics,
)

from mneme.open_architecture.orchestrator import (
    PreflightResult,
    IncompleteCandidateRecord,
    OpenArchitectureRunResult,
    preflight_open_architecture_analysis,
    run_open_architecture_analysis,
)

from mneme.open_architecture.export import (
    export_candidates_jsonl,
    import_candidates_jsonl,
    export_scenarios_jsonl,
    import_scenarios_jsonl,
    compute_bundle_content_hash,
    export_bundle,
)

from mneme.open_architecture.reporting import (
    generate_report,
    render_markdown_report,
)

__all__ = [
    # manifest
    "Manifest",
    "RepositoryConfig",
    "TargetsConfig",
    "SamplingConfig",
    # schemas
    "DecisionCandidate",
    "Scope",
    "Relationship",
    "ApplicabilityScenario",
    "ChangeContext",
    "validate_candidate",
    "validate_scenario",
    # store
    "RESEARCH_STORE_SCHEMA_VERSION",
    "ResearchStoreSchemaCompatibilityError",
    "ResearchStore",
    "RepositoryRecord",
    "TaxonomyVersionRecord",
    "ClassifierVersionRecord",
    "AnalysisRunRecord",
    "SourceDocumentRecord",
    "DecisionCandidateRecord",
    "CandidateClassificationRecord",
    "CandidateDomainRecord",
    "CandidatePurposeRecord",
    "CandidateAuthorityRecord",
    "CandidateScopeRecord",
    "CandidateLifecycleRecord",
    "CandidateRelationshipRecord",
    "EnforcementAssessmentRecord",
    "EvidenceRecord",
    "ApplicabilityScenarioRecord",
    "ScenarioExpectedDecisionRecord",
    "ScenarioResultRecord",
    "ScenarioResultDecisionRecord",
    "HumanReviewRecord",
    "ClassifierExecutionRecord",
    "ClassifierDisagreementRecord",
    "generate_id",
    "now_iso",
    # run_metadata
    "RunMetadata",
    "get_environment_fingerprint",
    # metrics
    "GoverningDecisionSetMetrics",
    "compute_suite_metrics",
    # errors
    "O1AErrorCategory",
    "O1AError",
    "VALID_ERROR_CATEGORIES",
    "ERROR_CATEGORY_DESCRIPTIONS",
    "validate_error_category",
    "get_error_description",
    # execution
    "RepositoryCheckout",
    "materialize_repository",
    "RepositoryExecutionError",
    "MissingCommitShaError",
    "MalformedCommitShaError",
    "GitUnavailableError",
    "RepositoryCloneError",
    "CommitUnavailableError",
    "CheckoutError",
    "ResolvedShaMismatchError",
    "DirtyWorkingTreeError",
    "RepositoryOriginMismatchError",
    # discovery
    "DOCUMENTATION_EXTENSIONS",
    "DEFAULT_MAX_DOCUMENT_BYTES",
    "DiscoveredSourceDocument",
    "SourceDiscoveryDiagnostic",
    "DiscoveryResult",
    "discover_sources",
    # candidates
    "LineSpan",
    "ExtractedCandidate",
    "CandidateExtractor",
    "HeuristicExtractor",
    "build_decision_candidate",
    # classification
    "ClassifierTaskType",
    "VALID_TASK_TYPES",
    "ClassifierTask",
    "ClassifierResult",
    "SemanticClassifier",
    "NormalizationError",
    "normalize_classification",
    "normalize_domains",
    "normalize_purposes",
    "normalize_authority",
    "normalize_scopes",
    "normalize_lifecycle",
    "normalize_relationships",
    "normalize_enforcement_potential",
    "StaticClassifier",
    "build_source_context",
    "execute_classifier_batch",
    # projection
    "project_candidate_to_decision",
    "project_candidates_to_decisions",
    # gds_evaluation
    "render_scenario_query",
    "GoverningDecisionSetResult",
    "evaluate_governing_decisions",
    "evaluate_governing_decisions_batch",
    "compute_suite_gds_metrics",
    # orchestrator
    "PreflightResult",
    "IncompleteCandidateRecord",
    "OpenArchitectureRunResult",
    "preflight_open_architecture_analysis",
    "run_open_architecture_analysis",
    # export
    "export_candidates_jsonl",
    "import_candidates_jsonl",
    "export_scenarios_jsonl",
    "import_scenarios_jsonl",
    "compute_bundle_content_hash",
    "export_bundle",
    # reporting
    "generate_report",
    "render_markdown_report",
]
