"""Regression tests for issue #254 — enforcement must not be retrieval-gated.

Retrieval answers "what context is relevant?" — a ranking question, where a
top-N cutoff is correct. Enforcement answers "is this forbidden?" — a safety
question, where ranking is wrong. Before #254, `enforcer._top_nonzero` filtered
retrieved decisions to `score > 0`, so a decision that scored zero against the
hook's `"edit to <file_path>"` query was never evaluated at all. Byte-identical
violating content was therefore caught or missed purely on whether the filename
happened to contain a scope keyword.

These tests deliberately use *neutral* filenames that share no token with the
fixture decision's scope. `tests/integrations/claude_code/test_hook_e2e.py`
names its target `storage_db.py` and says so in a comment — it was built around
the limitation rather than exposing it, which is why the defect survived.
"""
import json
from pathlib import Path

import pytest

from mneme.cli import main
from mneme.decision_retriever import DecisionRetriever
from mneme.enforcer import Severity, check_prompt
from mneme.memory_store import MemoryStore

# The same fixture the Claude Code e2e suite uses: one decision, scoped to
# ["storage", "database"], forbidding psycopg2.
FIXTURE = (
    Path(__file__).parent
    / "integrations" / "claude_code" / "fixtures" / "project_memory.json"
)

VIOLATING_CONTENT = "import psycopg2\n"

# Filenames sharing no retrieval token with scope ["storage", "database"].
# "db.py" is included deliberately: the scope says "database", and "db" is not
# a lexical match for it.
NEUTRAL_FILENAMES = ["service.py", "models.py", "db.py", "handler.py"]


@pytest.fixture
def memory(tmp_path):
    mem = tmp_path / "project_memory.json"
    mem.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    return mem


def _write(tmp_path, name, content=VIOLATING_CONTENT):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ── the defect, stated directly ───────────────────────────────────────────────

@pytest.mark.parametrize("filename", NEUTRAL_FILENAMES)
def test_violation_is_caught_under_a_neutral_filename(memory, tmp_path, filename):
    """Forbidden content must FAIL regardless of what the file is called."""
    target = _write(tmp_path, filename)
    exit_code = main([
        "check",
        "--memory", str(memory),
        "--input", str(target),
        "--query", f"edit to {filename}",
        "--mode", "strict",
    ])
    assert exit_code == 2, (
        f"{filename}: identical violating content must be caught; enforcement "
        f"must not depend on the filename containing a scope keyword"
    )


def test_verdict_is_identical_for_identical_content_across_filenames(
    memory, tmp_path,
):
    """The scope-keyword filename and a neutral one must agree.

    This is the exact reproduction from #254: byte-identical content, only the
    filename differs, opposite verdicts.
    """
    verdicts = {}
    for filename in ["storage_db.py", *NEUTRAL_FILENAMES]:
        target = _write(tmp_path, filename)
        verdicts[filename] = main([
            "check",
            "--memory", str(memory),
            "--input", str(target),
            "--query", f"edit to {filename}",
            "--mode", "strict",
        ])
    assert len(set(verdicts.values())) == 1, (
        f"identical content produced different verdicts by filename: {verdicts}"
    )


def test_zero_scoring_decision_is_still_enforced(memory):
    """Unit-level statement of the same property.

    Enforcement reads the whole corpus, not the retriever's positive-score
    top-N. A decision that scores 0.00 against the query still has its
    anti_patterns checked against the content.
    """
    store = MemoryStore(memory)
    store.load()
    scored = DecisionRetriever(store.decisions()).retrieve("edit to service.py")

    # Premise: the decision genuinely scores zero for this query. If this
    # assertion ever fails the test has stopped testing what it claims to.
    assert all(s.score == 0 for s in scored), (
        f"premise broken: expected an all-zero retrieval score, got "
        f"{[(s.decision.id, s.score) for s in scored]}"
    )

    result = check_prompt(VIOLATING_CONTENT, scored)
    assert result.verdict == Severity.FAIL
    assert any(v.trigger == "psycopg2" for v in result.violations)


def test_compliant_content_still_passes_under_a_neutral_filename(memory, tmp_path):
    """Corpus-wide enforcement must not turn into blanket failure."""
    target = _write(tmp_path, "service.py", "import sqlite3\n")
    exit_code = main([
        "check",
        "--memory", str(memory),
        "--input", str(target),
        "--query", "edit to service.py",
        "--mode", "strict",
    ])
    assert exit_code == 0
