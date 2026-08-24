"""R0 logging hook for the Codex CLI capability probe.

Behavior:
- Always appends the raw stdin payload byte-exact to
  $MNEME_PROBE_EVIDENCE_DIR/events/ plus an index line with sha256.
- MNEME_PROBE_MODE=log (default): exit 0, no stdout output.
- MNEME_PROBE_MODE=deny_apply_patch: additionally return a documented deny
  decision for PreToolUse events whose tool_name is apply_patch; all other
  events stay silent. The deny shape used here is one of the shapes under
  test -- which shape actually blocks on the pinned build is an R0 finding,
  selectable via MNEME_PROBE_DENY_SHAPE (hookSpecificOutput | legacy | exit2),
  default hookSpecificOutput.
- MNEME_PROBE_MODE=additional_context (M1d-a): return a non-blocking
  hookSpecificOutput.additionalContext diagnostic for PreToolUse apply_patch
  -- no permissionDecision at all -- to prove whether Codex 0.149.1 accepts
  and delivers hook-specific diagnostics on this surface.

This hook contains no Mneme logic and must never grow any.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path


def _evidence_dir() -> Path:
    root = os.environ.get("MNEME_PROBE_EVIDENCE_DIR")
    if not root:
        sys.stderr.write("log_hook: MNEME_PROBE_EVIDENCE_DIR not set\n")
        sys.exit(3)
    events = Path(root) / "events"
    events.mkdir(parents=True, exist_ok=True)
    return events


def _capture(events_dir: Path, raw: bytes) -> None:
    parsed = {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except Exception:
        pass
    event = str(parsed.get("hook_event_name", "unknown"))
    tool = str(parsed.get("tool_name", ""))
    seq = len(list(events_dir.glob("*.json")))
    ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    name = f"{seq:04d}-{event}" + (f"-{tool}" if tool else "") + f"-{ts}.json"
    path = events_dir / name
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    index_line = json.dumps(
        {
            "seq": seq,
            "file": name,
            "hook_event_name": event,
            "tool_name": tool,
            "sha256": digest,
            "captured_utc": ts,
        }
    )
    with open(events_dir / "index.jsonl", "a", encoding="utf-8") as fh:
        fh.write(index_line + "\n")
    return parsed, event, tool


def main() -> int:
    raw = sys.stdin.buffer.read()
    events_dir = _evidence_dir()
    parsed, event, tool = _capture(events_dir, raw)

    mode = os.environ.get("MNEME_PROBE_MODE", "log")
    if mode == "additional_context":
        if event == "PreToolUse" and tool == "apply_patch":
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "additionalContext": (
                                "[mneme-probe] NONBLOCKING_DIAGNOSTIC_1491"
                            ),
                        }
                    }
                )
            )
        return 0
    if mode == "deny_bash":
        if event == "PreToolUse" and tool == "Bash":
            reason = "M2a probe: deterministic deny of shell command"
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": reason,
                        }
                    }
                )
            )
        return 0
    if mode != "deny_apply_patch":
        return 0
    if event != "PreToolUse" or tool != "apply_patch":
        return 0

    shape = os.environ.get("MNEME_PROBE_DENY_SHAPE", "hookSpecificOutput")
    reason = "R0 probe: deterministic deny of apply_patch (test arm B)"
    if shape == "legacy":
        print(json.dumps({"decision": "block", "reason": reason}))
    elif shape == "exit2":
        sys.stderr.write(reason)
        return 2
    else:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": reason,
                    }
                }
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
