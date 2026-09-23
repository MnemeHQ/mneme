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
]
