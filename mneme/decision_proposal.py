"""
decision_proposal.py — Decision proposal domain model (ADR-027, D2A).

Non-authoritative candidate decisions submitted by external producers.
A proposal is NOT a canonical decision (ADR-023): it never enforces, never
creates a typed rule, and never projects into Layer 1 governance. Proposal
lifecycle (``proposed`` / ``accepted`` / ``rejected``) is separate from the
canonical decision lifecycle.

Authority boundary (ADR-027 sections 2, 3, 7):

* Producers submit ``DecisionProposalCandidate`` input only. The candidate
  type structurally cannot carry status, accepted decision ids, canonical
  lifecycle state, typed rules, trusted evidence, or enforcement state.
* Every producer-created proposal enters as ``proposed``.
* ``accepted`` / ``rejected`` states exist in the model because ADR-027
  defines them, but no producer path in D2A causes those transitions; they
  are reserved for the separate Mneme authority action (D2C).

Provenance (ADR-027 section 9) is first-class but informational. Producer
claims are never mapped into ``CanonicalTestEvidence`` or trusted execution
evidence (ADR-024/ADR-025).

Deterministic identity (ADR-027 section 8)
------------------------------------------
No random UUIDs. Proposal identity is derived from:

1. a producer/source key over
   ``producer_name + producer_type + source_reference + external_source_id
   + source_version + repository_locator``; and
2. an exact deterministic fingerprint of the candidate content.

``proposed_at`` is excluded from identity. Consequences:

* identical source/version/content resend -> the same proposal id, so the
  store returns the existing proposal (idempotent, no duplicate);
* same source/version, changed content -> a new proposal id (new candidate);
  the previous proposal is retained;
* changed source version -> a new producer key, hence a new proposal id;
  the previous proposal is retained;
* no silent overwrite, ever.

Fallback for absent optional key components: when ``external_source_id``,
``source_version``, or ``repository_locator`` is absent, the literal marker
``"-"`` is used in the key material. This is the narrowest deterministic
fallback justified by the supplied provenance: the content fingerprint
remains part of the identity, so distinct candidates from the same
producer/document never collide, and identical resends remain idempotent.
No LLM, vector, or semantic similarity participates in identity.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

PROPOSAL_STATUS_PROPOSED = "proposed"
PROPOSAL_STATUS_ACCEPTED = "accepted"
PROPOSAL_STATUS_REJECTED = "rejected"

VALID_PROPOSAL_STATUSES: frozenset[str] = frozenset({
    PROPOSAL_STATUS_PROPOSED,
    PROPOSAL_STATUS_ACCEPTED,
    PROPOSAL_STATUS_REJECTED,
})

ORIGIN_AI_GENERATED = "ai_generated"
ORIGIN_HUMAN_AUTHORED = "human_authored"
ORIGIN_IMPORTED_UNKNOWN = "imported_unknown"

VALID_ORIGIN_CLASSIFICATIONS: frozenset[str] = frozenset({
    ORIGIN_AI_GENERATED,
    ORIGIN_HUMAN_AUTHORED,
    ORIGIN_IMPORTED_UNKNOWN,
})

# Marker for absent optional source-key components (see module docstring).
_ABSENT_COMPONENT = "-"

# Field separator for hashed key material (unit separator; never valid input).
_KEY_SEPARATOR = "\x1f"

_PROPOSAL_ID_PREFIX = "dprop-"
_PROPOSAL_ID_HEX_LENGTH = 32


def _require_non_empty_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_str_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not all(
        isinstance(entry, str) and entry for entry in value
    ):
        raise ValueError(f"{field_name} must be a tuple of non-empty strings")
    return value


@dataclass(frozen=True)
class DecisionProposalSourceProvenance:
    """Typed producer/source provenance for one proposal (ADR-027 section 9).

    Informational only: these claims never become trusted execution
    evidence (ADR-024/ADR-025) and never feed ``CanonicalTestEvidence``.

    Attributes:
        producer_name:          Submitting producer/system name.
        producer_type:          Producer/system type (e.g. ``"architecture
                                agent"``, ``"document tooling"``).
        source_reference:       Source document/output reference.
        external_source_id:     Producer-side decision/source id, when the
                                source system has one.
        source_version:         Source version or commit, when available.
        repository_locator:     Repository/project locator, when available.
        origin_classification:  One of ``ai_generated``, ``human_authored``,
                                ``imported_unknown``.
    """

    producer_name: str
    producer_type: str
    source_reference: str
    external_source_id: str = ""
    source_version: str = ""
    repository_locator: str = ""
    origin_classification: str = ORIGIN_IMPORTED_UNKNOWN

    def __post_init__(self) -> None:
        _require_non_empty_str(self.producer_name, "producer_name")
        _require_non_empty_str(self.producer_type, "producer_type")
        _require_non_empty_str(self.source_reference, "source_reference")
        for optional in (
            self.external_source_id,
            self.source_version,
            self.repository_locator,
        ):
            if not isinstance(optional, str):
                raise ValueError("optional provenance components must be strings")
        if self.origin_classification not in VALID_ORIGIN_CLASSIFICATIONS:
            raise ValueError(
                f"origin_classification {self.origin_classification!r} is not "
                f"one of {sorted(VALID_ORIGIN_CLASSIFICATIONS)}"
            )


@dataclass(frozen=True)
class DecisionProposalCandidate:
    """Producer-controlled proposal input (ADR-027 section 4).

    This type structurally excludes every authoritative field: there is no
    ``status``, no ``accepted_decision_id``, no canonical lifecycle state,
    no typed rules, no trusted evidence, and no enforcement state. A
    producer cannot grant itself authority because the input type cannot
    carry it.

    ``provenance`` may be ``None`` only for batch submission with shared
    provenance (``DecisionIndexService.propose_batch``); the service fails
    closed when neither the candidate nor the batch supplies one.
    """

    title: str
    statement: str
    rationale: str = ""
    provenance: DecisionProposalSourceProvenance | None = None
    scope_hints: tuple[str, ...] = ()
    architecture_context: dict[str, str] = field(default_factory=dict)
    related_decision_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty_str(self.title, "title")
        _require_non_empty_str(self.statement, "statement")
        if not isinstance(self.rationale, str):
            raise ValueError("rationale must be a string")
        _require_str_tuple(self.scope_hints, "scope_hints")
        _require_str_tuple(self.related_decision_ids, "related_decision_ids")
        if not isinstance(self.architecture_context, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in self.architecture_context.items()
        ):
            raise ValueError(
                "architecture_context must be a dict of string keys and values"
            )


@dataclass(frozen=True)
class DecisionProposal:
    """A stored, non-authoritative decision proposal (ADR-027 section 2).

    ``status`` may represent ``accepted`` / ``rejected`` because ADR-027
    defines those states, but D2A provides no producer path that causes
    them. ``accepted_decision_id`` is populated only by the separate Mneme
    authority action (future D2C), never by ``propose``.
    """

    proposal_id: str
    status: str
    candidate: DecisionProposalCandidate
    producer_key: str
    content_fingerprint: str
    proposed_at: str
    accepted_decision_id: str | None = None

    def __post_init__(self) -> None:
        if self.status not in VALID_PROPOSAL_STATUSES:
            raise ValueError(
                f"proposal status {self.status!r} is not one of "
                f"{sorted(VALID_PROPOSAL_STATUSES)}"
            )
        # Lifecycle/link invariants (fail closed). ``accepted`` requires the
        # canonical decision id assigned by the separate Mneme authority
        # action; ``proposed``/``rejected`` must not carry one. This is
        # domain validation only: D2C still owns the authority transition,
        # and no producer path can reach these states through D2A.
        if self.status == PROPOSAL_STATUS_ACCEPTED:
            if not (
                isinstance(self.accepted_decision_id, str)
                and self.accepted_decision_id
            ):
                raise ValueError(
                    "an accepted proposal requires a non-empty "
                    "accepted_decision_id"
                )
        elif self.accepted_decision_id is not None:
            raise ValueError(
                f"a {self.status!r} proposal must not carry "
                "accepted_decision_id"
            )


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def producer_key_of(provenance: DecisionProposalSourceProvenance) -> str:
    """Deterministic producer/source key (ADR-027 section 8).

    Hash of the canonical JSON of
    ``[producer_name, producer_type, source_reference, external_source_id,
    source_version, repository_locator]`` with absent optional components
    replaced by the ``"-"`` marker.
    """
    key_material = [
        provenance.producer_name,
        provenance.producer_type,
        provenance.source_reference,
        provenance.external_source_id or _ABSENT_COMPONENT,
        provenance.source_version or _ABSENT_COMPONENT,
        provenance.repository_locator or _ABSENT_COMPONENT,
    ]
    return _sha256_hex(_canonical_json(key_material))


def content_fingerprint_of(candidate: DecisionProposalCandidate) -> str:
    """Exact deterministic fingerprint of the candidate content.

    Covers title, statement, rationale, scope hints, architecture context,
    and related decision ids. Provenance is deliberately excluded (it is
    part of the producer key); ``proposed_at`` is not candidate content.
    """
    payload = {
        "title": candidate.title,
        "statement": candidate.statement,
        "rationale": candidate.rationale,
        "scope_hints": list(candidate.scope_hints),
        "architecture_context": candidate.architecture_context,
        "related_decision_ids": list(candidate.related_decision_ids),
    }
    return _sha256_hex(_canonical_json(payload))


def proposal_identity(
    provenance: DecisionProposalSourceProvenance,
    candidate: DecisionProposalCandidate,
) -> str:
    """Full deterministic proposal identity hex digest.

    SHA-256 over ``producer_key + separator + content_fingerprint``.
    ``proposed_at`` is excluded by construction.
    """
    return _sha256_hex(
        producer_key_of(provenance)
        + _KEY_SEPARATOR
        + content_fingerprint_of(candidate)
    )


def proposal_id_of(
    provenance: DecisionProposalSourceProvenance,
    candidate: DecisionProposalCandidate,
) -> str:
    """Stable proposal id derived from the deterministic identity.

    The 128-bit truncated prefix makes accidental collision negligible;
    the full identity remains recoverable from the stored record fields.
    """
    return _PROPOSAL_ID_PREFIX + proposal_identity(provenance, candidate)[
        :_PROPOSAL_ID_HEX_LENGTH
    ]


def merge_provenance(
    primary: DecisionProposalSourceProvenance | None,
    fallback: DecisionProposalSourceProvenance | None,
) -> DecisionProposalSourceProvenance | None:
    """Deterministically merge batch-shared provenance into a candidate's.

    The candidate's own non-empty components win; absent optional
    components are filled from the shared provenance. The candidate's
    ``origin_classification`` always wins. Returns ``None`` only when both
    inputs are ``None``.
    """
    if primary is None:
        return fallback
    if fallback is None:
        return primary
    return DecisionProposalSourceProvenance(
        producer_name=primary.producer_name or fallback.producer_name,
        producer_type=primary.producer_type or fallback.producer_type,
        source_reference=primary.source_reference or fallback.source_reference,
        external_source_id=(
            primary.external_source_id or fallback.external_source_id
        ),
        source_version=primary.source_version or fallback.source_version,
        repository_locator=(
            primary.repository_locator or fallback.repository_locator
        ),
        origin_classification=primary.origin_classification,
    )


# ── Lossless JSON serialization (store round trip) ──────────────────────────


def provenance_to_dict(provenance: DecisionProposalSourceProvenance) -> dict[str, Any]:
    return {
        "producer_name": provenance.producer_name,
        "producer_type": provenance.producer_type,
        "source_reference": provenance.source_reference,
        "external_source_id": provenance.external_source_id,
        "source_version": provenance.source_version,
        "repository_locator": provenance.repository_locator,
        "origin_classification": provenance.origin_classification,
    }


def provenance_from_dict(data: object) -> DecisionProposalSourceProvenance:
    if not isinstance(data, dict):
        raise ValueError("provenance record must be an object")
    return DecisionProposalSourceProvenance(
        producer_name=data["producer_name"],
        producer_type=data["producer_type"],
        source_reference=data["source_reference"],
        external_source_id=data.get("external_source_id", ""),
        source_version=data.get("source_version", ""),
        repository_locator=data.get("repository_locator", ""),
        origin_classification=data.get(
            "origin_classification", ORIGIN_IMPORTED_UNKNOWN
        ),
    )


def candidate_to_dict(candidate: DecisionProposalCandidate) -> dict[str, Any]:
    return {
        "title": candidate.title,
        "statement": candidate.statement,
        "rationale": candidate.rationale,
        "provenance": (
            provenance_to_dict(candidate.provenance)
            if candidate.provenance is not None
            else None
        ),
        "scope_hints": list(candidate.scope_hints),
        "architecture_context": dict(candidate.architecture_context),
        "related_decision_ids": list(candidate.related_decision_ids),
    }


def candidate_from_dict(data: object) -> DecisionProposalCandidate:
    if not isinstance(data, dict):
        raise ValueError("candidate record must be an object")
    provenance_data = data.get("provenance")
    return DecisionProposalCandidate(
        title=data["title"],
        statement=data["statement"],
        rationale=data.get("rationale", ""),
        provenance=(
            provenance_from_dict(provenance_data)
            if provenance_data is not None
            else None
        ),
        scope_hints=tuple(data.get("scope_hints", [])),
        architecture_context=dict(data.get("architecture_context", {})),
        related_decision_ids=tuple(data.get("related_decision_ids", [])),
    )


def proposal_to_dict(proposal: DecisionProposal) -> dict[str, Any]:
    return {
        "proposal_id": proposal.proposal_id,
        "status": proposal.status,
        "candidate": candidate_to_dict(proposal.candidate),
        "producer_key": proposal.producer_key,
        "content_fingerprint": proposal.content_fingerprint,
        "proposed_at": proposal.proposed_at,
        "accepted_decision_id": proposal.accepted_decision_id,
    }


def proposal_from_dict(data: object) -> DecisionProposal:
    if not isinstance(data, dict):
        raise ValueError("proposal record must be an object")
    return DecisionProposal(
        proposal_id=data["proposal_id"],
        status=data["status"],
        candidate=candidate_from_dict(data["candidate"]),
        producer_key=data["producer_key"],
        content_fingerprint=data["content_fingerprint"],
        proposed_at=data["proposed_at"],
        accepted_decision_id=data.get("accepted_decision_id"),
    )


__all__ = [
    "ORIGIN_AI_GENERATED",
    "ORIGIN_HUMAN_AUTHORED",
    "ORIGIN_IMPORTED_UNKNOWN",
    "PROPOSAL_STATUS_ACCEPTED",
    "PROPOSAL_STATUS_PROPOSED",
    "PROPOSAL_STATUS_REJECTED",
    "VALID_ORIGIN_CLASSIFICATIONS",
    "VALID_PROPOSAL_STATUSES",
    "DecisionProposal",
    "DecisionProposalCandidate",
    "DecisionProposalSourceProvenance",
    "candidate_from_dict",
    "candidate_to_dict",
    "content_fingerprint_of",
    "merge_provenance",
    "producer_key_of",
    "proposal_from_dict",
    "proposal_id_of",
    "proposal_identity",
    "proposal_to_dict",
    "provenance_from_dict",
    "provenance_to_dict",
]
