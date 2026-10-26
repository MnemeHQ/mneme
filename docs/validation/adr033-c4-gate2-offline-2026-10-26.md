# ADR-033 C4 Gate 2: offline validation of the CI availability adapter, 2026-10-26

**Status:** evidence record for review. This records the one authorized Gate 2
run: the merged C4 adapter, pinned at `c51729f7`, against the CI1-approved
evaluator, on Linux with Python 3.12. It changes no implementation, fixture,
workflow, ruleset, Actions setting or lab. Gates 3 and 4 are not authorized.

**Result: PASS on every step. No failures, no skips, no deviations.**

| Step | Result |
|---|---|
| Pin checks (adapter commit, blob, mode, SHA-256; wheel SHA-256; lock SHA-256; clean checkout) | all verified before any test ran |
| `tests/test_adr033_c4_ci_gate.py`, real-evaluator group on the approved evaluator | **323 passed**, 0 skipped, 0 failed |
| CI1.2 corpora replay against the approved evaluator | **PASS**: manifest replay 46/46, ADR-005 cross-check 13/13, memory regeneration 2/2, classifier stubs 35/35; identity re-checked after the replay |
| CI1 contract tests (`test_ci1_contract_fixtures.py`, `test_ci1_contract_matrix.py`) on the pinned tree | **123 passed** |
| Frozen canonical benchmark, approved evaluator | Layer 2 **7/7**, 100%; Layer 1 mean recall@3 1.00, precision@3 0.33 |
| Frozen canonical benchmark, pinned tree | identical: 7/7, 100%; recall@3 1.00, precision@3 0.33 |

## 1. Authorization and scope

- **Owner authorization (2026-10-26, Mneme Core conversation):** "Authorize C4
  Gate 2 as scoped: adapter pinned at c51729f7, preserved hash-verified
  0b74d410 wheel, Linux Python 3.12, record results in a docs/validation PR. No
  implementation change, no lab change." Recorded on the owner's behalf; not a
  separate GitHub review.
- **Governing documents:** ADR-033 §§1-2 and 5-7; the
  [C4 Gate 0 charter](../plans/2026-10-26-adr033-c4-ci-availability-charter.md)
  (#676, A1-A5); the
  [C4 Gate 1 charter](../plans/2026-10-26-adr033-c4-gate1-implementation-charter-proposal.md)
  (#677, R1-R3; §5 offline protocol, §6 evidence); the Layer 1 freeze
  amendment (#678); the adapter implementation (#679).
- **Evaluator source decision:** the approved wheel was not rebuilt. A
  preserved copy from the CI1 lab's own P2 run (GitHub Actions run
  `39055862171`, artifact `p2-evaluator-preflight-39055862171`) was used after
  its SHA-256 matched the approved value. A rebuild with a different hash would
  have needed a separate decision.

## 2. Pins and identities

All values were checked by the run script before any test ran
([`run-output/pins.txt`](adr033-c4-gate2-offline-2026-10-26/run-output/pins.txt)).

| Item | Value |
|---|---|
| Core commit | `c51729f78199203fe12fcbc5c678b89a2c4f7d3e` (#679 squash; reviewed head `d98af324`) |
| Adapter | `scripts/ci/adr033_c4_gate.py`, mode `100644`, git blob `5feedf60ce1a67b2bb85673354c8b8b367a87d06`, SHA-256 `afe1d69c1ce4170875989c5866bb2ec7b5089fc895efa699ced826317e3777f9` |
| Test module | `tests/test_adr033_c4_ci_gate.py`, blob `67c407309b19a62a5748c0ba82e0fe70c0c09beb` |
| C4 fixtures | `tests/fixtures/adr033_c4_ci/v1`, tree `5fbecc922dc1fab2333f15501156b5127b9e43c7` |
| CI1 contract fixtures | `tests/fixtures/ci1_contract`, tree `c8ee9e3988210c3ad6f961f54e58d968eb40e6cb` (unchanged) |
| CI1 preflight (functions reused) | `scripts/ci1_evaluator_preflight.py`, blob `6cb9120e1f5b9d2e3e44d0fc84c1fa1f7473e785` |
| Evaluator | `mneme-hq` 0.10.0, commit build of `0b74d410b45e7b3efcf08d00ce58e7bd7017b757`, wheel SHA-256 `e3fcc769c440ed232ad05117f256739daf233e0c9f6d3d46586adc0de9b48c51` (CI1 P2) |
| Evaluator runtime lock | CI1 lab `gate/evaluator-requirements.txt` at lab `3cd402fe`, SHA-256 `e4ef9d786fd2a49f0dc76a9d5304278f92f23d8257e2410f0305dca883ecca8b` ([copy](adr033-c4-gate2-offline-2026-10-26/inputs/evaluator-requirements.txt)) |
| Run script | [`inputs/run_c4_gate2.sh`](adr033-c4-gate2-offline-2026-10-26/inputs/run_c4_gate2.sh), SHA-256 `e6306c412db976a61a7ce3e582763158a6d66c7ebbfe9c720b52ee25f3627434` |
| Replay driver | [`inputs/c4_gate2_ci1_replay.py`](adr033-c4-gate2-offline-2026-10-26/inputs/c4_gate2_ci1_replay.py), SHA-256 `8e1644a8063818ed8f006b357291ee64a56d8bf7c5bc4b57ea9a1d6711570762` |

## 3. Platform

| Item | Value |
|---|---|
| Container image | `ubuntu@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac` (`ubuntu:24.04`, Ubuntu 24.04.5 LTS) |
| Interpreter | `/usr/bin/python3.12`, 3.12.3 (`python3.12` 3.12.3-1ubuntu0.17), the same path the CI1 lab workflow uses on `ubuntu-24.04` |
| Git | 2.43.0 (`1:2.43.0-1ubuntu7.4`) |
| Host | Windows 11 (10.0.26300), Docker Desktop 29.1.2, WSL2 kernel `5.15.167.4-microsoft-standard-WSL2` |
| Run window | 2026-10-26T21:44:41Z to 21:46:27Z |

This is a Linux container on a Windows host, not a GitHub-hosted runner. The
exact command is in
[`inputs/docker-command.txt`](adr033-c4-gate2-offline-2026-10-26/inputs/docker-command.txt).

## 4. Method

The run script cloned the host checkout read-only into the container, checked
out `c51729f7` detached, and stopped on any pin mismatch. It then built two
separate virtual environments:

- **Evaluator venv:** installed exactly as the CI1 lab workflow does it,
  `pip install --require-hashes --only-binary=:all: --no-deps` from the lab lock
  plus the preserved wheel with its approved hash, then the lab's identity probe
  (`mneme.__file__` inside the venv). The adapter's real-evaluator tests and the
  CI1 replay invoke this evaluator only as `python -I -m mneme.cli`.
- **Harness venv:** the pinned checkout installed editable with `[dev]` extras
  (dependencies resolved from PyPI, not hash-locked). It runs pytest and the
  adapter; it is never used as the evaluator. It also provides the shipped
  `assess_verdict` at `c51729f7` for the parity cases.

Steps, each with its full log and exit code in
[`run-output/steps.txt`](adr033-c4-gate2-offline-2026-10-26/run-output/steps.txt):

1. The full adapter test module with `MNEME_C4_EVALUATOR_PYTHON` set to the
   evaluator venv, so the real-evaluator group ran against the approved build.
2. The CI1.2 corpora replay. The driver reuses the merged preflight's identity
   probe, RECORD check, corpus replay, ADR-005 cross-check, memory regeneration
   and classifier checks unchanged; it only skips the preflight's own install
   step (rebuild or PyPI download) because the evaluator venv already exists.
3. The CI1 contract tests on the pinned tree, for reference.
4. The frozen canonical benchmark (`benchmark examples/benchmarks/ --memory
   examples/project_memory.json`) once with the approved evaluator and once
   with the pinned tree.

The checkout stayed clean after the installs and at the end
(`core-status-after-install.txt`, `core-status-end.txt` are empty).

## 5. Results against the Gate 1 charter §5 protocol

| §5 item | Covered by | Result |
|---|---|---|
| All Gate 0 rows (O1-O12, O2w, O8s, O9s, O9p, O9n, O10, O10x, O11) in `closed` and `open` | matrix rows (35, each per mode and posture), O9p path tests, O12 unit and end-to-end tests | pass |
| 1. O7 coherence cross-product and `assess_verdict` parity | 53 payload cases (`agree` / `untrusted` / `stricter`), CI1 stub replay, CI1 classifier comparison, exit-table pin | pass |
| 2. Protected paths: symlink, submodule, deletion, case variants, unnormalizable paths | O8, O8d, O8s, O8c, O9, O9d, O9s, O9u, O9x, O9p, A1-order test | pass |
| 3. Non-protected non-regular entries, materialization and gate errors | O9n, O4, O4s, workspace and invalid-surface tests | pass |
| 4. O11 mixtures, strict and warn, with subordinate detail | O11a-f, O11dw, mixed-detail test | pass |
| 5. O12 missing or invalid posture | posture tests | pass |
| 6. Negative controls: timeout, launch error, wrong pins, bad report, missing summary or annotation, posture mismatch | O6t, O6l, decision-step tests, CLI tests | pass |
| 7. CI1.2 replay, ADR-005, contradictory-output controls; canonical benchmark | CI1 replay (§4 step 2), CI1 contract tests, benchmark | pass; replay counts equal the CI1 P2 Linux record (46/46, 13/13, 2/2, 35/35) |
| 8. Evaluator wheel hash unchanged; no `mneme/` change | pin checks; #679 diff | pass |

The real-evaluator group ran all five cases against the approved evaluator:
CI1.2.1 APPLIED compliant (PASS, success), APPLIED violating in `strict`
(VIOLATION, failure) and in `warn` (WARN, success), and the two EXCLUDED cases
(`docs/history/**` and `src/**`, PASS with applicability `EXCLUDED`).

## 6. What this does not show

- **No live GitHub behavior.** Required-check conclusions, merge refusals,
  annotations and job summaries on GitHub, `pull_request_target` after
  2026-11-02, and the trusted bootstrap that fetches and verifies the adapter
  are Gate 3.
- **Not the lab runner.** The platform matches its OS release and interpreter
  path but is a container on a Windows/WSL2 host.
- **Harness dependencies are not hash-locked.** Only the evaluator venv is.
  The harness only drives tests; it never evaluates a PR.
- **Coverage stays as charted.** Literal-tier rules, the CI1 corpora and the
  Gate 0 matrix. The CI1 limits (P7/P8, no governed decision update, include
  selector coverage, partial ADR-029 binding, merge races) and the adapter's
  documented limits (posture change does not re-run checks, no Unicode
  normalization matching) are unchanged.
- **No ADR-029 "relevant enforcement observed" claim.** These are offline
  results.

## 7. Evidence

[`adr033-c4-gate2-offline-2026-10-26/`](adr033-c4-gate2-offline-2026-10-26/):

- `run-output/`: everything the container wrote: `pins.txt`, `steps.txt`,
  `environment.txt`, `apt-packages.txt`, both pip freezes, install logs,
  evaluator identity, pytest logs and JUnit XML, `ci1-replay.json` and its log,
  both benchmark logs, checkout status files, and the run's own `SHA256SUMS`
  (verified after copying).
- `inputs/`: the run script, the replay driver, the lab lock file, the
  container image digest and the exact `docker run` command.
- `run-output-console.log`: the container's console output.
- `EVIDENCE-SHA256SUMS`: SHA-256 of every file in the folder.

The preserved evaluator wheel is cited by hash and origin, not republished.
Collected files are stored as written; do not re-normalize their line endings,
or the manifests will no longer match.
