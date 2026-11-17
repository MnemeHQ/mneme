import { spawn } from "node:child_process";
import { appendFileSync, createWriteStream } from "node:fs";
import net from "node:net";
import readline from "node:readline";

const ENV = process.env;
const CONTROL_PORT = Number(ENV.CM01_CONTROL_PORT);
const CONTROL_TOKEN = ENV.CM01_CONTROL_TOKEN;
const MODE = ENV.CM01_RELAY_MODE || "passthrough";
const EVENT_LOG = ENV.CM01_EVENT_LOG;
const CHILD_STDERR = ENV.CM01_CHILD_STDERR;
const CHILD_EVENT_LOG = ENV.CM01_CHILD_EVENT_LOG;
const TARGET_TOOL = ENV.CM01_TARGET_TOOL || "decision.get";
const TARGET_RECORD = ENV.CM01_TARGET_RECORD || "ADR-9901";

let seq = 0;
let control = null;
let controlBuffer = "";
const pendingControlWrites = [];

function emit(type, data = {}) {
  const event = { seq: ++seq, ts: new Date().toISOString(), pid: process.pid, type, ...data };
  const line = `${JSON.stringify(event)}\n`;
  try {
    appendFileSync(EVENT_LOG, line);
  } catch (error) {
    process.stderr.write(`[relay] event-log-error ${error.message}\n`);
  }
  process.stderr.write(`[relay] ${line}`);
  if (control && !control.destroyed) {
    control.write(line);
  } else {
    pendingControlWrites.push(line);
  }
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
      const reader = readline.createInterface({ input: socket });
      reader.on("line", (line) => {
        if (!line.trim()) return;
        let command;
        try {
          command = JSON.parse(line);
        } catch {
          emit("control_parse_error", { line });
          return;
        }
        handleCommand(command);
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

const childStderrStream = createWriteStream(CHILD_STDERR, { flags: "a" });
child.stderr.pipe(childStderrStream);
child.stderr.on("data", (chunk) => {
  process.stderr.write(`[upstream-stderr] ${chunk.toString("utf8")}`);
});

let childSeq = 0;
function emitChildEvent(type, data = {}) {
  if (!CHILD_EVENT_LOG) return;
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
    process.stderr.write(`[relay] child-event-log-error ${error.message}\n`);
  }
}

emitChildEvent("child_spawn", {
  fixture: ENV.CM01_FIXTURE,
  cwd: ENV.CM01_EMPTY_CWD,
  command: ENV.CM01_PYTHON || "python",
});

emit("relay_start", {
  mode: MODE,
  target_tool: TARGET_TOOL,
  target_record: TARGET_RECORD,
  upstream_pid: child.pid,
  control_port: CONTROL_PORT,
  event_log: EVENT_LOG,
});

let targetRequestId = null;
let targetRequestForwarded = false;
let upstreamResponseReceived = false;
let heldLine = null;
let heldRequestId = null;
let childExited = false;
let shuttingDown = false;
const cancellationEvents = [];

function inspectClientMessage(message) {
  if (Array.isArray(message)) return message.map(inspectClientMessage);
  if (!message || typeof message !== "object") return;
  if (message.method === "notifications/cancelled") {
    const event = { requestId: message.params?.requestId ?? null, reason: message.params?.reason ?? null };
    cancellationEvents.push(event);
    emit("cancel_from_client", event);
  }
  if (message.method === "tools/call") {
    const tool = message.params?.name ?? null;
    const record = message.params?.arguments?.record_id ?? null;
    emit("tools_call_from_client", { requestId: message.id ?? null, tool, record });
    if (tool === TARGET_TOOL && (TARGET_RECORD === null || record === TARGET_RECORD)) {
      targetRequestId = message.id ?? null;
      emit("target_request_seen", { requestId: targetRequestId, tool, record });
    }
  }
}

function forwardUpstream(line) {
  if (childExited || child.stdin.destroyed) {
    emit("upstream_forward_dropped", { line });
    return;
  }
  emitChildEvent("child_stdin_line", { line });
  child.stdin.write(`${line}\n`);
}

function inspectUpstreamMessage(message, rawLine) {
  if (Array.isArray(message)) {
    for (const entry of message) inspectUpstreamMessage(entry, rawLine);
    return false;
  }
  if (!message || typeof message !== "object") return false;
  const isResponse = message.id !== undefined && (message.result !== undefined || message.error !== undefined);
  if (isResponse && targetRequestId !== null && message.id === targetRequestId) {
    upstreamResponseReceived = true;
    emit("upstream_response_received", {
      requestId: message.id,
      has_result: message.result !== undefined,
      has_error: message.error !== undefined,
    });
    if (MODE === "withhold" && heldLine === null) {
      heldLine = rawLine;
      heldRequestId = message.id;
      emit("response_withheld", { requestId: message.id });
      return true;
    }
  }
  return false;
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
  if (message && message.method === "tools/call" && targetRequestId !== null) {
    targetRequestForwarded = true;
    emit("target_request_forwarded", { requestId: targetRequestId });
  }
  forwardUpstream(line);
});
clientReader.on("close", () => {
  emit("client_stdin_end", { held_request_id: heldRequestId });
  finish("client_stdin_end");
});

const childReader = readline.createInterface({ input: child.stdout });
childReader.on("line", (line) => {
  if (!line.trim()) return;
  emitChildEvent("child_stdout_line", { line });
  let message;
  try {
    message = JSON.parse(line);
  } catch {
    emit("upstream_parse_error", { line });
    process.stdout.write(`${line}\n`);
    return;
  }
  const withheld = inspectUpstreamMessage(message, line);
  if (!withheld) {
    process.stdout.write(`${line}\n`);
    if (message && message.method === undefined && message.id !== undefined) {
      emit("upstream_message_forwarded_downstream", { requestId: message.id });
    }
  }
});

function handleCommand(command) {
  if (!command || typeof command !== "object") return;
  if (command.cmd === "release") {
    if (heldLine !== null) {
      const released = heldLine;
      const id = heldRequestId;
      heldLine = null;
      heldRequestId = null;
      process.stdout.write(`${released}\n`);
      emit("response_released_downstream", { requestId: id, command_at: command.at ?? null });
    } else {
      emit("release_noop", { command_at: command.at ?? null });
    }
    return;
  }
  if (command.cmd === "status") {
    emit("status", {
      child_alive: !childExited && child.exitCode === null,
      upstream_pid: child.pid,
      target_request_id: targetRequestId,
      target_request_forwarded: targetRequestForwarded,
      upstream_response_received: upstreamResponseReceived,
      held_request_id: heldRequestId,
      mode: MODE,
      cancellation_events: cancellationEvents,
      requested_at: command.at ?? null,
    });
    return;
  }
  if (command.cmd === "shutdown") {
    finish("control_shutdown");
  }
}

function finish(reason) {
  if (shuttingDown) return;
  shuttingDown = true;
  emit("relay_finishing", {
    reason,
    held_request_id: heldRequestId,
    withheld_response_discarded: heldLine !== null,
  });
  heldLine = null;
  heldRequestId = null;
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
    }
    setTimeout(() => {
      if (control && !control.destroyed) control.end();
      process.exit(0);
    }, 50);
  });
}

child.on("error", (error) => {
  emit("child_spawn_error", { message: error.message });
});
child.on("exit", (code, signal) => {
  if (!childExited) {
    childExited = true;
    emit("child_exit", { code, signal, upstream_pid: child.pid, observed_by: "top_level" });
    emitChildEvent("child_exit", { code, signal, observed_by: "top_level" });
  }
  if (!shuttingDown) finish("upstream_exit_detected");
});

startControl();
