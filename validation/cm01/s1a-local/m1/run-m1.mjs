import { execFileSync, execSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import {
  StdioClientTransport,
  getDefaultEnvironment,
} from "@modelcontextprotocol/sdk/client/stdio.js";
import { checkM4Protection, DEFAULT_BASE_SHA, S0_SHA } from "../m4-guard.mjs";

const M1_DIR = dirname(fileURLToPath(import.meta.url));
const S1A_DIR = dirname(M1_DIR);
const ROOT = resolve(M1_DIR, "../../../..");
const FIXTURE = join(M1_DIR, "fixture", "canonical", "project_memory.json");
const PRE_MIGRATION = join(M1_DIR, "fixture", "pre_migration.json");
const EMPTY_CWD = join(M1_DIR, "empty-cwd");
const EVIDENCE = join(M1_DIR, "evidence");
const EXPECTED_TOOLS = [
  "decision.propose",
  "decision.propose_batch",
  "decision.get",
  "decision.search",
  "decision.applicable_to",
  "decision.trace",
];

mkdirSync(EVIDENCE, { recursive: true });
mkdirSync(EMPTY_CWD, { recursive: true });

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

function normalizedInventory(listing) {
  return {
    nextCursor: listing.nextCursor ?? null,
    tools: [...listing.tools]
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((tool) => stable(tool)),
  };
}

function listEmptyCwd() {
  return execFileSync("git", ["ls-files", "--others", "--exclude-standard"], {
    cwd: EMPTY_CWD,
    encoding: "utf8",
  })
    .split(/\r?\n/)
    .filter(Boolean);
}

function pythonVersion() {
  const code = [
    "import json, sys",
    "import mneme",
    "from importlib.metadata import version",
    "print(json.dumps({",
    "  'python': sys.version.split()[0],",
    "  'mneme': getattr(mneme, '__version__', 'unknown'),",
    "  'mcp': version('mcp'),",
    "}))",
  ].join("\n");
  const env = { ...process.env, PYTHONPATH: ROOT };
  return JSON.parse(
    execFileSync(process.env.CM01_PYTHON || "python", ["-c", code], {
      cwd: EMPTY_CWD,
      env,
      encoding: "utf8",
    }),
  );
}

function nodeVersions() {
  const pkg = JSON.parse(readFileSync(join(M1_DIR, "package.json"), "utf8"));
  return {
    node: process.version,
    npm: execSync("npm --version", { encoding: "utf8" }).trim(),
    sdk: pkg.dependencies["@modelcontextprotocol/sdk"],
    zod: pkg.dependencies.zod,
  };
}

async function runServer(runLabel) {
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
  const client = new Client({ name: "cm01-m1", version: "0.1.0" });
  transport.stderr?.on("data", (chunk) => stderr.push(chunk.toString("utf8")));

  let result;
  try {
    await client.connect(transport);
    const listing = await client.listTools();
    result = {
      run: runLabel,
      pid: transport.pid,
      handshake: {
        server_info: client.getServerVersion() ?? null,
        server_capabilities: client.getServerCapabilities() ?? null,
        instructions: client.getInstructions() ?? null,
      },
      listing: {
        nextCursor: listing.nextCursor ?? null,
        tools: listing.tools,
      },
      normalized_inventory: normalizedInventory(listing),
      stderr: stderr.join(""),
      tool_calls_executed: 0,
    };
  } catch (error) {
    result = {
      run: runLabel,
      pid: transport.pid,
      handshake: null,
      listing: null,
      normalized_inventory: null,
      stderr: stderr.join(""),
      error: error?.message || String(error),
      tool_calls_executed: 0,
    };
  } finally {
    try {
      await client.close();
    } catch (error) {
      result.close_error = error?.message || String(error);
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 100));
  }
  return result;
}

function inventoryPass(run) {
  if (!run || run.error || !run.listing) return false;
  const names = run.listing.tools.map((tool) => tool.name).sort();
  const expected = [...EXPECTED_TOOLS].sort();
  if (JSON.stringify(names) !== JSON.stringify(expected)) return false;
  const byName = Object.fromEntries(run.listing.tools.map((tool) => [tool.name, tool]));
  for (const name of [
    "decision.get",
    "decision.search",
    "decision.applicable_to",
    "decision.trace",
  ]) {
    if (byName[name]?.annotations?.readOnlyHint !== true) return false;
    if (byName[name]?.annotations?.destructiveHint !== false) return false;
    if (byName[name]?.annotations?.idempotentHint !== true) return false;
  }
  for (const name of ["decision.propose", "decision.propose_batch"]) {
    if (byName[name]?.annotations?.readOnlyHint !== false) return false;
    if (byName[name]?.annotations?.idempotentHint !== true) return false;
  }
  return true;
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

const versions = { ...nodeVersions(), ...pythonVersion() };
let run1;
let run2;
try {
  run1 = await runServer("run1");
  run2 = await runServer("run2");
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

const sameInventory =
  run1?.normalized_inventory &&
  run2?.normalized_inventory &&
  JSON.stringify(run1.normalized_inventory) === JSON.stringify(run2.normalized_inventory);

const checks = [
  { id: "M1-HANDSHAKE-1", pass: Boolean(run1 && !run1.error && run1.handshake) },
  { id: "M1-HANDSHAKE-2", pass: Boolean(run2 && !run2.error && run2.handshake) },
  { id: "M1-SIX-TOOLS-1", pass: inventoryPass(run1) },
  { id: "M1-SIX-TOOLS-2", pass: inventoryPass(run2) },
  { id: "M1-REPEAT-INVENTORY", pass: Boolean(sameInventory) },
  {
    id: "M1-NO-TOOL-CALLS",
    pass: (run1?.tool_calls_executed ?? 0) === 0 && (run2?.tool_calls_executed ?? 0) === 0,
  },
  {
    id: "M1-NO-MUTATION",
    pass:
      before.fixture_sha256 === after.fixture_sha256 &&
      before.pre_migration_sha256 === after.pre_migration_sha256 &&
      before.repo_memory_sha256 === after.repo_memory_sha256 &&
      before.repo_proposals_exists === after.repo_proposals_exists &&
      before.repo_proposals_sha256 === after.repo_proposals_sha256 &&
      JSON.stringify(before.empty_cwd_files) === JSON.stringify(after.empty_cwd_files),
  },
  { id: "M1-M4", pass: before.m4.pass && after.m4.pass },
];

const result = {
  schema: "mneme.cm01.s1a1.m1/v1",
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
  versions,
  fixture: {
    path: FIXTURE,
    pre_migration: PRE_MIGRATION,
    sha256: before.fixture_sha256,
    pre_migration_sha256: before.pre_migration_sha256,
    synthetic: true,
    repository_memory_used: false,
  },
  expected_tools: EXPECTED_TOOLS,
  runs: [run1, run2],
  checks,
  verdict: {
    pass: checks.every((check) => check.pass),
    failed: checks.filter((check) => !check.pass).map((check) => check.id),
  },
  no_mutation: { before, after },
  limitations: [
    "M1 only: initialization and tools/list. No decision tool was called.",
    "No Code Mode connection; no M2-M8.",
    "No production memory, proposal execution, or canonical mutation.",
  ],
};

writeFileSync(join(EVIDENCE, "m1.json"), `${JSON.stringify(result, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run1-tools.json"), `${JSON.stringify(run1?.listing ?? null, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run2-tools.json"), `${JSON.stringify(run2?.listing ?? null, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "run1-stderr.log"), `${run1?.stderr ?? ""}\n`);
writeFileSync(join(EVIDENCE, "run2-stderr.log"), `${run2?.stderr ?? ""}\n`);

process.stdout.write(`${JSON.stringify(result.verdict)}\n`);
process.stdout.write(`${JSON.stringify({ checks, versions }, null, 2)}\n`);
process.exit(result.verdict.pass ? 0 : 1);
