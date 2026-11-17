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

const M6_DIR = dirname(fileURLToPath(import.meta.url));
const S1A_DIR = dirname(M6_DIR);
const ROOT = resolve(M6_DIR, "../../../..");
const M1_DIR = join(S1A_DIR, "m1");
const M4_DIR = join(S1A_DIR, "m4");
const FIXTURE = join(M4_DIR, "fixture", "canonical", "project_memory.json");
const PRE_MIGRATION = join(M4_DIR, "fixture", "pre_migration.json");
const EMPTY_CWD = join(M1_DIR, "empty-cwd");
const EVIDENCE = join(M6_DIR, "evidence");
const READ_TOOLS = [
  "decision.get",
  "decision.search",
  "decision.applicable_to",
  "decision.trace",
];
const CASES = [
  { id: "active", args: { record_id: "ADR-9901" } },
  { id: "deprecated", args: { record_id: "ADR-9902" } },
  { id: "unknown", args: { record_id: "ADR-9999" } },
];
const TRACE_KEYS = [
  "canonical_decision_id",
  "canonical_record",
  "declared_test_evidence",
  "derived_rules",
  "missing_links",
  "result_type",
].sort();
const NOT_FOUND_KEYS = ["missing_links", "record_id", "result_type"].sort();

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
  const pkg = JSON.parse(readFileSync(join(M6_DIR, "package.json"), "utf8"));
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
  const client = new Client({ name: "cm01-m6", version: "0.1.0" });
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
      record: {
        decision_id: logical.decision_id,
        version: version?.revision ?? null,
        version_id: version?.version_id ?? null,
        decision_version_id: version?.version_id ?? null,
        content_digest: version?.content_digest ?? null,
        statement: version?.statement ?? null,
        rationale: version?.rationale ?? null,
        lifecycle_status: logical.lifecycle_status,
        constraints: version?.constraints ?? null,
        anti_patterns: version?.anti_patterns ?? null,
        relationships: logical.relationships ?? null,
        derived_rule_ids: rules.map((rule) => rule.rule_id),
      },
      rules: rules.map((rule) => ({
        rule_id: rule.rule_id,
        decision_id: rule.decision_id,
        decision_version: rule.decision_version,
        decision_version_id: rule.decision_version_id,
        sequence: rule.sequence,
        rule_type: rule.rule_type,
        rule_payload: rule.rule_payload,
        applicability: rule.applicability,
        lifecycle_status: "active",
      })),
      test_evidence: logical.test_evidence ?? [],
    };
  }
  return facts;
}

const TRACE_CODE = `async () => ({
  "active": await codemode.decision_trace({ record_id: "ADR-9901" }),
  "deprecated": await codemode.decision_trace({ record_id: "ADR-9902" }),
  "unknown": await codemode.decision_trace({ record_id: "ADR-9999" })
})`;

function recordMatches(actual, expected) {
  return [
    "decision_id",
    "version",
    "version_id",
    "decision_version_id",
    "content_digest",
    "statement",
    "rationale",
    "lifecycle_status",
    "constraints",
    "anti_patterns",
    "relationships",
    "derived_rule_ids",
  ].every(
    (key) =>
      JSON.stringify(stable(actual?.[key])) === JSON.stringify(stable(expected?.[key])),
  );
}

function ruleMatches(actual, expected) {
  return [
    "rule_id",
    "decision_id",
    "decision_version",
    "decision_version_id",
    "sequence",
    "rule_type",
    "rule_payload",
    "applicability",
    "lifecycle_status",
  ].every(
    (key) =>
      JSON.stringify(stable(actual?.[key])) === JSON.stringify(stable(expected?.[key])),
  );
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
  const executor = new QuickJSExecutor({ timeoutMs: 2000, memoryLimitBytes: 8 * 1024 * 1024 });
  const adapter = makeM2Adapter({ client, inventory, validators, executor });

  const direct = {};
  for (const testCase of CASES) {
    const raw = await client.callTool({
      name: "decision.trace",
      arguments: testCase.args,
    });
    direct[testCase.id] = { raw, normalized: normalizeMcpSuccess("decision.trace", raw) };
  }

  const codeModeOutput = await adapter.tool.execute({ code: TRACE_CODE });
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

  const active = direct.active.normalized;
  const deprecated = direct.deprecated.normalized;
  const unknown = direct.unknown.normalized;

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
    canonical_trace: {
      active_keys: Object.keys(active ?? {}).sort(),
      deprecated_keys: Object.keys(deprecated ?? {}).sort(),
      active_result_type: active?.result_type ?? null,
      deprecated_result_type: deprecated?.result_type ?? null,
      active_record_matches: recordMatches(active?.canonical_record, facts["ADR-9901"].record),
      deprecated_record_matches: recordMatches(deprecated?.canonical_record, facts["ADR-9902"].record),
      active_derived_rule_count: active?.derived_rules?.length ?? null,
      deprecated_derived_rule_count: deprecated?.derived_rules?.length ?? null,
      active_rule_matches: ruleMatches(active?.derived_rules?.[0], facts["ADR-9901"].rules[0]),
      active_missing_links: active?.missing_links ?? null,
      deprecated_missing_links: deprecated?.missing_links ?? null,
      declared_test_evidence_counts: {
        active: active?.declared_test_evidence?.length ?? null,
        deprecated: deprecated?.declared_test_evidence?.length ?? null,
        unknown: unknown?.declared_test_evidence?.length ?? null,
      },
      declared_evidence_has_verification_state: [
        ...(active?.declared_test_evidence ?? []),
        ...(deprecated?.declared_test_evidence ?? []),
      ].some((item) => "verification_state" in item || "verification_status" in item),
    },
    unknown: {
      keys: Object.keys(unknown ?? {}).sort(),
      result_type: unknown?.result_type ?? null,
      record_id: unknown?.record_id ?? null,
      missing_links: unknown?.missing_links ?? null,
      classified_as_proposal: "proposal" in (unknown ?? {}),
      classified_as_canonical: "canonical_decision" in (unknown ?? {}),
      type_unknown: unknown?.missing_links?.some((link) => link.startsWith("record_type: unknown")) ?? false,
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
    canonical_trace: run.canonical_trace,
    unknown: run.unknown,
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
  { id: "M6-UPSTREAM-SIX-1", pass: Boolean(run1?.upstream_inventory?.exact_six) },
  { id: "M6-UPSTREAM-SIX-2", pass: Boolean(run2?.upstream_inventory?.exact_six) },
  { id: "M6-PARITY-1", pass: Object.values(run1?.cases ?? {}).every((c) => c.equal) },
  { id: "M6-PARITY-2", pass: Object.values(run2?.cases ?? {}).every((c) => c.equal) },
  {
    id: "M6-ACTIVE-TRACE",
    pass:
      run1?.canonical_trace?.active_result_type === "canonical_trace" &&
      JSON.stringify(run1?.canonical_trace?.active_keys) === JSON.stringify(TRACE_KEYS) &&
      run1?.canonical_trace?.active_record_matches &&
      run1?.canonical_trace?.active_derived_rule_count === 1 &&
      run1?.canonical_trace?.active_rule_matches,
  },
  {
    id: "M6-DEPRECATED-TRACE",
    pass:
      run1?.canonical_trace?.deprecated_result_type === "canonical_trace" &&
      JSON.stringify(run1?.canonical_trace?.deprecated_keys) === JSON.stringify(TRACE_KEYS) &&
      run1?.canonical_trace?.deprecated_record_matches &&
      run1?.canonical_trace?.deprecated_derived_rule_count === 0,
  },
  {
    id: "M6-MISSING-LINKS",
    pass:
      run1?.canonical_trace?.active_missing_links?.join("|") ===
        "declared_test_evidence: none declared for canonical decision|enforcement_links: absent (enforcement points are not modelled in the current canonical kernel)" &&
      run1?.canonical_trace?.deprecated_missing_links?.join("|") ===
        "derived_rules: none recorded for canonical decision|declared_test_evidence: none declared for canonical decision|enforcement_links: absent (enforcement points are not modelled in the current canonical kernel)",
  },
  {
    id: "M6-UNKNOWN",
    pass:
      run1?.unknown?.result_type === "trace_not_found" &&
      run1?.unknown?.record_id === "ADR-9999" &&
      JSON.stringify(run1?.unknown?.keys) === JSON.stringify(NOT_FOUND_KEYS) &&
      !run1?.unknown?.classified_as_proposal &&
      !run1?.unknown?.classified_as_canonical &&
      run1?.unknown?.type_unknown,
  },
  {
    id: "M6-DECLARED-EVIDENCE",
    pass:
      run1?.canonical_trace?.declared_test_evidence_counts?.active === 0 &&
      run1?.canonical_trace?.declared_test_evidence_counts?.deprecated === 0 &&
      run1?.canonical_trace?.declared_evidence_has_verification_state === false,
  },
  {
    id: "M6-NO-PROPOSAL-CALLS",
    pass:
      run1?.adapter?.call_log?.length === 3 &&
      run2?.adapter?.call_log?.length === 3 &&
      run1?.adapter?.call_log?.every((call) => call.tool === "decision.trace") &&
      run2?.adapter?.call_log?.every((call) => call.tool === "decision.trace"),
  },
  { id: "M6-REPEAT", pass: Boolean(sameEvidence) },
  {
    id: "M6-NO-MUTATION",
    pass:
      before.fixture_sha256 === after.fixture_sha256 &&
      before.pre_migration_sha256 === after.pre_migration_sha256 &&
      before.repo_memory_sha256 === after.repo_memory_sha256 &&
      before.repo_proposals_exists === after.repo_proposals_exists &&
      before.repo_proposals_sha256 === after.repo_proposals_sha256 &&
      JSON.stringify(before.empty_cwd_files) === JSON.stringify(after.empty_cwd_files) &&
      JSON.stringify(before.preserved) === JSON.stringify(after.preserved),
  },
  { id: "M6-M4", pass: before.m4.pass && after.m4.pass },
];

const result = {
  schema: "mneme.cm01.s1a1.m6/v1",
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
    "M6 only: decision.trace parity. No M7-M8 acceptance tests.",
    "A trace is lineage only; it is not enforcement evidence or mutation permission.",
    "No proposal method was invoked.",
    "No Cloudflare Workers, tunnel, live model, credentials, or repository project memory.",
  ],
};

writeFileSync(join(EVIDENCE, "m6.json"), `${JSON.stringify(result, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run1.json"), `${JSON.stringify(run1, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run2.json"), `${JSON.stringify(run2, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run1-stderr.log"), `${run1?.stderr ?? ""}\n`);
writeFileSync(join(EVIDENCE, "run2-stderr.log"), `${run2?.stderr ?? ""}\n`);

process.stdout.write(`${JSON.stringify(result.verdict)}\n`);
process.stdout.write(`${JSON.stringify({ checks, versions: result.versions }, null, 2)}\n`);
process.exit(result.verdict.pass ? 0 : 1);
