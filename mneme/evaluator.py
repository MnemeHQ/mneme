"""
evaluator.py — Deterministic alignment checker for Mneme.

This module is the nucleus of Mneme's evaluation capability. v1 is
intentionally simple and auditable: no LLM judge, no ML. The upgrade
path to a model-based evaluator is clear — replace _is_recommended()
and _is_contradicted() with model calls and keep everything else.

What is evaluated
-----------------
The evaluator takes a ContextPacket (the memory that was actually
injected into the call) rather than the full ProjectMemory. This keeps
evaluation honest: the model is only checked against the rules it was
given, not against constraints it never saw.

Two kinds of checks are run:

1. Hard-constraint check (rules + anti_patterns)
   For each constraint in packet.hard_constraints, extract the
   "forbidden terms" — keywords from the title, content, and tags.
   A violation is detected when:
     - a forbidden term appears in the response, AND
     - a positive recommendation signal is within 10 words, AND
     - no negation signal is also present in that window.

2. Decision-example check (decision_examples)
   For each injected DecisionExample whose decision was negative
   (the project previously declined something), check whether the
   response recommends the declined subject. Contradiction detected
   when the response recommends the same topic the decision rejected.

Score
-----
  alignment_score = matched_checks / total_checks

  Each constraint and each decision example is one check. A check
  passes if no violation is detected. Score 1.0 = all clear.
  Score 0.0 = every check detected a violation.

Upgrade path
------------
  v2: replace _is_recommended() with a fast classifier or LLM judge
  v3: replace _is_contradicted() with semantic similarity
  v4: add positive-alignment verification (currently only violations
      are checked; confirming explicit compliance requires NLP)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mneme.schemas import AlignmentResult, ContextPacket, DecisionExample, LLMResponse, MemoryItem


# ── Signal lexicons ───────────────────────────────────────────────────────────

# Words that suggest the model is recommending something.
_POSITIVE_SIGNALS: frozenset[str] = frozenset({
    "use", "add", "implement", "install", "integrate", "adopt", "migrate",
    "recommend", "suggest", "propose", "consider", "try", "introduce",
    "switch", "upgrade", "build", "create", "yes", "should", "could",
    "worth", "beneficial", "helpful", "ideal", "better", "best",
})

# Words that suggest the model is rejecting or cautioning against something.
_NEGATIVE_SIGNALS: frozenset[str] = frozenset({
    "dont", "don't", "avoid", "not", "never", "no", "shouldn't", "shouldnt",
    "won't", "wont", "cannot", "cant", "can't", "skip", "reject", "decline",
    "defer", "instead", "rather", "without", "against", "unnecessary",
    "premature", "overkill", "overhead",
    # Causal negatives: "embeddings break determinism", "adds heavy dependency"
    "break", "breaks", "breaking", "heavy", "bloat", "bloated", "cost",
    "complexity", "complex", "fragile", "risky", "dangerous",
})

# Words in a decision text that indicate the project previously said "no".
_DECLINED_MARKERS: frozenset[str] = frozenset({
    "declined", "deferred", "rejected", "refused", "decided against",
    "not adding", "not include",
})


# ── Text utilities ────────────────────────────────────────────────────────────

def _tokenize(text: str) -> set[str]:
    """Lowercase word tokens of length >= 3, punctuation stripped."""
    return {w for w in re.split(r"\W+", text.lower()) if len(w) >= 3}


def _windows(text: str, term: str, radius: int = 10) -> list[set[str]]:
    """Return a list of word-sets, one per occurrence of term in text.

    Each set contains the words within ``radius`` positions of the match.
    This is the neighbourhood checked for recommendation/negation signals.

    Args:
        text:   The text to search.
        term:   The keyword to locate.
        radius: Half-window size in words.

    Returns:
        One set per occurrence, or an empty list if the term is absent.
    """
    words = re.split(r"\W+", text.lower())
    result = []
    for i, word in enumerate(words):
        if word == term or (len(term) > 3 and term in word):
            lo = max(0, i - radius)
            hi = min(len(words), i + radius + 1)
            result.append(set(words[lo:hi]))
    return result


def _is_recommended(response: str, terms: set[str]) -> tuple[bool, str]:
    """Check whether any term appears with a positive signal nearby.

    A term counts as "recommended" when a positive signal word appears
    in its context window AND no negation signal counters it.

    Args:
        response: The LLM response text.
        terms:    Set of keywords to check.

    Returns:
        (True, triggering_term) if a recommendation is detected,
        (False, "") otherwise.
    """
    for term in sorted(terms):  # sorted for determinism
        for window in _windows(response, term):
            has_positive = bool(window & _POSITIVE_SIGNALS)
            has_negative = bool(window & _NEGATIVE_SIGNALS)
            if has_positive and not has_negative:
                return True, term
    return False, ""


# ── Per-check logic ───────────────────────────────────────────────────────────

def _check_constraint(item: MemoryItem, response: str) -> str | None:
    """Check one hard constraint against the response.

    Extracts "forbidden terms" from the item and detects if the response
    recommends any of them. Returns a violation message or None.

    Args:
        item:     A MemoryItem of type "rule" or "anti_pattern".
        response: The full LLM response text.

    Returns:
        A plain-English violation description, or None if no violation found.
    """
    # Collect forbidden terms: tags (excluding meta-labels) + title key words.
    meta_tags = {"forbidden", "avoid", "rule", "anti_pattern", "required"}
    tag_terms = {t.lower() for t in item.tags if t.lower() not in meta_tags}
    title_terms = {w for w in _tokenize(item.title) if len(w) > 4}
    forbidden = (tag_terms | title_terms) - meta_tags

    # Only proceed if we have something to check.
    if not forbidden:
        return None

    recommended, term = _is_recommended(response, forbidden)
    if recommended:
        label = "anti-pattern" if item.type == "anti_pattern" else "rule"
        return (
            f"Response appears to recommend '{term}' despite {label}: "
            f'"{item.title}"'
        )
    return None


def _check_decision(example: DecisionExample, response: str) -> str | None:
    """Check one decision example for contradictions in the response.

    Only runs when the decision was negative (project previously declined
    something). If so, checks whether the response recommends the declined
    subject matter anyway.

    Args:
        example:  A DecisionExample from the injected ContextPacket.
        response: The full LLM response text.

    Returns:
        A plain-English contradiction description, or None if no contradiction.
    """
    # Determine if this was a negative decision.
    decision_tokens = _tokenize(example.decision)
    if not (decision_tokens & _DECLINED_MARKERS):
        return None  # Not a "no" decision — skip.

    # What was declined? Key nouns from the task + tags.
    # Minimum length 5 filters out noise tokens like "v1", "v2", "and", "the".
    noise = _POSITIVE_SIGNALS | _NEGATIVE_SIGNALS | _DECLINED_MARKERS
    task_terms = {w for w in _tokenize(example.task) if len(w) >= 5} - noise
    tag_terms = {t.lower() for t in example.tags if len(t) >= 5} - noise
    subject = task_terms | tag_terms

    if not subject:
        return None

    recommended, term = _is_recommended(response, subject)
    if recommended:
        return (
            f"Response recommends '{term}', contradicting a prior decision: "
            f'"{example.decision.strip()}"'
        )
    return None


# ── Evaluator ─────────────────────────────────────────────────────────────────

class Evaluator:
    """Scores an LLM response against the ContextPacket that was injected.

    Usage::

        evaluator = Evaluator()
        result = evaluator.evaluate(response, packet)
        print(f"Score: {result.alignment_score:.2f}")
        print(result.explanation)
    """

    def evaluate(
        self,
        response: LLMResponse,
        packet: ContextPacket,
    ) -> AlignmentResult:
        """Run all checks and return a structured AlignmentResult.

        Args:
            response: The LLMResponse to evaluate.
            packet:   The ContextPacket that was injected into this call.
                      Evaluation is scoped to what the model was given.

        Returns:
            AlignmentResult with score, matched/missed rule lists,
            and a plain-English explanation.
        """
        matched: list[str] = []
        missed: list[str] = []
        text = response.content

        # ── Check 1: hard constraints ──────────────────────────────────────
        for item in packet.hard_constraints:
            violation = _check_constraint(item, text)
            if violation:
                missed.append(violation)
            else:
                matched.append(f"{item.id}: {item.title}")

        # ── Check 2: decision examples ────────────────────────────────────
        for example in packet.decision_examples:
            contradiction = _check_decision(example, text)
            if contradiction:
                missed.append(contradiction)
            else:
                # Only credit examples that had something checkable.
                dec_tokens = _tokenize(example.decision)
                if dec_tokens & _DECLINED_MARKERS:
                    matched.append(f"{example.id}: {example.decision[:60]}")

        # ── Score and explanation ─────────────────────────────────────────
        total = len(matched) + len(missed)
        score = round(len(matched) / total, 2) if total > 0 else 1.0

        explanation = _build_explanation(score, matched, missed, packet)

        return AlignmentResult(
            alignment_score=score,
            matched_rules=matched,
            missed_rules=missed,
            explanation=explanation,
        )


def _build_explanation(
    score: float,
    matched: list[str],
    missed: list[str],
    packet: ContextPacket,
) -> str:
    """Build a 2-3 sentence plain English summary of the evaluation.

    Args:
        score:   The computed alignment score.
        matched: List of passed check descriptions.
        missed:  List of failed check descriptions.
        packet:  The injected ContextPacket (for context in the summary).

    Returns:
        A short plain-text explanation string.
    """
    total = len(matched) + len(missed)
    checked = (
        f"{len(packet.hard_constraints)} constraint(s) and "
        f"{len(packet.decision_examples)} decision example(s)"
    )

    if not missed:
        return (
            f"Score: {score:.2f}. "
            f"Checked {checked}. "
            "No violations detected — the response is consistent with injected project memory. "
            "Note: this evaluator detects explicit violations; "
            "positive alignment verification requires a model-based judge."
        )

    n = len(missed)
    plural = "violation" if n == 1 else "violations"
    return (
        f"Score: {score:.2f}. "
        f"Checked {checked}; {n} {plural} detected out of {total} checks. "
        f"The response conflicts with: "
        + "; ".join(f'"{m.split(chr(58))[0]}"' for m in missed[:3])
        + ("." if len(missed) <= 3 else f", and {len(missed) - 3} more.")
    )
