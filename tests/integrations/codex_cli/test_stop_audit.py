"""M3 tests: Stop changed-tree audit.

Uses MNEME_SESSION_STATE_DIR override for deterministic state; the whole-file
check runs through an injectable-style real subprocess against a governed tmp
project (same pattern as the gate tests).
"""
import json
import os
from pathlib import Path

import pytest

from mneme.integrations.codex_cli import stop_audit

FORBIDDEN = "FORBIDDEN_TOKEN_XYZ"


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEME_SESSION_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("MNEME_MEMORY", raising=False)
    monkeypatch.delenv("MNEME_HOOK_MODE", raising=False)
    yield


def _project(tmp_path, seed="def existing():\n    return 1\n"):
    import subprocess
    (tmp_path / ".mneme").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".mneme" / "project_memory.json").write_text(json.dumps({
        "meta": {"name": "t", "description": "t"},
        "decisions": [{
            "id": "ADR-S",
            "decision": "The forbidden token must not appear.",
            "rules": [{"type": "FORBID_LITERAL", "value": FORBIDDEN}],
        }],
    }), encoding="utf-8")
    if seed is not None:
        (tmp_path / "seed.py").write_text(seed, encoding="utf-8")
    if not (tmp_path / ".git").exists():
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True,
                       check=True)
    return tmp_path


def _pretooluse(project):
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash",
            "session_id": "sess-1", "cwd": str(project),
            "tool_input": {"command": "echo hi"}}


def _stop(project):
    return {"hook_event_name": "Stop", "session_id": "sess-1",
            "cwd": str(project)}


def _run_handler(payload, project):
    out = Path(project) / "__stdout.json"
    code = stop_audit.handle_stop(payload, stderr=__import__("io").StringIO(),
                                  stdout=out.open("w", encoding="utf-8"))
    text = out.read_text(encoding="utf-8").strip()
    if text:
        os.unlink(out)
        return code, json.loads(text)
    os.unlink(out)
    return code, None


def test_pretooluse_captures_baseline_before_mutation(tmp_path):
    project = _project(tmp_path)
    spath = stop_audit.ensure_session_baseline(_pretooluse(project))
    assert spath is not None and spath.exists()
    baseline = json.loads(spath.read_text(encoding="utf-8"))
    assert "seed.py" in baseline["files"]  # pre-mutation content captured


def test_shell_written_forbidden_file_blocks_with_named_rule(tmp_path):
    project = _project(tmp_path)
    stop_audit.ensure_session_baseline(_pretooluse(project))
    # Simulate a shell write that bypassed pre-exec reconstruction:
    (project / "shell_made.py").write_text(f'x = "{FORBIDDEN}"\n',
                                           encoding="utf-8")
    code, wire = _run_handler(_stop(project), project)
    assert code == 0
    assert wire["decision"] == "block"
    assert "[shell_made.py]" in wire["reason"]
    assert "ADR-S" in wire["reason"] and FORBIDDEN in wire["reason"]


def test_compliant_change_completes_silently(tmp_path):
    project = _project(tmp_path)
    stop_audit.ensure_session_baseline(_pretooluse(project))
    (project / "clean.py").write_text("def ok():\n    return 1\n",
                                      encoding="utf-8")
    code, wire = _run_handler(_stop(project), project)
    assert code == 0 and wire is None


def test_preexisting_dirty_file_untouched_by_codex_is_not_blamed(tmp_path):
    dirty = f'keep = "{FORBIDDEN}"\n'
    project = _project(tmp_path, seed=dirty)  # dirty before session: baseline
    stop_audit.ensure_session_baseline(_pretooluse(project))
    # Codex does nothing to keep.py; only adds a clean file.
    (project / "new_clean.py").write_text("ok = 1\n", encoding="utf-8")
    code, wire = _run_handler(_stop(project), project)
    assert code == 0 and wire is None


def test_dirty_before_session_then_modified_by_codex_is_audited(tmp_path):
    project = _project(tmp_path, seed=f'keep = "{FORBIDDEN}"\n')
    stop_audit.ensure_session_baseline(_pretooluse(project))
    # Codex modifies the already-dirty file during the session:
    (project / "seed.py").write_text(f'# touched\nx = "{FORBIDDEN}"\n',
                                     encoding="utf-8")
    code, wire = _run_handler(_stop(project), project)
    assert wire is not None and wire["decision"] == "block"
    assert "[seed.py]" in wire["reason"]


def test_deleted_files_recorded_but_not_enforced(tmp_path):
    project = _project(tmp_path)
    stop_audit.ensure_session_baseline(_pretooluse(project))
    (project / "seed.py").unlink()  # pure deletion, no sibling violation
    code, wire = _run_handler(_stop(project), project)
    assert code == 0 and wire is None  # deletions alone never block


def test_unevaluated_artifact_disclosed_not_claimed_governed(
        tmp_path, monkeypatch):
    project = _project(tmp_path)
    stop_audit.ensure_session_baseline(_pretooluse(project))
    big = ("# " + "x" * 64 + "\n") * 5000  # > MAX_FILE_BYTES
    (project / "huge.py").write_text(big, encoding="utf-8")
    out = tmp_path / "__out.json"
    stop_audit.handle_stop(_stop(project),
                           stderr=__import__("io").StringIO(),
                           stdout=out.open("w", encoding="utf-8"))
    text = out.read_text(encoding="utf-8")
    os.unlink(out)
    wire = json.loads(text)
    assert wire.get("decision") != "block"
    assert "systemMessage" in wire and "Unevaluated" in wire["systemMessage"]


def test_remediation_passes_and_block_cap_bounds_loops(tmp_path):
    project = _project(tmp_path)
    stop_audit.ensure_session_baseline(_pretooluse(project))
    (project / "bad.py").write_text(f'x = "{FORBIDDEN}"\n', encoding="utf-8")

    code, wire = _run_handler(_stop(project), project)
    assert wire["decision"] == "block"          # first Stop blocks

    # Deterministic remediation:
    (project / "bad.py").write_text("x = 1\n", encoding="utf-8")
    code, wire = _run_handler(_stop(project), project)
    assert wire is None                          # repaired file passes

    # Cap: force the counter to the limit with a persisting violation.
    (project / "bad.py").write_text(f'y = "{FORBIDDEN}"\n', encoding="utf-8")
    spath = stop_audit.snapshot_path(project.resolve(), "sess-1")
    blocks = stop_audit._blocks_path(spath)
    blocks.write_text(str(stop_audit.MAX_CONSECUTIVE_STOP_BLOCKS),
                      encoding="utf-8")
    out = tmp_path / "__out2.json"
    stop_audit.handle_stop(_stop(project),
                           stderr=__import__("io").StringIO(),
                           stdout=out.open("w", encoding="utf-8"))
    text = out.read_text(encoding="utf-8")
    os.unlink(out)
    wire = json.loads(text)
    assert wire.get("continue") is True          # loop released, not blocked
    assert "cap" in wire["systemMessage"].lower() or \
        "releasing" in wire["systemMessage"].lower()
