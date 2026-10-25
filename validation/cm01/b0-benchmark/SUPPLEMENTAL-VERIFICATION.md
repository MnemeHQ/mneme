# CM-01-B0-M - Supplemental Independent Verification

**Status:** VERIFIED.  
**Original B0-M verdict:** PASS, unchanged.  
**Scope:** read-only supplemental reconstruction of the original B0-M evidence.  
**Baseline:** `f8591102b2693379dabec9b5704862e194eca4ce`.

## Result

- Supplemental verifier: `verify-b0m-supplemental.mjs`.
- Supplemental checks: **98/98 passed**.
- Machine-readable record: `supplemental/verification.json`.
- Separate record hash: `supplemental/verification.sha256`.
- Supplemental record SHA-256: `70afd4272fce2ba1e35e3ea78332b84175f41153139e384c2e51eff357614708`.
- Original verdict remains **PASS**, with 39/39 checks in run1 and run2.
- Original verification remains **VERIFIED**, with 14/14 static and 4/4 reproduction checks.
- Original evidence manifest remains `94dd0ee381fba2e9775634e0fc8f005dfeb59c9b874fd022227c6fcb92ed17ac`.

## What the supplemental verifier reconstructs

Every T1-T8 direct and Code Mode result is reconstructed from the raw MCP transport logs and reconciled against `run1.json`, `run2.json`, `tasks.json` and the frozen fixture.

- Request IDs: every `tools/call` uses the expected sequential ID and matches the recorded ID.
- Tool sequence: T1-T8 call sequences match the task definitions, including T5/T6 two-call and T7/T8 three-call workflows.
- Method arguments: raw arguments match the recorded `mcp_calls` arguments exactly.
- Response payloads: raw structured content reproduces each task answer exactly.
- Payload sizes: per-call `result_bytes`, aggregate `mcp_result_bytes` and task `result_bytes` match raw response records.
- Corpus/task truth: expected answers are re-derived from the frozen fixture and match `tasks.json`.
- Direct/Code equivalence: both arms return identical structured payloads and identical task outcomes.
- Repeatability: run1 and run2 produce identical normalized task outcomes.
- Genuine MCP: 32 unique MCP child processes across 16 task phases and both arms, each with a real MCP initialize/tools-list/tools-call exchange.
- Inventory: every `tools/list` returns exactly the six ADR-027 tools.
- Authority boundary: no `decision.propose` or `decision.propose_batch` call appears; only the four read-only methods are called.
- Cancellation: one withheld response, one client cancellation, one matching upstream notification, client rejection `-32001`, no pending request, one settled cancelled call, zero unsettled calls, clean child and relay exit.
- Cleanup: no cleanup errors and no surviving server, relay or upstream children.
- Hash pins: fixture, tasks, package lock, F1 executor/adapter/harness/relay/runner/package lock, frozen S1-A1 executor, M4 guard and S1-A1 digest.
- Preservation: P0 remains FAIL/VERIFIED, F1 remains PASS/VERIFIED, no changes under S1-A1, P0, F1 or `mneme/`.
- Model fields: `NOT_MEASURED` throughout.

## Hash coverage

The original evidence manifest covers exactly the 111 files under `evidence/`, excluding `evidence/verification.json`. It is unchanged.

The supplemental record lives in `supplemental/`, outside `evidence/`, and is hashed separately. Adding it does not extend, replace or redefine the original manifest.

| Item | SHA-256 |
|---|---|
| Original evidence manifest (111 files) | `94dd0ee381fba2e9775634e0fc8f005dfeb59c9b874fd022227c6fcb92ed17ac` |
| Supplemental record | `70afd4272fce2ba1e35e3ea78332b84175f41153139e384c2e51eff357614708` |
| Fixture | `a996e2aa5c2d41bf8a75293c8d60adebf9ab89eb59caea926fbccf97297a1dca` |
| Tasks | `7aaa196a72b52726ea6db7e46db612c6a6abc0f2bf7f3d5f3a13be2822e163b6` |
| B0 package lock | `c9850209a6330a810fbf2f784427eca6c89df4cce71fb6ec49564fee01c55e9f` |
| F1 executor | `0d81093b20fa0b77a3fc9f2e6b4a90bf184668d0377242c3e4f37e64afd9d2b1` |
| F1 adapter | `3d8123975bc9f67147fec90ff3e6911a08e40a7f2dc4bd7b43da14b0530cb08c` |
| F1 relay | `536f32e7869fc407782b1c1db7d55afc3bd383bc0ede405f40d6f08b45e0f5e5` |
| F1 runner | `55a40f182df80bf7f3828e165601758298912eaa7f6285ef0772cc967103e830` |
| F1 harness | `3b2a7591614dd19532e3d7a5064e403ea4d58e73e73e305009b9d67385ba8076` |
| Frozen S1-A1 executor | `4b960124e9218ed124ed34e3b3595b648477b9dab6540c4ce1609d2efaf31313` |
| M4 guard | `7df06ddb301355d2a040e2a3d04e915f513f36177d640e40b5224b7ca9d128a6` |
| S1-A1 tracked digest | `cc7f884866e6e94255b100de57b82eec4a51660aadaf51c6464198131030af57` |

## Byte portability

The B0 `.gitattributes` applies only within this package:

- `.gitattributes`, `.gitignore`, JSON, MJS and Python files: `-text`.
- `evidence/**` and `fixture/**`: `-text`.
- `supplemental/**`: `-text`.
- Markdown: `text eol=lf`.

A nested package was committed and cloned with `core.autocrlf=true`. The clone preserved all 129 package files byte-for-byte, including the 112 files under `evidence/` (111 covered by the original manifest plus `verification.json`), the fixture, tasks, package lock, source scripts and supplemental record. The cloned evidence manifest remained `94dd0ee381fba2e9775634e0fc8f005dfeb59c9b874fd022227c6fcb92ed17ac`, and the clone had a clean worktree.

## Fresh reproduction

The original verifier was re-run against the updated package in an isolated worktree at the recorded baseline:

- 14/14 static checks passed.
- 4/4 reproduction checks passed.
- `node run-b0m.mjs` exited `0` with PASS/PASS and 39/39 checks in both reproduced runs.
- Normalized results, check matrix and source hashes matched canonical.
- The temporary reproduction worktree was removed.
- The original evidence manifest was unchanged before and after.

The ADR-034 M4 guard passed at the recorded baseline. Commits on current `main` after the baseline are unrelated ADR-034 G2-1 and C3 changes; they do not alter the recorded B0-M bytes or verdict.

## Methodological limitations

- The two original runs are two sequential executions within one Node process, each using fresh MCP child processes, followed by independent fresh-worktree reproduction. They are not two separate Node-process executions.
- Original task transport logs do not contain the full MCP initialize exchange; the inbound initialize response is present in the cancellation child-event traces.
- Mechanical timing excludes some connection, handshake and teardown lifecycle overhead.
- Model tokens, turns, model-visible intermediate context and model-mediated efficiency are `NOT_MEASURED`.
- Ground truth is derived from the frozen fixture; this validates retrieval/projection fidelity and exact composition, not independent recomputation of identity digests.
- B0-A statistical power has not been validated. B0-A remains unauthorized.
- No separate B0 protocol document is committed or preregistered in this repository; `tasks.json` and `make-tasks.py` are the executable task definitions.
- No production, Workers, server-side termination or S1-A2 claim is made.

## Provenance

- Change author: agent
- Agent: opencode
- Agent model: opencode-go/deepseek-v4.1-flash
- Agent session: not-exposed
- Task origin: local
- Human owner: @TheoV823
