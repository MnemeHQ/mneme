"""Benchmark-only: run ``mneme check`` inside the hook's own interpreter.

The production hook launches ``sys.executable -m mneme check`` as a child
process. This module runs the same ``mneme.cli.main`` argv in-process and
returns the same ``CompletedProcess`` shape, so the hook's verdict handling
is unchanged. It holds no policy: timeouts and fail-open stay with the
caller. Selected only via ``MNEME_HOOK_CHECK_TRANSPORT=inprocess`` for the
issue #60 latency benchmark; not a supported user option.
"""
from __future__ import annotations

import contextlib
import io
import subprocess
import traceback
from typing import List


def run_check_inprocess(argv: List[str]) -> subprocess.CompletedProcess:
    """Run ``mneme <argv>`` in-process; never raises for CLI errors.

    ``argv`` is everything after ``-m mneme``. A ``SystemExit`` (argparse)
    becomes its exit code; any other exception becomes exit 1 with the
    traceback on stderr, matching what a crashing child would produce.
    """
    from mneme import cli  # lazy: the subprocess path never pays this import

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            returncode = cli.main(list(argv))
        except SystemExit as e:
            # Same mapping the interpreter applies at exit.
            if e.code is None:
                returncode = 0
            elif isinstance(e.code, int):
                returncode = e.code
            else:
                err.write(f"{e.code}\n")
                returncode = 1
        except Exception:
            err.write(traceback.format_exc())
            returncode = 1
    if returncode is None:  # `raise SystemExit(main())` with a None return exits 0
        returncode = 0
    return subprocess.CompletedProcess(
        args=list(argv), returncode=returncode, stdout=out.getvalue(), stderr=err.getvalue()
    )
