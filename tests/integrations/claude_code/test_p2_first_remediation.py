"""T-08 P2-first: the MEMORY_PATH_MISMATCH remediation text (decision O4, A2-RT).

At emit time: when the declared memory is not a file, the remediation names
restoring it; when it is a file (cause A), the existing text is kept. The
causes come from the remediation-text decision §1:

A. declared memory present; MNEME_MEMORY names another memory (pre-P2-first only)
B. declared memory missing; ancestor memory found; MNEME_MEMORY unset
C. declared memory missing; ancestor memory found; MNEME_MEMORY set (P2-first only)
D. declared memory missing; nothing walked; MNEME_MEMORY names another file (row 6)

The emit-level tests pass the selected memory directly, so they cover the
selection before and after P2-first. The tests use a Verification with a tip:
without a baseline, no remediation line prints.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from mneme.availability_authority import AUTHORIZED, Verification
from mneme.integrations.claude_code import availability as av
from mneme.integrations.claude_code import hook
from tests.integrations.check_contract import check_result

NEW = ("restore .mneme/project_memory.json from the baseline branch, replacing anything "
       "else at that path; while it is not a file, another memory is selected")
OLD = "unset MNEME_MEMORY or point it at the declared .mneme/project_memory.json"
DOC = {"schema": av.SCHEMA, "availability": "closed", "memory_path": av.MEMORY_PATH}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("MNEME_MEMORY", "MNEME_HOOK_MODE", "CLAUDE_PLUGIN_OPTION_MODE",
                 "MNEME_HOOK_CHECK_TRANSPORT"):
        monkeypatch.delenv(name, raising=False)


def _authorized():
    v = Verification(AUTHORIZED, "", url="https://example.com/p", branch="main",
                     tip="a" * 40, baseline=DOC)
    return lambda _d: v


def _mem(d: Path) -> Path:
    p = d / ".mneme" / "project_memory.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{}", encoding="utf-8")
    return p


@pytest.fixture
def tree(tmp_path):
    base = tmp_path.resolve()
    parent = base / "P"
    r = parent / "R"
    (r / ".mneme").mkdir(parents=True)
    (r / ".mneme" / av.DECLARATION_NAME).write_text(json.dumps(DOC), encoding="utf-8")
    foreign = _mem(base / "foreign")
    return {"base": base, "parent": parent, "R": r, "foreign": foreign,
            "declared": r / ".mneme" / "project_memory.json"}


def _emit(tree, memory: Path) -> tuple[bool, str]:
    err = io.StringIO()
    decl = av.discover_declaration(tree["R"])
    refused = av.emit_availability(decl, "TRUSTED_COMPLETE", err, memory=memory,
                                   verifier=_authorized())
    return refused, err.getvalue()


def _remediation(err: str) -> str:
    lines = [ln for ln in err.splitlines() if "remediation:" in ln]
    assert len(lines) == 1, err
    return lines[0]


def test_cause_a_keeps_the_existing_line(tree):
    tree["declared"].write_text("{}", encoding="utf-8")
    refused, err = _emit(tree, tree["foreign"])
    assert refused
    assert "MEMORY_PATH_MISMATCH" in err
    assert _remediation(err) == f"mneme-hook: not a decision violation; remediation: {OLD}."


@pytest.mark.parametrize("selected", ["ancestor", "foreign"])
def test_causes_b_c_d_name_restoring_the_declared_memory(tree, selected):
    ancestor = _mem(tree["parent"])
    memory = ancestor if selected == "ancestor" else tree["foreign"]
    refused, err = _emit(tree, memory)
    assert refused
    assert "MEMORY_PATH_MISMATCH" in err
    assert _remediation(err) == f"mneme-hook: not a decision violation; remediation: {NEW}."
    assert "unset MNEME_MEMORY" not in err


def test_a_directory_at_the_declared_path_counts_as_not_a_file(tree):
    tree["declared"].mkdir()
    refused, err = _emit(tree, tree["foreign"])
    assert refused and NEW in err


def test_other_remediation_texts_unchanged():
    assert av._REMEDIATION["MEMORY_MISSING"] == "restore .mneme/project_memory.json from the baseline branch"
    assert av._REMEDIATION["MEMORY_PATH_MISMATCH"] == OLD


def test_text_is_ascii():
    assert all(ord(c) < 128 for c in NEW)


# ── End to end through the hook, under P2-first selection ────────────────────


def _write(target: Path):
    return {"hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": str(target.parent),
            "tool_input": {"file_path": str(target), "content": "x = 1\n"}}


def _run(envelope):
    out, err = io.StringIO(), io.StringIO()
    with patch.object(av, "live_verifier", _authorized()), \
            patch.object(hook, "_invoke_check", return_value=check_result("PASS")):
        rc = hook.handle_event(envelope, stderr=err, stdout=out)
    return rc, out.getvalue(), err.getvalue()


@pytest.mark.parametrize("override", ["unset", "foreign"])
def test_hook_ancestor_layout_causes_b_and_c(tree, monkeypatch, override):
    _mem(tree["parent"])
    if override == "foreign":
        monkeypatch.setenv("MNEME_MEMORY", str(tree["foreign"]))
    rc, out, err = _run(_write(tree["R"] / "a.py"))
    assert rc == 2 and out == ""
    assert "MEMORY_PATH_MISMATCH" in err and NEW in err


def test_hook_row6_cause_d(tree, monkeypatch):
    monkeypatch.setenv("MNEME_MEMORY", str(tree["foreign"]))
    rc, out, err = _run(_write(tree["R"] / "a.py"))
    assert rc == 2 and out == ""
    assert "MEMORY_PATH_MISMATCH" in err and NEW in err


def test_hook_declared_memory_present_ignores_override(tree, monkeypatch):
    """Under P2-first, cause A cannot occur: the declared memory governs."""
    tree["declared"].write_text("{}", encoding="utf-8")
    monkeypatch.setenv("MNEME_MEMORY", str(tree["foreign"]))
    rc, out, err = _run(_write(tree["R"] / "a.py"))
    assert rc == 0
    assert "MEMORY_PATH_MISMATCH" not in err and "SS-3" not in err
