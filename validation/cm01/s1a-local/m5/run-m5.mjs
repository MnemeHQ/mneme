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

const M5_DIR = dirname(fileURLToPath(import.meta.url));
const S1A_DIR = dirname(M5_DIR);
const ROOT = resolve(M5_DIR, "../../../..");
const M1_DIR = join(S1A_DIR, "m1");
const M4_DIR = join(S1A_DIR, "m4");
const FIXTURE = join(M1_DIR, "fixture", "canonical", "project_memory.json");
const PRE_MIGRATION = join(M1_DIR, "fixture", "pre_migration.json");
const EMPTY_CWD = join(M1_DIR, "empty-cwd");
const EVIDENCE = join(M5_DIR, "evidence");
const READ_TOOLS = [
  "decision.get",
  "decision.search",
  "decision.applicable_to",
  "decision.trace",
];
const CASES = [
  { id: "matching-context", args: { context: ["cache"] } },
  { id: "opaque-path", args: { paths: ["src/cache.py"] } },
  { id: "empty-context", args: { context: [], paths: [] } },
  { id: "unmatched-context", args: { context: ["unrelated"] } },
];
const SLIM_REF_FIELDS = [
  "context_scope",
  "decision_id",
  "lifecycle_status",
  "statement",
  "version",
  "version_id",
].sort();

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
  const pkg = JSON.parse(readFileSync(join(M5_DIR, "package.json"), "utf8"));
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
  const client = new Client({ name: "cm01-m5", version: "0.1.0" });
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
  return {
    decision_id: logical.decision_id,
    version: version.revision,
    version_id: version.version_id,
    statement: version.statement,
    lifecycle_status: logical.lifecycle_status,
    context_scope: version.context_scope,
  };
}

const APPLICABLE_CODE = `async () => ({
  "matching-context": await codemode.decision_applicable_to({ context: ["cache"] }),
  "opaque-path": await codemode.decision_applicable_to({ paths: ["src/cache.py"] }),
  "empty-context": await codemode.decision_applicable_to({ context: [], paths: [] }),
  "unmatched-context": await codemode.decision_applicable_to({ context: ["unrelated"] })
})`;

function canonicalRefs(document) {
  return document?.canonical_scope_matches ?? [];
}

function findRef(refs, decisionId) {
  return refs.find((ref) => ref.decision_id === decisionId) ?? null;
}

function exactSlimRef(ref) {
  if (!ref) return false;
  return JSON.stringify(Object.keys(ref).sort()) === JSON.stringify(SLIM_REF_FIELDS);
}

function refMatchesFixture(ref, expected) {
  if (!ref) return false;
  return SLIM_REF_FIELDS.every(
    (key) =>
      JSON.stringify(stable(ref[key])) === JSON.stringify(stable(expected[key])),
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
      name: "decision.applicable_to",
      arguments: testCase.args,
    });
    direct[testCase.id] = { raw, normalized: normalizeMcpSuccess("decision.applicable_to", raw) };
  }

  const codeModeOutput = await adapter.tool.execute({ code: APPLICABLE_CODE });
  const codeMode = codeModeOutput.result;
  const expected = fixtureIdentity();

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

  const matching = direct["matching-context"].normalized;
  const opaque = direct["opaque-path"].normalized;
  const empty = direct["empty-context"].normalized;
  const unmatched = direct["unmatched-context"].normalized;
  const matchingRef = findRef(canonicalRefs(matching), "ADR-9901");
  const opaqueRef = findRef(canonicalRefs(opaque), "ADR-9901");

  const allRefs = [
    ...canonicalRefs(matching),
    ...canonicalRefs(opaque),
    ...canonicalRefs(empty),
    ...canonicalRefs(unmatched),
  ];

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
    fixture_identity: expected,
    cases,
    direct_raw: Object.fromEntries(
      CASES.map((testCase) => [testCase.id, direct[testCase.id].raw]),
    ),
    code_mode_raw: codeModeOutput,
    structure: {
      top_level_keys: Object.keys(matching ?? {}).sort(),
      proposal_hint_matches_is_array: Array.isArray(matching?.proposal_hint_matches),
      canonical_scope_matches_is_array: Array.isArray(matching?.canonical_scope_matches),
      all_canonical_refs_exact_slim_fields: allRefs.every(exactSlimRef),
      canonical_ref_key_sets: [...new Set(allRefs.map((ref) => JSON.stringify(Object.keys(ref).sort())))],
      contains_typed_rule_fields: allRefs.some((ref) =>
        ["rules", "rule_id", "applicability", "selector", "outcome", "verdict", "enforcement"].some((key) => key in ref),
      ),
    },
    matching: {
      context_match_ids: canonicalRefs(matching).map((ref) => ref.decision_id),
      opaque_path_match_ids: canonicalRefs(opaque).map((ref) => ref.decision_id),
      empty_context_ids: canonicalRefs(empty).map((ref) => ref.decision_id),
      unmatched_context_ids: canonicalRefs(unmatched).map((ref) => ref.decision_id),
      matching_ref: matchingRef,
      opaque_path_ref: opaqueRef,
      matching_ref_matches_fixture: refMatchesFixture(matchingRef, expected),
      opaque_path_ref_matches_fixture: refMatchesFixture(opaqueRef, expected),
      path_semantics: "opaque path string substring match; no ADR-020 selector or glob evaluation",
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
    fixture_identity: run.fixture_identity,
    cases: run.cases,
    structure: run.structure,
    matching: run.matching,
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
const casesEqual =
  Object.values(run1?.cases ?? {}).every((testCase) => testCase.equal) &&
  Object.values(run2?.cases ?? {}).every((testCase) => testCase.equal);

const checks = [
  { id: "M5-UPSTREAM-SIX-1", pass: Boolean(run1?.upstream_inventory?.exact_six) },
  { id: "M5-UPSTREAM-SIX-2", pass: Boolean(run2?.upstream_inventory?.exact_six) },
  { id: "M5-PARITY-1", pass: Object.values(run1?.cases ?? {}).every((c) => c.equal) },
  { id: "M5-PARITY-2", pass: Object.values(run2?.cases ?? {}).every((c) => c.equal) },
  {
    id: "M5-SEPARATE-LISTS",
    pass:
      run1?.structure?.top_level_keys?.join(",") === "canonical_scope_matches,proposal_hint_matches" &&
      run2?.structure?.top_level_keys?.join(",") === "canonical_scope_matches,proposal_hint_matches" &&
      run1?.structure?.proposal_hint_matches_is_array &&
      run1?.structure?.canonical_scope_matches_is_array,
  },
  {
    id: "M5-SLIM-FIELDS",
    pass: Boolean(run1?.structure?.all_canonical_refs_exact_slim_fields) &&
      JSON.stringify(run1?.structure?.canonical_ref_key_sets) === JSON.stringify([JSON.stringify(SLIM_REF_FIELDS)]),
  },
  {
    id: "M5-NO-TYPED-RULE-DATA",
    pass: run1?.structure?.contains_typed_rule_fields === false &&
      run2?.structure?.contains_typed_rule_fields === false,
  },
  {
    id: "M5-MATCHING-CONTEXT",
    pass:
      JSON.stringify(run1?.matching?.context_match_ids) === JSON.stringify(["ADR-9901"]) &&
      run1?.matching?.matching_ref_matches_fixture,
  },
  {
    id: "M5-OPAQUE-PATH",
    pass:
      JSON.stringify(run1?.matching?.opaque_path_match_ids) === JSON.stringify(["ADR-9901"]) &&
      run1?.matching?.opaque_path_ref_matches_fixture,
  },
  {
    id: "M5-EMPTY-AND-UNMATCHED",
    pass:
      JSON.stringify(run1?.matching?.empty_context_ids) === JSON.stringify([]) &&
      JSON.stringify(run1?.matching?.unmatched_context_ids) === JSON.stringify([]),
  },
  {
    id: "M5-CANONICAL-IDENTITY",
    pass:
      run1?.matching?.matching_ref &&
      run1.matching.matching_ref.version_id === run1.fixture_identity.version_id &&
      run1.matching.matching_ref.context_scope.join(",") === run1.fixture_identity.context_scope.join(",") &&
      run1.matching.matching_ref.lifecycle_status === "active",
  },
  {
    id: "M5-NO-PROPOSAL-CALLS",
    pass:
      run1?.adapter?.call_log?.length === 4 &&
      run2?.adapter?.call_log?.length === 4 &&
      run1?.adapter?.call_log?.every((call) => call.tool === "decision.applicable_to") &&
      run2?.adapter?.call_log?.every((call) => call.tool === "decision.applicable_to"),
  },
  { id: "M5-REPEAT", pass: Boolean(sameEvidence) },
  {
    id: "M5-NO-MUTATION",
    pass:
      before.fixture_sha256 === after.fixture_sha256 &&
      before.pre_migration_sha256 === after.pre_migration_sha256 &&
      before.repo_memory_sha256 === after.repo_memory_sha256 &&
      before.repo_proposals_exists === after.repo_proposals_exists &&
      before.repo_proposals_sha256 === after.repo_proposals_sha256 &&
      JSON.stringify(before.empty_cwd_files) === JSON.stringify(after.empty_cwd_files) &&
      JSON.stringify(before.preserved) === JSON.stringify(after.preserved),
  },
  { id: "M5-M4", pass: before.m4.pass && after.m4.pass },
];

const result = {
  schema: "mneme.cm01.s1a1.m5/v1",
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
    "M5 only: decision.applicable_to retrieval/context parity. No M6-M8 acceptance tests.",
    "A retrieval match is not permission to mutate a file and is not typed-rule applicability.",
    "No proposal method was invoked.",
    "No Cloudflare Workers, tunnel, live model, credentials, or repository project memory.",
  ],
};

writeFileSync(join(EVIDENCE, "m5.json"), `${JSON.stringify(result, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run1.json"), `${JSON.stringify(run1, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run2.json"), `${JSON.stringify(run2, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run1-stderr.log"), `${run1?.stderr ?? ""}\n`);
writeFileSync(join(EVIDENCE, "run2-stderr.log"), `${run2?.stderr ?? ""}\n`);

process.stdout.write(`${JSON.stringify(result.verdict)}\n`);
process.stdout.write(`${JSON.stringify({ checks, versions: result.versions }, null, 2)}\n`);
process.exit(result.verdict.pass ? 0 : 1);
