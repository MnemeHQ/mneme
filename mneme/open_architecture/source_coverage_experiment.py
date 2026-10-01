"""
mneme.open_architecture.source_coverage_experiment — T1 Stage A discovery coverage experiment.

Evaluates whether making repository source-code evidence reachable (.go files in Archlint)
improves Stage A discovery metrics while holding candidate extraction mechanics strictly
frozen to the reference HeuristicExtractor.

Architecture and Safety Rules:
- Research-only sidecar: does NOT modify or parameterize frozen discovery.py or candidates.py.
- Untrusted repository contents: read files only, never execute, never follow symlinks or junctions.
- Zero model/API calls.
- Zero canonical writes: does not write canonical project authority or memory state.
- Decouples Source Coverage (file reachability) from Stage A Recall (candidate line overlap).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mneme.open_architecture.candidates import ExtractedCandidate, HeuristicExtractor
from mneme.open_architecture.discovery import (
    DEFAULT_MAX_DOCUMENT_BYTES,
    DiscoveredSourceDocument,
    DiscoveryResult,
    SourceDiscoveryDiagnostic,
    discover_sources,
)
from mneme.open_architecture.execution import RepositoryCheckout, materialize_repository
from mneme.open_architecture.export import compute_reference_corpus_content_hash
from mneme.open_architecture.harness import (
    FrozenReferenceDecision,
    StageADiscoveryResult,
    evaluate_discovery_matches,
    load_reference_corpus,
)
from mneme.open_architecture.manifest import RepositoryConfig

PINNED_ARCHLINT_REPO_ID: str = "archlint"
PINNED_ARCHLINT_GITHUB: str = "muhammetsafak/archlint"
PINNED_ARCHLINT_SHA: str = "185837e93565718d8e1ea653236cd70ca0a89e3a"
FROZEN_BASELINE_ID: str = "o1a-batch-01-baseline"
FROZEN_REFERENCE_CORPUS_HASH: str = "0455bd66aae52551c35b37a63c2d185f"

# Authoritative B0 Stage B and Stage C scores (frozen)
B0_STAGE_B_SEMANTIC_SCORE: float = 0.517188
B0_STAGE_C_APPLICABILITY_SCORE: float = 0.103728

# Frozen B0 Stage A totals across the four non-Archlint repositories:
# adrkit, gsa_agentic_coding_quickstart, helix, modonome.
# In B0, Archlint contributed: 16 candidates, 6 matched candidates, 6 matched refs.
# Global B0 had: 5,459 candidates, 256 matched candidates, 85 matched refs, 100 refs total.
B0_OTHER_REPOS_CANDIDATES: int = 5459 - 16  # 5,443
B0_OTHER_REPOS_MATCHED_CANDIDATES: int = 256 - 6  # 250
B0_OTHER_REPOS_MATCHED_REFERENCES: int = 85 - 6  # 79
B0_OTHER_REPOS_TOTAL_REFERENCES: int = 80
B0_OTHER_REPOS_SOURCE_COVERED_REFERENCES: int = 80


# ── Profile Model ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SourceCoverageExperimentProfile:
    """Immutable research experiment profile for T1 source coverage experiments.

    Attributes:
        experiment_id: Unique experiment slug (default 't1-source-coverage-go').
        baseline_id: Benchmark baseline identity (default 'o1a-batch-01-baseline').
        target_repository: Target repository identifier (default 'archlint').
        target_extension: Target source-code file extension (strictly '.go').
        reference_corpus_hash: Pinned reference corpus digest.
        experiment_profile_hash: Deterministically derived hex digest over profile inputs.
    """

    experiment_id: str = "t1-source-coverage-go"
    baseline_id: str = FROZEN_BASELINE_ID
    target_repository: str = PINNED_ARCHLINT_REPO_ID
    target_extension: str = ".go"
    reference_corpus_hash: str = FROZEN_REFERENCE_CORPUS_HASH
    experiment_profile_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.experiment_id != "t1-source-coverage-go":
            raise ValueError(
                f"experiment_id must be strictly 't1-source-coverage-go', got {self.experiment_id!r}"
            )
        if self.baseline_id != FROZEN_BASELINE_ID:
            raise ValueError(
                f"baseline_id must be strictly {FROZEN_BASELINE_ID!r}, got {self.baseline_id!r}"
            )
        if self.target_repository != PINNED_ARCHLINT_REPO_ID:
            raise ValueError(
                f"target_repository must be strictly {PINNED_ARCHLINT_REPO_ID!r}, got {self.target_repository!r}"
            )
        if self.target_extension != ".go":
            raise ValueError(
                f"target_extension must be strictly '.go', got {self.target_extension!r}"
            )
        if self.reference_corpus_hash != FROZEN_REFERENCE_CORPUS_HASH:
            raise ValueError(
                f"reference_corpus_hash must be strictly {FROZEN_REFERENCE_CORPUS_HASH!r}, "
                f"got {self.reference_corpus_hash!r}"
            )

        # Derive experiment_profile_hash deterministically from profile inputs.
        # Callers cannot supply it, and it does not include itself.
        payload = {
            "baseline_id": self.baseline_id,
            "experiment_id": self.experiment_id,
            "reference_corpus_hash": self.reference_corpus_hash,
            "target_extension": self.target_extension,
            "target_repository": self.target_repository,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
        object.__setattr__(self, "experiment_profile_hash", digest)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "baseline_id": self.baseline_id,
            "target_repository": self.target_repository,
            "target_extension": self.target_extension,
            "reference_corpus_hash": self.reference_corpus_hash,
            "experiment_profile_hash": self.experiment_profile_hash,
        }


# ── Discovery Adapter for Go Source Files ──────────────────────────────────────


def discover_go_sources(
    checkout: RepositoryCheckout | Path | str,
    *,
    max_file_size_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES,
) -> DiscoveryResult:
    """Independently enumerate only .go files in a repository checkout.

    Preserves the exact frozen discovery safety semantics:
    - Deterministic os.walk traversal (dirs and files sorted lexicographically)
    - followlinks=False (symlinks and directory junctions skipped with diagnostics)
    - Exclude .git directory unconditionally
    - Normalized POSIX relative paths
    - Strict UTF-8 decoding (no silent replacement)
    - Default 2 MiB maximum file size limit
    - SHA-256 over original bytes ('sha256:<hex>')
    - Adapts files into DiscoveredSourceDocument using source_type='documentation'
      for compatibility with the frozen DTO, with metadata marking evidence_kind='source_code'.
    - Deterministic ordering of documents and diagnostics.

    Args:
        checkout: RepositoryCheckout from materialize_repository, or Path to checkout root.
        max_file_size_bytes: Maximum allowed file size in bytes before skipping.

    Returns:
        DiscoveryResult containing sorted documents and diagnostics.

    Raises:
        ValueError: If checkout directory does not exist or is not a directory.
    """
    if isinstance(checkout, RepositoryCheckout):
        checkout_root = checkout.checkout_path
    else:
        checkout_root = Path(checkout)

    if not checkout_root.is_dir():
        raise ValueError(f"Checkout path does not exist or is not a directory: {checkout_root}")

    documents: list[DiscoveredSourceDocument] = []
    diagnostics: list[SourceDiscoveryDiagnostic] = []

    for root, dirs, files in os.walk(checkout_root, followlinks=False):
        # Deterministic traversal order
        dirs.sort()
        files.sort()

        # Prune .git directory unconditionally
        if ".git" in dirs:
            dirs.remove(".git")

        # Detect and prune symlinked / junction directories
        symlink_dirs: list[str] = []
        for d in dirs:
            dir_path = Path(root) / d
            if dir_path.is_symlink() or (hasattr(dir_path, "is_junction") and dir_path.is_junction()):
                symlink_dirs.append(d)
                rel_dir = dir_path.relative_to(checkout_root).as_posix()
                diagnostics.append(
                    SourceDiscoveryDiagnostic(
                        path=rel_dir,
                        kind="symlink_skipped",
                        message=f"Symbolic link directory '{rel_dir}' was not followed",
                    )
                )

        for d in symlink_dirs:
            dirs.remove(d)

        # Process .go files
        for f in files:
            if f == ".git":
                continue

            file_path = Path(root) / f
            rel_path = file_path.relative_to(checkout_root).as_posix()

            # Skip symlinks and junctions
            if file_path.is_symlink() or (hasattr(file_path, "is_junction") and file_path.is_junction()):
                diagnostics.append(
                    SourceDiscoveryDiagnostic(
                        path=rel_path,
                        kind="symlink_skipped",
                        message=f"Symbolic link file '{rel_path}' was not followed",
                    )
                )
                continue

            # Strict single-extension filter: .go only
            ext = file_path.suffix.lower()
            if ext != ".go":
                continue

            # Read raw bytes
            try:
                raw_bytes = file_path.read_bytes()
            except (OSError, PermissionError) as exc:
                diagnostics.append(
                    SourceDiscoveryDiagnostic(
                        path=rel_path,
                        kind="unreadable_file",
                        message=f"Could not read file: {exc}",
                    )
                )
                continue

            # Check size limit
            if len(raw_bytes) > max_file_size_bytes:
                diagnostics.append(
                    SourceDiscoveryDiagnostic(
                        path=rel_path,
                        kind="file_oversized",
                        message=(
                            f"File size ({len(raw_bytes)} bytes) exceeds maximum "
                            f"allowed size ({max_file_size_bytes} bytes)"
                        ),
                    )
                )
                continue

            # Attempt strict UTF-8 decoding
            try:
                content = raw_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                diagnostics.append(
                    SourceDiscoveryDiagnostic(
                        path=rel_path,
                        kind="undecodable_encoding",
                        message=f"File could not be decoded as UTF-8: {exc}",
                    )
                )
                continue

            # Compute stable content hash
            content_hash = f"sha256:{hashlib.sha256(raw_bytes).hexdigest().lower()}"

            # Deterministic metadata marking this as source-code evidence
            metadata: dict[str, Any] = {
                "is_mneme_adr": False,
                "byte_length": len(raw_bytes),
                "extension": ".go",
                "evidence_kind": "source_code",
                "language": "go",
            }

            documents.append(
                DiscoveredSourceDocument(
                    relative_path=rel_path,
                    source_type="documentation",
                    content_hash=content_hash,
                    content=content,
                    metadata=metadata,
                )
            )

    # Deterministic lexicographical sorting
    documents.sort(key=lambda d: d.relative_path)
    diagnostics.sort(key=lambda g: (g.path, g.kind, g.message))

    return DiscoveryResult(
        documents=tuple(documents),
        diagnostics=tuple(diagnostics),
    )


# ── Decoupled Source Coverage Evaluation ───────────────────────────────────────


def calculate_source_coverage(
    references: list[FrozenReferenceDecision],
    discovered_paths: set[str],
) -> dict[str, Any]:
    """Calculate source coverage strictly mirroring existing missed-source semantics.

    A frozen reference is source-covered if at least one of its referenced source
    paths is present in discovered_paths. References where none of their paths
    are in discovered_paths are MISSED_SOURCE.

    Args:
        references: List of FrozenReferenceDecision ground-truth instances.
        discovered_paths: Set of repository-relative POSIX paths discovered.

    Returns:
        Dictionary detailing covered reference IDs, missed reference IDs, and coverage rate.
    """
    covered_ids: list[str] = []
    missed_ids: list[str] = []

    for r in references:
        r_files = [f.strip() for f in r.source_file.split(",") if f.strip()]
        if any(f in discovered_paths for f in r_files):
            covered_ids.append(r.reference_decision_id)
        else:
            missed_ids.append(r.reference_decision_id)

    covered_ids.sort()
    missed_ids.sort()

    total = len(references)
    coverage_rate = len(covered_ids) / total if total > 0 else 0.0

    return {
        "total_references": total,
        "source_covered_count": len(covered_ids),
        "source_coverage_rate": coverage_rate,
        "source_covered_reference_ids": covered_ids,
        "missed_source_count": len(missed_ids),
        "missed_source_reference_ids": missed_ids,
    }


# ── Experiment Execution & Result Model ────────────────────────────────────────


@dataclass(frozen=True)
class SourceCoverageExperimentResult:
    """Immutable result of a T1 source coverage experiment."""

    profile: SourceCoverageExperimentProfile
    archlint_stage_a: StageADiscoveryResult
    archlint_source_coverage: dict[str, Any]
    go_documents_count: int
    go_candidates_count: int
    aggregate_metrics: dict[str, Any]
    output_dir: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.to_dict(),
            "archlint_stage_a": self.archlint_stage_a.to_dict(),
            "archlint_source_coverage": self.archlint_source_coverage,
            "go_documents_count": self.go_documents_count,
            "go_candidates_count": self.go_candidates_count,
            "aggregate_metrics": self.aggregate_metrics,
            "output_dir": str(self.output_dir),
        }


def _verify_and_prepare_output_dir(output_dir: str | Path) -> Path:
    """Enforce output directory rules:

    - path absent -> create it
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


def execute_source_coverage_experiment(
    *,
    experiment_profile: SourceCoverageExperimentProfile | None = None,
    reference_corpus_dir: str | Path,
    output_dir: str | Path,
    clone_source: str | Path | None = None,
    workspace_dir: str | Path | None = None,
) -> SourceCoverageExperimentResult:
    """Execute the T1 Stage A source-coverage experiment against pinned Archlint.

    Workflow:
    1. Validates and prepares output_dir according to non-empty overwrite rules.
    2. Materializes pinned Archlint checkout using materialize_repository at pinned SHA.
    3. Executes frozen discover_sources() for Markdown/RST documents.
    4. Executes discover_go_sources() for .go documents.
    5. Combines both document streams deterministically.
    6. Runs unchanged HeuristicExtractor over all discovered documents.
    7. Evaluates Stage A matches using evaluate_discovery_matches().
    8. Calculates Source Coverage decoupled from Stage A interval matches.
    9. Derives aggregate metrics across the benchmark combining B0 other repos with T1 Archlint.
    10. Emits deterministic artifacts: t1_summary.json and candidate_matches.jsonl.
    11. Terminates strictly after Stage A without model calls or canonical state mutations.

    Args:
        experiment_profile: Optional profile (defaults to standard T1 profile).
        reference_corpus_dir: Directory containing frozen reference decisions.
        output_dir: Explicit output directory for experiment evidence artifacts.
        clone_source: Optional clone source for isolated/offline testing.
        workspace_dir: Optional caller-controlled materialization workspace.

    Returns:
        SourceCoverageExperimentResult containing all actual execution outcomes.
    """
    if experiment_profile is None:
        experiment_profile = SourceCoverageExperimentProfile()

    out_path = _verify_and_prepare_output_dir(output_dir)

    # 1. Enforce frozen reference corpus content hash
    computed_ref_hash = compute_reference_corpus_content_hash(reference_corpus_dir)
    if (
        computed_ref_hash != experiment_profile.reference_corpus_hash
        or computed_ref_hash != FROZEN_REFERENCE_CORPUS_HASH
    ):
        raise ValueError(
            f"Reference corpus hash mismatch: computed {computed_ref_hash!r}, "
            f"expected {experiment_profile.reference_corpus_hash!r} "
            f"(frozen: {FROZEN_REFERENCE_CORPUS_HASH!r})"
        )

    # 2. Load frozen Archlint references
    references = load_reference_corpus(reference_corpus_dir, repo_id=experiment_profile.target_repository)
    if len(references) != 20:
        raise ValueError(
            f"Expected exactly 20 reference decisions for '{experiment_profile.target_repository}', "
            f"got {len(references)}"
        )

    # 3. Materialize repository at pinned SHA
    repo_config = RepositoryConfig(
        id=experiment_profile.target_repository,
        github=PINNED_ARCHLINT_GITHUB,
        commit_sha=PINNED_ARCHLINT_SHA,
        primary_test="decision_to_enforceable_rule",
        validation_status="reviewed",
    )

    with materialize_repository(
        repo_config,
        workspace_dir=workspace_dir,
        clone_source=clone_source,
    ) as checkout:
        if checkout.resolved_commit_sha.lower() != PINNED_ARCHLINT_SHA.lower():
            raise ValueError(
                f"Resolved SHA {checkout.resolved_commit_sha} does not match pinned {PINNED_ARCHLINT_SHA}"
            )

        # 3. Discover documentation using frozen discovery
        doc_discovery = discover_sources(checkout)

        # 4. Discover Go sources using T1 adapter
        go_discovery = discover_go_sources(checkout)

        # 5. Combine document streams deterministically
        combined_documents: list[DiscoveredSourceDocument] = sorted(
            list(doc_discovery.documents) + list(go_discovery.documents),
            key=lambda d: d.relative_path,
        )
        discovered_paths = {d.relative_path for d in combined_documents}

        # 6. Extract candidates using unchanged HeuristicExtractor
        extractor = HeuristicExtractor()
        all_raw_cands: list[ExtractedCandidate] = []
        go_paths = {d.relative_path for d in go_discovery.documents}

        for d in combined_documents:
            all_raw_cands.extend(extractor.extract(d, checkout.resolved_commit_sha))

        # Deduplicate candidates by candidate_id
        seen_cand: set[str] = set()
        unique_cands: list[ExtractedCandidate] = []
        for c in all_raw_cands:
            if c.candidate_id not in seen_cand:
                seen_cand.add(c.candidate_id)
                unique_cands.append(c)

    go_candidates_count = sum(1 for c in unique_cands if c.source_path in go_paths)

    # 7. Evaluate Stage A interval matches
    archlint_stage_a = evaluate_discovery_matches(
        candidates=unique_cands,
        discovered_paths=discovered_paths,
        references=references,
        repo_id=repo_config.id,
        discovered_documents_count=len(combined_documents),
    )

    # 8. Calculate decoupled Source Coverage
    source_coverage = calculate_source_coverage(references, discovered_paths)

    # Compute extraction misses: references that are source-covered but unmatched by extractor
    extraction_miss_ids = sorted(
        [r_id for r_id in source_coverage["source_covered_reference_ids"] if r_id in archlint_stage_a.unmatched_reference_ids]
    )

    # 9. Derive aggregate benchmark metrics combining frozen B0 other-repos + T1 Archlint
    total_candidates = B0_OTHER_REPOS_CANDIDATES + archlint_stage_a.extracted_candidates_count
    total_matched_candidates = B0_OTHER_REPOS_MATCHED_CANDIDATES + archlint_stage_a.matched_candidate_count
    total_references = B0_OTHER_REPOS_TOTAL_REFERENCES + archlint_stage_a.reference_decisions_count  # 100
    total_matched_references = B0_OTHER_REPOS_MATCHED_REFERENCES + archlint_stage_a.matched_reference_count
    total_source_covered_refs = B0_OTHER_REPOS_SOURCE_COVERED_REFERENCES + source_coverage["source_covered_count"]

    agg_recall = total_matched_references / total_references if total_references > 0 else 0.0
    agg_precision = total_matched_candidates / total_candidates if total_candidates > 0 else 0.0
    agg_f1 = (
        2 * agg_precision * agg_recall / (agg_precision + agg_recall)
        if (agg_precision + agg_recall) > 0
        else 0.0
    )
    agg_source_coverage_rate = total_source_covered_refs / total_references if total_references > 0 else 0.0

    overall_o1_score = (agg_f1 + B0_STAGE_B_SEMANTIC_SCORE + B0_STAGE_C_APPLICABILITY_SCORE) / 3.0

    aggregate_metrics = {
        "total_references": total_references,
        "source_covered_references": total_source_covered_refs,
        "source_coverage_rate": agg_source_coverage_rate,
        "total_candidates": total_candidates,
        "matched_candidates": total_matched_candidates,
        "matched_references": total_matched_references,
        "unmatched_references": total_references - total_matched_references,
        "stage_a_recall": agg_recall,
        "discovery_precision": agg_precision,
        "stage_a_micro_f1": agg_f1,
        "b0_stage_b_semantic_score": B0_STAGE_B_SEMANTIC_SCORE,
        "b0_stage_c_applicability_score": B0_STAGE_C_APPLICABILITY_SCORE,
        "t1_overall_o1_score": overall_o1_score,
    }

    # 10. Emit deterministic artifacts
    summary_data = {
        "experiment_id": experiment_profile.experiment_id,
        "profile": experiment_profile.to_dict(),
        "pinned_repository_sha": PINNED_ARCHLINT_SHA,
        "archlint": {
            "total_documents": len(combined_documents),
            "doc_documents_count": len(doc_discovery.documents),
            "go_documents_count": len(go_discovery.documents),
            "total_extracted_candidates": archlint_stage_a.extracted_candidates_count,
            "go_extracted_candidates": go_candidates_count,
            "matched_candidates": archlint_stage_a.matched_candidate_count,
            "reference_decisions_count": archlint_stage_a.reference_decisions_count,
            "source_covered_count": source_coverage["source_covered_count"],
            "source_coverage_rate": source_coverage["source_coverage_rate"],
            "missed_source_reference_ids": source_coverage["missed_source_reference_ids"],
            "stage_a_matched_references": archlint_stage_a.matched_reference_count,
            "stage_a_recall": archlint_stage_a.recall,
            "stage_a_precision": archlint_stage_a.precision,
            "stage_a_f1": archlint_stage_a.f1,
            "unmatched_reference_ids": archlint_stage_a.unmatched_reference_ids,
            "extraction_miss_reference_ids": extraction_miss_ids,
        },
        "aggregate": aggregate_metrics,
    }

    (out_path / "t1_summary.json").write_text(
        json.dumps(summary_data, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    # Emit candidate_matches.jsonl
    cand_to_ref = archlint_stage_a.cand_to_ref_matches
    cand_lines: list[str] = []
    for c in unique_cands:
        matched_refs = sorted(cand_to_ref.get(c.candidate_id, []))
        rec = {
            "candidate_id": c.candidate_id,
            "source_path": c.source_path,
            "source_location": c.location_string,
            "start_line": c.source_location.start_line,
            "end_line": c.source_location.end_line,
            "evidence_kind": "source_code" if c.source_path in go_paths else "documentation",
            "raw_statement": c.raw_statement,
            "matched": len(matched_refs) > 0,
            "matched_reference_ids": matched_refs,
        }
        cand_lines.append(json.dumps(rec, sort_keys=True))

    (out_path / "candidate_matches.jsonl").write_text(
        "\n".join(cand_lines) + "\n",
        encoding="utf-8",
    )

    return SourceCoverageExperimentResult(
        profile=experiment_profile,
        archlint_stage_a=archlint_stage_a,
        archlint_source_coverage=source_coverage,
        go_documents_count=len(go_discovery.documents),
        go_candidates_count=go_candidates_count,
        aggregate_metrics=aggregate_metrics,
        output_dir=out_path,
    )


__all__ = [
    "PINNED_ARCHLINT_REPO_ID",
    "PINNED_ARCHLINT_GITHUB",
    "PINNED_ARCHLINT_SHA",
    "FROZEN_BASELINE_ID",
    "FROZEN_REFERENCE_CORPUS_HASH",
    "SourceCoverageExperimentProfile",
    "SourceCoverageExperimentResult",
    "discover_go_sources",
    "calculate_source_coverage",
    "execute_source_coverage_experiment",
]
