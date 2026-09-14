"""
decision_authority.py — Mneme decision authority service (D2C1, ADR-027).

Protocol-independent Core module implementing the accepted-proposal
authority path recorded in ADR-027 ("Accepted-proposal authority path" /
D2C persistence boundary) and issue #365's authority service scope:

```text
DecisionProposalStore
        |
        | human Mneme authority accepts  <-- this service
        v
accepted proposal + accepted_decision_id
        |
        | deterministic materialization
        v
project_memory.json decisions[]
        |
        v
CanonicalDecisionRecord via existing decisions_to_canonical()
        |
        v
existing Audit / retrieval / later protection
```

Ownership. This service owns ALL lifecycle, identity, collision,
persistence, recovery, and verification semantics of the authority
action: transition legality, canonical decision id assignment, collision
checks, memory materialization, crash recovery/idempotency, and
fail-closed behavior. Adapters (future CLI, any other UI) must call this
service; none of these rules may be duplicated in a transport. The MCP
stays exactly the six D2B producer/read tools, and this module imports no
MCP, CLI, or frozen runtime module — it is callable from plain Python.

Authority semantics. Acceptance/rejection is Mneme-owned human
authority. Only a ``proposed`` proposal may transition; ``accepted`` and
``rejected`` are terminal in D2C1. Rejection never touches
``project_memory.json`` and never creates a canonical record. Acceptance
materializes exactly one architecture decision with status ``active``
(= authoritative and eligible for the existing runtime/Audit; NOT
Protected, not mechanically enforced, no rule, no rule applicability, no
evidence — those remain separate Mneme processes; protection activation is
never called from here).

Canonical identity (pinned algorithm, D2C1). No random UUIDs:

```text
default_decision_id = "ddec-" + SHA-256(
    canonical_json([proposal_id, producer_key, content_fingerprint])
)[:32]
```

``canonical_json`` is ``json.dumps(sort_keys=True, separators=(",",":"))``
(the same canonicalization as ``decision_proposal`` identity). The id is
deterministic from the immutable proposal identity, lives in the
``ddec-`` namespace distinct from the ``dprop-`` proposal-id namespace,
and never equals a proposal id. An explicit human-authority-assigned
``decision_id`` is supported: it must be a non-empty string and must not
collide with any proposal id. Once ``accepted_decision_id`` is recorded,
retries reuse it and cannot replace it.

Fail-safe write order (ADR-027; no cross-file transaction, no database):

```text
1. validate everything before mutation
2. atomically transition the proposal: proposed -> accepted + id
3. atomically materialize the decision into project_memory.json
4. reload memory; derive canonical records via decisions_to_canonical()
5. verify both representations; only then return success
```

Recovery (explicit, fail-closed):

* crash after step 2 (proposal accepted, decision missing): retry reuses
  the stored id, materializes, verifies, and returns an idempotent
  ``already_accepted`` + ``recovered`` result;
* fully accepted + exact expected decision present: no duplicate, no
  history mutation, verification still runs, idempotent success;
* dangerous reverse half-state (proposal still ``proposed`` while the
  requested decision id already exists in memory): fail closed —
  acceptance is never inferred and the proposal is never auto-transitioned;
* collision (same decision id, content differing from the exact expected
  D2C materialization): fail closed — never overwritten, never merged;
  no partial success is ever reported as success.

Provenance boundary (ADR-027). Full producer provenance stays durably
preserved in the retained proposal; the durable proposal ↔ decision link
is ``accepted_decision_id``. The runtime ``Decision`` /
``decisions_to_canonical`` path does NOT carry proposal provenance into
``CanonicalSourceEvidence``; nothing is fabricated: materialized records
carry no source block (so the canonical record has empty source evidence),
no constraints, no anti-patterns, no typed rules, and no test evidence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from mneme.decision_index import (
    CANONICAL_VERSION,
    CanonicalArchitectureIndex,
    CanonicalDecisionRecord,
    decisions_to_canonical,
)
from mneme.decision_proposal import (
    PROPOSAL_STATUS_ACCEPTED,
    PROPOSAL_STATUS_PROPOSED,
    PROPOSAL_STATUS_REJECTED,
    DecisionProposal,
)
from mneme.decision_proposal_store import DecisionProposalStore
from mneme.memory_store import MemoryStore
from mneme.setup_state import atomic_write_json

_DECISION_ID_PREFIX = "ddec-"
_DECISION_ID_HEX_LENGTH = 32

# Field separator for hashed id material (unit separator; never valid input).
_ID_SEPARATOR = "\x1f"


# ── Fail-closed authority error taxonomy (narrow, deterministic) ────────────


class DecisionAuthorityError(Exception):
    """Base class for Mneme decision authority failures (fail closed).

    Raised instead of returning a partial or ambiguous success. The
    proposal store may already have transitioned when a post-write
    verification error is raised; that state is explicit, non-enforcing,
    and recoverable by retry (see module docstring). Nothing is silently
    repaired, overwritten, or merged.
    """


class ProposalNotFoundError(DecisionAuthorityError):
    """The requested proposal id does not exist in the proposal store."""


class ProposalAlreadyRejectedError(DecisionAuthorityError):
    """Acceptance requested for a rejected proposal (terminal in D2C1)."""


class ProposalAlreadyAcceptedError(DecisionAuthorityError):
    """Rejection requested for an accepted proposal (terminal in D2C1)."""


class AcceptedProposalIdConflictError(DecisionAuthorityError):
    """A retry requested a different decision id than the stored one."""


class ProposalStoreCorruptError(DecisionAuthorityError):
    """The proposal store is malformed or disagrees with the authority
    view of the lifecycle (fail closed; never repaired)."""


class MemoryMissingError(DecisionAuthorityError):
    """The project memory file does not exist (nothing was mutated)."""


class MemoryInvalidError(DecisionAuthorityError):
    """The project memory file is malformed or fails the memory schema.

    The file is never silently repaired; the caller fixes the file.
    """


class DecisionIdCollisionError(DecisionAuthorityError):
    """An existing decision with the same id has different content.

    Fail closed: the existing decision is never overwritten or merged.
    """


class ReverseHalfStateError(DecisionAuthorityError):
    """An active runtime decision exists while the proposal is ``proposed``.

    Dangerous reverse half-state (corruption or manual modification):
    acceptance is never inferred and the proposal is never
    auto-transitioned; the state must be fixed by the operator.
    """


class DecisionIdNamespaceError(DecisionAuthorityError):
    """An explicit decision id violates the proposal-id namespace rule."""


class MaterializationVerificationError(DecisionAuthorityError):
    """Post-write runtime verification failed (no success is reported)."""


class CanonicalVerificationError(DecisionAuthorityError):
    """Post-write canonical verification failed (fail closed)."""


# ── Deterministic canonical decision identity (pinned in D2C1) ──────────────


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def default_decision_id_of(proposal: DecisionProposal) -> str:
    """Default canonical decision id for ``proposal`` (pinned D2C1).

    ``"ddec-" + SHA-256(canonical_json([proposal_id, producer_key,
    content_fingerprint]))[:32]`` — deterministic from the immutable
    proposal identity; the ``ddec-`` namespace never intersects the
    ``dprop-`` proposal-id namespace; identical proposals always derive
    the identical id; distinct proposal identities derive distinct ids.
    """
    payload = [
        proposal.proposal_id,
        proposal.producer_key,
        proposal.content_fingerprint,
    ]
    return _DECISION_ID_PREFIX + _sha256_hex(_canonical_json(payload))[
        :_DECISION_ID_HEX_LENGTH
    ]


# ── Result types (facts only; no inferred product tiers) ────────────────────


@dataclass(frozen=True)
class AcceptResult:
    """Outcome of one ``accept`` call.

    Attributes:
        proposal_id:      Accepted proposal id.
        decision_id:      Canonical decision id used (stored id on retry).
        proposal_status:  Proposal lifecycle status after the call
                          (``accepted``).
        materialized:     This call wrote the decision into
                          ``project_memory.json``.
        already_accepted: The proposal was already accepted before this
                          call (idempotent retry / crash-recovery entry).
        recovered:        Crash-recovery completion: the proposal was
                          already accepted while the decision was missing,
                          and this call materialized and verified it.
        verified:         Runtime AND canonical verification both passed
                          (only set on the returned success path).
    """

    proposal_id: str
    decision_id: str
    proposal_status: str
    materialized: bool
    already_accepted: bool
    recovered: bool
    verified: bool


@dataclass(frozen=True)
class RejectResult:
    """Outcome of one ``reject`` call (narrow, deterministic).

    ``already_rejected=True`` means an identical rejection already existed;
    the proposal is returned unchanged and nothing is rewritten.
    """

    proposal_id: str
    proposal_status: str
    already_rejected: bool


# ── Materialized decision shape (ADR-027 "The decision created by acceptance")


def expected_materialization_entry(
    proposal: DecisionProposal, decision_id: str, timestamp: str
) -> dict[str, object]:
    """The exact decisions[] entry D2C1 materializes for ``proposal``.

    Mapping (ADR-027): ``decision`` ← proposal statement; ``rationale`` ←
    proposal rationale; ``scope`` ← proposal scope_hints (decision/
    retrieval scope ONLY — never include/exclude paths, never typed-rule
    applicability, never enforcement scope); ``constraints`` /
    ``anti_patterns`` / ``rules`` / ``test_evidence`` empty; ``status``
    ``active``; both timestamps the authority clock value. Proposal
    ``title`` is deliberately not mapped (no architecture contract assigns
    it a semantic field) and proposal prose never generates rules,
    constraints, anti-patterns, or evidence.
    """
    return {
        "id": decision_id,
        "decision": proposal.candidate.statement,
        "rationale": proposal.candidate.rationale,
        "scope": list(proposal.candidate.scope_hints),
        "constraints": [],
        "anti_patterns": [],
        "rules": [],
        "test_evidence": [],
        "created_at": timestamp,
        "updated_at": timestamp,
        "status": "active",
    }


def _materialization_mismatch(
    entry: dict[str, object],
    proposal: DecisionProposal,
    decision_id: str,
) -> str | None:
    """Return a mismatch reason, or ``None`` when the entry is exactly the
    expected D2C materialization of ``proposal`` under ``decision_id``.

    Deterministic content fields must match exactly (present and equal).
    Timestamps were owned by the first acceptance attempt's clock, so a
    recovered verification requires only that they are non-empty strings;
    every other deviation — including a decision that protection later
    gave rules — is a mismatch (fail closed, never overwritten).
    """
    expected_fields: tuple[tuple[str, object], ...] = (
        ("decision", proposal.candidate.statement),
        ("rationale", proposal.candidate.rationale),
        ("scope", list(proposal.candidate.scope_hints)),
        ("constraints", []),
        ("anti_patterns", []),
        ("rules", []),
        ("test_evidence", []),
        ("status", "active"),
    )
    for field, expected_value in expected_fields:
        if field not in entry:
            return f"field {field!r} missing"
        if entry[field] != expected_value:
            return f"field {field!r} differs from the expected materialization"
    for timestamp_field in ("created_at", "updated_at"):
        value = entry.get(timestamp_field)
        if not isinstance(value, str) or not value:
            return f"field {timestamp_field!r} must be a non-empty string"
    if entry.get("id") != decision_id:
        return "id mismatch"
    return None


def _default_clock() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class DecisionAuthorityService:
    """Mneme authority service over one proposal store + one memory file.

    Args:
        proposal_store: The dedicated proposal store (required). The
            service uses ``transition_if_proposed`` for every lifecycle
            mutation and never mutates candidate content.
        memory_path: Path to the existing ``project_memory.json`` ledger
            (the bounded D2C durable backing for accepted decisions).
            The file must exist, parse, and load through
            ``MemoryStore`` before any mutation; malformed memory fails
            closed and is never repaired.
        clock: Injectable clock returning a timestamp string; owns
            ``created_at``/``updated_at`` of newly materialized decisions
            (the authority clock — callers cannot assert timestamps).
    """

    def __init__(
        self,
        proposal_store: DecisionProposalStore,
        memory_path: str | Path,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._store = proposal_store
        self._memory_path = Path(memory_path)
        self._clock = clock if clock is not None else _default_clock

    # ── Authority operations ─────────────────────────────────────────────

    def accept(
        self, proposal_id: str, decision_id: str | None = None
    ) -> AcceptResult:
        """Accept a proposed proposal and materialize its decision.

        Full contract (ADR-027 fail-safe order):

        1. validate everything before mutation — proposal exists, is not
           rejected, the requested id is legal, the memory file exists,
           parses, and loads through ``MemoryStore``, the collision scan
           is complete, and no reverse half-state exists;
        2. atomically transition the proposal
           ``proposed -> accepted + accepted_decision_id``;
        3. atomically materialize exactly one decision entry into
           ``project_memory.json`` ``decisions[]`` (only when absent);
        4. reload through ``MemoryStore`` and derive the canonical
           representation through the existing ``decisions_to_canonical``;
        5. verify both representations; only then return success.

        Idempotency/recovery: an already-accepted proposal retries with
        its stored ``accepted_decision_id`` (a different requested id
        fails closed); a missing decision is materialized and verified
        (``recovered=True``); an exact expected decision present means
        success with no write; a proposed proposal whose requested id
        already exists fails closed as a reverse half-state.

        Does NOT: assign an Audit tier, activate protection, create
        rules/applicability/evidence, or touch anything else in memory.
        """
        proposal = self._get_proposal(proposal_id)
        if proposal.status == PROPOSAL_STATUS_REJECTED:
            raise ProposalAlreadyRejectedError(
                f"proposal {proposal_id!r} is rejected; rejected proposals "
                "cannot be accepted (terminal in D2C1)"
            )
        if decision_id is not None:
            if not (isinstance(decision_id, str) and decision_id):
                raise DecisionIdNamespaceError(
                    "an explicit decision_id must be a non-empty string"
                )
            proposal_ids = {p.proposal_id for p in self._list_proposals()}
            if decision_id in proposal_ids:
                raise DecisionIdNamespaceError(
                    f"explicit decision_id {decision_id!r} collides with "
                    "the proposal-id namespace; a canonical decision id "
                    "must never equal a proposal id"
                )
        stored_id = proposal.accepted_decision_id
        if proposal.status == PROPOSAL_STATUS_ACCEPTED:
            if stored_id is None:  # defensive; the domain type forbids this
                raise ProposalStoreCorruptError(
                    f"proposal {proposal_id!r} is accepted without a "
                    "stored accepted_decision_id"
                )
            if decision_id is not None and decision_id != stored_id:
                raise AcceptedProposalIdConflictError(
                    f"proposal {proposal_id!r} is already accepted with "
                    f"decision id {stored_id!r}; retries cannot replace "
                    f"the stored accepted_decision_id with "
                    f"{decision_id!r}"
                )
            effective_id = stored_id
            already_accepted = True
        else:
            effective_id = (
                decision_id
                if decision_id is not None
                else default_decision_id_of(proposal)
            )
            already_accepted = False

        raw = self._load_memory_raw()
        entries = raw["decisions"]
        existing_entry = self._collision_scan(entries, effective_id)
        if not already_accepted and existing_entry is not None:
            raise ReverseHalfStateError(
                f"decision id {effective_id!r} already exists in "
                f"{self._memory_path} while proposal {proposal_id!r} is "
                "still proposed; acceptance is never inferred from an "
                "existing runtime decision (dangerous reverse half-state; "
                "fail closed)"
            )
        if existing_entry is not None:
            mismatch = _materialization_mismatch(
                existing_entry, proposal, effective_id
            )
            if mismatch is not None:
                raise DecisionIdCollisionError(
                    f"decision id {effective_id!r} already exists in "
                    f"{self._memory_path} with different content "
                    f"({mismatch}); the existing decision is never "
                    "overwritten or merged"
                )

        if not already_accepted:
            transitioned, transitioned_ok = self._transition(
                proposal_id, PROPOSAL_STATUS_ACCEPTED, effective_id
            )
            if not transitioned_ok and (
                transitioned.accepted_decision_id != effective_id
            ):
                raise AcceptedProposalIdConflictError(
                    f"proposal {proposal_id!r} was accepted concurrently "
                    f"with decision id "
                    f"{transitioned.accepted_decision_id!r}"
                )
            proposal = transitioned

        materialized = False
        expected_timestamp: str | None = None
        if existing_entry is None:
            expected_timestamp = self._clock()
            entries.append(
                expected_materialization_entry(
                    proposal, effective_id, expected_timestamp
                )
            )
            self._write_memory_raw(raw)
            materialized = True

        self._verify(proposal, effective_id, expected_timestamp)
        return AcceptResult(
            proposal_id=proposal_id,
            decision_id=effective_id,
            proposal_status=PROPOSAL_STATUS_ACCEPTED,
            materialized=materialized,
            already_accepted=already_accepted,
            recovered=already_accepted and materialized,
            verified=True,
        )

    def reject(self, proposal_id: str) -> RejectResult:
        """Reject a proposed proposal (no memory/canonical side effects).

        Only ``proposed`` proposals may be rejected; rejecting an accepted
        proposal fails closed. A rejected proposal never carries
        ``accepted_decision_id``, never touches ``project_memory.json``,
        and remains inspectable in the store. A repeated identical
        rejection is deterministic and idempotent
        (``already_rejected=True``). Reopening/amending is not supported.
        """
        proposal = self._get_proposal(proposal_id)
        if proposal.status == PROPOSAL_STATUS_REJECTED:
            return RejectResult(
                proposal_id=proposal_id,
                proposal_status=PROPOSAL_STATUS_REJECTED,
                already_rejected=True,
            )
        if proposal.status == PROPOSAL_STATUS_ACCEPTED:
            raise ProposalAlreadyAcceptedError(
                f"proposal {proposal_id!r} is accepted; rejecting an "
                "accepted proposal fails closed (terminal in D2C1)"
            )
        self._transition(proposal_id, PROPOSAL_STATUS_REJECTED, None)
        persisted = self._get_proposal(proposal_id)
        if persisted.status != PROPOSAL_STATUS_REJECTED:
            raise ProposalStoreCorruptError(
                f"proposal {proposal_id!r} did not persist as rejected; "
                "failing closed"
            )
        return RejectResult(
            proposal_id=proposal_id,
            proposal_status=PROPOSAL_STATUS_REJECTED,
            already_rejected=False,
        )

    # ── Internal helpers (validation-first, fail closed) ─────────────────

    def _get_proposal(self, proposal_id: str) -> DecisionProposal:
        try:
            proposal = self._store.get(proposal_id)
        except ValueError as exc:
            raise ProposalStoreCorruptError(str(exc)) from exc
        if proposal is None:
            raise ProposalNotFoundError(
                f"proposal {proposal_id!r} not found"
            )
        return proposal

    def _list_proposals(self) -> tuple[DecisionProposal, ...]:
        try:
            return self._store.list_proposals()
        except ValueError as exc:
            raise ProposalStoreCorruptError(str(exc)) from exc

    def _transition(
        self,
        proposal_id: str,
        target_status: str,
        accepted_decision_id: str | None,
    ) -> tuple[DecisionProposal, bool]:
        try:
            return self._store.transition_if_proposed(
                proposal_id, target_status, accepted_decision_id
            )
        except ValueError as exc:
            raise ProposalStoreCorruptError(str(exc)) from exc

    def _load_memory_raw(self) -> dict[str, object]:
        """Load the memory file raw, fail closed before any mutation.

        The file must exist, parse as JSON, be an object, and load
        successfully through the existing ``MemoryStore`` schema. A
        missing ``decisions`` key is initialized to an empty list only
        where the existing write conventions permit it (``adr_import``
        ``write_imported_decisions``); a malformed memory file is never
        silently repaired.
        """
        if not self._memory_path.exists():
            raise MemoryMissingError(
                f"memory file {self._memory_path} does not exist"
            )
        try:
            MemoryStore(self._memory_path).load()
        except FileNotFoundError as exc:
            raise MemoryMissingError(str(exc)) from exc
        except Exception as exc:
            raise MemoryInvalidError(
                f"memory file {self._memory_path} is not loadable project "
                f"memory: {exc}"
            ) from exc
        try:
            with open(self._memory_path, encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError) as exc:
            raise MemoryInvalidError(
                f"memory file {self._memory_path} could not be read as "
                f"JSON: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise MemoryInvalidError(
                f"memory file {self._memory_path} is not a JSON object"
            )
        entries = raw.get("decisions")
        if entries is None:
            raw["decisions"] = []
        elif not isinstance(entries, list):
            raise MemoryInvalidError(
                f"memory file {self._memory_path} has a malformed "
                "decisions[] (not a list)"
            )
        return raw

    def _collision_scan(
        self, entries: list[object], decision_id: str
    ) -> dict[str, object] | None:
        """Scan decisions[] for a colliding entry (fail closed)."""
        for entry in entries:
            if not isinstance(entry, dict):
                raise MemoryInvalidError(
                    f"memory file {self._memory_path} has a malformed "
                    "decisions[] entry (not an object)"
                )
            if entry.get("id") == decision_id:
                return entry
        return None

    def _write_memory_raw(self, raw: dict[str, object]) -> None:
        """Atomic raw write preserving every other top-level key verbatim."""
        atomic_write_json(self._memory_path, raw)

    def _verify(
        self,
        proposal: DecisionProposal,
        decision_id: str,
        expected_timestamp: str | None,
    ) -> None:
        """Verify both representations; raise before success is reported.

        1. reload through ``MemoryStore``;
        2. find the runtime ``Decision`` by ``accepted_decision_id``;
        3. assert its fields equal the expected D2C materialization;
        4. derive canonical records through the existing
           ``decisions_to_canonical``;
        5. find the canonical record by the same id and assert identity,
           version, lifecycle, statement, rationale, scope, and the
           no-rules/no-evidence invariants.
        """
        store = MemoryStore(self._memory_path)
        try:
            store.load()
        except Exception as exc:
            raise MaterializationVerificationError(
                f"verification could not reload memory: {exc}"
            ) from exc
        decision = next(
            (d for d in store.decisions() if d.id == decision_id), None
        )
        if decision is None:
            raise MaterializationVerificationError(
                f"decision {decision_id!r} missing from reloaded memory"
            )
        candidate = proposal.candidate
        runtime_expectations: tuple[tuple[str, object, object], ...] = (
            ("decision", decision.decision, candidate.statement),
            ("rationale", decision.rationale, candidate.rationale),
            ("scope", list(decision.scope), list(candidate.scope_hints)),
            ("constraints", decision.constraints, []),
            ("anti_patterns", decision.anti_patterns, []),
            ("rules", decision.rules, []),
            ("test_evidence", decision.test_evidence, []),
            ("status", decision.status, "active"),
        )
        for field, actual, expected in runtime_expectations:
            if actual != expected:
                raise MaterializationVerificationError(
                    f"materialized decision {decision_id!r} field "
                    f"{field!r} is {actual!r}, expected {expected!r}"
                )
        if expected_timestamp is not None:
            for timestamp_field, value in (
                ("created_at", decision.created_at),
                ("updated_at", decision.updated_at),
            ):
                if value != expected_timestamp:
                    raise MaterializationVerificationError(
                        f"materialized decision {decision_id!r} field "
                        f"{timestamp_field!r} is {value!r}, expected the "
                        f"authority clock value {expected_timestamp!r}"
                    )
        else:
            for timestamp_field, value in (
                ("created_at", decision.created_at),
                ("updated_at", decision.updated_at),
            ):
                if not (isinstance(value, str) and value):
                    raise MaterializationVerificationError(
                        f"materialized decision {decision_id!r} field "
                        f"{timestamp_field!r} is missing"
                    )
        index: CanonicalArchitectureIndex = decisions_to_canonical(
            store.decisions()
        )
        record: CanonicalDecisionRecord | None = next(
            (r for r in index.records if r.decision_id == decision_id), None
        )
        if record is None:
            raise CanonicalVerificationError(
                f"canonical record {decision_id!r} missing after "
                "decisions_to_canonical"
            )
        canonical_expectations: tuple[tuple[str, object, object], ...] = (
            ("version", record.version, CANONICAL_VERSION),
            ("lifecycle_status", record.lifecycle_status, "active"),
            ("statement", record.statement, candidate.statement),
            ("rationale", record.rationale, candidate.rationale),
            ("context_scope", record.context_scope, tuple(candidate.scope_hints)),
            ("constraints", record.constraints, ()),
            ("anti_patterns", record.anti_patterns, ()),
            ("derived_rule_ids", record.derived_rule_ids, ()),
            ("test_evidence", record.test_evidence, ()),
        )
        for field, actual, expected in canonical_expectations:
            if actual != expected:
                raise CanonicalVerificationError(
                    f"canonical record {decision_id!r} field {field!r} is "
                    f"{actual!r}, expected {expected!r}"
                )


__all__ = [
    "AcceptedProposalIdConflictError",
    "AcceptResult",
    "CanonicalVerificationError",
    "DecisionAuthorityError",
    "DecisionAuthorityService",
    "DecisionIdCollisionError",
    "DecisionIdNamespaceError",
    "MaterializationVerificationError",
    "MemoryInvalidError",
    "MemoryMissingError",
    "ProposalAlreadyAcceptedError",
    "ProposalAlreadyRejectedError",
    "ProposalNotFoundError",
    "ProposalStoreCorruptError",
    "RejectResult",
    "default_decision_id_of",
    "expected_materialization_entry",
]
