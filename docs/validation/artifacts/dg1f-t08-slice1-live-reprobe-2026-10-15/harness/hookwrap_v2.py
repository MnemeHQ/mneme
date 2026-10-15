"""Observation wrapper (v2) around the unmodified Mneme Claude Code hook.

v1 logged ``find_memory(payload cwd)``, which is no longer what the hook uses
after T-08 slice 1. v2 records the hook's *actual* ``find_memory`` calls
(start directory and returned memory) through a pass-through shim that
returns the real result unchanged, so the decision is not altered.
"""
import io
import json
import os
import sys
import time
from pathlib import Path

SRC = os.environ["T08_MNEME_SRC"]
LOG = os.environ["T08_LOG"]
sys.path.insert(0, SRC)

from mneme.integrations.claude_code import hook  # noqa: E402

_real_find_memory = hook.find_memory
calls = []


def _recording_find_memory(start):
    result = _real_find_memory(start)
    calls.append({"start": str(start), "returned": str(result) if result else None})
    return result


hook.find_memory = _recording_find_memory

raw = sys.stdin.read()
try:
    env = json.loads(raw)
except json.JSONDecodeError:
    env = {}
ti = env.get("tool_input") or {}
err, out = io.StringIO(), io.StringIO()
rc = hook.main(stdin=io.StringIO(raw), stderr=err, stdout=out)
with open(LOG, "a", encoding="utf-8") as f:
    f.write(json.dumps({
        "t": time.time(),
        "wrapper": "hookwrap_v2",
        "hook_event_name": env.get("hook_event_name"),
        "tool_name": env.get("tool_name"),
        "payload_cwd": env.get("cwd"),
        "file_path": ti.get("file_path"),
        "command": ti.get("command"),
        "MNEME_MEMORY": os.environ.get("MNEME_MEMORY"),
        "find_memory_calls": calls,
        "selected_memory": calls[-1]["returned"] if calls else None,
        "hook_module": hook.__file__,
        "exit": rc,
        "stderr": err.getvalue(),
        "stdout": out.getvalue(),
    }) + "\n")
sys.stdout.write(out.getvalue())
sys.stderr.write(err.getvalue())
sys.exit(rc)
