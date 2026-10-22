"""Self-test stand-in for `claude`. NOT Claude Code, and never live evidence.

It exercises the harness plumbing offline: it reads the probe's planned call
from ``../setup.json``, runs the PreToolUse hook registered in the project
``.claude/settings.json`` exactly as configured (with the settings ``env``),
applies the edit only when the hook exits 0, and prints stream-json shaped
events. It does not model Claude Code's real behavior on hook timeouts or
launch failures; batch H is recorded live only.

Session transcript (C2b §17.5). The stub writes a transcript shaped like the
entries Claude Code 2.1.202 recorded in H1a-edit: the hook's stdout as a
`hook_success` attachment and, when that stdout carries
`hookSpecificOutput.additionalContext`, a `hook_additional_context`
attachment. ``C3_STUB_DIAG`` makes the negative cases: ``host_only`` (no
`hook_additional_context` attachment), ``missing`` (no hook attachments),
``no_transcript`` (the file is never written) and ``inject`` (a diagnostic
attachment the hook never emitted).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

DIAG_MARKER = "Mneme availability:"


def emit(event: dict) -> None:
    print(json.dumps(event), flush=True)


def main() -> int:
    args = sys.argv[1:]
    if args[:1] == ["--version"]:
        print("selftest-stub (not Claude Code)")
        return 0
    # Real `claude -p` reads piped stdin as extra input. The live ABSENT batch on
    # 2026-10-21 fed the batch runner's row list into Claude this way, so the
    # stub refuses any stdin content: the self-test must catch a leak.
    if not sys.stdin.isatty():
        leaked = sys.stdin.read()
        if leaked:
            print(f"stub claude: unexpected stdin ({len(leaked)} chars): {leaked[:80]!r}",
                  file=sys.stderr)
            return 3
    model = args[args.index("--model") + 1] if "--model" in args else "stub"
    repo = Path.cwd()
    setup = json.loads((repo.parent / "setup.json").read_text(encoding="utf-8"))
    plan = setup["plan"]
    tool = plan["tool"]
    tool_input = {k: v for k, v in plan.items() if k != "tool"}
    use_id = "toolu_" + uuid.uuid4().hex[:20]
    session = str(uuid.uuid4())
    diag_mode = os.environ.get("C3_STUB_DIAG", "")
    home = Path(os.environ["C3_SELFTEST_CLAUDE_HOME"])
    transcript_path = home / "projects" / "stub-project" / f"{session}.jsonl"
    transcript = [{"type": "user", "sessionId": session,
                   "message": {"role": "user", "content": args[args.index("-p") + 1]}}]
    offered = [t for t in ("Write", "Edit", "NotebookEdit")
               if t != os.environ.get("C3_STUB_DROP_TOOL")]
    emit({"type": "system", "subtype": "init", "model": model, "session_id": session,
          "tools": offered})
    if tool not in offered:  # a real host cannot call a tool it does not offer
        emit({"type": "result", "subtype": "success", "result": f"no {tool} tool"})
        return 0
    # Negative self-tests: a stub that never calls the tool, or ignores the hook.
    if os.environ.get("C3_STUB_SKIP_CALL") == "1":
        emit({"type": "result", "subtype": "success", "result": "declined"})
        return 0
    assistant = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": use_id, "name": tool, "input": tool_input}]}}
    emit(assistant)
    transcript.append(dict(assistant, sessionId=session))

    settings = json.loads((repo / ".claude" / "settings.json").read_text(encoding="utf-8"))
    env = dict(os.environ, **settings.get("env", {}))
    envelope = json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool,
                           "tool_input": tool_input, "tool_use_id": use_id,
                           "session_id": session, "transcript_path": str(transcript_path),
                           "cwd": str(repo)})
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
            hook = {"hookName": f"PreToolUse:{tool}", "toolUseID": use_id,
                    "hookEvent": "PreToolUse"}
            if diag_mode != "missing":
                transcript.append({"type": "attachment", "sessionId": session, "attachment": dict(
                    hook, type="hook_success", content="", stdout=proc.stdout,
                    stderr=proc.stderr, exitCode=proc.returncode)})
            context = None
            if proc.returncode == 0 and proc.stdout.strip():
                try:
                    context = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
                except (ValueError, KeyError, TypeError):
                    context = None
            if diag_mode == "inject" and context is None:
                context = (f"{DIAG_MARKER} authorization could not be verified "
                           "(AUTHORIZATION_UNVERIFIABLE, reason INJECTED).")
            if context is not None and diag_mode not in ("host_only", "missing"):
                transcript.append({"type": "attachment", "sessionId": session, "attachment": dict(
                    hook, type="hook_additional_context", content=[context])})

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
    result = {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": use_id, "is_error": blocked, "content": message}]}}
    emit(result)
    transcript.append(dict(result, sessionId=session))
    if diag_mode != "no_transcript":
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.write_text("".join(json.dumps(e) + "\n" for e in transcript),
                                   encoding="utf-8")
    emit({"type": "result", "subtype": "success", "result": message[:200]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
