"""Observation wrapper around the unmodified Mneme Claude Code hook (T-08 live).

Pins the hook to the checkout in T08_MNEME_SRC, records what the host sent and
what the hook decided to T08_LOG (outside the governed repo), then relays the
hook's own stdout/stderr/exit code unchanged. It never alters the decision.
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

raw = sys.stdin.read()
try:
    env = json.loads(raw)
except json.JSONDecodeError:
    env = {}
ti = env.get("tool_input") or {}
cwd = env.get("cwd") or "."
selected = hook.find_memory(Path(cwd))
err, out = io.StringIO(), io.StringIO()
rc = hook.main(stdin=io.StringIO(raw), stderr=err, stdout=out)
with open(LOG, "a", encoding="utf-8") as f:
    f.write(json.dumps({
        "t": time.time(),
        "hook_event_name": env.get("hook_event_name"),
        "tool_name": env.get("tool_name"),
        "payload_cwd": env.get("cwd"),
        "file_path": ti.get("file_path"),
        "command": ti.get("command"),
        "MNEME_MEMORY": os.environ.get("MNEME_MEMORY"),
        "selected_memory": str(selected) if selected else None,
        "hook_module": hook.__file__,
        "exit": rc,
        "stderr": err.getvalue(),
        "stdout": out.getvalue(),
    }) + "\n")
sys.stdout.write(out.getvalue())
sys.stderr.write(err.getvalue())
sys.exit(rc)
