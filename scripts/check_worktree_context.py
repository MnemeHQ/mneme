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
import subprocess
import sys
from pathlib import Path


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--expected-root", required=True, help="worktree root this task must run in")
    parser.add_argument("--expected-branch", required=True, help="branch this task must be on")
    args = parser.parse_args(argv)

    repo = Path.cwd()
    state = gather_state(repo)
    failures = evaluate(state, Path(args.expected_root), args.expected_branch)
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
