"""ADR-021: the Stop completion boundary.

Post-mutation / pre-completion session-delta checks. The boundary blocks the
turn on trusted verdicts over session-introduced lines only, honors
stop_hook_active, and degrades visibly (never a fabricated pass) when
attribution is unavailable.
"""
import io
import json
import subprocess
from pathlib import Path

import pytest

from mneme.integrations.claude_code.hook import handle_event

FIXTURE = Path(__file__).parent / "fixtures" / "project_memory.json"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setenv("MNEME_SESSION_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "state").mkdir()
    subprocess.run(["git", "init", "-q"], cwd=work, check=True)
    subprocess.run(
        ["git", "-C", str(work), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "--allow-empty", "-m", "init"],
        check=True,
    )
    (work / ".mneme").mkdir()
    (work / ".mneme" / "project_memory.json").write_text(
        FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return work


def _stop_event(cwd, **extra):
    event = {
        "hook_event_name": "Stop",
        "session_id": "sess-1",
        "cwd": str(cwd),
    }
    event.update(extra)
    return event


def _session_start(cwd):
    return {
        "hook_event_name": "SessionStart",
        "source": "startup",
        "session_id": "sess-1",
        "cwd": str(cwd),
    }


def _run(event):
    err, out = io.StringIO(), io.StringIO()
    rc = handle_event(event, stderr=err, stdout=out)
    return rc, err.getvalue(), out.getvalue()


class TestBlocking:
    def test_shell_generated_violation_blocks_stop(self, repo):
        assert _run(_session_start(repo))[0] == 0
        # An unsupported indirect mutation lands on disk.
        target = repo / "storage_db.py"
        target.write_text("import psycopg2\n", encoding="utf-8")
        rc, err, out = _run(_stop_event(repo))
        assert rc == 0  # Stop blocks via JSON decision, not exit code
        decision = json.loads(out)
        assert decision["decision"] == "block"
        assert "psycopg2" in decision["reason"]
        assert "storage_db.py" in decision["reason"]

    def test_new_untracked_violation_blocks(self, repo):
        assert _run(_session_start(repo))[0] == 0
        (repo / "fresh_violation.py").write_text("import psycopg2\n", encoding="utf-8")
        rc, _, out = _run(_stop_event(repo))
        assert json.loads(out)["decision"] == "block"

    def test_compliant_session_passes(self, repo):
        assert _run(_session_start(repo))[0] == 0
        (repo / "clean.py").write_text("import sqlite3\n", encoding="utf-8")
        rc, _, out = _run(_stop_event(repo))
        assert rc == 0
        assert out.strip() == ""

    def test_repair_converges_without_new_baseline(self, repo):
        """After a blocked Stop, fixing the delta must let the next Stop pass."""
        assert _run(_session_start(repo))[0] == 0
        (repo / "storage_db.py").write_text("import psycopg2\n", encoding="utf-8")
        rc, _, out = _run(_stop_event(repo))
        assert json.loads(out)["decision"] == "block"
        # Agent repairs.
        (repo / "storage_db.py").write_text("import sqlite3\n", encoding="utf-8")
        rc, _, out = _run(_stop_event(repo))
        assert rc == 0
        assert out.strip() == ""

    def test_multiple_dirty_artifacts_names_the_right_one(self, repo):
        assert _run(_session_start(repo))[0] == 0
        (repo / "fine.py").write_text("ok = True\n", encoding="utf-8")
        (repo / "guilty.py").write_text("import psycopg2\n", encoding="utf-8")
        rc, _, out = _run(_stop_event(repo))
        reason = json.loads(out)["reason"]
        assert "guilty.py" in reason
        assert "fine.py" not in reason

    def test_deletion_only_remediation_never_blocks(self, repo):
        (repo / "pre_bad.py").write_text("import psycopg2\n", encoding="utf-8")  # pre-session
        assert _run(_session_start(repo))[0] == 0
        (repo / "pre_bad.py").unlink()
        rc, _, out = _run(_stop_event(repo))
        assert out.strip() == ""


class TestAttribution:
    def test_pre_session_violation_not_blamed(self, repo):
        (repo / "legacy_wound.py").write_text("import psycopg2\n", encoding="utf-8")
        assert _run(_session_start(repo))[0] == 0
        # Claude does unrelated work.
        (repo / "unrelated.txt").write_text("notes\n", encoding="utf-8")
        rc, _, out = _run(_stop_event(repo))
        assert out.strip() == "", "a pre-session violation must not block the session"

    def test_unrelated_edit_to_wounded_artifact_not_blamed(self, repo):
        wounded = repo / "wounded.py"
        wounded.write_text("import psycopg2\nstable = 1\n", encoding="utf-8")
        assert _run(_session_start(repo))[0] == 0
        wounded.write_text("import psycopg2\nstable = 1\ninnocent = 2\n", encoding="utf-8")
        rc, _, out = _run(_stop_event(repo))
        assert out.strip() == ""

    def test_violation_on_top_of_dirty_lines_is_caught(self, repo):
        wounded = repo / "wounded.py"
        wounded.write_text("import psycopg2\nstable = 1\n", encoding="utf-8")
        assert _run(_session_start(repo))[0] == 0
        wounded.write_text(
            "import psycopg2\nstable = 1\nguilty_addition = 'import psycopg2'\n",
            encoding="utf-8",
        )
        rc, _, out = _run(_stop_event(repo))
        assert json.loads(out)["decision"] == "block"

    def test_pre_session_untracked_untouched_not_attributed(self, repo):
        (repo / "old_untracked.py").write_text("import psycopg2\n", encoding="utf-8")
        assert _run(_session_start(repo))[0] == 0
        rc, _, out = _run(_stop_event(repo))
        assert out.strip() == ""


class TestLoopSafetyAndDegrade:
    def test_stop_hook_active_short_circuits_even_with_violations(self, repo):
        assert _run(_session_start(repo))[0] == 0
        (repo / "storage_db.py").write_text("import psycopg2\n", encoding="utf-8")
        rc, _, out = _run(_stop_event(repo, stop_hook_active=True))
        assert rc == 0
        assert "decision" not in out

    def test_missing_baseline_created_visibly_no_block(self, repo):
        # No SessionStart ran; a violation already sits in the tree.
        (repo / "storage_db.py").write_text("import psycopg2\n", encoding="utf-8")
        rc, err, out = _run(_stop_event(repo))
        assert rc == 0
        assert out.strip() == "", "without a baseline nothing may be attributed"
        assert "baseline" in err.lower()

    def test_second_stop_after_late_baseline_enforces(self, repo):
        rc, err, _ = _run(_stop_event(repo))  # creates late baseline
        assert rc == 0
        (repo / "storage_db.py").write_text("import psycopg2\n", encoding="utf-8")
        rc, _, out = _run(_stop_event(repo))
        assert json.loads(out)["decision"] == "block"

    def test_non_git_directory_reports_inactive(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MNEME_SESSION_STATE_DIR", str(tmp_path / "state"))
        (tmp_path / "state").mkdir()
        (tmp_path / ".mneme").mkdir()
        (tmp_path / ".mneme" / "project_memory.json").write_text(
            FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
        )
        rc, err, out = _run(_stop_event(tmp_path))
        assert rc == 0
        assert out.strip() == ""
        assert "git" in err.lower()

    def test_corrupt_baseline_degrades_visibly(self, repo):
        from mneme.integrations.claude_code import session_state as ss

        snap_path = ss.snapshot_path(repo, "sess-1")
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        snap_path.write_text("{ corrupt", encoding="utf-8")
        rc, err, out = _run(_stop_event(repo))
        assert rc == 0
        assert out.strip() == ""
        assert "baseline" in err.lower()

    def test_oversized_changed_artifact_reported_not_passed_silently(self, repo):
        assert _run(_session_start(repo))[0] == 0
        big = repo / "big.log"
        big.write_text("x" * 20, encoding="utf-8")
        # Re-capture is not done; simulate an oversized baseline entry instead.
        from mneme.integrations.claude_code import session_state as ss

        path = ss.snapshot_path(repo, "sess-1")
        snap = ss.load_snapshot(path)
        snap["files"]["big.log"] = {
            "sha256": "0" * 64,
            "size": ss.MAX_FILE_BYTES + 5,
            "content": None,
        }
        ss.save_snapshot(path, snap)
        big.write_text("y" * (ss.MAX_FILE_BYTES + 5), encoding="utf-8")
        rc, err, out = _run(_stop_event(repo))
        assert rc == 0
        assert out.strip() == ""
        assert "big.log" in err

    def test_crashing_checker_fails_open_with_diagnostics(self, repo):
        assert _run(_session_start(repo))[0] == 0
        (repo / ".mneme" / "project_memory.json").write_text(
            "{ broken", encoding="utf-8"
        )
        (repo / "storage_db.py").write_text("import psycopg2\n", encoding="utf-8")
        rc, err, out = _run(_stop_event(repo))
        assert rc == 0
        assert out.strip() == "", "an untrusted verdict must never block"
        lowered = err.lower()
        assert "fail" in lowered or "verdict" in lowered or "could not" in lowered

    def test_warn_mode_reports_without_blocking(self, repo, monkeypatch):
        monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
        assert _run(_session_start(repo))[0] == 0
        (repo / "storage_db.py").write_text("import psycopg2\n", encoding="utf-8")
        rc, _, out = _run(_stop_event(repo))
        assert rc == 0
        emitted = json.loads(out)
        assert emitted["hookSpecificOutput"]["additionalContext"]
        assert "decision" not in emitted


class TestSessionStart:
    def test_startup_captures_baseline(self, repo):
        rc, err, out = _run(_session_start(repo))
        assert rc == 0
        from mneme.integrations.claude_code import session_state as ss

        assert ss.load_snapshot(ss.snapshot_path(repo, "sess-1")) is not None

    def test_compact_source_preserves_existing_baseline(self, repo):
        assert _run(_session_start(repo))[0] == 0
        from mneme.integrations.claude_code import session_state as ss

        path = ss.snapshot_path(repo, "sess-1")
        original = ss.load_snapshot(path)
        original["files"]["marker.xyz"] = {"sha256": "1" * 64, "size": 1, "content": "z"}
        ss.save_snapshot(path, original)

        # compact/clear/resume must NOT refresh the baseline
        event = {
            "hook_event_name": "SessionStart",
            "source": "compact",
            "session_id": "sess-1",
            "cwd": str(repo),
        }
        err, out = io.StringIO(), io.StringIO()
        assert handle_event(event, stderr=err, stdout=out) == 0
        kept = ss.load_snapshot(path)
        assert "marker.xyz" in kept["files"]

    def test_startup_refreshes_existing_baseline(self, repo):
        assert _run(_session_start(repo))[0] == 0
        from mneme.integrations.claude_code import session_state as ss

        path = ss.snapshot_path(repo, "sess-1")
        snap = ss.load_snapshot(path)
        snap["files"]["stale.marker"] = {"sha256": "1" * 64, "size": 1, "content": "z"}
        ss.save_snapshot(path, snap)
        assert _run(_session_start(repo))[0] == 0
        refreshed = ss.load_snapshot(path)
        assert "stale.marker" not in refreshed["files"]

    def test_absent_memory_is_a_no_op(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MNEME_SESSION_STATE_DIR", str(tmp_path / "state"))
        rc, _, _ = _run(_session_start(tmp_path))
        assert rc == 0
