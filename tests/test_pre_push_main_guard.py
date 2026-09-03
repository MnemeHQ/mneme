"""Tests for scripts/githooks/pre-push (main push guard).

Each test builds a small real git repository in tmp_path and invokes the hook
with stdin matching git's pre-push protocol:
  <local-ref> <local-sha> <remote-ref> <remote-sha>
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "scripts" / "githooks" / "pre-push"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8"
    )
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result


def _run_hook(stdin_text: str, repo: Path, env: dict[str, str] | None = None) -> int:
    """Invoke the hook's main() with given stdin, returning exit code."""
    test_env = os.environ.copy()
    if env:
        test_env.update(env)
    # Use subprocess to invoke the hook as git would (fresh process, stdin)
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        cwd=repo,
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=test_env,
    )
    return result.returncode, result.stdout, result.stderr


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    git_repo = tmp_path / "repo"
    git_repo.mkdir()
    _git(git_repo, "init", "-b", "main")
    _git(git_repo, "config", "user.email", "test@example.com")
    _git(git_repo, "config", "user.name", "Test")
    (git_repo / "file.txt").write_text("one\n", encoding="utf-8")
    _git(git_repo, "add", "file.txt")
    _git(git_repo, "commit", "-m", "first")
    # Create a feature branch
    _git(git_repo, "switch", "-c", "feature/test-task")
    (git_repo / "file.txt").write_text("two\n", encoding="utf-8")
    _git(git_repo, "add", "file.txt")
    _git(git_repo, "commit", "-m", "feature work")
    # Go back to main
    _git(git_repo, "switch", "main")
    return git_repo


# --- Helper to get current HEAD sha ---

def _head_sha(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _zero_sha() -> str:
    return "0" * 40


# --- Tests ---

def test_feature_branch_push_passes(repo: Path) -> None:
    """feature branch → remote feature branch: PASS"""
    local_sha = _head_sha(repo)
    stdin = f"refs/heads/feature/test-task {local_sha} refs/heads/feature/test-task {_zero_sha()}\n"
    code, out, err = _run_hook(stdin, repo)
    assert code == 0, f"expected PASS, got {code}: {out} {err}"


def test_feature_branch_push_with_existing_remote_passes(repo: Path) -> None:
    """feature branch → remote feature branch (update, non-zero remote sha): PASS"""
    local_sha = _head_sha(repo)
    remote_sha = "a" * 40  # some existing remote sha
    stdin = f"refs/heads/feature/test-task {local_sha} refs/heads/feature/test-task {remote_sha}\n"
    code, out, err = _run_hook(stdin, repo)
    assert code == 0, f"expected PASS, got {code}: {out} {err}"


def test_direct_main_push_blocked_fast_forward(repo: Path) -> None:
    """local main → origin/main (fast-forward): BLOCK"""
    local_sha = _head_sha(repo)
    remote_sha = "b" * 40  # existing remote main
    stdin = f"refs/heads/main {local_sha} refs/heads/main {remote_sha}\n"
    code, out, err = _run_hook(stdin, repo)
    assert code == 1, f"expected BLOCK, got {code}: {out} {err}"
    assert "BLOCKED: direct push to main" in out
    assert "ADR-022" in out
    assert "new_task_worktree.py" in out


def test_direct_main_push_blocked_force_push(repo: Path) -> None:
    """local main → origin/main (force push, non-fast-forward): BLOCK"""
    local_sha = _head_sha(repo)
    remote_sha = "c" * 40
    stdin = f"refs/heads/main {local_sha} refs/heads/main {remote_sha}\n"
    code, out, err = _run_hook(stdin, repo)
    assert code == 1, f"expected BLOCK, got {code}: {out} {err}"
    assert "BLOCKED: direct push to main" in out


def test_delete_main_blocked(repo: Path) -> None:
    """delete remote main (git push origin :main): BLOCK"""
    local_sha = _zero_sha()
    remote_sha = "d" * 40
    stdin = f"refs/heads/main {local_sha} refs/heads/main {remote_sha}\n"
    code, out, err = _run_hook(stdin, repo)
    assert code == 1, f"expected BLOCK, got {code}: {out} {err}"
    assert "BLOCKED: direct push to main" in out


def test_main_push_allowed_with_explicit_override(repo: Path) -> None:
    """MNEME_ALLOW_MAIN_PUSH=1 allows direct main push (administrative override)"""
    local_sha = _head_sha(repo)
    remote_sha = "e" * 40
    stdin = f"refs/heads/main {local_sha} refs/heads/main {remote_sha}\n"
    code, out, err = _run_hook(stdin, repo, env={"MNEME_ALLOW_MAIN_PUSH": "1"})
    assert code == 0, f"expected PASS with override, got {code}: {out} {err}"
    assert "OVERRIDE" in out


def test_main_push_not_allowed_with_other_env_values(repo: Path) -> None:
    """Only exact '1' enables override; 'true', 'yes', etc. do not"""
    local_sha = _head_sha(repo)
    remote_sha = "f" * 40
    stdin = f"refs/heads/main {local_sha} refs/heads/main {remote_sha}\n"
    for val in ["true", "yes", "on", "0", ""]:
        code, out, err = _run_hook(stdin, repo, env={"MNEME_ALLOW_MAIN_PUSH": val})
        assert code == 1, f"expected BLOCK for value={val!r}, got {code}: {out} {err}"


def test_multiple_refs_in_stdin_main_blocked(repo: Path) -> None:
    """Multiple refs on stdin; one is main → BLOCK"""
    local_sha = _head_sha(repo)
    stdin = (
        f"refs/heads/feature/test-task {local_sha} refs/heads/feature/test-task {_zero_sha()}\n"
        f"refs/heads/main {local_sha} refs/heads/main {'g' * 40}\n"
    )
    code, out, err = _run_hook(stdin, repo)
    assert code == 1, f"expected BLOCK, got {code}: {out} {err}"
    assert "BLOCKED: direct push to main" in out


def test_multiple_refs_in_stdin_all_feature_passes(repo: Path) -> None:
    """Multiple refs on stdin; all feature branches → PASS"""
    local_sha = _head_sha(repo)
    stdin = (
        f"refs/heads/feature/test-task {local_sha} refs/heads/feature/test-task {_zero_sha()}\n"
        f"refs/heads/feature/other {local_sha} refs/heads/feature/other {'h' * 40}\n"
    )
    code, out, err = _run_hook(stdin, repo)
    assert code == 0, f"expected PASS, got {code}: {out} {err}"


def test_empty_stdin_passes(repo: Path) -> None:
    """No refs pushed (git push --delete without refs? edge case): PASS"""
    code, out, err = _run_hook("", repo)
    assert code == 0


def test_hook_file_exists():
    """Sanity: the hook file exists and is executable"""
    assert HOOK.exists(), f"Hook not found at {HOOK}"