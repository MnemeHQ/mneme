"""Failing-first regression evidence for the legacy anti-pattern token false positive.

Dogfood incident: ``mneme check`` FAILs benign planning/documentation prose
because a multi-term legacy anti-pattern is decomposed into individual content
terms and fires when ANY single term appears
(``mneme/enforcer.py::check_prompt``, anti_patterns loop).

These tests pin the expected semantics WITHOUT changing production behavior:

    A/B. A multi-term anti-pattern must not describe a violation merely because
         benign prose contains one ordinary token from it (``awin`` /
         ``live`` / ``category`` / ``slug``).
    C.   The genuine pattern (the full phrase describing the forbidden
         approach) still FAILs, so any future fix cannot over-weaken.
    D.   Typed FORBID_LITERAL keeps its deterministic exact-match FAIL and is
         out of scope for any weakening.

Current state at base 3a47cc1c: A and B FAIL against the implementation,
proving the defect. C and D pass and guard the eventual semantic fix.
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

    This is the case the legacy rule exists for. Any semantic repair to the
    term-level matcher has to preserve this verdict.

    Note: the rule's own underscore-joined spelling never matches -- ``\\b``
    boundaries see ``assume_awin`` as one token, so no extracted term occurs.
    The genuine case therefore expresses the pattern in ordinary words, the
    only form the legacy matcher has ever been able to detect.
    """
    result = check_prompt(
        "Attribution logic assumes awin and awin us are the same source "
        "for every market.\n",
        [_scored(AWIN)],
    )
    fail = [v for v in result.violations if v.severity == Severity.FAIL]
    assert len(fail) >= 1
    assert result.verdict == Severity.FAIL


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
