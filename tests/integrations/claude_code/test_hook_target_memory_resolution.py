"""T-08 slice 1: the direct-write gate selects memory from the edited target.

Charter: docs/plans/2026-10-15-t08-target-path-memory-resolution-charter.md
(§3, §5, §7.1), authorized by the slice-1 amendment in
docs/architecture/layer1-freeze-e73ff7d.md.

Ported from the fixture and envelopes of
docs/validation/artifacts/dg1f-t08-cwd-memory-selection-2026-10-15/repro_t08.py.
Every case drives the real ``hook.main`` and the real ``mneme check`` child in
disposable repositories. The only instrumentation is a pass-through spy on
``_invoke_check`` that records which memory the hook handed to the checker and
the checker's payload; it never alters the call or its result. No case applies
the edit, so file contents are not used as prevention evidence.

The first group is FIXED by slice 1 (on ``main`` the payload ``cwd`` chose the
memory). The second group is asserted UNCHANGED from ``main`` and is deferred
to charter §8 (D1, D3, D4, D6): these tests characterize current behavior and
are not an endorsement of it.
"""
import io
import json
import os
import subprocess
from pathlib import Path

import pytest

from mneme.integrations.claude_code import hook
from mneme.path_selectors import policy_root

META = {"name": "t08", "description": "d", "version": "0", "owner": "t", "created": "2026-10-15"}
PROTECTED = {"meta": META, "items": [], "decisions": [{
    "id": "T08-DEC", "decision": "The application uses SQLite; do not introduce a PostgreSQL client.",
    "rationale": "r", "scope": ["db"], "constraints": [], "anti_patterns": [],
    "rules": [{"type": "FORBID_LITERAL", "value": "psycopg2"}],
}]}
PERMISSIVE = {"meta": META, "items": [], "decisions": [{
    "id": "PERM-001", "decision": "Prefer small functions.", "rationale": "r",
    "scope": ["style"], "constraints": [], "anti_patterns": [], "rules": [],
}]}

SEED = "import os\n\ndef existing():\n    return 1\n"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("MNEME_HOOK_MODE", "CLAUDE_PLUGIN_OPTION_MODE", "MNEME_MEMORY"):
        monkeypatch.delenv(key, raising=False)


def _git_init(d: Path) -> None:
    d.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)


def _write_mem(d: Path, mem: dict) -> Path:
    (d / ".mneme").mkdir(parents=True, exist_ok=True)
    p = d / ".mneme" / "project_memory.json"
    p.write_text(json.dumps(mem, indent=2), encoding="utf-8")
    return p


class Env:
    """The repro_t08 layout: protected repo_a, permissive sibling repo_b."""

    def __init__(self, root: Path):
        self.root = root
        self.repo_a = root / "repo_a"          # protected
        self.repo_b = root / "repo_b"          # permissive sibling repo
        self.plain = root / "plain"            # no memory anywhere up the tree
        _git_init(self.repo_a)
        _git_init(self.repo_b)
        self.plain.mkdir()
        self.mem_a = _write_mem(self.repo_a, PROTECTED)
        self.mem_b = _write_mem(self.repo_b, PERMISSIVE)
        self.sub = self.repo_a / "vendor_tools"   # in-repo planted permissive memory
        self.sub.mkdir()
        self.mem_sub = _write_mem(self.sub, PERMISSIVE)
        self.target = self.repo_a / "app.py"
        self.target.write_text(SEED, encoding="utf-8")


@pytest.fixture
def env(tmp_path):
    e = Env(tmp_path.resolve())
    # Precondition for the "no memory" cases: nothing above tmp_path governs.
    assert hook.find_memory(e.plain) is None, "an ancestor of tmp_path has a .mneme memory"
    return e


@pytest.fixture
def spy(monkeypatch):
    """Record each real ``mneme check`` invocation; never alter it."""
    calls = []
    real = hook._invoke_check

    def _spy(memory, rel_label, target_path, checked_content, stderr=None, **kwargs):
        proc = real(memory, rel_label, target_path, checked_content, stderr=stderr, **kwargs)
        calls.append({
            "memory": Path(memory),
            "target_path": target_path,
            "payload": json.loads(proc.stdout) if proc is not None and proc.stdout else None,
        })
        return proc

    monkeypatch.setattr(hook, "_invoke_check", _spy)
    return calls


def _edit(cwd, file_path, old="import os", new="import psycopg2"):
    return {
        "hook_event_name": "PreToolUse", "tool_name": "Edit", "cwd": str(cwd),
        "tool_input": {"file_path": str(file_path), "old_string": old, "new_string": new},
    }


def _write(cwd, file_path, content="import psycopg2\n"):
    tool_input = {"content": content}
    if file_path is not None:
        tool_input["file_path"] = str(file_path)
    return {
        "hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": str(cwd),
        "tool_input": tool_input,
    }


def _run(envelope):
    err, out = io.StringIO(), io.StringIO()
    rc = hook.main(stdin=io.StringIO(json.dumps(envelope)), stderr=err, stdout=out)
    return rc, err.getvalue(), out.getvalue()


def _resolved_target(envelope) -> Path:
    file_path = Path(envelope["tool_input"]["file_path"])
    if not file_path.is_absolute():
        file_path = Path(envelope["cwd"]) / file_path
    return file_path.resolve()


def _assert_contained(call, envelope):
    """Charter §4/§7.1: the selected memory's policy root contains the target.

    So ``mneme check`` never evaluates a target outside the memory it was given,
    and every applicability trace carries a normalized (in-root) input path
    rather than the swallowed "outside policy root" error.
    """
    resolved = _resolved_target(envelope)
    root = policy_root(call["memory"])
    assert resolved.is_relative_to(root), (resolved, root)
    payload = call["payload"]
    assert payload is not None and payload["evaluation_complete"] is True
    expected = resolved.relative_to(root).as_posix()
    for trace in payload["applicability"]:
        assert trace["input_path"] == expected, trace
        assert "outside" not in (trace["reason"] or ""), trace


# ── FIXED by slice 1 ─────────────────────────────────────────────────────────


def test_v0_control_cwd_is_target_repo(env, spy):
    envelope = _edit(env.repo_a, env.target)
    rc, err, _ = _run(envelope)
    assert [c["memory"] for c in spy] == [env.mem_a]
    assert rc == 2
    assert "T08-DEC" in err
    _assert_contained(spy[0], envelope)


def test_v1_sibling_repo_cwd_does_not_select_memory(env, spy):
    """The live-confirmed L4 defect: a sibling-repo session cwd governed the edit."""
    envelope = _edit(env.repo_b, env.target)
    rc, err, _ = _run(envelope)
    assert [c["memory"] for c in spy] == [env.mem_a]
    assert rc == 2
    assert "T08-DEC" in err
    _assert_contained(spy[0], envelope)


def test_v2_cwd_without_memory(env, spy):
    envelope = _edit(env.plain, env.target)
    rc, err, _ = _run(envelope)
    assert [c["memory"] for c in spy] == [env.mem_a]
    assert rc == 2
    assert "T08-DEC" in err
    _assert_contained(spy[0], envelope)


def test_v3_planted_nested_memory_as_cwd_outside_its_subtree(env, spy):
    envelope = _edit(env.sub, env.target)
    rc, err, _ = _run(envelope)
    assert [c["memory"] for c in spy] == [env.mem_a]
    assert rc == 2
    assert "T08-DEC" in err
    _assert_contained(spy[0], envelope)


def test_v10a_protected_cwd_does_not_govern_sibling_repo(env, spy):
    """Accepted narrowing (charter §5): repo_a's rules no longer reach repo_b."""
    other = env.repo_b / "x.py"
    envelope = _write(env.repo_a, other)
    rc, err, _ = _run(envelope)
    assert [c["memory"] for c in spy] == [env.mem_b]
    assert rc == 0
    assert "T08-DEC" not in err
    _assert_contained(spy[0], envelope)
    assert spy[0]["payload"]["verdict"] == "PASS"


def test_v10b_protected_cwd_does_not_govern_ungoverned_file(env, spy):
    """Accepted narrowing (charter §5): an ungoverned file has no memory."""
    envelope = _write(env.repo_a, env.plain / "x.py")
    rc, err, out = _run(envelope)
    assert spy == [], "mneme check must not be invoked without a memory"
    assert rc == 0
    assert err == "" and out == ""


@pytest.mark.parametrize("cwd_name, file_path", [
    ("repo_a", "app.py"),
    ("repo_b", "../repo_a/app.py"),
])
def test_v11_relative_target_anchored_to_cwd(env, spy, monkeypatch, cwd_name, file_path):
    """A relative file_path is anchored to the payload cwd (path resolution only).

    Uses Write: materializing an Edit reads a relative file_path against the
    process cwd, which is outside slice 1. The process cwd is moved to a
    memory-less directory so only the payload cwd can anchor the target.
    """
    monkeypatch.chdir(env.plain)
    cwd = getattr(env, cwd_name)
    envelope = _write(cwd, file_path)
    rc, err, _ = _run(envelope)
    assert [c["memory"] for c in spy] == [env.mem_a]
    assert rc == 2
    assert "T08-DEC" in err
    _assert_contained(spy[0], envelope)


def test_write_into_not_yet_existing_directories(env, spy):
    """The walk passes through absent levels to reach repo_a/.mneme (charter §3)."""
    new_file = env.repo_a / "new_pkg" / "deep" / "mod.py"
    assert not new_file.parent.parent.exists()
    envelope = _write(env.repo_b, new_file)
    rc, err, _ = _run(envelope)
    assert [c["memory"] for c in spy] == [env.mem_a]
    assert rc == 2
    assert "T08-DEC" in err
    _assert_contained(spy[0], envelope)
    assert not new_file.parent.parent.exists(), "the hook must not create directories"


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError) as e:
        pytest.skip(f"symlinks unsupported here: {e}")


def test_symlink_target_selects_resolved_tree(env, spy):
    """repo_a/link.py -> repo_b/real.py: repo_b's memory governs the resolved file."""
    real = env.repo_b / "real.py"
    real.write_text(SEED, encoding="utf-8")
    link = env.repo_a / "link.py"
    _symlink_or_skip(link, real)
    envelope = _edit(env.repo_a, link)
    rc, err, _ = _run(envelope)
    assert [c["memory"] for c in spy] == [env.mem_b]
    assert rc == 0
    assert "T08-DEC" not in err
    _assert_contained(spy[0], envelope)


def test_symlink_into_protected_repo_is_governed_by_it(env, spy):
    """repo_b/link.py -> repo_a/app.py: a symlink cannot route around repo_a."""
    link = env.repo_b / "link.py"
    _symlink_or_skip(link, env.target)
    envelope = _edit(env.repo_b, link)
    rc, err, _ = _run(envelope)
    assert [c["memory"] for c in spy] == [env.mem_a]
    assert rc == 2
    assert "T08-DEC" in err
    _assert_contained(spy[0], envelope)


# ── UNCHANGED from main (characterization; deferred, charter §8) ─────────────


def test_v4_mneme_memory_missing_file_unchanged(env, spy, monkeypatch):
    """D6: MNEME_MEMORY precedence is unchanged; a missing override means no memory."""
    monkeypatch.setenv("MNEME_MEMORY", str(env.root / "nope.json"))
    rc, err, out = _run(_edit(env.repo_a, env.target))
    assert spy == []
    assert rc == 0
    assert err == "" and out == ""


def test_v5_mneme_memory_other_repo_unchanged(env, spy, monkeypatch):
    """D3/D6: the override still wins and still yields an out-of-root complete PASS."""
    monkeypatch.setenv("MNEME_MEMORY", str(env.mem_b))
    rc, err, _ = _run(_edit(env.repo_a, env.target))
    assert [c["memory"] for c in spy] == [env.mem_b]
    assert rc == 0
    assert "T08-DEC" not in err
    payload = spy[0]["payload"]
    assert payload["verdict"] == "PASS"
    assert payload["evaluation_complete"] is True


def test_v6_edit_under_planted_memory_unchanged(env, spy):
    """D4: the nearest memory still governs; the planted one shadows repo_a.

    cwd is the planted directory, the V6 setup on main, so main and slice 1
    select the same (planted) memory.
    """
    tool = env.sub / "tool.py"
    tool.write_text(SEED, encoding="utf-8")
    envelope = _edit(env.sub, tool)
    rc, err, _ = _run(envelope)
    assert [c["memory"] for c in spy] == [env.mem_sub]
    assert rc == 0
    assert "T08-DEC" not in err


def test_bash_heredoc_still_selects_memory_from_cwd(env, spy):
    """D1: the Bash class-A preflight is out of slice 1 and still uses cwd."""
    command = f"cat > {env.target.as_posix()} << 'EOF'\nimport psycopg2\nEOF"
    envelope = {
        "hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(env.repo_b),
        "tool_input": {"command": command},
    }
    rc, err, _ = _run(envelope)
    assert [c["memory"] for c in spy] == [env.mem_b]
    assert rc == 0
    assert "T08-DEC" not in err


@pytest.mark.parametrize("cwd_name, expected_rc", [("repo_a", 2), ("repo_b", 0)])
def test_no_file_path_still_walks_from_cwd(env, spy, cwd_name, expected_rc):
    """No resolvable target: the walk still starts at the payload cwd."""
    cwd = getattr(env, cwd_name)
    rc, _, _ = _run(_write(cwd, None))
    assert [c["memory"] for c in spy] == [env.mem_a if cwd_name == "repo_a" else env.mem_b]
    assert all(not c["target_path"] for c in spy)
    assert rc == expected_rc


@pytest.mark.parametrize("proc_cwd_name, expected_rc", [("repo_a", 2), ("plain", 0)])
def test_relative_target_with_empty_cwd_walks_from_process_cwd(
    env, spy, monkeypatch, proc_cwd_name, expected_rc
):
    """A relative target with no payload cwd keeps main's walk from ".". """
    monkeypatch.chdir(getattr(env, proc_cwd_name))
    rc, _, _ = _run(_write("", "app.py"))
    expected = [env.mem_a] if proc_cwd_name == "repo_a" else []
    assert [c["memory"] for c in spy] == expected
    assert rc == expected_rc
