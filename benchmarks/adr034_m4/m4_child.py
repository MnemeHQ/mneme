#!/usr/bin/env python3
"""Child-process entry point for the ADR-034 M4 scoring harness.

The harness never imports ``mneme`` itself. Every call into the build under
test (and into the gate-12 old reader) runs in a child interpreter through
this file, started as ``<python> -P m4_child.py <command> ...`` with a
scrubbed environment, so that the code that is hashed, the code that is
checked and the code that validates trust are one import of one tree.

Commands:

- ``cli <args...>``: run the shipped ``mneme.cli`` exactly as
  ``python -m mneme.cli <args...>`` would (``runpy`` with ``alter_sys``);
- ``probe``: report what ``import mneme`` resolves to, as JSON;
- ``trust <requests.json>``: apply the shipped Claude Code hook trust
  validator (``assess_verdict``, strict mode) to captured check results;
- ``identity <requests.json>``: compute ADR-030 rule ids with the shipped
  ``rule_identity`` module (ADR-034 §5 golden vectors).

Network access is denied in every child by an audit hook installed before
anything else is imported: name resolution and connections to anything but
loopback raise ``PermissionError``, which surfaces as an operational failure.
"""
from __future__ import annotations

import json
import sys

_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


def _host(value):
    if isinstance(value, tuple) and value:
        value = value[0]
    if isinstance(value, bytes):
        value = value.decode("ascii", "replace")
    return value


def _deny_network(event, args):
    if event == "socket.getaddrinfo":
        host = _host(args[0]) if args else None
        if host is not None and host not in _LOOPBACK:
            raise PermissionError(f"M4 harness: network access denied ({event} {host!r})")
    elif event in ("socket.connect", "socket.sendto", "socket.sendmsg"):
        host = _host(args[1]) if len(args) > 1 else None
        if host is not None and host not in _LOOPBACK:
            raise PermissionError(f"M4 harness: network access denied ({event} {host!r})")


sys.addaudithook(_deny_network)


def _cli(argv):
    import runpy

    sys.argv = ["mneme", *argv]
    runpy.run_module("mneme.cli", run_name="__main__", alter_sys=True)
    return 0


def _probe():
    import importlib.util
    import platform
    from pathlib import Path

    import mneme

    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            dist_version = version("mneme-hq")
        except PackageNotFoundError:
            dist_version = None
    except ImportError:  # pragma: no cover - stdlib on every supported Python
        dist_version = None
    mneme_file = Path(mneme.__file__).resolve()
    print(json.dumps({
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "mneme_file": str(mneme_file),
        "mneme_dir": str(mneme_file.parent),
        "mneme_version": getattr(mneme, "__version__", None),
        "distribution_version": dist_version,
        "numeric_rule_module": importlib.util.find_spec("mneme.numeric_rule") is not None,
        "sys_path": list(sys.path),
    }, sort_keys=True))
    return 0


def _read_requests(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _trust(path):
    from mneme.integrations.claude_code.hook import assess_verdict

    results = []
    for request in _read_requests(path):
        assessment = assess_verdict(request["stdout"], request["returncode"], "strict")
        results.append({
            "trusted": assessment.payload is not None,
            "problem": assessment.problem,
            "inconsistent": assessment.inconsistent,
        })
    print(json.dumps(results, sort_keys=True))
    return 0


def _identity(path):
    from mneme.rule_identity import canonical_json, rule_id_of

    results = []
    for request in _read_requests(path):
        value = request["value"]
        if request.get("canonical") is not None:
            value = canonical_json(request["canonical"])
        results.append({
            "value": value,
            "rule_id": rule_id_of(
                request["decision_id"],
                request["rule_type"],
                value,
                request["applicability"],
            ),
        })
    print(json.dumps(results, sort_keys=True))
    return 0


def main(argv):
    if not argv:
        print("usage: m4_child.py {cli,probe,trust,identity} ...", file=sys.stderr)
        return 64
    command, rest = argv[0], argv[1:]
    if command == "cli":
        return _cli(rest)
    if command == "probe" and not rest:
        return _probe()
    if command == "trust" and len(rest) == 1:
        return _trust(rest[0])
    if command == "identity" and len(rest) == 1:
        return _identity(rest[0])
    print(f"m4_child.py: bad command {argv!r}", file=sys.stderr)
    return 64


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
