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


def _spans(needle: str, haystack: str) -> list[tuple[int, int]]:
    """Every case-insensitive occurrence of needle, as half-open spans."""
    if not needle:
        return []
    out: list[tuple[int, int]] = []
    lowered, target = haystack.lower(), needle.lower()
    start = lowered.find(target)
    while start != -1:
        out.append((start, start + len(target)))
        start = lowered.find(target, start + 1)
    return out


def _literal_violations(
    decision, input_text: str,
) -> list[Violation]:
    """Report each forbidden literal occurrence not covered by an exemption.

    Neither of the simpler matchers works for the case this exists to solve
    (ADR-005's `pip install mneme` vs `pip install mneme-hq`):

    - term matching fires on any single token, so it flags the *correct*
      command and any prose containing "install";
    - plain substring matching flags the correct command too, because the
      forbidden literal is a substring of it;
    - word-boundary matching does not help either, since the hyphen is itself
      a word boundary.

    So: find every occurrence of the forbidden literal, then suppress an
    occurrence only when an allowed container *fully contains* it. Containment
    is strict on purpose. An exemption that merely overlaps -- ALLOW
    `install mneme-hq` against FORBID `pip install mneme` -- leaves the
    forbidden span's `pip ` prefix uncovered and the correct command is still
    reported. That is an authoring hazard rather than an algorithm defect, and
    it is pinned by test rather than smoothed over, because widening the rule
    to "overlaps" would let a narrow exemption silently disable a broad
    prohibition.
    """
    violations: list[Violation] = []
    for rule in getattr(decision, "literal_rules", []) or []:
        exempt: list[tuple[int, int]] = []
        for container in rule.allowed_containers:
            exempt.extend(_spans(container, input_text))

        for start, end in _spans(rule.value, input_text):
            covered = any(a <= start and end <= b for a, b in exempt)
            if covered:
                continue
            violations.append(Violation(
                decision_id=decision.id,
                decision_text=decision.decision,
                severity=Severity.FAIL,
                rule=f"FORBID_STRING: {rule.value}",
                trigger=rule.value,
            ))
    return violations


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

    Returns:
        EnforcementResult with verdict and list of Violations.
    """
    violations: list[Violation] = []

    for s, literal_only in _enforcement_scope(scored, top):
        d = s.decision

        # Typed literal rules are enforceable by construction, so they apply to
        # every decision regardless of retrieval score or tier (ADR-019). This
        # is what makes the vocabulary worth having: it closes #254 for these
        # rules outright, rather than via the term-count proxy in ADR-017.
        violations.extend(_literal_violations(d, input_text))

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
                    ))
                    break

    if any(v.severity == Severity.FAIL for v in violations):
        verdict = Severity.FAIL
    elif violations:
        verdict = Severity.WARN
    else:
        verdict = Severity.PASS

    return EnforcementResult(verdict=verdict, violations=violations)
