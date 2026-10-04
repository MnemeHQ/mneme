"""D1B canonical persistence and migration tests (ADR-030, #423)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from mneme.benchmark import BenchmarkRunner
from mneme.decision_index_persistence import (
    append_canonical_version_occurrence,
    append_initial_canonical_decision,
    DECISION_INDEX_SCHEMA,
    DecisionIndexPersistenceError,
    content_digest_of,
    load_persisted_decision_index,
    migrate_memory_document,
    migrate_memory_file,
    rebuild_compatibility_snapshot,
    rule_id_of,
    version_id_of,
)
from mneme.decision_projection import project_canonical_index
from mneme.memory_store import MemoryStore
from mneme.schemas import Rule


REPO_ROOT = Path(__file__).resolve().parent.parent


class _DecisionSource:
    def __init__(self, decisions):
        self._decisions = list(decisions)

    def decisions(self):
        return list(self._decisions)


def _document(*, two_rules: bool = False) -> dict:
    rules = [{
        "type": "FORBID_LITERAL",
        "value": "pip install bad",
        "include_paths": ["src/**"],
        "exclude_paths": ["src/generated/**"],
    }]
    if two_rules:
        rules.append({
            "type": "FORBID_LITERAL",
            "value": "curl unsafe.example",
        })
    return {
        "meta": {
            "name": "d1b-test",
            "description": "D1B persistence fixture",
            "version": "1.0.0",
        },
        "items": [{
            "id": "legacy-rule",
            "type": "rule",
            "title": "Stay local",
            "content": "no external service",
            "tags": ["legacy"],
            "priority": "high",
        }],
        "examples": [],
        "decisions": [{
            "id": "dec-1",
            "decision": "Use JSON",
            "rationale": "Because",
            "scope": ["storage"],
            "constraints": ["no postgres"],
            "anti_patterns": ["ORM"],
            "rules": rules,
            "test_evidence": [{
                "selector": "tests/test_storage.py::test_json",
                "sha": "abc123",
            }],
            "created_at": "2026-09-01",
            "updated_at": "2026-09-02",
            "status": "active",
            "source": {
                "type": "adr",
                "path": "../docs/adr/dec-1.md",
                "sha256": "source-sha",
            },
        }],
    }


def _write(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    "relative_path",
    [
        ".mneme/project_memory.json",
        "examples/project_memory.json",
    ],
)
def test_real_memory_migration_projects_exact_runtime_decisions(
    relative_path: str,
) -> None:
    memory_path = REPO_ROOT / relative_path
    document = json.loads(memory_path.read_text(encoding="utf-8"))
    baseline = MemoryStore(memory_path).load().decisions
    migrated = migrate_memory_document(document)
    index = load_persisted_decision_index(migrated["decision_index"])
    projected = project_canonical_index(
        index,
        memory_path=str(memory_path.resolve()),
    )
    assert projected == baseline


def test_real_migrated_projection_preserves_frozen_benchmark_results() -> None:
    memory_path = REPO_ROOT / "examples" / "project_memory.json"
    document = json.loads(memory_path.read_text(encoding="utf-8"))
    baseline_store = MemoryStore(memory_path)
    baseline_store.load()
    baseline = BenchmarkRunner(baseline_store).run_suite(
        REPO_ROOT / "examples" / "benchmarks"
    )

    migrated = migrate_memory_document(document)
    index = load_persisted_decision_index(migrated["decision_index"])
    projected = project_canonical_index(
        index,
        memory_path=str(memory_path.resolve()),
    )
    migrated_results = BenchmarkRunner(
        _DecisionSource(projected)
    ).run_suite(REPO_ROOT / "examples" / "benchmarks")

    assert migrated_results == baseline





def test_source_evidence_rejects_proposal_fields_on_runtime_records():
    document = migrate_memory_document({
        "items": [],
        "examples": [],
        "decisions": [{
            "id": "runtime-1",
            "decision": "Keep runtime decision",
            "rationale": "",
            "scope": [],
            "constraints": [],
            "anti_patterns": [],
        }],
    })
    section = document["decision_index"]
    section["versions"][0]["source_evidence"][0]["proposal_id"] = "dprop-invalid"
    with pytest.raises(
        DecisionIndexPersistenceError,
        match="contains unsupported fields",
    ):
        load_persisted_decision_index(section)


def test_proposal_source_evidence_requires_matching_accepted_decision_id():
    document = migrate_memory_document({
        "items": [],
        "examples": [],
        "decisions": [],
    })
    document, created = append_initial_canonical_decision(
        document,
        decision_id="ddec-one",
        statement="Use canonical storage",
        rationale="Reviewed",
        context_scope=[],
        lifecycle_status="active",
        created_at="2026-10-03T00:00:00Z",
        updated_at="2026-10-03T00:00:00Z",
        occurrence_source_identity=[
            "dprop-one",
            "producer-key",
            "content-fingerprint",
        ],
        source_evidence=[{
            "source_type": "proposal",
            "source_locator": "design/review.md",
            "source_revision": "",
            "observed_at": "2026-10-03T00:00:00Z",
            "verification_status": "",
            "proposal_id": "dprop-one",
            "producer_key": "producer-key",
            "content_fingerprint": "content-fingerprint",
            "origin_classification": "ai_generated",
            "proposed_at": "2026-10-02T00:00:00Z",
            "source_reference": "design/review.md",
            "accepted_decision_id": "ddec-one",
        }],
    )
    assert created is True
    section = document["decision_index"]
    section["versions"][0]["source_evidence"][0][
        "accepted_decision_id"
    ] = "ddec-other"
    with pytest.raises(
        DecisionIndexPersistenceError,
        match="proposal provenance links to",
    ):
        load_persisted_decision_index(section)


def _evolve_decision(document: dict, predecessor: str, *, statement: str, source_sha: str):
    return append_canonical_version_occurrence(
        document,
        decision_id="dec-1",
        predecessor_version_id=predecessor,
        statement=statement,
        rationale=f"Rationale for {statement}",
        context_scope=("storage",),
        constraints=("no postgres",),
        anti_patterns=("ORM",),
        rules=[Rule(
            type="FORBID_LITERAL",
            value="pip install bad",
            include_paths=("src/**",),
            exclude_paths=("src/generated/**",),
        )],
        created_at="2026-10-04",
        updated_at="2026-10-04",
        occurrence_source_identity=("dec-1", source_sha, "adr-import"),
        source_evidence=[{
            "source_type": "adr",
            "source_locator": "../docs/adr/dec-1.md",
            "source_revision": source_sha,
            "observed_at": "",
            "verification_status": "",
        }],
    )


def test_d1d_version_occurrence_is_predecessor_bound_and_retry_is_noop():
    migrated = migrate_memory_document(_document())
    index = load_persisted_decision_index(migrated["decision_index"])
    predecessor = next(
        r.version_id for r in index.records if r.decision_id == "dec-1"
    )

    evolved, version_id, created = _evolve_decision(
        migrated, predecessor, statement="Use JSON v2", source_sha="sha-v2"
    )
    assert created is True
    assert version_id != predecessor

    retried, retry_id, retry_created = _evolve_decision(
        evolved, predecessor, statement="Use JSON v2", source_sha="sha-v2"
    )
    assert retry_created is False
    assert retry_id == version_id
    assert retried == evolved


def test_d1d_stale_new_occurrence_fails_closed():
    migrated = migrate_memory_document(_document())
    index = load_persisted_decision_index(migrated["decision_index"])
    predecessor = next(
        r.version_id for r in index.records if r.decision_id == "dec-1"
    )
    evolved, _, _ = _evolve_decision(
        migrated, predecessor, statement="Use JSON v2", source_sha="sha-v2"
    )
    with pytest.raises(DecisionIndexPersistenceError, match="stale version evolution"):
        _evolve_decision(
            evolved, predecessor, statement="Use JSON v3", source_sha="sha-v3"
        )


def test_d1d_unchanged_rule_id_rebinds_to_new_version():
    migrated = migrate_memory_document(_document())
    index = load_persisted_decision_index(migrated["decision_index"])
    predecessor = next(
        r.version_id for r in index.records if r.decision_id == "dec-1"
    )
    old_rule = index.rules_for_decision("dec-1")[0]
    evolved, version_id, _ = _evolve_decision(
        migrated, predecessor, statement="Use JSON v2", source_sha="sha-v2"
    )
    evolved_index = load_persisted_decision_index(evolved["decision_index"])
    new_rule = evolved_index.rules_for_decision("dec-1")[0]
    assert new_rule.rule_id == old_rule.rule_id
    assert new_rule.decision_version_id == version_id
    bindings = [
        row for row in evolved["decision_index"]["rules"]
        if row["rule_id"] == old_rule.rule_id
    ]
    assert {row["decision_version_id"] for row in bindings} == {
        predecessor,
        version_id,
    }


def test_d1d_rebuild_snapshot_preserves_adr_source_block():
    migrated = migrate_memory_document(_document())
    rebuilt = rebuild_compatibility_snapshot(migrated)
    row = next(d for d in rebuilt["decisions"] if d["id"] == "dec-1")
    assert row["source"] == {
        "type": "adr",
        "path": "../docs/adr/dec-1.md",
        "sha256": "source-sha",
    }

def test_identity_golden_vectors() -> None:
    digest = content_digest_of(
        "Use JSON",
        "Because",
        ["storage"],
        ["no postgres"],
        ["ORM"],
    )
    assert digest == (
        "52053ee57003414a3a4d97ee032a1fed"
        "56ae4de6cdcde8ba76241ed7fea59e7d"
    )
    assert version_id_of(
        "dec-1",
        digest,
        ["legacy-decisions", "dec-1"],
    ) == "dver-e93328da2425d5d1409adac25dceffcf"
    assert rule_id_of(
        "dec-1",
        "FORBID_LITERAL",
        "pip install bad",
        {
            "include_paths": ["src/**"],
            "exclude_paths": ["src/generated/**"],
        },
    ) == "dec-1:FORBID_LITERAL:48f5b4d61ec6f6f84cb3e847ebcf3627"


def test_migration_builds_schema_and_preserves_runtime_projection(tmp_path: Path) -> None:
    path = tmp_path / ".mneme" / "project_memory.json"
    _write(path, _document())
    before = MemoryStore(path).load().decisions

    assert migrate_memory_file(path) is True
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["decision_index"]["schema"] == DECISION_INDEX_SCHEMA

    after = MemoryStore(path).load().decisions
    assert after == before
    assert [decision.id for decision in after] == ["dec-1", "legacy-rule"]
    assert after[0].memory_path == str(path.resolve())
    assert after[1].memory_path == ""


def test_migration_is_byte_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "project_memory.json"
    _write(path, _document())

    assert migrate_memory_file(path) is True
    first = path.read_bytes()
    assert migrate_memory_file(path) is False
    assert path.read_bytes() == first


def test_document_migration_is_side_effect_free_and_structurally_idempotent() -> None:
    original = _document()
    before = copy.deepcopy(original)
    migrated = migrate_memory_document(original)
    assert original == before
    assert migrate_memory_document(migrated) == migrated
    assert not any(
        key.startswith("_validated")
        for version in migrated["decision_index"]["versions"]
        for key in version
    )


def test_native_and_legacy_item_id_collision_fails_closed() -> None:
    document = _document()
    document["items"][0]["id"] = "dec-1"
    with pytest.raises(DecisionIndexPersistenceError, match="collides"):
        migrate_memory_document(document)


def test_migration_records_adr_revision_and_occurrence_identity() -> None:
    migrated = migrate_memory_document(_document())
    [version, legacy_version] = migrated["decision_index"]["versions"]

    assert version["source_evidence"] == [{
        "source_type": "adr",
        "source_locator": "../docs/adr/dec-1.md",
        "source_revision": "source-sha",
        "observed_at": "",
        "verification_status": "",
    }]
    assert version["occurrence_source_identity"] == [
        "dec-1",
        "source-sha",
        "adr-import",
    ]
    assert legacy_version["occurrence_source_identity"] == [
        "legacy-items",
        "legacy-rule",
    ]


def test_native_without_verified_adr_revision_uses_legacy_decision_identity() -> None:
    document = _document()
    document["decisions"][0].pop("source")
    migrated = migrate_memory_document(document)
    [version, _] = migrated["decision_index"]["versions"]
    assert version["occurrence_source_identity"] == [
        "legacy-decisions",
        "dec-1",
    ]
    assert version["source_evidence"][0]["source_type"] == "runtime"


def test_adr_locator_without_revision_is_preserved_without_claiming_adr_identity(
    tmp_path: Path,
) -> None:
    document = _document()
    document["decisions"][0]["source"].pop("sha256")
    path = tmp_path / ".mneme" / "project_memory.json"
    _write(path, document)
    before_source = MemoryStore(path).load().decisions[0].source_path

    migrated = migrate_memory_document(document)
    [version, _] = migrated["decision_index"]["versions"]
    assert version["source_evidence"][0]["source_locator"] == "../docs/adr/dec-1.md"
    assert version["source_evidence"][0]["source_revision"] == ""
    assert version["occurrence_source_identity"] == [
        "legacy-decisions",
        "dec-1",
    ]

    _write(path, migrated)
    assert MemoryStore(path).load().decisions[0].source_path == before_source


def test_rule_identity_is_stable_under_reordering() -> None:
    first = _document(two_rules=True)
    second = copy.deepcopy(first)
    second["decisions"][0]["rules"].reverse()

    first_section = migrate_memory_document(first)["decision_index"]
    second_section = migrate_memory_document(second)["decision_index"]

    assert first_section["versions"][0]["version_id"] == (
        second_section["versions"][0]["version_id"]
    )
    assert {row["rule_id"] for row in first_section["rules"]} == {
        row["rule_id"] for row in second_section["rules"]
    }
    assert [row["rule_id"] for row in first_section["rules"]] != [
        row["rule_id"] for row in second_section["rules"]
    ]


def test_rule_identity_changes_when_semantics_change() -> None:
    first = migrate_memory_document(_document())["decision_index"]["rules"][0]
    changed = _document()
    changed["decisions"][0]["rules"][0]["value"] = "pip install worse"
    second = migrate_memory_document(changed)["decision_index"]["rules"][0]
    assert first["rule_id"] != second["rule_id"]


def test_duplicate_identical_rule_bindings_fail_closed() -> None:
    document = _document()
    document["decisions"][0]["rules"].append(
        copy.deepcopy(document["decisions"][0]["rules"][0])
    )
    with pytest.raises(
        DecisionIndexPersistenceError,
        match="duplicate identical rule bindings",
    ):
        migrate_memory_document(document)


def test_content_digest_corruption_fails_closed() -> None:
    section = migrate_memory_document(_document())["decision_index"]
    section["versions"][0]["statement"] = "tampered"
    with pytest.raises(DecisionIndexPersistenceError, match="content_digest mismatch"):
        load_persisted_decision_index(section)


def test_version_identity_corruption_fails_closed() -> None:
    section = migrate_memory_document(_document())["decision_index"]
    section["versions"][0]["version_id"] = "dver-" + ("0" * 32)
    section["decisions"][0]["active_version_id"] = "dver-" + ("0" * 32)
    section["rules"][0]["decision_version_id"] = "dver-" + ("0" * 32)
    with pytest.raises(DecisionIndexPersistenceError, match="identity mismatch"):
        load_persisted_decision_index(section)


def test_active_version_pointer_is_only_resolution_path() -> None:
    section = migrate_memory_document(_document())["decision_index"]
    section["decisions"][0]["active_version_id"] = "dver-" + ("f" * 32)
    with pytest.raises(
        DecisionIndexPersistenceError,
        match="active_version_id",
    ):
        load_persisted_decision_index(section)


def test_duplicate_rule_sequence_fails_closed() -> None:
    section = migrate_memory_document(_document(two_rules=True))["decision_index"]
    section["rules"][1]["sequence"] = section["rules"][0]["sequence"]
    with pytest.raises(DecisionIndexPersistenceError, match="duplicate rule sequence"):
        load_persisted_decision_index(section)


def test_rule_identity_corruption_fails_closed() -> None:
    section = migrate_memory_document(_document())["decision_index"]
    section["rules"][0]["rule_payload"]["value"] = "changed"
    with pytest.raises(DecisionIndexPersistenceError, match="rule .* identity mismatch"):
        load_persisted_decision_index(section)


def test_unknown_persisted_rule_payload_field_fails_closed() -> None:
    section = migrate_memory_document(_document())["decision_index"]
    section["rules"][0]["rule_payload"]["future"] = "unsupported"
    with pytest.raises(
        DecisionIndexPersistenceError,
        match="payload contains unsupported fields",
    ):
        load_persisted_decision_index(section)


def test_unknown_persisted_applicability_field_fails_closed() -> None:
    section = migrate_memory_document(_document())["decision_index"]
    section["rules"][0]["applicability"]["component"] = "api"
    with pytest.raises(
        DecisionIndexPersistenceError,
        match="applicability contains unsupported fields",
    ):
        load_persisted_decision_index(section)


def test_compatibility_snapshot_divergence_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "project_memory.json"
    _write(path, _document())
    assert migrate_memory_file(path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["decisions"][0]["decision"] = "snapshot diverged"
    _write(path, raw)

    with pytest.raises(DecisionIndexPersistenceError, match="snapshot diverges"):
        MemoryStore(path).load()


def test_new_legacy_item_after_migration_stays_context_only(tmp_path: Path) -> None:
    path = tmp_path / "project_memory.json"
    _write(path, _document())
    assert migrate_memory_file(path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["items"].append({
        "id": "post-migration-rule",
        "type": "rule",
        "title": "New context-only legacy item",
        "content": "do not synthesize",
        "tags": [],
        "priority": "medium",
    })
    _write(path, raw)

    store = MemoryStore(path)
    store.load()
    assert "post-migration-rule" in {item.id for item in store.rules()}
    assert "post-migration-rule" not in {
        decision.id for decision in store.decisions()
    }


def test_non_active_decision_is_retained_canonically_not_runtime_snapshot() -> None:
    document = _document()
    document["decisions"][0]["status"] = "superseded"
    migrated = migrate_memory_document(document)
    index = load_persisted_decision_index(migrated["decision_index"])

    record = next(r for r in index.records if r.decision_id == "dec-1")
    assert record.lifecycle_status == "superseded"
    assert "dec-1" not in {row["id"] for row in migrated["decisions"]}
