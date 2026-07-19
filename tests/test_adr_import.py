# tests/test_adr_import.py
"""Tests for the ADR import flow (graph projection, conflicts, persistence)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mneme.adr_import import DecisionNode, project_decision_graph
from mneme.adr_parser import parse_adr_directory

FIXTURES = Path(__file__).parent / "fixtures"


def test_project_decision_graph_returns_active_superseded_deprecated():
    adrs = parse_adr_directory(FIXTURES / "adrs_import_basic")
    nodes = project_decision_graph(adrs)
    by_id = {n.id: n for n in nodes}

    # ADR-101 is accepted and not superseded -> "active"
    assert by_id["ADR-101"].status == "active"
    assert by_id["ADR-101"].supersedes == []
    assert by_id["ADR-101"].superseded_by is None

    # ADR-102 is accepted and not superseded -> "active"
    assert by_id["ADR-102"].status == "active"

    # ADR-103 has status=superseded in its frontmatter -> "superseded"
    assert by_id["ADR-103"].status == "superseded"


def test_project_decision_graph_derives_superseded_by_from_supersedes():
    adrs = parse_adr_directory(FIXTURES / "adrs_e2e_clean")
    nodes = project_decision_graph(adrs)
    by_id = {n.id: n for n in nodes}

    # ADR-012 supersedes ADR-011 -> ADR-011.superseded_by == "ADR-012",
    # and ADR-011 status flips to "superseded" even though its frontmatter
    # says "accepted" (the active-set semantics dominate).
    assert by_id["ADR-011"].superseded_by == "ADR-012"
    assert by_id["ADR-011"].status == "superseded"
    assert by_id["ADR-012"].supersedes == ["ADR-011"]
    assert by_id["ADR-012"].status == "active"


def test_project_decision_graph_proposed_status_marked_inactive():
    """ADR-013 in adrs_e2e_clean is status=proposed -> not active."""
    adrs = parse_adr_directory(FIXTURES / "adrs_e2e_clean")
    nodes = project_decision_graph(adrs)
    by_id = {n.id: n for n in nodes}
    # We render proposed as "inactive" to keep the graph status enum to
    # exactly {active, superseded, deprecated, inactive}. The user's spec
    # named three; "inactive" carries the proposed/draft case.
    assert by_id["ADR-013"].status == "inactive"


def test_detect_collisions_same_id_in_decisions():
    from mneme.adr_import import detect_collisions, DecisionNode

    target_memory = json.loads(
        (FIXTURES / "memory_for_import_collision.json").read_text(encoding="utf-8")
    )
    incoming = [DecisionNode(id="ADR-101", status="active")]

    collisions = detect_collisions(incoming, target_memory)
    assert len(collisions) == 1
    assert collisions[0].kind == "same_id"
    assert collisions[0].adr_id == "ADR-101"
    assert collisions[0].existing_in == "decisions"


def test_detect_collisions_same_id_in_items():
    from mneme.adr_import import detect_collisions, DecisionNode

    target_memory = {
        "meta": {"name": "x", "description": "x", "version": "1.0.0", "owner": "x", "created": "2026-01-01"},
        "items": [{"id": "ADR-555", "type": "rule", "title": "manual rule", "content": "x", "tags": [], "priority": "medium"}],
        "examples": [],
        "decisions": [],
    }
    incoming = [DecisionNode(id="ADR-555", status="active")]

    collisions = detect_collisions(incoming, target_memory)
    assert collisions[0].existing_in == "items"


def test_detect_collisions_returns_empty_when_no_overlap():
    from mneme.adr_import import detect_collisions, DecisionNode

    target_memory = json.loads(
        (FIXTURES / "memory_for_import_collision.json").read_text(encoding="utf-8")
    )
    incoming = [DecisionNode(id="ADR-999", status="active")]
    assert detect_collisions(incoming, target_memory) == []


def test_compile_for_import_surfaces_precedence_ambiguity_as_diagnostic():
    """Active-active scope tie should be a loud diagnostic, not a raise."""
    from mneme.adr_import import compile_for_import

    report = compile_for_import(FIXTURES / "adrs_import_with_conflicts")
    # The compile completes (no raise), but a diagnostic is recorded.
    assert any(d.kind == "active_active_contradiction" for d in report.diagnostics)
    # Active-set should be empty because precedence couldn't pick — we don't
    # silently pick a winner.
    assert report.active_nodes == []


def test_compile_for_import_clean_corpus_has_no_diagnostics():
    from mneme.adr_import import compile_for_import

    report = compile_for_import(FIXTURES / "adrs_import_basic")
    assert report.diagnostics == []
    active_ids = {n.id for n in report.active_nodes}
    assert active_ids == {"ADR-101", "ADR-102"}


def test_format_preview_lists_active_nodes_and_constraints():
    from mneme.adr_import import compile_for_import, format_preview

    report = compile_for_import(FIXTURES / "adrs_import_basic")
    out = format_preview(report, collisions=[])

    # Header
    assert "ADR import preview" in out
    # Active set
    assert "ADR-101" in out
    assert "ADR-102" in out
    # Status projection (not the raw "accepted")
    assert "active" in out
    # The "no mongodb" constraint (FORBID_DEPENDENCY bridge)
    assert "no mongodb" in out
    # ADR-103 is superseded -> shown but flagged
    assert "ADR-103" in out
    assert "superseded" in out


def test_format_preview_includes_collision_diagnostics():
    from mneme.adr_import import (
        compile_for_import,
        detect_collisions,
        format_preview,
    )

    report = compile_for_import(FIXTURES / "adrs_import_basic")
    target = json.loads(
        (FIXTURES / "memory_for_import_collision.json").read_text(encoding="utf-8")
    )
    collisions = detect_collisions(report.active_nodes, target)

    out = format_preview(report, collisions=collisions)
    assert "Conflicts" in out
    assert "ADR-101" in out
    assert "--update-existing" in out


def test_format_preview_shows_active_active_contradiction_block():
    from mneme.adr_import import compile_for_import, format_preview

    report = compile_for_import(FIXTURES / "adrs_import_with_conflicts")
    out = format_preview(report, collisions=[])
    assert "Active-active contradiction" in out
    assert "--approve-conflicts" in out


def test_apply_import_appends_decisions_to_target_memory(tmp_path):
    """Persistence path: clean corpus + clean target -> appended decisions[]."""
    from mneme.adr_import import apply_import, compile_for_import

    # Set up an empty target
    target = tmp_path / "project_memory.json"
    target.write_text(json.dumps({
        "meta": {"name": "test", "description": "test", "version": "1.0.0", "owner": "test", "created": "2026-01-01"},
        "items": [], "examples": [], "decisions": [],
    }), encoding="utf-8")

    report = compile_for_import(FIXTURES / "adrs_import_basic")
    written_ids = apply_import(report, target_path=target, allow_update=False)

    assert written_ids == ["ADR-101", "ADR-102"]
    persisted = json.loads(target.read_text(encoding="utf-8"))
    persisted_ids = [d["id"] for d in persisted["decisions"]]
    assert persisted_ids == ["ADR-101", "ADR-102"]
    # Constraints make the round-trip
    by_id = {d["id"]: d for d in persisted["decisions"]}
    assert "no mongodb" in by_id["ADR-101"]["constraints"]


def test_apply_import_writes_source_provenance_block(tmp_path):
    """Each imported decision must carry a `source` block with type/path/sha256
    so `mneme.adr_freshness.check_freshness` can detect drift later.
    """
    import hashlib
    from mneme.adr_import import apply_import, compile_for_import

    target = tmp_path / "project_memory.json"
    target.write_text(json.dumps({
        "meta": {"name": "test", "description": "test"},
        "items": [], "examples": [], "decisions": [],
    }), encoding="utf-8")

    report = compile_for_import(FIXTURES / "adrs_import_basic")
    apply_import(report, target_path=target, allow_update=False)

    persisted = json.loads(target.read_text(encoding="utf-8"))
    by_id = {d["id"]: d for d in persisted["decisions"]}

    for adr_id in ("ADR-101", "ADR-102"):
        source = by_id[adr_id].get("source")
        assert source is not None, f"{adr_id} missing source block"
        assert source["type"] == "adr"
        assert source["path"].endswith(".md")
        assert len(source["sha256"]) == 64  # SHA-256 hex digest

        # Hash must match the bytes the importer actually read from disk.
        resolved = (target.parent / source["path"]).resolve()
        expected = hashlib.sha256(resolved.read_bytes()).hexdigest()
        assert source["sha256"] == expected


def test_apply_import_refuses_overwrite_without_allow_update(tmp_path):
    """Same-id collision must block apply unless allow_update=True."""
    from mneme.adr_import import apply_import, compile_for_import

    target = tmp_path / "project_memory.json"
    # seed with a collision against ADR-101
    target.write_text((FIXTURES / "memory_for_import_collision.json").read_text(encoding="utf-8"), encoding="utf-8")

    report = compile_for_import(FIXTURES / "adrs_import_basic")
    with pytest.raises(RuntimeError, match="ADR-101.*--update-existing"):
        apply_import(report, target_path=target, allow_update=False)


def test_apply_import_overwrites_with_allow_update(tmp_path):
    """allow_update=True overwrites the colliding decisions[] entry in place."""
    from mneme.adr_import import apply_import, compile_for_import

    target = tmp_path / "project_memory.json"
    target.write_text((FIXTURES / "memory_for_import_collision.json").read_text(encoding="utf-8"), encoding="utf-8")

    report = compile_for_import(FIXTURES / "adrs_import_basic")
    written_ids = apply_import(report, target_path=target, allow_update=True)
    assert "ADR-101" in written_ids

    persisted = json.loads(target.read_text(encoding="utf-8"))
    by_id = {d["id"]: d for d in persisted["decisions"]}
    # ADR-101 was overwritten — the imported title wins
    assert by_id["ADR-101"]["decision"] == "No MongoDB"
    # No duplicate entry was created
    assert sum(1 for d in persisted["decisions"] if d["id"] == "ADR-101") == 1


def test_apply_import_refuses_when_unresolved_active_active(tmp_path):
    """If the corpus has an active-active contradiction, apply must refuse."""
    from mneme.adr_import import apply_import, compile_for_import

    target = tmp_path / "project_memory.json"
    target.write_text(json.dumps({
        "meta": {"name": "x", "description": "x", "version": "1.0.0", "owner": "x", "created": "2026-01-01"},
        "items": [], "examples": [], "decisions": [],
    }), encoding="utf-8")

    report = compile_for_import(FIXTURES / "adrs_import_with_conflicts")
    with pytest.raises(RuntimeError, match="active-active"):
        apply_import(report, target_path=target, allow_update=False, approve_conflicts=False)
