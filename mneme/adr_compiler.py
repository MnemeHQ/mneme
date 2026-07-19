"""
adr_compiler.py — Validate, resolve precedence, and compile an ADR corpus.

The compiler is a deterministic three-stage pipeline:

    parse  ->  validate_corpus  ->  resolve_precedence  ->  active set

Each stage fails hard on bad input rather than silently dropping records.
``compile_adrs`` is the public entry point that runs all stages over a
directory of ADR markdown files.
"""

from __future__ import annotations

import re
from datetime import date as _date
from pathlib import Path

from mneme.adr_parser import parse_adr_directory
from mneme.adr_schema import (
    ADR,
    PRIORITY_RANK,
    VALID_PRIORITIES,
    VALID_STATUSES,
    ADRPrecedenceError,
    ADRValidationError,
)
from mneme.schemas import Decision
from mneme.adr_constraints import ConstraintDirective, parse_constraints_section


def _directive_to_constraint_string(d: ConstraintDirective) -> str:
    """Render a directive as a Decision.constraint string.

    FORBID_DEPENDENCY is rendered in the ``"no X"`` form so the existing
    enforcer (mneme.enforcer.check_prompt) triggers a WARN when the
    forbidden term appears in a checked input. FORBID_PATH and REQUIRE_PATH
    persist verbatim -- they're stored for retrieval visibility, but glob-
    vs-changed-file enforcement is not implemented (out of scope for the
    import MVP; the enforcer is a term-matcher, not a path-matcher).
    """
    if d.kind == "FORBID_DEPENDENCY":
        return f"no {d.value}"
    return f"{d.kind} {d.value}"


# ── Validation ────────────────────────────────────────────────────────────────


_ID_PATTERN = re.compile(r"^ADR-\d+$")
_SCOPE_SEGMENT = re.compile(r"^[a-z0-9_]+$")
_REQUIRED_FIELDS: tuple[str, ...] = ("id", "title", "status", "priority", "date")


def validate_corpus(adrs: list[ADR]) -> None:
    """Validate an ADR corpus and raise ``ADRValidationError`` on any problem.

    Errors are aggregated: the raised exception lists every detected
    problem, not just the first. This is intentional — it lets a maintainer
    fix the corpus in one pass instead of rerunning the compiler per error.

    Args:
        adrs: List of parsed ADR records.

    Raises:
        ADRValidationError: If any record is missing required fields, uses
                            an invalid enum value, has a malformed id /
                            date / scope, or if the supersession graph is
                            broken (unknown refs, cycles).
    """
    errors: list[str] = []

    # Per-record field checks.
    for adr in adrs:
        errors.extend(_check_required_fields(adr))
        errors.extend(_check_enums(adr))
        errors.extend(_check_id_format(adr))
        errors.extend(_check_date(adr))
        errors.extend(_check_scope(adr))

    # Cross-record checks.
    errors.extend(_check_unique_ids(adrs))
    errors.extend(_check_supersedes_refs(adrs))
    errors.extend(_check_no_supersession_cycles(adrs))

    if errors:
        raise ADRValidationError(errors)


def _check_required_fields(adr: ADR) -> list[str]:
    out: list[str] = []
    for field_name in _REQUIRED_FIELDS:
        value = getattr(adr, field_name, None)
        # ``scope`` is allowed to be empty (= global). It is not in the
        # required list above; ``_check_scope`` validates its format.
        if value in (None, ""):
            out.append(
                f"{adr.source_path or adr.id or '<unknown>'}: "
                f"missing required field '{field_name}'"
            )
    return out


def _check_enums(adr: ADR) -> list[str]:
    out: list[str] = []
    if adr.status and adr.status not in VALID_STATUSES:
        out.append(
            f"{adr.id or adr.source_path}: invalid status {adr.status!r} "
            f"(expected one of {VALID_STATUSES})"
        )
    if adr.priority and adr.priority not in VALID_PRIORITIES:
        out.append(
            f"{adr.id or adr.source_path}: invalid priority {adr.priority!r} "
            f"(expected one of {VALID_PRIORITIES})"
        )
    return out


def _check_id_format(adr: ADR) -> list[str]:
    if adr.id and not _ID_PATTERN.match(adr.id):
        return [
            f"{adr.source_path or adr.id}: invalid id {adr.id!r} "
            f"(expected pattern 'ADR-<number>')"
        ]
    return []


def _check_date(adr: ADR) -> list[str]:
    if not adr.date:
        return []
    try:
        _date.fromisoformat(adr.date)
    except ValueError:
        return [
            f"{adr.id or adr.source_path}: invalid date {adr.date!r} "
            f"(expected ISO 8601 YYYY-MM-DD)"
        ]
    return []


def _check_scope(adr: ADR) -> list[str]:
    # Empty scope == global. Allowed.
    if adr.scope == "":
        return []
    if adr.scope.startswith(".") or adr.scope.endswith("."):
        return [
            f"{adr.id or adr.source_path}: invalid scope {adr.scope!r} "
            f"(no leading or trailing dot)"
        ]
    segments = adr.scope.split(".")
    for seg in segments:
        if not _SCOPE_SEGMENT.match(seg):
            return [
                f"{adr.id or adr.source_path}: invalid scope {adr.scope!r} "
                f"(segments must match [a-z0-9_]+, dot-separated)"
            ]
    return []


def _check_unique_ids(adrs: list[ADR]) -> list[str]:
    seen: dict[str, int] = {}
    for adr in adrs:
        if not adr.id:
            continue
        seen[adr.id] = seen.get(adr.id, 0) + 1
    return [f"duplicate ADR id {adr_id!r} ({n} occurrences)"
            for adr_id, n in seen.items() if n > 1]


def _check_supersedes_refs(adrs: list[ADR]) -> list[str]:
    known = {a.id for a in adrs if a.id}
    out: list[str] = []
    for adr in adrs:
        for ref in adr.supersedes:
            if ref not in known:
                out.append(
                    f"{adr.id}: supersedes references unknown ADR {ref!r}"
                )
    return out


def _check_no_supersession_cycles(adrs: list[ADR]) -> list[str]:
    """Detect cycles in the supersession graph using DFS.

    Self-supersession (A -> A) is treated as a cycle and reported.
    """
    graph: dict[str, list[str]] = {}
    for adr in adrs:
        if not adr.id:
            continue
        # Only follow refs that exist in the corpus; unknown refs are
        # already reported by ``_check_supersedes_refs`` and would
        # otherwise cause spurious cycle reports.
        graph[adr.id] = [r for r in adr.supersedes if any(a.id == r for a in adrs)]

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in graph}
    cycles: list[list[str]] = []

    def dfs(node: str, stack: list[str]) -> None:
        color[node] = GRAY
        stack.append(node)
        for nxt in graph.get(node, []):
            if color.get(nxt, WHITE) == GRAY:
                # Cycle: from first occurrence of nxt in stack to end.
                start = stack.index(nxt)
                cycles.append(stack[start:] + [nxt])
            elif color.get(nxt, WHITE) == WHITE:
                dfs(nxt, stack)
        stack.pop()
        color[node] = BLACK

    for node in graph:
        if color[node] == WHITE:
            dfs(node, [])

    # Deduplicate cycles by their canonical form (sorted node tuple) so
    # the same cycle reached from different starts is reported once.
    seen: set[tuple[str, ...]] = set()
    out: list[str] = []
    for cyc in cycles:
        key = tuple(sorted(set(cyc)))
        if key in seen:
            continue
        seen.add(key)
        out.append("circular supersession detected: " + " -> ".join(cyc))
    return out


# ── Precedence resolution ────────────────────────────────────────────────────


def resolve_precedence(adrs: list[ADR]) -> list[ADR]:
    """Resolve ADR precedence and return the active constraint set.

    Hierarchy applied (in order):
        1. Status filter — only ``status == "accepted"`` survives.
        2. Explicit supersedes — any ADR whose id is referenced by another
           accepted ADR's ``supersedes`` is removed.
        3. Same-scope conflicts — within a scope group, higher priority
           wins; on a priority tie, the newer date wins.
        4. Specificity — does NOT cause compile-time conflicts; broader
           and narrower scopes coexist in the active set. The output is
           sorted most-specific-first so consumers can apply constraints
           in the natural overriding order.
        5. Ambiguity — if same-scope precedence cannot be broken,
           ``ADRPrecedenceError`` is raised. The compiler never silently
           picks a winner.

    Args:
        adrs: A validated list of parsed ADR records. Callers should run
              ``validate_corpus`` first; this function trusts its input.

    Returns:
        The active constraint set, sorted by scope specificity (desc),
        priority (desc), and id (asc) for stable output.

    Raises:
        ADRPrecedenceError: If two accepted ADRs share a scope and tie on
                            both priority and date.
    """
    # 1. Status filter.
    accepted = [a for a in adrs if a.status == "accepted"]

    # 2. Apply explicit supersedes.
    superseded_ids: set[str] = set()
    for a in accepted:
        for ref in a.supersedes:
            superseded_ids.add(ref)
    surviving = [a for a in accepted if a.id not in superseded_ids]

    # 3. Group by scope and resolve same-scope conflicts.
    by_scope: dict[str, list[ADR]] = {}
    for a in surviving:
        by_scope.setdefault(a.scope, []).append(a)

    winners: list[ADR] = []
    for scope, group in by_scope.items():
        winners.append(_pick_within_scope(scope, group))

    # 5. Stable, deterministic output ordering.
    winners.sort(
        key=lambda a: (-_specificity(a.scope), -PRIORITY_RANK[a.priority], a.id)
    )
    return winners


def _pick_within_scope(scope: str, group: list[ADR]) -> ADR:
    """Pick the single winner for a scope group via priority then date."""
    if len(group) == 1:
        return group[0]

    max_rank = max(PRIORITY_RANK[a.priority] for a in group)
    top_priority = [a for a in group if PRIORITY_RANK[a.priority] == max_rank]
    if len(top_priority) == 1:
        return top_priority[0]

    newest_date = max(a.date for a in top_priority)
    newest = [a for a in top_priority if a.date == newest_date]
    if len(newest) == 1:
        return newest[0]

    raise ADRPrecedenceError(scope=scope, ids=[a.id for a in newest])


def _specificity(scope: str) -> int:
    """Return the depth (segment count) of a scope. Empty == 0 (global)."""
    if scope == "":
        return 0
    return scope.count(".") + 1


# ── Compile orchestrator ─────────────────────────────────────────────────────


def compile_adrs(adr_dir: str | Path) -> list[ADR]:
    """Parse, validate, and resolve precedence over a directory of ADRs.

    Args:
        adr_dir: Path to a directory containing ADR markdown files.

    Returns:
        The compiled active constraint set, ordered by scope specificity
        (desc), priority (desc), and id (asc).

    Raises:
        ADRParseError:      If any file fails to parse.
        ADRValidationError: If the corpus fails schema validation.
        ADRPrecedenceError: If two accepted ADRs share a scope and tie on
                            both priority and date.
    """
    adrs = parse_adr_directory(adr_dir)
    validate_corpus(adrs)
    return resolve_precedence(adrs)


# ── Bridge to existing Decision schema ───────────────────────────────────────


def adrs_to_decisions(adrs: list[ADR]) -> list[Decision]:
    """Convert compiled ADR records into Decision records.

    The ``Decision`` dataclass is what the runtime pipeline (retriever,
    conflict detector, context builder) already consumes. This bridge
    lets ADR-driven corpora plug in without changing those components.

    Mapping:
        ADR.id      -> Decision.id
        ADR.title   -> Decision.decision
        ADR.body    -> Decision.rationale
        ADR.scope   -> Decision.scope (wrapped in a single-element list)
        ADR.date    -> Decision.created_at and Decision.updated_at

    ``Decision.constraints`` is populated from the ADR body's optional
    ``## Constraints`` section via ``parse_constraints_section`` and the
    ``_directive_to_constraint_string`` bridge. ``Decision.anti_patterns``
    is left empty for v1 — anti-pattern modelling stays in manual memory.

    Args:
        adrs: List of compiled (active) ADR records.

    Returns:
        Decision records in the same order as the input.
    """
    return [
        Decision(
            id=adr.id,
            decision=adr.title,
            rationale=adr.body,
            scope=[adr.scope],
            constraints=[
                _directive_to_constraint_string(d)
                for d in parse_constraints_section(adr.body)
            ],
            anti_patterns=[],
            created_at=adr.date,
            updated_at=adr.date,
        )
        for adr in adrs
    ]


__all__ = [
    "validate_corpus",
    "resolve_precedence",
    "compile_adrs",
    "adrs_to_decisions",
    "ADRPrecedenceError",
]
