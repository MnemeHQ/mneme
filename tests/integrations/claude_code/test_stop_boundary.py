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

    def test_exact_content_move_not_attributed_to_session(self, repo):
        """mv of a pre-session artifact must not blame its lines on Claude."""
        (repo / "legacy.py").write_text("import psycopg2\n", encoding="utf-8")
        assert _run(_session_start(repo))[0] == 0
        (repo / "legacy.py").rename(repo / "moved.py")
        rc, _, out = _run(_stop_event(repo))
        assert out.strip() == "", "an exact-content move introduces nothing new"

    def test_copy_of_violating_artifact_still_attributed(self, repo):
        """A copy whose source still exists is new content: attributed."""
        (repo / "src_bad.py").write_text("import psycopg2\n", encoding="utf-8")
        assert _run(_session_start(repo))[0] == 0
        (repo / "copy_bad.py").write_text("import psycopg2\n", encoding="utf-8")
        rc, _, out = _run(_stop_event(repo))
        reason = json.loads(out)["reason"]
        assert "copy_bad.py" in reason

    def test_moved_then_edited_is_attributed_for_its_edit(self, repo):
        """Rename plus edit falls back to full attribution (conservative)."""
        (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
        assert _run(_session_start(repo))[0] == 0
        target = repo / "b.py"
        target.write_text("x = 1\nimport psycopg2\n", encoding="utf-8")
        (repo / "a.py").unlink()
        rc, _, out = _run(_stop_event(repo))
        assert json.loads(out)["decision"] == "block"

    def test_ambiguous_duplicate_content_rename_is_unevaluated_not_guessed(
        self, repo
    ):
        """Two identical vanished sources: provenance is unknowable, so the
        delta must be surfaced as unevaluated rather than paired with
        whichever identical source was enumerated first."""
        (repo / "tests_dir").mkdir()
        (repo / "tests_dir" / "a.py").write_text(
            "same = 'bytes'\n", encoding="utf-8"
        )
        (repo / "src_dir").mkdir()
        (repo / "src_dir" / "b.py").write_text(
            "same = 'bytes'\n", encoding="utf-8"
        )
        assert _run(_session_start(repo))[0] == 0
        (repo / "tests_dir" / "a.py").unlink()
        (repo / "src_dir" / "b.py").unlink()
        (repo / "src_dir" / "c.py").write_text("same = 'bytes'\n", encoding="utf-8")

        from mneme.integrations.claude_code import session_state as ss

        base = ss.load_snapshot(ss.snapshot_path(repo, "sess-1"), expected_root=repo)
        d = ss.compute_session_delta(repo, base)
        assert d.renamed == {}
        assert "ambiguous rename provenance" in d.skipped.get("src_dir/c.py", "")

        rc, err, out = _run(_stop_event(repo))
        assert rc == 0
        emitted = json.loads(out)
        context = emitted["hookSpecificOutput"]["additionalContext"]
        assert "c.py" in context and "ambiguous" in context
        assert "decision" not in emitted

    def test_session_start_storage_failure_is_agent_visible(self, repo, monkeypatch):
        import mneme.integrations.claude_code.hook as hook

        def boom(path, data):
            raise OSError("disk full")

        monkeypatch.setattr(hook, "save_snapshot", boom)
        out = io.StringIO()
        rc = handle_event(_session_start(repo), stderr=io.StringIO(), stdout=out)
        assert rc == 0
        text = out.getvalue()
        assert "could not be stored" in text
        assert "disk full" in text


class TestLoopSafetyAndDegrade:
    def test_stop_hook_active_still_evaluates_and_blocks(self, repo):
        """The repair-recheck turn (stop_hook_active=true) must be evaluated."""
        assert _run(_session_start(repo))[0] == 0
        (repo / "storage_db.py").write_text("import psycopg2\n", encoding="utf-8")
        rc, _, out = _run(_stop_event(repo, stop_hook_active=True))
        assert rc == 0
        assert json.loads(out)["decision"] == "block"

    def test_repaired_state_passes_on_stop_hook_active_turn(self, repo):
        """First Stop blocks; the repair converges on the very next Stop."""
        assert _run(_session_start(repo))[0] == 0
        target = repo / "storage_db.py"
        target.write_text("import psycopg2\n", encoding="utf-8")
        rc, _, out = _run(_stop_event(repo))
        assert json.loads(out)["decision"] == "block"
        target.write_text("import sqlite3\n", encoding="utf-8")
        rc, _, out = _run(_stop_event(repo, stop_hook_active=True))
        assert rc == 0
        assert out.strip() == "", "a verified repair must allow completion"

    def test_unrepaired_violation_blocks_again(self, repo):
        """No repair -> second Stop blocks again (bounded by harness cap)."""
        assert _run(_session_start(repo))[0] == 0
        (repo / "storage_db.py").write_text("import psycopg2\n", encoding="utf-8")
        assert json.loads(_run(_stop_event(repo))[2])["decision"] == "block"
        rc, _, out = _run(_stop_event(repo, stop_hook_active=True))
        assert json.loads(out)["decision"] == "block"

    def test_missing_baseline_created_visibly_no_block(self, repo):
        # No SessionStart ran; a violation already sits in the tree.
        (repo / "storage_db.py").write_text("import psycopg2\n", encoding="utf-8")
        rc, err, out = _run(_stop_event(repo))
        assert rc == 0
        emitted = json.loads(out)
        context = emitted["hookSpecificOutput"]["additionalContext"]
        assert "baseline" in context.lower()
        assert "decision" not in emitted

    def test_second_stop_after_late_baseline_enforces(self, repo):
        rc, _, _ = _run(_stop_event(repo))  # creates late baseline
        (repo / "storage_db.py").write_text("import psycopg2\n", encoding="utf-8")
        rc, _, out = _run(_stop_event(repo))
        assert json.loads(out)["decision"] == "block"

    def test_non_git_directory_reports_inactive_to_agent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MNEME_SESSION_STATE_DIR", str(tmp_path / "state"))
        (tmp_path / "state").mkdir()
        (tmp_path / ".mneme").mkdir()
        (tmp_path / ".mneme" / "project_memory.json").write_text(
            FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
        )
        rc, err, out = _run(_stop_event(tmp_path))
        assert rc == 0
        emitted = json.loads(out)
        context = emitted["hookSpecificOutput"]["additionalContext"]
        assert "git" in context.lower()
        assert "inactive" in context
        assert "decision" not in emitted

    def test_corrupt_baseline_degrades_visibly(self, repo):
        from mneme.integrations.claude_code import session_state as ss

        snap_path = ss.snapshot_path(repo, "sess-1")
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        snap_path.write_text("{ corrupt", encoding="utf-8")
        rc, err, out = _run(_stop_event(repo))
        assert rc == 0
        emitted = json.loads(out)
        context = emitted["hookSpecificOutput"]["additionalContext"]
        assert "baseline" in context.lower()
        assert "decision" not in emitted

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
        # Claude never sees exit-0 stderr, so the unevaluated delta must be
        # surfaced as non-blocking Stop feedback instead.
        emitted = json.loads(out)
        context = emitted["hookSpecificOutput"]["additionalContext"]
        assert "big.log" in context
        assert "not evaluated" in context
        assert "decision" not in emitted

    def test_crashing_checker_fails_open_with_diagnostics(self, repo):
        assert _run(_session_start(repo))[0] == 0
        (repo / ".mneme" / "project_memory.json").write_text(
            "{ broken", encoding="utf-8"
        )
        (repo / "storage_db.py").write_text("import psycopg2\n", encoding="utf-8")
        rc, err, out = _run(_stop_event(repo))
        assert rc == 0
        emitted = json.loads(out)
        assert "decision" not in emitted, "an untrusted verdict must never block"
        context = emitted["hookSpecificOutput"]["additionalContext"]
        assert "could not be evaluated" in context

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


SCOPED_MEMORY = {
    "meta": {"name": "scoped", "description": "d", "version": "0", "owner": "t",
             "created": "2026-08-22"},
    "items": [],
    "decisions": [
        {
            "id": "scoped_001",
            "decision": "legacy_client stays out of production code",
            "rationale": "r",
            "scope": ["legacy"],
            "constraints": [],
            "anti_patterns": [],
            "rules": [
                {
                    "type": "FORBID_LITERAL",
                    "value": "legacy_client",
                    "include_paths": ["src/**"],
                    "exclude_paths": ["tests/**"],
                }
            ],
        }
    ],
}


class TestRenameApplicability:
    """ADR-020: byte identity is not policy identity across a move."""

    @pytest.fixture
    def scoped_repo(self, tmp_path, monkeypatch):
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
            json.dumps(SCOPED_MEMORY), encoding="utf-8"
        )
        return work

    def test_move_from_excluded_to_included_blocks(self, scoped_repo):
        fixture = scoped_repo / "tests"
        fixture.mkdir()
        (fixture / "fixture.py").write_text(
            "import legacy_client\n", encoding="utf-8"
        )
        (fixture / "fixture.py").parent.mkdir(parents=True, exist_ok=True)
        assert _run(_session_start(scoped_repo))[0] == 0
        target_dir = scoped_repo / "src"
        target_dir.mkdir()
        (fixture / "fixture.py").rename(target_dir / "production.py")
        rc, _, out = _run(_stop_event(scoped_repo))
        reason = json.loads(out)["reason"]
        assert "production.py" in reason
        assert "legacy_client" in reason

    def test_move_within_same_applicability_passes(self, scoped_repo):
        """No applicability change -> no false attribution of old lines."""
        (scoped_repo / "src").mkdir()
        (scoped_repo / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
        assert _run(_session_start(scoped_repo))[0] == 0
        (scoped_repo / "src" / "a.py").rename(scoped_repo / "src" / "b.py")
        rc, _, out = _run(_stop_event(scoped_repo))
        assert out.strip() == ""

    def test_move_from_included_to_excluded_relaxes(self, scoped_repo):
        (scoped_repo / "src").mkdir()
        (scoped_repo / "src" / "bad.py").write_text(
            "import legacy_client\n", encoding="utf-8"
        )
        assert _run(_session_start(scoped_repo))[0] == 0
        target_dir = scoped_repo / "tests"
        target_dir.mkdir(exist_ok=True)
        (scoped_repo / "src" / "bad.py").rename(target_dir / "ok.py")
        rc, _, out = _run(_stop_event(scoped_repo))
        assert out.strip() == ""


class TestNewFileBudget:
    def test_oversized_new_artifact_reported_not_evaluated(self, repo):
        assert _run(_session_start(repo))[0] == 0
        from mneme.integrations.claude_code import session_state as ss

        big = repo / "huge_generated.txt"
        big.write_text("import psycopg2\n" * (ss.MAX_FILE_BYTES // 16 + 5),
                       encoding="utf-8")
        assert big.stat().st_size > ss.MAX_FILE_BYTES
        rc, err, out = _run(_stop_event(repo))
        assert rc == 0
        emitted = json.loads(out)
        context = emitted["hookSpecificOutput"]["additionalContext"]
        assert "huge_generated.txt" in context
        assert "size budget" in context
        assert "decision" not in emitted


class TestBaselineIntegrity:
    def test_enumeration_failure_does_not_save_empty_baseline(self, repo, monkeypatch):
        import mneme.integrations.claude_code.session_state as ss

        monkeypatch.setattr(ss, "enumerate_repo_files", lambda root: None)
        assert ss.capture_baseline(repo) is None

    def test_unreadable_at_capture_never_attributed_as_new(self, repo, monkeypatch):
        """A placeholder entry makes the later readable state unevaluated."""
        import mneme.integrations.claude_code.session_state as ss
        from pathlib import Path as P

        real_read_bytes = P.read_bytes
        victim = repo / "shy.txt"
        victim.write_text("locked at capture time\n", encoding="utf-8")

        def flaky(self):
            if self == victim:
                raise PermissionError("transient lock")
            return real_read_bytes(self)

        monkeypatch.setattr(P, "read_bytes", flaky)
        base = ss.capture_baseline(repo)
        assert base["files"]["shy.txt"]["sha256"] == ss._UNAVAILABLE_SHA
        monkeypatch.setattr(P, "read_bytes", real_read_bytes)

        d = ss.compute_session_delta(repo, base)
        assert "shy.txt" not in d.new
        assert "not evaluated" in d.skipped.get("shy.txt", "")
