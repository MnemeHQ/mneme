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
    FAIL  — input contains a term from a decision's anti_patterns list.
    WARN  — input mentions a term that a "no X" constraint forbids.
    PASS  — no violations found.

Exit codes for the CLI:
    0 = PASS, 1 = WARN, 2 = FAIL
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from mneme.decision_retriever import ScoredDecision
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
    trigger: str  # the specific term found in the input
    kind: str = "legacy"
    rule_type: str | None = None


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


def _is_declaring_source(input_path: str | Path | None, source_path: str) -> bool:
    """Return whether an input is the ADR that declared this decision."""
    if input_path is None or not source_path:
        return False
    try:
        return Path(input_path).resolve() == Path(source_path).resolve()
    except OSError:
        return False


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
    explodes into {open, without, encoding, python}, any one of which fires on
    its own -- so the rule reports a violation on prose that merely contains
    the word "open". Evaluating those corpus-wide turns a documented
    false-positive nuisance (#150) into a repo-wide edit block, so they stay
    behind retrieval until a typed literal vocabulary replaces them (#250).
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
    top-N retrieved decisions. See ``_enforcement_scope``.

    Args:
        input_text: The prompt or content to validate.
        scored:     Pre-scored decisions (from DecisionRetriever.retrieve()),
                    sorted descending by score.
        top:        Size of the retrieval-gated tier. This bounds how many
                    decisions have their *multi-term* rules applied; it never
                    limits which decisions are enforced.
        input_path: Optional checked-file path. A typed rule does not enforce
                    against its own declaring ADR source, which must be able to
                    contain the literal it defines.

    Returns:
        EnforcementResult with verdict and list of Violations.
    """
    violations: list[Violation] = []

    for s, literal_only in _enforcement_scope(scored, top):
        d = s.decision

        if not _is_declaring_source(input_path, d.source_path):
            for rule in d.rules:
                if rule.type == "FORBID_LITERAL" and literal_in_text(
                    rule.value, input_text
                ):
                    violations.append(Violation(
                        decision_id=d.id,
                        decision_text=d.decision,
                        severity=Severity.FAIL,
                        rule=rule.value,
                        trigger=rule.value,
                        kind="typed_rule",
                        rule_type=rule.type,
                    ))

        for ap in d.anti_patterns:
            if literal_only and not _is_literal_rule(ap):
                continue
            for term in _rule_terms(ap):
                if _word_in_text(term, input_text):
                    violations.append(Violation(
                        decision_id=d.id,
                        decision_text=d.decision,
                        severity=Severity.FAIL,
                        rule=ap,
                        trigger=term,
                        kind="anti_pattern",
                    ))
                    break  # one violation per anti_pattern entry

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

    return EnforcementResult(verdict=verdict, violations=violations)
