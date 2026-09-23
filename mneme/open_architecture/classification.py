"""
mneme.open_architecture.classification — Backend-neutral semantic classifier contract.

Defines the classifier protocol, task types, request/result models, and
vocabulary normalization. Does not depend on any specific model provider.

Architecture:
- The O1A benchmark compares classifier backends without changing ontology.
- Real backends (Anthropic, OpenAI, etc.) plug into the SemanticClassifier protocol.
- A StaticClassifier is provided for deterministic testing.
"""

from __future__ import annotations

import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

from mneme.open_architecture.candidates import ExtractedCandidate, LineSpan
from mneme.open_architecture.discovery import DiscoveredSourceDocument
from mneme.open_architecture.schemas import (
    VALID_AUTHORITIES,
    VALID_CLASSIFICATIONS,
    VALID_DOMAINS,
    VALID_ENFORCEMENT_POTENTIAL,
    VALID_LIFECYCLES,
    VALID_PURPOSES,
    VALID_RELATIONSHIP_TYPES,
    VALID_SCOPE_TYPES,
)


# ── Taxonomy Versioning ────────────────────────────────────────────────────────

TAXONOMY_VERSION = "0.1"


# ── Task Types ─────────────────────────────────────────────────────────────────


class ClassifierTaskType(str, Enum):
    """Explicit task types for semantic interpretation.

    The benchmark measures these dimensions separately.
    """

    CANDIDATE_DISCOVERY = "candidate_discovery"
    DECISION_CLASSIFICATION = "decision_classification"
    DOMAINS = "domains"
    PURPOSES = "purposes"
    AUTHORITY = "authority"
    SCOPE = "scope"
    LIFECYCLE = "lifecycle"
    RELATIONSHIPS = "relationships"
    ENFORCEMENT_POTENTIAL = "enforcement_potential"


VALID_TASK_TYPES: frozenset[ClassifierTaskType] = frozenset(ClassifierTaskType)


# ── Classifier Request/Result Models ───────────────────────────────────────────


@dataclass(frozen=True)
class ClassifierTask:
    """Deterministic research input for a single classifier task.

    Contains only source evidence necessary for the task. No canonical
    Decision state is supplied. Taxonomy version is explicit.
    """

    task_type: ClassifierTaskType
    candidate_id: str
    repository_identifier: str
    repository_commit_sha: str
    source_path: str
    source_location: str  # LineSpan string representation (e.g., "L42-L48")
    raw_statement: str
    source_context: str  # Surrounding document context
    taxonomy_version: str = TAXONOMY_VERSION

    def to_json(self) -> str:
        """Deterministic JSON serialization."""
        return json.dumps(
            {
                "task_type": self.task_type.value,
                "candidate_id": self.candidate_id,
                "repository_identifier": self.repository_identifier,
                "repository_commit_sha": self.repository_commit_sha,
                "source_path": self.source_path,
                "source_location": self.source_location,
                "raw_statement": self.raw_statement,
                "source_context": self.source_context,
                "taxonomy_version": self.taxonomy_version,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_extracted_candidate(
        cls,
        extracted: ExtractedCandidate,
        task_type: ClassifierTaskType,
        source_context: str,
    ) -> ClassifierTask:
        """Create a ClassifierTask from an ExtractedCandidate and context."""
        return cls(
            task_type=task_type,
            candidate_id=extracted.candidate_id,
            repository_identifier=extracted.repository_identifier,
            repository_commit_sha=extracted.repository_commit_sha,
            source_path=extracted.source_path,
            source_location=extracted.location_string,
            raw_statement=extracted.raw_statement,
            source_context=source_context,
        )


@dataclass(frozen=True)
class ClassifierResult:
    """Raw classifier execution result preserving provenance and metrics.

    Aligns with the Research Store `classifier_executions` contract.
    Fields may be nullable where not measurable.
    """

    task_type: ClassifierTaskType
    backend_id: str
    classifier_version: str
    model_identifier: str | None
    taxonomy_version: str
    candidate_id: str
    output: dict[str, Any]  # Raw structured output (validated separately)
    confidence: float | None
    latency_ms: float | None
    cost_amount: float | None
    cost_currency: str | None
    escalated: bool = False
    executed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    execution_id: str = field(default_factory=lambda: f"exec-{uuid.uuid4().hex[:32]}")

    def to_json(self) -> str:
        """Deterministic JSON serialization."""
        return json.dumps(
            {
                "task_type": self.task_type.value,
                "backend_id": self.backend_id,
                "classifier_version": self.classifier_version,
                "model_identifier": self.model_identifier,
                "taxonomy_version": self.taxonomy_version,
                "candidate_id": self.candidate_id,
                "output": self.output,
                "confidence": self.confidence,
                "latency_ms": self.latency_ms,
                "cost_amount": self.cost_amount,
                "cost_currency": self.cost_currency,
                "escalated": self.escalated,
                "executed_at": self.executed_at,
                "execution_id": self.execution_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        )


# ── Semantic Classifier Protocol ──────────────────────────────────────────────


class SemanticClassifier(Protocol):
    """Backend-neutral classifier interface for O1A research.

    Real backends (Anthropic, OpenAI, local, etc.) implement this protocol.
    The benchmark orchestrates multiple classifiers against the same tasks.
    """

    @property
    def backend_id(self) -> str:
        """Stable backend identifier (e.g., 'anthropic', 'openai', 'static')."""
        ...

    @property
    def classifier_version(self) -> str:
        """Semantic version of this classifier implementation."""
        ...

    @property
    def model_identifier(self) -> str | None:
        """Model identifier if applicable (e.g., 'claude-sonnet-4-6')."""
        ...

    def execute(self, task: ClassifierTask) -> ClassifierResult:
        """Execute a single classifier task and return the raw result.

        The result's output field contains structured data that must be
        normalized through the vocabulary functions below.
        """
        ...


# ── Vocabulary Normalization (Fail-Closed) ──────────────────────────────────


class NormalizationError(ValueError):
    """Raised when classifier output cannot be normalized to O1A vocabulary."""


def normalize_classification(value: str | list[str]) -> tuple[str, ...]:
    """Normalize classification output to O1A vocabulary.

    Args:
        value: String or list of strings from classifier.

    Returns:
        Tuple of valid classifications (sorted for determinism).

    Raises:
        NormalizationError: If any value is not in VALID_CLASSIFICATIONS.
    """
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = list(value)
    else:
        raise NormalizationError(f"classification must be str or list, got {type(value).__name__}")

    normalized = []
    for v in values:
        if v not in VALID_CLASSIFICATIONS:
            raise NormalizationError(
                f"Invalid classification: {v!r}. Valid: {sorted(VALID_CLASSIFICATIONS)}"
            )
        normalized.append(v)

    return tuple(sorted(set(normalized)))


def normalize_domains(value: str | list[str]) -> tuple[str, ...]:
    """Normalize domains output to O1A vocabulary."""
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = list(value)
    else:
        raise NormalizationError(f"domains must be str or list, got {type(value).__name__}")

    normalized = []
    for v in values:
        if v not in VALID_DOMAINS:
            raise NormalizationError(
                f"Invalid domain: {v!r}. Valid: {sorted(VALID_DOMAINS)}"
            )
        normalized.append(v)

    if not normalized:
        raise NormalizationError("decision_domains must be non-empty")

    return tuple(sorted(set(normalized)))


def normalize_purposes(value: str | list[str]) -> tuple[str, ...]:
    """Normalize purposes output to O1A vocabulary."""
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = list(value)
    else:
        raise NormalizationError(f"purposes must be str or list, got {type(value).__name__}")

    normalized = []
    for v in values:
        if v not in VALID_PURPOSES:
            raise NormalizationError(
                f"Invalid purpose: {v!r}. Valid: {sorted(VALID_PURPOSES)}"
            )
        normalized.append(v)

    if not normalized:
        raise NormalizationError("decision_purposes must be non-empty")

    return tuple(sorted(set(normalized)))


def normalize_authority(value: str) -> str:
    """Normalize authority output to O1A vocabulary.

    Note: All authority states including 'explicitly_accepted', 'superseded',
    and 'rejected' are valid research classifications. They do NOT make the
    candidate canonical authority.
    """
    if value not in VALID_AUTHORITIES:
        raise NormalizationError(
            f"Invalid authority: {value!r}. Valid: {sorted(VALID_AUTHORITIES)}"
        )
    return value


def normalize_scopes(value: list[dict[str, Any]]) -> tuple[Any, ...]:
    """Normalize scopes output to O1A Scope model."""
    from mneme.open_architecture.schemas import Scope

    scopes = []
    for item in value:
        if not isinstance(item, dict):
            raise NormalizationError(f"scope entry must be dict, got {type(item).__name__}")
        scope_type = item.get("scope_type")
        if scope_type not in VALID_SCOPE_TYPES:
            raise NormalizationError(
                f"Invalid scope_type: {scope_type!r}. Valid: {sorted(VALID_SCOPE_TYPES)}"
            )
        scope_expr = item.get("scope_expression")
        scopes.append(Scope(scope_type=scope_type, scope_expression=scope_expr))

    return tuple(scopes)


def normalize_lifecycle(value: str) -> str:
    """Normalize lifecycle output to O1A vocabulary."""
    if value not in VALID_LIFECYCLES:
        raise NormalizationError(
            f"Invalid lifecycle: {value!r}. Valid: {sorted(VALID_LIFECYCLES)}"
        )
    return value


def normalize_relationships(value: list[dict[str, Any]]) -> tuple[Any, ...]:
    """Normalize relationships output to O1A Relationship model."""
    from mneme.open_architecture.schemas import Relationship

    relationships = []
    for item in value:
        if not isinstance(item, dict):
            raise NormalizationError(f"relationship entry must be dict, got {type(item).__name__}")
        rel_type = item.get("relationship_type")
        if rel_type not in VALID_RELATIONSHIP_TYPES:
            raise NormalizationError(
                f"Invalid relationship_type: {rel_type!r}. Valid: {sorted(VALID_RELATIONSHIP_TYPES)}"
            )
        relationships.append(
            Relationship(
                relationship_type=rel_type,
                target_candidate_id=item.get("target_candidate_id"),
                target_reference=item.get("target_reference"),
                confidence=item.get("confidence"),
                evidence_reference=item.get("evidence_reference"),
            )
        )

    return tuple(relationships)


def normalize_enforcement_potential(value: str) -> str:
    """Normalize enforcement potential output to O1A vocabulary."""
    if value not in VALID_ENFORCEMENT_POTENTIAL:
        raise NormalizationError(
            f"Invalid enforcement_potential: {value!r}. Valid: {sorted(VALID_ENFORCEMENT_POTENTIAL)}"
        )
    return value


# ── Static/Fake Classifier for Testing ────────────────────────────────────────


class StaticClassifier:
    """Deterministic in-memory classifier for testing.

    Allows tests to supply predetermined outputs and verify:
    - task construction
    - validation
    - normalization
    - backend identity
    - repeated-run determinism

    Does not pretend to be a real semantic model.
    """

    def __init__(
        self,
        *,
        backend_id: str = "static",
        classifier_version: str = "0.1",
        model_identifier: str | None = "static/test",
        outputs: dict[ClassifierTaskType, dict[str, Any]] | None = None,
        default_confidence: float = 0.9,
        default_latency_ms: float = 1.0,
        default_cost: float | None = None,
        default_currency: str | None = None,
    ) -> None:
        self._backend_id = backend_id
        self._classifier_version = classifier_version
        self._model_identifier = model_identifier
        self._outputs = outputs or {}
        self._default_confidence = default_confidence
        self._default_latency_ms = default_latency_ms
        self._default_cost = default_cost
        self._default_currency = default_currency
        self._execution_count = 0

    @property
    def backend_id(self) -> str:
        return self._backend_id

    @property
    def classifier_version(self) -> str:
        return self._classifier_version

    @property
    def model_identifier(self) -> str | None:
        return self._model_identifier

    def execute(self, task: ClassifierTask) -> ClassifierResult:
        """Execute a task with predetermined output."""
        self._execution_count += 1

        output = self._outputs.get(task.task_type, {"note": "no predetermined output"})
        confidence = self._default_confidence
        latency_ms = self._default_latency_ms
        cost = self._default_cost
        currency = self._default_currency

        result = ClassifierResult(
            task_type=task.task_type,
            backend_id=self._backend_id,
            classifier_version=self._classifier_version,
            model_identifier=self._model_identifier,
            taxonomy_version=task.taxonomy_version,
            candidate_id=task.candidate_id,
            output=output,
            confidence=confidence,
            latency_ms=latency_ms,
            cost_amount=cost,
            cost_currency=currency,
            escalated=False,
        )
        return result


# ── Helper: Build Context for Classifier Task ─────────────────────────────────


def build_source_context(
    doc: DiscoveredSourceDocument,
    span: LineSpan,
    context_lines: int = 10,
) -> str:
    """Build surrounding context for a classifier task.

    Returns the document content with the evidence span marked.
    """
    lines = doc.content.splitlines()
    start = max(0, span.start_line - 1 - context_lines)
    end = min(len(lines), span.end_line + context_lines)

    context_parts = []
    for i in range(start, end):
        line_num = i + 1
        prefix = ">>> " if span.start_line <= line_num <= span.end_line else "    "
        context_parts.append(f"{prefix}{line_num:4d}: {lines[i]}")

    return "\n".join(context_parts)


# ── Batch Execution Helper ────────────────────────────────────────────────────


def execute_classifier_batch(
    classifier: SemanticClassifier,
    tasks: list[ClassifierTask],
) -> list[ClassifierResult]:
    """Execute multiple tasks with the same classifier.

    Preserves input order. Each task is executed independently.
    """
    results: list[ClassifierResult] = []
    for task in tasks:
        start = time.perf_counter()
        try:
            result = classifier.execute(task)
        except Exception as exc:
            # Wrap exception in a failed result
            result = ClassifierResult(
                task_type=task.task_type,
                backend_id=classifier.backend_id,
                classifier_version=classifier.classifier_version,
                model_identifier=classifier.model_identifier,
                taxonomy_version=task.taxonomy_version,
                candidate_id=task.candidate_id,
                output={"error": str(exc)},
                confidence=0.0,
                latency_ms=(time.perf_counter() - start) * 1000,
                cost_amount=None,
                cost_currency=None,
                escalated=True,
            )
        results.append(result)
    return results


__all__ = [
    # Task types
    "ClassifierTaskType",
    "VALID_TASK_TYPES",
    # Models
    "ClassifierTask",
    "ClassifierResult",
    # Protocol
    "SemanticClassifier",
    # Normalization
    "NormalizationError",
    "normalize_classification",
    "normalize_domains",
    "normalize_purposes",
    "normalize_authority",
    "normalize_scopes",
    "normalize_lifecycle",
    "normalize_relationships",
    "normalize_enforcement_potential",
    # Static classifier
    "StaticClassifier",
    # Helpers
    "build_source_context",
    "execute_classifier_batch",
]
