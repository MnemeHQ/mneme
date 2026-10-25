import { createBrowserCodeTool } from "@cloudflare/codemode/browser";

export const READ_TOOLS = [
  "decision.get",
  "decision.search",
  "decision.applicable_to",
  "decision.trace",
];

export class HostCancelledError extends Error {
  constructor(message, { code = null, cause = null } = {}) {
    super(message);
    this.name = "HostCancelledError";
    this.code = code;
    if (cause) this.cause = cause;
  }
}

function textContent(result) {
  if (!Array.isArray(result.content)) return "";
  return result.content
    .filter((part) => part.type === "text")
    .map((part) => part.text ?? "")
    .join("\n");
}

function normalizeMcpSuccess(toolName, result) {
  if (result.structuredContent != null) return result.structuredContent;
  if (result.toolResult !== undefined) return result.toolResult;
  const text = textContent(result);
  if (!text) throw new Error(`MCP ${toolName} returned no structured result`);
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`MCP ${toolName} returned non-JSON text`);
  }
}

export function makeAdapter({ client, inventory, validators, executor, validate = true }) {
  const callLog = [];
  const descriptors = {};
  const byName = new Map(inventory.tools.map((tool) => [tool.name, tool]));

  for (const name of READ_TOOLS) {
    const tool = byName.get(name);
    if (!tool) throw new Error(`missing upstream tool ${name}`);
    descriptors[name] = {
      description: tool.description,
      inputSchema: tool.inputSchema,
      execute: async (args, context = {}) => {
        if (validate) {
          const validator = validators.get(name);
          if (!validator(args)) {
            throw new Error(
              `Argument validation failed for ${name}: ${JSON.stringify(validator.errors ?? null)}`,
            );
          }
        }

        const seq = callLog.length + 1;
        const signal = context?.signal;
        const requestOptions = signal ? { signal } : undefined;
        let result;
        try {
          result = await client.callTool(
            { name, arguments: args },
            undefined,
            requestOptions,
          );
        } catch (error) {
          const message = error?.message || String(error);
          const cancelled = Boolean(signal?.aborted) && error?.code !== -32000;
          const entry = {
            seq,
            tool: name,
            args,
            outcome: cancelled ? "cancelled" : "error",
            cancelled,
            errorName: error?.name || "Error",
            errorCode: error?.code ?? null,
            text: message,
            signalAborted: Boolean(signal?.aborted),
          };
          callLog.push(entry);
          if (cancelled) {
            throw new HostCancelledError(`MCP ${name} cancelled: ${message}`, {
              code: error?.code ?? null,
              cause: error,
            });
          }
          throw new Error(`MCP ${name} error: ${message}`);
        }

        const entry = {
          seq,
          tool: name,
          args,
          outcome: "fulfilled",
          cancelled: false,
          isError: Boolean(result.isError),
          structuredContent: result.structuredContent ?? null,
          toolResult: result.toolResult ?? null,
          text: textContent(result),
          signalAborted: Boolean(signal?.aborted),
        };
        callLog.push(entry);

        if (result.isError) {
          throw new Error(`MCP ${name} error: ${entry.text || "tool returned isError"}`);
        }
        return normalizeMcpSuccess(name, result);
      },
    };
  }

  return {
    tool: createBrowserCodeTool({ tools: descriptors, executor }),
    descriptors,
    callLog,
  };
}
