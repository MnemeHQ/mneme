"""Regression tests for the legacy anti-pattern token false positive.

Dogfood incident: ``mneme check`` FAILed benign planning/documentation prose
because a multi-term legacy anti-pattern was decomposed into individual content
terms and fired when ANY single term appeared
(``mneme/enforcer.py::check_prompt``, anti_patterns loop).

Semantics pinned here (ADR-017 amendment, 2026-08-24):

    A/B. A multi-term anti-pattern does not fire on benign prose that merely
         contains one ordinary token from it (``awin`` / ``live`` /
         ``category`` / ``slug``).
    C.   The genuine pattern -- the complete ordered term sequence -- still
         FAILs, so no future repair may over-weaken.
    #4   The rule's own underscore identifier spelling is detectable
         (separator equivalence).
    #5   Terms scattered through prose or reordered never match.
    D.   Typed FORBID_LITERAL keeps its deterministic exact-match FAIL and is
         out of scope for any weakening.

History: tests A and B were committed failing-first at base 3a47cc1c and
turned green by the phrase-sequence matcher; C and D guarded that change.
See ADR-017 (multi-term rules remain retrieval-gated) and issue #150.
"""
import pytest

from mneme.decision_retriever import ScoredDecision
from mneme.enforcer import Severity, check_prompt
from mneme.schemas import Decision, Rule


def _scored(decision: Decision, score: float = 1.0) -> ScoredDecision:
    return ScoredDecision(decision=decision, score=score)


AWIN = Decision(
    id="awin-001",
    decision="Affiliate attribution must resolve to one source per market.",
    rationale="duplicate tracking pixels caused double attribution",
    scope=["affiliate"],
    constraints=[],
    # The reported incident identifier, verbatim shape: underscores split into
    # separate terms by _rule_terms(), so bare "awin" prose triggers a FAIL.
    anti_patterns=["assume_awin_awin_us_same_source"],
)

SLUG = Decision(
    id="slug-001",
    decision="URL slugs are derived once at publish time.",
    rationale="mutating routes breaks external links",
    scope=["publishing"],
    constraints=[],
    anti_patterns=["regenerate live category slug on every request"],
)


def test_multi_term_anti_pattern_does_not_fail_on_benign_awin_mention():
    """A: benign planning prose mentioning 'awin' is not the anti-pattern."""
    result = check_prompt(
        "Plan: we will track the awin programme per market and review "
        "attribution weekly.\n",
        [_scored(AWIN)],
    )
    assert result.violations == []
    assert result.verdict == Severity.PASS


def test_multi_term_anti_pattern_does_not_fail_on_live_category_slug_prose():
    """B: same defect class for other ordinary tokens from the incident."""
    result = check_prompt(
        "The documentation describes how each live category page receives "
        "its slug before launch.\n",
        [_scored(SLUG)],
    )
    assert result.violations == []
    assert result.verdict == Severity.PASS


def test_genuine_anti_pattern_phrase_still_fails():
    """C: content actually carrying the forbidden pattern must keep failing.

    This is the case the legacy rule exists for. The phrase-sequence matcher
    (ADR-017 amendment) requires the complete ordered term sequence, so a
    genuine violation states the pattern as the rule states it.
    """
    result = check_prompt(
        "Attribution logic will assume awin awin us same source behavior "
        "for every market.\n",
        [_scored(AWIN)],
    )
    fail = [v for v in result.violations if v.severity == Severity.FAIL]
    assert len(fail) >= 1
    assert fail[0].trigger == AWIN.anti_patterns[0]
    assert result.verdict == Severity.FAIL


def test_underscore_identifier_form_of_rule_matches():
    """Gate: the rule's own identifier spelling is now detectable.

    Under the previous whole-term matcher, ``\\b`` boundaries saw
    ``assume_awin_awin_us_same_source`` as one token and no extracted term
    could ever occur inside it, so the rule was blind to its literal form.
    Separator equivalence (``_`` = whitespace) fixes that.
    """
    result = check_prompt(
        "Migration notes: legacy pixel assume_awin_awin_us_same_source "
        "retained for this locale.\n",
        [_scored(AWIN)],
    )
    fail = [v for v in result.violations if v.severity == Severity.FAIL]
    assert len(fail) >= 1
    assert result.verdict == Severity.FAIL


def test_scattered_or_reordered_terms_do_not_match():
    """Gate: same terms scattered through prose or out of order never match.

    All significant terms are present, but not together-and-in-order, so no
    violation fires even though the decision sits in the retrieval-gated tier.
    """
    scattered = (
        "We assume teams document the source of each feed. Another "
        "awin market uses the same schema, and one more awin variant "
        "is planned.\n"
    )
    result = check_prompt(scattered, [_scored(AWIN)])
    assert result.violations == []
    assert result.verdict == Severity.PASS

    reordered = "same source assume awin us awin mapping\n"
    result = check_prompt(reordered, [_scored(AWIN)])
    assert result.violations == []
    assert result.verdict == Severity.PASS


def test_internal_stopwords_are_part_of_the_phrase_template():
    """Gate: rule and input normalize identically -- nothing is dropped.

    A stopword-like word inside a multi-term rule is part of the complete
    sequence: its canonical spaced form and its separator-equivalent compound
    form both match, while the same tokens without it never do. This keeps
    the matcher exactly as broad as the phrase the rule states.
    """
    rule = Decision(
        id="fb-001",
        decision="Foo and bar must stay together",
        rationale="splitting them breaks ordering guarantees",
        scope=["widgets"],
        constraints=[],
        anti_patterns=["foo and bar"],
    )

    canonical = check_prompt("config uses foo and bar here\n", [_scored(rule)])
    assert canonical.verdict == Severity.FAIL

    identifier = check_prompt("config uses foo_and_bar here\n", [_scored(rule)])
    assert identifier.verdict == Severity.FAIL

    incomplete = check_prompt("config uses foo bar here\n", [_scored(rule)])
    assert incomplete.violations == []
    assert incomplete.verdict == Severity.PASS


def test_typed_forbid_literal_keeps_deterministic_fail():
    """D: FORBID_LITERAL stays exact, case-sensitive, and retrieval-independent."""
    decision = Decision(
        id="ADR-901",
        decision="Use the published install command only",
        rules=[Rule(type="FORBID_LITERAL", value="pip install mneme-legacy")],
    )
    # Score 0.0: typed rules enforce regardless of retrieval tier (ADR-019).
    result = check_prompt(
        "run pip install mneme-legacy to reproduce\n",
        [_scored(decision, score=0.0)],
    )
    [violation] = result.violations
    assert violation.kind == "typed_rule"
    assert violation.rule_type == "FORBID_LITERAL"
    assert violation.trigger == "pip install mneme-legacy"
    assert result.verdict == Severity.FAIL
