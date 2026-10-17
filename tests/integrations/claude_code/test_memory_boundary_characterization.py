"""D5 + P2 charter §6: characterize today's memory discovery across Git boundaries.

Charter: docs/plans/2026-10-17-t08-d5-p2-memory-resolution-charter.md (§6),
implementing the accepted D5 boundary contract and D6/Q2 P2 precedence rule.

These tests pin ``main``'s behavior **before** any change: ``find_memory``
ignores ``.git`` entirely and ``MNEME_MEMORY`` always wins. They are
characterization, not endorsement. The shared D5 + P2 implementation PR is
expected to flip these assertions to the charter §3.3 outcomes, and that flip
is the reviewable diff of the behavior change. No runtime code is touched here.

Every case checks both the bare walk (``find_memory``) and the start directory
the Claude Code direct-write gate actually uses (``_direct_write_memory_start``).
"""
import io
import json
import subprocess
from pathlib import Path

import pytest

from mneme.integrations.claude_code import hook

META = {"name": "d5", "description": "d", "version": "0", "owner": "t", "created": "2026-10-17"}
PROTECTED = {"meta": META, "items": [], "decisions": [{
    "id": "D5-DEC", "decision": "The application uses SQLite; do not introduce a PostgreSQL client.",
    "rationale": "r", "scope": ["db"], "constraints": [], "anti_patterns": [],
    "rules": [{"type": "FORBID_LITERAL", "value": "psycopg2"}],
}]}
PERMISSIVE = {"meta": META, "items": [], "decisions": [{
    "id": "PERM-001", "decision": "Prefer small functions.", "rationale": "r",
    "scope": ["style"], "constraints": [], "anti_patterns": [], "rules": [],
}]}

SEED = "import os\n\ndef existing():\n    return 1\n"
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
       "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("MNEME_HOOK_MODE", "CLAUDE_PLUGIN_OPTION_MODE", "MNEME_MEMORY"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def root(tmp_path):
    r = tmp_path.resolve()
    # Precondition: nothing above tmp_path governs, so every selection below
    # comes from the layout built here.
    assert hook.find_memory(r) is None, "an ancestor of tmp_path has a .mneme memory"
    return r


def _git_init(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    subprocess.run([*GIT, "init", "-q"], cwd=d, check=True)


def _write_mem(d: Path, mem: dict) -> Path:
    (d / ".mneme").mkdir(parents=True, exist_ok=True)
    p = d / ".mneme" / "project_memory.json"
    p.write_text(json.dumps(mem, indent=2), encoding="utf-8")
    return p


def _target(d: Path, name: str = "app.py") -> Path:
    d.mkdir(parents=True, exist_ok=True)
    t = d / name
    t.write_text(SEED, encoding="utf-8")
    return t


def _edit(target: Path, cwd: Path) -> dict:
    return {
        "hook_event_name": "PreToolUse", "tool_name": "Edit", "cwd": str(cwd),
        "tool_input": {"file_path": str(target), "old_string": "import os",
                       "new_string": "import psycopg2"},
    }


def _selected(target: Path, cwd: Path):
    """Memory chosen by the bare walk and by the direct-write gate's start."""
    walk = hook.find_memory(target.parent)
    gate = hook.find_memory(hook._direct_write_memory_start(hook.parse_event(json.dumps(_edit(target, cwd)))))
    return walk, gate


def _run(envelope: dict):
    err, out = io.StringIO(), io.StringIO()
    rc = hook.main(stdin=io.StringIO(json.dumps(envelope)), stderr=err, stdout=out)
    return rc, err.getvalue()


def test_l4_task_worktree_without_memory_crosses_into_outer_checkout(root):
    """L4: a linked worktree nested in another checkout, with no memory of its own.

    Today the walk ignores the worktree's ``.git`` file and selects the outer
    checkout's memory. Charter §3.3 row 4 (BOUNDARY_SHADOWS_MEMORY) replaces this.
    """
    outer = root / "outer"
    _git_init(outer)
    (outer / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run([*GIT, "add", "README.md"], cwd=outer, check=True)
    subprocess.run([*GIT, "commit", "-q", "-m", "seed"], cwd=outer, check=True)
    # Memory exists in the outer working tree but is not on the worktree's branch.
    mem_outer = _write_mem(outer, PROTECTED)
    wt = outer / ".worktrees" / "wt"
    subprocess.run([*GIT, "worktree", "add", "-q", "-b", "wt", str(wt)], cwd=outer, check=True)
    assert (wt / ".git").is_file(), "a linked worktree's .git must be a file"
    assert not (wt / ".mneme").exists()

    target = _target(wt)
    assert _selected(target, wt) == (mem_outer, mem_outer)


def test_l5_submodule_style_git_file_without_memory_uses_outer_memory(root):
    """L5: an inner repository marked by a ``.git`` file, with no memory of its own.

    Today the outer repository's memory governs the inner one. Charter §3.3
    row 4 replaces this; row 3 keeps it only when the override names it.
    """
    outer = root / "outer"
    _git_init(outer)
    mem_outer = _write_mem(outer, PROTECTED)
    sub = outer / "libs" / "sub"
    sub.mkdir(parents=True)
    (outer / ".git" / "modules" / "sub").mkdir(parents=True)
    (sub / ".git").write_text("gitdir: ../../.git/modules/sub\n", encoding="utf-8")

    target = _target(sub)
    assert _selected(target, sub) == (mem_outer, mem_outer)


def test_l6_parent_directory_memory_governs_repository_without_memory(root):
    """L6: a memory above a Git repository that has none (parent fallback).

    The parent is not itself a repository. Today its memory governs.
    """
    parent = root / "workspace"
    mem_parent = _write_mem(parent, PROTECTED)
    repo = parent / "repo"
    _git_init(repo)

    target = _target(repo / "src")
    assert _selected(target, repo) == (mem_parent, mem_parent)


def test_l8b_invalid_git_marker_is_ignored_by_the_walk(root):
    """L8b: a ``.git`` file whose ``gitdir:`` target is missing.

    Today the walk ignores it and continues upward. Under D5 B1 an existing
    marker is a boundary whether or not Git considers it valid.
    """
    outer = root / "outer"
    _git_init(outer)
    mem_outer = _write_mem(outer, PROTECTED)
    inner = outer / "broken"
    inner.mkdir()
    (inner / ".git").write_text("gitdir: ../does-not-exist\n", encoding="utf-8")
    assert not (outer / "does-not-exist").exists()

    target = _target(inner)
    assert _selected(target, inner) == (mem_outer, mem_outer)


class TestPlantedMarkerPlusOverride:
    """D6/Q2 §5 rule 2 adversarial layout: repo A's memory, ``A/src/.git`` planted.

    Today the planted marker changes nothing, and ``MNEME_MEMORY`` always wins.
    Charter §3.3 row 5 (OVERRIDE_REFUSED_AT_BOUNDARY) replaces the override case.
    """

    @pytest.fixture
    def layout(self, root):
        a = root / "repo_a"
        _git_init(a)
        mem_a = _write_mem(a, PROTECTED)
        b = root / "repo_b"
        _git_init(b)
        mem_b = _write_mem(b, PERMISSIVE)
        src = a / "src"
        src.mkdir()
        (src / ".git").write_text("", encoding="utf-8")  # planted, existence-only
        return a, mem_a, mem_b, _target(src)

    def test_without_override_the_planted_marker_is_ignored(self, layout):
        a, mem_a, _, target = layout
        assert _selected(target, a) == (mem_a, mem_a)

    def test_override_replaces_repository_memory(self, layout, monkeypatch):
        a, _, mem_b, target = layout
        monkeypatch.setenv("MNEME_MEMORY", str(mem_b))
        assert _selected(target, a) == (mem_b, mem_b)

    def test_forbidden_edit_is_blocked_without_override(self, layout):
        a, _, _, target = layout
        rc, err = _run(_edit(target, a))
        assert rc == 2
        assert "D5-DEC" in err

    def test_forbidden_edit_is_permitted_under_override(self, layout, monkeypatch):
        """The wrong-memory outcome D6/Q2 records: B's memory, forbidden edit permitted."""
        a, _, mem_b, target = layout
        monkeypatch.setenv("MNEME_MEMORY", str(mem_b))
        rc, err = _run(_edit(target, a))
        assert rc == 0
        assert "D5-DEC" not in err
