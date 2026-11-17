"""T-08 D5+P2 P2-first: the shared memory resolver (charter §5.2.2).

Pins the five P2-first rows on today's unbounded walk, the returned path form,
the resolver fields, the explicit-path record, and the §2 invariant of the
remediation-text decision (owner condition, #811): under P2-first, with a
valid declaration at R, a memory-path mismatch implies the declared memory is
not a file.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from mneme.integrations.claude_code import availability as av
from mneme.integrations.memory_selection import (
    OVERRIDE_FILLS_ABSENCE,
    OVERRIDE_IGNORED,
    OVERRIDE_MISSING,
    DISCOVERED,
    NO_MEMORY_ON_PATH,
    MemorySelection,
    explicit_selection,
    resolve_memory,
    selection_notice,
)

MEM = ".mneme/project_memory.json"


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    monkeypatch.delenv("MNEME_MEMORY", raising=False)


def _mem(d: Path) -> Path:
    p = d / ".mneme" / "project_memory.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{}", encoding="utf-8")
    return p


@pytest.fixture
def root(tmp_path):
    r = tmp_path.resolve()
    assert resolve_memory(r).path is None, "an ancestor of tmp_path has a .mneme memory"
    return r


# ── Rows (charter §5.2.2) ────────────────────────────────────────────────────


def test_row1_discovered_without_override(root):
    mem = _mem(root / "repo")
    sel = resolve_memory(root / "repo")
    assert sel == MemorySelection(path=mem, source="discovered", reason=DISCOVERED, walk="unbounded")


def test_row1_equal_override_keeps_override_form(root, monkeypatch):
    mem = _mem(root / "repo")
    given = str(root / "repo" / ".mneme" / "." / "project_memory.json")
    monkeypatch.setenv("MNEME_MEMORY", given)
    sel = resolve_memory(root / "repo" / "src")
    assert sel.reason == DISCOVERED
    assert sel.source == "discovered"
    assert sel.path == Path(given), "row 1 with an equal override returns Path(M_X) as given"
    assert sel.path.resolve() == mem.resolve()


def test_row2_different_override_is_ignored(root, monkeypatch):
    mem = _mem(root / "repo")
    other = _mem(root / "other")
    monkeypatch.setenv("MNEME_MEMORY", str(other))
    sel = resolve_memory(root / "repo")
    assert (sel.path, sel.source, sel.reason) == (mem, "discovered", OVERRIDE_IGNORED)


def test_row2_missing_override_is_ignored(root, monkeypatch):
    mem = _mem(root / "repo")
    monkeypatch.setenv("MNEME_MEMORY", str(root / "nope.json"))
    sel = resolve_memory(root / "repo")
    assert (sel.path, sel.reason) == (mem, OVERRIDE_IGNORED)


def test_row2_ancestor_memory_beats_override(root, monkeypatch):
    """Case 2 (charter §5.2.3): Phase 2 turns this into row 3 or row 5."""
    ancestor = _mem(root)
    other = _mem(root / "elsewhere")
    (root / "nested" / "repo").mkdir(parents=True)
    monkeypatch.setenv("MNEME_MEMORY", str(other))
    sel = resolve_memory(root / "nested" / "repo")
    assert (sel.path, sel.reason) == (ancestor, OVERRIDE_IGNORED)


def test_row6_override_fills_absence(root, monkeypatch):
    other = _mem(root / "elsewhere")
    (root / "plain").mkdir()
    monkeypatch.setenv("MNEME_MEMORY", str(other))
    sel = resolve_memory(root / "plain")
    assert sel == MemorySelection(path=Path(str(other)), source="override",
                                  reason=OVERRIDE_FILLS_ABSENCE, walk="unbounded")


def test_row6_existing_unreadable_or_malformed_override_is_selected(root, monkeypatch):
    """A2-3: is_file() only; the resolver never opens the override."""
    bad = root / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    (root / "plain").mkdir()
    monkeypatch.setenv("MNEME_MEMORY", str(bad))
    sel = resolve_memory(root / "plain")
    assert (sel.path, sel.reason) == (bad, OVERRIDE_FILLS_ABSENCE)


def test_row7_missing_override_selects_nothing(root, monkeypatch):
    (root / "plain").mkdir()
    monkeypatch.setenv("MNEME_MEMORY", str(root / "nope.json"))
    sel = resolve_memory(root / "plain")
    assert sel == MemorySelection(path=None, source="none", reason=OVERRIDE_MISSING, walk="unbounded")


def test_row7_directory_override_counts_as_missing(root, monkeypatch):
    (root / "plain").mkdir()
    (root / "adir").mkdir()
    monkeypatch.setenv("MNEME_MEMORY", str(root / "adir"))
    assert resolve_memory(root / "plain").reason == OVERRIDE_MISSING


def test_row8_plain_absence(root):
    (root / "plain").mkdir()
    sel = resolve_memory(root / "plain")
    assert sel == MemorySelection(path=None, source="none", reason=NO_MEMORY_ON_PATH, walk="unbounded")


def test_empty_override_is_unset(root, monkeypatch):
    mem = _mem(root / "repo")
    monkeypatch.setenv("MNEME_MEMORY", "")
    assert resolve_memory(root / "repo").reason == DISCOVERED
    assert resolve_memory(root / "repo").path == mem


def test_relative_override_equal_to_walked_memory(root, monkeypatch):
    mem = _mem(root / "repo")
    monkeypatch.chdir(root / "repo")
    monkeypatch.setenv("MNEME_MEMORY", MEM)
    sel = resolve_memory(root / "repo")
    assert sel.reason == DISCOVERED
    assert sel.path == Path(MEM)
    assert sel.path.resolve() == mem.resolve()


def test_relative_override_fills_absence(root, monkeypatch):
    other = _mem(root / "elsewhere")
    (root / "plain").mkdir()
    monkeypatch.chdir(root / "elsewhere")
    monkeypatch.setenv("MNEME_MEMORY", MEM)
    sel = resolve_memory(root / "plain")
    assert (sel.path, sel.reason) == (Path(MEM), OVERRIDE_FILLS_ABSENCE)
    assert sel.path.resolve() == other.resolve()


@pytest.mark.skipif(sys.platform != "win32", reason="case-insensitive filesystem only")
def test_case_variant_override_equal_on_windows(root, monkeypatch):
    mem = _mem(root / "repo")
    monkeypatch.setenv("MNEME_MEMORY", str(mem).upper())
    sel = resolve_memory(root / "repo")
    assert sel.reason == DISCOVERED


def test_symlinked_override_to_walked_memory_is_equal(root, monkeypatch):
    mem = _mem(root / "repo")
    link = root / "link.json"
    try:
        link.symlink_to(mem)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    monkeypatch.setenv("MNEME_MEMORY", str(link))
    sel = resolve_memory(root / "repo")
    assert sel.reason == DISCOVERED
    assert sel.path == link


def test_walk_ignores_git_markers(root):
    """P2-first keeps today's walk: a .git marker does not stop it."""
    mem = _mem(root / "a")
    (root / "a" / "src" / ".git").mkdir(parents=True)
    assert resolve_memory(root / "a" / "src").path == mem


def test_boundary_fields_unpopulated(root):
    _mem(root / "repo")
    sel = resolve_memory(root / "repo")
    assert sel.boundary is None and sel.shadowed is None and sel.walk == "unbounded"


def test_explicit_selection_record(root):
    mem = _mem(root / "repo")
    assert explicit_selection(mem) == MemorySelection(path=mem, source="explicit", reason=None, walk=None)
    assert explicit_selection(root / "nope.json").path is None


def test_find_memory_is_the_wrapper(root, monkeypatch):
    from mneme.integrations.claude_code.hook import find_memory

    mem = _mem(root / "repo")
    other = _mem(root / "other")
    monkeypatch.setenv("MNEME_MEMORY", str(other))
    assert find_memory(root / "repo") == mem == resolve_memory(root / "repo").path


# ── Notices (charter §5.2.4): rows 2 and 7 only ──────────────────────────────


def test_notice_only_for_rows_2_and_7(root, monkeypatch):
    mem = _mem(root / "repo")
    (root / "plain").mkdir()
    assert selection_notice(resolve_memory(root / "repo")) is None
    assert selection_notice(resolve_memory(root / "plain")) is None
    monkeypatch.setenv("MNEME_MEMORY", str(root / "nope.json"))
    ignored = selection_notice(resolve_memory(root / "repo"))
    missing = selection_notice(resolve_memory(root / "plain"))
    assert ignored is not None and "OVERRIDE_IGNORED" in ignored and str(mem) in ignored
    assert missing is not None and "OVERRIDE_MISSING" in missing
    other = _mem(root / "elsewhere")
    monkeypatch.setenv("MNEME_MEMORY", str(other))
    assert selection_notice(resolve_memory(root / "plain")) is None, "row 6 is informational"
    assert all(ord(c) < 128 for c in ignored + missing)


# ── §2 invariant layout matrix (remediation-text decision §7; owner condition) ─


def _declare(r: Path) -> None:
    (r / ".mneme").mkdir(parents=True, exist_ok=True)
    (r / ".mneme" / av.DECLARATION_NAME).write_text(json.dumps(
        {"schema": av.SCHEMA, "availability": "closed", "memory_path": av.MEMORY_PATH}
    ), encoding="utf-8")


DECLARED = ("present", "missing", "directory", "symlink")
ANCESTOR = ("present", "absent")
OVERRIDE = ("unset", "missing", "equal", "case-variant", "relative", "foreign")
START = ("R", "R/src", "R/.mneme", "R/not/yet")


@pytest.mark.parametrize("declared", DECLARED)
@pytest.mark.parametrize("ancestor", ANCESTOR)
@pytest.mark.parametrize("override", OVERRIDE)
@pytest.mark.parametrize("start", START)
def test_p2_first_mismatch_implies_declared_memory_missing(
    tmp_path, monkeypatch, declared, ancestor, override, start
):
    base = tmp_path.resolve()
    parent = base / "P"
    r = parent / "R"
    (r / "src").mkdir(parents=True)
    _declare(r)
    declared_path = r / ".mneme" / "project_memory.json"
    if declared == "present":
        declared_path.write_text("{}", encoding="utf-8")
    elif declared == "directory":
        declared_path.mkdir()
    elif declared == "symlink":
        target = base / "outside.json"
        target.write_text("{}", encoding="utf-8")
        try:
            declared_path.symlink_to(target)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks unavailable")
    if ancestor == "present":
        _mem(parent)
    foreign = _mem(base / "foreign")
    if override == "missing":
        monkeypatch.setenv("MNEME_MEMORY", str(base / "nope.json"))
    elif override == "equal":
        monkeypatch.setenv("MNEME_MEMORY", str(declared_path))
    elif override == "case-variant":
        monkeypatch.setenv("MNEME_MEMORY", str(declared_path).upper())
    elif override == "relative":
        monkeypatch.chdir(r)
        monkeypatch.setenv("MNEME_MEMORY", MEM)
    elif override == "foreign":
        monkeypatch.setenv("MNEME_MEMORY", str(foreign))
    starts = {"R": r, "R/src": r / "src", "R/.mneme": r / ".mneme", "R/not/yet": r / "not" / "yet"}
    s = starts[start]

    declaration = av.discover_declaration(s)
    assert declaration is not None and not declaration.problem
    selection = resolve_memory(s)
    if av.memory_mismatch(declaration, selection.path):
        assert not declared_path.is_file(), (declared, ancestor, override, start, selection)
    if declared_path.is_file():
        assert selection.path is not None
        assert selection.path.resolve() == declared_path.resolve()
