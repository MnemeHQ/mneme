import { spawn } from "node:child_process";
import { appendFileSync, createWriteStream } from "node:fs";
import net from "node:net";
import readline from "node:readline";

const ENV = process.env;
const CONTROL_PORT = Number(ENV.CM01_CONTROL_PORT);
const CONTROL_TOKEN = ENV.CM01_CONTROL_TOKEN;
const MODE = ENV.CM01_RELAY_MODE || "passthrough";
const DELAY_MS = Number(ENV.CM01_DELAY_MS || 0);
const WITHHOLD_TOOLS = new Set(
  (ENV.CM01_WITHHOLD_TOOLS || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean),
);
const EVENT_LOG = ENV.CM01_EVENT_LOG;
const CHILD_STDERR = ENV.CM01_CHILD_STDERR;
const CHILD_EVENT_LOG = ENV.CM01_CHILD_EVENT_LOG;

let seq = 0;
let control = null;
const pendingControlWrites = [];

function emit(type, data = {}) {
  const event = { seq: ++seq, ts: new Date().toISOString(), pid: process.pid, type, ...data };
  const line = `${JSON.stringify(event)}\n`;
  try {
    appendFileSync(EVENT_LOG, line);
  } catch (error) {
    process.stderr.write(`[f1-relay] event-log-error ${error.message}\n`);
  }
  process.stderr.write(`[f1-relay] ${line}`);
  if (control && !control.destroyed) control.write(line);
  else pendingControlWrites.push(line);
}

function startControl() {
  const attempt = () => {
    const socket = net.createConnection({ host: "127.0.0.1", port: CONTROL_PORT });
    let settled = false;
    socket.once("connect", () => {
      settled = true;
      control = socket;
      socket.write(`${JSON.stringify({ token: CONTROL_TOKEN, role: "relay" })}\n`);
      for (const line of pendingControlWrites.splice(0)) socket.write(line);
      readline.createInterface({ input: socket }).on("line", (line) => {
        if (!line.trim()) return;
        try {
          handleCommand(JSON.parse(line));
        } catch {
          emit("control_parse_error", { line });
        }
      });
      socket.on("error", (error) => emit("control_error", { message: error.message }));
    });
    socket.on("error", () => {
      if (!settled) {
        socket.destroy();
        setTimeout(attempt, 20);
      }
    });
  };
  attempt();
}

const child = spawn(
  ENV.CM01_PYTHON || "python",
  [
    "-m",
    "mneme",
    "decision-mcp",
    "--memory",
    ENV.CM01_FIXTURE,
    "--proposals",
    "",
  ],
  {
    cwd: ENV.CM01_EMPTY_CWD,
    env: {
      ...process.env,
      PYTHONPATH: ENV.CM01_ROOT,
      PYTHONIOENCODING: "utf-8",
    },
    stdio: ["pipe", "pipe", "pipe"],
    windowsHide: true,
    shell: false,
  },
);

const childStderr = createWriteStream(CHILD_STDERR, { flags: "a" });
child.stderr.pipe(childStderr);
child.stderr.on("data", (chunk) => process.stderr.write(`[upstream-stderr] ${chunk}`));

let childSeq = 0;
function emitChild(type, data = {}) {
  const event = {
    seq: ++childSeq,
    ts: new Date().toISOString(),
    upstream_pid: child.pid ?? null,
    type,
    ...data,
  };
  try {
    appendFileSync(CHILD_EVENT_LOG, `${JSON.stringify(event)}\n`);
  } catch (error) {
    process.stderr.write(`[f1-relay] child-event-log-error ${error.message}\n`);
  }
}

emitChild("child_spawn", {
  fixture: ENV.CM01_FIXTURE,
  cwd: ENV.CM01_EMPTY_CWD,
  command: ENV.CM01_PYTHON || "python",
});
emit("relay_start", {
  mode: MODE,
  delay_ms: DELAY_MS,
  withhold_tools: [...WITHHOLD_TOOLS],
  upstream_pid: child.pid,
  control_port: CONTROL_PORT,
  event_log: EVENT_LOG,
});

let childExited = false;
let shuttingDown = false;
const held = new Map();
const delayed = new Map();
const targetRequests = new Map();
const cancellationEvents = [];
let targetRequestCount = 0;

function targetTool(tool) {
  if (WITHHOLD_TOOLS.size === 0) return true;
  return WITHHOLD_TOOLS.has(tool);
}

function inspectClientMessage(message) {
  if (!message || typeof message !== "object") return;
  if (message.method === "notifications/cancelled") {
    const event = {
      requestId: message.params?.requestId ?? null,
      reason: message.params?.reason ?? null,
    };
    cancellationEvents.push(event);
    emit("cancel_from_client", event);
  }
  if (message.method === "tools/call") {
    targetRequestCount += 1;
    const tool = message.params?.name ?? null;
    const requestId = message.id ?? null;
    emit("tools_call_from_client", { requestId, tool, seq: targetRequestCount });
    if (targetTool(tool)) {
      targetRequests.set(requestId, {
        requestId,
        tool,
        mode: MODE,
        delayMs: DELAY_MS,
      });
      emit("target_request_seen", {
        requestId,
        tool,
        mode: MODE,
        delayMs: DELAY_MS,
      });
    }
  }
}

function forwardUpstream(line) {
  if (childExited || child.stdin.destroyed) {
    emit("upstream_forward_dropped", { line });
    return;
  }
  emitChild("child_stdin_line", { line });
  child.stdin.write(`${line}\n`);
}

function forwardDownstream(line, requestId, how) {
  process.stdout.write(`${line}\n`);
  emit("response_forwarded_downstream", { requestId, how });
}

function inspectUpstreamMessage(message, rawLine) {
  if (!message || typeof message !== "object") return false;
  const isResponse =
    message.id !== undefined && (message.result !== undefined || message.error !== undefined);
  if (!isResponse) return false;
  const target = targetRequests.get(message.id);
  if (!target) return false;

  targetRequests.delete(message.id);
  emit("upstream_response_received", {
    requestId: message.id,
    tool: target.tool,
    has_result: message.result !== undefined,
    has_error: message.error !== undefined,
  });

  if (MODE === "withhold") {
    held.set(message.id, { line: rawLine, tool: target.tool });
    emit("response_withheld", { requestId: message.id, tool: target.tool });
    return true;
  }

  if (MODE === "delay" && DELAY_MS > 0) {
    emit("response_delayed", {
      requestId: message.id,
      tool: target.tool,
      delayMs: DELAY_MS,
    });
    const timer = setTimeout(() => {
      delayed.delete(message.id);
      forwardDownstream(rawLine, message.id, "delay");
    }, DELAY_MS);
    delayed.set(message.id, { line: rawLine, tool: target.tool, timer });
    return true;
  }

  forwardDownstream(rawLine, message.id, "target");
  return true;
}

const clientReader = readline.createInterface({ input: process.stdin });
clientReader.on("line", (line) => {
  if (!line.trim()) return;
  let message;
  try {
    message = JSON.parse(line);
  } catch {
    emit("client_parse_error", { line });
    forwardUpstream(line);
    return;
  }
  inspectClientMessage(message);
  if (message?.method === "tools/call" && targetRequests.has(message.id)) {
    emit("target_request_forwarded", { requestId: message.id });
  }
  forwardUpstream(line);
});
clientReader.on("close", () => {
  emit("client_stdin_end", { held_request_ids: [...held.keys()] });
  finish("client_stdin_end");
});

const childReader = readline.createInterface({ input: child.stdout });
childReader.on("line", (line) => {
  if (!line.trim()) return;
  emitChild("child_stdout_line", { line });
  let message;
  try {
    message = JSON.parse(line);
  } catch {
    emit("upstream_parse_error", { line });
    process.stdout.write(`${line}\n`);
    return;
  }
  const handledAsTarget = inspectUpstreamMessage(message, line);
  if (!handledAsTarget) {
    process.stdout.write(`${line}\n`);
    if (message.id !== undefined) {
      emit("upstream_message_forwarded_downstream", { requestId: message.id });
    }
  }
});

function releaseHeld() {
  const ids = [...held.keys()];
  for (const id of ids) {
    const entry = held.get(id);
    held.delete(id);
    process.stdout.write(`${entry.line}\n`);
    emit("response_released_downstream", { requestId: id, tool: entry.tool });
  }
  return ids;
}

function handleCommand(command) {
  if (!command || typeof command !== "object") return;
  if (command.cmd === "release") {
    const ids = releaseHeld();
    emit("release_ack", { requestIds: ids, command_at: command.at ?? null });
    return;
  }
  if (command.cmd === "status") {
    emit("status", {
      child_alive: !childExited && child.exitCode === null,
      upstream_pid: child.pid,
      held_request_ids: [...held.keys()],
      delayed_request_ids: [...delayed.keys()],
      pending_target_request_ids: [...targetRequests.keys()],
      cancellation_events: cancellationEvents,
      mode: MODE,
      delay_ms: DELAY_MS,
      withhold_tools: [...WITHHOLD_TOOLS],
      requested_at: command.at ?? null,
    });
    return;
  }
  if (command.cmd === "shutdown") finish("control_shutdown");
}

function finish(reason) {
  if (shuttingDown) return;
  shuttingDown = true;
  emit("relay_finishing", {
    reason,
    held_request_ids: [...held.keys()],
    withheld_discarded: held.size,
  });
  for (const entry of delayed.values()) clearTimeout(entry.timer);
  delayed.clear();
  held.clear();
  if (childExited) {
    if (control && !control.destroyed) control.end();
    setTimeout(() => process.exit(0), 50);
    return;
  }
  try {
    child.stdin.end();
  } catch (error) {
    emit("child_stdin_end_error", { message: error.message });
  }
  const termTimer = setTimeout(() => {
    if (!childExited) {
      emit("child_sigterm", { upstream_pid: child.pid });
      try {
        child.kill("SIGTERM");
      } catch (error) {
        emit("child_sigterm_error", { message: error.message });
      }
    }
  }, 1500);
  const killTimer = setTimeout(() => {
    if (!childExited) {
      emit("child_sigkill", { upstream_pid: child.pid });
      try {
        child.kill("SIGKILL");
      } catch (error) {
        emit("child_sigkill_error", { message: error.message });
      }
    }
  }, 3000);
  child.once("exit", (code, signal) => {
    clearTimeout(termTimer);
    clearTimeout(killTimer);
    if (!childExited) {
      childExited = true;
      emit("child_exit", { code, signal, upstream_pid: child.pid, observed_by: "finish" });
      emitChild("child_exit", { code, signal, observed_by: "finish" });
    }
    setTimeout(() => {
      if (control && !control.destroyed) control.end();
      process.exit(0);
    }, 50);
  });
}

child.on("error", (error) => emit("child_spawn_error", { message: error.message }));
child.on("exit", (code, signal) => {
  if (!childExited) {
    childExited = true;
    emit("child_exit", { code, signal, upstream_pid: child.pid, observed_by: "top_level" });
    emitChild("child_exit", { code, signal, observed_by: "top_level" });
  }
  if (!shuttingDown) finish("upstream_exit_detected");
});

startControl();
