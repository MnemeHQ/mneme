import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const B0_DIR = dirname(fileURLToPath(import.meta.url));
const CM01_DIR = dirname(B0_DIR);
const ROOT = resolve(B0_DIR, "../../..");
const EVIDENCE = join(B0_DIR, "evidence");
const RAW = join(EVIDENCE, "raw");
const FIXTURE = join(B0_DIR, "fixture", "project_memory.json");
const TASKS = join(B0_DIR, "tasks.json");
const SUPPLEMENTAL_DIR = join(B0_DIR, "supplemental");
const SUPPLEMENTAL_RECORD = join(SUPPLEMENTAL_DIR, "verification.json");
const SUPPLEMENTAL_HASH = join(SUPPLEMENTAL_DIR, "verification.sha256");
const BASELINE = "f8591102b2693379dabec9b5704862e194eca4ce";
const FIXTURE_SHA = "a996e2aa5c2d41bf8a75293c8d60adebf9ab89eb59caea926fbccf97297a1dca";
const TASKS_SHA = "7aaa196a72b52726ea6db7e46db612c6a6abc0f2bf7f3d5f3a13be2822e163b6";
const PACKAGE_LOCK_SHA = "c9850209a6330a810fbf2f784427eca6c89df4cce71fb6ec49564fee01c55e9f";
const ORIGINAL_MANIFEST_SHA = "94dd0ee381fba2e9775634e0fc8f005dfeb59c9b874fd022227c6fcb92ed17ac";
const ORIGINAL_EVIDENCE_FILE_COUNT = 111;
const F1_EXECUTOR_SHA = "0d81093b20fa0b77a3fc9f2e6b4a90bf184668d0377242c3e4f37e64afd9d2b1";
const F1_ADAPTER_SHA = "3d8123975bc9f67147fec90ff3e6911a08e40a7f2dc4bd7b43da14b0530cb08c";
const F1_RELAY_SHA = "536f32e7869fc407782b1c1db7d55afc3bd383bc0ede405f40d6f08b45e0f5e5";
const F1_RUNNER_SHA = "55a40f182df80bf7f3828e165601758298912eaa7f6285ef0772cc967103e830";
const F1_HARNESS_SHA = "3b2a7591614dd19532e3d7a5064e403ea4d58e73e73e305009b9d67385ba8076";
const FROZEN_EXECUTOR_SHA = "4b960124e9218ed124ed34e3b3595b648477b9dab6540c4ce1609d2efaf31313";
const M4_GUARD_SHA = "7df06ddb301355d2a040e2a3d04e915f513f36177d640e40b5224b7ca9d128a6";
const F1_PACKAGE_LOCK_SHA = "4f4f81b24f31490ff1a1d3f5c1a33fd359d1545567f91daffaa56abaa8e63167";
const S1A_DIGEST = "cc7f884866e6e94255b100de57b82eec4a51660aadaf51c6464198131030af57";
const NOT_MEASURED = "NOT_MEASURED";
const READ_TOOLS = ["decision.get", "decision.search", "decision.applicable_to", "decision.trace"];
const SIX_TOOLS = [
  "decision.propose",
  "decision.propose_batch",
  "decision.get",
  "decision.search",
  "decision.applicable_to",
  "decision.trace",
];
const EXPECTED_CALLS = {
  T1: ["decision.get"],
  T2: ["decision.search"],
  T3: ["decision.applicable_to"],
  T4: ["decision.trace"],
  T5: ["decision.search", "decision.get"],
  T6: ["decision.search", "decision.trace"],
  T7: ["decision.applicable_to", "decision.get", "decision.trace"],
  T8: ["decision.search", "decision.get", "decision.get"],
};

const checks = [];
const check = (id, pass, detail = null) => checks.push({ id, pass: Boolean(pass), detail });

function sha256File(file) {
  return createHash("sha256").update(readFileSync(file)).digest("hex");
}
function sha256Text(text) {
  return createHash("sha256").update(text, "utf8").digest("hex");
}
function readJson(file) {
  return JSON.parse(readFileSync(file, "utf8"));
}
function readJsonl(file) {
  return readFileSync(file, "utf8")
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
    .map((file) => relative(EVIDENCE, file).split("\\").join("/"))
    .filter((file) => file !== "verification.json")
    .sort();
  const hashes = Object.fromEntries(
    files.map((file) => [file, sha256File(join(EVIDENCE, ...file.split("/")))]),
  );
  return { files: hashes, digest: sha256Text(JSON.stringify(hashes)) };
}
function s1aDigest() {
  const files = gitLines(["ls-files", "validation/cm01/s1a-local"]).sort();
  const hashes = Object.fromEntries(
    files.map((file) => [file, sha256File(join(ROOT, ...file.split("/")))]),
  );
  return sha256Text(JSON.stringify(hashes));
}
function indexOf(document) {
  const index = document.decision_index;
  const decisions = Object.fromEntries(index.decisions.map((row) => [row.decision_id, row]));
  const versions = Object.fromEntries(index.versions.map((row) => [row.version_id, row]));
  const rules = {};
  for (const rule of index.rules) {
    rules[rule.decision_id] ??= [];
    rules[rule.decision_id].push(rule);
  }
  return { decisions, versions, rules };
}
function fixtureGet(document, decisionId) {
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
function fixtureTrace(document, decisionId) {
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
function fixtureSearch(document, query, lifecycle = null) {
  const { decisions, versions } = indexOf(document);
  const needle = String(query).toLowerCase();
  return Object.entries(decisions)
    .filter(([, record]) => lifecycle === null || record.lifecycle_status === lifecycle)
    .filter(([id, record]) => {
      const version = versions[record.active_version_id];
      return [id, version.statement, version.rationale, ...version.context_scope].some((value) =>
        String(value).toLowerCase().includes(needle),
      );
    })
    .map(([id]) => id)
    .sort();
}
function fixtureApplicable(document, context) {
  const { decisions, versions } = indexOf(document);
  const needle = String(context).toLowerCase();
  return Object.entries(decisions)
    .filter(([, record]) => {
      const version = versions[record.active_version_id];
      return version.context_scope.some((scope) => scope.toLowerCase().includes(needle));
    })
    .map(([id]) => id)
    .sort();
}
function fixtureExpected(document, task) {
  switch (task.id) {
    case "T1":
      return fixtureGet(document, task.params.record_id);
    case "T2": {
      const ids = fixtureSearch(document, task.params.query, task.params.canonical_lifecycle_status);
      return { canonical_ids: ids, count: ids.length };
    }
    case "T3": {
      const ids = fixtureApplicable(document, task.params.context[0]);
      return { canonical_ids: ids, count: ids.length };
    }
    case "T4":
      return fixtureTrace(document, task.params.record_id);
    case "T5":
      return fixtureGet(
        document,
        fixtureSearch(document, task.params.query, task.params.canonical_lifecycle_status)[0],
      );
    case "T6":
      return fixtureTrace(
        document,
        fixtureSearch(document, task.params.query, task.params.canonical_lifecycle_status)[0],
      );
    case "T7": {
      const index = indexOf(document);
      const id = fixtureApplicable(document, task.params.context[0]).filter(
        (candidate) => index.decisions[candidate].lifecycle_status === "active",
      )[0];
      return { selected_id: id, get: fixtureGet(document, id), trace: fixtureTrace(document, id) };
    }
    case "T8": {
      const index = indexOf(document);
      const ids = fixtureSearch(document, task.params.query, task.params.canonical_lifecycle_status)
        .filter((id) => (index.rules[id] ?? []).length > 0)
        .slice(0, 2);
      return {
        items: ids.map((id) => {
          const projection = fixtureGet(document, id);
          return {
            decision_id: id,
            version: projection.version,
            content_digest: projection.content_digest,
            derived_rule_ids: projection.derived_rule_ids,
          };
        }),
      };
    }
    default:
      throw new Error(`unknown task ${task.id}`);
  }
}
function projectGet(structuredContent) {
  const record = structuredContent.canonical_decision;
  return {
    decision_id: record.decision_id,
    version: record.version,
    version_id: record.version_id,
    content_digest: record.content_digest,
    lifecycle_status: record.lifecycle_status,
    context_scope: record.context_scope,
    derived_rule_ids: record.derived_rule_ids,
  };
}
function projectTrace(structuredContent) {
  const record = structuredContent.canonical_record;
  return {
    canonical_decision_id: structuredContent.canonical_decision_id,
    version: record.version,
    version_id: record.version_id,
    content_digest: record.content_digest,
    derived_rule_ids: structuredContent.derived_rules.map((rule) => rule.rule_id),
    declared_test_evidence: structuredContent.declared_test_evidence ?? [],
  };
}
function reconstruct(task, calls) {
  switch (task.id) {
    case "T1":
      return projectGet(calls[0].structuredContent);
    case "T2": {
      const ids = calls[0].structuredContent.canonical_decisions.map((row) => row.decision_id).sort();
      return { canonical_ids: ids, count: ids.length };
    }
    case "T3": {
      const ids = calls[0].structuredContent.canonical_scope_matches
        .map((row) => row.decision_id)
        .sort();
      return { canonical_ids: ids, count: ids.length };
    }
    case "T4":
      return projectTrace(calls[0].structuredContent);
    case "T5":
      return projectGet(calls[1].structuredContent);
    case "T6":
      return projectTrace(calls[1].structuredContent);
    case "T7": {
      const ids = calls[0].structuredContent.canonical_scope_matches
        .filter((row) => row.lifecycle_status === "active")
        .map((row) => row.decision_id)
        .sort();
      return {
        selected_id: ids[0],
        get: projectGet(calls[1].structuredContent),
        trace: projectTrace(calls[2].structuredContent),
      };
    }
    case "T8":
      return {
        items: calls.slice(1).map((call) => {
          const projection = projectGet(call.structuredContent);
          return {
            decision_id: projection.decision_id,
            version: projection.version,
            content_digest: projection.content_digest,
            derived_rule_ids: projection.derived_rule_ids,
          };
        }),
      };
    default:
      throw new Error(`unknown task ${task.id}`);
  }
}
function readPhase(run, task, arm) {
  const file = join(RAW, `${run}-${task.id}-${arm}-transport.jsonl`);
  const lines = readJsonl(file);
  const outbound = lines.filter((entry) => entry.dir === "out");
  const inbound = lines.filter((entry) => entry.dir === "in");
  const initialize = outbound.find((entry) => entry.message?.method === "initialize")?.message;
  const listOut = outbound.find((entry) => entry.message?.method === "tools/list")?.message;
  const listIn = inbound.find((entry) => entry.message?.id === listOut?.id)?.message;
  const calls = outbound
    .filter((entry) => entry.message?.method === "tools/call")
    .map((entry) => {
      const request = entry.message;
      const response = inbound.find((candidate) => candidate.message?.id === request.id)?.message;
      return {
        request,
        response,
        name: request.params?.name,
        args: request.params?.arguments,
        request_id: request.id,
        response_bytes: response ? JSON.stringify(response).length : 0,
        structuredContent: response?.result?.structuredContent ?? null,
      };
    });
  return { lines, outbound, inbound, initialize, listOut, listIn, calls };
}
function readHarness(run, task, arm) {
  return readJsonl(join(RAW, `${run}-${task.id}-${arm}-harness.jsonl`));
}

const manifest = evidenceManifest();
const originalVerdict = readJson(join(EVIDENCE, "verdict.json"));
const originalVerification = readJson(join(EVIDENCE, "verification.json"));
const runs = {
  run1: readJson(join(EVIDENCE, "run1.json")),
  run2: readJson(join(EVIDENCE, "run2.json")),
};
const fixture = readJson(FIXTURE);
const tasksDocument = readJson(TASKS);

check(
  "SUP-ORIGINAL-MANIFEST",
  Object.keys(manifest.files).length === ORIGINAL_EVIDENCE_FILE_COUNT &&
    manifest.digest === ORIGINAL_MANIFEST_SHA,
  { file_count: Object.keys(manifest.files).length, digest: manifest.digest },
);
check(
  "SUP-FIXTURE-HASH",
  sha256File(FIXTURE) === FIXTURE_SHA && originalVerdict.fixture.sha256 === FIXTURE_SHA,
  { sha256: sha256File(FIXTURE) },
);
check(
  "SUP-TASKS-HASH",
  sha256File(TASKS) === TASKS_SHA && originalVerdict.tasks.sha256 === TASKS_SHA,
  { sha256: sha256File(TASKS) },
);
check(
  "SUP-PACKAGE-LOCK-HASH",
  sha256File(join(B0_DIR, "package-lock.json")) === PACKAGE_LOCK_SHA &&
    originalVerdict.source_hashes.package_lock === PACKAGE_LOCK_SHA,
  { sha256: sha256File(join(B0_DIR, "package-lock.json")) },
);
check(
  "SUP-ORIGINAL-VERDICT",
  originalVerdict.verdict === "PASS" &&
    originalVerdict.baseline === BASELINE &&
    originalVerdict.repeatable === true &&
    originalVerdict.preservation.pass === true &&
    originalVerdict.failed_checks.length === 0 &&
    originalVerdict.unhandled.length === 0 &&
    originalVerdict.model_fields.status === NOT_MEASURED &&
    Object.values(runs).every(
      (run) =>
        run.verdict === "PASS" &&
        run.checks.length === 39 &&
        run.checks.every((entry) => entry.pass === true),
    ),
  {
    verdict: originalVerdict.verdict,
    runs: Object.fromEntries(
      Object.entries(runs).map(([name, run]) => [name, { verdict: run.verdict, checks: run.checks.length }]),
    ),
  },
);
check(
  "SUP-ORIGINAL-VERIFICATION",
  originalVerification.verification_status === "VERIFIED" &&
    originalVerification.original_verdict === "PASS" &&
    originalVerification.checks.length === 14 &&
    originalVerification.checks.every((entry) => entry.pass === true) &&
    originalVerification.reproduction?.performed === true &&
    originalVerification.reproduction?.exit_code === 0 &&
    originalVerification.reproduction?.checks?.length === 4 &&
    originalVerification.reproduction.checks.every((entry) => entry.pass === true) &&
    originalVerification.canonical_evidence.digest_before === ORIGINAL_MANIFEST_SHA &&
    originalVerification.canonical_evidence.digest_after === ORIGINAL_MANIFEST_SHA,
  {
    status: originalVerification.verification_status,
    static_checks: originalVerification.checks.length,
    reproduction_checks: originalVerification.reproduction?.checks?.length ?? null,
  },
);
check(
  "SUP-F1-HASHES",
  sha256File(join(CM01_DIR, "p0-f1", "quickjs-executor.mjs")) === F1_EXECUTOR_SHA &&
    sha256File(join(CM01_DIR, "p0-f1", "adapter.mjs")) === F1_ADAPTER_SHA &&
    sha256File(join(CM01_DIR, "p0-f1", "relay.mjs")) === F1_RELAY_SHA &&
    sha256File(join(CM01_DIR, "p0-f1", "run-f1.mjs")) === F1_RUNNER_SHA &&
    sha256File(join(CM01_DIR, "p0-f1", "harness.mjs")) === F1_HARNESS_SHA &&
    sha256File(join(CM01_DIR, "p0-f1", "package-lock.json")) === F1_PACKAGE_LOCK_SHA &&
    sha256File(join(CM01_DIR, "s1a-local", "e0", "quickjs-executor.mjs")) === FROZEN_EXECUTOR_SHA &&
    sha256File(join(CM01_DIR, "s1a-local", "m4-guard.mjs")) === M4_GUARD_SHA,
  {
    f1_executor: F1_EXECUTOR_SHA,
    f1_adapter: F1_ADAPTER_SHA,
    f1_relay: F1_RELAY_SHA,
    f1_runner: F1_RUNNER_SHA,
    f1_harness: F1_HARNESS_SHA,
    frozen_executor: FROZEN_EXECUTOR_SHA,
  },
);
check("SUP-S1A-DIGEST", s1aDigest() === S1A_DIGEST, { digest: s1aDigest() });

const p0Verdict = readJson(join(CM01_DIR, "p0-cancellation", "evidence", "verdict.json"));
const p0Verification = readJson(join(CM01_DIR, "p0-cancellation", "evidence", "verification.json"));
const f1Verdict = readJson(join(CM01_DIR, "p0-f1", "evidence", "verdict.json"));
const f1Verification = readJson(join(CM01_DIR, "p0-f1", "evidence", "verification.json"));
const preservedStatus = gitLines([
  "status",
  "--porcelain",
  "--",
  "validation/cm01/s1a-local",
  "validation/cm01/p0-cancellation",
  "validation/cm01/p0-f1",
]);
const preservedDiff = gitLines([
  "diff",
  "--name-only",
  "HEAD",
  "--",
  "validation/cm01/s1a-local",
  "validation/cm01/p0-cancellation",
  "validation/cm01/p0-f1",
  "mneme",
]);
check(
  "SUP-P0-F1-PRESERVATION",
  p0Verdict.verdict === "FAIL" &&
    p0Verification.verification_status === "VERIFIED" &&
    f1Verdict.verdict === "PASS" &&
    f1Verification.verification_status === "VERIFIED" &&
    preservedStatus.length === 0 &&
    preservedDiff.length === 0,
  {
    p0: p0Verdict.verdict,
    p0_verification: p0Verification.verification_status,
    f1: f1Verdict.verdict,
    f1_verification: f1Verification.verification_status,
    preserved_status: preservedStatus,
    preserved_diff: preservedDiff,
  },
);

const status = gitLines(["status", "--porcelain", "--untracked-files=all"]);
const outsideB0 = status.filter(
  (line) =>
    !line.includes("validation/cm01/b0-benchmark/") &&
    !line.includes(".mneme/task_context.json"),
);
check("SUP-REPO-SCOPE", outsideB0.length === 0, { outside_count: outsideB0.length, outside: outsideB0 });

const modelFields = [];
let genuineMcp = true;
let toolInventoryOk = true;
let noProposal = true;
let cleanupOk = true;
const pids = [];
const perTask = {};
const perPhase = {};

for (const runName of ["run1", "run2"]) {
  const run = runs[runName];
  const runTasks = new Map(run.tasks.map((task) => [task.id, task]));
  for (const task of tasksDocument.tasks) {
    const recordedTask = runTasks.get(task.id);
    const phaseResults = {};
    for (const arm of ["direct", "code"]) {
      const recorded = recordedTask.results[arm];
      const phase = readPhase(runName, task, arm);
      const harness = readHarness(runName, task, arm);
      const connected = harness.find((entry) => entry.type === "connected_direct");
      const cleanup = harness.find((entry) => entry.type === "cleanup_direct");
      if (connected) pids.push(connected.pid);
      genuineMcp &&= phase.initialize?.params?.clientInfo?.name === "cm01-f1";
      genuineMcp &&= phase.initialize?.id === 0;
      genuineMcp &&= phase.listOut?.id === 1;
      genuineMcp &&= Boolean(phase.listIn);
      genuineMcp &&= connected?.tools === 6;
      toolInventoryOk &&= equal((phase.listIn?.result?.tools ?? []).map((tool) => tool.name), SIX_TOOLS);
      noProposal &&= phase.calls.every((call) => READ_TOOLS.includes(call.name));
      cleanupOk &&= cleanup?.errors?.length === 0 && cleanup?.server_alive_after === false;
      modelFields.push(
        recorded.model_turns === NOT_MEASURED &&
          recorded.input_tokens === NOT_MEASURED &&
          recorded.output_tokens === NOT_MEASURED &&
          recorded.intermediate_context_model_tokens === NOT_MEASURED,
      );
      const expectedNames = EXPECTED_CALLS[task.id];
      const callMeta = phase.calls.map((call) => ({
        name: call.name,
        args: call.args,
        request_id: call.request_id,
        result_bytes: call.response_bytes,
      }));
      const recordedMeta = recorded.mcp_calls.map((call) => ({
        name: call.name,
        args: call.args,
        request_id: call.request_id,
        result_bytes: call.result_bytes,
      }));
      const actual = reconstruct(task, phase.calls);
      const fixtureAnswer = fixtureExpected(fixture, task);
      const callsOk =
        equal(phase.calls.map((call) => call.name), expectedNames) &&
        equal(phase.calls.map((call) => call.request_id), expectedNames.map((_, index) => index + 2)) &&
        equal(callMeta, recordedMeta) &&
        recorded.mcp_call_count === phase.calls.length &&
        recorded.mcp_result_bytes === callMeta.reduce((sum, call) => sum + call.result_bytes, 0) &&
        recorded.result_bytes === JSON.stringify(recorded.actual).length;
      check(`SUP-CALLS-${runName}-${task.id}-${arm}`, callsOk, {
        expectedNames,
        observedNames: phase.calls.map((call) => call.name),
      });
      const actualOk =
        equal(actual, recorded.actual) &&
        equal(actual, task.expected) &&
        equal(fixtureAnswer, task.expected) &&
        recorded.decision_identity_ok === true &&
        recorded.ok === true &&
        recorded.no_proposal === true &&
        recorded.cleanup?.errors?.length === 0 &&
        recorded.process_cleanup_ok === true &&
        recorded.host_calls === (arm === "code" ? phase.calls.length : 0);
      check(`SUP-ACTUAL-${runName}-${task.id}-${arm}`, actualOk, null);
      phaseResults[arm] = {
        actual,
        payloads: phase.calls.map((call) => call.structuredContent),
        callMeta,
      };
    }
    const equivalent =
      equal(phaseResults.direct.actual, phaseResults.code.actual) &&
      equal(phaseResults.direct.payloads, phaseResults.code.payloads) &&
      equal(
        phaseResults.direct.callMeta.map((call) => ({ name: call.name, args: call.args })),
        phaseResults.code.callMeta.map((call) => ({ name: call.name, args: call.args })),
      );
    check(`SUP-EQUIVALENT-${runName}-${task.id}`, equivalent, null);
    perTask[`${runName}:${task.id}`] = phaseResults;
    perPhase[`${runName}:${task.id}`] = true;
  }
}

check(
  "SUP-GENUINE-MCP",
  genuineMcp && pids.length === 32 && new Set(pids).size === pids.length,
  { phases: pids.length, unique_pids: new Set(pids).size },
);
check("SUP-TOOL-INVENTORY", toolInventoryOk, { expected: SIX_TOOLS, phases_checked: Object.keys(perPhase).length * 2 });
check("SUP-NO-PROPOSAL", noProposal, { called: READ_TOOLS });
check(
  "SUP-MODEL-NOT-MEASURED",
  modelFields.every(Boolean) && originalVerdict.model_fields.status === NOT_MEASURED,
  { fields: modelFields.length },
);

let repeatable = true;
for (const task of tasksDocument.tasks) {
  for (const arm of ["direct", "code"]) {
    repeatable &&= equal(perTask[`run1:${task.id}`][arm].actual, perTask[`run2:${task.id}`][arm].actual);
  }
}
check("SUP-REPEATABLE", repeatable, null);

const cancellationDetails = [];
let cancellationOk = true;
for (const runName of ["run1", "run2"]) {
  const run = runs[runName];
  const relay = readJsonl(join(RAW, `${runName}-cancellation-relay.jsonl`));
  const child = readJsonl(join(RAW, `${runName}-cancellation-child-events.jsonl`));
  const childInit = child
    .filter((entry) => entry.type === "child_stdout_line")
    .map((entry) => JSON.parse(entry.line))
    .find((message) => message.id === 0);
  const withheld = relay.filter((entry) => entry.type === "response_withheld").length;
  const cancelled = relay.filter((entry) => entry.type === "cancel_from_client").length;
  const released = relay.filter((entry) => entry.type === "response_released_downstream").length;
  const childCancels = child.filter(
    (entry) => entry.type === "child_stdin_line" && /notifications\/cancelled/.test(entry.line),
  ).length;
  const childExit = child.find((entry) => entry.type === "child_exit");
  const relayExit = relay.find((entry) => entry.type === "child_exit");
  const result = run.cancellation;
  const runOk =
    result.ok === true &&
    result.withheld === true &&
    result.cancellation_count === 1 &&
    result.state?.outcome === "rejected" &&
    result.state?.errorCode === -32001 &&
    result.state?.pending === false &&
    result.stats?.cancelledCalls === 1 &&
    result.stats?.cancelledSettled === 1 &&
    result.stats?.cancelledUnsettled === 0 &&
    result.cleanup?.errors?.length === 0 &&
    result.cleanup?.relay_alive_after === false &&
    result.cleanup?.upstream_alive_after === false &&
    withheld === 1 &&
    cancelled === 1 &&
    released === 1 &&
    childCancels === 1 &&
    childExit?.code === 0 &&
    relayExit?.code === 0 &&
    childInit?.result?.serverInfo?.name === "mneme-decision-index";
  cancellationOk &&= runOk;
  cancellationDetails.push({
    run: runName,
    withheld,
    cancelled,
    released,
    childCancels,
    childExit: childExit?.code,
    relayExit: relayExit?.code,
    server: childInit?.result?.serverInfo?.name ?? null,
  });
}
check("SUP-CANCELLATION", cancellationOk, cancellationDetails);
check("SUP-CLEANUP", cleanupOk, null);

const verifierSha = sha256File(fileURLToPath(import.meta.url));
const protectedPaths = [
  "validation/cm01/b0-benchmark/fixture/project_memory.json",
  "validation/cm01/b0-benchmark/tasks.json",
  "validation/cm01/b0-benchmark/package.json",
  "validation/cm01/b0-benchmark/package-lock.json",
  "validation/cm01/b0-benchmark/arms.mjs",
  "validation/cm01/b0-benchmark/run-b0m.mjs",
  "validation/cm01/b0-benchmark/make-corpus.py",
  "validation/cm01/b0-benchmark/make-tasks.py",
  "validation/cm01/b0-benchmark/verify-b0m-evidence.mjs",
  "validation/cm01/b0-benchmark/verify-b0m-supplemental.mjs",
  ...Object.keys(manifest.files).map((file) => `validation/cm01/b0-benchmark/evidence/${file}`),
];
const attributeOutput = execFileSync("git", ["check-attr", "text", "--", ...protectedPaths], {
  cwd: ROOT,
  encoding: "utf8",
  maxBuffer: 8 * 1024 * 1024,
});
const attributeMap = Object.fromEntries(
  attributeOutput
    .trim()
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => {
      const marker = line.lastIndexOf(": text: ");
      return [line.slice(0, marker), line.slice(marker + 8)];
    }),
);
const attributesOk =
  Object.keys(attributeMap).length === protectedPaths.length &&
  protectedPaths.every((path) => attributeMap[path] === "unset");
check("SUP-BYTES-ATTRIBUTES", attributesOk, {
  checked: protectedPaths.length,
  failures: protectedPaths.filter((path) => attributeMap[path] !== "unset"),
});

const originalVerificationSha = sha256File(join(EVIDENCE, "verification.json"));
const allPass = checks.every((entry) => entry.pass);
const statusValue = allPass ? "VERIFIED" : "BLOCKED";
const generatedAt = process.env.CM01_SUPPLEMENTAL_GENERATED_AT || new Date().toISOString();
const record = {
  schema: "mneme.cm01.b0m.supplemental-verification/v1",
  generated_at: generatedAt,
  verification_status: statusValue,
  scope: "read-only supplemental verification of original CM-01-B0-M evidence",
  baseline: BASELINE,
  original_verdict: "PASS",
  original_verdict_preserved: true,
  original_verification: {
    status: originalVerification.verification_status,
    static_checks: originalVerification.checks.length,
    reproduction_checks: originalVerification.reproduction?.checks?.length ?? null,
    sha256: originalVerificationSha,
  },
  original_evidence: {
    file_count: Object.keys(manifest.files).length,
    manifest_sha256: manifest.digest,
    historical_manifest_sha256: ORIGINAL_MANIFEST_SHA,
    unchanged: manifest.digest === ORIGINAL_MANIFEST_SHA,
    coverage: "all files under evidence/ except verification.json",
  },
  supplemental_evidence: {
    record_path: "supplemental/verification.json",
    hash_file: "supplemental/verification.sha256",
    coverage: "supplemental record only; outside the original evidence manifest",
    verifier_path: "verify-b0m-supplemental.mjs",
    verifier_sha256: verifierSha,
  },
  hashes: {
    fixture_sha256: FIXTURE_SHA,
    tasks_sha256: TASKS_SHA,
    package_lock_sha256: PACKAGE_LOCK_SHA,
    original_evidence_manifest_sha256: ORIGINAL_MANIFEST_SHA,
    f1_executor_sha256: F1_EXECUTOR_SHA,
    f1_adapter_sha256: F1_ADAPTER_SHA,
    f1_relay_sha256: F1_RELAY_SHA,
    f1_runner_sha256: F1_RUNNER_SHA,
    f1_harness_sha256: F1_HARNESS_SHA,
    frozen_executor_sha256: FROZEN_EXECUTOR_SHA,
    f1_package_lock_sha256: F1_PACKAGE_LOCK_SHA,
    m4_guard_sha256: M4_GUARD_SHA,
    s1a_digest: S1A_DIGEST,
  },
  checks,
  summary: {
    total_checks: checks.length,
    failed_checks: checks.filter((entry) => !entry.pass).map((entry) => entry.id),
    verification_status: statusValue,
  },
  observations: {
    inbound_initialize_logged_for_task_transports: false,
    inbound_initialize_note:
      "Task transport logs begin after the client installs incoming-message logging. Cancellation child events contain the initialize response and serverInfo.",
    pids: pids.length,
    unique_pids: new Set(pids).size,
  },
  model_fields: {
    model_turns: NOT_MEASURED,
    input_tokens: NOT_MEASURED,
    output_tokens: NOT_MEASURED,
    intermediate_context_model_tokens: NOT_MEASURED,
    efficiency: NOT_MEASURED,
  },
  limitations: [
    "Two sequential executions within one Node process, each using fresh MCP child processes, followed by independent fresh-worktree reproduction.",
    "Original raw transport logs do not contain the full MCP initialize exchange.",
    "Mechanical timing excludes some lifecycle overhead.",
    "Model tokens and turns are NOT_MEASURED.",
    "The ground truth is derived from the frozen fixture.",
    "B0-A statistical power has not been validated.",
    "No B0 protocol document is committed or preregistered in this repository; tasks.json and make-tasks.py are the executable task definitions.",
  ],
  provenance: {
    change_author: "agent",
    agent: "opencode",
    agent_model: "opencode-go/deepseek-v4.1-flash",
    agent_session: "not-exposed",
    task_origin: "local",
  },
};

mkdirSync(SUPPLEMENTAL_DIR, { recursive: true });
const serialized = `${JSON.stringify(record, null, 2)}\n`;
writeFileSync(SUPPLEMENTAL_RECORD, serialized, "utf8");
const recordSha = sha256Text(serialized);
writeFileSync(SUPPLEMENTAL_HASH, `${recordSha}  verification.json\n`, "utf8");

process.stdout.write(
  `${JSON.stringify({
    verification_status: statusValue,
    total_checks: checks.length,
    failed_checks: record.summary.failed_checks,
    original_evidence_manifest: manifest.digest,
    supplemental_record_sha256: recordSha,
    supplemental_hash_path: "supplemental/verification.sha256",
  })}\n`,
);
process.exit(allPass ? 0 : 1);
