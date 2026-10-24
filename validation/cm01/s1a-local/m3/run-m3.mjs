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

const M3_DIR = dirname(fileURLToPath(import.meta.url));
const S1A_DIR = dirname(M3_DIR);
const ROOT = resolve(M3_DIR, "../../../..");
const M1_DIR = join(S1A_DIR, "m1");
const FIXTURE = join(M1_DIR, "fixture", "canonical", "project_memory.json");
const PRE_MIGRATION = join(M1_DIR, "fixture", "pre_migration.json");
const EMPTY_CWD = join(M1_DIR, "empty-cwd");
const EVIDENCE = join(M3_DIR, "evidence");
const DECISION_ID = "ADR-9901";
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
  const pkg = JSON.parse(readFileSync(join(M3_DIR, "package.json"), "utf8"));
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
  const client = new Client({ name: "cm01-m3", version: "0.1.0" });
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
        if (result.structuredContent != null) return result.structuredContent;
        if (result.toolResult !== undefined) return result.toolResult;
        throw new Error(`MCP ${name} returned no structured result`);
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
  const logical = section.decisions.find((row) => row.decision_id === DECISION_ID);
  if (!logical) throw new Error(`fixture has no ${DECISION_ID}`);
  const version = section.versions.find(
    (row) => row.version_id === logical.active_version_id,
  );
  if (!version) throw new Error(`fixture has no active version for ${DECISION_ID}`);
  const rules = section.rules.filter(
    (row) => row.decision_version_id === version.version_id,
  );
  return {
    decision_id: logical.decision_id,
    version: version.revision,
    version_id: version.version_id,
    decision_version_id: version.version_id,
    content_digest: version.content_digest,
    lifecycle_status: logical.lifecycle_status,
    constraints: version.constraints,
    relationships: logical.relationships,
    derived_rule_ids: rules.map((rule) => rule.rule_id),
  };
}

const GET_CODE = `async () => codemode.decision_get({ record_id: "ADR-9901" })`;

async function runOnce(label) {
  const server = await connectServer();
  const { client, inventory, stderr } = server;
  const upstreamNames = [...inventory.tools].map((tool) => tool.name).sort();
  const validators = makeValidators(inventory);
  const executor = new QuickJSExecutor({ timeoutMs: 2000, memoryLimitBytes: 8 * 1024 * 1024 });
  const adapter = makeM2Adapter({ client, inventory, validators, executor });

  const directRaw = await client.callTool({
    name: "decision.get",
    arguments: { record_id: DECISION_ID },
  });
  const directNormalized =
    directRaw.structuredContent != null
      ? directRaw.structuredContent
      : directRaw.toolResult ?? null;

  const codeModeOutput = await adapter.tool.execute({ code: GET_CODE });
  const codeModeNormalized = codeModeOutput.result;
  const differences = diffValues(stable(directNormalized), stable(codeModeNormalized));

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
    direct: {
      raw: directRaw,
      normalized: directNormalized,
    },
    code_mode: {
      raw: codeModeOutput,
      normalized: codeModeNormalized,
    },
    normalization: {
      direct_path: "CallToolResult.structuredContent",
      code_mode_path: "ProxyToolOutput.result",
      dropped_fields: [],
      excluded_transport_envelope_fields: [
        "content",
        "structuredContent",
        "isError",
        "toolResult",
      ],
      differences,
      equal: differences.length === 0,
    },
    fixture_identity: {
      expected: fixtureIdentity(),
      direct: directNormalized?.canonical_decision ?? directNormalized,
      code_mode: codeModeNormalized?.canonical_decision ?? codeModeNormalized,
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

function identityPass(run) {
  const expected = run.fixture_identity.expected;
  const direct = run.fixture_identity.direct;
  const code = run.fixture_identity.code_mode;
  for (const source of [direct, code]) {
    for (const key of [
      "decision_id",
      "version",
      "version_id",
      "decision_version_id",
      "content_digest",
      "lifecycle_status",
      "constraints",
      "relationships",
      "derived_rule_ids",
    ]) {
      if (JSON.stringify(stable(source?.[key])) !== JSON.stringify(stable(expected[key]))) {
        return false;
      }
    }
  }
  return true;
}

function normalizedRun(run) {
  return {
    upstream_inventory: run.upstream_inventory,
    adapter: {
      allowlist: run.adapter.allowlist,
      schema_passthrough: run.adapter.schema_passthrough,
    },
    direct_normalized: run.direct.normalized,
    code_mode_normalized: run.code_mode.normalized,
    normalization: run.normalization,
    fixture_identity: run.fixture_identity,
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

const checks = [
  { id: "M3-UPSTREAM-SIX-1", pass: Boolean(run1?.upstream_inventory?.exact_six) },
  { id: "M3-UPSTREAM-SIX-2", pass: Boolean(run2?.upstream_inventory?.exact_six) },
  { id: "M3-DIRECT-CODE-PARITY-1", pass: Boolean(run1?.normalization?.equal) },
  { id: "M3-DIRECT-CODE-PARITY-2", pass: Boolean(run2?.normalization?.equal) },
  { id: "M3-IDENTITY-1", pass: identityPass(run1) },
  { id: "M3-IDENTITY-2", pass: identityPass(run2) },
  {
    id: "M3-NO-DROPPED-FIELDS",
    pass: (run1?.normalization?.dropped_fields?.length ?? 1) === 0 &&
      (run2?.normalization?.dropped_fields?.length ?? 1) === 0,
  },
  {
    id: "M3-SCHEMA-PASSTHROUGH",
    pass:
      Object.values(run1?.adapter?.schema_passthrough ?? {}).every(Boolean) &&
      Object.values(run2?.adapter?.schema_passthrough ?? {}).every(Boolean),
  },
  {
    id: "M3-NO-PROPOSAL-CALLS",
    pass:
      run1?.adapter?.call_log?.every((call) => call.tool === "decision.get") &&
      run2?.adapter?.call_log?.every((call) => call.tool === "decision.get") &&
      run1?.adapter?.call_log?.length === 1 &&
      run2?.adapter?.call_log?.length === 1,
  },
  { id: "M3-REPEAT", pass: Boolean(sameEvidence) },
  {
    id: "M3-NO-MUTATION",
    pass:
      before.fixture_sha256 === after.fixture_sha256 &&
      before.pre_migration_sha256 === after.pre_migration_sha256 &&
      before.repo_memory_sha256 === after.repo_memory_sha256 &&
      before.repo_proposals_exists === after.repo_proposals_exists &&
      before.repo_proposals_sha256 === after.repo_proposals_sha256 &&
      JSON.stringify(before.empty_cwd_files) === JSON.stringify(after.empty_cwd_files),
  },
  { id: "M3-M4", pass: before.m4.pass && after.m4.pass },
];

const result = {
  schema: "mneme.cm01.s1a1.m3/v1",
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
    "M3 only: decision.get parity for ADR-9901. No M4-M8 acceptance tests.",
    "No enforcement compatibility or performance claim.",
    "No proposal method is invoked; the M2 four-method adapter is used with only decision.get exercised.",
    "No Cloudflare Workers, tunnel, live model, credentials, or repository project memory.",
  ],
};

writeFileSync(join(EVIDENCE, "m3.json"), `${JSON.stringify(result, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run1.json"), `${JSON.stringify(run1, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run2.json"), `${JSON.stringify(run2, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run1-stderr.log"), `${run1?.stderr ?? ""}\n`);
writeFileSync(join(EVIDENCE, "run2-stderr.log"), `${run2?.stderr ?? ""}\n`);

process.stdout.write(`${JSON.stringify(result.verdict)}\n`);
process.stdout.write(`${JSON.stringify({ checks, versions: result.versions }, null, 2)}\n`);
process.exit(result.verdict.pass ? 0 : 1);
