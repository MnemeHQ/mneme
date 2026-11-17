import { execFileSync, execSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createBrowserCodeTool } from "@cloudflare/codemode/browser";
import { QuickJSExecutor } from "./quickjs-executor.mjs";
import { createSyntheticHost } from "./synthetic-host.mjs";
import { probeNativePromiseBridge } from "./probe-native-promise.mjs";
import { checkM4Protection, DEFAULT_BASE_SHA, S0_SHA } from "../m4-guard.mjs";

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const EVIDENCE = join(ROOT, "evidence");
const RAW = join(EVIDENCE, "raw");
mkdirSync(RAW, { recursive: true });

const ORDER_CODE = `async () => {
  const a = await codemode.synthetic_read({ key: "a", delayMs: 20 });
  const b = await codemode.synthetic_read({ key: "b", delayMs: 1 });
  const c = await codemode.synthetic_read({ key: "c", delayMs: 5 });
  return [a.key, b.key, c.key];
}`;

const ERROR_CODE = `async () => {
  const a = await codemode.synthetic_read({ key: "a", delayMs: 1 });
  const b = await codemode.synthetic_read({ key: "b", delayMs: 1 });
  const c = await codemode.synthetic_read({ key: "c", delayMs: 1 });
  return [a.key, b.key, c.key];
}`;

const TIMEOUT_CODE = `async () => {
  await codemode.synthetic_read({ key: "never" });
  return "not reached";
}`;

const MEMORY_CODE = `async () => {
  const x = "x".repeat(64 * 1024 * 1024);
  return x.length;
}`;

const GLOBALS_CODE = `async () => ({
  process: typeof process,
  require: typeof require,
  fetch: typeof fetch,
  Buffer: typeof Buffer,
  module: typeof module,
  exports: typeof exports,
  __dirname: typeof __dirname,
  Deno: typeof Deno,
  Bun: typeof Bun,
  codemode: typeof codemode,
  globalThis: typeof globalThis
})`;

function makeTool(host, executor) {
  return createBrowserCodeTool({
    tools: {
      synthetic_read: {
        description: "Synthetic read used only by CM-01 E0.",
        inputSchema: {
          type: "object",
          properties: {
            key: { type: "string" },
            delayMs: { type: "number" },
          },
          required: ["key"],
        },
        execute: (args) => host.read(args),
      },
    },
    executor,
  });
}

async function runTool({
  code,
  hostOptions = {},
  timeoutMs = 500,
  memoryLimitBytes = 8 * 1024 * 1024,
}) {
  const host = createSyntheticHost(hostOptions);
  const executor = new QuickJSExecutor({
    timeoutMs,
    memoryLimitBytes,
    onCleanup: () => host.cancelAll(),
  });
  const tool = makeTool(host, executor);
  let result = null;
  let error = null;
  try {
    const output = await tool.execute({ code });
    result = output.result;
  } catch (caught) {
    error = caught?.message || String(caught);
  }
  return {
    tool_name: tool.name,
    result,
    error,
    stats: executor.stats(),
    host: {
      calls: host.calls,
      starts: host.calls.filter((call) => call.phase === "start").map((call) => call.key),
      ends: host.calls.filter((call) => call.phase === "end").map((call) => call.key),
      activeCalls: host.activeCalls(),
      pendingTimers: host.pendingTimers(),
    },
  };
}

function versions() {
  const packageJson = JSON.parse(readFileSync(join(ROOT, "package.json"), "utf8"));
  return {
    node: process.version,
    npm: execSync("npm --version", { encoding: "utf8" }).trim(),
    codemode: packageJson.dependencies["@cloudflare/codemode"],
    quickjs: packageJson.dependencies["quickjs-emscripten"],
    platform: `${process.platform} ${process.arch}`,
  };
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function verdict(checks) {
  const failed = checks.filter((check) => !check.pass);
  return {
    pass: failed.length === 0,
    failed: failed.map((check) => check.id),
  };
}

const startedAt = new Date().toISOString();
const m4Before = checkM4Protection({ cwd: ROOT, baseSha: DEFAULT_BASE_SHA });
const native = await probeNativePromiseBridge();
assert(native.pass, "native QuickJS promise bridge probe failed; do not select Asyncify without review");

const checks = [];
const details = {};

const order = await runTool({ code: ORDER_CODE });
details.order = order;
checks.push({
  id: "E0-ORDER",
  pass:
    !order.error &&
    JSON.stringify(order.result) === JSON.stringify(["a", "b", "c"]) &&
    JSON.stringify(order.host.starts) === JSON.stringify(["a", "b", "c"]) &&
    JSON.stringify(order.host.ends) === JSON.stringify(["a", "b", "c"]) &&
    order.stats.hostCalls === 3 &&
    order.stats.resolvedCalls === 3 &&
    order.stats.pendingAtEnd === 0,
});

const failure = await runTool({
  code: ERROR_CODE,
  hostOptions: { failOn: "b" },
});
details.error = failure;
checks.push({
  id: "E0-ERROR",
  pass:
    Boolean(failure.error) &&
    /synthetic failure at b/.test(failure.error) &&
    JSON.stringify(failure.host.starts) === JSON.stringify(["a", "b"]) &&
    JSON.stringify(failure.host.ends) === JSON.stringify(["a", "b"]) &&
    !failure.host.starts.includes("c") &&
    failure.stats.failedCalls === 1 &&
    failure.stats.pendingAtEnd === 0,
});

const timeout = await runTool({
  code: TIMEOUT_CODE,
  hostOptions: { hangOn: "never" },
  timeoutMs: 60,
});
details.timeout = timeout;
checks.push({
  id: "E0-TIMEOUT",
  pass:
    Boolean(timeout.error) &&
    /exceeded 60ms/.test(timeout.error) &&
    timeout.stats.timedOut === true &&
    timeout.stats.pendingAtEnd === 0 &&
    timeout.host.activeCalls === 0 &&
    timeout.host.pendingTimers === 0,
});

const memory = await runTool({
  code: MEMORY_CODE,
  timeoutMs: 3000,
  memoryLimitBytes: 8 * 1024 * 1024,
});
details.memory = memory;
checks.push({
  id: "E0-MEMORY",
  pass:
    Boolean(memory.error) &&
    memory.stats.pendingAtEnd === 0 &&
    (memory.stats.interrupted === true || /memory|allocation|out of memory/i.test(memory.error)),
});

const globals = await runTool({ code: GLOBALS_CODE });
details.globals = globals;
const expectedUndefined = [
  "process",
  "require",
  "fetch",
  "Buffer",
  "module",
  "exports",
  "__dirname",
  "Deno",
  "Bun",
];
checks.push({
  id: "E0-GLOBALS",
  pass:
    !globals.error &&
    expectedUndefined.every((key) => globals.result[key] === "undefined") &&
    globals.result.codemode === "object" &&
    globals.result.globalThis === "object",
});

const cleanup = {
  timeout_pending_at_end: timeout.stats.pendingAtEnd,
  timeout_active_host_calls: timeout.host.activeCalls,
  timeout_pending_timers: timeout.host.pendingTimers,
  error_pending_at_end: failure.stats.pendingAtEnd,
  error_active_host_calls: failure.host.activeCalls,
  error_pending_timers: failure.host.pendingTimers,
};
details.cleanup = cleanup;
checks.push({
  id: "E0-CLEANUP",
  pass: Object.values(cleanup).every((value) => value === 0),
});

const repeatA = await runTool({ code: ORDER_CODE });
const repeatB = await runTool({ code: ORDER_CODE });
const repeatable =
  JSON.stringify({
    result: repeatA.result,
    starts: repeatA.host.starts,
    ends: repeatA.host.ends,
  }) ===
  JSON.stringify({
    result: repeatB.result,
    starts: repeatB.host.starts,
    ends: repeatB.host.ends,
  });
details.repeatability = { run_a: repeatA, run_b: repeatB, repeatable };
checks.push({ id: "E0-REPEAT", pass: repeatable });

const m4After = checkM4Protection({ cwd: ROOT, baseSha: DEFAULT_BASE_SHA });
checks.push({ id: "E0-M4", pass: m4Before.pass && m4After.pass });

const result = {
  schema: "mneme.cm01.s1a1.e0/v1",
  started_at: startedAt,
  finished_at: new Date().toISOString(),
  repository: {
    base_sha: DEFAULT_BASE_SHA,
    s0_sha: S0_SHA,
    branch: execFileSync("git", ["branch", "--show-current"], {
      cwd: ROOT,
      encoding: "utf8",
    }).trim(),
    head_sha: execFileSync("git", ["rev-parse", "HEAD"], {
      cwd: ROOT,
      encoding: "utf8",
    }).trim(),
  },
  versions: versions(),
  native_probe: native,
  details,
  checks,
  verdict: verdict(checks),
  m4_guard: { before: m4Before, after: m4After },
  limitations: [
    "Local Code Mode orchestration only; no Cloudflare CodemodeRuntime, McpConnector, codemode.search/describe, approvals, replay, or rollback.",
    "No Mneme MCP connection, credentials, project memory, or proposal tools.",
    "Fixed synthetic host calls only; no live model-generated code.",
  ],
};

writeFileSync(join(EVIDENCE, "e0.json"), `${JSON.stringify(result, null, 2)}\n`);
writeFileSync(
  join(RAW, "e0.log"),
  `${JSON.stringify({ checks, native_probe: native, versions: result.versions }, null, 2)}\n`,
);

process.stdout.write(`${JSON.stringify(result.verdict)}\n`);
process.stdout.write(`${JSON.stringify({ checks, m4_pass: m4After.pass }, null, 2)}\n`);
process.exit(result.verdict.pass ? 0 : 1);
