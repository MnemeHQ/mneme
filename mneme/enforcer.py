"""
enforcer.py — Pre-flight enforcement of Mneme decisions against a prompt.

Checks an input text against retrieved decisions and returns a structured
result with PASS / WARN / FAIL verdict and per-violation details.

Severity semantics:
    FAIL  — input contains a term from a decision's anti_patterns list.
    WARN  — input mentions a term that a "no X" constraint forbids.
    PASS  — no violations found among the top-N retrieved decisions.

Exit codes for the CLI:
    0 = PASS, 1 = WARN, 2 = FAIL
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from mneme.decision_retriever import ScoredDecision


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
    trigger: str  # the specific term found in the input


@dataclass
class EnforcementResult:
    verdict: Severity
    violations: list[Violation] = field(default_factory=list)


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


def check_prompt(
    input_text: str,
    scored: list[ScoredDecision],
    top: int = 3,
) -> EnforcementResult:
    """Check input_text against the top-N retrieved decisions.

    Args:
        input_text: The prompt or content to validate.
        scored:     Pre-scored decisions (from DecisionRetriever.retrieve()),
                    sorted descending by score.
        top:        Maximum number of decisions to check.

    Returns:
        EnforcementResult with verdict and list of Violations.
    """
    violations: list[Violation] = []

    for s in _top_nonzero(scored, top):
        d = s.decision

        for ap in d.anti_patterns:
            for term in _rule_terms(ap):
                if _word_in_text(term, input_text):
                    violations.append(Violation(
                        decision_id=d.id,
                        decision_text=d.decision,
                        severity=Severity.FAIL,
                        rule=ap,
                        trigger=term,
                    ))
                    break  # one violation per anti_pattern entry

        for constraint in d.constraints:
            # Only handle "no X" style constraints.
            m = re.match(r"^no\s+(.+)$", constraint.strip(), re.IGNORECASE)
            if not m:
                continue
            forbidden_phrase = m.group(1).strip()
            for term in _rule_terms(forbidden_phrase, min_len=3):
                if _word_in_text(term, input_text):
                    violations.append(Violation(
                        decision_id=d.id,
                        decision_text=d.decision,
                        severity=Severity.WARN,
                        rule=constraint,
                        trigger=term,
                    ))
                    break

    if any(v.severity == Severity.FAIL for v in violations):
        verdict = Severity.FAIL
    elif violations:
        verdict = Severity.WARN
    else:
        verdict = Severity.PASS

    return EnforcementResult(verdict=verdict, violations=violations)
