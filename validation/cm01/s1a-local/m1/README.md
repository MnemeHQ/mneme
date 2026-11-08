# CM-01 S1-A1 — M1 local Decision MCP inventory

**Status:** M1 only. PASS. No decision tool was called; no Code Mode connection, M2–M8, production memory, or canonical mutation.

## Scope

M1 proves:

- the existing `mneme decision-mcp` starts as a local stdio child process;
- the pinned Node MCP SDK initializes the session with `StdioClientTransport`;
- `tools/list` returns exactly the six ADR-027 tools;
- full input schemas and annotations are recorded;
- two independent server startups return the same normalized inventory;
- no proposal execution, canonical-memory mutation, unintended `.mneme/` access, or M4 change occurs.

M1 does **not** prove retrieval outputs, Code Mode integration, or any enforcement behavior.

## Base and fixture

| Item | Value |
|---|---|
| Current-main base | `942de7b121994647e99e9b862b44cda784c0ae84` |
| S0 source | `9eb4057a290795883076ab05bf11c92038c6ca13` |
| Branch | `feat/cm01-s1a1-e0-local-executor` |
| Fixture | `m1/fixture/canonical/project_memory.json` |
| Pre-migration fixture | `m1/fixture/pre_migration.json` |
| Repository project memory | not used |

The fixture was created by copying `pre_migration.json` to `fixture/work/project_memory.json` and running Mneme's existing migration command against the copy. The original pre-migration file was not modified.

## Pinned dependencies

| Dependency | Version |
|---|---|
| Node.js | `v24.13.1` |
| npm | `11.8.0` |
| `@modelcontextprotocol/sdk` | `1.32.2` |
| `zod` | `4.6.7` |
| Python | `3.12.10` |
| `mneme-hq` | `0.10.0` |
| Python `mcp` | `2.2.0` |

## Exact commands

From `validation/cm01/s1a-local/m1/`:

```text
npm install --ignore-scripts --no-audit --no-fund
npm run m1
```

Fixture creation commands, run from `m1/empty-cwd/` with `PYTHONPATH` set to the worktree root:

```text
python -m mneme decision-index migrate --memory <m1>/fixture/work/project_memory.json
python -m mneme decision-index migrate --memory <m1>/fixture/work/project_memory.json --apply
```

The canonical result was copied to `fixture/canonical/project_memory.json`.

## Checks

| Check | Evidence |
|---|---|
| `M1-HANDSHAKE-1` | Run 1 initialized; server info/capabilities recorded |
| `M1-HANDSHAKE-2` | Independent run 2 initialized |
| `M1-SIX-TOOLS-1` | Exactly six upstream tools with expected annotations |
| `M1-SIX-TOOLS-2` | Same on independent startup |
| `M1-REPEAT-INVENTORY` | Normalized inventories identical |
| `M1-NO-TOOL-CALLS` | `tool_calls_executed: 0`; no `callTool` |
| `M1-NO-MUTATION` | Fixture, pre-migration file, repository memory, proposal existence, and empty cwd unchanged |
| `M1-M4` | M4 guard passes before and after |

## Evidence

- `evidence/m1.json` — handshake results, normalized inventories, checks, hashes, versions, M4 guard.
- `evidence/run1-tools.json` — full `tools/list` output for run 1.
- `evidence/run2-tools.json` — full `tools/list` output for run 2.
- `evidence/run1-stderr.log` / `run2-stderr.log` — child stderr.
- `evidence/commands.txt` — exact commands and observed results.

## Stop

M1 stops here. M2–M8 are not started.
