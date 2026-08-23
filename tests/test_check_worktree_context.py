"""Tests for scripts/check_worktree_context.py.

Each test builds a small real git repository in a tmp_path so the checker's
subprocess calls run against actual git state, including the detached-HEAD
condition which cannot be faked with mocks.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_worktree_context.py"

spec = importlib.util.spec_from_file_location("check_worktree_context", SCRIPT)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def _git(repo: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8"
    )
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"


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
    (git_repo / "file.txt").write_text("two\n", encoding="utf-8")
    _git(git_repo, "add", "file.txt")
    _git(git_repo, "commit", "-m", "second")
    return git_repo


def test_correct_branch_and_worktree_passes(repo: Path) -> None:
    state = check.gather_state(repo)
    failures = check.evaluate(state, repo, "main")
    assert failures == []


def test_wrong_branch_fails(repo: Path) -> None:
    _git(repo, "switch", "-c", "other-task")
    state = check.gather_state(repo)
    failures = check.evaluate(state, repo, "main")
    assert len(failures) == 1
    assert "branch mismatch" in failures[0]
    assert "expected branch: main" in failures[0]
    assert "actual branch:   other-task" in failures[0]


def test_wrong_worktree_fails(repo: Path, tmp_path: Path) -> None:
    other = tmp_path / "elsewhere"
    other.mkdir()
    state = check.gather_state(repo)
    failures = check.evaluate(state, other, "main")
    assert len(failures) == 1
    assert "worktree mismatch" in failures[0]


def test_detached_head_fails(repo: Path) -> None:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    _git(repo, "checkout", "--detach", head)
    state = check.gather_state(repo)
    failures = check.evaluate(state, repo, "main")
    assert len(failures) == 1
    assert "detached HEAD" in failures[0]


def test_missing_expected_branch_argument_fails(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        check.main(["--expected-root", str(REPO_ROOT)])
    assert excinfo.value.code != 0
    assert "required" in capsys.readouterr().err.lower()


def test_missing_expected_root_argument_fails(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        check.main(["--expected-branch", "main"])
    assert excinfo.value.code != 0
    assert "required" in capsys.readouterr().err.lower()


def test_main_passes_against_live_repo() -> None:
    """Self-check: running main() against this checkout with its own facts passes."""
    toplevel = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=REPO_ROOT, capture_output=True, text=True
    ).stdout.strip()
    if not branch:
        pytest.skip("tests are running from a detached HEAD checkout")
    assert check.main(["--expected-root", str(toplevel), "--expected-branch", branch]) == 0


def test_not_a_git_repository_fails(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    state = check.gather_state(empty)
    failures = check.evaluate(state, empty, "main")
    assert len(failures) == 1
    assert "not a git repository" in failures[0]
