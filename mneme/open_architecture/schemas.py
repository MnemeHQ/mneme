"""
Validation and serialization for O1A Decision Candidate and Applicability Scenario schemas.

Uses the merged JSON Schema draft/2020-12 from PR #389 for validation.
Deterministic JSON-compatible serialization.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema

from mneme.open_architecture.errors import O1AErrorCategory


# ── JSON Schema Loading ────────────────────────────────────────────────────────

_SCHEMA_DIR = Path(__file__).parent.parent.parent / "benchmarks" / "open_architecture" / "schema"

_CANDIDATE_SCHEMA: dict[str, Any] | None = None
_SCENARIO_SCHEMA: dict[str, Any] | None = None


def _load_candidate_schema() -> dict[str, Any]:
    global _CANDIDATE_SCHEMA
    if _CANDIDATE_SCHEMA is None:
        schema_path = _SCHEMA_DIR / "decision_candidate.schema.json"
        _CANDIDATE_SCHEMA = json.loads(schema_path.read_text(encoding="utf-8"))
    return _CANDIDATE_SCHEMA


def _load_scenario_schema() -> dict[str, Any]:
    global _SCENARIO_SCHEMA
    if _SCENARIO_SCHEMA is None:
        schema_path = _SCHEMA_DIR / "applicability_scenario.schema.json"
        _SCENARIO_SCHEMA = json.loads(schema_path.read_text(encoding="utf-8"))
    return _SCENARIO_SCHEMA


# ── Decision Candidate Vocabulary (merged PR #389) ─────────────────────────────

VALID_CLASSIFICATIONS = frozenset({
    "prescriptive", "advisory", "descriptive", "historical", "ambiguous",
})

VALID_DOMAINS = frozenset({
    "architecture_structure",
    "dependency_technology",
    "api_interface",
    "data_contract",
    "integration_eventing",
    "persistence",
    "security_privacy",
    "deployment_infrastructure",
    "reliability_observability",
    "performance_scalability",
    "testing_quality",
    "compatibility_versioning",
    "migration_evolution",
    "ownership_boundary",
    "developer_workflow",
    "compliance",
    "cost_resource",
    "other",
})

VALID_PURPOSES = frozenset({
    "constrain",
    "standardize",
    "select",
    "prohibit",
    "require",
    "allocate_ownership",
    "define_boundary",
    "preserve_compatibility",
    "manage_risk",
    "enable_migration",
    "deprecate",
    "freeze",
    "create_exception",
    "require_evidence",
    "optimize_quality_attribute",
    "document_tradeoff",
    "other",
})

VALID_AUTHORITIES = frozenset({
    "candidate", "explicitly_accepted", "superseded", "rejected", "unknown",
})

VALID_SCOPE_TYPES = frozenset({
    "repository", "service", "package", "directory", "file_pattern",
    "component", "api", "dependency", "other",
})

VALID_LIFECYCLES = frozenset({
    "active", "superseded", "deprecated", "temporary", "unknown",
})

VALID_ENFORCEMENT_POTENTIAL = frozenset({
    "deterministic_rule", "contextual_guidance", "warning", "block",
    "not_mechanically_enforceable", "unknown",
})

VALID_HUMAN_VALIDATION_STATUSES = frozenset({
    "unreviewed", "correct", "partially_correct", "incorrect", "ambiguous",
})

VALID_RELATIONSHIP_TYPES = frozenset({
    "requires", "prohibits", "depends_on", "refines", "conflicts_with", "supersedes", "exception_to",
})


@dataclass(frozen=True)
class Scope:
    """Scope entry for a decision candidate."""

    scope_type: str
    scope_expression: str | None

    def __post_init__(self) -> None:
        if self.scope_type not in VALID_SCOPE_TYPES:
            raise ValueError(f"invalid scope_type: {self.scope_type!r}")

    def to_dict(self) -> dict[str, Any]:
        d = {"scope_type": self.scope_type}
        if self.scope_expression is not None:
            d["scope_expression"] = self.scope_expression
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scope:
        return cls(
            scope_type=str(data["scope_type"]),
            scope_expression=data.get("scope_expression"),
        )


@dataclass(frozen=True)
class Relationship:
    """Relationship to another decision/candidate."""

    relationship_type: str
    target_candidate_id: str | None
    target_reference: str | None
    confidence: float | None
    evidence_reference: str | None

    def __post_init__(self) -> None:
        if self.relationship_type not in VALID_RELATIONSHIP_TYPES:
            raise ValueError(f"invalid relationship_type: {self.relationship_type!r}")

    def to_dict(self) -> dict[str, Any]:
        d = {"relationship_type": self.relationship_type}
        if self.target_candidate_id is not None:
            d["target_candidate_id"] = self.target_candidate_id
        if self.target_reference is not None:
            d["target_reference"] = self.target_reference
        if self.confidence is not None:
            d["confidence"] = self.confidence
        if self.evidence_reference is not None:
            d["evidence_reference"] = self.evidence_reference
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Relationship:
        return cls(
            relationship_type=str(data["relationship_type"]),
            target_candidate_id=data.get("target_candidate_id"),
            target_reference=data.get("target_reference"),
            confidence=data.get("confidence"),
            evidence_reference=data.get("evidence_reference"),
        )


@dataclass(frozen=True)
class DecisionCandidate:
    """O1A Decision Candidate - inferred decision from repository analysis.

    This is RESEARCH DATA ONLY. An inferred candidate is never authoritative or enforceable.
    Vocabulary matches merged PR #389 decision_candidate.schema.json.
    """

    candidate_id: str
    repository: str
    source_file: str
    source_location: str | None
    raw_statement: str | None
    normalized_decision: str
    classification: str
    decision_domains: tuple[str, ...]
    decision_purposes: tuple[str, ...]
    authority_status: str
    authority_evidence: str | None
    scopes: tuple[Scope, ...]
    lifecycle_status: str
    relationships: tuple[Relationship, ...]
    enforcement_potential: str
    candidate_rule: str | None
    confidence: float | None
    human_validation_status: str
    human_corrections: dict[str, Any] | None

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise ValueError("candidate_id must be non-empty")
        if not self.repository:
            raise ValueError("repository must be non-empty")
        if not self.source_file:
            raise ValueError("source_file must be non-empty")
        if not self.normalized_decision:
            raise ValueError("normalized_decision must be non-empty")

        if self.classification not in VALID_CLASSIFICATIONS:
            raise ValueError(f"invalid classification: {self.classification!r}")

        if not self.decision_domains:
            raise ValueError("decision_domains must be non-empty")
        for d in self.decision_domains:
            if d not in VALID_DOMAINS:
                raise ValueError(f"invalid decision_domain: {d!r}")

        if not self.decision_purposes:
            raise ValueError("decision_purposes must be non-empty")
        for p in self.decision_purposes:
            if p not in VALID_PURPOSES:
                raise ValueError(f"invalid decision_purpose: {p!r}")

        if self.authority_status not in VALID_AUTHORITIES:
            raise ValueError(f"invalid authority_status: {self.authority_status!r}")

        for scope in self.scopes:
            if scope.scope_type not in VALID_SCOPE_TYPES:
                raise ValueError(f"invalid scope_type: {scope.scope_type!r}")

        if self.lifecycle_status not in VALID_LIFECYCLES:
            raise ValueError(f"invalid lifecycle_status: {self.lifecycle_status!r}")

        for rel in self.relationships:
            if rel.relationship_type not in VALID_RELATIONSHIP_TYPES:
                raise ValueError(f"invalid relationship_type: {rel.relationship_type!r}")

        if self.enforcement_potential not in VALID_ENFORCEMENT_POTENTIAL:
            raise ValueError(f"invalid enforcement_potential: {self.enforcement_potential!r}")

        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")

        if self.human_validation_status not in VALID_HUMAN_VALIDATION_STATUSES:
            raise ValueError(f"invalid human_validation_status: {self.human_validation_status!r}")

    def to_dict(self) -> dict[str, Any]:
        """Deterministic JSON-compatible serialization."""
        return {
            "candidate_id": self.candidate_id,
            "repository": self.repository,
            "source_file": self.source_file,
            "source_location": self.source_location,
            "raw_statement": self.raw_statement,
            "normalized_decision": self.normalized_decision,
            "classification": self.classification,
            "decision_domains": list(self.decision_domains),
            "decision_purposes": list(self.decision_purposes),
            "authority_status": self.authority_status,
            "authority_evidence": self.authority_evidence,
            "scopes": [s.to_dict() for s in self.scopes],
            "lifecycle_status": self.lifecycle_status,
            "relationships": [r.to_dict() for r in self.relationships],
            "enforcement_potential": self.enforcement_potential,
            "candidate_rule": self.candidate_rule,
            "confidence": self.confidence,
            "human_validation_status": self.human_validation_status,
            "human_corrections": self.human_corrections,
        }

    def to_json(self) -> str:
        """Deterministic JSON serialization with sorted keys."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionCandidate:
        """Create from validated dictionary."""
        validate_candidate(data)

        return cls(
            candidate_id=str(data["candidate_id"]),
            repository=str(data["repository"]),
            source_file=str(data["source_file"]),
            source_location=data.get("source_location"),
            raw_statement=data.get("raw_statement"),
            normalized_decision=str(data["normalized_decision"]),
            classification=str(data["classification"]),
            decision_domains=tuple(str(d) for d in data["decision_domains"]),
            decision_purposes=tuple(str(p) for p in data["decision_purposes"]),
            authority_status=str(data["authority_status"]),
            authority_evidence=data.get("authority_evidence"),
            scopes=tuple(Scope.from_dict(s) for s in data.get("scopes", [])),
            lifecycle_status=str(data["lifecycle_status"]),
            relationships=tuple(Relationship.from_dict(r) for r in data.get("relationships", [])),
            enforcement_potential=str(data["enforcement_potential"]),
            candidate_rule=data.get("candidate_rule"),
            confidence=data.get("confidence"),
            human_validation_status=str(data["human_validation_status"]),
            human_corrections=data.get("human_corrections"),
        )

    @classmethod
    def from_json(cls, text: str) -> DecisionCandidate:
        """Parse from JSON string."""
        return cls.from_dict(json.loads(text))


def validate_candidate(data: dict[str, Any]) -> None:
    """Validate a candidate dict against the merged JSON Schema.

    Raises:
        jsonschema.ValidationError: If validation fails.
    """
    schema = _load_candidate_schema()
    jsonschema.validate(instance=data, schema=schema)


# ── Applicability Scenario ────────────────────────────────────────────────────

VALID_VALIDATION_STATES = frozenset({
    "unreviewed", "reviewed", "ambiguous",
})


@dataclass(frozen=True)
class ChangeContext:
    """Change context for an applicability scenario."""

    path: str | None
    component: str | None
    change_type: str | None
    dependencies: tuple[str, ...]
    api: str | None
    technology: str | None
    other_context: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "component": self.component,
            "change_type": self.change_type,
            "dependencies": list(self.dependencies),
            "api": self.api,
            "technology": self.technology,
            "other_context": self.other_context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChangeContext:
        return cls(
            path=data.get("path"),
            component=data.get("component"),
            change_type=data.get("change_type"),
            dependencies=tuple(str(d) for d in data.get("dependencies", [])),
            api=data.get("api"),
            technology=data.get("technology"),
            other_context=data.get("other_context"),
        )


@dataclass(frozen=True)
class ApplicabilityScenario:
    """O1A Applicability Scenario - benchmark reference label.

    Expected governing decisions are BENCHMARK REFERENCE LABELS.
    They must NEVER be derived automatically from Mneme's own prediction during scoring.
    Vocabulary matches merged PR #389 applicability_scenario.schema.json.
    """

    scenario_id: str
    repository: str
    description: str
    change_context: ChangeContext
    expected_governing_decision_ids: tuple[str, ...]
    mneme_governing_decision_ids: tuple[str, ...]
    human_notes: str | None
    validation_state: str

    def __post_init__(self) -> None:
        if not self.scenario_id:
            raise ValueError("scenario_id must be non-empty")
        if not self.repository:
            raise ValueError("repository must be non-empty")
        if not self.description:
            raise ValueError("description must be non-empty")
        if not self.expected_governing_decision_ids:
            raise ValueError("expected_governing_decision_ids must be non-empty")
        if self.validation_state not in VALID_VALIDATION_STATES:
            raise ValueError(f"invalid validation_state: {self.validation_state!r}")

    def to_dict(self) -> dict[str, Any]:
        """Deterministic JSON-compatible serialization."""
        return {
            "scenario_id": self.scenario_id,
            "repository": self.repository,
            "description": self.description,
            "change_context": self.change_context.to_dict(),
            "expected_governing_decision_ids": list(self.expected_governing_decision_ids),
            "mneme_governing_decision_ids": list(self.mneme_governing_decision_ids),
            "human_notes": self.human_notes,
            "validation_state": self.validation_state,
        }

    def to_json(self) -> str:
        """Deterministic JSON serialization with sorted keys."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ApplicabilityScenario:
        """Create from validated dictionary."""
        validate_scenario(data)

        return cls(
            scenario_id=str(data["scenario_id"]),
            repository=str(data["repository"]),
            description=str(data["description"]),
            change_context=ChangeContext.from_dict(data["change_context"]),
            expected_governing_decision_ids=tuple(str(e) for e in data["expected_governing_decision_ids"]),
            mneme_governing_decision_ids=tuple(str(e) for e in data.get("mneme_governing_decision_ids", [])),
            human_notes=data.get("human_notes"),
            validation_state=str(data["validation_state"]),
        )

    @classmethod
    def from_json(cls, text: str) -> ApplicabilityScenario:
        """Parse from JSON string."""
        return cls.from_dict(json.loads(text))

    def with_mneme_predictions(self, mneme_ids: list[str]) -> ApplicabilityScenario:
        """Return new scenario with Mneme predictions populated.

        This is used during scoring. Expected governing decision IDs remain unchanged.
        """
        return ApplicabilityScenario(
            scenario_id=self.scenario_id,
            repository=self.repository,
            description=self.description,
            change_context=self.change_context,
            expected_governing_decision_ids=self.expected_governing_decision_ids,
            mneme_governing_decision_ids=tuple(mneme_ids),
            human_notes=self.human_notes,
            validation_state=self.validation_state,
        )


def validate_scenario(data: dict[str, Any]) -> None:
    """Validate a scenario dict against the merged JSON Schema.

    Raises:
        jsonschema.ValidationError: If validation fails.
    """
    schema = _load_scenario_schema()
    jsonschema.validate(instance=data, schema=schema)