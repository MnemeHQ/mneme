"""Deterministic, compact architectural guidance for a submitted task.

Prompt-time guidance is intentionally distinct from edit-time enforcement.  It
selects relevant recorded decisions and describes typed-rule path selectors,
but it never decides whether a scoped rule applies without a target artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mneme.context_builder import DEFAULT_MAX_DECISIONS
from mneme.decision_retriever import DecisionRetriever, ScoredDecision, _tokenize
from mneme.guidance_roles import (
    ADJACENT_CONSTRAINT,
    GuidanceRoleAssignment,
    classify_guidance_roles,
)
from mneme.memory_store import MemoryStore
from mneme.schemas import Rule

DEFAULT_GUIDANCE_CHAR_BUDGET = 8_000
DEFAULT_GUIDANCE_MIN_SCORE = 1.0

_GUIDANCE_HEADER = (
    "[Mneme architectural guidance]\n"
    "Use these decisions only to guide the work the user requested. They do not\n"
    "expand the task. Do not add components, storage, dependencies, interfaces,\n"
    "refactors, or other architecture solely because a decision appears below."
)

_DIRECT_PREFIX = (
    "DIRECT DECISION [{decision_id}]\n"
    "This decision directly governs the requested work. Apply it to implementation\n"
    "choices within the user's requested scope."
)

_ADJACENT_PREFIX = (
    "ADJACENT CONSTRAINT [{decision_id}] — DO NOT IMPLEMENT AS EXTRA WORK\n"
    "This decision may constrain the requested work only if that work actually\n"
    "touches its area. Do not implement this decision merely because it is shown.\n"
    "Do not add components, storage, dependencies, interfaces, refactors, or other\n"
    "architecture solely to satisfy it."
)


@dataclass(frozen=True)
class GuidanceResult:
    """Observable result of one prompt-time guidance lookup."""

    context: str
    decision_ids: tuple[str, ...]
    scores: tuple[float, ...]
    reason: str


def _one_line(value: str) -> str:
    """Collapse untrusted memory prose to one compact, deterministic line."""
    return " ".join(value.split())


def _has_structured_match(scored: ScoredDecision) -> bool:
    """Whether relevance is supported outside the free-form rationale field."""
    return any(
        count > 0
        for field_name, count in scored.matches.items()
        if field_name != "rationale"
    )


def select_guidance_decisions(
    prompt: str,
    scored: list[ScoredDecision],
    *,
    max_items: int = DEFAULT_MAX_DECISIONS,
    min_score: float = DEFAULT_GUIDANCE_MIN_SCORE,
) -> list[ScoredDecision]:
    """Select confident decisions without using the empty-query fallback.

    Automatic guidance is conservative by design:

    - a prompt with no meaningful tokens returns no decisions;
    - the score must be strictly above ``min_score``;
    - rationale-only overlap is insufficient because imported ADR rationale can
      contain an entire long-form document; and
    - duplicate IDs are first-seen-wins, matching existing context behavior.
    """
    if max_items <= 0 or max_items > DEFAULT_MAX_DECISIONS:
        raise ValueError(
            f"max_items must be between 1 and {DEFAULT_MAX_DECISIONS}, "
            f"got {max_items!r}"
        )
    if min_score < 0:
        raise ValueError(f"min_score must be >= 0, got {min_score!r}")
    if not _tokenize(prompt):
        return []

    selected: list[ScoredDecision] = []
    seen: set[str] = set()
    for item in scored:
        if item.score <= min_score:
            continue
        if not _has_structured_match(item):
            continue
        if item.decision.id in seen:
            continue
        seen.add(item.decision.id)
        selected.append(item)
        if len(selected) >= max_items:
            break
    return selected


def _format_rule(rule: Rule) -> list[str]:
    label = (
        f"{rule.type} (forbidden exact literal)"
        if rule.type == "FORBID_LITERAL"
        else rule.type
    )
    lines = [f"  Rule {label}: {_one_line(rule.value)}"]
    if rule.include_paths is None:
        lines.append("    Applies to: all repository paths")
    else:
        lines.append(
            "    Applies when editing: "
            + ", ".join(_one_line(path) for path in rule.include_paths)
        )
        if rule.exclude_paths:
            lines.append(
                "    Excludes: "
                + ", ".join(_one_line(path) for path in rule.exclude_paths)
            )
    return lines


def _format_decision(assignment: GuidanceRoleAssignment) -> str:
    decision = assignment.scored_decision.decision
    prefix_template = (
        _ADJACENT_PREFIX
        if assignment.role == ADJACENT_CONSTRAINT
        else _DIRECT_PREFIX
    )
    lines = [
        prefix_template.format(decision_id=decision.id),
        f"Decision: {_one_line(decision.decision)}",
    ]
    if decision.scope:
        lines.append("  Scope: " + ", ".join(_one_line(v) for v in decision.scope))
    if decision.constraints:
        lines.append("  Constraints:")
        lines.extend(f"    - {_one_line(value)}" for value in decision.constraints)
    if decision.anti_patterns:
        lines.append("  Avoid:")
        lines.extend(f"    - {_one_line(value)}" for value in decision.anti_patterns)
    for rule in decision.rules:
        lines.extend(_format_rule(rule))
    return "\n".join(lines)


def _format_with_budget(
    assignments: tuple[GuidanceRoleAssignment, ...],
    char_budget: int,
) -> tuple[str, list[GuidanceRoleAssignment]]:
    if char_budget <= len(_GUIDANCE_HEADER):
        raise ValueError(
            "char_budget must be large enough for the guidance header; "
            f"got {char_budget!r}"
        )

    context = _GUIDANCE_HEADER
    kept: list[GuidanceRoleAssignment] = []
    for assignment in assignments:
        candidate = context + "\n\n" + _format_decision(assignment)
        if len(candidate) > char_budget:
            break
        context = candidate
        kept.append(assignment)

    if not kept:
        return "", []
    return context, kept


def build_guidance(
    memory_path: str | Path,
    prompt: str,
    *,
    max_items: int = DEFAULT_MAX_DECISIONS,
    min_score: float = DEFAULT_GUIDANCE_MIN_SCORE,
    char_budget: int = DEFAULT_GUIDANCE_CHAR_BUDGET,
) -> GuidanceResult:
    """Build compact, applicability-aware context for the current prompt only.

    File, JSON, and schema errors intentionally propagate to integration
    adapters, which own their transport-specific fail-open policy.
    """
    if not _tokenize(prompt):
        return GuidanceResult("", (), (), "low_signal")

    store = MemoryStore(memory_path)
    store.load()
    retriever = DecisionRetriever(store.decisions())
    selected = select_guidance_decisions(
        prompt,
        retriever.retrieve(prompt),
        max_items=max_items,
        min_score=min_score,
    )
    if not selected:
        return GuidanceResult("", (), (), "no_confident_match")

    assignments = classify_guidance_roles(selected)
    context, kept = _format_with_budget(assignments, char_budget)
    if not kept:
        return GuidanceResult("", (), (), "budget_exhausted")
    return GuidanceResult(
        context=context,
        decision_ids=tuple(
            item.scored_decision.decision.id for item in kept
        ),
        scores=tuple(item.scored_decision.score for item in kept),
        reason="context_ready",
    )


__all__ = [
    "DEFAULT_GUIDANCE_CHAR_BUDGET",
    "DEFAULT_GUIDANCE_MIN_SCORE",
    "GuidanceResult",
    "build_guidance",
    "select_guidance_decisions",
]
