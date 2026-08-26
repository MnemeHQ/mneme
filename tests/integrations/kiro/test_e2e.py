"""End-to-end tests through the real mneme CLI.

Skipped when mneme is not importable/runnable in the current interpreter
(fresh CI before `pip install -e .`).

The envelopes here mirror the observed Kiro CLI write shape: tool_name
``fs_write`` with ``tool_input.path`` and full ``tool_input.content``.
"""
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from mneme.integrations.kiro.hook import main

FIXTURE = Path(__file__).parent / "fixtures" / "project_memory.json"
VIOLATION = "legacy_client.connect("

requires_mneme = pytest.mark.skipif(
    subprocess.run(
        [sys.executable, "-m", "mneme", "--help"], capture_output=True
    ).returncode != 0,
    reason="mneme CLI not runnable via sys.executable -m mneme",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("MNEME_MEMORY", raising=False)
    monkeypatch.delenv("MNEME_HOOK_MODE", raising=False)


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".mneme").mkdir()
    (tmp_path / ".mneme" / "project_memory.json").write_text(
        FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return tmp_path


def _envelope(cwd, path, content):
    return json.dumps({
        "hook_event_name": "preToolUse",
        "cwd": str(cwd),
        "tool_name": "fs_write",
        "tool_input": {"path": str(path), "content": content},
    })


@requires_mneme
def test_violating_write_blocks_before_disk(project):
    target = project / "service.py"
    rc = main(
        stdin=io.StringIO(_envelope(project, target, f"x = 1\n{VIOLATION}\n")),
        stderr=io.StringIO(),
    )
    assert rc != 0, "a typed-literal violation must block the native write"
    assert not target.exists(), "nothing may reach disk on a block"


@requires_mneme
def test_compliant_write_allowed(project):
    target = project / "service.py"
    out, err = io.StringIO(), io.StringIO()
    rc = main(
        stdin=io.StringIO(_envelope(project, target, "x = 1\ny = 2\n")),
        stderr=err, stdout=out,
    )
    assert rc == 0
    assert out.getvalue() == "", "PASS must stay silent"


@requires_mneme
def test_remediation_allowed_end_to_end(project):
    target = project / "dirty.py"
    target.write_text(f"a\n{VIOLATION}\nb\n", encoding="utf-8")
    rc = main(
        stdin=io.StringIO(_envelope(project, target, "a\nb\n")),
        stderr=io.StringIO(), stdout=io.StringIO(),
    )
    assert rc == 0


@requires_mneme
def test_preexisting_violation_does_not_block_unrelated_edit(project):
    target = project / "dirty.py"
    target.write_text(f"{VIOLATION}\nrest\n", encoding="utf-8")
    rc = main(
        stdin=io.StringIO(_envelope(project, target, f"{VIOLATION}\nrest\nmore_ok\n")),
        stderr=io.StringIO(), stdout=io.StringIO(),
    )
    assert rc == 0


@requires_mneme
def test_violation_blocks_under_generic_filename(project):
    """ADR-017: enforcement must not depend on lexical filename overlap."""
    err = io.StringIO()
    rc = main(
        stdin=io.StringIO(_envelope(project, project / "handler.py", VIOLATION + "\n")),
        stderr=err,
    )
    assert rc != 0
    assert "test_002" in err.getvalue() or VIOLATION in err.getvalue()


@requires_mneme
def test_scoped_rule_enforced_under_include_path(project):
    src = project / "src"
    src.mkdir()
    err = io.StringIO()
    envelope = _envelope(project, src / "app.py", "EXPERIMENTAL_MARKER_XY\n")
    rc = main(stdin=io.StringIO(envelope), stderr=err)
    assert rc != 0


@requires_mneme
def test_corrupt_memory_fails_open_against_real_cli(project):
    (project / ".mneme" / "project_memory.json").write_text(
        "{ this is not valid json", encoding="utf-8"
    )
    out, err = io.StringIO(), io.StringIO()
    rc = main(
        stdin=io.StringIO(_envelope(project, project / "f.py", VIOLATION)),
        stderr=err, stdout=out,
    )
    assert rc == 0, "a crashing check must never hard-block a write"
    assert "UNEVALUATED" in out.getvalue()


@requires_mneme
def test_warn_mode_surfaces_warning_through_stdout(project, monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    out, err = io.StringIO(), io.StringIO()
    rc = main(
        stdin=io.StringIO(_envelope(project, project / "f.py", VIOLATION + "\n")),
        stderr=err, stdout=out,
    )
    assert rc == 0
    assert "[mneme] WARN" in out.getvalue()
