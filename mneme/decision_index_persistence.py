"""
decision_index_persistence.py — D1B canonical Decision Index persistence.

ADR-030 keeps canonical decisions in the versioned ``decision_index`` section
of ``project_memory.json`` while preserving ``MemoryStore.decisions()`` as the
Layer 1 compatibility API. This module owns the file-format boundary only:
identity, migration, validation, and conversion into the existing canonical
read model. It does not own authority transitions, MCP composition, retrieval,
enforcement, Audit, or Open Architecture research data.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from mneme.decision_index import (
    CANONICAL_DECISION_CLASS_ARCHITECTURE,
    CANONICAL_VERSION,
    CanonicalArchitectureIndex,
    CanonicalDecisionRecord,
    CanonicalRuleRecord,
    CanonicalSourceEvidence,
    CanonicalTestEvidence,
    VALID_LIFECYCLE_STATUSES,
)
from mneme.decision_projection import project_canonical_index
from mneme.schemas import Decision, MemoryItem, Rule

DECISION_INDEX_SCHEMA = "mneme.decision-index/v1"
NO_PREDECESSOR = "-"
_RESERVED_PROPOSAL_PREFIX = "dprop-"


class DecisionIndexPersistenceError(ValueError):
    """The durable Decision Index is malformed or internally inconsistent."""


class LegacyDecisionsWriteRefused(DecisionIndexPersistenceError):
    """A legacy ``decisions[]`` writer targeted canonical project memory."""


def refuse_legacy_decisions_write(document: object, *, operation: str) -> None:
    """Refuse a legacy ``decisions[]`` mutation of canonical project memory.

    D1 persisted-index containment invariant, keyed purely on section
    presence: once a top-level ``decision_index`` exists the loader treats it
    as the durable decision authority and ``decisions[]`` as derived
    compatibility state, so no legacy writer may mutate it. Callers must invoke this after reading the
    document and before any mutation or write. ``operation`` only names the
    caller in the error; it does not change the invariant.
    """
    if isinstance(document, dict) and "decision_index" in document:
        raise LegacyDecisionsWriteRefused(
            f"{operation} is a legacy decisions[] writer and cannot modify "
            "project memory that uses canonical Decision Index persistence. "
            "decisions[] is a derived compatibility snapshot of "
            "the authoritative decision_index section. Nothing was written."
        )


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def content_digest_of(
    statement: str,
    rationale: str,
    context_scope: list[str] | tuple[str, ...],
    constraints: list[str] | tuple[str, ...],
    anti_patterns: list[str] | tuple[str, ...],
) -> str:
    """ADR-030 Tier-1 content digest."""
    return _sha256_hex([
        statement,
        rationale,
        list(context_scope),
        list(constraints),
        list(anti_patterns),
    ])


def version_id_of(
    decision_id: str,
    content_digest: str,
    occurrence_source_identity: list[Any] | tuple[Any, ...],
    supersedes_version_id: str | None = None,
) -> str:
    """ADR-030 immutable version-occurrence identity."""
    predecessor = supersedes_version_id or NO_PREDECESSOR
    digest = _sha256_hex([
        decision_id,
        content_digest,
        list(occurrence_source_identity),
        predecessor,
    ])
    return f"dver-{digest[:32]}"


def rule_id_of(
    decision_id: str,
    rule_type: str,
    value: str,
    applicability: dict[str, Any],
) -> str:
    """ADR-030 stable rule identity, independent of rule order."""
    digest = _sha256_hex([value, applicability])
    return f"{decision_id}:{rule_type}:{digest[:32]}"


def _require_dict(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DecisionIndexPersistenceError(f"{label} must be an object")
    return value


def _require_list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise DecisionIndexPersistenceError(f"{label} must be a list")
    return value


def _require_str(value: object, label: str, *, non_empty: bool = False) -> str:
    if not isinstance(value, str) or (non_empty and not value):
        qualifier = "non-empty " if non_empty else ""
        raise DecisionIndexPersistenceError(f"{label} must be a {qualifier}string")
    return value


def _str_list(value: object, label: str) -> list[str]:
    rows = _require_list(value, label)
    if not all(isinstance(item, str) for item in rows):
        raise DecisionIndexPersistenceError(f"{label} must contain only strings")
    return list(rows)


def _rule_from_memory_record(record: object) -> Rule:
    """Pre-D1 rule loader semantics, preserved byte-for-byte in behavior."""
    if not isinstance(record, dict):
        raise ValueError("rule record must be an object")
    include_paths: tuple[str, ...] | None = None
    if "include_paths" in record:
        raw_include = record["include_paths"]
        if not isinstance(raw_include, list):
            raise ValueError("rule include_paths must be a list")
        include_paths = tuple(raw_include)
    raw_exclude = record.get("exclude_paths", [])
    if not isinstance(raw_exclude, list):
        raise ValueError("rule exclude_paths must be a list")
    return Rule(
        type=record["type"],
        value=record["value"],
        include_paths=include_paths,
        exclude_paths=tuple(raw_exclude),
    )


def _resolved_adr_source_path(
    memory_path: Path | None,
    source: object,
    decision_id: str,
) -> str:
    if not isinstance(source, dict) or source.get("type") != "adr":
        return ""
    raw_path = source.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return ""
    source_name = Path(raw_path).name
    if Path(source_name).suffix.lower() != ".md":
        return ""
    if source_name != f"{decision_id}.md" and not source_name.startswith(
        f"{decision_id}-"
    ):
        return ""
    if memory_path is None:
        return raw_path
    return str((memory_path.parent / raw_path).resolve())


def runtime_decision_from_memory_record(
    record: object,
    memory_path: Path | None = None,
) -> Decision:
    """Load one pre-D1 ``decisions[]`` entry with the exact old semantics."""
    if not isinstance(record, dict):
        raise TypeError("decision record must be an object")
    return Decision(
        id=record["id"],
        decision=record["decision"],
        rationale=record.get("rationale", ""),
        scope=list(record.get("scope", [])),
        constraints=list(record.get("constraints", [])),
        anti_patterns=list(record.get("anti_patterns", [])),
        rules=[
            _rule_from_memory_record(rule)
            for rule in record.get("rules", [])
        ],
        test_evidence=[
            entry
            for entry in (record.get("test_evidence") or [])
            if isinstance(entry, dict)
        ],
        source_path=_resolved_adr_source_path(
            memory_path,
            record.get("source"),
            record["id"],
        ),
        memory_path=str(memory_path.resolve()) if memory_path is not None else "",
        created_at=record.get("created_at", ""),
        updated_at=record.get("updated_at", ""),
        status=record.get("status", "active"),
    )


def legacy_item_to_runtime_decision(item: MemoryItem) -> Decision | None:
    """Reproduce the pre-D1 legacy item -> Decision synthesis exactly."""
    if item.type == "rule":
        return Decision(
            id=item.id,
            decision=item.title,
            rationale="",
            scope=["general"],
            constraints=[item.content] if item.content else [],
        )
    if item.type == "anti_pattern":
        return Decision(
            id=item.id,
            decision=f"Avoid: {item.title}",
            rationale="",
            scope=["general"],
            constraints=[item.content] if item.content else [],
            anti_patterns=[item.title],
        )
    return None


def _memory_item_from_record(record: object) -> MemoryItem:
    raw = _require_dict(record, "memory item")
    try:
        return MemoryItem(
            id=raw["id"],
            type=raw["type"],
            title=raw["title"],
            content=raw["content"],
            tags=list(raw.get("tags", [])),
            priority=raw.get("priority", "medium"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DecisionIndexPersistenceError(f"invalid memory item: {exc}") from exc


def _applicability_of(rule: Rule) -> dict[str, Any]:
    applicability: dict[str, Any] = {}
    if rule.include_paths is not None:
        applicability["include_paths"] = list(rule.include_paths)
    if rule.exclude_paths:
        applicability["exclude_paths"] = list(rule.exclude_paths)
    return applicability


def _rule_bindings_for_version(
    decision_id: str,
    version_id: str,
    revision: str,
    rules: list[Rule] | tuple[Rule, ...],
) -> list[dict[str, Any]]:
    """Build explicit immutable rule bindings for one version occurrence."""
    bindings: list[dict[str, Any]] = []
    seen_rule_ids: set[str] = set()
    for sequence, rule in enumerate(rules):
        applicability = _applicability_of(rule)
        rule_id = rule_id_of(decision_id, rule.type, rule.value, applicability)
        if rule_id in seen_rule_ids:
            raise DecisionIndexPersistenceError(
                f"decision {decision_id!r} contains duplicate identical rule bindings"
            )
        seen_rule_ids.add(rule_id)
        bindings.append({
            "rule_id": rule_id,
            "decision_id": decision_id,
            "decision_version_id": version_id,
            "decision_version": revision,
            "sequence": sequence,
            "rule_type": rule.type,
            "rule_payload": {"value": rule.value},
            "applicability": applicability,
        })
    return bindings


def _source_snapshot(
    raw_decision: dict[str, Any] | None,
) -> tuple[list[dict[str, str]], list[str]]:
    if raw_decision is not None:
        raw_source = raw_decision.get("source")
        if isinstance(raw_source, dict) and raw_source.get("type") == "adr":
            locator = _resolved_adr_source_path(
                None,
                raw_source,
                raw_decision["id"],
            )
            revision = raw_source.get("sha256", "")
            if locator:
                evidence = [{
                    "source_type": "adr",
                    "source_locator": locator,
                    "source_revision": revision if isinstance(revision, str) else "",
                    "observed_at": "",
                    "verification_status": "",
                }]
                if isinstance(revision, str) and revision:
                    return (
                        evidence,
                        [raw_decision["id"], revision, "adr-import"],
                    )
                return (
                    evidence,
                    ["legacy-decisions", raw_decision["id"]],
                )
    decision_id = raw_decision["id"] if raw_decision is not None else ""
    return (
        [{
            "source_type": "runtime",
            "source_locator": "",
            "source_revision": "",
            "observed_at": "",
            "verification_status": "",
        }],
        ["legacy-decisions", decision_id],
    )


def _version_and_rules_for_migration(
    decision: Decision,
    *,
    source_identity: list[str],
    source_evidence: list[dict[str, str]],
    created_at: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    digest = content_digest_of(
        decision.decision,
        decision.rationale,
        decision.scope,
        decision.constraints,
        decision.anti_patterns,
    )
    version_id = version_id_of(
        decision.id,
        digest,
        source_identity,
        NO_PREDECESSOR,
    )
    version = {
        "version_id": version_id,
        "decision_id": decision.id,
        "revision": "1",
        "content_digest": digest,
        "statement": decision.decision,
        "rationale": decision.rationale,
        "context_scope": list(decision.scope),
        "constraints": list(decision.constraints),
        "anti_patterns": list(decision.anti_patterns),
        "source_evidence": source_evidence,
        "occurrence_source_identity": list(source_identity),
        "supersedes_version_id": None,
        "created_at": created_at,
    }
    bindings = _rule_bindings_for_version(
        decision.id,
        version_id,
        CANONICAL_VERSION,
        decision.rules,
    )
    return version, bindings


def _logical_record_for_migration(
    decision: Decision,
    version_id: str,
) -> dict[str, Any]:
    return {
        "decision_id": decision.id,
        "decision_class": CANONICAL_DECISION_CLASS_ARCHITECTURE,
        "lifecycle_status": decision.status,
        "active_version_id": version_id,
        "test_evidence": [
            {
                "selector": str(entry.get("selector", "")),
                "sha": str(entry.get("sha", "")),
            }
            for entry in decision.test_evidence
        ],
        "relationships": [],
        "updated_at": decision.updated_at,
    }


def _snapshot_record_from_decision(decision: Decision) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": decision.id,
        "decision": decision.decision,
        "rationale": decision.rationale,
        "scope": list(decision.scope),
        "constraints": list(decision.constraints),
        "anti_patterns": list(decision.anti_patterns),
        "rules": [],
        "test_evidence": copy.deepcopy(decision.test_evidence),
        "created_at": decision.created_at,
        "updated_at": decision.updated_at,
        "status": decision.status,
    }
    for rule in decision.rules:
        raw_rule: dict[str, Any] = {
            "type": rule.type,
            "value": rule.value,
        }
        if rule.include_paths is not None:
            raw_rule["include_paths"] = list(rule.include_paths)
        if rule.exclude_paths:
            raw_rule["exclude_paths"] = list(rule.exclude_paths)
        record["rules"].append(raw_rule)
    return record


def migrate_memory_document(document: dict[str, Any]) -> dict[str, Any]:
    """Build the initial D1B canonical section from a pre-D1 memory document.

    If a section already exists it is validated and the document is returned
    unchanged, making a second migration a structural no-op.
    """
    if not isinstance(document, dict):
        raise DecisionIndexPersistenceError("project memory must be an object")
    if "decision_index" in document:
        load_persisted_decision_index(document["decision_index"])
        return copy.deepcopy(document)

    raw_decisions = _require_list(document.get("decisions", []), "decisions")
    native: list[tuple[Decision, dict[str, Any]]] = []
    seen_ids: set[str] = set()
    for row in raw_decisions:
        raw = _require_dict(row, "decision record")
        decision = runtime_decision_from_memory_record(raw)
        if decision.id in seen_ids:
            raise DecisionIndexPersistenceError(
                f"duplicate decision id {decision.id!r} in decisions[]"
            )
        if decision.id.startswith(_RESERVED_PROPOSAL_PREFIX):
            raise DecisionIndexPersistenceError(
                f"decision id {decision.id!r} uses reserved proposal namespace"
            )
        seen_ids.add(decision.id)
        native.append((decision, raw))

    migrated_items: list[Decision] = []
    for row in _require_list(document.get("items", []), "items"):
        item = _memory_item_from_record(row)
        decision = legacy_item_to_runtime_decision(item)
        if decision is None:
            continue
        if decision.id in seen_ids:
            raise DecisionIndexPersistenceError(
                f"legacy item id {decision.id!r} collides with an existing decision id"
            )
        if decision.id.startswith(_RESERVED_PROPOSAL_PREFIX):
            raise DecisionIndexPersistenceError(
                f"legacy item id {decision.id!r} uses reserved proposal namespace"
            )
        seen_ids.add(decision.id)
        migrated_items.append(decision)

    logical: list[dict[str, Any]] = []
    versions: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []

    for decision, raw in native:
        evidence, source_identity = _source_snapshot(raw)
        version, decision_rules = _version_and_rules_for_migration(
            decision,
            source_identity=source_identity,
            source_evidence=evidence,
            created_at=decision.created_at,
        )
        logical.append(_logical_record_for_migration(decision, version["version_id"]))
        versions.append(version)
        bindings.extend(decision_rules)

    for decision in migrated_items:
        evidence = [{
            "source_type": "runtime",
            "source_locator": "",
            "source_revision": "",
            "observed_at": "",
            "verification_status": "",
        }]
        source_identity = ["legacy-items", decision.id]
        version, decision_rules = _version_and_rules_for_migration(
            decision,
            source_identity=source_identity,
            source_evidence=evidence,
            created_at="",
        )
        logical.append(_logical_record_for_migration(decision, version["version_id"]))
        versions.append(version)
        bindings.extend(decision_rules)

    section = {
        "schema": DECISION_INDEX_SCHEMA,
        "decisions": logical,
        "versions": versions,
        "rules": bindings,
    }
    load_persisted_decision_index(section)

    migrated = copy.deepcopy(document)
    migrated["decision_index"] = section
    migrated["decisions"] = [
        copy.deepcopy(raw)
        for decision, raw in native
        if decision.status == "active"
    ]
    migrated["decisions"].extend(
        _snapshot_record_from_decision(decision)
        for decision in migrated_items
        if decision.status == "active"
    )
    return migrated



def append_initial_canonical_decision(
    document: dict[str, Any],
    *,
    decision_id: str,
    statement: str,
    rationale: str,
    context_scope: list[str] | tuple[str, ...],
    lifecycle_status: str,
    created_at: str,
    updated_at: str,
    occurrence_source_identity: list[Any] | tuple[Any, ...],
    source_evidence: list[dict[str, Any]],
    constraints: list[str] | tuple[str, ...] = (),
    anti_patterns: list[str] | tuple[str, ...] = (),
    rules: list[Rule] | tuple[Rule, ...] = (),
    relationships: list[dict[str, str]] | tuple[dict[str, str], ...] = (),
) -> tuple[dict[str, Any], bool]:
    """Append one first canonical occurrence and its derived compatibility row.

    This is a persistence primitive only. The caller owns authority and
    transition semantics. A section-less document is migrated first so the
    write always lands in the durable Decision Index. Existing decision ids
    are returned unchanged for the caller to verify or fail closed.
    """
    migrated = migrate_memory_document(document)
    section = copy.deepcopy(
        _require_dict(migrated["decision_index"], "decision_index")
    )
    logical_rows = _require_list(
        section.get("decisions"), "decision_index.decisions"
    )
    if any(
        isinstance(row, dict) and row.get("decision_id") == decision_id
        for row in logical_rows
    ):
        return migrated, False

    digest = content_digest_of(
        statement,
        rationale,
        context_scope,
        constraints,
        anti_patterns,
    )
    version_id = version_id_of(
        decision_id,
        digest,
        occurrence_source_identity,
        NO_PREDECESSOR,
    )
    logical_rows.append({
        "decision_id": decision_id,
        "decision_class": CANONICAL_DECISION_CLASS_ARCHITECTURE,
        "lifecycle_status": lifecycle_status,
        "active_version_id": version_id,
        "test_evidence": [],
        "relationships": copy.deepcopy(list(relationships)),
        "updated_at": updated_at,
    })
    _require_list(
        section.get("versions"), "decision_index.versions"
    ).append({
        "version_id": version_id,
        "decision_id": decision_id,
        "revision": "1",
        "content_digest": digest,
        "statement": statement,
        "rationale": rationale,
        "context_scope": list(context_scope),
        "constraints": list(constraints),
        "anti_patterns": list(anti_patterns),
        "source_evidence": copy.deepcopy(source_evidence),
        "occurrence_source_identity": list(occurrence_source_identity),
        "supersedes_version_id": None,
        "created_at": created_at,
    })

    _require_list(section.get("rules"), "decision_index.rules").extend(
        _rule_bindings_for_version(
            decision_id,
            version_id,
            CANONICAL_VERSION,
            rules,
        )
    )
    migrated["decision_index"] = section
    index = load_persisted_decision_index(section)
    projected = project_canonical_index(index)
    decision = next(
        (item for item in projected if item.id == decision_id),
        None,
    )
    if decision is not None:
        decisions = _require_list(migrated.get("decisions", []), "decisions")
        snapshot_row = _snapshot_record_from_decision(decision)
        if source_evidence:
            first_source = source_evidence[0]
            if (
                isinstance(first_source, dict)
                and first_source.get("source_type") == "adr"
                and isinstance(first_source.get("source_locator"), str)
                and first_source.get("source_locator")
            ):
                snapshot_row["source"] = {
                    "type": "adr",
                    "path": first_source["source_locator"],
                    "sha256": str(first_source.get("source_revision", "")),
                }
        decisions.append(snapshot_row)
    return migrated, True


def append_canonical_version_occurrence(
    document: dict[str, Any],
    *,
    decision_id: str,
    predecessor_version_id: str,
    statement: str,
    rationale: str,
    context_scope: list[str] | tuple[str, ...],
    constraints: list[str] | tuple[str, ...],
    anti_patterns: list[str] | tuple[str, ...],
    rules: list[Rule] | tuple[Rule, ...],
    created_at: str,
    updated_at: str,
    occurrence_source_identity: list[Any] | tuple[Any, ...],
    source_evidence: list[dict[str, Any]],
) -> tuple[dict[str, Any], str, bool]:
    """Append or idempotently reuse one immutable D1D version occurrence.

    The predecessor is an explicit authority input. It is never re-derived
    after the operation starts. An exact persisted retry is a structural
    no-op even if a later authority action moved the active pointer.
    """
    migrated = migrate_memory_document(document)
    section = copy.deepcopy(
        _require_dict(migrated["decision_index"], "decision_index")
    )
    logical_rows = _require_list(
        section.get("decisions"), "decision_index.decisions"
    )
    logical = next(
        (
            row for row in logical_rows
            if isinstance(row, dict) and row.get("decision_id") == decision_id
        ),
        None,
    )
    if logical is None:
        raise DecisionIndexPersistenceError(
            f"decision {decision_id!r} does not exist for version evolution"
        )
    active_version_id = _require_str(
        logical.get("active_version_id"),
        f"decision {decision_id!r} active_version_id",
        non_empty=True,
    )

    digest = content_digest_of(
        statement,
        rationale,
        context_scope,
        constraints,
        anti_patterns,
    )
    version_id = version_id_of(
        decision_id,
        digest,
        occurrence_source_identity,
        predecessor_version_id,
    )
    version_record = {
        "version_id": version_id,
        "decision_id": decision_id,
        # Public version/revision remains display-only in D1D. Do not
        # create a second authority signal by deriving identity from it.
        "revision": CANONICAL_VERSION,
        "content_digest": digest,
        "statement": statement,
        "rationale": rationale,
        "context_scope": list(context_scope),
        "constraints": list(constraints),
        "anti_patterns": list(anti_patterns),
        "source_evidence": copy.deepcopy(source_evidence),
        "occurrence_source_identity": list(occurrence_source_identity),
        "supersedes_version_id": predecessor_version_id,
        "created_at": created_at,
    }
    expected_bindings = _rule_bindings_for_version(
        decision_id,
        version_id,
        CANONICAL_VERSION,
        rules,
    )

    versions = _require_list(section.get("versions"), "decision_index.versions")
    existing = next(
        (
            row for row in versions
            if isinstance(row, dict) and row.get("version_id") == version_id
        ),
        None,
    )
    if existing is not None:
        if existing != version_record:
            raise DecisionIndexPersistenceError(
                f"version occurrence {version_id!r} already exists with "
                "different immutable content"
            )
        existing_bindings = sorted(
            [
                row for row in _require_list(
                    section.get("rules"), "decision_index.rules"
                )
                if isinstance(row, dict)
                and row.get("decision_version_id") == version_id
            ],
            key=lambda row: row.get("sequence", -1),
        )
        if existing_bindings != expected_bindings:
            raise DecisionIndexPersistenceError(
                f"version occurrence {version_id!r} rule bindings differ "
                "from the persisted immutable occurrence"
            )
        load_persisted_decision_index(section)
        return migrated, version_id, False

    if active_version_id != predecessor_version_id:
        raise DecisionIndexPersistenceError(
            f"stale version evolution for {decision_id!r}: expected active "
            f"predecessor {predecessor_version_id!r}, found {active_version_id!r}"
        )

    predecessor = next(
        (
            row for row in versions
            if isinstance(row, dict)
            and row.get("version_id") == predecessor_version_id
            and row.get("decision_id") == decision_id
        ),
        None,
    )
    if predecessor is None:
        raise DecisionIndexPersistenceError(
            f"decision {decision_id!r} predecessor "
            f"{predecessor_version_id!r} does not exist"
        )

    versions.append(version_record)
    _require_list(section.get("rules"), "decision_index.rules").extend(
        expected_bindings
    )
    logical["active_version_id"] = version_id
    logical["updated_at"] = updated_at
    migrated["decision_index"] = section
    load_persisted_decision_index(section)
    return migrated, version_id, True


def apply_canonical_supersession(
    document: dict[str, Any],
    *,
    superseding_decision_id: str,
    target_decision_ids: list[str] | tuple[str, ...],
    updated_at: str,
) -> tuple[dict[str, Any], bool]:
    """Persist explicit cross-decision supersedes semantics only.

    This is deliberately narrower than a general lifecycle writer: D1D may
    mark targets superseded only as the consequence of an explicit
    ADR-sanctioned ``supersedes`` relationship.
    """
    migrated = migrate_memory_document(document)
    section = copy.deepcopy(
        _require_dict(migrated["decision_index"], "decision_index")
    )
    logical_rows = _require_list(
        section.get("decisions"), "decision_index.decisions"
    )
    by_id = {
        row.get("decision_id"): row
        for row in logical_rows
        if isinstance(row, dict)
    }
    source = by_id.get(superseding_decision_id)
    if source is None:
        raise DecisionIndexPersistenceError(
            f"superseding decision {superseding_decision_id!r} does not exist"
        )

    targets = list(target_decision_ids)
    if len(set(targets)) != len(targets):
        raise DecisionIndexPersistenceError(
            f"decision {superseding_decision_id!r} declares duplicate supersedes targets"
        )
    if superseding_decision_id in targets:
        raise DecisionIndexPersistenceError(
            f"decision {superseding_decision_id!r} cannot supersede itself"
        )
    for target_id in targets:
        if target_id not in by_id:
            raise DecisionIndexPersistenceError(
                f"supersedes target {target_id!r} does not exist canonically"
            )

    desired_relationships = [
        {"type": "supersedes", "target_decision_id": target_id}
        for target_id in targets
    ]
    changed = source.get("relationships", []) != desired_relationships
    source["relationships"] = desired_relationships
    if changed:
        source["updated_at"] = updated_at

    for target_id in targets:
        target = by_id[target_id]
        if target.get("lifecycle_status") != "superseded":
            target["lifecycle_status"] = "superseded"
            target["updated_at"] = updated_at
            changed = True

    migrated["decision_index"] = section
    load_persisted_decision_index(section)
    return migrated, changed

def rebind_legacy_initial_occurrence(
    document: dict[str, Any],
    *,
    decision_id: str,
    occurrence_source_identity: list[Any] | tuple[Any, ...],
    source_evidence: list[dict[str, Any]],
) -> tuple[dict[str, Any], bool]:
    """Replace only a migration-only legacy occurrence identity.

    D1C uses this when a proposal was accepted before canonical cutover and
    its old compatibility row was migrated by D1B. Content, rule ids,
    ordering, lifecycle, timestamps, and the compatibility snapshot remain
    unchanged; only first-occurrence identity and provenance are corrected.
    """
    migrated = migrate_memory_document(document)
    section = copy.deepcopy(
        _require_dict(migrated["decision_index"], "decision_index")
    )
    logical_rows = _require_list(
        section.get("decisions"), "decision_index.decisions"
    )
    logical = next(
        (
            row
            for row in logical_rows
            if isinstance(row, dict) and row.get("decision_id") == decision_id
        ),
        None,
    )
    if logical is None:
        return migrated, False
    active_version_id = _require_str(
        logical.get("active_version_id"),
        f"decision {decision_id!r} active_version_id",
        non_empty=True,
    )
    versions = _require_list(
        section.get("versions"), "decision_index.versions"
    )
    version = next(
        (
            row
            for row in versions
            if isinstance(row, dict) and row.get("version_id") == active_version_id
        ),
        None,
    )
    if version is None:
        raise DecisionIndexPersistenceError(
            f"decision {decision_id!r} active version is missing"
        )
    existing_identity = _require_list(
        version.get("occurrence_source_identity", []),
        f"decision {decision_id!r} occurrence_source_identity",
    )
    if existing_identity != ["legacy-decisions", decision_id]:
        return migrated, False
    if version.get("supersedes_version_id") is not None:
        raise DecisionIndexPersistenceError(
            f"decision {decision_id!r} legacy migration occurrence has a predecessor"
        )

    new_version_id = version_id_of(
        decision_id,
        _require_str(
            version.get("content_digest"),
            f"decision {decision_id!r} content_digest",
            non_empty=True,
        ),
        occurrence_source_identity,
        NO_PREDECESSOR,
    )
    if any(
        isinstance(row, dict)
        and row is not version
        and row.get("version_id") == new_version_id
        for row in versions
    ):
        raise DecisionIndexPersistenceError(
            f"proposal-backed version id {new_version_id!r} already exists"
        )
    version["version_id"] = new_version_id
    version["occurrence_source_identity"] = list(occurrence_source_identity)
    version["source_evidence"] = copy.deepcopy(source_evidence)
    logical["active_version_id"] = new_version_id
    for rule in _require_list(section.get("rules"), "decision_index.rules"):
        if (
            isinstance(rule, dict)
            and rule.get("decision_id") == decision_id
            and rule.get("decision_version_id") == active_version_id
        ):
            rule["decision_version_id"] = new_version_id

    migrated["decision_index"] = section
    load_persisted_decision_index(section)
    return migrated, True


def _parse_source_evidence(
    raw: object,
    decision_id: str,
) -> tuple[CanonicalSourceEvidence, ...]:
    rows = _require_list(raw, f"decision {decision_id!r} source_evidence")
    evidence: list[CanonicalSourceEvidence] = []
    for index, row in enumerate(rows):
        item = _require_dict(row, f"source_evidence[{index}]")
        source_type = _require_str(
            item.get("source_type"),
            f"source_evidence[{index}].source_type",
            non_empty=True,
        )
        if source_type not in {"adr", "runtime", "proposal"}:
            raise DecisionIndexPersistenceError(
                f"decision {decision_id!r} source evidence has unknown source_type "
                f"{source_type!r}"
            )
        common_keys = {
            "source_type",
            "source_locator",
            "source_revision",
            "observed_at",
            "verification_status",
        }
        proposal_keys = {
            "proposal_id",
            "producer_key",
            "content_fingerprint",
            "origin_classification",
            "proposed_at",
            "source_reference",
            "accepted_decision_id",
        }
        allowed_keys = (
            common_keys | proposal_keys
            if source_type == "proposal"
            else common_keys
        )
        unknown_keys = set(item) - allowed_keys
        if unknown_keys:
            raise DecisionIndexPersistenceError(
                f"decision {decision_id!r} source evidence type {source_type!r} "
                f"contains unsupported fields {sorted(unknown_keys)}"
            )

        common = {
            "source_type": source_type,
            "source_locator": _require_str(
                item.get("source_locator", ""),
                f"source_evidence[{index}].source_locator",
            ),
            "source_revision": _require_str(
                item.get("source_revision", ""),
                f"source_evidence[{index}].source_revision",
            ),
            "observed_at": _require_str(
                item.get("observed_at", ""),
                f"source_evidence[{index}].observed_at",
            ),
            "verification_status": _require_str(
                item.get("verification_status", ""),
                f"source_evidence[{index}].verification_status",
            ),
        }
        if source_type != "proposal":
            evidence.append(CanonicalSourceEvidence(**common))
            continue

        proposal_fields = {
            "proposal_id": _require_str(
                item.get("proposal_id"),
                f"source_evidence[{index}].proposal_id",
                non_empty=True,
            ),
            "producer_key": _require_str(
                item.get("producer_key"),
                f"source_evidence[{index}].producer_key",
                non_empty=True,
            ),
            "content_fingerprint": _require_str(
                item.get("content_fingerprint"),
                f"source_evidence[{index}].content_fingerprint",
                non_empty=True,
            ),
            "origin_classification": _require_str(
                item.get("origin_classification"),
                f"source_evidence[{index}].origin_classification",
                non_empty=True,
            ),
            "proposed_at": _require_str(
                item.get("proposed_at"),
                f"source_evidence[{index}].proposed_at",
                non_empty=True,
            ),
            "source_reference": _require_str(
                item.get("source_reference"),
                f"source_evidence[{index}].source_reference",
                non_empty=True,
            ),
            "accepted_decision_id": _require_str(
                item.get("accepted_decision_id"),
                f"source_evidence[{index}].accepted_decision_id",
                non_empty=True,
            ),
        }
        if proposal_fields["accepted_decision_id"] != decision_id:
            raise DecisionIndexPersistenceError(
                f"decision {decision_id!r} proposal provenance links to "
                f"{proposal_fields['accepted_decision_id']!r}"
            )
        evidence.append(CanonicalSourceEvidence(
            **common,
            **proposal_fields,
        ))
    return tuple(evidence)


def _parse_test_evidence(
    raw: object,
    decision_id: str,
) -> tuple[CanonicalTestEvidence, ...]:
    rows = _require_list(raw, f"decision {decision_id!r} test_evidence")
    out: list[CanonicalTestEvidence] = []
    for index, row in enumerate(rows):
        item = _require_dict(row, f"test_evidence[{index}]")
        out.append(CanonicalTestEvidence(
            selector=_require_str(
                item.get("selector", ""),
                f"test_evidence[{index}].selector",
            ),
            sha=_require_str(
                item.get("sha", ""),
                f"test_evidence[{index}].sha",
            ),
        ))
    return tuple(out)


def _parse_relationships(
    raw: object,
    decision_id: str,
) -> tuple[tuple[str, str], ...]:
    rows = _require_list(raw, f"decision {decision_id!r} relationships")
    out: list[tuple[str, str]] = []
    for index, row in enumerate(rows):
        item = _require_dict(row, f"relationships[{index}]")
        rel_type = _require_str(
            item.get("type"),
            f"relationships[{index}].type",
            non_empty=True,
        )
        target = _require_str(
            item.get("target_decision_id"),
            f"relationships[{index}].target_decision_id",
            non_empty=True,
        )
        if rel_type != "supersedes":
            raise DecisionIndexPersistenceError(
                f"decision {decision_id!r} has unsupported relationship type "
                f"{rel_type!r}"
            )
        out.append((rel_type, target))
    return tuple(out)


def load_persisted_decision_index(
    section: object,
) -> CanonicalArchitectureIndex:
    """Validate a D1B section and build the existing canonical read model."""
    root = _require_dict(section, "decision_index")
    if root.get("schema") != DECISION_INDEX_SCHEMA:
        raise DecisionIndexPersistenceError(
            f"decision_index schema must be {DECISION_INDEX_SCHEMA!r}"
        )

    logical_rows = _require_list(root.get("decisions"), "decision_index.decisions")
    version_rows = _require_list(root.get("versions"), "decision_index.versions")
    rule_rows = _require_list(root.get("rules"), "decision_index.rules")

    versions_by_id: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(version_rows):
        raw = _require_dict(row, f"decision_index.versions[{index}]")
        version_id = _require_str(
            raw.get("version_id"),
            f"versions[{index}].version_id",
            non_empty=True,
        )
        if version_id in versions_by_id:
            raise DecisionIndexPersistenceError(
                f"duplicate version_id {version_id!r}"
            )
        decision_id = _require_str(
            raw.get("decision_id"),
            f"versions[{index}].decision_id",
            non_empty=True,
        )
        revision = _require_str(
            raw.get("revision"),
            f"versions[{index}].revision",
            non_empty=True,
        )
        statement = _require_str(
            raw.get("statement"), f"versions[{index}].statement"
        )
        rationale = _require_str(
            raw.get("rationale", ""), f"versions[{index}].rationale"
        )
        context_scope = _str_list(
            raw.get("context_scope", []),
            f"versions[{index}].context_scope",
        )
        constraints = _str_list(
            raw.get("constraints", []),
            f"versions[{index}].constraints",
        )
        anti_patterns = _str_list(
            raw.get("anti_patterns", []),
            f"versions[{index}].anti_patterns",
        )
        stored_digest = _require_str(
            raw.get("content_digest"),
            f"versions[{index}].content_digest",
            non_empty=True,
        )
        expected_digest = content_digest_of(
            statement,
            rationale,
            context_scope,
            constraints,
            anti_patterns,
        )
        if stored_digest != expected_digest:
            raise DecisionIndexPersistenceError(
                f"version {version_id!r} content_digest mismatch"
            )
        occurrence = _require_list(
            raw.get("occurrence_source_identity"),
            f"versions[{index}].occurrence_source_identity",
        )
        predecessor = raw.get("supersedes_version_id")
        if predecessor is not None and not isinstance(predecessor, str):
            raise DecisionIndexPersistenceError(
                f"versions[{index}].supersedes_version_id must be a string or null"
            )
        expected_version_id = version_id_of(
            decision_id,
            stored_digest,
            occurrence,
            predecessor,
        )
        if version_id != expected_version_id:
            raise DecisionIndexPersistenceError(
                f"version {version_id!r} identity mismatch"
            )
        validated = dict(raw)
        validated["_validated_revision"] = revision
        validated["_validated_statement"] = statement
        validated["_validated_rationale"] = rationale
        validated["_validated_scope"] = context_scope
        validated["_validated_constraints"] = constraints
        validated["_validated_anti_patterns"] = anti_patterns
        versions_by_id[version_id] = validated

    for version_id, version in versions_by_id.items():
        predecessor = version.get("supersedes_version_id")
        if predecessor is None:
            continue
        prior = versions_by_id.get(predecessor)
        if prior is None or prior.get("decision_id") != version.get("decision_id"):
            raise DecisionIndexPersistenceError(
                f"version {version_id!r} has invalid predecessor {predecessor!r}"
            )

    rules_by_version: dict[str, list[CanonicalRuleRecord]] = {}
    sequence_by_version: dict[str, set[int]] = {}
    binding_keys: set[tuple[str, str, str]] = set()
    for index, row in enumerate(rule_rows):
        raw = _require_dict(row, f"decision_index.rules[{index}]")
        rule_id = _require_str(
            raw.get("rule_id"),
            f"rules[{index}].rule_id",
            non_empty=True,
        )
        decision_id = _require_str(
            raw.get("decision_id"),
            f"rules[{index}].decision_id",
            non_empty=True,
        )
        decision_version_id = _require_str(
            raw.get("decision_version_id"),
            f"rules[{index}].decision_version_id",
            non_empty=True,
        )
        version = versions_by_id.get(decision_version_id)
        if version is None or version.get("decision_id") != decision_id:
            raise DecisionIndexPersistenceError(
                f"rule {rule_id!r} does not resolve to its declared decision/version"
            )
        display_version = _require_str(
            raw.get("decision_version"),
            f"rules[{index}].decision_version",
            non_empty=True,
        )
        if display_version != version["_validated_revision"]:
            raise DecisionIndexPersistenceError(
                f"rule {rule_id!r} display version disagrees with its version occurrence"
            )
        sequence = raw.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise DecisionIndexPersistenceError(
                f"rule {rule_id!r} sequence must be a non-negative integer"
            )
        used = sequence_by_version.setdefault(decision_version_id, set())
        if sequence in used:
            raise DecisionIndexPersistenceError(
                f"duplicate rule sequence {sequence} for version "
                f"{decision_version_id!r}"
            )
        used.add(sequence)
        rule_type = _require_str(
            raw.get("rule_type"),
            f"rules[{index}].rule_type",
            non_empty=True,
        )
        payload = _require_dict(
            raw.get("rule_payload"),
            f"rules[{index}].rule_payload",
        )
        if set(payload) != {"value"}:
            raise DecisionIndexPersistenceError(
                f"rule {rule_id!r} payload contains unsupported fields"
            )
        value = _require_str(
            payload.get("value"),
            f"rules[{index}].rule_payload.value",
            non_empty=True,
        )
        applicability = _require_dict(
            raw.get("applicability", {}),
            f"rules[{index}].applicability",
        )
        unknown_applicability = set(applicability) - {
            "include_paths",
            "exclude_paths",
        }
        if unknown_applicability:
            raise DecisionIndexPersistenceError(
                f"rule {rule_id!r} applicability contains unsupported fields "
                f"{sorted(unknown_applicability)}"
            )
        try:
            _ = Rule(
                type=rule_type,
                value=value,
                include_paths=(
                    tuple(
                        _str_list(
                            applicability["include_paths"],
                            "include_paths",
                        )
                    )
                    if "include_paths" in applicability
                    else None
                ),
                exclude_paths=tuple(
                    _str_list(
                        applicability.get("exclude_paths", []),
                        "exclude_paths",
                    )
                ),
            )
        except (TypeError, ValueError) as exc:
            raise DecisionIndexPersistenceError(
                f"rule {rule_id!r} is invalid: {exc}"
            ) from exc
        expected_rule_id = rule_id_of(
            decision_id,
            rule_type,
            value,
            applicability,
        )
        if rule_id != expected_rule_id:
            raise DecisionIndexPersistenceError(
                f"rule {rule_id!r} identity mismatch"
            )
        key = (decision_id, decision_version_id, rule_id)
        if key in binding_keys:
            raise DecisionIndexPersistenceError(
                f"duplicate rule binding {key!r}"
            )
        binding_keys.add(key)
        rules_by_version.setdefault(decision_version_id, []).append(
            CanonicalRuleRecord(
                rule_id=rule_id,
                decision_id=decision_id,
                decision_version=display_version,
                decision_version_id=decision_version_id,
                sequence=sequence,
                rule_type=rule_type,
                rule_payload={"value": value},
                applicability=copy.deepcopy(applicability),
            )
        )

    records: list[CanonicalDecisionRecord] = []
    all_rules: list[CanonicalRuleRecord] = []
    decision_ids: set[str] = set()
    active_versions: set[str] = set()

    for index, row in enumerate(logical_rows):
        raw = _require_dict(row, f"decision_index.decisions[{index}]")
        decision_id = _require_str(
            raw.get("decision_id"),
            f"decisions[{index}].decision_id",
            non_empty=True,
        )
        if decision_id in decision_ids:
            raise DecisionIndexPersistenceError(
                f"duplicate decision_id {decision_id!r}"
            )
        if decision_id.startswith(_RESERVED_PROPOSAL_PREFIX):
            raise DecisionIndexPersistenceError(
                f"decision id {decision_id!r} uses reserved proposal namespace"
            )
        decision_ids.add(decision_id)
        decision_class = _require_str(
            raw.get("decision_class"),
            f"decisions[{index}].decision_class",
            non_empty=True,
        )
        if decision_class != CANONICAL_DECISION_CLASS_ARCHITECTURE:
            raise DecisionIndexPersistenceError(
                f"decision {decision_id!r} has unsupported decision_class "
                f"{decision_class!r}"
            )
        lifecycle = _require_str(
            raw.get("lifecycle_status"),
            f"decisions[{index}].lifecycle_status",
            non_empty=True,
        )
        if lifecycle not in VALID_LIFECYCLE_STATUSES:
            raise DecisionIndexPersistenceError(
                f"decision {decision_id!r} has invalid lifecycle_status "
                f"{lifecycle!r}"
            )
        active_version_id = _require_str(
            raw.get("active_version_id"),
            f"decisions[{index}].active_version_id",
            non_empty=True,
        )
        if active_version_id in active_versions:
            raise DecisionIndexPersistenceError(
                f"version {active_version_id!r} is active for more than one decision"
            )
        active_versions.add(active_version_id)
        version = versions_by_id.get(active_version_id)
        if version is None or version.get("decision_id") != decision_id:
            raise DecisionIndexPersistenceError(
                f"decision {decision_id!r} active_version_id "
                f"{active_version_id!r} does not resolve to that decision"
            )
        decision_rules = sorted(
            rules_by_version.get(active_version_id, []),
            key=lambda rule: rule.sequence if rule.sequence is not None else -1,
        )
        decision_rules = [
            CanonicalRuleRecord(
                rule_id=rule.rule_id,
                decision_id=rule.decision_id,
                decision_version=rule.decision_version,
                decision_version_id=rule.decision_version_id,
                sequence=rule.sequence,
                rule_type=rule.rule_type,
                rule_payload=rule.rule_payload,
                applicability=rule.applicability,
                lifecycle_status=lifecycle,
            )
            for rule in decision_rules
        ]
        all_rules.extend(decision_rules)
        records.append(CanonicalDecisionRecord(
            decision_id=decision_id,
            version=version["_validated_revision"],
            version_id=active_version_id,
            content_digest=version["content_digest"],
            occurrence_source_identity=tuple(
                version["occurrence_source_identity"]
            ),
            decision_class=decision_class,
            statement=version["_validated_statement"],
            rationale=version["_validated_rationale"],
            lifecycle_status=lifecycle,
            decided_at=_require_str(
                version.get("created_at", ""),
                f"version {active_version_id!r} created_at",
            ),
            updated_at=_require_str(
                raw.get("updated_at", ""),
                f"decision {decision_id!r} updated_at",
            ),
            context_scope=tuple(version["_validated_scope"]),
            constraints=tuple(version["_validated_constraints"]),
            anti_patterns=tuple(version["_validated_anti_patterns"]),
            source_evidence=_parse_source_evidence(
                version.get("source_evidence", []),
                decision_id,
            ),
            test_evidence=_parse_test_evidence(
                raw.get("test_evidence", []),
                decision_id,
            ),
            relationships=_parse_relationships(
                raw.get("relationships", []),
                decision_id,
            ),
            derived_rule_ids=tuple(rule.rule_id for rule in decision_rules),
        ))

    for version_id, version in versions_by_id.items():
        if version.get("decision_id") not in decision_ids:
            raise DecisionIndexPersistenceError(
                f"orphan version {version_id!r} has no logical decision"
            )
    for version_id in rules_by_version:
        if version_id not in versions_by_id:
            raise DecisionIndexPersistenceError(
                f"orphan rule bindings target unknown version {version_id!r}"
            )

    return CanonicalArchitectureIndex(
        records=tuple(records),
        rules=tuple(all_rules),
    )


def rebuild_compatibility_snapshot(
    document: dict[str, Any],
) -> dict[str, Any]:
    """Re-project active canonical authority into deprecated decisions[]."""
    migrated = migrate_memory_document(document)
    index = load_persisted_decision_index(migrated["decision_index"])
    records_by_id = {record.decision_id: record for record in index.records}
    rows: list[dict[str, Any]] = []
    for decision in project_canonical_index(index):
        row = _snapshot_record_from_decision(decision)
        record = records_by_id[decision.id]
        if record.source_evidence:
            evidence = record.source_evidence[0]
            if evidence.source_type == "adr" and evidence.source_locator:
                row["source"] = {
                    "type": "adr",
                    "path": evidence.source_locator,
                    "sha256": evidence.source_revision,
                }
        rows.append(row)
    migrated["decisions"] = rows
    return migrated

def compatibility_snapshot_decisions(
    document: dict[str, Any],
    memory_path: Path,
) -> list[Decision]:
    """Load only persisted ``decisions[]``; never synthesize legacy items."""
    rows = _require_list(document.get("decisions", []), "decisions")
    return [
        runtime_decision_from_memory_record(row, memory_path)
        for row in rows
    ]


def verify_compatibility_snapshot(
    document: dict[str, Any],
    index: CanonicalArchitectureIndex,
    memory_path: Path,
) -> list[Decision]:
    """Fail closed if deprecation-window decisions[] diverges from projection."""
    projected = project_canonical_index(
        index,
        memory_path=str(memory_path.resolve()),
    )
    snapshot = compatibility_snapshot_decisions(document, memory_path)
    legacy_item_ids = {
        record.decision_id
        for record in index.records
        if record.occurrence_source_identity[:1] == ("legacy-items",)
    }
    for decision in snapshot:
        if decision.id in legacy_item_ids:
            decision.memory_path = ""
    if snapshot != projected:
        raise DecisionIndexPersistenceError(
            "persisted decisions[] compatibility snapshot diverges from "
            "authoritative decision_index projection"
        )
    return projected



def load_decision_index_from_memory_file(
    path: str | Path,
) -> CanonicalArchitectureIndex:
    """Load the authoritative persisted index from project memory, read-only.

    Section-less pre-D1 memory is not adapted here: canonical consumers must
    never reconstruct a second authority from the compatibility snapshot.
    """
    memory_path = Path(path)
    with open(memory_path, encoding="utf-8") as handle:
        document = json.load(handle)
    if not isinstance(document, dict):
        raise DecisionIndexPersistenceError("project memory must be an object")
    if "decision_index" not in document:
        raise DecisionIndexPersistenceError(
            "project memory has no authoritative decision_index section"
        )
    index = load_persisted_decision_index(document["decision_index"])
    verify_compatibility_snapshot(document, index, memory_path)
    return index


def migrate_memory_file(path: str | Path) -> bool:
    """Atomically add D1B canonical persistence to one pre-D1 memory file.

    Returns ``True`` when a migration write occurred and ``False`` for an
    already-migrated, valid file. A second call performs no write, preserving
    the exact bytes produced by the first call.
    """
    memory_path = Path(path)
    with open(memory_path, encoding="utf-8") as handle:
        document = json.load(handle)
    if "decision_index" in document:
        index = load_persisted_decision_index(document["decision_index"])
        verify_compatibility_snapshot(document, index, memory_path)
        return False

    migrated = migrate_memory_document(document)
    index = load_persisted_decision_index(migrated["decision_index"])
    verify_compatibility_snapshot(migrated, index, memory_path)

    rendered = json.dumps(
        migrated,
        indent=2,
        ensure_ascii=False,
    ) + "\n"
    tmp_path = memory_path.with_name(memory_path.name + ".d1b.tmp")
    try:
        tmp_path.write_text(rendered, encoding="utf-8")
        os.replace(tmp_path, memory_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return True


__all__ = [
    "DECISION_INDEX_SCHEMA",
    "NO_PREDECESSOR",
    "DecisionIndexPersistenceError",
    "LegacyDecisionsWriteRefused",
    "append_initial_canonical_decision",
    "compatibility_snapshot_decisions",
    "content_digest_of",
    "legacy_item_to_runtime_decision",
    "load_decision_index_from_memory_file",
    "load_persisted_decision_index",
    "migrate_memory_document",
    "migrate_memory_file",
    "rebind_legacy_initial_occurrence",
    "refuse_legacy_decisions_write",
    "rule_id_of",
    "runtime_decision_from_memory_record",
    "verify_compatibility_snapshot",
    "version_id_of",
]
