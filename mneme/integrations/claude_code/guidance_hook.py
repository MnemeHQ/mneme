"""Claude Code UserPromptSubmit adapter for Mneme architectural guidance."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from mneme.guidance import build_guidance
from mneme.integrations.claude_code.hook import find_memory


@dataclass(frozen=True)
class PromptEvent:
    prompt: str
    cwd: str


_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_GUIDANCE_ENV_VARS = ("MNEME_GUIDANCE", "CLAUDE_PLUGIN_OPTION_GUIDANCE")


def guidance_enabled() -> bool:
    """Resolve opt-in guidance configuration.

    ``MNEME_GUIDANCE`` is the explicit environment override.  The plugin
    option follows.  Missing or unrecognized values are disabled because this
    feature remains opt-in until its live-model outcome gate is complete.
    """
    for name in _GUIDANCE_ENV_VARS:
        value = os.environ.get(name)
        if value is not None:
            return value.strip().lower() in _TRUE_VALUES
    return False


def parse_prompt_event(raw: str) -> PromptEvent:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("hook envelope must be a JSON object")
    if payload.get("hook_event_name") != "UserPromptSubmit":
        raise ValueError("expected UserPromptSubmit hook event")
    prompt = payload.get("prompt")
    if not isinstance(prompt, str):
        raise ValueError("UserPromptSubmit event requires a string prompt")
    cwd = payload.get("cwd", "")
    if not isinstance(cwd, str):
        raise ValueError("UserPromptSubmit cwd must be a string")
    return PromptEvent(prompt=prompt, cwd=cwd)


def _emit_context(context: str, stdout: TextIO) -> None:
    payload = json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    })
    stdout.write(payload + "\n")


def main(
    stdin: TextIO = sys.stdin,
    stderr: TextIO = sys.stderr,
    stdout: TextIO = sys.stdout,
) -> int:
    """Add guidance context when enabled; never reject the submitted prompt."""
    if not guidance_enabled():
        return 0

    try:
        event = parse_prompt_event(stdin.read())
    except Exception as exc:
        stderr.write(
            f"mneme-guidance-hook: invalid envelope ({exc}). "
            "Continuing without guidance.\n"
        )
        return 0

    try:
        memory = find_memory(Path(event.cwd or "."))
        if memory is None:
            return 0
        result = build_guidance(memory, event.prompt)
        if not result.context:
            return 0
        _emit_context(result.context, stdout)
    except Exception as exc:  # integration boundary must never reject the prompt
        stderr.write(
            "mneme-guidance-hook: guidance processing failed "
            f"({type(exc).__name__}: {exc}). Continuing without guidance.\n"
        )
        return 0
    return 0


def cli_main() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    cli_main()
