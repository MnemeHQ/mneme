"""
decision_proposal_store.py — Local decision proposal persistence (D2A).

A dedicated proposal store, deliberately separate from:

* ``mneme.memory_store.MemoryStore`` and ``.mneme/project_memory.json``
  (runtime Layer 1 policy memory — proposals must never touch it);
* canonical Decision Index records (``mneme.decision_index``);
* runtime Layer 1 memory.

Storage is simple, local and OSS-compatible (ADR-027 section 12): no
database, no ORM, no hosted persistence, no organization/repository
aggregation. Two implementations with identical semantics are provided:
an in-memory store for tests, and a deterministic JSON file store using
the repository's existing file-backed conventions.

Semantics:

* ``add_if_new`` is the only producer-facing write operation. It appends a
  proposal when its id is unknown and returns the existing record unchanged
  otherwise (append-preserving history; no silent overwrite, no update, no
  delete).
* ``get`` and ``list_proposals`` are read-only.
* ``transition_if_proposed`` (D2C1) is the single Core persistence primitive
  for the Mneme authority action (ADR-027 "Accepted-proposal authority
  path"). It is deliberately NOT a producer capability: no producer path
  reaches it. It transitions ``proposed`` to exactly one target status —
  ``accepted`` (which requires a non-empty ``accepted_decision_id``) or
  ``rejected`` (which must not carry one) — never rewrites candidate
  content, producer key, fingerprint, or ``proposed_at``, never touches a
  record already at the target status (returned unchanged, ``transitioned=
  False``), and fails closed on any other terminal state, on unknown ids,
  and on invalid arguments. Proposal candidate content is immutable: the
  transition replaces only the status/link fields.
* Records keep insertion order; reload reproduces ids, history, and order
  deterministically.
"""
from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Protocol

from mneme.decision_proposal import (
    PROPOSAL_STATUS_ACCEPTED,
    PROPOSAL_STATUS_PROPOSED,
    PROPOSAL_STATUS_REJECTED,
    DecisionProposal,
    proposal_from_dict,
    proposal_to_dict,
)

SCHEMA = "mneme.decision-proposals/v1"


def _validate_transition_args(
    target_status: str, accepted_decision_id: str | None
) -> None:
    """Fail closed on invalid authority-transition arguments."""
    if target_status not in (PROPOSAL_STATUS_ACCEPTED, PROPOSAL_STATUS_REJECTED):
        raise ValueError(
            f"target_status {target_status!r} is not a legal authority "
            "transition target (accepted/rejected)"
        )
    if target_status == PROPOSAL_STATUS_ACCEPTED:
        if not (isinstance(accepted_decision_id, str) and accepted_decision_id):
            raise ValueError(
                "transitioning to accepted requires a non-empty "
                "accepted_decision_id"
            )
    elif accepted_decision_id is not None:
        raise ValueError(
            "transitioning to rejected must not carry an accepted_decision_id"
        )


class DecisionProposalStore(Protocol):
    """Minimal persistence contract required by D2A + D2C1."""

    def add_if_new(
        self, proposal: DecisionProposal
    ) -> tuple[DecisionProposal, bool]:
        """Append ``proposal`` if its id is unknown.

        Returns ``(stored_proposal, created)``. When a proposal with the
        same id already exists, the existing record is returned unchanged
        with ``created=False`` — never replaced, never mutated.
        """
        ...

    def get(self, proposal_id: str) -> DecisionProposal | None:
        """Return the proposal with this id, or ``None``."""
        ...

    def list_proposals(self) -> tuple[DecisionProposal, ...]:
        """Return all proposals in insertion order."""
        ...

    def transition_if_proposed(
        self,
        proposal_id: str,
        target_status: str,
        accepted_decision_id: str | None = None,
    ) -> tuple[DecisionProposal, bool]:
        """Core authority primitive (D2C1, ADR-027 authority path).

        Transition ``proposal_id`` from ``proposed`` to ``target_status``
        (``accepted`` requires a non-empty ``accepted_decision_id``;
        ``rejected`` must not carry one). Returns
        ``(proposal_after_call, transitioned)``:

        * ``proposed``  -> target status, persisted atomically,
          ``transitioned=True``; candidate content, ``producer_key``,
          ``content_fingerprint``, and ``proposed_at`` are unchanged;
        * already at ``target_status`` -> existing record returned
          unchanged with ``transitioned=False`` (idempotent retry);
        * any other status (accepted→rejected, rejected→accepted), an
          unknown id, or an invalid argument -> ``ValueError`` (fail
          closed; callers map to their own authority error types).
        """
        ...


class InMemoryDecisionProposalStore:
    """In-memory implementation; semantics identical to the file store."""

    def __init__(self) -> None:
        self._by_id: dict[str, DecisionProposal] = {}
        self._order: list[str] = []

    def add_if_new(
        self, proposal: DecisionProposal
    ) -> tuple[DecisionProposal, bool]:
        existing = self._by_id.get(proposal.proposal_id)
        if existing is not None:
            return existing, False
        self._by_id[proposal.proposal_id] = proposal
        self._order.append(proposal.proposal_id)
        return proposal, True

    def get(self, proposal_id: str) -> DecisionProposal | None:
        return self._by_id.get(proposal_id)

    def list_proposals(self) -> tuple[DecisionProposal, ...]:
        return tuple(self._by_id[pid] for pid in self._order)

    def transition_if_proposed(
        self,
        proposal_id: str,
        target_status: str,
        accepted_decision_id: str | None = None,
    ) -> tuple[DecisionProposal, bool]:
        _validate_transition_args(target_status, accepted_decision_id)
        existing = self._by_id.get(proposal_id)
        if existing is None:
            raise ValueError(f"proposal {proposal_id!r} not found")
        if existing.status == target_status:
            return existing, False
        if existing.status != PROPOSAL_STATUS_PROPOSED:
            raise ValueError(
                f"proposal {proposal_id!r} has status {existing.status!r}; "
                f"only a proposed proposal may transition to "
                f"{target_status!r}"
            )
        transitioned = dataclasses.replace(
            existing, status=target_status, accepted_decision_id=accepted_decision_id
        )
        self._by_id[proposal_id] = transitioned
        return transitioned, True


class JsonFileDecisionProposalStore:
    """Deterministic JSON file store.

    File format::

        {"schema": "mneme.decision-proposals/v1", "proposals": [...]}

    The file is loaded once at construction and rewritten atomically
    (temporary file + ``os.replace``) on each successful append. Existing
    entries are never rewritten: an idempotent ``add_if_new`` performs no
    write at all. Reload reproduces proposal ids, history, and insertion
    order deterministically.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._by_id: dict[str, DecisionProposal] = {}
        self._order: list[str] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with open(self.path, encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict) or data.get("schema") != SCHEMA:
            raise ValueError(
                f"{self.path} is not a {SCHEMA} decision-proposals document"
            )
        entries = data.get("proposals")
        if not isinstance(entries, list):
            raise ValueError(f"{self.path} proposals must be a list")
        for entry in entries:
            proposal = proposal_from_dict(entry)
            if proposal.proposal_id in self._by_id:
                raise ValueError(
                    f"{self.path} contains duplicate proposal id "
                    f"{proposal.proposal_id!r}"
                )
            self._by_id[proposal.proposal_id] = proposal
            self._order.append(proposal.proposal_id)

    def _persist(self) -> None:
        document = {
            "schema": SCHEMA,
            "proposals": [
                proposal_to_dict(self._by_id[pid]) for pid in self._order
            ],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(document, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp_path, self.path)

    def add_if_new(
        self, proposal: DecisionProposal
    ) -> tuple[DecisionProposal, bool]:
        existing = self._by_id.get(proposal.proposal_id)
        if existing is not None:
            return existing, False
        self._by_id[proposal.proposal_id] = proposal
        self._order.append(proposal.proposal_id)
        self._persist()
        return proposal, True

    def transition_if_proposed(
        self,
        proposal_id: str,
        target_status: str,
        accepted_decision_id: str | None = None,
    ) -> tuple[DecisionProposal, bool]:
        """Authority transition (D2C1).

        Writes only the one record's status/link fields: the document is
        rebuilt with every other record serialized exactly as stored
        (identical content, identical order) and replaced atomically via
        the same temp-file + ``os.replace`` convention as ``_persist``.
        After the write the file is reloaded and the persisted entry is
        verified to carry the transitioned state; the in-memory state is
        updated only after that verification succeeds, so a failed write
        or verification leaves the store's memory of the record unchanged.
        """
        _validate_transition_args(target_status, accepted_decision_id)
        existing = self._by_id.get(proposal_id)
        if existing is None:
            raise ValueError(f"proposal {proposal_id!r} not found")
        if existing.status == target_status:
            return existing, False
        if existing.status != PROPOSAL_STATUS_PROPOSED:
            raise ValueError(
                f"proposal {proposal_id!r} has status {existing.status!r}; "
                f"only a proposed proposal may transition to "
                f"{target_status!r}"
            )
        transitioned = dataclasses.replace(
            existing, status=target_status, accepted_decision_id=accepted_decision_id
        )
        document = {
            "schema": SCHEMA,
            "proposals": [
                proposal_to_dict(
                    transitioned if pid == proposal_id else self._by_id[pid]
                )
                for pid in self._order
            ],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(document, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp_path, self.path)
        # Reload the persisted document and verify the transition survived.
        with open(self.path, encoding="utf-8") as handle:
            persisted = json.load(handle)
        persisted_entries = persisted.get("proposals")
        if not isinstance(persisted_entries, list):
            raise ValueError(
                f"{self.path} does not contain a proposals list after "
                f"transitioning {proposal_id!r}"
            )
        persisted_entry = next(
            (
                entry
                for entry in persisted_entries
                if isinstance(entry, dict)
                and entry.get("proposal_id") == proposal_id
            ),
            None,
        )
        if (
            persisted_entry is None
            or persisted_entry.get("status") != target_status
            or persisted_entry.get("accepted_decision_id")
            != accepted_decision_id
        ):
            raise ValueError(
                f"{self.path} does not carry the {proposal_id!r} transition "
                f"to {target_status!r} after write; failing closed"
            )
        self._by_id[proposal_id] = transitioned
        return transitioned, True

    def get(self, proposal_id: str) -> DecisionProposal | None:
        return self._by_id.get(proposal_id)

    def list_proposals(self) -> tuple[DecisionProposal, ...]:
        return tuple(self._by_id[pid] for pid in self._order)


__all__ = [
    "SCHEMA",
    "DecisionProposalStore",
    "InMemoryDecisionProposalStore",
    "JsonFileDecisionProposalStore",
]
