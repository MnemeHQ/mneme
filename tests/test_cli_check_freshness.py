"""CLI integration tests for ADR freshness warnings on `mneme check`.

Freshness diagnostics are warn-only: they appear in stdout with an
``ADR_<CODE>`` token so they are distinguishable from enforcement
violations, and they do NOT influence the exit code returned by
``mneme check``.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from mneme.cli import main


_ADR_TEXT_TEMPLATE = (
    "---\n"
    "id: {adr_id}\n"
    "title: Test {adr_id}\n"
    "status: accepted\n"
    "priority: normal\n"
    "date: 2026-05-01\n"
    "scope: test\n"
    "---\n\n"
    "Body.\n"
)


def _write_adr(path: Path, adr_id: str) -> str:
    text = _ADR_TEXT_TEMPLATE.format(adr_id=adr_id)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _memory(tmp_path: Path) -> Path:
    mem = tmp_path / ".mneme" / "project_memory.json"
    mem.parent.mkdir(parents=True, exist_ok=True)
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
    }), encoding="utf-8")
    return mem


def _input(tmp_path: Path, content: str = "Store everything as flat JSON.") -> Path:
    p = tmp_path / "prompt.txt"
    p.write_text(content, encoding="utf-8")
    return p


# ── --adr-dir flag wires freshness in ─────────────────────────────────────────


def test_check_emits_unimported_diagnostic(tmp_path, capsys):
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    _write_adr(adr_dir / "ADR-101-new.md", "ADR-101")

    mem = _memory(tmp_path)
    inp = _input(tmp_path)

    code = main([
        "check",
        "--memory", str(mem),
        "--input", str(inp),
        "--query", "storage",
        "--mode", "warn",
        "--adr-dir", str(adr_dir),
    ])

    out = capsys.readouterr().out
    assert "ADR_UNIMPORTED" in out
    assert "ADR-101" in out
    # Freshness is warn-only -> exit code follows enforcer verdict only.
    assert code == 0


def test_check_freshness_does_not_change_exit_code_in_strict_mode(tmp_path):
    """An unimported ADR is warn-only; with a PASS prompt, strict mode stays 0."""
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    _write_adr(adr_dir / "ADR-200-fresh.md", "ADR-200")

    mem = _memory(tmp_path)
    inp = _input(tmp_path, content="Store everything as flat JSON files.")

    code = main([
        "check",
        "--memory", str(mem),
        "--input", str(inp),
        "--query", "storage",
        "--mode", "strict",
        "--adr-dir", str(adr_dir),
    ])
    assert code == 0


def test_check_clean_when_no_freshness_issues(tmp_path, capsys):
    """When ADR dir is empty, no ADR_ tokens appear in output."""
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)  # empty

    mem = _memory(tmp_path)
    inp = _input(tmp_path)

    main([
        "check",
        "--memory", str(mem),
        "--input", str(inp),
        "--query", "storage",
        "--mode", "warn",
        "--adr-dir", str(adr_dir),
    ])

    out = capsys.readouterr().out
    assert "ADR_UNIMPORTED" not in out
    assert "ADR_CHANGED" not in out
    assert "ADR_MISSING" not in out


def test_check_without_adr_dir_default_missing_is_silent(tmp_path, capsys):
    """If --adr-dir is not provided and the default does not exist,
    freshness output is silent (preserves existing CLI behavior)."""
    mem = _memory(tmp_path)
    inp = _input(tmp_path)

    # Run from a directory that has no docs/adr/.
    import os
    cwd_before = os.getcwd()
    os.chdir(tmp_path)
    try:
        main([
            "check",
            "--memory", str(mem),
            "--input", str(inp),
            "--query", "storage",
            "--mode", "warn",
        ])
    finally:
        os.chdir(cwd_before)

    out = capsys.readouterr().out
    assert "ADR_UNIMPORTED" not in out
    assert "ADR_CHANGED" not in out
    assert "ADR_MISSING" not in out
    assert "ADR_UNPARSEABLE" not in out


def test_check_emits_unparseable_diagnostic(tmp_path, capsys):
    """An ADR-shaped file without valid frontmatter surfaces as
    ADR_UNPARSEABLE in mneme check output (warn-only)."""
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-777-broken.md").write_text(
        "# ADR-777: legacy header only\n\nno yaml here\n",
        encoding="utf-8",
    )

    mem = _memory(tmp_path)
    inp = _input(tmp_path)

    code = main([
        "check",
        "--memory", str(mem),
        "--input", str(inp),
        "--query", "storage",
        "--mode", "warn",
        "--adr-dir", str(adr_dir),
    ])

    out = capsys.readouterr().out
    assert "ADR_UNPARSEABLE" in out
    assert "ADR-777" in out
    # Warn-only: exit code follows enforcer verdict, not freshness.
    assert code == 0


def test_check_ignores_non_adr_markdown_in_adr_dir(tmp_path, capsys):
    """README.md / notes.md in --adr-dir must not produce any ADR_*
    warnings (not UNPARSEABLE, not UNIMPORTED, not anything)."""
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "README.md").write_text("# Index of ADRs\n", encoding="utf-8")
    (adr_dir / "notes.md").write_text("scratch\n", encoding="utf-8")

    mem = _memory(tmp_path)
    inp = _input(tmp_path)

    main([
        "check",
        "--memory", str(mem),
        "--input", str(inp),
        "--query", "storage",
        "--mode", "warn",
        "--adr-dir", str(adr_dir),
    ])

    out = capsys.readouterr().out
    for code in ("ADR_UNIMPORTED", "ADR_CHANGED", "ADR_MISSING", "ADR_UNPARSEABLE"):
        assert code not in out
