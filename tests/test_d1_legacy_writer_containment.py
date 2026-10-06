"""D1 containment: legacy decisions[] writers refuse canonical memory.

Once the top-level ``decision_index`` section exists, the merged D1B/D1C
loader treats it as the durable decision authority and ``decisions[]`` as a
derived compatibility snapshot. The remaining legacy writer
(``eventcatalog import --apply``) must refuse such files before any mutation,
leave them byte-identical, and keep section-less legacy files behaving as
before.

``adr import --apply`` (since D1D), ``protect activate`` (since D1E2b), and
``add_decision`` (since D1E3) are no longer legacy writers on canonical
memory: they are canonical authority writers, pinned in
``tests/test_adr_import.py``, ``tests/test_d1e2b_canonical_protect.py``, and
``tests/test_d1e3_canonical_add_decision.py``. Section-less protection and
``add_decision`` keep their legacy writes until D1E5 (pinned below).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mneme.cli import main
from mneme.decision_index_persistence import (
    LegacyDecisionsWriteRefused,
    migrate_memory_file,
    refuse_legacy_decisions_write,
)
from mneme.integrations.eventcatalog import apply_import as ec_apply_import
from mneme.integrations.eventcatalog import compile_for_import as ec_compile_for_import
from mneme.memory_store import MemoryStore
from mneme.protection import activate_protection

FIXTURES = Path(__file__).parent / "fixtures"
EC_FIXTURES = FIXTURES / "eventcatalog_import"

BASE_TS = "2026-01-01T00:00:00Z"

REFUSAL_TEXT = "legacy decisions[] writer"

READY_DECISION = {
    "id": "d_ready",
    "decision": "No postgres in the service layer",
    "constraints": [],
    "anti_patterns": ["postgres"],
    "created_at": BASE_TS,
    "updated_at": BASE_TS,
}

SETUP_ACTIVATION = {
    "schema": "mneme.setup/v1",
    "state": "setup",
    "mneme_version": "0.6.0",
    "setup_started_at": BASE_TS,
    "setup_completed_at": BASE_TS,
    "activated_at": None,
    "audit_ref": "",
    "baseline": None,
    "integrations_detected": [],
    "integrations_configured": [],
    "enforcement": "not_enabled",
}


def _write_memory(
    path: Path,
    decisions: list[dict] | None = None,
    activation: dict | None = None,
) -> Path:
    document: dict = {
        "meta": {"name": "d1", "description": "D1 containment fixture"},
        "items": [],
        "examples": [],
        "decisions": list(decisions or []),
    }
    if activation is not None:
        document["activation"] = activation
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


def _canonical_memory(path: Path, **kwargs) -> Path:
    _write_memory(path, **kwargs)
    assert migrate_memory_file(path) is True
    assert "decision_index" in json.loads(path.read_text(encoding="utf-8"))
    return path


def _assert_refused_unchanged(path: Path, before: bytes) -> None:
    assert path.read_bytes() == before
    # A refused write leaves no decisions[] / decision_index divergence.
    MemoryStore(path).load()


# ── Shared guard ─────────────────────────────────────────────────────────────


def test_guard_refuses_when_decision_index_is_present():
    with pytest.raises(LegacyDecisionsWriteRefused) as excinfo:
        refuse_legacy_decisions_write(
            {"decisions": [], "decision_index": {}},
            operation="some legacy writer",
        )
    message = str(excinfo.value)
    assert "some legacy writer" in message
    assert REFUSAL_TEXT in message
    assert "Nothing was written" in message


def test_guard_is_keyed_only_on_section_presence():
    # Section presence alone decides; content validity is not consulted.
    with pytest.raises(LegacyDecisionsWriteRefused):
        refuse_legacy_decisions_write(
            {"decision_index": None}, operation="x"
        )
    refuse_legacy_decisions_write({"decisions": []}, operation="x")
    refuse_legacy_decisions_write({}, operation="x")


# ── add_decision ─────────────────────────────────────────────────────────────


def test_add_decision_on_legacy_memory_is_unchanged(tmp_path, capsys):
    memory = _write_memory(tmp_path / "project_memory.json")

    code = main([
        "add_decision", "--memory", str(memory),
        "--id", "d_new", "--decision", "Something new",
    ])

    assert code == 0
    assert "Added decision [d_new]" in capsys.readouterr().out
    raw = json.loads(memory.read_text(encoding="utf-8"))
    assert "decision_index" not in raw
    assert [d["id"] for d in raw["decisions"]] == ["d_new"]


# ── protection activation ────────────────────────────────────────────────────


def _repo(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    return root, root / ".mneme" / "project_memory.json"


def test_protection_on_legacy_memory_is_unchanged(tmp_path):
    root, memory = _repo(tmp_path)
    _write_memory(memory, decisions=[READY_DECISION], activation=SETUP_ACTIVATION)

    outcome = activate_protection("d_ready", memory, repo_root=root)

    assert outcome.result == "verified"
    assert outcome.rule_installed is True
    raw = json.loads(memory.read_text(encoding="utf-8"))
    assert "decision_index" not in raw
    assert raw["decisions"][0]["rules"] == [
        {"type": "FORBID_LITERAL", "value": "postgres"}
    ]
    assert raw["activation"]["state"] == "active"


# ── eventcatalog import --apply ──────────────────────────────────────────────


def test_eventcatalog_import_apply_refuses_canonical_memory(tmp_path):
    memory = _canonical_memory(tmp_path / "project_memory.json")
    before = memory.read_bytes()
    report = ec_compile_for_import(EC_FIXTURES / "index.json", EC_FIXTURES)

    with pytest.raises(RuntimeError) as excinfo:
        ec_apply_import(report, target_path=memory, catalog_root=EC_FIXTURES)

    assert "mneme eventcatalog import --apply" in str(excinfo.value)
    assert REFUSAL_TEXT in str(excinfo.value)
    _assert_refused_unchanged(memory, before)


def test_eventcatalog_import_apply_cli_refuses_canonical_memory(tmp_path, capsys):
    memory = _canonical_memory(tmp_path / "project_memory.json")
    before = memory.read_bytes()

    code = main([
        "eventcatalog", "import",
        "--index", str(EC_FIXTURES / "index.json"),
        "--catalog-root", str(EC_FIXTURES),
        "--memory", str(memory),
        "--apply",
    ])
    captured = capsys.readouterr()

    assert code == 2
    assert REFUSAL_TEXT in captured.err
    assert "Wrote" not in captured.out
    _assert_refused_unchanged(memory, before)


def test_eventcatalog_import_apply_on_legacy_memory_is_unchanged(tmp_path):
    memory = _write_memory(tmp_path / "project_memory.json")
    report = ec_compile_for_import(EC_FIXTURES / "index.json", EC_FIXTURES)

    written = ec_apply_import(report, target_path=memory, catalog_root=EC_FIXTURES)

    assert written
    raw = json.loads(memory.read_text(encoding="utf-8"))
    assert "decision_index" not in raw
    assert [d["id"] for d in raw["decisions"]] == written
