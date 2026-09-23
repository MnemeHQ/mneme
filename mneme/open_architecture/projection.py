"""
mneme.open_architecture.projection — Temporary retrieval projection for O1A research.

Maps research DecisionCandidate records to in-memory mneme.schemas.Decision
objects for use with the existing frozen DecisionRetriever.

This is an ADAPTER ONLY:
- No persistence (no MemoryStore, no JSON file writes)
- No authority mutation (no DecisionAuthorityService, no DecisionProposal)
- No rule derivation from candidate_rule/enforcement_potential
- Pure data transformation for retrieval evaluation only
"""

from __future__ import annotations

from typing import Any

from mneme.open_architecture.candidates import ExtractedCandidate
from mneme.open_architecture.schemas import DecisionCandidate, Scope
from mneme.schemas import Decision


# ── Scope Projection ───────────────────────────────────────────────────────────


def _project_scopes(candidate: DecisionCandidate) -> list[str]:
    """Project DecisionCandidate scopes to Decision.scope format.

    Rules:
    - Preserve non-empty scope_expression values
    - If a scope has no expression, do not invent one
    - Deterministic ordering (lexicographic by type then expression)
    - Remove exact duplicates
    """
    seen: set[tuple[str, str | None]] = set()
    projected: list[str] = []

    for scope in candidate.scopes:
        key = (scope.scope_type, scope.scope_expression)
        if key in seen:
            continue
        seen.add(key)

        if scope.scope_expression is not None:
            projected.append(f"{scope.scope_type}:{scope.scope_expression}")
        else:
            projected.append(scope.scope_type)

    # Deterministic ordering
    projected.sort()
    return projected


# ── Primary Projection Function ────────────────────────────────────────────────


def project_candidate_to_decision(candidate: DecisionCandidate) -> Decision:
    """Project a research DecisionCandidate to a temporary mneme.schemas.Decision.

    This is a pure adapter for retrieval evaluation. It does NOT:
    - Persist the resulting Decision
    - Invoke any authority writer
    - Derive rules from candidate_rule or enforcement_potential
    - Filter by lifecycle or authority status

    Mapping:
    - DecisionCandidate.candidate_id          → Decision.id
    - DecisionCandidate.normalized_decision   → Decision.decision
    - DecisionCandidate.raw_statement         → Decision.rationale
    - DecisionCandidate.scopes (projected)    → Decision.scope

    Empty/constant fields:
    - constraints = []
    - anti_patterns = []
    - rules = []
    - test_evidence = []
    - created_at = "" (no invented timestamps)
    - updated_at = "" (no invented timestamps)
    - source_path = "" (no invented provenance)
    - memory_path = "" (no invented provenance)
    - status = candidate.lifecycle_status (passed through; NOT used for filtering)

    Note: lifecycle_status is mapped to status but the projection does NOT
    filter by it. Eligibility filtering is a caller/pipeline responsibility.
    """
    if not candidate.candidate_id:
        raise ValueError("candidate_id must be non-empty")
    if not candidate.normalized_decision:
        raise ValueError("normalized_decision must be non-empty")

    scope_list = _project_scopes(candidate)

    return Decision(
        id=candidate.candidate_id,
        decision=candidate.normalized_decision,
        rationale=candidate.raw_statement if candidate.raw_statement is not None else "",
        scope=scope_list,
        constraints=[],  # Not derived from research data in O1A2.4
        anti_patterns=[],  # Not derived from research data in O1A2.4
        rules=[],  # NOT derived from candidate_rule/enforcement_potential
        test_evidence=[],
        created_at="",
        updated_at="",
        source_path="",
        memory_path="",
        status=candidate.lifecycle_status,  # Pass through; eligibility filtering is caller's responsibility
    )


# ── Batch Projection ───────────────────────────────────────────────────────────


def project_candidates_to_decisions(candidates: list[DecisionCandidate]) -> list[Decision]:
    """Project a list of DecisionCandidates to temporary Decisions.

    Validates:
    - No duplicate candidate_ids (fails closed)
    """
    seen: set[str] = set()
    for c in candidates:
        if c.candidate_id in seen:
            raise ValueError(f"Duplicate candidate_id in projection input: {c.candidate_id}")
        seen.add(c.candidate_id)

    return [project_candidate_to_decision(c) for c in candidates]


__all__ = [
    "project_candidate_to_decision",
    "project_candidates_to_decisions",
]