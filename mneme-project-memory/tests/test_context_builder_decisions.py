"""Top-N decision injection in ContextBuilder."""
from mneme.context_builder import format_decisions, DEFAULT_MAX_DECISIONS
from mneme.decision_retriever import ScoredDecision
from mneme.schemas import Decision


def _scored(decision_id: str, score: float) -> ScoredDecision:
    return ScoredDecision(
        decision=Decision(
            id=decision_id,
            decision=f"Decision {decision_id}",
            scope=["scope-" + decision_id],
            constraints=[f"constraint-{decision_id}"],
            anti_patterns=[f"anti-{decision_id}"],
        ),
        score=score,
        matches={},
    )


def test_default_limit_is_three():
    assert DEFAULT_MAX_DECISIONS == 3


def test_injects_only_top_n():
    scored = [_scored(str(i), score=10 - i) for i in range(10)]
    out = format_decisions(scored, max_items=3)
    # Top 3 IDs are "0", "1", "2".
    for keep in ["Decision 0", "Decision 1", "Decision 2"]:
        assert keep in out
    for drop in ["Decision 5", "Decision 9"]:
        assert drop not in out


def test_skips_zero_score_items():
    scored = [_scored("a", score=2.0), _scored("b", score=0.0)]
    out = format_decisions(scored, max_items=3)
    assert "Decision a" in out
    assert "Decision b" not in out


def test_output_shows_decision_constraints_and_anti_patterns():
    scored = [_scored("a", score=5.0)]
    out = format_decisions(scored, max_items=3)
    assert "Decision a" in out
    assert "constraint-a" in out
    assert "anti-a" in out


def test_empty_input_returns_empty_string():
    assert format_decisions([], max_items=3) == ""


def test_deduplicates_by_id():
    """Same Decision id must not be injected twice."""
    scored = [_scored("a", score=5.0), _scored("a", score=4.0)]
    out = format_decisions(scored, max_items=3)
    assert out.count("Decision a") == 1


def test_format_decisions_default_min_score_is_zero():
    """Default behavior unchanged: only score == 0 is filtered."""
    scored = [_scored("a", score=0.0), _scored("b", score=2.0)]
    out = format_decisions(scored, max_items=3)
    assert "Decision a" not in out
    assert "Decision b" in out


def test_format_decisions_threshold_drops_low_scores():
    """A min_score above 0 must drop decisions with score <= threshold."""
    scored = [_scored("a", score=1.0), _scored("b", score=5.0)]
    out = format_decisions(scored, max_items=3, min_score=2.0)
    assert "Decision a" not in out
    assert "Decision b" in out


def test_format_decisions_negative_threshold_raises():
    """Reject nonsensical thresholds at the call site."""
    import pytest
    scored = [_scored("a", score=1.0)]
    with pytest.raises(ValueError, match="min_score"):
        format_decisions(scored, max_items=3, min_score=-0.5)


def test_format_decisions_score_at_threshold_is_dropped():
    """Floor is exclusive: a score equal to min_score is excluded."""
    scored = [_scored("a", score=2.0), _scored("b", score=2.5)]
    out = format_decisions(scored, max_items=3, min_score=2.0)
    assert "Decision a" not in out
    assert "Decision b" in out
