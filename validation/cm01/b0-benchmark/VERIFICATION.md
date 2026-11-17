# CM-01-B0-M - Independent Verification

**Verification status:** VERIFIED.  
**Original B0-M verdict:** PASS, unchanged.  
**Scope:** model-free mechanical validation only.

## Result

- 14/14 static verification checks passed.
- 4/4 fresh-checkout reproduction checks passed.
- Zero discrepancies.
- Original B0-M runs remain PASS with 39/39 checks each.
- Original evidence manifest unchanged: `94dd0ee381fba2e9775634e0fc8f005dfeb59c9b874fd022227c6fcb92ed17ac`.
- Supplemental raw-transport verification passed 98/98 checks.

Verifier: `verify-b0m-evidence.mjs`.  
Machine-readable record: `evidence/verification.json`.

The two original runs are two sequential executions within one Node process, each using fresh MCP child processes, followed by independent fresh-worktree reproduction.

## What was verified

- Task ground truth re-derived from the frozen corpus and matched `tasks.json`.
- Direct-MCP and Code Mode outputs matched expected answers for all T1-T8 tasks.
- Direct and Code Mode outputs were identical for all tasks.
- MCP call counts, request IDs, result sizes and mechanical timings were present and consistent.
- No proposal methods were called; only the four read-only methods appeared.
- Cancellation: one matching notification, client rejection `-32001`, no pending request, clean relay/upstream exit.
- Cleanup: no errors, no surviving children.
- No unhandled rejections.
- Run1/run2 normalized outcomes and the check matrix agree.
- Source/fixture/task hashes match the recorded evidence.
- P0 remains FAIL and VERIFIED; F1 remains PASS and VERIFIED.
- S1-A1 digest, frozen executor, and M4 guard remain unchanged.
- Only `validation/cm01/b0-benchmark/` is new.

## Independent reproduction

A fresh detached worktree was created at `f8591102`, the B0 source/fixture/tasks were copied, and both the merged F1 dependency tree and B0 package were installed with `npm ci`. `node run-b0m.mjs` exited `0`.

| Item | Result |
|---|---|
| Reproduced verdict | PASS |
| Runs | PASS / PASS |
| Check matrix | 39/39 in both runs, identical to canonical |
| Normalized signature | Exact match |
| Source hashes | Exact match |
| Temporary worktree cleanup | Removed |
| Task worktree modified by reproduction | No |

## Supplemental read-only verification

`verify-b0m-supplemental.mjs` reconstructs every T1-T8 direct and Code Mode output from `evidence/raw/*-transport.jsonl` and reconciles it with `run1.json`, `run2.json`, `tasks.json` and the frozen fixture. It also checks request IDs, tool sequence, method arguments, response payloads, measured payload sizes, genuine Decision MCP processes, the six-tool upstream inventory, zero proposal or mutation calls, cleanup, cancellation and the pinned hashes.

- Result: **VERIFIED**, 98/98 checks.
- Record: `supplemental/verification.json`.
- Separate hash: `supplemental/verification.sha256` (`70afd4272fce2ba1e35e3ea78332b84175f41153139e384c2e51eff357614708`).
- Original evidence coverage is unchanged: 111 files under `evidence/`, excluding `evidence/verification.json`, digest `94dd0ee381fba2e9775634e0fc8f005dfeb59c9b874fd022227c6fcb92ed17ac`.
- Supplemental files are outside `evidence/` and are hashed separately; they do not redefine the original manifest.

## Limitations

- Original raw transport logs do not contain the full MCP initialize exchange; the inbound initialize response is present in the cancellation child-event traces.
- Mechanical timing excludes some connection, handshake and teardown lifecycle overhead.
- Model turns, input/output tokens, model-visible intermediate context, model latency and model-mediated efficiency are `NOT_MEASURED`.
- Ground truth is derived from the frozen fixture.
- B0-A statistical power has not been validated and B0-A remains unauthorized.
- No B0 protocol document is committed or preregistered in this repository; `tasks.json` and `make-tasks.py` are the executable task definitions.

## Missing B0-A capabilities

B0-M does not measure model turns, input/output tokens, model-visible intermediate context, model latency or cost. Those fields remain `NOT_MEASURED`. B0-A also requires an approved model snapshot, API/budget authorization, a primary endpoint, sample-size rationale, a material-effect threshold and a multiple-comparison policy. B0-M does not validate statistical power.

## Recommendation

**READY for human-reviewed B0-M evidence-record PR.** B0-A is not authorized. S1-A2 remains undefined and blocked. No production, Workers, server-side termination, or efficiency claim is made.

The original verifier did not commit, open a PR, merge, or clean the task worktree. This evidence-record PR records the verified evidence without changing the original verdict, runs, raw logs or original verification record.
