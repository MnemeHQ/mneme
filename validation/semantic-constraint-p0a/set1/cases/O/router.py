"""Synthetic routing validator (orchestrator decision sandbox)."""

ROUTER_DEADLINE_S = 5.0
FALLBACK_ROUTE = "safe-default"


def _fallback():
    return FALLBACK_ROUTE


def route(request, classify):
    """Return the classified route, or FALLBACK_ROUTE when the deadline is hit."""
    try:
        return classify(request, ROUTER_DEADLINE_S)
    except TimeoutError:
        return _fallback()
