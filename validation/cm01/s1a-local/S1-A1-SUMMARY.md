# CM-01 S1-A1 — Local OSS Code Mode Compatibility Experiment

**Status:** PR preparation only. Reviewed READY for the bounded local experiment, with residual risks. Not S1-A1 closure, not a production approval, and not S1-A2.

## Scope

Local OSS compatibility only:

- `@cloudflare/codemode/browser`
- a custom local QuickJS executor
- Mneme's existing stdio Decision MCP
- four read-only methods: `decision.get`, `decision.search`, `decision.applicable_to`, `decision.trace`
- synthetic canonical fixtures only

Not covered:

- Cloudflare Workers, `CodemodeRuntime`, durable approvals or replay
- mutation enforcement, file permissions or fail-closed behavior
- production hardening, performance or model-call reduction

## Exact base and provenance

| Item | Value |
|---|---|
| Reviewed base | `942de7b121994647e99e9b862b44cda784c0ae84` |
| S0 provenance | `9eb4057a290795883076ab05bf11c92038c6ca13` |
| Branch | `feat/cm01-s1a1-e0-local-executor` |
| Newer main inspected | `85b43d5c` — C3 validation harness only; no overlap with `validation/cm01/` |
| Evidence rerun for this PR | No |

The newer main commit changes only:

```text
docs/validation/artifacts/adr033-c3-claude-code-enforcement-live/harness/README.md
docs/validation/artifacts/adr033-c3-claude-code-enforcement-live/harness/selftest/run_selftest.sh
docs/validation/artifacts/adr033-c3-claude-code-enforcement-live/harness/setup_c3_probe.py
```

It does not conflict with this experiment. The pinned validation baseline remains `942de7b1`.

## Validation matrix

| Milestone | Result | Evidence |
|---|---|---|
| E0 local executor | PASS | `evidence/e0.json` |
| M1 inventory/handshake | PASS | `m1/evidence/m1.json` |
| M2 local integration | PASS | `m2/evidence/m2.json` |
| M3 `decision.get` parity | PASS | `m3/evidence/m3.json` |
| M4 original `decision.search` | **FAIL** (preserved) | `m4/evidence/m4.json` |
| M4-F1 corrected search parity | PASS | `m4/f1/evidence/m4-f1.json` |
| M5 `decision.applicable_to` parity | PASS | `m5/evidence/m5.json` |
| M6 `decision.trace` parity | PASS | `m6/evidence/m6.json` |
| M7 data-dependent composition | PASS | `m7/evidence/m7.json` |
| M8 failure behavior | PASS | `m8/evidence/m8.json` |

The original M4 FAIL remains a FAIL. M4-F1 is a separate corrected result and does not rewrite the original.

## Dependency pins

| Dependency | Version |
|---|---|
| Node.js | `24.13.1` |
| npm | `11.8.0` |
| `@cloudflare/codemode` | `0.5.5` |
| `@modelcontextprotocol/sdk` | `1.32.2` |
| `ajv` | `8.17.1` |
| `zod` | `4.6.7` |
| Python | `3.12.10` |
| `mneme-hq` | `0.10.0` |
| Python `mcp` | `2.2.0` |

## Reproduction

From each package directory (`s1a-local`, `m1`–`m8`):

```text
npm ci --ignore-scripts --no-audit --no-fund
```

Then, from `s1a-local` and each milestone directory:

```text
npm run e0
npm run m1
npm run m2
npm run m3
npm run m4          # expected FAIL, preserved
node m4/f1/run-m4-f1.mjs
npm run m5
npm run m6
npm run m7
npm run m8
```

An independent reproduction was run in a temporary clone at base `942de7b1`. E0–M8 checks matched the committed evidence; original M4 failed as expected and M4-F1 passed.

## Original M4 failure and M4-F1 correction

| Result | Evidence | SHA-256 |
|---|---|---|
| Original M4 FAIL | `m4/evidence/m4.json` | `dde0f195ef6f38e7d239a13c3a2b932b834b8e166a7ba32fe59b0787376878dd` |
| M4-F1 PASS | `m4/f1/evidence/m4-f1.json` | `7e47140dbb6cfd0cadca63f066ceea510b312d3d0d69805da1c69de602ef01af` |

Fixtures:

- M1 canonical: `8f73429e70e04a6876b965bb00a1777fc90409f9da2889c72dab9ac26b9621ea`
- M4-F1 canonical: `b4d83d0cc0f70f442e2a62bd0e527220ae99b07cba1238e39d0ad8c5685d4e7f`

## Residual risks from independent review

1. **Adapter duplication:** M3–M8 mirror the M2 four-method adapter rather than importing one shared module. Behavior matches in evidence, but future drift is possible.
2. **In-process isolation only:** QuickJS provides a language/WASM boundary with no Node globals, but not OS/process isolation.
3. **MCP call cancellation on timeout is not established:** synthetic host cleanup is proven; a hung MCP `callTool` may outlive the executor timeout.
4. **`__hostCall` is globally reachable:** provider allowlisting and host validation constrain it to the four read methods, but it is an alternate sandbox call surface.

## Explicitly unsupported claims

This PR does not claim:

- hardened or OS-level isolation
- MCP-call cancellation
- enforcement compatibility or permission to mutate files
- fail-closed enforcement
- Cloudflare durable-runtime compatibility
- fewer model calls, lower latency or performance improvement
- S1-A1 closure or S1-A2 readiness

## Review and lifecycle

- Independent review verdict: **READY — limited scope**.
- This PR is draft only; no merge, closure or S1-A2 work.
- `INCLUSION-MANIFEST.txt` records the exact PR file inventory.
- Raw `.log` evidence is unignored and included; dependencies and caches are excluded.
