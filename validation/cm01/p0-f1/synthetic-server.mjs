import { appendFileSync } from "node:fs";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

const LOG = process.env.CM01_SYNTHETIC_LOG;
let seq = 0;
function log(type, data = {}) {
  const event = { seq: ++seq, ts: new Date().toISOString(), type, ...data };
  if (LOG) appendFileSync(LOG, `${JSON.stringify(event)}\n`);
  process.stderr.write(`[f1-synthetic] ${JSON.stringify(event)}\n`);
}

log("server_start", { pid: process.pid });

const server = new Server(
  { name: "f1-synthetic-slow", version: "0.1.0" },
  { capabilities: { tools: {} } },
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "slow.echo",
      description: "Test-only slow tool used to observe cooperative cancellation.",
      inputSchema: {
        type: "object",
        properties: {
          delay_ms: { type: "number", description: "How long the handler waits." },
        },
      },
    },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (request, extra) => {
  const name = request.params.name;
  if (name !== "slow.echo") {
    throw new Error(`unknown synthetic tool: ${name}`);
  }
  const delayMs = Number(request.params.arguments?.delay_ms ?? 1000);
  const started = Date.now();
  log("tool_started", {
    tool: name,
    delayMs,
    requestId: extra.requestId ?? null,
  });

  let aborted = false;
  await new Promise((resolve) => {
    const timer = setTimeout(resolve, delayMs);
    const onAbort = () => {
      aborted = true;
      clearTimeout(timer);
      log("signal_aborted", {
        tool: name,
        requestId: extra.requestId ?? null,
        elapsedMs: Date.now() - started,
      });
      resolve();
    };
    if (extra.signal.aborted) {
      onAbort();
      return;
    }
    extra.signal.addEventListener("abort", onAbort, { once: true });
  });

  log("handler_returned", {
    tool: name,
    requestId: extra.requestId ?? null,
    aborted,
    elapsedMs: Date.now() - started,
    response_expected: !aborted,
  });

  if (aborted) {
    return {
      content: [{ type: "text", text: "cancelled" }],
      structuredContent: { cancelled: true },
    };
  }
  return {
    content: [{ type: "text", text: "slow-ok" }],
    structuredContent: { ok: true, delay_ms: delayMs },
  };
});

const transport = new StdioServerTransport();
await server.connect(transport);
