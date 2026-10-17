# CI1.3 P2: pinned-evaluator preflight (offline)

**Status:** validation record. **P2 is NOT met by `mneme-hq==0.10.0`.** The
release does not reproduce the CI1.2 corpus. A commit build of `main` @
`0b74d410` reproduces all of it. Choosing that build as the pinned evaluator is
a decision for the CI1.3 approvals. This record does not make it.
**Scope:** offline replay only. No lab repository, ruleset, workflow, Core,
enforcement engine, `.mneme/` or fixture expectation is changed. Strict mode is
not enabled anywhere. The `v1` goldens are untouched.
**Contract:** [CI1.3 charter](../plans/2026-10-17-ci1-3-isolated-merge-blocking-experiment-charter.md)
§4 (P2) and §4a. **Tracker:** #540, including its P2 coverage note.
**Corpus anchor:** `tests/fixtures/ci1_contract` tree `c8ee9e39`. It is the
same at `main` @ `0b74d410` (#541) and at the harness commit. The canonical
`.mneme/project_memory.json` blob is `5002a6c0`, and the
`tests/test_ci1_contract_matrix.py` blob is `1646e1bd`.
**Harness:** [`scripts/ci1_evaluator_preflight.py`](../../scripts/ci1_evaluator_preflight.py),
with offline unit tests in
[`tests/test_ci1_evaluator_preflight.py`](../../tests/test_ci1_evaluator_preflight.py).

## 1. Why a separate replay

The merged CI1.2 runners set `PYTHONPATH` to the checkout, so they always test
the checkout's Mneme and never a release (charter §4a). The preflight replays
the committed corpus *data* against an installed build:

- **Install.** It creates a fresh venv and runs `pip download --only-binary=:all: mneme-hq==0.10.0`.
  Every downloaded wheel's sha256 is checked against PyPI's JSON API. The
  `mneme-hq` wheel is also checked against the digest pinned in the harness.
  Then `pip install --require-hashes --no-index --no-deps` installs from that
  verified, hash-locked set.
- **Execution.** It runs `<venv python> -I -m mneme.cli` with `PYTHONPATH`,
  `PYTHONHOME` and similar variables removed. The working directory is a
  scratch directory outside any checkout, and each corpus `vN/` is copied
  there first.
- **Identity, before and after the replay (hard failure).** The checks cover
  the interpreter and `sys.prefix` inside the venv, isolated mode, and
  `mneme.__file__` and `mneme.cli.__file__` inside the venv's site-packages and
  not the checkout. No `sys.path` entry may point into the checkout. The checks
  also cover `importlib.metadata.version`, the `mneme` console-script metadata,
  every installed file against the wheel's own `RECORD` hash, and the absence
  of any module the wheel did not ship.
- **Comparison.** Each case is compared with the expectation that applies to
  it. Golden cases compare payload, exit code and classification for every
  query variant, after the README's record sort, with empty stderr where the
  merged runner requires it. `memory_errors/v1` cases compare empty stdout,
  the recorded stderr form and the exit code in both modes. A traceback must
  not name a file in the checkout.
- **Separate checks.** These are reported apart from the replay, as the #540
  coverage note requires: the ADR-005 global-rule cross-check, corpus memory
  regeneration through the installed `decision-index migrate` and
  `adr import`, and the classifier stub battery. The classifier is the merged
  `classify` from `tests/test_ci1_contract_matrix.py`, loaded from that file
  and not copied. It also classifies every real output in the replay and the
  ADR-005 check.

## 2. Result: `mneme-hq==0.10.0` (PyPI)

Full per-case record: [`mneme-hq-0.10.0.md`](ci1-3-p2-pinned-evaluator-preflight-2026-10-17/mneme-hq-0.10.0.md).

Evaluator identity verified and unchanged after the replay. The wheel was
`mneme_hq-0.10.0-py3-none-any.whl`, sha256
`fc7e0ec7191e243e998055d34e5764e473aa439ecdc40c22a969acf376ec5312` (local,
PyPI and pinned all match). 110 installed files matched the wheel `RECORD`.
The host was Windows 11 with Python 3.12.10.

| Check | Runs | Parity |
|---|---|---|
| Manifest replay | 46 | **13** |
| ADR-005 cross-check | 13 | **1** |
| Corpus memory regeneration | 2 | **0** |
| Classifier stubs | 35 | 35 |

Failing cases, grouped by cause:

| Corpus / check | Failing | Observed in 0.10.0 |
|---|---|---|
| `path_scoped_forbid_literal/v1` | all 5 cases × 3 variants (15) | `mneme check` crashes before evaluating. stderr ends `DecisionIndexPersistenceError: decision_index schema must be 'mneme.decision-index/v1'`, exit 1, no payload, classified UNEVALUATED. The corpus memory is `mneme.decision-index/v2` |
| `incomplete_evaluation/v1` | all 5 cases × 3 variants (15) | Same crash and the same cause (v2 index) |
| `warn_verdict/v1` | `warn_strict`, `warn_warn_mode`, `fail_warn_mode` | Verdict, exit code and classification match. The legacy-constraint violation records lack the `rule_id` and `decision_version_id` keys, which the goldens carry as `null` |
| `warn_verdict/v1` | (passes) `pass_strict` | No records, so nothing to differ |
| `memory_errors/v1` | none (12/12 pass) | Same stdout, stderr form and exit codes as the goldens record |
| ADR-005 cross-check | all 8 violation runs and all 4 `mneme-hq` runs | **Behaviour matches**: FAIL, exit 2, VIOLATION, APPLIED, `path_scoped: false` on every path and query, and PASS, exit 0, VERIFIED_PASS for `mneme-hq`. It fails because the records carry no `rule_id` or `decision_version_id`, so the canonical rule identity (`ADR-005:FORBID_LITERAL:cbf4d271…`) cannot be bound. The memory-only rule-shape check passes |
| Regeneration | both ADR-derived corpora | 0.10.0 writes `mneme.decision-index/v1`, and the committed memory is `v2` |

The failures have two causes. 0.10.0 predates decision-index v2 (DG1B1
canonical applicability, #487, merged 2026-10-13). It also does not emit
canonical rule identity on `mneme check` records (DG1E evidence identity,
#469, merged 2026-10-08). Both landed after the `v0.10.0` tag (2026-10-07).
These causes are attributed from the observed error and missing fields plus
the merge dates. They were not bisected.

**Correction to the charter.** The merged P2 row (#541) said that `v0.10.0`
"carries `evaluation_complete`, `rule_id` and `decision_version_id`". This PR
replaces that row. The `0.10.0`
check payload carries `evaluation_complete`, but its `applicability` and
`violations` records carry neither `rule_id` nor `decision_version_id`, and it
cannot load a v2 decision index at all.

**Hazard seen in passing.** On the corpus memory, 0.10.0 exits 1 with no
payload. That is the strict WARN exit code. An adapter that maps exit codes
alone would read every one of those 30 crashes as WARN, which is the
`memory_errors` collision the CI1.2.2 README already pins.

## 3. Fallback: commit build of `main` @ `0b74d410` (control)

Full per-case record: [`commit-build-0b74d410.md`](ci1-3-p2-pinned-evaluator-preflight-2026-10-17/commit-build-0b74d410.md).

The charter's fallback is to pin a `MnemeHQ/mneme` commit build. The same
harness ran with `--commit-build 0b74d410`. The source came from
`git archive` into the scratch directory, so the working tree was not read.
The wheel was built with `pip wheel --no-deps`, and the dependencies were
hash-checked against PyPI as above.

| Check | Runs | Parity |
|---|---|---|
| Manifest replay | 46 | 46 |
| ADR-005 cross-check | 13 | 13 |
| Corpus memory regeneration | 2 | 2 |
| Classifier stubs | 35 | 35 |

The built wheel's sha256 was
`e0ca654ec54bc43649260c1b748e492ce8dad8bc4bf8cf18791c4c8ecca2d113`. This run
also serves as the harness's positive control: the same replay logic that
fails 0.10.0 passes a build that matches the corpus.

Caveats for anyone pinning this build:

- **The version string does not identify the evaluator.** `main`'s
  `pyproject.toml` still says `0.10.0`, so the commit build reports
  `importlib.metadata.version("mneme-hq") == "0.10.0"`, exactly like the
  release that fails. The pin must be the commit SHA plus the wheel sha256,
  never the version.
- **Reproducibility of the wheel hash was not tested.** A lab workflow that
  rebuilds from the commit should record its own wheel hash, or consume one
  stored build artifact.
- **The build backend is not hash-locked.** pip's build isolation fetched
  `setuptools` without hash checking. The runtime dependency set and the
  built wheel are hash-locked.

## 4. Not covered

- **Linux.** Both runs were on Windows. The lab workflow will run on a GitHub
  Linux runner. Rerunning the harness there is cheap (`python
  scripts/ci1_evaluator_preflight.py ...`) and is recommended once the pin is
  chosen.
- **Network-free execution.** The install step needs PyPI. The unit tests in
  the battery are offline and use fakes. They do not install anything.
- **Dependency drift.** The resolved runtime dependency set (listed in each
  per-run record) is whatever PyPI served on 2026-10-17. Only `mneme-hq`
  itself is pinned by the harness.

## 5. Reproduce

```bash
python scripts/ci1_evaluator_preflight.py --version 0.10.0 --record-out <file.md> --json-out <file.json>
python scripts/ci1_evaluator_preflight.py --commit-build 0b74d410 --record-out <file.md>
```

Exit codes: 0 means full parity, 1 means parity failures (recorded), and 2
means the evaluator identity or install could not be verified, so nothing was
replayed.
