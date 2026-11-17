"""Runs inside a pinned build's interpreter (``python -I pinned_child.py``).

``g6``: R2 §5 G6 steps 2-4 are computed by the pinned build's own
``relevant_enforcement_per_rule()``, ``relevant_enforcement_observed()``
and ``recorded_evaluation_complete()`` with the pinned host identity.
``env``: identity of the installed package, for the scoring report.
"""

import hashlib
import json
import sys
from pathlib import Path


def _env() -> dict:
    import mneme

    package = Path(mneme.__file__).resolve().parent
    files = sorted(p for p in package.rglob("*.py") if p.is_file())
    manifest = "".join(
        f"{p.relative_to(package).as_posix()}:{hashlib.sha256(p.read_bytes()).hexdigest()}\n"
        for p in files
    )
    return {
        "python": sys.version.split()[0],
        "mneme_version": mneme.__version__,
        "mneme_package": str(package),
        "source_files": len(files),
        "source_manifest_sha256": hashlib.sha256(manifest.encode("utf-8")).hexdigest(),
    }


def _g6(request: dict) -> dict:
    from mneme.integrations.claude_code import hook

    record, host = request["record"], tuple(request["pinned_host"])
    return {
        "per_rule": hook.relevant_enforcement_per_rule(record, host),
        "event": hook.relevant_enforcement_observed(record, host),
        "complete": hook.recorded_evaluation_complete(record),
    }


def main() -> int:
    command = sys.argv[1]
    if command == "env":
        out = _env()
    elif command == "g6":
        out = _g6(json.loads(sys.stdin.read()))
    else:
        raise SystemExit(f"unknown command {command!r}")
    sys.stdout.write(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
