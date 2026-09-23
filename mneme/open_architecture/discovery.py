"""
mneme.open_architecture.discovery — Deterministic repository source discovery.

Enumerates and preserves repository documentation that may contain architectural
evidence for the O1A Open Architecture benchmark.

Critical Architecture Rules:
- Broad discovery: ADRs, architecture docs, READMEs, design docs, contributor docs.
- Untrusted repository contents: read files only, never execute, never import Python
  from checkout, never follow symlinks.
- Do NOT use resolve_precedence as a discovery filter: active, proposed, superseded,
  deprecated, and historical decisions must all be preserved.
- Do NOT assume external repositories follow Mneme's ADR convention: non-Mneme ADRs
  must remain available as research evidence, with parsing outcome recorded separately.
- No classification: do not produce DecisionCandidate or infer authority/scope/domain.
- No canonical authority writes: do not write to MemoryStore, DecisionProposal,
  or DecisionIndex.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mneme.adr_compiler import (
    _check_date,
    _check_enums,
    _check_id_format,
    _check_required_fields,
    _check_scope,
)
from mneme.adr_parser import _build_adr, _split_frontmatter
from mneme.adr_schema import ADR, ADRParseError, ADRValidationError
from mneme.open_architecture.execution import RepositoryCheckout

DOCUMENTATION_EXTENSIONS: frozenset[str] = frozenset({".md", ".mdx", ".rst"})
DEFAULT_MAX_DOCUMENT_BYTES: int = 2 * 1024 * 1024  # 2 MiB


# ── Data Models ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DiscoveredSourceDocument:
    """A discovered source document within a repository checkout.

    Attributes:
        relative_path: Repository-relative POSIX path (forward slashes, no leading slash).
        source_type: Coarse source category ('adr' or 'documentation').
        content_hash: SHA-256 hex digest of the original file bytes ('sha256:<hex>').
        content: Decoded UTF-8 text content.
        metadata: Deterministic structural metadata (e.g. ADR frontmatter fields, byte length).
    """

    relative_path: str
    source_type: str
    content_hash: str
    content: str
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.relative_path or "\\" in self.relative_path or self.relative_path.startswith("/"):
            raise ValueError(
                f"relative_path must be a normalized non-empty POSIX relative path, got {self.relative_path!r}"
            )
        if self.source_type not in ("adr", "documentation"):
            raise ValueError(f"source_type must be 'adr' or 'documentation', got {self.source_type!r}")
        if not re.match(r"^sha256:[0-9a-f]{64}$", self.content_hash):
            raise ValueError(f"content_hash must be 'sha256:<64 hex>', got {self.content_hash!r}")


@dataclass(frozen=True)
class SourceDiscoveryDiagnostic:
    """A diagnostic recorded during source discovery for skipped or unusual files.

    Attributes:
        path: Repository-relative POSIX path associated with the diagnostic.
        kind: Diagnostic classification ('symlink_skipped', 'file_oversized',
              'undecodable_encoding', 'adr_parse_failure', 'unreadable_file').
        message: Human-readable explanation of why the file was skipped or flagged.
    """

    path: str
    kind: str
    message: str

    def __post_init__(self) -> None:
        if not self.path or "\\" in self.path or self.path.startswith("/"):
            raise ValueError(
                f"path must be a normalized non-empty POSIX relative path, got {self.path!r}"
            )


@dataclass(frozen=True)
class DiscoveryResult:
    """Immutable result of source discovery.

    Documents and diagnostics are ordered deterministically:
    - documents: sorted lexicographically by relative_path.
    - diagnostics: sorted lexicographically by (path, kind, message).
    """

    documents: tuple[DiscoveredSourceDocument, ...]
    diagnostics: tuple[SourceDiscoveryDiagnostic, ...]


# ── Internal Discovery Helpers ─────────────────────────────────────────────────


def _is_adr_candidate(rel_path: str, filename: str) -> bool:
    """Check whether a file's name or path suggests it is an architectural decision record."""
    lowered_name = filename.lower()
    lowered_path = rel_path.lower()

    # Matches files named ADR-*, adr-*, adr_*, or numeric prefixes like 0001-*
    if re.match(r"^adr[-_0-9]", lowered_name):
        return True

    # In an ADR/decisions directory and not an index, readme, or template file
    in_adr_dir = bool(re.search(r"(?:^|/)(?:adr|adrs|decisions|architecture-decisions)/", lowered_path))
    if in_adr_dir and not re.match(r"^(?:readme|index|template|draft|notes)\b", lowered_name):
        return True

    return False


def _validate_single_adr(adr: ADR) -> list[str]:
    """Validate per-record ADR schema rules without requiring cross-record references."""
    errors: list[str] = []
    errors.extend(_check_required_fields(adr))
    errors.extend(_check_enums(adr))
    errors.extend(_check_id_format(adr))
    errors.extend(_check_date(adr))
    errors.extend(_check_scope(adr))
    return errors


def _analyze_adr_structure(
    content: str,
    file_path: Path,
    rel_path: str,
    raw_bytes_len: int,
) -> tuple[str, dict[str, Any], SourceDiscoveryDiagnostic | None]:
    """Attempt structured Mneme ADR parsing on candidate content.

    Returns:
        (source_type, metadata_dict, optional_diagnostic)
    """
    is_candidate = _is_adr_candidate(rel_path, file_path.name)
    has_frontmatter = content.startswith("---")

    metadata: dict[str, Any] = {
        "is_mneme_adr": False,
        "byte_length": raw_bytes_len,
        "extension": file_path.suffix.lower(),
    }

    if not is_candidate and not has_frontmatter:
        return "documentation", metadata, None

    # Attempt frontmatter parsing
    try:
        meta_dict, body = _split_frontmatter(content, file_path)
        adr = _build_adr(meta_dict, body, file_path)
        validation_errors = _validate_single_adr(adr)
        if validation_errors:
            raise ADRValidationError(validation_errors)

        # Valid Mneme ADR
        metadata["is_mneme_adr"] = True
        metadata["adr_id"] = adr.id
        metadata["adr_title"] = adr.title
        metadata["adr_status"] = adr.status
        metadata["adr_priority"] = adr.priority
        metadata["adr_date"] = adr.date
        metadata["adr_scope"] = adr.scope
        metadata["supersedes"] = list(adr.supersedes)
        return "adr", metadata, None

    except (ADRParseError, ADRValidationError) as exc:
        if is_candidate:
            metadata["is_mneme_adr"] = False
            metadata["adr_parse_error"] = str(exc)
            diagnostic = SourceDiscoveryDiagnostic(
                path=rel_path,
                kind="adr_parse_failure",
                message=f"Structured ADR parsing failed: {exc}",
            )
            return "adr", metadata, diagnostic
        # Non-candidate with frontmatter that is not an ADR (e.g. general doc with frontmatter)
        metadata["is_mneme_adr"] = False
        return "documentation", metadata, None


# ── Public Discovery API ───────────────────────────────────────────────────────


def discover_sources(
    checkout: RepositoryCheckout | Path | str,
    *,
    max_file_size_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES,
) -> DiscoveryResult:
    """Deterministically discover and preserve repository documentation.

    Scans the repository working tree for documentation files (.md, .mdx, .rst)
    excluding .git/ and symlinks. Extracts raw bytes, content SHA-256, and UTF-8
    text. Identifies ADRs and retains structured metadata when Mneme ADR conventions
    match, while retaining non-conforming or generic documentation without alteration.

    Args:
        checkout: RepositoryCheckout from materialize_repository, or Path to checkout root.
        max_file_size_bytes: Maximum allowed file size in bytes before skipping (default 2 MiB).

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

        # Detect and prune symlinked/junction directories
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

        # Process candidate files
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

            # Check supported documentation extensions
            ext = file_path.suffix.lower()
            if ext not in DOCUMENTATION_EXTENSIONS:
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

            # Attempt strict UTF-8 decoding (no silent replacement)
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

            # Analyze ADR structure
            source_type, metadata, diag = _analyze_adr_structure(
                content=content,
                file_path=file_path,
                rel_path=rel_path,
                raw_bytes_len=len(raw_bytes),
            )
            if diag is not None:
                diagnostics.append(diag)

            documents.append(
                DiscoveredSourceDocument(
                    relative_path=rel_path,
                    source_type=source_type,
                    content_hash=content_hash,
                    content=content,
                    metadata=metadata,
                )
            )

    # Sort results lexicographically for deterministic output
    documents.sort(key=lambda d: d.relative_path)
    diagnostics.sort(key=lambda g: (g.path, g.kind, g.message))

    return DiscoveryResult(
        documents=tuple(documents),
        diagnostics=tuple(diagnostics),
    )


__all__ = [
    "DOCUMENTATION_EXTENSIONS",
    "DEFAULT_MAX_DOCUMENT_BYTES",
    "DiscoveredSourceDocument",
    "SourceDiscoveryDiagnostic",
    "DiscoveryResult",
    "discover_sources",
]
