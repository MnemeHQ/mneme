"""Tests for the new Decision dataclass."""
import pytest

from mneme.schemas import Decision, Rule


def test_decision_minimal_construction():
    d = Decision(id="mneme_001", decision="Use JSON storage only")
    assert d.id == "mneme_001"
    assert d.decision == "Use JSON storage only"
    assert d.rationale == ""
    assert d.scope == []
    assert d.constraints == []
    assert d.anti_patterns == []
    assert d.rules == []
    assert d.memory_path == ""


def test_decision_full_construction():
    d = Decision(
        id="mneme_001",
        decision="Use JSON storage only",
        rationale="Avoid infra complexity and keep local-first",
        scope=["storage", "backend"],
        constraints=["no postgres", "no external db"],
        anti_patterns=["introduce ORM", "add migration layer"],
        created_at="2026-04-24T00:00:00Z",
        updated_at="2026-04-24T00:00:00Z",
    )
    assert d.scope == ["storage", "backend"]
    assert "no postgres" in d.constraints
    assert "introduce ORM" in d.anti_patterns


def test_decision_defaults_are_independent_lists():
    # Regression: mutable defaults must be per-instance, not shared.
    a = Decision(id="a", decision="x")
    b = Decision(id="b", decision="y")
    a.scope.append("storage")
    assert b.scope == []


def test_typed_rule_validates_type_and_value():
    rule = Rule(type="FORBID_LITERAL", value="pip install mneme")
    assert rule.type == "FORBID_LITERAL"
    assert rule.value == "pip install mneme"

    with pytest.raises(ValueError, match="unknown rule type"):
        Rule(type="FORBID_REGEX", value="mneme")
    with pytest.raises(ValueError, match="non-empty"):
        Rule(type="FORBID_LITERAL", value="")
    with pytest.raises(ValueError, match="non-empty"):
        Rule(type="FORBID_LITERAL", value="   ")


def test_mneme_conflict_error_carries_conflicts_and_result():
    from mneme.schemas import MnemeConflictError

    err = MnemeConflictError(conflicts=["c1", "c2"], result="r")
    assert err.conflicts == ["c1", "c2"]
    assert err.result == "r"
    # The exception message should mention how many conflicts were found
    # so it is informative when raised without being caught.
    assert "2" in str(err)
