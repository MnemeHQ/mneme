"""
adr_lifecycle.py — Read-only lifecycle reconciliation analyzer.

Compares the on-disk ADR corpus against the imported ledger and the
precedence-resolved active set, surfacing mismatches as warn-only findings.

All findings use the existing FreshnessIssue type from adr_freshness to avoid
introducing a new abstraction. New codes are module-level constants below.
"""
from __future__ import annotations

import json
from pathlib import Path

from mneme.adr_compiler import PRIORITY_RANK, ADRPrecedenceError, _pick_within_scope
from mneme.adr_freshness import FreshnessIssue, _id_from_filename
from mneme.adr_import import project_decision_graph
from mneme.adr_parser import parse_adr_file
from mneme.adr_schema import ADR, ADRParseError

# ── Finding codes (extend FreshnessIssue.code vocabulary) ─────────────────────

DANGLING_SUPERSEDES = "DANGLING_SUPERSEDES"
ORPHAN_SUPERSEDED = "ORPHAN_SUPERSEDED"
ACTIVE_CONTRADICTION = "ACTIVE_CONTRADICTION"
SILENT_PRECEDENCE_ELIMINATION = "SILENT_PRECEDENCE_ELIMINATION"
LEDGER_STATUS_MISMATCH = "LEDGER_STATUS_MISMATCH"

# Deterministic output order
_CODE_ORDER = [
    DANGLING_SUPERSEDES,
    ORPHAN_SUPERSEDED,
    ACTIVE_CONTRADICTION,
    SILENT_PRECEDENCE_ELIMINATION,
    LEDGER_STATUS_MISMATCH,
]

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


def _scan_adr_directory_tolerant(adr_dir: Path) -> tuple[list[ADR], list[tuple[Path, str]]]:
    """Parse every ADR-*.md, separating successes from failures.

    Returns (parsed_list, parse_errors) where parse_errors is a list of
    (path, message) tuples for files matching the glob that failed to parse.
    """
    parsed: list[ADR] = []
    parse_errors: list[tuple[Path, str]] = []
    for path in sorted(adr_dir.glob("ADR-*.md")):
        try:
            parsed.append(parse_adr_file(path))
        except ADRParseError as exc:
            parse_errors.append((path, str(exc)))
        except Exception as exc:
            parse_errors.append((path, f"unexpected parse error: {exc}"))
    return parsed, parse_errors


# ── Public API ────────────────────────────────────────────────────────────────

def analyze_lifecycle(corpus_dir: str | Path, memory_path: str | Path) -> list[FreshnessIssue]:
    """
    Read-only lifecycle reconciliation.

    Args:
        corpus_dir: Directory containing ADR-*.md files.
        memory_path: Path to project_memory.json.

    Returns:
        List of FreshnessIssue records.
        Order is deterministic by _CODE_ORDER then by adr_id.
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
            adr_id=_id_from_filename(path),
            path=str(path),
            message=message,
        ))

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

    # Independent per-scope resolution over graph-derived active ADRs:
    # 1. Build the active set from project_decision_graph.
    # 2. Group active ADRs by scope.
    # 3. Resolve each scope separately.
    # 4. Emit ACTIVE_CONTRADICTION for a tied group.
    # 5. Emit SILENT_PRECEDENCE_ELIMINATION only when that same group has a real winner and active losers.
    active_ids = {n.id for n in nodes if n.status == "active"}
    valid_priorities = set(PRIORITY_RANK.keys())
    active_adrs = [
        a for a in parsed
        if a.id in active_ids
        and a.priority in valid_priorities
        and a.date
        and a.scope != "None"
    ]

    by_scope: dict[str, list[ADR]] = {}
    for a in active_adrs:
        by_scope.setdefault(a.scope, []).append(a)

    for scope, group in sorted(by_scope.items()):
        if len(group) < 2:
            continue
        try:
            winner = _pick_within_scope(scope, group)
            for loser in sorted(group, key=lambda a: a.id):
                if loser.id != winner.id:
                    findings.append(FreshnessIssue(
                        code=SILENT_PRECEDENCE_ELIMINATION,
                        adr_id=loser.id,
                        path=str(loser.source_path),
                        message=(
                            f"{loser.id} was silently eliminated by precedence in scope "
                            f"{scope!r} (winner: {winner.id}). Both claim active status with "
                            f"no explicit supersedes link. Add an explicit supersedes link or "
                            f"retire one decision."
                        ),
                    ))
        except ADRPrecedenceError as exc:
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
    "DANGLING_SUPERSEDES",
    "ORPHAN_SUPERSEDED",
    "ACTIVE_CONTRADICTION",
    "SILENT_PRECEDENCE_ELIMINATION",
    "LEDGER_STATUS_MISMATCH",
]
