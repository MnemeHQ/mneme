# CM-01-P0-01-F1 - Evidence Verification

**Verification status:** VERIFIED.
**Original F1 verdict:** PASS, unchanged.
**Verification scope:** read-only reconstruction plus a fresh isolated reproduction.
**Implementation source modified:** no.
**Original F1 evidence modified:** no.

## Verification result

- 32 static verification checks passed.
- 5 independent-reproduction checks passed.
- Original F1 verdict remains PASS.
- Both original runs remain PASS with 20/20 checks.
- Normalized outcomes agree across the two original runs and the independent reproduction.
- No discrepancies were recorded.

Verifier: `verify-f1-evidence.mjs`.
Machine-readable record: `evidence/verification.json`.

## What was independently reconstructed

- **Verdict and matrices:** `run1.json` and `run2.json` were read directly; all 20 expected checks exist and pass in both runs; the check sets and pass states match exactly.
- **Cancellation:** the timeout scenario reaches the MCP client, emits exactly one `notifications/cancelled` with the matching request id, and settles the client promise with `McpError -32001` before executor return. The request is pending at the deadline and not pending at execution return.
- **Completed requests:** control, parallel-completed, sequential-completed, and race-before requests produce zero cancellation notifications.
- **Late responses:** the withheld response is released after cancellation; the request remains rejected and the late response cannot revive it. Cancellation count remains one.
- **Races:** response-before-timeout succeeds with zero notifications; timeout-before-response rejects with one notification; the boundary only permits success-with-zero or timeout-with-one, never success plus cancellation, and never a pending request.
- **Transport close:** close-while-pending yields `McpError -32000` with zero cancellations; timeout-then-close retains `-32001` and one cancellation.
- **Host cleanup:** no unhandled rejections, no `host_call_unsettled_after_grace`, and no post-grace `host_call_settled_after_abort`. All recorded relay/upstream/server children exited.
- **Genuine server observation:** the genuine Decision MCP received the cancellation frame after its withheld response. This is transport delivery, not server execution termination.
- **Synthetic server:** the slow async server observed `signal_aborted`, returned with `aborted: true` and `response_expected: false`, and sent no response after cancellation.
- **P0 comparison:** the original P0 failure signature remains pending-at-timeout/after-window, zero notifications, late-response settlement. F1 changes this to rejected `-32001`, one notification, and no late revival.

## Hashes and preservation

| Item | Verified value |
|---|---|
| Evidence manifest before/after | `5a2d98d5213fa9bc3163b92a1a3f2b361617895e83748395f23982bcdd6097b6` |
| S1-A1 tracked digest | `cc7f884866e6e94255b100de57b82eec4a51660aadaf51c6464198131030af57` |
| Frozen executor | `4b960124e9218ed124ed34e3b3595b648477b9dab6540c4ce1609d2efaf31313` |
| F1 executor | `0d81093b20fa0b77a3fc9f2e6b4a90bf184668d0377242c3e4f37e64afd9d2b1` |
| F1 adapter | `3d8123975bc9f67147fec90ff3e6911a08e40a7f2dc4bd7b43da14b0530cb08c` |
| F1 relay | `536f32e7869fc407782b1c1db7d55afc3bd383bc0ede405f40d6f08b45e0f5e5` |
| F1 synthetic server | `b1469f6ed676ab3b057a92e6329096336a62456f1604317c46d70f6941833063` |
| F1 runner | `55a40f182df80bf7f3828e165601758298912eaa7f6285ef0772cc967103e830` |
| F1 package lock | `4f4f81b24f31490ff1a1d3f5c1a33fd359d1545567f91daffaa56abaa8e63167` |
| P0 verdict | `0917f33f66f9d92e6b639767b89c44af8c40cca9ab03c0e7fa3cb6d0ddabf46a` |

Preservation checks:

- `validation/cm01/s1a-local/` and `validation/cm01/p0-cancellation/` have no diff and no status changes.
- P0 evidence files match the merged HEAD blobs; the P0 verification remains `VERIFIED`.
- The original P0 verdict remains FAIL.
- Canonical memory matches HEAD; production `mneme/` diff is empty.
- M4 guard passes; no ADR-034 M4 change.
- Only `validation/cm01/p0-f1/` is new.

## Grace and latency

- Provisional grace: 100 ms.
- Final grace: 50 ms.
- Calibration: 16 cancellations, max 3 ms, min 1 ms, mean 1.875 ms.
- Final recorded and recomputed latency: 16 samples, max 4 ms, mean 1.5625 ms.
- All recomputed samples are within the 50 ms bound.

The 50 ms bound is environment-specific and is not generalized beyond this tested environment.

## Independent reproduction

A fresh detached worktree was created at `adf50933`, the F1 source files were copied into it, and `npm ci` installed the pinned dependencies. `node run-f1.mjs` exited `0`.

| Reproduction item | Result |
|---|---|
| Verdict | PASS |
| Runs | PASS / PASS |
| Check matrix | 20/20 in both runs, identical to canonical |
| Normalized outcomes | Exact match |
| Source hashes | Exact match |
| Latency samples | 16, all within 50 ms |
| Temporary worktree cleanup | Removed |
| Task worktree modified | No |

## Limitations

- Client settlement and cancellation dispatch are proven.
- Server-side execution termination is not claimed.
- Notification delivery remains fire-and-forget; the record shows transport dispatch and server receipt.
- In-progress server cancellation is demonstrated with the synthetic async server, not the synchronous genuine tools.
- The measured bound is local to this environment.

## Recommendation

**F1 is READY for an evidence-record PR.** The original F1 verdict and raw evidence are unchanged. No commit, PR, merge, or task-worktree cleanup was performed.
