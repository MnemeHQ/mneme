import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { checkM4Protection } from "../s1a-local/m4-guard.mjs";

const F1_DIR = dirname(fileURLToPath(import.meta.url));
const CM01_DIR = dirname(F1_DIR);
const ROOT = resolve(F1_DIR, "../../..");
const EVIDENCE = join(F1_DIR, "evidence");
const RAW = join(EVIDENCE, "raw");
const P0_DIR = join(CM01_DIR, "p0-cancellation");
const S1A_DIR = join(CM01_DIR, "s1a-local");
const M4_FIXTURE = join(S1A_DIR, "m4", "fixture", "canonical", "project_memory.json");
const P0_FIXTURE = join(S1A_DIR, "m1", "fixture", "canonical", "project_memory.json");
const DECLARED_BASELINE = "adf50933d0beac255ac2a134e00ee13d40442302";
const EXPECTED_CHECKS = [
  "F1-N1-CONTROL-DIRECT",
  "F1-N2-CONTROL-RELAY",
  "F1-T1-TIMEOUT-SETTLES",
  "F1-T2-LATE-NO-REVIVAL",
  "F1-C1-RACE-BEFORE",
  "F1-C2-RACE-BOUNDARY",
  "F1-C3-RACE-AFTER",
  "F1-C3-PARALLEL",
  "F1-R1-SEQUENTIAL",
  "F1-R2-REPEATED",
  "F1-F1-TRANSPORT-CLOSE",
  "F1-F2-TIMEOUT-THEN-CLOSE",
  "F1-A1-VALIDATION",
  "F1-A2-MCP-ISERROR",
  "F1-A3-PROPOSALS",
  "F1-S1-GENUINE-CANCEL-FRAME",
  "F1-S2-SYNTHETIC-CANCEL",
  "F1-P1-CLEANUP",
  "F1-P1-NO-POST-DISPOSAL",
  "F1-NO-UNHANDLED",
];
const SOURCE_FILES = [
  "quickjs-executor.mjs",
  "adapter.mjs",
  "relay.mjs",
  "synthetic-server.mjs",
  "harness.mjs",
  "run-f1.mjs",
  "package.json",
  "package-lock.json",
  ".gitignore",
  ".gitattributes",
  "README.md",
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

function sha256GitBlob(ref, path) {
  const buffer = execFileSync("git", ["show", `${ref}:${path}`], {
    cwd: ROOT,
    maxBuffer: 32 * 1024 * 1024,
  });
  return createHash("sha256").update(buffer).digest("hex");
}

function gitLines(args) {
  const text = execFileSync("git", args, { cwd: ROOT, encoding: "utf8" }).trim();
  return text ? text.split(/\r?\n/) : [];
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function readJsonl(path) {
  if (!existsSync(path)) return [];
  return readFileSync(path, "utf8")
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line));
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

function raw(run, phase, suffix) {
  return join(RAW, `${run}-${phase}-${suffix}`);
}

function count(events, type, predicate = () => true) {
  return events.filter((event) => event.type === type && predicate(event)).length;
}

function one(events, type, predicate = () => true) {
  return events.find((event) => event.type === type && predicate(event)) ?? null;
}

function ids(events) {
  return events.map((event) => event.requestId).filter((value) => value !== undefined);
}

function phaseOf(run, name) {
  return run[name];
}

function latencySamples(run) {
  const samples = [];
  const add = (scenario, state) => {
    if (state?.cancellationSentAt && state?.settledAt) {
      samples.push({
        run: run.run,
        scenario,
        abortToSettlementMs: Date.parse(state.settledAt) - Date.parse(state.cancellationSentAt),
      });
    }
  };
  add("timeout-withhold", run.timeoutWithhold?.stateAtReturn);
  for (const iteration of run.repeated?.iterations ?? []) add(`repeated-${iteration.index}`, iteration.state);
  add("parallel-search", run.parallel?.search);
  add("sequential-trace", run.sequential?.states?.["decision.trace"]);
  add("transport-close", run.transportClose?.state);
  add("timeout-then-close", run.timeoutThenClose?.state);
  add("synthetic", run.synthetic?.state);
  return samples;
}

function summary(samples) {
  if (samples.length === 0) return { samples: 0, max_ms: null, min_ms: null, mean_ms: null };
  const values = samples.map((entry) => entry.abortToSettlementMs);
  return {
    samples: samples.length,
    max_ms: Math.max(...values),
    min_ms: Math.min(...values),
    mean_ms: values.reduce((sum, value) => sum + value, 0) / values.length,
  };
}

function normalized(run, { includeBoundaryExact = true } = {}) {
  const race = (iteration) => ({
    label: iteration?.label ?? null,
    outcome: iteration?.state?.outcome ?? null,
    errorCode: iteration?.state?.errorCode ?? null,
    pending: iteration?.state?.pending ?? null,
    cancelCount: iteration?.cancel?.count ?? null,
    timedOut: iteration?.stats?.timedOut ?? null,
    cancelledCalls: iteration?.stats?.cancelledCalls ?? null,
    cancelledUnsettled: iteration?.stats?.cancelledUnsettled ?? null,
  });
  return {
    checks: run.checks?.map((entry) => ({ id: entry.id, pass: entry.pass })),
    controlDirect: { parity: run.controlDirect?.parity, order: run.controlDirect?.order, ok: run.controlDirect?.ok },
    controlRelay: { parity: run.controlRelay?.parity, relayEvents: run.controlRelay?.relayEvents, ok: run.controlRelay?.ok },
    timeout: {
      ok: run.timeoutWithhold?.ok,
      pendingAtDeadline: run.timeoutWithhold?.pendingAtDeadline,
      pendingAtExecutionReturn: run.timeoutWithhold?.pendingAtExecutionReturn,
      outcome: run.timeoutWithhold?.stateAtReturn?.outcome,
      errorCode: run.timeoutWithhold?.stateAtReturn?.errorCode,
      cancelCount: run.timeoutWithhold?.cancel?.count,
      cancelAfterRelease: run.timeoutWithhold?.cancelAfterRelease?.count,
      lateAfterRelease: run.timeoutWithhold?.lateResponsesAfterRelease,
      stateAfterRelease: run.timeoutWithhold?.stateAfterRelease?.outcome,
      cancelledCalls: run.timeoutWithhold?.stats?.cancelledCalls,
      cancelledSettled: run.timeoutWithhold?.stats?.cancelledSettled,
      cancelledUnsettled: run.timeoutWithhold?.stats?.cancelledUnsettled,
      failedCalls: run.timeoutWithhold?.stats?.failedCalls,
    },
    raceBefore: race(run.raceBefore?.iteration),
    raceAfter: race(run.raceAfter?.iteration),
    raceBoundary: includeBoundaryExact
      ? (run.raceBoundary?.iterations ?? []).map(race)
      : {
          ok: run.raceBoundary?.ok,
          invalid: run.raceBoundary?.invalid,
          count: (run.raceBoundary?.iterations ?? []).length,
        },
    parallel: {
      ok: run.parallel?.ok,
      getOutcome: run.parallel?.get?.outcome,
      searchOutcome: run.parallel?.search?.outcome,
      searchError: run.parallel?.search?.errorCode,
      getCancel: run.parallel?.getCancel?.count,
      searchCancel: run.parallel?.searchCancel?.count,
      cancelledCalls: run.parallel?.stats?.cancelledCalls,
      resolvedCalls: run.parallel?.stats?.resolvedCalls,
    },
    sequential: {
      ok: run.sequential?.ok,
      outcomes: Object.fromEntries(
        Object.entries(run.sequential?.states ?? {}).map(([name, state]) => [name, state.outcome]),
      ),
      cancellations: Object.fromEntries(
        Object.entries(run.sequential?.cancellations ?? {}).map(([name, cancel]) => [name, cancel.count]),
      ),
      cancelledCalls: run.sequential?.stats?.cancelledCalls,
      resolvedCalls: run.sequential?.stats?.resolvedCalls,
    },
    repeated: {
      ok: run.repeated?.ok,
      iterations: (run.repeated?.iterations ?? []).map((iteration) => ({
        outcome: iteration.state?.outcome,
        errorCode: iteration.state?.errorCode,
        cancelCount: iteration.cancel?.count,
        cancelledSettled: iteration.stats?.cancelledSettled,
        cancelledUnsettled: iteration.stats?.cancelledUnsettled,
      })),
    },
    transportClose: {
      ok: run.transportClose?.ok,
      outcome: run.transportClose?.state?.outcome,
      errorCode: run.transportClose?.state?.errorCode,
      cancelCount: run.transportClose?.cancel?.count,
      timedOut: run.transportClose?.stats?.timedOut,
      cancelledCalls: run.transportClose?.stats?.cancelledCalls,
      failedCalls: run.transportClose?.stats?.failedCalls,
    },
    timeoutThenClose: {
      ok: run.timeoutThenClose?.ok,
      errorCode: run.timeoutThenClose?.state?.errorCode,
      cancelCount: run.timeoutThenClose?.cancel?.count,
      afterCloseError: run.timeoutThenClose?.afterClose?.errorCode,
    },
    validation: {
      ok: run.validation?.ok,
      trackedCalls: run.validation?.trackedCalls?.length,
      cancelledCalls: run.validation?.stats?.cancelledCalls,
    },
    mcpError: {
      ok: run.mcpError?.ok,
      stateOutcome: run.mcpError?.state?.outcome,
      isError: run.mcpError?.adapterCalls?.[0]?.isError,
      cancelCount: run.mcpError?.cancel?.count,
    },
    synthetic: {
      ok: run.synthetic?.ok,
      stateOutcome: run.synthetic?.state?.outcome,
      errorCode: run.synthetic?.state?.errorCode,
      cancelCount: run.synthetic?.cancel?.count,
      aborted: run.synthetic?.serverReturned?.aborted,
      responseExpected: run.synthetic?.serverReturned?.response_expected,
      responseAfterCancel: run.synthetic?.responseAfterCancel,
    },
    p0_comparison: run.p0_comparison,
    unhandled: run.unhandled,
  };
}

function packageInstalledVersion(name) {
  const path = join(F1_DIR, "node_modules", ...name.split("/"), "package.json");
  return readJson(path).version;
}

const manifestBefore = evidenceManifest();
const verdict = readJson(join(EVIDENCE, "verdict.json"));
const runFiles = [readJson(join(EVIDENCE, "run1.json")), readJson(join(EVIDENCE, "run2.json"))];
const versions = readJson(join(EVIDENCE, "versions.json"));
const measurements = readJson(join(EVIDENCE, "measurements.json"));
const head = gitLines(["rev-parse", "HEAD"])[0];

check(
  "F1-ORIGINAL-VERDICT",
  verdict.verdict === "PASS" &&
    runFiles.every((run) => run.verdict === "PASS") &&
    runFiles.every((run) => run.checks?.length === 20) &&
    runFiles.every((run) => run.checks.every((entry) => entry.pass)),
  {
    verdict: verdict.verdict,
    runs: runFiles.map((run) => ({
      run: run.run,
      verdict: run.verdict,
      checks: run.checks?.length,
      failed: run.checks?.filter((entry) => !entry.pass).map((entry) => entry.id),
    })),
  },
);

const checkIdsByRun = runFiles.map((run) => run.checks.map((entry) => entry.id));
check(
  "F1-CHECK-MATRIX",
  runFiles.every(
    (run) =>
      new Set(run.checks.map((entry) => entry.id)).size === 20 &&
      EXPECTED_CHECKS.every((id) =>
        run.checks.some((entry) => entry.id === id && entry.pass === true),
      ) &&
      run.checks.every((entry) => entry.pass === true),
  ),
  { expected: EXPECTED_CHECKS, actual: checkIdsByRun },
);

check(
  "F1-REPEATABLE",
  verdict.repeatable === true &&
    equal(
      normalized(runFiles[0]),
      normalized(runFiles[1]),
    ),
  {
    recorded: verdict.repeatable,
    derived: equal(normalized(runFiles[0]), normalized(runFiles[1])),
  },
);

const identityKeys = [
  "f1_executor",
  "f1_adapter",
  "f1_relay",
  "f1_synthetic_server",
  "f1_runner",
  "package_lock",
  "fixture",
  "p0_fixture",
  "p0_verdict",
  "p0_run1",
  "p0_run2",
  "frozen_executor",
];
const identityResults = Object.fromEntries(
  identityKeys.map((key) => {
    const entry = verdict.identities[key];
    return [key, Boolean(entry) && sha256File(entry.path) === entry.sha256];
  }),
);
check("F1-SOURCE-HASHES", Object.values(identityResults).every(Boolean), identityResults);

const pkg = readJson(join(F1_DIR, "package.json"));
const installed = {
  codemode: packageInstalledVersion("@cloudflare/codemode"),
  sdk: packageInstalledVersion("@modelcontextprotocol/sdk"),
  ajv: packageInstalledVersion("ajv"),
  quickjs: packageInstalledVersion("quickjs-emscripten"),
  zod: packageInstalledVersion("zod"),
};
const python = JSON.parse(
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
    { cwd: F1_DIR, env: { ...process.env, PYTHONPATH: ROOT }, encoding: "utf8" },
  ),
);
check(
  "F1-VERSIONS",
  equal(verdict.versions, versions) &&
    verdict.versions.node === process.version &&
    verdict.versions.codemode === pkg.dependencies["@cloudflare/codemode"] &&
    verdict.versions.sdk === pkg.dependencies["@modelcontextprotocol/sdk"] &&
    verdict.versions.ajv === pkg.dependencies.ajv &&
    verdict.versions.quickjs === pkg.dependencies["quickjs-emscripten"] &&
    verdict.versions.zod === pkg.dependencies.zod &&
    installed.codemode === verdict.versions.codemode &&
    installed.sdk === verdict.versions.sdk &&
    installed.ajv === verdict.versions.ajv &&
    installed.quickjs === verdict.versions.quickjs &&
    installed.zod === verdict.versions.zod &&
    python.python === verdict.versions.python &&
    python.mneme === verdict.versions.mneme &&
    python.mcp === verdict.versions.mcp,
  { recorded: verdict.versions, installed, python, package: pkg.dependencies },
);

const fixtureChecks = {
  m4: sha256File(M4_FIXTURE) === "b4d83d0cc0f70f442e2a62bd0e527220ae99b07cba1238e39d0ad8c5685d4e7f",
  m1: sha256File(P0_FIXTURE) === "8f73429e70e04a6876b965bb00a1777fc90409f9da2889c72dab9ac26b9621ea",
  m4_baseline: sha256GitBlob("HEAD", "validation/cm01/s1a-local/m4/fixture/canonical/project_memory.json") === sha256File(M4_FIXTURE),
  m1_baseline: sha256GitBlob("HEAD", "validation/cm01/s1a-local/m1/fixture/canonical/project_memory.json") === sha256File(P0_FIXTURE),
};
check("F1-FIXTURES", Object.values(fixtureChecks).every(Boolean), fixtureChecks);

const recordedLatency = verdict.cancellation_latency;
const recomputedSamples = runFiles.flatMap((run) => latencySamples(run));
const recomputedLatency = summary(recomputedSamples);
const calibration = verdict.grace_decision?.calibration;
const latencyChecks = {
  grace_is_50: verdict.host_cancellation_grace_ms === 50,
  provisional_is_100: verdict.grace_decision?.provisional_ms === 100,
  final_is_50: verdict.grace_decision?.final_ms === 50,
  calibration_present: Boolean(calibration) && calibration.latency?.samples > 0,
  calibration_max_3: calibration?.latency?.max_ms === 3,
  samples_match: recordedLatency.samples === recomputedLatency.samples,
  max_match: recordedLatency.max_ms === recomputedLatency.max_ms,
  min_match: recordedLatency.min_ms === recomputedLatency.min_ms,
  mean_match: Math.abs(recordedLatency.mean_ms - recomputedLatency.mean_ms) < 1e-9,
  all_within_grace: recomputedSamples.every(
    (sample) => sample.abortToSettlementMs >= 0 && sample.abortToSettlementMs <= 50,
  ),
  measurements_file_matches:
    measurements.host_cancellation_grace_ms === 50 &&
    measurements.latency?.samples === recomputedLatency.samples &&
    measurements.latency?.max_ms === recomputedLatency.max_ms,
};
check("F1-GRACE-AND-LATENCY", Object.values(latencyChecks).every(Boolean), {
  ...latencyChecks,
  recorded: { samples: recordedLatency.samples, max_ms: recordedLatency.max_ms, min_ms: recordedLatency.min_ms, mean_ms: recordedLatency.mean_ms },
  recomputed: recomputedLatency,
});

check(
  "F1-N1-CONTROL-DIRECT",
  runFiles.every(
    (run) =>
      phaseOf(run, "controlDirect").ok === true &&
      Object.values(phaseOf(run, "controlDirect").parity).every(Boolean) &&
      equal(phaseOf(run, "controlDirect").order, [
        "decision.get",
        "decision.search",
        "decision.applicable_to",
        "decision.trace",
      ]) &&
      phaseOf(run, "controlDirect").stats.cancelledCalls === 0 &&
      phaseOf(run, "controlDirect").stats.resolvedCalls === 4,
  ),
  runFiles.map((run) => phaseOf(run, "controlDirect").parity),
);

const relayControlRaw = runFiles.map((run) => {
  const events = readJsonl(raw(run.run, "control-relay", "relay.jsonl"));
  return {
    run: run.run,
    targetForwarded: count(events, "target_request_forwarded"),
    upstreamResponses: count(events, "upstream_response_received"),
    withheld: count(events, "response_withheld"),
    cancellations: count(events, "cancel_from_client"),
  };
});
check(
  "F1-N2-CONTROL-RELAY",
  runFiles.every(
    (run) =>
      phaseOf(run, "controlRelay").ok === true &&
      Object.values(phaseOf(run, "controlRelay").parity).every(Boolean),
  ) &&
    relayControlRaw.every(
      (entry) =>
        entry.targetForwarded === 4 &&
        entry.upstreamResponses === 4 &&
        entry.withheld === 0 &&
        entry.cancellations === 0,
    ),
  relayControlRaw,
);

const timeoutRaw = runFiles.map((run) => {
  const relay = readJsonl(raw(run.run, "timeout-withhold", "relay.jsonl"));
  const child = readJsonl(raw(run.run, "timeout-withhold", "child-events.jsonl"));
  const host = readJsonl(raw(run.run, "timeout-withhold", "host-events.jsonl"));
  const phase = phaseOf(run, "timeoutWithhold");
  const requestId = phase.stateAtReturn?.requestId;
  const cancelEvent = one(relay, "cancel_from_client", (event) => event.requestId === requestId);
  const releaseEvent = one(relay, "response_released_downstream", (event) => event.requestId === requestId);
  const withheldEvent = one(relay, "response_withheld", (event) => event.requestId === requestId);
  const childCancel = child.find(
    (event) =>
      event.type === "child_stdin_line" &&
      event.line?.includes("notifications/cancelled") &&
      event.line?.includes(`"requestId":${requestId}`),
  );
  const aborted = one(host, "host_call_aborted");
  const settledAfterAbort = one(host, "host_call_settled_after_abort");
  return {
    run: run.run,
    phase,
    requestId,
    withheldEvent,
    cancelEvent,
    releaseEvent,
    childCancel,
    aborted,
    settledAfterAbort,
    settledBeforeFinish:
      Boolean(phase.stateAtReturn?.settledAt) &&
      Boolean(phase.finished_at) &&
      Date.parse(phase.stateAtReturn.settledAt) <= Date.parse(phase.finished_at),
  };
});
check(
  "F1-T1-TIMEOUT-SETTLES",
  timeoutRaw.every(
    (entry) =>
      entry.phase.ok === true &&
      entry.phase.pendingAtDeadline === true &&
      entry.phase.pendingAtExecutionReturn === false &&
      entry.phase.stateAtReturn?.outcome === "rejected" &&
      entry.phase.stateAtReturn?.errorCode === -32001 &&
      entry.phase.cancel?.count === 1 &&
      entry.phase.controlCancellation?.requestId === entry.requestId &&
      Boolean(entry.withheldEvent) &&
      Boolean(entry.cancelEvent) &&
      Boolean(entry.childCancel) &&
      Boolean(entry.aborted) &&
      entry.settledAfterAbort?.outcome === "rejected" &&
      entry.settledAfterAbort?.afterAbortMs <= 50 &&
      entry.settledBeforeFinish &&
      entry.phase.stats.cancelledCalls === 1 &&
      entry.phase.stats.cancelledSettled === 1 &&
      entry.phase.stats.cancelledUnsettled === 0 &&
      entry.phase.stats.failedCalls === 0,
  ),
  timeoutRaw,
);

check(
  "F1-T2-LATE-NO-REVIVAL",
  runFiles.every((run) => {
    const phase = phaseOf(run, "timeoutWithhold");
    const relay = readJsonl(raw(run.run, "timeout-withhold", "relay.jsonl"));
    const released = one(relay, "response_released_downstream", (event) => event.requestId === phase.stateAtReturn?.requestId);
    return (
      phase.stateAfterRelease?.outcome === "rejected" &&
      phase.stateAfterRelease?.errorCode === -32001 &&
      phase.lateResponsesAfterRelease >= 1 &&
      phase.cancelAfterRelease?.count === 1 &&
      Boolean(released) &&
      Boolean(phase.childCancellationFrame)
    );
  }),
  runFiles.map((run) => phaseOf(run, "timeoutWithhold").stateAfterRelease),
);

check(
  "F1-ZERO-CANCEL-COMPLETED",
  runFiles.every((run) => {
    const parallelRelay = readJsonl(raw(run.run, "parallel", "relay.jsonl"));
    const sequentialRelay = readJsonl(raw(run.run, "sequential-fourth", "relay.jsonl"));
    const parallelGetId = phaseOf(run, "parallel").get?.requestId;
    const sequentialFirst = ["decision.get", "decision.search", "decision.applicable_to"];
    const sequentialFirstIds = sequentialFirst.map(
      (name) => phaseOf(run, "sequential").states?.[name]?.requestId,
    );
    return (
      phaseOf(run, "controlDirect").stats.cancelledCalls === 0 &&
      phaseOf(run, "controlRelay").relayEvents.cancellations === 0 &&
      phaseOf(run, "parallel").getCancel?.count === 0 &&
      phaseOf(run, "parallel").searchCancel?.count === 1 &&
      phaseOf(run, "raceBefore").iteration?.cancel?.count === 0 &&
      sequentialFirst.every(
        (name) => phaseOf(run, "sequential").cancellations?.[name]?.count === 0,
      ) &&
      count(parallelRelay, "cancel_from_client", (event) => event.requestId === parallelGetId) === 0 &&
      sequentialFirstIds.every(
        (id) => count(sequentialRelay, "cancel_from_client", (event) => event.requestId === id) === 0,
      )
    );
  }),
  null,
);

const raceRaw = runFiles.map((run) => {
  const before = readJsonl(raw(run.run, "race-before", "relay.jsonl"));
  const after = readJsonl(raw(run.run, "race-after", "relay.jsonl"));
  return {
    run: run.run,
    beforeDelayed: count(before, "response_forwarded_downstream", (event) => event.how === "delay"),
    afterDelayed: count(after, "response_forwarded_downstream", (event) => event.how === "delay"),
    afterCancel: count(after, "cancel_from_client"),
  };
});
check(
  "F1-RACES",
  runFiles.every(
    (run) =>
      phaseOf(run, "raceBefore").iteration?.state?.outcome === "fulfilled" &&
      phaseOf(run, "raceBefore").iteration?.cancel?.count === 0 &&
      phaseOf(run, "raceAfter").iteration?.state?.outcome === "rejected" &&
      phaseOf(run, "raceAfter").iteration?.state?.errorCode === -32001 &&
      phaseOf(run, "raceAfter").iteration?.cancel?.count === 1 &&
      phaseOf(run, "raceAfter").iteration?.afterForward?.outcome === "rejected" &&
      phaseOf(run, "raceBoundary").invalid === 0 &&
      (phaseOf(run, "raceBoundary").iterations ?? []).every(
        (iteration) =>
          iteration.state?.pending === false &&
          !(iteration.state?.outcome === "fulfilled" && iteration.cancel?.count > 0),
      ),
  ) &&
    raceRaw.every((entry) => entry.beforeDelayed === 1 && entry.afterDelayed === 1 && entry.afterCancel === 1),
  { runs: runFiles.map((run) => ({
    before: phaseOf(run, "raceBefore").iteration?.state,
    after: phaseOf(run, "raceAfter").iteration?.state,
    boundary: phaseOf(run, "raceBoundary").iterations?.map((iteration) => ({
      outcome: iteration.state?.outcome,
      cancel: iteration.cancel?.count,
    })),
  })), raw: raceRaw },
);

const parallelRaw = runFiles.map((run) => {
  const relay = readJsonl(raw(run.run, "parallel", "relay.jsonl"));
  return {
    run: run.run,
    cancellations: count(relay, "cancel_from_client"),
    withheld: count(relay, "response_withheld"),
    withheldTool: one(relay, "response_withheld")?.tool ?? null,
  };
});
check(
  "F1-PARALLEL",
  runFiles.every(
    (run) =>
      phaseOf(run, "parallel").get?.outcome === "fulfilled" &&
      phaseOf(run, "parallel").search?.outcome === "rejected" &&
      phaseOf(run, "parallel").search?.errorCode === -32001 &&
      phaseOf(run, "parallel").getCancel?.count === 0 &&
      phaseOf(run, "parallel").searchCancel?.count === 1 &&
      phaseOf(run, "parallel").stats?.cancelledCalls === 1,
  ) && parallelRaw.every((entry) => entry.cancellations === 1 && entry.withheld === 1 && entry.withheldTool === "decision.search"),
  parallelRaw,
);

const sequentialRaw = runFiles.map((run) => {
  const relay = readJsonl(raw(run.run, "sequential-fourth", "relay.jsonl"));
  return {
    run: run.run,
    cancellations: count(relay, "cancel_from_client"),
    withheldTool: one(relay, "response_withheld")?.tool ?? null,
  };
});
check(
  "F1-SEQUENTIAL",
  runFiles.every(
    (run) =>
      phaseOf(run, "sequential").states?.["decision.get"]?.outcome === "fulfilled" &&
      phaseOf(run, "sequential").states?.["decision.search"]?.outcome === "fulfilled" &&
      phaseOf(run, "sequential").states?.["decision.applicable_to"]?.outcome === "fulfilled" &&
      phaseOf(run, "sequential").states?.["decision.trace"]?.outcome === "rejected" &&
      phaseOf(run, "sequential").states?.["decision.trace"]?.errorCode === -32001 &&
      phaseOf(run, "sequential").cancellations?.["decision.trace"]?.count === 1 &&
      phaseOf(run, "sequential").stats?.cancelledCalls === 1 &&
      phaseOf(run, "sequential").stats?.resolvedCalls === 3,
  ) && sequentialRaw.every((entry) => entry.cancellations === 1 && entry.withheldTool === "decision.trace"),
  sequentialRaw,
);

check(
  "F1-REPEATED",
  runFiles.every(
    (run) =>
      phaseOf(run, "repeated").iterations?.length === 3 &&
      phaseOf(run, "repeated").iterations.every(
        (iteration) =>
          iteration.state?.outcome === "rejected" &&
          iteration.state?.errorCode === -32001 &&
          iteration.cancel?.count === 1 &&
          iteration.settled?.found === true &&
          iteration.stats?.cancelledCalls === 1 &&
          iteration.stats?.cancelledUnsettled === 0,
      ),
  ) &&
    runFiles.every((run) => count(readJsonl(raw(run.run, "repeated", "relay.jsonl")), "cancel_from_client") === 3),
  runFiles.map((run) => phaseOf(run, "repeated").iterations?.length),
);

check(
  "F1-TRANSPORT-CLOSE",
  runFiles.every((run) => {
    const relay = readJsonl(raw(run.run, "transport-close", "relay.jsonl"));
    const phase = phaseOf(run, "transportClose");
    return (
      phase.pendingBeforeClose === true &&
      phase.state?.outcome === "rejected" &&
      phase.state?.errorCode === -32000 &&
      phase.cancel?.count === 0 &&
      phase.stats?.timedOut === false &&
      phase.stats?.cancelledCalls === 0 &&
      phase.stats?.failedCalls === 1 &&
      count(relay, "cancel_from_client") === 0 &&
      count(relay, "child_exit") === 1
    );
  }),
  runFiles.map((run) => phaseOf(run, "transportClose").state),
);

check(
  "F1-TIMEOUT-THEN-CLOSE",
  runFiles.every((run) => {
    const phase = phaseOf(run, "timeoutThenClose");
    return (
      phase.state?.outcome === "rejected" &&
      phase.state?.errorCode === -32001 &&
      phase.cancel?.count === 1 &&
      phase.afterClose?.outcome === "rejected" &&
      phase.afterClose?.errorCode === -32001 &&
      phase.stats?.cancelledCalls === 1
    );
  }),
  runFiles.map((run) => phaseOf(run, "timeoutThenClose").state),
);

check(
  "F1-VALIDATION",
  runFiles.every((run) => {
    const phase = phaseOf(run, "validation");
    return (
      phase.trackedCalls?.length === 0 &&
      phase.cancel?.count === 0 &&
      phase.stats?.cancelledCalls === 0 &&
      /Argument validation failed/.test(phase.outcome?.error ?? "")
    );
  }),
  runFiles.map((run) => phaseOf(run, "validation").outcome?.error),
);

check(
  "F1-MCP-ERROR",
  runFiles.every((run) => {
    const phase = phaseOf(run, "mcpError");
    return (
      phase.state?.outcome === "fulfilled" &&
      phase.adapterCalls?.[0]?.isError === true &&
      phase.cancel?.count === 0 &&
      phase.stats?.cancelledCalls === 0
    );
  }),
  runFiles.map((run) => phaseOf(run, "mcpError").adapterCalls),
);

check(
  "F1-PROPOSALS",
  runFiles.every(
    (run) =>
      phaseOf(run, "controlDirect").outcome?.result?.capabilities?.propose === "undefined" &&
      phaseOf(run, "controlDirect").outcome?.result?.capabilities?.propose_batch === "undefined",
  ),
  runFiles.map((run) => phaseOf(run, "controlDirect").outcome?.result?.capabilities),
);

check(
  "F1-S1-GENUINE-CANCEL-FRAME",
  timeoutRaw.every(
    (entry) =>
      Boolean(entry.childCancel) &&
      entry.phase.serverResponseBeforeCancel === true &&
      Boolean(entry.withheldEvent) &&
      Boolean(entry.cancelEvent),
  ),
  timeoutRaw.map((entry) => ({
    requestId: entry.requestId,
    childCancel: entry.childCancel,
    serverResponseBeforeCancel: entry.phase.serverResponseBeforeCancel,
  })),
);

check(
  "F1-S2-SYNTHETIC-CANCEL",
  runFiles.every((run) => {
    const phase = phaseOf(run, "synthetic");
    const events = readJsonl(raw(run.run, "synthetic-cancel", "server.jsonl"));
    const started = one(events, "tool_started");
    const aborted = one(events, "signal_aborted");
    const returned = one(events, "handler_returned");
    return (
      phase.state?.outcome === "rejected" &&
      phase.state?.errorCode === -32001 &&
      phase.cancel?.count === 1 &&
      phase.responseAfterCancel === 0 &&
      Boolean(started) &&
      Boolean(aborted) &&
      returned?.aborted === true &&
      returned?.response_expected === false &&
      phase.stats?.cancelledCalls === 1
    );
  }),
  runFiles.map((run) => phaseOf(run, "synthetic").serverReturned),
);

const cleanupChecks = runFiles.map((run) => {
  const failures = [];
  for (const [name, value] of Object.entries(run)) {
    if (!value || !value.cleanup) continue;
    if (value.cleanup.errors?.length) failures.push(`${name}: errors`);
    if (value.cleanup.relay_alive_after === true) failures.push(`${name}: relay alive`);
    if (value.cleanup.upstream_alive_after === true) failures.push(`${name}: upstream alive`);
    if (value.cleanup.server_alive_after === true) failures.push(`${name}: server alive`);
  }
  for (const phase of [
    "control-relay",
    "timeout-withhold",
    "race-before",
    "race-boundary",
    "race-after",
    "parallel",
    "sequential-fourth",
    "repeated",
    "transport-close",
    "timeout-then-close",
  ]) {
    const events = readJsonl(raw(run.run, phase, "relay.jsonl"));
    if (count(events, "child_exit") === 0) failures.push(`${phase}: no child_exit`);
  }
  return { run: run.run, failures };
});
check("F1-CLEANUP", cleanupChecks.every((entry) => entry.failures.length === 0), cleanupChecks);

const postDisposal = runFiles.map((run) => {
  const groups = [
    run.timeoutWithhold?.hostEvents,
    run.raceBefore?.iteration?.hostEvents,
    run.raceAfter?.iteration?.hostEvents,
    ...(run.raceBoundary?.iterations ?? []).map((iteration) => iteration.hostEvents),
    ...(run.repeated?.iterations ?? []).map((iteration) => iteration.hostEvents),
  ].filter(Boolean);
  const events = groups.flat();
  return {
    run: run.run,
    hostEvents: events.length,
    unsettled: events.filter((event) => event.type === "host_call_unsettled_after_grace"),
    late: events.filter(
      (event) =>
        event.type === "host_call_settled_after_abort" &&
        (event.afterAbortMs == null || event.afterAbortMs > 50),
    ),
  };
});
check(
  "F1-POST-DISPOSAL",
  postDisposal.every((entry) => entry.unsettled.length === 0 && entry.late.length === 0),
  postDisposal,
);

check(
  "F1-UNHANDLED",
  verdict.unhandled?.length === 0 &&
    runFiles.every((run) => (run.unhandled ?? []).length === 0),
  { verdict: verdict.unhandled, runs: runFiles.map((run) => run.unhandled) },
);

const p0Verdict = readJson(join(P0_DIR, "evidence", "verdict.json"));
const p0Run1 = readJson(join(P0_DIR, "evidence", "run1.json"));
const p0Verification = readJson(join(P0_DIR, "evidence", "verification.json"));
const p0FilesMatchHead = ["verdict.json", "run1.json", "run2.json", "versions.json", "verification.json"].every(
  (name) =>
    sha256File(join(P0_DIR, "evidence", name)) ===
    sha256GitBlob("HEAD", `validation/cm01/p0-cancellation/evidence/${name}`),
);
check(
  "F1-P0-EVIDENCE",
  p0Verdict.verdict === "FAIL" &&
    p0Verification.verification_status === "VERIFIED" &&
    p0Run1.fault?.classification?.pending_immediately_after_timeout === true &&
    p0Run1.fault?.classification?.pending_after_observation_window === true &&
    p0Run1.fault?.classification?.cancellation_notifications_sent === 0 &&
    p0Run1.fault?.classification?.late_response_settled_request === true &&
    p0Verdict.verdict === "FAIL" &&
    p0FilesMatchHead,
  {
    p0_verdict: p0Verdict.verdict,
    p0_verification: p0Verification.verification_status,
    p0_classification: p0Run1.fault?.classification,
    files_match_head: p0FilesMatchHead,
  },
);

const s1aFiles = gitLines(["ls-files", "validation/cm01/s1a-local"]).sort();
const s1aHashes = Object.fromEntries(
  s1aFiles.map((file) => [file, sha256File(join(ROOT, file))]),
);
const s1aDigest = sha256Text(JSON.stringify(s1aHashes));
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
const m4Guard = checkM4Protection({ cwd: ROOT, baseSha: DECLARED_BASELINE });
check(
  "F1-PRESERVATION",
  s1aDigest === "cc7f884866e6e94255b100de57b82eec4a51660aadaf51c6464198131030af57" &&
    frozenStatus.length === 0 &&
    frozenDiff.length === 0 &&
    sha256File(join(S1A_DIR, "e0", "quickjs-executor.mjs")) ===
      "4b960124e9218ed124ed34e3b3595b648477b9dab6540c4ce1609d2efaf31313" &&
    m4Guard.pass === true,
  { s1a_digest: s1aDigest, frozenStatus, frozenDiff, m4Guard: m4Guard.pass },
);

const canonicalMemoryPath = ".mneme/project_memory.json";
const canonicalMemoryHash = sha256File(join(ROOT, canonicalMemoryPath));
const canonicalMemoryHead = sha256GitBlob("HEAD", canonicalMemoryPath);
const productionDiff = gitLines(["diff", "--name-only", "HEAD", "--", "mneme"]);
check(
  "F1-CANONICAL-MEMORY-PRODUCTION",
  canonicalMemoryHash === canonicalMemoryHead && productionDiff.length === 0,
  { canonical_memory_match: canonicalMemoryHash === canonicalMemoryHead, productionDiff },
);

const m4Paths = [
  "benchmarks/adr034_m4",
  "tests/adr034_m4_",
  "tests/test_adr034_m4_",
  "scripts/run_test_battery.py",
  "docs/validation/adr-034-m4-",
  "docs/plans",
];
const m4Diff = gitLines(["diff", "--name-only", "HEAD"]);
const m4Violations = m4Diff.filter((path) =>
  m4Paths.some((prefix) => path.startsWith(prefix)),
);
check(
  "F1-M4-UNTOUCHED",
  m4Guard.pass === true && m4Violations.length === 0,
  { guard: m4Guard.pass, violations: m4Guard.violations, m4Diff: m4Violations },
);

const status = gitLines(["status", "--porcelain", "--untracked-files=all"]);
const nonF1Status = status.filter(
  (line) =>
    !line.includes("validation/cm01/p0-f1/") &&
    !line.includes(".mneme/task_context.json"),
);
check(
  "F1-ONLY-P0F1",
  nonF1Status.length === 0 &&
    status.every(
      (line) =>
        line.includes("validation/cm01/p0-f1/") ||
        line.includes(".mneme/task_context.json"),
    ),
  { status, nonF1Status },
);

// ---------------------------------------------------------------------------
// Read-only verification of the F1 evidence is complete. Reproduction is
// performed in a fresh detached worktree; the task worktree is not modified.
// ---------------------------------------------------------------------------
let reproduction = { performed: false, reason: "not requested" };
const reproduce = process.argv.includes("--reproduce");

if (reproduce) {
  const tempRoot = join(
    process.env.TEMP || process.env.TMP || tmpdir(),
    "opencode",
    `f1-verify-${Date.now()}`,
  );
  const tempP0 = join(tempRoot, "validation", "cm01", "p0-f1");
  reproduction = {
    performed: true,
    temp_worktree: tempRoot,
    head,
    steps: [],
    checks: [],
  };
  try {
    mkdirSync(dirname(tempRoot), { recursive: true });
    execFileSync("git", ["worktree", "add", "--detach", tempRoot, head], {
      cwd: ROOT,
      stdio: "pipe",
      timeout: 120000,
    });
    reproduction.steps.push({ step: "worktree_add", ok: true });
    mkdirSync(tempP0, { recursive: true });
    for (const file of SOURCE_FILES) {
      cpSync(join(F1_DIR, file), join(tempP0, file));
    }
    reproduction.steps.push({ step: "copy_sources", ok: true, files: SOURCE_FILES });
    execFileSync(process.platform === "win32" ? "npm.cmd" : "npm", ["ci", "--ignore-scripts", "--no-audit", "--no-fund"], {
      cwd: tempP0,
      stdio: "pipe",
      timeout: 300000,
      shell: process.platform === "win32",
    });
    reproduction.steps.push({ step: "npm_ci", ok: true });
    const result = spawnSync(process.execPath, ["run-f1.mjs"], {
      cwd: tempP0,
      encoding: "utf8",
      timeout: 600000,
      env: { ...process.env },
    });
    reproduction.exit_code = result.status;
    reproduction.stdout_tail = (result.stdout ?? "").split(/\r?\n/).filter(Boolean).slice(-4);
    reproduction.stderr_tail = (result.stderr ?? "").split(/\r?\n/).filter(Boolean).slice(-6);
    reproduction.steps.push({ step: "run", ok: result.status === 0, status: result.status });
    const tempVerdict = readJson(join(tempP0, "evidence", "verdict.json"));
    const tempRun1 = readJson(join(tempP0, "evidence", "run1.json"));
    const tempRun2 = readJson(join(tempP0, "evidence", "run2.json"));
    const tempLatency = latencySamples(tempRun1).concat(latencySamples(tempRun2));
    const canonicalForRepro = normalized(runFiles[0], { includeBoundaryExact: false });
    const canonicalForRepro2 = normalized(runFiles[1], { includeBoundaryExact: false });
    const tempForRepro = normalized(tempRun1, { includeBoundaryExact: false });
    const tempForRepro2 = normalized(tempRun2, { includeBoundaryExact: false });
    const sourceHashKeys = ["f1_executor", "f1_adapter", "f1_relay", "f1_synthetic_server", "f1_runner", "package_lock"];
    const sourceHashesMatch = sourceHashKeys.every(
      (key) => tempVerdict.identities[key]?.sha256 === verdict.identities[key]?.sha256,
    );
    reproduction.verdict = tempVerdict.verdict;
    reproduction.repeatable = tempVerdict.repeatable;
    reproduction.checks.push({
      id: "REPRO-VERDICT",
      pass:
        tempVerdict.verdict === "PASS" &&
        tempRun1.verdict === "PASS" &&
        tempRun2.verdict === "PASS" &&
        tempVerdict.repeatable === true &&
        tempVerdict.p0_comparison_pass === true &&
        tempVerdict.preservation?.pass === true &&
        (tempVerdict.unhandled ?? []).length === 0,
      detail: {
        verdict: tempVerdict.verdict,
        runs: [tempRun1.verdict, tempRun2.verdict],
        repeatable: tempVerdict.repeatable,
        p0_comparison: tempVerdict.p0_comparison_pass,
        preservation: tempVerdict.preservation?.pass,
        unhandled: tempVerdict.unhandled,
      },
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
      detail: {
        temp: tempRun1.checks?.map((entry) => ({ id: entry.id, pass: entry.pass })),
        canonical: runFiles[0].checks?.map((entry) => ({ id: entry.id, pass: entry.pass })),
      },
    });
    reproduction.checks.push({
      id: "REPRO-NORMALIZED-OUTCOMES",
      pass:
        equal(canonicalForRepro, tempForRepro) &&
        equal(canonicalForRepro2, tempForRepro2),
      detail: { canonical: canonicalForRepro, reproduced: tempForRepro },
    });
    reproduction.checks.push({
      id: "REPRO-SOURCE-HASHES",
      pass: sourceHashesMatch,
      detail: Object.fromEntries(
        sourceHashKeys.map((key) => [
          key,
          {
            canonical: verdict.identities[key]?.sha256 ?? null,
            reproduced: tempVerdict.identities[key]?.sha256 ?? null,
          },
        ]),
      ),
    });
    reproduction.checks.push({
      id: "REPRO-LATENCY-BOUND",
      pass:
        tempLatency.length === 16 &&
        tempLatency.every(
          (sample) => sample.abortToSettlementMs >= 0 && sample.abortToSettlementMs <= 50,
        ),
      detail: { samples: tempLatency.length, max_ms: summary(tempLatency).max_ms },
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
  !reproduce ||
  (reproduction.checks.length > 0 && reproduction.checks.every((entry) => entry.pass));

const manifestAfter = evidenceManifest();
const manifestUnchanged = manifestBefore.digest === manifestAfter.digest;
check("F1-EVIDENCE-UNCHANGED", manifestUnchanged, {
  before: manifestBefore.digest,
  after: manifestAfter.digest,
});

const allStaticPass = checks.every((entry) => entry.pass);
const verificationStatus =
  allStaticPass && reproductionPass ? "VERIFIED" : "BLOCKED";
const errors = [
  ...checks.filter((entry) => !entry.pass).map((entry) => `${entry.id}: ${JSON.stringify(entry.detail)}`),
  ...(reproduction.checks ?? []).filter((entry) => !entry.pass).map((entry) => `${entry.id}: ${JSON.stringify(entry.detail)}`),
];

const record = {
  schema: "mneme.cm01.p0-f1.verification/v1",
  generated_at: new Date().toISOString(),
  task: "CM-01-P0-01-F1 evidence verification",
  verification_status: verificationStatus,
  read_only: true,
  original_verdict: verdict.verdict,
  original_verdict_changed: false,
  head,
  baseline: DECLARED_BASELINE,
  canonical_evidence: {
    files: Object.keys(manifestBefore.files),
    digest_before: manifestBefore.digest,
    digest_after: manifestAfter.digest,
    unchanged: manifestUnchanged,
  },
  checks,
  reproduction,
  summary: {
    total_checks: checks.length,
    failed_checks: checks.filter((entry) => !entry.pass).map((entry) => entry.id),
    reproduced: reproduce ? reproductionPass : null,
    verification_status: verificationStatus,
  },
  errors,
  latency: {
    grace_ms: verdict.host_cancellation_grace_ms,
    provisional_ms: verdict.grace_decision?.provisional_ms,
    final_ms: verdict.grace_decision?.final_ms,
    recorded: {
      samples: recordedLatency.samples,
      max_ms: recordedLatency.max_ms,
      min_ms: recordedLatency.min_ms,
      mean_ms: recordedLatency.mean_ms,
    },
    recomputed: recomputedLatency,
    samples: recomputedSamples,
    note:
      "Latency is environment-specific. The 50 ms bound is not generalized beyond this tested environment.",
  },
  preservation: {
    s1a_digest: s1aDigest,
    frozen_status: frozenStatus,
    frozen_diff: frozenDiff,
    m4_guard_pass: m4Guard.pass,
    canonical_memory_matches_head: canonicalMemoryHash === canonicalMemoryHead,
    production_diff: productionDiff,
    status: status,
  },
};

mkdirSync(EVIDENCE, { recursive: true });
writeFileSync(join(EVIDENCE, "verification.json"), `${JSON.stringify(record, null, 2)}\n`);
process.stdout.write(
  `${JSON.stringify({
    verification_status: verificationStatus,
    original_verdict: record.original_verdict,
    total_checks: record.summary.total_checks,
    failed_checks: record.summary.failed_checks,
    reproduced: record.summary.reproduced,
    errors: record.errors,
  })}\n`,
);
process.exit(verificationStatus === "VERIFIED" ? 0 : 1);


