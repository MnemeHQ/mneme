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

* ``add_if_new`` is the only write operation. It appends a proposal when
  its id is unknown and returns the existing record unchanged otherwise
  (append-preserving history; no silent overwrite, no update, no delete).
* ``get`` and ``list_proposals`` are read-only. There are deliberately no
  authority mutation methods (accept/reject/activate/supersede) — those
  belong to the separate Mneme authority action (D2C), not to a producer
  convenience API (ADR-027 section 7).
* Records keep insertion order; reload reproduces ids, history, and order
  deterministically.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol

from mneme.decision_proposal import (
    DecisionProposal,
    proposal_from_dict,
    proposal_to_dict,
)

SCHEMA = "mneme.decision-proposals/v1"


class DecisionProposalStore(Protocol):
    """Minimal persistence contract required by D2A."""

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
