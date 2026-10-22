"""ADR-033 availability routing for Claude Code direct writes only.

Architecture A: no enrollment record or trusted host state. C2a added the
routing; C2b (charter §7) replaces the verifier stub with a live verifier of
the remote baseline (``mneme.availability_authority``). An availability
refusal happens only when authorization is verified as AUTHORIZED and a
charter §5.3 R3-R6 condition holds. Without a declaration nothing here runs.
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
    data: Optional[dict] = None


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
                return LocalDeclaration(current, candidate, None, "invalid schema", data)
            if data.get("availability") != "closed":
                return LocalDeclaration(current, candidate, None, "invalid availability", data)
            if data.get("memory_path") != MEMORY_PATH:
                return LocalDeclaration(current, candidate, None, "invalid memory_path", data)
            return LocalDeclaration(current, candidate, MEMORY_PATH, data=data)
        if current.parent == current:
            return None
        current = current.parent


def verifier_stub(_declaration: LocalDeclaration) -> tuple[str, str]:
    """The C2a verifier, kept as a no-I/O test double."""
    return UNVERIFIABLE, VERIFIER_CONFIG_MISSING


def live_verifier(declaration: LocalDeclaration):
    """The shipped C2b verifier: live remote baseline, HTTPS ``origin`` only.

    Imported lazily so the no-declaration path never loads it. The test
    transport is not selectable from here, the environment or the envelope.
    """
    from mneme.availability_authority import verify
    return verify(declaration.root)


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


_TAMPERED = frozenset({"BEHIND", "DIVERGES", "INVALID"})
_STATE_CATEGORY = {
    "NOT_RUN": "CHECK_NOT_RUN",
    "UNTRUSTED": "CHECK_UNTRUSTED",
    "INCOMPLETE": "EVALUATION_INCOMPLETE",
    "COMPLETENESS_UNSTATED": "COMPLETENESS_UNSTATED",
}
_REMEDIATION = {
    "LOCAL_DECLARATION_TAMPERED":
        "restore .mneme/availability.json from the baseline branch "
        "(local declaration {relation})",
    "MEMORY_PATH_MISMATCH":
        "unset MNEME_MEMORY or point it at the declared .mneme/project_memory.json",
    "MEMORY_MISSING": "restore .mneme/project_memory.json from the baseline branch",
    "CHECK_NOT_RUN": "the check could not run; fix the mneme installation and retry",
    "CHECK_UNTRUSTED": "the check output was not trustworthy; fix mneme and retry",
    "EVALUATION_INCOMPLETE": "the check could not evaluate every applicable rule; "
                             "fix the cause and retry",
    "COMPLETENESS_UNSTATED": "upgrade mneme so the check states evaluation completeness",
}


def refusal_category(
    authorization: str,
    state: str,
    *,
    missing_memory: bool = False,
    invalid_declaration: bool = False,
    mismatch: bool = False,
    local_relation: Optional[str] = None,
) -> Optional[str]:
    """Charter §5.3 R3-R6 in precedence order; None means no refusal."""
    if authorization not in _VALID_AUTHORIZATION:
        raise ValueError("unknown authorization state")
    if state not in _VALID_STATES:
        raise ValueError("unknown evaluation state")
    if authorization != "AUTHORIZED" or state == "SKIPPED":
        return None
    if invalid_declaration or local_relation in _TAMPERED:
        return "LOCAL_DECLARATION_TAMPERED"
    if mismatch:
        return "MEMORY_PATH_MISMATCH"
    if missing_memory:
        return "MEMORY_MISSING"
    return _STATE_CATEGORY.get(state)


def routing_refuses(
    authorization: str,
    state: str,
    *,
    missing_memory: bool = False,
    invalid_declaration: bool = False,
    mismatch: bool = False,
    local_relation: Optional[str] = None,
) -> bool:
    """True only for AUTHORIZED with a charter §5.3 R3-R6 condition."""
    return refusal_category(
        authorization, state,
        missing_memory=missing_memory,
        invalid_declaration=invalid_declaration,
        mismatch=mismatch,
        local_relation=local_relation,
    ) is not None


def emit_availability(
    declaration: Optional[LocalDeclaration],
    state: str,
    stderr: TextIO,
    *,
    memory: Optional[Path] = None,
    payload: Optional[dict[str, Any]] = None,
    detail: str = "",
    verifier: Optional[Callable[[LocalDeclaration], Any]] = None,
) -> bool:
    """Emit an operational diagnostic and return whether to refuse (exit 2).

    The real hook never supplies a verifier, so ``live_verifier`` runs. A
    verifier may return a ``(state, reason)`` pair (test doubles) or a
    ``Verification``. Diagnostics are asserted as *emitted*, not delivered.
    """
    if declaration is None:
        return False
    result = (verifier or live_verifier)(declaration)
    if isinstance(result, tuple):
        authorization, reason = result
        baseline_label, relation = "", None
    else:
        authorization, reason = result.authorization, result.reason
        baseline_label = (f"; baseline={result.branch}@{result.tip[:7]}"
                          if result.tip and authorization != UNVERIFIABLE else "")
        relation = None
        if authorization == "AUTHORIZED" and result.baseline is not None:
            from mneme.availability_authority import local_relation
            relation = local_relation(declaration.data, declaration.problem, result.baseline)
    mismatch = memory_mismatch(declaration, memory)
    missing = memory is None
    category = refusal_category(
        authorization, state,
        missing_memory=missing,
        invalid_declaration=bool(declaration.problem),
        mismatch=mismatch,
        local_relation=relation,
    )
    refusal = category is not None
    detailed = bool(baseline_label) or relation is not None
    if category is None:
        verdict = "availability did not refuse."
    elif detailed:
        verdict = f"operational refusal (UNEVALUATED: {category})."
    else:
        verdict = "operational refusal."
    lines = [
        f"mneme-hook: availability {authorization}"
        + (f"({reason})" if reason else "")
        + baseline_label
        + f"; evaluation={state}; "
        + verdict,
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
        # ADR-034 charter §6 (F2): name the numeric matcher records that made
        # the evaluation incomplete. Rule identity and reason only; this is
        # an availability refusal, never a numeric violation.
        unevaluated = sorted({
            f"{item['rule_id']} {item.get('matcher_status')} "
            f"({item.get('primary_reason')})"
            for item in payload.get("applicability") or []
            if isinstance(item, dict)
            and item.get("rule_type") == "FORBID_NUMERIC_ABOVE"
            and item.get("matcher_status") in ("PARTIAL", "MATCHER_UNEVALUATED")
            and isinstance(item.get("rule_id"), str)
        })
        if unevaluated:
            lines.append(
                "mneme-hook: numeric rule(s) unevaluated on this input "
                "(whole-file audit only): " + "; ".join(unevaluated) + "."
            )
    if category is not None and detailed:
        lines.append(
            "mneme-hook: not a decision violation; remediation: "
            + _REMEDIATION[category].format(relation=(relation or "invalid").lower()) + "."
        )
    print("\n".join(lines), file=stderr)
    return refusal
