"""Pure role classification for already-selected guidance decisions.

This module implements the frozen R2 unique-primary-anchor contract.  It is
not imported by the production guidance formatter or Claude Code hook in R3.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from mneme.decision_retriever import ScoredDecision


GuidanceRole = Literal["direct", "adjacent_constraint"]
GuidanceRoleReason = Literal[
    "unique_highest_retrieval_rank",
    "secondary_retrieval_candidate",
    "top_score_tie_no_direct_anchor",
]

DIRECT: GuidanceRole = "direct"
ADJACENT_CONSTRAINT: GuidanceRole = "adjacent_constraint"

UNIQUE_HIGHEST_RETRIEVAL_RANK: GuidanceRoleReason = (
    "unique_highest_retrieval_rank"
)
SECONDARY_RETRIEVAL_CANDIDATE: GuidanceRoleReason = (
    "secondary_retrieval_candidate"
)
TOP_SCORE_TIE_NO_DIRECT_ANCHOR: GuidanceRoleReason = (
    "top_score_tie_no_direct_anchor"
)


@dataclass(frozen=True)
class GuidanceRoleAssignment:
    """One selected decision plus its guidance-only role metadata.

    ``scored_decision`` is the original object supplied by the caller.  The
    classifier wraps it without copying, rescoring, or mutating its fields.
    """

    scored_decision: ScoredDecision
    role: GuidanceRole
    reason_code: GuidanceRoleReason
    retrieval_rank: int


def classify_guidance_roles(
    selected: list[ScoredDecision],
) -> tuple[GuidanceRoleAssignment, ...]:
    """Assign deterministic roles without changing selection or ranking.

    ``selected`` must be the descending, deduplicated output of
    ``select_guidance_decisions()``.  A unique highest-scoring candidate is the
    sole direct anchor.  Every other candidate is adjacent; a top-score tie
    grants no direct role.
    """
    if not selected:
        return ()

    top_score = selected[0].score
    top_tie = len(selected) > 1 and selected[1].score == top_score
    assignments: list[GuidanceRoleAssignment] = []

    for index, item in enumerate(selected):
        if index == 0 and not top_tie:
            role = DIRECT
            reason = UNIQUE_HIGHEST_RETRIEVAL_RANK
        elif top_tie and item.score == top_score:
            role = ADJACENT_CONSTRAINT
            reason = TOP_SCORE_TIE_NO_DIRECT_ANCHOR
        else:
            role = ADJACENT_CONSTRAINT
            reason = SECONDARY_RETRIEVAL_CANDIDATE
        assignments.append(GuidanceRoleAssignment(
            scored_decision=item,
            role=role,
            reason_code=reason,
            retrieval_rank=index + 1,
        ))

    return tuple(assignments)


__all__ = [
    "ADJACENT_CONSTRAINT",
    "DIRECT",
    "GuidanceRole",
    "GuidanceRoleAssignment",
    "GuidanceRoleReason",
    "SECONDARY_RETRIEVAL_CANDIDATE",
    "TOP_SCORE_TIE_NO_DIRECT_ANCHOR",
    "UNIQUE_HIGHEST_RETRIEVAL_RANK",
    "classify_guidance_roles",
]
