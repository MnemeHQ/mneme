"""Kiro hook — enforces Mneme decisions before Kiro's native write reaches disk.

Translates the Kiro CLI v1 ``PreToolUse`` hook envelope onto the existing
Mneme mutation-gate path. No retrieval, applicability, conflict, or
enforcement semantics are implemented here; the pure pieces are imported
from ``mneme.integrations.claude_code.hook`` (the same precedent as the
Agent SDK adapter).

Documented contract (Kiro CLI 3.0+, IDE 1.0+; see
docs/integrations/kiro-hook-spec.md for documented-versus-observed status):

- Hook files live at ``.kiro/hooks/*.json`` (schema ``version: "v1"``).
- A command action receives one JSON event on STDIN with at least
  ``hook_event_name``, ``cwd``, ``session_id``, ``tool_name``, and
  ``tool_input``.
- The native file-write tool is ``write`` (documented aliases:
  ``fs_write``, ``fsWrite``) whose input carries ``path`` and the full
  proposed ``content``.
- Exit code 0: hook succeeded; stdout is added to agent context.
- Any non-zero exit from ``PreToolUse`` blocks the tool invocation;
  stderr is sent to the agent.

Policy (mirrors the Claude Code hook policy):

- trusted PASS                  -> exit 0, no output (Kiro's normal
                                   permission flow is untouched)
- trusted WARN/FAIL, strict     -> reason to stderr, exit 2 (blocks)
- trusted WARN/FAIL, warn mode  -> exit 0, warning on stdout so Kiro adds
                                   it to agent context
- malformed envelope            -> exit 0 quietly (nothing to gate)
- materialization failure,
  timeout, subprocess failure,
  stale CLI, unparseable
  verdict, incomplete
  applicability evaluation      -> fail open but visibly: exit 0 with an
                                   UNEVALUATED notice on stdout
- no project memory             -> exit 0 quietly

Only trusted ``mneme.check/v1`` JSON verdicts are acted on. An exit code
from ``mneme check`` alone is never interpreted as a policy verdict.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Optional, TextIO

from mneme.integrations.claude_code.hook import (
    ToolEvent,
    _CHECK_TIMEOUT_SECONDS,
    _child_env,
    _is_stale_runtime,
    find_memory,
    format_applicability_reason,
    format_reason,
    introduced_content,
    MaterializeError,
    parse_verdict,
    resolve_mode,
)

# The native write tool name plus its documented aliases (kiro.dev/docs/
# reference/built-in-tools/). No undocumented names are accepted.
_WRITE_TOOL_NAMES = frozenset({"write", "fs_write", "fsWrite"})

_EVENT_NAME = "pretooluse"

_BLOCK_EXIT_CODE = 2


def parse_kiro_envelope(raw: str) -> Dict[str, object]:
    """Parse the JSON event Kiro pipes to a command-action hook on STDIN.

    Raises ``json.JSONDecodeError`` for non-JSON input and ``KeyError``
    when required fields are missing.
    """
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise KeyError("envelope is not a JSON object")
    if "hook_event_name" not in payload:
        raise KeyError("missing hook_event_name")
    return payload


def is_write_tool(tool_name: str) -> bool:
    """True for the native write tool under any documented name."""
    return tool_name in _WRITE_TOOL_NAMES


def normalize_to_tool_event(payload: Dict[str, object]) -> Optional[ToolEvent]:
    """Map the observed native write shape onto Mneme's ToolEvent.

    Returns ``None`` for events this gate does not govern (non-PreToolUse
    events, non-write tools). Only the observed shape -- ``tool_input``
    carrying ``path`` and full ``content`` -- is normalized. Missing
    ``path`` or ``content`` degrade to empty strings so the shared
    materializer decides how to treat them.
    """
    if str(payload.get("hook_event_name", "")).lower() != _EVENT_NAME:
        return None
    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str) or not is_write_tool(tool_name):
        return None
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}
    path = tool_input.get("path", "")
    content = tool_input.get("content", "")
    # Reuse the Claude-Code-shaped materializer verbatim by presenting the
    # event as a whole-content Write.
    return ToolEvent(
        tool_name="Write",
        file_path=path if isinstance(path, str) else "",
        cwd=str(payload.get("cwd", "") or ""),
        tool_input={
            "file_path": path if isinstance(path, str) else "",
            "content": content if isinstance(content, str) else "",
        },
    )


def _run_check(
    event: ToolEvent,
    checked_content: str,
    memory: Path,
    stderr: TextIO,
    stdout: TextIO,
) -> int:
    """Evaluate introduced content through `mneme check` and map to exit codes.

    The child invocation is identical to the Claude Code hook's: same
    memory, same query form, same ``--target-path`` for typed-rule
    applicability, same pinned PYTHONPATH, same timeout.
    """
    mode = resolve_mode()

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(checked_content)
        input_path = tf.name

    try:
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
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=_CHECK_TIMEOUT_SECONDS,
                env=_child_env(),
            )
        except FileNotFoundError:
            _emit_unevaluated(
                stdout, "could not launch mneme check (interpreter not found)"
            )
            return 0
        except (OSError, subprocess.TimeoutExpired) as e:
            _emit_unevaluated(stdout, f"check could not run ({e})")
            return 0

        payload = parse_verdict(proc.stdout)
        if payload is None:
            if _is_stale_runtime(proc.stderr):
                print(
                    "mneme-kiro-hook: the installed mneme CLI does not support "
                    "the required JSON/path-aware check options, so no edit "
                    "can be checked and ENFORCEMENT IS INACTIVE. "
                    "Upgrade with: pipx upgrade mneme-hq",
                    file=stderr,
                )
                _emit_unevaluated(
                    stdout, "stale mneme CLI; enforcement inactive"
                )
                return 0
            _emit_unevaluated(
                stdout,
                f"no parseable verdict from mneme check (exit {proc.returncode})",
            )
            if proc.stderr:
                print(proc.stderr, file=stderr)
            return 0

        verdict = payload["verdict"]
        if payload.get("evaluation_complete") is False:
            print(format_applicability_reason(payload), file=stderr)
            _emit_unevaluated(
                stdout, "typed-rule path applicability unknown"
            )
            return 0
        if verdict == "PASS":
            return 0

        reason = format_reason(payload)
        if mode == "warn":
            print(
                "[mneme] WARN - architectural decision flagged "
                "(warn mode; not blocked):\n" + reason,
                file=stdout,
            )
            return 0

        print(reason, file=stderr)
        return _BLOCK_EXIT_CODE
    finally:
        try:
            os.unlink(input_path)
        except OSError:
            pass


def _emit_unevaluated(stdout: TextIO, detail: str) -> None:
    """Fail open visibly: exit-0 stdout becomes Kiro's agent context."""
    print(f"[mneme] UNEVALUATED - failing open, this mutation was NOT checked: {detail}", file=stdout)


def main(
    stdin: TextIO = sys.stdin,
    stderr: TextIO = sys.stderr,
    stdout: TextIO = sys.stdout,
) -> int:
    try:
        raw = stdin.read()
        payload = parse_kiro_envelope(raw)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"mneme-kiro-hook: bad envelope: {e}", file=stderr)
        return 0

    event = normalize_to_tool_event(payload)
    if event is None:
        return 0

    memory = find_memory(Path(event.cwd or "."))
    if memory is None:
        return 0

    try:
        # Introduced-delta enforcement (ADR-018) via the shared gate: a
        # whole-content Write over an existing file checks only inserted or
        # replaced lines; a new file checks all of it; remediation of a
        # pre-existing violation is never blocked by what it removes.
        checked_content = introduced_content(event)
    except MaterializeError as e:
        _emit_unevaluated(stdout, f"cannot materialize content ({e})")
        return 0

    if not checked_content.strip():
        # Pure deletion or whitespace-only change: nothing introduced that a
        # mechanical rule could match (ADR-018).
        return 0

    return _run_check(event, checked_content, memory, stderr, stdout)


def cli_main() -> None:
    sys.exit(main())


if __name__ == "__main__":
    cli_main()
