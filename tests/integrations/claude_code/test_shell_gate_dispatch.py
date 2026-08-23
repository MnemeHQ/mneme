"""ADR-021: the PreToolUse Bash gate, driven through the event dispatcher.

A reconstructable violating shell mutation must be refused BEFORE execution;
compliant ones pass; ambiguous mutating commands are never preflight-blocked
on guessed semantics.
"""
import io
import json
from pathlib import Path

import pytest

from mneme.integrations.claude_code.hook import handle_event

FIXTURE = Path(__file__).parent / "fixtures" / "project_memory.json"


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".mneme").mkdir()
    (tmp_path / ".mneme" / "project_memory.json").write_text(
        FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return tmp_path


def _bash_event(cwd, command):
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "cwd": str(cwd),
        "tool_input": {"command": command},
    }


def _run(event):
    err, out = io.StringIO(), io.StringIO()
    rc = handle_event(event, stderr=err, stdout=out)
    return rc, err.getvalue(), out.getvalue()


def test_violating_heredoc_refused_before_execution(project):
    """The command is refused; the target artifact never receives it."""
    target = project / "storage_db.py"
    assert not target.exists()
    rc, err, _ = _run(_bash_event(project, "cat > storage_db.py << 'EOF'\nimport psycopg2\nEOF"))
    assert rc == 2
    assert "psycopg2" in err or "test_001" in err
    assert not target.exists(), "refusal must precede any disk mutation"


def test_compliant_heredoc_passes(project):
    rc, _, _ = _run(_bash_event(project, "cat > storage_db.py << 'EOF'\nimport sqlite3\nEOF"))
    assert rc == 0


def test_append_checks_only_appended_lines(project):
    existing = project / "storage_db.py"
    existing.write_text("import sqlite3\n", encoding="utf-8")
    rc, err, _ = _run(
        _bash_event(project, "cat >> storage_db.py << 'EOF'\nimport psycopg2\nEOF")
    )
    assert rc == 2
    # The untouched pre-existing line must not be part of the checked delta.
    assert "sqlite3" not in err


@pytest.mark.parametrize(
    "cmd",
    [
        "perl -e \"print 'x'\" > out.txt",
        "./tools/generate.sh",
        "echo hi | tee out.txt",
        "cd src && cat > db.py << 'EOF'\nx\nEOF",
        # Unquoted delimiter: expansion makes the resulting bytes unknowable.
        "cat > storage_db.py << EOF\nimport psycopg2\nEOF",
    ],
)
def test_ambiguous_mutating_command_not_preflight_refused(project, cmd):
    """Class B passes through; the Stop boundary audits its results."""
    rc, err, out = _run(_bash_event(project, cmd))
    assert rc == 0
    assert "permissionDecision" not in out


def test_non_mutating_command_unaffected(project):
    rc, _, _ = _run(_bash_event(project, "ls -la"))
    assert rc == 0


def test_malformed_input_deterministic_no_op(project):
    for cmd in ("", "   ", "cat > a.txt << 'EOF'\nunterminated"):
        rc, _, _ = _run(_bash_event(project, cmd))
        assert rc == 0, f"{cmd!r} must fail operational, deterministically"


def test_absent_memory_passthrough(tmp_path):
    rc, _, _ = _run(_bash_event(tmp_path, "cat > a.py << 'EOF'\nimport psycopg2\nEOF"))
    assert rc == 0


def test_real_target_path_reaches_checker(project, monkeypatch):
    """ADR-020: applicability must see the true repository-relative path."""
    captured = {}

    import mneme.integrations.claude_code.hook as hook

    real_invoke = hook._invoke_check

    def spy(memory, rel_label, target_path, body, *args, **kwargs):
        captured["target"] = target_path
        return real_invoke(memory, rel_label, target_path, body, *args, **kwargs)

    monkeypatch.setattr(hook, "_invoke_check", spy)
    rc, _, _ = _run(
        _bash_event(project, "cat > src/deep/storage_db.py << 'EOF'\nimport psycopg2\nEOF")
    )
    assert rc == 2
    assert Path(captured["target"]) == project / "src" / "deep" / "storage_db.py"


def test_warn_mode_defers_never_allows_bash_gate(project, monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    out = io.StringIO()
    rc = handle_event(
        _bash_event(project, "cat > storage_db.py << 'EOF'\nimport psycopg2\nEOF"),
        stderr=io.StringIO(),
        stdout=out,
    )
    assert rc == 0
    emitted = json.loads(out.getvalue())
    hso = emitted["hookSpecificOutput"]
    assert hso["permissionDecision"] == "defer"
    assert "psycopg2" in hso["permissionDecisionReason"]
