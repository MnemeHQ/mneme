import { spawn } from "node:child_process"

const DEFAULT_TIMEOUT_MS = 60_000

type Decision = { decision?: string; reason?: string }

// Non-write tools are outside the S1 surface. Diagnose each one once per
// plugin lifetime so noncoverage is visible without intercepting or blocking.
const notCoveredTools = new Set<string>()

function pythonExecutable(): string {
  return (
    process.env.MNEME_OPENCODE_PYTHON ||
    (process.platform === "win32" ? "python" : "python3")
  )
}

function runBridge(
  request: unknown,
  authorityPath: string | null,
  timeoutMs: number,
): Promise<Decision> {
  return new Promise((resolve) => {
    const args = ["-m", "mneme.integrations.opencode.bridge"]
    if (authorityPath) args.push("--authority", authorityPath)

    const child = spawn(pythonExecutable(), args, {
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
    })

    let stdout = ""
    let settled = false

    const finish = (value: Decision) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve(value)
    }

    const timer = setTimeout(() => {
      try {
        child.kill()
      } catch {
        // The bridge is already gone.
      }
      finish({ decision: "unevaluated", reason: "bridge_timeout" })
    }, timeoutMs)

    child.stdout.setEncoding("utf8")
    child.stdout.on("data", (chunk: string) => {
      stdout += chunk
    })
    child.stderr.on("data", () => {
      // Transport diagnostics stay out of the decision channel.
    })
    child.on("error", () => {
      finish({ decision: "unevaluated", reason: "bridge_launch_error" })
    })
    child.on("close", (code: number | null) => {
      if (code !== 0) {
        finish({ decision: "unevaluated", reason: `bridge_exit_${code}` })
        return
      }
      try {
        const parsed = JSON.parse(stdout) as Decision
        if (!parsed || typeof parsed.decision !== "string") {
          finish({ decision: "unevaluated", reason: "bridge_no_decision" })
          return
        }
        finish(parsed)
      } catch {
        finish({ decision: "unevaluated", reason: "bridge_unparseable" })
      }
    })

    try {
      child.stdin.write(JSON.stringify(request))
      child.stdin.end()
    } catch {
      finish({ decision: "unevaluated", reason: "bridge_write_error" })
    }
  })
}

export default {
  id: "mneme.opencode.s1",
  async setup(ctx: any) {
    const authorityPath =
      typeof ctx?.options?.authorityPath === "string"
        ? ctx.options.authorityPath
        : null
    const timeoutMs =
      Number.isInteger(ctx?.options?.timeoutMs) && ctx.options.timeoutMs > 0
        ? ctx.options.timeoutMs
        : DEFAULT_TIMEOUT_MS

    await ctx.tool.hook("execute.before", async (event: any) => {
      const tool = event?.tool
      if (tool !== "write") {
        const name = typeof tool === "string" && tool ? tool : "unknown"
        if (!notCoveredTools.has(name)) {
          notCoveredTools.add(name)
          console.error(
            `Mneme NOT_COVERED: tool ${name} is outside the S1 surface ` +
              "(write only); no evaluation, authorization or protection claim.",
          )
        }
        return
      }

      const input = event?.input ?? {}
      let sessionDirectory: string | null = null
      try {
        const session = await ctx.session.get({ sessionID: event?.sessionID })
        sessionDirectory = session?.location?.directory ?? null
      } catch {
        sessionDirectory = null
      }

      const decision = await runBridge(
        {
          tool: "write",
          input: { path: input.path, content: input.content },
          sessionDirectory,
          sessionID: event?.sessionID ?? null,
          callID: event?.callID ?? event?.id ?? null,
          agent: event?.agent ?? null,
          messageID: event?.messageID ?? null,
          eventID: event?.id ?? null,
          hostVersion: ctx?.app?.version ?? null,
        },
        authorityPath,
        timeoutMs,
      )

      if (decision.decision === "block") {
        throw new Error(`Mneme BLOCK: ${decision.reason ?? "literal violation"}`)
      }
      if (decision.decision === "setup_invalid") {
        console.error(
          `Mneme NOT_PROTECTED: ${decision.reason ?? "authority mismatch"}`,
        )
      } else if (decision.decision !== "allow") {
        console.error(`Mneme ${decision.decision}: ${decision.reason ?? "no reason"}`)
      }
    })
  },
}
