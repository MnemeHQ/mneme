# tests/test_eventcatalog_import.py
"""Tests for the EventCatalog import flow."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mneme.integrations.eventcatalog import (
    EventCatalogImportReport,
    compile_for_import,
    detect_collisions,
    format_preview,
    apply_import,
)

FIXTURES = Path(__file__).parent / "fixtures" / "eventcatalog_import"


def test_compile_for_import_active_only():
    """Only accepted ADRs without supersededBy should be active."""
    report = compile_for_import(FIXTURES / "index.json", FIXTURES)

    active = [n for n in report.nodes if n.status == "active"]
    active_ids = {n.id for n in active}

    assert active_ids == {"choose-kafka"}
    assert len(report.decisions) == 1
    assert report.decisions[0].id == "ec-choose-kafka"


def test_compile_for_import_proposed_excluded():
    """Proposed ADRs should not be in active set."""
    report = compile_for_import(FIXTURES / "index.json", FIXTURES)

    proposed = [n for n in report.nodes if n.id == "use-postgres"]
    assert len(proposed) == 1
    assert proposed[0].status == "inactive"


def test_compile_for_import_superseded_excluded():
    """Explicitly superseded ADRs should not be in active set."""
    report = compile_for_import(FIXTURES / "index.json", FIXTURES)

    superseded = [n for n in report.nodes if n.id == "use-rabbitmq"]
    assert len(superseded) == 1
    assert superseded[0].status == "superseded"


def test_compile_for_import_accepted_but_superseded_by_excluded():
    """Accepted ADRs with supersededBy should not be active."""
    report = compile_for_import(FIXTURES / "index.json", FIXTURES)

    superseded = [n for n in report.nodes if n.id == "accepted-but-superseded"]
    assert len(superseded) == 1
    assert superseded[0].status == "superseded"
    assert superseded[0].superseded_by == "choose-kafka"


def test_decision_mapping_correct():
    """Decision fields should map correctly from EventCatalog ADR."""
    report = compile_for_import(FIXTURES / "index.json", FIXTURES)
    decision = report.decisions[0]

    assert decision.id == "ec-choose-kafka"
    assert "Apache Kafka" in decision.decision
    assert "event streaming platform" in decision.rationale
    assert "orders domain" in decision.scope
    assert "payment-service" in decision.scope
    assert "payment-accepted" in decision.scope
    assert decision.constraints == []
    assert decision.anti_patterns == []
    assert decision.rules == []
    assert decision.source_path == "adrs/choose-kafka/index.mdx"


def test_retrieval_only_diagnostic_always_present():
    """Every EventCatalog ADR should produce a retrieval-only diagnostic."""
    report = compile_for_import(FIXTURES / "index.json", FIXTURES)

    retrieval_diags = [d for d in report.diagnostics if d.kind == "retrieval_only"]
    assert len(retrieval_diags) == 1
    assert "retrieval-only" in retrieval_diags[0].message
    assert "constraints=[]" in retrieval_diags[0].message
    assert "anti_patterns=[]" in retrieval_diags[0].message
    assert "rules=[]" in retrieval_diags[0].message


def test_detect_collisions_same_id_in_decisions():
    target_memory = {
        "meta": {"name": "test", "description": "test", "version": "1.0.0", "owner": "test", "created": "2026-01-01"},
        "items": [], "examples": [], "decisions": [{"id": "ec-choose-kafka"}],
    }
    from mneme.integrations.eventcatalog import EventCatalogNode
    incoming = [EventCatalogNode(type="adr", id="choose-kafka", version=None, name="", status="active")]

    collisions = detect_collisions(incoming, target_memory)
    assert len(collisions) == 1
    assert collisions[0].kind == "same_id"
    assert collisions[0].node_id == "ec-choose-kafka"
    assert collisions[0].existing_in == "decisions"


def test_detect_collisions_same_id_in_items():
    target_memory = {
        "meta": {"name": "test", "description": "test", "version": "1.0.0", "owner": "test", "created": "2026-01-01"},
        "items": [{"id": "ec-choose-kafka", "type": "rule", "title": "x", "content": "x", "tags": [], "priority": "medium"}],
        "examples": [], "decisions": [],
    }
    from mneme.integrations.eventcatalog import EventCatalogNode
    incoming = [EventCatalogNode(type="adr", id="choose-kafka", version=None, name="", status="active")]

    collisions = detect_collisions(incoming, target_memory)
    assert collisions[0].existing_in == "items"


def test_format_preview_shows_active_and_scope():
    report = compile_for_import(FIXTURES / "index.json", FIXTURES)
    out = format_preview(report, collisions=[])

    assert "EventCatalog import preview" in out
    assert "ec-choose-kafka" in out
    assert "orders domain" in out
    assert "payment-service" in out
    assert "payment-accepted" in out
    assert "retrieval-only" in out


def test_apply_import_appends_decisions(tmp_path):
    """Persistence: clean corpus + clean target -> appended decisions[]."""
    target = tmp_path / "project_memory.json"
    target.write_text(json.dumps({
        "meta": {"name": "test", "description": "test", "version": "1.0.0", "owner": "test", "created": "2026-01-01"},
        "items": [], "examples": [], "decisions": [],
    }), encoding="utf-8")

    report = compile_for_import(FIXTURES / "index.json", FIXTURES)
    written_ids = apply_import(report, target_path=target, catalog_root=FIXTURES, allow_update=False)

    assert written_ids == ["ec-choose-kafka"]
    persisted = json.loads(target.read_text(encoding="utf-8"))
    persisted_ids = [d["id"] for d in persisted["decisions"]]
    assert persisted_ids == ["ec-choose-kafka"]


def test_apply_import_writes_source_provenance(tmp_path):
    """Each imported decision must carry a source block with type/path/sha256."""
    import hashlib
    target = tmp_path / "project_memory.json"
    target.write_text(json.dumps({
        "meta": {"name": "test", "description": "test"},
        "items": [], "examples": [], "decisions": [],
    }), encoding="utf-8")

    report = compile_for_import(FIXTURES / "index.json", FIXTURES)
    apply_import(report, target_path=target, catalog_root=FIXTURES, allow_update=False)

    persisted = json.loads(target.read_text(encoding="utf-8"))
    source = persisted["decisions"][0].get("source")
    assert source is not None
    assert source["type"] == "eventcatalog"
    assert source["path"] == "adrs/choose-kafka/index.mdx"
    assert len(source["sha256"]) == 64

    # Hash must match
    resolved = FIXTURES / source["path"]
    expected = hashlib.sha256(resolved.read_bytes()).hexdigest()
    assert source["sha256"] == expected


def test_apply_import_refuses_overwrite_without_allow_update(tmp_path):
    """Same-id collision must block apply unless allow_update=True."""
    target = tmp_path / "project_memory.json"
    target.write_text(json.dumps({
        "meta": {"name": "test", "description": "test", "version": "1.0.0", "owner": "test", "created": "2026-01-01"},
        "items": [], "examples": [], "decisions": [{"id": "ec-choose-kafka"}],
    }), encoding="utf-8")

    report = compile_for_import(FIXTURES / "index.json", FIXTURES)
    with pytest.raises(RuntimeError, match="same-id collision"):
        apply_import(report, target_path=target, catalog_root=FIXTURES, allow_update=False)


def test_apply_import_overwrites_with_allow_update(tmp_path):
    """allow_update=True overwrites the colliding decisions[] entry in place."""
    target = tmp_path / "project_memory.json"
    target.write_text(json.dumps({
        "meta": {"name": "test", "description": "test", "version": "1.0.0", "owner": "test", "created": "2026-01-01"},
        "items": [], "examples": [], "decisions": [{"id": "ec-choose-kafka", "decision": "old"}],
    }), encoding="utf-8")

    report = compile_for_import(FIXTURES / "index.json", FIXTURES)
    written_ids = apply_import(report, target_path=target, catalog_root=FIXTURES, allow_update=True)
    assert "ec-choose-kafka" in written_ids

    persisted = json.loads(target.read_text(encoding="utf-8"))
    by_id = {d["id"]: d for d in persisted["decisions"]}
    assert by_id["ec-choose-kafka"]["decision"] == "We will use Apache Kafka as our event streaming platform."
    assert sum(1 for d in persisted["decisions"] if d["id"] == "ec-choose-kafka") == 1


def test_repeated_import_deterministic(tmp_path):
    """Repeated imports produce identical output."""
    target = tmp_path / "project_memory.json"
    target.write_text(json.dumps({
        "meta": {"name": "test", "description": "test", "version": "1.0.0", "owner": "test", "created": "2026-01-01"},
        "items": [], "examples": [], "decisions": [],
    }), encoding="utf-8")

    report1 = compile_for_import(FIXTURES / "index.json", FIXTURES)
    report2 = compile_for_import(FIXTURES / "index.json", FIXTURES)

    # Decisions should be identical
    assert [d.id for d in report1.decisions] == [d.id for d in report2.decisions]
    assert [d.decision for d in report1.decisions] == [d.decision for d in report2.decisions]
    assert [d.scope for d in report1.decisions] == [d.scope for d in report2.decisions]

    # Apply twice with allow_update
    apply_import(report1, target_path=target, catalog_root=FIXTURES, allow_update=True)
    apply_import(report2, target_path=target, catalog_root=FIXTURES, allow_update=True)

    persisted = json.loads(target.read_text(encoding="utf-8"))
    assert len(persisted["decisions"]) == 1


def test_malformed_index_raises():
    """Malformed index should raise."""
    bad_index = FIXTURES / "bad_index.json"
    bad_index.write_text(json.dumps({"resources": "not a list"}))

    try:
        with pytest.raises(ValueError, match="EventCatalog index 'resources' must be a list"):
            compile_for_import(bad_index, FIXTURES)
    finally:
        bad_index.unlink(missing_ok=True)


def test_missing_index_raises():
    """Missing index should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        compile_for_import(FIXTURES / "nonexistent.json", FIXTURES)


def test_missing_catalog_root_raises():
    """Missing catalog root should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        compile_for_import(FIXTURES / "index.json", FIXTURES / "nonexistent")