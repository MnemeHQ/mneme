"""Observation shim for the ADR-034 G2-1 scoring harness.

The harness puts this directory on ``PYTHONPATH`` for every hook process it
starts, for both builds alike. The Claude Code hook passes its own
environment on to the ``python -m mneme check`` child it launches
(``_child_env`` prepends the package root and keeps the rest of
``PYTHONPATH``), so this module is imported by that child too.

It acts only in a process started as ``python -m mneme check ...``. There it
records, as one JSON line appended to ``MNEME_G2H_OBSERVE_LOG``:

- the argument vector after ``-m mneme check``, with the carrier file path
  replaced by ``<CARRIER>`` (the hook's temporary file name is random);
- which input flag carried the content, and the SHA-256 and size of the
  carrier bytes as the child found them on disk;
- the exact text the child wrote to ``sys.stdout`` (the check payload).

It never writes to ``stdout`` or ``stderr``, never changes what the child
writes there, and never changes its exit status: every write is passed
through unchanged to the original stream, and every shim error is swallowed
and recorded in the log line instead. Outside that one process shape it does
nothing.
"""
import os
import sys

_LOG_ENV = "MNEME_G2H_OBSERVE_LOG"
_INPUT_FLAGS = ("--proposed-new-file", "--input", "--source-file")


class _Tee:
    """Pass every write through to ``inner`` and keep a copy of the text."""

    def __init__(self, inner, sink):
        self._g2h_inner = inner
        self._g2h_sink = sink

    def write(self, text):
        written = self._g2h_inner.write(text)
        try:
            self._g2h_sink.append(text)
        except Exception:  # pragma: no cover - list.append does not fail
            pass
        return written

    def __getattr__(self, name):
        return getattr(self._g2h_inner, name)


def _install():
    log_path = os.environ.get(_LOG_ENV)
    if not log_path:
        return
    argv = list(getattr(sys, "orig_argv", None) or [])
    try:
        at = argv.index("-m")
    except ValueError:
        return
    if argv[at + 1:at + 3] != ["mneme", "check"]:
        return

    import atexit
    import hashlib
    import json

    tail = argv[at + 3:]
    record = {"argv": list(tail), "input_flag": None, "carrier_sha256": None,
              "carrier_size": None, "shim_errors": []}
    for flag in _INPUT_FLAGS:
        if flag in tail:
            index = tail.index(flag)
            record["input_flag"] = flag
            if index + 1 < len(tail):
                path = tail[index + 1]
                record["argv"][index + 1] = "<CARRIER>"
                try:
                    with open(path, "rb") as handle:
                        data = handle.read()
                    record["carrier_sha256"] = hashlib.sha256(data).hexdigest()
                    record["carrier_size"] = len(data)
                except Exception as exc:
                    record["shim_errors"].append(f"carrier: {type(exc).__name__}")
            break
    captured = []
    try:
        sys.stdout = _Tee(sys.stdout, captured)
    except Exception as exc:  # pragma: no cover - defensive
        record["shim_errors"].append(f"tee: {type(exc).__name__}")

    def _flush():
        record["stdout"] = "".join(captured)
        line = json.dumps(record, sort_keys=True, ensure_ascii=True)
        try:
            with open(log_path, "a", encoding="ascii", newline="\n") as handle:
                handle.write(line + "\n")
        except Exception:
            pass

    atexit.register(_flush)


try:
    _install()
except Exception:  # never affect the observed process
    pass
