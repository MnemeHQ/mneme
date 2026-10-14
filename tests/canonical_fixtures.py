"""Canonical project-memory fixtures for tests (ADR-030 §1).

Production code reaches canonical memory only through
``mneme decision-index migrate``; canonical writers refuse section-less
memory. Tests that need a canonical starting point build it here, in one
place, from the same migration transformation the command uses.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

from mneme.decision_index_persistence import (
    DECISION_INDEX_SCHEMA,
    _migrate_memory_document,
    apply_memory_migration,
    plan_memory_migration,
)


def canonical_document(document: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical form of an in-memory pre-D1 document.

    This is the current canonical schema (``mneme.decision-index/v2`` since
    DG1B1), matching what ``mneme decision-index migrate`` writes.
    """
    return _migrate_memory_document(document)


def v1_document(document: dict[str, Any]) -> dict[str, Any]:
    """Return the schema-v1 view of a canonical document for characterization.

    The shipped v1 loader rejects any non-v1 schema and ignores unknown keys.
    Tests that characterize that loader build their fixture here: the current
    canonical document uses schema v2 (DG1B1), so this drops the v2-only
    ``semantic_features`` declaration and restores the v1 schema tag. Test-only
    view; never production memory.
    """
    document = copy.deepcopy(document)
    section = document["decision_index"]
    section["schema"] = DECISION_INDEX_SCHEMA
    section.pop("semantic_features", None)
    return document


def without_version_identity(items: Iterable[Any]) -> list[Any]:
    """Behavioral view of runtime objects for parity across load paths.

    Canonical version identity (ADR-031 §10) exists only on decisions
    projected from the persisted Decision Index, so it legitimately differs
    between, for example, pre- and post-migration loads. Version identity
    takes part in equality (different versions are different evidence), so
    behavioral parity must exclude it explicitly. ``rule_id`` is kept: it is
    one algorithm on every load path.
    """
    out: list[Any] = []
    for item in items:
        if hasattr(item, "version_id"):
            item = replace(item, version_id="")
        elif getattr(item, "decision_version_id", None):
            item = replace(item, decision_version_id="")
        out.append(item)
    return out


def migrate_memory_fixture(path: str | Path) -> bool:
    """Migrate a fixture file exactly as the explicit migration command does."""
    return apply_memory_migration(plan_memory_migration(path))
