"""Canonical project-memory fixtures for tests (ADR-030 §1).

Production code reaches canonical memory only through
``mneme decision-index migrate``; canonical writers refuse section-less
memory. Tests that need a canonical starting point build it here, in one
place, from the same migration transformation the command uses.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from mneme.decision_index_persistence import (
    _migrate_memory_document,
    apply_memory_migration,
    plan_memory_migration,
)


def canonical_document(document: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical form of an in-memory pre-D1 document."""
    return _migrate_memory_document(document)


def migrate_memory_fixture(path: str | Path) -> bool:
    """Migrate a fixture file exactly as the explicit migration command does."""
    return apply_memory_migration(plan_memory_migration(path))
