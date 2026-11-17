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

const M4_DIR = dirname(fileURLToPath(import.meta.url));
const S1A_DIR = dirname(M4_DIR);
const ROOT = resolve(M4_DIR, "../../../..");
const M1_DIR = join(S1A_DIR, "m1");
const FIXTURE = join(M1_DIR, "fixture", "canonical", "project_memory.json");
const PRE_MIGRATION = join(M1_DIR, "fixture", "pre_migration.json");
const EMPTY_CWD = join(M1_DIR, "empty-cwd");
const EVIDENCE = join(M4_DIR, "evidence");
const READ_TOOLS = [
  "decision.get",
  "decision.search",
  "decision.applicable_to",
  "decision.trace",
];
const CASES = [
  { id: "query-cache", args: { query: "cache" } },
  { id: "active", args: { query: "", canonical_lifecycle_status: "active" } },
  { id: "deprecated", args: { query: "", canonical_lifecycle_status: "deprecated" } },
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
  const pkg = JSON.parse(readFileSync(join(M4_DIR, "package.json"), "utf8"));
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
  const client = new Client({ name: "cm01-m4", version: "0.1.0" });
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

function makeM2Adapter({ client, inventory, validators, executor }) {
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
        const validator = validators.get(name);
        if (!validator(args)) {
          throw new Error(
            `Argument validation failed for ${name}: ${JSON.stringify(validator.errors ?? null)}`,
          );
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

function fixtureFacts() {
  const document = JSON.parse(readFileSync(FIXTURE, "utf8"));
  const section = document.decision_index;
  const facts = {};
  for (const logical of section.decisions) {
    const version = section.versions.find(
      (row) => row.version_id === logical.active_version_id,
    );
    const rules = version
      ? section.rules.filter((row) => row.decision_version_id === version.version_id)
      : [];
    facts[logical.decision_id] = {
      decision_id: logical.decision_id,
      lifecycle_status: logical.lifecycle_status,
      version: version?.revision ?? null,
      version_id: version?.version_id ?? null,
      decision_version_id: version?.version_id ?? null,
      content_digest: version?.content_digest ?? null,
      constraints: version?.constraints ?? null,
      relationships: logical.relationships ?? null,
      derived_rule_ids: rules.map((rule) => rule.rule_id),
    };
  }
  return facts;
}

const SEARCH_CODE = `async () => ({
  "query-cache": await codemode.decision_search({ query: "cache" }),
  "active": await codemode.decision_search({ query: "", canonical_lifecycle_status: "active" }),
  "deprecated": await codemode.decision_search({ query: "", canonical_lifecycle_status: "deprecated" })
})`;

function findDecision(document, decisionId) {
  for (const row of document?.canonical_decisions ?? []) {
    if (row.decision_id === decisionId) return row;
  }
  return null;
}

function identityMatches(actual, expected) {
  if (!actual || !expected) return false;
  return [
    "decision_id",
    "version",
    "version_id",
    "decision_version_id",
    "content_digest",
    "lifecycle_status",
    "constraints",
    "relationships",
    "derived_rule_ids",
  ].every(
    (key) =>
      JSON.stringify(stable(actual[key])) === JSON.stringify(stable(expected[key])),
  );
}

async function runOnce(label) {
  const server = await connectServer();
  const { client, inventory, stderr } = server;
  const upstreamNames = [...inventory.tools].map((tool) => tool.name).sort();
  const validators = makeValidators(inventory);
  const executor = new QuickJSExecutor({ timeoutMs: 2000, memoryLimitBytes: 8 * 1024 * 1024 });
  const adapter = makeM2Adapter({ client, inventory, validators, executor });

  const direct = {};
  for (const testCase of CASES) {
    const raw = await client.callTool({
      name: "decision.search",
      arguments: testCase.args,
    });
    direct[testCase.id] = { raw, normalized: normalizeMcpSuccess("decision.search", raw) };
  }

  const codeModeOutput = await adapter.tool.execute({ code: SEARCH_CODE });
  const codeMode = codeModeOutput.result;
  const facts = fixtureFacts();

  const cases = {};
  for (const testCase of CASES) {
    const differences = diffValues(
      stable(direct[testCase.id].normalized),
      stable(codeMode[testCase.id]),
    );
    cases[testCase.id] = {
      args: testCase.args,
      direct_normalized: direct[testCase.id].normalized,
      code_mode_normalized: codeMode[testCase.id],
      differences,
      equal: differences.length === 0,
    };
  }

  const queryCache = direct["query-cache"].normalized;
  const active = direct.active.normalized;
  const deprecated = direct.deprecated.normalized;
  const adr9901Query = findDecision(queryCache, "ADR-9901");
  const adr9901Active = findDecision(active, "ADR-9901");
  const adr9902Deprecated = findDecision(deprecated, "ADR-9902");

  const result = {
    run: label,
    pid: server.transport.pid,
    upstream_inventory: {
      count: upstreamNames.length,
      names: upstreamNames,
      exact_six: upstreamNames.length === 6,
    },
    adapter: {
      allowlist: READ_TOOLS,
      call_log: adapter.callLog,
      schema_passthrough: Object.fromEntries(
        Object.entries(adapter.schemaHashes).map(([name, hashes]) => [
          name,
          hashes.upstream === hashes.descriptor,
        ]),
      ),
    },
    fixture_facts: facts,
    cases,
    direct_raw: Object.fromEntries(
      CASES.map((testCase) => [testCase.id, direct[testCase.id].raw]),
    ),
    code_mode_raw: codeModeOutput,
    separation: {
      proposals_is_array_query: Array.isArray(queryCache?.proposals),
      canonical_is_array_query: Array.isArray(queryCache?.canonical_decisions),
      proposals_is_array_active: Array.isArray(active?.proposals),
      canonical_is_array_active: Array.isArray(active?.canonical_decisions),
      proposals_is_array_deprecated: Array.isArray(deprecated?.proposals),
      canonical_is_array_deprecated: Array.isArray(deprecated?.canonical_decisions),
      query_keys: Object.keys(queryCache ?? {}).sort(),
    },
    lifecycle: {
      adr9901_in_query_cache: Boolean(adr9901Query),
      adr9901_in_active: Boolean(adr9901Active),
      adr9902_in_deprecated: Boolean(adr9902Deprecated),
      adr9901_query_lifecycle: adr9901Query?.lifecycle_status ?? null,
      adr9901_active_lifecycle: adr9901Active?.lifecycle_status ?? null,
      adr9902_deprecated_lifecycle: adr9902Deprecated?.lifecycle_status ?? null,
      fixture_decision_ids: Object.keys(facts).sort(),
    },
    identity: {
      adr9901_query: identityMatches(adr9901Query, facts["ADR-9901"]),
      adr9901_active: identityMatches(adr9901Active, facts["ADR-9901"]),
      adr9902_deprecated: identityMatches(adr9902Deprecated, facts["ADR-9902"]),
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

function normalizedRun(run) {
  return {
    upstream_inventory: run.upstream_inventory,
    adapter: {
      allowlist: run.adapter.allowlist,
      schema_passthrough: run.adapter.schema_passthrough,
    },
    fixture_facts: run.fixture_facts,
    cases: run.cases,
    separation: run.separation,
    lifecycle: run.lifecycle,
    identity: run.identity,
  };
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

const sameEvidence =
  JSON.stringify(normalizedRun(run1)) === JSON.stringify(normalizedRun(run2));
const allCasesEqual =
  Object.values(run1?.cases ?? {}).every((testCase) => testCase.equal) &&
  Object.values(run2?.cases ?? {}).every((testCase) => testCase.equal);

const checks = [
  { id: "M4-UPSTREAM-SIX-1", pass: Boolean(run1?.upstream_inventory?.exact_six) },
  { id: "M4-UPSTREAM-SIX-2", pass: Boolean(run2?.upstream_inventory?.exact_six) },
  { id: "M4-PARITY-1", pass: Object.values(run1?.cases ?? {}).every((c) => c.equal) },
  { id: "M4-PARITY-2", pass: Object.values(run2?.cases ?? {}).every((c) => c.equal) },
  {
    id: "M4-SEPARATION",
    pass:
      run1?.separation?.query_keys?.join(",") === "canonical_decisions,proposals" &&
      run2?.separation?.query_keys?.join(",") === "canonical_decisions,proposals" &&
      run1?.separation?.proposals_is_array_query &&
      run1?.separation?.canonical_is_array_query,
  },
  {
    id: "M4-ADR9901-ACTIVE",
    pass:
      run1?.lifecycle?.adr9901_in_query_cache &&
      run1?.lifecycle?.adr9901_in_active &&
      run1?.lifecycle?.adr9901_query_lifecycle === "active" &&
      run1?.lifecycle?.adr9901_active_lifecycle === "active",
  },
  {
    id: "M4-ADR9902-DEPRECATED",
    pass:
      run1?.lifecycle?.adr9902_in_deprecated &&
      run1?.lifecycle?.adr9902_deprecated_lifecycle === "deprecated",
  },
  {
    id: "M4-IDENTITY",
    pass:
      run1?.identity?.adr9901_query &&
      run1?.identity?.adr9901_active &&
      run1?.identity?.adr9902_deprecated,
  },
  {
    id: "M4-NO-PROPOSAL-CALLS",
    pass:
      run1?.adapter?.call_log?.length === 3 &&
      run2?.adapter?.call_log?.length === 3 &&
      run1?.adapter?.call_log?.every((call) => call.tool === "decision.search") &&
      run2?.adapter?.call_log?.every((call) => call.tool === "decision.search"),
  },
  { id: "M4-REPEAT", pass: Boolean(sameEvidence) },
  {
    id: "M4-NO-MUTATION",
    pass:
      before.fixture_sha256 === after.fixture_sha256 &&
      before.pre_migration_sha256 === after.pre_migration_sha256 &&
      before.repo_memory_sha256 === after.repo_memory_sha256 &&
      before.repo_proposals_exists === after.repo_proposals_exists &&
      before.repo_proposals_sha256 === after.repo_proposals_sha256 &&
      JSON.stringify(before.empty_cwd_files) === JSON.stringify(after.empty_cwd_files),
  },
  { id: "M4-M4", pass: before.m4.pass && after.m4.pass },
];

const missingAdr9902 = !run1?.lifecycle?.adr9902_in_deprecated;
const result = {
  schema: "mneme.cm01.s1a1.m4/v1",
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
  blocker: missingAdr9902
    ? "Frozen M1 canonical fixture contains only ADR-9901; ADR-9902 is absent, so the deprecated lifecycle search returns an empty canonical list. The fixture cannot be changed under M4's preservation boundary."
    : null,
  no_mutation: { before, after },
  limitations: [
    "M4 search parity only. No M5-M8 acceptance tests.",
    "No enforcement compatibility or performance claim.",
    "No proposal method was invoked.",
    "No Cloudflare Workers, tunnel, live model, credentials, or repository project memory.",
  ],
};

writeFileSync(join(EVIDENCE, "m4.json"), `${JSON.stringify(result, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run1.json"), `${JSON.stringify(run1, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run2.json"), `${JSON.stringify(run2, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run1-stderr.log"), `${run1?.stderr ?? ""}\n`);
writeFileSync(join(EVIDENCE, "run2-stderr.log"), `${run2?.stderr ?? ""}\n`);

process.stdout.write(`${JSON.stringify(result.verdict)}\n`);
process.stdout.write(`${JSON.stringify({ checks, blocker: result.blocker }, null, 2)}\n`);
process.exit(result.verdict.pass ? 0 : 1);
