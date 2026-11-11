"""Self-test: the G3 observers are pass-through (charter §8). NOT live evidence.

usage: test_observers.py <mneme-src>

1. ``observe`` returns the real result object unchanged, passes positional and
   keyword arguments through, and re-raises the very exception object.
2. With the pinned hook, ``hook.main`` gives the same exit code, stdout and
   stderr with and without the observers on ``find_memory`` and
   ``_invoke_check``, for a violating and a compliant Edit, and the observers
   record the hook's own selection and checker result.
Prints ``ok`` lines and exits 0, or ``FAIL`` lines and exits 1.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from observe import describe_find_memory, describe_invoke_check, observe  # noqa: E402

fail = 0


def report(ok: bool, what: str) -> None:
    global fail
    print(("ok   " if ok else "FAIL ") + what)
    fail |= not ok


def unit() -> None:
    sentinel = object()
    seen = []

    def real(a, b=None, *, transport="subprocess", carrier=None):
        seen.append((a, b, transport, carrier))
        return sentinel

    sink: list = []
    wrapped = observe(real, sink, lambda args, kwargs, result: {"args": len(args)})
    got = wrapped(1, 2, transport="inprocess", carrier=b"x")
    report(got is sentinel and seen == [(1, 2, "inprocess", b"x")] and sink == [{"args": 2}],
           "observe: same result object; args and kwargs passed through")

    boom = RuntimeError("boom")

    def raising(*_a, **_k):
        raise boom

    sink = []
    try:
        observe(raising, sink, describe_find_memory)("x")
        report(False, "observe: exception re-raised")
    except RuntimeError as exc:
        report(exc is boom and sink == [{"exception": "RuntimeError: boom", "returned": None}],
               "observe: the same exception object re-raised and recorded")

    sink = []
    out = observe(lambda: 7, sink, lambda *_: 1 / 0)()
    report(out == 7 and "observer_error" in sink[0],
           "observe: a describe failure is recorded and never reaches the caller")


def hook_parity(src: str) -> None:
    sys.path.insert(0, src)
    from mneme.cli import main as cli
    from mneme.integrations.claude_code import hook

    for key in ("MNEME_MEMORY", "MNEME_HOOK_MODE", "CLAUDE_PLUGIN_OPTION_MODE",
                "MNEME_HOOK_CHECK_TRANSPORT"):
        os.environ.pop(key, None)
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        app = repo / "app.py"
        app.write_text("import os\n\n\ndef handler():\n    return 1\n", encoding="utf-8")
        memory = repo / ".mneme" / "project_memory.json"
        quiet = io.StringIO()
        old_stdout, sys.stdout = sys.stdout, quiet
        try:
            cli(["init", "--path", str(memory)])
            cli(["add_decision", "--memory", str(memory), "--id", "C3-DEC",
                 "--decision", "Do not use psycopg2 in the service layer",
                 "--anti-pattern", "psycopg2"])
        finally:
            sys.stdout = old_stdout

        def envelope(old: str, new: str) -> str:
            return json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Edit",
                               "tool_use_id": "toolu_selftest", "cwd": str(repo),
                               "tool_input": {"file_path": str(app), "old_string": old,
                                              "new_string": new}})

        def run(env: str) -> tuple:
            err, out = io.StringIO(), io.StringIO()
            rc = hook.main(stdin=io.StringIO(env), stderr=err, stdout=out)
            return rc, out.getvalue(), err.getvalue()

        real_find, real_check = hook.find_memory, hook._invoke_check
        for name, env, want_rc in (("violating", envelope("import os", "import psycopg2"), 2),
                                   ("compliant", envelope("    return 1", "    return 2"), 0)):
            bare = run(env)
            finds, checks = [], []
            hook.find_memory = observe(real_find, finds, describe_find_memory)
            hook._invoke_check = observe(real_check, checks, describe_invoke_check)
            try:
                observed = run(env)
            finally:
                hook.find_memory, hook._invoke_check = real_find, real_check
            report(bare == observed and bare[0] == want_rc,
                   f"hook parity ({name} Edit): exit {bare[0]}, stdout and stderr identical "
                   "with and without observers")
            selected = [c.get("returned") for c in finds]
            payload = checks[-1].get("payload") if checks else None
            want = "FAIL" if want_rc else "PASS"
            report(len(finds) == 1 and Path(selected[0]).resolve() == memory.resolve()
                   and isinstance(payload, dict) and payload.get("verdict") == want
                   and payload.get("evaluation_complete") is True
                   and (payload.get("decision_ids") == (["C3-DEC"] if want_rc else [])),
                   f"observers recorded the hook's own selection and {want} payload ({name})")


if __name__ == "__main__":
    unit()
    hook_parity(sys.argv[1])
    print("OBSERVERS OK" if not fail else "OBSERVERS FAILED")
    raise SystemExit(1 if fail else 0)
