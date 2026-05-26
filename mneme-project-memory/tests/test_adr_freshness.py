"""Tests for ADR freshness detection in `mneme.adr_freshness`.

Covers the four canonical states:
  - ADR_UNIMPORTED   active ADR file present, no matching decision
  - ADR_CHANGED      imported ADR file content differs from stored hash
  - ADR_MISSING      imported decision references an ADR path that vanished
  - clean            ADR + decision + hash all in sync -> no issues

Plus backward-compatibility: legacy memory files where imported decisions
lack the new ``source`` provenance block must not crash and must not
produce spurious warnings.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from mneme.adr_freshness import (
    ADR_CHANGED,
    ADR_MISSING,
    ADR_UNIMPORTED,
    FreshnessIssue,
    check_freshness,
)


# ── helpers ───────────────────────────────────────────────────────────────────


def _adr_text(adr_id: str, body: str = "Body content.", status: str = "accepted") -> str:
    return (
        f"---\n"
        f"id: {adr_id}\n"
        f"title: Test {adr_id}\n"
        f"status: {status}\n"
        f"priority: normal\n"
        f"date: 2026-05-01\n"
        f"scope: test_{adr_id.lower().replace('-', '_')}\n"
        f"---\n\n"
        f"{body}\n"
    )


def _write_adr(path: Path, adr_id: str, body: str = "Body content.",
               status: str = "accepted") -> str:
    """Write an ADR file and return the SHA-256 of its on-disk bytes.

    Hashing the bytes the OS actually wrote (rather than the source
    string) avoids false hash mismatches caused by Windows line-ending
    translation in ``Path.write_text``.
    """
    text = _adr_text(adr_id, body=body, status=status)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_memory(path: Path, decisions: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "meta": {"name": "t", "description": "t"},
                "items": [],
                "examples": [],
                "decisions": decisions,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _layout(tmp_path: Path) -> tuple[Path, Path]:
    """Return (memory_path, adr_dir) with conventional repo layout."""
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    memory = tmp_path / ".mneme" / "project_memory.json"
    return memory, adr_dir


# ── ADR_UNIMPORTED ────────────────────────────────────────────────────────────


def test_unimported_active_adr_produces_warning(tmp_path):
    memory, adr_dir = _layout(tmp_path)
    _write_adr(adr_dir / "ADR-001-foo.md", "ADR-001")
    _write_memory(memory, decisions=[])

    issues = check_freshness(memory_path=memory, adr_dir=adr_dir)
    unimported = [i for i in issues if i.code == ADR_UNIMPORTED]
    assert len(unimported) == 1
    assert unimported[0].adr_id == "ADR-001"


def test_unimported_proposed_adr_does_not_warn(tmp_path):
    """Proposed ADRs are intentionally not imported; do not flag them."""
    memory, adr_dir = _layout(tmp_path)
    _write_adr(adr_dir / "ADR-099-draft.md", "ADR-099", status="proposed")
    _write_memory(memory, decisions=[])

    issues = check_freshness(memory_path=memory, adr_dir=adr_dir)
    assert [i for i in issues if i.code == ADR_UNIMPORTED] == []


def test_unimported_does_not_trigger_for_non_adr_decisions(tmp_path):
    """Non-ADR decisions in memory must not produce freshness diagnostics."""
    memory, adr_dir = _layout(tmp_path)
    _write_memory(memory, decisions=[{"id": "workflow-001", "decision": "manual"}])

    issues = check_freshness(memory_path=memory, adr_dir=adr_dir)
    assert issues == []


# ── ADR_CHANGED ───────────────────────────────────────────────────────────────


def test_modified_adr_produces_changed_warning(tmp_path):
    memory, adr_dir = _layout(tmp_path)
    original_hash = _write_adr(adr_dir / "ADR-002-bar.md", "ADR-002", body="Original.")

    _write_memory(memory, decisions=[{
        "id": "ADR-002",
        "decision": "Test ADR-002",
        "source": {
            "type": "adr",
            "path": "../docs/adr/ADR-002-bar.md",
            "sha256": original_hash,
        },
    }])

    # Modify the ADR after "import"
    _write_adr(adr_dir / "ADR-002-bar.md", "ADR-002", body="Modified.")

    issues = check_freshness(memory_path=memory, adr_dir=adr_dir)
    changed = [i for i in issues if i.code == ADR_CHANGED]
    assert len(changed) == 1
    assert changed[0].adr_id == "ADR-002"


def test_unchanged_adr_produces_no_changed_warning(tmp_path):
    memory, adr_dir = _layout(tmp_path)
    sha = _write_adr(adr_dir / "ADR-004-aligned.md", "ADR-004")

    _write_memory(memory, decisions=[{
        "id": "ADR-004",
        "decision": "Aligned",
        "source": {
            "type": "adr",
            "path": "../docs/adr/ADR-004-aligned.md",
            "sha256": sha,
        },
    }])

    issues = check_freshness(memory_path=memory, adr_dir=adr_dir)
    assert issues == []


# ── ADR_MISSING ───────────────────────────────────────────────────────────────


def test_missing_adr_source_produces_missing_warning(tmp_path):
    memory, adr_dir = _layout(tmp_path)
    # No ADR file written.

    _write_memory(memory, decisions=[{
        "id": "ADR-003",
        "decision": "Gone",
        "source": {
            "type": "adr",
            "path": "../docs/adr/ADR-003-gone.md",
            "sha256": "0" * 64,
        },
    }])

    issues = check_freshness(memory_path=memory, adr_dir=adr_dir)
    missing = [i for i in issues if i.code == ADR_MISSING]
    assert len(missing) == 1
    assert missing[0].adr_id == "ADR-003"


# ── backward compatibility ────────────────────────────────────────────────────


def test_decision_without_source_is_backward_compatible(tmp_path):
    """A legacy decision whose id matches an ADR but has no `source` field
    must not crash and must not produce a spurious UNIMPORTED warning.
    Without a stored hash there is nothing to compare against, so the checker
    is silent on freshness for that pairing.
    """
    memory, adr_dir = _layout(tmp_path)
    _write_adr(adr_dir / "ADR-005-legacy.md", "ADR-005")
    _write_memory(memory, decisions=[{"id": "ADR-005", "decision": "Legacy"}])

    issues = check_freshness(memory_path=memory, adr_dir=adr_dir)
    codes = [i.code for i in issues]
    assert ADR_UNIMPORTED not in codes
    assert ADR_CHANGED not in codes
    assert ADR_MISSING not in codes


def test_memory_file_without_decisions_key_does_not_crash(tmp_path):
    memory, adr_dir = _layout(tmp_path)
    memory.parent.mkdir(parents=True, exist_ok=True)
    memory.write_text(json.dumps({"meta": {"name": "t", "description": "t"}}),
                      encoding="utf-8")
    issues = check_freshness(memory_path=memory, adr_dir=adr_dir)
    # No decisions, no ADRs -> no issues
    assert issues == []


def test_missing_adr_dir_returns_empty(tmp_path):
    """When the adr_dir does not exist, the checker returns no issues
    (it cannot say whether anything is unimported)."""
    memory = tmp_path / ".mneme" / "project_memory.json"
    _write_memory(memory, decisions=[])
    issues = check_freshness(memory_path=memory, adr_dir=tmp_path / "nope")
    assert issues == []


# ── output shape ──────────────────────────────────────────────────────────────


def test_issue_carries_path_and_message(tmp_path):
    memory, adr_dir = _layout(tmp_path)
    _write_adr(adr_dir / "ADR-006-shape.md", "ADR-006")
    _write_memory(memory, decisions=[])

    issues = check_freshness(memory_path=memory, adr_dir=adr_dir)
    assert len(issues) == 1
    i = issues[0]
    assert isinstance(i, FreshnessIssue)
    assert i.code == ADR_UNIMPORTED
    assert i.adr_id == "ADR-006"
    assert "ADR-006-shape.md" in i.path
    assert i.message  # non-empty
