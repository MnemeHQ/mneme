"""
enforcer.py — Pre-flight enforcement of Mneme decisions against a prompt.

Checks an input text against the decision corpus and returns a structured
result with PASS / WARN / FAIL verdict and per-violation details.

Retrieval and enforcement answer different questions. Retrieval asks "what
context is relevant?" -- a ranking question, where a top-N cutoff is right.
Enforcement asks "is this forbidden?" -- a safety question, where ranking is
wrong, because a violation does not stop being a violation when the filename
happens to share no token with the decision's scope. See ADR-017.

Severity semantics:
    A typed FORBID_LITERAL match is a FAIL.
    FAIL  — input contains a single-term anti-pattern term, or the complete
            ordered term sequence of a multi-term anti-pattern (ADR-017
            amendment, 2026-08-24).
    WARN  — input mentions a term that a "no X" constraint forbids.
    PASS  — no violations found.

Exit codes for the CLI:
    0 = PASS, 1 = WARN, 2 = FAIL
    Path applicability UNKNOWN is an operational exit 2, not a policy verdict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from mneme.decision_retriever import ScoredDecision
from mneme.path_selectors import (
    RuleEvaluation,
    SelectorOutcome,
    evaluate_path_selectors,
)
from mneme.rule_matcher import literal_in_text


class Severity(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class Violation:
    decision_id: str
    decision_text: str
    severity: Severity
    rule: str     # the constraint or anti_pattern string that triggered
    trigger: str  # the matched term (single-term rules) or the matched rule
                  # expression (multi-term phrase match). For a phrase match
                  # this is the rule's text as authored; it need not appear
                  # verbatim in the input, since separators normalize away.
    kind: str = "legacy"
    rule_type: str | None = None
    input_path: str | None = None
    selector: str | None = None


@dataclass
class EnforcementResult:
    verdict: Severity
    violations: list[Violation] = field(default_factory=list)
    applicability: list[RuleEvaluation] = field(default_factory=list)

    @property
    def evaluation_complete(self) -> bool:
        return not any(
            item.outcome == SelectorOutcome.UNKNOWN
            for item in self.applicability
        )


# Words that appear frequently in rule descriptions but carry no domain signal.
_RULE_STOPWORDS: frozenset[str] = frozenset({
    "add", "use", "not", "get", "set", "run", "and", "the",
    "for", "with", "into", "from", "that", "this", "will",
    "should", "would", "could", "make", "keep", "have",
})


def _rule_terms(text: str, min_len: int = 3) -> list[str]:
    """Extract significant terms from a rule phrase."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if len(w) >= min_len and w not in _RULE_STOPWORDS]


def _word_in_text(term: str, text: str) -> bool:
    """True if term appears as a whole word (case-insensitive) in text."""
    return bool(re.search(r"\b" + re.escape(term) + r"\b", text, re.IGNORECASE))


def _phrase_tokens(text: str) -> list[str]:
    """All lowercased alphanumeric tokens of a phrase, in order.

    Rule and input use exactly the same normalization: whitespace,
    underscores, hyphens, and punctuation separate tokens identically, and
    nothing is dropped -- stopwords and short tokens included. Every token in
    the rule is therefore required to occur in the input, so
    ``assume_awin_awin_us_same_source`` normalizes to the same sequence as
    "assume awin awin us same source", while "foo bar" can never satisfy a
    rule stating "foo and bar".
    """
    return re.findall(r"[a-z0-9]+", text.lower())


def _phrase_in_text(phrase: list[str], text: str) -> bool:
    """True if the complete ordered token sequence occurs contiguously.

    A multi-term legacy anti-pattern is prose describing a pattern, not a bag
    of independent forbidden words (ADR-017 amendment). Requiring the whole
    sequence together and in order prevents benign prose that merely contains
    one ordinary term -- `awin`, `live`, `content` -- from failing the check,
    while still matching the rule's canonical or identifier spelling.
    """
    if not phrase:
        return False
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    n = len(phrase)
    return any(tokens[i:i + n] == phrase for i in range(len(tokens) - n + 1))


def _top_nonzero(scored: list[ScoredDecision], top: int) -> list[ScoredDecision]:
    kept: list[ScoredDecision] = []
    seen: set[str] = set()
    for s in scored:
        if s.score <= 0:
            continue
        if s.decision.id in seen:
            continue
        seen.add(s.decision.id)
        kept.append(s)
        if len(kept) >= top:
            break
    return kept


def _is_literal_rule(text: str, min_len: int = 3) -> bool:
    """True when a rule reduces to exactly one significant term.

    For a one-term rule such as ``"psycopg2"`` or ``"no postgres"``, the
    term-matching below is indistinguishable from matching the rule's own
    literal text: there is no phrase to take apart and therefore no guess
    about which word carries the meaning. Those rules are safe to evaluate
    against every decision in the corpus.

    Multi-term rules are the opposite. ``"open() without encoding= in Python"``
    is prose describing a pattern. Treating its terms as independent forbidden
    words made any single occurrence -- a bare "open", "without", or "content"
    -- fail benign prose (#150, and the 2026-08 dogfood false positives).
    They stay retrieval-gated here, and since the ADR-017 amendment they
    additionally match only as a complete ordered phrase (see
    ``_phrase_in_text``), so the gated tier no longer fires on incidental
    tokens either.
    """
    return len(_rule_terms(text, min_len=min_len)) == 1


def _enforcement_scope(
    scored: list[ScoredDecision],
    top: int,
) -> list[tuple[ScoredDecision, bool]]:
    """Every decision to evaluate, paired with whether to restrict it.

    Enforcement is not a ranking question -- "is this forbidden?" has the same
    answer whether or not the filename happened to share a token with the
    decision's scope (#254). So the corpus is evaluated in two tiers:

    - the retrieval-gated tier (top-N, positive score) keeps its pre-#254
      behaviour and is checked against every rule it carries;
    - every remaining decision is checked against its unambiguous literal
      rules only.

    Returns ``(scored_decision, literal_rules_only)`` pairs, gated tier first,
    each decision appearing once.
    """
    gated = _top_nonzero(scored, top)
    gated_ids = {g.decision.id for g in gated}

    out: list[tuple[ScoredDecision, bool]] = [(g, False) for g in gated]
    seen: set[str] = set(gated_ids)
    for s in scored:
        if s.decision.id in seen:
            continue
        seen.add(s.decision.id)
        out.append((s, True))
    return out


def check_prompt(
    input_text: str,
    scored: list[ScoredDecision],
    top: int = 3,
    input_path: str | Path | None = None,
) -> EnforcementResult:
    """Check input_text against the decision corpus.

    Unambiguous literal rules are checked against every decision supplied,
    regardless of retrieval score; multi-term rules are checked only for the
    top-N retrieved decisions, and there they match their complete ordered
    term sequence rather than any single term (ADR-017 amendment). See
    ``_enforcement_scope``.

    Args:
        input_text: The prompt or content to validate.
        scored:     Pre-scored decisions (from DecisionRetriever.retrieve()),
                    sorted descending by score.
        top:        Size of the retrieval-gated tier. This bounds how many
                    decisions have their *multi-term* rules applied; it never
                    limits which decisions are enforced.
        input_path: Optional checked-file path. A typed rule does not enforce
                    against its declaring ADR or policy-memory source, both of
                    which must be able to contain the literal it defines.

    Returns:
        EnforcementResult with verdict and list of Violations.
    """
    violations: list[Violation] = []
    applicability: list[RuleEvaluation] = []

    for s, literal_only in _enforcement_scope(scored, top):
        d = s.decision

        for rule_index, rule in enumerate(d.rules):
            selection = evaluate_path_selectors(
                include_paths=rule.include_paths,
                exclude_paths=rule.exclude_paths,
                input_path=input_path,
                memory_path=d.memory_path,
                policy_paths=(d.source_path, d.memory_path),
            )
            applicability.append(RuleEvaluation(
                decision_id=d.id,
                rule_type=rule.type,
                rule_value=rule.value,
                rule_index=rule_index,
                path_scoped=rule.is_path_scoped,
                outcome=selection.outcome,
                input_path=selection.input_path,
                selector=selection.selector,
                reason=selection.reason,
            ))
            if (
                selection.outcome == SelectorOutcome.APPLIED
                and rule.type == "FORBID_LITERAL"
                and literal_in_text(rule.value, input_text)
            ):
                violations.append(Violation(
                    decision_id=d.id,
                    decision_text=d.decision,
                    severity=Severity.FAIL,
                    rule=rule.value,
                    trigger=rule.value,
                    kind="typed_rule",
                    rule_type=rule.type,
                    input_path=selection.input_path,
                    selector=selection.selector,
                ))

        for ap in d.anti_patterns:
            if literal_only and not _is_literal_rule(ap):
                continue
            if _is_literal_rule(ap):
                # One significant term: term matching and literal matching
                # coincide, so the pre-existing whole-word behaviour is kept.
                trigger = next(
                    (t for t in _rule_terms(ap) if _word_in_text(t, input_text)),
                    None,
                )
            else:
                # Multi-term: the complete ordered phrase must be present.
                if _phrase_in_text(_phrase_tokens(ap), input_text):
                    trigger = ap
                else:
                    trigger = None
            if trigger is not None:
                violations.append(Violation(
                    decision_id=d.id,
                    decision_text=d.decision,
                    severity=Severity.FAIL,
                    rule=ap,
                    trigger=trigger,
                    kind="anti_pattern",
                ))

        for constraint in d.constraints:
            # Only handle "no X" style constraints.
            m = re.match(r"^no\s+(.+)$", constraint.strip(), re.IGNORECASE)
            if not m:
                continue
            forbidden_phrase = m.group(1).strip()
            if literal_only and not _is_literal_rule(forbidden_phrase):
                continue
            for term in _rule_terms(forbidden_phrase, min_len=3):
                if _word_in_text(term, input_text):
                    violations.append(Violation(
                        decision_id=d.id,
                        decision_text=d.decision,
                        severity=Severity.WARN,
                        rule=constraint,
                        trigger=term,
                        kind="constraint",
                    ))
                    break

    if any(v.severity == Severity.FAIL for v in violations):
        verdict = Severity.FAIL
    elif violations:
        verdict = Severity.WARN
    else:
        verdict = Severity.PASS

    return EnforcementResult(
        verdict=verdict,
        violations=violations,
        applicability=applicability,
    )


# ── Governability Assessment ────────────────────────────────────────────────────────

from dataclasses import dataclass
from typing import Literal

GovernabilityTier = Literal["enforceable", "partial", "guidance"]


@dataclass(frozen=True)
class GovernabilityAssessment:
    """
    Mneme's authoritative assessment of a Decision's governability.

    This is the single source of truth for whether a Decision can be
    deterministically enforced. Consumers (audit workspace, CLI, etc.)
    MUST use this function rather than reimplementing Mneme's semantics.

    Enforcement tiers (matching Mneme's check_prompt behavior):

    - enforceable: Decision has at least one mechanically enforceable rule
      (typed FORBID_LITERAL rule, or single-term anti_pattern).
      These are always checked regardless of retrieval score.

    - partial: Decision has only multi-term anti_patterns or "no X" constraints.
      Multi-term anti_patterns are only enforced for top-N retrieved decisions.
      "no X" constraints produce WARN severity.

    - guidance: Decision has no mechanically enforceable rules at all.
      It exists for retrieval/context only.
    """
    decision_id: str
    tier: GovernabilityTier
    has_literal_rules: bool
    has_single_term_anti_patterns: bool
    has_multi_term_anti_patterns: bool
    has_no_constraints: bool
    applicable_paths: tuple[str, ...]  # paths where typed rules apply
    confidence: float  # 1.0 = fully enforceable, 0.7 = partial, 0.0 = guidance only


def assess_governability(decision: "Decision") -> GovernabilityAssessment:
    """
    Assess whether a Decision can be deterministically governed by Mneme.

    This is the authoritative implementation of Mneme's governability semantics.
    All external consumers (audit workspace, CLI, etc.) MUST call this function
    rather than reimplementing the logic.

    Args:
        decision: A Mneme Decision object (from schemas.py)

    Returns:
        GovernabilityAssessment with Mneme's authoritative verdict.
    """
    from mneme.schemas import Decision

    # Check typed FORBID_LITERAL rules (always enforced, FAIL severity)
    has_literal_rules = any(
        rule.type == "FORBID_LITERAL"
        for rule in decision.rules
    )

    # Check anti-patterns - determine which are single-term (always enforced)
    single_term_aps = []
    multi_term_aps = []
    for ap in decision.anti_patterns:
        if _is_literal_rule(ap):
            single_term_aps.append(ap)
        else:
            multi_term_aps.append(ap)

    has_single_term_anti_patterns = bool(single_term_aps)
    has_multi_term_anti_patterns = bool(multi_term_aps)

    # Check "no X" constraints (produce WARN severity)
    has_no_constraints = any(
        _rule_terms(c, min_len=3) for c in decision.constraints
        if re.match(r"^no\s+(.+)$", c.strip(), re.IGNORECASE)
    )

    # Collect paths from typed rules
    applicable_paths = set()
    for rule in decision.rules:
        if rule.include_paths:
            applicable_paths.update(rule.include_paths)

    # Determine tier and confidence based on Mneme's enforcement behavior
    if has_literal_rules or has_single_term_anti_patterns:
        # These are ALWAYS enforced regardless of retrieval score
        tier: GovernabilityTier = "enforceable"
        confidence = 1.0
    elif has_multi_term_anti_patterns or has_no_constraints:
        # Multi-term anti-patterns only enforced for top-N retrieved decisions
        # "no X" constraints produce WARN (not FAIL)
        tier = "partial"
        confidence = 0.7
    else:
        # No mechanically enforceable rules - retrieval/context only
        tier = "guidance"
        confidence = 0.0

    return GovernabilityAssessment(
        decision_id=decision.id,
        tier=tier,
        has_literal_rules=has_literal_rules,
        has_single_term_anti_patterns=has_single_term_anti_patterns,
        has_multi_term_anti_patterns=has_multi_term_anti_patterns,
        has_no_constraints=has_no_constraints,
        applicable_paths=tuple(sorted(applicable_paths)),
        confidence=confidence,
    )


# Export for external consumers
__all__ = [
    "Severity",
    "Violation",
    "EnforcementResult",
    "check_prompt",
    "GovernabilityAssessment",
    "GovernabilityTier",
    "assess_governability",
]
