import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { createBrowserCodeTool } from "@cloudflare/codemode/browser";
import { QuickJSExecutor } from "./quickjs-executor.mjs";
import { makeAdapter, READ_TOOLS } from "./adapter.mjs";
import * as H from "./harness.mjs";
import { checkM4Protection } from "../s1a-local/m4-guard.mjs";

const EVIDENCE = join(H.F1_DIR, "evidence");
const RAW = join(EVIDENCE, "raw");
const DECLARED_BASELINE = "adf50933d0beac255ac2a134e00ee13d40442302";
const HOST_GRACE_MS = 50;
const NORMAL_TIMEOUT_MS = 10000;
const CANCEL_TIMEOUT_MS = 300;
const RACE_TIMEOUT_MS = 300;
const OBSERVE_MS = 1000;
const LATE_WAIT_MS = 1400;
const FROZEN_PATHS = [
  "validation/cm01/s1a-local",
  "validation/cm01/p0-cancellation",
];
const KNOWN_P0 = {
  verdict: "FAIL",
  pending_at_timeout: true,
  pending_after_window: true,
  cancellation_notifications_sent: 0,
  late_response_settled_request: true,
  executor_sha256: "4b960124e9218ed124ed34e3b3595b648477b9dab6540c4ce1609d2efaf31313",
  s1a_digest: "cc7f884866e6e94255b100de57b82eec4a51660aadaf51c6464198131030af57",
};
const PARITY_ARGS = [
  { name: "decision.get", arguments: { record_id: "ADR-9901" } },
  {
    name: "decision.search",
    arguments: { query: "cache", canonical_lifecycle_status: "active" },
  },
  { name: "decision.applicable_to", arguments: { context: ["cache"] } },
  { name: "decision.trace", arguments: { record_id: "ADR-9901" } },
];
const PARITY_CODE = `async () => {
  const get = await codemode.decision_get({ record_id: "ADR-9901" });
  const search = await codemode.decision_search({ query: "cache", canonical_lifecycle_status: "active" });
  const applicable = await codemode.decision_applicable_to({ context: ["cache"] });
  const trace = await codemode.decision_trace({ record_id: "ADR-9901" });
  return {
    get, search, applicable, trace,
    capabilities: {
      propose: typeof codemode.decision_propose,
      propose_batch: typeof codemode.decision_propose_batch
    }
  };
}`;

mkdirSync(EVIDENCE, { recursive: true });
mkdirSync(RAW, { recursive: true });
mkdirSync(H.EMPTY_CWD, { recursive: true });

const unhandled = [];
process.on("unhandledRejection", (reason) => {
  unhandled.push(reason?.stack || reason?.message || String(reason));
});

function check(checks, id, pass, detail = null) {
  checks.push({ id, pass: Boolean(pass), detail });
}

function makeExecutor(harness, phase, timeoutMs) {
  const hostEvents = [];
  const hostEventsPath = join(RAW, `${harness.run}-${phase}-host-events.jsonl`);
  const executor = new QuickJSExecutor({
    timeoutMs,
    memoryLimitBytes: 8 * 1024 * 1024,
    hostCancellationGraceMs: HOST_GRACE_MS,
    onHostEvent: (event) => {
      hostEvents.push(event);
      try {
        writeFileSync(hostEventsPath, `${JSON.stringify(event)}\n`, { flag: "a" });
      } catch {
        // Evidence logging must not alter execution.
      }
    },
    onCleanup: () => harness.event("executor_cleanup", { phase }),
  });
  return { executor, hostEvents, hostEventsPath };
}

function makeTrackedAdapter(ctx, executor) {
  const tracker = H.createTracker(ctx.client);
  ctx.observer.tracker = tracker;
  const validators = H.makeValidators(ctx.inventory);
  const adapter = makeAdapter({
    client: tracker.trackedClient,
    inventory: ctx.inventory,
    validators,
    executor,
    validate: true,
  });
  return { tracker, adapter };
}

async function directResults(client) {
  const results = {};
  for (const { name, arguments: args } of PARITY_ARGS) {
    const raw = await client.callTool({ name, arguments: args });
    if (raw.isError) throw new Error(`direct ${name} returned isError`);
    results[name] = raw.structuredContent ?? raw.toolResult;
  }
  return results;
}

function parityChecks(codeResult, direct) {
  if (!codeResult) {
    return {
      get: false,
      search: false,
      applicable: false,
      trace: false,
      capabilities: false,
    };
  }
  return {
    get: H.deepEqual(codeResult.get, direct["decision.get"]),
    search: H.deepEqual(codeResult.search, direct["decision.search"]),
    applicable: H.deepEqual(codeResult.applicable, direct["decision.applicable_to"]),
    trace: H.deepEqual(codeResult.trace, direct["decision.trace"]),
    capabilities:
      codeResult.capabilities?.propose === "undefined" &&
      codeResult.capabilities?.propose_batch === "undefined",
  };
}

function cancelSummary(log, state) {
  const requestId = state?.requestId ?? null;
  const events = requestId === null ? [] : H.countOutbound(log, "notifications/cancelled", requestId);
  return {
    requestId,
    count: events.length,
    events: events.map((entry) => ({
      ts: entry.ts,
      requestId: entry.message?.params?.requestId ?? null,
      reason: entry.message?.params?.reason ?? null,
    })),
  };
}

function settlementLatency(state) {
  if (!state?.cancellationSentAt || !state?.settledAt) return null;
  return Date.parse(state.settledAt) - Date.parse(state.cancellationSentAt);
}

function lateResponses(log, requestId) {
  return log.filter(
    (entry) =>
      entry.dir === "in" &&
      entry.message?.id === requestId &&
      (entry.message?.result !== undefined || entry.message?.error !== undefined),
  );
}

function phaseConnectDirect(run, name) {
  return (harness) => H.connectDirect({ phase: name, logPath: join(RAW, `${run}-${name}-harness.jsonl`), harness });
}

function phaseConnectRelay(run, name, options) {
  return (harness) => H.connectRelay({ run, phase: name, harness, ...options });
}

async function runPhase(run, name, connect, body) {
  const harness = H.makeHarnessLog(join(RAW, `${run}-${name}-harness.jsonl`));
  harness.run = run;
  const result = { name, started_at: H.nowIso(), ok: false };
  let ctx = null;
  try {
    ctx = await connect(harness);
    result.connected = true;
    const outcome = await body(ctx, harness);
    Object.assign(result, outcome);
    result.ok = outcome.ok === true && !outcome.error;
  } catch (error) {
    result.error = error?.stack || error?.message || String(error);
    harness.event("phase_error", { name, error: result.error });
  } finally {
    if (ctx) {
      if (ctx.kind === "relay") result.cleanup = await H.cleanupRelay(ctx, harness);
      else if (ctx.kind === "synthetic") result.cleanup = await H.cleanupSynthetic(ctx, harness);
      else result.cleanup = await H.cleanupDirect(ctx, harness);
      if (ctx.kind !== "relay") {
        writeFileSync(join(RAW, `${run}-${name}-child-stderr.log`), ctx.stderrText());
      }
      harness.event("client_errors", { phase: name, errors: ctx.clientErrors });
    }
    result.finished_at = H.nowIso();
    harness.event("phase_end", { name, ok: result.ok, error: result.error ?? null });
  }
  return result;
}

async function controlStatus(ctx) {
  const before = ctx.control.events.length;
  ctx.control.send({ cmd: "status", at: H.nowIso() });
  return ctx.control.waitFor((event) => event.type === "status", H.CONTROL_TIMEOUT_MS, {
    after: before,
  });
}

async function releaseHeld(ctx) {
  const before = ctx.control.events.length;
  ctx.control.send({ cmd: "release", at: H.nowIso() });
  return ctx.control.waitFor(
    (event) => event.type === "response_released_downstream",
    H.CONTROL_TIMEOUT_MS,
    { after: before },
  );
}

async function phaseControlDirect(run, baselineDirect = null) {
  return runPhase(run, "control-direct", phaseConnectDirect(run, "control-direct"), async (ctx, harness) => {
    const direct = await directResults(ctx.client);
    const { executor } = makeExecutor(harness, "control-direct", NORMAL_TIMEOUT_MS);
    const { tracker, adapter } = makeTrackedAdapter(ctx, executor);
    const outcome = await H.executeWith(adapter.tool, PARITY_CODE, executor);
    const parity = parityChecks(outcome.result, direct);
    const order = tracker.states.map((state) => state.name);
    return {
      direct,
      outcome,
      parity,
      order,
      calls: tracker.states.map((state) => tracker.snapshot(state)),
      stats: executor.stats(),
      ok:
        !outcome.error &&
        Object.values(parity).every(Boolean) &&
        JSON.stringify(order) === JSON.stringify(READ_TOOLS) &&
        executor.stats()?.cancelledCalls === 0 &&
        executor.stats()?.resolvedCalls === 4,
      baselineDirectMatches: baselineDirect ? H.deepEqual(direct, baselineDirect) : null,
    };
  });
}

async function phaseControlRelay(run, directBaseline) {
  return runPhase(
    run,
    "control-relay",
    phaseConnectRelay(run, "control-relay", { mode: "passthrough" }),
    async (ctx, harness) => {
      const { executor } = makeExecutor(harness, "control-relay", NORMAL_TIMEOUT_MS);
      const { tracker, adapter } = makeTrackedAdapter(ctx, executor);
      const outcome = await H.executeWith(adapter.tool, PARITY_CODE, executor);
      const parity = parityChecks(outcome.result, directBaseline);
      const order = tracker.states.map((state) => state.name);
      const relayEvents = {
        targetSeen: ctx.control.events.filter((event) => event.type === "target_request_seen").length,
        targetForwarded: ctx.control.events.filter((event) => event.type === "target_request_forwarded").length,
        upstreamResponses: ctx.control.events.filter((event) => event.type === "upstream_response_received").length,
        withheld: ctx.control.events.filter((event) => event.type === "response_withheld").length,
        cancellations: ctx.control.events.filter((event) => event.type === "cancel_from_client").length,
      };
      return {
        outcome,
        parity,
        order,
        calls: tracker.states.map((state) => tracker.snapshot(state)),
        relayEvents,
        stats: executor.stats(),
        ok:
          !outcome.error &&
          Object.values(parity).every(Boolean) &&
          JSON.stringify(order) === JSON.stringify(READ_TOOLS) &&
          relayEvents.targetForwarded === 4 &&
          relayEvents.upstreamResponses === 4 &&
          relayEvents.withheld === 0 &&
          relayEvents.cancellations === 0,
      };
    },
  );
}

async function phaseTimeoutWithhold(run) {
  return runPhase(
    run,
    "timeout-withhold",
    phaseConnectRelay(run, "timeout-withhold", {
      mode: "withhold",
      withholdTools: ["decision.get"],
    }),
    async (ctx, harness) => {
      const { executor, hostEvents } = makeExecutor(harness, "timeout-withhold", CANCEL_TIMEOUT_MS);
      const { tracker, adapter } = makeTrackedAdapter(ctx, executor);
      const before = ctx.control.events.length;
      const execPromise = H.executeWith(
        adapter.tool,
        `async () => codemode.decision_get({ record_id: "ADR-9901" })`,
        executor,
      );
      const withheld = await ctx.control.waitFor(
        (event) => event.type === "response_withheld",
        LATE_WAIT_MS,
        { after: before },
      );
      const outcome = await execPromise;
      const state = tracker.currentState();
      const settled = await tracker.waitForSettlement(state, OBSERVE_MS);
      const cancel = cancelSummary(ctx.log, state);
      const controlCancel = await ctx.control.waitFor(
        (event) => event.type === "cancel_from_client" && event.requestId === state.requestId,
        OBSERVE_MS,
        { after: before },
      );
      const status = await controlStatus(ctx);
      const lateBeforeRelease = lateResponses(ctx.log, state.requestId).length;
      const released = await releaseHeld(ctx);
      await delay(300);
      const afterRelease = tracker.snapshot(state);
      const lateAfterRelease = lateResponses(ctx.log, state.requestId).length;
      const cancelAfterRelease = cancelSummary(ctx.log, state);
      const childEvent = H.readJsonl(ctx.childEvents).find(
        (event) =>
          event.type === "child_stdin_line" &&
          event.line?.includes("notifications/cancelled") &&
          event.line?.includes(`"requestId":${state.requestId}`),
      );
      const stats = executor.stats();
      const abortedEvent = hostEvents.find((event) => event.type === "host_call_aborted");
      const pendingAtDeadline =
        Boolean(abortedEvent) &&
        Date.parse(state.startedAt) <= Date.parse(abortedEvent.ts) &&
        (!state.settledAt || Date.parse(state.settledAt) >= Date.parse(abortedEvent.ts));
      return {
        withheld: withheld.event,
        outcome,
        stateAtReturn: tracker.snapshot(state),
        pendingAtDeadline,
        pendingAtExecutionReturn: state.pending,
        settled,
        cancel,
        controlCancellation: controlCancel.event,
        serverResponseBeforeCancel:
          Boolean(withheld.event?.ts) &&
          Boolean(controlCancel.event?.ts) &&
          Date.parse(withheld.event.ts) < Date.parse(controlCancel.event.ts),
        status: status.event,
        lateResponsesBeforeRelease: lateBeforeRelease,
        released: released.event,
        stateAfterRelease: afterRelease,
        lateResponsesAfterRelease: lateAfterRelease,
        cancelAfterRelease: cancelAfterRelease,
        childCancellationFrame: childEvent ?? null,
        clientErrors: ctx.clientErrors,
        hostEvents,
        stats,
        settlementLatencyMs: settlementLatency(state),
        ok:
          withheld.found &&
          Boolean(outcome.error) &&
          /execution exceeded/i.test(outcome.error ?? "") &&
          outcome.stats?.timedOut === true &&
          pendingAtDeadline === true &&
          state.pending === false &&
          state.outcome === "rejected" &&
          state.errorCode === -32001 &&
          settled.found === true &&
          cancel.count === 1 &&
          cancelAfterRelease.count === 1 &&
          controlCancel.found === true &&
          lateBeforeRelease === 0 &&
          lateAfterRelease >= 1 &&
          afterRelease.outcome === "rejected" &&
          afterRelease.errorCode === -32001 &&
          stats.cancelledCalls === 1 &&
          stats.cancelledSettled >= 1 &&
          stats.cancelledUnsettled === 0 &&
          stats.pendingAtEnd === 0 &&
          stats.failedCalls === 0 &&
          stats.cleanupErrors.length === 0 &&
          Boolean(childEvent),
      };
    },
  );
}

async function raceIteration(ctx, harness, { timeoutMs, delayMs, label }) {
  const { executor, hostEvents } = makeExecutor(harness, `race-${label}`, timeoutMs);
  const { tracker, adapter } = makeTrackedAdapter(ctx, executor);
  const before = ctx.control.events.length;
  const execPromise = H.executeWith(
    adapter.tool,
    `async () => codemode.decision_get({ record_id: "ADR-9901" })`,
    executor,
  );
  const outcome = await execPromise;
  const state = tracker.currentState();
  const settled = await tracker.waitForSettlement(state, OBSERVE_MS);
  const forwarded = await ctx.control.waitFor(
    (event) => event.type === "response_forwarded_downstream" && event.how === "delay",
    LATE_WAIT_MS,
    { after: before },
  );
  await delay(150);
  const afterForward = tracker.snapshot(state);
  const cancel = cancelSummary(ctx.log, state);
  return {
    label,
    timeoutMs,
    delayMs,
    outcome,
    state,
    settled,
    forwarded: forwarded.event,
    afterForward,
    cancel,
    hostEvents,
    stats: executor.stats(),
    settlementLatencyMs: settlementLatency(state),
  };
}

async function phaseRaceBefore(run) {
  return runPhase(
    run,
    "race-before",
    phaseConnectRelay(run, "race-before", {
      mode: "delay",
      delayMs: 100,
      withholdTools: ["decision.get"],
    }),
    async (ctx, harness) => {
      const iteration = await raceIteration(ctx, harness, {
        timeoutMs: RACE_TIMEOUT_MS + 100,
        delayMs: 100,
        label: "before",
      });
      return {
        iteration,
        ok:
          iteration.state.outcome === "fulfilled" &&
          iteration.cancel.count === 0 &&
          iteration.stats.cancelledCalls === 0 &&
          iteration.stats.timedOut === false,
      };
    },
  );
}

async function phaseRaceAfter(run) {
  return runPhase(
    run,
    "race-after",
    phaseConnectRelay(run, "race-after", {
      mode: "delay",
      delayMs: 700,
      withholdTools: ["decision.get"],
    }),
    async (ctx, harness) => {
      const iteration = await raceIteration(ctx, harness, {
        timeoutMs: RACE_TIMEOUT_MS,
        delayMs: 700,
        label: "after",
      });
      return {
        iteration,
        ok:
          iteration.state.outcome === "rejected" &&
          iteration.state.errorCode === -32001 &&
          iteration.cancel.count === 1 &&
          iteration.forwarded !== null &&
          iteration.afterForward.outcome === "rejected" &&
          iteration.afterForward.errorCode === -32001,
      };
    },
  );
}

async function phaseRaceBoundary(run) {
  return runPhase(
    run,
    "race-boundary",
    phaseConnectRelay(run, "race-boundary", {
      mode: "delay",
      delayMs: RACE_TIMEOUT_MS,
      withholdTools: ["decision.get"],
    }),
    async (ctx, harness) => {
      const iterations = [];
      for (let index = 0; index < 3; index += 1) {
        iterations.push(
          await raceIteration(ctx, harness, {
            timeoutMs: RACE_TIMEOUT_MS,
            delayMs: RACE_TIMEOUT_MS,
            label: `boundary-${index}`,
          }),
        );
      }
      const invalid = iterations.filter(
        (iteration) =>
          (iteration.state.outcome === "fulfilled" && iteration.cancel.count > 0) ||
          (iteration.state.pending === true),
      );
      return {
        iterations,
        invalid: invalid.length,
        ok: invalid.length === 0,
      };
    },
  );
}

async function phaseParallel(run) {
  return runPhase(
    run,
    "parallel",
    phaseConnectRelay(run, "parallel", {
      mode: "withhold",
      withholdTools: ["decision.search"],
    }),
    async (ctx, harness) => {
      const { executor } = makeExecutor(harness, "parallel", CANCEL_TIMEOUT_MS);
      const { tracker, adapter } = makeTrackedAdapter(ctx, executor);
      const before = ctx.control.events.length;
      const execPromise = H.executeWith(
        adapter.tool,
        `async () => Promise.all([
          codemode.decision_get({ record_id: "ADR-9901" }),
          codemode.decision_search({ query: "cache", canonical_lifecycle_status: "active" })
        ])`,
        executor,
      );
      const withheld = await ctx.control.waitFor(
        (event) => event.type === "response_withheld" && event.tool === "decision.search",
        LATE_WAIT_MS,
        { after: before },
      );
      const outcome = await execPromise;
      const getState = tracker.states.find((state) => state.name === "decision.get");
      const searchState = tracker.states.find((state) => state.name === "decision.search");
      const getSettled = await tracker.waitForSettlement(getState, OBSERVE_MS);
      const searchSettled = await tracker.waitForSettlement(searchState, OBSERVE_MS);
      const getCancel = cancelSummary(ctx.log, getState);
      const searchCancel = cancelSummary(ctx.log, searchState);
      const released = await releaseHeld(ctx);
      await delay(200);
      return {
        withheld: withheld.event,
        outcome,
        get: tracker.snapshot(getState),
        search: tracker.snapshot(searchState),
        getSettled,
        searchSettled,
        getCancel,
        searchCancel,
        released: released.event,
        stats: executor.stats(),
        ok:
          withheld.found &&
          getState.outcome === "fulfilled" &&
          searchState.outcome === "rejected" &&
          searchState.errorCode === -32001 &&
          getCancel.count === 0 &&
          searchCancel.count === 1 &&
          executor.stats()?.cancelledCalls === 1 &&
          executor.stats()?.resolvedCalls === 1,
      };
    },
  );
}

async function phaseSequential(run) {
  return runPhase(
    run,
    "sequential-fourth",
    phaseConnectRelay(run, "sequential-fourth", {
      mode: "withhold",
      withholdTools: ["decision.trace"],
    }),
    async (ctx, harness) => {
      const { executor } = makeExecutor(harness, "sequential-fourth", 500);
      const { tracker, adapter } = makeTrackedAdapter(ctx, executor);
      const before = ctx.control.events.length;
      const execPromise = H.executeWith(adapter.tool, PARITY_CODE, executor);
      const withheld = await ctx.control.waitFor(
        (event) => event.type === "response_withheld" && event.tool === "decision.trace",
        LATE_WAIT_MS,
        { after: before },
      );
      const outcome = await execPromise;
      const states = Object.fromEntries(tracker.states.map((state) => [state.name, state]));
      const cancellations = Object.fromEntries(
        tracker.states.map((state) => [state.name, cancelSummary(ctx.log, state)]),
      );
      const released = await releaseHeld(ctx);
      await delay(200);
      return {
        withheld: withheld.event,
        outcome,
        states: Object.fromEntries(
          Object.entries(states).map(([name, state]) => [name, tracker.snapshot(state)]),
        ),
        cancellations,
        released: released.event,
        stats: executor.stats(),
        ok:
          withheld.found &&
          states["decision.get"]?.outcome === "fulfilled" &&
          states["decision.search"]?.outcome === "fulfilled" &&
          states["decision.applicable_to"]?.outcome === "fulfilled" &&
          states["decision.trace"]?.outcome === "rejected" &&
          states["decision.trace"]?.errorCode === -32001 &&
          cancellations["decision.get"]?.count === 0 &&
          cancellations["decision.search"]?.count === 0 &&
          cancellations["decision.applicable_to"]?.count === 0 &&
          cancellations["decision.trace"]?.count === 1 &&
          executor.stats()?.cancelledCalls === 1 &&
          executor.stats()?.resolvedCalls === 3,
      };
    },
  );
}

async function phaseRepeated(run) {
  return runPhase(
    run,
    "repeated",
    phaseConnectRelay(run, "repeated", {
      mode: "withhold",
      withholdTools: ["decision.get"],
    }),
    async (ctx, harness) => {
      const iterations = [];
      for (let index = 0; index < 3; index += 1) {
        const { executor, hostEvents } = makeExecutor(harness, `repeated-${index}`, 250);
        const { tracker, adapter } = makeTrackedAdapter(ctx, executor);
        const before = ctx.control.events.length;
        const execPromise = H.executeWith(
          adapter.tool,
          `async () => codemode.decision_get({ record_id: "ADR-9901" })`,
          executor,
        );
        const withheld = await ctx.control.waitFor(
          (event) => event.type === "response_withheld",
          LATE_WAIT_MS,
          { after: before },
        );
        const outcome = await execPromise;
        const state = tracker.currentState();
        const settled = await tracker.waitForSettlement(state, OBSERVE_MS);
        const cancel = cancelSummary(ctx.log, state);
        const released = await releaseHeld(ctx);
        await delay(75);
        iterations.push({
          index,
          withheld: withheld.event,
          outcome,
          state: tracker.snapshot(state),
          settled,
          cancel,
          released: released.event,
          hostEvents,
          stats: executor.stats(),
          settlementLatencyMs: settlementLatency(state),
        });
      }
      return {
        iterations,
        ok: iterations.every(
          (iteration) =>
            iteration.state.outcome === "rejected" &&
            iteration.state.errorCode === -32001 &&
            iteration.cancel.count === 1 &&
            iteration.settled.found === true &&
            iteration.stats.cancelledCalls === 1 &&
            iteration.stats.cancelledUnsettled === 0,
        ),
      };
    },
  );
}

async function phaseTransportClose(run) {
  return runPhase(
    run,
    "transport-close",
    phaseConnectRelay(run, "transport-close", {
      mode: "withhold",
      withholdTools: ["decision.get"],
    }),
    async (ctx, harness) => {
      const { executor } = makeExecutor(harness, "transport-close", 5000);
      const { tracker, adapter } = makeTrackedAdapter(ctx, executor);
      const before = ctx.control.events.length;
      const execPromise = H.executeWith(
        adapter.tool,
        `async () => codemode.decision_get({ record_id: "ADR-9901" })`,
        executor,
      );
      const withheld = await ctx.control.waitFor(
        (event) => event.type === "response_withheld",
        LATE_WAIT_MS,
        { after: before },
      );
      const state = tracker.currentState();
      const pendingBeforeClose = state.pending;
      await ctx.client.close();
      const outcome = await execPromise;
      const settled = await tracker.waitForSettlement(state, OBSERVE_MS);
      const cancel = cancelSummary(ctx.log, state);
      const stats = executor.stats();
      return {
        withheld: withheld.event,
        pendingBeforeClose,
        outcome,
        state: tracker.snapshot(state),
        settled,
        cancel,
        stats,
        ok:
          withheld.found &&
          pendingBeforeClose === true &&
          state.outcome === "rejected" &&
          state.errorCode === -32000 &&
          cancel.count === 0 &&
          stats.timedOut === false &&
          stats.cancelledCalls === 0 &&
          stats.failedCalls === 1,
      };
    },
  );
}

async function phaseTimeoutThenClose(run) {
  return runPhase(
    run,
    "timeout-then-close",
    phaseConnectRelay(run, "timeout-then-close", {
      mode: "withhold",
      withholdTools: ["decision.get"],
    }),
    async (ctx, harness) => {
      const { executor } = makeExecutor(harness, "timeout-then-close", 250);
      const { tracker, adapter } = makeTrackedAdapter(ctx, executor);
      const before = ctx.control.events.length;
      const execPromise = H.executeWith(
        adapter.tool,
        `async () => codemode.decision_get({ record_id: "ADR-9901" })`,
        executor,
      );
      await ctx.control.waitFor(
        (event) => event.type === "response_withheld",
        LATE_WAIT_MS,
        { after: before },
      );
      const outcome = await execPromise;
      const state = tracker.currentState();
      const settled = await tracker.waitForSettlement(state, OBSERVE_MS);
      const cancel = cancelSummary(ctx.log, state);
      await ctx.client.close();
      await delay(100);
      const afterClose = tracker.snapshot(state);
      return {
        outcome,
        state: tracker.snapshot(state),
        settled,
        cancel,
        afterClose,
        stats: executor.stats(),
        ok:
          state.outcome === "rejected" &&
          state.errorCode === -32001 &&
          cancel.count === 1 &&
          afterClose.outcome === "rejected" &&
          afterClose.errorCode === -32001 &&
          executor.stats()?.cancelledCalls === 1,
      };
    },
  );
}

async function phaseValidation(run) {
  return runPhase(run, "validation", phaseConnectDirect(run, "validation"), async (ctx, harness) => {
    const { executor } = makeExecutor(harness, "validation", 1000);
    const { tracker, adapter } = makeTrackedAdapter(ctx, executor);
    const outcome = await H.executeWith(
      adapter.tool,
      `async () => codemode.decision_get({ record_id: 123 })`,
      executor,
    );
    const cancel = tracker.states.length ? cancelSummary(ctx.log, tracker.states[0]) : { count: 0 };
    return {
      outcome,
      trackedCalls: tracker.states.map((state) => tracker.snapshot(state)),
      cancel,
      adapterCalls: adapter.callLog,
      stats: executor.stats(),
      ok:
        Boolean(outcome.error) &&
        /Argument validation failed/.test(outcome.error ?? "") &&
        tracker.states.length === 0 &&
        cancel.count === 0 &&
        executor.stats()?.cancelledCalls === 0,
    };
  });
}

async function phaseMcpError(run) {
  return runPhase(run, "mcp-error", phaseConnectDirect(run, "mcp-error"), async (ctx, harness) => {
    const { executor } = makeExecutor(harness, "mcp-error", 1000);
    const tracker = H.createTracker(ctx.client);
    ctx.observer.tracker = tracker;
    const adapter = makeAdapter({
      client: tracker.trackedClient,
      inventory: ctx.inventory,
      validators: H.makeValidators(ctx.inventory),
      executor,
      validate: false,
    });
    const outcome = await H.executeWith(
      adapter.tool,
      `async () => codemode.decision_search({ canonical_lifecycle_status: "bogus" })`,
      executor,
    );
    const state = tracker.states[0];
    const cancel = cancelSummary(ctx.log, state);
    return {
      outcome,
      state: tracker.snapshot(state),
      adapterCalls: adapter.callLog,
      cancel,
      stats: executor.stats(),
      ok:
        Boolean(outcome.error) &&
        /MCP decision\.search error/.test(outcome.error ?? "") &&
        state?.outcome === "fulfilled" &&
        adapter.callLog[0]?.isError === true &&
        cancel.count === 0 &&
        executor.stats()?.cancelledCalls === 0,
    };
  });
}

async function phaseSynthetic(run) {
  const harness = H.makeHarnessLog(join(RAW, `${run}-synthetic-cancel-harness.jsonl`));
  harness.run = run;
  const syntheticLog = join(RAW, `${run}-synthetic-cancel-server.jsonl`);
  if (existsSync(syntheticLog)) rmSync(syntheticLog);
  const result = { name: "synthetic-cancel", started_at: H.nowIso(), ok: false };
  let ctx = null;
  try {
    ctx = await H.connectSynthetic({ phase: "synthetic-cancel", harness, syntheticLog });
    const { executor } = makeExecutor(harness, "synthetic-cancel", 150);
    const tracker = H.createTracker(ctx.client);
    ctx.observer.tracker = tracker;
    const descriptor = {
      "slow.echo": {
        description: "Test-only slow tool",
        inputSchema: {
          type: "object",
          properties: { delay_ms: { type: "number" } },
        },
        execute: async (args, context = {}) => {
          const options = context.signal ? { signal: context.signal } : undefined;
          return tracker.trackedClient.callTool(
            { name: "slow.echo", arguments: args },
            undefined,
            options,
          );
        },
      },
    };
    const tool = createBrowserCodeTool({ tools: descriptor, executor });
    const execPromise = H.executeWith(
      tool,
      `async () => codemode.slow_echo({ delay_ms: 1000 })`,
      executor,
    );
    const started = await H.waitUntil(
      () => existsSync(syntheticLog) && readFileSync(syntheticLog, "utf8").includes('"type":"tool_started"'),
      3000,
    );
    const outcome = await execPromise;
    const state = tracker.currentState();
    const settled = await tracker.waitForSettlement(state, OBSERVE_MS);
    const cancel = cancelSummary(ctx.log, state);
    await H.waitUntil(
      () =>
        existsSync(syntheticLog) &&
        readFileSync(syntheticLog, "utf8").includes('"type":"handler_returned"'),
      3000,
    );
    const serverEvents = H.readJsonl(syntheticLog);
    const startedEvent = serverEvents.find((event) => event.type === "tool_started");
    const abortedEvent = serverEvents.find((event) => event.type === "signal_aborted");
    const returnedEvent = serverEvents.find((event) => event.type === "handler_returned");
    const responseAfterCancel = lateResponses(ctx.log, state.requestId);
    result.serverEvents = serverEvents;
    Object.assign(result, {
      started,
      outcome,
      state: tracker.snapshot(state),
      settled,
      cancel,
      serverStarted: startedEvent ?? null,
      serverAborted: abortedEvent ?? null,
      serverReturned: returnedEvent ?? null,
      responseAfterCancel: responseAfterCancel.length,
      stats: executor.stats(),
      ok:
        started &&
        Boolean(abortedEvent) &&
        returnedEvent?.aborted === true &&
        returnedEvent?.response_expected === false &&
        state.outcome === "rejected" &&
        state.errorCode === -32001 &&
        cancel.count === 1 &&
        responseAfterCancel.length === 0 &&
        executor.stats()?.cancelledCalls === 1,
    });
  } catch (error) {
    result.error = error?.stack || error?.message || String(error);
    harness.event("phase_error", { name: "synthetic-cancel", error: result.error });
  } finally {
    if (ctx) result.cleanup = await H.cleanupSynthetic(ctx, harness);
    result.finished_at = H.nowIso();
    harness.event("phase_end", { name: "synthetic-cancel", ok: result.ok, error: result.error ?? null });
  }
  return result;
}

function normalizedRun(run) {
  const pickIteration = (iteration) => ({
    label: iteration.label,
    state: {
      outcome: iteration.state?.outcome ?? null,
      errorCode: iteration.state?.errorCode ?? null,
      pending: iteration.state?.pending ?? null,
    },
    cancelCount: iteration.cancel?.count ?? null,
    timedOut: iteration.stats?.timedOut ?? null,
    cancelledCalls: iteration.stats?.cancelledCalls ?? null,
    cancelledUnsettled: iteration.stats?.cancelledUnsettled ?? null,
  });
  return {
    phases: {
      controlDirect: {
        ok: run.controlDirect?.ok,
        parity: run.controlDirect?.parity,
        order: run.controlDirect?.order,
      },
      controlRelay: {
        ok: run.controlRelay?.ok,
        parity: run.controlRelay?.parity,
        relayEvents: run.controlRelay?.relayEvents,
      },
      timeoutWithhold: {
        ok: run.timeoutWithhold?.ok,
        outcome: run.timeoutWithhold?.stateAtReturn?.outcome,
        errorCode: run.timeoutWithhold?.stateAtReturn?.errorCode,
        pending: run.timeoutWithhold?.stateAtReturn?.pending,
        pendingAtDeadline: run.timeoutWithhold?.pendingAtDeadline,
        pendingAtExecutionReturn: run.timeoutWithhold?.pendingAtExecutionReturn,
        cancelCount: run.timeoutWithhold?.cancel?.count,
        cancelAfterRelease: run.timeoutWithhold?.cancelAfterRelease?.count,
        lateAfterRelease: run.timeoutWithhold?.lateResponsesAfterRelease,
        timedOut: run.timeoutWithhold?.stats?.timedOut,
        cancelledCalls: run.timeoutWithhold?.stats?.cancelledCalls,
        cancelledSettled: run.timeoutWithhold?.stats?.cancelledSettled,
        cancelledUnsettled: run.timeoutWithhold?.stats?.cancelledUnsettled,
        failedCalls: run.timeoutWithhold?.stats?.failedCalls,
      },
      raceBefore: pickIteration(run.raceBefore?.iteration ?? {}),
      raceAfter: pickIteration(run.raceAfter?.iteration ?? {}),
      raceBoundary: (run.raceBoundary?.iterations ?? []).map(pickIteration),
      parallel: {
        ok: run.parallel?.ok,
        getOutcome: run.parallel?.get?.outcome,
        searchOutcome: run.parallel?.search?.outcome,
        searchError: run.parallel?.search?.errorCode,
        getCancel: run.parallel?.getCancel?.count,
        searchCancel: run.parallel?.searchCancel?.count,
        cancelledCalls: run.parallel?.stats?.cancelledCalls,
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
    },
    cleanup: {
      all: Object.values(run)
        .filter((value) => value && value.cleanup)
        .every((value) => !value.cleanup.errors?.length),
    },
    unhandled: run.unhandled ?? [],
  };
}

function evaluateRun(run, runUnhandled) {
  const checks = [];
  const phase = (name) => run[name];
  check(checks, "F1-N1-CONTROL-DIRECT", phase("controlDirect")?.ok === true, phase("controlDirect")?.parity);
  check(checks, "F1-N2-CONTROL-RELAY", phase("controlRelay")?.ok === true, phase("controlRelay")?.relayEvents);
  check(
    checks,
    "F1-T1-TIMEOUT-SETTLES",
    phase("timeoutWithhold")?.ok === true,
    {
      state: phase("timeoutWithhold")?.stateAtReturn,
      cancel: phase("timeoutWithhold")?.cancel,
      stats: phase("timeoutWithhold")?.stats,
    },
  );
  check(
    checks,
    "F1-T2-LATE-NO-REVIVAL",
    phase("timeoutWithhold")?.stateAfterRelease?.errorCode === -32001 &&
      phase("timeoutWithhold")?.lateResponsesAfterRelease >= 1 &&
      phase("timeoutWithhold")?.cancelAfterRelease?.count === 1,
    {
      stateAfterRelease: phase("timeoutWithhold")?.stateAfterRelease,
      late: phase("timeoutWithhold")?.lateResponsesAfterRelease,
      cancel: phase("timeoutWithhold")?.cancelAfterRelease,
    },
  );
  check(checks, "F1-C1-RACE-BEFORE", phase("raceBefore")?.ok === true, phase("raceBefore")?.iteration);
  check(checks, "F1-C2-RACE-BOUNDARY", phase("raceBoundary")?.ok === true, {
    invalid: phase("raceBoundary")?.invalid,
    iterations: phase("raceBoundary")?.iterations?.map((iteration) => ({
      outcome: iteration.state?.outcome,
      cancel: iteration.cancel?.count,
    })),
  });
  check(checks, "F1-C3-RACE-AFTER", phase("raceAfter")?.ok === true, phase("raceAfter")?.iteration);
  check(checks, "F1-C3-PARALLEL", phase("parallel")?.ok === true, {
    get: phase("parallel")?.get,
    search: phase("parallel")?.search,
    cancels: {
      get: phase("parallel")?.getCancel,
      search: phase("parallel")?.searchCancel,
    },
  });
  check(checks, "F1-R1-SEQUENTIAL", phase("sequential")?.ok === true, {
    states: phase("sequential")?.states,
    cancels: phase("sequential")?.cancellations,
  });
  check(checks, "F1-R2-REPEATED", phase("repeated")?.ok === true, phase("repeated")?.iterations);
  check(checks, "F1-F1-TRANSPORT-CLOSE", phase("transportClose")?.ok === true, {
    state: phase("transportClose")?.state,
    cancel: phase("transportClose")?.cancel,
    stats: phase("transportClose")?.stats,
  });
  check(checks, "F1-F2-TIMEOUT-THEN-CLOSE", phase("timeoutThenClose")?.ok === true, {
    state: phase("timeoutThenClose")?.state,
    afterClose: phase("timeoutThenClose")?.afterClose,
    cancel: phase("timeoutThenClose")?.cancel,
  });
  check(checks, "F1-A1-VALIDATION", phase("validation")?.ok === true, {
    outcome: phase("validation")?.outcome?.error,
    tracked: phase("validation")?.trackedCalls,
    stats: phase("validation")?.stats,
  });
  check(checks, "F1-A2-MCP-ISERROR", phase("mcpError")?.ok === true, {
    state: phase("mcpError")?.state,
    calls: phase("mcpError")?.adapterCalls,
  });
  check(
    checks,
    "F1-A3-PROPOSALS",
    phase("controlDirect")?.outcome?.result?.capabilities?.propose === "undefined" &&
      phase("controlDirect")?.outcome?.result?.capabilities?.propose_batch === "undefined",
    phase("controlDirect")?.outcome?.result?.capabilities,
  );
  check(checks, "F1-S1-GENUINE-CANCEL-FRAME", Boolean(phase("timeoutWithhold")?.childCancellationFrame), {
    frame: phase("timeoutWithhold")?.childCancellationFrame,
    serverResponseBeforeCancel: phase("timeoutWithhold")?.serverResponseBeforeCancel,
    note:
      "The genuine server received the cancellation frame after its withheld response; this is client/transport behavior, not server execution termination.",
  });
  check(checks, "F1-S2-SYNTHETIC-CANCEL", phase("synthetic")?.ok === true, {
    state: phase("synthetic")?.state,
    server: {
      started: phase("synthetic")?.serverStarted,
      aborted: phase("synthetic")?.serverAborted,
      returned: phase("synthetic")?.serverReturned,
    },
    responseAfterCancel: phase("synthetic")?.responseAfterCancel,
  });
  const allCleanup = Object.values(run)
    .filter((value) => value && value.cleanup)
    .every(
      (value) =>
        value.cleanup.errors?.length === 0 &&
        value.cleanup.relay_alive_after !== true &&
        value.cleanup.upstream_alive_after !== true &&
        value.cleanup.server_alive_after !== true,
    );
  check(checks, "F1-P1-CLEANUP", allCleanup, Object.fromEntries(
    Object.entries(run)
      .filter(([, value]) => value && value.cleanup)
      .map(([name, value]) => [name, value.cleanup]),
  ));
  const hostEventGroups = [
    run.timeoutWithhold?.hostEvents,
    run.raceBefore?.iteration?.hostEvents,
    run.raceAfter?.iteration?.hostEvents,
    ...(run.raceBoundary?.iterations ?? []).map((iteration) => iteration.hostEvents),
    ...(run.repeated?.iterations ?? []).map((iteration) => iteration.hostEvents),
  ].filter(Boolean);
  const hostEvents = hostEventGroups.flat();
  const unsettledAfterGrace = hostEvents.filter(
    (event) => event.type === "host_call_unsettled_after_grace",
  );
  const lateAfterGrace = hostEvents.filter(
    (event) =>
      event.type === "host_call_settled_after_abort" &&
      (event.afterAbortMs == null || event.afterAbortMs > HOST_GRACE_MS),
  );
  check(
    checks,
    "F1-P1-NO-POST-DISPOSAL",
    unsettledAfterGrace.length === 0 && lateAfterGrace.length === 0,
    {
      host_events: hostEvents.length,
      unsettled_after_grace: unsettledAfterGrace,
      late_after_grace: lateAfterGrace,
    },
  );
  check(checks, "F1-NO-UNHANDLED", runUnhandled.length === 0, runUnhandled);
  return checks;
}

const startTime = H.nowIso();
const versions = H.versions();
const identities = {
  fixture: { path: H.M4_FIXTURE, sha256: H.sha256File(H.M4_FIXTURE) },
  p0_fixture: {
    path: join(H.S1A_DIR, "m1", "fixture", "canonical", "project_memory.json"),
    sha256: H.sha256File(join(H.S1A_DIR, "m1", "fixture", "canonical", "project_memory.json")),
  },
  f1_executor: { path: join(H.F1_DIR, "quickjs-executor.mjs"), sha256: H.sha256File(join(H.F1_DIR, "quickjs-executor.mjs")) },
  f1_adapter: { path: join(H.F1_DIR, "adapter.mjs"), sha256: H.sha256File(join(H.F1_DIR, "adapter.mjs")) },
  f1_relay: { path: join(H.F1_DIR, "relay.mjs"), sha256: H.sha256File(join(H.F1_DIR, "relay.mjs")) },
  f1_synthetic_server: {
    path: join(H.F1_DIR, "synthetic-server.mjs"),
    sha256: H.sha256File(join(H.F1_DIR, "synthetic-server.mjs")),
  },
  f1_runner: { path: join(H.F1_DIR, "run-f1.mjs"), sha256: H.sha256File(join(H.F1_DIR, "run-f1.mjs")) },
  package_lock: { path: join(H.F1_DIR, "package-lock.json"), sha256: H.sha256File(join(H.F1_DIR, "package-lock.json")) },
  p0_verdict: { path: join(H.P0_DIR, "evidence", "verdict.json"), sha256: H.sha256File(join(H.P0_DIR, "evidence", "verdict.json")) },
  p0_run1: { path: join(H.P0_DIR, "evidence", "run1.json"), sha256: H.sha256File(join(H.P0_DIR, "evidence", "run1.json")) },
  p0_run2: { path: join(H.P0_DIR, "evidence", "run2.json"), sha256: H.sha256File(join(H.P0_DIR, "evidence", "run2.json")) },
  frozen_executor: {
    path: join(H.S1A_DIR, "e0", "quickjs-executor.mjs"),
    sha256: H.sha256File(join(H.S1A_DIR, "e0", "quickjs-executor.mjs")),
  },
};

const p0Verdict = H.readJson(join(H.P0_DIR, "evidence", "verdict.json"));
const p0Run1 = H.readJson(join(H.P0_DIR, "evidence", "run1.json"));

function s1aDigest() {
  const files = H.gitLines(["ls-files", "validation/cm01/s1a-local"]).sort();
  const hashes = Object.fromEntries(files.map((file) => [file, H.sha256File(join(H.ROOT, file))]));
  return { files: hashes, digest: H.sha256Text(JSON.stringify(hashes)) };
}

const preservedBefore = s1aDigest();
const frozenStatusBefore = H.gitLines([
  "status",
  "--porcelain",
  "--",
  ...FROZEN_PATHS,
]);
const m4GuardBefore = checkM4Protection({ cwd: H.ROOT, baseSha: DECLARED_BASELINE });

const runs = [];
for (const runLabel of ["run1", "run2"]) {
  process.stdout.write(`[f1] starting ${runLabel}\n`);
  const controlDirect = await phaseControlDirect(runLabel);
  const controlRelay = await phaseControlRelay(runLabel, controlDirect.direct);
  const timeoutWithhold = await phaseTimeoutWithhold(runLabel);
  const raceBefore = await phaseRaceBefore(runLabel);
  const raceBoundary = await phaseRaceBoundary(runLabel);
  const raceAfter = await phaseRaceAfter(runLabel);
  const parallel = await phaseParallel(runLabel);
  const sequential = await phaseSequential(runLabel);
  const repeated = await phaseRepeated(runLabel);
  const transportClose = await phaseTransportClose(runLabel);
  const timeoutThenClose = await phaseTimeoutThenClose(runLabel);
  const validation = await phaseValidation(runLabel);
  const mcpError = await phaseMcpError(runLabel);
  const synthetic = await phaseSynthetic(runLabel);

  const run = {
    run: runLabel,
    started_at: H.nowIso(),
    controlDirect,
    controlRelay,
    timeoutWithhold,
    raceBefore,
    raceBoundary,
    raceAfter,
    parallel,
    sequential,
    repeated,
    transportClose,
    timeoutThenClose,
    validation,
    mcpError,
    synthetic,
    p0_comparison: {
      original: {
        verdict: p0Verdict.verdict,
        pending_at_timeout: p0Run1.fault?.classification?.pending_immediately_after_timeout,
        pending_after_window: p0Run1.fault?.classification?.pending_after_observation_window,
        cancellation_notifications_sent: p0Run1.fault?.classification?.cancellation_notifications_sent,
        late_response_settled_request: p0Run1.fault?.classification?.late_response_settled_request,
      },
      corrected: {
        pending_at_deadline: timeoutWithhold.pendingAtDeadline,
        pending_at_execution_return: timeoutWithhold.pendingAtExecutionReturn,
        pending_after_grace: timeoutWithhold.pendingAtExecutionReturn,
        cancellation_notifications_sent: timeoutWithhold.cancel?.count,
        late_response_settled_request: timeoutWithhold.stateAfterRelease?.outcome === "fulfilled",
        client_outcome: timeoutWithhold.stateAtReturn?.outcome,
        client_error_code: timeoutWithhold.stateAtReturn?.errorCode,
      },
    },
  };
  const runUnhandled = [...unhandled];
  run.unhandled = runUnhandled;
  run.checks = evaluateRun(run, runUnhandled);
  run.verdict = run.checks.every((entry) => entry.pass) ? "PASS" : "FAIL";
  runs.push(run);
  writeFileSync(join(EVIDENCE, `${runLabel}.json`), `${JSON.stringify(run, null, 2)}\n`);
  process.stdout.write(
    `${JSON.stringify({
      run: runLabel,
      verdict: run.verdict,
      failed: run.checks.filter((entry) => !entry.pass).map((entry) => entry.id),
    })}\n`,
  );
}

const preservedAfter = s1aDigest();
const frozenStatusAfter = H.gitLines([
  "status",
  "--porcelain",
  "--",
  ...FROZEN_PATHS,
]);
const frozenDiff = H.gitLines([
  "diff",
  "--name-only",
  "HEAD",
  "--",
  ...FROZEN_PATHS,
]);
const m4GuardAfter = checkM4Protection({ cwd: H.ROOT, baseSha: DECLARED_BASELINE });
const repeatable = JSON.stringify(normalizedRun(runs[0])) === JSON.stringify(normalizedRun(runs[1]));
const allChecksPass = runs.every((run) => run.verdict === "PASS");
const p0FilesMatchHead = ["verdict.json", "run1.json", "run2.json", "versions.json"].every(
  (name) =>
    H.sha256File(join(H.P0_DIR, "evidence", name)) ===
    H.sha256GitBlob("HEAD", `validation/cm01/p0-cancellation/evidence/${name}`),
);
const p0Verification = H.readJson(join(H.P0_DIR, "evidence", "verification.json"));
const preservationPass =
  preservedBefore.digest === KNOWN_P0.s1a_digest &&
  preservedAfter.digest === KNOWN_P0.s1a_digest &&
  frozenStatusBefore.length === 0 &&
  frozenStatusAfter.length === 0 &&
  frozenDiff.length === 0 &&
  identities.frozen_executor.sha256 === KNOWN_P0.executor_sha256 &&
  identities.p0_fixture.sha256 === "8f73429e70e04a6876b965bb00a1777fc90409f9da2889c72dab9ac26b9621ea" &&
  identities.fixture.sha256 === "b4d83d0cc0f70f442e2a62bd0e527220ae99b07cba1238e39d0ad8c5685d4e7f" &&
  p0FilesMatchHead &&
  p0Verdict.verdict === KNOWN_P0.verdict &&
  p0Run1.fault?.classification?.pending_immediately_after_timeout === KNOWN_P0.pending_at_timeout &&
  p0Run1.fault?.classification?.pending_after_observation_window === KNOWN_P0.pending_after_window &&
  p0Run1.fault?.classification?.cancellation_notifications_sent ===
    KNOWN_P0.cancellation_notifications_sent &&
  p0Run1.fault?.classification?.late_response_settled_request ===
    KNOWN_P0.late_response_settled_request &&
  p0Verification.verification_status === "VERIFIED" &&
  m4GuardBefore.pass === true &&
  m4GuardAfter.pass === true;
const p0ComparisonPass = runs.every(
  (run) =>
    run.p0_comparison.original.verdict === "FAIL" &&
    run.p0_comparison.original.pending_at_timeout === true &&
    run.p0_comparison.original.cancellation_notifications_sent === 0 &&
    run.p0_comparison.original.late_response_settled_request === true &&
    run.p0_comparison.corrected.client_outcome === "rejected" &&
    run.p0_comparison.corrected.client_error_code === -32001 &&
    run.p0_comparison.corrected.pending_at_deadline === true &&
    run.p0_comparison.corrected.pending_at_execution_return === false &&
    run.p0_comparison.corrected.pending_after_grace === false &&
    run.p0_comparison.corrected.cancellation_notifications_sent === 1 &&
    run.p0_comparison.corrected.late_response_settled_request === false,
);

const latencyMeasurements = [];
for (const run of runs) {
  const collect = (scenario, state) => {
    if (state?.cancellationSentAt && state?.settledAt) {
      latencyMeasurements.push({
        run: run.run,
        scenario,
        abortToSettlementMs: Date.parse(state.settledAt) - Date.parse(state.cancellationSentAt),
      });
    }
  };
  collect("timeout-withhold", run.timeoutWithhold.stateAtReturn);
  for (const iteration of run.repeated.iterations) {
    collect(`repeated-${iteration.index}`, iteration.state);
  }
  collect("parallel-search", run.parallel.search);
  collect("sequential-trace", run.sequential.states["decision.trace"]);
  collect("transport-close", run.transportClose.state);
  collect("timeout-then-close", run.timeoutThenClose.state);
  collect("synthetic", run.synthetic.state);
}
const latencySummary = latencyMeasurements.length
  ? {
      samples: latencyMeasurements.length,
      max_ms: Math.max(...latencyMeasurements.map((entry) => entry.abortToSettlementMs)),
      min_ms: Math.min(...latencyMeasurements.map((entry) => entry.abortToSettlementMs)),
      mean_ms:
        latencyMeasurements.reduce((sum, entry) => sum + entry.abortToSettlementMs, 0) /
        latencyMeasurements.length,
      values: latencyMeasurements,
    }
  : { samples: 0, max_ms: null, min_ms: null, mean_ms: null, values: [] };

const calibrationPath = join(EVIDENCE, "calibration-100ms.json");
const calibration = existsSync(calibrationPath)
  ? {
      file: "evidence/calibration-100ms.json",
      provisional_grace_ms: 100,
      latency: H.readJson(calibrationPath).cancellation_latency,
    }
  : null;

const verdict = {
  schema: "mneme.cm01.p0-f1.verdict/v1",
  started_at: startTime,
  finished_at: H.nowIso(),
  baseline: DECLARED_BASELINE,
  head: H.gitLines(["rev-parse", "HEAD"])[0],
  versions,
  identities,
  host_cancellation_grace_ms: HOST_GRACE_MS,
  grace_decision: {
    provisional_ms: 100,
    final_ms: HOST_GRACE_MS,
    calibration,
    basis:
      calibration && calibration.latency?.max_ms != null
        ? `Final bound ${HOST_GRACE_MS}ms; calibration max was ${calibration.latency.max_ms}ms over ${calibration.latency.samples} cancellations (${(HOST_GRACE_MS / Math.max(calibration.latency.max_ms, 1)).toFixed(1)}x margin).`
        : `Final bound ${HOST_GRACE_MS}ms; calibration evidence unavailable.`,
  },
  cancellation_latency: latencySummary,
  runs: runs.map((run) => ({
    run: run.run,
    verdict: run.verdict,
    checks: run.checks,
    p0_comparison: run.p0_comparison,
  })),
  p0_vs_f1: {
    original_p0: runs[0].p0_comparison.original,
    corrected_f1: runs[0].p0_comparison.corrected,
    classification_changed_from_original: false,
    observed_differences: [
      "MCP client request: pending after executor timeout -> rejected with McpError -32001",
      "Cancellation notifications: 0 -> exactly 1 matching request id",
      "Late withheld response: settled the request -> ignored; request remained rejected",
      "Executor stats: cancelledCalls 0 -> 1; cancelledSettled 1; cancelledUnsettled 0",
    ],
    both_runs_consistent: runs.every(
      (run) =>
        JSON.stringify(run.p0_comparison) === JSON.stringify(runs[0].p0_comparison),
    ),
  },
  repeatable,
  preservation: {
    pass: preservationPass,
    s1a_digest_before: preservedBefore.digest,
    s1a_digest_after: preservedAfter.digest,
    frozen_status_before: frozenStatusBefore,
    frozen_status_after: frozenStatusAfter,
    frozen_diff: frozenDiff,
    m4_guard_before: m4GuardBefore,
    m4_guard_after: m4GuardAfter,
  },
  p0_comparison_pass: p0ComparisonPass,
  unhandled,
  verdict: allChecksPass && repeatable && preservationPass && p0ComparisonPass && unhandled.length === 0 ? "PASS" : "FAIL",
  failed_checks: runs.flatMap((run) =>
    run.checks.filter((entry) => !entry.pass).map((entry) => `${run.run}:${entry.id}`),
  ),
  limitations: [
    "Client settlement and cancellation dispatch are proven; server-side thread termination is not claimed.",
    "The genuine Decision MCP tools are synchronous and fast; in-progress server cancellation is observed only with the synthetic async server.",
    "MCP cancellation notification delivery is fire-and-forget; evidence records transport dispatch and server receipt, not an acknowledgement.",
    "No production code, S1-A2, Cloudflare Workers, or ADR-034 M4 work is included.",
  ],
};

writeFileSync(join(EVIDENCE, "verdict.json"), `${JSON.stringify(verdict, null, 2)}\n`);
writeFileSync(join(EVIDENCE, "versions.json"), `${JSON.stringify(versions, null, 2)}\n`);
writeFileSync(
  join(EVIDENCE, "measurements.json"),
  `${JSON.stringify({ host_cancellation_grace_ms: HOST_GRACE_MS, latency: latencySummary }, null, 2)}\n`,
);
process.stdout.write(
  `${JSON.stringify({
    verdict: verdict.verdict,
    repeatable,
    preservation: preservationPass,
    p0_comparison: p0ComparisonPass,
    failed_checks: verdict.failed_checks,
    latency: { samples: latencySummary.samples, max_ms: latencySummary.max_ms, mean_ms: latencySummary.mean_ms },
  })}\n`,
);
process.exit(verdict.verdict === "PASS" ? 0 : 1);


