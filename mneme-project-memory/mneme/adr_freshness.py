"""
adr_freshness.py -- Warn-only ADR freshness / change detection.

Compares the active ADR corpus on disk against the imported decision
provenance in a Mneme memory file and surfaces three kinds of drift:

    ADR_UNIMPORTED  An active ADR file exists in the ADR directory but
                    no decision in the memory file carries its id. The
                    ADR has not been imported.
    ADR_CHANGED     A decision references an ADR file whose current
                    SHA-256 differs from the hash captured at import.
                    The source has been edited since import.
    ADR_MISSING     A decision references an ADR file that no longer
                    exists on disk. The source has been deleted or
                    renamed without re-importing.

The checker is intentionally warn-only: it returns a list of issues that
the caller (the ``mneme check`` CLI) is expected to print but never to
escalate into a non-zero exit. It does NOT mutate the memory file, does
NOT re-import, and does NOT change the runtime retrieval surface.

Provenance shape
----------------
Each imported decision JSON entry may carry an optional ``source`` block::

    {
      "id": "ADR-123",
      "decision": "...",
      ...,
      "source": {
        "type":   "adr",
        "path":   "<POSIX path relative to memory_path.parent>",
        "sha256": "<hex digest of the ADR file's UTF-8 bytes>"
      }
    }

Memory files written before this provenance block was introduced remain
fully supported: an imported decision whose id matches an active ADR but
which lacks ``source`` is treated as imported and produces no freshness
diagnostics (silently passes -- there is no hash to compare).

The checker reads the memory file raw (json.load) rather than via
MemoryStore so the ``source`` block survives the round-trip; the
Decision dataclass intentionally does not carry source provenance.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mneme.adr_import import project_decision_graph
from mneme.adr_parser import parse_adr_directory


ADR_UNIMPORTED = "ADR_UNIMPORTED"
ADR_CHANGED = "ADR_CHANGED"
ADR_MISSING = "ADR_MISSING"

_SOURCE_TYPE_ADR = "adr"


@dataclass(frozen=True)
class FreshnessIssue:
    """A single ADR freshness diagnostic.

    Attributes:
        code:    One of ADR_UNIMPORTED, ADR_CHANGED, ADR_MISSING.
        adr_id:  The ADR id this issue refers to (e.g. "ADR-007"), or
                 the decision id when the ADR file is missing.
        path:    Path string the user should look at. Stored as written
                 in the memory file (POSIX, relative to the memory
                 file's parent) for MISSING / CHANGED, or as the
                 ADR file's source path for UNIMPORTED.
        message: Single-line human-readable explanation.
    """

    code: str
    adr_id: str
    path: str
    message: str


def compute_source_hash(adr_path: str | Path) -> str:
    """Return the SHA-256 hex digest of an ADR file's UTF-8 bytes."""
    data = Path(adr_path).read_bytes()
    return hashlib.sha256(data).hexdigest()


def relative_source_path(adr_path: str | Path, memory_path: str | Path) -> str:
    """Compute the POSIX path stored in ``source.path`` for an ADR.

    The path is relative to the memory file's parent directory so the
    provenance survives moves of the repo as a whole. ``os.path.relpath``
    handles the ``..`` traversal that ``Path.relative_to`` refuses.
    """
    import os
    memory_parent = Path(memory_path).resolve().parent
    target = Path(adr_path).resolve()
    return Path(os.path.relpath(str(target), str(memory_parent))).as_posix()


def check_freshness(
    memory_path: str | Path,
    adr_dir: str | Path,
) -> list[FreshnessIssue]:
    """Compare on-disk ADRs against imported provenance in a memory file.

    Args:
        memory_path: Path to the ``project_memory.json`` file.
        adr_dir:     Path to the directory containing ADR markdown files.

    Returns:
        A list of ``FreshnessIssue`` records, possibly empty. Order is
        deterministic: UNIMPORTED first (sorted by ADR id), then CHANGED,
        then MISSING.

        If ``adr_dir`` does not exist, returns an empty list: the
        checker cannot determine what is unimported without a corpus
        to compare against.
    """
    memory_path = Path(memory_path)
    adr_dir = Path(adr_dir)

    if not adr_dir.is_dir():
        return []
    if not memory_path.is_file():
        return []

    raw_decisions = _load_raw_decisions(memory_path)
    decisions_by_id: dict[str, dict] = {d["id"]: d for d in raw_decisions if "id" in d}

    active_adr_ids, adrs_by_id = _active_adrs(adr_dir)

    unimported: list[FreshnessIssue] = []
    changed: list[FreshnessIssue] = []
    missing: list[FreshnessIssue] = []

    # ADR_UNIMPORTED + ADR_CHANGED: scan the on-disk active corpus.
    for adr_id in sorted(active_adr_ids):
        adr = adrs_by_id[adr_id]
        decision = decisions_by_id.get(adr_id)
        if decision is None:
            unimported.append(FreshnessIssue(
                code=ADR_UNIMPORTED,
                adr_id=adr_id,
                path=str(adr.source_path),
                message=(
                    f"{adr_id} exists in {adr.source_path} but no matching "
                    f"decision is present in {memory_path.name}. Run "
                    f"`mneme adr import` to import it."
                ),
            ))
            continue

        source = _coerce_source(decision.get("source"))
        if source is None:
            # Legacy memory file -- imported by id, no hash to compare.
            continue
        if source.get("sha256") is None:
            continue

        stored_hash = source["sha256"]
        current_hash = compute_source_hash(adr.source_path)
        if stored_hash != current_hash:
            changed.append(FreshnessIssue(
                code=ADR_CHANGED,
                adr_id=adr_id,
                path=str(source.get("path", adr.source_path)),
                message=(
                    f"{adr_id} source file changed since import "
                    f"(hash mismatch). Re-run `mneme adr import` to "
                    f"refresh the imported decision."
                ),
            ))

    # ADR_MISSING: scan decisions for source paths that have vanished.
    memory_parent = memory_path.resolve().parent
    for decision in raw_decisions:
        source = _coerce_source(decision.get("source"))
        if source is None:
            continue
        if source.get("type") != _SOURCE_TYPE_ADR:
            continue
        rel = source.get("path")
        if not rel:
            continue
        resolved = (memory_parent / rel).resolve()
        if not resolved.is_file():
            missing.append(FreshnessIssue(
                code=ADR_MISSING,
                adr_id=str(decision.get("id", "<unknown>")),
                path=str(rel),
                message=(
                    f"Decision {decision.get('id', '<unknown>')!s} references "
                    f"ADR source {rel!s} but that file does not exist. "
                    f"Either restore the file or remove the decision."
                ),
            ))

    return unimported + changed + missing


# ── internals ─────────────────────────────────────────────────────────────────


def _load_raw_decisions(memory_path: Path) -> list[dict]:
    """Read decisions[] from the memory file as raw dicts.

    Returns [] if the file is missing the decisions key or if it cannot
    be parsed (the freshness checker is warn-only and never raises).
    """
    try:
        data = json.loads(memory_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    raw = data.get("decisions") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    return [d for d in raw if isinstance(d, dict)]


def _active_adrs(adr_dir: Path):
    """Parse the ADR directory and return (active_id_set, adr_id_to_ADR_map).

    "Active" mirrors the import contract: ``project_decision_graph`` marks
    accepted-and-not-superseded ADRs as ``status == "active"``. Proposed,
    deprecated, and superseded ADRs are not expected in memory and do not
    trigger UNIMPORTED.

    Parse errors are swallowed -- the freshness checker is warn-only and
    must not crash an unrelated ``mneme check`` invocation.
    """
    try:
        adrs = parse_adr_directory(adr_dir)
    except Exception:
        return set(), {}

    nodes = project_decision_graph(adrs)
    active_ids = {n.id for n in nodes if n.status == "active"}
    by_id = {a.id: a for a in adrs}
    return active_ids, by_id


def _coerce_source(value: Any) -> dict | None:
    """Return ``value`` if it is a dict, else None. Tolerates malformed input."""
    if isinstance(value, dict):
        return value
    return None


__all__ = [
    "ADR_UNIMPORTED",
    "ADR_CHANGED",
    "ADR_MISSING",
    "FreshnessIssue",
    "check_freshness",
    "compute_source_hash",
    "relative_source_path",
]
