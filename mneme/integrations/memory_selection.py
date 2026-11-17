"""Shared memory selection for every implicit-discovery consumer (T-08 D5+P2).

P2-first interim phase (D5+P2 charter Amendment A2, §5.2; authorized by the
P2-first ``[layer1-freeze]`` amendment). The walk is today's: the nearest
``.mneme/project_memory.json`` at or above the start, with no Git-marker
check. On top of it, the D6/Q2 P2 precedence rule applies: a memory the walk
finds always governs, and a ``MNEME_MEMORY`` override only fills an absence.

Only rows 1, 2, 6, 7 and 8 of charter §3.3 can occur. Rows 3-5 need the D5
boundary, which is Phase 2; their reason codes are reserved and never emitted.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

MEMORY_RELATIVE_PATH = Path(".mneme") / "project_memory.json"
OVERRIDE_ENV = "MNEME_MEMORY"

DISCOVERED = "DISCOVERED"
OVERRIDE_IGNORED = "OVERRIDE_IGNORED"
OVERRIDE_FILLS_ABSENCE = "OVERRIDE_FILLS_ABSENCE"
OVERRIDE_MISSING = "OVERRIDE_MISSING"
NO_MEMORY_ON_PATH = "NO_MEMORY_ON_PATH"

WALK_UNBOUNDED = "unbounded"

# Charter §5.2.4: only these rows produce a host notice, and only on H1 paths.
_NOTICE_REASONS = frozenset({OVERRIDE_IGNORED, OVERRIDE_MISSING})


@dataclass(frozen=True)
class MemorySelection:
    """Which memory governs, and why (charter §3.1, §5.2.2).

    ``boundary`` and ``shadowed`` are never populated in P2-first; ``walk``
    records that, so no consumer can read an absent boundary as "no Git
    repository" (charter A2-5).
    """

    path: Optional[Path]
    source: str
    reason: Optional[str]
    walk: Optional[str]
    boundary: Optional[Path] = None
    shadowed: Optional[Path] = None


def _walk(start: Path) -> Optional[Path]:
    """Today's walk: nearest memory at or above ``start``, no marker check."""
    cur = Path(start).resolve()
    while True:
        candidate = cur / MEMORY_RELATIVE_PATH
        if candidate.is_file():
            return candidate
        if cur.parent == cur:
            return None
        cur = cur.parent


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except (OSError, RuntimeError):
        return False


def resolve_memory(start: Path) -> MemorySelection:
    """Select the governing memory for ``start`` under P2-first precedence.

    The override is tested with ``is_file()`` only and is never opened: an
    unreadable or malformed override that is selected takes the existing
    load-failure path (charter A2-3). The returned path keeps today's form:
    ``Path(MNEME_MEMORY)`` as given when the override is the selection, the
    walk's path otherwise.
    """
    walked = _walk(start)
    raw = os.environ.get(OVERRIDE_ENV)
    override = Path(raw) if raw else None

    if walked is not None:
        if override is None:
            return MemorySelection(walked, "discovered", DISCOVERED, WALK_UNBOUNDED)
        if override.is_file() and _same_file(override, walked):
            return MemorySelection(override, "discovered", DISCOVERED, WALK_UNBOUNDED)
        return MemorySelection(walked, "discovered", OVERRIDE_IGNORED, WALK_UNBOUNDED)

    if override is None:
        return MemorySelection(None, "none", NO_MEMORY_ON_PATH, WALK_UNBOUNDED)
    if override.is_file():
        return MemorySelection(override, "override", OVERRIDE_FILLS_ABSENCE, WALK_UNBOUNDED)
    return MemorySelection(None, "none", OVERRIDE_MISSING, WALK_UNBOUNDED)


def explicit_selection(memory: Path) -> MemorySelection:
    """Record an embedder's explicit memory path (Q2 O3); not a resolver row."""
    p = Path(memory)
    return MemorySelection(p if p.is_file() else None, "explicit", None, None)


def selection_notice(selection: MemorySelection) -> Optional[str]:
    """The host notice for rows 2 and 7, or ``None`` (charter §5.2.4).

    ASCII only. Emitting it is the caller's job, and only on the H1 paths in
    their probed shapes.
    """
    if selection.reason not in _NOTICE_REASONS:
        return None
    raw = os.environ.get(OVERRIDE_ENV, "")
    if selection.reason == OVERRIDE_IGNORED:
        return (
            "mneme: MNEME_MEMORY override ignored (OVERRIDE_IGNORED): the "
            f"repository memory {selection.path} governs here; the override "
            f"{raw} was not applied."
        )
    return (
        "mneme: no memory selected (OVERRIDE_MISSING): MNEME_MEMORY names "
        f"{raw}, which is not a file, and no repository memory was found; "
        "no Mneme memory governs this action."
    )


__all__ = [
    "MemorySelection",
    "resolve_memory",
    "explicit_selection",
    "selection_notice",
    "DISCOVERED",
    "OVERRIDE_IGNORED",
    "OVERRIDE_FILLS_ABSENCE",
    "OVERRIDE_MISSING",
    "NO_MEMORY_ON_PATH",
    "WALK_UNBOUNDED",
]
