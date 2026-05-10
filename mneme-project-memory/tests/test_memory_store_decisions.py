"""Tests for MemoryStore loading Decision records (native + legacy migration)."""
from pathlib import Path

from mneme.memory_store import MemoryStore

FIXTURES = Path(__file__).parent / "fixtures"


def test_loads_native_decisions():
    store = MemoryStore(FIXTURES / "memory_v2.json")
    memory = store.load()
    assert len(memory.decisions) == 1
    d = memory.decisions[0]
    assert d.id == "mneme_001"
    assert d.decision == "Use JSON storage only"
    assert d.scope == ["storage", "backend"]
    assert "no postgres" in d.constraints
    assert "introduce ORM" in d.anti_patterns


def test_legacy_rules_migrate_to_decisions():
    """Legacy rule + anti_pattern items must surface as Decisions."""
    store = MemoryStore(FIXTURES / "memory_legacy_only.json")
    memory = store.load()
    ids = {d.id for d in memory.decisions}
    assert "rule-001" in ids
    assert "anti-001" in ids

    rule_dec = next(d for d in memory.decisions if d.id == "rule-001")
    assert rule_dec.decision == "Extend current infrastructure before rebuilding"
    assert rule_dec.scope == ["general"]
    assert rule_dec.rationale == ""

    anti_dec = next(d for d in memory.decisions if d.id == "anti-001")
    # Legacy anti_pattern items land in the anti_patterns field.
    assert "Do not use langchain" in anti_dec.anti_patterns
    assert anti_dec.scope == ["general"]


def test_decisions_accessor():
    store = MemoryStore(FIXTURES / "memory_v2.json")
    store.load()
    assert len(store.decisions()) == 1
    assert store.decisions()[0].id == "mneme_001"


def test_legacy_anti_pattern_migration_does_not_dump_content_into_anti_patterns():
    """Migrating a legacy anti_pattern item must not push its entire content
    prose into the anti_patterns field. The enforcer tokenizes every entry
    in anti_patterns into forbidden terms, so dumping prose causes ordinary
    words ("between", "session", "module", "conversation") to be treated as
    forbidden — producing false-positive FAIL verdicts on innocent text.
    """
    store = MemoryStore(FIXTURES / "memory_legacy_only.json")
    memory = store.load()
    anti_dec = next(d for d in memory.decisions if d.id == "anti-001")
    assert "Do not use langchain" in anti_dec.anti_patterns
    content = "langchain adds weight and abstracts the API surface."
    assert content not in anti_dec.anti_patterns, (
        "Migration is dumping content prose into anti_patterns; "
        "every word in the content becomes a forbidden term."
    )


# ── Step 3C Stage 1: anti_pattern.content migration symmetry ──────────────


def test_legacy_anti_pattern_migration_lands_content_in_constraints():
    """Stage 1 fix: anti_pattern.content must land in `constraints`.

    Symmetry with the rule migration (rule.content -> constraints). Without
    this, content prose for migrated anti-patterns is invisible to the
    constraints-weighted retrieval signal and only appears at the
    rationale weight (0.5x), making migrated anti-patterns systematically
    under-rank native Decisions on equivalent queries.
    """
    store = MemoryStore(FIXTURES / "memory_legacy_only.json")
    memory = store.load()
    anti_dec = next(d for d in memory.decisions if d.id == "anti-001")
    expected_content = "langchain adds weight and abstracts the API surface."
    assert expected_content in anti_dec.constraints, (
        f"anti_pattern.content must migrate into constraints; "
        f"got constraints={anti_dec.constraints}"
    )


def test_legacy_anti_pattern_migration_leaves_rationale_empty():
    """Stage 1 fix: anti_pattern.content must NOT remain in `rationale`.

    Mirror of the rule migration which sets rationale="". Keeping content
    in both `constraints` and `rationale` would double-count it under
    retrieval weights.
    """
    store = MemoryStore(FIXTURES / "memory_legacy_only.json")
    memory = store.load()
    anti_dec = next(d for d in memory.decisions if d.id == "anti-001")
    assert anti_dec.rationale == "", (
        f"Legacy anti_pattern migration must leave rationale empty; "
        f"got rationale={anti_dec.rationale!r}"
    )


def test_legacy_anti_pattern_migration_preserves_id_type_and_anti_patterns():
    """Stage 1 fix must not regress the existing migration shape:
    Decision.id, Decision.decision (Avoid: <title>), scope=['general'],
    and anti_patterns=[<title>] all still hold."""
    store = MemoryStore(FIXTURES / "memory_legacy_only.json")
    memory = store.load()
    anti_dec = next(d for d in memory.decisions if d.id == "anti-001")
    assert anti_dec.id == "anti-001"
    assert anti_dec.decision == "Avoid: Do not use langchain"
    assert anti_dec.scope == ["general"]
    assert anti_dec.anti_patterns == ["Do not use langchain"]
