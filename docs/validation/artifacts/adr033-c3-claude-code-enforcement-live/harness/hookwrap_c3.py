"""Observation wrapper around the unmodified Mneme Claude Code hook (C3).

It records, without changing any decision:

- the hook's exit code, stdout and stderr (E3), relayed unchanged;
- each ``live_verifier`` result: authorization, reason, branch, tip, URL;
- each verifier Git call: argv with the endpoint, and the env key names
  (E4, the wrapper half; the OS capture is the other half).

Operator fault injection (scope Q3, accepted), selected by environment set by
the runner only:

- ``C3_STALL_CHECK_SECONDS``: the checker child command (``-m mneme check``)
  sleeps this long first, so the hook's own 10 s subprocess timeout fires
  for real (R-7). The hook and the checker are not modified.
- ``C3_STALL_HOOK_SECONDS``: the wrapper sleeps before running the hook, to
  exceed the host hook timeout (H-2).

Self-test only (``C3_SELFTEST=1``): the verifier may read a local ``file://``
remote. The runner refuses that flag unless ``claude`` is the self-test stub,
so it can never reach a live session.

Fail-safe: once the hook has returned, its exit code and streams are relayed
whatever happens to the log. If the wrapper cannot load the hook, it exits 2
with a ``c3-harness:`` message so a harness defect blocks visibly.
"""
import io
import json
import os
import subprocess
import sys
import time
import traceback

try:
    SRC = os.environ["C3_MNEME_SRC"]
    LOG = os.environ["C3_LOG"]
    sys.path.insert(0, SRC)
    from mneme import availability_authority as aa  # noqa: E402
    from mneme.integrations.claude_code import availability, hook  # noqa: E402
except Exception:  # harness defect: fail closed and say so
    sys.stderr.write("c3-harness: wrapper could not load the hook:\n" + traceback.format_exc())
    sys.exit(2)

verifications = []
git_calls = []

_real_live_verifier = availability.live_verifier
_real_run_git = aa._run_git
_real_subprocess_run = subprocess.run


def _recording_run_git(argv, *, env, cwd, timeout):
    git_calls.append({"argv": [str(a) for a in argv], "env_keys": sorted(env), "cwd": str(cwd)})
    return _real_run_git(argv, env=env, cwd=cwd, timeout=timeout)


def _recording_live_verifier(declaration):
    started = time.time()
    if os.environ.get("C3_SELFTEST") == "1":
        result = aa.verify(declaration.root, allow_file=True)
    else:
        result = _real_live_verifier(declaration)
    verifications.append({
        "authorization": result.authorization, "reason": result.reason,
        "detail": result.detail, "url": result.url, "branch": result.branch,
        "tip": result.tip, "seconds": round(time.time() - started, 3),
    })
    return result


def _stalling_run(command, *args, **kwargs):
    stall = os.environ.get("C3_STALL_CHECK_SECONDS")
    if stall and isinstance(command, list) and command[1:4] == ["-m", "mneme", "check"]:
        # Same interpreter, same `mneme check` arguments, preceded by a sleep.
        command = [command[0], "-c",
                   "import runpy, sys, time; time.sleep(float(sys.argv[1])); "
                   "sys.argv = ['mneme', 'check'] + sys.argv[2:]; "
                   "runpy.run_module('mneme', run_name='__main__')",
                   stall, *command[4:]]
    return _real_subprocess_run(command, *args, **kwargs)


aa._run_git = _recording_run_git
availability.live_verifier = _recording_live_verifier
subprocess.run = _stalling_run

hook_stall = os.environ.get("C3_STALL_HOOK_SECONDS")
if hook_stall:
    time.sleep(float(hook_stall))

raw = sys.stdin.read()
err, out = io.StringIO(), io.StringIO()
started = time.time()
rc = hook.main(stdin=io.StringIO(raw), stderr=err, stdout=out)

try:
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        envelope = {}
    tool_input = envelope.get("tool_input") or {}
    record = json.dumps({
        "t": started,
        "wrapper": "hookwrap_c3",
        "launch_id": os.environ.get("C3_LAUNCH_ID"),
        "hook_event_name": envelope.get("hook_event_name"),
        "tool_name": envelope.get("tool_name"),
        "tool_use_id": envelope.get("tool_use_id"),
        "file_path": tool_input.get("file_path"),
        "MNEME_MEMORY": os.environ.get("MNEME_MEMORY"),
        "proxy_env_present": sorted(k for k in os.environ
                                    if k.upper().endswith("_PROXY") or k.upper().startswith("GIT_")),
        "verifications": verifications,
        "verifier_git_calls": git_calls,
        "hook_module": hook.__file__,
        "seconds": round(time.time() - started, 3),
        "exit": rc,
        "stderr": err.getvalue(),
        "stdout": out.getvalue(),
    })
    with open(LOG, "a", encoding="utf-8") as handle:
        handle.write(record + "\n")
except Exception:
    try:
        with open(LOG + ".wrapper-errors", "a", encoding="utf-8") as handle:
            handle.write(f"{time.time()} exit={rc}\n{traceback.format_exc()}\n")
    except Exception:
        pass
finally:
    sys.stdout.write(out.getvalue())
    sys.stderr.write(err.getvalue())
    sys.exit(rc)
