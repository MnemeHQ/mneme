"""
mneme.open_architecture.harness — Staged benchmark execution harness for O1A Batch 01.

Implements the frozen three-stage benchmark protocol:
- Preflight: fail-closed validation of frozen baseline, manifest, and corpora identities.
- Stage A (Discovery): deterministic line-interval matching between extracted cand-* spans
  and frozen ref-* reference decisions.
- Stage B (Semantic Classification): 800 logical tasks over the exact 100 human-reviewed
  reference decisions, evaluated against frozen human labels.
- Stage C (Governing Decision Set): isolated retrieval evaluation projecting human ref-*
  decisions through frozen DecisionRetriever against 50 scenarios (headline metric).
- Batch Provenance Envelope: durable provenance preserving global 50-scenario corpus identity
  alongside per-run 10-scenario subset metadata without modifying RunMetadata.

Security & Boundaries:
- Research-only infrastructure. Zero writes to canonical Mneme state (.mneme/project_memory.json,
  DecisionIndex, DecisionProposal, etc.).
- Never modifies frozen semantic runtime modules.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from mneme.open_architecture.baseline import (
    APPROVED_BATCH_01_REPOSITORIES,
    FROZEN_SEMANTIC_MNEME_SHA,
    BaselineConfig,
    validate_baseline_freeze,
)
from mneme.open_architecture.candidates import (
    CandidateExtractor,
    ExtractedCandidate,
    HeuristicExtractor,
    LineSpan,
)
from mneme.open_architecture.classification import (
    ClassifierResult,
    ClassifierTask,
    ClassifierTaskType,
    NormalizationError,
    SemanticClassifier,
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
    materialize_repository,
)
from mneme.open_architecture.export import (
    compute_reference_corpus_content_hash,
    import_scenarios_jsonl,
)
from mneme.open_architecture.gds_evaluation import (
    GoverningDecisionSetResult,
    compute_suite_gds_metrics,
    evaluate_governing_decisions_batch,
)
from mneme.open_architecture.manifest import Manifest, RepositoryConfig
from mneme.open_architecture.metrics import (
    GoverningDecisionSetMetrics,
    compute_suite_metrics,
)
from mneme.open_architecture.orchestrator import _compute_scenario_content_hash
from mneme.open_architecture.projection import project_candidates_to_decisions
from mneme.open_architecture.run_metadata import RunMetadata, _get_git_commit_sha
from mneme.open_architecture.schemas import (
    ApplicabilityScenario,
    DecisionCandidate,
    Relationship,
    Scope,
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
    TaxonomyVersionRecord,
    now_iso,
)


FROZEN_BATCH_ID = "o1a-batch-01"
FROZEN_BASELINE_ID = "o1a-batch-01-baseline"
FROZEN_BASELINE_CONFIG_HASH = "31e18dc1e2bd9ad30bec86dce1a9295a"
FROZEN_MANIFEST_CONFIG_HASH = "4af7e5794011b43d39682cdfeac9f54e"
FROZEN_REFERENCE_CORPUS_HASH = "0455bd66aae52551c35b37a63c2d185f"
FROZEN_SCENARIO_CORPUS_HASH = "2ff8751955fd64a33316aca6692dc803"


# ── A. Frozen Preflight ─────────────────────────────────────────────────────────


class HarnessPreflightError(ValueError):
    """Raised when preflight verification of frozen benchmark prerequisites fails."""


@dataclass(frozen=True)
class BatchPreflightResult:
    status: str
    baseline_id: str
    baseline_configuration_hash: str
    manifest_configuration_hash: str
    reference_corpus_hash: str
    scenario_corpus_hash: str
    semantic_mneme_sha: str
    repositories_verified: tuple[str, ...]
    classifier_backend_id: str
    classifier_version: str
    classifier_model_identifier: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "baseline_id": self.baseline_id,
            "baseline_configuration_hash": self.baseline_configuration_hash,
            "manifest_configuration_hash": self.manifest_configuration_hash,
            "reference_corpus_hash": self.reference_corpus_hash,
            "scenario_corpus_hash": self.scenario_corpus_hash,
            "semantic_mneme_sha": self.semantic_mneme_sha,
            "repositories_verified": list(self.repositories_verified),
            "classifier_backend_id": self.classifier_backend_id,
            "classifier_version": self.classifier_version,
            "classifier_model_identifier": self.classifier_model_identifier,
        }


def preflight_batch_01(
    *,
    baseline_path: str | Path,
    manifest_path: str | Path,
    reference_corpus_dir: str | Path,
    scenarios_path: str | Path,
    classifier: SemanticClassifier | None = None,
    extractor: CandidateExtractor | None = None,
) -> BatchPreflightResult:
    """Validate all frozen benchmark prerequisites fail-closed before execution.

    Requires:
    - baseline.yaml status == 'frozen' and configuration_hash matches frozen baseline
    - manifest.yaml status == 'frozen' and configuration_hash matches baseline.manifest_ref
    - reference corpus content hash matches baseline
    - global 50-scenario corpus content hash matches baseline
    - pinned repository commit SHAs match baseline
    - classifier identity/version/model matches baseline (if classifier supplied)
    - extractor identity/version/config matches baseline (if extractor supplied)

    No network calls or model execution performed.
    """
    baseline = BaselineConfig.load(baseline_path)
    manifest = Manifest.load(manifest_path)

    if baseline.status != "frozen":
        raise HarnessPreflightError(
            f"Baseline status must be 'frozen', got {baseline.status!r}"
        )
    if manifest.status != "frozen":
        raise HarnessPreflightError(
            f"Manifest status must be 'frozen', got {manifest.status!r}"
        )

    # Validate baseline freeze prerequisites
    validate_baseline_freeze(baseline, manifest=manifest)

    # Verify baseline configuration hash
    computed_baseline_hash = baseline.configuration_hash()
    if computed_baseline_hash != FROZEN_BASELINE_CONFIG_HASH:
        raise HarnessPreflightError(
            f"Baseline configuration hash mismatch: expected {FROZEN_BASELINE_CONFIG_HASH!r}, "
            f"computed {computed_baseline_hash!r}"
        )

    # Verify manifest configuration hash
    computed_manifest_hash = manifest.configuration_hash()
    expected_manifest_hash = baseline.manifest_ref.get("configuration_hash")
    if computed_manifest_hash != expected_manifest_hash:
        raise HarnessPreflightError(
            f"Manifest configuration hash mismatch: baseline binds {expected_manifest_hash!r}, "
            f"computed {computed_manifest_hash!r}"
        )
    if computed_manifest_hash != FROZEN_MANIFEST_CONFIG_HASH:
        raise HarnessPreflightError(
            f"Manifest configuration hash does not match frozen identity {FROZEN_MANIFEST_CONFIG_HASH!r}, "
            f"got {computed_manifest_hash!r}"
        )
    if expected_manifest_hash != FROZEN_MANIFEST_CONFIG_HASH:
        raise HarnessPreflightError(
            f"Baseline manifest_ref configuration hash does not match frozen identity {FROZEN_MANIFEST_CONFIG_HASH!r}, "
            f"got {expected_manifest_hash!r}"
        )

    # Recompute and verify reference corpus hash
    computed_ref_hash = compute_reference_corpus_content_hash(reference_corpus_dir)
    if computed_ref_hash != baseline.reference_corpus.content_hash:
        raise HarnessPreflightError(
            f"Reference corpus content hash mismatch: expected {baseline.reference_corpus.content_hash!r}, "
            f"computed {computed_ref_hash!r}"
        )
    if computed_ref_hash != FROZEN_REFERENCE_CORPUS_HASH:
        raise HarnessPreflightError(
            f"Reference corpus content hash does not match frozen identity {FROZEN_REFERENCE_CORPUS_HASH!r}"
        )

    # Recompute and verify global 50-scenario corpus hash
    try:
        all_scenarios = import_scenarios_jsonl(scenarios_path)
    except Exception as exc:
        raise HarnessPreflightError(f"Scenario import failed: {exc}") from exc
    if len(all_scenarios) != baseline.scenario_corpus.total_required:
        raise HarnessPreflightError(
            f"Scenario count mismatch: expected {baseline.scenario_corpus.total_required}, "
            f"got {len(all_scenarios)}"
        )
    computed_scn_hash = _compute_scenario_content_hash(all_scenarios)
    if computed_scn_hash != baseline.scenario_corpus.content_hash:
        raise HarnessPreflightError(
            f"Scenario corpus content hash mismatch: expected {baseline.scenario_corpus.content_hash!r}, "
            f"computed {computed_scn_hash!r}"
        )
    if computed_scn_hash != FROZEN_SCENARIO_CORPUS_HASH:
        raise HarnessPreflightError(
            f"Scenario corpus content hash does not match frozen identity {FROZEN_SCENARIO_CORPUS_HASH!r}"
        )

    # Verify pinned repository identities and commit SHAs
    manifest_repos = {r.id: r.commit_sha for r in manifest.repositories}
    baseline_repos = {r.id: r.commit_sha for r in baseline.repositories}
    if set(baseline_repos.keys()) != APPROVED_BATCH_01_REPOSITORIES:
        raise HarnessPreflightError(
            f"Baseline repositories do not match approved set {sorted(APPROVED_BATCH_01_REPOSITORIES)}"
        )
    if manifest_repos != baseline_repos:
        raise HarnessPreflightError(
            f"Repository commit SHA mismatch between manifest and baseline:\n"
            f"  manifest: {manifest_repos}\n  baseline: {baseline_repos}"
        )

    # Verify classifier if supplied
    if classifier is not None:
        if classifier.backend_id != baseline.classifier.backend_id:
            raise HarnessPreflightError(
                f"Classifier backend_id mismatch: expected {baseline.classifier.backend_id!r}, "
                f"got {classifier.backend_id!r}"
            )
        if classifier.classifier_version != baseline.classifier.classifier_version:
            raise HarnessPreflightError(
                f"Classifier version mismatch: expected {baseline.classifier.classifier_version!r}, "
                f"got {classifier.classifier_version!r}"
            )
        if classifier.model_identifier != baseline.classifier.model_identifier:
            raise HarnessPreflightError(
                f"Classifier model mismatch: expected {baseline.classifier.model_identifier!r}, "
                f"got {classifier.model_identifier!r}"
            )

    # Always verify runtime HeuristicExtractor against frozen baseline contract
    runtime_extractor = HeuristicExtractor()
    if runtime_extractor.extractor_id != baseline.extractor.id:
        raise HarnessPreflightError(
            f"Runtime extractor ID mismatch: expected {baseline.extractor.id!r}, got {runtime_extractor.extractor_id!r}"
        )
    if runtime_extractor.extractor_version != baseline.extractor.version:
        raise HarnessPreflightError(
            f"Runtime extractor version mismatch: expected {baseline.extractor.version!r}, got {runtime_extractor.extractor_version!r}"
        )
    if runtime_extractor.min_lines != baseline.extractor.config.get("min_lines"):
        raise HarnessPreflightError(
            f"Runtime extractor min_lines mismatch: expected {baseline.extractor.config.get('min_lines')!r}, got {runtime_extractor.min_lines!r}"
        )
    if runtime_extractor.max_lines != baseline.extractor.config.get("max_lines"):
        raise HarnessPreflightError(
            f"Runtime extractor max_lines mismatch: expected {baseline.extractor.config.get('max_lines')!r}, got {runtime_extractor.max_lines!r}"
        )
    if runtime_extractor.confidence != baseline.extractor.config.get("confidence"):
        raise HarnessPreflightError(
            f"Runtime extractor confidence mismatch: expected {baseline.extractor.config.get('confidence')!r}, got {runtime_extractor.confidence!r}"
        )
    expected_keywords = baseline.extractor.config.get("keywords")
    if expected_keywords is None or set(runtime_extractor.DECISION_KEYWORDS) != set(expected_keywords):
        raise HarnessPreflightError(
            f"Runtime extractor keywords mismatch: expected {expected_keywords!r}, got {sorted(runtime_extractor.DECISION_KEYWORDS)!r}"
        )

    # Verify explicitly supplied extractor if passed
    if extractor is not None:
        ext_id = getattr(extractor, "extractor_id", type(extractor).__name__)
        ext_ver = getattr(extractor, "extractor_version", "0.1")
        if ext_id != baseline.extractor.id:
            raise HarnessPreflightError(
                f"Extractor ID mismatch: expected {baseline.extractor.id!r}, got {ext_id!r}"
            )
        if ext_ver != baseline.extractor.version:
            raise HarnessPreflightError(
                f"Extractor version mismatch: expected {baseline.extractor.version!r}, got {ext_ver!r}"
            )
        ext_min_lines = getattr(extractor, "min_lines", None)
        if ext_min_lines != baseline.extractor.config.get("min_lines"):
            raise HarnessPreflightError(
                f"Extractor min_lines mismatch: expected {baseline.extractor.config.get('min_lines')!r}, got {ext_min_lines!r}"
            )
        ext_max_lines = getattr(extractor, "max_lines", None)
        if ext_max_lines != baseline.extractor.config.get("max_lines"):
            raise HarnessPreflightError(
                f"Extractor max_lines mismatch: expected {baseline.extractor.config.get('max_lines')!r}, got {ext_max_lines!r}"
            )
        ext_confidence = getattr(extractor, "confidence", None)
        if ext_confidence != baseline.extractor.config.get("confidence"):
            raise HarnessPreflightError(
                f"Extractor confidence mismatch: expected {baseline.extractor.config.get('confidence')!r}, got {ext_confidence!r}"
            )
        ext_keywords = getattr(extractor, "DECISION_KEYWORDS", None)
        if ext_keywords is None:
            ext_keywords = getattr(extractor, "keywords", None)
        if ext_keywords is None or set(ext_keywords) != set(expected_keywords):
            raise HarnessPreflightError(
                f"Extractor keywords mismatch: expected {expected_keywords!r}, got {ext_keywords!r}"
            )

    return BatchPreflightResult(
        status="preflight_ok",
        baseline_id=baseline.baseline_id,
        baseline_configuration_hash=computed_baseline_hash,
        manifest_configuration_hash=computed_manifest_hash,
        reference_corpus_hash=computed_ref_hash,
        scenario_corpus_hash=computed_scn_hash,
        semantic_mneme_sha=baseline.semantic_mneme_sha,
        repositories_verified=tuple(sorted(baseline_repos.keys())),
        classifier_backend_id=baseline.classifier.backend_id,
        classifier_version=baseline.classifier.classifier_version,
        classifier_model_identifier=baseline.classifier.model_identifier,
    )


# ── B. Reference Corpus Representation & Loader ─────────────────────────────────


@dataclass(frozen=True)
class FrozenReferenceDecision:
    """Exact, immutable representation of a frozen human reference decision."""

    reference_decision_id: str
    repository: str
    repository_commit_sha: str
    source_file: str
    source_location: str
    raw_evidence: str
    normalized_decision: str
    classification: str
    decision_domains: tuple[str, ...]
    decision_purposes: tuple[str, ...]
    authority_status: str
    authority_evidence: str | None
    scopes: tuple[dict[str, Any], ...]
    lifecycle_status: str
    supersedes: str | None
    superseded_by: str | None
    effective_date: str | None
    expiration_if_any: str | None
    relationships: tuple[dict[str, Any], ...]
    enforcement_potential: str
    candidate_rule: str | None
    sampling_category: str
    human_review_status: str
    human_notes: str | None
    raw_record: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FrozenReferenceDecision:
        ref_id = str(data["reference_decision_id"])
        if not ref_id.startswith("ref-"):
            raise ValueError(f"reference_decision_id must start with 'ref-', got {ref_id!r}")
        return cls(
            reference_decision_id=ref_id,
            repository=str(data["repository"]),
            repository_commit_sha=str(data["repository_commit_sha"]),
            source_file=str(data["source_file"]),
            source_location=str(data["source_location"]),
            raw_evidence=str(data["raw_evidence"]),
            normalized_decision=str(data["normalized_decision"]),
            classification=str(data["classification"]),
            decision_domains=tuple(str(d) for d in data.get("decision_domains", [])),
            decision_purposes=tuple(str(p) for p in data.get("decision_purposes", [])),
            authority_status=str(data["authority_status"]),
            authority_evidence=data.get("authority_evidence"),
            scopes=tuple(dict(s) for s in data.get("scopes", [])),
            lifecycle_status=str(data["lifecycle_status"]),
            supersedes=data.get("supersedes"),
            superseded_by=data.get("superseded_by"),
            effective_date=data.get("effective_date"),
            expiration_if_any=data.get("expiration_if_any"),
            relationships=tuple(dict(r) for r in data.get("relationships", [])),
            enforcement_potential=str(data["enforcement_potential"]),
            candidate_rule=data.get("candidate_rule"),
            sampling_category=str(data.get("sampling_category", "")),
            human_review_status=str(data.get("human_review_status", "reviewed")),
            human_notes=data.get("human_notes"),
            raw_record=dict(data),
        )

    def to_decision_candidate(self) -> DecisionCandidate:
        """Adapt this reference decision into a DecisionCandidate for Stage C projection."""
        return DecisionCandidate(
            candidate_id=self.reference_decision_id,
            repository=self.repository,
            source_file=self.source_file,
            source_location=self.source_location,
            raw_statement=self.raw_evidence,
            normalized_decision=self.normalized_decision,
            classification=self.classification,
            decision_domains=self.decision_domains,
            decision_purposes=self.decision_purposes,
            authority_status=self.authority_status,
            authority_evidence=self.authority_evidence,
            scopes=tuple(Scope.from_dict(s) for s in self.scopes),
            lifecycle_status=self.lifecycle_status,
            relationships=tuple(Relationship.from_dict(r) for r in self.relationships),
            enforcement_potential=self.enforcement_potential,
            candidate_rule=self.candidate_rule,
            confidence=None,
            human_validation_status="correct" if self.human_review_status == "reviewed" else "ambiguous",
            human_corrections=None,
        )


def load_reference_corpus(
    corpus_dir: str | Path,
    repo_id: str | None = None,
) -> list[FrozenReferenceDecision]:
    """Load reference decisions deterministically from corpus_dir/*/ref-*.jsonl.

    Enforces:
    - Exactly corpus/*/ref-*.jsonl pattern
    - Uniqueness of reference_decision_id
    - Lexicographical sort by reference_decision_id
    """
    root = Path(corpus_dir)
    if not root.is_dir():
        raise ValueError(f"reference corpus directory '{root}' does not exist")

    pattern = f"{repo_id}/ref-*.jsonl" if repo_id else "*/ref-*.jsonl"
    files = sorted(root.glob(pattern))

    records: list[FrozenReferenceDecision] = []
    seen_ids: set[str] = set()

    for f in files:
        if not (f.is_file() and f.name.startswith("ref-") and f.name.endswith(".jsonl")):
            continue
        text = f.read_text(encoding="utf-8").strip()
        if not text:
            continue
        data = json.loads(text)
        record = FrozenReferenceDecision.from_dict(data)
        if record.reference_decision_id in seen_ids:
            raise ValueError(
                f"Duplicate reference_decision_id: {record.reference_decision_id!r}"
            )
        seen_ids.add(record.reference_decision_id)
        records.append(record)

    records.sort(key=lambda r: r.reference_decision_id)
    return records


# ── C. Stage A: Discovery Matching ──────────────────────────────────────────────


def parse_reference_intervals(
    source_file: str,
    source_location: str,
) -> list[tuple[str, int, int]]:
    """Parse reference location string into (file_path, start_line, end_line) intervals.

    Supports:
    - Ordinary 'L42-L48' or 'L42'
    - Discontinuous spans 'L16-L29, L53-L67'
    - Multi-file locations 'golang.go:L17-L44; typescript.go:L20-L47'
    """
    results: list[tuple[str, int, int]] = []
    files_list = [f.strip() for f in source_file.split(",") if f.strip()]

    parts = [p.strip() for p in re.split(r"[;,]", source_location) if p.strip()]
    for p in parts:
        target_file = files_list[0] if len(files_list) == 1 else ""
        if ":" in p and not re.match(r"^L?\d+", p):
            f_prefix, span_str = p.split(":", 1)
            f_prefix = f_prefix.strip()
            span_str = span_str.strip()
            for candidate_f in files_list:
                if candidate_f.endswith(f_prefix) or f_prefix in candidate_f:
                    target_file = candidate_f
                    break
        else:
            span_str = p.strip()
            if len(files_list) == 1:
                target_file = files_list[0]

        m = re.search(r"L?(\d+)(?:\s*-\s*L?(\d+))?", span_str, re.IGNORECASE)
        if m and target_file:
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else start
            results.append((target_file, start, end))

    return results


@dataclass(frozen=True)
class StageADiscoveryResult:
    repo_id: str
    discovered_documents_count: int
    extracted_candidates_count: int
    reference_decisions_count: int
    matched_reference_count: int
    matched_candidate_count: int
    recall: float
    precision: float
    f1: float
    cand_to_ref_matches: dict[str, list[str]]
    ref_to_cand_matches: dict[str, list[str]]
    unmatched_reference_ids: list[str]
    unmatched_candidate_ids: list[str]
    missed_source_reference_ids: list[str]
    diagnostic_ior_ioc: dict[tuple[str, str], dict[str, float]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_id": self.repo_id,
            "discovered_documents_count": self.discovered_documents_count,
            "extracted_candidates_count": self.extracted_candidates_count,
            "reference_decisions_count": self.reference_decisions_count,
            "matched_reference_count": self.matched_reference_count,
            "matched_candidate_count": self.matched_candidate_count,
            "recall": self.recall,
            "precision": self.precision,
            "f1": self.f1,
            "unmatched_reference_ids": self.unmatched_reference_ids,
            "missed_source_reference_ids": self.missed_source_reference_ids,
        }


def evaluate_discovery_matches(
    *,
    candidates: list[ExtractedCandidate],
    discovered_paths: set[str],
    references: list[FrozenReferenceDecision],
    repo_id: str,
    discovered_documents_count: int,
) -> StageADiscoveryResult:
    """Pure deterministic matching between dynamic candidates and frozen references.

    Calculates discovery recall, precision, and F1 using non-empty line interval intersection
    on matching source file components. No semantic/LLM matching; no IoR/IoC gating.
    """
    # 1. Parse reference intervals
    ref_intervals: dict[str, list[tuple[str, int, int]]] = {
        r.reference_decision_id: parse_reference_intervals(r.source_file, r.source_location)
        for r in references
    }

    # Identify MISSED_SOURCE references
    missed_sources: list[str] = []
    for r in references:
        r_files = [f.strip() for f in r.source_file.split(",") if f.strip()]
        if not any(f in discovered_paths for f in r_files):
            missed_sources.append(r.reference_decision_id)

    # 2. Match candidates to references using deterministic non-empty interval intersection
    cand_to_ref: dict[str, list[str]] = {}
    ref_to_cand: dict[str, list[str]] = {}
    diagnostic_metrics: dict[tuple[str, str], dict[str, float]] = {}

    for c in candidates:
        c_file = c.source_path
        c_start = c.source_location.start_line
        c_end = c.source_location.end_line
        c_len = c_end - c_start + 1

        for r in references:
            r_id = r.reference_decision_id
            intervals = ref_intervals[r_id]

            total_overlap = 0
            total_ref_lines = sum(e - s + 1 for _, s, e in intervals)

            for r_file, r_start, r_end in intervals:
                if c_file == r_file:
                    overlap_start = max(c_start, r_start)
                    overlap_end = min(c_end, r_end)
                    if overlap_start <= overlap_end:
                        total_overlap += (overlap_end - overlap_start + 1)

            if total_overlap > 0:
                cand_to_ref.setdefault(c.candidate_id, []).append(r_id)
                ref_to_cand.setdefault(r_id, []).append(c.candidate_id)
                ior = total_overlap / total_ref_lines if total_ref_lines > 0 else 0.0
                ioc = total_overlap / c_len if c_len > 0 else 0.0
                diagnostic_metrics[(c.candidate_id, r_id)] = {"ior": ior, "ioc": ioc}

    matched_refs = set(ref_to_cand.keys())
    matched_cands = set(cand_to_ref.keys())

    recall = len(matched_refs) / len(references) if references else 0.0
    precision = len(matched_cands) / len(candidates) if candidates else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return StageADiscoveryResult(
        repo_id=repo_id,
        discovered_documents_count=discovered_documents_count,
        extracted_candidates_count=len(candidates),
        reference_decisions_count=len(references),
        matched_reference_count=len(matched_refs),
        matched_candidate_count=len(matched_cands),
        recall=recall,
        precision=precision,
        f1=f1,
        cand_to_ref_matches=cand_to_ref,
        ref_to_cand_matches=ref_to_cand,
        unmatched_reference_ids=sorted([r.reference_decision_id for r in references if r.reference_decision_id not in matched_refs]),
        unmatched_candidate_ids=sorted([c.candidate_id for c in candidates if c.candidate_id not in matched_cands]),
        missed_source_reference_ids=sorted(missed_sources),
        diagnostic_ior_ioc=diagnostic_metrics,
    )


def evaluate_stage_a_discovery(
    *,
    repository_config: RepositoryConfig,
    references: list[FrozenReferenceDecision],
    clone_source: str | Path | None = None,
    workspace_dir: str | Path | None = None,
) -> StageADiscoveryResult:
    """Execute Stage A discovery evaluation against frozen reference decisions.

    Always materializes the repository via materialize_repository and extracts using
    the frozen runtime HeuristicExtractor to guarantee verified, reproducible checkout.
    No extractor substitution is permitted.
    """
    extractor = HeuristicExtractor()

    with materialize_repository(
        repository_config,
        workspace_dir=workspace_dir,
        clone_source=clone_source,
    ) as checkout:
        discovery = discover_sources(checkout)
        cands = []
        for d in discovery.documents:
            cands.extend(extractor.extract(d, checkout.resolved_commit_sha))

    discovered_paths = {d.relative_path for d in discovery.documents}

    # Deduplicate extracted candidates by candidate_id
    seen_cand: set[str] = set()
    unique_cands: list[ExtractedCandidate] = []
    for c in cands:
        if c.candidate_id not in seen_cand:
            seen_cand.add(c.candidate_id)
            unique_cands.append(c)

    return evaluate_discovery_matches(
        candidates=unique_cands,
        discovered_paths=discovered_paths,
        references=references,
        repo_id=repository_config.id,
        discovered_documents_count=len(discovery.documents),
    )


# ── D. Stage B: Semantic Classification ─────────────────────────────────────────


SEMANTIC_TASK_TYPES: tuple[ClassifierTaskType, ...] = (
    ClassifierTaskType.DECISION_CLASSIFICATION,
    ClassifierTaskType.DOMAINS,
    ClassifierTaskType.PURPOSES,
    ClassifierTaskType.AUTHORITY,
    ClassifierTaskType.SCOPE,
    ClassifierTaskType.LIFECYCLE,
    ClassifierTaskType.RELATIONSHIPS,
    ClassifierTaskType.ENFORCEMENT_POTENTIAL,
)


def build_stage_b_tasks(references: list[FrozenReferenceDecision]) -> list[ClassifierTask]:
    """Construct exactly 8 ClassifierTask instances per reference decision."""
    tasks: list[ClassifierTask] = []
    for ref in references:
        for task_type in SEMANTIC_TASK_TYPES:
            tasks.append(
                ClassifierTask(
                    task_type=task_type,
                    candidate_id=ref.reference_decision_id,
                    repository_identifier=ref.repository,
                    repository_commit_sha=ref.repository_commit_sha,
                    source_path=ref.source_file,
                    source_location=ref.source_location,
                    raw_statement=ref.raw_evidence,
                    source_context=ref.raw_evidence,
                    taxonomy_version="0.1",
                )
            )
    return tasks


@dataclass(frozen=True)
class SemanticDimensionMetric:
    accuracy: float
    total_evaluated: int
    correct_count: int
    escalated_count: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StageBClassificationResult:
    repo_id: str
    reference_count: int
    task_count: int
    classifier_backend: str
    classifier_version: str
    model_identifier: str | None
    metrics: dict[str, Any]
    results_by_ref: dict[str, dict[ClassifierTaskType, ClassifierResult]]
    incomplete_references: dict[str, dict[str, str]]

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "repo_id": self.repo_id,
            "reference_count": self.reference_count,
            "task_count": self.task_count,
            "classifier_backend": self.classifier_backend,
            "classifier_version": self.classifier_version,
            "model_identifier": self.model_identifier,
            "metrics": self.metrics,
            "incomplete_count": len(self.incomplete_references),
        }


def _evaluate_set_prf(expected: Iterable[str], predicted: Iterable[str]) -> tuple[float, float, float]:
    """Compute standard set precision, recall, F1."""
    e_set = set(expected)
    p_set = set(predicted)
    overlap = len(e_set & p_set)
    p = overlap / len(p_set) if p_set else (1.0 if not e_set else 0.0)
    r = overlap / len(e_set) if e_set else 1.0
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    return p, r, f1


def execute_stage_b_classification(
    *,
    repository_config: RepositoryConfig,
    references: list[FrozenReferenceDecision],
    classifier: SemanticClassifier,
    preflight: BatchPreflightResult,
    research_store: ResearchStore | None = None,
    run_id: str | None = None,
) -> StageBClassificationResult:
    """Execute Stage B semantic classification baseline over frozen reference decisions."""
    # Preflight verification before building tasks or calling classifier
    if not isinstance(preflight, BatchPreflightResult):
        raise HarnessPreflightError("Stage B execution requires a valid BatchPreflightResult instance")
    if preflight.status != "preflight_ok":
        raise HarnessPreflightError(f"Stage B preflight status must be 'preflight_ok', got {preflight.status!r}")
    if preflight.baseline_configuration_hash != FROZEN_BASELINE_CONFIG_HASH:
        raise HarnessPreflightError(
            f"Stage B preflight baseline hash mismatch: expected {FROZEN_BASELINE_CONFIG_HASH!r}, "
            f"got {preflight.baseline_configuration_hash!r}"
        )
    if preflight.manifest_configuration_hash != FROZEN_MANIFEST_CONFIG_HASH:
        raise HarnessPreflightError(
            f"Stage B preflight manifest hash mismatch: expected {FROZEN_MANIFEST_CONFIG_HASH!r}, "
            f"got {preflight.manifest_configuration_hash!r}"
        )
    if preflight.reference_corpus_hash != FROZEN_REFERENCE_CORPUS_HASH:
        raise HarnessPreflightError(
            f"Stage B preflight reference corpus hash mismatch: expected {FROZEN_REFERENCE_CORPUS_HASH!r}, "
            f"got {preflight.reference_corpus_hash!r}"
        )
    if preflight.scenario_corpus_hash != FROZEN_SCENARIO_CORPUS_HASH:
        raise HarnessPreflightError(
            f"Stage B preflight scenario corpus hash mismatch: expected {FROZEN_SCENARIO_CORPUS_HASH!r}, "
            f"got {preflight.scenario_corpus_hash!r}"
        )
    if preflight.semantic_mneme_sha != FROZEN_SEMANTIC_MNEME_SHA:
        raise HarnessPreflightError(
            f"Stage B preflight semantic Mneme SHA mismatch: expected {FROZEN_SEMANTIC_MNEME_SHA!r}, "
            f"got {preflight.semantic_mneme_sha!r}"
        )

    # Verify actual classifier instance matches frozen baseline identity before execution
    if classifier.backend_id != preflight.classifier_backend_id:
        raise HarnessPreflightError(
            f"Stage B classifier backend mismatch: expected {preflight.classifier_backend_id!r}, "
            f"got {classifier.backend_id!r}"
        )
    if classifier.classifier_version != preflight.classifier_version:
        raise HarnessPreflightError(
            f"Stage B classifier version mismatch: expected {preflight.classifier_version!r}, "
            f"got {classifier.classifier_version!r}"
        )
    if classifier.model_identifier != preflight.classifier_model_identifier:
        raise HarnessPreflightError(
            f"Stage B classifier model mismatch: expected {preflight.classifier_model_identifier!r}, "
            f"got {classifier.model_identifier!r}"
        )

    tasks = build_stage_b_tasks(references)
    raw_results = execute_classifier_batch(classifier, tasks)

    # Organize results by reference and task type
    results_by_ref: dict[str, dict[ClassifierTaskType, ClassifierResult]] = {}
    for r in raw_results:
        results_by_ref.setdefault(r.candidate_id, {})[r.task_type] = r

    # Fail-closed semantic normalization and scoring
    incomplete_refs: dict[str, dict[str, str]] = {}

    exact_class_matches = 0
    prescriptive_tp = 0
    prescriptive_fp = 0
    prescriptive_fn = 0

    domain_f1_list: list[float] = []
    domain_p_list: list[float] = []
    domain_r_list: list[float] = []
    domain_overlap_total = 0
    domain_pred_total = 0
    domain_exp_total = 0

    purpose_f1_list: list[float] = []
    purpose_p_list: list[float] = []
    purpose_r_list: list[float] = []
    purpose_overlap_total = 0
    purpose_pred_total = 0
    purpose_exp_total = 0

    exact_auth_matches = 0
    exact_scope_matches = 0
    exact_lifecycle_matches = 0
    exact_rel_matches = 0
    exact_enf_matches = 0

    total_refs = len(references)

    for ref in references:
        ref_id = ref.reference_decision_id
        task_map = results_by_ref.get(ref_id, {})
        ref_errors: dict[str, str] = {}

        # 1. Classification
        c_res = task_map.get(ClassifierTaskType.DECISION_CLASSIFICATION)
        norm_class: str | None = None
        try:
            if c_res is None:
                raise NormalizationError("Missing result for classification")
            if "error" in c_res.output:
                raise NormalizationError(c_res.output["error"])
            val = c_res.output.get("classification")
            norm_class = normalize_classification(val)[0]
        except Exception as exc:
            ref_errors["classification"] = str(exc)

        is_exp_prescriptive = (ref.classification == "prescriptive")
        if norm_class is not None:
            if norm_class == ref.classification:
                exact_class_matches += 1
            is_pred_prescriptive = (norm_class == "prescriptive")
            if is_pred_prescriptive and is_exp_prescriptive:
                prescriptive_tp += 1
            elif is_pred_prescriptive and not is_exp_prescriptive:
                prescriptive_fp += 1
            elif not is_pred_prescriptive and is_exp_prescriptive:
                prescriptive_fn += 1
        else:
            if is_exp_prescriptive:
                prescriptive_fn += 1

        # 2. Domains
        d_res = task_map.get(ClassifierTaskType.DOMAINS)
        norm_domains: tuple[str, ...] | None = None
        try:
            if d_res is None:
                raise NormalizationError("Missing result for domains")
            if "error" in d_res.output:
                raise NormalizationError(d_res.output["error"])
            val = d_res.output.get("domains")
            norm_domains = normalize_domains(val)
        except Exception as exc:
            ref_errors["domains"] = str(exc)

        if norm_domains is not None:
            dp, dr, df1 = _evaluate_set_prf(ref.decision_domains, norm_domains)
            domain_p_list.append(dp)
            domain_r_list.append(dr)
            domain_f1_list.append(df1)
            e_set = set(ref.decision_domains)
            p_set = set(norm_domains)
            domain_overlap_total += len(e_set & p_set)
            domain_pred_total += len(p_set)
            domain_exp_total += len(e_set)
        else:
            domain_p_list.append(0.0)
            domain_r_list.append(0.0)
            domain_f1_list.append(0.0)
            domain_exp_total += len(ref.decision_domains)

        # 3. Purposes
        p_res = task_map.get(ClassifierTaskType.PURPOSES)
        norm_purposes: tuple[str, ...] | None = None
        try:
            if p_res is None:
                raise NormalizationError("Missing result for purposes")
            if "error" in p_res.output:
                raise NormalizationError(p_res.output["error"])
            val = p_res.output.get("purposes")
            norm_purposes = normalize_purposes(val)
        except Exception as exc:
            ref_errors["purposes"] = str(exc)

        if norm_purposes is not None:
            pp, pr, pf1 = _evaluate_set_prf(ref.decision_purposes, norm_purposes)
            purpose_p_list.append(pp)
            purpose_r_list.append(pr)
            purpose_f1_list.append(pf1)
            e_set = set(ref.decision_purposes)
            p_set = set(norm_purposes)
            purpose_overlap_total += len(e_set & p_set)
            purpose_pred_total += len(p_set)
            purpose_exp_total += len(e_set)
        else:
            purpose_p_list.append(0.0)
            purpose_r_list.append(0.0)
            purpose_f1_list.append(0.0)
            purpose_exp_total += len(ref.decision_purposes)

        # 4. Authority
        a_res = task_map.get(ClassifierTaskType.AUTHORITY)
        norm_auth: str | None = None
        try:
            if a_res is None:
                raise NormalizationError("Missing result for authority")
            if "error" in a_res.output:
                raise NormalizationError(a_res.output["error"])
            val = a_res.output.get("authority")
            norm_auth = normalize_authority(val)
        except Exception as exc:
            ref_errors["authority"] = str(exc)

        if norm_auth is not None and norm_auth == ref.authority_status:
            exact_auth_matches += 1

        # 5. Scope (exact set equality over (scope_type, scope_expression) tuples)
        s_res = task_map.get(ClassifierTaskType.SCOPE)
        norm_scopes: tuple | None = None
        try:
            if s_res is None:
                raise NormalizationError("Missing result for scopes")
            if "error" in s_res.output:
                raise NormalizationError(s_res.output["error"])
            val = s_res.output.get("scopes", [])
            norm_scopes = normalize_scopes(val)
        except Exception as exc:
            ref_errors["scopes"] = str(exc)

        if norm_scopes is not None:
            pred_scope_set = {(s.scope_type, s.scope_expression) for s in norm_scopes}
            exp_scope_set = {(s["scope_type"], s.get("scope_expression")) for s in ref.scopes}
            if pred_scope_set == exp_scope_set:
                exact_scope_matches += 1

        # 6. Lifecycle
        l_res = task_map.get(ClassifierTaskType.LIFECYCLE)
        norm_lc: str | None = None
        try:
            if l_res is None:
                raise NormalizationError("Missing result for lifecycle")
            if "error" in l_res.output:
                raise NormalizationError(l_res.output["error"])
            val = l_res.output.get("lifecycle")
            norm_lc = normalize_lifecycle(val)
        except Exception as exc:
            ref_errors["lifecycle"] = str(exc)

        if norm_lc is not None and norm_lc == ref.lifecycle_status:
            exact_lifecycle_matches += 1

        # 7. Relationships (exact set equality over (relationship_type, target_reference))
        r_res = task_map.get(ClassifierTaskType.RELATIONSHIPS)
        norm_rels: tuple | None = None
        try:
            if r_res is None:
                raise NormalizationError("Missing result for relationships")
            if "error" in r_res.output:
                raise NormalizationError(r_res.output["error"])
            val = r_res.output.get("relationships", [])
            norm_rels = normalize_relationships(val)
        except Exception as exc:
            ref_errors["relationships"] = str(exc)

        if norm_rels is not None:
            pred_rel_set = {(r.relationship_type, r.target_reference) for r in norm_rels}
            exp_rel_set = {(r["relationship_type"], r.get("target_reference")) for r in ref.relationships}
            if pred_rel_set == exp_rel_set:
                exact_rel_matches += 1

        # 8. Enforcement potential
        e_res = task_map.get(ClassifierTaskType.ENFORCEMENT_POTENTIAL)
        norm_enf: str | None = None
        try:
            if e_res is None:
                raise NormalizationError("Missing result for enforcement_potential")
            if "error" in e_res.output:
                raise NormalizationError(e_res.output["error"])
            val = e_res.output.get("enforcement_potential")
            norm_enf = normalize_enforcement_potential(val)
        except Exception as exc:
            ref_errors["enforcement_potential"] = str(exc)

        if norm_enf is not None and norm_enf == ref.enforcement_potential:
            exact_enf_matches += 1

        if ref_errors:
            incomplete_refs[ref_id] = ref_errors

        # Persist to ResearchStore if provided
        if research_store is not None and run_id is not None:
            # 1. Insert decision candidate for ref (discovery_confidence=None)
            research_store.insert_decision_candidate(
                DecisionCandidateRecord(
                    candidate_id=ref_id,
                    run_id=run_id,
                    source_id=None,
                    source_location=ref.source_location,
                    raw_evidence_reference=ref.raw_evidence[:200],
                    normalized_decision=ref.normalized_decision,
                    discovery_confidence=None,
                    discovery_metadata_json=json.dumps({"sampling_category": ref.sampling_category}),
                )
            )

            # Persist normalized semantic child rows only for dimensions that succeeded
            if norm_class is not None:
                cls_id = f"cls-{hashlib.sha256(f'{run_id}:{ref_id}:{norm_class}'.encode()).hexdigest()[:32]}"
                research_store.insert_candidate_classification(
                    CandidateClassificationRecord(
                        classification_id=cls_id,
                        candidate_id=ref_id,
                        run_id=run_id,
                        classification=norm_class,
                        classifier_version=classifier.classifier_version,
                        taxonomy_version="0.1",
                        confidence=c_res.confidence if c_res else None,
                        rationale=c_res.output.get("rationale") if c_res else None,
                        created_at=now_iso(),
                    )
                )

            if norm_domains is not None:
                for dom in norm_domains:
                    research_store.insert_candidate_domain(
                        CandidateDomainRecord(
                            candidate_id=ref_id,
                            run_id=run_id,
                            domain=dom,
                            confidence=d_res.confidence if d_res else None,
                            classifier_version=classifier.classifier_version,
                        )
                    )

            if norm_purposes is not None:
                for pur in norm_purposes:
                    research_store.insert_candidate_purpose(
                        CandidatePurposeRecord(
                            candidate_id=ref_id,
                            run_id=run_id,
                            purpose=pur,
                            confidence=p_res.confidence if p_res else None,
                            classifier_version=classifier.classifier_version,
                        )
                    )

            if norm_auth is not None:
                research_store.upsert_candidate_authority(
                    CandidateAuthorityRecord(
                        candidate_id=ref_id,
                        run_id=run_id,
                        authority_status=norm_auth,
                        authority_evidence=a_res.output.get("evidence") if a_res else None,
                        confidence=a_res.confidence if a_res else None,
                    )
                )

            if norm_scopes is not None:
                for sc in norm_scopes:
                    sc_id = f"sc-{hashlib.sha256(f'{run_id}:{ref_id}:{sc.scope_type}:{sc.scope_expression}'.encode()).hexdigest()[:32]}"
                    research_store.insert_candidate_scope(
                        CandidateScopeRecord(
                            scope_id=sc_id,
                            candidate_id=ref_id,
                            run_id=run_id,
                            scope_type=sc.scope_type,
                            scope_expression=sc.scope_expression,
                            confidence=s_res.confidence if s_res else None,
                            evidence_reference=None,
                        )
                    )

            if norm_lc is not None:
                l_data = l_res.output if l_res else {}
                research_store.upsert_candidate_lifecycle(
                    CandidateLifecycleRecord(
                        candidate_id=ref_id,
                        run_id=run_id,
                        lifecycle_status=norm_lc,
                        supersedes=l_data.get("supersedes"),
                        superseded_by=l_data.get("superseded_by"),
                        effective_date=l_data.get("effective_date"),
                        expiration_if_any=l_data.get("expiration_if_any"),
                        confidence=l_res.confidence if l_res else None,
                    )
                )

            if norm_rels is not None:
                for rel in norm_rels:
                    rel_id = f"rel-{hashlib.sha256(f'{run_id}:{ref_id}:{rel.relationship_type}:{rel.target_reference}'.encode()).hexdigest()[:32]}"
                    research_store.insert_candidate_relationship(
                        CandidateRelationshipRecord(
                            relationship_id=rel_id,
                            run_id=run_id,
                            source_candidate_id=ref_id,
                            relationship_type=rel.relationship_type,
                            target_candidate_id=None,
                            target_reference=rel.target_reference,
                            confidence=rel.confidence,
                            evidence_reference=rel.evidence_reference,
                        )
                    )

            if norm_enf is not None:
                e_data = e_res.output if e_res else {}
                research_store.upsert_enforcement_assessment(
                    EnforcementAssessmentRecord(
                        candidate_id=ref_id,
                        run_id=run_id,
                        enforcement_potential=norm_enf,
                        candidate_rule=e_data.get("candidate_rule"),
                        confidence=e_res.confidence if e_res else None,
                    )
                )

            # Persist raw ClassifierExecutionRecord for ALL 8 tasks (including failed/escalated ones)
            for task_type, r in task_map.items():
                research_store.insert_classifier_execution(
                    ClassifierExecutionRecord(
                        execution_id=r.execution_id,
                        candidate_id=ref_id,
                        run_id=run_id,
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

    # Prescriptive metrics
    presc_p = prescriptive_tp / (prescriptive_tp + prescriptive_fp) if (prescriptive_tp + prescriptive_fp) > 0 else 0.0
    presc_r = prescriptive_tp / (prescriptive_tp + prescriptive_fn) if (prescriptive_tp + prescriptive_fn) > 0 else 0.0
    presc_f1 = 2 * presc_p * presc_r / (presc_p + presc_r) if (presc_p + presc_r) > 0 else 0.0

    # Macro & micro averages for domains / purposes
    domain_macro_p = sum(domain_p_list) / total_refs if total_refs > 0 else 0.0
    domain_macro_r = sum(domain_r_list) / total_refs if total_refs > 0 else 0.0
    domain_macro_f1 = sum(domain_f1_list) / total_refs if total_refs > 0 else 0.0
    domain_micro_p = domain_overlap_total / domain_pred_total if domain_pred_total > 0 else 0.0
    domain_micro_r = domain_overlap_total / domain_exp_total if domain_exp_total > 0 else 0.0
    domain_micro_f1 = 2 * domain_micro_p * domain_micro_r / (domain_micro_p + domain_micro_r) if (domain_micro_p + domain_micro_r) > 0 else 0.0

    purpose_macro_p = sum(purpose_p_list) / total_refs if total_refs > 0 else 0.0
    purpose_macro_r = sum(purpose_r_list) / total_refs if total_refs > 0 else 0.0
    purpose_macro_f1 = sum(purpose_f1_list) / total_refs if total_refs > 0 else 0.0
    purpose_micro_p = purpose_overlap_total / purpose_pred_total if purpose_pred_total > 0 else 0.0
    purpose_micro_r = purpose_overlap_total / purpose_exp_total if purpose_exp_total > 0 else 0.0
    purpose_micro_f1 = 2 * purpose_micro_p * purpose_micro_r / (purpose_micro_p + purpose_micro_r) if (purpose_micro_p + purpose_micro_r) > 0 else 0.0

    metrics = {
        "decision_classification_accuracy": exact_class_matches / total_refs if total_refs > 0 else 0.0,
        "prescriptive_intent_precision": presc_p,
        "prescriptive_intent_recall": presc_r,
        "prescriptive_intent_f1": presc_f1,
        "domain_macro_precision": domain_macro_p,
        "domain_macro_recall": domain_macro_r,
        "domain_macro_f1": domain_macro_f1,
        "domain_micro_precision": domain_micro_p,
        "domain_micro_recall": domain_micro_r,
        "domain_micro_f1": domain_micro_f1,
        "purpose_macro_precision": purpose_macro_p,
        "purpose_macro_recall": purpose_macro_r,
        "purpose_macro_f1": purpose_macro_f1,
        "purpose_micro_precision": purpose_micro_p,
        "purpose_micro_recall": purpose_micro_r,
        "purpose_micro_f1": purpose_micro_f1,
        "authority_accuracy": exact_auth_matches / total_refs if total_refs > 0 else 0.0,
        "scope_accuracy": exact_scope_matches / total_refs if total_refs > 0 else 0.0,
        "lifecycle_accuracy": exact_lifecycle_matches / total_refs if total_refs > 0 else 0.0,
        "relationship_accuracy": exact_rel_matches / total_refs if total_refs > 0 else 0.0,
        "enforcement_classification_accuracy": exact_enf_matches / total_refs if total_refs > 0 else 0.0,
    }

    return StageBClassificationResult(
        repo_id=repository_config.id,
        reference_count=total_refs,
        task_count=len(tasks),
        classifier_backend=classifier.backend_id,
        classifier_version=classifier.classifier_version,
        model_identifier=classifier.model_identifier,
        metrics=metrics,
        results_by_ref=results_by_ref,
        incomplete_references=incomplete_refs,
    )


# ── E. Stage C: Isolated Human-Reference GDS ────────────────────────────────────


@dataclass(frozen=True)
class StageCGdsResult:
    repo_id: str
    scenario_count: int
    suite_metrics: dict[str, float]
    scenario_results: tuple[GoverningDecisionSetResult, ...]
    diagnostic_by_validation_state: dict[str, dict[str, float]]

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "repo_id": self.repo_id,
            "scenario_count": self.scenario_count,
            "suite_metrics": dict(self.suite_metrics),
            "diagnostic_by_validation_state": dict(self.diagnostic_by_validation_state),
        }


def execute_stage_c_gds(
    *,
    repository_config: RepositoryConfig,
    references: list[FrozenReferenceDecision],
    scenarios: list[ApplicabilityScenario],
    research_store: ResearchStore | None = None,
    run_id: str | None = None,
    classifier_version: str = "0.1",
) -> StageCGdsResult:
    """Execute Stage C isolated GDS evaluation projecting human reference decisions.

    Inputs are exclusively the 20 frozen human reference decisions for the repo,
    projected through existing frozen DecisionRetriever against the repository scenarios.
    All scenarios participate in the primary metric, with diagnostic breakdown by validation_state.
    """
    # 1. Adapt references to DecisionCandidate objects (candidate_id=ref-*)
    candidates = [r.to_decision_candidate() for r in references]

    # 2. Evaluate GDS using frozen retrieval batch evaluation
    results = evaluate_governing_decisions_batch(candidates, scenarios)
    suite = compute_suite_gds_metrics(list(results))

    # 3. Diagnostic breakdown by validation_state
    by_state: dict[str, list[GoverningDecisionSetResult]] = {}
    for r, s in zip(results, scenarios):
        by_state.setdefault(s.validation_state, []).append(r)

    diagnostic_by_state = {
        state: compute_suite_gds_metrics(res_list)
        for state, res_list in by_state.items()
    }

    # 4. Persist to ResearchStore if provided
    if research_store is not None and run_id is not None:
        for s in scenarios:
            research_store.insert_applicability_scenario(
                ApplicabilityScenarioRecord(
                    scenario_id=s.scenario_id,
                    repo_id=repository_config.id,
                    description=s.description,
                    path=s.change_context.path,
                    component=s.change_context.component,
                    change_type=s.change_context.change_type,
                    dependencies_json=json.dumps(list(s.change_context.dependencies)),
                    api_context=s.change_context.api,
                    technology_context=s.change_context.technology,
                    other_context=s.change_context.other_context,
                    validation_state=s.validation_state,
                )
            )
            for exp_id in s.expected_governing_decision_ids:
                research_store.insert_scenario_expected_decision(
                    ScenarioExpectedDecisionRecord(
                        scenario_id=s.scenario_id,
                        candidate_id=exp_id,
                    )
                )

        for gds_res in results:
            result_id = f"res-{hashlib.sha256(f'{run_id}:{gds_res.scenario_id}'.encode()).hexdigest()[:32]}"
            research_store.insert_scenario_result(
                ScenarioResultRecord(
                    result_id=result_id,
                    scenario_id=gds_res.scenario_id,
                    run_id=run_id,
                    classifier_version=classifier_version,
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

    return StageCGdsResult(
        repo_id=repository_config.id,
        scenario_count=len(scenarios),
        suite_metrics=suite,
        scenario_results=results,
        diagnostic_by_validation_state=diagnostic_by_state,
    )


# ── F. Batch Provenance Envelope ────────────────────────────────────────────────


@dataclass(frozen=True)
class BatchProvenanceEnvelope:
    """Immutable research batch provenance envelope preserving global corpus identity."""

    schema_version: str = "0.1"
    batch_id: str = FROZEN_BATCH_ID
    baseline_id: str = FROZEN_BASELINE_ID
    baseline_configuration_hash: str = FROZEN_BASELINE_CONFIG_HASH
    manifest_configuration_hash: str = FROZEN_MANIFEST_CONFIG_HASH
    reference_corpus_hash: str = FROZEN_REFERENCE_CORPUS_HASH
    scenario_corpus_hash: str = FROZEN_SCENARIO_CORPUS_HASH
    semantic_mneme_sha: str = FROZEN_SEMANTIC_MNEME_SHA
    harness_commit_sha: str = field(default_factory=_get_git_commit_sha)
    runs: dict[str, RunMetadata] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "batch_id": self.batch_id,
            "baseline_id": self.baseline_id,
            "baseline_configuration_hash": self.baseline_configuration_hash,
            "manifest_configuration_hash": self.manifest_configuration_hash,
            "reference_corpus_hash": self.reference_corpus_hash,
            "scenario_corpus_hash": self.scenario_corpus_hash,
            "semantic_mneme_sha": self.semantic_mneme_sha,
            "harness_commit_sha": self.harness_commit_sha,
            "runs": {repo_id: meta.to_dict() for repo_id, meta in sorted(self.runs.items())},
        }


__all__ = [
    "FROZEN_BATCH_ID",
    "FROZEN_BASELINE_ID",
    "FROZEN_BASELINE_CONFIG_HASH",
    "FROZEN_MANIFEST_CONFIG_HASH",
    "FROZEN_REFERENCE_CORPUS_HASH",
    "FROZEN_SCENARIO_CORPUS_HASH",
    "HarnessPreflightError",
    "BatchPreflightResult",
    "preflight_batch_01",
    "FrozenReferenceDecision",
    "load_reference_corpus",
    "parse_reference_intervals",
    "StageADiscoveryResult",
    "evaluate_discovery_matches",
    "evaluate_stage_a_discovery",
    "SEMANTIC_TASK_TYPES",
    "build_stage_b_tasks",
    "StageBClassificationResult",
    "execute_stage_b_classification",
    "StageCGdsResult",
    "execute_stage_c_gds",
    "BatchProvenanceEnvelope",
]
