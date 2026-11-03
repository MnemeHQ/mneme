# GitHub Actions trusted availability gate (ADR-033 C4)

**Status: Experimental.** The adapter is validated offline
([Gate 2 record](../validation/adr033-c4-gate2-offline-2026-10-26.md), #680)
and live in an isolated GitHub lab
([Gate 3 record](../validation/adr033-c4-gate3-live-2026-10-26.md), #681),
and C4 is closed as a bounded milestone
([closure record](../validation/adr033-c4-closure-2026-10-26.md)). It is
**not** enabled on Mneme Core's CI and is not a production-ready or general
fail-closed enforcement claim. Core's `mneme-check.yml` stays advisory (an
implicit, undeclared `open`; ADR-033 §5). Any adoption needs a separate rollout
decision.

Governing documents: [ADR-033](../adr/ADR-033-opt-in-fail-closed-enforcement.md)
§§1-2 and 5-7; the [C4 Gate 0 charter](../plans/2026-10-26-adr033-c4-ci-availability-charter.md)
(#676, amendments A1-A5); the [C4 Gate 1 charter](../plans/2026-10-26-adr033-c4-gate1-implementation-charter-proposal.md)
(#677, review fixes R1-R3); the Layer 1 freeze amendment (#678).

## What it does

`scripts/ci/adr033_c4_gate.py` turns `mneme check --json` results for a pull
request into one required-check outcome, keeping three things apart:

- **Trusted rule results:** a coherent, complete `mneme.check/v1` payload keeps
  its `strict`/`warn` meaning.
- **UNEVALUATED:** the check could not run, did not finish, or its output was
  not trustworthy. Never a rule FAIL and never a PASS.
- **Policy refusal:** the PR changes `.mneme/`, the trusted CI surface, or a
  path the gate cannot show is outside them. Non-success under every posture.

It is CI merge verification, not pre-write interception (ADR-021).

## Trust model

The adapter runs from the base revision of a `pull_request_target` workflow.
The PR head is fetched as git objects only and never checked out, imported or
executed. Decision memory is read from the base commit. A PR cannot set:

- the **availability posture**, read from the repository Actions variable
  `MNEME_CI_AVAILABILITY` (administrative trust, ADR-033 §5, P7/P8);
- the **violation mode**, a literal `--mode` constant in the trusted workflow;
- the **trusted surface**, `.github/`, `.gitattributes`, `.gitmodules` plus any
  `--trusted-surface` entries in the trusted workflow;
- the **evaluator**, the CI1-approved build of `0b74d410` (wheel sha256
  `e3fcc769c440ed232ad05117f256739daf233e0c9f6d3d46586adc0de9b48c51`).

This holds only while the trusted surface is protected from ordinary PRs and
while nobody with administrator rights (including an agent token that has
them) changes the variable, ruleset, workflow or Actions policy.

## Decision rules

Paths are classified before file types (A1):

1. An unnormalizable path (absolute, backslash, NUL, invalid UTF-8, empty,
   `.` or `..` component) is REFUSED.
2. Anything under `.mneme/` or on the trusted surface is REFUSED, for any
   change type and any file mode. Matching is case-insensitive.
3. A deletion elsewhere is SKIP.
4. A symlink, submodule or other non-regular entry elsewhere is UNEVALUATED.
5. Every other file is evaluated.

If the change list itself cannot be established, or a `--trusted-surface`
entry is not a normalized path (a directory takes exactly one trailing `/`, so
`gate//` is invalid), the result is REFUSED.

Per-file results combine as REFUSED > strict VIOLATION > UNEVALUATED > WARN >
PASS (A2). Under `strict`, a trusted WARN or FAIL is a strict violation (R1).
A run with only SKIP results is SKIP, never PASS.

| Aggregate | `closed` | `open` |
| --- | --- | --- |
| PASS, WARN (warn mode), SKIP | success | success |
| UNEVALUATED | failure | success, labelled UNEVALUATED |
| VIOLATION (strict) | failure | failure |
| REFUSED | failure | failure |

A missing variable, or any value other than exactly `open` or `closed`, means
`closed` with a visible warning.

## Configuration

`evaluate` judges one PR and writes the report:

```bash
python -I scripts/ci/adr033_c4_gate.py evaluate --repo base --base-sha "$BASE_SHA" --head-sha "$HEAD_SHA" --mode strict --workspace "$RUNNER_TEMP/ws" --empty-dir "$RUNNER_TEMP/empty" --venv-python "$EVALUATOR_PYTHON" --evaluator-commit "$EVALUATOR_COMMIT" --evaluator-wheel-sha256 "$APPROVED_WHEEL_SHA256" --trusted-surface gate/ --report "$RUNNER_TEMP/gate-out/gate-report.json" --summary "$GITHUB_STEP_SUMMARY"
```

`verify-report` is the decision step. It never takes the adapter's exit code
alone: it re-reads the posture variable, recomputes the aggregate and
disposition from the per-file results, and checks the base and head SHAs, mode,
adapter SHA-256, evaluator commit and evaluator wheel SHA-256 against the
trusted workflow's values; a missing trusted value fails too. An `open` UNEVALUATED success also needs its `::warning::` annotation
and job-summary entry. Anything missing or inconsistent fails the check.

```bash
python -I scripts/ci/adr033_c4_gate.py verify-report --report "$RUNNER_TEMP/gate-out/gate-report.json" --adapter-exit "$GATE_EXIT" --base-sha "$BASE_SHA" --head-sha "$HEAD_SHA" --mode strict --adapter-sha256 "$ADAPTER_SHA256" --evaluator-commit "$EVALUATOR_COMMIT" --evaluator-wheel-sha256 "$APPROVED_WHEEL_SHA256" --summary "$GITHUB_STEP_SUMMARY"
```

Both steps belong to the one genuine required check. The adapter creates no
Checks API run and no second check identity.

Before running the adapter, the trusted workflow must fetch it from an exact,
reviewed Core commit and path (never from the PR or a mutable branch) and verify
its git blob id and content SHA-256. If that preflight fails, the check fails
under every posture.

## Reference workflow and required check

The workflow validated in the isolated lab is kept as evidence:
[`bootstrap-ci1-trusted-gate.yml`](../validation/adr033-c4-gate3-live-2026-10-26/bootstrap-ci1-trusted-gate.yml).
It is a reference, not an installable product. Using it in a repository needs:

1. **The workflow on the default branch.** `pull_request_target` always runs the
   base branch's copy, so the workflow governs PRs only after it is merged. A
   gate that protects `.github/` refuses its own installation PR; the lab merged
   it through a recorded administrator operation (Gate 3 record §3).
2. **The adapter pins** (`ADAPTER_COMMIT`, `ADAPTER_PATH`, `ADAPTER_BLOB`,
   `ADAPTER_SHA256`) and the evaluator pins (`EVALUATOR_COMMIT`,
   `APPROVED_WHEEL_SHA256`, a hash-locked runtime lock file and build
   constraints) set to reviewed values.
3. **Trusted-surface entries** covering every file the workflow reads
   (`--trusted-surface`; `.github/`, `.gitattributes` and `.gitmodules` are
   always included).
4. **A ruleset or branch protection** that requires the job's check name
   (`CI1 trusted gate` in the lab) from the GitHub Actions app, with no bypass
   actors.
5. **An Actions policy** that allows `pull_request_target` for this workflow,
   where the organization restricts it.
6. **The repository variable** `MNEME_CI_AVAILABILITY` set by an administrator
   to `closed` or `open`. Leaving it unset means `closed`.

## Outputs

The report (`mneme.c4.gate-report/v1`, adapter-internal, not a public CLI
schema) records the adapter and evaluator identity, base, head and merge-base
SHAs, the requested mode, the effective posture and any fallback, the trusted
surface, the trusted memory blob, every file's classification, kind and reason,
raw evaluator output, applicability traces, the aggregate and the disposition.

An `EXCLUDED` result is a trusted PASS for the check but is not ADR-029
"relevant enforcement observed". Neither is a green check, a SKIP or a process
exit by itself.

## Limitations

- Changing the posture does not re-run checks. A head that turned green under
  `open` stays green after the variable switches to `closed` until the check is
  re-run.
- If the runner or the adapter never starts, or no valid report exists, there
  is no UNEVALUATED report to deliver and the check fails. Host timeouts and
  outages outside the job are not covered.
- Literal-tier rules only, as in CI1 (fixed query, ADR-017). ADR-034 numeric or
  `subject` records in a payload are treated as UNEVALUATED.
- Unicode normalization variants of protected paths (for example NFD on macOS)
  are not matched; only case variants are.
- The decision step runs the same script as the evaluation step, so it catches
  an inconsistent or tampered report but not a defect shared by both.
- The per-file report records path, content SHA-256 and head SHA, not the
  file's git blob id.
- The CI1 limits stay: administrative P7/P8 exposure (an administrator can
  disable the ruleset, as the lab bootstrap did), no governed decision update
  route, rule coverage only as wide as the include selectors, partial ADR-029
  binding, untested merge races. GitHub `pull_request_target` behavior after
  2026-11-02 is unverified.

## Release implications

None. The adapter is a standalone, standard-library-only script outside the
`mneme-hq` wheel, so installing or upgrading `mneme-hq` does not install it, and
no `mneme-hq` release is needed for it. The Gate 2 and Gate 3 evidence exists;
adoption by any repository, including Mneme Core, still needs a separate
rollout decision with its own Layer 1 authorization.
