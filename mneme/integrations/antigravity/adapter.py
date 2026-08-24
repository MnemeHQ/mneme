"""Google Antigravity integration — deterministic enforcement at the pre-tool gate.

Maps Antigravity's ``PreToolUse`` hook events onto existing Mneme surfaces:

    PreToolUse (write_to_file | replace_file_content | multi_replace_file_content)
        -> ToolEvent translation (Antigravity args -> canonical Write/Edit/MultiEdit)
        -> introduced-content materialization + `mneme check`
           (the same enforcement path as the Claude Code hook)
        -> {"decision": "deny"} + Mneme's reason, or {} (no opinion)

No retrieval, applicability, conflict, or enforcement semantics are
implemented here. The pure pieces are imported from
``mneme.integrations.claude_code.hook``; this module only translates
between Antigravity's hook transport and that existing behavior.

Policy:

- trusted PASS              -> no opinion: stdout {} keeps Antigravity's
                               normal permission flow in charge. Emitting
                               "allow" would auto-grant the tool call and
                               weaken permissions a warning mode must not
                               touch.
- trusted WARN/FAIL,
  strict mode               -> deny, reason = Mneme's violation report
- trusted WARN/FAIL,
  warn mode                 -> no decision; the report goes to stderr
- unparseable verdict,
  operational failure,
  incomplete evaluation     -> fail open (no decision) but visibly: the
                               reason goes to stderr

Every code path writes exactly one JSON object to stdout. Antigravity
fails closed on hook output it cannot parse, so the adapter must always
emit well-formed JSON even when it has no opinion.

Usage — ``.agents/hooks.json`` inside a governed project::

    {
      "mneme": {
        "PreToolUse": [
          {
            "matcher": "write_to_file|replace_file_content|multi_replace_file_content",
            "hooks": [
              {
                "type": "command",
                "command": "python -m mneme.integrations.antigravity",
                "timeout": 30
              }
            ]
          }
        ]
      }
    }

Enforcement mode follows the shared resolution (``MNEME_HOOK_MODE``, then
"strict").
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Dict, Optional, TextIO

from mneme.integrations.claude_code.hook import (
    ToolEvent,
    _CHECK_TIMEOUT_SECONDS,
    _child_env,
    find_memory,
    format_applicability_reason,
    format_reason,
    introduced_content,
    MaterializeError,
    parse_verdict,
    resolve_mode,
    should_check,
)


class BadHookEvent(ValueError):
    """Raised when an Antigravity hook payload cannot be translated."""


# Antigravity mutation tools -> canonical Claude-style tool names. The
# canonical names select behavior in the shared materializer; this table is
# pure payload translation, not new tool semantics.
_TOOL_ALIASES = {
    "write_to_file": "Write",
    "replace_file_content": "Edit",
    "multi_replace_file_content": "MultiEdit",
}


def translate_tool_call(name: str, args: Dict) -> tuple[str, str, Dict]:
    """Translate one Antigravity tool call into ``(canonical_name, file_path, tool_input)``.

    Raises :class:`BadHookEvent` for unmapped tools or malformed arguments.
    """
    canonical = _TOOL_ALIASES.get(name)
    if canonical is None:
        raise BadHookEvent(f"unmapped tool: {name!r}")
    if not isinstance(args, dict):
        raise BadHookEvent("toolCall.args must be an object")

    file_path = args.get("TargetFile", "")
    if not isinstance(file_path, str):
        raise BadHookEvent("TargetFile must be a string")

    if canonical == "Write":
        tool_input = {
            "file_path": file_path,
            "content": args.get("CodeContent", ""),
        }
    elif canonical == "Edit":
        tool_input = {
            "file_path": file_path,
            "old_string": args.get("TargetContent", ""),
            "new_string": args.get("ReplacementContent", ""),
        }
    else:  # MultiEdit
        chunks = args.get("ReplacementChunks", [])
        if not isinstance(chunks, list):
            raise BadHookEvent("ReplacementChunks must be a list")
        edits = []
        for chunk in chunks:
            if not isinstance(chunk, dict):
                raise BadHookEvent("ReplacementChunks entries must be objects")
            edits.append(
                {
                    "old_string": chunk.get("TargetContent", ""),
                    "new_string": chunk.get("ReplacementContent", ""),
                }
            )
        tool_input = {"file_path": file_path, "edits": edits}

    return canonical, file_path, tool_input


def parse_hook_event(raw: str) -> Optional[ToolEvent]:
    """Parse one Antigravity PreToolUse stdin payload.

    Returns ``None`` for read-only or otherwise unmapped tool calls (the
    gate has no opinion on them). Raises ``BadHookEvent`` for mutating
    calls whose arguments cannot be translated safely -- callers must fail
    open rather than guess at content they cannot reconstruct.
    """
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise BadHookEvent("hook payload must be an object")
    call = payload.get("toolCall")
    if not isinstance(call, dict):
        raise BadHookEvent("missing toolCall")
    name = call.get("name", "")
    args = call.get("args") or {}

    if name not in _TOOL_ALIASES:
        return None
    canonical, file_path, tool_input = translate_tool_call(name, args)

    workspaces = payload.get("workspacePaths") or []
    cwd = workspaces[0] if workspaces and isinstance(workspaces[0], str) else ""
    return ToolEvent(
        tool_name=canonical,
        file_path=file_path,
        cwd=cwd,
        tool_input=tool_input,
    )


CheckRunner = Callable[..., subprocess.CompletedProcess]


def run_check(event: ToolEvent, content: str, memory: Path, mode: str, check_runner: CheckRunner):
    """Run `mneme check` exactly as the existing integrations do."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(content)
        input_path = tf.name

    rel = event.file_path or "(unknown)"
    target_path = event.file_path
    if target_path and not Path(target_path).is_absolute() and event.cwd:
        target_path = str(Path(event.cwd) / target_path)

    command = [
        sys.executable, "-m", "mneme", "check",
        "--memory", str(memory),
        "--input", input_path,
        "--query", f"edit to {rel}",
        "--mode", mode,
        "--json",
    ]
    if target_path:
        command.extend(["--target-path", target_path])

    try:
        return check_runner(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=_CHECK_TIMEOUT_SECONDS,
            env=_child_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        try:
            os.unlink(input_path)
        except OSError:
            pass


def emit(obj: Dict, stdout: TextIO) -> None:
    json.dump(obj, stdout)
    stdout.write("\n")


def main(
    stdin: TextIO = sys.stdin,
    stderr: TextIO = sys.stderr,
    stdout: TextIO = sys.stdout,
    check_runner: Optional[CheckRunner] = None,
) -> int:
    """One Antigravity hook invocation: stdin JSON -> stdout JSON."""
    try:
        event = parse_hook_event(stdin.read())
    except (json.JSONDecodeError, BadHookEvent) as e:
        print(f"mneme-antigravity: bad hook event, failing open: {e}", file=stderr)
        emit({}, stdout)
        return 0

    if event is None or not should_check(event.tool_name):
        emit({}, stdout)
        return 0

    memory = find_memory(Path(event.cwd or "."))
    if memory is None:
        # Same policy as every other integration: outside any governed
        # project, the gate has no opinion.
        emit({}, stdout)
        return 0

    try:
        checked_content = introduced_content(event)
    except MaterializeError as e:
        print(
            f"mneme-antigravity: cannot materialize content, failing open: {e}",
            file=stderr,
        )
        emit({}, stdout)
        return 0

    if not checked_content.strip():
        emit({}, stdout)
        return 0

    mode = resolve_mode()
    proc = run_check(event, checked_content, memory, mode, check_runner or subprocess.run)

    if proc is None:
        print(
            "mneme-antigravity: could not run mneme check. Failing open.",
            file=stderr,
        )
        emit({}, stdout)
        return 0

    payload = parse_verdict(proc.stdout)
    if payload is None:
        print(
            "mneme-antigravity: no parseable verdict from mneme check "
            f"(exit {proc.returncode}). Failing open.",
            file=stderr,
        )
        if proc.stderr:
            print(proc.stderr, file=stderr)
        emit({}, stdout)
        return 0

    verdict = payload["verdict"]
    if payload.get("evaluation_complete") is False:
        print(format_applicability_reason(payload), file=stderr)
        emit({}, stdout)
        return 0

    if verdict == "PASS":
        emit({}, stdout)
        return 0

    reason = format_reason(payload)
    if mode == "warn":
        print(
            "[mneme] WARN - architectural decision flagged (warn mode; "
            f"not blocked):\n{reason}",
            file=stderr,
        )
        emit({}, stdout)
        return 0

    emit({"decision": "deny", "reason": reason}, stdout)
    return 0


def cli_main() -> None:
    sys.exit(main())


if __name__ == "__main__":
    cli_main()
