"""D1 containment: the shared legacy-writer guard and section-less writes.

Once the top-level ``decision_index`` section exists, the D1 loader treats it
as the durable decision authority and ``decisions[]`` as a derived
compatibility snapshot. ``refuse_legacy_decisions_write`` is the shared guard,
keyed only on section presence (pinned below).

Every writer that reaches canonical memory is now either a canonical
authority writer or retired:

- ``adr import --apply`` (D1D), ``protect activate`` (D1E2b), and
  ``add_decision`` (D1E3) are canonical writers, pinned in
  ``tests/test_adr_import.py``, ``tests/test_d1e2b_canonical_protect.py``,
  and ``tests/test_d1e3_canonical_add_decision.py``;
- ``eventcatalog import --apply`` is retired for canonical memory in D1
  (D1E4), pinned in ``tests/test_d1e4_eventcatalog_retirement.py``.

Section-less memory keeps the legacy ``add_decision``, protection, and
EventCatalog apply writes until D1E5 (pinned below).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mneme.cli import main
from mneme.decision_index_persistence import (
    LegacyDecisionsWriteRefused,
    refuse_legacy_decisions_write,
)
from mneme.integrations.eventcatalog import apply_import as ec_apply_import
from mneme.integrations.eventcatalog import compile_for_import as ec_compile_for_import
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


def test_eventcatalog_import_apply_on_legacy_memory_is_unchanged(tmp_path):
    memory = _write_memory(tmp_path / "project_memory.json")
    report = ec_compile_for_import(EC_FIXTURES / "index.json", EC_FIXTURES)

    written = ec_apply_import(report, target_path=memory, catalog_root=EC_FIXTURES)

    assert written
    raw = json.loads(memory.read_text(encoding="utf-8"))
    assert "decision_index" not in raw
    assert [d["id"] for d in raw["decisions"]] == written
