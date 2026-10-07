"""D1E5: new ``init``/``setup`` memory is canonical (ADR-030 §15).

New project memory carries an empty ``decision_index`` section from creation,
so it never passes through a temporary section-less state. This is
construction, not migration: existing files are never given the section
(``mneme decision-index migrate`` stays the only transition, ADR-030 §1), and
``init --force`` keeps its explicit reset semantics.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mneme.cli import main
from mneme.decision_index_persistence import (
    DECISION_INDEX_SCHEMA,
    apply_memory_migration,
    empty_decision_index_section,
    load_decision_index_from_memory_file,
    plan_memory_migration,
)
from mneme.memory_store import MemoryStore
from mneme.setup import run_setup
from mneme.setup_state import scaffold_project_memory
from tests.canonical_fixtures import canonical_document, migrate_memory_fixture

BASE_TS = "2026-01-01T00:00:00Z"

EMPTY_SECTION = {
    "schema": "mneme.decision-index/v1",
    "decisions": [],
    "versions": [],
    "rules": [],
}

LEGACY = {
    "meta": {"name": "d1e5", "description": "existing memory"},
    "items": [],
    "examples": [],
    "decisions": [{
        "id": "d_existing",
        "decision": "No postgres in the service layer",
        "constraints": [],
        "anti_patterns": ["postgres"],
        "created_at": BASE_TS,
        "updated_at": BASE_TS,
    }],
}


def _repo(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    return root, root / ".mneme" / "project_memory.json"


def _existing(path: Path, *, canonical: bool) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(LEGACY, indent=2) + "\n", encoding="utf-8")
    if canonical:
        assert migrate_memory_fixture(path) is True
    return path


def _raw(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _without_activation(document: dict) -> dict:
    return {key: value for key, value in document.items() if key != "activation"}


def _assert_empty_canonical(path: Path) -> dict:
    raw = _raw(path)
    assert raw["decision_index"] == EMPTY_SECTION
    assert raw["decisions"] == []
    index = load_decision_index_from_memory_file(path)  # MCP startup read
    assert index.records == ()
    assert MemoryStore(path).load().decisions == []
    return raw


# ── The shared empty-section constructor ────────────────────────────────────


def test_empty_section_matches_migration_of_empty_memory():
    empty = {"meta": {"name": "", "description": ""}, "items": [], "examples": [],
             "decisions": []}
    assert empty_decision_index_section() == canonical_document(empty)["decision_index"]
    assert empty_decision_index_section() == EMPTY_SECTION
    assert empty_decision_index_section()["schema"] == DECISION_INDEX_SCHEMA


def test_empty_section_is_fresh_on_every_call():
    first = empty_decision_index_section()
    first["decisions"].append({"mutated": True})
    second = empty_decision_index_section()
    assert second == EMPTY_SECTION
    assert second["decisions"] is not first["decisions"]


def test_scaffold_carries_the_empty_canonical_section():
    for created_by in ("mneme init", "mneme setup"):
        document = scaffold_project_memory(created_by=created_by)
        assert document["decision_index"] == EMPTY_SECTION
        assert document["decisions"] == []
        assert document["meta"]["created_by"] == created_by


# ── 1-2: fresh creation ─────────────────────────────────────────────────────


def test_fresh_init_creates_empty_canonical_memory(tmp_path, capsys):
    path = tmp_path / ".mneme" / "project_memory.json"

    assert main(["init", "--path", str(path)]) == 0

    raw = _assert_empty_canonical(path)
    assert "activation" not in raw
    assert "Created" in capsys.readouterr().out


def test_fresh_setup_creates_empty_canonical_memory_and_activation(tmp_path):
    root, path = _repo(tmp_path)

    outcome = run_setup(root=root, pairing=None)

    assert outcome.created_memory is True
    raw = _assert_empty_canonical(path)
    assert raw["activation"]["state"] == "setup"


# ── 3-4: setup on existing memory updates activation only ───────────────────


def test_setup_on_existing_sectionless_memory_never_adds_the_section(tmp_path):
    root, path = _repo(tmp_path)
    _existing(path, canonical=False)
    before = _raw(path)

    outcome = run_setup(root=root, pairing=None)

    assert outcome.created_memory is False
    after = _raw(path)
    assert "decision_index" not in after  # no implicit migration
    assert _without_activation(after) == before
    assert after["activation"]["state"] == "setup"


def test_setup_on_existing_canonical_memory_updates_activation_only(tmp_path):
    root, path = _repo(tmp_path)
    _existing(path, canonical=True)
    before = _raw(path)

    run_setup(root=root, pairing=None)

    after = _raw(path)
    assert _without_activation(after) == before
    assert after["activation"]["state"] == "setup"
    load_decision_index_from_memory_file(path)


# ── 5-7: init on an existing file ───────────────────────────────────────────


@pytest.mark.parametrize("canonical", [False, True], ids=["section-less", "canonical"])
def test_init_without_force_still_refuses_an_existing_file(tmp_path, canonical, capsys):
    path = _existing(tmp_path / ".mneme" / "project_memory.json", canonical=canonical)
    before = path.read_bytes()

    assert main(["init", "--path", str(path)]) == 1

    assert "already exists" in capsys.readouterr().out
    assert path.read_bytes() == before


@pytest.mark.parametrize("canonical", [False, True], ids=["section-less", "canonical"])
def test_init_force_resets_to_fresh_empty_canonical_memory(tmp_path, canonical):
    # Explicit, user-authorized destructive reset (unchanged semantics); the
    # reset target is now fresh canonical memory.
    path = _existing(tmp_path / ".mneme" / "project_memory.json", canonical=canonical)

    assert main(["init", "--path", str(path), "--force"]) == 0

    raw = _assert_empty_canonical(path)
    assert raw["meta"]["created_by"] == "mneme init"


# ── 8-9: new memory works without migration ─────────────────────────────────


def test_init_add_decision_check_works_without_migration(tmp_path):
    path = tmp_path / ".mneme" / "project_memory.json"
    assert main(["init", "--path", str(path)]) == 0

    assert main([
        "add_decision", "--memory", str(path),
        "--id", "config-format", "--decision", "Use JSON for configuration files",
        "--scope", "config", "--anti-pattern", "yaml",
    ]) == 0

    (version,) = _raw(path)["decision_index"]["versions"]
    assert version["occurrence_source_identity"] == ["cli-add", "config-format"]
    probe = tmp_path / "input.txt"
    probe.write_text("switch the config files to yaml\n", encoding="utf-8")
    assert main([
        "check", "--memory", str(path), "--input", str(probe),
        "--query", "config format", "--mode", "strict",
    ]) == 2


def test_setup_add_decision_and_canonical_readers_work_without_migration(tmp_path):
    root, path = _repo(tmp_path)
    run_setup(root=root, pairing=None)

    assert main([
        "add_decision", "--memory", str(path),
        "--id", "config-format", "--decision", "Use JSON for configuration files",
        "--anti-pattern", "yaml",
    ]) == 0

    index = load_decision_index_from_memory_file(path)
    assert [record.decision_id for record in index.records] == ["config-format"]
    assert [d.id for d in MemoryStore(path).load().decisions] == ["config-format"]
    assert main(["list_decisions", "--memory", str(path)]) == 0
    assert main(["protect", "list", "--memory", str(path)]) == 0


# ── 10: migrate on newly created memory is a no-op ──────────────────────────


@pytest.mark.parametrize("creator", ["init", "setup"])
def test_migrate_reports_new_memory_as_already_canonical(tmp_path, capsys, creator):
    if creator == "init":
        path = tmp_path / ".mneme" / "project_memory.json"
        assert main(["init", "--path", str(path)]) == 0
    else:
        root, path = _repo(tmp_path)
        run_setup(root=root, pairing=None)
    before = path.read_bytes()
    capsys.readouterr()

    assert apply_memory_migration(plan_memory_migration(path)) is False
    assert main(["decision-index", "migrate", "--memory", str(path)]) == 0
    assert main(["decision-index", "migrate", "--memory", str(path), "--apply"]) == 0

    assert "Already migrated" in capsys.readouterr().out
    assert path.read_bytes() == before
