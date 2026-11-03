import { execFileSync, execSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import {
  appendFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { createServer } from "node:net";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createBrowserCodeTool } from "@cloudflare/codemode/browser";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import {
  StdioClientTransport,
  getDefaultEnvironment,
} from "@modelcontextprotocol/sdk/client/stdio.js";
import Ajv2020 from "ajv/dist/2020.js";
import { QuickJSExecutor } from "../s1a-local/e0/quickjs-executor.mjs";
import { checkM4Protection, DEFAULT_BASE_SHA, M4_PATTERNS, S0_SHA } from "../s1a-local/m4-guard.mjs";

const P0_DIR = dirname(fileURLToPath(import.meta.url));
const CM01_DIR = dirname(P0_DIR);
const ROOT = resolve(P0_DIR, "../../..");
const S1A_DIR = join(CM01_DIR, "s1a-local");
const M1_DIR = join(S1A_DIR, "m1");
const FIXTURE = join(M1_DIR, "fixture", "canonical", "project_memory.json");
const PRE_MIGRATION = join(M1_DIR, "fixture", "pre_migration.json");
const M4_FIXTURE = join(S1A_DIR, "m4", "fixture", "canonical", "project_memory.json");
const EMPTY_CWD = join(M1_DIR, "empty-cwd");
const EVIDENCE = join(P0_DIR, "evidence");
const RAW = join(EVIDENCE, "raw");
const RELAY = join(P0_DIR, "relay.mjs");
const EXECUTOR = join(S1A_DIR, "e0", "quickjs-executor.mjs");
const M4_GUARD = join(S1A_DIR, "m4-guard.mjs");

const READ_TOOLS = [
  "decision.get",
  "decision.search",
  "decision.applicable_to",
  "decision.trace",
];
const TARGET_TOOL = "decision.get";
const TARGET_RECORD = "ADR-9901";
const CODE = `async () => codemode.decision_get({ record_id: "${TARGET_RECORD}" })`;
const TIME_PIN = {
  node: "24.13.1",
  npm: "11.8.0",
  codemode: "0.5.5",
  sdk: "1.32.2",
  ajv: "8.17.1",
  quickjs: "0.32.0",
  zod: "4.6.7",
  python: "3.12.10",
  mneme: "0.10.0",
  mcp: "2.2.0",
};

const DECLARED_BASELINE = "ddeb85eec8f7734edde1c921250592d51afedbee";
const VALIDATION_PREFIX = "validation/cm01/p0-cancellation/";

const FAULT_TIMEOUT_MS = 1500;
const OBSERVE_MS = 1500;
const LATE_MS = 3000;
const CONNECT_TIMEOUT_MS = 30000;
const WITHHOLD_TIMEOUT_MS = 8000;
const CONTROL_TIMEOUT_MS = 6000;

mkdirSync(EVIDENCE, { recursive: true });
mkdirSync(RAW, { recursive: true });
mkdirSync(EMPTY_CWD, { recursive: true });

for (const entry of ["run1", "run2"]) {
  for (const suffix of ["harness-events.jsonl"]) {
    const path = join(RAW, `${entry}-${suffix}`);
    if (existsSync(path)) rmSync(path);
  }
}

function nowIso() {
  return new Date().toISOString();
}

function sha256File(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function sha256Text(text) {
  return createHash("sha256").update(text).digest("hex");
}

function sha256GitBlob(ref, path) {
  const buffer = execFileSync("git", ["show", `${ref}:${path}`], {
    cwd: ROOT,
    maxBuffer: 32 * 1024 * 1024,
  });
  return createHash("sha256").update(buffer).digest("hex");
}

function gitLines(args) {
  const text = execFileSync("git", args, { cwd: ROOT, encoding: "utf8" }).trim();
  return text ? text.split(/\r?\n/) : [];
}

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, stable(value[key])]),
    );
  }
  return value;
}

function deepCopy(value) {
  return value === undefined ? null : JSON.parse(JSON.stringify(value));
}

function delay(ms) {
  return new Promise((resolveDelay) => setTimeout(resolveDelay, ms));
}

function processAlive(pid) {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

async function waitUntil(predicate, timeoutMs, intervalMs = 25) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (predicate()) return true;
    await delay(intervalMs);
  }
  return predicate();
}

function withTimeout(promise, ms, label) {
  let timer;
  return Promise.race([
    promise.finally(() => clearTimeout(timer)),
    new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`${label} exceeded ${ms}ms`)), ms);
    }),
  ]);
}

function makeHarnessLog(path) {
  const events = [];
  const api = {
    events,
    path,
    event(type, data = {}) {
      const event = { seq: events.length + 1, ts: nowIso(), type, ...data };
      events.push(event);
      appendFileSync(path, `${JSON.stringify(event)}\n`);
      return event;
    },
  };
  return api;
}

function createBus() {
  const listeners = new Set();
  return {
    on(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    emit(event) {
      for (const listener of [...listeners]) {
        try {
          listener(event);
        } catch {
          // Instrumentation must not alter the experiment.
        }
      }
    },
  };
}

function createControlServer() {
  const token = randomUUID();
  const events = [];
  const waiters = new Set();
  let relaySocket = null;
  let helloResolve;
  const hello = new Promise((resolveHello) => {
    helloResolve = resolveHello;
  });
  const server = createServer((socket) => {
    let buffer = "";
    socket.on("data", (chunk) => {
      buffer += chunk.toString("utf8");
      let index;
      while ((index = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, index);
        buffer = buffer.slice(index + 1);
        if (!line.trim()) continue;
        let message;
        try {
          message = JSON.parse(line);
        } catch {
          continue;
        }
        if (message.role === "relay" && message.token === token) {
          relaySocket = socket;
          helloResolve({ ok: true, ts: nowIso() });
          continue;
        }
        if (message && message.type) {
          events.push(message);
          for (const waiter of [...waiters]) waiter.test(message);
        }
      }
    });
    socket.on("error", () => {});
    socket.on("close", () => {
      if (socket === relaySocket) relaySocket = null;
    });
  });
  const api = {
    token,
    events,
    port: null,
    listening: null,
    async waitForConnection(timeoutMs) {
      const started = Date.now();
      const result = await Promise.race([
        hello,
        delay(timeoutMs).then(() => ({ ok: false, ts: nowIso() })),
      ]);
      return { ...result, elapsed_ms: Date.now() - started };
    },
    waitFor(predicate, timeoutMs, { after = 0 } = {}) {
      const found = events.slice(after).find(predicate);
      if (found) return Promise.resolve({ found: true, event: found, elapsed_ms: 0 });
      return new Promise((resolveWait) => {
        const started = Date.now();
        const waiter = {
          test(event) {
            if (!predicate(event)) return;
            clearTimeout(timer);
            waiters.delete(waiter);
            resolveWait({ found: true, event, elapsed_ms: Date.now() - started });
          },
        };
        const timer = setTimeout(() => {
          waiters.delete(waiter);
          resolveWait({ found: false, event: null, elapsed_ms: Date.now() - started });
        }, timeoutMs);
        waiters.add(waiter);
      });
    },
    send(command) {
      if (!relaySocket || relaySocket.destroyed) return false;
      relaySocket.write(`${JSON.stringify(command)}\n`);
      return true;
    },
    close() {
      try {
        relaySocket?.end();
      } catch {
        // ignore
      }
      try {
        server.close();
      } catch {
        // ignore
      }
    },
  };
  api.listening = new Promise((resolveListen, rejectListen) => {
    server.once("error", rejectListen);
    server.listen(0, "127.0.0.1", () => {
      server.removeListener("error", rejectListen);
      server.on("error", () => {});
      api.port = server.address().port;
      resolveListen();
    });
  });
  return api;
}

function instrumentTransport(transport, bus, harness, phase) {
  const originalSend = transport.send.bind(transport);
  transport.send = (message, options) => {
    harness.event("transport_send", { phase, message });
    bus.emit({ type: "transport_send", message });
    if (message?.method === "notifications/cancelled") {
      bus.emit({ type: "cancellation_sent", message });
    }
    return originalSend(message, options);
  };
}

function wrapIncoming(transport, bus, harness, phase) {
  const previous = transport.onmessage;
  transport.onmessage = (message, extra) => {
    harness.event("transport_receive", { phase, message });
    bus.emit({ type: "transport_receive", message });
    previous?.(message, extra);
  };
}

async function connectDirect(phase, harness, bus) {
  const stderrChunks = [];
  const transport = new StdioClientTransport({
    command: process.env.CM01_PYTHON || "python",
    args: [
      "-m",
      "mneme",
      "decision-mcp",
      "--memory",
      FIXTURE,
      "--proposals",
      "",
    ],
    cwd: EMPTY_CWD,
    env: {
      ...getDefaultEnvironment(),
      PYTHONPATH: ROOT,
      PYTHONIOENCODING: "utf-8",
    },
    stderr: "pipe",
  });
  instrumentTransport(transport, bus, harness, phase);
  transport.stderr?.on("data", (chunk) => stderrChunks.push(chunk.toString("utf8")));
  const client = new Client({ name: "cm01-p0", version: "0.1.0" });
  client.onclose = () => bus.emit({ type: "client_closed" });
  client.onerror = (error) =>
    bus.emit({ type: "client_error", message: error?.message || String(error) });
  await withTimeout(client.connect(transport), CONNECT_TIMEOUT_MS, "direct connect");
  wrapIncoming(transport, bus, harness, phase);
  const inventory = await withTimeout(client.listTools(), CONNECT_TIMEOUT_MS, "listTools");
  harness.event("connected_direct", {
    phase,
    pid: transport.pid ?? null,
    tool_count: inventory.tools.length,
  });
  return {
    client,
    transport,
    inventory,
    pid: transport.pid ?? null,
    stderrText: () => stderrChunks.join(""),
  };
}

async function connectRelay(phase, harness, bus, mode) {
  const control = createControlServer();
  await control.listening;
  const port = control.port;
  if (!port) {
    control.close();
    throw new Error("control server did not expose a port");
  }
  const eventLog = join(RAW, `${harness.run}-${phase}-relay.jsonl`);
  const childStderr = join(RAW, `${harness.run}-${phase}-child-stderr.log`);
  const childEvents = join(RAW, `${harness.run}-${phase}-child-events.jsonl`);
  if (existsSync(eventLog)) rmSync(eventLog);
  if (existsSync(childStderr)) rmSync(childStderr);
  if (existsSync(childEvents)) rmSync(childEvents);
  const stderrChunks = [];
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: [RELAY],
    cwd: P0_DIR,
    env: {
      ...getDefaultEnvironment(),
      CM01_PYTHON: process.env.CM01_PYTHON || "python",
      CM01_ROOT: ROOT,
      CM01_FIXTURE: FIXTURE,
      CM01_EMPTY_CWD: EMPTY_CWD,
      CM01_CONTROL_PORT: String(port),
      CM01_CONTROL_TOKEN: control.token,
      CM01_RELAY_MODE: mode,
      CM01_EVENT_LOG: eventLog,
      CM01_CHILD_STDERR: childStderr,
      CM01_CHILD_EVENT_LOG: childEvents,
      CM01_TARGET_TOOL: TARGET_TOOL,
      CM01_TARGET_RECORD: TARGET_RECORD,
    },
    stderr: "pipe",
  });
  instrumentTransport(transport, bus, harness, phase);
  transport.stderr?.on("data", (chunk) => stderrChunks.push(chunk.toString("utf8")));
  const client = new Client({ name: "cm01-p0", version: "0.1.0" });
  client.onclose = () => bus.emit({ type: "client_closed" });
  client.onerror = (error) =>
    bus.emit({ type: "client_error", message: error?.message || String(error) });

  const connection = await control.waitForConnection(CONNECT_TIMEOUT_MS);
  harness.event("relay_control_connected", { phase, connection });
  await withTimeout(client.connect(transport), CONNECT_TIMEOUT_MS, "relay connect");
  wrapIncoming(transport, bus, harness, phase);
  const inventory = await withTimeout(client.listTools(), CONNECT_TIMEOUT_MS, "listTools");
  harness.event("connected_relay", {
    phase,
    mode,
    relay_pid: transport.pid ?? null,
    tool_count: inventory.tools.length,
  });
  return {
    client,
    transport,
    inventory,
    control,
    pid: transport.pid ?? null,
    eventLog,
    childStderr,
    childEvents,
    stderrText: () => stderrChunks.join(""),
  };
}

async function cleanupDirect(ctx, harness, phase) {
  const result = { phase, errors: [], client_pid: ctx.pid ?? null };
  try {
    await ctx.client.close();
  } catch (error) {
    result.errors.push(`client.close: ${error?.message || String(error)}`);
  }
  const exited = ctx.pid ? await waitUntil(() => !processAlive(ctx.pid), 5000) : true;
  result.server_alive_after = ctx.pid ? processAlive(ctx.pid) : false;
  result.server_exit_observed = exited;
  writeFileSync(join(RAW, `${harness.run}-${phase}-child-stderr.log`), ctx.stderrText());
  harness.event("cleanup_direct", result);
  return result;
}

async function cleanupRelay(ctx, harness, phase) {
  const result = { phase, errors: [], child_event_log: ctx.childEvents ?? null };
  const relayStart = ctx.control.events.find((event) => event.type === "relay_start");
  const upstreamPid = relayStart?.upstream_pid ?? null;
  const before = ctx.control.events.length;
  ctx.control.send({ cmd: "shutdown", at: nowIso() });
  const childExit = await ctx.control.waitFor(
    (event) => event.type === "child_exit",
    CONTROL_TIMEOUT_MS,
    { after: before },
  );
  result.child_exit_event = childExit.event;
  result.child_exit_observed = childExit.found;
  try {
    await ctx.client.close();
  } catch (error) {
    result.errors.push(`client.close: ${error?.message || String(error)}`);
  }
  const relayGone = ctx.pid ? await waitUntil(() => !processAlive(ctx.pid), 5000) : true;
  result.relay_pid = ctx.pid ?? null;
  result.relay_alive_after = ctx.pid ? processAlive(ctx.pid) : false;
  result.relay_exit_observed = relayGone;
  const upstreamGone = upstreamPid
    ? await waitUntil(() => !processAlive(upstreamPid), 5000)
    : true;
  result.upstream_pid = upstreamPid;
  result.upstream_alive_after = upstreamPid ? processAlive(upstreamPid) : false;
  result.upstream_exit_observed = upstreamGone;
  writeFileSync(join(RAW, `${harness.run}-${phase}-relay-stderr.log`), ctx.stderrText());
  ctx.control.close();
  harness.event("cleanup_relay", result);
  return result;
}

function createTracker(bus) {
  const calls = [];
  let current = null;
  const waiters = new Set();

  function snapshot(state) {
    if (!state) return null;
    return {
      seq: state.seq,
      name: state.name,
      args: state.args,
      request_id: state.request_id,
      started_at: state.started_at,
      pending: state.pending,
      outcome: state.outcome,
      settled_at: state.settled_at,
      error: state.error,
      adapter_error: state.adapter_error,
    };
  }

  function notify(event, state) {
    bus.emit(event);
    for (const waiter of [...waiters]) {
      if (waiter.state !== state) continue;
      waiters.delete(waiter);
      clearTimeout(waiter.timer);
      waiter.resolve({ found: true, elapsed_ms: Date.now() - waiter.started, state: snapshot(state) });
    }
  }

  return {
    calls,
    snapshot,
    currentState: () => current,
    begin(name, args) {
      const state = {
        seq: calls.length + 1,
        name,
        args,
        request_id: null,
        started_at: nowIso(),
        started_ms: Date.now(),
        pending: true,
        outcome: null,
        settled_at: null,
        settled_ms: null,
        error: null,
        adapter_error: null,
      };
      calls.push(state);
      current = state;
      return state;
    },
    invoke(client, params, state) {
      let promise;
      try {
        promise = client.callTool(params);
      } catch (error) {
        state.pending = false;
        state.outcome = "threw";
        state.error = error?.message || String(error);
        state.settled_at = nowIso();
        notify({ type: "client_settled", state: snapshot(state) }, state);
        throw error;
      }
      promise.then(
        (value) => {
          state.pending = false;
          state.outcome = "fulfilled";
          state.settled_at = nowIso();
          state.settled_ms = Date.now();
          state.result_is_error = Boolean(value?.isError);
          state.result_record_type = value?.structuredContent?.record_type ?? null;
          notify({ type: "client_settled", state: snapshot(state) }, state);
        },
        (error) => {
          state.pending = false;
          state.outcome = "rejected";
          state.error = error?.message || String(error);
          state.settled_at = nowIso();
          state.settled_ms = Date.now();
          notify({ type: "client_settled", state: snapshot(state) }, state);
        },
      );
      return promise;
    },
    nextSettlement(state, timeoutMs) {
      if (!state) return Promise.resolve({ found: false, state: null, elapsed_ms: 0 });
      if (!state.pending) {
        return Promise.resolve({ found: true, state: snapshot(state), elapsed_ms: 0 });
      }
      return new Promise((resolveWait) => {
        const started = Date.now();
        const waiter = {
          state,
          started,
          resolve: resolveWait,
          timer: setTimeout(() => {
            waiters.delete(waiter);
            resolveWait({ found: false, state: snapshot(state), elapsed_ms: Date.now() - started });
          }, timeoutMs),
        };
        waiters.add(waiter);
      });
    },
  };
}

function textContent(result) {
  if (!Array.isArray(result.content)) return "";
  return result.content
    .filter((part) => part.type === "text")
    .map((part) => part.text ?? "")
    .join("\n");
}

function normalizeMcpSuccess(toolName, result) {
  if (result.structuredContent != null) return result.structuredContent;
  if (result.toolResult !== undefined) return result.toolResult;
  const text = textContent(result);
  if (!text) throw new Error(`MCP ${toolName} returned no structured result`);
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`MCP ${toolName} returned non-JSON text`);
  }
}

function makeValidators(inventory) {
  const ajv = new Ajv2020({ strict: false, allErrors: true });
  const validators = new Map();
  for (const name of READ_TOOLS) {
    const tool = inventory.tools.find((candidate) => candidate.name === name);
    if (!tool) throw new Error(`missing upstream tool ${name}`);
    validators.set(name, ajv.compile(tool.inputSchema));
  }
  return validators;
}

function makeAdapter({ client, inventory, validators, executor, tracker, validate = true }) {
  const callLog = [];
  const descriptors = {};
  const byName = new Map(inventory.tools.map((tool) => [tool.name, tool]));

  for (const name of READ_TOOLS) {
    const tool = byName.get(name);
    if (!tool) throw new Error(`missing upstream tool ${name}`);
    descriptors[name] = {
      description: tool.description,
      inputSchema: tool.inputSchema,
      execute: async (args) => {
        if (validate) {
          const validator = validators.get(name);
          if (!validator(args)) {
            throw new Error(
              `Argument validation failed for ${name}: ${JSON.stringify(validator.errors ?? null)}`,
            );
          }
        }
        const seq = callLog.length + 1;
        const state = tracker.begin(name, args);
        let result;
        try {
          result = await tracker.invoke(client, { name, arguments: args }, state);
        } catch (error) {
          const message = error?.message || String(error);
          callLog.push({ seq, tool: name, args, error: message });
          state.adapter_error = message;
          throw new Error(`MCP ${name} error: ${message}`);
        }
        const entry = {
          seq,
          tool: name,
          args,
          isError: Boolean(result.isError),
          structuredContent: result.structuredContent ?? null,
          toolResult: result.toolResult ?? null,
          text: textContent(result),
        };
        callLog.push(entry);
        if (result.isError) {
          throw new Error(`MCP ${name} error: ${entry.text || "tool returned isError"}`);
        }
        return normalizeMcpSuccess(name, result);
      },
    };
  }

  return {
    tool: createBrowserCodeTool({ tools: descriptors, executor }),
    callLog,
  };
}

async function executeWith(tool, code, executor) {
  try {
    const output = await tool.execute({ code });
    return { result: output.result ?? null, error: null, stats: deepCopy(executor.stats()) };
  } catch (error) {
    return {
      result: null,
      error: error?.message || String(error),
      error_name: error?.name || null,
      stats: deepCopy(executor.stats()),
    };
  }
}

function canonicalGetOk(result) {
  return (
    result?.record_type === "canonical_decision" &&
    result?.canonical_decision?.decision_id === TARGET_RECORD
  );
}

function observeWindow({ bus, state, ms }) {
  return new Promise((resolveWindow) => {
    const started = Date.now();
    let settled = false;
    const finish = (reason, event = null) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      unsubscribe();
      resolveWindow({ reason, event, elapsed_ms: Date.now() - started });
    };
    const unsubscribe = bus.on((event) => {
      if (event.type === "client_settled" && event.state?.seq === state?.seq) {
        finish("client_settled", event);
      } else if (event.type === "cancellation_sent") {
        finish("cancellation_sent", event);
      } else if (event.type === "client_closed") {
        finish("client_closed", event);
      } else if (event.type === "client_error") {
        finish("client_error", event);
      }
    });
    const timer = setTimeout(() => finish("window_elapsed"), ms);
    if (state && !state.pending) finish("already_settled");
  });
}

function countCancellationMessages(events) {
  return events.filter(
    (entry) =>
      entry.type === "transport_send" &&
      entry.message?.method === "notifications/cancelled",
  ).length;
}

async function phaseControlDirect(run) {
  const phase = "control-direct";
  const harness = makeHarnessLog(join(RAW, `${run}-harness-events.jsonl`));
  harness.run = run;
  const bus = createBus();
  let ctx = null;
  const result = { phase, ok: false, started_at: nowIso() };
  try {
    ctx = await connectDirect(phase, harness, bus);
    const executor = new QuickJSExecutor({ timeoutMs: 10000, memoryLimitBytes: 8 * 1024 * 1024 });
    const tracker = createTracker(bus);
    bus.on((event) => {
      if (event.type !== "transport_send") return;
      const message = event.message;
      if (message?.method !== "tools/call") return;
      const state = tracker.currentState();
      if (state && state.pending && state.request_id === null) {
        state.request_id = message.id ?? null;
      }
    });
    const adapter = makeAdapter({
      client: ctx.client,
      inventory: ctx.inventory,
      validators: makeValidators(ctx.inventory),
      executor,
      tracker,
      validate: true,
    });
    const outcome = await executeWith(adapter.tool, CODE, executor);
    const state = tracker.currentState();
    result.outcome = outcome;
    result.call = tracker.snapshot(state);
    result.adapter_calls = adapter.callLog;
    result.canonical_get_ok = canonicalGetOk(outcome.result);
    result.ok = result.canonical_get_ok && !outcome.error && state?.outcome === "fulfilled";
    harness.event("control_direct_result", {
      phase,
      ok: result.ok,
      canonical_get_ok: result.canonical_get_ok,
      error: outcome.error,
      call: result.call,
    });
  } catch (error) {
    result.error = error?.message || String(error);
    harness.event("control_direct_error", { phase, error: result.error });
  } finally {
    if (ctx) result.cleanup = await cleanupDirect(ctx, harness, phase);
    result.finished_at = nowIso();
  }
  return result;
}

async function phaseControlRelay(run) {
  const phase = "control-relay";
  const harness = makeHarnessLog(join(RAW, `${run}-harness-events.jsonl`));
  harness.run = run;
  const bus = createBus();
  let ctx = null;
  const result = { phase, ok: false, started_at: nowIso() };
  try {
    ctx = await connectRelay(phase, harness, bus, "passthrough");
    const executor = new QuickJSExecutor({ timeoutMs: 10000, memoryLimitBytes: 8 * 1024 * 1024 });
    const tracker = createTracker(bus);
    bus.on((event) => {
      if (event.type !== "transport_send") return;
      const message = event.message;
      if (message?.method !== "tools/call") return;
      const state = tracker.currentState();
      if (state && state.pending && state.request_id === null) {
        state.request_id = message.id ?? null;
      }
    });
    const adapter = makeAdapter({
      client: ctx.client,
      inventory: ctx.inventory,
      validators: makeValidators(ctx.inventory),
      executor,
      tracker,
      validate: true,
    });
    const outcome = await executeWith(adapter.tool, CODE, executor);
    const state = tracker.currentState();
    result.outcome = outcome;
    result.call = tracker.snapshot(state);
    result.adapter_calls = adapter.callLog;
    result.canonical_get_ok = canonicalGetOk(outcome.result);
    const started = ctx.control.events.length;
    ctx.control.send({ cmd: "status", at: nowIso() });
    const status = await ctx.control.waitFor(
      (event) => event.type === "status",
      CONTROL_TIMEOUT_MS,
      { after: started },
    );
    result.relay_status = status.event;
    result.relay_events = {
      target_seen: ctx.control.events.some((event) => event.type === "target_request_seen"),
      target_forwarded: ctx.control.events.some(
        (event) => event.type === "target_request_forwarded",
      ),
      upstream_response_received: ctx.control.events.some(
        (event) => event.type === "upstream_response_received",
      ),
      response_withheld: ctx.control.events.some((event) => event.type === "response_withheld"),
      response_forwarded: ctx.control.events.some(
        (event) => event.type === "upstream_message_forwarded_downstream",
      ),
    };
    result.ok =
      result.canonical_get_ok &&
      !outcome.error &&
      state?.outcome === "fulfilled" &&
      result.relay_events.target_forwarded &&
      result.relay_events.upstream_response_received &&
      result.relay_events.response_withheld === false;
    harness.event("control_relay_result", {
      phase,
      ok: result.ok,
      canonical_get_ok: result.canonical_get_ok,
      relay_events: result.relay_events,
      error: outcome.error,
      call: result.call,
    });
  } catch (error) {
    result.error = error?.message || String(error);
    harness.event("control_relay_error", { phase, error: result.error });
  } finally {
    if (ctx) result.cleanup = await cleanupRelay(ctx, harness, phase);
    result.finished_at = nowIso();
  }
  return result;
}

async function phaseFault(run) {
  const phase = "fault";
  const harness = makeHarnessLog(join(RAW, `${run}-harness-events.jsonl`));
  harness.run = run;
  const bus = createBus();
  let ctx = null;
  const result = { phase, started_at: nowIso(), timeout_ms: FAULT_TIMEOUT_MS };
  try {
    ctx = await connectRelay(phase, harness, bus, "withhold");
    const tracker = createTracker(bus);
    bus.on((event) => {
      if (event.type !== "transport_send") return;
      const message = event.message;
      if (message?.method !== "tools/call") return;
      const state = tracker.currentState();
      if (state && state.pending && state.request_id === null) {
        state.request_id = message.id ?? null;
      }
    });
    const executor = new QuickJSExecutor({
      timeoutMs: FAULT_TIMEOUT_MS,
      memoryLimitBytes: 8 * 1024 * 1024,
      onCleanup: () => {
        harness.event("executor_cleanup", {
          phase,
          at: nowIso(),
          client_call: tracker.snapshot(tracker.currentState()),
          note: "executor assigns lastStats after onCleanup, so stats are recorded from the execution outcome instead",
        });
      },
    });
    const adapter = makeAdapter({
      client: ctx.client,
      inventory: ctx.inventory,
      validators: makeValidators(ctx.inventory),
      executor,
      tracker,
      validate: true,
    });

    const execStartedMs = Date.now();
    const execPromise = executeWith(adapter.tool, CODE, executor);
    const withheld = await ctx.control.waitFor(
      (event) => event.type === "response_withheld",
      WITHHOLD_TIMEOUT_MS,
    );
    result.withheld_event = withheld.event;
    result.withheld_observed = withheld.found;
    const execOutcome = await execPromise;
    const execFinishedMs = Date.now();
    const state = tracker.currentState();
    result.execution = {
      ...execOutcome,
      duration_ms: execFinishedMs - execStartedMs,
      finished_at: nowIso(),
    };
    result.adapter_calls = adapter.callLog;
    const atTimeout = tracker.snapshot(state);
    result.client_side = {
      request: {
        id: state?.request_id ?? null,
        tool: state?.name ?? null,
        args: state?.args ?? null,
        method: "tools/call",
      },
      at_timeout_return: atTimeout,
      pending_after_timeout_return: atTimeout?.pending === true,
    };
    const observation = await observeWindow({ bus, state, ms: OBSERVE_MS });
    const afterWindow = tracker.snapshot(state);
    result.observation = {
      window_ms: OBSERVE_MS,
      ...observation,
      client_after_window: afterWindow,
      pending_after_window: afterWindow?.pending === true,
    };

    const statusIndex = ctx.control.events.length;
    ctx.control.send({ cmd: "status", at: nowIso() });
    const status = await ctx.control.waitFor(
      (event) => event.type === "status",
      CONTROL_TIMEOUT_MS,
      { after: statusIndex },
    );
    result.server_side = {
      relay_status_at_observation: status.event,
      relay_events: {
        target_seen: ctx.control.events.some((event) => event.type === "target_request_seen"),
        target_forwarded: ctx.control.events.some(
          (event) => event.type === "target_request_forwarded",
        ),
        upstream_response_received: ctx.control.events.some(
          (event) => event.type === "upstream_response_received",
        ),
        response_withheld: ctx.control.events.some((event) => event.type === "response_withheld"),
      },
      cancellation_events_forwarded: ctx.control.events.filter(
        (event) => event.type === "cancel_from_client",
      ),
    };

    const beforeRelease = {
      ts: nowIso(),
      client_pending: tracker.currentState()?.pending === true,
      cancellation_messages: countCancellationMessages(harness.events),
      transport_messages_out: harness.events.filter((event) => event.type === "transport_send")
        .length,
      transport_messages_in: harness.events.filter((event) => event.type === "transport_receive")
        .length,
    };
    result.before_release = beforeRelease;

    const releaseIndex = ctx.control.events.length;
    ctx.control.send({ cmd: "release", at: nowIso() });
    const released = await ctx.control.waitFor(
      (event) => event.type === "response_released_downstream",
      CONTROL_TIMEOUT_MS,
      { after: releaseIndex },
    );
    result.release = released.event;
    const late = await tracker.nextSettlement(tracker.currentState(), LATE_MS);
    const afterLate = tracker.snapshot(tracker.currentState());
    const postReleaseStats = deepCopy(executor.stats());
    result.late_completion = {
      window_ms: LATE_MS,
      settled: late.found,
      outcome: late.state?.outcome ?? null,
      error: late.state?.error ?? null,
      elapsed_ms: late.elapsed_ms,
      client_after_late: afterLate,
      delivered_response_observed: harness.events.some(
        (event) =>
          event.type === "transport_receive" &&
          event.message?.id === state?.request_id &&
          (event.message?.result !== undefined || event.message?.error !== undefined),
      ),
      executor_stats_before_timeout: execOutcome.stats,
      executor_stats_after_late: postReleaseStats,
      executor_resolved_calls_delta:
        (postReleaseStats?.resolvedCalls ?? 0) - (execOutcome.stats?.resolvedCalls ?? 0),
    };

    const genuine =
      result.server_side.relay_events.target_forwarded &&
      result.server_side.relay_events.upstream_response_received;
    const timeoutReturned =
      !execOutcome.result &&
      Boolean(execOutcome.error) &&
      execOutcome.stats?.timedOut === true &&
      /execution exceeded/i.test(execOutcome.error ?? "");
    const cancellationSent = countCancellationMessages(harness.events);
    const pendingAtTimeout = result.client_side.pending_after_timeout_return;
    const pendingAtWindowEnd = result.observation.pending_after_window;
    const lateSettled = late.found && late.state?.outcome === "fulfilled";
    const requiredHarnessRelease = pendingAtWindowEnd;

    result.classification = {
      genuine_upstream_request: genuine,
      timeout_error_returned: timeoutReturned,
      timeout_error: execOutcome.error,
      cancellation_notifications_sent: cancellationSent,
      cancellation_observed_by_relay: result.server_side.cancellation_events_forwarded.length,
      pending_immediately_after_timeout: pendingAtTimeout,
      pending_after_observation_window: pendingAtWindowEnd,
      observation_end_reason: observation.reason,
      late_response_settled_request: lateSettled,
      required_harness_release_to_settle: requiredHarnessRelease,
      transport_open_after_timeout: !["client_closed", "client_error"].includes(
        observation.reason,
      ),
      client_closed_after_timeout: harness.events.some(
        (event) => event.type === "client_closed",
      ),
      relay_upstream_alive_at_observation:
        result.server_side.relay_status_at_observation?.child_alive ?? null,
      direct_response_delivered_after_release:
        result.late_completion.delivered_response_observed,
    };

    if (!genuine || !timeoutReturned) {
      result.verdict = "BLOCKED";
      result.reason = !genuine
        ? "The relay could not demonstrate that the request reached the genuine MCP server and returned a response."
        : "Code Mode did not return the expected executor timeout error.";
    } else if (pendingAtTimeout || pendingAtWindowEnd || lateSettled) {
      result.verdict = "FAIL";
      const reasons = [];
      if (pendingAtTimeout) {
        reasons.push("the underlying MCP client request was still pending when Code Mode returned its timeout error");
      }
      if (pendingAtWindowEnd) {
        reasons.push(
          `the underlying MCP client request was still pending after a ${OBSERVE_MS}ms bounded observation period`,
        );
      }
      if (lateSettled) {
        reasons.push("the withheld late response still fulfilled the abandoned MCP client request");
      }
      if (cancellationSent === 0) {
        reasons.push("no notifications/cancelled was emitted by the integration");
      }
      result.reason = reasons.join("; ");
    } else {
      result.verdict = "PASS";
      result.reason = "The integration terminated or cancelled the outstanding request within the observation window.";
    }
    harness.event("fault_result", {
      phase,
      verdict: result.verdict,
      reason: result.reason,
      classification: result.classification,
      client_side: {
        request: result.client_side.request,
        at_timeout_return: result.client_side.at_timeout_return,
      },
      observation: result.observation,
      late_completion: result.late_completion,
    });
  } catch (error) {
    result.verdict = "BLOCKED";
    result.error = error?.message || String(error);
    result.reason = `Fault run could not be completed: ${result.error}`;
    harness.event("fault_error", { phase, error: result.error });
  } finally {
    if (ctx) result.cleanup = await cleanupRelay(ctx, harness, phase);
    result.finished_at = nowIso();
    result.process_cleanup_ok =
      result.cleanup?.relay_exit_observed === true &&
      result.cleanup?.upstream_exit_observed === true &&
      result.cleanup?.relay_alive_after === false &&
      result.cleanup?.upstream_alive_after === false;
  }
  return result;
}

function versions() {
  const pkg = JSON.parse(readFileSync(join(P0_DIR, "package.json"), "utf8"));
  const pythonScript = [
    "import json, sys",
    "import mneme",
    "from importlib.metadata import version",
    "print(json.dumps({",
    "  'python': sys.version.split()[0],",
    "  'mneme': getattr(mneme, '__version__', 'unknown'),",
    "  'mcp': version('mcp'),",
    "}))",
  ].join("\n");
  const py = JSON.parse(
    execFileSync(process.env.CM01_PYTHON || "python", ["-c", pythonScript], {
      cwd: EMPTY_CWD,
      env: { ...process.env, PYTHONPATH: ROOT },
      encoding: "utf8",
    }),
  );
  return {
    node: process.version,
    npm: execSync("npm --version", { encoding: "utf8" }).trim(),
    codemode: pkg.dependencies["@cloudflare/codemode"],
    sdk: pkg.dependencies["@modelcontextprotocol/sdk"],
    ajv: pkg.dependencies.ajv,
    quickjs: pkg.dependencies["quickjs-emscripten"],
    zod: pkg.dependencies.zod,
    ...py,
  };
}

function preservedHashes() {
  const files = execFileSync("git", ["ls-files", "validation/cm01/s1a-local"], {
    cwd: ROOT,
    encoding: "utf8",
  })
    .split(/\r?\n/)
    .filter(Boolean)
    .sort();
  const hashes = {};
  for (const file of files) hashes[file] = sha256File(join(ROOT, file));
  return { files: hashes, digest: sha256Text(JSON.stringify(hashes)) };
}

function s1aStatus() {
  return execFileSync("git", ["status", "--porcelain", "--", "validation/cm01/s1a-local"], {
    cwd: ROOT,
    encoding: "utf8",
  }).trim();
}

function isEmptyCwdClean() {
  const list = execFileSync("git", ["ls-files", "--others", "--exclude-standard"], {
    cwd: EMPTY_CWD,
    encoding: "utf8",
  })
    .split(/\r?\n/)
    .filter(Boolean);
  return { clean: list.length === 0, files: list };
}

function normalizedFault(run) {
  const fault = run.fault;
  return {
    verdict: fault?.verdict ?? null,
    genuine: fault?.classification?.genuine_upstream_request ?? null,
    timeout_error_returned: fault?.classification?.timeout_error_returned ?? null,
    pending_at_timeout: fault?.classification?.pending_immediately_after_timeout ?? null,
    pending_after_window: fault?.classification?.pending_after_observation_window ?? null,
    observation_end_reason: fault?.classification?.observation_end_reason ?? null,
    cancellation_notifications_sent: fault?.classification?.cancellation_notifications_sent ?? null,
    late_response_settled_request: fault?.classification?.late_response_settled_request ?? null,
    request_id_is_number: typeof fault?.client_side?.request?.id === "number",
    adapter_call_count: fault?.adapter_calls?.length ?? null,
  };
}

const startedAt = nowIso();
const preservedBefore = preservedHashes();
const s1aBefore = s1aStatus();
const emptyCwdBefore = isEmptyCwdClean();
const identities = {
  fixture: { path: FIXTURE, sha256: sha256File(FIXTURE) },
  pre_migration: { path: PRE_MIGRATION, sha256: sha256File(PRE_MIGRATION) },
  m4_fixture: { path: M4_FIXTURE, sha256: sha256File(M4_FIXTURE) },
  executor: { path: EXECUTOR, sha256: sha256File(EXECUTOR) },
  relay: { path: RELAY, sha256: sha256File(RELAY) },
  runner: { path: join(P0_DIR, "run-cancellation.mjs"), sha256: sha256File(join(P0_DIR, "run-cancellation.mjs")) },
  m4_guard: { path: M4_GUARD, sha256: sha256File(M4_GUARD) },
  package_lock: { path: join(P0_DIR, "package-lock.json"), sha256: sha256File(join(P0_DIR, "package-lock.json")) },
};
const headSha = execFileSync("git", ["rev-parse", "HEAD"], {
  cwd: ROOT,
  encoding: "utf8",
}).trim();
const baselineToHeadPaths = gitLines([
  "diff",
  "--name-only",
  `${DECLARED_BASELINE}..${headSha}`,
]);
const baselineToHeadCommits = gitLines([
  "log",
  "--format=%H %s",
  `${DECLARED_BASELINE}..${headSha}`,
]);
const codeUnderTestPathsChanged = gitLines([
  "diff",
  "--name-only",
  `${DECLARED_BASELINE}..${headSha}`,
  "--",
  "validation/cm01",
  "mneme",
]);
const baselineM4Paths = baselineToHeadPaths.filter((path) =>
  M4_PATTERNS.some((pattern) => pattern.test(path)),
);
const workingTreeDelta = gitLines([
  "status",
  "--porcelain",
  "--untracked-files=all",
]).map((line) => line.replace(/^..\s+/, ""));
const workingTreePathsOutsideValidationScope = workingTreeDelta.filter(
  (path) => !path.startsWith(VALIDATION_PREFIX),
);
const baselineIdentity = {
  executor: {
    baseline_sha256: sha256GitBlob(DECLARED_BASELINE, "validation/cm01/s1a-local/e0/quickjs-executor.mjs"),
    current_sha256: identities.executor.sha256,
  },
  fixture: {
    baseline_sha256: sha256GitBlob(DECLARED_BASELINE, "validation/cm01/s1a-local/m1/fixture/canonical/project_memory.json"),
    current_sha256: identities.fixture.sha256,
  },
  pre_migration: {
    baseline_sha256: sha256GitBlob(DECLARED_BASELINE, "validation/cm01/s1a-local/m1/fixture/pre_migration.json"),
    current_sha256: identities.pre_migration.sha256,
  },
  m4_fixture: {
    baseline_sha256: sha256GitBlob(DECLARED_BASELINE, "validation/cm01/s1a-local/m4/fixture/canonical/project_memory.json"),
    current_sha256: identities.m4_fixture.sha256,
  },
  m4_guard: {
    baseline_sha256: sha256GitBlob(DECLARED_BASELINE, "validation/cm01/s1a-local/m4-guard.mjs"),
    current_sha256: identities.m4_guard.sha256,
  },
};
for (const entry of Object.values(baselineIdentity)) {
  entry.matches_baseline = entry.baseline_sha256 === entry.current_sha256;
}
const m4WorktreeGuard = checkM4Protection({ cwd: ROOT, baseSha: headSha });
const environment = {
  versions: versions(),
  time_pin: TIME_PIN,
  platform: process.platform,
  arch: process.arch,
  node_exec_path: process.execPath,
  head: headSha,
  declared_baseline: DECLARED_BASELINE,
  s1a1_base: DEFAULT_BASE_SHA,
  s1a1_s0: S0_SHA,
  baseline_drift: {
    head_moved_since_declared_baseline: headSha !== DECLARED_BASELINE,
    paths_changed_between_baseline_and_head: baselineToHeadPaths,
    commits_between_baseline_and_head: baselineToHeadCommits,
    code_under_test_paths_changed: codeUnderTestPathsChanged,
    code_under_test_unchanged_since_declared_baseline: codeUnderTestPathsChanged.length === 0,
    note:
      "The working tree fast-forwarded to an upstream docs-only commit during the session. No path under validation/cm01 or mneme changed between the declared baseline and HEAD.",
  },
};

const runs = [];
for (const runLabel of ["run1", "run2"]) {
  const controlDirect = await phaseControlDirect(runLabel);
  const controlRelay = await phaseControlRelay(runLabel);
  const fault = await phaseFault(runLabel);
  const run = {
    run: runLabel,
    started_at: nowIso(),
    control_direct: controlDirect,
    control_relay: controlRelay,
    fault,
    controls_ok: controlDirect.ok === true && controlRelay.ok === true,
  };
  run.verdict =
    !run.controls_ok || fault.verdict === "BLOCKED" ? "BLOCKED" : fault.verdict;
  if (!run.controls_ok) {
    run.reason = "Control runs did not both complete successfully; fault classification cannot be trusted.";
  } else {
    run.reason = fault.reason;
  }
  runs.push(run);
  writeFileSync(join(EVIDENCE, `${runLabel}.json`), `${JSON.stringify(run, null, 2)}\n`);
  process.stdout.write(
    `${JSON.stringify({ run: runLabel, verdict: run.verdict, reason: run.reason })}\n`,
  );
}

const preservedAfter = preservedHashes();
const s1aAfter = s1aStatus();
const emptyCwdAfter = isEmptyCwdClean();
const repeatable =
  JSON.stringify(normalizedFault(runs[0])) === JSON.stringify(normalizedFault(runs[1]));
const noMutation =
  preservedBefore.digest === preservedAfter.digest &&
  s1aBefore === s1aAfter &&
  emptyCwdBefore.clean &&
  emptyCwdAfter.clean &&
  identities.fixture.sha256 === sha256File(FIXTURE) &&
  identities.pre_migration.sha256 === sha256File(PRE_MIGRATION) &&
  identities.m4_fixture.sha256 === sha256File(M4_FIXTURE) &&
  m4WorktreeGuard.pass &&
  workingTreePathsOutsideValidationScope.length === 0 &&
  Object.values(baselineIdentity).every((entry) => entry.matches_baseline) &&
  codeUnderTestPathsChanged.length === 0;

const failingRuns = runs.filter((run) => run.verdict === "FAIL");
const blockedRuns = runs.filter((run) => run.verdict === "BLOCKED");
const overall =
  blockedRuns.length > 0 ? "BLOCKED" : failingRuns.length > 0 ? "FAIL" : "PASS";
const verdictReasons =
  overall === "FAIL"
    ? [...new Set(failingRuns.map((run) => run.reason))]
    : overall === "BLOCKED"
      ? [...new Set(blockedRuns.map((run) => run.reason))]
      : ["Both independent runs cancelled or terminated the outstanding request within the bounded window."];

const verdict = {
  schema: "mneme.cm01.p0-cancellation.verdict/v1",
  question:
    "When the local QuickJS executor times out while awaiting a genuine MCP client.callTool() request, does the underlying MCP operation also terminate, or does it remain outstanding?",
  started_at: startedAt,
  finished_at: nowIso(),
  baseline: DECLARED_BASELINE,
  environment,
  identities,
  runs: runs.map((run) => ({
    run: run.run,
    verdict: run.verdict,
    reason: run.reason,
    controls_ok: run.controls_ok,
    fault_classification: run.fault.classification ?? null,
    client_request_id: run.fault.client_side?.request?.id ?? null,
    pending_after_timeout: run.fault.classification?.pending_immediately_after_timeout ?? null,
    pending_after_window: run.fault.classification?.pending_after_observation_window ?? null,
    cancellation_notifications_sent:
      run.fault.classification?.cancellation_notifications_sent ?? null,
    late_response_settled_request:
      run.fault.classification?.late_response_settled_request ?? null,
    process_cleanup_ok: run.fault.process_cleanup_ok ?? null,
  })),
  repeatable,
  acceptance_criteria: {
    genuine_request_reached_server: runs.every(
      (run) => run.fault.classification?.genuine_upstream_request === true,
    ),
    code_mode_returned_timeout_not_success: runs.every(
      (run) => run.fault.classification?.timeout_error_returned === true,
    ),
    integration_cancelled_or_terminated_within_window: runs.every(
      (run) =>
        run.fault.classification?.pending_after_observation_window === false ||
        run.fault.classification?.observation_end_reason !== "window_elapsed",
    ),
    no_request_pending_before_harness_cleanup: runs.every(
      (run) => run.fault.classification?.pending_after_observation_window === false,
    ),
    late_response_cannot_settle_request: runs.every(
      (run) => run.fault.classification?.late_response_settled_request === false,
    ),
    reproducible_in_two_runs: repeatable,
    no_protected_artifact_changed: noMutation,
  },
  failure_conditions_observed: {
    request_pending_after_executor_timeout: runs.some(
      (run) => run.fault.classification?.pending_immediately_after_timeout === true,
    ),
    request_pending_after_bounded_window: runs.some(
      (run) => run.fault.classification?.pending_after_observation_window === true,
    ),
    late_response_settled_request: runs.some(
      (run) => run.fault.classification?.late_response_settled_request === true,
    ),
    harness_release_required_to_settle: runs.some(
      (run) => run.fault.classification?.required_harness_release_to_settle === true,
    ),
    cancellation_notification_emitted: runs.some(
      (run) => (run.fault.classification?.cancellation_notifications_sent ?? 0) > 0,
    ),
  },
  no_mutation: {
    pass: noMutation,
    s1a_evidence_before: preservedBefore.digest,
    s1a_evidence_after: preservedAfter.digest,
    s1a_git_status_before: s1aBefore,
    s1a_git_status_after: s1aAfter,
    empty_cwd_before: emptyCwdBefore,
    empty_cwd_after: emptyCwdAfter,
    fixtures_unchanged:
      identities.fixture.sha256 === sha256File(FIXTURE) &&
      identities.pre_migration.sha256 === sha256File(PRE_MIGRATION) &&
      identities.m4_fixture.sha256 === sha256File(M4_FIXTURE),
    working_tree_delta: workingTreeDelta,
    working_tree_paths_outside_validation_scope: workingTreePathsOutsideValidationScope,
    baseline_identity: baselineIdentity,
    code_under_test_changed_since_baseline: codeUnderTestPathsChanged,
    m4_paths_added_between_baseline_and_head_by_upstream: baselineM4Paths,
  },
  m4_worktree_guard: m4WorktreeGuard,
  m4_validation_scope: {
    pass: m4WorktreeGuard.pass,
    validation_committed_changes: false,
    working_tree_paths_outside_validation_scope: workingTreePathsOutsideValidationScope,
    m4_paths_changed_by_validation: m4WorktreeGuard.violations,
    upstream_m4_docs_arrived_during_session: baselineM4Paths,
    note:
      "The guard is anchored at HEAD so it measures this validation's working-tree delta. The only baseline-to-HEAD delta is an upstream docs-only ADR-034 M4 results record fast-forwarded during the session; no commit or working-tree edit was made by this validation.",
  },
  verdict: overall,
  reason: verdictReasons.join(" | "),
  scope: {
    tests_transport_response_boundary_only: true,
    proves_server_side_cancellation_of_executing_code: false,
    production_changes: false,
    s1a1_evidence_modified: false,
    adr034_m4_modified: false,
  },
  observation_notes: {
    executor_timeout_ms: FAULT_TIMEOUT_MS,
    post_timeout_observation_window_ms: OBSERVE_MS,
    mcp_sdk_default_request_timeout_ms: 60000,
    abort_signal_passed_to_call_tool: false,
    sdk_cancellation_trigger:
      "MCP SDK 1.32.2 Protocol.request sends notifications/cancelled only when an AbortSignal aborts or its own request timeout fires; the M2 adapter passes no options or signal.",
    pending_at_end_not_used_as_cancellation_evidence: true,
    server_side_operation_state_at_withhold:
      "The genuine upstream server had already returned its response before withholding; this experiment measures the client/transport boundary, not server-side cancellation of executing tool code.",
  },
  limitations: [
    "One fault phase per run at the transport-response boundary; no server-side cancellation of executing code is proven.",
    "The withheld response is released by the harness after measurement; that release is the late-completion probe, not cleanup.",
    "The 60s MCP SDK default request timeout is deliberately not exercised, so a cancellation at 60s would not be attributable to Code Mode.",
    "No production implementation, S1-A2, ADR-034 M4, enforcement, performance, or closure claim is made.",
  ],
  smallest_correction_boundary:
    overall === "FAIL"
      ? "Host-call boundary only: the adapter/executor bridge would need to propagate an AbortSignal (or equivalent cancellation token) from QuickJS timeout cleanup into client.callTool(), then await transport-level settlement. No server-side cancellation of already-executing tool code is implied."
      : null,
};

writeFileSync(join(EVIDENCE, "verdict.json"), `${JSON.stringify(verdict, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "versions.json"), `${JSON.stringify(environment, null, 2)}\n`);
process.stdout.write(`${JSON.stringify({ verdict: overall, reason: verdict.reason, repeatable, noMutation })}\n`);
process.stdout.write(`${JSON.stringify(verdict.runs, null, 2)}\n`);
process.exit(overall === "PASS" ? 0 : overall === "FAIL" ? 1 : 2);
