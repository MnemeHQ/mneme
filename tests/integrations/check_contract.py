"""Contract-faithful doubles for ``mneme check --json`` (#260).

Integrations trust a check result only when payload, requested mode and exit
status agree (``hook.assess_verdict``). Test doubles therefore have to emit
what the real CLI emits, not an approximation: the mode the command asked
for, the CLI's exit code for that mode and verdict, schema-complete violation
records, and an UNKNOWN applicability trace behind ``evaluation_complete:
false``. ``tests/integrations/claude_code/test_hook_verdict_consistency.py``
pins these doubles against the real CLI so they cannot drift.
"""
from __future__ import annotations

import json
import subprocess
from typing import Any, Dict, List, Optional, Sequence

SCHEMA = "mneme.check/v1"

_EXIT_CODES = {
    "strict": {"PASS": 0, "WARN": 1, "FAIL": 2},
    "warn": {"PASS": 0, "WARN": 0, "FAIL": 0},
}

UNKNOWN_TRACE = {
    "decision_id": "scoped_001",
    "rule_type": "FORBID_LITERAL",
    "rule_value": "install legacy-client",
    "outcome": "UNKNOWN",
    "reason": "input path outside policy root",
}


def mode_of(command: Sequence[str]) -> str:
    """The ``--mode`` value an integration passed to ``mneme check``."""
    return command[list(command).index("--mode") + 1]


def violation(
    severity: str = "FAIL",
    *,
    decision_id: str = "D1",
    decision_text: str = "never do the bad thing",
    rule: str = "FORBIDDEN_TOKEN",
    trigger: Optional[str] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """One violation record shaped like the CLI's."""
    record = {
        "decision_id": decision_id,
        "decision_text": decision_text,
        "severity": severity,
        "rule": rule,
        "trigger": trigger if trigger is not None else rule,
        "kind": "legacy",
    }
    record.update(extra)
    return record


def check_payload(
    verdict: str,
    mode: str = "strict",
    *,
    violations: Optional[List[Dict[str, Any]]] = None,
    complete: bool = True,
    applicability: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """A payload the real CLI could emit for ``verdict`` in ``mode``.

    Omitted ``violations`` default to one record of the verdict's severity
    (none for PASS), since a WARN/FAIL verdict always carries one.
    """
    if violations is None:
        violations = [] if verdict == "PASS" else [violation(verdict)]
    if applicability is None:
        applicability = [] if complete else [dict(UNKNOWN_TRACE)]
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "mode": mode,
        "evaluation_complete": complete,
        "applicability": applicability,
        "violations": violations,
        "freshness": [],
    }


def exit_code(verdict: str, mode: str, *, complete: bool = True) -> int:
    """The CLI's exit status: incomplete applicability is always 2."""
    return 2 if not complete else _EXIT_CODES[mode][verdict]


def check_result(
    verdict: str,
    mode: str = "strict",
    *,
    stderr: str = "",
    **payload_kwargs: Any,
) -> subprocess.CompletedProcess:
    """A ``CompletedProcess`` matching ``mneme check --json`` exactly."""
    payload = check_payload(verdict, mode, **payload_kwargs)
    return subprocess.CompletedProcess(
        [],
        exit_code(verdict, mode, complete=payload["evaluation_complete"]),
        json.dumps(payload) + "\n",
        stderr,
    )


def check_result_for(
    command: Sequence[str],
    verdict: str,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    """``check_result`` in the mode ``command`` requested."""
    return check_result(verdict, mode_of(command), **kwargs)
