import { execFileSync, execSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import * as F1 from "../p0-f1/harness.mjs";
import { QuickJSExecutor } from "../p0-f1/quickjs-executor.mjs";
import { makeAdapter } from "../p0-f1/adapter.mjs";
import { checkM4Protection } from "../s1a-local/m4-guard.mjs";
import { codeForTask, runDirectTask } from "./arms.mjs";

const B0_DIR = dirname(fileURLToPath(import.meta.url));
const CM01_DIR = dirname(B0_DIR);
const ROOT = resolve(B0_DIR, "../../..");
const F1_DIR = join(CM01_DIR, "p0-f1");
const F1_EXECUTOR = join(F1_DIR, "quickjs-executor.mjs");
const F1_ADAPTER = join(F1_DIR, "adapter.mjs");
const F1_RELAY = join(F1_DIR, "relay.mjs");
const F1_RUNNER = join(F1_DIR, "run-f1.mjs");
const P0_DIR = join(CM01_DIR, "p0-cancellation");
const S1A_DIR = join(CM01_DIR, "s1a-local");
const FROZEN_EXECUTOR = join(S1A_DIR, "e0", "quickjs-executor.mjs");
const FIXTURE = join(B0_DIR, "fixture", "project_memory.json");
const TASKS_PATH = join(B0_DIR, "tasks.json");
const EVIDENCE = join(B0_DIR, "evidence");
const RAW = join(EVIDENCE, "raw");
const BASELINE = "f8591102b2693379dabec9b5704862e194eca4ce";
const F1_EXECUTOR_SHA = "0d81093b20fa0b77a3fc9f2e6b4a90bf184668d0377242c3e4f37e64afd9d2b1";
const F1_ADAPTER_SHA = "3d8123975bc9f67147fec90ff3e6911a08e40a7f2dc4bd7b43da14b0530cb08c";
const F1_RELAY_SHA = "536f32e7869fc407782b1c1db7d55afc3bd383bc0ede405f40d6f08b45e0f5e5";
const F1_RUNNER_SHA = "55a40f182df80bf7f3828e165601758298912eaa7f6285ef0772cc967103e830";
const FROZEN_EXECUTOR_SHA = "4b960124e9218ed124ed34e3b3595b648477b9dab6540c4ce1609d2efaf31313";
const S1A_DIGEST = "cc7f884866e6e94255b100de57b82eec4a51660aadaf51c6464198131030af57";
const READ_TOOLS = ["decision.get", "decision.search", "decision.applicable_to", "decision.trace"];
const NOT_MEASURED = "NOT_MEASURED";

mkdirSync(EVIDENCE, { recursive: true });
mkdirSync(RAW, { recursive: true });
mkdirSync(F1.EMPTY_CWD, { recursive: true });

const unhandled = [];
process.on("unhandledRejection", (reason) => {
  unhandled.push(reason?.stack || reason?.message || String(reason));
});

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

function versionInfo() {
  const pkg = readJson(join(B0_DIR, "package.json"));
  const py = JSON.parse(
    execFileSync(
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
      { cwd: B0_DIR, env: { ...process.env, PYTHONPATH: ROOT }, encoding: "utf8" },
    ),
  );
  return {
    node: process.version,
    npm: execSync("npm --version", { encoding: "utf8" }).trim(),
    codemode: pkg.dependencies["@cloudflare/codemode"],
    sdk: pkg.dependencies["@modelcontextprotocol/sdk"],
    ajv: pkg.dependencies.ajv,
    quickjs: pkg.dependencies["quickjs-emscripten"],
    zod: pkg.dependencies.zod,
    ...py,
  };
}

function s1aDigest() {
  const files = gitLines(["ls-files", "validation/cm01/s1a-local"]).sort();
  const hashes = Object.fromEntries(
    files.map((file) => [file, sha256File(join(ROOT, file))]),
  );
  return { files: hashes, digest: sha256Text(JSON.stringify(hashes)) };
}

function normalizeResult(result) {
  return {
    task_id: result.task_id,
    arm: result.arm,
    ok: result.ok,
    actual: result.actual,
    expected: result.expected,
    mcp_call_names: result.mcp_calls.map((call) => call.name),
    no_proposal: result.no_proposal,
    functional_completion: result.functional_completion,
    decision_identity_ok: result.decision_identity_ok,
    cleanup_errors: result.cleanup?.errors ?? null,
    process_cleanup_ok: result.process_cleanup_ok,
  };
}

function checksFor(run) {
  const checks = [];
  for (const task of run.tasks) {
    const direct = task.results.direct;
    const code = task.results.code;
    checks.push({ id: `B0M-${task.id}-DIRECT`, pass: direct.ok === true });
    checks.push({ id: `B0M-${task.id}-CODE`, pass: code.ok === true });
    checks.push({
      id: `B0M-${task.id}-EQUIVALENT`,
      pass: direct.actual !== null && equal(direct.actual, code.actual),
    });
    checks.push({
      id: `B0M-${task.id}-NO-PROPOSAL`,
      pass: direct.no_proposal === true && code.no_proposal === true,
    });
  }
  checks.push({
    id: "B0M-MCP-INSTRUMENTATION",
    pass: run.tasks.every(
      (task) =>
        task.results.direct.mcp_calls.length > 0 &&
        task.results.code.mcp_calls.length > 0 &&
        task.results.direct.mcp_calls.every((call) => call.request_id !== null) &&
        task.results.code.mcp_calls.every((call) => call.request_id !== null),
    ),
  });
  checks.push({
    id: "B0M-MCP-CALL-METRICS",
    pass: run.tasks.flatMap((task) => [task.results.direct, task.results.code]).every(
      (result) =>
        result.mcp_call_count === result.mcp_calls.length &&
        result.mcp_calls.every(
          (call) =>
            call.request_id !== null &&
            READ_TOOLS.includes(call.name) &&
            call.result_bytes > 0 &&
            call.duration_ms !== null &&
            call.duration_ms >= 0,
        ),
    ),
  });
  checks.push({
    id: "B0M-RESULT-SIZES",
    pass: run.tasks.flatMap((task) => [task.results.direct, task.results.code]).every(
      (result) => result.result_bytes > 0 && result.mcp_result_bytes > 0,
    ),
  });
  checks.push({
    id: "B0M-MODEL-NOT-MEASURED",
    pass: run.tasks.flatMap((task) => [task.results.direct, task.results.code]).every(
      (result) =>
        result.model_turns === NOT_MEASURED &&
        result.input_tokens === NOT_MEASURED &&
        result.output_tokens === NOT_MEASURED &&
        result.intermediate_context_model_tokens === NOT_MEASURED,
    ),
  });
  checks.push({
    id: "B0M-CANCELLATION",
    pass: run.cancellation?.ok === true,
  });
  checks.push({
    id: "B0M-CLEANUP",
    pass: run.tasks
      .flatMap((task) => [task.results.direct, task.results.code])
      .every(
        (result) =>
          result.cleanup &&
          result.cleanup.errors?.length === 0 &&
          result.cleanup.server_alive_after === false &&
          result.process_cleanup_ok === true,
      ) &&
      run.cancellation?.cleanup?.errors?.length === 0 &&
      run.cancellation?.cleanup?.relay_alive_after === false &&
      run.cancellation?.cleanup?.upstream_alive_after === false,
  });
  checks.push({
    id: "B0M-UNHANDLED",
    pass: (run.unhandled ?? []).length === 0,
  });
  return checks;
}

async function runArm({ runLabel, task, arm }) {
  const phase = `${task.id}-${arm}`;
  const harness = F1.makeHarnessLog(join(RAW, `${runLabel}-${phase}-harness.jsonl`));
  harness.run = runLabel;
  let ctx = null;
  const result = {
    task_id: task.id,
    family: task.family,
    arm,
    started_at: new Date().toISOString(),
    ok: false,
    actual: null,
    expected: task.expected,
    mcp_calls: [],
    model_turns: NOT_MEASURED,
    input_tokens: NOT_MEASURED,
    output_tokens: NOT_MEASURED,
    intermediate_context_model_tokens: NOT_MEASURED,
    no_proposal: false,
    functional_completion: false,
    decision_identity_ok: false,
    process_cleanup_ok: false,
  };
  try {
    ctx = await F1.connectDirect({
      phase,
      logPath: harness.path,
      harness,
      fixture: FIXTURE,
    });
    const tracker = F1.createTracker(ctx.client);
    ctx.observer.tracker = tracker;
    const hostEvents = [];
    const started = Date.now();
    let actual;
    if (arm === "direct") {
      actual = await runDirectTask(task, tracker.trackedClient);
    } else {
      const executor = new QuickJSExecutor({
        timeoutMs: 5000,
        memoryLimitBytes: 8 * 1024 * 1024,
        onHostEvent: (event) => hostEvents.push(event),
      });
      const validators = F1.makeValidators(ctx.inventory);
      const adapter = makeAdapter({
        client: tracker.trackedClient,
        inventory: ctx.inventory,
        validators,
        executor,
        validate: true,
      });
      const output = await adapter.tool.execute({ code: codeForTask(task) });
      actual = output.result;
    }
    const durationMs = Date.now() - started;
    const inbound = ctx.log.filter((entry) => entry.dir === "in");
    result.actual = actual;
    result.duration_ms = durationMs;
    result.mcp_calls = tracker.states.map((state) => {
      const snapshot = tracker.snapshot(state);
      const response = inbound.find(
        (entry) => entry.message?.id === snapshot.requestId,
      );
      return {
        name: snapshot.name,
        args: snapshot.args,
        request_id: snapshot.requestId,
        outcome: snapshot.outcome,
        error_code: snapshot.errorCode,
        duration_ms:
          snapshot.settledAt && snapshot.startedAt
            ? Date.parse(snapshot.settledAt) - Date.parse(snapshot.startedAt)
            : null,
        result_bytes: response ? JSON.stringify(response.message).length : 0,
      };
    });
    result.mcp_call_count = result.mcp_calls.length;
    result.mcp_result_bytes = result.mcp_calls.reduce(
      (sum, call) => sum + call.result_bytes,
      0,
    );
    result.result_bytes = JSON.stringify(actual).length;
    result.host_calls = hostEvents.filter((event) => event.type === "host_call_started").length;
    result.no_proposal = result.mcp_calls.every((call) => READ_TOOLS.includes(call.name));
    result.decision_identity_ok = equal(actual, task.expected);
    result.functional_completion = actual !== null && actual !== undefined;
    result.ok = result.decision_identity_ok && result.functional_completion;
    result.host_events = hostEvents;
  } catch (error) {
    result.error = error?.stack || error?.message || String(error);
    harness.event("task_error", { task: task.id, arm, error: result.error });
  } finally {
    if (ctx) {
      result.cleanup = await F1.cleanupDirect(ctx, harness);
      writeFileSync(
        join(RAW, `${runLabel}-${phase}-transport.jsonl`),
        ctx.log.map((entry) => JSON.stringify(entry)).join("\n") + "\n",
      );
      writeFileSync(
        join(RAW, `${runLabel}-${phase}-child-stderr.log`),
        ctx.stderrText(),
      );
      result.process_cleanup_ok =
        result.cleanup.errors?.length === 0 &&
        result.cleanup.server_alive_after === false;
    }
    harness.event("task_end", { task: task.id, arm, ok: result.ok });
    result.finished_at = new Date().toISOString();
  }
  return result;
}

async function runCancellation(runLabel) {
  const phase = "cancellation";
  const harness = F1.makeHarnessLog(join(RAW, `${runLabel}-${phase}-harness.jsonl`));
  harness.run = runLabel;
  let ctx = null;
  const result = { phase, ok: false };
  try {
    ctx = await F1.connectRelay({
      run: runLabel,
      phase,
      harness,
      mode: "withhold",
      withholdTools: ["decision.get"],
      fixture: FIXTURE,
    });
    const tracker = F1.createTracker(ctx.client);
    ctx.observer.tracker = tracker;
    const executor = new QuickJSExecutor({ timeoutMs: 250, memoryLimitBytes: 8 * 1024 * 1024 });
    const adapter = makeAdapter({
      client: tracker.trackedClient,
      inventory: ctx.inventory,
      validators: F1.makeValidators(ctx.inventory),
      executor,
      validate: true,
    });
    const before = ctx.control.events.length;
    const execPromise = adapter.tool.execute({
      code: `async () => codemode.decision_get({ record_id: "ADR-B0-001" })`,
    }).then(
      (output) => ({ result: output.result ?? null, error: null, stats: executor.stats() }),
      (error) => ({ result: null, error: error?.message || String(error), stats: executor.stats() }),
    );
    const withheld = await ctx.control.waitFor(
      (event) => event.type === "response_withheld",
      F1.CONTROL_TIMEOUT_MS,
      { after: before },
    );
    const outcome = await execPromise;
    const state = tracker.currentState();
    const settled = await tracker.waitForSettlement(state, 1000);
    const cancelEvents = ctx.log.filter(
      (entry) =>
        entry.dir === "out" &&
        entry.message?.method === "notifications/cancelled" &&
        entry.message?.params?.requestId === state.requestId,
    );
    const released = ctx.control.send({ cmd: "release", at: new Date().toISOString() });
    result.withheld = withheld.found;
    result.outcome = outcome;
    result.state = tracker.snapshot(state);
    result.settled = settled;
    result.cancellation_count = cancelEvents.length;
    result.released = released;
    result.stats = executor.stats();
    result.client_errors = ctx.clientErrors;
    result.ok =
      withheld.found &&
      Boolean(outcome.error) &&
      /execution exceeded/i.test(outcome.error ?? "") &&
      outcome.stats?.timedOut === true &&
      state.pending === false &&
      state.outcome === "rejected" &&
      state.errorCode === -32001 &&
      cancelEvents.length === 1 &&
      executor.stats()?.cancelledCalls === 1 &&
      executor.stats()?.cancelledUnsettled === 0;
  } catch (error) {
    result.error = error?.stack || error?.message || String(error);
    harness.event("cancellation_error", { error: result.error });
  } finally {
    if (ctx) result.cleanup = await F1.cleanupRelay(ctx, harness);
    result.finished_at = new Date().toISOString();
    harness.event("cancellation_end", { ok: result.ok });
  }
  return result;
}

async function runSuite(runLabel) {
  process.stdout.write(`[b0m] starting ${runLabel}\n`);
  const tasks = readJson(TASKS_PATH).tasks;
  const results = [];
  for (const task of tasks) {
    const direct = await runArm({ runLabel, task, arm: "direct" });
    const code = await runArm({ runLabel, task, arm: "code" });
    results.push({
      id: task.id,
      family: task.family,
      expected: task.expected,
      results: { direct, code },
    });
  }
  const cancellation = await runCancellation(runLabel);
  const run = {
    run: runLabel,
    started_at: new Date().toISOString(),
    tasks: results,
    cancellation,
    unhandled: [...unhandled],
    model_fields: {
      model_turns: NOT_MEASURED,
      input_tokens: NOT_MEASURED,
      output_tokens: NOT_MEASURED,
      intermediate_context_model_tokens: NOT_MEASURED,
      note: "B0-M is model-free; these fields are placeholders for B0-A, not observations.",
    },
  };
  run.checks = checksFor(run);
  run.verdict = run.checks.every((check) => check.pass) ? "PASS" : "FAIL";
  run.finished_at = new Date().toISOString();
  writeFileSync(join(EVIDENCE, `${runLabel}.json`), `${JSON.stringify(run, null, 2)}\n`);
  process.stdout.write(
    `${JSON.stringify({
      run: runLabel,
      verdict: run.verdict,
      failed: run.checks.filter((check) => !check.pass).map((check) => check.id),
    })}\n`,
  );
  return run;
}

const versions = versionInfo();
const tasksDocument = readJson(TASKS_PATH);
const fixtureHash = sha256File(FIXTURE);
const tasksHash = sha256File(TASKS_PATH);
const sourceHashes = {
  arms: sha256File(join(B0_DIR, "arms.mjs")),
  runner: sha256File(join(B0_DIR, "run-b0m.mjs")),
  make_corpus: sha256File(join(B0_DIR, "make-corpus.py")),
  make_tasks: sha256File(join(B0_DIR, "make-tasks.py")),
  fixture: fixtureHash,
  tasks: tasksHash,
  package_lock: sha256File(join(B0_DIR, "package-lock.json")),
  f1_executor: sha256File(F1_EXECUTOR),
  f1_adapter: sha256File(F1_ADAPTER),
  f1_relay: sha256File(F1_RELAY),
  f1_runner: sha256File(F1_RUNNER),
  frozen_executor: sha256File(FROZEN_EXECUTOR),
};
const preservedBefore = s1aDigest();
const frozenStatusBefore = gitLines([
  "status",
  "--porcelain",
  "--",
  "validation/cm01/s1a-local",
  "validation/cm01/p0-cancellation",
]);
const m4GuardBefore = checkM4Protection({ cwd: ROOT, baseSha: BASELINE });
const p0Verdict = readJson(join(P0_DIR, "evidence", "verdict.json"));
const p0Verification = readJson(join(P0_DIR, "evidence", "verification.json"));
const f1Verdict = readJson(join(F1_DIR, "evidence", "verdict.json"));
const f1Verification = readJson(join(F1_DIR, "evidence", "verification.json"));

const run1 = await runSuite("run1");
const run2 = await runSuite("run2");
const preservedAfter = s1aDigest();
const frozenStatusAfter = gitLines([
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
const m4GuardAfter = checkM4Protection({ cwd: ROOT, baseSha: BASELINE });

const normalized = (run) => ({
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
});
const repeatable = equal(normalized(run1), normalized(run2));
const sourceChecks = {
  f1_executor: sourceHashes.f1_executor === F1_EXECUTOR_SHA,
  f1_adapter: sourceHashes.f1_adapter === F1_ADAPTER_SHA,
  f1_relay: sourceHashes.f1_relay === F1_RELAY_SHA,
  f1_runner: sourceHashes.f1_runner === F1_RUNNER_SHA,
  frozen_executor: sourceHashes.frozen_executor === FROZEN_EXECUTOR_SHA,
  fixture: fixtureHash === tasksDocument.fixture.sha256,
};
const preservation = {
  pass:
    sourceChecks.f1_executor &&
    sourceChecks.f1_adapter &&
    sourceChecks.f1_relay &&
    sourceChecks.f1_runner &&
    sourceChecks.frozen_executor &&
    sourceChecks.fixture &&
    preservedBefore.digest === S1A_DIGEST &&
    preservedAfter.digest === S1A_DIGEST &&
    frozenStatusBefore.length === 0 &&
    frozenStatusAfter.length === 0 &&
    frozenDiff.length === 0 &&
    m4GuardBefore.pass === true &&
    m4GuardAfter.pass === true &&
    p0Verdict.verdict === "FAIL" &&
    p0Verification.verification_status === "VERIFIED" &&
    f1Verdict.verdict === "PASS" &&
    f1Verification.verification_status === "VERIFIED",
  source_checks: sourceChecks,
  s1a_digest_before: preservedBefore.digest,
  s1a_digest_after: preservedAfter.digest,
  frozen_status_before: frozenStatusBefore,
  frozen_status_after: frozenStatusAfter,
  frozen_diff: frozenDiff,
  m4_guard_before: m4GuardBefore,
  m4_guard_after: m4GuardAfter,
  p0_verdict: p0Verdict.verdict,
  p0_verification: p0Verification.verification_status,
  f1_verdict: f1Verdict.verdict,
  f1_verification: f1Verification.verification_status,
};

const allChecksPass = [run1, run2].every((run) => run.verdict === "PASS");
const verdict = {
  schema: "mneme.cm01.b0m.verdict/v1",
  started_at: run1.started_at,
  finished_at: new Date().toISOString(),
  baseline: BASELINE,
  head: gitLines(["rev-parse", "HEAD"])[0],
  scope: "CM-01-B0-M model-free mechanical benchmark",
  versions,
  source_hashes: sourceHashes,
  fixture: {
    path: "fixture/project_memory.json",
    sha256: fixtureHash,
    decisions: tasksDocument.tasks.length ? 24 : 0,
  },
  tasks: {
    path: "tasks.json",
    sha256: tasksHash,
    count: tasksDocument.tasks.length,
    families: tasksDocument.tasks.map((task) => ({ id: task.id, family: task.family })),
  },
  runs: [run1, run2],
  repeatable,
  checks: [run1.checks, run2.checks],
  model_fields: {
    status: NOT_MEASURED,
    note: "Model turns, input/output tokens, and model-visible intermediate context are not measured in B0-M.",
  },
  preservation,
  unhandled,
  verdict: allChecksPass && repeatable && preservation.pass && unhandled.length === 0 ? "PASS" : "FAIL",
  failed_checks: [run1, run2].flatMap((run) =>
    run.checks.filter((check) => !check.pass).map((check) => `${run.run}:${check.id}`),
  ),
  b0a: {
    authorized: false,
    note: "B0-A requires model/API/budget approval, a frozen B0-A protocol, and an approved primary endpoint/sample size.",
  },
  s1a2: {
    status: "undefined and blocked",
    note: "B0-M does not define, authorize, or unblock S1-A2.",
  },
  roadmap_corrections: [
    "Update docs/roadmap/README.md F1 status from uncommitted/unmerged to merged at f8591102 via PR #642 and independently VERIFIED.",
    "Mark the F1 evidence-record gate complete; reference CM-01-B0-M and B0-A as the benchmark gates.",
    "Update issue #640 current state: F1 merged and VERIFIED; B0 protocol reviewed; B0-M mechanical validation complete/pending review; B0-A not authorized.",
    "Keep S1-A2 explicitly undefined and blocked; do not treat B0-M or B0-A as S1-A2.",
    "Keep CM-01 parallel/optional; do not make it a dependency of core enforcement validation.",
  ],
  limitations: [
    "Model-free mechanical benchmark only; no model-turn, token, or efficiency claims.",
    "Timing is mechanical and environment-specific; not a model or production performance claim.",
    "No server-side execution termination claim.",
    "No production integration, Workers, hardened isolation, or S1-A2 claim.",
    "B0-A statistical power, primary endpoint, material-effect threshold, and multiple-comparison policy are not validated by B0-M.",
  ],
};

writeFileSync(join(EVIDENCE, "verdict.json"), `${JSON.stringify(verdict, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "versions.json"), `${JSON.stringify(versions, null, 2)}\n`);
writeFileSync(
  join(EVIDENCE, "measurements.json"),
  `${JSON.stringify(
    {
      scope: "mechanical timing only",
      model_fields: verdict.model_fields,
      runs: {
        run1: run1.tasks.map((task) => ({
          task: task.id,
          direct_ms: task.results.direct.duration_ms,
          code_ms: task.results.code.duration_ms,
          direct_mcp_calls: task.results.direct.mcp_call_count,
          code_mcp_calls: task.results.code.mcp_call_count,
          direct_result_bytes: task.results.direct.result_bytes,
          code_result_bytes: task.results.code.result_bytes,
          direct_mcp_result_bytes: task.results.direct.mcp_result_bytes,
          code_mcp_result_bytes: task.results.code.mcp_result_bytes,
        })),
        run2: run2.tasks.map((task) => ({
          task: task.id,
          direct_ms: task.results.direct.duration_ms,
          code_ms: task.results.code.duration_ms,
          direct_mcp_calls: task.results.direct.mcp_call_count,
          code_mcp_calls: task.results.code.mcp_call_count,
          direct_result_bytes: task.results.direct.result_bytes,
          code_result_bytes: task.results.code.result_bytes,
          direct_mcp_result_bytes: task.results.direct.mcp_result_bytes,
          code_mcp_result_bytes: task.results.code.mcp_result_bytes,
        })),
      },
    },
    null,
    2,
  )}\n`,
);
process.stdout.write(
  `${JSON.stringify({
    verdict: verdict.verdict,
    repeatable,
    preservation: preservation.pass,
    failed_checks: verdict.failed_checks,
    model_fields: verdict.model_fields.status,
  })}\n`,
);
process.exit(verdict.verdict === "PASS" ? 0 : 1);



