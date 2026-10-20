"""Functional architectural oracle for ADR-001, independent of Mneme.

Judges a candidate router source against C1/C2/C3 by executing it in an
isolated namespace. The oracle never reads Mneme output; it is the
"expected architectural result" that machine verdicts are compared against.
"""

import math
from dataclasses import dataclass, field

MAX_DEADLINE_S = 5.0


@dataclass(frozen=True)
class OracleResult:
    accept: bool
    failures: list = field(default_factory=list)


def _primary(request, deadline):
    return "primary"


def _timeout(request, deadline):
    raise TimeoutError("synthetic deadline hit")


def evaluate(router_source: str) -> OracleResult:
    namespace: dict = {}
    try:
        exec(compile(router_source, "<candidate router>", "exec"), namespace)
        deadline = namespace["ROUTER_DEADLINE_S"]
        fallback = namespace["FALLBACK_ROUTE"]
        route = namespace["route"]
    except Exception as e:  # noqa: BLE001 - any load failure is a rejection
        return OracleResult(False, [f"LOAD_ERROR: {type(e).__name__}"])

    failures = []
    numeric = isinstance(deadline, (int, float)) and not isinstance(deadline, bool)
    if not numeric or deadline <= 0 or math.isinf(deadline) or math.isnan(deadline):
        failures.append("C1_DISABLED")
    elif deadline > MAX_DEADLINE_S:
        failures.append("C2_DEADLINE_EXCEEDS_5S")

    try:
        on_timeout = route("synthetic request", _timeout)
    except Exception:  # noqa: BLE001 - an escaping timeout means no fallback
        on_timeout = None
    if on_timeout != fallback:
        failures.append("C3_NO_FALLBACK")

    try:
        normal = route("synthetic request", _primary)
    except Exception:  # noqa: BLE001
        normal = None
    if normal != "primary":
        failures.append("ROUTE_BROKEN")

    return OracleResult(not failures, failures)
