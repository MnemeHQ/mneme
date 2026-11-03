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


_LIVE_OK = ["--confirm-requests", "150", "--confirm-usd", "25", "--attest-workspace-spend-limit-usd", "25"]


def test_live_requires_api_key(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert C.main(["--live", "--out", str(tmp_path / "a"), *_LIVE_OK]) == 2
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().err


@pytest.mark.parametrize("limit", [None, "0", "-1", "25.01", "100"])
def test_live_requires_attested_provider_spend_limit_within_cap(tmp_path, monkeypatch, capsys, limit):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-SECRET")
    args = ["--live", "--out", str(tmp_path / "a"), "--confirm-requests", "150", "--confirm-usd", "25"]
    if limit is not None:
        args += ["--attest-workspace-spend-limit-usd", limit]
    assert C.main(args) == 2
    assert "attest-workspace-spend-limit-usd" in capsys.readouterr().err


def test_live_transport_headers_include_workspace_only_when_set():
    with_ws = C.LiveTransport("sk-test-SECRET", "wrkspc_cal").headers()
    without_ws = C.LiveTransport("sk-test-SECRET").headers()
    assert with_ws["anthropic-workspace-id"] == "wrkspc_cal"
    assert "anthropic-workspace-id" not in without_ws
    assert with_ws["anthropic-version"] == T.ANTHROPIC_VERSION
    assert with_ws["Authorization"] == "Bearer sk-test-SECRET"


def test_live_transport_sends_headers_without_network(monkeypatch):
    captured = {}

    class _Response:
        status = 200

        def __init__(self):
            self.headers = {"request-id": "req_x"}

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def read(self):
            return b'{"type": "message"}'

    def fake_urlopen(request, timeout):
        captured["headers"] = {k.lower(): v for k, v in request.header_items()}
        return _Response()

    monkeypatch.setattr(C.urllib.request, "urlopen", fake_urlopen)
    result = C.LiveTransport("sk-test-SECRET", "wrkspc_cal").send(T.API_URL, b"{}")
    assert result.status == 200 and result.request_id == "req_x"
    assert captured["headers"]["anthropic-workspace-id"] == "wrkspc_cal"


# ── K1 probes fail closed ─────────────────────────────────────────────────────


def _err(status):
    return C.HttpResult(status, "r", {"type": "error", "error": {"type": "x", "message": "y"}}, 0.0)


def _probe_ok():
    return _ok(_usage(output_tokens=16))


def test_valid_baseline_probe_failure_stops_run(tmp_path):
    runner = _runner(tmp_path, _ScriptedTransport([_err(400)]))
    with pytest.raises(C.ProbeStop):
        runner.run_probes()
    assert runner.probes[0]["expectation_met"] is False


def test_invalid_probes_rejected_as_expected_are_recorded_not_failed(tmp_path):
    runner = _runner(tmp_path, _ScriptedTransport([_probe_ok(), _err(400), _err(400), _err(400)]))
    runner.run_probes()
    assert [p["expectation_met"] for p in runner.probes] == [True, True, True, True]


def test_invalid_probe_unexpectedly_accepted_is_recorded_without_stopping(tmp_path):
    runner = _runner(tmp_path, _ScriptedTransport([_probe_ok(), _probe_ok(), _err(400), _err(400)]))
    runner.run_probes()
    assert runner.probes[1]["purpose"] == "K1-temperature"
    assert runner.probes[1]["expectation_met"] is False


# ── K4 requires a demonstrated tool loop ─────────────────────────────────────


def _turn(seq, stop):
    return {"seq": seq, "status": 200, "stop_reason": stop, "latency_s": 0.0}


def _loop(name, *, tool_call, valid=True, passback=(True,)):
    turns = [_turn(1, "tool_use"), _turn(2, "end_turn")] if tool_call else [_turn(1, "end_turn")]
    return {
        "loop": name,
        "structured": True,
        "turns": turns,
        "tool_calls": [{"turn": 0, "name": "x", "via": "genuine_mcp", "ok": True}] if tool_call else [],
        "passback_identical": list(passback) if tool_call else [],
        "end": "end_turn",
        "final": {"parsed": True, "schema_valid": valid},
    }


def _all_cells(**kwargs):
    return [
        C.k4_cell(_loop(f"{task}/{arm}/json_schema", **kwargs))
        for task in T.TASKS
        for arm in ("direct", "codemode")
    ]


def test_k4_immediate_valid_json_without_tool_call_cannot_pass():
    cell = C.k4_cell(_loop("CAL-T5/direct/json_schema", tool_call=False))
    assert cell["status"] == "INCONCLUSIVE"
    assert C.k4_status(_all_cells(tool_call=False)) == "INCONCLUSIVE"


def test_k4_passes_only_with_tool_call_continuation_and_valid_answer():
    assert C.k4_status(_all_cells(tool_call=True)) == "PASS"


def test_k4_requires_every_arm_and_schema_cell():
    cells = _all_cells(tool_call=True)[:-1]
    assert C.k4_status(cells) == "INCONCLUSIVE"


def test_k4_invalid_final_answer_fails():
    assert C.k4_cell(_loop("CAL-T5/direct/json_schema", tool_call=True, valid=False))["status"] == "FAIL"


def test_k4_altered_passback_fails():
    cell = C.k4_cell(_loop("CAL-T5/direct/json_schema", tool_call=True, passback=(False,)))
    assert cell["status"] == "FAIL"


def test_k4_tool_call_without_continuation_is_inconclusive():
    loop = _loop("CAL-T5/direct/json_schema", tool_call=True)
    loop["turns"] = [_turn(1, "tool_use")]
    assert C.k4_cell(loop)["status"] == "INCONCLUSIVE"


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
    assert summary["metadata"]["mode"] == "dry_run"
    k4 = summary["checks"]["K4"]
    assert k4["status"] == "PASS" and len(k4["cells"]) == 6
    assert all(c["successful_tool_calls"] >= 1 and c["continued_after_tool_result"] for c in k4["cells"])
    assert {v for c in k4["cells"] for v in c["tool_call_via"]} == {"genuine_mcp", "fixed_stub"}
    k6 = summary["checks"]["K6"]
    assert k6["status"] == "DESCRIPTIVE"
    assert all(p["schema_sha256"] and p["tools_sha256"] and p["first_sent_utc"] for p in k6["pairs"])
    assert len({p["tools_sha256"] for p in k6["pairs"]}) == 2

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
