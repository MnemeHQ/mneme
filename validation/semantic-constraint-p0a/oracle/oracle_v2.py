"""Corrected synthetic oracle for ADR-001 (P0-A, charter D2), independent of Mneme.

Successor to validation/orchestrator-decision-sandbox/scripts/oracle.py, which
stays byte-identical as #570 evidence. Differences from v1:

- records the deadline actually passed to ``classify`` on each path, so a
  call-site override (case K) is observed even when the module constant is
  compliant; the deadline findings use that supplied value;
- records the module constant separately;
- records the timeout-path and normal-path results instead of a bare verdict;
- runs each fixture under an explicit environment probe (case S).

Output is an observation under stated conditions, never an architectural
label (charter section 5.1).

The oracle executes candidate source with ``exec``. It may only run the
frozen synthetic fixtures of this experiment: ``observe`` refuses any source
whose SHA-256 is not in the caller's allow-list of frozen digests. It must
never be pointed at proposed agent content.
"""

import hashlib
import math
import os
from contextlib import contextmanager

ORACLE_VERSION = "p0a-oracle-v2.0.0"
MAX_DEADLINE_S = 5.0
REQUEST = "synthetic request"
PRIMARY_ROUTE = "primary"


class UnfrozenSourceError(RuntimeError):
    """Raised when asked to execute source that is not a frozen fixture."""


def classify_deadline(value) -> str:
    """Classify a deadline value with the #570 oracle's rules."""
    numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not numeric or value <= 0 or math.isinf(value) or math.isnan(value):
        return "DISABLED"
    if value > MAX_DEADLINE_S:
        return "EXCEEDS_5S"
    return "WITHIN_BOUND"


def _describe(value) -> dict:
    return {"repr": repr(value), "type": type(value).__name__}


@contextmanager
def _probe_environ(env: dict):
    saved = {key: os.environ.get(key) for key in env}
    try:
        for key, value in env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _run_path(route, raise_timeout: bool) -> dict:
    calls = []

    def classify(*args, **kwargs):
        if len(args) > 1:
            calls.append(args[1])
        elif "deadline" in kwargs:
            calls.append(kwargs["deadline"])
        else:
            calls.append("<no deadline argument>")
        if raise_timeout:
            raise TimeoutError("synthetic deadline hit")
        return PRIMARY_ROUTE

    try:
        value = route(REQUEST, classify)
        result = {"kind": "returned", **_describe(value)}
    except Exception as e:  # noqa: BLE001 - an escaping exception is the observation
        value = None
        result = {"kind": "raised", "type": type(e).__name__}
    return {
        "classify_deadlines": [
            {**_describe(d), "classification": classify_deadline(d)} for d in calls
        ],
        "result": result,
        "_value": value,
    }


def observe(source: bytes, *, frozen_digests: set, env: dict) -> dict:
    """Execute one frozen fixture under ``env`` and return its observations."""
    digest = hashlib.sha256(source).hexdigest()
    if digest not in frozen_digests:
        raise UnfrozenSourceError(f"refusing to execute unfrozen source {digest}")

    observation = {
        "oracle_version": ORACLE_VERSION,
        "source_sha256": digest,
        "env": dict(sorted(env.items())),
    }
    namespace: dict = {}
    with _probe_environ(env):
        try:
            exec(compile(source.decode("utf-8"), "<frozen fixture>", "exec"), namespace)
            route = namespace["route"]
            fallback = namespace["FALLBACK_ROUTE"]
        except Exception as e:  # noqa: BLE001 - any load failure is the observation
            observation.update(
                load=f"LOAD_ERROR: {type(e).__name__}",
                findings=["LOAD_ERROR"],
                verdict="REJECT",
                violation_observed={"C1": False, "C2": False, "C3": False},
            )
            return observation
        normal = _run_path(route, raise_timeout=False)
        timeout = _run_path(route, raise_timeout=True)

    if "ROUTER_DEADLINE_S" in namespace:
        constant = namespace["ROUTER_DEADLINE_S"]
        module_constant = {
            "present": True,
            **_describe(constant),
            "classification": classify_deadline(constant),
        }
    else:
        module_constant = {"present": False}

    supplied = normal["classify_deadlines"] + timeout["classify_deadlines"]
    if supplied:
        basis = "classify_call"
        classes = {d["classification"] for d in supplied}
    elif module_constant["present"]:
        basis = "module_constant (classify not called)"
        classes = {module_constant["classification"]}
    else:
        basis = "none observed"
        classes = set()

    findings = []
    if "DISABLED" in classes:
        findings.append("C1_DISABLED")
    if "EXCEEDS_5S" in classes:
        findings.append("C2_DEADLINE_EXCEEDS_5S")
    timeout_returned_fallback = (
        timeout["result"]["kind"] == "returned" and timeout["_value"] == fallback
    )
    if not timeout_returned_fallback:
        findings.append("C3_NO_FALLBACK")
    if not (normal["result"]["kind"] == "returned" and normal["_value"] == PRIMARY_ROUTE):
        findings.append("ROUTE_BROKEN")

    for path in (normal, timeout):
        del path["_value"]
    observation.update(
        load="OK",
        fallback_symbol=_describe(fallback),
        module_constant=module_constant,
        deadline_supplied_to_classify=sorted({d["repr"] for d in supplied}),
        deadline_basis=basis,
        normal_path=normal,
        timeout_path={**timeout, "returned_fallback": timeout_returned_fallback},
        findings=findings,
        verdict="ACCEPT" if not findings else "REJECT",
        violation_observed={
            "C1": "C1_DISABLED" in findings,
            "C2": "C2_DEADLINE_EXCEEDS_5S" in findings,
            "C3": "C3_NO_FALLBACK" in findings,
        },
    )
    return observation
