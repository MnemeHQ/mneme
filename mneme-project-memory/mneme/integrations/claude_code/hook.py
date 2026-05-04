"""Claude Code hook shim — translates PreToolUse events into mneme check calls."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, TextIO


@dataclass(frozen=True)
class ToolEvent:
    tool_name: str
    file_path: str
    cwd: str
    tool_input: Dict[str, Any]


def parse_event(raw: str) -> ToolEvent:
    payload = json.loads(raw)
    tool_input = payload.get("tool_input", {}) or {}
    return ToolEvent(
        tool_name=payload["tool_name"],
        file_path=tool_input.get("file_path", ""),
        cwd=payload.get("cwd", ""),
        tool_input=tool_input,
    )


_MUTATING_TOOLS = frozenset({"Edit", "Write", "MultiEdit"})


def should_check(tool_name: str) -> bool:
    return tool_name in _MUTATING_TOOLS


class MaterializeError(Exception):
    """Raised when proposed content cannot be reconstructed (file missing,
    old_string not found, etc.). Caller should fail open."""


def materialize_proposed_content(event: ToolEvent) -> str:
    ti = event.tool_input
    if event.tool_name == "Write":
        return ti.get("content", "")

    file_path = ti.get("file_path", "")
    if not file_path:
        raise MaterializeError("missing file_path")

    try:
        original = Path(file_path).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as e:
        raise MaterializeError(f"cannot read {file_path}: {e}") from e

    if event.tool_name == "Edit":
        old, new = ti.get("old_string", ""), ti.get("new_string", "")
        if old not in original:
            raise MaterializeError("old_string not found in file")
        return original.replace(old, new, 1)

    if event.tool_name == "MultiEdit":
        content = original
        for i, edit in enumerate(ti.get("edits", [])):
            old, new = edit.get("old_string", ""), edit.get("new_string", "")
            if old not in content:
                raise MaterializeError(f"edit[{i}].old_string not found")
            content = content.replace(old, new, 1)
        return content

    raise MaterializeError(f"unsupported tool: {event.tool_name}")


def find_memory(start: Path) -> Optional[Path]:
    env = os.environ.get("MNEME_MEMORY")
    if env:
        p = Path(env)
        return p if p.is_file() else None
    cur = Path(start).resolve()
    while True:
        candidate = cur / ".mneme" / "project_memory.json"
        if candidate.is_file():
            return candidate
        if cur.parent == cur:
            return None
        cur = cur.parent


_CHECK_TIMEOUT_SECONDS = 10


def _run_check(event: ToolEvent, proposed_content: str, memory: Path, stderr: TextIO) -> int:
    mode = os.environ.get("MNEME_HOOK_MODE", "strict")
    if mode not in ("strict", "warn"):
        mode = "strict"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(proposed_content)
        input_path = tf.name

    try:
        rel = event.file_path or "(unknown)"
        try:
            proc = subprocess.run(
                [
                    sys.executable, "-m", "mneme", "check",
                    "--memory", str(memory),
                    "--input", input_path,
                    "--query", f"edit to {rel}",
                    "--mode", mode,
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=_CHECK_TIMEOUT_SECONDS,
            )
        except FileNotFoundError:
            print(
                "mneme-hook: could not launch mneme check (interpreter not found). "
                "Failing open.",
                file=stderr,
            )
            return 0
        except (OSError, subprocess.TimeoutExpired) as e:
            print(f"mneme-hook: check could not run ({e}). Failing open.", file=stderr)
            return 0

        if proc.stdout:
            print(proc.stdout, file=stderr)
        if proc.stderr:
            print(proc.stderr, file=stderr)
        return 2 if proc.returncode != 0 else 0
    finally:
        try:
            os.unlink(input_path)
        except OSError:
            pass


def main(stdin: TextIO = sys.stdin, stderr: TextIO = sys.stderr) -> int:
    try:
        raw = stdin.read()
        event = parse_event(raw)
    except (json.JSONDecodeError, KeyError) as e:
        print(f"mneme-hook: bad envelope: {e}", file=stderr)
        return 0

    if not should_check(event.tool_name):
        return 0

    memory = find_memory(Path(event.cwd or "."))
    if memory is None:
        return 0

    try:
        proposed_content = materialize_proposed_content(event)
    except MaterializeError as e:
        print(f"mneme-hook: cannot materialize content, failing open: {e}", file=stderr)
        return 0

    return _run_check(event, proposed_content, memory, stderr)


def cli_main() -> None:
    sys.exit(main())


if __name__ == "__main__":
    cli_main()
