# CI1: Separate-PR gate weakening, architecture and threat-model review (proposal)

**Status:** **PROPOSED, design only.** Nothing here is executed or
authorized. It does not change the lab repository, its ruleset `25313704`,
its Actions policy `7806`, its baseline `3a87809c`, the gate, any workflow,
`.mneme/`, Mneme Core, or anything in `MnemeHQ/mneme`. It does not open a lab
PR, attempt a merge, or decide ADR-033. Section 7 lists what would need its
own approval.
**Tracker:** #540 (CI1 Enforcement Assurance).
**Responds to:** [CI1.4 record](../validation/ci1-4-trusted-merge-gate-validation-2026-10-19.md)
§6.1 (separate-PR gate weakening) and §7 condition 1 ("close or explicitly
accept ... with a designed and tested mitigation").
**Builds on:** [CI1.3 charter](2026-10-17-ci1-3-isolated-merge-blocking-experiment-charter.md)
§3 (T1 to T4), §9, §10;
[ADR-029](../adr/ADR-029-enforcement-evidence-binding-semantics.md);
[ADR-031](../adr/ADR-031-decision-governance-semantics.md) §7;
[Layer 1 freeze](../architecture/layer1-freeze-e73ff7d.md).
**Lab source read (not modified):** `MnemeHQ/mneme-ci1-lab` @ `3a87809c`:
`gate/ci1_gate.py`, `.github/workflows/ci1-trusted-gate.yml`,
`gate/evaluator-requirements.txt`, `policy/ruleset-main.proposed.json`,
`policy/actions-policy-gate-event.proposed.json`.
**Core anchor:** `main` @ `f814867b`.

## 0. Summary

- **The threat.** T1 protects a PR's *own* evaluation by running the base
  copy of the gate. It does not protect the base copy. A compliant PR that
  edits only the gate's trusted surface (gate script, workflow, evaluator
  pin, build constraints) has nothing for ADR-901 to apply to, passes, and,
  under a ruleset with 0 required approvals, is predicted to merge. Every later
  PR is then judged by the weakened gate.
- **Evidence versus prediction.** Evidenced: the gate classifies gate and
  workflow files as VERIFIED_PASS data (V5), and package files likewise (V4);
  the gate refuses only `.mneme/` and non-regular or unnormalized paths
  (source). Predicted, never attempted: that GitHub would merge such a PR,
  and that later PRs would then run the modified gate.
- **The asymmetry.** Decision memory is protected *across* PRs, because the
  gate refuses every `.mneme/` change. The gate's own definition is not. The
  smallest mitigation is to extend the same refusal to the gate's trusted
  surface.
- **Recommendation (section 6): C1, the gate refuses changes to its own
  trusted surface**, as the preferred direction for further design. C1 is the
  mechanically enforced part. Any route for legitimate gate or policy changes
  is a separate, human or administrative exception that C1 cannot constrain
  (section 4); its authority, eligibility, bootstrap, rollback and host-side
  validation stay undecided. T3 (code-owner review) is optional defense in
  depth. T4 (external check identity) changes the trust boundary and is not a
  prerequisite. The next step is a separate, narrowly scoped C1 lab
  implementation and validation charter, initially with **no** bypass actor.
  Production merge blocking stays **DEFERRED**. Nothing is authorized here.

## 1. The threat, stated precisely

### 1.1 Question

Can a compliant earlier PR **A**, which edits only the gate script or the gate
workflow (nothing under `docs/**`, nothing under `.mneme/`), merge into lab
`main` under ruleset `25313704` (PR required, 0 approvals, required check
`CI1 trusted gate` from integration 15368, `bypass_actors: []`), so that a
later PR **B** containing a real ADR-901 violation is evaluated by the
weakened base gate and merges?

### 1.2 Why the gate would pass PR A (from source)

The base gate at `3a87809c` treats a PR's changes as follows:

| Change in PR A | Gate handling (`gate/ci1_gate.py`) | Result |
|---|---|---|
| Edit `gate/ci1_gate.py` or `.github/workflows/ci1-trusted-gate.yml` | Regular blob, not under `.mneme/`, so `refusal_reason` returns `None`; materialized and evaluated as data. ADR-901 has `include_paths: [docs/**]`, so applicability is EXCLUDED and the verdict PASS | VERIFIED_PASS |
| Edit `gate/evaluator-requirements.txt` or `p2/build-constraints.txt` | Same | VERIFIED_PASS |
| Edit the evaluator pin (`EVALUATOR_COMMIT`, `APPROVED_WHEEL_SHA256`, `repository:` in the workflow) | Same: it is a line in the workflow file | VERIFIED_PASS |
| Delete the workflow or the gate script | Deletions outside `.mneme/` are recorded as `skipped` ("deleted") and never evaluated | PASS (nothing refused) |
| Add a new workflow | Regular blob, evaluated as data | VERIFIED_PASS |

`decide()` passes when nothing is refused and every evaluated file is
VERIFIED_PASS. PR A therefore gets a green `CI1 trusted gate` from the base
gate, which is the only thing the ruleset requires.

### 1.3 What is evidenced and what is predicted

| Claim | Status | Basis |
|---|---|---|
| The gate evaluates its own script and workflow as ordinary data and classifies them VERIFIED_PASS | **Evidenced (live)** | V5 (lab PR #14, run 39066656055): the PR's workflow and `gate/ci1_gate.py` "were only evaluated as files (VERIFIED_PASS)"; [#540 comment](https://github.com/MnemeHQ/mneme/issues/540#issuecomment-6240521788) |
| Package and packaging files are likewise VERIFIED_PASS data | **Evidenced (live)** | V4 (lab PR #13), same comment |
| The gate refuses only `.mneme/`, non-regular modes, unnormalized paths and collisions | **Evidenced (source)** | `refusal_reason` and `build_workspace` at `3a87809c`; the lab's offline `test_refusal_reason` |
| Non-`.mneme/` deletions are not evaluated and do not block | **Evidenced (source)** | `build_workspace` (`skipped`) |
| A PR whose gate result is green, under 0 required approvals, is merged by GitHub | **Evidenced (live)** for compliant `docs/` and `src/` changes | V0 (#3), V8 (#24): HTTP 200 |
| **A PR that changes only the gate's trusted surface merges** | **Predicted, never attempted** | Follows from the rows above. No such PR was opened and no merge was attempted (CI1.4 §6.1) |
| **After that merge, later PRs run the modified gate** | **Predicted from documented platform behavior** | `pull_request_target` runs the workflow file from the base branch, and V5 showed the base copy, not the PR copy, runs. A run of a modified base gate was never observed |
| A weakened base gate lets a violating PR B merge | **Predicted** | Depends on how the gate was weakened (section 1.4) |

The prediction is strong, but V5 alone does not prove it. V5 measured only
that the PR's own copy does not run for that PR. It did not measure the next
PR.

### 1.4 Weakening variants

Not every edit to the trusted surface produces a silent bypass. The
distinction matters for detection and for the controls in section 3.

| Variant (PR A) | Effect on later PR B | Class |
|---|---|---|
| Keep job name `CI1 trusted gate` and trigger, and change the **workflow's** `Gate decision` step so it succeeds regardless (for example the V5 workflow payload, a same-name job that exits 0, merged on its own instead of combined with a violation) | Required check reports success without evaluating | **Silent bypass** |
| Keep the workflow, and change `gate/ci1_gate.py` so it exits 0 **and** writes a coherent, parseable `gate-report.json` with `passed: true` and `verdict: "PASS"` without evaluating | The unchanged decision step accepts the fabricated report | **Silent bypass** |
| Change `gate/ci1_gate.py` only to exit 0 (for example V5's `raise SystemExit(0)`) without producing a passing report | The `Gate decision` step (lab PR #5, `051d21ee`) requires exit 0 **and** a report that parses with `passed: true` and `verdict: "PASS"`. A missing or contradictory report blocks | **Fail-safe**, not a bypass |
| Change the evaluator pin to another commit and hash, in any repository the workflow names | A different evaluator decides. It also runs inside the `pull_request_target` job with the read-only token | **Silent bypass**, plus code execution in the privileged context |
| Edit `evaluator-requirements.txt` or `build-constraints.txt` | Dependencies or build inputs change. A hash mismatch fails closed; a coordinated hash change does not | Silent bypass if coordinated |
| Edit the gate's verdict rule (for example treat WARN or UNEVALUATED as pass, or shrink the refusal list) | Partial weakening | Silent, partial |
| Narrow `on.pull_request_target.branches` or `types`, rename the job, or delete the workflow | The genuine check never reports. PR B shows the required check as expected and is blocked | **Fail-safe** on its own |
| The fail-safe variant, then PR B adds its own `pull_request` job named `CI1 trusted gate` | The look-alike is the only check of that name, from app 15368, and is green. V7/V7b showed a genuine failure wins when both exist, not what happens when the genuine check is absent | **Silent bypass: untested hypothesis** |

The last row matters: deleting the gate is fail-safe only while no other check
can claim its name. The ruleset pins integration 15368, which every Actions
workflow shares (V6, V7), so any PR can supply a same-name check. **"The
genuine gate stops reporting" is therefore a candidate bypass path**, in two
steps. This is an **untested hypothesis**: no lab row has observed a
same-name look-alike with the genuine check absent.

### 1.5 Threat actor and preconditions

- **Actor:** an agent or person who can open and merge PRs. This is the CI1
  proof's subject: "an agent cannot make a prohibited change pass by
  modifying the policies or mechanisms that evaluate that same change".
  Splitting the work over two PRs is cheap for an agent and needs no
  privilege beyond the one already assumed.
- **Preconditions:** 0 required approvals; no rule that treats gate paths
  specially; merge rights for the actor. All three hold in the lab.
- **Not needed:** admin rights, secrets, or any change to the ruleset or the
  Actions policy.
- **Detection today:** none by mechanism. The weakening is visible in the PR
  diff and in `main` history to a reader.

## 2. Related trust-boundary paths

The gate's verdict depends on more than the two files named in §1.1. Its
**trusted surface** is everything the base commit or the repository settings
supply to a gate run.

| # | Path | Who can change it | Protected today? | Notes |
|---|---|---|---|---|
| P1 | Gate workflow `.github/workflows/ci1-trusted-gate.yml`: trigger, job name, steps, permissions, evaluator pin (`EVALUATOR_COMMIT`, `APPROVED_WHEEL_SHA256`, `repository:`), `GATE_PYTHON` | Any compliant PR | **No** | Section 1 |
| P2 | Gate script `gate/ci1_gate.py`: refusal rules, query, classification, verdict | Any compliant PR | **No** | Section 1 |
| P3 | Evaluator inputs `gate/evaluator-requirements.txt`, `p2/build-constraints.txt` | Any compliant PR | **No.** The wheel hash fails closed; a coordinated hash change does not | Read from `base/` by the workflow |
| P4 | Any other workflow under `.github/workflows/` | Any compliant PR | **No** | Can supply a same-name, same-app check (V6, V7) and runs on `pull_request` with the repository's default permissions |
| P5 | Base checkout influence: `.gitattributes` and similar files that change how `actions/checkout` writes the base tree | Any compliant PR | **No** | **Not analyzed.** `git cat-file blob` (used for PR content and memory) applies no filters, but the gate script and constraints files are read from a checked-out tree. Listed for completeness, not as a known exploit |
| P6 | Decision memory `.mneme/**` | Nobody, through the gated PR path | **Yes, by refusal** (V2, V3, V3a, V13-B) | Also means legitimate decision changes cannot merge at all (CI1.4 §6.7) |
| P7 | Actions policy `7806` (allows `pull_request_target` only for the gate workflow path) | Repository or org admins, out of band | No in-repo mechanism | Deleting it exposes GitHub's default restriction from 2026-11-02 (behavior unknown, CI1.4 §6.8). Editing its `workflow_path` lets another workflow use `pull_request_target` |
| P8 | Ruleset `25313704`: required check, integration pin, approvals, bypass list, enforcement | Repository or org admins, out of band | No in-repo mechanism | An admin can remove the check, add bypass actors or disable enforcement. No in-repo control can prevent this; it is the GitHub root of trust |
| P9 | Evaluator source `MnemeHQ/mneme` at `0b74d410` | Not mutable (commit pinned, wheel hash checked) | **Yes**, for the pinned commit | Holds only while P1 keeps the pin. A pin change is P1 |
| P10 | Third-party actions pinned by SHA (`actions/checkout`, `actions/upload-artifact`) | A P1 edit | Pinned, but the pin is in P1 | Same as P9 |

P1 to P5 are in-repo and reachable by a compliant PR. P7 and P8 are
out-of-band admin settings. P6 is the one in-repo surface the gate already
protects, and the design to copy.

## 3. Candidate controls

### C1. The gate refuses changes to its own trusted surface

**Mechanism.** Extend the base gate's refusal list from `.mneme/` to a
trusted-surface list held in the base commit: at least `.github/**` (all
workflows, which also covers P4 and the look-alike path), `gate/**`, `p2/**`,
`policy/**`, `.gitattributes`, and wherever the list itself lives. Refuse
additions, modifications **and deletions** (today non-`.mneme/` deletions are
skipped). `--no-renames` already turns a rename into a delete and an add, so a
rename out of a protected path is a refused delete. A refused path blocks,
exactly as V2 and V3 did for `.mneme/`.

- **Mitigates:** P1 to P5 through the gated PR path. It makes the threat in
  section 1 fail closed by the same mechanism CI1.3 already proved for P6. It
  also closes the two-step look-alike path in §1.4, because no PR can add or
  change a workflow.
- **Residual risk:**
  - Completeness of the list. Anything the base run reads that is not on the
    list stays open. The list must be derived from what the workflow actually
    reads, and kept under review.
  - P7 and P8 (admin edits) are untouched.
  - The integration pin still cannot tell a same-name check apart (V7). With
    C1 no PR can introduce a workflow, so the remaining sources are an admin
    or an installed app.
  - **Legitimate gate and policy changes can no longer merge through the gated
    path at all.** That is the position `.mneme/` is already in (CI1.4 §6.7).
    Any way through is a separate exception, outside what C1 enforces
    (section 4).
- **Free plan:** yes. Pure gate logic.
- **ADR-031 §7 / Layer 1 freeze:** fits. It changes the lab adapter's policy
  only, not Mneme's retrieval or enforcement behavior. Any adoption in
  `MnemeHQ/mneme` still needs the G2 C1 charter and a `[layer1-freeze]`
  amendment (charter §9.4, CI1.4 §7.9).
- **Governed path for legitimate changes:** not provided by C1. C1 only
  refuses. Any exception route (section 4) is separately trusted human or
  administrative authority, and C1 cannot limit what that authority is used
  for.

### C2 (T3). CODEOWNERS and required code-owner review on gate paths

**Mechanism.** A base-branch `CODEOWNERS` assigning P1 to P5 (and `CODEOWNERS`
itself) to a named owner, with `require_code_owner_review: true` in the
ruleset.

- **Mitigates:** P1 to P5, by requiring a human approval for any change to
  them. GitHub reads `CODEOWNERS` from the base branch, so a PR cannot remove
  its own owner requirement.
- **Residual risk:**
  - **Human-dependent.** It does not meet the charter §1 proof by mechanism
    (charter §3: T3 "must not count toward the §1 proof").
  - A reviewer approving a plausible-looking change is the attack surface.
  - GitHub does not count a PR author's approval of their own PR. If the
    author is the sole code owner, a single-maintainer organization either
    cannot change the gate or needs a bypass, which brings back section 4's
    question.
  - Whether `require_code_owner_review` is enforced while
    `required_approving_review_count` is 0 is **to be confirmed**. If it is
    not, C2 needs a non-zero approval count for every PR, a broader ruleset
    change.
  - `dismiss_stale_reviews_on_push` and `require_last_push_approval` must be
    on, or an approved PR can be changed after approval (the V10 analogue for
    reviews).
- **Free plan:** yes for public repositories.
- **ADR-031 §7 / freeze:** fits as a ruleset-level measure; it changes no
  Mneme behavior. In `MnemeHQ/mneme` it is a ruleset change, so it falls
  under the G2 C1 charter and `[layer1-freeze]` amendment requirement.
- **Governed path:** the review itself is the path. That is its strength and
  its weakness.

### C3 (T4). External check identity: a GitHub App with a pinned `integration_id`

**Mechanism.** The evaluator and gate run outside the repository (a GitHub App
or external CI) and post `CI1 trusted gate` under the app's own identity. The
ruleset pins the required check to that app's `integration_id`, not 15368.

- **Mitigates:** P1 to P4 and P10 for the verdict: no repository PR can change
  the code that decides, because it is not in the repository. It also closes
  the same-app look-alike limit (V7) and the two-step deletion path (§1.4),
  because an Actions check can no longer satisfy the requirement.
- **Residual risk:**
  - The trust boundary moves to the app's source, release process, hosting
    and private key. That deployment needs its own protection, so the
    separate-PR question recurs one level up.
  - P7/P8: an admin can still change the ruleset pin or uninstall the app.
  - Policy source: where the app reads decision memory (base commit, or a
    separate store) must be specified, or P6 reopens.
  - An app outage blocks every merge. That is fail-closed and therefore
    correct, but costly.
- **Free plan:** GitHub Apps are available on Free. Hosting is not GitHub's,
  so it is a new service to run.
- **ADR-031 §7 / freeze:** compatible, but heavyweight. It is closest to a
  product (charter §3: "not an experiment default") and overlaps the reusable
  adapter work tracked outside CI1 (#278). It needs its own charter and,
  before any `MnemeHQ/mneme` use, the freeze amendment.
- **Governed path:** gate changes ship through the app's release pipeline.
  Decision changes still need the section 4 path, unless the app owns a
  decision store, which is DG1 territory (#497).

### C4. Gate definition held in a separate protected repository

**Two variants.**

- **C4a (T2, ruleset "required workflows").** An org ruleset requires a
  workflow that lives in a policy repository, which the governed repositories
  cannot edit. Charter §3 treats this as needing a paid plan. **Treated as
  unavailable on Free; to confirm.**
- **C4b (SHA-pinned reusable workflow).** The in-repo workflow becomes a stub:
  `uses: MnemeHQ/<gate-repo>/.github/workflows/gate.yml@<sha>`.

- **Mitigates:** C4a removes P1 to P4 from the repository entirely. C4b moves
  the gate *logic* out, but **the stub and its pin are still P1**: a compliant
  PR can repoint the stub. So C4b does not mitigate the threat on its own. It
  only shrinks the in-repo surface to one file, which C1 or C2 must then
  protect.
- **Residual risk:** for C4a, the policy repository's own change path (its own
  separate-PR question) and P8 at org level. For C4b, everything in C1/C2,
  plus the policy repository.
- **Free plan:** C4a believed no; C4b yes.
- **ADR-031 §7 / freeze:** as for C1; it changes no Mneme behavior.
- **Governed path:** changes go through the policy repository's protections.
  With one maintainer, that repository has the same review problem as C2.

### C5. Accept the risk

**Mechanism.** None. Record the limit and restrict who can merge.

- **Mitigates:** nothing by mechanism. In practice the risk is bounded by who
  holds merge rights and whether every merge is read by a person.
- **Residual risk:** the whole of section 1. With agents holding merge rights,
  the two-step attack has no control.
- **Free plan:** yes.
- **ADR-031 §7 / freeze:** compatible only with an advisory, non-blocking
  posture. A merge-blocking claim under charter §1 cannot be made while this
  limit is accepted, because two PRs change the mechanism that judges the
  second one.
- **Governed path:** unchanged (any PR).

### 3.1 Comparison

| Control | P1 to P3 gate, pin | P4 other workflows, look-alike | P5 checkout influence | P6 memory | P7/P8 admin | Mechanism, not people | Free | Cost |
|---|---|---|---|---|---|---|---|---|
| C1 refuse own surface | **Yes** | **Yes**, if `.github/**` is listed | Yes, if listed | Already yes | No | **Yes** | Yes | Low: gate logic and tests |
| C2 code-owner review | Yes (human) | Yes (human) | Yes (human) | Can add | No | No | Yes (to confirm with 0 approvals) | Low setup; ongoing review cost; single-maintainer gap |
| C3 external app | **Yes** | **Yes** (identity pin) | Yes | Depends on design | No | **Yes** | App yes, hosting extra | High |
| C4a required workflows | Yes | Partly | Yes | Depends | No (org admin) | Yes | **Believed no** | Plan change |
| C4b reusable stub | **No**, alone | No | No | No | No | No | Yes | Low, but needs C1 or C2 |
| C5 accept | No | No | No | Already yes | No | n/a | Yes | None; rules out the §1 claim |

No control covers P7/P8. Admin edits of the ruleset and the Actions policy
are outside any in-repo mechanism on GitHub. The honest handling is to name
them as the root of trust and observe them (section 6), not to claim
otherwise.

## 4. Exceptions for legitimate trusted-surface changes (separate from C1)

C1, like the existing `.mneme/` refusal, makes every legitimate gate or policy
change unmergeable through the gated path. That is the intended effect. A
production design would still need some way through, but that way is **not
part of C1** and must not be described as if C1 enforced it.

**Two different things, kept apart:**

- **C1, mechanically enforced.** The base gate refuses changes to the trusted
  surface and to `.mneme/`. Nothing in a PR can switch that off. This is the
  only part of this document that meets the charter §1 standard by mechanism.
- **The exception, separately trusted.** Any route that lets a refused change
  land relies on a human or administrative actor whom the gate does not
  control. Its safety rests on that actor, not on the gate.

**Why a ruleset bypass is broader than the exception.** The obvious route on
GitHub Free is a ruleset bypass actor with `bypass_mode: pull_request`.
GitHub grants that as permission to bypass the ruleset's rules for pull
requests in general. It is not limited to particular changed paths or to a
particular refusal reason. An actor holding it could merge a genuine ADR-901
violation as easily as a legitimate gate update. Each use is visible
afterwards in rule-suite history, but nothing scopes it beforehand. It is
therefore not a bounded exception, and this document does not recommend it
as one.

**Reporting cannot constrain a bypass.** The gate could report a refused
trusted-surface change distinctly from a violation (for example
`GOVERNED_CHANGE`), so a reviewer can tell "needs the exception route" from
"violates a decision". That helps a careful human. It **cannot** constrain an
actor who uses a ruleset bypass: the bypass skips the required check whatever
the check reported. The check still fails either way.

**Candidate routes, for a later charter to evaluate (none recommended here):**

1. A ruleset bypass actor (`bypass_mode: pull_request`), with the scope limits
   above recorded as residual risk, not as a control.
2. An admin-only direct change, no PR. It leaves no PR review record and
   conflicts with the repository's PR-only practice for `main` (ADR-022's
   pre-push guard; the `main-pr-only` ruleset named in charter §2).
3. C2 review as the route: the gate admits a trusted-surface change only when
   the PR carries a code-owner approval. That needs the gate to read review
   state, which is host data rather than repository data and opens its own
   trust questions.

**Common mechanism versus authority.** One technical exception workflow could
serve both gate changes and decision-memory (`.mneme/`) changes (CI1.4 §7
condition 6, DG1 #497). That stays a candidate. Sharing a mechanism does
**not** share authority: ADR-031 defines decision governance semantics, and
nothing in it establishes who may approve changes to the CI gate, its
workflow or its evaluator. The following are **explicitly undecided**, pending
a separate charter:

- **approval authority:** who may approve a trusted-surface change, and
  whether that differs from who may approve a decision change;
- **eligibility:** which changes may use the exception at all;
- **bootstrap:** how the first C1 gate reaches `main`, since C1 refuses
  trusted-surface changes once it is in place;
- **rollback:** how a bad gate or evaluator change is reverted when the revert
  is itself a refused change;
- **host-side validation:** how ruleset and Actions policy state is checked
  around an exception, given P7 and P8.

## 5. Validation each control would need

| Control | Offline (no lab change) | Live lab run (needs its own approval) |
|---|---|---|
| **Threat baseline** (no control) | Already covered by source reading and the V4/V5 classification evidence (section 1.3) | **Optional.** The only way to turn the prediction into an observation. Use a **benign** trusted-surface change (for example a comment-only edit to `gate/ci1_gate.py`) and one pinned merge attempt; expected HTTP 200. That proves "trusted-surface changes merge" without installing a weakened gate. It moves the lab baseline and needs a revert plan. Merging a weakened gate and then a violating PR B is **not** recommended: it deliberately breaks the lab's trusted state |
| **C1** | Unit tests in the lab's `tests/test_ci1_gate.py`: every listed path refused for add, modify, delete, mode change and rename; deleting a trusted-surface path blocks even as the only change; nested paths; a control outside the trusted surface still passes; the report distinguishes trusted-surface refusals from violations. A workflow test that enumerates every base file the workflow reads and asserts each is covered. Replay against local commits, as V9-A and V12 did | One short batch after the C1 gate is on lab `main`: (a) compliant PR changing only `gate/ci1_gate.py`, expected **405**; (b) PR deleting the gate workflow, **405**; (c) PR adding a `pull_request` workflow, **405**; (d) compliant `docs/` PR, **200**. Run initially with **no bypass actor** on the ruleset. Any exception route (section 4) is out of scope for this batch and needs its own charter |
| **C2** | Not meaningfully testable offline; the control is the host's review enforcement | Confirm `require_code_owner_review` with 0 approvals, author-as-sole-owner behavior, and stale-review dismissal after a push. Human-dependent, so recorded as defense in depth, not proof |
| **C3** | The app's evaluator logic could reuse the gate's offline tests | Full live validation: identity pin, a 15368 look-alike no longer satisfies the requirement, an app outage blocks. Needs an app and hosting; product-scale charter |
| **C4a** | n/a | Needs a plan change to test at all |
| **C4b** | As for C1, applied to the stub path | As for C1 |
| **C5** | n/a | n/a. A written acceptance with a named owner and scope |

The C1 offline tests are cheap and decisive for gate behavior, because the
refusal path that turns into a host refusal is already proven live (V2, V3,
V3a, V13-B). A live C1 batch adds confirmation that the new refusals reach the
host the same way. It is one short batch, not a new matrix. It does not
validate any exception route.

In the lab, bootstrap is not yet a blocker: the current base gate does not
refuse gate paths, so the PR introducing C1 would pass it (that is the threat
in section 1). Once C1 is on lab `main`, every later gate change, including a
rollback of C1, is refused. A C1 lab charter must say how the lab is reset or
archived afterwards without an exception route.

## 6. Recommendation

**Direction, for further design only: C1, the gate refuses changes to its own
trusted surface.** This is a preferred design direction, not an approved
implementation and not an exception policy. C1 covers additions,
modifications, deletions and renames on the trusted surface, extending the
existing `.mneme/` refusal. Any exception route is a separate, separately
trusted decision (section 4).

Reasons:

1. It closes the identified threat by **mechanism**, the standard charter §1
   sets, using a refusal path already proven live for `.mneme/`. It adds no
   new trust assumption.
2. It would also close the two-step look-alike path (§1.4, an untested
   hypothesis), which C2 handles only through people and C3 only at product
   cost.
3. It is available on Free, small, and fully testable offline before any live
   run.
4. V5 showed that a PR cannot substitute the gate for its own run. It does not
   protect the gate after an earlier PR has changed the trusted base. C1 is the
   smallest change that makes the base itself unchangeable through the gated
   path.

**What C1 does not settle.** It leaves legitimate gate and policy changes with
no route through the gated path. Whatever route is later chosen is human or
administrative trust, not mechanism, and on GitHub Free the available bypass
is broader than any single exception (section 4). C1 therefore removes the
unreviewed path; it does not create a bounded exception.

**Optional defense in depth:** C2 on the same paths, once a second reviewer
exists. It is not counted toward the §1 proof.

**Later, separately:** C3 (T4) changes the trust boundary (to the app's own
deployment) rather than closing it, and is not a prerequisite for C1. It is
the candidate remedy for the same-app look-alike limit and for moving the
verdict out of the repository, and belongs with adapter productization, not
with closing §6.1.

**Next step (needs its own approval):** a separate, narrowly scoped C1 lab
implementation and validation charter: the lab gate change, the offline tests
and the short live batch in section 5, initially with **no** bypass actor.
Production merge blocking remains **DEFERRED** (CI1.4 §7).

**Not recommended:** C4b alone (it moves the problem into a stub), and C5 for
any merge-blocking claim.

**What remains after C1**, for the CI1.4 §7 decision: P7/P8 (admin edits of the
ruleset and the Actions policy) are the GitHub root of trust and stay outside
any in-repo control. They can be observed (for example by recording the
ruleset and policy contents and `updated_at` per evaluation in the gate
report) but not prevented. The trusted-surface list (P5 in particular) needs
ongoing review.

## 7. Not authorized by this document

- Any change to `MnemeHQ/mneme-ci1-lab`: gate, workflows, tests, ruleset
  `25313704`, Actions policy `7806`, baseline `3a87809c`, branches or PRs.
- Opening any lab PR or attempting any merge, including the benign baseline
  row in section 5.
- Any change to `MnemeHQ/mneme` workflows, rulesets, `.mneme/`, Core code or
  the frozen benchmark.
- Choosing a bypass actor or adding one to any ruleset.
- Treating C1, C2 or C3 as accepted. Each needs its own charter and, for any
  `MnemeHQ/mneme` adoption, the G2 C1 charter and a `[layer1-freeze]`
  amendment (ADR-031 §7).

**Decisions this document asks for, separately:**

1. Accept or reject C1 as the design direction for CI1.4 §7 condition 1.
2. Whether the optional benign baseline row (section 5) should run first, or
   whether the source-level prediction is enough.
3. Whether to draft the separate C1 lab implementation and validation charter
   (no bypass actor).
4. Separately and later: a charter for any exception route, covering approval
   authority, eligibility, bootstrap, rollback and host-side validation
   (section 4). This document decides none of them.
