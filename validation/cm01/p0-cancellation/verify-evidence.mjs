import { execFileSync, execSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { checkM4Protection, M4_PATTERNS } from "../s1a-local/m4-guard.mjs";

const P0_DIR = dirname(fileURLToPath(import.meta.url));
const CM01_DIR = dirname(P0_DIR);
const ROOT = resolve(P0_DIR, "../../..");
const S1A_DIR = join(CM01_DIR, "s1a-local");
const EVIDENCE = join(P0_DIR, "evidence");
const RAW = join(EVIDENCE, "raw");
const EMPTY_CWD = join(S1A_DIR, "m1", "empty-cwd");
const DECLARED_BASELINE = "ddeb85eec8f7734edde1c921250592d51afedbee";
const CANONICAL_FILES = ["verdict.json", "run1.json", "run2.json", "versions.json"];
const REPO_SOURCE_FILES = [
  "run-cancellation.mjs",
  "relay.mjs",
  "package.json",
  "package-lock.json",
  ".gitignore",
  ".gitattributes",
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

function readJsonl(path) {
  return readFileSync(path, "utf8")
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function gitLines(args) {
  const text = execFileSync("git", args, { cwd: ROOT, encoding: "utf8" }).trim();
  return text ? text.split(/\r?\n/) : [];
}

function sha256GitBlob(ref, path) {
  const buffer = execFileSync("git", ["show", `${ref}:${path}`], {
    cwd: ROOT,
    maxBuffer: 32 * 1024 * 1024,
  });
  return createHash("sha256").update(buffer).digest("hex");
}

function one(events, type) {
  return events.filter((event) => event.type === type);
}

function indices(events, types) {
  return types.map((type) => events.findIndex((event) => event.type === type));
}

function increasing(values) {
  return values.every((value, index) => value >= 0 && (index === 0 || value > values[index - 1]));
}

function nondecreasing(values) {
  return values.every((value, index) => value >= 0 && (index === 0 || value >= values[index - 1]));
}

function normalizedFault(run) {
  const fault = run.fault;
  return {
    verdict: fault?.verdict ?? null,
    genuine: fault?.classification?.genuine_upstream_request ?? null,
    timeout_error_returned: fault?.classification?.timeout_error_returned ?? null,
    pending_at_timeout: fault?.classification?.pending_immediately_after_timeout ?? null,
    pending_after_window: fault?.classification?.pending_after_observation_window ?? null,
    observation_end_reason: fault?.classification?.observation_end_reason ?? null,
    cancellation_notifications_sent: fault?.classification?.cancellation_notifications_sent ?? null,
    late_response_settled_request: fault?.classification?.late_response_settled_request ?? null,
    request_id_is_number: typeof fault?.client_side?.request?.id === "number",
    adapter_call_count: fault?.adapter_calls?.length ?? null,
  };
}

function classify(fault) {
  const genuine =
    fault.server_side.relay_events.target_forwarded &&
    fault.server_side.relay_events.upstream_response_received;
  const timeoutReturned =
    !fault.execution.result &&
    Boolean(fault.execution.error) &&
    fault.execution.stats?.timedOut === true &&
    /execution exceeded/i.test(fault.execution.error ?? "");
  const pendingAtTimeout = fault.client_side.pending_after_timeout_return;
  const pendingAtWindowEnd = fault.observation.pending_after_window;
  const lateSettled =
    fault.late_completion.settled && fault.late_completion.outcome === "fulfilled";
  return { genuine, timeoutReturned, pendingAtTimeout, pendingAtWindowEnd, lateSettled };
}

const canonicalHashesBefore = Object.fromEntries(
  CANONICAL_FILES.map((name) => [name, sha256File(join(EVIDENCE, name))]),
);
const verdict = readJson(join(EVIDENCE, "verdict.json"));
const runFiles = [readJson(join(EVIDENCE, "run1.json")), readJson(join(EVIDENCE, "run2.json"))];
const versionInfo = readJson(join(EVIDENCE, "versions.json"));
check(
  "ORIGINAL-CLASSIFICATION",
  verdict.verdict === "FAIL" && /still pending/i.test(verdict.reason) && /late response/i.test(verdict.reason),
  { original_verdict: verdict.verdict, reason: verdict.reason },
);
check(
  "ORIGINAL-RUNS-PRESENT",
  runFiles.length === 2 &&
    runFiles.every((run) => run.verdict === "FAIL" && run.fault?.classification),
  runFiles.map((run) => ({ run: run.run, verdict: run.verdict })),
);

for (const run of runFiles) {
  const label = run.run.toUpperCase();
  const requestId = run.fault?.client_side?.request?.id;
  const relayEvents = readJsonl(join(RAW, `${run.run}-fault-relay.jsonl`));
  const childEvents = readJsonl(join(RAW, `${run.run}-fault-child-events.jsonl`));
  const harnessEvents = readJsonl(join(RAW, `${run.run}-harness-events.jsonl`));
  const controlRelayEvents = readJsonl(join(RAW, `${run.run}-control-relay-relay.jsonl`));
  const controlChildEvents = readJsonl(join(RAW, `${run.run}-control-relay-child-events.jsonl`));
  const faultHarness = harnessEvents.filter((event) => event.phase === "fault");
  const controlHarness = harnessEvents.filter((event) => event.phase === "control-relay");

  const controlDirect = run.control_direct;
  check(
    `${label}-CONTROL-DIRECT`,
    controlDirect.ok === true &&
      controlDirect.canonical_get_ok === true &&
      controlDirect.outcome?.result?.canonical_decision?.decision_id === "ADR-9901" &&
      controlDirect.outcome?.error === null &&
      controlDirect.call?.outcome === "fulfilled" &&
      typeof controlDirect.call?.request_id === "number" &&
      controlDirect.cleanup?.errors?.length === 0 &&
      controlDirect.cleanup?.server_exit_observed === true &&
      controlDirect.cleanup?.server_alive_after === false,
    {
      ok: controlDirect.ok,
      canonical: controlDirect.canonical_get_ok,
      request_id: controlDirect.call?.request_id ?? null,
      cleanup: controlDirect.cleanup ?? null,
    },
  );

  const controlRelay = run.control_relay;
  check(
    `${label}-CONTROL-RELAY`,
    controlRelay.ok === true &&
      controlRelay.canonical_get_ok === true &&
      controlRelay.call?.outcome === "fulfilled" &&
      controlRelay.relay_events?.target_seen === true &&
      controlRelay.relay_events?.target_forwarded === true &&
      controlRelay.relay_events?.upstream_response_received === true &&
      controlRelay.relay_events?.response_forwarded === true &&
      controlRelay.relay_events?.response_withheld === false &&
      controlRelay.cleanup?.errors?.length === 0 &&
      controlRelay.cleanup?.relay_alive_after === false &&
      controlRelay.cleanup?.upstream_alive_after === false,
    {
      ok: controlRelay.ok,
      canonical: controlRelay.canonical_get_ok,
      relay_events: controlRelay.relay_events,
      cleanup: controlRelay.cleanup ?? null,
    },
  );

  const controlSeen = one(controlRelayEvents, "target_request_seen");
  const controlForwarded = one(controlRelayEvents, "target_request_forwarded");
  const controlReceived = one(controlRelayEvents, "upstream_response_received");
  const controlDelivered = controlRelayEvents.filter(
    (event) =>
      event.type === "upstream_message_forwarded_downstream" &&
      event.requestId === controlSeen[0]?.requestId,
  );
  const controlExit = one(controlRelayEvents, "child_exit");
  check(
    `${label}-CONTROL-RELAY-RAW`,
    controlSeen.length === 1 &&
      controlForwarded.length === 1 &&
      controlReceived.length === 1 &&
      controlDelivered.length === 1 &&
      one(controlRelayEvents, "response_withheld").length === 0 &&
      one(controlRelayEvents, "cancel_from_client").length === 0 &&
      controlExit.length === 1 &&
      controlExit[0].code === 0 &&
      nondecreasing(
        indices(controlRelayEvents, [
          "target_request_seen",
          "target_request_forwarded",
          "upstream_response_received",
        ]),
      ),
    {
      seen: controlSeen.length,
      forwarded: controlForwarded.length,
      received: controlReceived.length,
      delivered: controlDelivered.length,
      withheld: one(controlRelayEvents, "response_withheld").length,
      child_exit: controlExit[0] ?? null,
    },
  );

  const controlToolsCall = controlChildEvents.find(
    (event) =>
      event.type === "child_stdin_line" &&
      JSON.parse(event.line)?.method === "tools/call" &&
      JSON.parse(event.line)?.params?.name === "decision.get",
  );
  const controlCallId = controlToolsCall ? JSON.parse(controlToolsCall.line).id : null;
  const controlResponses = controlChildEvents.filter(
    (event) =>
      event.type === "child_stdout_line" &&
      JSON.parse(event.line)?.id === controlCallId &&
      JSON.parse(event.line)?.result !== undefined,
  );
  const controlChildExit = one(controlChildEvents, "child_exit");
  check(
    `${label}-CONTROL-CHILD-RAW`,
    Boolean(controlToolsCall) &&
      controlResponses.length === 1 &&
      controlChildExit.length === 1 &&
      controlChildExit[0].code === 0,
    { call_id: controlCallId, responses: controlResponses.length, exit: controlChildExit[0] ?? null },
  );

  const fault = run.fault;
  check(
    `${label}-FAULT-WITHHELD`,
    fault.withheld_observed === true &&
      fault.withheld_event?.type === "response_withheld" &&
      fault.withheld_event?.requestId === requestId,
    { withheld: fault.withheld_observed, event: fault.withheld_event ?? null, request_id: requestId },
  );

  check(
    `${label}-FAULT-TIMEOUT`,
    fault.execution?.result === null &&
      /execution exceeded 1500ms/.test(fault.execution?.error ?? "") &&
      fault.execution?.stats?.timedOut === true &&
      fault.execution?.stats?.pendingAtEnd === 0 &&
      fault.execution?.stats?.cleanupErrors?.length === 0,
    {
      error: fault.execution?.error ?? null,
      stats: fault.execution?.stats ?? null,
    },
  );

  check(
    `${label}-FAULT-PENDING`,
    fault.client_side?.pending_after_timeout_return === true &&
      fault.client_side?.at_timeout_return?.pending === true &&
      fault.observation?.pending_after_window === true &&
      fault.observation?.reason === "window_elapsed" &&
      fault.observation?.window_ms === 1500,
    {
      at_timeout: fault.client_side?.at_timeout_return ?? null,
      observation: fault.observation ?? null,
    },
  );

  check(
    `${label}-FAULT-NO-CANCELLATION`,
    fault.classification?.cancellation_notifications_sent === 0 &&
      fault.server_side?.cancellation_events_forwarded?.length === 0 &&
      one(relayEvents, "cancel_from_client").length === 0 &&
      !faultHarness.some(
        (event) =>
          event.type === "transport_send" &&
          event.message?.method === "notifications/cancelled",
      ),
    {
      sent: fault.classification?.cancellation_notifications_sent ?? null,
      relay_observed: fault.server_side?.cancellation_events_forwarded?.length ?? null,
    },
  );

  check(
    `${label}-FAULT-LATE-SETTLEMENT`,
    fault.late_completion?.settled === true &&
      fault.late_completion?.outcome === "fulfilled" &&
      fault.late_completion?.delivered_response_observed === true &&
      fault.late_completion?.executor_resolved_calls_delta >= 1 &&
      fault.classification?.late_response_settled_request === true &&
      fault.classification?.required_harness_release_to_settle === true,
    {
      late: fault.late_completion ?? null,
      classification: fault.classification ?? null,
    },
  );

  check(
    `${label}-FAULT-CLEANUP`,
    fault.process_cleanup_ok === true &&
      fault.cleanup?.errors?.length === 0 &&
      fault.cleanup?.child_exit_observed === true &&
      fault.cleanup?.child_exit_event?.code === 0 &&
      fault.cleanup?.relay_alive_after === false &&
      fault.cleanup?.upstream_alive_after === false &&
      fault.cleanup?.relay_exit_observed === true &&
      fault.cleanup?.upstream_exit_observed === true,
    fault.cleanup ?? null,
  );

  const relaySeen = one(relayEvents, "target_request_seen");
  const relayForwarded = one(relayEvents, "target_request_forwarded");
  const relayReceived = one(relayEvents, "upstream_response_received");
  const relayWithheld = one(relayEvents, "response_withheld");
  const relayStatus = one(relayEvents, "status");
  const relayReleased = one(relayEvents, "response_released_downstream");
  const relayExit = one(relayEvents, "child_exit");
  const relayOrder = indices(relayEvents, [
    "target_request_seen",
    "target_request_forwarded",
    "upstream_response_received",
    "response_withheld",
    "status",
    "response_released_downstream",
    "child_exit",
  ]);
  const timeoutAt = Date.parse(fault.execution.finished_at);
  const withheldAt = Date.parse(relayWithheld[0]?.ts ?? 0);
  const releasedAt = Date.parse(relayReleased[0]?.ts ?? 0);
  const windowEnd = timeoutAt + fault.observation.window_ms - 100;
  check(
    `${label}-FAULT-RELAY-RAW`,
    relaySeen.length === 1 &&
      relayForwarded.length === 1 &&
      relayReceived.length === 1 &&
      relayWithheld.length === 1 &&
      relayStatus.length === 1 &&
      relayReleased.length === 1 &&
      relayExit.length === 1 &&
      relaySeen[0].requestId === requestId &&
      relayForwarded[0].requestId === requestId &&
      relayReceived[0].requestId === requestId &&
      relayWithheld[0].requestId === requestId &&
      relayReleased[0].requestId === requestId &&
      relayStatus[0].held_request_id === requestId &&
      relayStatus[0].child_alive === true &&
      relayStatus[0].cancellation_events?.length === 0 &&
      one(relayEvents, "cancel_from_client").length === 0 &&
      relayExit[0].code === 0 &&
      increasing(relayOrder) &&
      withheldAt < timeoutAt &&
      releasedAt > windowEnd,
    {
      counts: {
        seen: relaySeen.length,
        forwarded: relayForwarded.length,
        received: relayReceived.length,
        withheld: relayWithheld.length,
        status: relayStatus.length,
        released: relayReleased.length,
        exit: relayExit.length,
      },
      order: relayOrder,
      withheld_before_timeout: withheldAt < timeoutAt,
      released_after_window: releasedAt > windowEnd,
      status: relayStatus[0] ?? null,
      exit: relayExit[0] ?? null,
    },
  );

  const faultToolsCall = childEvents.find(
    (event) =>
      event.type === "child_stdin_line" &&
      JSON.parse(event.line)?.method === "tools/call" &&
      JSON.parse(event.line)?.id === requestId,
  );
  const faultResponses = childEvents.filter(
    (event) =>
      event.type === "child_stdout_line" &&
      JSON.parse(event.line)?.id === requestId &&
      JSON.parse(event.line)?.result !== undefined,
  );
  const faultChildExit = one(childEvents, "child_exit");
  check(
    `${label}-FAULT-CHILD-RAW`,
    Boolean(faultToolsCall) &&
      faultResponses.length === 1 &&
      faultChildExit.length === 1 &&
      faultChildExit[0].code === 0 &&
      Date.parse(faultResponses[0].ts) <= withheldAt,
    {
      call_id: requestId,
      response_lines: faultResponses.length,
      response_ts: faultResponses[0]?.ts ?? null,
      withheld_ts: relayWithheld[0]?.ts ?? null,
      exit: faultChildExit[0] ?? null,
    },
  );

  const faultSends = faultHarness.filter((event) => event.type === "transport_send");
  const faultReceives = faultHarness.filter((event) => event.type === "transport_receive");
  const callSends = faultSends.filter(
    (event) => event.message?.method === "tools/call" && event.message?.id === requestId,
  );
  const responseReceives = faultReceives.filter(
    (event) =>
      event.message?.id === requestId &&
      (event.message?.result !== undefined || event.message?.error !== undefined),
  );
  const executorCleanup = faultHarness.filter((event) => event.type === "executor_cleanup");
  const releasedTs = Date.parse(relayReleased[0]?.ts ?? 0);
  check(
    `${label}-FAULT-HARNESS-RAW`,
    callSends.length === 1 &&
      responseReceives.length === 1 &&
      Date.parse(responseReceives[0].ts) >= releasedTs &&
      executorCleanup.length === 1 &&
      executorCleanup[0].client_call?.pending === true &&
      executorCleanup[0].client_call?.request_id === requestId &&
      Date.parse(executorCleanup[0].ts) <= timeoutAt &&
      !faultSends.some((event) => event.message?.method === "notifications/cancelled") &&
      !faultReceives.some((event) => event.message?.method === "notifications/cancelled"),
    {
      call_sends: callSends.length,
      response_receives: responseReceives.length,
      response_ts: responseReceives[0]?.ts ?? null,
      release_ts: relayReleased[0]?.ts ?? null,
      executor_cleanup: executorCleanup[0] ?? null,
      timeout_ts: fault.execution.finished_at,
    },
  );

  const derived = classify(fault);
  check(
    `${label}-CLASSIFICATION`,
    derived.genuine === true &&
      derived.timeoutReturned === true &&
      derived.pendingAtTimeout === true &&
      derived.pendingAtWindowEnd === true &&
      derived.lateSettled === true &&
      fault.verdict === "FAIL",
    { derived, verdict: fault.verdict, reason: fault.reason },
  );

  check(
    `${label}-RAW-FILES-PRESENT`,
    ["fault-relay.jsonl", "fault-child-events.jsonl", "harness-events.jsonl", "control-relay-relay.jsonl", "control-relay-child-events.jsonl"].every(
      (suffix) => existsSync(join(RAW, `${run.run}-${suffix}`)),
    ),
    null,
  );
}

const derivedRepeatable =
  JSON.stringify(normalizedFault(runFiles[0])) === JSON.stringify(normalizedFault(runFiles[1]));
check(`${"VERDICT"}-REPEATABLE`, verdict.repeatable === true && derivedRepeatable, {
  recorded: verdict.repeatable,
  derived: derivedRepeatable,
});

const derivedAcceptance = {
  genuine_request_reached_server: runFiles.every(
    (run) => run.fault.classification?.genuine_upstream_request === true,
  ),
  code_mode_returned_timeout_not_success: runFiles.every(
    (run) => run.fault.classification?.timeout_error_returned === true,
  ),
  integration_cancelled_or_terminated_within_window: runFiles.every(
    (run) =>
      run.fault.classification?.pending_after_observation_window === false ||
      run.fault.classification?.observation_end_reason !== "window_elapsed",
  ),
  no_request_pending_before_harness_cleanup: runFiles.every(
    (run) => run.fault.classification?.pending_after_observation_window === false,
  ),
  late_response_cannot_settle_request: runFiles.every(
    (run) => run.fault.classification?.late_response_settled_request === false,
  ),
  reproducible_in_two_runs: derivedRepeatable,
  no_protected_artifact_changed: verdict.no_mutation?.pass === true,
};
check(
  "VERDICT-ACCEPTANCE",
  JSON.stringify(derivedAcceptance) === JSON.stringify(verdict.acceptance_criteria),
  { recorded: verdict.acceptance_criteria, derived: derivedAcceptance },
);

const derivedFailure = {
  request_pending_after_executor_timeout: runFiles.some(
    (run) => run.fault.classification?.pending_immediately_after_timeout === true,
  ),
  request_pending_after_bounded_window: runFiles.some(
    (run) => run.fault.classification?.pending_after_observation_window === true,
  ),
  late_response_settled_request: runFiles.some(
    (run) => run.fault.classification?.late_response_settled_request === true,
  ),
  harness_release_required_to_settle: runFiles.some(
    (run) => run.fault.classification?.required_harness_release_to_settle === true,
  ),
  cancellation_notification_emitted: runFiles.some(
    (run) => (run.fault.classification?.cancellation_notifications_sent ?? 0) > 0,
  ),
};
check(
  "VERDICT-FAILURE-CONDITIONS",
  JSON.stringify(derivedFailure) === JSON.stringify(verdict.failure_conditions_observed),
  { recorded: verdict.failure_conditions_observed, derived: derivedFailure },
);

const recordedRunMap = Object.fromEntries(verdict.runs.map((run) => [run.run, run]));
const aggregationMatches = runFiles.every((run) => {
  const recorded = recordedRunMap[run.run];
  return (
    recorded &&
    recorded.verdict === run.verdict &&
    recorded.controls_ok === run.controls_ok &&
    recorded.pending_after_timeout === run.fault.classification.pending_immediately_after_timeout &&
    recorded.pending_after_window === run.fault.classification.pending_after_observation_window &&
    recorded.cancellation_notifications_sent ===
      run.fault.classification.cancellation_notifications_sent &&
    recorded.late_response_settled_request ===
      run.fault.classification.late_response_settled_request &&
    recorded.process_cleanup_ok === run.fault.process_cleanup_ok
  );
});
check("VERDICT-RUN-AGGREGATION", aggregationMatches, { recorded: verdict.runs });

const headSha = execFileSync("git", ["rev-parse", "HEAD"], { cwd: ROOT, encoding: "utf8" }).trim();
const codeUnderTestChanged = gitLines([
  "diff",
  "--name-only",
  `${DECLARED_BASELINE}..${headSha}`,
  "--",
  "validation/cm01",
  "mneme",
]);
const driftPaths = gitLines(["diff", "--name-only", `${DECLARED_BASELINE}..${headSha}`]);
check(
  "BASELINE-PRESERVATION",
  verdict.environment.declared_baseline === DECLARED_BASELINE &&
    verdict.environment.head === headSha &&
    verdict.environment.baseline_drift?.code_under_test_unchanged_since_declared_baseline === true &&
    codeUnderTestChanged.length === 0 &&
    driftPaths.every((path) => !path.startsWith("validation/cm01/") && !path.startsWith("mneme/")),
  {
    declared_baseline: verdict.environment.declared_baseline,
    head: headSha,
    code_under_test_changed: codeUnderTestChanged,
    drift_paths: driftPaths,
  },
);

const identityChecks = {};
for (const [key, entry] of Object.entries(verdict.identities)) {
  const current = sha256File(entry.path);
  identityChecks[key] = current === entry.sha256;
}
check("IDENTITY-HASHES", Object.values(identityChecks).every(Boolean), identityChecks);

const baselineIdentityChecks = {};
for (const [key, entry] of Object.entries(verdict.no_mutation.baseline_identity)) {
  const path = {
    executor: "validation/cm01/s1a-local/e0/quickjs-executor.mjs",
    fixture: "validation/cm01/s1a-local/m1/fixture/canonical/project_memory.json",
    pre_migration: "validation/cm01/s1a-local/m1/fixture/pre_migration.json",
    m4_fixture: "validation/cm01/s1a-local/m4/fixture/canonical/project_memory.json",
    m4_guard: "validation/cm01/s1a-local/m4-guard.mjs",
  }[key];
  const baseline = sha256GitBlob(DECLARED_BASELINE, path);
  baselineIdentityChecks[key] =
    baseline === entry.baseline_sha256 &&
    sha256File(join(ROOT, path)) === entry.current_sha256 &&
    entry.matches_baseline === true;
}
check(
  "BASELINE-BLOB-HASHES",
  Object.values(baselineIdentityChecks).every(Boolean),
  baselineIdentityChecks,
);

const s1aFiles = gitLines(["ls-files", "validation/cm01/s1a-local"]).sort();
const s1aHashes = Object.fromEntries(
  s1aFiles.map((file) => [file, sha256File(join(ROOT, file))]),
);
const s1aDigest = sha256Text(JSON.stringify(s1aHashes));
const s1aStatus = execFileSync("git", ["status", "--porcelain", "--", "validation/cm01/s1a-local"], {
  cwd: ROOT,
  encoding: "utf8",
}).trim();
check(
  "S1A-EVIDENCE-PRESERVATION",
  s1aDigest === verdict.no_mutation.s1a_evidence_before &&
    s1aDigest === verdict.no_mutation.s1a_evidence_after &&
    s1aStatus === "" &&
    verdict.no_mutation.s1a_git_status_before === "" &&
    verdict.no_mutation.s1a_git_status_after === "",
  { digest: s1aDigest, git_status: s1aStatus },
);

const m4Guard = checkM4Protection({ cwd: ROOT, baseSha: headSha });
check(
  "M4-WORKTREE-PRESERVATION",
  m4Guard.pass === true &&
    verdict.m4_worktree_guard?.pass === true &&
    m4Guard.violations.length === 0,
  { pass: m4Guard.pass, violations: m4Guard.violations },
);

const fixturesUnchanged =
  sha256File(verdict.identities.fixture.path) === verdict.identities.fixture.sha256 &&
  sha256File(verdict.identities.pre_migration.path) === verdict.identities.pre_migration.sha256 &&
  sha256File(verdict.identities.m4_fixture.path) === verdict.identities.m4_fixture.sha256;
check("FIXTURES-UNCHANGED", fixturesUnchanged, verdict.identities);

const currentVersions = {
  node: process.version,
  npm: execSync("npm --version", { encoding: "utf8" }).trim(),
  python: execFileSync(
    process.env.CM01_PYTHON || "python",
    ["-c", "import sys; print(sys.version.split()[0])"],
    { encoding: "utf8" },
  ).trim(),
  mneme: execFileSync(
    process.env.CM01_PYTHON || "python",
    ["-c", "import mneme; print(getattr(mneme, '__version__', 'unknown'))"],
    { cwd: EMPTY_CWD, env: { ...process.env, PYTHONPATH: ROOT }, encoding: "utf8" },
  ).trim(),
  mcp: execFileSync(
    process.env.CM01_PYTHON || "python",
    ["-c", "from importlib.metadata import version; print(version('mcp'))"],
    { cwd: EMPTY_CWD, env: { ...process.env, PYTHONPATH: ROOT }, encoding: "utf8" },
  ).trim(),
};
const pkg = readJson(join(P0_DIR, "package.json"));
const pinnedVersions = {
  codemode: pkg.dependencies["@cloudflare/codemode"],
  sdk: pkg.dependencies["@modelcontextprotocol/sdk"],
  ajv: pkg.dependencies.ajv,
  quickjs: pkg.dependencies["quickjs-emscripten"],
  zod: pkg.dependencies.zod,
};
const versionsMatch =
  JSON.stringify(verdict.environment) === JSON.stringify(versionInfo) &&
  currentVersions.node === verdict.environment.versions.node &&
  currentVersions.npm === verdict.environment.versions.npm &&
  currentVersions.python === verdict.environment.versions.python &&
  currentVersions.mneme === verdict.environment.versions.mneme &&
  currentVersions.mcp === verdict.environment.versions.mcp &&
  Object.entries(pinnedVersions).every(
    ([key, value]) => verdict.environment.versions[key] === value,
  );
check("SOURCE-VERSIONS", versionsMatch, {
  recorded: verdict.environment.versions,
  current: currentVersions,
  pinned: pinnedVersions,
});

const runnerHash = sha256File(join(P0_DIR, "run-cancellation.mjs"));
const relayHash = sha256File(join(P0_DIR, "relay.mjs"));
check(
  "HARNESS-HASHES",
  runnerHash === verdict.identities.runner.sha256 &&
    relayHash === verdict.identities.relay.sha256,
  { runner: runnerHash, relay: relayHash },
);

const canonicalFilesExist = CANONICAL_FILES.every((name) => existsSync(join(EVIDENCE, name)));
check("CANONICAL-FILES-EXIST", canonicalFilesExist, CANONICAL_FILES);

// ---------------------------------------------------------------------------
// Optional clean-checkout reproduction. The canonical evidence is read only.
// ---------------------------------------------------------------------------
let reproduction = { performed: false, reason: "not requested" };
const reproduce = process.argv.includes("--reproduce");

if (reproduce) {
  const tempRoot = join(
    process.env.TEMP || process.env.TMP || "C:\\Users\\hi\\AppData\\Local\\Temp",
    "opencode",
    `cm01-p0-verify-${Date.now()}`,
  );
  const tempP0 = join(tempRoot, "validation", "cm01", "p0-cancellation");
  const tempS1A = join(tempRoot, "validation", "cm01", "s1a-local");
  reproduction = {
    performed: true,
    temp_worktree: tempRoot,
    head: headSha,
    steps: [],
    checks: [],
  };
  try {
    mkdirSync(dirname(tempRoot), { recursive: true });
    execFileSync("git", ["worktree", "add", "--detach", tempRoot, headSha], {
      cwd: ROOT,
      stdio: "pipe",
      timeout: 120000,
    });
    reproduction.steps.push({ step: "worktree_add", ok: true });

    mkdirSync(tempP0, { recursive: true });
    for (const file of REPO_SOURCE_FILES) {
      cpSync(join(P0_DIR, file), join(tempP0, file));
    }
    reproduction.steps.push({ step: "copy_harness", ok: true, files: REPO_SOURCE_FILES });

    execSync("npm ci --ignore-scripts --no-audit --no-fund", {
      cwd: tempS1A,
      stdio: "pipe",
      timeout: 300000,
    });
    reproduction.steps.push({ step: "npm_ci_s1a", ok: true });
    execSync("npm ci --ignore-scripts --no-audit --no-fund", {
      cwd: tempP0,
      stdio: "pipe",
      timeout: 300000,
    });
    reproduction.steps.push({ step: "npm_ci_p0", ok: true });

    const result = spawnSync(process.execPath, ["run-cancellation.mjs"], {
      cwd: tempP0,
      encoding: "utf8",
      timeout: 300000,
      env: { ...process.env },
    });
    reproduction.exit_code = result.status;
    reproduction.stdout_tail = (result.stdout ?? "").split(/\r?\n/).filter(Boolean).slice(-3);
    reproduction.stderr_tail = (result.stderr ?? "").split(/\r?\n/).filter(Boolean).slice(-5);
    reproduction.steps.push({ step: "run", ok: result.status === 1, status: result.status });

    const tempVerdict = readJson(join(tempP0, "evidence", "verdict.json"));
    const tempRun1 = readJson(join(tempP0, "evidence", "run1.json"));
    const tempRun2 = readJson(join(tempP0, "evidence", "run2.json"));
    reproduction.verdict = tempVerdict.verdict;
    reproduction.reason = tempVerdict.reason;
    reproduction.signature = {
      verdict: tempVerdict.verdict,
      repeatable: tempVerdict.repeatable,
      acceptance_criteria: tempVerdict.acceptance_criteria,
      failure_conditions_observed: tempVerdict.failure_conditions_observed,
      run_signatures: [normalizedFault(tempRun1), normalizedFault(tempRun2)],
      process_cleanup: [tempRun1.fault?.process_cleanup_ok, tempRun2.fault?.process_cleanup_ok],
    };
    const canonicalSignature = {
      verdict: verdict.verdict,
      repeatable: verdict.repeatable,
      acceptance_criteria: verdict.acceptance_criteria,
      failure_conditions_observed: verdict.failure_conditions_observed,
      run_signatures: [normalizedFault(runFiles[0]), normalizedFault(runFiles[1])],
      process_cleanup: [runFiles[0].fault?.process_cleanup_ok, runFiles[1].fault?.process_cleanup_ok],
    };
    const signatureMatches =
      JSON.stringify(reproduction.signature) === JSON.stringify(canonicalSignature);
    reproduction.checks.push({
      id: "REPRO-SIGNATURE-MATCH",
      pass: signatureMatches,
      detail: { canonical: canonicalSignature, reproduced: reproduction.signature },
    });
    reproduction.checks.push({
      id: "REPRO-EXIT-CODE",
      pass: result.status === 1,
      detail: { exit_code: result.status },
    });
    reproduction.checks.push({
      id: "REPRO-NO-MUTATION",
      pass:
        tempVerdict.no_mutation?.pass === true &&
        tempRun1.fault?.process_cleanup_ok === true &&
        tempRun2.fault?.process_cleanup_ok === true,
      detail: { no_mutation: tempVerdict.no_mutation?.pass ?? null },
    });
  } catch (error) {
    reproduction.error = error?.message || String(error);
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
  !reproduce || (reproduction.checks.length > 0 && reproduction.checks.every((entry) => entry.pass));

const canonicalHashesAfter = Object.fromEntries(
  CANONICAL_FILES.map((name) => [name, sha256File(join(EVIDENCE, name))]),
);
const canonicalUnchanged = JSON.stringify(canonicalHashesBefore) === JSON.stringify(canonicalHashesAfter);
check("CANONICAL-EVIDENCE-UNCHANGED", canonicalUnchanged, {
  before: canonicalHashesBefore,
  after: canonicalHashesAfter,
});

const allChecksPass = checks.every((entry) => entry.pass) && reproductionPass;

const record = {
  schema: "mneme.cm01.p0-cancellation.verification/v1",
  generated_at: new Date().toISOString(),
  purpose:
    "Read-only verification of the recorded CM-01-P0-01 FAIL against both raw runs, relay logs, child-process logs, source versions, fixture hashes, and baseline preservation.",
  original_verdict: verdict.verdict,
  original_reason: verdict.reason,
  classification_changed: false,
  canonical_evidence: {
    files: CANONICAL_FILES,
    hashes_before: canonicalHashesBefore,
    hashes_after: canonicalHashesAfter,
    unchanged: canonicalUnchanged,
  },
  repository: {
    head: headSha,
    declared_baseline: DECLARED_BASELINE,
    code_under_test_unchanged_since_baseline: codeUnderTestChanged.length === 0,
    drift_paths: driftPaths,
    s1a_evidence_digest: s1aDigest,
    s1a_git_status: s1aStatus,
    m4_guard_pass: m4Guard.pass,
  },
  verification_status: allChecksPass ? "VERIFIED" : "FAILED",
  checks,
  reproduction,
  summary: {
    total_checks: checks.length,
    failed_checks: checks.filter((entry) => !entry.pass).map((entry) => entry.id),
    reproduced: reproduce ? reproductionPass : null,
    classification_changed: false,
  },
};

mkdirSync(EVIDENCE, { recursive: true });
writeFileSync(join(EVIDENCE, "verification.json"), `${JSON.stringify(record, null, 2)}\n`);
process.stdout.write(
  `${JSON.stringify({
    verification_status: record.verification_status,
    original_verdict: record.original_verdict,
    failed_checks: record.summary.failed_checks,
    reproduced: record.summary.reproduced,
  })}\n`,
);
process.exit(allChecksPass ? 0 : 1);
