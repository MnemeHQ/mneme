"""CM-01 B0-A provider calibration harness (A4).

Calibration only, not B0-A evidence. It checks provider usage accounting and the
ratified A2 configuration (K1-K9 in README.md). Boundaries:

- no model-generated code is ever executed: the Code Mode stand-in tool returns
  a fixed result precomputed from the genuine MCP, whatever code it receives;
- the direct arm calls the genuine pinned Decision MCP on the frozen B0-M
  fixture, exposing only the four ADR-027 read methods;
- requests run strictly sequentially under a hard request cap and USD cap that
  count every attempt, retry, warm-up and probe;
- the API key is read from ANTHROPIC_API_KEY, sent only in the request header
  and never written to evidence.

Usage:
    python calibration.py --dry-run --out <empty dir>
    python calibration.py --live --out <empty dir> --confirm-requests 150 --confirm-usd 25
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import anyio
import jsonschema

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import templates as T

REPO_ROOT = HERE.parents[2]
FIXTURE = REPO_ROOT / "validation" / "cm01" / "b0-benchmark" / "fixture" / "project_memory.json"
FIXTURE_SHA256 = "a996e2aa5c2d41bf8a75293c8d60adebf9ab89eb59caea926fbccf97297a1dca"

REQUEST_CAP = 150
USD_CAP = 25.0
COUNT_TOKENS_CAP = 60
LOOP_TURN_CAP = 6
# Added to the request byte length to bound input tokens from above: covers
# provider-injected system text for tools, thinking and structured outputs.
# Every response is checked against this bound; a violation halts the run.
INPUT_OVERHEAD_ALLOWANCE_TOKENS = 8000
INFRA_RETRY_STATUSES = {429, 500, 502, 503, 504, 529}
INFRA_BACKOFF_SECONDS = (10.0, 30.0)
MAX_TOKENS_MULTIPLIER = 4
MODEL_MAX_OUTPUT = 128000


class RunStop(Exception):
    """Base class for conditions that end the run and are recorded."""

    reason = "stopped"


class BudgetStop(RunStop):
    reason = "budget_cap"


class BoundViolation(RunStop):
    reason = "bound_violation"


class AuthStop(RunStop):
    reason = "auth_error"


class RedactionError(RuntimeError):
    pass


# ── Usage accounting ──────────────────────────────────────────────────────────

_REQUIRED_USAGE_FIELDS = (
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "output_tokens",
)


def normalize_usage(usage: Any) -> dict[str, Any]:
    """Map Anthropic usage to the #660 normalized totals.

    Missing or null required categories make the record usage-incomplete; they
    are never treated as zero. ``thinking_tokens`` is a diagnostic subset only.
    """
    issues: list[str] = []
    if not isinstance(usage, dict):
        return {"complete": False, "issues": ["usage absent"]}
    values: dict[str, int] = {}
    for name in _REQUIRED_USAGE_FIELDS:
        value = usage.get(name)
        if not isinstance(value, int) or value < 0:
            issues.append(f"{name} missing or null")
        else:
            values[name] = value
    details = usage.get("output_tokens_details") or {}
    thinking = details.get("thinking_tokens") if isinstance(details, dict) else None
    record: dict[str, Any] = {
        "complete": not issues,
        "issues": issues,
        "thinking_tokens_approx": thinking,
    }
    if not issues:
        record["normalized_input_total"] = (
            values["input_tokens"]
            + values["cache_creation_input_tokens"]
            + values["cache_read_input_tokens"]
        )
        record["normalized_output_total"] = values["output_tokens"]
        record["normalized_total"] = record["normalized_input_total"] + values["output_tokens"]
        record["split"] = [
            values["input_tokens"],
            values["cache_creation_input_tokens"],
            values["cache_read_input_tokens"],
        ]
        record["thinking_exceeds_output"] = (
            isinstance(thinking, int) and thinking > values["output_tokens"]
        )
    return record


def actual_cost_usd(usage: Any) -> float | None:
    """Billed-cost estimate from a complete usage object, else None."""
    norm = normalize_usage(usage)
    if not norm["complete"]:
        return None
    p = T.PRICE_PER_MTOK
    creation = usage["cache_creation_input_tokens"]
    breakdown = usage.get("cache_creation") or {}
    five = breakdown.get("ephemeral_5m_input_tokens")
    hour = breakdown.get("ephemeral_1h_input_tokens")
    if isinstance(five, int) and isinstance(hour, int) and five + hour == creation:
        creation_cost = five * p["cache_write_5m"] + hour * p["cache_write_1h"]
    else:
        creation_cost = creation * p["cache_write_1h"]
    total = (
        usage["input_tokens"] * p["input"]
        + creation_cost
        + usage["cache_read_input_tokens"] * p["cache_read"]
        + usage["output_tokens"] * p["output"]
    )
    return total / 1_000_000


def worst_case(body_bytes: bytes, max_tokens: int) -> tuple[int, float]:
    """Upper bounds for one request: input tokens and USD."""
    input_upper = len(body_bytes) + INPUT_OVERHEAD_ALLOWANCE_TOKENS
    usd = (input_upper * T.WORST_CASE_INPUT_PRICE + max_tokens * T.PRICE_PER_MTOK["output"]) / 1_000_000
    return input_upper, usd


@dataclass
class Budget:
    request_cap: int = REQUEST_CAP
    usd_cap: float = USD_CAP
    count_cap: int = COUNT_TOKENS_CAP
    requests: int = 0
    count_calls: int = 0
    spent_usd: float = 0.0

    def authorize(self, body_bytes: bytes, max_tokens: int) -> tuple[int, float]:
        """Admit one Messages attempt or stop before it could exceed a cap."""
        input_upper, usd_upper = worst_case(body_bytes, max_tokens)
        if self.requests + 1 > self.request_cap:
            raise BudgetStop(f"request cap {self.request_cap} reached")
        if self.spent_usd + usd_upper > self.usd_cap:
            raise BudgetStop(
                f"next request worst case ${usd_upper:.4f} would exceed "
                f"remaining ${self.usd_cap - self.spent_usd:.4f}"
            )
        self.requests += 1
        return input_upper, usd_upper

    def authorize_count(self) -> None:
        if self.count_calls + 1 > self.count_cap:
            raise BudgetStop(f"count_tokens cap {self.count_cap} reached")
        self.count_calls += 1

    def charge(self, status: int | None, usage: Any, usd_upper: float) -> float:
        """Charge one attempt: actual cost when known, worst case when unknown.

        4xx client errors are not billed by the provider and are charged 0.
        """
        if status is not None and 400 <= status < 500 and status != 429:
            charged = 0.0
        else:
            cost = actual_cost_usd(usage) if status == 200 else None
            charged = cost if cost is not None else usd_upper
        self.spent_usd += charged
        return charged


# ── Transports ────────────────────────────────────────────────────────────────


@dataclass
class HttpResult:
    status: int | None
    request_id: str | None
    body: Any
    latency_s: float
    error: str | None = None


class Transport(Protocol):
    def send(self, url: str, body_bytes: bytes) -> HttpResult: ...


class LiveTransport:
    """Sequential HTTPS transport. The key lives only in this object."""

    def __init__(self, api_key: str, timeout_s: float = 600.0) -> None:
        self._key = api_key
        self._timeout = timeout_s

    def send(self, url: str, body_bytes: bytes) -> HttpResult:
        request = urllib.request.Request(
            url,
            data=body_bytes,
            method="POST",
            headers={
                "content-type": "application/json",
                "anthropic-version": T.ANTHROPIC_VERSION,
                "Authorization": f"Bearer {self._key}",
            },
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                raw = response.read()
                status = response.status
                request_id = response.headers.get("request-id")
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
            request_id = exc.headers.get("request-id") if exc.headers else None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return HttpResult(None, None, None, time.perf_counter() - started, type(exc).__name__)
        latency = time.perf_counter() - started
        try:
            body: Any = json.loads(raw)
        except ValueError:
            body = {"non_json_body_sha256": hashlib.sha256(raw).hexdigest()}
        return HttpResult(status, request_id, body, latency)


class FakeTransport:
    """Dry-run transport: official-schema synthetic responses, no network."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._n = 0

    def send(self, url: str, body_bytes: bytes) -> HttpResult:
        body = json.loads(body_bytes)
        self.calls.append(body)
        self._n += 1
        rid = f"dryrun-{self._n:04d}"
        if url == T.COUNT_TOKENS_URL:
            return HttpResult(200, rid, {"input_tokens": len(body_bytes) // 4}, 0.0)
        if "temperature" in body:
            return HttpResult(400, rid, _error("invalid_request_error", "temperature is not supported"), 0.0)
        if body.get("tool_choice", {}).get("type") in {"any", "tool"}:
            return HttpResult(400, rid, _error("invalid_request_error", "forced tool use is not supported"), 0.0)
        if body.get("thinking", {}).get("type") == "between_tools" and body["output_config"].get("effort") in {"xhigh", "max"}:
            return HttpResult(400, rid, _error("invalid_request_error", "between_tools requires effort high or below"), 0.0)
        usage = {
            "input_tokens": len(body_bytes) // 4,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 0},
            "output_tokens": 60,
            "output_tokens_details": {"thinking_tokens": 20},
            "service_tier": "standard",
            "speed": "standard",
            "inference_geo": "global",
        }
        if body["max_tokens"] < 64:
            usage["output_tokens"] = body["max_tokens"]
            return HttpResult(200, rid, _message([{"type": "text", "text": "o"}], "max_tokens", usage), 0.0)
        tools = body.get("tools") or []
        has_results = any(
            isinstance(m.get("content"), list)
            and any(block.get("type") == "tool_result" for block in m["content"])
            for m in body["messages"]
        )
        thinking = {"type": "thinking", "thinking": "", "signature": "dryrun-signature"}
        if tools and not has_results:
            tool = tools[0]
            if tool["name"] == T.CODEMODE_TOOL_NAME:
                tool_input: dict[str, Any] = {"code": "return null;"}
            else:
                tool = next(t for t in tools if t["name"] == "decision_search")
                tool_input = {"query": "", "canonical_lifecycle_status": "active"}
            block = {"type": "tool_use", "id": f"toolu_dry{self._n:04d}", "name": tool["name"], "input": tool_input}
            return HttpResult(200, rid, _message([thinking, block], "tool_use", usage), 0.0)
        schema_key = _schema_key_of(body)
        answer = _minimal_instance(T.SCHEMAS[schema_key or "T6"])
        return HttpResult(200, rid, _message([thinking, {"type": "text", "text": json.dumps(answer)}], "end_turn", usage), 0.0)


def _error(kind: str, message: str) -> dict[str, Any]:
    return {"type": "error", "error": {"type": kind, "message": message}}


def _message(content: list[dict[str, Any]], stop: str, usage: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "msg_dryrun",
        "type": "message",
        "role": "assistant",
        "model": T.MODEL,
        "content": content,
        "stop_reason": stop,
        "stop_sequence": None,
        "usage": usage,
    }


def _schema_key_of(body: dict[str, Any]) -> str | None:
    fmt = body.get("output_config", {}).get("format")
    if not fmt:
        return None
    for key, schema in T.SCHEMAS.items():
        if schema == fmt["schema"]:
            return key
    return None


def _minimal_instance(schema: dict[str, Any]) -> Any:
    kind = schema.get("type")
    if kind == "object":
        return {k: _minimal_instance(schema["properties"][k]) for k in schema.get("required", [])}
    if kind == "array":
        return []
    if kind == "integer":
        return 0
    return ""


# ── Evidence ──────────────────────────────────────────────────────────────────


class Evidence:
    """Append-only JSONL evidence with a secret tripwire."""

    FILES = ("requests.jsonl", "responses.jsonl", "ledger.jsonl", "mcp.jsonl", "events.jsonl")

    def __init__(self, out_dir: Path, secret: str | None) -> None:
        self.dir = out_dir
        self._secret = secret
        self.dir.mkdir(parents=True, exist_ok=True)
        for name in self.FILES:
            (self.dir / name).touch()

    def _check(self, text: str) -> None:
        if self._secret and self._secret in text:
            raise RedactionError("secret would be written to evidence")

    def append(self, name: str, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False)
        self._check(line)
        with open(self.dir / name, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")

    def write_json(self, name: str, obj: Any) -> None:
        text = json.dumps(obj, ensure_ascii=False, indent=2)
        self._check(text)
        (self.dir / name).write_text(text + "\n", encoding="utf-8", newline="\n")

    def write_manifest(self) -> None:
        lines = []
        sources = [HERE / "calibration.py", HERE / "templates.py", FIXTURE]
        for path in sorted(self.dir.glob("*")) + sources:
            if path.name == "manifest.sha256" and path.parent == self.dir:
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            label = path.name if path.parent == self.dir else str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            lines.append(f"{digest}  {label}")
        (self.dir / "manifest.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


# ── Genuine Decision MCP bridge ───────────────────────────────────────────────


class McpBridge:
    """One genuine pinned Decision MCP child; only the four read tools pass."""

    def __init__(self, session: Any, evidence: Evidence, loop_id: str) -> None:
        self._session = session
        self._evidence = evidence
        self._loop_id = loop_id
        self.inventory: list[dict[str, Any]] = []

    async def load_inventory(self) -> None:
        listed = await self._session.list_tools()
        self.inventory = [tool.model_dump(by_alias=True, exclude_none=True) for tool in listed.tools]

    async def call(self, mcp_name: str, args: dict[str, Any]) -> tuple[bool, Any]:
        if mcp_name not in T.READ_TOOLS:
            self._evidence.append("mcp.jsonl", {"loop": self._loop_id, "method": mcp_name, "rejected": True})
            return False, {"error": f"method {mcp_name} is not allowed"}
        result = await self._session.call_tool(mcp_name, args)
        dumped = result.model_dump(by_alias=True)
        payload = dumped.get("structuredContent")
        if payload is None:
            payload = {"content": dumped.get("content")}
        text = json.dumps(payload, ensure_ascii=False)
        self._evidence.append("mcp.jsonl", {
            "loop": self._loop_id,
            "method": mcp_name,
            "args": args,
            "is_error": bool(dumped.get("isError")),
            "result_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "result_bytes": len(text.encode("utf-8")),
        })
        return not dumped.get("isError"), payload


async def _with_mcp(evidence: Evidence, loop_id: str, fn: Callable[[McpBridge], Any]) -> Any:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mneme", "decision-mcp", "--memory", str(FIXTURE), "--proposals", ""],
        cwd=str(REPO_ROOT),
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        bridge = McpBridge(session, evidence, loop_id)
        await bridge.load_inventory()
        return await fn(bridge)


# ── Runner ────────────────────────────────────────────────────────────────────


@dataclass
class Runner:
    transport: Transport
    evidence: Evidence
    budget: Budget = field(default_factory=Budget)
    sleep: Callable[[float], None] = time.sleep
    seq: int = 0
    loops: list[dict[str, Any]] = field(default_factory=list)
    probes: list[dict[str, Any]] = field(default_factory=list)
    replays: list[dict[str, Any]] = field(default_factory=list)
    counts: list[dict[str, Any]] = field(default_factory=list)
    warm: list[dict[str, Any]] = field(default_factory=list)
    stop: dict[str, Any] | None = None

    def send_message(self, body: dict[str, Any], purpose: str) -> dict[str, Any]:
        """Send one Messages request with fixed infrastructure retries.

        Every attempt is admitted by the budget guard first. Returns the record
        of the final attempt.
        """
        body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
        body_sha = hashlib.sha256(body_bytes).hexdigest()
        record: dict[str, Any] = {}
        for attempt in range(len(INFRA_BACKOFF_SECONDS) + 1):
            input_upper, usd_upper = self.budget.authorize(body_bytes, body["max_tokens"])
            self.seq += 1
            self.evidence.append("requests.jsonl", {"seq": self.seq, "purpose": purpose, "attempt": attempt, "body_sha256": body_sha, "body": body})
            result = self.transport.send(T.API_URL, body_bytes)
            usage = result.body.get("usage") if isinstance(result.body, dict) else None
            charged = self.budget.charge(result.status, usage, usd_upper)
            norm = normalize_usage(usage) if result.status == 200 else None
            record = {
                "seq": self.seq,
                "purpose": purpose,
                "attempt": attempt,
                "status": result.status,
                "request_id": result.request_id,
                "latency_s": result.latency_s,
                "transport_error": result.error,
                "body_sha256": body_sha,
                "response": result.body,
                "usage_norm": norm,
            }
            self.evidence.append("responses.jsonl", record)
            self.evidence.append("ledger.jsonl", {
                "seq": self.seq,
                "purpose": purpose,
                "attempt": attempt,
                "input_upper_tokens": input_upper,
                "usd_upper": usd_upper,
                "usd_charged": charged,
                "usd_spent": self.budget.spent_usd,
                "requests_used": self.budget.requests,
            })
            if result.status in (401, 403):
                raise AuthStop(f"HTTP {result.status}")
            if norm and norm["complete"]:
                if norm["normalized_input_total"] > input_upper:
                    raise BoundViolation(f"seq {self.seq}: input {norm['normalized_input_total']} > bound {input_upper}")
                if norm["normalized_output_total"] > body["max_tokens"]:
                    raise BoundViolation(f"seq {self.seq}: output exceeds max_tokens")
            retryable = result.status in INFRA_RETRY_STATUSES or result.status is None
            if not retryable or attempt == len(INFRA_BACKOFF_SECONDS):
                return record
            self.sleep(INFRA_BACKOFF_SECONDS[attempt])
        return record

    def count_tokens(self, body: dict[str, Any], purpose: str) -> dict[str, Any]:
        self.budget.authorize_count()
        count_body = {k: v for k, v in body.items() if k not in {"max_tokens", "service_tier", "speed"}}
        count_bytes = json.dumps(count_body, ensure_ascii=False).encode("utf-8")
        result = self.transport.send(T.COUNT_TOKENS_URL, count_bytes)
        record = {"purpose": purpose, "status": result.status, "request_id": result.request_id, "response": result.body}
        self.evidence.append("events.jsonl", {"event": "count_tokens", **record})
        return record

    # K1 error and edge probes, outside any tool loop.
    def run_probes(self) -> None:
        base = [{"role": "user", "content": "Reply with the single word: ok"}]
        no_tools = {"tools": None, "tool_choice": None}
        cases = [
            ("K1-max_tokens", {**no_tools, "max_tokens": 16}),
            ("K1-temperature", {**no_tools, "temperature": 0.5}),
            ("K1-forced_tool", {"tool_choice": {"type": "any"}}),
            ("K1-between_tools_xhigh", {**no_tools, "thinking": {"type": "between_tools"}, "output_config": {"effort": "xhigh"}}),
        ]
        for purpose, overrides in cases:
            tools = [T.codemode_tool()] if purpose == "K1-forced_tool" else []
            body = T.build_request(tools=tools, messages=base, schema_key=None, overrides=overrides)
            record = self.send_message(body, purpose)
            self.probes.append({"purpose": purpose, "status": record["status"], "response": record["response"]})

    async def run_loop(self, task_id: str, arm: str, structured: bool, warm_repeat: bool) -> None:
        task = T.TASKS[task_id]
        loop_id = f"{task_id}/{arm}/{'json_schema' if structured else 'text_json'}"
        schema_key = task["schema"] if structured else None

        async def body_fn(bridge: McpBridge) -> None:
            if arm == "direct":
                tools = T.direct_tools(bridge.inventory)
                stub = None
            else:
                tools = [T.codemode_tool()]
                stub = await self._reference_stub(bridge, task)
            messages: list[dict[str, Any]] = [{"role": "user", "content": task["prompt"]}]
            loop = {"loop": loop_id, "task": task_id, "arm": arm, "structured": structured, "turns": [], "final": None}
            self.loops.append(loop)
            for turn in range(LOOP_TURN_CAP):
                body = T.build_request(tools=tools, messages=messages, schema_key=schema_key)
                record = self.send_message(body, f"loop:{loop_id}:turn{turn}")
                loop["turns"].append(self._turn_summary(record, body))
                if turn == 0 and warm_repeat and record["status"] == 200:
                    repeat = self.send_message(body, f"warm:{loop_id}")
                    self.warm.append({"loop": loop_id, "cold": self._turn_summary(record, body), "warm": self._turn_summary(repeat, body)})
                if record["status"] != 200:
                    loop["end"] = f"http_{record['status']}"
                    return
                response = record["response"]
                messages.append({"role": "assistant", "content": response["content"]})
                if response.get("stop_reason") != "tool_use":
                    loop["end"] = response.get("stop_reason")
                    loop["final"] = self._final_answer(response, task["schema"])
                    loop["last_body"] = body
                    return
                results = []
                for block in response["content"]:
                    if block.get("type") != "tool_use":
                        continue
                    if arm == "direct":
                        mcp_name = T.TOOL_NAME_TO_MCP.get(block["name"], block["name"])
                        ok, payload = await bridge.call(mcp_name, block.get("input") or {})
                    else:
                        ok, payload = True, stub
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": json.dumps(payload, ensure_ascii=False),
                        **({} if ok else {"is_error": True}),
                    })
                messages.append({"role": "user", "content": results})
            loop["end"] = "turn_cap"

        await _with_mcp(self.evidence, loop_id, body_fn)

    async def _reference_stub(self, bridge: McpBridge, task: dict[str, Any]) -> dict[str, Any]:
        """Fixed Code Mode stand-in result from the genuine MCP; code never runs."""
        method, args = task["reference_select"]
        _, selected = await bridge.call(method, args)
        matches = selected.get("canonical_decisions") or selected.get("canonical_scope_matches") or []
        traces = []
        for match in matches:
            if match.get("lifecycle_status") == "active":
                _, trace = await bridge.call("decision.trace", {"record_id": match["decision_id"]})
                traces.append(trace)
        return {
            "calibration_stub": True,
            "code_executed": False,
            "reference_data": {"selection": selected, "traces": traces},
        }

    @staticmethod
    def _turn_summary(record: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        response = record["response"] if isinstance(record["response"], dict) else {}
        content = response.get("content") or []
        sent_thinking = any(
            isinstance(m.get("content"), list)
            and any(block.get("type") in ("thinking", "redacted_thinking") for block in m["content"])
            for m in body["messages"]
            if m["role"] == "assistant"
        )
        return {
            "seq": record["seq"],
            "status": record["status"],
            "latency_s": record["latency_s"],
            "stop_reason": response.get("stop_reason"),
            "model": response.get("model"),
            "usage_norm": record["usage_norm"],
            "echo": {k: (response.get("usage") or {}).get(k) for k in ("service_tier", "speed", "inference_geo")},
            "blocks": [block.get("type") for block in content],
            "sent_thinking_blocks": sent_thinking,
            "error": response.get("error") if response.get("type") == "error" else None,
        }

    @staticmethod
    def _final_answer(response: dict[str, Any], schema_key: str) -> dict[str, Any]:
        text = "".join(block.get("text", "") for block in response["content"] if block.get("type") == "text")
        result: dict[str, Any] = {"text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
        try:
            answer = json.loads(text)
        except ValueError:
            result.update(parsed=False, schema_valid=False)
            return result
        try:
            jsonschema.validate(answer, T.SCHEMAS[schema_key])
            valid = True
        except jsonschema.ValidationError:
            valid = False
        result.update(parsed=True, schema_valid=valid)
        return result

    def run_replays(self, loop_ids: list[str]) -> None:
        """K3: resend completed loops' final requests to vary the cache split."""
        for loop in self.loops:
            if loop["loop"] not in loop_ids or "last_body" not in loop:
                continue
            original = next(t for t in reversed(loop["turns"]) if t["status"] == 200)
            group = {"loop": loop["loop"], "observations": [original["usage_norm"]]}
            for index in range(2):
                record = self.send_message(loop["last_body"], f"K3-replay:{loop['loop']}:{index}")
                group["observations"].append(record["usage_norm"])
            self.replays.append(group)

    async def run_counts(self) -> None:
        """K5: count_tokens with and without the schema, per arm and task."""
        async def inventory(bridge: McpBridge) -> list[dict[str, Any]]:
            return bridge.inventory

        mcp_tools = await _with_mcp(self.evidence, "K5-inventory", inventory)
        for task_id, task in T.TASKS.items():
            for arm, tools in (("direct", T.direct_tools(mcp_tools)), ("codemode", [T.codemode_tool()])):
                messages = [{"role": "user", "content": task["prompt"]}]
                pair = {"task": task_id, "arm": arm}
                for label, key in (("with_schema", task["schema"]), ("without_schema", None)):
                    body = T.build_request(tools=tools, messages=messages, schema_key=key)
                    pair[label] = self.count_tokens(body, f"K5:{task_id}/{arm}/{label}")
                self.counts.append(pair)


# ── Checks ────────────────────────────────────────────────────────────────────


def compute_checks(runner: Runner) -> dict[str, Any]:
    turns = [turn for loop in runner.loops for turn in loop["turns"]]
    ok_turns = [t for t in turns if t["status"] == 200]
    checks: dict[str, Any] = {}

    incomplete = [t["seq"] for t in ok_turns if not (t["usage_norm"] or {}).get("complete")]
    checks["K1"] = {
        "status": "PASS" if ok_turns and not incomplete else ("FAIL" if incomplete else "INCONCLUSIVE"),
        "successful_responses": len(ok_turns),
        "usage_incomplete_seqs": incomplete,
        "probes_observed": [
            {"purpose": p["purpose"], "status": p["status"], "has_usage": isinstance(p["response"], dict) and "usage" in p["response"]}
            for p in runner.probes
        ],
        "note": "Error responses without usage are observed API errors, not calibration failures.",
    }

    over = [t["seq"] for t in ok_turns if (t["usage_norm"] or {}).get("thinking_exceeds_output")]
    checks["K2"] = {
        "status": "PASS" if ok_turns and not incomplete else "INCONCLUSIVE",
        "thinking_tokens_exceeding_output_seqs": over,
        "note": "thinking_tokens is approximate and diagnostic only; never used to reconcile the primary total.",
    }

    groups = []
    for group in runner.replays:
        obs = [o for o in group["observations"] if o and o.get("complete")]
        totals = {o["normalized_input_total"] for o in obs}
        splits = {tuple(o["split"]) for o in obs}
        groups.append({"loop": group["loop"], "n": len(obs), "totals": sorted(totals), "distinct_splits": len(splits)})
    if not groups or any(g["n"] < 2 for g in groups):
        k3 = "INCONCLUSIVE"
    elif any(len(g["totals"]) > 1 for g in groups):
        k3 = "FAIL"
    elif all(g["distinct_splits"] < 2 for g in groups):
        k3 = "INCONCLUSIVE"
    else:
        k3 = "PASS"
    checks["K3"] = {"status": k3, "groups": groups, "note": "PASS needs equal input totals across at least two different cache splits."}

    structured = [loop for loop in runner.loops if loop["structured"]]
    k4_cells = [
        {"loop": loop["loop"], "end": loop.get("end"), "schema_valid": (loop["final"] or {}).get("schema_valid", False)}
        for loop in structured
    ]
    k4_ok = bool(k4_cells) and all(c["end"] == "end_turn" and c["schema_valid"] for c in k4_cells)
    checks["K4"] = {
        "status": "PASS" if k4_ok else "FAIL",
        "cells": k4_cells,
        "consequence": "Enable output_config.format in both arms" if k4_ok else "Fall back to evaluator-validated JSON in both arms",
    }

    k5 = []
    for pair in runner.counts:
        with_n = (pair["with_schema"]["response"] or {}).get("input_tokens")
        without_n = (pair["without_schema"]["response"] or {}).get("input_tokens")
        k5.append({
            "task": pair["task"],
            "arm": pair["arm"],
            "with_schema": with_n,
            "without_schema": without_n,
            "estimated_overhead": with_n - without_n if isinstance(with_n, int) and isinstance(without_n, int) else None,
        })
    checks["K5"] = {"status": "RECORDED" if k5 else "INCONCLUSIVE", "estimates": k5, "note": "count_tokens returns estimates; actual accounting is taken from Messages responses."}

    checks["K6"] = {
        "status": "RECORDED" if runner.warm else "INCONCLUSIVE",
        "pairs": [
            {"loop": w["loop"], "cold_latency_s": w["cold"]["latency_s"], "warm_latency_s": w["warm"]["latency_s"]}
            for w in runner.warm
        ],
        "note": "Cold is cold only if this arm and schema pair was not compiled in the previous 24 hours.",
    }

    models = {t["model"] for t in ok_turns}
    checks["K7"] = {
        "status": "PASS" if models == {T.MODEL} else "FAIL",
        "models": sorted(m for m in models if m),
        "echo_values": sorted({json.dumps(t["echo"], sort_keys=True) for t in ok_turns}),
        "anthropic_version": T.ANTHROPIC_VERSION,
    }

    roundtrip = [t for t in turns if t["sent_thinking_blocks"]]
    checks["K8"] = {
        "status": "PASS" if roundtrip and all(t["status"] == 200 for t in roundtrip) else ("FAIL" if roundtrip else "INCONCLUSIVE"),
        "requests_with_passed_back_thinking": len(roundtrip),
    }

    outputs = [t["usage_norm"]["normalized_output_total"] for t in ok_turns if (t["usage_norm"] or {}).get("complete")]
    largest = max(outputs) if outputs else None
    checks["K9"] = {
        "status": "RECORDED" if largest else "INCONCLUSIVE",
        "largest_representative_output": largest,
        "provisional_benchmark_max_tokens": min(MODEL_MAX_OUTPUT, MAX_TOKENS_MULTIPLIER * largest) if largest else None,
        "rule": f"min({MODEL_MAX_OUTPUT}, {MAX_TOKENS_MULTIPLIER} x largest representative calibration output); provisional until reviewed",
        "calibration_ceiling_hits": [t["seq"] for t in ok_turns if t["stop_reason"] == "max_tokens"],
    }
    return checks


# ── Plan ──────────────────────────────────────────────────────────────────────


async def run_plan(runner: Runner) -> None:
    runner.run_probes()
    for task_id in T.TASKS:
        for arm in ("direct", "codemode"):
            await runner.run_loop(task_id, arm, structured=True, warm_repeat=True)
    for arm in ("direct", "codemode"):
        await runner.run_loop("CAL-T5", arm, structured=False, warm_repeat=False)
    runner.run_replays(["CAL-T5/direct/json_schema", "CAL-T8/direct/json_schema"])
    await runner.run_counts()


def execute(runner: Runner) -> dict[str, Any]:
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        anyio.run(run_plan, runner)
        status = "completed"
    except RunStop as stop:
        status = stop.reason
        runner.stop = {"reason": stop.reason, "detail": str(stop)}
        runner.evidence.append("events.jsonl", {"event": "stop", **runner.stop})
    for loop in runner.loops:
        loop.pop("last_body", None)
    summary = {
        "run_status": status,
        "started_utc": started,
        "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "budget": {
            "request_cap": runner.budget.request_cap,
            "usd_cap": runner.budget.usd_cap,
            "requests_used": runner.budget.requests,
            "usd_spent_estimate": round(runner.budget.spent_usd, 6),
            "count_tokens_calls": runner.budget.count_calls,
        },
        "loops": runner.loops,
        "checks": compute_checks(runner),
        "stop": runner.stop,
    }
    runner.evidence.write_json("checks.json", summary)
    runner.evidence.write_manifest()
    return summary


def _verify_fixture() -> None:
    digest = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    if digest != FIXTURE_SHA256:
        raise SystemExit(f"B0-M fixture hash mismatch: {digest}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="synthetic responses, no network")
    mode.add_argument("--live", action="store_true", help="billable run against the Anthropic API")
    parser.add_argument("--out", required=True, help="new or empty evidence directory")
    parser.add_argument("--confirm-requests", type=int)
    parser.add_argument("--confirm-usd", type=float)
    args = parser.parse_args(argv)

    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        print(f"refusing to write into non-empty {out}", file=sys.stderr)
        return 2
    _verify_fixture()

    if args.live:
        if args.confirm_requests != REQUEST_CAP or args.confirm_usd != USD_CAP:
            print(f"live run requires --confirm-requests {REQUEST_CAP} --confirm-usd {USD_CAP:g}", file=sys.stderr)
            return 2
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            print("ANTHROPIC_API_KEY is not set", file=sys.stderr)
            return 2
        runner = Runner(LiveTransport(key), Evidence(out, key))
    else:
        runner = Runner(FakeTransport(), Evidence(out, None), sleep=lambda _s: None)

    summary = execute(runner)
    print(json.dumps({
        "run_status": summary["run_status"],
        "budget": summary["budget"],
        "checks": {k: v["status"] for k, v in summary["checks"].items()},
    }, indent=2))
    return 0 if summary["run_status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
