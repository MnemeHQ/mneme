"""
Drift detection tests — realistic AI output scenarios checked against real
Mneme project decisions from examples/project_memory.json.

Three families of drift:
  1. Storage drift     — suggestions that violate the JSON-only storage decision
  2. Banned framework  — suggestions that introduce disallowed retrieval deps
  3. Cursor AI drift   — simulated Cursor assistant outputs (post-rules-injection)
     that still violate decisions, or correctly follow them

One test in this file also exposes a real bug in the enforcer:
  'no embeddings in v1' parses 'in' (len=2) as a forbidden term with
  min_len=2, causing false WARNs on any clean text containing the word 'in'.
  The fix is to raise constraint min_len to 3 inside _rule_terms.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mneme.decision_retriever import DecisionRetriever
from mneme.enforcer import Severity, check_prompt
from mneme.memory_store import MemoryStore

_EXAMPLE_MEMORY = Path(__file__).parent.parent / "examples" / "project_memory.json"


def _retrieve(query: str, top: int = 3):
    store = MemoryStore(str(_EXAMPLE_MEMORY))
    store.load()
    return DecisionRetriever(store.decisions()).retrieve(query), top


# ── 1. Storage drift ──────────────────────────────────────────────────────────

def test_drift_postgres_suggestion_is_warned():
    """AI output that mentions postgres violates the 'no postgres' constraint."""
    scored, top = _retrieve("storage backend")
    output = "We could migrate the storage layer to postgres for better query support."
    result = check_prompt(output, scored, top=top)
    assert result.verdict in (Severity.WARN, Severity.FAIL)
    assert any("postgres" in v.trigger for v in result.violations)


def test_drift_sqlalchemy_introduction_is_failed():
    """AI output introducing sqlalchemy violates the storage anti_pattern."""
    scored, top = _retrieve("storage backend")
    output = "I'll add sqlalchemy as an ORM layer to manage the decision records."
    result = check_prompt(output, scored, top=top)
    assert result.verdict == Severity.FAIL
    assert any(v.decision_id == "mneme_storage_json" for v in result.violations)


def test_drift_migration_layer_is_failed():
    """AI output that adds a migration layer violates the storage anti_pattern."""
    scored, top = _retrieve("storage persistence")
    output = "To support schema evolution, let's add a migration layer using Alembic."
    result = check_prompt(output, scored, top=top)
    assert result.verdict == Severity.FAIL


def test_drift_orm_mention_is_failed():
    """Direct ORM suggestion against JSON-only storage decision."""
    scored, top = _retrieve("storage backend")
    output = "Wrap the JSON reads with an ORM so we get type safety automatically."
    result = check_prompt(output, scored, top=top)
    assert result.verdict == Severity.FAIL


def test_clean_json_storage_output_passes():
    """AI output that follows the JSON storage decision should PASS."""
    scored, top = _retrieve("storage backend")
    output = "Read the JSON file, append the new decision dict, write it back to disk."
    result = check_prompt(output, scored, top=top)
    assert result.verdict == Severity.PASS


# ── 2. Banned framework / retrieval drift ─────────────────────────────────────

def test_drift_sentence_transformers_is_failed():
    """AI output adding sentence-transformers violates the retrieval anti_pattern."""
    scored, top = _retrieve("retrieval ranking")
    output = "For better semantic search, add sentence-transformers to the retrieval module."
    result = check_prompt(output, scored, top=top)
    assert result.verdict == Severity.FAIL
    assert any(
        v.decision_id == "mneme_retrieval_deterministic" for v in result.violations
    )


def test_drift_vector_database_is_failed():
    """Adding a vector database violates the deterministic-retrieval decision."""
    scored, top = _retrieve("retrieval ranking")
    output = "Let's introduce a vector database like Pinecone for retrieval."
    result = check_prompt(output, scored, top=top)
    assert result.verdict == Severity.FAIL


def test_drift_embeddings_mention_is_warned():
    """Mentioning 'embeddings' violates the 'no embeddings in v1' constraint."""
    scored, top = _retrieve("retrieval ranking")
    output = "We could use embeddings here for a better retrieval experience."
    result = check_prompt(output, scored, top=top)
    assert result.verdict in (Severity.WARN, Severity.FAIL)
    assert any("embeddings" in v.trigger for v in result.violations)


def test_clean_keyword_retrieval_output_passes():
    """AI output describing keyword scoring should not trigger any violation."""
    scored, top = _retrieve("retrieval ranking")
    output = "Score each decision by counting keyword overlaps with the query tokens."
    result = check_prompt(output, scored, top=top)
    assert result.verdict == Severity.PASS


def test_no_false_warn_from_short_words_in_constraint_phrase():
    """
    BUG REGRESSION: 'no embeddings in v1' must not trigger WARN because
    the word 'in' (a fragment of the constraint phrase) appears in unrelated text.

    Before fix: enforcer extracts 'in' (len=2) as a forbidden term with
    min_len=2 → any sentence containing 'in' falsely triggers WARN.
    After fix:  min_len raised to 3 → 'in' excluded → only 'embeddings' checked.
    """
    scored, top = _retrieve("retrieval ranking")
    # Clean text — no embeddings, no ML — but 'in' is a common English word
    output = "Rank decisions in descending order by keyword overlap score."
    result = check_prompt(output, scored, top=top)
    assert result.verdict == Severity.PASS


# ── 3. Cursor AI output drift ─────────────────────────────────────────────────

def test_drift_cursor_output_introduces_orm_via_sqlalchemy():
    """
    Simulates a Cursor AI response that received the .mdc rules but still
    suggested an ORM/sqlalchemy pattern for storage.
    """
    scored, top = _retrieve("storage backend")
    cursor_output = """
Here is the implementation I suggest:

```python
from sqlalchemy.orm import Session
engine = create_engine('postgresql://localhost/mneme')
```

This uses sqlalchemy to manage the decision records with a PostgreSQL backend.
"""
    result = check_prompt(cursor_output, scored, top=top)
    assert result.verdict == Severity.FAIL


def test_drift_cursor_output_suggests_postgres_connection():
    """Cursor suggestion to connect to postgres triggers WARN on storage constraint."""
    scored, top = _retrieve("storage backend")
    cursor_output = (
        "Connect to postgres using psycopg2 "
        "and store decisions in a decisions table."
    )
    result = check_prompt(cursor_output, scored, top=top)
    assert result.verdict in (Severity.WARN, Severity.FAIL)


def test_cursor_output_following_rules_passes():
    """A Cursor AI response that stays within the JSON-only contract should PASS."""
    scored, top = _retrieve("storage backend")
    cursor_output = (
        "Load the JSON file, append the new decision as a dict, "
        "and write the updated structure back to disk."
    )
    result = check_prompt(cursor_output, scored, top=top)
    assert result.verdict == Severity.PASS


def test_drift_cursor_retrieval_output_adds_embeddings():
    """Cursor suggestion to add embeddings to retrieval violates the determinism decision."""
    scored, top = _retrieve("retrieval ranking")
    cursor_output = (
        "Replace keyword scoring with embeddings from sentence-transformers "
        "for higher recall."
    )
    result = check_prompt(cursor_output, scored, top=top)
    assert result.verdict == Severity.FAIL


def test_cursor_retrieval_output_following_rules_passes():
    """Cursor suggestion that stays deterministic should PASS."""
    scored, top = _retrieve("retrieval ranking")
    # Avoids "weights" (appears in the 'no learned weights' constraint) and
    # "embeddings" — uses neutral language describing keyword overlap scoring.
    cursor_output = (
        "Score by token overlap: tokenise the query and each decision field, "
        "count matching tokens per field, multiply by a fixed constant, "
        "sum and sort descending."
    )
    result = check_prompt(cursor_output, scored, top=top)
    assert result.verdict == Severity.PASS


# ── 4. Cross-decision drift ───────────────────────────────────────────────────

def test_drift_combining_storage_and_retrieval_violations():
    """Output violating multiple decisions produces FAIL with >= 1 violation."""
    scored, top = _retrieve("storage retrieval")
    output = "Add sqlalchemy for storage and sentence-transformers for retrieval."
    result = check_prompt(output, scored, top=top)
    assert result.verdict == Severity.FAIL
    assert len(result.violations) >= 1


def test_violation_report_carries_full_provenance():
    """Every violation must have: decision_id, decision_text, rule, trigger."""
    scored, top = _retrieve("storage backend")
    output = "We'll add sqlalchemy ORM for the storage layer."
    result = check_prompt(output, scored, top=top)
    assert result.violations, "Expected at least one violation"
    for v in result.violations:
        assert v.decision_id, "violation.decision_id must be non-empty"
        assert v.decision_text, "violation.decision_text must be non-empty"
        assert v.rule, "violation.rule must be non-empty"
        assert v.trigger, "violation.trigger must be non-empty"


def test_verdict_is_fail_when_anti_pattern_and_constraint_both_hit():
    """FAIL takes precedence over WARN when both are present in one output."""
    scored, top = _retrieve("storage backend")
    # postgres → WARN (constraint), sqlalchemy → FAIL (anti_pattern)
    output = "Connect to postgres and wrap it with sqlalchemy for easy querying."
    result = check_prompt(output, scored, top=top)
    assert result.verdict == Severity.FAIL
    severities = {v.severity for v in result.violations}
    assert Severity.FAIL in severities
    assert Severity.WARN in severities
