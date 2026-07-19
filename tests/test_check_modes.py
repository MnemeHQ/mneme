"""Tests for --mode flag on `mneme check`.

Covers:
  - strict mode (explicit): PASS→0, WARN→1, FAIL→2
  - warn mode:              PASS→0, WARN→0, FAIL→0
  - default mode:           must be strict (regression)
  - warn mode still prints verdict (not silent)
  - invalid mode is rejected by the parser
"""
import json
from pathlib import Path

import pytest

from mneme.cli import main


# ── shared helpers ────────────────────────────────────────────────────────────

def _memory(tmp_path: Path) -> Path:
    mem = tmp_path / "project_memory.json"
    mem.write_text(json.dumps({
        "meta": {"name": "t", "description": "t"},
        "items": [], "examples": [],
        "decisions": [
            {
                "id": "storage_json",
                "decision": "Use JSON storage only",
                "rationale": "local-first",
                "scope": ["storage"],
                "constraints": ["no postgres"],
                "anti_patterns": ["introduce ORM"],
                "created_at": "2026-04-24T00:00:00Z",
                "updated_at": "2026-04-24T00:00:00Z",
            },
        ],
    }))
    return mem


def _input(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "prompt.txt"
    p.write_text(content, encoding="utf-8")
    return p


# Canonical inputs for each verdict ─────────────────────────────────────────
# PASS: no forbidden terms
_PASS_TEXT = "Store everything as flat JSON files on disk."
# WARN: mentions a term from a 'no X' constraint, no anti-pattern
_WARN_TEXT = "Should we use postgres for the storage backend?"
# FAIL: contains a term from anti_patterns
_FAIL_TEXT = "Let us introduce an ORM for the storage layer."


# ── strict mode (explicit) ────────────────────────────────────────────────────

def test_strict_mode_pass_exits_zero(tmp_path):
    mem = _memory(tmp_path)
    inp = _input(tmp_path, _PASS_TEXT)
    code = main(["check", "--memory", str(mem), "--input", str(inp),
                 "--query", "storage", "--mode", "strict"])
    assert code == 0


def test_strict_mode_warn_exits_one(tmp_path):
    mem = _memory(tmp_path)
    inp = _input(tmp_path, _WARN_TEXT)
    code = main(["check", "--memory", str(mem), "--input", str(inp),
                 "--query", "storage", "--mode", "strict"])
    assert code == 1


def test_strict_mode_fail_exits_two(tmp_path):
    mem = _memory(tmp_path)
    inp = _input(tmp_path, _FAIL_TEXT)
    code = main(["check", "--memory", str(mem), "--input", str(inp),
                 "--query", "storage", "--mode", "strict"])
    assert code == 2


# ── warn mode ─────────────────────────────────────────────────────────────────

def test_warn_mode_pass_exits_zero(tmp_path):
    mem = _memory(tmp_path)
    inp = _input(tmp_path, _PASS_TEXT)
    code = main(["check", "--memory", str(mem), "--input", str(inp),
                 "--query", "storage", "--mode", "warn"])
    assert code == 0


def test_warn_mode_warn_exits_zero(tmp_path):
    mem = _memory(tmp_path)
    inp = _input(tmp_path, _WARN_TEXT)
    code = main(["check", "--memory", str(mem), "--input", str(inp),
                 "--query", "storage", "--mode", "warn"])
    assert code == 0


def test_warn_mode_fail_exits_zero(tmp_path):
    mem = _memory(tmp_path)
    inp = _input(tmp_path, _FAIL_TEXT)
    code = main(["check", "--memory", str(mem), "--input", str(inp),
                 "--query", "storage", "--mode", "warn"])
    assert code == 0


# ── default mode is strict (regression guard) ─────────────────────────────────

def test_default_mode_fail_exits_two(tmp_path):
    """No --mode flag → defaults to strict → FAIL exits 2."""
    mem = _memory(tmp_path)
    inp = _input(tmp_path, _FAIL_TEXT)
    code = main(["check", "--memory", str(mem), "--input", str(inp),
                 "--query", "storage"])
    assert code == 2


def test_default_mode_warn_exits_one(tmp_path):
    """No --mode flag → defaults to strict → WARN exits 1."""
    mem = _memory(tmp_path)
    inp = _input(tmp_path, _WARN_TEXT)
    code = main(["check", "--memory", str(mem), "--input", str(inp),
                 "--query", "storage"])
    assert code == 1


def test_default_mode_pass_exits_zero(tmp_path):
    """No --mode flag → defaults to strict → PASS exits 0."""
    mem = _memory(tmp_path)
    inp = _input(tmp_path, _PASS_TEXT)
    code = main(["check", "--memory", str(mem), "--input", str(inp),
                 "--query", "storage"])
    assert code == 0


# ── warn mode still prints verdict ───────────────────────────────────────────

def test_warn_mode_prints_fail_verdict(tmp_path, capsys):
    """warn mode exits 0 on FAIL but still prints the FAIL verdict."""
    mem = _memory(tmp_path)
    inp = _input(tmp_path, _FAIL_TEXT)
    main(["check", "--memory", str(mem), "--input", str(inp),
          "--query", "storage", "--mode", "warn"])
    out = capsys.readouterr().out
    assert "FAIL" in out


def test_warn_mode_prints_warn_verdict(tmp_path, capsys):
    """warn mode exits 0 on WARN but still prints the WARN verdict."""
    mem = _memory(tmp_path)
    inp = _input(tmp_path, _WARN_TEXT)
    main(["check", "--memory", str(mem), "--input", str(inp),
          "--query", "storage", "--mode", "warn"])
    out = capsys.readouterr().out
    assert "WARN" in out


def test_warn_mode_prints_pass_verdict(tmp_path, capsys):
    mem = _memory(tmp_path)
    inp = _input(tmp_path, _PASS_TEXT)
    main(["check", "--memory", str(mem), "--input", str(inp),
          "--query", "storage", "--mode", "warn"])
    out = capsys.readouterr().out
    assert "PASS" in out


# ── invalid mode is rejected ──────────────────────────────────────────────────

def test_invalid_mode_is_rejected(tmp_path):
    """Passing an unknown --mode value must cause argparse to exit non-zero."""
    mem = _memory(tmp_path)
    inp = _input(tmp_path, _PASS_TEXT)
    with pytest.raises(SystemExit) as exc:
        main(["check", "--memory", str(mem), "--input", str(inp),
              "--query", "storage", "--mode", "yolo"])
    assert exc.value.code != 0
