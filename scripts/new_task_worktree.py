#!/usr/bin/env python3
"""Provision a fresh task-owned worktree with its expected identity recorded.

Implements the Worktree Lifecycle policy in CLAUDE.md:

    one task -> one branch -> one worktree -> one PR/outcome -> teardown

Creates a worktree and branch from the current base ref (default
origin/main), then writes .mneme/task_context.json inside it so
scripts/check_worktree_context.py (and the pre-commit hook) can verify
execution context without being told explicitly.

Usage:
  python scripts/new_task_worktree.py <branch> [--path PATH] [--base REF]

Defaults:
  path = <repo-root>/.worktrees/<branch-slug>
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    # Always operate on the repository that owns this script, regardless of
    # the invoking shell's cwd. Otherwise a relative worktree path or fetch
    # could silently target an unrelated checkout.
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8"
    )


def slugify(branch: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", branch).strip("-").lower()
    return slug or "task"


def create_task_worktree(branch: str, base: str, path: Path) -> int:
    result = _git("fetch", "origin", "--prune")
    if result.returncode != 0:
        print(f"[new-task] fetch failed:\n{result.stderr}", file=sys.stderr)
        return 1

    result = _git("worktree", "add", str(path), "-b", branch, base)
    if result.returncode != 0:
        print(f"[new-task] worktree add failed:\n{result.stderr}", file=sys.stderr)
        return 1

    context_dir = path / ".mneme"
    context_dir.mkdir(parents=True, exist_ok=True)
    context = {"branch": branch, "worktree": str(path)}
    (context_dir / "task_context.json").write_text(
        json.dumps(context, indent=2) + "\n", encoding="utf-8"
    )

    print(f"[new-task] worktree: {path}")
    print(f"[new-task] branch:   {branch} (from {base})")
    print(f"[new-task] context:  {context_dir / 'task_context.json'}")
    print("[new-task] next: run your agent session in that directory;")
    print("           scripts/check_worktree_context.py now verifies automatically.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("branch", help="dedicated task branch to create")
    parser.add_argument("--path", default=None, help="worktree location (default .worktrees/<slug>)")
    parser.add_argument("--base", default="origin/main", help="base ref (default origin/main)")
    args = parser.parse_args(argv)

    path = Path(args.path) if args.path else REPO_ROOT / ".worktrees" / slugify(args.branch)
    if not path.is_absolute():
        path = REPO_ROOT / path
    if path.exists():
        print(f"[new-task] FAIL -- path already exists: {path}", file=sys.stderr)
        return 1
    return create_task_worktree(args.branch, args.base, path)


if __name__ == "__main__":
    sys.exit(main())
