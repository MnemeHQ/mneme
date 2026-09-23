"""
mneme.open_architecture.candidates — Candidate evidence extraction and deterministic identity.

Provides the research-only candidate evidence model and extraction interface.
Does not perform semantic classification or write canonical Mneme state.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from mneme.open_architecture.discovery import DiscoveredSourceDocument


# ── Line Span Model ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, order=True)
class LineSpan:
    """Explicit 1-based inclusive line range within a source document.

    Attributes:
        start_line: First line of the evidence span (>= 1).
        end_line: Last line of the evidence span (>= start_line).
    """

    start_line: int
    end_line: int

    def __post_init__(self) -> None:
        if self.start_line < 1:
            raise ValueError(f"start_line must be >= 1, got {self.start_line}")
        if self.end_line < self.start_line:
            raise ValueError(
                f"end_line ({self.end_line}) must be >= start_line ({self.start_line})"
            )

    def contains(self, other: LineSpan) -> bool:
        """True if this span fully contains the other."""
        return self.start_line <= other.start_line and self.end_line >= other.end_line

    def overlaps(self, other: LineSpan) -> bool:
        """True if this span overlaps with the other."""
        return not (self.end_line < other.start_line or other.end_line < self.start_line)

    def to_string(self) -> str:
        """Human-readable representation: 'L42-L48'."""
        if self.start_line == self.end_line:
            return f"L{self.start_line}"
        return f"L{self.start_line}-L{self.end_line}"

    @classmethod
    def from_string(cls, s: str) -> LineSpan:
        """Parse 'L42-L48', 'L42-48', or 'L42' format."""
        s = s.strip().upper()
        if not s.startswith("L"):
            raise ValueError(f"LineSpan string must start with 'L', got {s!r}")
        if "-" in s:
            start_str, end_str = s[1:].split("-", 1)
            if end_str.startswith("L"):
                end_str = end_str[1:]
            return cls(int(start_str), int(end_str))
        return cls(int(s[1:]), int(s[1:]))

    def line_count(self) -> int:
        """Number of lines in the span."""
        return self.end_line - self.start_line + 1


# ── Candidate Evidence Model ────────────────────────────────────────────────────


@dataclass(frozen=True)
class ExtractedCandidate:
    """Research candidate evidence span identified from a source document.

    This is NOT a DecisionCandidate (the fully interpreted O1A schema).
    This is NOT canonical authority.
    It is raw evidence that a decision may exist at a specific location.

    Attributes:
        candidate_id: Deterministic SHA-256 derived from source evidence fields.
        repository_identifier: GitHub owner/repo (e.g. 'mbeacom/adrkit').
        repository_commit_sha: 40-character hex SHA of the pinned commit.
        source_path: Repository-relative POSIX path to source document.
        source_content_hash: 'sha256:<hex>' of the source document's raw bytes.
        source_location: Line span within the source document (e.g. 'L42-L48').
        raw_statement: Exact text extracted from the source lines.
        discovery_confidence: Heuristic confidence in extraction [0.0, 1.0].
        discovery_metadata: Deterministic metadata about the extraction process.
    """

    candidate_id: str
    repository_identifier: str
    repository_commit_sha: str
    source_path: str
    source_content_hash: str
    source_location: LineSpan
    raw_statement: str
    discovery_confidence: float
    discovery_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validate candidate_id format
        if not re.match(r"^cand-[0-9a-f]{32}$", self.candidate_id):
            raise ValueError(
                f"candidate_id must match 'cand-<32 hex>', got {self.candidate_id!r}"
            )

        # Validate SHA format
        if not re.match(r"^[0-9a-f]{40}$", self.repository_commit_sha):
            raise ValueError(
                f"repository_commit_sha must be 40-char hex, got {self.repository_commit_sha!r}"
            )

        # Validate source_content_hash
        if not re.match(r"^sha256:[0-9a-f]{64}$", self.source_content_hash):
            raise ValueError(
                f"source_content_hash must be 'sha256:<64 hex>', got {self.source_content_hash!r}"
            )

        # Validate path format
        if "\\" in self.source_path or self.source_path.startswith("/"):
            raise ValueError(
                f"source_path must be normalized POSIX relative, got {self.source_path!r}"
            )

        # Validate confidence bounds
        if not (0.0 <= self.discovery_confidence <= 1.0):
            raise ValueError(
                f"discovery_confidence must be in [0.0, 1.0], got {self.discovery_confidence}"
            )

    @property
    def location_string(self) -> str:
        """Human-readable location string."""
        return self.source_location.to_string()

    def to_identity_dict(self) -> dict[str, Any]:
        """Canonical identity fields for deterministic candidate_id generation."""
        return {
            "repository_identifier": self.repository_identifier,
            "repository_commit_sha": self.repository_commit_sha,
            "source_path": self.source_path,
            "source_content_hash": self.source_content_hash,
            "source_location": self.location_string,
            "raw_statement": self.raw_statement,
        }

    @classmethod
    def generate_candidate_id(cls, identity: dict[str, Any]) -> str:
        """Generate deterministic candidate_id from identity fields."""
        canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
        return f"cand-{digest}"

    def extract_source_lines(self, document: DiscoveredSourceDocument) -> str:
        """Verify and extract raw_statement from the source document content."""
        lines = document.content.splitlines()
        start = self.source_location.start_line - 1  # Convert to 0-index
        end = self.source_location.end_line
        if start < 0 or end > len(lines):
            raise ValueError(
                f"LineSpan {self.location_string} out of bounds for document "
                f"{document.relative_path} (has {len(lines)} lines)"
            )
        return "\n".join(lines[start:end])

    @classmethod
    def from_source_document(
        cls,
        doc: DiscoveredSourceDocument,
        repo_commit_sha: str,
        line_span: LineSpan,
        discovery_confidence: float = 0.8,
        metadata: dict[str, Any] | None = None,
    ) -> ExtractedCandidate:
        """Create an ExtractedCandidate from a DiscoveredSourceDocument and line span."""
        # Verify the line span is within the document
        lines = doc.content.splitlines()
        if line_span.start_line < 1 or line_span.end_line > len(lines):
            raise ValueError(
                f"LineSpan {line_span.to_string()} out of bounds for "
                f"{doc.relative_path} ({len(lines)} lines)"
            )

        raw_statement = "\n".join(lines[line_span.start_line - 1 : line_span.end_line])
        if not raw_statement.strip():
            raise ValueError("Extracted statement is empty or whitespace-only")

        identity = {
            "repository_identifier": doc.metadata.get("repository_identifier", "unknown"),
            "repository_commit_sha": repo_commit_sha.lower(),
            "source_path": doc.relative_path,
            "source_content_hash": doc.content_hash,
            "source_location": line_span.to_string(),
            "raw_statement": raw_statement,
        }
        candidate_id = cls.generate_candidate_id(identity)

        return cls(
            candidate_id=candidate_id,
            repository_identifier=identity["repository_identifier"],
            repository_commit_sha=identity["repository_commit_sha"],
            source_path=identity["source_path"],
            source_content_hash=identity["source_content_hash"],
            source_location=line_span,
            raw_statement=raw_statement,
            discovery_confidence=discovery_confidence,
            discovery_metadata=metadata or {},
        )


# ── Candidate Extractor Protocol ──────────────────────────────────────────────


class CandidateExtractor(Protocol):
    """Protocol for candidate evidence extraction strategies.

    O1A must support multiple extraction approaches (deterministic,
    model-assisted, hybrid, human-supplied) for comparison.
    """

    @property
    def extractor_id(self) -> str:
        """Stable extractor identifier (e.g., 'heuristic')."""
        ...

    @property
    def extractor_version(self) -> str:
        """Semantic version of this extractor implementation (e.g., '0.1')."""
        ...

    def extract(
        self,
        document: DiscoveredSourceDocument,
        repo_commit_sha: str,
    ) -> list[ExtractedCandidate]:
        """Extract candidate evidence spans from a discovered document.

        Args:
            document: A DiscoveredSourceDocument from discover_sources().
            repo_commit_sha: The pinned repository commit SHA.

        Returns:
            List of ExtractedCandidate instances (may be empty).
        """
        ...


# ── Deterministic Heuristic Extractor (Reference Implementation) ──────────────


class HeuristicExtractor:
    """Reference deterministic extractor using simple heuristics.

    Splits documents into candidate spans based on heading boundaries and
    decision-indicative keywords. Not a semantic classifier.
    """

    # Keywords that suggest a decision statement
    DECISION_KEYWORDS = frozenset({
        "decide", "decision", "decided", "adopt", "adopted",
        "standardize", "standardised", "standard", "mandate", "mandated",
        "require", "required", "prohibit", "prohibited", "forbid", "forbidden",
        "must", "shall", "should not", "never", "always",
        "use", "using", "prefer", "preferred", "avoid",
    })

    def __init__(
        self,
        *,
        min_lines: int = 2,
        max_lines: int = 50,
        confidence: float = 0.5,
        extractor_id: str = "heuristic",
        extractor_version: str = "0.1",
    ) -> None:
        self.min_lines = min_lines
        self.max_lines = max_lines
        self.confidence = confidence
        self._extractor_id = extractor_id
        self._extractor_version = extractor_version

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

        # Find heading-like lines and potential decision boundaries
        heading_indices = self._find_headings(lines)
        spans = self._build_spans(lines, heading_indices)

        for span in spans:
            if span.line_count() < self.min_lines:
                continue
            if span.line_count() > self.max_lines:
                # Split large spans
                for sub_span in self._split_span(span):
                    if sub_span.line_count() >= self.min_lines:
                        self._try_add_candidate(candidates, document, repo_commit_sha, sub_span)
            else:
                self._try_add_candidate(candidates, document, repo_commit_sha, span)

        return candidates

    def _find_headings(self, lines: list[str]) -> list[int]:
        """Find 0-indexed line numbers of markdown headings."""
        heading_pattern = re.compile(r"^\s*#{1,6}\s+")
        return [i for i, line in enumerate(lines) if heading_pattern.match(line)]

    def _build_spans(self, lines: list[str], headings: list[int]) -> list[LineSpan]:
        """Build candidate spans between headings."""
        spans: list[LineSpan] = []
        total_lines = len(lines)

        if not headings:
            # Single span for entire document
            spans.append(LineSpan(1, total_lines))
            return spans

        # Span from start to first heading
        if headings[0] > 0:
            spans.append(LineSpan(1, headings[0]))

        # Spans between headings
        for i in range(len(headings)):
            start = headings[i] + 1
            end = headings[i + 1] if i + 1 < len(headings) else total_lines
            if start <= end:
                spans.append(LineSpan(start, end))

        return spans

    def _split_span(self, span: LineSpan) -> list[LineSpan]:
        """Split a large span into smaller chunks."""
        sub_spans: list[LineSpan] = []
        remaining = span.line_count()
        start = span.start_line
        while remaining > 0:
            chunk_size = min(self.max_lines, remaining)
            sub_spans.append(LineSpan(start, start + chunk_size - 1))
            start += chunk_size
            remaining -= chunk_size
        return sub_spans

    def _try_add_candidate(
        self,
        candidates: list[ExtractedCandidate],
        document: DiscoveredSourceDocument,
        repo_commit_sha: str,
        span: LineSpan,
    ) -> None:
        """Create candidate if span contains decision-indicative content."""
        lines = document.content.splitlines()
        start = span.start_line - 1
        end = span.end_line
        text = "\n".join(lines[start:end]).lower()

        # Check for decision keywords
        if not any(kw in text for kw in self.DECISION_KEYWORDS):
            return

        try:
            candidate = ExtractedCandidate.from_source_document(
                doc=document,
                repo_commit_sha=repo_commit_sha,
                line_span=span,
                discovery_confidence=self.confidence,
                metadata={"extractor": "heuristic", "extractor_version": "0.1"},
            )
            candidates.append(candidate)
        except ValueError:
            # Skip invalid spans (out of bounds, empty, etc.)
            pass


# ── Helper for Normalizing ExtractedCandidates to DecisionCandidate ───────────


def build_decision_candidate(
    extracted: ExtractedCandidate,
    *,
    classification: str,
    decision_domains: tuple[str, ...],
    decision_purposes: tuple[str, ...],
    authority_status: str,
    authority_evidence: str | None = None,
    scopes: tuple = (),
    lifecycle_status: str = "active",
    relationships: tuple = (),
    enforcement_potential: str = "unknown",
    candidate_rule: str | None = None,
    confidence: float | None = None,
    human_validation_status: str = "unreviewed",
    human_corrections: dict[str, Any] | None = None,
) -> "DecisionCandidate":
    """Compose a full DecisionCandidate from validated classifier outputs.

    This is a convenience helper for the later composition step when all
    required dimensions are available. It does NOT perform classification.

    Args:
        extracted: The ExtractedCandidate with source evidence.
        classification: One of VALID_CLASSIFICATIONS.
        decision_domains: Tuple of VALID_DOMAINS.
        decision_purposes: Tuple of VALID_PURPOSES.
        authority_status: One of VALID_AUTHORITIES.
        authority_evidence: Optional evidence for authority claim.
        scopes: Tuple of Scope entries.
        lifecycle_status: One of VALID_LIFECYCLES.
        relationships: Tuple of Relationship entries.
        enforcement_potential: One of VALID_ENFORCEMENT_POTENTIAL.
        candidate_rule: Optional rule string.
        confidence: Optional overall confidence.
        human_validation_status: One of VALID_HUMAN_VALIDATION_STATUSES.
        human_corrections: Optional corrections dict.

    Returns:
        A fully populated DecisionCandidate (validated through schema).
    """
    # Import here to avoid circular dependency
    from mneme.open_architecture.schemas import DecisionCandidate

    return DecisionCandidate(
        candidate_id=extracted.candidate_id,
        repository=extracted.repository_identifier,
        source_file=extracted.source_path,
        source_location=extracted.location_string,
        raw_statement=extracted.raw_statement,
        normalized_decision=extracted.raw_statement,  # Will be refined by classifier
        classification=classification,
        decision_domains=decision_domains,
        decision_purposes=decision_purposes,
        authority_status=authority_status,
        authority_evidence=authority_evidence,
        scopes=scopes,
        lifecycle_status=lifecycle_status,
        relationships=relationships,
        enforcement_potential=enforcement_potential,
        candidate_rule=candidate_rule,
        confidence=confidence,
        human_validation_status=human_validation_status,
        human_corrections=human_corrections,
    )


__all__ = [
    "LineSpan",
    "ExtractedCandidate",
    "CandidateExtractor",
    "HeuristicExtractor",
    "build_decision_candidate",
]
