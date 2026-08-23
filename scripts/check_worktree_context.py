#!/usr/bin/env python3
"""Assert that the current execution context matches the task's declared identity.

Agents working in shared repositories with multiple worktrees can inherit an
unexpected checkout (wrong worktree, wrong branch, detached HEAD) and commit
to it without noticing. This checker makes branch identity an explicit,
verified precondition instead of agent discretion.

The expected context is provided by the orchestrating task, never chosen by
the agent. The checker is read-only: it never modifies repository state.

Usage:
  python scripts/check_worktree_context.py --expected-root PATH --expected-branch NAME

Exit codes:
  0  actual root == expected root AND branch == expected AND HEAD attached
  1  any mismatch or missing argument (fail closed)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

TASK_CONTEXT_FILENAME = ".mneme/task_context.json"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def gather_state(repo: Path) -> dict[str, object]:
    """Collect actual execution-context facts by querying git in `repo`."""
    toplevel = _git(repo, "rev-parse", "--show-toplevel")
    branch = _git(repo, "branch", "--show-current")
    symbolic = _git(repo, "symbolic-ref", "-q", "HEAD")
    return {
        "toplevel": toplevel.stdout.strip() if toplevel.returncode == 0 else None,
        "toplevel_ok": toplevel.returncode == 0,
        "branch": branch.stdout.strip(),
        "attached": symbolic.returncode == 0,
    }


def evaluate(state: dict[str, object], expected_root: Path, expected_branch: str) -> list[str]:
    """Return a list of failure descriptions; empty list means PASS."""
    failures: list[str] = []
    if not state["toplevel_ok"]:
        failures.append(f"not a git repository (or worktree): {expected_root}")
        return failures
    actual_root = Path(str(state["toplevel"])).resolve()
    if actual_root != expected_root.resolve():
        failures.append(
            f"worktree mismatch:\n    expected root:   {expected_root.resolve()}\n"
            f"    actual root:     {actual_root}"
        )
    if not state["attached"]:
        failures.append("detached HEAD (no branch is checked out)")
    elif state["branch"] != expected_branch:
        failures.append(
            f"branch mismatch:\n    expected branch: {expected_branch}\n"
            f"    actual branch:   {state['branch']}"
        )
    return failures


def load_task_context(repo: Path) -> dict[str, str] | None:
    """Return the task context written by scripts/new_task_worktree.py, if any.

    Expected shape: {"branch": "<task-branch>", "worktree": "<worktree-root>"}.
    Returns None when the file does not exist; raises ValueError on malformed
    content so callers can fail closed.
    """
    path = repo / TASK_CONTEXT_FILENAME
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "branch" not in data or "worktree" not in data:
        raise ValueError(f"{TASK_CONTEXT_FILENAME} must be an object with 'branch' and 'worktree' keys")
    return {"branch": str(data["branch"]), "worktree": str(data["worktree"])}


def main(argv: list[str] | None = None, repo: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--expected-root", default=None, help="worktree root this task must run in")
    parser.add_argument("--expected-branch", default=None, help="branch this task must be on")
    args = parser.parse_args(argv)

    repo = repo or Path.cwd()
    state = gather_state(repo)

    expected_root = args.expected_root
    expected_branch = args.expected_branch
    if expected_root is None or expected_branch is None:
        try:
            context = load_task_context(repo)
        except (json.JSONDecodeError, ValueError) as exc:
            print("[context-check] FAIL -- malformed task context")
            print(f"  {exc}")
            return 1
        if context is None:
            print(f"[context-check] FAIL -- no explicit arguments and no {TASK_CONTEXT_FILENAME} found")
            print("  Provision a task worktree with: python scripts/new_task_worktree.py <branch>")
            print("  Or pass --expected-root/--expected-branch explicitly.")
            return 1
        expected_root = expected_root or context["worktree"]
        expected_branch = expected_branch or context["branch"]

    failures = evaluate(state, Path(expected_root), expected_branch)
    if not failures:
        print(
            f"[context-check] OK (root={Path(str(state['toplevel'])).resolve()}, "
            f"branch={state['branch']})"
        )
        return 0
    print("[context-check] FAIL -- do not proceed; abort any pending commit")
    for failure in failures:
        print(f"  {failure}")
    print("  Fix: switch to the declared worktree/branch for this task before continuing.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
