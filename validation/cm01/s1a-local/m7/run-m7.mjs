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

const M7_DIR = dirname(fileURLToPath(import.meta.url));
const S1A_DIR = dirname(M7_DIR);
const ROOT = resolve(M7_DIR, "../../../..");
const M1_DIR = join(S1A_DIR, "m1");
const M4_DIR = join(S1A_DIR, "m4");
const FIXTURE = join(M4_DIR, "fixture", "canonical", "project_memory.json");
const PRE_MIGRATION = join(M4_DIR, "fixture", "pre_migration.json");
const EMPTY_CWD = join(M1_DIR, "empty-cwd");
const EVIDENCE = join(M7_DIR, "evidence");
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
  const pkg = JSON.parse(readFileSync(join(M7_DIR, "package.json"), "utf8"));
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
  const client = new Client({ name: "cm01-m7", version: "0.1.0" });
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

function fixtureIdentity() {
  const document = JSON.parse(readFileSync(FIXTURE, "utf8"));
  const section = document.decision_index;
  const logical = section.decisions.find((row) => row.decision_id === "ADR-9901");
  if (!logical) throw new Error("fixture has no ADR-9901");
  const version = section.versions.find(
    (row) => row.version_id === logical.active_version_id,
  );
  if (!version) throw new Error("fixture has no active ADR-9901 version");
  const rules = section.rules.filter(
    (row) => row.decision_version_id === version.version_id,
  );
  return {
    decision_id: logical.decision_id,
    version_id: version.version_id,
    content_digest: version.content_digest,
    derived_rule_ids: rules.map((rule) => rule.rule_id),
  };
}

function selectCanonical(searchResult) {
  const matches = (searchResult?.canonical_decisions ?? []).filter(
    (row) =>
      Array.isArray(row.context_scope) &&
      row.context_scope.includes("cache") &&
      row.lifecycle_status === "active",
  );
  if (matches.length !== 1) {
    throw new Error(`expected exactly one canonical cache/active decision, got ${matches.length}`);
  }
  return matches[0];
}

function identityOfSearch(row) {
  return {
    decision_id: row.decision_id,
    version_id: row.version_id,
    content_digest: row.content_digest,
    derived_rule_ids: row.derived_rule_ids,
  };
}

function identityOfGet(get) {
  const record = get?.canonical_decision;
  return {
    decision_id: record?.decision_id ?? null,
    version_id: record?.version_id ?? null,
    content_digest: record?.content_digest ?? null,
    derived_rule_ids: record?.derived_rule_ids ?? null,
  };
}

function identityOfTrace(trace) {
  const record = trace?.canonical_record;
  return {
    decision_id: trace?.canonical_decision_id ?? null,
    version_id: record?.version_id ?? null,
    content_digest: record?.content_digest ?? null,
    derived_rule_ids: record?.derived_rule_ids ?? null,
  };
}

function sameIdentity(left, right) {
  return ["decision_id", "version_id", "content_digest", "derived_rule_ids"].every(
    (key) => JSON.stringify(stable(left?.[key])) === JSON.stringify(stable(right?.[key])),
  );
}

const CHAIN_CODE = `async () => {
  const search = await codemode.decision_search({ query: "cache" });
  const matches = (search.canonical_decisions ?? []).filter(
    (row) => Array.isArray(row.context_scope) && row.context_scope.includes("cache") && row.lifecycle_status === "active"
  );
  if (matches.length !== 1) throw new Error("expected exactly one canonical cache/active decision, got " + matches.length);
  const selected = matches[0];
  const selectedId = selected.decision_id;
  const get = await codemode.decision_get({ record_id: selectedId });
  const gotId = get?.canonical_decision?.decision_id;
  if (!gotId) throw new Error("decision.get returned no canonical decision id");
  const trace = await codemode.decision_trace({ record_id: gotId });
  return {
    search,
    get,
    trace,
    selected_identity: {
      decision_id: selected.decision_id,
      version_id: selected.version_id,
      content_digest: selected.content_digest,
      derived_rule_ids: selected.derived_rule_ids
    },
    get_identity: {
      decision_id: gotId,
      version_id: get.canonical_decision.version_id,
      content_digest: get.canonical_decision.content_digest,
      derived_rule_ids: get.canonical_decision.derived_rule_ids
    },
    trace_identity: {
      decision_id: trace.canonical_decision_id,
      version_id: trace.canonical_record?.version_id,
      content_digest: trace.canonical_record?.content_digest,
      derived_rule_ids: trace.canonical_record?.derived_rule_ids
    }
  };
}`;

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
  const executor = new QuickJSExecutor({ timeoutMs: 3000, memoryLimitBytes: 8 * 1024 * 1024 });
  const adapter = makeM2Adapter({ client, inventory, validators, executor });

  const directCalls = [];
  const searchRaw = await client.callTool({
    name: "decision.search",
    arguments: { query: "cache" },
  });
  directCalls.push({ tool: "decision.search", args: { query: "cache" } });
  const search = normalizeMcpSuccess("decision.search", searchRaw);
  const selected = selectCanonical(search);
  const selectedId = selected.decision_id;

  const getRaw = await client.callTool({
    name: "decision.get",
    arguments: { record_id: selectedId },
  });
  directCalls.push({ tool: "decision.get", args: { record_id: selectedId } });
  const get = normalizeMcpSuccess("decision.get", getRaw);
  const gotId = get?.canonical_decision?.decision_id;
  if (!gotId) throw new Error("direct decision.get returned no canonical decision id");

  const traceRaw = await client.callTool({
    name: "decision.trace",
    arguments: { record_id: gotId },
  });
  directCalls.push({ tool: "decision.trace", args: { record_id: gotId } });
  const trace = normalizeMcpSuccess("decision.trace", traceRaw);

  const directResult = {
    search,
    get,
    trace,
    selected_identity: identityOfSearch(selected),
    get_identity: identityOfGet(get),
    trace_identity: identityOfTrace(trace),
  };

  let codeModeExecuteCalls = 0;
  codeModeExecuteCalls += 1;
  const codeModeOutput = await adapter.tool.execute({ code: CHAIN_CODE });
  const codeModeResult = codeModeOutput.result;
  const differences = diffValues(stable(directResult), stable(codeModeResult));

  const expected = fixtureIdentity();
  const identities = {
    selected: codeModeResult?.selected_identity ?? null,
    get: codeModeResult?.get_identity ?? null,
    trace: codeModeResult?.trace_identity ?? null,
  };
  const identityConsistent =
    sameIdentity(identities.selected, identities.get) &&
    sameIdentity(identities.get, identities.trace) &&
    sameIdentity(identities.selected, expected);

  const codeModeCalls = adapter.callLog.map((call) => ({
    seq: call.seq,
    tool: call.tool,
    args: call.args,
    isError: call.isError,
  }));

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
      call_log: codeModeCalls,
      schema_passthrough: Object.fromEntries(
        Object.entries(adapter.schemaHashes).map(([name, hashes]) => [
          name,
          hashes.upstream === hashes.descriptor,
        ]),
      ),
    },
    selected: {
      by: "canonical_decisions filtered by context_scope includes cache and lifecycle active",
      match_count: 1,
      decision_id: selectedId,
      selected_identity: identities.selected,
    },
    direct: {
      calls: directCalls,
      raw: { search: searchRaw, get: getRaw, trace: traceRaw },
      normalized: directResult,
    },
    code_mode: {
      execute_calls: codeModeExecuteCalls,
      raw: codeModeOutput,
      normalized: codeModeResult,
    },
    parity: {
      differences,
      equal: differences.length === 0,
    },
    identity: {
      expected,
      selected: identities.selected,
      get: identities.get,
      trace: identities.trace,
      consistent: identityConsistent,
    },
    downstream_hardcoded_id: /record_id:\s*["']ADR-9901["']/.test(CHAIN_CODE),
    call_sequence: {
      direct: directCalls.map((call) => call.tool),
      code_mode: codeModeCalls.map((call) => call.tool),
      expected: ["decision.search", "decision.get", "decision.trace"],
    },
    stderr: stderr.join(""),
    chain_code: CHAIN_CODE,
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
    selected: run.selected,
    direct_calls: run.direct.calls,
    direct_normalized: run.direct.normalized,
    code_mode_execute_calls: run.code_mode.execute_calls,
    code_mode_normalized: run.code_mode.normalized,
    parity: run.parity,
    identity: run.identity,
    downstream_hardcoded_id: run.downstream_hardcoded_id,
    call_sequence: run.call_sequence,
  };
}

const startedAt = new Date().toISOString();
const repoMemory = join(ROOT, ".mneme", "project_memory.json");
const repoProposals = join(ROOT, ".mneme", "decision_proposals.json");
const preservedBefore = preservedHashes();
const before = {
  fixture_sha256: sha256File(FIXTURE),
  pre_migration_sha256: sha256File(PRE_MIGRATION),
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
  { id: "M7-UPSTREAM-SIX-1", pass: Boolean(run1?.upstream_inventory?.exact_six) },
  { id: "M7-UPSTREAM-SIX-2", pass: Boolean(run2?.upstream_inventory?.exact_six) },
  { id: "M7-PARITY-1", pass: Boolean(run1?.parity?.equal) },
  { id: "M7-PARITY-2", pass: Boolean(run2?.parity?.equal) },
  {
    id: "M7-CALL-SEQUENCE",
    pass:
      JSON.stringify(run1?.call_sequence?.direct) === JSON.stringify(["decision.search", "decision.get", "decision.trace"]) &&
      JSON.stringify(run1?.call_sequence?.code_mode) === JSON.stringify(["decision.search", "decision.get", "decision.trace"]) &&
      JSON.stringify(run1?.direct?.calls) === JSON.stringify(run1?.adapter?.call_log?.map(({ tool, args }) => ({ tool, args }))),
  },
  { id: "M7-ONE-EXECUTE", pass: run1?.code_mode?.execute_calls === 1 && run2?.code_mode?.execute_calls === 1 },
  {
    id: "M7-DERIVED-ARGS",
    pass:
      run1?.downstream_hardcoded_id === false &&
      run1?.direct?.calls?.[1]?.args?.record_id === run1?.selected?.decision_id &&
      run1?.direct?.calls?.[2]?.args?.record_id === run1?.identity?.get?.decision_id &&
      run1?.adapter?.call_log?.[1]?.args?.record_id === run1?.selected?.decision_id &&
      run1?.adapter?.call_log?.[2]?.args?.record_id === run1?.identity?.get?.decision_id,
  },
  { id: "M7-IDENTITY", pass: Boolean(run1?.identity?.consistent) && Boolean(run2?.identity?.consistent) },
  {
    id: "M7-NO-PROPOSAL-CALLS",
    pass:
      run1?.adapter?.call_log?.length === 3 &&
      run2?.adapter?.call_log?.length === 3 &&
      run1?.adapter?.call_log?.every((call) => call.tool !== "decision.propose" && call.tool !== "decision.propose_batch") &&
      run2?.adapter?.call_log?.every((call) => call.tool !== "decision.propose" && call.tool !== "decision.propose_batch"),
  },
  { id: "M7-REPEAT", pass: Boolean(sameEvidence) },
  {
    id: "M7-NO-MUTATION",
    pass:
      before.fixture_sha256 === after.fixture_sha256 &&
      before.pre_migration_sha256 === after.pre_migration_sha256 &&
      before.repo_memory_sha256 === after.repo_memory_sha256 &&
      before.repo_proposals_exists === after.repo_proposals_exists &&
      before.repo_proposals_sha256 === after.repo_proposals_sha256 &&
      JSON.stringify(before.empty_cwd_files) === JSON.stringify(after.empty_cwd_files) &&
      JSON.stringify(before.preserved) === JSON.stringify(after.preserved),
  },
  { id: "M7-M4", pass: before.m4.pass && after.m4.pass },
];

const result = {
  schema: "mneme.cm01.s1a1.m7/v1",
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
    "M7 only: one fixed local Code Mode composition. No M8 error-class acceptance tests.",
    "No claim of fewer model calls, lower latency, or improved enforcement.",
    "A retrieval match is not mutation permission.",
    "No proposal method was invoked.",
    "No Cloudflare Workers, tunnel, live model, credentials, or repository project memory.",
  ],
};

writeFileSync(join(EVIDENCE, "m7.json"), `${JSON.stringify(result, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run1.json"), `${JSON.stringify(run1, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run2.json"), `${JSON.stringify(run2, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run1-stderr.log"), `${run1?.stderr ?? ""}\n`);
writeFileSync(join(EVIDENCE, "run2-stderr.log"), `${run2?.stderr ?? ""}\n`);

process.stdout.write(`${JSON.stringify(result.verdict)}\n`);
process.stdout.write(`${JSON.stringify({ checks, versions: result.versions }, null, 2)}\n`);
process.exit(result.verdict.pass ? 0 : 1);
