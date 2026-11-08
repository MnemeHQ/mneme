"""
conflict_detector.py — Flag violations of injected decisions in LLM output.

This is a *detector*, not a blocker: it returns Conflict records so the
caller can decide how to react (log, warn, surface in UI, reject).

v1 matching is deliberately simple:
  - Substring match, case-insensitive.
  - A constraint/anti-pattern phrase is extracted into keyword candidates.
  - A violation fires when the phrase appears in the response AND the
    surrounding 10-word window is NOT dominated by negation signals.

Upgrade path: swap the legacy phrase classifier for a model-based classifier
while preserving the structured conflict and applicability results.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from mneme.path_selectors import (
    RuleEvaluation,
    SelectorOutcome,
    evaluate_path_selectors,
)
from mneme.rule_identity import rule_id_for
from mneme.rule_matcher import literal_in_text
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


NONCOVERAGE_NOT_EVALUATED_ON_RESPONSE_TEXT = "NOT_EVALUATED_ON_RESPONSE_TEXT"


@dataclass(frozen=True)
class RuleNoncoverage:
    """A typed rule the response-text detector does not evaluate (ADR-034 §9).

    ``FORBID_NUMERIC_ABOVE`` is decided only by a whole-file source audit, so
    response text never covers it. The skip is reported, never presented as
    a conflict-free check.
    """

    decision_id: str
    decision_version_id: str
    rule_id: str
    rule_type: str
    reason: str = NONCOVERAGE_NOT_EVALUATED_ON_RESPONSE_TEXT


@dataclass
class ConflictDetectionResult:
    conflicts: list[Conflict] = field(default_factory=list)
    applicability: list[RuleEvaluation] = field(default_factory=list)
    # Additive (charter §7, F3). Reported, but deliberately not part of
    # ``evaluation_complete``: noncoverage is a stated limit of this surface.
    noncoverage: list[RuleNoncoverage] = field(default_factory=list)

    @property
    def evaluation_complete(self) -> bool:
        return not any(
            item.outcome == SelectorOutcome.UNKNOWN
            for item in self.applicability
        )


def noncoverage_note(noncoverage: list[RuleNoncoverage]) -> str:
    """Human note callers show next to any conflict result (F3)."""
    rule_ids = ", ".join(item.rule_id for item in noncoverage)
    return (
        f"{len(noncoverage)} numeric typed rule(s) not evaluated on response "
        f"text ({NONCOVERAGE_NOT_EVALUATED_ON_RESPONSE_TEXT}); the absence of "
        f"conflicts does not cover them: {rule_ids}"
    )


class NumericRuleNoncoverageError(RuntimeError):
    """Raised when list-only ``detect()`` would hide numeric noncoverage.

    ``detect()`` returns a bare list that cannot carry a note, so a decision
    set containing ``FORBID_NUMERIC_ABOVE`` rules is refused rather than
    returned as an apparently complete (possibly empty) conflict list. Use
    ``evaluate()`` for the explicit ``noncoverage`` trace.
    """

    def __init__(
        self,
        noncoverage: list[RuleNoncoverage],
        result: "ConflictDetectionResult",
    ) -> None:
        self.noncoverage = noncoverage
        self.result = result
        super().__init__(noncoverage_note(noncoverage))


class PathApplicabilityUnknownError(RuntimeError):
    """Raised when detect() cannot safely evaluate a scoped typed rule."""

    def __init__(self, applicability: list[RuleEvaluation]) -> None:
        self.applicability = applicability
        reasons = sorted({
            item.reason
            for item in applicability
            if item.outcome == SelectorOutcome.UNKNOWN
        })
        super().__init__(
            "typed-rule path applicability could not be evaluated: "
            + "; ".join(reasons)
        )


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

    def evaluate(
        self,
        response: str,
        decisions: Iterable[Decision],
        target_path: str | Path | None = None,
    ) -> ConflictDetectionResult:
        """Return a list of Conflicts — empty if no violation detected.

        Args:
            response:  The LLM response text to audit.
            decisions: The Decisions that were injected into the call.
            target_path: Artifact path the response is intended to modify.
        """
        conflicts: list[Conflict] = []
        applicability: list[RuleEvaluation] = []
        noncoverage: list[RuleNoncoverage] = []
        seen: set[tuple[str, str]] = set()  # (decision_id, phrase)

        for d in decisions:
            for rule_index, rule in enumerate(d.rules):
                if rule.type == "FORBID_NUMERIC_ABOVE":
                    # No numeric matching on response text (ADR-034 §9).
                    noncoverage.append(RuleNoncoverage(
                        decision_id=d.id,
                        decision_version_id=d.version_id,
                        rule_id=rule_id_for(d.id, rule),
                        rule_type=rule.type,
                    ))
                    continue
                if rule.type != "FORBID_LITERAL":
                    continue
                selection = evaluate_path_selectors(
                    include_paths=rule.include_paths,
                    exclude_paths=rule.exclude_paths,
                    input_path=target_path,
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
                    rule_id=rule_id_for(d.id, rule),
                    decision_version_id=d.version_id,
                ))
                if selection.outcome != SelectorOutcome.APPLIED:
                    continue
                if not literal_in_text(rule.value, response):
                    continue
                key = (d.id, f"{rule.type}:{rule.value}")
                if key in seen:
                    continue
                seen.add(key)
                conflicts.append(Conflict(
                    violated_decision_id=d.id,
                    reason=(
                        f"response contains {rule.type} value {rule.value!r}"
                    ),
                    snippet=_find_snippet(response, rule.value) or rule.value,
                ))

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

        return ConflictDetectionResult(
            conflicts=conflicts,
            applicability=applicability,
            noncoverage=noncoverage,
        )

    def detect(
        self,
        response: str,
        decisions: Iterable[Decision],
        target_path: str | Path | None = None,
    ) -> list[Conflict]:
        """Return conflicts, raising if scoped applicability is unknown.

        Raises ``NumericRuleNoncoverageError`` for a decision set containing
        numeric rules: a bare list cannot say they were not checked.
        """
        result = self.evaluate(response, decisions, target_path=target_path)
        if not result.evaluation_complete:
            raise PathApplicabilityUnknownError(result.applicability)
        if result.noncoverage:
            raise NumericRuleNoncoverageError(result.noncoverage, result)
        return result.conflicts


__all__ = [
    "Conflict",
    "ConflictDetectionResult",
    "ConflictDetector",
    "NONCOVERAGE_NOT_EVALUATED_ON_RESPONSE_TEXT",
    "NumericRuleNoncoverageError",
    "PathApplicabilityUnknownError",
    "RuleNoncoverage",
    "noncoverage_note",
]
