"""Dry-run tests for the CM-01 B0-A calibration harness. No network, no API key.

Run from the repository root:
    python -m pytest validation/cm01/b0a-calibration/test_calibration.py -q
"""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import calibration as C
import templates as T

# ── A2 request template ───────────────────────────────────────────────────────


def test_a2_template_matches_ratified_configuration():
    body = T.build_request(tools=[T.codemode_tool()], messages=[{"role": "user", "content": "x"}], schema_key="T5")
    assert body["model"] == "claude-sonnet-5-5"
    assert body["thinking"] == {"type": "adaptive", "display": "omitted"}
    assert body["output_config"]["effort"] == "high"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["speed"] == "standard"
    assert body["service_tier"] == "standard_only"
    assert body["tool_choice"] == {"type": "auto"}
    for forbidden in ("temperature", "top_p", "top_k", "stream"):
        assert forbidden not in body


def test_template_without_schema_has_no_format():
    body = T.build_request(tools=[], messages=[], schema_key=None)
    assert "format" not in body["output_config"]


def test_base_template_is_not_mutated_by_overrides():
    T.build_request(tools=[], messages=[], schema_key="T6", overrides={"temperature": 0.5})
    assert "format" not in T.A2_BASE["output_config"]
    assert "temperature" not in T.A2_BASE


def test_structured_output_schemas_are_closed():
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for schema in T.SCHEMAS.values():
        walk(schema)


# ── Tool exposure (ADR-027) ───────────────────────────────────────────────────


def _inventory():
    names = ["decision.propose", "decision.propose_batch", *T.READ_TOOLS]
    return [{"name": n, "description": f"d {n}", "inputSchema": {"type": "object"}} for n in names]


def test_direct_tools_expose_only_four_read_methods_with_valid_names():
    tools = T.direct_tools(_inventory())
    names = [t["name"] for t in tools]
    assert names == ["decision_get", "decision_search", "decision_applicable_to", "decision_trace"]
    assert all("propose" not in n for n in names)
    assert {T.TOOL_NAME_TO_MCP[n] for n in names} == set(T.READ_TOOLS)
    import re
    assert all(re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", n) for n in names)


def test_direct_tools_pass_upstream_description_and_schema_verbatim():
    inventory = _inventory()
    tools = T.direct_tools(inventory)
    upstream = {t["name"]: t for t in inventory}
    for tool in tools:
        source = upstream[T.TOOL_NAME_TO_MCP[tool["name"]]]
        assert tool["description"] == source["description"]
        assert tool["input_schema"] == source["inputSchema"]


def test_calibration_tasks_are_not_b0a_scenarios():
    assert all(task_id.startswith("CAL-") for task_id in T.TASKS)
    assert all("b0a-" not in json.dumps(task) for task in T.TASKS.values())


# ── Usage accounting ──────────────────────────────────────────────────────────


def _usage(**over):
    usage = {
        "input_tokens": 100,
        "cache_creation_input_tokens": 50,
        "cache_read_input_tokens": 25,
        "cache_creation": {"ephemeral_5m_input_tokens": 50, "ephemeral_1h_input_tokens": 0},
        "output_tokens": 40,
        "output_tokens_details": {"thinking_tokens": 10},
    }
    usage.update(over)
    return usage


def test_normalized_total_adds_cache_categories_once():
    norm = C.normalize_usage(_usage())
    assert norm["complete"]
    assert norm["normalized_input_total"] == 175
    assert norm["normalized_total"] == 215


def test_thinking_tokens_are_never_added_to_the_total():
    assert C.normalize_usage(_usage())["normalized_output_total"] == 40


@pytest.mark.parametrize("field", ["input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"])
def test_null_or_missing_category_is_incomplete_not_zero(field):
    assert not C.normalize_usage(_usage(**{field: None}))["complete"]
    usage = _usage()
    del usage[field]
    assert not C.normalize_usage(usage)["complete"]


def test_absent_usage_is_incomplete():
    assert C.normalize_usage(None) == {"complete": False, "issues": ["usage absent"]}


def test_thinking_above_output_is_flagged_as_diagnostic():
    norm = C.normalize_usage(_usage(output_tokens_details={"thinking_tokens": 99}))
    assert norm["complete"] and norm["thinking_exceeds_output"]


def test_actual_cost_uses_cache_ttl_breakdown():
    cost = C.actual_cost_usd(_usage())
    expected = (100 * 2.0 + 50 * 2.5 + 25 * 0.10 + 40 * 10.0) / 1_000_000
    assert cost == pytest.approx(expected)


def test_actual_cost_unknown_breakdown_uses_highest_write_price():
    cost = C.actual_cost_usd(_usage(cache_creation=None))
    expected = (100 * 2.0 + 50 * 4.0 + 25 * 0.10 + 40 * 10.0) / 1_000_000
    assert cost == pytest.approx(expected)


# ── Budget guard ──────────────────────────────────────────────────────────────


def test_budget_stops_before_a_request_could_exceed_usd_cap():
    budget = C.Budget(usd_cap=0.30)
    body = b"x" * 1000
    _, upper = C.worst_case(body, 16000)
    assert upper < 0.30 < 2 * upper
    budget.authorize(body, 16000)
    budget.charge(200, None, upper)  # usage unknown: charged at worst case
    with pytest.raises(C.BudgetStop):
        budget.authorize(body, 16000)
    assert budget.requests == 1


def test_budget_request_cap_counts_every_attempt():
    budget = C.Budget(request_cap=2)
    budget.authorize(b"{}", 10)
    budget.authorize(b"{}", 10)
    with pytest.raises(C.BudgetStop):
        budget.authorize(b"{}", 10)


def test_client_errors_cost_nothing_server_errors_cost_worst_case():
    budget = C.Budget()
    assert budget.charge(400, None, 0.5) == 0.0
    assert budget.charge(503, None, 0.5) == 0.5
    assert budget.charge(429, None, 0.5) == 0.5
    assert budget.charge(None, None, 0.5) == 0.5


def test_successful_response_with_usage_charges_actual_cost():
    budget = C.Budget()
    assert budget.charge(200, _usage(), 0.5) == pytest.approx(C.actual_cost_usd(_usage()))


class _ScriptedTransport:
    def __init__(self, results):
        self.results = list(results)
        self.sent = 0

    def send(self, url, body_bytes):
        self.sent += 1
        return self.results.pop(0)


def _runner(tmp_path, transport, **budget):
    return C.Runner(transport, C.Evidence(tmp_path, "sk-test-SECRET"), budget=C.Budget(**budget), sleep=lambda _s: None)


def _ok(usage=None):
    return C.HttpResult(200, "req", {"type": "message", "model": T.MODEL, "content": [], "stop_reason": "end_turn", "usage": usage or _usage()}, 0.01)


def test_infrastructure_retries_are_bounded_and_counted(tmp_path):
    transport = _ScriptedTransport([C.HttpResult(529, "r", {"type": "error"}, 0.0)] * 3)
    runner = _runner(tmp_path, transport)
    body = T.build_request(tools=[], messages=[], schema_key=None)
    record = runner.send_message(body, "t")
    assert transport.sent == 3 and runner.budget.requests == 3
    assert record["status"] == 529


def test_retry_stops_when_budget_would_be_exceeded(tmp_path):
    transport = _ScriptedTransport([C.HttpResult(529, "r", {"type": "error"}, 0.0)] * 3)
    runner = _runner(tmp_path, transport, request_cap=2)
    with pytest.raises(C.BudgetStop):
        runner.send_message(T.build_request(tools=[], messages=[], schema_key=None), "t")
    assert transport.sent == 2


def test_auth_error_stops_the_run(tmp_path):
    runner = _runner(tmp_path, _ScriptedTransport([C.HttpResult(401, "r", {"type": "error"}, 0.0)]))
    with pytest.raises(C.AuthStop):
        runner.send_message(T.build_request(tools=[], messages=[], schema_key=None), "t")


def test_input_bound_violation_halts(tmp_path):
    huge = _usage(input_tokens=10_000_000)
    runner = _runner(tmp_path, _ScriptedTransport([_ok(huge)]))
    with pytest.raises(C.BoundViolation):
        runner.send_message(T.build_request(tools=[], messages=[], schema_key=None), "t")


# ── Evidence and redaction ────────────────────────────────────────────────────


def test_secret_tripwire_blocks_writes(tmp_path):
    evidence = C.Evidence(tmp_path, "sk-test-SECRET")
    with pytest.raises(C.RedactionError):
        evidence.append("events.jsonl", {"leak": "Bearer sk-test-SECRET"})


def test_live_transport_never_writes_key_to_evidence(tmp_path):
    runner = _runner(tmp_path, _ScriptedTransport([_ok()]))
    runner.send_message(T.build_request(tools=[], messages=[], schema_key=None), "t")
    for path in tmp_path.iterdir():
        assert "sk-test-SECRET" not in path.read_text(encoding="utf-8")


# ── CLI guards ────────────────────────────────────────────────────────────────


def test_live_requires_exact_confirmations(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-SECRET")
    assert C.main(["--live", "--out", str(tmp_path / "a")]) == 2
    assert C.main(["--live", "--out", str(tmp_path / "b"), "--confirm-requests", "150", "--confirm-usd", "30"]) == 2


def test_live_requires_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert C.main(["--live", "--out", str(tmp_path / "a"), "--confirm-requests", "150", "--confirm-usd", "25"]) == 2


def test_refuses_non_empty_output_directory(tmp_path):
    (tmp_path / "existing").write_text("x", encoding="utf-8")
    assert C.main(["--dry-run", "--out", str(tmp_path)]) == 2


# ── End-to-end dry run (genuine local MCP, fake provider, no network) ─────────


def test_dry_run_end_to_end_without_network(tmp_path, monkeypatch):
    def no_network(*_args, **_kwargs):
        raise AssertionError("network access attempted during dry run")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(C.urllib.request, "urlopen", no_network)
    out = tmp_path / "evidence"
    assert C.main(["--dry-run", "--out", str(out)]) == 0

    summary = json.loads((out / "checks.json").read_text(encoding="utf-8"))
    assert summary["run_status"] == "completed"
    assert summary["budget"]["requests_used"] <= C.REQUEST_CAP
    assert set(summary["checks"]) == {f"K{i}" for i in range(1, 10)}
    assert summary["checks"]["K4"]["status"] == "PASS"

    mcp_calls = [json.loads(line) for line in (out / "mcp.jsonl").read_text(encoding="utf-8").splitlines()]
    assert mcp_calls and all(call["method"] in T.READ_TOOLS for call in mcp_calls)

    manifest = (out / "manifest.sha256").read_text(encoding="utf-8")
    for name in ("checks.json", "responses.jsonl", "ledger.jsonl", "validation/cm01/b0-benchmark/fixture/project_memory.json"):
        assert name in manifest
    assert C.FIXTURE_SHA256 in manifest


def test_codemode_stub_never_executes_submitted_code(tmp_path):
    out = tmp_path / "evidence"
    assert C.main(["--dry-run", "--out", str(out)]) == 0
    requests = [json.loads(line) for line in (out / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
    stub_results = [
        json.loads(block["content"])
        for req in requests
        if "codemode" in req["purpose"]
        for message in req["body"]["messages"]
        if isinstance(message["content"], list)
        for block in message["content"]
        if block.get("type") == "tool_result"
    ]
    assert stub_results
    assert all(r["calibration_stub"] is True and r["code_executed"] is False for r in stub_results)


def test_max_tokens_rule_is_four_times_largest_and_capped(tmp_path):
    runner = C.Runner(C.FakeTransport(), C.Evidence(tmp_path, None))
    runner.loops = [{
        "loop": "x", "structured": False, "final": None, "turns": [
            {"seq": 1, "status": 200, "latency_s": 0, "stop_reason": "end_turn", "model": T.MODEL,
             "usage_norm": {"complete": True, "normalized_output_total": 50_000, "split": [1, 0, 0], "normalized_input_total": 1},
             "echo": {}, "blocks": [], "sent_thinking_blocks": False, "error": None},
        ],
    }]
    k9 = C.compute_checks(runner)["K9"]
    assert k9["largest_representative_output"] == 50_000
    assert k9["provisional_benchmark_max_tokens"] == 128_000
