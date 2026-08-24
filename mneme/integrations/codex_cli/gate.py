"""Codex CLI gate delegation (M1c): apply_patch proposal -> mneme check.

A thin transport layer in the established Agent SDK adapter pattern. This
module owns nothing about retrieval, rule applicability, conflict detection,
or enforcement semantics; it translates one parsed Codex ``apply_patch``
proposal into the existing ``mneme check --json`` contract and reports an
internal, transport-neutral result.

Policy (identical direction to the Claude Code hook / Agent SDK adapter):

- trusted PASS                  -> PASS (no Codex permission opinion)
- trusted WARN/FAIL, strict     -> DENY with Mneme's violation report
- trusted WARN/FAIL, warn mode  -> WARN (non-blocking diagnostic)
- evaluation_complete is False  -> FAIL_OPEN with applicability diagnostics
- unparseable Mneme output      -> FAIL_OPEN
- launch failure / timeout      -> FAIL_OPEN
- parse failure of the proposal -> FAIL_OPEN, explicitly "not evaluated"
- blank introduced content      -> SKIP (ADR-018 blank-delta rule)
- no project memory             -> SKIP

Fail-open outcomes are never silent at the result level: they carry the
reason so the eventual hook-wiring slice (M1d) can surface them on whatever
diagnostic channel Codex proves to accept. Only the DENY outcome has a proven
Codex wire shape (R0); this module keeps every other result transport-neutral.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from mneme.integrations.claude_code.hook import (
    _CHECK_TIMEOUT_SECONDS,
    _child_env,
    find_memory,
    format_applicability_reason,
    format_reason,
    parse_verdict,
    resolve_mode,
)
from mneme.integrations.codex_cli.patch_parser import (
    CodexPatchParseError,
    parse_pretooluse_payload,
)

# Internal outcomes. These are integration results, not Codex wire values;
# only codex_deny_output() below maps anything onto Codex's proven shape.
PASS = "PASS"
DENY = "DENY"
WARN = "WARN"
FAIL_OPEN = "FAIL_OPEN"
SKIP = "SKIP"


@dataclass(frozen=True)
class GateResult:
    action: str
    reason: str = ""
    verdict: Optional[str] = None
    evaluation_complete: bool = True
    target_path: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


def _run_mneme_check(
    memory: Path,
    rel_label: str,
    target_path: str,
    checked_content: str,
    mode: str,
    runner,
):
    """Materialize the delta and invoke the existing CLI contract once.

    The temporary input file always exists only for the duration of the call,
    including on launch failure and timeout.
    """
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    )
    handle.write(checked_content)
    input_path = handle.name
    handle.close()

    command = [
        sys.executable, "-m", "mneme", "check",
        "--memory", str(memory),
        "--input", input_path,
        "--query", f"edit to {rel_label}",
        "--mode", mode,
        "--json",
        "--target-path", target_path,
    ]
    try:
        return runner(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=_CHECK_TIMEOUT_SECONDS,
            env=_child_env(),
        )
    except subprocess.TimeoutExpired:
        print(
            "mneme-codex-gate: mneme check timed out. Failing open.",
            file=sys.stderr,
        )
        return None
    except FileNotFoundError:
        print(
            "mneme-codex-gate: could not launch mneme check "
            "(interpreter not found). Failing open.",
            file=sys.stderr,
        )
        return None
    except OSError as e:
        print(
            f"mneme-codex-gate: check could not run ({e}). Failing open.",
            file=sys.stderr,
        )
        return None
    finally:
        try:
            os.unlink(input_path)
        except OSError:
            pass


def evaluate_apply_patch(
    payload: Dict[str, Any],
    cwd: str = "",
    mode: Optional[str] = None,
    memory_override: Optional[str] = None,
    check_runner=subprocess.run,
) -> GateResult:
    """Evaluate one raw Codex PreToolUse apply_patch payload internally.

    ``check_runner`` is injectable for deterministic tests (Agent SDK adapter
    pattern). ``memory_override`` and ``mode`` exist for tests and embedders;
    production callers pass only ``payload`` and ``cwd``.
    """
    if memory_override:
        memory = Path(memory_override)
        if not memory.is_file():
            return GateResult(SKIP, "no project memory", target_path="")
    else:
        memory = find_memory(Path(cwd or "."))
        if memory is None:
            return GateResult(SKIP, "no project memory", target_path="")

    try:
        target_path_rel, introduced = parse_pretooluse_payload(payload)
    except CodexPatchParseError as e:
        # Not understood != governed. Fail open, visibly, by result.
        return GateResult(
            FAIL_OPEN,
            f"proposal not evaluated (apply_patch parse failure): {e}",
        )

    if not introduced.strip():
        # ADR-018: an edit introducing no non-blank lines cannot violate a
        # mechanically enforceable typed rule. Nothing to check.
        return GateResult(SKIP, "no non-blank introduced content",
                          target_path=target_path_rel)

    resolved_mode = mode if mode is not None else resolve_mode()

    target_abs = target_path_rel
    if target_path_rel and not Path(target_path_rel).is_absolute() and cwd:
        target_abs = str(Path(cwd) / target_path_rel)

    proc = _run_mneme_check(
        memory=memory,
        rel_label=target_path_rel,
        target_path=target_abs,
        checked_content=introduced,
        mode=resolved_mode,
        runner=check_runner,
    )
    if proc is None:
        return GateResult(
            FAIL_OPEN,
            "could not run mneme check. Failing open.",
            target_path=target_path_rel,
        )

    verdict_payload = parse_verdict(proc.stdout)
    if verdict_payload is None:
        return GateResult(
            FAIL_OPEN,
            "no parseable mneme.check/v1 verdict from mneme check "
            f"(exit {proc.returncode}). Failing open.",
            target_path=target_path_rel,
            details={"stderr": proc.stderr},
        )

    verdict = verdict_payload["verdict"]
    if verdict_payload.get("evaluation_complete") is False:
        return GateResult(
            FAIL_OPEN,
            format_applicability_reason(verdict_payload),
            verdict=verdict,
            evaluation_complete=False,
            target_path=target_path_rel,
            details={"payload": verdict_payload},
        )

    if verdict == "PASS":
        return GateResult(
            PASS,
            "",
            verdict=verdict,
            target_path=target_path_rel,
            details={"payload": verdict_payload},
        )

    reason = format_reason(verdict_payload)
    if resolved_mode == "warn":
        return GateResult(
            WARN,
            reason,
            verdict=verdict,
            target_path=target_path_rel,
            details={"payload": verdict_payload},
        )
    return GateResult(
        DENY,
        reason,
        verdict=verdict,
        target_path=target_path_rel,
        details={"payload": verdict_payload},
    )


def codex_deny_output(result: GateResult) -> Optional[Dict[str, Any]]:
    """The one Codex wire shape proven in R0, for the DENY outcome only.

    Every other outcome stays transport-neutral here: whether Codex accepts
    additionalContext-style diagnostics is unproven and belongs to M1d's live
    probing, not to this slice.
    """
    if result.action != DENY:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": result.reason,
        }
    }
