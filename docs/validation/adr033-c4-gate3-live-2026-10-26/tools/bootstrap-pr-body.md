## ADR-033 C4 Gate 3 bootstrap (lab only)

Replaces the CI1 gate steps in `.github/workflows/ci1-trusted-gate.yml` with the C4 availability adapter, as authorized by the owner for C4 Gate 3 on 2026-10-26. One file changes. No ruleset, Actions policy or memory change in this PR.

**Pins (all verified by the workflow before the adapter runs):**

| Item | Value |
|---|---|
| Adapter | `MnemeHQ/mneme@c51729f78199203fe12fcbc5c678b89a2c4f7d3e:scripts/ci/adr033_c4_gate.py`, mode `100644`, blob `5feedf60ce1a67b2bb85673354c8b8b367a87d06`, SHA-256 `afe1d69c1ce4170875989c5866bb2ec7b5089fc895efa699ced826317e3777f9` |
| Evaluator | rebuilt from `0b74d410`, required wheel SHA-256 `e3fcc769…` (unchanged CI1 steps) |
| Violation mode | literal `strict` (R2) |
| Posture | `vars.MNEME_CI_AVAILABILITY` (A3; missing/invalid → closed) |
| Trusted surface | adapter defaults (`.github/`, `.gitattributes`, `.gitmodules`) + `gate/`, `p2/`, `policy/` |
| Required check | job name `CI1 trusted gate` unchanged |

**Changed steps:** new "Check out the adapter at the reviewed commit" and "Verify the adapter pins before running it"; "Evaluate the PR" runs `adr033_c4_gate.py evaluate` and copies its summary into the job summary; "Gate decision" runs `verify-report` instead of the CI1 `passed/verdict` check. Base checkout, head fetch with the freshness check, evaluator rebuild and hash-locked install are unchanged.

**Expected on this PR:** the current CI1 gate refuses it (`.github/` is on its trusted surface), so the check fails. The plan is a recorded admin merge: ruleset 25313704 to `disabled`, squash-merge this exact head, ruleset back to `active`, snapshots compared.

**Offline dry run** of this file's own `run:` blocks in `ubuntu:24.04` with `/usr/bin/python3.12` and the approved evaluator: L1 closed compliant → PASS/success; L2 closed symlink → UNEVALUATED/failure; L3 open symlink → UNEVALUATED/success with `::warning::`; L4 open `gate/` change → REFUSED/failure; L5 open `install legacy-client` → VIOLATION/failure; unset and `Open` posture → closed/failure. 7/7 as expected.

**Known:** `tests/test_gate_workflow.py` and `gate/ci1_gate.py` describe the CI1 gate and are not updated; the workflow no longer runs `gate/ci1_gate.py`.
