"""ADR-033 C2a availability diagnostics for Claude Code direct writes only.

Architecture A: this module has no verifier, enrollment or trusted host state.
The only shipped authorization result is AUTHORIZATION_UNVERIFIABLE. Routing
for other results is a deterministic test seam for C2b; it is not reachable
from an installed C2a hook. No availability refusal may occur in C2a.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, TextIO


DECLARATION_NAME = "availability.json"
SCHEMA = "mneme.availability/v1"
MEMORY_PATH = ".mneme/project_memory.json"
UNVERIFIABLE = "AUTHORIZATION_UNVERIFIABLE"
VERIFIER_CONFIG_MISSING = "VERIFIER_CONFIG_MISSING"

_VALID_STATES = frozenset({
    "TRUSTED_COMPLETE", "COMPLETENESS_UNSTATED", "INCOMPLETE",
    "UNTRUSTED", "NOT_RUN", "SKIPPED",
})
_VALID_AUTHORIZATION = frozenset({
    "AUTHORIZED", "REVOKED", "VERIFIED_ABSENT", UNVERIFIABLE,
})


@dataclass(frozen=True)
class LocalDeclaration:
    """Local trigger, not proof of authorization (ADR-033 Architecture A)."""

    root: Path
    path: Path
    memory_path: Optional[str]
    problem: str = ""


def discover_declaration(start: Path) -> Optional[LocalDeclaration]:
    """Inspect only the first ancestor that contains a .mneme directory.

    Do not consult MNEME_MEMORY, git config, remote refs or the network. An
    outer declaration is intentionally hidden by an inner .mneme directory.
    An absent declaration produces no extra output or work beyond this walk.
    """
    current = Path(start).resolve()
    while True:
        mneme_dir = current / ".mneme"
        if mneme_dir.is_dir():
            candidate = mneme_dir / DECLARATION_NAME
            if not candidate.exists() and not candidate.is_symlink():
                return None
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError):
                return LocalDeclaration(current, candidate, None, "unreadable or invalid JSON")
            if not isinstance(data, dict):
                return LocalDeclaration(current, candidate, None, "not an object")
            if data.get("schema") != SCHEMA:
                return LocalDeclaration(current, candidate, None, "invalid schema")
            if data.get("availability") != "closed":
                return LocalDeclaration(current, candidate, None, "invalid availability")
            if data.get("memory_path") != MEMORY_PATH:
                return LocalDeclaration(current, candidate, None, "invalid memory_path")
            return LocalDeclaration(current, candidate, MEMORY_PATH)
        if current.parent == current:
            return None
        current = current.parent


def verifier_stub(_declaration: LocalDeclaration) -> tuple[str, str]:
    """The only shipped C2a verifier: no I/O, no trusted authority."""
    return UNVERIFIABLE, VERIFIER_CONFIG_MISSING


def classify_observation(
    payload: Optional[dict[str, Any]],
    *,
    not_run: bool = False,
) -> str:
    """Classify a result after the existing assess_verdict coherence check.

    A None payload means UNTRUSTED if the check ran, not a new verdict parser.
    """
    if not_run:
        return "NOT_RUN"
    if payload is None:
        return "UNTRUSTED"
    if "evaluation_complete" not in payload:
        return "COMPLETENESS_UNSTATED"
    if payload["evaluation_complete"] is False:
        return "INCOMPLETE"
    return "TRUSTED_COMPLETE"


def memory_mismatch(declaration: LocalDeclaration, memory: Optional[Path]) -> bool:
    if memory is None or declaration.memory_path is None:
        return False
    return memory.resolve() != (declaration.root / declaration.memory_path).resolve()


def routing_refuses(
    authorization: str,
    state: str,
    *,
    missing_memory: bool = False,
    invalid_declaration: bool = False,
    mismatch: bool = False,
) -> bool:
    """Future C2b route, exercised via unit tests only.

    The C2a verifier cannot return AUTHORIZED, so this never introduces an
    availability refusal in the shipped hook.
    """
    if authorization not in _VALID_AUTHORIZATION:
        raise ValueError("unknown authorization state")
    if state not in _VALID_STATES:
        raise ValueError("unknown evaluation state")
    if authorization != "AUTHORIZED" or state == "SKIPPED":
        return False
    return (
        missing_memory or invalid_declaration or mismatch
        or state in {"COMPLETENESS_UNSTATED", "INCOMPLETE", "UNTRUSTED", "NOT_RUN"}
    )


def emit_availability(
    declaration: Optional[LocalDeclaration],
    state: str,
    stderr: TextIO,
    *,
    memory: Optional[Path] = None,
    payload: Optional[dict[str, Any]] = None,
    detail: str = "",
    verifier: Callable[[LocalDeclaration], tuple[str, str]] = verifier_stub,
) -> bool:
    """Emit an operational diagnostic and return whether the seam would refuse.

    The real hook never supplies a different verifier. Printed diagnostics are
    only asserted as *emitted*, not delivered to a Claude Code conversation.
    """
    if declaration is None:
        return False
    authorization, reason = verifier(declaration)
    mismatch = memory_mismatch(declaration, memory)
    missing = memory is None
    refusal = routing_refuses(
        authorization, state,
        missing_memory=missing,
        invalid_declaration=bool(declaration.problem),
        mismatch=mismatch,
    )
    lines = [
        f"mneme-hook: availability {authorization}"
        + (f"({reason})" if reason else "")
        + f"; evaluation={state}; "
        + ("operational refusal." if refusal else "availability did not refuse."),
    ]
    if declaration.problem:
        lines.append("mneme-hook: declaration invalid: " + declaration.problem)
    if missing:
        lines.append("mneme-hook: canonical memory missing.")
    if mismatch:
        lines.append("mneme-hook: SS-3 memory path mismatch; evaluation not bound to declaration.")
    if detail:
        lines.append("mneme-hook: " + detail)
    if state == "INCOMPLETE" and payload is not None:
        matched = payload.get("violations") or []
        # Only authoritative identifiers and counts; never proposed source,
        # triggers, rule text or checker stderr.
        decision_ids = sorted({
            str(v["decision_id"]) for v in matched
            if isinstance(v, dict) and isinstance(v.get("decision_id"), str)
        })
        lines.append(
            f"mneme-hook: {len(matched)} violation(s) matched in a partial "
            "evaluation, not a complete rule verdict"
            + (": " + ", ".join(decision_ids) if decision_ids else "") + "."
        )
    print("\n".join(lines), file=stderr)
    return refusal
