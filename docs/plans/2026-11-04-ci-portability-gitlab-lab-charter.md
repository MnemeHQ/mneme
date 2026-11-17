# CI portability: GitLab Free lab charter

**Status: CHARTER PROPOSAL.** Documentation only. Merging this charter makes
it the reviewed protocol for the experiment. It authorizes no group, project,
account, runner, setting, variable, pipeline, merge request or merge attempt.
The experiment (§9, gate E) needs the owner's separate, explicit
authorization after this charter is reviewed and the preconditions in §8 are
met.
**Date:** 2026-11-04.
**Repository:** `MnemeHQ/mneme`; Core baseline `d0b6a922` (#746).
**Basis:** [CI portability Gate 0 assessment](2026-11-03-ci-portability-gate0-assessment.md)
§7 (#746).
**Governing decisions:** [ADR-033](../adr/ADR-033-opt-in-fail-closed-enforcement.md)
§§1-2, 5 and 7; ADR-017, ADR-020, ADR-022, ADR-029, ADR-034; Layer 1 freeze
(unchanged).
**Prior evidence:** ADR-033 C4 Gates 2-3 and closure (#680-#682); CI1
contract fixtures (CI1.2); CI1 gate-weakening threat model; R0 closure §5
(#742) and operating-status decision (#743).

**Authorization (owner, 2026-11-04, Mneme Core conversation, recorded on the
owner's behalf):** "Approve §7 of the merged Gate 0 assessment as the basis
for drafting the GitLab Free lab charter PR. This authorizes the charter PR
only, not lab creation, configuration or execution. Preserve the existing C4
adapter and evaluator pins, strict violation mode, closed availability
posture and literal-tier fixtures. Maintain separate verdicts for
same-repository and fork-based cases. V5 must remain independently reported,
with no fork-protection claim if unverified. The experiment requires separate
owner authorization after the charter PR is reviewed and the Developer-only
contributor account and GitLab access are established. Do not modify Mneme
Core enforcement, ADRs or existing CI configuration."

## 1. Question

Does the unmodified ADR-033 C4 adapter, run under `closed` posture from a
pipeline definition the change cannot edit, give the same accept/refuse
outcomes on GitLab.com Free as it gave on GitHub (C4 Gate 3), and does
GitLab itself refuse the merge when the gate fails?

Same-repository and fork-based changes are separate questions with separate
verdicts (§5).

## 2. Hypotheses

| ID | Hypothesis | Tested by |
|---|---|---|
| H1 | The adapter and evaluator pins run unmodified on a GitLab runner and reproduce the CI1 corpora | B5, V1-V3 |
| H2 | With the CI/CD configuration file set to a file in a separate project, an MR's own `.gitlab-ci.yml` never defines the gating pipeline | V4a |
| H3 | A Developer-only contributor cannot change the configuration source, merge checks, posture or pins | V4b-V4d |
| H4 | "Pipelines must succeed" makes GitLab refuse a merge whose gating pipeline failed, for a non-admin account | V6-S |
| H5 | A fork MR cannot satisfy the merge check with a pipeline the fork controls | V5, V6-F. **No prior expectation.** Gate 0 rated this the highest-risk unknown |

## 3. Fixed inputs (pins)

Any difference from this table stops the experiment (§7).

| Input | Value |
|---|---|
| Adapter | `MnemeHQ/mneme` commit `c51729f78199203fe12fcbc5c678b89a2c4f7d3e`, path `scripts/ci/adr033_c4_gate.py`, mode `100644`, blob `5feedf60ce1a67b2bb85673354c8b8b367a87d06`, SHA-256 `afe1d69c1ce4170875989c5866bb2ec7b5089fc895efa699ced826317e3777f9` |
| Evaluator | built from commit `0b74d410b45e7b3efcf08d00ce58e7bd7017b757` with `setuptools==84.0.0`, wheel SHA-256 `e3fcc769c440ed232ad05117f256739daf233e0c9f6d3d46586adc0de9b48c51` |
| Evaluator dependencies | `docs/validation/adr033-c4-gate2-offline-2026-10-26/inputs/evaluator-requirements.txt` at Core `d0b6a922`: blob `327fe8e61e6f854d88eb9332b3e67dc400bca33c`, SHA-256 `e4ef9d786fd2a49f0dc76a9d5304278f92f23d8257e2410f0305dca883ecca8b`; identical to the lock inlined in Core's `mneme-trusted-gate.yml` |
| Violation mode | `strict`, a constant of the trusted definition |
| Availability posture | `closed`, project CI/CD variable `MNEME_CI_AVAILABILITY` |
| Decision memory | `tests/fixtures/ci1_contract/path_scoped_forbid_literal/v1/project_memory.json` at Core `d0b6a922`, committed unchanged as the lab's `.mneme/project_memory.json` (ADR-901: `FORBID_LITERAL` `install legacy-client`, include `docs/**`, exclude `docs/history/**`) |
| Extra trusted surface | `--trusted-surface .gitlab-ci.yml --trusted-surface .gitlab/` (the adapter always adds `.github/`, `.gitattributes`, `.gitmodules`; `.mneme/` is refused as policy) |
| Runner image | `ubuntu@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac` (`ubuntu:24.04`, the C4 Gate 2 container image); packages `git`, `python3.12`, `python3.12-venv`, `ca-certificates` from the Ubuntu archive at run time (not hash-pinned; the wheel and adapter hashes fail closed if anything differs) |
| Trusted definition | Appendix A, committed to `gate-config` branch `gate-v1` (protected), its commit recorded at B1 |

No adapter code, evaluator, rule type, fixture or posture change is allowed.
`open` is out of scope (Gate 0 G-2).

**Known risk: wheel reproducibility.** The approved wheel has been rebuilt
only on GitHub-hosted `ubuntu-24.04` runners (CI1 P2, R0, #745); C4 Gate 2
reused a preserved copy instead of rebuilding. A rebuild inside this
container image, as root, is unproven. B5 is its first evidence. A different
hash is a stop (§7), not a reason to accept another wheel; a fix (for
example a verified preserved copy of the approved wheel) needs a reviewed
amendment.

## 4. Lab design

### 4.1 Topology

- One new **public** GitLab.com group, used for nothing else. The owner is
  its only member. It is public because a GitLab project cannot be more
  visible than its group: a private group holds only private projects, so
  a public `gate-config` needs a public group.
- Project **`gate-config`**, **public**: holds only `gate.yml` (Appendix A)
  on branch `gate-v1`, protected with push and merge "No one" after the
  commit. No project members beyond the owner's inherited group role. It is
  public because GitLab documents that a user needs read access to another
  project's CI file in the `include:project` case, and its own docs suggest
  a public project for an external CI file. Readers can see the definition,
  which is already public in Core's workflow; only the owner can change it.
- Project **`lab`**, **private**: the target repository. Seed commit on
  `main`: `.mneme/project_memory.json` (§3) and `docs/README.md` (compliant
  text). Members: the owner (inherited group Owner) and the contributor
  (direct project member, Developer).

The contributor is **never** a member of the group or of `gate-config`, so
no group role is inherited by any project. Group membership is the only
inheritance path, and B3 checks it is unused for the contributor. The
contributor is never given write access to `gate-config` to make anything
work; if the design cannot run without it, that is a stop (§7).
- The contributor's personal namespace, used only for the V5 fork.

### 4.2 Accounts and identities

- **Owner**: existing GitLab account, group Owner. Performs every
  administrative step (§6) and nothing in a case's contributor path.
- **Contributor**: a separate account created by the owner, direct
  Developer member of `lab` only; no role on `gate-config` or the group. Every case MR and
  merge attempt is made as the contributor.
- The agent never handles either account's password or token. Commands run
  under a session the owner authenticated (GitLab MCP, `glab` or a separate
  CLI profile per identity), and every evidence file names the identity used.

### 4.3 `lab` settings (to be applied at gate E, snapshotted before and after)

| Setting | Value | Projects API attribute |
|---|---|---|
| CI/CD configuration file | `gate.yml@<group>/gate-config:gate-v1` (GitLab documents a branch as the ref; B1 records the branch's commit) | `ci_config_path` |
| Pipelines must succeed | on | `only_allow_merge_if_pipeline_succeeds` |
| Skipped pipelines are considered successful | off | `allow_merge_on_skipped_pipeline` |
| Merged results pipelines, merge trains | off | n/a on Free |
| Minimum role to use pipeline variables | `no_one_allowed` | `ci_pipeline_variables_minimum_override_role` |
| Project CI/CD variables | exactly one: `MNEME_CI_AVAILABILITY=closed`, not protected, not masked | variables API |
| Protected branch `main` | push: No one; merge: Developers + Maintainers; force push off | protected branches API |
| Forking | enabled (needed for V5) | project features |
| Fork pipelines in parent project | default, recorded | `ci_allow_fork_pipelines_to_run_in_parent_project` (API only; recorded, not changed) |

Project CI/CD variables override YAML variables in GitLab. B4 therefore
checks that no project or group variable shadows a pin in Appendix A.

### 4.4 Trusted pipeline behavior

Appendix A is the exact proposed definition. In order:

1. Runs only for `merge_request_event` pipelines; the runner does no git
   operation and starts from an empty build directory
   (`GIT_STRATEGY: empty`; `none` may leave a stale working copy).
2. Clones the target project (`CI_MERGE_REQUEST_PROJECT_PATH`) with the job
   token, detaches at the target branch tip and records it as `BASE_SHA`.
3. Fetches `refs/merge-requests/<iid>/head` as objects only and requires it
   to equal `CI_COMMIT_SHA`; a mismatch fails the job (a newer push runs its
   own pipeline).
4. Clones Core from GitHub, rebuilds the evaluator at `0b74d410` and requires
   the approved wheel SHA-256; installs it with the hash-locked dependencies
   read from Core `d0b6a922` after checking their SHA-256.
5. Extracts the adapter from `c51729f7` and checks mode, blob and SHA-256.
6. Runs `evaluate` and then `verify-report` exactly as Core's workflow does,
   with the §3 trusted surface. Only `verify-report`'s exit decides the job.
7. Keeps `gate-report.json`, `summary.md` and the step outputs as job
   artifacts (`when: always`).

### 4.5 Undocumented behavior the lab must establish

The official documentation (checked 2026-11-04) does not state the
following. Each is an assumption of this design, tested before or by the
cases; none is treated as known.

| ID | Assumption | Established by | If false |
|---|---|---|---|
| U1 | with an external CI file, MR pipelines are still created from its `workflow:rules` | B5 | stop |
| U2 | `lab`'s own `.gitlab-ci.yml` is ignored when the external file is set | V4a | V4a FAIL |
| U3 | the job token can clone `lab` and fetch `refs/merge-requests/<iid>/head` | B5 | stop |
| U4 | in a detached MR pipeline `CI_COMMIT_SHA` equals the MR head ref | B5 (the job fails closed if not) | stop |
| U5 | a branch ref in `ci_config_path` is honored, and the pipeline reads the file at that branch | B1, B5 | stop |
| U6 | how a fork pipeline relates to `lab`'s "Pipelines must succeed" | V5a, V6-F | reported as found |
| U7 | the evaluator wheel rebuilds to the approved hash in this image (§3) | B5 | stop |

The adapter's `::error`/`::warning` lines appear as plain log text; under
`closed` nothing depends on them (Gate 0 G-2). The report's `posture.source`
reads `vars.MNEME_CI_AVAILABILITY`; the evidence records the real source, a
GitLab project variable (Gate 0 G-4).

## 5. Validation cases

Each case is judged on its own and gets one verdict: **PASS**, **FAIL** or
**UNVERIFIED**. A case that is not run, or whose result cannot be attributed,
is UNVERIFIED. No verdict is inferred from another case. Same-repository
cases (V1-V4, V6-S) and fork cases (V5, V6-F) are reported in separate
tables, and the fork verdicts never enter the same-repository result.

### 5.1 Same-repository cases

| ID | Contributor change (MR from a `lab` branch) | Expected gate | Expected host | PASS when |
|---|---|---|---|---|
| V1 | add `docs/v1-compliant.md` without the literal | PASS → job success | merge accepted | pipeline from `gate-config` at the pinned SHA; report aggregate PASS; head-pinned merge by the contributor accepted |
| V2 | add `docs/v2-violation.md` containing `install legacy-client` | VIOLATION → job failure | merge refused | report shows ADR-901 rule APPLIED and FAIL; merge refused |
| V3 | add a symlink `docs/v3-link.md` (as C4 L2) | UNEVALUATED → job failure under `closed` | merge refused | report states UNEVALUATED and its reason, never PASS; merge refused |
| V4a | add `.gitlab-ci.yml` defining one always-passing job, plus a violating `docs/v4a.md` | REFUSED → job failure | merge refused | the MR's file defines no job that ran; the gating pipeline came from `gate-config`; report REFUSED on `.gitlab-ci.yml`; merge refused |
| V4b | contributor attempts to change `ci_config_path`, merge checks or the posture variable via the API | n/a | n/a | every attempt refused by role; settings unchanged per snapshot |
| V4c | contributor triggers a pipeline for the V2 MR with `MNEME_CI_AVAILABILITY=open` as a pipeline variable | n/a | merge still refused | pipeline creation refused, or the run still reports `closed`; V2 merge stays refused |
| V4d | contributor attempts to push to `gate-config` or change its `gate-v1` branch | n/a | n/a | refused (public read, no write) |
| V6-S | head-pinned merge attempts (`PUT …/merge` with `sha`) for V1-V4a, plus one retry of V2 after its pipeline finishes | n/a | V1 accepted; V2, V3, V4a refused | each refusal is a host response to the contributor's own attempt; no refusal depends on a setting the contributor can change |

**Accepted and refused, defined by state.** Accepted: the merge call
returns success, the MR is `merged`, and `main` moves to the merge commit.
Refused: the call does not succeed (GitLab documents 405 for an MR that
cannot merge, 401 for a user who cannot accept it, 409 for a SHA mismatch),
the MR stays `opened`, and `main` is unchanged. The raw status, body,
`detailed_merge_status` (for example `ci_must_pass`) and `main` before and
after are recorded. A 409, 401 or 422 is a protocol fault for that attempt,
not evidence of gate enforcement, and is retried once with corrected inputs
before the case is judged.

### 5.2 Fork cases

| ID | Contributor change | Observe | PASS when |
|---|---|---|---|
| V5a | fork `lab` into the contributor namespace; in the fork add `.gitlab-ci.yml` with one always-passing job and a violating `docs/v5.md`; open an MR to `lab` | which project ran which pipeline, from which configuration, and which pipeline the MR's merge check uses | no pipeline defined by the fork satisfies `lab`'s merge check |
| V5b | **excluded from gate E.** The owner running the V5a MR's pipeline in the parent project | which configuration the parent-run pipeline uses | not run under this charter (see below) |
| V6-F | head-pinned merge attempt on the V5a MR by the contributor | host response | merge refused |

**Fork warning.** GitLab documents that a fork MR pipeline normally runs in
the fork with the fork's own configuration, and that even when a
parent-project member runs it in the parent project, the configuration
comes from the fork's branch, with the parent's variables and resources
and the triggering member's permissions. A parent run would therefore
execute untrusted configuration with `lab`'s resources. V5b is excluded
from gate E for that reason; running it needs its own authorization after
the V5a result, with its own risk assessment.

If V5a or V6-F is FAIL or UNVERIFIED, the results record states that fork
protection is **not shown** and makes no fork-protection claim. Nothing in
V5 changes the same-repository verdicts.

### 5.3 Not tested

Posture `open`; V5b (parent-project run of a fork pipeline); merge races;
the documented older-successful-pipeline caveat (GitLab notes that an
older successful MR pipeline can allow a merge after a newer pipeline
fails), which no case exercises and which stays an explicit limitation of
any result; runner outage or timeout; first-time-contributor approval (no GitLab
equivalent documented); administrator resistance (R6); paid-tier controls
(pipeline execution policies, external status checks, approval-policy
bypass). Each stays a recorded limitation.

## 6. Procedure (at gate E only)

1. **Build.** Create the public group, the public `gate-config` and the
   private `lab`, commit the seed and Appendix A, apply §4.3, add the
   contributor as a direct Developer member of `lab` only. Snapshot every setting (API GET) before
   and after.
2. **Build checks (all must pass before any case):**
   - **B1** `ci_config_path` is `gate.yml@<group>/gate-config:gate-v1`;
     the `gate-v1` head commit is recorded and its `gate.yml` is
     byte-identical to Appendix A; `gate-v1` is protected.
   - **B2** the job log shows the §3 image digest; instance runners are
     available to the group.
   - **B3** visibility and membership: group public, `gate-config` public,
     `lab` private; the group's only member is the owner; the contributor is
     a direct Developer member of `lab` and a member of nothing else (group
     and `gate-config` member lists, including inherited members, recorded).
   - **B4** only `MNEME_CI_AVAILABILITY` is defined as a project or group
     variable; no variable shadows an Appendix A pin.
   - **B5** a throwaway owner MR touching only `docs/` runs the gate end to
     end: wheel and adapter pins verified, report PASS. Then, on the same
     runner image, the CI1 contract corpora replay offline (the Gate 2
     replay commands) with the Gate 2 counts. The B5 MR is closed unmerged.
3. **Cases** in the order V1, V2, V3, V4a-d, V6-S, V5a, V6-F. For each:
   open the MR as the contributor, wait for the pipeline, fetch evidence,
   attempt the head-pinned merge, record.
4. **Restore and archive.** Close open MRs, delete the fork, export the
   evidence, archive the group (or delete it, if the owner prefers),
   snapshot the final state.

## 7. Stop rules

Stop at once, record the state, and report:

- any pin in §3 differs, or a case would need an adapter, evaluator, rule,
  fixture or posture change;
- a build check fails;
- a case needs an owner or admin action;
- GitLab behaves in a way this charter did not anticipate and the next step
  is not covered here;
- a paid tier would be needed.

A stop is a result. The protocol is not changed mid-run; a rerun needs a
reviewed amendment.

## 8. Preconditions for gate E

The owner establishes, outside this charter:

- a GitLab.com account able to create the public group, and any identity verification GitLab requires for
  Free users to run jobs on GitLab-hosted runners (email, phone or payment
  method, by risk score). Free namespaces get 400 compute minutes a month;
  this charter needs about 15 pipeline runs;
- the contributor account with Developer-only access;
- authenticated access for the agent (GitLab MCP via `/mcp`, or a CLI
  session per identity), without the agent handling secrets.

## 9. Gates

| Gate | Content | Authorizes |
|---|---|---|
| C0 | this charter, reviewed and merged | nothing beyond the protocol |
| E | owner authorization, after §8 | build, build checks, cases V1-V4, V6-S, V5a, V6-F and restore, exactly as §§4-7. Not V5b |
| R | results record PR with an independent read-only audit (as C4 Gate 4) | closure of this experiment; no support claim |

## 10. Evidence

Committed under `docs/validation/ci-portability-gitlab-lab-<date>/` with an
`EVIDENCE-SHA256SUMS` manifest:

- pins as observed in each job log (adapter blob and SHA-256, wheel SHA-256,
  lock SHA-256, image digest, `gate-config` commit);
- settings snapshots (before build, after build, after restore), the
  group's and both projects' visibility, and member lists with roles,
  direct and inherited;
- per case: identity used, MR IID and URLs, source project, pipeline ID,
  project the pipeline ran in and its configuration source, job ID, full
  job log, `gate-report.json`, `summary.md`, `verify-report` output,
  `BASE_SHA`, `HEAD_SHA`, `CI_COMMIT_SHA`, `CI_MERGE_REQUEST_DIFF_BASE_SHA`,
  the MR's `detailed_merge_status`, and the raw merge request and response;
- V4b-V4d raw API requests and responses;
- the B5 offline replay output.

No tokens, passwords or personal data in any committed file.

## 11. Claims

- **A full PASS of §5.1** supports only: in one GitLab.com Free lab, under
  `closed` and the §3 pins, the unmodified C4 adapter enforced V1-V4 and
  GitLab refused the failing same-repository merges for a Developer-only
  contributor.
- **§5.2** is reported on its own. Without a V5a and V6-F PASS there is no
  fork-protection claim.
- Never claimed: GitLab support, production readiness, administrator
  resistance (R6), ADR-029 relevant enforcement observed, equivalence for
  paid tiers or Self-Managed.

## 12. Not authorized

Lab creation, configuration or execution before gate E; any change to Core
enforcement, the adapter, the evaluator, ADRs, the Layer 1 freeze, `.mneme/`
or Core's CI configuration; posture `open`; V5b; granting the contributor
any access to `gate-config` or the group; any additional platform.

## Appendix A. Proposed trusted definition (`gate-config/gate.yml`)

Not applied. The committed file at gate E must be byte-identical to this
text (B1).

```yaml
# Mneme CI portability lab: trusted gate definition (charter 2026-11-04,
# Appendix A). Held in gate-config; lab's ci_config_path points here, so an
# MR in lab cannot edit it. Mirrors Core's mneme-trusted-gate.yml.
workflow:
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - when: never

variables:
  GIT_STRATEGY: empty
  CORE_URL: https://github.com/MnemeHQ/mneme.git
  CORE_COMMIT: d0b6a922585c54a1f8a49e730280319ce20c3fd8
  EVALUATOR_COMMIT: 0b74d410b45e7b3efcf08d00ce58e7bd7017b757
  APPROVED_WHEEL_SHA256: e3fcc769c440ed232ad05117f256739daf233e0c9f6d3d46586adc0de9b48c51
  LOCK_PATH: docs/validation/adr033-c4-gate2-offline-2026-10-26/inputs/evaluator-requirements.txt
  LOCK_SHA256: e4ef9d786fd2a49f0dc76a9d5304278f92f23d8257e2410f0305dca883ecca8b
  ADAPTER_COMMIT: c51729f78199203fe12fcbc5c678b89a2c4f7d3e
  ADAPTER_PATH: scripts/ci/adr033_c4_gate.py
  ADAPTER_BLOB: 5feedf60ce1a67b2bb85673354c8b8b367a87d06
  ADAPTER_SHA256: afe1d69c1ce4170875989c5866bb2ec7b5089fc895efa699ced826317e3777f9
  VIOLATION_MODE: strict
  # MNEME_CI_AVAILABILITY comes only from the lab project variable.

mneme-trusted-gate:
  image: ubuntu@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac
  timeout: 20m
  artifacts:
    when: always
    expire_in: 90 days
    paths:
      - gate-out/
  script:
    - |
      set -euo pipefail
      unset PYTHONPATH
      out="$CI_PROJECT_DIR/gate-out"; t=/tmp/mneme-gate
      mkdir -p "$out" "$t"
      export DEBIAN_FRONTEND=noninteractive
      apt-get update -q >/dev/null
      apt-get install -y -q --no-install-recommends git python3.12 python3.12-venv ca-certificates >/dev/null
      py=/usr/bin/python3.12

      # Trusted base: the target branch tip of the target project.
      git clone -q --no-tags "https://gitlab-ci-token:${CI_JOB_TOKEN}@${CI_SERVER_HOST}/${CI_MERGE_REQUEST_PROJECT_PATH}.git" "$t/base"
      git -C "$t/base" checkout -q --detach "origin/${CI_MERGE_REQUEST_TARGET_BRANCH_NAME}"
      BASE_SHA="$(git -C "$t/base" rev-parse HEAD)"
      # MR head as objects only; never checked out.
      git -C "$t/base" fetch -q --no-tags origin "+refs/merge-requests/${CI_MERGE_REQUEST_IID}/head:refs/gate/mr-head"
      HEAD_SHA="$(git -C "$t/base" rev-parse refs/gate/mr-head)"
      git -C "$t/base" remote remove origin
      [ "$HEAD_SHA" = "$CI_COMMIT_SHA" ] || { echo "MR head moved ($HEAD_SHA != $CI_COMMIT_SHA); not evaluated"; exit 1; }
      printf 'base %s\nhead %s\ncommit %s\ndiff_base %s\nproject %s\nmr_project %s\nsource_project %s\n' \
        "$BASE_SHA" "$HEAD_SHA" "$CI_COMMIT_SHA" "${CI_MERGE_REQUEST_DIFF_BASE_SHA:-}" \
        "$CI_PROJECT_PATH" "$CI_MERGE_REQUEST_PROJECT_PATH" "${CI_MERGE_REQUEST_SOURCE_PROJECT_PATH:-}" | tee "$out/revisions.txt"

      # Core: evaluator source, adapter and dependency lock at pinned commits.
      git clone -q --no-tags "$CORE_URL" "$t/core"
      [ "$(git -C "$t/core" rev-parse "${CORE_COMMIT}^{commit}")" = "$CORE_COMMIT" ]
      git -C "$t/core" cat-file blob "${CORE_COMMIT}:${LOCK_PATH}" > "$t/lock.txt"
      [ "$(sha256sum "$t/lock.txt" | cut -d' ' -f1)" = "$LOCK_SHA256" ] || { echo "dependency lock sha256 mismatch"; exit 1; }

      # Rebuild the evaluator wheel and require the approved sha256
      # (same umask, archive, epoch and backend pin as Core's workflow).
      umask 0002
      mkdir -p "$t/build"
      git -C "$t/core" archive --format=tar "$EVALUATOR_COMMIT" > "$t/build/src.tar"
      "$py" -I -c "import sys, tarfile; tarfile.open(sys.argv[1]).extractall(sys.argv[2], filter='data')" "$t/build/src.tar" "$t/build/src"
      "$py" -I -m venv "$t/build/venv"
      export SOURCE_DATE_EPOCH="$(git -C "$t/core" log -1 --format=%ct "$EVALUATOR_COMMIT")"
      echo 'setuptools==84.0.0' > "$t/build/build-constraints.txt"
      PIP_CONSTRAINT="$t/build/build-constraints.txt" \
        "$t/build/venv/bin/python" -I -m pip wheel -q --no-deps --disable-pip-version-check \
        --wheel-dir "$t/build/built" "$t/build/src"
      wheels=("$t"/build/built/*.whl)
      [ "${#wheels[@]}" -eq 1 ] || { echo "expected exactly one built wheel"; exit 1; }
      sha="$(sha256sum "${wheels[0]}" | cut -d' ' -f1)"
      [ "$sha" = "$APPROVED_WHEEL_SHA256" ] || { echo "evaluator wheel $sha != approved"; exit 1; }
      "$py" -I -m venv "$t/evaluator"
      { grep -vE '^[[:space:]]*(#|$)' "$t/lock.txt"; echo "${wheels[0]} --hash=sha256:$APPROVED_WHEEL_SHA256"; } > "$t/req.txt"
      "$t/evaluator/bin/python" -I -m pip install -q --disable-pip-version-check \
        --require-hashes --only-binary=:all: --no-deps -r "$t/req.txt"
      "$t/evaluator/bin/python" -I -c "import importlib.metadata as m, mneme, sys; p = mneme.__file__; assert p.startswith(sys.prefix), p; print(m.version('mneme-hq'), p)"

      # Adapter at the reviewed commit, checked before it runs.
      entry="$(git -C "$t/core" ls-tree "$ADAPTER_COMMIT" -- "$ADAPTER_PATH")"
      [ "${entry%% *}" = "100644" ] || { echo "adapter is not a regular file"; exit 1; }
      [ "$(echo "$entry" | cut -d' ' -f3 | cut -f1)" = "$ADAPTER_BLOB" ] || { echo "adapter blob mismatch"; exit 1; }
      git -C "$t/core" cat-file blob "$ADAPTER_BLOB" > "$t/adr033_c4_gate.py"
      [ "$(sha256sum "$t/adr033_c4_gate.py" | cut -d' ' -f1)" = "$ADAPTER_SHA256" ] || { echo "adapter sha256 mismatch"; exit 1; }

      # Evaluate (records only), then the trusted decision step decides.
      set +e
      "$py" -I "$t/adr033_c4_gate.py" evaluate \
        --repo "$t/base" --base-sha "$BASE_SHA" --head-sha "$HEAD_SHA" --mode "$VIOLATION_MODE" \
        --workspace "$t/ws" --empty-dir "$t/empty" \
        --venv-python "$t/evaluator/bin/python" --evaluator-commit "$EVALUATOR_COMMIT" \
        --evaluator-wheel-sha256 "$APPROVED_WHEEL_SHA256" \
        --trusted-surface .gitlab-ci.yml --trusted-surface .gitlab/ \
        --report "$out/gate-report.json" --summary "$out/summary.md"
      code=$?
      set -e
      echo "adapter exit code: $code" | tee "$out/evaluate-exit.txt"
      "$py" -I "$t/adr033_c4_gate.py" verify-report \
        --report "$out/gate-report.json" --adapter-exit "$code" \
        --base-sha "$BASE_SHA" --head-sha "$HEAD_SHA" --mode "$VIOLATION_MODE" \
        --adapter-sha256 "$ADAPTER_SHA256" --evaluator-commit "$EVALUATOR_COMMIT" \
        --evaluator-wheel-sha256 "$APPROVED_WHEEL_SHA256" --summary "$out/summary.md"
```
