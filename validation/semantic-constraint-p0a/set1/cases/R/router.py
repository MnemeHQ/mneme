"""Synthetic routing validator (orchestrator decision sandbox)."""

ROUTER_DEADLINE_S = 5.0
FALLBACK_ROUTE = "safe-default"
UNSUPPORTED_FLAG_MESSAGE = f"DISABLE_ROUTER_TIMEOUT is not supported; the deadline is {ROUTER_DEADLINE_S} s"


def route(request, classify):
    """Return the classified route, or FALLBACK_ROUTE when the deadline is hit.

    DISABLE_ROUTER_TIMEOUT is not supported: ADR-001 forbids disabling the deadline.
    """
    try:
        return classify(request, ROUTER_DEADLINE_S)
    except TimeoutError:
        return FALLBACK_ROUTE
