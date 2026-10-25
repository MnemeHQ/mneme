import { execFileSync, execSync } from "node:child_process";
import { createHash } from "node:crypto";
import { appendFileSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as delay } from "node:timers/promises";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import {
  StdioClientTransport,
  getDefaultEnvironment,
} from "@modelcontextprotocol/sdk/client/stdio.js";
import Ajv2020 from "ajv/dist/2020.js";

export const F1_DIR = dirname(fileURLToPath(import.meta.url));
export const CM01_DIR = dirname(F1_DIR);
export const ROOT = resolve(F1_DIR, "../../..");
export const S1A_DIR = join(CM01_DIR, "s1a-local");
export const P0_DIR = join(CM01_DIR, "p0-cancellation");
export const M4_FIXTURE = join(S1A_DIR, "m4", "fixture", "canonical", "project_memory.json");
export const EMPTY_CWD = join(F1_DIR, "empty-cwd");
export const RELAY = join(F1_DIR, "relay.mjs");
export const SYNTHETIC_SERVER = join(F1_DIR, "synthetic-server.mjs");
export const READ_TOOLS = [
  "decision.get",
  "decision.search",
  "decision.applicable_to",
  "decision.trace",
];

export const CONNECT_TIMEOUT_MS = 30000;
export const CONTROL_TIMEOUT_MS = 8000;

export function nowIso() {
  return new Date().toISOString();
}

export function sha256File(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

export function sha256Text(text) {
  return createHash("sha256").update(text).digest("hex");
}

export function sha256GitBlob(ref, path) {
  const buffer = execFileSync("git", ["show", `${ref}:${path}`], {
    cwd: ROOT,
    maxBuffer: 32 * 1024 * 1024,
  });
  return createHash("sha256").update(buffer).digest("hex");
}

export function gitLines(args) {
  const text = execFileSync("git", args, { cwd: ROOT, encoding: "utf8" }).trim();
  return text ? text.split(/\r?\n/) : [];
}

export function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

export function readJsonl(path) {
  if (!existsSync(path)) return [];
  return readFileSync(path, "utf8")
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

export function processAlive(pid) {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

export async function waitUntil(predicate, timeoutMs, intervalMs = 25) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (predicate()) return true;
    await delay(intervalMs);
  }
  return predicate();
}

export function withTimeout(promise, ms, label) {
  let timer;
  return Promise.race([
    promise.finally(() => clearTimeout(timer)),
    new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`${label} exceeded ${ms}ms`)), ms);
    }),
  ]);
}

export function makeHarnessLog(path) {
  mkdirSync(dirname(path), { recursive: true });
  const events = [];
  return {
    path,
    events,
    event(type, data = {}) {
      const event = { seq: events.length + 1, ts: nowIso(), type, ...data };
      events.push(event);
      appendFileSync(path, `${JSON.stringify(event)}\n`);
      return event;
    },
  };
}

export function createControlServer() {
  const token = createHash("sha256").update(`${process.pid}-${Date.now()}-${Math.random()}`).digest("hex");
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

export function instrumentTransport(transport, log, observer) {
  const originalSend = transport.send.bind(transport);
  transport.send = (message, options) => {
    log.push({ dir: "out", ts: nowIso(), message });
    observer.tracker?.noteOutbound(message);
    return originalSend(message, options);
  };
}

export function wrapIncoming(transport, log) {
  const previous = transport.onmessage;
  transport.onmessage = (message, extra) => {
    log.push({ dir: "in", ts: nowIso(), message });
    previous?.(message, extra);
  };
}

function baseConnect({
  command,
  args,
  env,
  cwd,
  log,
  observer,
  onclose,
  onerror,
}) {
  const transport = new StdioClientTransport({
    command,
    args,
    cwd,
    env,
    stderr: "pipe",
  });
  const stderrChunks = [];
  transport.stderr?.on("data", (chunk) => stderrChunks.push(chunk.toString("utf8")));
  instrumentTransport(transport, log, observer);
  const client = new Client({ name: "cm01-f1", version: "0.1.0" });
  client.onclose = () => onclose?.();
  client.onerror = (error) => onerror?.(error);
  return { transport, client, stderrText: () => stderrChunks.join("") };
}

export async function connectDirect({
  phase,
  logPath,
  harness,
  fixture = M4_FIXTURE,
}) {
  const log = [];
  const observer = { tracker: null };
  const clientErrors = [];
  const { transport, client, stderrText } = baseConnect({
    command: process.env.CM01_PYTHON || "python",
    args: ["-m", "mneme", "decision-mcp", "--memory", fixture, "--proposals", ""],
    cwd: EMPTY_CWD,
    env: { ...getDefaultEnvironment(), PYTHONPATH: ROOT, PYTHONIOENCODING: "utf-8" },
    log,
    observer,
    onclose: () => harness.event("client_closed", { phase }),
    onerror: (error) => {
      const message = error?.message || String(error);
      clientErrors.push(message);
      harness.event("client_error", { phase, message });
    },
  });
  await withTimeout(client.connect(transport), CONNECT_TIMEOUT_MS, `${phase} connect`);
  wrapIncoming(transport, log);
  const inventory = await withTimeout(client.listTools(), CONNECT_TIMEOUT_MS, `${phase} listTools`);
  harness.event("connected_direct", { phase, pid: transport.pid ?? null, tools: inventory.tools.length });
  return {
    kind: "direct",
    phase,
    client,
    transport,
    inventory,
    pid: transport.pid ?? null,
    log,
    observer,
    clientErrors,
    stderrText,
    logPath,
  };
}

export async function connectRelay({
  run,
  phase,
  harness,
  mode = "passthrough",
  withholdTools = [],
  delayMs = 0,
  fixture = M4_FIXTURE,
}) {
  const control = createControlServer();
  await control.listening;
  const relayLog = join(dirname(harness.path), `${run}-${phase}-relay.jsonl`);
  const childEvents = join(dirname(harness.path), `${run}-${phase}-child-events.jsonl`);
  const childStderr = join(dirname(harness.path), `${run}-${phase}-child-stderr.log`);
  const relayStderr = join(dirname(harness.path), `${run}-${phase}-relay-stderr.log`);
  for (const path of [relayLog, childEvents, childStderr]) {
    if (existsSync(path)) rmSync(path);
  }
  const log = [];
  const observer = { tracker: null };
  const clientErrors = [];
  const { transport, client, stderrText } = baseConnect({
    command: process.execPath,
    args: [RELAY],
    cwd: F1_DIR,
    env: {
      ...getDefaultEnvironment(),
      CM01_PYTHON: process.env.CM01_PYTHON || "python",
      CM01_ROOT: ROOT,
      CM01_FIXTURE: fixture,
      CM01_EMPTY_CWD: EMPTY_CWD,
      CM01_CONTROL_PORT: String(control.port),
      CM01_CONTROL_TOKEN: control.token,
      CM01_RELAY_MODE: mode,
      CM01_WITHHOLD_TOOLS: withholdTools.join(","),
      CM01_DELAY_MS: String(delayMs),
      CM01_EVENT_LOG: relayLog,
      CM01_CHILD_EVENT_LOG: childEvents,
      CM01_CHILD_STDERR: childStderr,
    },
    log,
    observer,
    onclose: () => harness.event("client_closed", { phase }),
    onerror: (error) => {
      const message = error?.message || String(error);
      clientErrors.push(message);
      harness.event("client_error", { phase, message });
    },
  });
  const connectPromise = withTimeout(
    client.connect(transport),
    CONNECT_TIMEOUT_MS,
    `${phase} connect`,
  );
  const connection = await control.waitForConnection(CONNECT_TIMEOUT_MS);
  harness.event("control_connected", { phase, connection });
  await connectPromise;
  wrapIncoming(transport, log);
  const inventory = await withTimeout(client.listTools(), CONNECT_TIMEOUT_MS, `${phase} listTools`);
  const relayStart = control.events.find((event) => event.type === "relay_start");
  harness.event("connected_relay", {
    phase,
    mode,
    delay_ms: delayMs,
    withhold_tools: withholdTools,
    relay_pid: transport.pid ?? null,
    upstream_pid: relayStart?.upstream_pid ?? null,
    tools: inventory.tools.length,
  });
  return {
    kind: "relay",
    phase,
    client,
    transport,
    inventory,
    control,
    pid: transport.pid ?? null,
    upstreamPid: relayStart?.upstream_pid ?? null,
    log,
    observer,
    clientErrors,
    relayLog,
    childEvents,
    childStderr,
    relayStderr,
    stderrText,
  };
}

export async function connectSynthetic({ phase, harness, syntheticLog }) {
  const log = [];
  const observer = { tracker: null };
  const clientErrors = [];
  const { transport, client, stderrText } = baseConnect({
    command: process.execPath,
    args: [SYNTHETIC_SERVER],
    cwd: F1_DIR,
    env: {
      ...getDefaultEnvironment(),
      CM01_SYNTHETIC_LOG: syntheticLog,
    },
    log,
    observer,
    onclose: () => harness.event("client_closed", { phase }),
    onerror: (error) => {
      const message = error?.message || String(error);
      clientErrors.push(message);
      harness.event("client_error", { phase, message });
    },
  });
  await withTimeout(client.connect(transport), CONNECT_TIMEOUT_MS, `${phase} connect`);
  wrapIncoming(transport, log);
  const inventory = await withTimeout(client.listTools(), CONNECT_TIMEOUT_MS, `${phase} listTools`);
  harness.event("connected_synthetic", {
    phase,
    pid: transport.pid ?? null,
    tools: inventory.tools.map((tool) => tool.name),
  });
  return {
    kind: "synthetic",
    phase,
    client,
    transport,
    inventory,
    pid: transport.pid ?? null,
    log,
    observer,
    clientErrors,
    syntheticLog,
    stderrText,
  };
}

export async function cleanupDirect(ctx, harness) {
  const result = { kind: "direct", phase: ctx.phase, errors: [], pid: ctx.pid };
  try {
    await ctx.client.close();
  } catch (error) {
    result.errors.push(`client.close: ${error?.message || String(error)}`);
  }
  result.server_exit_observed = ctx.pid ? await waitUntil(() => !processAlive(ctx.pid), 5000) : true;
  result.server_alive_after = ctx.pid ? processAlive(ctx.pid) : false;
  harness.event("cleanup_direct", result);
  return result;
}

export async function cleanupRelay(ctx, harness) {
  const result = {
    kind: "relay",
    phase: ctx.phase,
    errors: [],
    relay_pid: ctx.pid,
    upstream_pid: ctx.upstreamPid,
  };
  const logEvents = readJsonl(ctx.relayLog);
  const existingExit = logEvents.find((event) => event.type === "child_exit");
  if (existingExit) {
    result.child_exit_event = existingExit;
    result.child_exit_observed = true;
  } else {
    const startIndex = ctx.control.events.length;
    ctx.control.send({ cmd: "shutdown", at: nowIso() });
    const childExit = await ctx.control.waitFor(
      (event) => event.type === "child_exit",
      CONTROL_TIMEOUT_MS,
      { after: startIndex },
    );
    result.child_exit_event = childExit.event;
    result.child_exit_observed =
      childExit.found || readJsonl(ctx.relayLog).some((event) => event.type === "child_exit");
  }
  try {
    await ctx.client.close();
  } catch (error) {
    result.errors.push(`client.close: ${error?.message || String(error)}`);
  }
  result.relay_exit_observed = ctx.pid ? await waitUntil(() => !processAlive(ctx.pid), 5000) : true;
  result.relay_alive_after = ctx.pid ? processAlive(ctx.pid) : false;
  result.upstream_exit_observed = ctx.upstreamPid
    ? await waitUntil(() => !processAlive(ctx.upstreamPid), 5000)
    : true;
  result.upstream_alive_after = ctx.upstreamPid ? processAlive(ctx.upstreamPid) : false;
  writeFileSync(ctx.relayStderr, ctx.stderrText());
  ctx.control.close();
  harness.event("cleanup_relay", result);
  return result;
}

export async function cleanupSynthetic(ctx, harness) {
  const result = { kind: "synthetic", phase: ctx.phase, errors: [], pid: ctx.pid };
  try {
    await ctx.client.close();
  } catch (error) {
    result.errors.push(`client.close: ${error?.message || String(error)}`);
  }
  result.server_exit_observed = ctx.pid ? await waitUntil(() => !processAlive(ctx.pid), 5000) : true;
  result.server_alive_after = ctx.pid ? processAlive(ctx.pid) : false;
  harness.event("cleanup_synthetic", result);
  return result;
}

export function createTracker(client) {
  const states = [];
  let current = null;
  const waiters = new Set();

  function snapshot(state) {
    if (!state) return null;
    return {
      seq: state.seq,
      name: state.name,
      args: state.args,
      requestId: state.requestId,
      startedAt: state.startedAt,
      pending: state.pending,
      outcome: state.outcome,
      settledAt: state.settledAt,
      errorName: state.errorName,
      errorCode: state.errorCode,
      errorMessage: state.errorMessage,
      cancellationSentAt: state.cancellationSentAt,
      cancellationSeen: state.cancellationSeen,
      signalAborted: Boolean(state.options?.signal?.aborted),
    };
  }

  function notify(state) {
    for (const waiter of [...waiters]) {
      if (waiter.state !== state) continue;
      waiters.delete(waiter);
      clearTimeout(waiter.timer);
      waiter.resolve({ found: true, state: snapshot(state), elapsedMs: Date.now() - waiter.started });
    }
  }

  const trackedClient = {
    callTool(params, resultSchema, options) {
      const state = {
        seq: states.length + 1,
        name: params.name,
        args: params.arguments,
        options,
        requestId: null,
        startedAt: nowIso(),
        startedMs: Date.now(),
        pending: true,
        outcome: null,
        settledAt: null,
        settledMs: null,
        errorName: null,
        errorCode: null,
        errorMessage: null,
        cancellationSentAt: null,
        cancellationSeen: false,
      };
      states.push(state);
      current = state;
      let promise;
      try {
        promise = client.callTool(params, resultSchema, options);
      } catch (error) {
        state.pending = false;
        state.outcome = "threw";
        state.settledAt = nowIso();
        state.settledMs = Date.now();
        state.errorName = error?.name || "Error";
        state.errorCode = error?.code ?? null;
        state.errorMessage = error?.message || String(error);
        notify(state);
        throw error;
      }
      state.promise = promise;
      promise.then(
        (value) => {
          state.pending = false;
          state.outcome = "fulfilled";
          state.settledAt = nowIso();
          state.settledMs = Date.now();
          state.value = value;
          notify(state);
        },
        (error) => {
          state.pending = false;
          state.outcome = "rejected";
          state.settledAt = nowIso();
          state.settledMs = Date.now();
          state.errorName = error?.name || "Error";
          state.errorCode = error?.code ?? null;
          state.errorMessage = error?.message || String(error);
          notify(state);
        },
      );
      return promise;
    },
  };

  return {
    states,
    trackedClient,
    currentState: () => current,
    snapshot,
    noteOutbound(message) {
      if (!message || typeof message !== "object") return;
      if (message.method === "tools/call") {
        const state = states.find(
          (candidate) =>
            candidate.requestId === null &&
            candidate.pending &&
            candidate.name === message.params?.name,
        );
        if (state) state.requestId = message.id ?? null;
      }
      if (message.method === "notifications/cancelled") {
        const requestId = message.params?.requestId;
        const state = states.find((candidate) => candidate.requestId === requestId);
        if (state) {
          state.cancellationSeen = true;
          state.cancellationSentAt = nowIso();
        }
      }
    },
    waitForSettlement(state, timeoutMs) {
      if (!state) return Promise.resolve({ found: false, state: null, elapsedMs: 0 });
      if (!state.pending) {
        return Promise.resolve({ found: true, state: snapshot(state), elapsedMs: 0 });
      }
      return new Promise((resolveWait) => {
        const started = Date.now();
        const waiter = {
          state,
          started,
          resolve: resolveWait,
          timer: setTimeout(() => {
            waiters.delete(waiter);
            resolveWait({ found: false, state: snapshot(state), elapsedMs: Date.now() - started });
          }, timeoutMs),
        };
        waiters.add(waiter);
      });
    },
  };
}

export function makeValidators(inventory) {
  const ajv = new Ajv2020({ strict: false, allErrors: true });
  const validators = new Map();
  for (const name of READ_TOOLS) {
    const tool = inventory.tools.find((candidate) => candidate.name === name);
    if (!tool) throw new Error(`missing upstream tool ${name}`);
    validators.set(name, ajv.compile(tool.inputSchema));
  }
  return validators;
}

export async function executeWith(tool, code, executor) {
  try {
    const output = await tool.execute({ code });
    return { result: output.result ?? null, error: null, stats: executor.stats() };
  } catch (error) {
    return {
      result: null,
      error: error?.message || String(error),
      errorName: error?.name || null,
      stats: executor.stats(),
    };
  }
}

export function countOutbound(log, method, requestId = undefined) {
  return log.filter(
    (entry) =>
      entry.dir === "out" &&
      entry.message?.method === method &&
      (requestId === undefined || entry.message?.params?.requestId === requestId),
  );
}

export function outboundToolCalls(log) {
  return log.filter(
    (entry) => entry.dir === "out" && entry.message?.method === "tools/call",
  );
}

export function versions() {
  const pkg = readJson(join(F1_DIR, "package.json"));
  const py = JSON.parse(
    execFileSync(
      process.env.CM01_PYTHON || "python",
      [
        "-c",
        [
          "import json, sys",
          "import mneme",
          "from importlib.metadata import version",
          "print(json.dumps({",
          "  'python': sys.version.split()[0],",
          "  'mneme': getattr(mneme, '__version__', 'unknown'),",
          "  'mcp': version('mcp'),",
          "}))",
        ].join("\n"),
      ],
      {
        cwd: EMPTY_CWD,
        env: { ...process.env, PYTHONPATH: ROOT },
        encoding: "utf8",
      },
    ),
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

export function stable(value) {
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

export function deepEqual(left, right) {
  return JSON.stringify(stable(left)) === JSON.stringify(stable(right));
}

export function cancellationFor(log, requestId) {
  return countOutbound(log, "notifications/cancelled", requestId);
}

