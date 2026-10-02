"""
mneme.open_architecture.structural_extraction_experiment — T2B.1 Stage A Source Boundary Hygiene.

Implements research-only source boundary hygiene over the frozen Batch 01 source stream:
- T2B.1: Source Boundary Hygiene (excludes *_test.go and path component 'examples' for Go code).
- Preserves exact T2A.2 scoped lexical extraction semantics on all retained documents.
- Protects candidate identities, line spans, and raw statements identically to T2A.2.

Architecture and Boundary Invariants:
- Research-only sidecar: does NOT modify or parameterize candidates.py, discovery.py, or harness.py.
- Preserves frozen B0, corrected T1, and T2A baselines without mutation.
- Strict fail-closed predicate for Go source-code vs. documentation evidence.
- Zero model/API calls.
- Zero canonical authority writes (no MemoryStore, DecisionProposal, DecisionIndex mutations).
- Terminates strictly after Stage A discovery matching.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mneme.open_architecture.baseline import (
    BaselineConfig,
    validate_baseline_freeze,
)
from mneme.open_architecture.candidates import (
    CandidateExtractor,
    ExtractedCandidate,
)
from mneme.open_architecture.discovery import (
    DiscoveredSourceDocument,
    discover_sources,
)
from mneme.open_architecture.execution import (
    materialize_repository,
)
from mneme.open_architecture.export import compute_reference_corpus_content_hash
from mneme.open_architecture.extraction_tuning_experiment import (
    B0_STAGE_B_SEMANTIC_SCORE,
    B0_STAGE_C_APPLICABILITY_SCORE,
    FROZEN_BASELINE_ID,
    FROZEN_REFERENCE_CORPUS_HASH,
    FROZEN_REPOSITORY_SHAS,
    T2A2_CODE_KEYWORDS,
    T2A2_DOC_KEYWORDS,
    LexicalCandidateExtractor,
    _verify_and_prepare_output_dir,
    is_source_code_document,
)
from mneme.open_architecture.harness import (
    StageADiscoveryResult,
    evaluate_discovery_matches,
    load_reference_corpus,
)
from mneme.open_architecture.manifest import Manifest
from mneme.open_architecture.source_coverage_experiment import discover_go_sources

FROZEN_PARENT_MAIN_SHA: str = "3ccd5992a0035eea300ab5615674a2cdcedc5fde"

EXCLUSION_SUFFIX: str = "_test.go"
EXCLUSION_PATH_COMPONENT: str = "examples"


# ── Fail-Closed Exclusion Predicate ──────────────────────────────────────────


def is_excluded_go_source(doc: DiscoveredSourceDocument) -> bool:
    """Exact fail-closed predicate enforcing T2B.1 Go source boundary hygiene.

    Applies strictly to Go source code documents where is_source_code_document(doc) is True.
    Excludes a Go document if:
      - relative_path ends with '_test.go'
      OR
      - any normalized POSIX path component is exactly 'examples'

    Does not use loose substring matching.
    Never excludes documentation or non-Go documents.
    """
    if not is_source_code_document(doc):
        return False
    norm_path = doc.relative_path.replace("\\", "/")
    if norm_path.endswith(EXCLUSION_SUFFIX):
        return True
    parts = norm_path.split("/")
    if EXCLUSION_PATH_COMPONENT in parts:
        return True
    return False


# ── Profile Contract ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class T2B1SourceBoundaryHygieneProfile:
    """Immutable research experiment profile for T2B.1 Source Boundary Hygiene."""

    experiment_id: str = "t2b1-source-boundary-hygiene"
    baseline_id: str = FROZEN_BASELINE_ID
    parent_main_sha: str = FROZEN_PARENT_MAIN_SHA
    reference_corpus_hash: str = FROZEN_REFERENCE_CORPUS_HASH
    doc_keywords: tuple[str, ...] = tuple(sorted(T2A2_DOC_KEYWORDS))
    code_keywords: tuple[str, ...] = tuple(sorted(T2A2_CODE_KEYWORDS))
    target_repositories: tuple[str, ...] = tuple(sorted(FROZEN_REPOSITORY_SHAS.keys()))
    exclusion_suffix: str = EXCLUSION_SUFFIX
    exclusion_path_component: str = EXCLUSION_PATH_COMPONENT
    experiment_profile_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.experiment_id != "t2b1-source-boundary-hygiene":
            raise ValueError(f"experiment_id must be 't2b1-source-boundary-hygiene', got {self.experiment_id!r}")
        if self.baseline_id != FROZEN_BASELINE_ID:
            raise ValueError(f"baseline_id must be {FROZEN_BASELINE_ID!r}, got {self.baseline_id!r}")
        if self.parent_main_sha != FROZEN_PARENT_MAIN_SHA:
            raise ValueError(f"parent_main_sha must be {FROZEN_PARENT_MAIN_SHA!r}, got {self.parent_main_sha!r}")
        if self.reference_corpus_hash != FROZEN_REFERENCE_CORPUS_HASH:
            raise ValueError(f"reference_corpus_hash must be {FROZEN_REFERENCE_CORPUS_HASH!r}, got {self.reference_corpus_hash!r}")
        if self.doc_keywords != tuple(sorted(T2A2_DOC_KEYWORDS)):
            raise ValueError("doc_keywords must match T2A.2 doc vocabulary")
        if self.code_keywords != tuple(sorted(T2A2_CODE_KEYWORDS)):
            raise ValueError("code_keywords must match T2A.2 code vocabulary")
        if self.target_repositories != tuple(sorted(FROZEN_REPOSITORY_SHAS.keys())):
            raise ValueError("target_repositories must be exactly the 5 Batch 01 repositories")
        if self.exclusion_suffix != EXCLUSION_SUFFIX:
            raise ValueError(f"exclusion_suffix must be {EXCLUSION_SUFFIX!r}, got {self.exclusion_suffix!r}")
        if self.exclusion_path_component != EXCLUSION_PATH_COMPONENT:
            raise ValueError(f"exclusion_path_component must be {EXCLUSION_PATH_COMPONENT!r}, got {self.exclusion_path_component!r}")

        payload = {
            "baseline_id": self.baseline_id,
            "code_keywords": list(self.code_keywords),
            "doc_keywords": list(self.doc_keywords),
            "exclusion_rules": {
                "path_component": self.exclusion_path_component,
                "suffix": self.exclusion_suffix,
            },
            "experiment_id": self.experiment_id,
            "parent_main_sha": self.parent_main_sha,
            "reference_corpus_hash": self.reference_corpus_hash,
            "target_repositories": list(self.target_repositories),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
        object.__setattr__(self, "experiment_profile_hash", digest)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "baseline_id": self.baseline_id,
            "parent_main_sha": self.parent_main_sha,
            "reference_corpus_hash": self.reference_corpus_hash,
            "doc_keywords": list(self.doc_keywords),
            "code_keywords": list(self.code_keywords),
            "target_repositories": list(self.target_repositories),
            "exclusion_rules": {
                "path_component": self.exclusion_path_component,
                "suffix": self.exclusion_suffix,
            },
            "experiment_profile_hash": self.experiment_profile_hash,
        }


# ── Result Model ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class T2B1ExperimentResult:
    """Immutable result of a T2B.1 extraction tuning experiment run across all 5 repos."""

    profile: T2B1SourceBoundaryHygieneProfile
    repository_results: dict[str, StageADiscoveryResult]
    total_candidates: int
    matched_candidates: int
    total_references: int
    matched_references: int
    unmatched_references: int
    discovery_precision: float
    stage_a_recall: float
    stage_a_micro_f1: float
    overall_o1_score: float
    go_documents_before: int
    go_documents_after: int
    excluded_document_count: int
    excluded_candidate_count: int
    excluded_paths: tuple[str, ...]
    output_dir: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.to_dict(),
            "repository_results": {
                repo_id: res.to_dict()
                for repo_id, res in sorted(self.repository_results.items())
            },
            "hygiene_metrics": {
                "archlint_go_documents_before": self.go_documents_before,
                "archlint_go_documents_after": self.go_documents_after,
                "archlint_excluded_document_count": self.excluded_document_count,
                "archlint_excluded_candidate_count": self.excluded_candidate_count,
                "archlint_excluded_paths": list(self.excluded_paths),
            },
            "aggregate_metrics": {
                "total_candidates": self.total_candidates,
                "matched_candidates": self.matched_candidates,
                "total_references": self.total_references,
                "matched_references": self.matched_references,
                "unmatched_references": self.unmatched_references,
                "discovery_precision": self.discovery_precision,
                "stage_a_recall": self.stage_a_recall,
                "stage_a_micro_f1": self.stage_a_micro_f1,
                "b0_stage_b_semantic_score": B0_STAGE_B_SEMANTIC_SCORE,
                "b0_stage_c_applicability_score": B0_STAGE_C_APPLICABILITY_SCORE,
                "overall_o1_score": self.overall_o1_score,
            },
            "output_dir": str(self.output_dir),
        }


# ── Runner ────────────────────────────────────────────────────────────────────


def execute_t2b1_experiment(
    *,
    baseline_path: str | Path,
    manifest_path: str | Path,
    reference_corpus_dir: str | Path,
    output_dir: str | Path,
    clone_sources: dict[str, str | Path] | None = None,
    workspace_dir: str | Path | None = None,
    profile: T2B1SourceBoundaryHygieneProfile | None = None,
) -> T2B1ExperimentResult:
    """Execute T2B.1 Source Boundary Hygiene experiment across all five Batch 01 repositories."""
    if profile is None:
        profile = T2B1SourceBoundaryHygieneProfile()

    out_path = _verify_and_prepare_output_dir(output_dir)

    # 1. Enforce frozen baseline and manifest integrity
    baseline = BaselineConfig.load(baseline_path)
    manifest = Manifest.load(manifest_path)
    validate_baseline_freeze(baseline, manifest=manifest)

    # 2. Enforce frozen reference corpus content hash
    computed_ref_hash = compute_reference_corpus_content_hash(reference_corpus_dir)
    if (
        computed_ref_hash != profile.reference_corpus_hash
        or computed_ref_hash != FROZEN_REFERENCE_CORPUS_HASH
    ):
        raise ValueError(
            f"Reference corpus hash mismatch: computed {computed_ref_hash!r}, "
            f"expected {profile.reference_corpus_hash!r} "
            f"(frozen: {FROZEN_REFERENCE_CORPUS_HASH!r})"
        )

    # 3. Instantiate extractor with exact T2A.2 scoped vocabulary
    extractor: CandidateExtractor = LexicalCandidateExtractor(
        doc_keywords=T2A2_DOC_KEYWORDS,
        code_keywords=T2A2_CODE_KEYWORDS,
        extractor_id=profile.experiment_id,
    )

    all_refs = load_reference_corpus(reference_corpus_dir)
    repo_results: dict[str, StageADiscoveryResult] = {}
    repo_unique_candidates: dict[str, list[ExtractedCandidate]] = {}

    archlint_go_before = 0
    archlint_go_after = 0
    archlint_excluded_paths: list[str] = []
    archlint_excluded_cands_count = 0

    # 4. Execute extraction and Stage A matching per repository
    for repo_cfg in manifest.repositories:
        expected_sha = FROZEN_REPOSITORY_SHAS.get(repo_cfg.id)
        if expected_sha is None or repo_cfg.commit_sha != expected_sha:
            raise ValueError(
                f"Repository '{repo_cfg.id}' SHA {repo_cfg.commit_sha} does not match expected {expected_sha}"
            )

        repo_refs = [r for r in all_refs if r.repository == repo_cfg.github]
        if len(repo_refs) != 20:
            raise ValueError(f"Expected 20 references for '{repo_cfg.id}', got {len(repo_refs)}")

        repo_clone_source = (clone_sources or {}).get(repo_cfg.id)

        with materialize_repository(
            repo_cfg,
            workspace_dir=workspace_dir,
            clone_source=repo_clone_source,
        ) as checkout:
            if checkout.resolved_commit_sha.lower() != expected_sha.lower():
                raise ValueError(
                    f"Resolved SHA {checkout.resolved_commit_sha} does not match expected {expected_sha}"
                )

            # Discover documentation
            doc_disc = discover_sources(checkout)
            docs = list(doc_disc.documents)

            # Discover Go sources strictly for Archlint with T2B.1 hygiene filtering
            if repo_cfg.id == "archlint":
                go_disc = discover_go_sources(checkout)
                go_docs = list(go_disc.documents)
                archlint_go_before = len(go_docs)

                excluded_go_docs = [d for d in go_docs if is_excluded_go_source(d)]
                retained_go_docs = [d for d in go_docs if not is_excluded_go_source(d)]
                archlint_go_after = len(retained_go_docs)
                archlint_excluded_paths = sorted(d.relative_path for d in excluded_go_docs)

                # Extract candidates from excluded Go docs to measure excluded candidate count
                raw_excluded_cands: list[ExtractedCandidate] = []
                for d in excluded_go_docs:
                    raw_excluded_cands.extend(extractor.extract(d, checkout.resolved_commit_sha))
                seen_ex: set[str] = set()
                uniq_excluded_cands: list[ExtractedCandidate] = []
                for c in raw_excluded_cands:
                    if c.candidate_id not in seen_ex:
                        seen_ex.add(c.candidate_id)
                        uniq_excluded_cands.append(c)
                archlint_excluded_cands_count = len(uniq_excluded_cands)

                docs.extend(retained_go_docs)

            docs.sort(key=lambda d: d.relative_path)
            discovered_paths = {d.relative_path for d in docs}

            # Extract candidates
            raw_cands: list[ExtractedCandidate] = []
            for d in docs:
                raw_cands.extend(extractor.extract(d, checkout.resolved_commit_sha))

            # Deduplicate by candidate_id
            seen_cand: set[str] = set()
            uniq_cands: list[ExtractedCandidate] = []
            for c in raw_cands:
                if c.candidate_id not in seen_cand:
                    seen_cand.add(c.candidate_id)
                    uniq_cands.append(c)

            repo_unique_candidates[repo_cfg.id] = uniq_cands

            stage_a_res = evaluate_discovery_matches(
                candidates=uniq_cands,
                discovered_paths=discovered_paths,
                references=repo_refs,
                repo_id=repo_cfg.id,
                discovered_documents_count=len(docs),
            )

            # Strict Recall Gate
            if stage_a_res.matched_reference_count < stage_a_res.reference_decisions_count:
                raise ValueError(
                    f"Recall gate failed for repository '{repo_cfg.id}': "
                    f"matched {stage_a_res.matched_reference_count}/{stage_a_res.reference_decisions_count}"
                )

            repo_results[repo_cfg.id] = stage_a_res

    # 5. Calculate benchmark aggregate metrics
    tot_cands = sum(res.extracted_candidates_count for res in repo_results.values())
    tot_matched_cands = sum(res.matched_candidate_count for res in repo_results.values())
    tot_refs = sum(res.reference_decisions_count for res in repo_results.values())  # 100
    tot_matched_refs = sum(res.matched_reference_count for res in repo_results.values())

    precision = tot_matched_cands / tot_cands if tot_cands > 0 else 0.0
    recall = tot_matched_refs / tot_refs if tot_refs > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    overall_o1 = (f1 + B0_STAGE_B_SEMANTIC_SCORE + B0_STAGE_C_APPLICABILITY_SCORE) / 3.0

    # 6. Emit deterministic artifacts
    summary_data = {
        "experiment_id": profile.experiment_id,
        "profile": profile.to_dict(),
        "parent_main_sha": profile.parent_main_sha,
        "hygiene_metrics": {
            "archlint_go_documents_before": archlint_go_before,
            "archlint_go_documents_after": archlint_go_after,
            "archlint_excluded_document_count": len(archlint_excluded_paths),
            "archlint_excluded_candidate_count": archlint_excluded_cands_count,
            "archlint_excluded_paths": archlint_excluded_paths,
        },
        "repositories": {
            repo_id: res.to_dict()
            for repo_id, res in sorted(repo_results.items())
        },
        "aggregate": {
            "total_candidates": tot_cands,
            "matched_candidates": tot_matched_cands,
            "total_references": tot_refs,
            "matched_references": tot_matched_refs,
            "unmatched_references": tot_refs - tot_matched_refs,
            "discovery_precision": precision,
            "stage_a_recall": recall,
            "stage_a_micro_f1": f1,
            "b0_stage_b_semantic_score": B0_STAGE_B_SEMANTIC_SCORE,
            "b0_stage_c_applicability_score": B0_STAGE_C_APPLICABILITY_SCORE,
            "overall_o1_score": overall_o1,
        },
    }

    (out_path / "t2b1_summary.json").write_text(
        json.dumps(summary_data, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    # Emit candidate_matches.jsonl covering every unique candidate across all repositories
    cand_lines: list[str] = []
    for repo_id in sorted(repo_results.keys()):
        stage_a_res = repo_results[repo_id]
        cand_to_ref = stage_a_res.cand_to_ref_matches
        repo_cands = repo_unique_candidates[repo_id]
        for c in sorted(repo_cands, key=lambda x: x.candidate_id):
            matched_refs = sorted(cand_to_ref.get(c.candidate_id, []))
            rec = {
                "candidate_id": c.candidate_id,
                "end_line": c.source_location.end_line,
                "matched": len(matched_refs) > 0,
                "matched_reference_ids": matched_refs,
                "repository": repo_id,
                "source_location": c.location_string,
                "source_path": c.source_path,
                "start_line": c.source_location.start_line,
            }
            cand_lines.append(json.dumps(rec, sort_keys=True))

    (out_path / "t2b1_candidate_matches.jsonl").write_text(
        "\n".join(cand_lines) + "\n",
        encoding="utf-8",
    )

    return T2B1ExperimentResult(
        profile=profile,
        repository_results=repo_results,
        total_candidates=tot_cands,
        matched_candidates=tot_matched_cands,
        total_references=tot_refs,
        matched_references=tot_matched_refs,
        unmatched_references=tot_refs - tot_matched_refs,
        discovery_precision=precision,
        stage_a_recall=recall,
        stage_a_micro_f1=f1,
        overall_o1_score=overall_o1,
        go_documents_before=archlint_go_before,
        go_documents_after=archlint_go_after,
        excluded_document_count=len(archlint_excluded_paths),
        excluded_candidate_count=archlint_excluded_cands_count,
        excluded_paths=tuple(archlint_excluded_paths),
        output_dir=out_path,
    )
