# CM-01-B0-M - Model-Free Mechanical Benchmark

**Status:** local mechanical validation complete. **Verdict: PASS** in two sequential executions within one Node process, each using fresh MCP child processes, followed by independent fresh-worktree reproduction.  
**Baseline:** `f8591102b2693379dabec9b5704862e194eca4ce`  
**Scope:** CM-01-B0-M only. No model API calls, production integration, S1-A2, or efficiency claim.

## What this validates

B0-M compares a scripted/oracle agent using direct Mneme MCP with the same agent using the merged F1 Code Mode implementation, over the frozen T1-T8 task families.

It validates:

- both arms reach the same genuine Decision MCP and frozen corpus;
- exact task-answer equivalence for decision IDs, versions, digests, scopes, rule identities and test-evidence identities;
- identical functional-completion requirements;
- MCP call, payload-size, mechanical-latency and cleanup instrumentation;
- the four read-only methods only, with no proposal or mutation exposure;
- F1 cancellation behavior using the merged F1 executor/relay;
- two-run deterministic repeatability;
- preservation of S1-A1, P0 and F1 evidence.

It does **not** measure model turns, tokens, model-visible intermediate context, model latency or efficiency. Those fields are present and marked `NOT_MEASURED`.

## Architecture

- ADR-017: retrieval/context only; no enforcement claim.
- ADR-023: Decision Index remains canonical; Code Mode is a consumer, not a resolver.
- ADR-027: six-tool upstream inventory unchanged; Code Mode exposes only the four read-only methods.
- No production Code Mode integration; no new MCP tools; no proposal ingestion; no authority change.
- Both arms use the genuine Decision MCP over stdio and the same frozen synthetic corpus.

## Frozen corpus and tasks

- Corpus: 24 deterministic synthetic decisions with versions, scopes, rules, test evidence, lifecycle variants and compatibility snapshot.
- Corpus SHA-256: `a996e2aa5c2d41bf8a75293c8d60adebf9ab89eb59caea926fbccf97297a1dca`.
- Tasks: T1-T8 executable task definitions in `tasks.json`, generated from the frozen fixture by `make-tasks.py`. No separate B0 protocol document is committed or preregistered in this repository; `tasks.json` and `make-tasks.py` are the executable task definitions.
- Tasks SHA-256: `7aaa196a72b52726ea6db7e46db612c6a6abc0f2bf7f3d5f3a13be2822e163b6`.
- Ground truth is derived from the frozen fixture by `make-tasks.py` and compared exactly; no LLM judge is used.

| Task | Family | Direct correct | Code Mode correct | Equivalent | MCP calls D/C |
|---|---|---|---|---|---|
| T1 | single get | yes | yes | yes | 1 / 1 |
| T2 | single search | yes | yes | yes | 1 / 1 |
| T3 | single applicability | yes | yes | yes | 1 / 1 |
| T4 | single trace | yes | yes | yes | 1 / 1 |
| T5 | search -> get | yes | yes | yes | 2 / 2 |
| T6 | search -> trace | yes | yes | yes | 2 / 2 |
| T7 | applicability -> get -> trace | yes | yes | yes | 3 / 3 |
| T8 | filter/compose | yes | yes | yes | 3 / 3 |

## Mechanical results

Both runs passed **39/39 checks**.

| Measurement | Result |
|---|---|
| Task correctness | 8/8 direct, 8/8 Code Mode |
| Direct/Code equivalence | 8/8 tasks |
| MCP calls recorded | equal per task/arm; all request IDs and payload sizes recorded |
| Proposal calls | 0 |
| Functional completion | 8/8 both arms |
| Cancellation | one matching notification; client rejected `-32001`; no pending request; clean relay/upstream exit |
| Cleanup | no cleanup errors; no surviving children |
| Unhandled rejections | 0 |
| Repeatability | exact normalized agreement across run1/run2 |
| Model fields | `NOT_MEASURED` |

Mechanical latency examples from run1 are recorded in `evidence/measurements.json`; they are environment-specific and are not model or production performance claims. Code Mode mechanically adds sandbox execution overhead in this harness and receives no efficiency credit.

## Independent verification

`verify-b0m-evidence.mjs --reproduce` reports **VERIFIED**:

- 14/14 static checks.
- 4/4 independent-reproduction checks.
- Fresh detached worktree at `f8591102`.
- `npm ci` for the F1 dependency tree and the B0 package.
- `node run-b0m.mjs` exit `0`.
- Normalized results, check matrix and source hashes match exactly.
- Temporary verification worktree removed.
- Original evidence manifest unchanged before/after verifier execution: `94dd0ee381fba2e9775634e0fc8f005dfeb59c9b874fd022227c6fcb92ed17ac`.

Supplemental read-only verification, `verify-b0m-supplemental.mjs`, reports **VERIFIED** (98 checks). It reconstructs T1-T8 from the raw MCP transport logs and reconciles request IDs, tool sequence, arguments, response payloads and measured payload sizes against the original run records. It also confirms genuine Decision MCP processes, the six-tool upstream inventory, zero proposal or mutation calls, cleanup and cancellation evidence, and the pinned corpus, task, dependency and original-manifest hashes.

The supplemental record is `supplemental/verification.json`; its independent hash is in `supplemental/verification.sha256`. It is intentionally outside `evidence/`, so the original 111-file evidence manifest remains the historical identity `94dd0ee3...` and is not redefined by the supplemental coverage.

## Reproduction

From `validation/cm01/b0-benchmark/`:

```text
# B0 imports the merged F1 executor/adapter, so its dependency tree must exist.
cd ../p0-f1
npm ci --ignore-scripts --no-audit --no-fund
cd ../b0-benchmark
npm ci --ignore-scripts --no-audit --no-fund

node run-b0m.mjs
node verify-b0m-evidence.mjs --reproduce
node verify-b0m-supplemental.mjs
```

Optional corpus/task regeneration (deterministic, not required for normal reproduction):

```text
# from the repository root
$env:PYTHONPATH = (Get-Location)
python validation/cm01/b0-benchmark/make-corpus.py
python validation/cm01/b0-benchmark/make-tasks.py
```

## Pinned versions

Node `24.13.1`, npm `11.8.0`, `@cloudflare/codemode` `0.5.5`, `@modelcontextprotocol/sdk` `1.32.2`, `ajv` `8.17.1`, `quickjs-emscripten` `0.32.0`, `zod` `4.6.7`, Python `3.12.10`, `mneme` `0.10.0`, Python `mcp` `2.2.0`.

Merged F1 identities reused read-only:

- Executor `0d81093b20fa0b77a3fc9f2e6b4a90bf184668d0377242c3e4f37e64afd9d2b1`
- Adapter `3d8123975bc9f67147fec90ff3e6911a08e40a7f2dc4bd7b43da14b0530cb08c`
- Relay `536f32e7869fc407782b1c1db7d55afc3bd383bc0ede405f40d6f08b45e0f5e5`
- Runner `55a40f182df80bf7f3828e165601758298912eaa7f6285ef0772cc967103e830`
- Frozen S1-A1 executor `4b960124e9218ed124ed34e3b3595b648477b9dab6540c4ce1609d2efaf31313`

## Preservation

- Original P0 FAIL and P0 VERIFIED evidence unchanged.
- F1 PASS and F1 VERIFIED evidence unchanged.
- S1-A1 tracked digest unchanged: `cc7f884866e6e94255b100de57b82eec4a51660aadaf51c6464198131030af57`.
- No changes under `validation/cm01/s1a-local/`, `validation/cm01/p0-cancellation/`, `validation/cm01/p0-f1/`, or `mneme/`.
- M4 guard passes at the recorded baseline; no ADR-034 M4 change.
- Original evidence manifest `94dd0ee381fba2e9775634e0fc8f005dfeb59c9b874fd022227c6fcb92ed17ac` remains unchanged and covers only the original `evidence/` set.
- Supplemental verification is hashed separately; it does not extend or redefine the original manifest.
- Only `validation/cm01/b0-benchmark/` is new.

## Missing capabilities for B0-A

B0-A remains not authorized and needs:

- a pinned model snapshot and approved API credentials/budget;
- model-turn and input/output-token measurement;
- model-visible intermediate-context token measurement with a pinned tokenizer;
- model latency and cost fields;
- one approved primary endpoint;
- sample-size rationale, material-effect threshold and multiple-comparison policy;
- a model-mediated reproduction/verification plan.

B0-M does not validate statistical power. The B0-A matrix of 8 tasks, 2 arms and 6 repetitions remains provisional.

## Roadmap and tracker corrections (not applied)

- `docs/roadmap/README.md`: change F1 from uncommitted/unmerged to merged at `f8591102` via PR #642 and independently VERIFIED.
- `docs/roadmap/README.md`: mark the F1 evidence gate complete; add B0-M as mechanical validation complete/pending review and B0-A as not authorized.
- Issue #640: update F1 to merged/VERIFIED; record B0 protocol reviewed, B0-M mechanical PASS, B0-A not authorized, S1-A2 undefined/blocked.
- Keep CM-01 parallel and optional; do not make it a dependency of core enforcement validation.

## Limitations

- Model-free mechanical benchmark only. Model turns, input/output tokens, model-visible intermediate context, model latency and model-mediated efficiency are `NOT_MEASURED`.
- The two original runs are two sequential executions within one Node process, each using fresh MCP child processes, followed by independent fresh-worktree reproduction. They are not two separate Node-process executions.
- Original raw transport logs do not contain the full MCP initialize exchange; the inbound initialize response is logged in the cancellation child-event traces.
- Mechanical timing is local, environment-specific and excludes some connection, handshake and teardown lifecycle overhead.
- Ground truth is derived from the frozen fixture, so this validates retrieval/projection fidelity and exact composition rather than independent recomputation of Mneme identity digests.
- No statistical-power claim for B0-A. B0-A remains unauthorized.
- No production integration, Workers, hardened isolation, server-side termination, or S1-A2 claim.

## Evidence

- `evidence/run1.json`, `evidence/run2.json` - full per-run task/arm results.
- `evidence/verdict.json` - PASS/FAIL, checks, source hashes, preservation.
- `evidence/measurements.json` - mechanical timings, MCP calls, sizes, `NOT_MEASURED` model fields.
- `evidence/verification.json` - original independent verifier and fresh-checkout reproduction.
- `evidence/versions.json` - pinned versions.
- `evidence/raw/` - raw MCP transport, harness, host, child stderr and cancellation logs.
- `supplemental/verification.json` - supplemental raw-transport reconstruction and hash-pin record.
- `supplemental/verification.sha256` - separate SHA-256 of the supplemental record.
- `SUPPLEMENTAL-VERIFICATION.md` - human-readable supplemental verification and portability record.
