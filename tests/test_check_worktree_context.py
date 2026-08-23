"""Tests for scripts/check_worktree_context.py.

Each test builds a small real git repository in a tmp_path so the checker's
subprocess calls run against actual git state, including the detached-HEAD
condition which cannot be faked with mocks.
"""
from __future__ import annotations

import importlib.util
import json
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


def test_missing_expected_branch_argument_falls_back_to_context_file(repo: Path) -> None:
    """Without --expected-branch the checker falls back to .mneme/task_context.json."""
    _write_task_context(repo, "main", repo)
    assert check.main(["--expected-root", str(repo)], repo=repo) == 0


def test_missing_expected_root_argument_falls_back_to_context_file(repo: Path) -> None:
    _write_task_context(repo, "main", repo)
    assert check.main(["--expected-branch", "main"], repo=repo) == 0


def test_missing_both_arguments_and_no_context_file_fails_closed(repo: Path) -> None:
    assert check.main([], repo=repo) == 1


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


# --- task context file (.mneme/task_context.json) resolution ---


def _write_task_context(repo: Path, branch: str, worktree: Path, raw: str | None = None) -> None:
    context_dir = repo / ".mneme"
    context_dir.mkdir(exist_ok=True)
    if raw is not None:
        (context_dir / "task_context.json").write_text(raw, encoding="utf-8")
    else:
        payload = {"branch": branch, "worktree": str(worktree)}
        (context_dir / "task_context.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )


def test_load_task_context_reads_file(repo: Path) -> None:
    _write_task_context(repo, "feat/example", repo)
    context = check.load_task_context(repo)
    assert context == {"branch": "feat/example", "worktree": str(repo)}


def test_load_task_context_missing_returns_none(repo: Path) -> None:
    assert check.load_task_context(repo) is None


def test_load_task_context_malformed_raises(repo: Path) -> None:
    _write_task_context(repo, "", repo, raw="{not json")
    with pytest.raises(json.JSONDecodeError):
        check.load_task_context(repo)
    _write_task_context(repo, "", repo, raw='{"branch": "main"}')
    with pytest.raises(ValueError):
        check.load_task_context(repo)


def test_main_no_args_uses_task_context_passes(repo: Path) -> None:
    _write_task_context(repo, "main", repo)
    assert check.main([], repo=repo) == 0


def test_main_no_args_task_context_branch_mismatch_fails(repo: Path) -> None:
    _write_task_context(repo, "some/other-branch", repo)
    assert check.main([], repo=repo) == 1


def test_main_no_args_task_context_wrong_worktree_fails(repo: Path, tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    _write_task_context(repo, "main", elsewhere)
    assert check.main([], repo=repo) == 1


def test_main_no_args_without_task_context_fails_closed(repo: Path) -> None:
    assert check.main([], repo=repo) == 1


def test_explicit_args_override_task_context(repo: Path) -> None:
    _write_task_context(repo, "stale/branch", tmp_path_factory := repo.parent / "stale-wt")
    assert (
        check.main(["--expected-root", str(repo), "--expected-branch", "main"], repo=repo) == 0
    )


# --- new_task_worktree provisioning ---


@pytest.fixture()
def provisioner():
    spec = importlib.util.spec_from_file_location(
        "new_task_worktree", REPO_ROOT / "scripts" / "new_task_worktree.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_slugify(provisioner) -> None:
    assert provisioner.slugify("feat/example-task") == "feat-example-task"
    assert provisioner.slugify("ci/pytest_merge_gate") == "ci-pytest-merge-gate"


def test_git_calls_are_scoped_to_script_repo_root(provisioner, tmp_path, monkeypatch) -> None:
    """Regression: git calls must target the script's repo, not the caller's cwd."""
    recorded = {}

    def fake_run(cmd, **kwargs):
        recorded["cwd"] = kwargs.get("cwd")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(provisioner.subprocess, "run", fake_run)
    unrelated_cwd = tmp_path / "unrelated"
    unrelated_cwd.mkdir()
    result = provisioner.create_task_worktree(
        "feat/regression", "origin/main", tmp_path / "wt"
    )
    assert result == 0
    assert recorded["cwd"] is not None
    assert Path(recorded["cwd"]).resolve() == REPO_ROOT.resolve()
