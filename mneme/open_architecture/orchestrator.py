"""
mneme.open_architecture.orchestrator — Research run orchestration.

Coordinates the full O1A pipeline:
1. Pinned repository validation
2. Run metadata generation with deterministic configuration hashing
3. Preflight check if dry_run=True (PreflightResult)
4. Isolated repository materialization (materialize_repository)
5. Deterministic source discovery (discover_sources)
6. Candidate evidence extraction (CandidateExtractor)
7. Explicit semantic classification (SemanticClassifier)
8. Fail-closed vocabulary normalization
9. Research DecisionCandidate composition
10. Governing Decision Set retrieval evaluation (frozen DecisionRetriever)
11. ResearchStore persistence (merged PR #389 schema)

Critical Architecture Rules:
- Research only: never writes to canonical MemoryStore, DecisionIndex, or DecisionProposal.
- No default model provider: extractor and classifier must be explicitly injected.
- Incomplete classification fails closed without inventing labels or dropping candidates.
- Historical runs are append-preserving: completed runs cannot be overwritten.
- Expected scenario labels are immutable reference truth; misses are retained and measurable.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mneme.open_architecture.candidates import (
    CandidateExtractor,
    ExtractedCandidate,
    LineSpan,
    build_decision_candidate,
)
from mneme.open_architecture.classification import (
    ClassifierResult,
    ClassifierTask,
    ClassifierTaskType,
    NormalizationError,
    SemanticClassifier,
    build_source_context,
    execute_classifier_batch,
    normalize_authority,
    normalize_classification,
    normalize_domains,
    normalize_enforcement_potential,
    normalize_lifecycle,
    normalize_purposes,
    normalize_relationships,
    normalize_scopes,
)
from mneme.open_architecture.discovery import (
    DiscoveredSourceDocument,
    DiscoveryResult,
    discover_sources,
)
from mneme.open_architecture.execution import (
    RepositoryCheckout,
    RepositoryExecutionError,
    materialize_repository,
)
from mneme.open_architecture.gds_evaluation import (
    GoverningDecisionSetResult,
    compute_suite_gds_metrics,
    evaluate_governing_decisions_batch,
)
from mneme.open_architecture.manifest import Manifest, RepositoryConfig
from mneme.open_architecture.run_metadata import RunMetadata
from mneme.open_architecture.schemas import (
    ApplicabilityScenario,
    DecisionCandidate,
)
from mneme.open_architecture.store import (
    AnalysisRunRecord,
    ApplicabilityScenarioRecord,
    CandidateAuthorityRecord,
    CandidateClassificationRecord,
    CandidateDomainRecord,
    CandidateLifecycleRecord,
    CandidatePurposeRecord,
    CandidateRelationshipRecord,
    CandidateScopeRecord,
    ClassifierExecutionRecord,
    ClassifierVersionRecord,
    DecisionCandidateRecord,
    EnforcementAssessmentRecord,
    RepositoryRecord,
    ResearchStore,
    ScenarioExpectedDecisionRecord,
    ScenarioResultDecisionRecord,
    ScenarioResultRecord,
    SourceDocumentRecord,
    TaxonomyVersionRecord,
    now_iso,
)


# ── Run Result & Preflight Models ──────────────────────────────────────────────


@dataclass(frozen=True)
class PreflightResult:
    """Immutable result of an O1A execution preflight check.

    Validates configuration, manifest, repository pinning, and input descriptors
    without performing git clone, semantic classification, or claiming analysis completed.
    """

    repository_config: RepositoryConfig
    manifest_config_hash: str
    execution_config_hash: str
    classifier_backend: str
    classifier_version: str
    classifier_model: str | None
    extractor_id: str
    extractor_version: str
    scenario_count: int
    scenario_content_hash: str
    status: str = "preflight_ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "repository": self.repository_config.github,
            "commit_sha": self.repository_config.commit_sha,
            "manifest_config_hash": self.manifest_config_hash,
            "execution_config_hash": self.execution_config_hash,
            "classifier_backend": self.classifier_backend,
            "classifier_version": self.classifier_version,
            "classifier_model": self.classifier_model,
            "extractor_id": self.extractor_id,
            "extractor_version": self.extractor_version,
            "scenario_count": self.scenario_count,
            "scenario_content_hash": self.scenario_content_hash,
        }


@dataclass(frozen=True)
class IncompleteCandidateRecord:
    """Record of a candidate whose semantic classification was incomplete."""

    candidate_id: str
    source_path: str
    raw_statement: str
    missing_or_failed_dimensions: tuple[str, ...]
    errors: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "source_path": self.source_path,
            "raw_statement": self.raw_statement,
            "missing_or_failed_dimensions": list(self.missing_or_failed_dimensions),
            "errors": dict(self.errors),
        }


@dataclass(frozen=True)
class OpenArchitectureRunResult:
    """Complete, immutable output of an Open Architecture analysis run."""

    run_metadata: RunMetadata
    repository_config: RepositoryConfig
    discovered_documents: tuple[DiscoveredSourceDocument, ...]
    extracted_candidates: tuple[ExtractedCandidate, ...]
    composed_candidates: tuple[DecisionCandidate, ...]
    incomplete_candidates: tuple[IncompleteCandidateRecord, ...]
    classifier_results: tuple[ClassifierResult, ...]
    scenarios: tuple[ApplicabilityScenario, ...]
    gds_results: tuple[GoverningDecisionSetResult, ...]
    suite_metrics: dict[str, float]
    diagnostics: tuple[Any, ...]

    @property
    def is_completed(self) -> bool:
        return self.run_metadata.status == "completed"

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_metadata.run_id,
            "status": self.run_metadata.status,
            "repository": self.repository_config.github,
            "commit_sha": self.repository_config.commit_sha,
            "configuration_hash": self.run_metadata.configuration_hash,
            "discovered_documents_count": len(self.discovered_documents),
            "extracted_candidates_count": len(self.extracted_candidates),
            "composed_candidates_count": len(self.composed_candidates),
            "incomplete_candidates_count": len(self.incomplete_candidates),
            "scenarios_count": len(self.scenarios),
            "suite_metrics": dict(self.suite_metrics),
        }


# ── Scenario Content Hashing Helper ───────────────────────────────────────────


def _compute_scenario_content_hash(scenarios: list[ApplicabilityScenario]) -> str:
    """Compute deterministic hash of the entire scenario corpus.

    Binds full scenario semantics: description, path, component, change_type,
    dependencies, api, technology, other_context, expected_governing_decision_ids,
    and validation_state.
    """
    if not scenarios:
        return "none"
    canonical_list = []
    for s in sorted(scenarios, key=lambda sc: sc.scenario_id):
        canonical_list.append(
            {
                "api": s.change_context.api,
                "change_type": s.change_context.change_type,
                "component": s.change_context.component,
                "dependencies": sorted(list(s.change_context.dependencies)),
                "description": s.description,
                "expected_governing_decision_ids": sorted(list(s.expected_governing_decision_ids)),
                "other_context": s.change_context.other_context,
                "path": s.change_context.path,
                "repository": s.repository,
                "scenario_id": s.scenario_id,
                "technology": s.change_context.technology,
                "validation_state": s.validation_state,
            }
        )
    canonical_json = json.dumps(canonical_list, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:32]


# ── Preflight / Validation Function ───────────────────────────────────────────


def preflight_open_architecture_analysis(
    *,
    repository_config: RepositoryConfig,
    manifest: Manifest,
    extractor: CandidateExtractor,
    classifier: SemanticClassifier,
    scenarios: list[ApplicabilityScenario] | None = None,
    taxonomy_version: str = "0.1",
    benchmark_schema_version: str = "0.1",
) -> PreflightResult:
    """Execute preflight validation without git clone or classification."""
    if extractor is None:
        raise ValueError("extractor must be explicitly provided (no hidden default)")
    if classifier is None:
        raise ValueError("classifier must be explicitly provided (no hidden default)")

    if repository_config.commit_sha is None or not repository_config.commit_sha.strip():
        raise ValueError(
            f"Repository '{repository_config.id}' ({repository_config.github}) must have a pinned commit_sha"
        )

    scenarios_list = list(scenarios or [])
    scenario_content_hash = _compute_scenario_content_hash(scenarios_list)
    extractor_id = getattr(extractor, "extractor_id", type(extractor).__name__)
    extractor_version = getattr(extractor, "extractor_version", "0.1")

    run_meta = RunMetadata.create(
        batch_id=manifest.batch_id,
        repo_id=repository_config.id,
        repo_commit_sha=repository_config.commit_sha,
        benchmark_schema_version=benchmark_schema_version,
        taxonomy_version=taxonomy_version,
        classifier_version=classifier.classifier_version,
        classifier_backend=classifier.backend_id,
        classifier_model=classifier.model_identifier,
        extractor_id=extractor_id,
        extractor_version=extractor_version,
        scenario_content_hash=scenario_content_hash,
        retrieval_policy="score_gt_zero",
        manifest_config_hash=manifest.configuration_hash(),
    )

    return PreflightResult(
        repository_config=repository_config,
        manifest_config_hash=manifest.configuration_hash(),
        execution_config_hash=run_meta.configuration_hash,
        classifier_backend=classifier.backend_id,
        classifier_version=classifier.classifier_version,
        classifier_model=classifier.model_identifier,
        extractor_id=extractor_id,
        extractor_version=extractor_version,
        scenario_count=len(scenarios_list),
        scenario_content_hash=scenario_content_hash,
    )


# ── Orchestrator Implementation ────────────────────────────────────────────────


def run_open_architecture_analysis(
    *,
    repository_config: RepositoryConfig,
    manifest: Manifest,
    extractor: CandidateExtractor,
    classifier: SemanticClassifier,
    scenarios: list[ApplicabilityScenario] | None = None,
    research_store: ResearchStore | None = None,
    workspace_dir: str | Path | None = None,
    clone_source: str | Path | None = None,
    taxonomy_version: str = "0.1",
    benchmark_schema_version: str = "0.1",
    timeout: float = 60.0,
    dry_run: bool = False,
) -> OpenArchitectureRunResult | PreflightResult:
    """Execute an Open Architecture research run over a pinned repository.

    Coordinates all stages using dependency-injected components.
    Does not write to canonical Mneme state.

    Args:
        repository_config: Repository to analyze with an exact 40-character commit SHA.
        manifest: Batch manifest providing configuration hash and targets.
        extractor: Explicit CandidateExtractor implementation.
        classifier: Explicit SemanticClassifier implementation.
        scenarios: Optional applicability scenarios for GDS evaluation.
        research_store: Optional SQLite ResearchStore for persistence.
        workspace_dir: Optional caller-owned directory for checkout workspace.
        clone_source: Optional local directory or URL to clone from (offline testing).
        taxonomy_version: Version of the O1A research taxonomy.
        benchmark_schema_version: Version of the benchmark schema.
        timeout: Subprocess timeout in seconds.
        dry_run: If True, validate preflight without executing git clone or classification.

    Returns:
        OpenArchitectureRunResult on full execution, or PreflightResult on dry_run.

    Raises:
        RepositoryExecutionError: If repository materialization fails.
        ValueError: If configuration, extractor, or classifier is invalid.
    """
    if extractor is None:
        raise ValueError("extractor must be explicitly provided (no hidden default)")
    if classifier is None:
        raise ValueError("classifier must be explicitly provided (no hidden default)")

    scenarios_list = list(scenarios or [])

    # Preflight / Dry Run check
    if dry_run:
        return preflight_open_architecture_analysis(
            repository_config=repository_config,
            manifest=manifest,
            extractor=extractor,
            classifier=classifier,
            scenarios=scenarios_list,
            taxonomy_version=taxonomy_version,
            benchmark_schema_version=benchmark_schema_version,
        )

    # 1. Validate pinned commit SHA
    if repository_config.commit_sha is None or not repository_config.commit_sha.strip():
        raise ValueError(
            f"Repository '{repository_config.id}' ({repository_config.github}) must have a pinned commit_sha"
        )

    # 2. Create RunMetadata with complete execution configuration identity
    scenario_content_hash = _compute_scenario_content_hash(scenarios_list)
    extractor_id = getattr(extractor, "extractor_id", type(extractor).__name__)
    extractor_version = getattr(extractor, "extractor_version", "0.1")

    run_meta = RunMetadata.create(
        batch_id=manifest.batch_id,
        repo_id=repository_config.id,
        repo_commit_sha=repository_config.commit_sha,
        benchmark_schema_version=benchmark_schema_version,
        taxonomy_version=taxonomy_version,
        classifier_version=classifier.classifier_version,
        classifier_backend=classifier.backend_id,
        classifier_model=classifier.model_identifier,
        extractor_id=extractor_id,
        extractor_version=extractor_version,
        scenario_content_hash=scenario_content_hash,
        retrieval_policy="score_gt_zero",
        manifest_config_hash=manifest.configuration_hash(),
    )

    # 3. Initialize ResearchStore run if provided
    if research_store is not None:
        # Check if an identical completed run already exists (do not overwrite)
        existing_run = research_store.get_analysis_run_by_identity(
            repo_id=repository_config.id,
            mneme_commit_sha=run_meta.mneme_commit_sha,
            configuration_hash=run_meta.configuration_hash,
        )
        if existing_run is not None and existing_run.status == "completed":
            raise ValueError(
                f"Completed analysis run already exists for repo '{repository_config.id}', "
                f"commit '{run_meta.mneme_commit_sha}', and config hash '{run_meta.configuration_hash}'."
            )

        # Upsert reference entities
        research_store.upsert_repository(
            RepositoryRecord(
                repo_id=repository_config.id,
                repository_url=f"https://github.com/{repository_config.github}.git",
                repository_identifier=repository_config.github,
                default_branch=None,
            )
        )
        research_store.upsert_taxonomy_version(
            TaxonomyVersionRecord(
                taxonomy_version=taxonomy_version,
                created_at=now_iso(),
                notes="O1A taxonomy",
            )
        )
        research_store.upsert_classifier_version(
            ClassifierVersionRecord(
                classifier_version=classifier.classifier_version,
                created_at=now_iso(),
                notes=f"backend={classifier.backend_id}, model={classifier.model_identifier}",
            )
        )
        research_store.create_analysis_run(
            AnalysisRunRecord(
                run_id=run_meta.run_id,
                repo_id=repository_config.id,
                repo_commit_sha=repository_config.commit_sha,
                mneme_version=run_meta.mneme_version,
                mneme_commit_sha=run_meta.mneme_commit_sha,
                taxonomy_version=taxonomy_version,
                classifier_version=classifier.classifier_version,
                benchmark_schema_version=benchmark_schema_version,
                configuration_hash=run_meta.configuration_hash,
                started_at=run_meta.started_at,
                completed_at=None,
                status="running",
            )
        )

    all_diagnostics: list[Any] = []

    try:
        # 4. Materialize repository at pinned commit SHA
        with materialize_repository(
            repository_config,
            workspace_dir=workspace_dir,
            clone_source=clone_source,
            timeout=timeout,
        ) as checkout:

            # 5. Discover sources
            discovery_result = discover_sources(checkout)
            all_diagnostics.extend(discovery_result.diagnostics)
            docs = discovery_result.documents

            # Store source documents in ResearchStore
            doc_source_id_map: dict[str, str] = {}
            doc_by_path: dict[str, DiscoveredSourceDocument] = {}
            for doc in docs:
                doc_by_path[doc.relative_path] = doc
                source_id = f"src-{hashlib.sha256(f'{run_meta.run_id}:{doc.relative_path}'.encode()).hexdigest()[:32]}"
                doc_source_id_map[doc.relative_path] = source_id
                if research_store is not None:
                    research_store.insert_source_document(
                        SourceDocumentRecord(
                            source_id=source_id,
                            run_id=run_meta.run_id,
                            path=doc.relative_path,
                            source_type=doc.source_type,
                            content_hash=doc.content_hash,
                            metadata_json=json.dumps(doc.metadata, sort_keys=True),
                        )
                    )

            # 6. Extract candidate evidence spans
            extracted_candidates: list[ExtractedCandidate] = []
            for doc in docs:
                cands = extractor.extract(doc, repository_config.commit_sha)
                extracted_candidates.extend(cands)

            # Deduplicate extracted candidates by candidate_id
            seen_cand_ids: set[str] = set()
            unique_extracted: list[ExtractedCandidate] = []
            for cand in extracted_candidates:
                if cand.candidate_id in seen_cand_ids:
                    continue
                seen_cand_ids.add(cand.candidate_id)
                unique_extracted.append(cand)
            extracted_candidates = unique_extracted

            # Persist discovered candidate evidence in decision_candidates table
            for cand in extracted_candidates:
                if research_store is not None:
                    research_store.insert_decision_candidate(
                        DecisionCandidateRecord(
                            candidate_id=cand.candidate_id,
                            run_id=run_meta.run_id,
                            source_id=doc_source_id_map.get(cand.source_path),
                            source_location=cand.location_string,
                            raw_evidence_reference=cand.raw_statement[:200],
                            normalized_decision=cand.raw_statement,
                            discovery_confidence=cand.discovery_confidence,
                            discovery_metadata_json=json.dumps(cand.discovery_metadata, sort_keys=True),
                        )
                    )

            # 7. Execute explicit classifier tasks
            all_classifier_results: list[ClassifierResult] = []
            composed_candidates: list[DecisionCandidate] = []
            incomplete_candidates: list[IncompleteCandidateRecord] = []

            for cand in extracted_candidates:
                doc = doc_by_path.get(cand.source_path)
                context = (
                    build_source_context(doc, cand.source_location, context_lines=5)
                    if doc is not None
                    else cand.raw_statement
                )

                # Required semantic dimensions (exactly 8, no duplicates)
                tasks = [
                    ClassifierTask.from_extracted_candidate(cand, ClassifierTaskType.DECISION_CLASSIFICATION, context),
                    ClassifierTask.from_extracted_candidate(cand, ClassifierTaskType.DOMAINS, context),
                    ClassifierTask.from_extracted_candidate(cand, ClassifierTaskType.PURPOSES, context),
                    ClassifierTask.from_extracted_candidate(cand, ClassifierTaskType.AUTHORITY, context),
                    ClassifierTask.from_extracted_candidate(cand, ClassifierTaskType.SCOPE, context),
                    ClassifierTask.from_extracted_candidate(cand, ClassifierTaskType.LIFECYCLE, context),
                    ClassifierTask.from_extracted_candidate(cand, ClassifierTaskType.RELATIONSHIPS, context),
                    ClassifierTask.from_extracted_candidate(cand, ClassifierTaskType.ENFORCEMENT_POTENTIAL, context),
                ]

                results = execute_classifier_batch(classifier, tasks)
                all_classifier_results.extend(results)

                # Map results by task_type
                res_by_type = {r.task_type: r for r in results}

                # Persist classifier execution records
                for r in results:
                    if research_store is not None:
                        research_store.insert_classifier_execution(
                            ClassifierExecutionRecord(
                                execution_id=r.execution_id,
                                candidate_id=cand.candidate_id,
                                run_id=run_meta.run_id,
                                classifier_backend=r.backend_id,
                                classifier_version=r.classifier_version,
                                model_identifier=r.model_identifier,
                                taxonomy_version=r.taxonomy_version,
                                task_type=r.task_type.value,
                                output_json=json.dumps(r.output, sort_keys=True),
                                confidence=r.confidence,
                                latency_ms=r.latency_ms,
                                cost_amount=r.cost_amount,
                                cost_currency=r.cost_currency,
                                escalated=1 if r.escalated else 0,
                                created_at=r.executed_at,
                            )
                        )

                # 8. Normalize semantic outputs (fail-closed on required dimensions)
                failed_dims: list[str] = []
                dim_errors: dict[str, str] = []

                # classification
                norm_class: tuple[str, ...] | None = None
                try:
                    c_out = res_by_type[ClassifierTaskType.DECISION_CLASSIFICATION].output.get("classification")
                    norm_class = normalize_classification(c_out)
                except Exception as exc:
                    failed_dims.append("classification")
                    dim_errors.append(f"classification: {exc}")

                # domains
                norm_domains: tuple[str, ...] | None = None
                try:
                    d_out = res_by_type[ClassifierTaskType.DOMAINS].output.get("domains")
                    norm_domains = normalize_domains(d_out)
                except Exception as exc:
                    failed_dims.append("domains")
                    dim_errors.append(f"domains: {exc}")

                # purposes
                norm_purposes: tuple[str, ...] | None = None
                try:
                    p_out = res_by_type[ClassifierTaskType.PURPOSES].output.get("purposes")
                    norm_purposes = normalize_purposes(p_out)
                except Exception as exc:
                    failed_dims.append("purposes")
                    dim_errors.append(f"purposes: {exc}")

                # authority
                norm_authority: str | None = None
                try:
                    a_out = res_by_type[ClassifierTaskType.AUTHORITY].output.get("authority")
                    norm_authority = normalize_authority(a_out)
                except Exception as exc:
                    failed_dims.append("authority")
                    dim_errors.append(f"authority: {exc}")

                # scopes
                norm_scopes: tuple = ()
                try:
                    s_out = res_by_type[ClassifierTaskType.SCOPE].output.get("scopes", [])
                    norm_scopes = normalize_scopes(s_out)
                except Exception as exc:
                    failed_dims.append("scopes")
                    dim_errors.append(f"scopes: {exc}")

                # lifecycle
                norm_lifecycle: str | None = None
                try:
                    l_out = res_by_type[ClassifierTaskType.LIFECYCLE].output.get("lifecycle")
                    norm_lifecycle = normalize_lifecycle(l_out)
                except Exception as exc:
                    failed_dims.append("lifecycle")
                    dim_errors.append(f"lifecycle: {exc}")

                # relationships
                norm_relationships: tuple = ()
                try:
                    r_out = res_by_type[ClassifierTaskType.RELATIONSHIPS].output.get("relationships", [])
                    norm_relationships = normalize_relationships(r_out)
                except Exception as exc:
                    failed_dims.append("relationships")
                    dim_errors.append(f"relationships: {exc}")

                # enforcement
                norm_enforcement: str | None = None
                try:
                    e_out = res_by_type[ClassifierTaskType.ENFORCEMENT_POTENTIAL].output.get("enforcement_potential")
                    norm_enforcement = normalize_enforcement_potential(e_out)
                except Exception as exc:
                    failed_dims.append("enforcement_potential")
                    dim_errors.append(f"enforcement_potential: {exc}")

                # Persist validated dimensions to ResearchStore where available
                if research_store is not None:
                    if norm_class:
                        for cls_val in norm_class:
                            classification_id = f"cls-{hashlib.sha256(f'{run_meta.run_id}:{cand.candidate_id}:{cls_val}'.encode()).hexdigest()[:32]}"
                            research_store.insert_candidate_classification(
                                CandidateClassificationRecord(
                                    classification_id=classification_id,
                                    candidate_id=cand.candidate_id,
                                    run_id=run_meta.run_id,
                                    classification=cls_val,
                                    classifier_version=classifier.classifier_version,
                                    taxonomy_version=taxonomy_version,
                                    confidence=res_by_type[ClassifierTaskType.DECISION_CLASSIFICATION].confidence,
                                    rationale=res_by_type[ClassifierTaskType.DECISION_CLASSIFICATION].output.get("rationale"),
                                    created_at=now_iso(),
                                )
                            )
                    if norm_domains:
                        for dom in norm_domains:
                            research_store.insert_candidate_domain(
                                CandidateDomainRecord(
                                    candidate_id=cand.candidate_id,
                                    run_id=run_meta.run_id,
                                    domain=dom,
                                    confidence=res_by_type[ClassifierTaskType.DOMAINS].confidence,
                                    classifier_version=classifier.classifier_version,
                                )
                            )
                    if norm_purposes:
                        for pur in norm_purposes:
                            research_store.insert_candidate_purpose(
                                CandidatePurposeRecord(
                                    candidate_id=cand.candidate_id,
                                    run_id=run_meta.run_id,
                                    purpose=pur,
                                    confidence=res_by_type[ClassifierTaskType.PURPOSES].confidence,
                                    classifier_version=classifier.classifier_version,
                                )
                            )
                    if norm_authority:
                        research_store.upsert_candidate_authority(
                            CandidateAuthorityRecord(
                                candidate_id=cand.candidate_id,
                                run_id=run_meta.run_id,
                                authority_status=norm_authority,
                                authority_evidence=res_by_type[ClassifierTaskType.AUTHORITY].output.get("evidence"),
                                confidence=res_by_type[ClassifierTaskType.AUTHORITY].confidence,
                            )
                        )
                    if norm_scopes:
                        for sc in norm_scopes:
                            scope_id = f"sc-{hashlib.sha256(f'{run_meta.run_id}:{cand.candidate_id}:{sc.scope_type}:{sc.scope_expression}'.encode()).hexdigest()[:32]}"
                            research_store.insert_candidate_scope(
                                CandidateScopeRecord(
                                    scope_id=scope_id,
                                    candidate_id=cand.candidate_id,
                                    run_id=run_meta.run_id,
                                    scope_type=sc.scope_type,
                                    scope_expression=sc.scope_expression,
                                    confidence=res_by_type[ClassifierTaskType.SCOPE].confidence,
                                    evidence_reference=None,
                                )
                            )
                    if norm_lifecycle:
                        l_data = res_by_type[ClassifierTaskType.LIFECYCLE].output
                        research_store.upsert_candidate_lifecycle(
                            CandidateLifecycleRecord(
                                candidate_id=cand.candidate_id,
                                run_id=run_meta.run_id,
                                lifecycle_status=norm_lifecycle,
                                supersedes=l_data.get("supersedes"),
                                superseded_by=l_data.get("superseded_by"),
                                effective_date=l_data.get("effective_date"),
                                expiration_if_any=l_data.get("expiration_if_any"),
                                confidence=res_by_type[ClassifierTaskType.LIFECYCLE].confidence,
                            )
                        )
                    if norm_relationships:
                        for rel in norm_relationships:
                            rel_id = f"rel-{hashlib.sha256(f'{run_meta.run_id}:{cand.candidate_id}:{rel.relationship_type}:{rel.target_candidate_id}'.encode()).hexdigest()[:32]}"
                            research_store.insert_candidate_relationship(
                                CandidateRelationshipRecord(
                                    relationship_id=rel_id,
                                    run_id=run_meta.run_id,
                                    source_candidate_id=cand.candidate_id,
                                    relationship_type=rel.relationship_type,
                                    target_candidate_id=rel.target_candidate_id,
                                    target_reference=rel.target_reference,
                                    confidence=rel.confidence,
                                    evidence_reference=rel.evidence_reference,
                                )
                            )
                    if norm_enforcement:
                        research_store.upsert_enforcement_assessment(
                            EnforcementAssessmentRecord(
                                candidate_id=cand.candidate_id,
                                run_id=run_meta.run_id,
                                enforcement_potential=norm_enforcement,
                                candidate_rule=res_by_type[ClassifierTaskType.ENFORCEMENT_POTENTIAL].output.get("candidate_rule"),
                                confidence=res_by_type[ClassifierTaskType.ENFORCEMENT_POTENTIAL].confidence,
                            )
                        )

                # Check if all required dimensions succeeded
                if (
                    norm_class is not None
                    and norm_domains is not None
                    and norm_purposes is not None
                    and norm_authority is not None
                    and norm_lifecycle is not None
                    and norm_enforcement is not None
                ):
                    composed = build_decision_candidate(
                        extracted=cand,
                        classification=norm_class[0],
                        decision_domains=norm_domains,
                        decision_purposes=norm_purposes,
                        authority_status=norm_authority,
                        scopes=norm_scopes,
                        lifecycle_status=norm_lifecycle,
                        relationships=norm_relationships,
                        enforcement_potential=norm_enforcement,
                        confidence=cand.discovery_confidence,
                    )
                    composed_candidates.append(composed)
                else:
                    # Incomplete candidate
                    incomplete_candidates.append(
                        IncompleteCandidateRecord(
                            candidate_id=cand.candidate_id,
                            source_path=cand.source_path,
                            raw_statement=cand.raw_statement,
                            missing_or_failed_dimensions=tuple(failed_dims),
                            errors={dim: err for dim, err in zip(failed_dims, dim_errors)},
                        )
                    )

            # 9. Evaluate Governing Decision Set across supplied applicability scenarios
            gds_results: list[GoverningDecisionSetResult] = []

            if scenarios_list:
                for scenario in scenarios_list:
                    # Persist scenario in ResearchStore
                    if research_store is not None:
                        research_store.insert_applicability_scenario(
                            ApplicabilityScenarioRecord(
                                scenario_id=scenario.scenario_id,
                                repo_id=repository_config.id,
                                description=scenario.description,
                                path=scenario.change_context.path,
                                component=scenario.change_context.component,
                                change_type=scenario.change_context.change_type,
                                dependencies_json=json.dumps(list(scenario.change_context.dependencies)),
                                api_context=scenario.change_context.api,
                                technology_context=scenario.change_context.technology,
                                other_context=scenario.change_context.other_context,
                                validation_state=scenario.validation_state,
                            )
                        )
                        # Persist expected decisions UNCONDITIONALLY (reference labels must survive machine misses)
                        for exp_id in scenario.expected_governing_decision_ids:
                            research_store.insert_scenario_expected_decision(
                                ScenarioExpectedDecisionRecord(
                                    scenario_id=scenario.scenario_id,
                                    candidate_id=exp_id,
                                )
                            )

                # Run GDS evaluation
                raw_gds = evaluate_governing_decisions_batch(composed_candidates, scenarios_list)
                gds_results.extend(raw_gds)

                # Persist scenario results
                if research_store is not None:
                    for gds_res in gds_results:
                        result_id = f"res-{hashlib.sha256(f'{run_meta.run_id}:{gds_res.scenario_id}'.encode()).hexdigest()[:32]}"
                        research_store.insert_scenario_result(
                            ScenarioResultRecord(
                                result_id=result_id,
                                scenario_id=gds_res.scenario_id,
                                run_id=run_meta.run_id,
                                classifier_version=classifier.classifier_version,
                                applicability_version="0.1",
                                precision=gds_res.precision,
                                recall=gds_res.recall,
                                f1=gds_res.f1,
                                created_at=now_iso(),
                                error_records_json=None,
                            )
                        )
                        for pred_id in gds_res.predicted_governing_decision_ids:
                            research_store.insert_scenario_result_decision(
                                ScenarioResultDecisionRecord(
                                    result_id=result_id,
                                    candidate_id=pred_id,
                                )
                            )

            suite_metrics = (
                compute_suite_gds_metrics(gds_results)
                if gds_results
                else {"macro_precision": 0.0, "macro_recall": 0.0, "macro_f1": 0.0}
            )

            # 10. Mark run completed
            completed_time = now_iso()
            run_meta = run_meta.with_completion("completed", completed_time)
            if research_store is not None:
                research_store.update_analysis_run_status(
                    run_id=run_meta.run_id,
                    status="completed",
                    completed_at=completed_time,
                )

            return OpenArchitectureRunResult(
                run_metadata=run_meta,
                repository_config=repository_config,
                discovered_documents=tuple(docs),
                extracted_candidates=tuple(extracted_candidates),
                composed_candidates=tuple(composed_candidates),
                incomplete_candidates=tuple(incomplete_candidates),
                classifier_results=tuple(all_classifier_results),
                scenarios=tuple(scenarios_list),
                gds_results=tuple(gds_results),
                suite_metrics=suite_metrics,
                diagnostics=tuple(all_diagnostics),
            )

    except Exception as exc:
        # Mark run failed in ResearchStore if already created
        if research_store is not None:
            try:
                research_store.update_analysis_run_status(
                    run_id=run_meta.run_id,
                    status="failed",
                    completed_at=now_iso(),
                )
            except Exception:
                pass
        raise


__all__ = [
    "PreflightResult",
    "IncompleteCandidateRecord",
    "OpenArchitectureRunResult",
    "preflight_open_architecture_analysis",
    "run_open_architecture_analysis",
]
