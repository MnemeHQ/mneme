import { execFileSync, execSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { checkM4Protection } from "../s1a-local/m4-guard.mjs";

const B0_DIR = dirname(fileURLToPath(import.meta.url));
const CM01_DIR = dirname(B0_DIR);
const ROOT = resolve(B0_DIR, "../../..");
const F1_DIR = join(CM01_DIR, "p0-f1");
const P0_DIR = join(CM01_DIR, "p0-cancellation");
const S1A_DIR = join(CM01_DIR, "s1a-local");
const EVIDENCE = join(B0_DIR, "evidence");
const FIXTURE = join(B0_DIR, "fixture", "project_memory.json");
const TASKS = join(B0_DIR, "tasks.json");
const BASELINE = "f8591102b2693379dabec9b5704862e194eca4ce";
const S1A_DIGEST = "cc7f884866e6e94255b100de57b82eec4a51660aadaf51c6464198131030af57";
const F1_EXECUTOR_SHA = "0d81093b20fa0b77a3fc9f2e6b4a90bf184668d0377242c3e4f37e64afd9d2b1";
const F1_ADAPTER_SHA = "3d8123975bc9f67147fec90ff3e6911a08e40a7f2dc4bd7b43da14b0530cb08c";
const F1_RELAY_SHA = "536f32e7869fc407782b1c1db7d55afc3bd383bc0ede405f40d6f08b45e0f5e5";
const F1_RUNNER_SHA = "55a40f182df80bf7f3828e165601758298912eaa7f6285ef0772cc967103e830";
const FROZEN_EXECUTOR_SHA = "4b960124e9218ed124ed34e3b3595b648477b9dab6540c4ce1609d2efaf31313";
const NOT_MEASURED = "NOT_MEASURED";
const SOURCE_FILES = [
  "package.json",
  "package-lock.json",
  ".gitignore",
  ".gitattributes",
  "make-corpus.py",
  "make-tasks.py",
  "fixture/project_memory.json",
  "tasks.json",
  "arms.mjs",
  "run-b0m.mjs",
];

const checks = [];
function check(id, pass, detail = null) {
  checks.push({ id, pass: Boolean(pass), detail });
}

function sha256File(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function sha256Text(text) {
  return createHash("sha256").update(text).digest("hex");
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
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

function equal(left, right) {
  return JSON.stringify(stable(left)) === JSON.stringify(stable(right));
}

function gitLines(args) {
  const text = execFileSync("git", args, { cwd: ROOT, encoding: "utf8" }).trim();
  return text ? text.split(/\r?\n/) : [];
}

function walkFiles(dir, out = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) walkFiles(path, out);
    else out.push(path);
  }
  return out;
}

function evidenceManifest() {
  const files = walkFiles(EVIDENCE)
    .map((path) => relative(EVIDENCE, path).replace(/\\/g, "/"))
    .filter((path) => path !== "verification.json")
    .sort();
  const hashes = Object.fromEntries(
    files.map((path) => [path, sha256File(join(EVIDENCE, path))]),
  );
  return { files: hashes, digest: sha256Text(JSON.stringify(hashes)) };
}

function s1aDigest() {
  const files = gitLines(["ls-files", "validation/cm01/s1a-local"]).sort();
  const hashes = Object.fromEntries(
    files.map((file) => [file, sha256File(join(ROOT, file))]),
  );
  return sha256Text(JSON.stringify(hashes));
}

function indexOf(document) {
  const index = document.decision_index;
  const decisions = Object.fromEntries(
    index.decisions.map((row) => [row.decision_id, row]),
  );
  const versions = Object.fromEntries(
    index.versions.map((row) => [row.version_id, row]),
  );
  const rules = {};
  for (const rule of index.rules) {
    rules[rule.decision_id] = rules[rule.decision_id] ?? [];
    rules[rule.decision_id].push(rule);
  }
  return { decisions, versions, rules };
}

function getProjection(document, decisionId) {
  const { decisions, versions, rules } = indexOf(document);
  const record = decisions[decisionId];
  const version = versions[record.active_version_id];
  return {
    decision_id: decisionId,
    version: version.revision,
    version_id: version.version_id,
    content_digest: version.content_digest,
    lifecycle_status: record.lifecycle_status,
    context_scope: version.context_scope,
    derived_rule_ids: (rules[decisionId] ?? []).map((rule) => rule.rule_id),
  };
}

function traceProjection(document, decisionId) {
  const { decisions, versions, rules } = indexOf(document);
  const record = decisions[decisionId];
  const version = versions[record.active_version_id];
  return {
    canonical_decision_id: decisionId,
    version: version.revision,
    version_id: version.version_id,
    content_digest: version.content_digest,
    derived_rule_ids: (rules[decisionId] ?? []).map((rule) => rule.rule_id),
    declared_test_evidence: record.test_evidence ?? [],
  };
}

function searchIds(document, query, lifecycle = null) {
  const { decisions, versions } = indexOf(document);
  const needle = query.toLowerCase();
  return Object.entries(decisions)
    .filter(([, record]) => lifecycle === null || record.lifecycle_status === lifecycle)
    .filter(([id, record]) => {
      const version = versions[record.active_version_id];
      return [id, version.statement, version.rationale, ...version.context_scope].some(
        (value) => String(value).toLowerCase().includes(needle),
      );
    })
    .map(([id]) => id)
    .sort();
}

function applicableIds(document, context) {
  const { decisions, versions } = indexOf(document);
  return Object.entries(decisions)
    .filter(([, record]) => {
      const version = versions[record.active_version_id];
      return version.context_scope.some((scope) =>
        scope.toLowerCase().includes(context.toLowerCase()),
      );
    })
    .map(([id]) => id)
    .sort();
}

function deriveExpected(document, task) {
  const { decisions, rules } = indexOf(document);
  switch (task.id) {
    case "T1":
      return getProjection(document, task.params.record_id);
    case "T2": {
      const ids = searchIds(document, task.params.query, task.params.canonical_lifecycle_status);
      return { canonical_ids: ids, count: ids.length };
    }
    case "T3": {
      const ids = applicableIds(document, task.params.context[0]);
      return { canonical_ids: ids, count: ids.length };
    }
    case "T4":
      return traceProjection(document, task.params.record_id);
    case "T5": {
      const id = searchIds(document, task.params.query, task.params.canonical_lifecycle_status)[0];
      return getProjection(document, id);
    }
    case "T6": {
      const id = searchIds(document, task.params.query, task.params.canonical_lifecycle_status)[0];
      return traceProjection(document, id);
    }
    case "T7": {
      const id = applicableIds(document, task.params.context[0]).filter(
        (candidate) => decisions[candidate].lifecycle_status === "active",
      )[0];
      return { selected_id: id, get: getProjection(document, id), trace: traceProjection(document, id) };
    }
    case "T8": {
      const ids = searchIds(document, task.params.query, task.params.canonical_lifecycle_status)
        .filter((id) => (rules[id] ?? []).length > 0)
        .slice(0, 2);
      return {
        items: ids.map((id) => ({
          decision_id: id,
          version: getProjection(document, id).version,
          content_digest: getProjection(document, id).content_digest,
          derived_rule_ids: getProjection(document, id).derived_rule_ids,
        })),
      };
    }
    default:
      throw new Error(`unknown task ${task.id}`);
  }
}

function normalizeResult(result) {
  return {
    task_id: result.task_id,
    arm: result.arm,
    ok: result.ok,
    actual: result.actual,
    expected: result.expected,
    mcp_call_names: result.mcp_calls.map((call) => call.name),
    mcp_call_count: result.mcp_call_count,
    result_bytes: result.result_bytes,
    mcp_result_bytes: result.mcp_result_bytes,
    host_calls: result.host_calls,
    no_proposal: result.no_proposal,
    functional_completion: result.functional_completion,
    decision_identity_ok: result.decision_identity_ok,
    cleanup_errors: result.cleanup?.errors ?? null,
    process_cleanup_ok: result.process_cleanup_ok,
  };
}

function normalizeRun(run) {
  return {
    tasks: run.tasks.map((task) => ({
      id: task.id,
      direct: normalizeResult(task.results.direct),
      code: normalizeResult(task.results.code),
    })),
    cancellation: {
      ok: run.cancellation.ok,
      withheld: run.cancellation.withheld,
      cancellation_count: run.cancellation.cancellation_count,
      outcome: run.cancellation.state?.outcome ?? null,
      error_code: run.cancellation.state?.errorCode ?? null,
      pending: run.cancellation.state?.pending ?? null,
      settled: run.cancellation.settled?.found ?? null,
      stats: run.cancellation.stats
        ? {
            cancelledCalls: run.cancellation.stats.cancelledCalls,
            cancelledSettled: run.cancellation.stats.cancelledSettled,
            cancelledUnsettled: run.cancellation.stats.cancelledUnsettled,
          }
        : null,
    },
    checks: run.checks,
  };
}

const manifestBefore = evidenceManifest();
const verdict = readJson(join(EVIDENCE, "verdict.json"));
const runFiles = [readJson(join(EVIDENCE, "run1.json")), readJson(join(EVIDENCE, "run2.json"))];
const tasksDocument = readJson(TASKS);
const fixtureDocument = readJson(FIXTURE);
const fixtureHash = sha256File(FIXTURE);
const tasksHash = sha256File(TASKS);

check(
  "B0M-ORIGINAL-VERDICT",
  verdict.verdict === "PASS" &&
    runFiles.every((run) => run.verdict === "PASS") &&
    runFiles.every((run) => run.checks.length === 39) &&
    runFiles.every((run) => run.checks.every((entry) => entry.pass)),
  {
    verdict: verdict.verdict,
    runs: runFiles.map((run) => ({
      run: run.run,
      verdict: run.verdict,
      checks: run.checks.length,
      failed: run.checks.filter((entry) => !entry.pass).map((entry) => entry.id),
    })),
  },
);

const taskIds = tasksDocument.tasks.map((task) => task.id);
const expectedCheckIds = [
  ...taskIds.flatMap((id) => [
    `B0M-${id}-DIRECT`,
    `B0M-${id}-CODE`,
    `B0M-${id}-EQUIVALENT`,
    `B0M-${id}-NO-PROPOSAL`,
  ]),
  "B0M-MCP-INSTRUMENTATION",
  "B0M-MCP-CALL-METRICS",
  "B0M-RESULT-SIZES",
  "B0M-MODEL-NOT-MEASURED",
  "B0M-CANCELLATION",
  "B0M-CLEANUP",
  "B0M-UNHANDLED",
];
check(
  "B0M-CHECK-MATRIX",
  runFiles.every(
    (run) =>
      run.checks.length === expectedCheckIds.length &&
      expectedCheckIds.every((id) =>
        run.checks.some((entry) => entry.id === id && entry.pass === true),
      ) &&
      run.checks.every((entry) => entry.pass === true),
  ),
  { expectedCheckIds, actual: runFiles.map((run) => run.checks.map((entry) => entry.id)) },
);

const expectedDerivation = tasksDocument.tasks.map((task) => ({
  id: task.id,
  expected: deriveExpected(fixtureDocument, task),
  frozen: task.expected,
}));
check(
  "B0M-FIXTURE-TASKS",
  fixtureHash === tasksDocument.fixture.sha256 &&
    verdict.fixture.sha256 === fixtureHash &&
    verdict.tasks.sha256 === tasksHash &&
    expectedDerivation.every((entry) => equal(entry.expected, entry.frozen)),
  { fixtureHash, tasksHash, expectedDerivation },
);

const perTask = runFiles.map((run) => ({
  run: run.run,
  tasks: run.tasks.map((task) => {
    const expected = tasksDocument.tasks.find((candidate) => candidate.id === task.id).expected;
    return {
      id: task.id,
      expected_match: equal(task.expected, expected),
      direct_ok: task.results.direct.ok,
      code_ok: task.results.code.ok,
      direct_expected: equal(task.results.direct.actual, expected),
      code_expected: equal(task.results.code.actual, expected),
      equivalent: equal(task.results.direct.actual, task.results.code.actual),
      direct_calls: task.results.direct.mcp_calls.map((call) => call.name),
      code_calls: task.results.code.mcp_calls.map((call) => call.name),
      no_proposal:
        task.results.direct.no_proposal === true && task.results.code.no_proposal === true,
    };
  }),
}));
check(
  "B0M-TASK-RESULTS",
  perTask.every((run) =>
    run.tasks.every(
      (task) =>
        task.expected_match &&
        task.direct_ok &&
        task.code_ok &&
        task.direct_expected &&
        task.code_expected &&
        task.equivalent &&
        task.no_proposal &&
        task.direct_calls.length > 0 &&
        task.code_calls.length > 0,
    ),
  ),
  perTask,
);

check(
  "B0M-INSTRUMENTATION",
  runFiles.every((run) =>
    run.tasks.every((task) =>
      [task.results.direct, task.results.code].every(
        (result) =>
          result.mcp_call_count === result.mcp_calls.length &&
          result.result_bytes > 0 &&
          result.mcp_result_bytes > 0 &&
          result.mcp_calls.every(
            (call) =>
              call.request_id !== null &&
              call.result_bytes > 0 &&
              call.duration_ms !== null &&
              call.duration_ms >= 0,
          ),
      ),
    ),
  ),
  runFiles.map((run) => ({
    run: run.run,
    calls: run.tasks.map((task) => ({
      id: task.id,
      direct: task.results.direct.mcp_call_count,
      code: task.results.code.mcp_call_count,
    })),
  })),
);

check(
  "B0M-MODEL-NOT-MEASURED",
  runFiles.every((run) =>
    run.tasks.flatMap((task) => [task.results.direct, task.results.code]).every(
      (result) =>
        result.model_turns === NOT_MEASURED &&
        result.input_tokens === NOT_MEASURED &&
        result.output_tokens === NOT_MEASURED &&
        result.intermediate_context_model_tokens === NOT_MEASURED,
    ),
  ) &&
    verdict.model_fields.status === NOT_MEASURED,
  { model_fields: verdict.model_fields },
);

check(
  "B0M-CANCELLATION",
  runFiles.every(
    (run) =>
      run.cancellation.ok === true &&
      run.cancellation.withheld === true &&
      run.cancellation.cancellation_count === 1 &&
      run.cancellation.state?.outcome === "rejected" &&
      run.cancellation.state?.errorCode === -32001 &&
      run.cancellation.state?.pending === false &&
      run.cancellation.stats?.cancelledCalls === 1 &&
      run.cancellation.stats?.cancelledSettled === 1 &&
      run.cancellation.stats?.cancelledUnsettled === 0,
  ),
  runFiles.map((run) => run.cancellation),
);

const cleanup = runFiles.map((run) => ({
  run: run.run,
  failures: [
    ...run.tasks.flatMap((task) =>
      [task.results.direct, task.results.code]
        .filter(
          (result) =>
            !result.cleanup ||
            result.cleanup.errors?.length > 0 ||
            result.cleanup.server_alive_after === true ||
            result.process_cleanup_ok !== true,
        )
        .map((result) => `${task.id}:${result.arm}`),
    ),
    ...(run.cancellation.cleanup?.errors?.length > 0 ? ["cancellation:errors"] : []),
    ...(run.cancellation.cleanup?.relay_alive_after === true ? ["cancellation:relay_alive"] : []),
    ...(run.cancellation.cleanup?.upstream_alive_after === true ? ["cancellation:upstream_alive"] : []),
  ],
}));
check("B0M-CLEANUP", cleanup.every((entry) => entry.failures.length === 0), cleanup);

check(
  "B0M-UNHANDLED",
  verdict.unhandled?.length === 0 && runFiles.every((run) => (run.unhandled ?? []).length === 0),
  { verdict: verdict.unhandled, runs: runFiles.map((run) => run.unhandled) },
);

const repeatable =
  verdict.repeatable === true &&
  equal(normalizeRun(runFiles[0]), normalizeRun(runFiles[1]));
check("B0M-REPEATABLE", repeatable, {
  recorded: verdict.repeatable,
  derived: equal(normalizeRun(runFiles[0]), normalizeRun(runFiles[1])),
});

const sourceChecks = {
  arms: sha256File(join(B0_DIR, "arms.mjs")) === verdict.source_hashes.arms,
  runner: sha256File(join(B0_DIR, "run-b0m.mjs")) === verdict.source_hashes.runner,
  make_corpus: sha256File(join(B0_DIR, "make-corpus.py")) === verdict.source_hashes.make_corpus,
  make_tasks: sha256File(join(B0_DIR, "make-tasks.py")) === verdict.source_hashes.make_tasks,
  fixture: fixtureHash === verdict.source_hashes.fixture,
  tasks: tasksHash === verdict.source_hashes.tasks,
  package_lock: sha256File(join(B0_DIR, "package-lock.json")) === verdict.source_hashes.package_lock,
  f1_executor: sha256File(join(F1_DIR, "quickjs-executor.mjs")) === F1_EXECUTOR_SHA,
  f1_adapter: sha256File(join(F1_DIR, "adapter.mjs")) === F1_ADAPTER_SHA,
  f1_relay: sha256File(join(F1_DIR, "relay.mjs")) === F1_RELAY_SHA,
  f1_runner: sha256File(join(F1_DIR, "run-f1.mjs")) === F1_RUNNER_SHA,
  frozen_executor: sha256File(join(S1A_DIR, "e0", "quickjs-executor.mjs")) === FROZEN_EXECUTOR_SHA,
};
check(
  "B0M-SOURCE-HASHES",
  Object.values(sourceChecks).every(Boolean) &&
    verdict.source_hashes.f1_executor === F1_EXECUTOR_SHA,
  sourceChecks,
);

const p0Verdict = readJson(join(P0_DIR, "evidence", "verdict.json"));
const p0Verification = readJson(join(P0_DIR, "evidence", "verification.json"));
const f1Verdict = readJson(join(F1_DIR, "evidence", "verdict.json"));
const f1Verification = readJson(join(F1_DIR, "evidence", "verification.json"));
const frozenStatus = gitLines([
  "status",
  "--porcelain",
  "--",
  "validation/cm01/s1a-local",
  "validation/cm01/p0-cancellation",
]);
const frozenDiff = gitLines([
  "diff",
  "--name-only",
  "HEAD",
  "--",
  "validation/cm01/s1a-local",
  "validation/cm01/p0-cancellation",
]);
const m4Guard = checkM4Protection({ cwd: ROOT, baseSha: BASELINE });
const preservation = {
  s1a: s1aDigest(),
  frozenStatus,
  frozenDiff,
  m4Guard,
  p0Verdict: p0Verdict.verdict,
  p0Verification: p0Verification.verification_status,
  f1Verdict: f1Verdict.verdict,
  f1Verification: f1Verification.verification_status,
};
check(
  "B0M-PRESERVATION",
  preservation.s1a === S1A_DIGEST &&
    frozenStatus.length === 0 &&
    frozenDiff.length === 0 &&
    m4Guard.pass === true &&
    p0Verdict.verdict === "FAIL" &&
    p0Verification.verification_status === "VERIFIED" &&
    f1Verdict.verdict === "PASS" &&
    f1Verification.verification_status === "VERIFIED",
  preservation,
);

const status = gitLines(["status", "--porcelain", "--untracked-files=all"]);
const outside = status.filter(
  (line) =>
    !line.includes("validation/cm01/b0-benchmark/") &&
    !line.includes(".mneme/task_context.json"),
);
check("B0M-ONLY-B0", outside.length === 0, { status, outside });

let reproduction = { performed: false, reason: "not requested" };
if (process.argv.includes("--reproduce")) {
  const tempRoot = join(
    process.env.TEMP || process.env.TMP || tmpdir(),
    "opencode",
    `b0m-verify-${Date.now()}`,
  );
  const tempB0 = join(tempRoot, "validation", "cm01", "b0-benchmark");
  const tempF1 = join(tempRoot, "validation", "cm01", "p0-f1");
  reproduction = {
    performed: true,
    temp_worktree: tempRoot,
    baseline: BASELINE,
    steps: [],
    checks: [],
  };
  try {
    mkdirSync(dirname(tempRoot), { recursive: true });
    execFileSync("git", ["worktree", "add", "--detach", tempRoot, BASELINE], {
      cwd: ROOT,
      stdio: "pipe",
      timeout: 120000,
    });
    reproduction.steps.push({ step: "worktree_add", ok: true });
    mkdirSync(tempB0, { recursive: true });
    for (const file of SOURCE_FILES) {
      cpSync(join(B0_DIR, file), join(tempB0, file));
    }
    reproduction.steps.push({ step: "copy_sources", ok: true, files: SOURCE_FILES });
    execSync("npm ci --ignore-scripts --no-audit --no-fund", {
      cwd: tempF1,
      stdio: "pipe",
      timeout: 300000,
    });
    reproduction.steps.push({ step: "npm_ci_f1", ok: true });
    execSync("npm ci --ignore-scripts --no-audit --no-fund", {
      cwd: tempB0,
      stdio: "pipe",
      timeout: 300000,
    });
    reproduction.steps.push({ step: "npm_ci_b0", ok: true });
    const result = spawnSync(process.execPath, ["run-b0m.mjs"], {
      cwd: tempB0,
      encoding: "utf8",
      timeout: 600000,
      env: { ...process.env },
    });
    reproduction.exit_code = result.status;
    reproduction.stdout_tail = (result.stdout ?? "").split(/\r?\n/).filter(Boolean).slice(-4);
    reproduction.stderr_tail = (result.stderr ?? "").split(/\r?\n/).filter(Boolean).slice(-6);
    reproduction.steps.push({ step: "run", ok: result.status === 0, status: result.status });
    const tempVerdict = readJson(join(tempB0, "evidence", "verdict.json"));
    const tempRun1 = readJson(join(tempB0, "evidence", "run1.json"));
    const tempRun2 = readJson(join(tempB0, "evidence", "run2.json"));
    const signatureMatch =
      equal(normalizeRun(runFiles[0]), normalizeRun(tempRun1)) &&
      equal(normalizeRun(runFiles[1]), normalizeRun(tempRun2));
    const sourceHashMatch = [
      "arms",
      "runner",
      "make_corpus",
      "make_tasks",
      "fixture",
      "tasks",
      "package_lock",
      "f1_executor",
      "f1_adapter",
      "f1_relay",
      "f1_runner",
      "frozen_executor",
    ].every((key) => tempVerdict.source_hashes[key] === verdict.source_hashes[key]);
    reproduction.verdict = tempVerdict.verdict;
    reproduction.checks.push({
      id: "REPRO-VERDICT",
      pass:
        tempVerdict.verdict === "PASS" &&
        tempRun1.verdict === "PASS" &&
        tempRun2.verdict === "PASS" &&
        tempVerdict.repeatable === true &&
        tempVerdict.preservation?.pass === true &&
        (tempVerdict.unhandled ?? []).length === 0,
      detail: {
        verdict: tempVerdict.verdict,
        runs: [tempRun1.verdict, tempRun2.verdict],
        repeatable: tempVerdict.repeatable,
        preservation: tempVerdict.preservation?.pass,
        unhandled: tempVerdict.unhandled,
      },
    });
    reproduction.checks.push({
      id: "REPRO-SIGNATURE",
      pass: signatureMatch,
      detail: {
        canonical: normalizeRun(runFiles[0]),
        reproduced: normalizeRun(tempRun1),
      },
    });
    reproduction.checks.push({
      id: "REPRO-SOURCE-HASHES",
      pass: sourceHashMatch,
      detail: { canonical: verdict.source_hashes, reproduced: tempVerdict.source_hashes },
    });
    reproduction.checks.push({
      id: "REPRO-CHECK-MATRIX",
      pass:
        equal(
          tempRun1.checks.map((entry) => ({ id: entry.id, pass: entry.pass })),
          tempRun2.checks.map((entry) => ({ id: entry.id, pass: entry.pass })),
        ) &&
        equal(
          tempRun1.checks.map((entry) => ({ id: entry.id, pass: entry.pass })),
          runFiles[0].checks.map((entry) => ({ id: entry.id, pass: entry.pass })),
        ),
      detail: { temp: tempRun1.checks },
    });
  } catch (error) {
    reproduction.error = error?.stack || error?.message || String(error);
    reproduction.checks.push({ id: "REPRO-EXECUTED", pass: false, detail: reproduction.error });
  } finally {
    try {
      execFileSync("git", ["worktree", "remove", "--force", tempRoot], {
        cwd: ROOT,
        stdio: "pipe",
        timeout: 120000,
      });
      reproduction.cleaned_worktree = true;
    } catch {
      try {
        rmSync(tempRoot, { recursive: true, force: true });
        reproduction.cleaned_worktree = "removed_directory_only";
      } catch {
        reproduction.cleaned_worktree = false;
      }
    }
    try {
      execFileSync("git", ["worktree", "prune"], { cwd: ROOT, stdio: "pipe" });
    } catch {
      // best effort
    }
  }
}

const reproductionPass =
  !process.argv.includes("--reproduce") ||
  (reproduction.checks.length > 0 && reproduction.checks.every((entry) => entry.pass));
const manifestAfter = evidenceManifest();
const unchanged = manifestBefore.digest === manifestAfter.digest;
check("B0M-EVIDENCE-UNCHANGED", unchanged, {
  before: manifestBefore.digest,
  after: manifestAfter.digest,
});

const allPass = checks.every((entry) => entry.pass) && reproductionPass;
const statusValue = allPass ? "VERIFIED" : "BLOCKED";
const record = {
  schema: "mneme.cm01.b0m.verification/v1",
  generated_at: new Date().toISOString(),
  verification_status: statusValue,
  original_verdict: verdict.verdict,
  original_verdict_changed: false,
  baseline: BASELINE,
  head: gitLines(["rev-parse", "HEAD"])[0],
  canonical_evidence: {
    manifest: manifestBefore.files,
    digest_before: manifestBefore.digest,
    digest_after: manifestAfter.digest,
    unchanged,
  },
  checks,
  reproduction,
  summary: {
    total_checks: checks.length,
    failed_checks: checks.filter((entry) => !entry.pass).map((entry) => entry.id),
    reproduced: process.argv.includes("--reproduce") ? reproductionPass : null,
    verification_status: statusValue,
  },
  properties: {
    model_free: true,
    model_fields: NOT_MEASURED,
    s1a2: "undefined and blocked",
    b0a_authorized: false,
  },
  errors: [
    ...checks.filter((entry) => !entry.pass).map((entry) => `${entry.id}: ${JSON.stringify(entry.detail)}`),
    ...(reproduction.checks ?? []).filter((entry) => !entry.pass).map((entry) => `${entry.id}: ${JSON.stringify(entry.detail)}`),
  ],
};
writeFileSync(join(EVIDENCE, "verification.json"), `${JSON.stringify(record, null, 2)}\n`);
process.stdout.write(
  `${JSON.stringify({
    verification_status: statusValue,
    original_verdict: record.original_verdict,
    total_checks: record.summary.total_checks,
    failed_checks: record.summary.failed_checks,
    reproduced: record.summary.reproduced,
    errors: record.errors,
  })}\n`,
);
process.exit(statusValue === "VERIFIED" ? 0 : 1);


