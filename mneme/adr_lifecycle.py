"""
adr_lifecycle.py — Read-only lifecycle reconciliation analyzer.

Compares the on-disk ADR corpus against the imported ledger and the
precedence-resolved active set, surfacing mismatches as warn-only findings.

All findings use the existing FreshnessIssue type from adr_freshness to avoid
introducing a new abstraction. New codes are module-level constants below.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mneme.adr_freshness import FreshnessIssue, check_freshness
from mneme.adr_import import project_decision_graph
from mneme.adr_parser import parse_adr_file, parse_adr_directory
from mneme.adr_compiler import resolve_precedence, ADRPrecedenceError, PRIORITY_RANK
from mneme.adr_schema import ADRParseError

# ── Finding codes (extend FreshnessIssue.code vocabulary) ─────────────────────

UNEXPLAINED_NUMBERING_GAP = "UNEXPLAINED_NUMBERING_GAP"
DANGLING_SUPERSEDES = "DANGLING_SUPERSEDES"
ORPHAN_SUPERSEDED = "ORPHAN_SUPERSEDED"
ACTIVE_CONTRADICTION = "ACTIVE_CONTRADICTION"
SILENT_PRECEDENCE_ELIMINATION = "SILENT_PRECEDENCE_ELIMINATION"
LEDGER_STATUS_MISMATCH = "LEDGER_STATUS_MISMATCH"

# Deterministic output order
_CODE_ORDER = [
    UNEXPLAINED_NUMBERING_GAP,
    DANGLING_SUPERSEDES,
    ORPHAN_SUPERSEDED,
    ACTIVE_CONTRADICTION,
    SILENT_PRECEDENCE_ELIMINATION,
    LEDGER_STATUS_MISMATCH,
]

# ── Internal helpers ──────────────────────────────────────────────────────────

_ADR_ID_PATTERN = re.compile(r"^ADR-(\d+)$")
_SOURCE_TYPE_ADR = "adr"


def _load_raw_decisions(memory_path: Path) -> list[dict]:
    """Read decisions[] from memory file as raw dicts (tolerant, warn-only)."""
    try:
        data = json.loads(memory_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    raw = data.get("decisions") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    return [d for d in raw if isinstance(d, dict)]


def _compute_source_hash(adr_path: Path) -> str:
    return hashlib.sha256(adr_path.read_bytes()).hexdigest()


def _scan_adr_directory_tolerant(adr_dir: Path):
    """Parse every ADR-*.md, separating successes from failures.

    Returns (parsed_list, parse_errors) where parse_errors is a list of
    (path, message) tuples for files matching the glob that failed to parse.
    """
    parsed: list = []
    parse_errors: list[tuple[Path, str]] = []
    for path in sorted(adr_dir.glob("ADR-*.md")):
        try:
            parsed.append(parse_adr_file(path))
        except ADRParseError as exc:
            parse_errors.append((path, str(exc)))
        except Exception as exc:
            parse_errors.append((path, f"unexpected parse error: {exc}"))
    return parsed, parse_errors


def _extract_numbering_gaps(parsed: list) -> list[int]:
    """Return sorted list of missing integer IDs between min and max present."""
    nums: list[int] = []
    for a in parsed:
        m = _ADR_ID_PATTERN.match(a.id)
        if m:
            nums.append(int(m.group(1)))
    if not nums:
        return []
    present = set(nums)
    full = set(range(min(nums), max(nums) + 1))
    return sorted(full - present)


def _has_ledger_tombstone_for_gap(gap_id: str, raw_decisions: list[dict]) -> bool:
    """Return True if ledger has a decision for the missing ADR (tombstone)."""
    for dec in raw_decisions:
        if dec.get("id") == gap_id:
            return True
    return False


# ── Public API ────────────────────────────────────────────────────────────────

def analyze_lifecycle(corpus_dir: str | Path, memory_path: str | Path) -> list[FreshnessIssue]:
    """
    Read-only lifecycle reconciliation.

    Args:
        corpus_dir: Directory containing ADR-*.md files.
        memory_path: Path to project_memory.json.

    Returns:
        List of FreshnessIssue records. May include freshness issues if
        check_freshness is called first; here we return only lifecycle-specific
        codes. Order is deterministic by _CODE_ORDER then by adr_id.
    """
    corpus_dir = Path(corpus_dir)
    memory_path = Path(memory_path)

    if not corpus_dir.is_dir():
        return []
    if not memory_path.is_file():
        return []

    parsed, parse_errors = _scan_adr_directory_tolerant(corpus_dir)
    nodes = project_decision_graph(parsed)
    parsed_ids = {a.id for a in parsed}

    findings: list[FreshnessIssue] = []

    # Parse errors as unparseable
    for path, message in parse_errors:
        findings.append(FreshnessIssue(
            code="ADR_UNPARSEABLE",
            adr_id=path.stem,
            path=str(path),
            message=message,
        ))

    # UNEXPLAINED_NUMBERING_GAP: ordinary missing numbers in sequence are common
    # and not treated as defects. Only suppressed when ledger has a record, and
    # ordinary gaps without a ledger produce no warning.
    # (Preserved in code vocabulary for callers that inspect index continuity).

    # DANGLING_SUPERSEDES (forward refs to unknown ids)
    for a in parsed:
        for ref in a.supersedes:
            if ref not in parsed_ids:
                findings.append(FreshnessIssue(
                    code=DANGLING_SUPERSEDES,
                    adr_id=a.id,
                    path=str(a.source_path),
                    message=(
                        f"{a.id} supersedes unknown ADR {ref!r} — the target does "
                        f"not exist in the corpus. Fix the reference or add the "
                        f"missing ADR."
                    ),
                ))

    # ORPHAN_SUPERSEDED (declared/derived superseded with no successor pointer)
    for n in nodes:
        if n.status == "superseded" and n.superseded_by is None:
            adr = next((a for a in parsed if a.id == n.id), None)
            src = str(adr.source_path) if adr else "unknown"
            findings.append(FreshnessIssue(
                code=ORPHAN_SUPERSEDED,
                adr_id=n.id,
                path=src,
                message=(
                    f"{n.id} is marked superseded (declared or via link) but has "
                    f"no recorded successor (superseded_by is None). Add a "
                    f"supersedes link from the replacing ADR or update status."
                ),
            ))

    # ACTIVE_CONTRADICTION + SILENT_PRECEDENCE_ELIMINATION
    # resolve_precedence raises ADRPrecedenceError on the first ambiguous scope.
    # Iterate to catch multiple scopes: on each raise, record the tie,
    # remove the tied ids, and retry.
    # Filter to valid accepted ADRs with known priority before calling.
    valid_priorities = set(PRIORITY_RANK.keys())
    remaining = [
        a for a in parsed
        if a.status == "accepted"
        and a.priority in valid_priorities
        and a.id
        and a.date
        and a.scope != "None"
    ]
    tied_ids: set[str] = set()
    while True:
        try:
            winners = resolve_precedence(remaining)
            break
        except ADRPrecedenceError as exc:
            for tid in exc.ids:
                tied_ids.add(tid)
            # Record contradiction finding
            findings.append(FreshnessIssue(
                code=ACTIVE_CONTRADICTION,
                adr_id=",".join(sorted(exc.ids)),
                path="",
                message=(
                    f"Active-active contradiction at scope {exc.scope!r} between: "
                    f"{', '.join(sorted(exc.ids))}. These accepted ADRs share the "
                    f"same scope, priority, and date — precedence cannot break the "
                    f"tie. Resolve by editing status/priority/date or adding an "
                    f"explicit supersedes link."
                ),
            ))
            # Remove tied ids from consideration for silent-elimination scan
            remaining = [a for a in remaining if a.id not in tied_ids]

    winner_ids = {w.id for w in winners}

    # SILENT_PRECEDENCE_ELIMINATION: narrow — report ONLY when:
    # 1. both decisions claim an active status (accepted + unreferenced);
    # 2. they overlap in scope (same scope);
    # 3. no explicit supersession relationship exists; and
    # 4. one disappears solely because precedence selects the other.
    accepted_unreferenced = {
        n.id for n in nodes
        if n.status == "active" and n.superseded_by is None
    }
    silent_losers = accepted_unreferenced - winner_ids - tied_ids
    for loser_id in sorted(silent_losers):
        adr = next((a for a in parsed if a.id == loser_id), None)
        src = str(adr.source_path) if adr else "unknown"
        scope = adr.scope if adr else "unknown"
        winner = next((w for w in winners if w.scope == scope), None)
        winner_id = winner.id if winner else "unknown"
        findings.append(FreshnessIssue(
            code=SILENT_PRECEDENCE_ELIMINATION,
            adr_id=loser_id,
            path=src,
            message=(
                f"{loser_id} was silently eliminated by precedence in scope "
                f"{scope!r} (winner: {winner_id}). Both claim active status with "
                f"no explicit supersedes link. Add an explicit supersedes link or "
                f"retire one decision."
            ),
        ))

    # LEDGER_STATUS_MISMATCH: ledger entries whose source ADR is non-active
    raw_decisions = _load_raw_decisions(memory_path)
    for dec in raw_decisions:
        source = dec.get("source")
        if not isinstance(source, dict) or source.get("type") != _SOURCE_TYPE_ADR:
            continue
        rel = source.get("path")
        if not rel:
            continue
        adr_id = dec.get("id")
        if not adr_id:
            continue
        # Resolve the source path relative to memory file parent
        resolved = (memory_path.parent / rel).resolve()
        if not resolved.is_file():
            # Missing file handled by freshness.ADR_MISSING; skip to avoid dup
            continue
        # Find the node in our graph
        node = next((n for n in nodes if n.id == adr_id), None)
        if node is None:
            # ADR not in current corpus (deleted or renamed); freshness owns this
            continue
        if node.status != "active":
            # The ledger still holds this as a current decision but the ADR is
            # no longer active. This decision remains retrievable.
            findings.append(FreshnessIssue(
                code=LEDGER_STATUS_MISMATCH,
                adr_id=adr_id,
                path=str(rel),
                message=(
                    f"Ledger decision {adr_id} references an ADR whose current "
                    f"derived status is {node.status!r}, not active. The ledger "
                    f"entry remains retrievable and enforceable. Re-import after "
                    f"updating the ADR or retire the decision explicitly."
                ),
            ))

    # Deterministic ordering
    order_map = {code: i for i, code in enumerate(_CODE_ORDER)}
    findings.sort(key=lambda f: (order_map.get(f.code, 99), f.adr_id))
    return findings


__all__ = [
    "analyze_lifecycle",
    "UNEXPLAINED_NUMBERING_GAP",
    "DANGLING_SUPERSEDES",
    "ORPHAN_SUPERSEDED",
    "ACTIVE_CONTRADICTION",
    "SILENT_PRECEDENCE_ELIMINATION",
    "LEDGER_STATUS_MISMATCH",
]