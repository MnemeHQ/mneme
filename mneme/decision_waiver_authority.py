"""
decision_waiver_authority.py — DG1B2a canonical waiver authority operations.

Charter docs/plans/2026-11-10-dg1b2-waiver-charter.md §3.3; Layer 1 freeze
amendment #785. ``waive`` and ``revoke_waiver`` are the **only** writers of
canonical waiver records, reached only from the explicit local CLI commands
``mneme decision waive`` and ``mneme decision revoke-waiver``. No producer
path (Decision MCP, the proposal store, proposal acceptance) and no runtime
surface (hooks, the C1a preview, Audit, protection, readiness) calls them.

Both follow ADR-030 writer discipline: read and verify the canonical state
before mutating, write atomically with an optimistic guard against a
concurrent change, reload and verify the written result, never repair and
never migrate implicitly (v1 or section-less memory is refused).

Mneme records ``requester`` / ``approver`` / ``revoked_by`` as identity
**claims**; it does not authenticate them (charter §3.4). The repository's
reviewed ``.mneme/`` change path is the authority check.

Waivers have no authoritative runtime consumer in DG1B2a: projection,
``mneme check``, hooks, CI, MCP and the C3a reporting consumers behave
exactly as before.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from mneme.decision_index import CanonicalWaiverRecord
from mneme.decision_index_persistence import (
    DecisionIndexPersistenceError,
    add_decision_waiver,
    load_decision_index_from_memory_file,
    load_persisted_decision_index,
    require_canonical_document,
    revoke_decision_waiver,
)
from mneme.setup_state import ConcurrentModificationError, atomic_write_json


class WaiverAuthorityError(Exception):
    """A waiver operation could not run; nothing was written."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class WaiverWriteResult:
    waiver_id: str
    waiver: CanonicalWaiverRecord


def _read(memory_path: Path) -> tuple[bytes, dict[str, Any]]:
    if not memory_path.is_file():
        raise WaiverAuthorityError(f"memory file {memory_path} does not exist")
    raw = memory_path.read_bytes()
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WaiverAuthorityError(
            f"memory file {memory_path} is not valid JSON: {exc}"
        ) from exc
    if not isinstance(document, dict):
        raise WaiverAuthorityError(f"memory file {memory_path} is not a JSON object")
    return raw, document


def _write_and_verify(
    memory_path: Path,
    expected_bytes: bytes,
    document: dict[str, Any],
    waiver_id: str,
    expected_status: str,
) -> CanonicalWaiverRecord:
    try:
        atomic_write_json(memory_path, document, expected_bytes=expected_bytes)
    except ConcurrentModificationError as exc:
        raise WaiverAuthorityError(str(exc)) from exc
    try:
        index = load_decision_index_from_memory_file(memory_path)
    except DecisionIndexPersistenceError as exc:
        raise WaiverAuthorityError(
            f"verification could not reload {memory_path}: {exc}"
        ) from exc
    waiver = next((w for w in index.waivers if w.waiver_id == waiver_id), None)
    if waiver is None or waiver.status != expected_status:
        raise WaiverAuthorityError(
            f"verification failed: waiver {waiver_id!r} is not {expected_status} "
            f"in {memory_path} after the write"
        )
    return waiver


def waive(
    memory_path: str | Path,
    *,
    target_decision_id: str,
    required_labels: list[str],
    requester: str,
    approver: str,
    approval_reference: str,
    reason: str,
    valid_from: str | None = None,
    valid_until: str | None = None,
    target_decision_version_id: str | None = None,
    clock: Callable[[], str] = _utc_now,
) -> WaiverWriteResult:
    """Record one canonical waiver. Raises on refusal; nothing is written.

    Raises:
        DecisionIndexMigrationRequired: v1 or section-less memory.
        DecisionWaiverRefused:          a charter §3.3 refusal.
        DecisionIndexPersistenceError:  invalid canonical state (no repair).
        WaiverAuthorityError:           I/O, concurrency or verification.
    """
    path = Path(memory_path)
    raw, document = _read(path)
    require_canonical_document(document)
    updated, waiver_id = add_decision_waiver(
        document,
        target_decision_id=target_decision_id,
        required_labels=required_labels,
        requester=requester,
        approver=approver,
        approval_reference=approval_reference,
        reason=reason,
        created_at=clock(),
        valid_from=valid_from,
        valid_until=valid_until,
        target_decision_version_id=target_decision_version_id,
    )
    waiver = _write_and_verify(path, raw, updated, waiver_id, "active")
    return WaiverWriteResult(waiver_id=waiver_id, waiver=waiver)


def revoke_waiver(
    memory_path: str | Path,
    *,
    waiver_id: str,
    revoked_by: str,
    revocation_reference: str,
    reason: str,
) -> WaiverWriteResult:
    """Revoke one canonical waiver; the record is retained."""
    path = Path(memory_path)
    raw, document = _read(path)
    updated = revoke_decision_waiver(
        document,
        waiver_id=waiver_id,
        revoked_by=revoked_by,
        revocation_reference=revocation_reference,
        reason=reason,
    )
    waiver = _write_and_verify(path, raw, updated, waiver_id, "revoked")
    return WaiverWriteResult(waiver_id=waiver_id, waiver=waiver)


def list_waivers(memory_path: str | Path) -> tuple[CanonicalWaiverRecord, ...]:
    """Read-only: every canonical waiver, active and revoked, sorted by id."""
    path = Path(memory_path)
    _, document = _read(path)
    migrated = require_canonical_document(document)
    return load_persisted_decision_index(migrated["decision_index"]).waivers


__all__ = [
    "WaiverAuthorityError",
    "WaiverWriteResult",
    "list_waivers",
    "revoke_waiver",
    "waive",
]
