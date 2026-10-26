"""CM-01 B0-A provider calibration: frozen request templates (A2) and calibration tasks.

Calibration only. These tasks run over the frozen B0-M fixture as a labeled
regression input; they are not B0-A pilot or confirmatory scenarios and must
never be reused as such. No value here is benchmark evidence.
"""

from __future__ import annotations

import copy
from typing import Any

MODEL = "claude-sonnet-5-5"
API_URL = "https://api.anthropic.com/v1/messages"
COUNT_TOKENS_URL = "https://api.anthropic.com/v1/messages/count_tokens"
# Taken from the official Messages API example (re-read 2026-10-26); recorded per
# response under K7. Change only by review, never mid-run.
ANTHROPIC_VERSION = "2026-10-21"

# Calibration-only output ceiling. It bounds K9 measurement and the budget guard;
# the benchmark ceiling is derived from K9 under the approved 4x rule.
CALIBRATION_MAX_TOKENS = 16000

# Ratified A2 configuration (decision pass, 2026-10-26). Sampling parameters are
# deliberately absent: Sonnet 5.5 rejects temperature/top_p/top_k with HTTP 400.
A2_BASE: dict[str, Any] = {
    "model": MODEL,
    "max_tokens": CALIBRATION_MAX_TOKENS,
    "thinking": {"type": "adaptive", "display": "omitted"},
    "output_config": {"effort": "high"},
    "speed": "standard",
    "service_tier": "standard_only",
}

SYSTEM_PROMPT = (
    "You answer read-only questions about an architecture decision index. "
    "Use the available tools to retrieve the data you need. When you have it, "
    "reply with only the final JSON answer that matches the required schema, "
    "with no other text."
)

# The four ADR-027 read methods. decision.propose and decision.propose_batch are
# never exposed. Anthropic tool names must match ^[a-zA-Z0-9_-]{1,64}$, so the
# dotted MCP names are mapped one-to-one (a D1-C harness item).
READ_TOOLS = (
    "decision.get",
    "decision.search",
    "decision.applicable_to",
    "decision.trace",
)
TOOL_NAME_TO_MCP = {name.replace(".", "_"): name for name in READ_TOOLS}

CODEMODE_TOOL_NAME = "codemode"

# Calibration price table, USD per million tokens, claude-sonnet-5-5 model page
# (read 2026-10-26). Used only by the budget guard.
PRICE_PER_MTOK = {
    "input": 2.00,
    "cache_write_5m": 2.50,
    "cache_write_1h": 4.00,
    "cache_read": 0.10,
    "output": 10.00,
}
WORST_CASE_INPUT_PRICE = max(
    PRICE_PER_MTOK["input"],
    PRICE_PER_MTOK["cache_write_5m"],
    PRICE_PER_MTOK["cache_write_1h"],
)

# Answer schemas shaped after the merged #662 section 3.1 proposals for T5, T6
# and T8. Structured outputs require additionalProperties: false on every
# object, so #662's open-ended rule_payload/applicability objects are given
# explicit shapes here; whether the API accepts these shapes is part of K4.
_RULE = {
    "type": "object",
    "properties": {
        "rule_id": {"type": "string"},
        "rule_payload": {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        "applicability": {
            "type": "object",
            "properties": {
                "include_paths": {"type": "array", "items": {"type": "string"}},
                "exclude_paths": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
        },
    },
    "required": ["rule_id", "rule_payload", "applicability"],
    "additionalProperties": False,
}

SCHEMAS: dict[str, dict[str, Any]] = {
    "T5": {
        "type": "object",
        "properties": {
            "decision_id": {"type": "string"},
            "version_id": {"type": "string"},
            "content_digest": {"type": "string"},
            "derived_rule_ids": {"type": "array", "items": {"type": "string"}},
            "derived_rules": {"type": "array", "items": _RULE},
            "missing_links": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "decision_id",
            "version_id",
            "content_digest",
            "derived_rule_ids",
            "derived_rules",
            "missing_links",
        ],
        "additionalProperties": False,
    },
    "T6": {
        "type": "object",
        "properties": {
            "canonical_ids": {"type": "array", "items": {"type": "string"}},
            "count": {"type": "integer"},
        },
        "required": ["canonical_ids", "count"],
        "additionalProperties": False,
    },
    "T8": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "decision_id": {"type": "string"},
                        "version_id": {"type": "string"},
                        "content_digest": {"type": "string"},
                        "derived_rules": {"type": "array", "items": _RULE},
                    },
                    "required": [
                        "decision_id",
                        "version_id",
                        "content_digest",
                        "derived_rules",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    },
}

# Calibration tasks over the B0-M fixture. ``reference_select`` names one genuine
# MCP selection call; the harness then traces every active canonical match. That
# reference data is used only to precompute the fixed Code Mode stub result.
# Neither arm is required to follow it.
TASKS: dict[str, dict[str, Any]] = {
    "CAL-T5": {
        "schema": "T5",
        "prompt": (
            "Find the single active canonical decision whose text contains the "
            "marker string 'marker_adr-b0-005'. Return its decision_id, "
            "version_id, content_digest, derived_rule_ids, its derived rules "
            "(rule_id, rule_payload, applicability) and its missing_links, "
            "exactly as the decision index reports them."
        ),
        "reference_select": (
            "decision.search",
            {"query": "marker_adr-b0-005", "canonical_lifecycle_status": "active"},
        ),
    },
    "CAL-T6": {
        "schema": "T6",
        "prompt": (
            "Consider the active canonical decisions applicable to the context "
            "'storage'. Return, sorted ascending, the decision IDs of those that "
            "have a derived rule whose applicability include_paths contains "
            "exactly the path 'src/calibration/none.py', together with their count."
        ),
        "reference_select": ("decision.applicable_to", {"context": ["storage"]}),
    },
    "CAL-T8": {
        "schema": "T8",
        "prompt": (
            "For every active canonical decision applicable to the context "
            "'routing', return an item with its decision_id, version_id, "
            "content_digest and its derived rules (rule_id, rule_payload, "
            "applicability). Sort the items by decision_id."
        ),
        "reference_select": ("decision.applicable_to", {"context": ["routing"]}),
    },
}


def direct_tools(mcp_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map the genuine MCP inventory to the four Anthropic read tools.

    Descriptions and input schemas are passed through verbatim from the pinned
    upstream server; only the name is normalized.
    """
    by_name = {tool["name"]: tool for tool in mcp_tools}
    tools = []
    for mcp_name in READ_TOOLS:
        upstream = by_name[mcp_name]
        tools.append({
            "name": mcp_name.replace(".", "_"),
            "description": upstream["description"],
            "input_schema": upstream["inputSchema"],
        })
    return tools


def codemode_tool() -> dict[str, Any]:
    """Calibration stand-in for the Code Mode tool.

    The production Code Mode description comes from the pinned F1 adapter; this
    stand-in only exercises one-tool loops, structured outputs and grammar
    caching for a one-tool set. Submitted code is never executed.
    """
    return {
        "name": CODEMODE_TOOL_NAME,
        "description": (
            "Run a short JavaScript async function body and return its result. "
            "Inside the code you may await codemode.decision_get({record_id}), "
            "codemode.decision_search({query, canonical_lifecycle_status}), "
            "codemode.decision_applicable_to({context, paths}) and "
            "codemode.decision_trace({record_id}). These are read-only. Use "
            "`return` to give back a JSON-serializable value."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "JavaScript function body."}},
            "required": ["code"],
            "additionalProperties": False,
        },
    }


def build_request(
    *,
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    schema_key: str | None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render one Messages API body from the frozen A2 base.

    ``schema_key`` enables structured outputs with that answer schema.
    ``overrides`` is used only by the K1 error probes.
    """
    body = copy.deepcopy(A2_BASE)
    body["system"] = SYSTEM_PROMPT
    body["tools"] = copy.deepcopy(tools)
    body["tool_choice"] = {"type": "auto"}
    body["messages"] = copy.deepcopy(messages)
    if schema_key is not None:
        body["output_config"]["format"] = {
            "type": "json_schema",
            "schema": copy.deepcopy(SCHEMAS[schema_key]),
        }
    for key, value in (overrides or {}).items():
        if value is None:
            body.pop(key, None)
        else:
            body[key] = copy.deepcopy(value)
    return body
