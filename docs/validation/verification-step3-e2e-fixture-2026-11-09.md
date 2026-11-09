# Verification step 3: frozen end-to-end fixture, two checkpoints

**Date:** 2026-11-09
**Authorization:** owner authorization of Verification step 3 with the approved
pins, 2026-11-09, under the [roadmap Verification slice](../roadmap/README.md)
(#579, #768). Step 4 (independent review) is not authorized.
**Type:** validation record. No runtime, schema, DecisionRetriever,
ConflictDetector, enforcement, CI workflow, evaluator pin or benchmark change.

## 1. Result

**13 of 13 verification checks pass, with 60 of 60 observation assertions.**
The fixture shows, for one reviewed decision and one typed rule:

- **A prohibited mutation is prevented at the pre-mutation checkpoint.** The
  LangChain middleware denied the write, the handler was never called, and the
  target stayed absent (new file) or byte-identical (existing file).
- **A CI revision is evaluated independently.** The pinned C4 adapter with the
  approved `0b74d410` evaluator evaluated the resulting revision (PASS) and a
  revision carrying the same prohibited content by another route (VIOLATION).
- **The cross-checkpoint claim is established only where the evidence allows
  it.** The allowed change carries the same full identity and the same subject
  digest at both checkpoints. Missing identity and a later revision are
  rejected.

**Every observation is at most "execution observed".** No checkpoint reaches
ADR-029 "relevant enforcement observed". For this literal rule, neither
evaluator emits a subject record, so ADR-029 dimension 2 is never bound by
Mneme (#761 E-2). This was the expected and accepted ceiling. The levels are
derived from each record's own fields, not asserted by the harness (§3).

Three things this record keeps apart:

| Statement | Established? |
|---|---|
| A prohibited mutation was prevented (A2, A3) | **yes**, observed on disk |
| A CI revision was evaluated independently (B1, B2) | **yes**, offline replay of the pinned gate |
| The evidence is sufficient for an ADR-029 relevant-enforcement claim | **no**, execution observed only |

## 2. Pins

| Component | Pin | Checked by the harness |
|---|---|---|
| Decision / rule | `ADR-901`, `FORBID_LITERAL "install legacy-client"`, `include_paths: ["docs/**"]`, `exclude_paths: ["docs/history/**"]` | identity read back at both checkpoints |
| Decision memory | blob `4c669436` (`docs/integrations/c4-gate/project_memory.example.json`) | `git hash-object` before running |
| Identity (both checkpoints) | `decision_version_id` `dver-d3d431ff6d5edba8b555a040a7b85f9b`, `rule_id` `ADR-901:FORBID_LITERAL:1eff1b82c5be57bd80379f967b799f7b` | asserted per check |
| Pre-mutation evaluator | v0.11.0, `619d5405e80da61788448a7a0eeacc7c5eb3d0c0`, run from a detached checkout | refuses any other commit or a dirty `mneme/` |
| Pre-mutation surface | LangChain `ToolGateMiddleware` (`mneme/integrations/langchain`, langchain 1.4.0) with a local file-writing handler | `mneme` import location and the checker subprocess's import location both verified |
| CI evaluator | `mneme-hq` 0.10.0, commit build of `0b74d410`, approved wheel sha256 `e3fcc769c440ed232ad05117f256739daf233e0c9f6d3d46586adc0de9b48c51`, hash-locked runtime from the C4 Gate 2 inputs | wheel hash on host and in the container |
| CI adapter | `c51729f7`, `scripts/ci/adr033_c4_gate.py`, blob `5feedf60`, sha256 `afe1d69c…` | blob on host, sha256 in the container |
| CI execution | offline Gate 2-style replay in `ubuntu@sha256:68ee2200…` (Ubuntu 24.04.5, Python 3.12.3), posture `closed`, mode `strict`, `evaluate` then `verify-report` as in the trusted gate workflow | [`ci-reports/pins.txt`](artifacts/verification-step3-e2e-fixture/ci-reports/pins.txt) |

**The CI checkpoint is not a GitHub Actions observation,** and its results are
`0b74d410` evidence, never v0.11.0 evidence. The two evaluators produced the
same canonical identity for `ADR-901`. That is an observed fact for this
memory, not a general compatibility claim.

## 3. Method

The harness is
[`run_step3.py`](artifacts/verification-step3-e2e-fixture/run_step3.py), with the
container script
[`ci_replay.sh`](artifacts/verification-step3-e2e-fixture/ci_replay.sh).

**Checkpoint A (pre-mutation).** For each case the harness builds a project
with the fixture memory and calls `ToolGateMiddleware.wrap_tool_call` with a
real `ToolCallRequest` and a handler that writes the file. Only the middleware
decides whether the handler runs. An observation-only wrapper records the
`GateResult` that `evaluate_tool_call` returned, so the payload's identity is
captured; it changes nothing. The checkpoint runs from a neutral working
directory (§5, O-3).

**Checkpoint B (CI).** The harness builds a fixture git repository with git
plumbing (fixed author, committer and dates, so commit SHAs are deterministic;
a symlink is a mode `120000` tree entry, so it works on any host). The
container installs the approved wheel hash-locked, verifies the adapter, and
runs `evaluate` and `verify-report` for each base/head pair. The resulting
revision for B1 contains the exact bytes A1's handler wrote.

**Verification.** For each case the harness asserts the expected runtime
observations and derives the evidence level from the record itself:

- not executed if nothing was evaluated (`fail_open`, `skip`, no trusted
  payload, or a CI file classified UNEVALUATED/REFUSED/SKIP);
- relevant only if Mneme emitted a subject record **and** identity is complete
  **and** applicability is `APPLIED`;
- execution observed otherwise.

A cross-checkpoint claim takes the weaker of the two levels. It is
established only if both identities are complete and equal as the full
`(decision_id, decision_version_id, rule_id)` tuple (Step 2 N-2), **and** the
pre-mutation subject digest equals the CI file's content digest.

The pre-mutation subject digest is computed by the harness from the tool
arguments. Mneme emits none for literal-only checks.

**Reproduce:**

```bash
git worktree add --detach ../mneme-619d5405 619d5405
python docs/validation/artifacts/verification-step3-e2e-fixture/run_step3.py --runtime-root ../mneme-619d5405 --approved-wheel <path to the approved wheel>
git worktree remove ../mneme-619d5405
```

It needs Docker and network access inside the container for the hash-locked
pip install. The approved wheel is not republished (C4 Gate 2 record §1). The
harness refuses (exit 2) on any pin mismatch, and exits 1 if any check
fails. It rewrites `results.json` and `ci-reports/`.

## 4. Cases: expected versus actual

### Checkpoint A: pre-mutation (v0.11.0, LangChain middleware)

| Case | Tool call | Action / verdict | Handler | Target before → after | Identity | Level |
|---|---|---|---|---|---|---|
| A1 allow | `write_file docs/guide.md` (neutral) | allow / PASS | called | absent → `37c6e073…` (= attempted content) | complete | execution |
| A2 deny, new file | `write_file docs/install.md` (forbidden) | deny / FAIL, `[mneme] DENIED` | **not called** | absent → **absent** | complete; violation names the rule | execution |
| A3 deny, existing file | `edit_file docs/readme.md` adding the forbidden line | deny / FAIL, `[mneme] DENIED` | **not called** | `20dfecfb…` → **`20dfecfb…`** | complete | execution |
| A4 incomplete | `write_file ../outside/notes.md` (forbidden; outside the policy root) | **fail_open** / PASS, `evaluation_complete: false`, applicability `UNKNOWN`, `[mneme] UNEVALUATED` | called (fail open) | absent → written | complete | **not executed** |
| A5 missing identity | section-less memory; `write_file docs/install.md` (forbidden) | deny / FAIL | not called | absent → absent | `decision_version_id` **empty** | execution |

### Checkpoint B: CI (offline replay, `0b74d410`, posture closed)

| Case | Base → head | Change | Aggregate / disposition | File result | Identity | Level |
|---|---|---|---|---|---|---|
| B1 allow | `978de46e` → `e7b90432` | `docs/guide.md` = A1's written bytes | PASS / success | `VERIFIED_PASS`, `37c6e073…` | complete | execution |
| B2 bypass | `978de46e` → `99bdbccb` | `docs/install.md` = A2's denied content, by another route | VIOLATION / failure | `VIOLATION`, `04f34575…` | complete | execution |
| B3 incomplete | `978de46e` → `1729a0ab` | `docs/link.md` symlink | UNEVALUATED / failure | `UNEVALUATED` (kind `mode`) | none | **not executed** |
| B4 missing identity | `cff670b1` → `d7e9451f` | section-less memory (blob `65d9f95d`); forbidden file | VIOLATION / failure | `VIOLATION` | `decision_version_id` **empty** | execution |
| B5 later revision | `e7b90432` → `f77bd0f8` | `docs/guide.md` edited after A1 | PASS / success | `VERIFIED_PASS`, `424fb9f4…` | complete | execution |

### Verification checks

| Check | Acceptance criterion | Result |
|---|---|---|
| V1 allow (A1, B1, linkage) | permitted content reaches the handler and the file; CI evaluates that revision; same full identity and same digest `37c6e073…` at both | PASS (3 checks) |
| V2 deny (A2, A3, B2) | rejected, handler not called, target absent/unchanged; the same bytes arriving by another route are a CI violation (`04f34575…` at both) | PASS (3 checks) |
| V3 incomplete (A4, B3) | evaluation cannot establish compliance and says so: UNEVALUATED at both, not executed | PASS (2 checks) |
| V4 missing identity (A5, B4, linkage) | the rule still blocks, but identity is incomplete at both and no cross-checkpoint claim is made | PASS (3 checks) |
| V5 stale evidence (A1 vs B5, B1 vs B5) | A1's evidence cannot verify the later `docs/guide.md` (`37c6e073…` ≠ `424fb9f4…`, though the identity is the same); B1's report is bound to `e7b90432`, not `f77bd0f8` | PASS (2 checks) |

`results.json` holds every expected and actual value. `ci-reports/` holds the
five raw `mneme.c4.gate-report/v1` reports.

**Sensitivity check.** Forcing the middleware into warn mode (not committed)
made V2 (both) and V4 fail on `action`, `handler_called`, `target_unchanged`
and the tool marker. In warn mode the forbidden content was written. The
checks detect a change in enforcement outcome; they do not only check labels.

**Reproducibility.** Two consecutive normal runs produced byte-identical
`results.json`. Running with `--runtime-root` at a non-pinned checkout, or with
a file that is not the approved wheel, was refused (exit 2).

## 5. Observations

| ID | Observation | Kind |
|---|---|---|
| O-1 | **Fail-open writes on incomplete evaluation (A4).** With the target outside the policy root, applicability is `UNKNOWN`, the adapter fails open, and the handler writes the forbidden content. The tool result carries `[mneme] UNEVALUATED`, so it is visible, and the evidence is not executed. This is the documented adapter policy (#769), not a new defect. | observation |
| O-2 | **Identity agrees across evaluator versions, subjects do not cross.** v0.11.0 and `0b74d410` produced the same full identity for `ADR-901`. Linkage then turns on the subject digest: B1 links to A1, and B5 (same identity) does not. Matching on `rule_id` alone would have accepted B5 (Step 2 N-2). | finding |
| O-3 | **The checker subprocess can import the wrong `mneme`.** `python -m mneme check` puts its working directory first on `sys.path`, ahead of the pinned `PYTHONPATH` from `_child_env`. Run from a directory that contains a `mneme/` package (this repository, for example), it imports that package instead of the adapter's own. The harness detected this and runs from a neutral directory. It does not affect user projects without a `mneme/` package; it matters for dogfooding inside Mneme's own repo. | observation; no runtime change here |
| O-4 | **The CI replay records the memory it evaluated** (blob and source commit, B1 `4c669436`, B4 `65d9f95d`). The pre-mutation checkpoint does not. Memory-wide configuration stays a documented limitation, not a blocker (#761 §5.1, E-4). | consistent with #761 |
| O-5 | **B3 has no memory record.** The symlink is classified UNEVALUATED before any evaluation, so nothing ties the result to a memory. Correctly not executed. | observation |

## 6. What this record does not claim

- No relevant enforcement observed, at either checkpoint.
- No GitHub Actions observation. The CI checkpoint is an offline replay of the
  pinned gate.
- No coverage across agent hosts. The local LangChain handler shows the
  middleware's deny path only; it says nothing about Claude Code, the Agent SDK
  host, other LangChain tools or raw `StateGraph` graphs.
- No equivalence between `0b74d410` and v0.11.0 beyond the identity observed
  for this one memory.
- No authenticity or attestation of any record (ADR-025), no waiver semantics,
  no change to any earlier result, and no authorization of step 4.
