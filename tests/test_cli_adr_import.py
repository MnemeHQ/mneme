# tests/test_cli_adr_import.py
"""CLI integration tests for `mneme adr import`."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mneme.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def _seed_empty_memory(path: Path) -> None:
    path.write_text(json.dumps({
        "meta": {"name": "test", "description": "test", "version": "1.0.0", "owner": "test", "created": "2026-01-01"},
        "items": [], "examples": [], "decisions": [],
    }), encoding="utf-8")


def test_adr_import_dry_run_prints_preview_and_does_not_write(tmp_path, capsys):
    target = tmp_path / "project_memory.json"
    _seed_empty_memory(target)
    before = target.read_text(encoding="utf-8")

    rc = main([
        "adr", "import",
        str(FIXTURES / "adrs_import_basic"),
        "--memory", str(target),
        "--dry-run",
    ])

    assert rc == 0
    out = capsys.readouterr().out
    assert "ADR import preview" in out
    assert "ADR-101" in out
    assert "no mongodb" in out
    # Target file is byte-for-byte unchanged
    assert target.read_text(encoding="utf-8") == before


def test_adr_import_default_is_dry_run(tmp_path):
    """Without --apply or --dry-run, behavior must match --dry-run."""
    target = tmp_path / "project_memory.json"
    _seed_empty_memory(target)
    before = target.read_text(encoding="utf-8")

    rc = main([
        "adr", "import",
        str(FIXTURES / "adrs_import_basic"),
        "--memory", str(target),
    ])

    assert rc == 0
    assert target.read_text(encoding="utf-8") == before


def test_adr_import_apply_writes_decisions(tmp_path):
    target = tmp_path / "project_memory.json"
    _seed_empty_memory(target)

    rc = main([
        "adr", "import",
        str(FIXTURES / "adrs_import_basic"),
        "--memory", str(target),
        "--apply",
    ])

    assert rc == 0
    persisted = json.loads(target.read_text(encoding="utf-8"))
    ids = [d["id"] for d in persisted["decisions"]]
    assert ids == ["ADR-101", "ADR-102"]


def test_adr_import_apply_refuses_collision_without_update_existing(tmp_path, capsys):
    target = tmp_path / "project_memory.json"
    target.write_text(
        (FIXTURES / "memory_for_import_collision.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    before = target.read_text(encoding="utf-8")

    rc = main([
        "adr", "import",
        str(FIXTURES / "adrs_import_basic"),
        "--memory", str(target),
        "--apply",
    ])

    assert rc == 2
    err = capsys.readouterr().err
    assert "ADR-101" in err
    assert "--update-existing" in err
    # Target is unchanged
    assert target.read_text(encoding="utf-8") == before


def test_adr_import_apply_with_update_existing_overwrites(tmp_path):
    target = tmp_path / "project_memory.json"
    target.write_text(
        (FIXTURES / "memory_for_import_collision.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    rc = main([
        "adr", "import",
        str(FIXTURES / "adrs_import_basic"),
        "--memory", str(target),
        "--apply",
        "--update-existing",
    ])

    assert rc == 0
    persisted = json.loads(target.read_text(encoding="utf-8"))
    by_id = {d["id"]: d for d in persisted["decisions"]}
    assert by_id["ADR-101"]["decision"] == "No MongoDB"


def test_adr_import_apply_refuses_active_active_without_approve(tmp_path, capsys):
    target = tmp_path / "project_memory.json"
    _seed_empty_memory(target)

    rc = main([
        "adr", "import",
        str(FIXTURES / "adrs_import_with_conflicts"),
        "--memory", str(target),
        "--apply",
    ])

    assert rc == 2
    err = capsys.readouterr().err
    assert "active-active" in err.lower() or "Active-active" in err
    assert "--approve-conflicts" in err


def test_adr_import_dry_run_returns_nonzero_on_diagnostics(tmp_path):
    """Dry-run with diagnostics still surfaces a nonzero exit (signals to CI)."""
    target = tmp_path / "project_memory.json"
    _seed_empty_memory(target)

    rc = main([
        "adr", "import",
        str(FIXTURES / "adrs_import_with_conflicts"),
        "--memory", str(target),
        "--dry-run",
    ])
    # 1 = warn (matches existing `mneme check --mode strict` warn convention)
    assert rc == 1
