"""Transparent pass-through observers for the hook's own calls (T-08 G3).

Charter docs/plans/2026-11-10-t08-g3-host-boundary-live-charter.md §6 items 2
and 5, §8. ``hookwrap_c3.py`` replaces two module attributes of the hook with
these observers before it runs the hook:

- ``find_memory``: the memory the hook actually selected (item 2);
- ``_invoke_check``: the live checker's result (item 5).

Each observer calls the real function with the original positional and
keyword arguments, returns its result unchanged (the same object), and records
any exception before re-raising that same exception. The wrapper makes no
lookup of its own. Only allowlisted payload fields are recorded: never the
proposed source, triggers or rule text.

``observe`` has no I/O and imports nothing from Mneme, so
``selftest/test_observers.py`` can check the pass-through property directly.
"""
from __future__ import annotations

import json
from typing import Any, Callable

# mneme.check/v1 fields kept from the live payload (charter §6 item 5).
PAYLOAD_FIELDS = ("verdict", "evaluation_complete", "mode")


def observe(real: Callable, sink: list, describe: Callable[[tuple, dict, Any], dict]) -> Callable:
    """Wrap ``real``: append one record per call to ``sink``; change nothing.

    ``describe(args, kwargs, result)`` builds the record for a returned call.
    A failure inside ``describe`` is recorded as ``observer_error`` and never
    reaches the caller.
    """

    def observer(*args, **kwargs):
        try:
            result = real(*args, **kwargs)
        except BaseException as exc:
            sink.append({"exception": f"{type(exc).__name__}: {exc}", "returned": None})
            raise
        try:
            record = describe(args, kwargs, result)
        except Exception as exc:  # observation must never alter the call
            record = {"observer_error": f"{type(exc).__name__}: {exc}"}
        sink.append(record)
        return result

    observer.__wrapped__ = real
    return observer


def describe_find_memory(args: tuple, kwargs: dict, result: Any) -> dict:
    start = args[0] if args else kwargs.get("start")
    return {"start": None if start is None else str(start),
            "returned": None if result is None else str(result),
            "exception": None}


def describe_invoke_check(args: tuple, kwargs: dict, result: Any) -> dict:
    """The hook's ``_invoke_check(memory, rel_label, target_path, ...)``."""
    memory = args[0] if args else kwargs.get("memory")
    target = args[2] if len(args) > 2 else kwargs.get("target_path")
    record: dict = {"memory": None if memory is None else str(memory),
                    "target_path": None if target is None else str(target),
                    "exception": None}
    if result is None:  # the hook's own "could not launch / timed out" path
        record.update(returned=None, payload="not_observed")
        return record
    record["returncode"] = getattr(result, "returncode", None)
    try:
        payload = json.loads(getattr(result, "stdout", "") or "")
    except (TypeError, ValueError):
        payload = None
    if not isinstance(payload, dict):
        record["payload"] = "not_observed"
        return record
    kept = {k: payload.get(k) for k in PAYLOAD_FIELDS if k in payload}
    kept["schema"] = payload.get("schema")
    kept["decision_ids"] = sorted({
        v["decision_id"] for v in payload.get("violations") or []
        if isinstance(v, dict) and isinstance(v.get("decision_id"), str)})
    record["payload"] = kept
    return record
