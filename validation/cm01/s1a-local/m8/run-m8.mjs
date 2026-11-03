import { execFileSync, execSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createBrowserCodeTool } from "@cloudflare/codemode/browser";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import {
  StdioClientTransport,
  getDefaultEnvironment,
} from "@modelcontextprotocol/sdk/client/stdio.js";
import Ajv2020 from "ajv/dist/2020.js";
import { QuickJSExecutor } from "../e0/quickjs-executor.mjs";
import { createSyntheticHost } from "../e0/synthetic-host.mjs";
import { checkM4Protection, DEFAULT_BASE_SHA, S0_SHA } from "../m4-guard.mjs";

const M8_DIR = dirname(fileURLToPath(import.meta.url));
const S1A_DIR = dirname(M8_DIR);
const ROOT = resolve(M8_DIR, "../../../..");
const M1_DIR = join(S1A_DIR, "m1");
const M4_DIR = join(S1A_DIR, "m4");
const FIXTURE = join(M4_DIR, "fixture", "canonical", "project_memory.json");
const PRE_MIGRATION = join(M4_DIR, "fixture", "pre_migration.json");
const SECTIONLESS = join(M8_DIR, "fixture", "sectionless.json");
const EMPTY_CWD = join(M1_DIR, "empty-cwd");
const EVIDENCE = join(M8_DIR, "evidence");
const READ_TOOLS = [
  "decision.get",
  "decision.search",
  "decision.applicable_to",
  "decision.trace",
];

mkdirSync(EVIDENCE, { recursive: true });

function sha256File(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
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

function schemaHash(schema) {
  return createHash("sha256").update(JSON.stringify(stable(schema))).digest("hex");
}

function diffValues(left, right, path = "", out = []) {
  if (Object.is(left, right)) return out;
  if (Array.isArray(left) || Array.isArray(right)) {
    if (!Array.isArray(left) || !Array.isArray(right)) {
      out.push({ path, left, right });
      return out;
    }
    if (left.length !== right.length) out.push({ path: `${path}.length`, left: left.length, right: right.length });
    const length = Math.max(left.length, right.length);
    for (let index = 0; index < length; index += 1) {
      diffValues(left[index], right[index], `${path}[${index}]`, out);
    }
    return out;
  }
  if (left && right && typeof left === "object" && typeof right === "object") {
    const keys = new Set([...Object.keys(left), ...Object.keys(right)]);
    for (const key of [...keys].sort()) {
      diffValues(left[key], right[key], path ? `${path}.${key}` : key, out);
    }
    return out;
  }
  out.push({ path, left, right });
  return out;
}

function listEmptyCwd() {
  return execFileSync("git", ["ls-files", "--others", "--exclude-standard"], {
    cwd: EMPTY_CWD,
    encoding: "utf8",
  })
    .split(/\r?\n/)
    .filter(Boolean);
}

function versions() {
  const pkg = JSON.parse(readFileSync(join(M8_DIR, "package.json"), "utf8"));
  const py = execFileSync(
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
  );
  return {
    node: process.version,
    npm: execSync("npm --version", { encoding: "utf8" }).trim(),
    codemode: pkg.dependencies["@cloudflare/codemode"],
    sdk: pkg.dependencies["@modelcontextprotocol/sdk"],
    ajv: pkg.dependencies.ajv,
    zod: pkg.dependencies.zod,
    ...JSON.parse(py),
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
  throw new Error(`MCP ${toolName} returned no structured result`);
}

function countedClient(client) {
  const calls = [];
  return {
    calls,
    client: {
      callTool: async (params) => {
        calls.push({ name: params.name, arguments: params.arguments });
        return client.callTool(params);
      },
    },
  };
}

async function connectServer({ memory = FIXTURE } = {}) {
  const stderr = [];
  const transport = new StdioClientTransport({
    command: process.env.CM01_PYTHON || "python",
    args: [
      "-m",
      "mneme",
      "decision-mcp",
      "--memory",
      memory,
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
  const client = new Client({ name: "cm01-m8", version: "0.1.0" });
  transport.stderr?.on("data", (chunk) => stderr.push(chunk.toString("utf8")));
  await client.connect(transport);
  const inventory = await client.listTools();
  return { client, transport, inventory, stderr };
}

async function attemptSectionlessStartup() {
  const stderr = [];
  const transport = new StdioClientTransport({
    command: process.env.CM01_PYTHON || "python",
    args: [
      "-m",
      "mneme",
      "decision-mcp",
      "--memory",
      SECTIONLESS,
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
  const client = new Client({ name: "cm01-m8-e5", version: "0.1.0" });
  transport.stderr?.on("data", (chunk) => stderr.push(chunk.toString("utf8")));
  const result = {
    connected: false,
    server_info: null,
    error: null,
    pid: null,
    stderr: "",
  };
  try {
    await Promise.race([
      client.connect(transport),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error("sectionless startup probe timed out")), 5000),
      ),
    ]);
    result.connected = true;
    result.server_info = client.getServerVersion() ?? null;
  } catch (error) {
    result.error = error?.message || String(error);
  } finally {
    result.pid = transport.pid;
    try {
      await client.close();
    } catch (error) {
      result.close_error = error?.message || String(error);
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 150));
    result.stderr = stderr.join("");
  }
  return result;
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

function makeM2Adapter({ client, inventory, validators, executor, validate = true }) {
  const callLog = [];
  const descriptors = {};
  const schemaHashes = {};
  const byName = new Map(inventory.tools.map((tool) => [tool.name, tool]));

  for (const name of READ_TOOLS) {
    const tool = byName.get(name);
    if (!tool) throw new Error(`missing upstream tool ${name}`);
    schemaHashes[name] = { upstream: schemaHash(tool.inputSchema) };
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
        const result = await client.callTool({ name, arguments: args });
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
    schemaHashes[name].descriptor = schemaHash(descriptors[name].inputSchema);
  }

  return {
    tool: createBrowserCodeTool({ tools: descriptors, executor }),
    callLog,
    schemaHashes,
  };
}

async function executeCatch(tool, code, executor) {
  try {
    const output = await tool.execute({ code });
    return { result: output.result, error: null, stats: executor.stats() };
  } catch (error) {
    return {
      result: null,
      error: error?.message || String(error),
      stats: executor.stats(),
    };
  }
}

function preservedHashes() {
  const files = {
    e0_evidence: join(S1A_DIR, "evidence", "e0.json"),
    m1_evidence: join(S1A_DIR, "m1", "evidence", "m1.json"),
    m2_evidence: join(S1A_DIR, "m2", "evidence", "m2.json"),
    m3_evidence: join(S1A_DIR, "m3", "evidence", "m3.json"),
    m4_evidence: join(S1A_DIR, "m4", "evidence", "m4.json"),
    m4_f1_evidence: join(S1A_DIR, "m4", "f1", "evidence", "m4-f1.json"),
    m5_evidence: join(S1A_DIR, "m5", "evidence", "m5.json"),
    m6_evidence: join(S1A_DIR, "m6", "evidence", "m6.json"),
    m7_evidence: join(S1A_DIR, "m7", "evidence", "m7.json"),
    m1_fixture: join(S1A_DIR, "m1", "fixture", "canonical", "project_memory.json"),
    m4_f1_fixture: join(S1A_DIR, "m4", "fixture", "canonical", "project_memory.json"),
  };
  return Object.fromEntries(
    Object.entries(files).map(([key, path]) => [key, sha256File(path)]),
  );
}

async function runOnce(label) {
  const server = await connectServer();
  const { client, inventory, stderr } = server;
  const upstreamNames = [...inventory.tools].map((tool) => tool.name).sort();
  const validators = makeValidators(inventory);

  const e1Counted = countedClient(client);
  const e1Executor = new QuickJSExecutor({ timeoutMs: 2000, memoryLimitBytes: 8 * 1024 * 1024 });
  const e1Adapter = makeM2Adapter({
    client: e1Counted.client,
    inventory,
    validators,
    executor: e1Executor,
    validate: true,
  });
  const directGetRaw = await client.callTool({
    name: "decision.get",
    arguments: { record_id: "ADR-9999" },
  });
  const directTraceRaw = await client.callTool({
    name: "decision.trace",
    arguments: { record_id: "ADR-9999" },
  });
  const directGet = normalizeMcpSuccess("decision.get", directGetRaw);
  const directTrace = normalizeMcpSuccess("decision.trace", directTraceRaw);
  const e1Code = await e1Adapter.tool.execute({
    code: `async () => ({
      get: await codemode.decision_get({ record_id: "ADR-9999" }),
      trace: await codemode.decision_trace({ record_id: "ADR-9999" })
    })`,
  });
  const e1 = {
    direct_get: { raw: directGetRaw, normalized: directGet, is_error: Boolean(directGetRaw.isError) },
    direct_trace: { raw: directTraceRaw, normalized: directTrace, is_error: Boolean(directTraceRaw.isError) },
    code_mode: { raw: e1Code.result, normalized: e1Code.result },
    parity: {
      get_differences: diffValues(stable(directGet), stable(e1Code.result?.get)),
      trace_differences: diffValues(stable(directTrace), stable(e1Code.result?.trace)),
    },
    typed_not_found:
      directGet?.record_type === "not_found" &&
      directGet?.record_id === "ADR-9999" &&
      directTrace?.result_type === "trace_not_found" &&
      directTrace?.record_id === "ADR-9999" &&
      !Boolean(directGetRaw.isError) &&
      !Boolean(directTraceRaw.isError),
    adapter_calls: e1Counted.calls,
  };

  const e2Counted = countedClient(client);
  const e2Executor = new QuickJSExecutor({ timeoutMs: 2000, memoryLimitBytes: 8 * 1024 * 1024 });
  const e2Adapter = makeM2Adapter({
    client: e2Counted.client,
    inventory,
    validators,
    executor: e2Executor,
    validate: true,
  });
  const e2 = await executeCatch(
    e2Adapter.tool,
    `async () => codemode.decision_get({ record_id: 123 })`,
    e2Executor,
  );
  const e2Result = {
    ...e2,
    origin: "host_validation",
    kind: "argument_validation_error",
    result_returned: e2.result != null,
    upstream_calls: e2Counted.calls.length,
    adapter_log: e2Adapter.callLog,
    is_not_found: /not_found/i.test(e2.error ?? ""),
  };

  let directInvalidRaw = null;
  let directInvalidError = null;
  try {
    directInvalidRaw = await client.callTool({
      name: "decision.search",
      arguments: { canonical_lifecycle_status: "bogus" },
    });
  } catch (error) {
    directInvalidError = error?.message || String(error);
  }
  const e3Counted = countedClient(client);
  const e3Executor = new QuickJSExecutor({ timeoutMs: 2000, memoryLimitBytes: 8 * 1024 * 1024 });
  const e3Adapter = makeM2Adapter({
    client: e3Counted.client,
    inventory,
    validators,
    executor: e3Executor,
    validate: false,
  });
  const e3 = await executeCatch(
    e3Adapter.tool,
    `async () => codemode.decision_search({ canonical_lifecycle_status: "bogus" })`,
    e3Executor,
  );
  const e3Result = {
    direct: {
      raw: directInvalidRaw,
      is_error: Boolean(directInvalidRaw?.isError) || Boolean(directInvalidError),
      structured_content: directInvalidRaw?.structuredContent ?? null,
      text: textContent(directInvalidRaw ?? {}) || directInvalidError || "",
    },
    code_mode: {
      ...e3,
      result_returned: e3.result != null,
      upstream_calls: e3Counted.calls.length,
      adapter_log: e3Adapter.callLog,
    },
    origin: "mcp_tool",
    kind: "mcp_tool_rejection",
  };

  const e4Server = await connectServer();
  const e4Validators = makeValidators(e4Server.inventory);
  const e4Counted = countedClient(e4Server.client);
  const e4Executor = new QuickJSExecutor({ timeoutMs: 2000, memoryLimitBytes: 8 * 1024 * 1024 });
  const e4Adapter = makeM2Adapter({
    client: e4Counted.client,
    inventory: e4Server.inventory,
    validators: e4Validators,
    executor: e4Executor,
    validate: true,
  });
  await e4Server.client.close();
  const e4 = await executeCatch(
    e4Adapter.tool,
    `async () => codemode.decision_search({ query: "cache" })`,
    e4Executor,
  );
  await new Promise((resolveDelay) => setTimeout(resolveDelay, 100));
  const e4Result = {
    ...e4,
    origin: "transport",
    kind: "transport_failure",
    result_returned: e4.result != null,
    upstream_calls: e4Counted.calls.length,
    adapter_log: e4Adapter.callLog,
    pid: e4Server.transport.pid,
    stderr: e4Server.stderr.join(""),
    cleanup: {
      pending_at_end: e4.stats?.pendingAtEnd ?? null,
      client_closed: true,
    },
  };

  const sectionlessBefore = sha256File(SECTIONLESS);
  const sectionlessDocBefore = JSON.parse(readFileSync(SECTIONLESS, "utf8"));
  const e5 = await attemptSectionlessStartup();
  const sectionlessAfter = sha256File(SECTIONLESS);
  const sectionlessDocAfter = JSON.parse(readFileSync(SECTIONLESS, "utf8"));
  const e5Result = {
    ...e5,
    origin: "startup",
    kind: "migration_required",
    sectionless_sha256_before: sectionlessBefore,
    sectionless_sha256_after: sectionlessAfter,
    still_sectionless:
      !("decision_index" in sectionlessDocAfter) &&
      !("decision_index" in sectionlessDocBefore),
    migration_or_index_reported: /decision_index|migrat/i.test(e5.stderr ?? ""),
    fallback_handshake: Boolean(e5.server_info),
    fallback_repository_memory: /repository project_memory|repository memory|fallback/i.test(e5.stderr ?? "") && !/no authoritative decision_index|migration/i.test(e5.stderr ?? ""),
  };

  const e6Host = createSyntheticHost({ hangOn: "never" });
  const e6Executor = new QuickJSExecutor({
    timeoutMs: 60,
    memoryLimitBytes: 8 * 1024 * 1024,
    onCleanup: () => e6Host.cancelAll(),
  });
  const e6Tool = createBrowserCodeTool({
    tools: {
      hang: {
        description: "Synthetic hanging host call for M8 E6.",
        inputSchema: { type: "object", properties: {} },
        execute: () => e6Host.read({ key: "never" }),
      },
    },
    executor: e6Executor,
  });
  const e6 = await executeCatch(e6Tool, `async () => codemode.hang({})`, e6Executor);
  const e6Result = {
    ...e6,
    origin: "executor",
    kind: "executor_timeout",
    result_returned: e6.result != null,
    timed_out: e6.stats?.timedOut ?? null,
    cleanup: {
      pending_at_end: e6.stats?.pendingAtEnd ?? null,
      host_active_calls: e6Host.activeCalls(),
      host_pending_timers: e6Host.pendingTimers(),
    },
  };

  const result = {
    run: label,
    pid: server.transport.pid,
    upstream_inventory: {
      count: upstreamNames.length,
      names: upstreamNames,
      exact_six: upstreamNames.length === 6,
    },
    e1,
    e2: e2Result,
    e3: e3Result,
    e4: e4Result,
    e5: e5Result,
    e6: e6Result,
    stderr: stderr.join(""),
  };

  try {
    await client.close();
  } catch (error) {
    result.close_error = error?.message || String(error);
  }
  await new Promise((resolveDelay) => setTimeout(resolveDelay, 100));
  return result;
}

function normalizedRun(run) {
  return {
    upstream_inventory: run.upstream_inventory,
    e1: {
      direct_get: run.e1.direct_get.normalized,
      direct_trace: run.e1.direct_trace.normalized,
      code_mode: run.e1.code_mode.normalized,
      parity: run.e1.parity,
      typed_not_found: run.e1.typed_not_found,
    },
    e2: {
      origin: run.e2.origin,
      kind: run.e2.kind,
      error: run.e2.error,
      result_returned: run.e2.result_returned,
      upstream_calls: run.e2.upstream_calls,
      is_not_found: run.e2.is_not_found,
    },
    e3: {
      direct_is_error: run.e3.direct.is_error,
      direct_structured: run.e3.direct.structured_content,
      direct_text: run.e3.direct.text,
      code_error: run.e3.code_mode.error,
      code_result_returned: run.e3.code_mode.result_returned,
      code_upstream_calls: run.e3.code_mode.upstream_calls,
      origin: run.e3.origin,
      kind: run.e3.kind,
    },
    e4: {
      origin: run.e4.origin,
      kind: run.e4.kind,
      error: run.e4.error,
      result_returned: run.e4.result_returned,
      upstream_calls: run.e4.upstream_calls,
      cleanup: run.e4.cleanup,
    },
    e5: {
      connected: run.e5.connected,
      server_info: run.e5.server_info,
      error: run.e5.error,
      stderr: run.e5.stderr,
      still_sectionless: run.e5.still_sectionless,
      migration_or_index_reported: run.e5.migration_or_index_reported,
      fallback_handshake: run.e5.fallback_handshake,
      fallback_repository_memory: run.e5.fallback_repository_memory,
    },
    e6: {
      origin: run.e6.origin,
      kind: run.e6.kind,
      error: run.e6.error,
      result_returned: run.e6.result_returned,
      cleanup: run.e6.cleanup,
      timed_out: run.e6.stats?.timedOut ?? null,
    },
  };
}

const startedAt = new Date().toISOString();
const repoMemory = join(ROOT, ".mneme", "project_memory.json");
const repoProposals = join(ROOT, ".mneme", "decision_proposals.json");
const preservedBefore = preservedHashes();
const before = {
  fixture_sha256: sha256File(FIXTURE),
  pre_migration_sha256: sha256File(PRE_MIGRATION),
  sectionless_sha256: sha256File(SECTIONLESS),
  repo_memory_sha256: existsSync(repoMemory) ? sha256File(repoMemory) : null,
  repo_proposals_exists: existsSync(repoProposals),
  repo_proposals_sha256: existsSync(repoProposals) ? sha256File(repoProposals) : null,
  empty_cwd_files: listEmptyCwd(),
  m4: checkM4Protection({ cwd: ROOT, baseSha: DEFAULT_BASE_SHA }),
  preserved: preservedBefore,
};

let run1;
let run2;
try {
  run1 = await runOnce("run1");
  run2 = await runOnce("run2");
} catch (error) {
  run1 = run1 ?? { run: "run1", error: error?.message || String(error) };
  run2 = run2 ?? { run: "run2", error: error?.message || String(error) };
}

const preservedAfter = preservedHashes();
const after = {
  fixture_sha256: sha256File(FIXTURE),
  pre_migration_sha256: sha256File(PRE_MIGRATION),
  sectionless_sha256: sha256File(SECTIONLESS),
  repo_memory_sha256: existsSync(repoMemory) ? sha256File(repoMemory) : null,
  repo_proposals_exists: existsSync(repoProposals),
  repo_proposals_sha256: existsSync(repoProposals) ? sha256File(repoProposals) : null,
  empty_cwd_files: listEmptyCwd(),
  m4: checkM4Protection({ cwd: ROOT, baseSha: DEFAULT_BASE_SHA }),
  preserved: preservedAfter,
};

const sameEvidence =
  JSON.stringify(normalizedRun(run1)) === JSON.stringify(normalizedRun(run2));

const checks = [
  { id: "M8-UPSTREAM-SIX-1", pass: Boolean(run1?.upstream_inventory?.exact_six) },
  { id: "M8-UPSTREAM-SIX-2", pass: Boolean(run2?.upstream_inventory?.exact_six) },
  {
    id: "M8-E1-TYPED-NOT-FOUND",
    pass:
      run1?.e1?.typed_not_found &&
      run1?.e1?.parity?.get_differences?.length === 0 &&
      run1?.e1?.parity?.trace_differences?.length === 0 &&
      run1.e1.code_mode.normalized?.get?.record_type === "not_found" &&
      run1.e1.code_mode.normalized?.trace?.result_type === "trace_not_found",
  },
  {
    id: "M8-E2-HOST-VALIDATION",
    pass:
      run1?.e2?.kind === "argument_validation_error" &&
      run1?.e2?.result_returned === false &&
      run1?.e2?.upstream_calls === 0 &&
      run1?.e2?.is_not_found === false &&
      /Argument validation failed/.test(run1.e2.error ?? ""),
  },
  {
    id: "M8-E3-MCP-REJECTION",
    pass:
      run1?.e3?.direct?.is_error === true &&
      run1?.e3?.direct?.structured_content === null &&
      Boolean(run1?.e3?.code_mode?.error) &&
      run1?.e3?.code_mode?.result_returned === false &&
      run1?.e3?.code_mode?.upstream_calls === 1 &&
      run1?.e3?.kind === "mcp_tool_rejection",
  },
  {
    id: "M8-E4-TRANSPORT-FAILURE",
    pass:
      run1?.e4?.kind === "transport_failure" &&
      Boolean(run1?.e4?.error) &&
      run1?.e4?.result_returned === false &&
      run1?.e4?.upstream_calls === 1 &&
      run1?.e4?.cleanup?.pending_at_end === 0,
  },
  {
    id: "M8-E5-MISSING-INDEX",
    pass:
      run1?.e5?.connected === false &&
      run1?.e5?.fallback_handshake === false &&
      run1?.e5?.migration_or_index_reported === true &&
      run1?.e5?.still_sectionless === true &&
      run1?.e5?.fallback_repository_memory === false,
  },
  {
    id: "M8-E6-EXECUTOR-FAILURE",
    pass:
      run1?.e6?.kind === "executor_timeout" &&
      Boolean(run1?.e6?.error) &&
      run1?.e6?.result_returned === false &&
      run1?.e6?.timed_out === true &&
      run1?.e6?.cleanup?.pending_at_end === 0 &&
      run1?.e6?.cleanup?.host_active_calls === 0 &&
      run1?.e6?.cleanup?.host_pending_timers === 0,
  },
  {
    id: "M8-NO-PROPOSAL-CALLS",
    pass:
      [...(run1?.e1?.adapter_calls ?? []), ...(run1?.e2?.adapter_log ?? []), ...(run1?.e3?.code_mode?.adapter_log ?? []), ...(run1?.e4?.adapter_log ?? [])].every(
        (call) => call.name !== "decision.propose" && call.tool !== "decision.propose" && call.name !== "decision.propose_batch" && call.tool !== "decision.propose_batch",
      ),
  },
  { id: "M8-REPEAT", pass: Boolean(sameEvidence) },
  {
    id: "M8-NO-MUTATION",
    pass:
      before.fixture_sha256 === after.fixture_sha256 &&
      before.pre_migration_sha256 === after.pre_migration_sha256 &&
      before.sectionless_sha256 === after.sectionless_sha256 &&
      before.repo_memory_sha256 === after.repo_memory_sha256 &&
      before.repo_proposals_exists === after.repo_proposals_exists &&
      before.repo_proposals_sha256 === after.repo_proposals_sha256 &&
      JSON.stringify(before.empty_cwd_files) === JSON.stringify(after.empty_cwd_files) &&
      JSON.stringify(before.preserved) === JSON.stringify(after.preserved),
  },
  { id: "M8-M4", pass: before.m4.pass && after.m4.pass },
];

const result = {
  schema: "mneme.cm01.s1a1.m8/v1",
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
  fixtures: {
    normal: FIXTURE,
    normal_sha256: before.fixture_sha256,
    sectionless: SECTIONLESS,
    sectionless_sha256: before.sectionless_sha256,
    repository_memory_used: false,
  },
  runs: [run1, run2],
  normalized_evidence_equal: sameEvidence,
  checks,
  verdict: {
    pass: checks.every((check) => check.pass),
    failed: checks.filter((check) => !check.pass).map((check) => check.id),
  },
  no_mutation: { before, after },
  limitations: [
    "M8 failure-behavior probes only. No merge and no S1-A1 closure claim.",
    "Error cases compare classifications and behavior, not transport-envelope equality.",
    "No proposal method was invoked.",
    "No Cloudflare Workers, tunnel, live model, credentials, or repository project memory.",
  ],
};

writeFileSync(join(EVIDENCE, "m8.json"), `${JSON.stringify(result, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run1.json"), `${JSON.stringify(run1, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run2.json"), `${JSON.stringify(run2, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run1-stderr.log"), `${run1?.stderr ?? ""}\n`);
writeFileSync(join(EVIDENCE, "run2-stderr.log"), `${run2?.stderr ?? ""}\n`);
writeFileSync(join(EVIDENCE, "e4-run1-stderr.log"), `${run1?.e4?.stderr ?? ""}\n`);
writeFileSync(join(EVIDENCE, "e4-run2-stderr.log"), `${run2?.e4?.stderr ?? ""}\n`);
writeFileSync(join(EVIDENCE, "e5-run1-stderr.log"), `${run1?.e5?.stderr ?? ""}\n`);
writeFileSync(join(EVIDENCE, "e5-run2-stderr.log"), `${run2?.e5?.stderr ?? ""}\n`);

process.stdout.write(`${JSON.stringify(result.verdict)}\n`);
process.stdout.write(`${JSON.stringify({ checks, versions: result.versions }, null, 2)}\n`);
process.exit(result.verdict.pass ? 0 : 1);
