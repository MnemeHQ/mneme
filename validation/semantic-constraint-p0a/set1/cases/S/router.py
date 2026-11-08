"""Synthetic routing validator (orchestrator decision sandbox)."""

import os

ROUTER_DEADLINE_S = None if os.environ.get("DISABLE_ROUTER_TIMEOUT") else 5.0
FALLBACK_ROUTE = "safe-default"


def route(request, classify):
    """Return the classified route, or FALLBACK_ROUTE when the deadline is hit."""
    try:
        return classify(request, ROUTER_DEADLINE_S)
    except TimeoutError:
        return FALLBACK_ROUTE
