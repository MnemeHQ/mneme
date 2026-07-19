"""
conflict_detector.py — Flag violations of injected decisions in LLM output.

This is a *detector*, not a blocker: it returns Conflict records so the
caller can decide how to react (log, warn, surface in UI, reject).

v1 matching is deliberately simple:
  - Substring match, case-insensitive.
  - A constraint/anti-pattern phrase is extracted into keyword candidates.
  - A violation fires when the phrase appears in the response AND the
    surrounding 10-word window is NOT dominated by negation signals.

Upgrade path: swap ``_appears_recommended`` for a model-based classifier
without changing the public API.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from mneme.schemas import Decision


# Keywords that usually indicate the model is *rejecting* a term.
_NEGATION_MARKERS: frozenset[str] = frozenset({
    "not", "don't", "dont", "never", "no", "without", "avoid", "stop",
    "rather", "instead", "skip", "reject", "decline", "remove",
})


@dataclass
class Conflict:
    """One detected violation of an injected decision.

    Attributes:
        violated_decision_id: id of the Decision whose constraint or
                              anti-pattern was matched.
        reason:               Short human-readable description.
        snippet:              Substring of the response showing context
                              around the match (approx. 80 chars).
    """

    violated_decision_id: str
    reason: str
    snippet: str


def _extract_candidate_phrases(decision: Decision) -> list[tuple[str, str]]:
    """Return (phrase, field_label) tuples extracted from a Decision."""
    phrases: list[tuple[str, str]] = []
    for c in decision.constraints:
        phrases.append((c, "constraint"))
    for a in decision.anti_patterns:
        phrases.append((a, "anti-pattern"))
    return phrases


def _content_words(phrase: str) -> list[str]:
    """Return low-noise content words from a phrase (length > 3)."""
    stop = {"the", "and", "for", "with", "this", "that", "from", "into", "use"}
    return [w for w in re.findall(r"[A-Za-z][A-Za-z0-9_-]*", phrase.lower())
            if len(w) > 3 and w not in stop]


def _find_snippet(response: str, term: str, radius: int = 40) -> str | None:
    """Return a context snippet around the first case-insensitive match of term."""
    idx = response.lower().find(term.lower())
    if idx < 0:
        return None
    lo = max(0, idx - radius)
    hi = min(len(response), idx + len(term) + radius)
    return response[lo:hi].strip()


def _window_is_negated(snippet: str) -> bool:
    """Rough check: does the snippet read as a rejection of the term?"""
    tokens = {w for w in re.split(r"\W+", snippet.lower()) if w}
    return bool(tokens & _NEGATION_MARKERS)


class ConflictDetector:
    """Detects violations of injected decisions in LLM output."""

    def detect(
        self,
        response: str,
        decisions: Iterable[Decision],
    ) -> list[Conflict]:
        """Return a list of Conflicts — empty if no violation detected.

        Args:
            response:  The LLM response text to audit.
            decisions: The Decisions that were injected into the call.
        """
        conflicts: list[Conflict] = []
        seen: set[tuple[str, str]] = set()  # (decision_id, phrase)

        for d in decisions:
            for phrase, field_label in _extract_candidate_phrases(d):
                # Pick the most content-bearing word as the search anchor.
                words = _content_words(phrase)
                if not words:
                    continue
                anchor = max(words, key=len)

                snippet = _find_snippet(response, anchor)
                if snippet is None:
                    continue
                if _window_is_negated(snippet):
                    continue

                key = (d.id, phrase)
                if key in seen:
                    continue
                seen.add(key)

                conflicts.append(Conflict(
                    violated_decision_id=d.id,
                    reason=f"response appears to endorse {field_label} '{phrase}'",
                    snippet=snippet,
                ))

        return conflicts
