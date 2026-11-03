# GitHub Actions trusted availability gate (ADR-033 C4)

**Status: required on Mneme Core's `main` as bounded dogfooding.** The adapter
is validated offline
([Gate 2 record](../validation/adr033-c4-gate2-offline-2026-10-26.md), #680),
live in an isolated GitHub lab
([Gate 3 record](../validation/adr033-c4-gate3-live-2026-10-26.md), #681), and
C4 is closed ([closure record](../validation/adr033-c4-closure-2026-10-26.md)).
The CI production rollout R0 made it a required check on Core
([R0 closure](../validation/ci-r0-s7-closure-2026-11-03.md), #742) and kept it
there as bounded dogfooding
([operating-status decision](../validation/ci-r0-operating-status-decision-2026-11-03.md),
#743). This is **not** a general production-readiness or universal fail-closed
claim: see [Limitations](#limitations). Core's advisory `mneme-check.yml` still
runs but is no longer a required check.

Governing documents: [ADR-033](../adr/ADR-033-opt-in-fail-closed-enforcement.md)
§§1-2 and 5-7; the [C4 Gate 0 charter](../plans/2026-10-26-adr033-c4-ci-availability-charter.md)
(#676, amendments A1-A5); the [C4 Gate 1 charter](../plans/2026-10-26-adr033-c4-gate1-implementation-charter-proposal.md)
(#677, review fixes R1-R3); the Layer 1 freeze amendment (#678); the
[R0 charter](../plans/2026-10-26-ci-r0-production-rollout-readiness-charter.md)
(#684, R6 #718).

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

The adapter runs in a `pull_request_target` workflow. GitHub runs that event
"in the context of the default branch of the base repository": the workflow
file, its `branches:` filter and `GITHUB_SHA` all come from the **default
branch's tip**, whatever branch the PR targets. The trusted base is therefore
always the default branch's tip, and the gate is meaningful only for PRs into
the default branch. The PR head is fetched as git objects only and never
checked out, imported or executed. Decision memory is read from the trusted
base. A PR cannot set:

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
python -I scripts/ci/adr033_c4_gate.py evaluate --repo base --base-sha "$BASE_SHA" --head-sha "$HEAD_SHA" --mode strict --workspace "$RUNNER_TEMP/ws" --empty-dir "$RUNNER_TEMP/empty" --venv-python "$EVALUATOR_PYTHON" --evaluator-commit "$EVALUATOR_COMMIT" --evaluator-wheel-sha256 "$APPROVED_WHEEL_SHA256" --report "$RUNNER_TEMP/gate-out/gate-report.json" --summary "$GITHUB_STEP_SUMMARY"
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

Add `--trusted-surface <file-or-dir/>` (repeatable) to `evaluate` only if your
workflow reads other files from the trusted base; the reference workflow reads
none outside `.github/` and `.mneme/`, so it passes none.

Both steps belong to the one genuine required check. The adapter creates no
Checks API run and no second check identity.

Before running the adapter, the trusted workflow must fetch it from an exact,
reviewed Core commit and path (never from the PR or a mutable branch) and verify
its git blob id and content SHA-256. If that preflight fails, the check fails
under every posture.

## Installation procedure

These steps install the gate in a GitHub repository as Core runs it. They need
administrator rights on the repository. Do them in order: the check is made
required only after the workflow is on the default branch.

### 1. Prerequisites

- GitHub Actions enabled, with `actions/checkout` and `actions/upload-artifact`
  allowed at the SHA-pinned versions the workflow uses.
- The workflow can fetch the public `MnemeHQ/mneme` repository at the pinned
  commits (adapter and evaluator source).
- Runners `ubuntu-24.04` (the workflow uses `/usr/bin/python3.12`).

### 2. Decision memory

The default branch must contain `.mneme/project_memory.json`, the file
`mneme check` reads, with at least one decision carrying a literal-tier typed
rule (for example `FORBID_LITERAL`). The gate evaluates literal-tier rules only;
memory without typed rules gives nothing to block.

**Minimal example.** [`c4-gate/project_memory.example.json`](c4-gate/project_memory.example.json)
is a complete, valid memory with one synthetic decision, `ADR-901`: a
`FORBID_LITERAL` rule for the text `install legacy-client` in `docs/**`
(excluding `docs/history/**`), with its decision index (version
`dver-d3d431ff6d5edba8b555a040a7b85f9b`, rule
`ADR-901:FORBID_LITERAL:1eff1b82c5be57bd80379f967b799f7b`). It is the decision
used in the C4 Gate 3 live lab, reduced to that one decision. With the pinned
evaluator (`0b74d410`, invoked as the adapter does) a `docs/` file containing
the text returns `FAIL` (exit 2) and a neutral `docs/` file returns `PASS`
(exit 0), both with `evaluation_complete: true`.

Copy it unchanged to `.mneme/project_memory.json` to install and verify the
gate. Do not hand-edit its values: the decision index carries content digests
and rule identities derived from the decision. To protect your own decisions,
create the memory with the `mneme-hq` CLI (`mneme init`, then `mneme adr import`
for ADRs whose constraints declare typed rules), and confirm it with the
step 7 tests, which run the pinned evaluator.

### 3. Availability posture

Create the repository variable `MNEME_CI_AVAILABILITY` with the value `closed`
(an unavailable evaluation blocks). An unset or invalid value also means
`closed`, with a warning in each run.

```bash
gh api -X POST repos/OWNER/REPO/actions/variables -f name=MNEME_CI_AVAILABILITY -f value=closed
```

### 4. The workflow

Copy Core's [`.github/workflows/mneme-trusted-gate.yml`](../../.github/workflows/mneme-trusted-gate.yml)
**verbatim** from `main` (blob `3fb1e0ba17ed0849649130b75447a22af18ac8f4`, last
changed at `141a29e87bd0530269c194a40fad3ef043961272`). It is self-contained:

- adapter pins `ADAPTER_COMMIT` `c51729f78199203fe12fcbc5c678b89a2c4f7d3e`,
  `ADAPTER_PATH` `scripts/ci/adr033_c4_gate.py`, `ADAPTER_BLOB`
  `5feedf60ce1a67b2bb85673354c8b8b367a87d06`, `ADAPTER_SHA256`
  `afe1d69c1ce4170875989c5866bb2ec7b5089fc895efa699ced826317e3777f9`;
- evaluator pins `EVALUATOR_COMMIT` `0b74d410b45e7b3efcf08d00ce58e7bd7017b757`,
  `APPROVED_WHEEL_SHA256`
  `e3fcc769c440ed232ad05117f256739daf233e0c9f6d3d46586adc0de9b48c51`, with the
  hash-locked runtime requirements and the build-backend pin inlined;
- `VIOLATION_MODE: strict`, posture from `vars.MNEME_CI_AVAILABILITY`;
- trigger `pull_request_target` on `branches: [main]`. If your default branch
  has another name, change only that filter value.

Do not change pins or steps; a different evaluator or adapter needs its own
parity evidence. Merge the file with an ordinary PR. Because
`pull_request_target` runs the default branch's copy, that PR gets no gate run;
the first runs are on PRs opened or updated after it is merged. The job name,
`mneme trusted gate`, is the check context.

### 5. Rulesets (after the workflow is on the default branch)

Use two branch rulesets on the default branch, so that a bypass of the gate
never bypasses the other protections:

- **Gate ruleset (`mneme-ci-gate`):** one rule, `required_status_checks` with
  context `mneme trusted gate` from the GitHub Actions app (integration id
  `15368`) and strict up-to-date on. Bypass list: exactly one designated human
  (`User` actor) in `pull_request` mode, never `always`. That person is the
  route for changes the gate always refuses (`.mneme/`, `.github/`); with no
  bypass actor such changes can merge only by disabling the ruleset.
- **Protections ruleset (`main-pr-only`), no bypass actors:** pull request
  required (squash only, no required approvals), deletion and non-fast-forward
  rules. Add your other required checks to it as a `required_status_checks`
  rule if you have any.

These are the shapes Core runs (rulesets 26391853 and 22196895). Set the three
values at the top, then run the block: it looks up the bypass user's numeric
id, writes both files as valid JSON and creates the rulesets.

```bash
REPO=OWNER/REPO            # the repository to protect
DEFAULT_BRANCH=main        # its default branch
BYPASS_LOGIN=github-login  # the one designated human bypass authority

BYPASS_ID="$(gh api "users/$BYPASS_LOGIN" --jq .id)"
python3 - "$BYPASS_ID" "$DEFAULT_BRANCH" <<'PY'
import json, sys
bypass_id, branch = int(sys.argv[1]), sys.argv[2]
ref = {"ref_name": {"include": [f"refs/heads/{branch}"], "exclude": []}}
gate = {
    "name": "mneme-ci-gate", "target": "branch", "enforcement": "active",
    "conditions": ref,
    "bypass_actors": [{"actor_id": bypass_id, "actor_type": "User",
                       "bypass_mode": "pull_request"}],
    "rules": [{"type": "required_status_checks", "parameters": {
        "strict_required_status_checks_policy": True,
        "do_not_enforce_on_create": False,
        "required_status_checks": [{"context": "mneme trusted gate",
                                    "integration_id": 15368}]}}],
}
protections = {
    "name": "main-pr-only", "target": "branch", "enforcement": "active",
    "conditions": ref, "bypass_actors": [],
    "rules": [
        {"type": "pull_request", "parameters": {
            "allowed_merge_methods": ["squash"],
            "dismiss_stale_reviews_on_push": False,
            "require_code_owner_review": False,
            "require_last_push_approval": False,
            "required_approving_review_count": 0,
            "required_review_thread_resolution": False}},
        {"type": "deletion"},
        {"type": "non_fast_forward"},
    ],
}
for name, body in (("gate-ruleset.json", gate), ("protections-ruleset.json", protections)):
    with open(name, "w", encoding="utf-8") as f:
        json.dump(body, f, indent=2)
        f.write("\n")
PY
gh api -X POST "repos/$REPO/rulesets" --input protections-ruleset.json
gh api -X POST "repos/$REPO/rulesets" --input gate-ruleset.json
```

Create the protections ruleset first, as above, so the gate's bypass never
exists without the no-bypass protections. Read both back with
`gh api repos/$REPO/rulesets` and `gh api repos/$REPO/rules/branches/$DEFAULT_BRANCH`.

### 6. Actions policy

Where an organization or repository restricts `pull_request_target`, allow it
for this workflow. On Core after GitHub's 2026-11-02 change, runs for PRs from
branches of the same repository started with no approval step and no policy
change. PRs from forks and first-time contributors have not been observed.

### 7. Verify

Open three throwaway PRs into the default branch and keep them unmerged:

| PR | Expected check | Expected merge |
|---|---|---|
| A change containing a literal your memory forbids | failure (VIOLATION) | blocked |
| A neutral change | success (PASS) | allowed |
| A symlink (non-regular file) under `closed` | failure (UNEVALUATED) | blocked |

Each run's `gate-report.json` artifact must show the pins above and posture
`closed`.

### 8. Operating it

- **Protected changes** (`.mneme/`, `.github/`, `.gitattributes`,
  `.gitmodules`) are always REFUSED. Merge them only through the designated
  human's bypass, with a record in the PR of the approval, the protected paths,
  the reason and the gate check-run id. GitHub enforces who may bypass, not the
  record.
- **Evaluation unavailable** (runner or evaluator failure): set the posture to
  `open` and re-run. Only UNEVALUATED then passes, visibly labelled; VIOLATION
  and REFUSED still block. Set it back to `closed` and re-run afterwards.
- **Gate defect:** remove the required check from the gate ruleset (or disable
  it), and restore it through a reviewed change.

The lab workflow from C4 Gate 3,
[`bootstrap-ci1-trusted-gate.yml`](../validation/adr033-c4-gate3-live-2026-10-26/bootstrap-ci1-trusted-gate.yml),
is kept as historical evidence only. It reads lab files and is not the
installable reference.

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
- Administrative exposure (P7/P8) stays: anyone with administrator rights,
  including an agent holding such a token, can change the rulesets, the
  posture variable or the workflow, and the bypass actor can merge past the
  gate. On Core this is an accepted dogfooding residual (R0 ruling R6), not an
  administrator-resistance claim.
- Protected-path changes have a procedural route (the recorded human bypass),
  not a governed decision-update mechanism.
- Rule coverage is only as wide as the memory's literal-tier rules and include
  selectors; ADR-029 binding is partial; merge races are untested.
- `pull_request_target` after GitHub's 2026-11-02 change was observed only for
  same-repository PRs (Core, 2026-11-02/03); fork and first-time-contributor
  PRs are unobserved.
- The gate covers the CI merge boundary only. Agent-host hooks are a separate
  boundary and are not fail-closed when the host does not invoke them.

## Release implications

None. The adapter is a standalone, standard-library-only script outside the
`mneme-hq` wheel, so installing or upgrading `mneme-hq` does not install it, and
no `mneme-hq` release is needed for it. Mneme Core adopted it through R0
(#684-#743). Other repositories install it with the procedure above; Core's
Layer 1 freeze governs changes to Core only.
