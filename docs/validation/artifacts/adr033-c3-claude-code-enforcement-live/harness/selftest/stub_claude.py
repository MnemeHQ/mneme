"""Self-test stand-in for `claude`. NOT Claude Code, and never live evidence.

It exercises the harness plumbing offline: it reads the probe's planned call
from ``../setup.json``, runs the PreToolUse hook registered in the project
``.claude/settings.json`` exactly as configured (with the settings ``env``),
applies the edit only when the hook exits 0, and prints stream-json shaped
events. It does not model Claude Code's real behavior on hook timeouts or
launch failures; batch H is recorded live only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path


def emit(event: dict) -> None:
    print(json.dumps(event), flush=True)


def main() -> int:
    args = sys.argv[1:]
    if args[:1] == ["--version"]:
        print("selftest-stub (not Claude Code)")
        return 0
    model = args[args.index("--model") + 1] if "--model" in args else "stub"
    repo = Path.cwd()
    setup = json.loads((repo.parent / "setup.json").read_text(encoding="utf-8"))
    plan = setup["plan"]
    tool = plan["tool"]
    tool_input = {k: v for k, v in plan.items() if k != "tool"}
    use_id = "toolu_" + uuid.uuid4().hex[:20]
    emit({"type": "system", "subtype": "init", "model": model, "session_id": "selftest"})
    # Negative self-tests: a stub that never calls the tool, or ignores the hook.
    if os.environ.get("C3_STUB_SKIP_CALL") == "1":
        emit({"type": "result", "subtype": "success", "result": "declined"})
        return 0
    emit({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": use_id, "name": tool, "input": tool_input}]}})

    settings = json.loads((repo / ".claude" / "settings.json").read_text(encoding="utf-8"))
    env = dict(os.environ, **settings.get("env", {}))
    envelope = json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool,
                           "tool_input": tool_input, "tool_use_id": use_id,
                           "session_id": "selftest", "cwd": str(repo)})
    blocked, message = False, ""
    for group in settings.get("hooks", {}).get("PreToolUse", []):
        if tool not in group.get("matcher", "").split("|"):
            continue
        for handler in group.get("hooks", []):
            try:
                proc = subprocess.run(handler["command"], shell=True, input=envelope, text=True,
                                      capture_output=True, env=env, cwd=str(repo),
                                      timeout=handler.get("timeout", 60))
            except subprocess.TimeoutExpired:
                continue  # not modeled; batch H is live-only
            if proc.returncode == 2:
                blocked = True
                message = f"PreToolUse:{tool} hook error: [{handler['command']}]: {proc.stderr}"

    if os.environ.get("C3_STUB_IGNORE_HOOK") == "1":
        blocked = False
    if not blocked:
        target = Path(plan["file_path"])
        if tool == "Write":
            target.write_text(plan["content"], encoding="utf-8")
        else:
            text = target.read_text(encoding="utf-8")
            for edit in plan.get("edits") or [plan]:
                text = text.replace(edit["old_string"], edit["new_string"], 1)
            target.write_text(text, encoding="utf-8")
        message = f"The file {target} has been updated."
    emit({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": use_id, "is_error": blocked, "content": message}]}})
    emit({"type": "result", "subtype": "success", "result": message[:200]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
