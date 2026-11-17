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
import { checkM4Protection, DEFAULT_BASE_SHA, S0_SHA } from "../m4-guard.mjs";

const M2_DIR = dirname(fileURLToPath(import.meta.url));
const S1A_DIR = dirname(M2_DIR);
const ROOT = resolve(M2_DIR, "../../../..");
const M1_DIR = join(S1A_DIR, "m1");
const FIXTURE = join(M1_DIR, "fixture", "canonical", "project_memory.json");
const PRE_MIGRATION = join(M1_DIR, "fixture", "pre_migration.json");
const EMPTY_CWD = join(M1_DIR, "empty-cwd");
const EVIDENCE = join(M2_DIR, "evidence");
const READ_TOOLS = [
  "decision.get",
  "decision.search",
  "decision.applicable_to",
  "decision.trace",
];
const EXPECTED_SANITIZED = {
  "decision.get": "decision_get",
  "decision.search": "decision_search",
  "decision.applicable_to": "decision_applicable_to",
  "decision.trace": "decision_trace",
  "decision.propose": "decision_propose",
  "decision.propose_batch": "decision_propose_batch",
};
const EXPECTED_TOOLS = Object.keys(EXPECTED_SANITIZED).sort();

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

function listEmptyCwd() {
  return execFileSync("git", ["ls-files", "--others", "--exclude-standard"], {
    cwd: EMPTY_CWD,
    encoding: "utf8",
  })
    .split(/\r?\n/)
    .filter(Boolean);
}

function versions() {
  const pkg = JSON.parse(readFileSync(join(M2_DIR, "package.json"), "utf8"));
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
  if (result.toolResult !== undefined) return result.toolResult;
  if (result.structuredContent != null) return result.structuredContent;
  const text = textContent(result);
  if (!text) {
    throw new Error(`MCP ${toolName} returned no structured content and no text`);
  }
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`MCP ${toolName} returned non-JSON text where a typed result was required`);
  }
}

function mcpCall(method, args) {
  return { method, args };
}

async function connectServer() {
  const stderr = [];
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
  const client = new Client({ name: "cm01-m2", version: "0.1.0" });
  transport.stderr?.on("data", (chunk) => stderr.push(chunk.toString("utf8")));
  await client.connect(transport);
  const inventory = await client.listTools();
  return { client, transport, inventory, stderr };
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

function makeAdapter({ client, inventory, validators, executor, validate = true }) {
  const callLog = [];
  const descriptors = {};
  const schemaHashes = {};
  const schemas = {};
  const byName = new Map(inventory.tools.map((tool) => [tool.name, tool]));

  for (const name of READ_TOOLS) {
    const tool = byName.get(name);
    if (!tool) throw new Error(`missing upstream tool ${name}`);
    const beforeHash = schemaHash(tool.inputSchema);
    schemaHashes[name] = { upstream: beforeHash };
    schemas[name] = tool.inputSchema;
    descriptors[name] = {
      description: tool.description,
      inputSchema: tool.inputSchema,
      execute: async (args) => {
        if (validate) {
          const validator = validators.get(name);
          if (!validator(args)) {
            const detail = JSON.stringify(validator.errors ?? null);
            throw new Error(`Argument validation failed for ${name}: ${detail}`);
          }
        }

        const seq = callLog.length + 1;
        let result;
        try {
          result = await client.callTool({ name, arguments: args });
        } catch (error) {
          const message = error?.message || String(error);
          callLog.push({
            seq,
            tool: name,
            args,
            isError: true,
            structuredContent: null,
            toolResult: null,
            text: message,
          });
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
    schemaHashes[name].descriptor = schemaHash(descriptors[name].inputSchema);
  }

  const tool = createBrowserCodeTool({ tools: descriptors, executor });
  return { tool, callLog, schemaHashes, schemas };
}

const SUCCESS_CODE = `async () => {
  const get = await codemode.decision_get({ record_id: "ADR-9901" });
  const search = await codemode.decision_search({ query: "cache", canonical_lifecycle_status: "active" });
  const applicable = await codemode.decision_applicable_to({ context: ["cache"] });
  const trace = await codemode.decision_trace({ record_id: "ADR-9901" });
  return { get, search, applicable, trace };
}`;

const NEGATIVE_CODE = `async () => ({
  get: typeof codemode.decision_get,
  search: typeof codemode.decision_search,
  applicable: typeof codemode.decision_applicable_to,
  trace: typeof codemode.decision_trace,
  propose: typeof codemode.decision_propose,
  propose_batch: typeof codemode.decision_propose_batch
})`;

const ERROR_CODE = `async () => codemode.decision_search({ canonical_lifecycle_status: "bogus" })`;
const VALIDATION_CODE = `async () => codemode.decision_get({ record_id: 123 })`;

async function executeWith(tool, code, executor) {
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

function normalizeCallLog(callLog) {
  return callLog.map((entry) => ({
    seq: entry.seq,
    tool: entry.tool,
    args: entry.args,
    isError: entry.isError,
    structuredContent: entry.structuredContent,
    toolResult: entry.toolResult,
    text: entry.text,
  }));
}

async function runOnce(label) {
  const server = await connectServer();
  const { client, inventory, stderr } = server;
  const tools = [...inventory.tools].sort((a, b) => a.name.localeCompare(b.name));
  const upstreamNames = tools.map((tool) => tool.name);
  const sanitized = Object.fromEntries(
    upstreamNames.map((name) => {
      const method = EXPECTED_SANITIZED[name] ?? name.replace(/[^a-zA-Z0-9_$]/g, "_");
      return [name, method];
    }),
  );
  const sanitizedValues = Object.values(sanitized);
  const collisionFree = new Set(sanitizedValues).size === sanitizedValues.length;
  const validators = makeValidators(inventory);

  const executor = new QuickJSExecutor({ timeoutMs: 2000, memoryLimitBytes: 8 * 1024 * 1024 });
  const adapter = makeAdapter({ client, inventory, validators, executor, validate: true });
  const success = await executeWith(adapter.tool, SUCCESS_CODE, executor);
  const negative = await executeWith(adapter.tool, NEGATIVE_CODE, executor);

  const errorExecutor = new QuickJSExecutor({ timeoutMs: 2000, memoryLimitBytes: 8 * 1024 * 1024 });
  const errorAdapter = makeAdapter({ client, inventory, validators, executor: errorExecutor, validate: false });
  const errorProbe = await executeWith(errorAdapter.tool, ERROR_CODE, errorExecutor);

  const validationExecutor = new QuickJSExecutor({ timeoutMs: 2000, memoryLimitBytes: 8 * 1024 * 1024 });
  const validationAdapter = makeAdapter({ client, inventory, validators, executor: validationExecutor, validate: true });
  const validationProbe = await executeWith(validationAdapter.tool, VALIDATION_CODE, validationExecutor);

  const result = {
    run: label,
    pid: server.transport.pid,
    upstream_inventory: {
      count: upstreamNames.length,
      names: upstreamNames,
      exact_six: JSON.stringify([...upstreamNames].sort()) === JSON.stringify(EXPECTED_TOOLS),
    },
    upstream_tools: tools,
    allowlist: READ_TOOLS,
    adapter_schemas: adapter.schemas,
    sanitized_names: sanitized,
    collision_free: collisionFree,
    schema_passthrough: Object.fromEntries(
      Object.entries(adapter.schemaHashes).map(([name, hashes]) => [
        name,
        hashes.upstream === hashes.descriptor,
      ]),
    ),
    success: {
      ...success,
      calls: normalizeCallLog(adapter.callLog),
    },
    negative_capability: negative,
    mcp_error_probe: {
      ...errorProbe,
      validation_bypassed: true,
      calls: normalizeCallLog(errorAdapter.callLog),
    },
    validation_probe: {
      ...validationProbe,
      host_validated: true,
      calls: normalizeCallLog(validationAdapter.callLog),
    },
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

function successShapes(run) {
  const result = run.success.result;
  if (!result) return false;
  const get = result.get;
  const search = result.search;
  const applicable = result.applicable;
  const trace = result.trace;
  return (
    get?.record_type === "canonical_decision" &&
    get?.canonical_decision?.decision_id === "ADR-9901" &&
    Array.isArray(search?.canonical_decisions) &&
    search.canonical_decisions.some((row) => row.decision_id === "ADR-9901") &&
    Array.isArray(applicable?.canonical_scope_matches) &&
    applicable.canonical_scope_matches.some((row) => row.decision_id === "ADR-9901") &&
    trace?.result_type === "canonical_trace" &&
    trace?.canonical_decision_id === "ADR-9901" &&
    Array.isArray(trace?.derived_rules) &&
    trace.derived_rules.length === 1
  );
}

function successCallOrder(run) {
  return run.success.calls.map((call) => call.tool);
}

const startedAt = new Date().toISOString();
const repoMemory = join(ROOT, ".mneme", "project_memory.json");
const repoProposals = join(ROOT, ".mneme", "decision_proposals.json");
const before = {
  fixture_sha256: sha256File(FIXTURE),
  pre_migration_sha256: sha256File(PRE_MIGRATION),
  repo_memory_sha256: existsSync(repoMemory) ? sha256File(repoMemory) : null,
  repo_proposals_exists: existsSync(repoProposals),
  repo_proposals_sha256: existsSync(repoProposals) ? sha256File(repoProposals) : null,
  empty_cwd_files: listEmptyCwd(),
  m4: checkM4Protection({ cwd: ROOT, baseSha: DEFAULT_BASE_SHA }),
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

const after = {
  fixture_sha256: sha256File(FIXTURE),
  pre_migration_sha256: sha256File(PRE_MIGRATION),
  repo_memory_sha256: existsSync(repoMemory) ? sha256File(repoMemory) : null,
  repo_proposals_exists: existsSync(repoProposals),
  repo_proposals_sha256: existsSync(repoProposals) ? sha256File(repoProposals) : null,
  empty_cwd_files: listEmptyCwd(),
  m4: checkM4Protection({ cwd: ROOT, baseSha: DEFAULT_BASE_SHA }),
};

const normalizedRun = (run) => ({
  upstream_inventory: run.upstream_inventory,
  upstream_tools: run.upstream_tools,
  allowlist: run.allowlist,
  adapter_schemas: run.adapter_schemas,
  sanitized_names: run.sanitized_names,
  collision_free: run.collision_free,
  schema_passthrough: run.schema_passthrough,
  success_result: run.success?.result ?? null,
  success_calls: run.success?.calls ?? null,
  negative_capability: run.negative_capability?.result ?? null,
  mcp_error: {
    error: run.mcp_error_probe?.error ?? null,
    calls: run.mcp_error_probe?.calls ?? null,
  },
  validation: {
    error: run.validation_probe?.error ?? null,
    calls: run.validation_probe?.calls ?? null,
  },
});

const sameEvidence =
  JSON.stringify(normalizedRun(run1)) === JSON.stringify(normalizedRun(run2));

const checks = [
  { id: "M2-UPSTREAM-SIX-1", pass: Boolean(run1?.upstream_inventory?.exact_six) },
  { id: "M2-UPSTREAM-SIX-2", pass: Boolean(run2?.upstream_inventory?.exact_six) },
  {
    id: "M2-ALLOWLIST",
    pass: READ_TOOLS.every((name) => Object.hasOwn(run1?.sanitized_names ?? {}, name)),
  },
  {
    id: "M2-NO-COLLISIONS",
    pass: Boolean(run1?.collision_free) && Boolean(run2?.collision_free),
  },
  {
    id: "M2-SCHEMA-PASSTHROUGH",
    pass:
      run1?.schema_passthrough &&
      Object.values(run1.schema_passthrough).every(Boolean) &&
      run2?.schema_passthrough &&
      Object.values(run2.schema_passthrough).every(Boolean),
  },
  {
    id: "M2-SUCCESS-1",
    pass:
      !run1?.success?.error &&
      successShapes(run1) &&
      JSON.stringify(successCallOrder(run1)) === JSON.stringify(READ_TOOLS) &&
      run1.success.calls.length === 4,
  },
  {
    id: "M2-SUCCESS-2",
    pass:
      !run2?.success?.error &&
      successShapes(run2) &&
      JSON.stringify(successCallOrder(run2)) === JSON.stringify(READ_TOOLS) &&
      run2.success.calls.length === 4,
  },
  {
    id: "M2-NO-PROPOSAL-METHODS",
    pass:
      run1?.negative_capability?.result?.propose === "undefined" &&
      run1?.negative_capability?.result?.propose_batch === "undefined" &&
      run2?.negative_capability?.result?.propose === "undefined" &&
      run2?.negative_capability?.result?.propose_batch === "undefined",
  },
  {
    id: "M2-MCP-ERROR-PROPAGATES",
    pass:
      Boolean(run1?.mcp_error_probe?.error) &&
      Boolean(run2?.mcp_error_probe?.error) &&
      run1.mcp_error_probe.calls?.some((call) => call.isError) &&
      run2.mcp_error_probe.calls?.some((call) => call.isError) &&
      !run1.mcp_error_probe.calls?.some((call) => call.structuredContent != null),
  },
  {
    id: "M2-HOST-VALIDATION",
    pass:
      Boolean(run1?.validation_probe?.error) &&
      Boolean(run2?.validation_probe?.error) &&
      run1.validation_probe.calls?.length === 0 &&
      run2.validation_probe.calls?.length === 0 &&
      /Argument validation failed/.test(run1.validation_probe.error) &&
      /Argument validation failed/.test(run2.validation_probe.error),
  },
  { id: "M2-REPEAT", pass: Boolean(sameEvidence) },
  {
    id: "M2-NO-MUTATION",
    pass:
      before.fixture_sha256 === after.fixture_sha256 &&
      before.pre_migration_sha256 === after.pre_migration_sha256 &&
      before.repo_memory_sha256 === after.repo_memory_sha256 &&
      before.repo_proposals_exists === after.repo_proposals_exists &&
      before.repo_proposals_sha256 === after.repo_proposals_sha256 &&
      JSON.stringify(before.empty_cwd_files) === JSON.stringify(after.empty_cwd_files),
  },
  { id: "M2-M4", pass: before.m4.pass && after.m4.pass },
];

const result = {
  schema: "mneme.cm01.s1a1.m2/v1",
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
  fixture: {
    path: FIXTURE,
    sha256: before.fixture_sha256,
    pre_migration_sha256: before.pre_migration_sha256,
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
    "M2 only: one local Code Mode execution per run for the four read methods; no M3-M8 acceptance.",
    "The MCP error probe intentionally bypasses host validation to prove server-side errors do not become empty successes; the normal adapter validates at the host boundary.",
    "No full output parity or enforcement-compatibility claim.",
    "Proposal tools are not exposed to Code Mode and are never called.",
    "No Cloudflare Workers, tunnel, live model, credentials, or repository project memory.",
  ],
};

writeFileSync(join(EVIDENCE, "m2.json"), `${JSON.stringify(result, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run1.json"), `${JSON.stringify(run1, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run2.json"), `${JSON.stringify(run2, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run1-stderr.log"), `${run1?.stderr ?? ""}\n`);
writeFileSync(join(EVIDENCE, "run2-stderr.log"), `${run2?.stderr ?? ""}\n`);

process.stdout.write(`${JSON.stringify(result.verdict)}\n`);
process.stdout.write(`${JSON.stringify({ checks, versions: result.versions }, null, 2)}\n`);
process.exit(result.verdict.pass ? 0 : 1);
