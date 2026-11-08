# CM-01-P0-01 — Evidence Verification Record

**Status:** VERIFIED. The original **FAIL** classification is preserved unchanged.
**Verification status:** 46/46 checks pass; independent clean-checkout reproduction matched.
**Fix authorized by this record:** none. S1-A2 remains blocked.

## Original result (unchanged)

| Field | Value |
|---|---|
| Verdict | **FAIL** |
| Reason | The MCP client request was still pending when Code Mode returned its timeout error; still pending after a 1500 ms bounded window; the withheld late response fulfilled the abandoned request; no `notifications/cancelled` was emitted. |
| Classification changed | **No** |
| Canonical verdict SHA-256 | `0917f33f66f9d92e6b639767b89c44af8c40cca9ab03c0e7fa3cb6d0ddabf46a` |
| Canonical run1 SHA-256 | `cd9360b21d8f6321dcb7c840b43bf1286ec841de055298a50ba7664900300492` |
| Canonical run2 SHA-256 | `49da740026fd2e8cc79c9cd8ef964bfa453e3fd49bfc9ae15a771df84b9cd826` |
| Canonical versions SHA-256 | `e8003a2a05ea5620b57635c24aa93e7ca5c69de3c574561a4626c6d0a0f8ae57` |

The verifier hashed these files before and after verification; all four hashes are identical. No run, verdict, or classification was edited.

## What was verified

`verify-evidence.mjs` read the canonical evidence and recomputed the verdict from the raw logs:

- Both fault relay logs contain exactly one target request (JSON-RPC id `2`), one upstream response, one withhold, one status, one release, and one child exit, in order.
- The response was withheld before the executor timeout and released only after the 1500 ms observation window.
- Both child-process logs contain the `tools/call` for id `2` and exactly one upstream response for id `2`.
- Both harness logs show the response arriving only after release, executor cleanup while the client promise was still pending, and zero cancellation notifications.
- The verdict's run aggregation, acceptance criteria, failure conditions, repeatability, and original FAIL reason match the two run files.
- Raw files, harness/relay SHA-256 identities, and the canonical evidence hashes match `verdict.json`.

## Source versions

Node `v24.13.1`, npm `11.8.0`, `@cloudflare/codemode` `0.5.5`, MCP SDK `1.32.2`, `ajv` `8.17.1`, `quickjs-emscripten` `0.32.0`, `zod` `4.6.7`, Python `3.12.10`, `mneme` `0.10.0`, Python `mcp` `2.2.0`. These match the recorded pins and the package manifest.

## Fixture and source identities

| Artifact | SHA-256 |
|---|---|
| M1 canonical fixture | `8f73429e70e04a6876b965bb00a1777fc90409f9da2889c72dab9ac26b9621ea` |
| M1 pre-migration fixture | `1923f12bdef0cec4a3c6bc56704e8e03f0d8531313574bff0ae010b5ce2a2a5c` |
| M4 canonical fixture | `b4d83d0cc0f70f442e2a62bd0e527220ae99b07cba1238e39d0ad8c5685d4e7f` |
| Merged QuickJS executor | `4b960124e9218ed124ed34e3b3595b648477b9dab6540c4ce1609d2efaf31313` |
| M4 guard | `7df06ddb301355d2a040e2a3d04e915f513f36177d640e40b5224b7ca9d128a6` |
| Instrumented relay | `e09e9b76c3b2e02b619a9339b7bb98c7c1abd8e358f785b1a08e518109adf9ad` |
| Runner | `87d0021d66e95153945265ea10413b6e7834a9eeb783639887e5dff253747133` |

All four reused artifacts match the declared baseline blobs at `ddeb85ee`.

## Baseline preservation

- Declared baseline: `ddeb85eec8f7734edde1c921250592d51afedbee`.
- HEAD during runs: `0d367fc61316e8af50161f6bc48b8dee1711c807`.
- Baseline-to-HEAD drift: one upstream docs-only ADR-034 M4 results record (`docs/validation/adr-034-m4-heldout-scoring-2026-10-24.md`, PR #628).
- `validation/cm01` and `mneme` were unchanged between baseline and HEAD.
- S1-A1 tracked evidence digest: `cc7f884866e6e94255b100de57b82eec4a51660aadaf51c6464198131030af57`; unchanged, and S1-A1 git status is clean.
- M4 worktree guard at HEAD: **pass**, zero violations. No M4 path was added, edited, or committed by this validation.
- Only `validation/cm01/p0-cancellation/` is new in the working tree.

## Independent reproduction

Performed in a fresh detached worktree at HEAD, with fresh `npm ci` in both the S1-A1 tree and the validation package:

| Item | Result |
|---|---|
| Clean worktree | `C:\Users\hi\AppData\Local\Temp\opencode\cm01-p0-verify-1792850504652` |
| Runner exit code | `1` (FAIL) |
| Reproduced verdict | **FAIL** |
| Signature comparison | Exact match across verdict, acceptance criteria, failure conditions, both run signatures, and process cleanup |
| Canonical evidence overwritten | No |
| Worktree cleanup | Removed |

## Rerun

From `validation/cm01/p0-cancellation/`:

```text
node verify-evidence.mjs
node verify-evidence.mjs --reproduce
```

`--reproduce` creates a temporary detached worktree, installs the pinned dependencies, runs the two-run experiment, compares signatures, writes `evidence/verification.json`, and removes the worktree. It does not modify `evidence/verdict.json`, `run1.json`, or `run2.json`.

## Boundary

This record verifies evidence only. It does not implement the `AbortSignal` correction, does not authorize S1-A2, and does not change the original FAIL. The result still does not establish server-side cancellation of code already executing.
