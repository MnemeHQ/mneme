"""Codex CLI PreToolUse hook entrypoint (M1d-b).

Reads one Codex PreToolUse JSON payload from stdin, delegates to
:func:`evaluate_apply_patch` (the M1c gate), and maps the internal
``GateResult`` onto exactly the Codex wire shapes proven in R0 and M1d-a:

=================  =========================================================
GateResult         Codex output
=================  =========================================================
PASS / SKIP        no output, exit 0 (no opinion)
DENY               ``permissionDecision: "deny"`` + Mneme reason (R0-proven)
WARN               ``additionalContext`` "[mneme] WARN ...", non-blocking
FAIL_OPEN          ``additionalContext`` "[mneme] UNEVALUATED ... NOT
                   evaluated", non-blocking (M1d-a-proven channel)
=================  =========================================================

No ``allow``, no ``ask``, no other output fields. Exit code is always 0:
blocking is expressed only through the trusted deny JSON; every degraded
path fails open visibly rather than by exit-code side effects.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import IO, Any, Dict, Optional

if __package__ in (None, ""):
    # Direct-script execution (codex hook commands invoke the file path).
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from mneme.integrations.codex_cli.gate import (
    DENY,
    FAIL_OPEN,
    WARN,
    codex_deny_output,
    evaluate_apply_patch,
)

WARN_CONTEXT_PREFIX = (
    "[mneme] WARN - architectural decision flagged (warn mode; not blocked):"
)
UNEVALUATED_CONTEXT_PREFIX = (
    "[mneme] UNEVALUATED - failing open, this mutation was NOT evaluated:"
)


def _context_output(text: str) -> Dict[str, Any]:
    """The non-blocking diagnostic shape proven in M1d-a."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": text,
        }
    }


def map_result(result) -> Optional[Dict[str, Any]]:
    """Map one internal :class:`GateResult` to Codex wire output (or None)."""
    deny_wire = codex_deny_output(result)
    if deny_wire is not None:
        return deny_wire
    if result.action == WARN:
        return _context_output(f"{WARN_CONTEXT_PREFIX}\n{result.reason}")
    if result.action == FAIL_OPEN:
        return _context_output(f"{UNEVALUATED_CONTEXT_PREFIX}\n{result.reason}")
    return None


def main(
    stdin: IO[str] = sys.stdin,
    stdout: IO[str] = sys.stdout,
    stderr: IO[str] = sys.stderr,
) -> int:
    try:
        payload = json.loads(stdin.read())
    except json.JSONDecodeError as e:
        print(f"mneme-codex-hook: bad envelope: {e}", file=stderr)
        return 0
    if not isinstance(payload, dict):
        print("mneme-codex-hook: bad envelope: not a JSON object", file=stderr)
        return 0
    # The hooks.json matcher scopes registration to apply_patch; anything else
    # reaching this entrypoint gets no opinion rather than a parse failure.
    if payload.get("tool_name") != "apply_patch":
        return 0

    result = evaluate_apply_patch(payload, cwd=str(payload.get("cwd") or ""))
    output = map_result(result)
    if output is not None:
        json.dump(output, stdout)
        stdout.write("\n")
    return 0


def cli_main() -> None:
    sys.exit(main())


if __name__ == "__main__":
    cli_main()
