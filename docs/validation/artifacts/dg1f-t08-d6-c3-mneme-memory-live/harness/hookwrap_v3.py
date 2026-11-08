"""Observation wrapper (v3) around the unmodified Mneme Claude Code hook.

v3 = #518's hookwrap_v2 plus the hook process's own environment view, which
D6 needs to tell which channel delivered ``MNEME_MEMORY``. It still records the
hook's *actual* ``find_memory`` calls through a pass-through shim that returns
the real result unchanged, and relays the hook's exit code, stdout and stderr
unchanged, so the decision is not altered.

Credential safety: values are logged only for the allowlisted keys below and
``CLAUDE_PROJECT_DIR``. Any other ``MNEME_*`` or ``CLAUDE*`` key is logged by
name only. Nothing else from the environment is logged.

Fail-safe: once the hook has returned, its exit code, stdout and stderr are
relayed whatever happens to the observation log. A logging failure is written
to a sidecar ``<log>.wrapper-errors`` file, never to the hook's streams. If the
wrapper cannot even run the hook (harness defect), it exits 2 with a
``t08-harness:`` message so the defect blocks visibly instead of failing open.
"""
import io
import json
import os
import sys
import time
import traceback

MNEME_VALUE_ALLOWLIST = ("MNEME_MEMORY", "MNEME_HOOK_MODE")

try:
    SRC = os.environ["T08_MNEME_SRC"]
    LOG = os.environ["T08_LOG"]
    sys.path.insert(0, SRC)
    from mneme.integrations.claude_code import hook  # noqa: E402
except Exception:  # harness defect: fail closed and say so
    sys.stderr.write("t08-harness: wrapper could not load the hook:\n" + traceback.format_exc())
    sys.exit(2)

_real_find_memory = hook.find_memory
calls = []


def _recording_find_memory(start):
    result = _real_find_memory(start)
    calls.append({"start": str(start), "returned": str(result) if result else None})
    return result


hook.find_memory = _recording_find_memory


def _env_view():
    mneme_keys = sorted(k for k in os.environ if k.upper().startswith("MNEME_"))
    mem = os.environ.get("MNEME_MEMORY")
    return {
        "MNEME_present": mneme_keys,
        "MNEME_values": {k: os.environ[k] for k in mneme_keys if k in MNEME_VALUE_ALLOWLIST},
        "MNEME_MEMORY_is_file": os.path.isfile(mem) if mem else None,
        "CLAUDE_PROJECT_DIR": os.environ.get("CLAUDE_PROJECT_DIR"),
        "CLAUDE_keys": sorted(k for k in os.environ if k.upper().startswith("CLAUDE")),
        "process_cwd": os.getcwd(),
        "pid": os.getpid(),
        "ppid": os.getppid(),
    }


try:
    env_view = _env_view()
except Exception:
    env_view = {"error": traceback.format_exc()}

raw = sys.stdin.read()
err, out = io.StringIO(), io.StringIO()
rc = hook.main(stdin=io.StringIO(raw), stderr=err, stdout=out)

try:
    try:
        env = json.loads(raw)
    except json.JSONDecodeError:
        env = {}
    ti = env.get("tool_input") or {}
    record = json.dumps({
        "t": time.time(),
        "wrapper": "hookwrap_v3",
        "hook_event_name": env.get("hook_event_name"),
        "tool_name": env.get("tool_name"),
        "tool_use_id": env.get("tool_use_id"),
        "session_id": env.get("session_id"),
        "payload_cwd": env.get("cwd"),
        "file_path": ti.get("file_path"),
        "command": ti.get("command"),
        "MNEME_MEMORY": os.environ.get("MNEME_MEMORY"),
        "hook_env_view": env_view,
        "find_memory_calls": calls,
        "selected_memory": calls[-1]["returned"] if calls else None,
        "hook_module": hook.__file__,
        "exit": rc,
        "stderr": err.getvalue(),
        "stdout": out.getvalue(),
    })
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(record + "\n")
except Exception:
    try:
        with open(LOG + ".wrapper-errors", "a", encoding="utf-8") as f:
            f.write(f"{time.time()} exit={rc}\n{traceback.format_exc()}\n")
    except Exception:
        pass
finally:
    sys.stdout.write(out.getvalue())
    sys.stderr.write(err.getvalue())
    sys.exit(rc)
