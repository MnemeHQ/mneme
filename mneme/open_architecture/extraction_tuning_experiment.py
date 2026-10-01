"""
mneme.open_architecture.extraction_tuning_experiment — T2A Stage A extraction tuning experiments.

Implements research-only lexical extraction tuning over the frozen Batch 01 source stream:
- T2A.1: Global Lexical Control (+supersede, +deprecate, +allow globally)
- T2A.2: Scoped Lexical Treatment (+supersede, +deprecate for docs; +allow for Go code)

Architecture and Boundary Invariants:
- Research-only sidecar: does NOT modify or parameterize candidates.py, discovery.py, or harness.py.
- Preserves frozen B0 and corrected T1 baselines without mutation.
- Strict fail-closed metadata predicate for Go source-code vs. documentation evidence.
- Zero model/API calls.
- Zero canonical authority writes (no MemoryStore, DecisionProposal, DecisionIndex mutations).
- Terminates strictly after Stage A discovery matching.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
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
    HeuristicExtractor,
    LineSpan,
)
from mneme.open_architecture.discovery import (
    DEFAULT_MAX_DOCUMENT_BYTES,
    DiscoveredSourceDocument,
    DiscoveryResult,
    discover_sources,
)
from mneme.open_architecture.execution import (
    RepositoryCheckout,
    materialize_repository,
)
from mneme.open_architecture.export import compute_reference_corpus_content_hash
from mneme.open_architecture.harness import (
    FrozenReferenceDecision,
    StageADiscoveryResult,
    evaluate_discovery_matches,
    load_reference_corpus,
)
from mneme.open_architecture.manifest import Manifest, RepositoryConfig
from mneme.open_architecture.source_coverage_experiment import discover_go_sources

FROZEN_BASELINE_ID: str = "o1a-batch-01-baseline"
FROZEN_PARENT_MAIN_SHA: str = "f098955711d9260b4c238769359d4a29a5bab922"
FROZEN_REFERENCE_CORPUS_HASH: str = "0455bd66aae52551c35b37a63c2d185f"

B0_STAGE_B_SEMANTIC_SCORE: float = 0.517188
B0_STAGE_C_APPLICABILITY_SCORE: float = 0.103728

# Base decision keywords frozen from HeuristicExtractor (26 terms)
FROZEN_BASE_KEYWORDS: frozenset[str] = frozenset({
    "adopt", "adopted", "always", "avoid", "decide", "decided", "decision",
    "forbid", "forbidden", "mandate", "mandated", "must", "never", "prefer",
    "preferred", "prohibit", "prohibited", "require", "required", "shall",
    "should not", "standard", "standardised", "standardize", "use", "using",
})

# Minimal root vocabulary extensions
LIFECYCLE_ROOT_KEYWORDS: frozenset[str] = frozenset({"supersede", "deprecate"})
PERMISSION_ROOT_KEYWORDS: frozenset[str] = frozenset({"allow"})

# Mode keyword sets
T2A1_GLOBAL_KEYWORDS: frozenset[str] = (
    FROZEN_BASE_KEYWORDS | LIFECYCLE_ROOT_KEYWORDS | PERMISSION_ROOT_KEYWORDS
)
T2A2_DOC_KEYWORDS: frozenset[str] = FROZEN_BASE_KEYWORDS | LIFECYCLE_ROOT_KEYWORDS
T2A2_CODE_KEYWORDS: frozenset[str] = FROZEN_BASE_KEYWORDS | PERMISSION_ROOT_KEYWORDS

# Frozen approved Batch 01 repositories and commit SHAs
FROZEN_REPOSITORY_SHAS: dict[str, str] = {
    "adrkit": "471457da29638ecca6119b35180c2845bf989cac",
    "gsa_agentic_coding_quickstart": "8e6160c63acc35bd48d0a3844e133ea3ad52a464",
    "helix": "37d994370deba2512588b5c4efb7f03483e7308b",
    "archlint": "185837e93565718d8e1ea653236cd70ca0a89e3a",
    "modonome": "7a4d5244dcb6879b6aa646105b39297aa6d0a5a2",
}


# ── Fail-Closed Source-Code Predicate ──────────────────────────────────────────


def is_source_code_document(doc: DiscoveredSourceDocument) -> bool:
    """Exact fail-closed predicate strictly enforcing the T1 source-code metadata contract.

    Returns True ONLY when all three metadata markers are present and match:
    - metadata["evidence_kind"] == "source_code"
    - metadata["language"] == "go"
    - metadata["extension"] == ".go"

    All other documents are classified as documentation evidence.
    Does not use source_type, path suffix fallback, or OR logic.
    """
    meta = doc.metadata
    return (
        meta.get("evidence_kind") == "source_code"
        and meta.get("language") == "go"
        and meta.get("extension") == ".go"
    )


# ── Span Construction Helpers ──────────────────────────────────────────────────


_HEADING_PATTERN = re.compile(r"^\s*#{1,6}\s+")


def _find_headings(lines: list[str]) -> list[int]:
    """Find 0-indexed line numbers of markdown headings."""
    return [i for i, line in enumerate(lines) if _HEADING_PATTERN.match(line)]


def _build_spans(lines: list[str], headings: list[int]) -> list[LineSpan]:
    """Build candidate spans between headings (or single document span if 0 headings)."""
    spans: list[LineSpan] = []
    total_lines = len(lines)

    if not headings:
        spans.append(LineSpan(1, total_lines))
        return spans

    if headings[0] > 0:
        spans.append(LineSpan(1, headings[0]))

    for i in range(len(headings)):
        start = headings[i] + 1
        end = headings[i + 1] if i + 1 < len(headings) else total_lines
        if start <= end:
            spans.append(LineSpan(start, end))

    return spans


def _split_span(span: LineSpan, max_lines: int = 50) -> list[LineSpan]:
    """Split a large span into smaller chunks of at most max_lines."""
    sub_spans: list[LineSpan] = []
    remaining = span.line_count()
    start = span.start_line
    while remaining > 0:
        chunk_size = min(max_lines, remaining)
        sub_spans.append(LineSpan(start, start + chunk_size - 1))
        start += chunk_size
        remaining -= chunk_size
    return sub_spans


# ── Experimental Extractors ────────────────────────────────────────────────────


class LexicalCandidateExtractor:
    """Deterministic candidate extractor implementing the CandidateExtractor protocol.

    Preserves the frozen heading-based and 50-line window chunking mechanics
    while supporting configurable document-scoped and code-scoped keyword sets.
    """

    def __init__(
        self,
        *,
        doc_keywords: frozenset[str],
        code_keywords: frozenset[str],
        extractor_id: str,
        extractor_version: str = "0.1",
        min_lines: int = 2,
        max_lines: int = 50,
        confidence: float = 0.5,
    ) -> None:
        self.doc_keywords = doc_keywords
        self.code_keywords = code_keywords
        self._extractor_id = extractor_id
        self._extractor_version = extractor_version
        self.min_lines = min_lines
        self.max_lines = max_lines
        self.confidence = confidence

    @property
    def extractor_id(self) -> str:
        return self._extractor_id

    @property
    def extractor_version(self) -> str:
        return self._extractor_version

    def extract(
        self,
        document: DiscoveredSourceDocument,
        repo_commit_sha: str,
    ) -> list[ExtractedCandidate]:
        candidates: list[ExtractedCandidate] = []
        lines = document.content.splitlines()
        if not lines:
            return candidates

        # Determine active keyword vocabulary via fail-closed predicate
        active_keywords = (
            self.code_keywords
            if is_source_code_document(document)
            else self.doc_keywords
        )

        heading_indices = _find_headings(lines)
        spans = _build_spans(lines, heading_indices)

        for span in spans:
            if span.line_count() < self.min_lines:
                continue
            if span.line_count() > self.max_lines:
                for sub_span in _split_span(span, self.max_lines):
                    if sub_span.line_count() >= self.min_lines:
                        self._try_add_candidate(
                            candidates, document, repo_commit_sha, sub_span, active_keywords
                        )
            else:
                self._try_add_candidate(
                    candidates, document, repo_commit_sha, span, active_keywords
                )

        return candidates

    def _try_add_candidate(
        self,
        candidates: list[ExtractedCandidate],
        document: DiscoveredSourceDocument,
        repo_commit_sha: str,
        span: LineSpan,
        keywords: frozenset[str],
    ) -> None:
        lines = document.content.splitlines()
        start = span.start_line - 1
        end = span.end_line
        text = "\n".join(lines[start:end]).lower()

        if not any(kw in text for kw in keywords):
            return

        try:
            candidate = ExtractedCandidate.from_source_document(
                doc=document,
                repo_commit_sha=repo_commit_sha,
                line_span=span,
                discovery_confidence=self.confidence,
                metadata={
                    "extractor": self.extractor_id,
                    "extractor_version": self.extractor_version,
                },
            )
            candidates.append(candidate)
        except ValueError:
            pass


# ── Profile Contracts ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class T2A1GlobalLexicalProfile:
    """Immutable research experiment profile for T2A.1 Global Lexical Control."""

    experiment_id: str = "t2a1-global-lexical"
    baseline_id: str = FROZEN_BASELINE_ID
    parent_main_sha: str = FROZEN_PARENT_MAIN_SHA
    reference_corpus_hash: str = FROZEN_REFERENCE_CORPUS_HASH
    keywords: tuple[str, ...] = tuple(sorted(T2A1_GLOBAL_KEYWORDS))
    target_repositories: tuple[str, ...] = tuple(sorted(FROZEN_REPOSITORY_SHAS.keys()))
    experiment_profile_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.experiment_id != "t2a1-global-lexical":
            raise ValueError(f"experiment_id must be 't2a1-global-lexical', got {self.experiment_id!r}")
        if self.baseline_id != FROZEN_BASELINE_ID:
            raise ValueError(f"baseline_id must be {FROZEN_BASELINE_ID!r}, got {self.baseline_id!r}")
        if self.parent_main_sha != FROZEN_PARENT_MAIN_SHA:
            raise ValueError(f"parent_main_sha must be {FROZEN_PARENT_MAIN_SHA!r}, got {self.parent_main_sha!r}")
        if self.reference_corpus_hash != FROZEN_REFERENCE_CORPUS_HASH:
            raise ValueError(f"reference_corpus_hash must be {FROZEN_REFERENCE_CORPUS_HASH!r}, got {self.reference_corpus_hash!r}")
        if self.keywords != tuple(sorted(T2A1_GLOBAL_KEYWORDS)):
            raise ValueError(f"keywords must be exactly the 29 T2A.1 terms, got {self.keywords!r}")
        if self.target_repositories != tuple(sorted(FROZEN_REPOSITORY_SHAS.keys())):
            raise ValueError("target_repositories must be exactly the 5 Batch 01 repositories")

        payload = {
            "baseline_id": self.baseline_id,
            "experiment_id": self.experiment_id,
            "keywords": list(self.keywords),
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
            "keywords": list(self.keywords),
            "target_repositories": list(self.target_repositories),
            "experiment_profile_hash": self.experiment_profile_hash,
        }


@dataclass(frozen=True)
class T2A2ScopedLexicalProfile:
    """Immutable research experiment profile for T2A.2 Scoped Lexical Treatment."""

    experiment_id: str = "t2a2-scoped-lexical"
    baseline_id: str = FROZEN_BASELINE_ID
    parent_main_sha: str = FROZEN_PARENT_MAIN_SHA
    reference_corpus_hash: str = FROZEN_REFERENCE_CORPUS_HASH
    doc_keywords: tuple[str, ...] = tuple(sorted(T2A2_DOC_KEYWORDS))
    code_keywords: tuple[str, ...] = tuple(sorted(T2A2_CODE_KEYWORDS))
    target_repositories: tuple[str, ...] = tuple(sorted(FROZEN_REPOSITORY_SHAS.keys()))
    experiment_profile_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.experiment_id != "t2a2-scoped-lexical":
            raise ValueError(f"experiment_id must be 't2a2-scoped-lexical', got {self.experiment_id!r}")
        if self.baseline_id != FROZEN_BASELINE_ID:
            raise ValueError(f"baseline_id must be {FROZEN_BASELINE_ID!r}, got {self.baseline_id!r}")
        if self.parent_main_sha != FROZEN_PARENT_MAIN_SHA:
            raise ValueError(f"parent_main_sha must be {FROZEN_PARENT_MAIN_SHA!r}, got {self.parent_main_sha!r}")
        if self.reference_corpus_hash != FROZEN_REFERENCE_CORPUS_HASH:
            raise ValueError(f"reference_corpus_hash must be {FROZEN_REFERENCE_CORPUS_HASH!r}, got {self.reference_corpus_hash!r}")
        if self.doc_keywords != tuple(sorted(T2A2_DOC_KEYWORDS)):
            raise ValueError(f"doc_keywords must be exactly the 28 T2A.2 doc terms, got {self.doc_keywords!r}")
        if self.code_keywords != tuple(sorted(T2A2_CODE_KEYWORDS)):
            raise ValueError(f"code_keywords must be exactly the 27 T2A.2 code terms, got {self.code_keywords!r}")
        if self.target_repositories != tuple(sorted(FROZEN_REPOSITORY_SHAS.keys())):
            raise ValueError("target_repositories must be exactly the 5 Batch 01 repositories")

        payload = {
            "baseline_id": self.baseline_id,
            "code_keywords": list(self.code_keywords),
            "doc_keywords": list(self.doc_keywords),
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
            "experiment_profile_hash": self.experiment_profile_hash,
        }


# ── Result Model & Execution Runner ────────────────────────────────────────────


@dataclass(frozen=True)
class T2AExperimentResult:
    """Immutable result of a T2A extraction tuning experiment run across all 5 repos."""

    profile: T2A1GlobalLexicalProfile | T2A2ScopedLexicalProfile
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
    output_dir: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.to_dict(),
            "repository_results": {
                repo_id: res.to_dict()
                for repo_id, res in sorted(self.repository_results.items())
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


def _verify_and_prepare_output_dir(output_dir: str | Path) -> Path:
    """Enforce fail-closed output directory rules:

    - path absent -> create directory
    - directory exists and is empty -> allowed
    - directory exists and is non-empty -> refuse
    - path exists and is not a directory -> refuse
    """
    out_path = Path(output_dir)
    if out_path.is_dir():
        if any(out_path.iterdir()):
            raise ValueError(
                f"output_dir '{out_path}' already exists and is not empty. Overwrite prevented."
            )
    elif out_path.exists():
        raise ValueError(f"output_dir '{out_path}' exists and is not a directory.")
    else:
        out_path.mkdir(parents=True, exist_ok=True)
    return out_path


def execute_t2a_experiment(
    *,
    profile: T2A1GlobalLexicalProfile | T2A2ScopedLexicalProfile,
    baseline_path: str | Path,
    manifest_path: str | Path,
    reference_corpus_dir: str | Path,
    output_dir: str | Path,
    clone_sources: dict[str, str | Path] | None = None,
    workspace_dir: str | Path | None = None,
) -> T2AExperimentResult:
    """Execute a T2A extraction tuning experiment across all five Batch 01 repositories.

    Workflow:
    1. Validates output_dir with fail-closed non-empty overwrite guard.
    2. Enforces baseline/manifest freeze validation and reference corpus hash check.
    3. Iterates over all five approved repositories, verifying pinned SHAs.
    4. Gathers discovered documents:
       - discover_sources() for all five
       - discover_go_sources() strictly for Archlint
    5. Applies the experimental extractor (Global or Scoped) matching the profile.
    6. Deduplicates candidates deterministically by candidate_id.
    7. Evaluates Stage A matches using evaluate_discovery_matches().
    8. Calculates exact aggregate Stage A and Overall O1 scores.
    9. Emits deterministic artifacts: summary JSON and candidate matches JSONL.
    10. Terminates strictly after Stage A with zero model calls and zero canonical writes.
    """
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

    # 3. Instantiate appropriate extractor
    if isinstance(profile, T2A1GlobalLexicalProfile):
        extractor: CandidateExtractor = LexicalCandidateExtractor(
            doc_keywords=T2A1_GLOBAL_KEYWORDS,
            code_keywords=T2A1_GLOBAL_KEYWORDS,
            extractor_id=profile.experiment_id,
        )
        artifact_prefix = "t2a1"
    elif isinstance(profile, T2A2ScopedLexicalProfile):
        extractor = LexicalCandidateExtractor(
            doc_keywords=T2A2_DOC_KEYWORDS,
            code_keywords=T2A2_CODE_KEYWORDS,
            extractor_id=profile.experiment_id,
        )
        artifact_prefix = "t2a2"
    else:
        raise TypeError(f"Unsupported profile type: {type(profile)!r}")

    all_refs = load_reference_corpus(reference_corpus_dir)
    repo_results: dict[str, StageADiscoveryResult] = {}
    all_unique_candidates: list[ExtractedCandidate] = []

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

            # Discover Go sources strictly for Archlint
            if repo_cfg.id == "archlint":
                go_disc = discover_go_sources(checkout)
                docs.extend(go_disc.documents)

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

            all_unique_candidates.extend(uniq_cands)

            stage_a_res = evaluate_discovery_matches(
                candidates=uniq_cands,
                discovered_paths=discovered_paths,
                references=repo_refs,
                repo_id=repo_cfg.id,
                discovered_documents_count=len(docs),
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

    (out_path / f"{artifact_prefix}_summary.json").write_text(
        json.dumps(summary_data, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    # Emit candidate_matches.jsonl
    repo_github_map = {r.id: r.github for r in manifest.repositories}
    cand_lines: list[str] = []
    for repo_id, stage_a_res in sorted(repo_results.items()):
        cand_to_ref = stage_a_res.cand_to_ref_matches
        repo_cands = [c for c in all_unique_candidates if c.repository_identifier == repo_github_map[repo_id]]
        for c in sorted(repo_cands, key=lambda x: x.candidate_id):
            matched_refs = sorted(cand_to_ref.get(c.candidate_id, []))
            rec = {
                "repository": repo_id,
                "candidate_id": c.candidate_id,
                "source_path": c.source_path,
                "source_location": c.location_string,
                "start_line": c.source_location.start_line,
                "end_line": c.source_location.end_line,
                "matched": len(matched_refs) > 0,
                "matched_reference_ids": matched_refs,
            }
            cand_lines.append(json.dumps(rec, sort_keys=True))

    (out_path / f"{artifact_prefix}_candidate_matches.jsonl").write_text(
        "\n".join(cand_lines) + "\n",
        encoding="utf-8",
    )

    return T2AExperimentResult(
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
        output_dir=out_path,
    )


def execute_t2a1_experiment(
    *,
    baseline_path: str | Path,
    manifest_path: str | Path,
    reference_corpus_dir: str | Path,
    output_dir: str | Path,
    clone_sources: dict[str, str | Path] | None = None,
    workspace_dir: str | Path | None = None,
) -> T2AExperimentResult:
    """Convenience runner for T2A.1 Global Lexical Control."""
    return execute_t2a_experiment(
        profile=T2A1GlobalLexicalProfile(),
        baseline_path=baseline_path,
        manifest_path=manifest_path,
        reference_corpus_dir=reference_corpus_dir,
        output_dir=output_dir,
        clone_sources=clone_sources,
        workspace_dir=workspace_dir,
    )


def execute_t2a2_experiment(
    *,
    baseline_path: str | Path,
    manifest_path: str | Path,
    reference_corpus_dir: str | Path,
    output_dir: str | Path,
    clone_sources: dict[str, str | Path] | None = None,
    workspace_dir: str | Path | None = None,
) -> T2AExperimentResult:
    """Convenience runner for T2A.2 Scoped Lexical Treatment."""
    return execute_t2a_experiment(
        profile=T2A2ScopedLexicalProfile(),
        baseline_path=baseline_path,
        manifest_path=manifest_path,
        reference_corpus_dir=reference_corpus_dir,
        output_dir=output_dir,
        clone_sources=clone_sources,
        workspace_dir=workspace_dir,
    )


__all__ = [
    "FROZEN_BASELINE_ID",
    "FROZEN_PARENT_MAIN_SHA",
    "FROZEN_REFERENCE_CORPUS_HASH",
    "FROZEN_BASE_KEYWORDS",
    "LIFECYCLE_ROOT_KEYWORDS",
    "PERMISSION_ROOT_KEYWORDS",
    "T2A1_GLOBAL_KEYWORDS",
    "T2A2_DOC_KEYWORDS",
    "T2A2_CODE_KEYWORDS",
    "FROZEN_REPOSITORY_SHAS",
    "is_source_code_document",
    "LexicalCandidateExtractor",
    "T2A1GlobalLexicalProfile",
    "T2A2ScopedLexicalProfile",
    "T2AExperimentResult",
    "execute_t2a_experiment",
    "execute_t2a1_experiment",
    "execute_t2a2_experiment",
]
