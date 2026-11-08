"""Synthetic routing validator (orchestrator decision sandbox)."""

ROUTER_DEADLINE_S = 5.0
FALLBACK_ROUTE = "safe-default"


def route(request, classify):
        return classify(request, ROUTER_DEADLINE_S)
