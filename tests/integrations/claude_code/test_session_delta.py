"""ADR-021: session baseline capture and delta attribution.

The baseline is captured once per session; only inserted/replaced lines of
the session's own diff may be attributed to it. Pre-session dirty state,
untouched untracked artifacts, and deletions must never be attributed.
"""
import json
import subprocess
from pathlib import Path

import pytest

from mneme.integrations.claude_code import session_state as ss


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
    return work


def _tracked(repo: Path, rel: str, body: str):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", rel], check=True)


def _commit(repo: Path, msg="c"):
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "-m", msg],
        check=True,
    )


def _capture(repo: Path) -> dict:
    return ss.capture_baseline(repo)


class TestEnumeration:
    def test_lists_tracked_and_untracked_not_ignored(self, repo):
        _tracked(repo, "src/a.py", "a = 1\n")
        _tracked(repo, ".gitignore", "ignored*\n")
        _commit(repo)
        (repo / "src" / "b.py").write_text("b = 2\n", encoding="utf-8")      # untracked
        (repo / "ignored.log").write_text("x\n", encoding="utf-8")           # ignored
        files = ss.enumerate_repo_files(repo)
        assert files is not None
        assert "src/a.py" in files
        assert "src/b.py" in files
        assert "ignored.log" not in files
        assert all("\\" not in f for f in files)

    def test_non_git_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MNEME_SESSION_STATE_DIR", str(tmp_path / "state"))
        plain = tmp_path / "plain"
        plain.mkdir()
        assert ss.enumerate_repo_files(plain) is None


class TestDelta:
    def test_new_untracked_attributed_in_full(self, repo):
        (repo / "gen.py").write_text("x = 1\n", encoding="utf-8")
        base = _capture(repo)
        (repo / "gen.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
        # gen.py existed at capture time (untracked), then grew.
        d = ss.compute_session_delta(repo, base)
        assert "gen.py" in d.modified
        assert d.modified["gen.py"] == "y = 2"

    def test_brand_new_artifact_introduces_everything(self, repo):
        base = _capture(repo)
        (repo / "new.py").write_text("a = 1\n", encoding="utf-8")
        d = ss.compute_session_delta(repo, base)
        assert "new.py" in d.new
        assert "new.py" not in d.modified

    def test_pre_session_dirty_untouched_not_attributed(self, repo):
        (repo / "dirty.py").write_text("bad = 1\n", encoding="utf-8")  # untracked, pre-delta
        base = _capture(repo)
        d = ss.compute_session_delta(repo, base)
        assert "dirty.py" not in d.new
        assert "dirty.py" not in d.modified

    def test_edit_to_dirty_artifact_attributes_only_own_lines(self, repo):
        (repo / "dirty.py").write_text("keep_old_violation = 1\nstable = 0\n", encoding="utf-8")
        base = _capture(repo)
        (repo / "dirty.py").write_text(
            "keep_old_violation = 1\nstable = 0\nfresh_line = 3\n", encoding="utf-8"
        )
        d = ss.compute_session_delta(repo, base)
        assert d.modified["dirty.py"] == "fresh_line = 3"

    def test_removing_preexisting_lines_introduces_nothing(self, repo):
        (repo / "f.py").write_text("a = 1\nb = 2\n", encoding="utf-8")
        base = _capture(repo)
        (repo / "f.py").write_text("a = 1\n", encoding="utf-8")
        d = ss.compute_session_delta(repo, base)
        assert "f.py" not in d.modified, "a removal introduces no content"

    def test_deletion_reported_separately_never_as_content(self, repo):
        _tracked(repo, "gone.py", "x = 1\n")
        _commit(repo)
        base = _capture(repo)
        (repo / "gone.py").unlink()
        d = ss.compute_session_delta(repo, base)
        assert "gone.py" in d.deleted
        assert "gone.py" not in d.modified
        assert "gone.py" not in d.new

    def test_unchanged_tracked_artifact_skipped(self, repo):
        _tracked(repo, "same.py", "x = 1\n")
        _commit(repo)
        base = _capture(repo)
        d = ss.compute_session_delta(repo, base)
        assert "same.py" not in d.modified and "same.py" not in d.new


class TestSnapshotStore:
    def test_snapshot_lands_outside_repo_and_keys_by_root_and_session(self, repo, tmp_path, monkeypatch):
        state_dir = tmp_path / "state"
        monkeypatch.setenv("MNEME_SESSION_STATE_DIR", str(state_dir))
        p1 = ss.snapshot_path(repo, "sess-a")
        p2 = ss.snapshot_path(repo, "sess-b")
        other = tmp_path / "other-repo"
        other.mkdir()
        p3 = ss.snapshot_path(other, "sess-a")
        assert p1 != p2 != p3
        assert state_dir in p1.parents
        assert repo not in p1.parents

    def test_save_and_load_roundtrip(self, repo, tmp_path, monkeypatch):
        state_dir = tmp_path / "state"
        monkeypatch.setenv("MNEME_SESSION_STATE_DIR", str(state_dir))
        snap = ss.capture_baseline(repo)
        path = ss.snapshot_path(repo, "s1")
        ss.save_snapshot(path, snap)
        loaded = ss.load_snapshot(path)
        assert loaded == snap

    def test_corrupt_snapshot_loads_as_none(self, repo, tmp_path, monkeypatch):
        state_dir = tmp_path / "state"
        monkeypatch.setenv("MNEME_SESSION_STATE_DIR", str(state_dir))
        path = ss.snapshot_path(repo, "s1")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ not json", encoding="utf-8")
        assert ss.load_snapshot(path) is None

    def test_foreign_root_snapshot_loads_as_none(self, repo, tmp_path, monkeypatch):
        state_dir = tmp_path / "state"
        monkeypatch.setenv("MNEME_SESSION_STATE_DIR", str(state_dir))
        snap = ss.capture_baseline(repo)
        path = ss.snapshot_path(repo, "s1")
        ss.save_snapshot(path, snap)
        assert ss.load_snapshot(path, expected_root=repo) is not None
        moved = json.loads(json.dumps(snap))
        moved["root"] = str(tmp_path / "somewhere-else")
        path.write_text(json.dumps(moved), encoding="utf-8")
        assert ss.load_snapshot(path, expected_root=repo) is None

    def test_oversized_artifact_hashed_but_body_absent(self, repo, monkeypatch):
        big = repo / "big.txt"
        big.write_text("x" * (ss.MAX_FILE_BYTES + 10), encoding="utf-8")
        snap = ss.capture_baseline(repo)
        entry = snap["files"]["big.txt"]
        assert entry["content"] is None
        assert len(entry["sha256"]) == 64

    def test_non_utf8_artifact_hashed_but_body_absent(self, repo):
        (repo / "blob.bin").write_bytes(b"\xff\xfe\x00binary")
        snap = ss.capture_baseline(repo)
        assert snap["files"]["blob.bin"]["content"] is None
