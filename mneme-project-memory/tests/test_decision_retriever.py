"""Field-weighted relevance scoring over Decision records."""
from mneme.decision_retriever import DecisionRetriever, ScoredDecision
from mneme.schemas import Decision


def _retriever(decisions):
    return DecisionRetriever(decisions)


def test_scope_match_outweighs_content_match():
    decisions = [
        Decision(id="a", decision="Use JSON storage", scope=["storage"]),
        Decision(id="b", decision="Keep storage simple", scope=["other"]),
    ]
    ranked = _retriever(decisions).retrieve("How should I handle storage?")
    assert ranked[0].decision.id == "a"
    # Scope-match bonus = 2 beats the pure content-match of "storage" in title.
    assert ranked[0].score > ranked[1].score


def test_constraint_match_scores_higher_than_decision_text():
    decisions = [
        Decision(
            id="a",
            decision="Storage choice",
            constraints=["no postgres"],
        ),
        Decision(id="b", decision="postgres tuning"),
    ]
    ranked = _retriever(decisions).retrieve("should I use postgres?")
    # Constraint match (1.5x) + decision-text overlap must beat item b's
    # single decision-text hit.
    assert ranked[0].decision.id == "a"


def test_unrelated_query_scores_zero():
    decisions = [
        Decision(id="a", decision="Use JSON storage", scope=["storage"]),
    ]
    ranked = _retriever(decisions).retrieve("completely unrelated query about colors")
    assert ranked[0].score == 0


def test_score_components_recorded():
    """Debug output must explain which fields contributed."""
    decisions = [
        Decision(
            id="a",
            decision="Use JSON storage",
            scope=["storage"],
            constraints=["no postgres"],
        ),
    ]
    ranked = _retriever(decisions).retrieve("should I use postgres storage?")
    s = ranked[0]
    assert isinstance(s, ScoredDecision)
    assert s.matches["scope"] >= 1
    assert s.matches["constraints"] >= 1


def test_results_sorted_descending():
    decisions = [
        Decision(id="a", decision="Avoid postgres", constraints=["no postgres"]),
        Decision(id="b", decision="Something else entirely"),
    ]
    ranked = _retriever(decisions).retrieve("postgres")
    assert ranked[0].score >= ranked[-1].score


def test_stopword_token_does_not_contribute_to_score():
    """A token in STOPWORDS must not create a false-positive match.

    "add" appears in both query and decision — it is a stopword and must
    be filtered before overlap is computed.
    """
    decisions = [
        Decision(id="noise", decision="Do not add agentic loops"),
    ]
    ranked = _retriever(decisions).retrieve("should I add embeddings?")
    assert ranked[0].score == 0


def test_legacy_migrated_item_does_not_outrank_native_via_stopword():
    """A migrated decision that only matches via a stopword must score zero.

    Before the fix, "add" in both query and migrated anti_patterns content
    contributed 2.5 points, drowning out genuine score differences.
    """
    decisions = [
        Decision(
            id="native",
            decision="Storage must remain JSON",
            scope=["storage"],
            constraints=["no postgres"],
        ),
        Decision(
            id="migrated",
            decision="Do not add agentic loops",
            anti_patterns=["Do not add agentic loops in v1"],
        ),
    ]
    ranked = _retriever(decisions).retrieve("should I add postgres storage?")
    assert ranked[0].decision.id == "native"
    migrated = next(r for r in ranked if r.decision.id == "migrated")
    # "add" is a stopword — migrated has no other token that overlaps the query
    assert migrated.score == 0


def test_empty_query_returns_fallback_with_positive_score():
    """All-stopword queries must surface decisions, not silently return nothing.

    `_tokenize` filters out short tokens and stopwords. Queries like "add use"
    produce an empty token set; without a fallback every decision scores 0
    and the pipeline filter drops everything. Mirror retriever.py:184–190.
    """
    decisions = [
        Decision(id="a", decision="Use JSON storage"),
        Decision(id="b", decision="Avoid postgres"),
    ]
    ranked = _retriever(decisions).retrieve("add use")
    # All decisions surfaced (in insertion order) with a positive score so they
    # survive the `score <= 0` filter downstream.
    assert [r.decision.id for r in ranked] == ["a", "b"]
    assert all(r.score > 0 for r in ranked)


def test_empty_query_fallback_is_deterministic():
    """Repeated calls with an empty query produce identical output."""
    decisions = [Decision(id=str(i), decision=f"d{i}") for i in range(5)]
    r = _retriever(decisions)
    assert r.retrieve("") == r.retrieve("")
    assert r.retrieve("the and for") == r.retrieve("the and for")


def test_non_empty_query_unaffected_by_fallback():
    """Existing scoring behavior must not change for queries with real tokens."""
    decisions = [
        Decision(id="a", decision="Use JSON storage", scope=["storage"]),
        Decision(id="b", decision="Keep storage simple", scope=["other"]),
    ]
    ranked = _retriever(decisions).retrieve("How should I handle storage?")
    # Scope-match still wins; not all decisions surface as in the fallback.
    assert ranked[0].decision.id == "a"
    assert ranked[0].score > ranked[1].score
