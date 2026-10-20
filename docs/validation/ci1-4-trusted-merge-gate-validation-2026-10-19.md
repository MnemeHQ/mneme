# CI1.4: Trusted merge-gate validation (evidence consolidation)

**Status:** validation record, **draft for independent review**. It
consolidates the CI1.3 lab evidence and gives a recommendation. It does not
change runtime, tests, fixtures, schemas, workflows, rulesets, Actions
policies or `.mneme/`, in this repository or in the lab. It does not decide
ADR-033 availability policy and does not authorize adoption.
**Contract:** [CI1.3 charter](../plans/2026-10-17-ci1-3-isolated-merge-blocking-experiment-charter.md)
§1 (the proof), §6 (matrix), §7 (evidence per row), §8 (outcomes).
**Tracker:** #540. Every row below links its evidence comment there.
**Builds on:** [CI1.1 record](ci1-1-enforcement-assurance-contract-validation-2026-10-16.md),
[CI1.2 fixtures](../../tests/fixtures/ci1_contract/README.md) (#536, #539),
[P2 record](ci1-3-p2-pinned-evaluator-preflight-2026-10-17.md),
[ADR-029](../adr/ADR-029-enforcement-evidence-binding-semantics.md),
[ADR-030](../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md),
[ADR-031](../adr/ADR-031-decision-governance-semantics.md).
**Core anchor:** `main` @ `1d9148f4` when this record was prepared.

## 0. Summary

- **Outcome under charter §8: Proven (T1), head-revision only.** V0 merged.
  V1 to V7 (with V3a and V7b), V10 and V13 (A and B) were refused by GitHub
  with HTTP 405 on the failing required check `CI1 trusted gate`, on the exact
  PR head. Section 2 lists the evidence caveats.
- **What that means.** In one isolated, public lab repository, with one
  literal-tier rule, a PR that violates the trusted rule could not be merged,
  even when the same PR also edited, deleted or symlinked the decision
  memory, substituted the evaluator or gate, or added a look-alike check. A
  green result on an earlier head did not authorize a later head.
- **What it does not mean.** The gate judges the PR diff, not the merge
  result (V11). A separate, compliant PR that weakens the gate first is a
  structurally identified, untested vulnerability. Protection stops at each rule's path
  selectors (V8). Decision-version freshness is not proven. Behavior after
  GitHub enforces its default `pull_request_target` policy (2026-11-02) is
  unknown.
- **Recommendation: DEFER production merge blocking** (section 7). Section 7
  also lists the conditions a later promotion needs.

## 1. Setup under test

| Item | Value |
|---|---|
| Lab repository | [`MnemeHQ/mneme-ci1-lab`](https://github.com/MnemeHQ/mneme-ci1-lab), public, GitHub Free plan, temporary (archive after CI1.4) |
| Trusted gate | `.github/workflows/ci1-trusted-gate.yml` + `gate/ci1_gate.py`, T1 design (charter §3). Event `pull_request_target`. Base checkout only. The PR head is fetched as objects, never checked out. Files are materialized from git blobs into a fresh workspace and never executed |
| Gate refusals | `.mneme/` add, edit or delete; non-regular modes (`120000`, `160000`); absolute, `..`, backslash or empty path parts; collisions |
| Trusted decision memory | blob `dd760bf0969aa9009c63d2496050b910e87191f1` (CI1.2.1 path-scoped corpus): ADR-901 `FORBID_LITERAL` `install legacy-client`, `include_paths: [docs/**]`, `exclude_paths: [docs/history/**]`, `rule_id` `ADR-901:FORBID_LITERAL:1eff1b82c5be57bd80379f967b799f7b`, `decision_version_id` `dver-d3d431ff6d5edba8b555a040a7b85f9b` |
| Evaluator | commit build of `MnemeHQ/mneme` `0b74d410`, reports version `0.10.0`, wheel sha256 `e3fcc769c440ed232ad05117f256739daf233e0c9f6d3d46586adc0de9b48c51` (P2, [lab run 39055862171](https://github.com/MnemeHQ/mneme-ci1-lab/actions/runs/39055862171)). The gate rebuilds it and requires that hash on every run. PyPI `mneme-hq==0.10.0` fails parity and is not used |
| Invocation | `python -I -m mneme.cli check --mode strict --json`, fixed query, empty cwd and ADR dir. Classification is payload-first: schema, requested-mode equality, `evaluation_complete`, verdict/violation coherence and the strict exit code must all agree, otherwise UNEVALUATED |
| Verdict rule (lab policy, not product policy) | the check succeeds only when every materialized file is VERIFIED_PASS and nothing was refused. UNEVALUATED and refusals block. This does not settle ADR-033 |
| Ruleset | `ci1-lab-main`, id `25313704`, active on the default branch: required check `CI1 trusted gate` from integration 15368 (GitHub Actions), strict status policy **off**, PR required with **0** approvals, squash only, `bypass_actors: []` |
| Actions policy | repo policy `7806`: allows `pull_request_target` only for the gate workflow, applied ahead of GitHub's default restriction |
| Merge attempts | one per test, `PUT /repos/MnemeHQ/mneme-ci1-lab/pulls/{n}/merge` with `sha=<head>` and `merge_method=squash`. The status line, request id and body are recorded |
| Baselines | `a0eaff92` (V0) → `dbe5a281` (V1) → `8755bf07` (V1 recheck to V10) → `1bb964dc` (V11, V13) → `3a87809c` (after V8, current) |

Ruleset `25313704` and policy `7806` kept their creation-time `updated_at`
through the whole matrix (last read after V8 on 2026-10-19).

## 2. Test matrix and outcomes

Host outcome means GitHub's response to the pinned merge attempt.

| Row | Scenario | Lab PR / head | Gate result | Host outcome | Evidence |
|---|---|---|---|---|---|
| V0 | Compliant `docs/` change | [#3](https://github.com/MnemeHQ/mneme-ci1-lab/pull/3) / `61fbeb8d` | VERIFIED_PASS, ADR-901 APPLIED | **HTTP 200**, merged `dbe5a281` | [comment](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6238967251) |
| V1 | Plain violation | [#4](https://github.com/MnemeHQ/mneme-ci1-lab/pull/4) / `d3818ade` | VIOLATION, BLOCK | **HTTP 405** | [comment](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6239056639) |
| (gate fix) | Reporting regression after lab PR #5 | [#6](https://github.com/MnemeHQ/mneme-ci1-lab/pull/6) / `d912dc1a` | VIOLATION, BLOCK; decision step ran and failed | no merge attempted | [comment](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6239343467) |
| V1 recheck | V1 with policy `7806` applied | [#9](https://github.com/MnemeHQ/mneme-ci1-lab/pull/9) / `6efce0bf` | VIOLATION, BLOCK | **HTTP 405** | [comment](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6239940604) |
| V2 | Violation + rule removed from PR memory | [#10](https://github.com/MnemeHQ/mneme-ci1-lab/pull/10) / `995fda47` | memory edit REFUSED; base memory `dd760bf0` used; VIOLATION; BLOCK | **HTTP 405** | [comment](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6239992746) |
| V3 | Violation + memory deleted | [#11](https://github.com/MnemeHQ/mneme-ci1-lab/pull/11) / `9ed62818` | deletion REFUSED; VIOLATION; BLOCK | **HTTP 405** | [comment](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6240285482) |
| V3a | Memory deletion only | [#12](https://github.com/MnemeHQ/mneme-ci1-lab/pull/12) / `158ca1a2` | deletion REFUSED; zero files evaluated; BLOCK | **HTTP 405** | [comment](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6240391117) |
| V4 | Violation + fake evaluator package | [#13](https://github.com/MnemeHQ/mneme-ci1-lab/pull/13) / `5364c507` | pinned venv used, PR code read as data; VIOLATION; BLOCK | **HTTP 405** | [comment](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6240521788) |
| V5 | Violation + gate and workflow edited to exit 0 | [#14](https://github.com/MnemeHQ/mneme-ci1-lab/pull/14) / `1221fa9f` | base gate ran in full; VIOLATION; BLOCK | **HTTP 405** | same comment |
| V6 | Violation + extra permissive workflow | [#15](https://github.com/MnemeHQ/mneme-ci1-lab/pull/15) / `6f77f1fa` | VIOLATION; BLOCK; PR's own check green but not required | **HTTP 405** | same comment |
| V7 | Violation + same-name look-alike finishing first | [#16](https://github.com/MnemeHQ/mneme-ci1-lab/pull/16) / `c6b2c2c1` | genuine gate VIOLATION; look-alike green, same app 15368 | **HTTP 405** | [comment](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6240653935) |
| V7b | Same, look-alike finishing last | [#17](https://github.com/MnemeHQ/mneme-ci1-lab/pull/17) / `86fee272` | genuine gate VIOLATION; look-alike green 100 s later | **HTTP 405** | [comment](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6240949749) |
| V8 | Literal in out-of-scope `src/notes.md` | [#24](https://github.com/MnemeHQ/mneme-ci1-lab/pull/24) / `1e5ab36b` | VERIFIED_PASS, ADR-901 **EXCLUDED** ("no include selector matched") | **HTTP 200**, merged `3a87809c` (expected: coverage limit) | [comment](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6264253243) |
| V9-A | Malformed trusted memory (offline) | local base `2efe4682`, head `f402a943` | file UNEVALUATED (evaluator traceback, exit 1, empty stdout); aggregate BLOCK, exit 1; valid-memory control VERIFIED_PASS | not applicable (offline) | [comment](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6264479327) |
| V10 | Green head, then violating push | [#18](https://github.com/MnemeHQ/mneme-ci1-lab/pull/18) / `51d697d7` → `fb65a49f` | new head VIOLATION; PR BLOCKED from the moment the new head registered | **HTTP 405** on the new head | [comment](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6263117383) |
| V11 | Base advanced into scope | seed [#19](https://github.com/MnemeHQ/mneme-ci1-lab/pull/19), PR [#20](https://github.com/MnemeHQ/mneme-ci1-lab/pull/20) / `e4d45bb8`, rename [#21](https://github.com/MnemeHQ/mneme-ci1-lab/pull/21) | PASS before **and after** the base moved (merge-base unchanged) | not merged: GitHub marked #20 **DIRTY** (merge conflict) | [live](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6263454460), [offline follow-up](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6263559908) |
| V12 | Evaluator reports `warn` for a `strict` request (offline) | local head `6680f5ed` | file UNEVALUATED "reported mode 'warn' != requested 'strict'"; aggregate BLOCK, exit 1; approved-evaluator control VERIFIED_PASS | not applicable (offline) | [comment](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6264718331) |
| V13-A | Violation + `docs/` symlink to `../../outside` | [#22](https://github.com/MnemeHQ/mneme-ci1-lab/pull/22) / `b22360de` | symlink REFUSED (mode `120000`); VIOLATION; BLOCK | **HTTP 405** | [comment](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6263977550) |
| V13-B | Violation + memory replaced by a symlink | [#23](https://github.com/MnemeHQ/mneme-ci1-lab/pull/23) / `d60bfe1a` | symlink REFUSED (`100644` → `120000`); base memory used; VIOLATION; BLOCK | **HTTP 405** | [comment](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6264140950) |
| V13-C | Directory-level symlink (`.mneme` itself) | not run | covered offline by the lab's `tests/test_ci1_gate.py::test_non_regular_entries_are_refused_not_followed` (`.mneme`, mode `120000`) | skipped by reviewer decision, optional coverage | this record |

Every 405 body read `Repository rule violations found` / `Required status
check "CI1 trusted gate" is failing.` In every live row the `CI1 trusted gate`
check run had `head_sha` equal to the PR head and app id 15368. Evidence PRs
for refused rows are left open on purpose. V11's PR #20 is left open (green
check, conflicting).

**Evidence caveats against charter §7.**

- **Ruleset snapshot.** It was verified field by field when applied. After
  that it was recorded per test as id, enforcement and `updated_at`, not as a
  full before/after snapshot per row.
- **Raw payloads.** They live in each run's `gate-report.json` artifact. GitHub
  keeps those artifacts for about 90 days (the V1 artifact expires
  2027-01-15). They are not copied into this repository.
- **`..` traversal.** No variant was attempted as a live PR. So no
  input-rejection result was recorded under the charter's V13 scope note.
  Traversal handling rests on the gate's offline unit tests
  (`test_refusal_reason`, for example `docs/../../etc/passwd`).
- **Offline rows.** V9-A, V12 and the V11 follow-up are executor-reported
  local runs. The reviewer checked them against the unchanged gate code, not by
  re-running them. Their evidence files are held by the executor, not in a
  repository.

## 3. T1 assurance assessment

### 3.1 Against charter §1 and §8

| §1 / §8 condition | Result | Rows |
|---|---|---|
| A real violation of the trusted rule cannot merge; the host refuses it | **Met** | V1, V1 recheck |
| It stays unmergeable with memory edit, deletion or symlink, evaluator substitution, gate or workflow edit, extra workflow, look-alike check, or filesystem redirection | **Met** for every attempted variant | V2, V3, V3a, V4, V5, V6, V7, V7b, V13-A, V13-B |
| A compliant PR can merge (gate not always red) | **Met** | V0, V8, plus V11 seed #19 and rename #21 |
| An earlier head's result cannot authorize a newer head | **Met** for the final state | V10 |
| Overall | **Proven (T1)**, scoped to head-revision blocking (§8 V11 limitation applies), with the §7 evidence gaps listed in section 2 (ruleset snapshots, `..` traversal not exercised live) | |

### 3.2 Host blocking versus classification

The live rows measure **host enforcement**: GitHub refused or accepted a
pinned merge. The offline rows (V9-A, V12, the V11 follow-up) measure the
**gate's classification** only. They show that the gate turns an evaluator
crash or an incoherent payload into UNEVALUATED, and UNEVALUATED into a failed
check. They do not show a host refusal, although the live rows show that any
failed check is refused. V9-A and V12 were offline by design (charter §6: they
test classification, never PR input).

### 3.3 Why the results satisfy the narrow T1 criteria

1. **Trusted inputs.** In every live row the report shows memory blob
   `dd760bf0` taken from the base commit. The job log shows the approved
   wheel hash, and the full base gate ran. V2, V3 and V13-B show a PR cannot
   replace the policy. V4 shows it cannot replace the evaluator. V5 shows it
   cannot replace the gate for its own run.
2. **The refusal is the host's.** Each refusal is a recorded HTTP 405 from the
   merge API, citing the required check. It is not a red job (charter §10).
3. **Check identity.** The PR-added checks in V6, V7 and V7b came from the
   same app (15368) as the gate, so the ruleset's integration pin does not
   tell them apart. In V7 and V7b the look-alike also had the same name, so
   neither name nor app id distinguished it from the genuine gate. What was
   demonstrated is that GitHub refused the merge while a genuine failed
   check coexisted with a successful same-name, same-app look-alike, in both
   observed completion orders. That is consistent with "any failing check of
   the required name blocks". It does not show that GitHub can tell the two
   checks apart, and other orderings (re-runs, re-requests) were not tested.
4. **Head binding.** Check runs attach to the PR head SHA (V0). A new head
   gets a new evaluation, and the old green stays attached only to the old
   SHA (V10).

## 4. ADR-029 evidence audit

The question is whether one live evaluation carries all six ADR-029 binding
dimensions, judged on what the evidence actually records (ADR-029 §2, fail
closed). Sample: the V13-A run (39229633542). All live rows share the same
report shape.

| # | Dimension | What the evidence carries | Binding |
|---|---|---|---|
| 1 | Control / provenance | Workflow path and event (base copy, `pull_request_target`); run id; check run name, app id, `head_sha`; evaluator wheel sha256 **in the job log**; base commit of the gate script. The `mneme.check/v1` payload names no evaluator build, and `0.10.0` is not identity-grade (P2). `gate-report.json` holds neither the wheel hash nor the gate script digest | **Partial.** Assembled by the adapter from the log, the report and the API, not carried by the runtime trace |
| 2 | Subject | Report: `base_sha`, `head_sha`, `merge_base`, and per file the path, git mode, content sha256 and blob id. The blob id is abbreviated (7 hex), because the gate reads `git diff --raw` without `--abbrev=40` or `--full-index`: both the V13-A and V8 artifacts record `"blob": "d7de394"` for blob `d7de39496a978e49d098472f95a3603a45bb647a`. Payload: repository-relative `input_path` only | **Partial.** Bound to the PR diff (merge-base..head) per file. Not bound to the would-be merge result (V11). The payload carries no subject digest |
| 3 | Decision | Payload `decision_id` `ADR-901` and `decision_version_id` `dver-d3d431ff6d5edba8b555a040a7b85f9b`, in both `applicability` and `violations`. Configuration identity: memory blob `dd760bf0` and its sha256, source commit, recorded by the gate | **Bound** for the decision version in the trusted memory. Configuration identity is adapter-recorded, not runtime-emitted |
| 4 | Rule | `rule_id` `ADR-901:FORBID_LITERAL:1eff1b82c5be57bd80379f967b799f7b` (ADR-030 §7 form) in `applicability` and `violations` | **Bound** (ADR-031 §10: `decision_id → decision_version_id → rule_id`) |
| 5 | Applicability | Per file and rule: `outcome` (`APPLIED` / `EXCLUDED`), `selector`, `reason`, `input_path` | **Bound.** V8's EXCLUDED is execution-observed only, never relevant enforcement (ADR-029 scenario B) |
| 6 | Outcome | Per rule: `violations[]` with `rule_id` for FAIL; APPLIED with no violation for PASS. Host: HTTP 405 or 200 tied to the required check on `head_sha` | **Partial.** Rule-level outcome is bound inside the payload. GitHub's response names the check, not the rule; the link from 405 to rule goes through check run → workflow run → artifact |

**Assessment.** ADR-029 §2 requires all six dimensions to be positively
established for the **same** evaluation, and any missing dimension keeps the
evidence at or below execution observed. For live VIOLATION rows, dimensions
3 to 5 are bound in the runtime payload, and so is the rule-level part of 6.
Dimensions 1, 2 and the host part of 6 rest on cross-record joins by the
adapter: the job log, `gate-report.json`, the check run and the merge API
response, linked by run id and head SHA. This record does not show that those
joins meet ADR-029's bar. They are assembled by the experimenter's adapter,
not carried by the runtime trace (ADR-029 §3, §5: no caller-supplied field
manufactures trusted evidence). The control identity is in the job log, not
the report, and the subject blob id is abbreviated.

**Classification: execution observed, with partial evidence binding.** The
lab does **not** claim "relevant enforcement observed" under ADR-029. The
rule-level chain (decision version → rule → applicability → rule outcome) is
complete inside the payload, which is the strongest part of the evidence.
None of this is persisted beyond artifact retention (ADR-029 §7: no evidence
store, which is expected).

**Missing bindings, stated explicitly:**

- the evaluator build identity in the runtime payload or in `gate-report.json`
- the gate script digest in `gate-report.json`
- a full blob id per materialized file: the report records 7 hex (see dimension 2). The content sha256 is present and fully identifies the bytes evaluated
- any binding to the post-merge revision or the synthetic merge commit
- the rule identity in the host's merge response (structural on GitHub, not fixable in the gate)
- durable retention of the bound record beyond about 90 days

UNEVALUATED rows (V9-A, V12) and refused paths carry no payload binding. They
fail closed and are not even rule-level bound.

## 5. Revision freshness

| Property | Status | Evidence |
|---|---|---|
| Head-revision protection | **Demonstrated.** A new head is evaluated afresh. The old green never satisfied it, and the PR showed BLOCKED from the moment the new head registered | V10 |
| Intermediate window after a push | **Observed, not probed.** For about 5 s the PR API still reported the old head with merge state `UNKNOWN`. No merge was attempted in that window | V10 |
| Base-revision / combined-state conformance | **Not implemented in the gate.** The gate evaluates merge-base..head, not the merge result. After the base moved the PR's content into scope, a fresh gate run still PASSed. **V11 Option A closed (2026-10-19):** with squash-only merges and strict up-to-date checks, a head the gate approved against an older base was refused once the base moved (HTTP 405), and after a merge update the landed tree equaled the evaluated head tree. A fresh run on an advanced decision snapshot applied that snapshot (offline). Conditional and GitHub-specific; a live decision-memory update end to end was not covered | V11 (live), follow-up (offline), V11 Option A ([offline](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6272349261), [lab](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6272698989), [charter](../plans/2026-10-19-ci1-v11-option-a-validation-charter.md)) |
| Stale-base false PASS | **Demonstrated** (gate level) | V11 |
| Host-side merge of a nonconforming combined state | **Not demonstrated on GitHub** for either construction. (1) **V11 rename/modify:** local git 2.47.1 with default config merges M2 `1bb964dc` + H `e4d45bb8` cleanly (`git merge-tree --write-tree` exits 0) and puts `install legacy-client` in `docs/v11-note.md`, but GitHub reported the PR DIRTY (a merge conflict, incidental to the gate), so no merge was possible. (2) **V11b directory rename (offline):** default git reports a file-location conflict; only the non-default `merge.directoryRenames=true` merges cleanly into a violating tree. GitHub's server-side behavior for V11b was not tested | [V11](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6263454460), [V11b](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6263559908) |
| Strict status policy (require up-to-date branches) | **Off** in ruleset `25313704`. **Effect measured by V11 Option A (2026-10-19):** with strict on temporarily, an unchanged green head that was BEHIND with no conflict was refused (HTTP 405), and the same PR merged after a merge update and a fresh gate run. Strict was then restored to off and the lab re-archived | ruleset, V11 Option A ([offline](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6272349261), [lab](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6272698989), [charter](../plans/2026-10-19-ci1-v11-option-a-validation-charter.md)) |
| Decision-version freshness | **Not proven.** The gate uses whatever memory the base commit holds and reports its `decision_version_id`. Nothing checks that version against a canonical authority, and there is no re-evaluation trigger when decisions change. Every lab payload's `freshness` channel reported `ADR_MISSING` for ADR-901 and ADR-902 (no ADR sources in the workspace). The gate ignores that channel | all live rows |

## 6. Limitations and unresolved risks

1. **Separate-PR gate weakening (structurally identified, untested).** The
   gate has no mechanism that protects its own definition. A PR that changes
   only `gate/ci1_gate.py` or `.github/workflows/ci1-trusted-gate.yml` has
   nothing in `docs/**`. Such files were evaluated as data and classified
   VERIFIED_PASS (the gate and workflow files in V5, the package files in
   V4). With 0 required approvals, the strong prediction is that such a PR
   would merge, and every later PR would then run the weakened base gate.
   **No such PR was opened and no host-side merge was attempted**, so this is
   a design-level prediction, not an observed result. It is enough on its own
   to justify deferring adoption. Mitigation candidates (required review on gate paths,
   which is T3 and so human-dependent; an external check identity, T4; or
   refusing changes to gate paths) each need their own charter.
2. **Excluded paths (by design).** Protection is exactly as wide as each
   rule's selectors. The same forbidden bytes that were refused under `docs/`
   merged under `src/` (V8). That is a coverage limit, not assurance.
3. **Stale bases.** See section 5. Correctness against an advanced base
   depends on merge conflicts or branch freshness, not on the gate.
4. **Malformed memory produces a crash, not evidence.** The evaluator exits 1
   with a traceback and empty stdout (V9-A, matching the CI1.2.2 memory-errors
   fixture). The gate's coherence check is what makes this UNEVALUATED. A
   structured incomplete-evaluation payload would be a separate CLI contract
   change with a new fixture version. This is a product follow-up, not a CI1
   blocker.
5. **UNEVALUATED blocks only by lab policy.** Per-file UNEVALUATED aggregates
   to BLOCK because the lab chose fail-closed (V9-A, V12). ADR-033 is
   undecided. The aggregate `UNEVALUATED` label is reserved for gate-level
   errors.
6. **Untested merge races.** These were not tested: a re-run or re-requested
   check replacing the genuine failure, the post-push window above, merge
   queues, and concurrent pushes during evaluation. V7 and V7b cover only two
   completion orders.
7. **Policy changes cannot pass the gate.** All `.mneme/` changes are refused,
   so in the lab a legitimate decision update cannot merge through the gated
   PR path at all. A production design needs a governed path for decision
   changes (DG1, #497), which this experiment did not address.
8. **Hosting dependencies.** `pull_request_target` behavior after GitHub's
   2026-11-02 default restriction is unknown; policy `7806` removed the
   evaluate-mode warning, but enforcement has not started. On the Free plan,
   rulesets enforce only on public repositories (charter §2).
9. **Narrow corpus.** One literal-tier, query-independent `FORBID_LITERAL`
   rule, one protected branch, one experimenter. Prose or retrieval-gated
   rules, multiple decisions, waivers and DG1 applicability were not
   exercised.
10. **Evidence durability.** GitHub artifacts expire in about 90 days. The
    offline evidence and the collector script are held locally by the
    executor and are unreviewed. The lab is due to be archived after CI1.4.

## 7. Recommendation

**DEFER production merge blocking.**

**Basis.** The lab proved the narrow T1 claim: with trusted inputs from the
base, a violating PR cannot merge, and substitution attempts inside the same
PR do not change that. It did not prove that `main` stays conformant. The
gate judges diffs, not merge results (V11). There is a structurally
identified, untested path to weaken its definition through an earlier,
compliant PR (section 6.1). Decision freshness is
unchecked. Experimental success is not production readiness, and charter §9.4
and ADR-031 §7 require a separate charter and `[layer1-freeze]` amendment for
any adoption in any case.

**Scope of what may be claimed now.** In an isolated lab, a T1
`pull_request_target` gate with a required status check makes GitHub refuse
the merge of a PR whose own diff violates an in-scope literal rule. This holds
against same-PR policy, evaluator, gate, look-alike and symlink substitution,
and is bound to the exact PR head. Nothing broader.

**Conditions for a later promotion decision** (each needs its own approval):

1. Close or explicitly accept the separate-PR gate-weakening limit, with a
   designed and tested mitigation.
2. Base-revision conformance: evaluate the merge result, or require
   up-to-date branches. Then measure it.
3. An ADR-033 decision on UNEVALUATED handling, replacing the lab's
   fail-closed choice.
4. A structured malformed-memory result in the CLI contract (new fixture
   version), or an explicit acceptance of the crash path.
5. Runtime-carried control provenance and subject binding (ADR-029
   dimensions 1 and 2), plus a durable evidence record, if production claims
   are to rest on them.
6. A governed path for decision changes under a gate that refuses `.mneme/`
   edits.
7. Confirmed `pull_request_target` behavior after 2026-11-02 on the target
   repository.
8. Coverage beyond one literal rule, and a production-shaped ruleset
   (approvals, bypass actors, merge queue).
9. The G2 C1 charter and a `[layer1-freeze]` amendment before any change to
   `MnemeHQ/mneme` workflows or rulesets.

**Next decision (separate).** Whether the separate-PR gate-weakening
experiment must run before the promote/defer decision is final. Then archive
the lab, after preserving the artifacts that this record cites.
