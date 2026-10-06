"""Canonical ``mneme add_decision`` authority path (ADR-030 §4, D1E3).

An explicit human authority operation with its own occurrence identity,
``["cli-add", decision_id]``. It creates only a first occurrence, with the
no-predecessor sentinel and honest ``runtime`` provenance; it never claims
ADR or proposal origin. An exact retry resolves to the persisted occurrence
and writes nothing. Any other existing record for the id fails closed:
``add_decision`` is not an edit or version-evolution surface.

Canonical memory only. Section-less memory is refused here with
``DecisionIndexMigrationRequired`` (ADR-030 §1); the CLI keeps the legacy
``decisions[]`` write for it until D1E5.
"""
from __future__ import annotations

from pathlib import Path

from mneme.decision_index_persistence import (
    NO_PREDECESSOR,
    DecisionIndexPersistenceError,
    append_initial_canonical_decision,
    content_digest_of,
    load_persisted_decision_index,
    rebuild_compatibility_snapshot,
    require_canonical_document,
    verify_compatibility_snapshot,
    version_id_of,
)
from mneme.setup_state import ConcurrentModificationError, atomic_write_json

CLI_ADD_SOURCE = "cli-add"


class AddDecisionError(ValueError):
    """Canonical ``add_decision`` refused before any write."""


def cli_add_occurrence_identity(decision_id: str) -> list[str]:
    """ADR-030 §4 occurrence identity of canonical ``add_decision``.

    No timestamp participates: an exact retry re-derives the same key.
    """
    return [CLI_ADD_SOURCE, decision_id]


def add_canonical_decision(
    path: Path,
    raw: dict,
    source_bytes: bytes,
    *,
    decision_id: str,
    statement: str,
    rationale: str,
    scope: list[str],
    constraints: list[str],
    anti_patterns: list[str],
    now: str,
) -> bool:
    """Add one canonical decision as a first ``cli-add`` occurrence.

    ``raw`` must be parsed from ``source_bytes``: the whole canonical state,
    including the compatibility snapshot, is verified from it before anything
    changes, and the write is refused if the file no longer holds those
    bytes. ``now`` is stored as ``created_at``/``updated_at`` and is not part
    of the occurrence identity.

    Returns ``False`` for an exact retry: an occurrence with the same key is
    already persisted, so nothing is written. Raises :class:`AddDecisionError`
    before any write otherwise.
    """
    try:
        return _add(
            path,
            raw,
            source_bytes,
            decision_id=decision_id,
            statement=statement,
            rationale=rationale,
            scope=scope,
            constraints=constraints,
            anti_patterns=anti_patterns,
            now=now,
        )
    except DecisionIndexPersistenceError as exc:
        raise AddDecisionError(
            f"cannot add canonical decision {decision_id!r}: {exc}. "
            "Nothing was written."
        ) from exc
    except ConcurrentModificationError as exc:
        raise AddDecisionError(str(exc)) from exc


def _add(
    path: Path,
    raw: dict,
    source_bytes: bytes,
    *,
    decision_id: str,
    statement: str,
    rationale: str,
    scope: list[str],
    constraints: list[str],
    anti_patterns: list[str],
    now: str,
) -> bool:
    document = require_canonical_document(raw)
    index = load_persisted_decision_index(document["decision_index"])
    # A divergent decisions[] is refused here, never repaired by the rebuild
    # below (ADR-030 §1/§12: writers do not repair canonical state).
    verify_compatibility_snapshot(document, index, path)
    if decision_id.startswith("dprop-"):
        raise DecisionIndexPersistenceError(
            f"decision id {decision_id!r} uses the reserved proposal-id "
            "namespace (dprop-*)"
        )

    identity = cli_add_occurrence_identity(decision_id)
    version_id = version_id_of(
        decision_id,
        content_digest_of(statement, rationale, scope, constraints, anti_patterns),
        identity,
        NO_PREDECESSOR,
    )
    if any(record.decision_id == decision_id for record in index.records):
        # The retry lookup covers the decision's whole version history
        # (ADR-030 §5). Rules are Tier 2 and outside the occurrence key.
        if any(
            row.get("version_id") == version_id
            for row in document["decision_index"]["versions"]
        ):
            return False
        raise DecisionIndexPersistenceError(
            f"decision id {decision_id!r} already exists canonically with "
            "different content or another authority; add_decision creates "
            "first occurrences only and is not an edit or version-evolution "
            "surface"
        )

    document, created = append_initial_canonical_decision(
        document,
        decision_id=decision_id,
        statement=statement,
        rationale=rationale,
        context_scope=scope,
        lifecycle_status="active",
        created_at=now,
        updated_at=now,
        occurrence_source_identity=identity,
        source_evidence=[{
            "source_type": "runtime",
            "source_locator": "",
            "source_revision": "",
            "observed_at": "",
            "verification_status": "",
        }],
        constraints=constraints,
        anti_patterns=anti_patterns,
    )
    if not created:
        raise DecisionIndexPersistenceError(
            f"decision id {decision_id!r} could not be created canonically"
        )
    document = rebuild_compatibility_snapshot(document)
    atomic_write_json(path, document, expected_bytes=source_bytes)
    return True
