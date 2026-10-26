# CI production rollout R0: readiness charter (Mneme Core)

**Status: ACCEPTED (owner, 2026-10-26).** Read-only charter. Merging it records
the owner's rulings R1-R5 in §6 and nothing else. R2 (Option A) is accepted as
design direction only. **It authorizes no workflow, ruleset, required-check,
Actions-policy, repository-variable or `.mneme/` change on `MnemeHQ/mneme`,
and no `[layer1-freeze]` amendment.** Production merge blocking stays
**DEFERRED** ([CI1.4 §7](../validation/ci1-4-trusted-merge-gate-validation-2026-10-19.md)).
**Date:** 2026-10-26.
**Baseline:** `main` @ `dbab816f` (#675; the review baseline was `085244dc`,
C4 closure #682. #674/#675 changed the hook's ADR-034 numeric path only, not
the CI adapter or the pinned evaluator).
**Prior milestone:** ADR-033 C4, closed by
[the C4 closure record](../validation/adr033-c4-closure-2026-10-26.md) (#682).
**Tracker:** #540 (CI1 Enforcement Assurance).

## 1. Question

C4 answered: *does the adapter behave according to its contract?* (yes, within
the recorded coverage, in the isolated lab).

R0 asks: *can Mneme Core adopt that adapter as one genuine required check on
`main` without unacceptable governance, operational or recovery risk?*

CI stays the verification layer (ADR-021); it does not replace pre-mutation
enforcement.

## 2. Rollout boundary (proposed)

| Dimension | R0 boundary |
|---|---|
| Repository | `MnemeHQ/mneme` only, branch `main` |
| Adapter | C4 pin: `c51729f7`, blob `5feedf60`, SHA-256 `afe1d69c…` |
| Evaluator | commit build of `0b74d410`, wheel SHA-256 `e3fcc769…` (CI1 P2) |
| Semantics | ADR-033 as implemented in C4; no change |
| Decision memory | trusted base revision (`source_commit` = base) |
| Check identity | one GitHub Actions check (app 15368) from a `pull_request_target` workflow |
| Availability | administrator-set `MNEME_CI_AVAILABILITY` (`open` / `closed`; invalid = `closed`) |
| Starting point | [`bootstrap-ci1-trusted-gate.yml`](../validation/adr033-c4-gate3-live-2026-10-26/bootstrap-ci1-trusted-gate.yml) and [`github-actions-c4-gate.md`](../integrations/github-actions-c4-gate.md) |
| Excluded | evaluator upgrade, new rules, multi-repo rollout, reopening C4, CLI malformed-memory redesign |

Changing either pin needs a new parity proof and owner approval (C4 Gate 0 A5).
Before any evaluator newer than `0b74d410`, the ADR-034 numeric/`subject`
payload case must be fixed in the adapter: those records are classed
UNEVALUATED, so under `open` a payload containing a FAIL could pass
(C4 closure §7).

## 3. Core configuration today (read-only, 2026-10-26)

Observed through the GitHub API; nothing was changed.

| Setting | Value | R0 relevance |
|---|---|---|
| Ruleset `main-pr-only` (22196895) | active; squash only; 0 required approvals; no bypass actors | §5 recovery route needs a bypass decision |
| Required checks | `gate (PR battery)`, `Scan docs/scripts for mojibake + BOM`, `Validate PR execution provenance`, `Verify install commands name mneme-hq`, `mneme check --mode warn` | the warn check is required but always green |
| Strict up-to-date (`strict_required_status_checks_policy`) | **false** | CI1 Option A depends on it (condition 2) |
| Actions permissions | enabled; `allowed_actions: all`; SHA pinning not required | lab workflow already SHA-pins its actions |
| Visibility | public | GitHub's 2026-11-02 `pull_request_target` change applies |

`mneme-check.yml` runs on `pull_request`, checks out the PR head, installs the
local package, runs `--mode warn` with `|| true`, and skips when memory is
absent. It is an implicit `open` with PR-controlled code and memory (ADR-033
§5). Switching it to `strict` would bypass the C4 trust model rather than adopt
it, so R0 does not propose that.

Core's memory has 21 decisions and **one** literal-tier rule: ADR-005's
`FORBID_LITERAL` on the wrong-package install command (the bare `mneme`
package name after `pip install`). The C4 evidence covers literal-tier rules
only, so this is the only rule the gate can currently block on.

Observed while drafting this charter (local `mneme check`, current `main`):
the correct `mneme-hq` install line does **not** trigger the rule, but a first
draft of this document that *quoted* the forbidden literal did (FAIL). Under a
required gate, any doc, ADR or test fixture that quotes the literal would be a
VIOLATION, and docs/ADRs routinely quote what they forbid. How often real Core
PRs do this is unmeasured (§7 S3).

## 4. The nine CI1 conditions, classified

Classes: **B** = hard blocker, must be resolved before the gate is required;
**R** = bounded residual risk, acceptable by an explicit owner ruling;
**E** = needs new evidence, gathered in the rollout itself before the
required-check switch.

| # | Condition | After C4 | Class | What closes it for R0 |
|---|---|---|---|---|
| 1 | Gate weakening | PR-level weakening refused (trusted-surface REFUSED, L4). Administrative P7/P8 exposure remains | **R** | owner accepts admin trust as residual, bound to the §5 route and an inventory of who holds admin rights (including agent tokens) |
| 2 | Merge freshness | Option A validated in the lab; Core has strict up-to-date **off** | **B** | strict up-to-date on in the same ruleset change that makes the gate required |
| 3 | UNEVALUATED policy | ADR-033 accepted; C4 implements the CI distinction | closed for CI | owner picks Core's starting posture (§6 R3) |
| 4 | Malformed-memory CLI | unchanged: exit 1, traceback, empty stdout; C4 classes it UNEVALUATED (O5) | **R** | accept the crash path for R0: under `closed` it blocks, under `open` it passes with a warning |
| 5 | ADR-029 binding | partial; C4 did not claim "relevant enforcement observed" | **R** | R0 claims a merge gate, not ADR-029 relevant enforcement; record that the claim stays at "execution observed, near-complete binding" |
| 6 | Governed `.mneme/` changes | no route; gate refuses `.mneme/` under every posture | **B** | §5 decision, implemented with the rollout |
| 7 | GitHub after 2026-11-02 | never observed | **E** | shadow-phase runs on Core on or after 2026-11-02 (§7 S3) |
| 8 | Production-shaped coverage | one literal rule, lab ruleset | **E** | shadow-phase results on representative Core PRs, including how often ADR-005 fires on documents that quote the forbidden literal |
| 9 | Separate authorization | not started | process | this charter, then a `[layer1-freeze]` amendment |

Conditions 1 and 5 stay separate: admin controls decide whether the gate can be
weakened; ADR-029 decides whether its evidence is attributable. Fixing one does
not fix the other.

## 5. First decision: governed decision update, bootstrap and recovery

A gate that protects `.mneme/` and `.github/` refuses (a) every legitimate
decision update, (b) its own later fixes, and, once required, (c) any change
to its own workflow. The lab handled its bootstrap with a recorded ruleset
disable; that turns every check off for the window and is not a production
route.

All of these are the same operation: **an authorized human merges one reviewed
PR whose required gate check is not green.** R0 uses one route for all of them.

| Option | Mechanism | Assessment |
|---|---|---|
| **A (accepted as design direction, §6 R2)** | A ruleset bypass actor that is one designated human authority, `bypass_mode: pull_request`. The gate stays required for everyone else | Native GitHub, no new code, no window where checks are off. Residual is exactly P7/P8 (condition 1) |
| B | Disable and re-enable the ruleset per change (lab method) | All required checks off during the window; easy to forget to re-enable; no per-PR audit link |
| C | Trusted decision-update workflow (label or signed approval read by the gate) | New trust surface and code; needs DG1 decision-update semantics (ADR-030/031). Out of R0 scope; a later replacement for A |

### 5.1 Scope of GitHub bypass authority (clarification 1)

GitHub bypass is **ruleset-wide, not check-specific.** A bypass actor on a
ruleset can merge past *every* rule in that ruleset: every required check (for
any verdict, including pending, failed, VIOLATION and UNEVALUATED, not only
REFUSED), the up-to-date requirement, and the PR rules. GitHub does not know
which Mneme verdict justified a bypass, and does not limit bypass to `.mneme/`
or `.github/` changes.

To keep that authority as narrow as GitHub allows:

- **Dedicated gate ruleset.** The Mneme gate's required check and the strict
  up-to-date requirement live in their own ruleset targeting `main`. Only that
  ruleset has a bypass list. `main-pr-only` keeps no bypass actors, so its
  required checks (PR battery, encoding, provenance, install command) and
  squash-only rule still apply to a bypassed merge. Rules from both rulesets
  aggregate; this layering must be confirmed on Core in S4 before it is
  relied on.
- **One designated human authority.** The bypass actor is a named human
  account (the owner), not a team, app or role that grows over time.
- **No agent-accessible credentials.** No token that agent sessions, CI or
  automation can use may carry that account's bypass ability. S2 records the
  credential inventory: which tokens exist for that account, where they are
  stored, and confirmation that none is configured in agent environments
  (`gh` auth, `GH_TOKEN`/`GITHUB_TOKEN` exports, MCP servers, repository or
  organization secrets). If the owner's day-to-day `gh` login is also the
  agent's login, that is a finding to resolve before S2 completes, by moving
  agents to a separate non-bypass identity.
- `bypass_mode: pull_request` only, never `always`; direct pushes to `main`
  stay blocked (ruleset and the ADR-022 pre-push guard).

### 5.2 Per-bypass record (clarification 2)

**GitHub enforces none of this; it is procedure.** GitHub logs that a bypass
happened (rule insights / audit log) but does not require a reason, an
approval, or a link to the check run. Every bypassed PR must carry, before
merge, in its PR body (and the squash commit body):

| Field | Content |
|---|---|
| Human approval | the designated authority's approval text and date |
| Protected paths | every changed path under `.mneme/`, `.github/` or the trusted adapter surface |
| Bypass reason | one of: decision update, gate fix, gate install/config, availability incident, other (explained) |
| Check-run identity | gate check-run id, head SHA, verdict and reason class (REFUSED / VIOLATION / UNEVALUATED / missing) |

After merge, the bypass is cross-checked against GitHub's rule-insights entry
for that merge and noted on #540. A bypass without the record is an incident,
not a recovery. A later stage may add an automated post-merge audit; R0 does
not assume one.

### 5.3 Bootstrap order (clarification 3)

The bypass actor exists before the protected workflow is installed:

1. Designate the authority and complete the credential inventory (§5.1).
2. Create the dedicated gate ruleset with that bypass actor and **no required
   check yet**. Whether GitHub accepts the ruleset in that shape, or it must
   be created disabled, is settled in S2.
3. Install the gate workflow by a normal reviewed PR. Note: under
   `pull_request_target` GitHub runs the workflow from the **base** branch, so
   the installing PR itself gets no gate run, and nothing yet requires one.
   The first gate runs are on PRs opened after the install merges.
4. Shadow runs, then recovery validation (§7 S3-S4), then the switch.

### 5.4 Rollback is two different controls (clarification 4)

| | Availability rollback | Required-check removal |
|---|---|---|
| Action | set `MNEME_CI_AVAILABILITY=open` | remove the gate from the gate ruleset's required checks (or disable that ruleset) |
| For | runner, evaluator install or memory-read **unavailability** | a **gate defect**: wrong VIOLATION/REFUSED, a check that never reports, a broken pin |
| Gate still required | yes | no |
| UNEVALUATED | passes with a warning | irrelevant (nothing required) |
| VIOLATION / REFUSED | **still block** | no longer block; every PR mergeable on the other rulesets alone |
| Missing check (job never reports) | still blocks: posture is read by the job | no longer blocks |
| Existing check results | unchanged until re-run; a head red under `closed` stays red until re-run (C4 §7) | irrelevant |
| Restore | set back to `closed`, re-run affected checks | re-add by a reviewed PR record and ruleset change |
| Exposure | narrow: only operational failures pass | wide: Mneme enforcement fully off on `main` |

Both are pre-authorized as emergency actions for the designated authority,
each recorded on #540 the same day with the trigger, start and end time and
PRs merged in the window. Neither is authorized by this charter. A single PR
that must merge past a correct refusal uses the §5.2 bypass, not either
rollback.

Recovery must be shown to work **before** promotion (§7 S4); no rollback path
is first exercised in an incident.

## 6. Owner rulings

| ID | Ruling | Status |
|---|---|---|
| R1 | Adopt the §2 boundary | **Accepted (owner, 2026-10-26):** single-repository boundary |
| R2 | Bootstrap, decision updates and recovery use §5 Option A | **Accepted as R0 design direction (owner, 2026-10-26)**, subject to clarifications 1-4 (§§5.1-5.4) and recovery validation before activation (§7 S4). Not an approval of implementation, activation or any bypass operation |
| R3 | Starting posture | **Accepted (owner, 2026-10-26):** `closed` (unavailable evaluation blocks; availability rollback to `open` per §5.4) |
| R4 | Accept conditions 1, 4 and 5 as bounded residuals (§4) | **Accepted (owner, 2026-10-26):** for bounded rollout validation only; no ADR-029 evidence-claim upgrade |
| R5 | Keep `mneme-check.yml` as an advisory comment but drop `mneme check --mode warn` from the required checks when the gate becomes required | **Accepted (owner, 2026-10-26):** the warn check stops being required when the gate becomes required (S5), not before |

Owner wording (2026-10-26, Mneme Core conversation, recorded on the owner's
behalf):

- R2: "This approves Option A as the R0 design direction, not its
  implementation, activation or any future bypass operation."
- R1, R3-R5: "accept R1 (single repo boundary), R3 (closed), R4 (residuals for
  bounded rollout validation, no ADR-029 upgrade), R5 (drop warn check from
  required when the gate becomes required)."

These rulings authorize no stage in §7. Production promotion stays DEFERRED.

## 7. Stages after this charter

Each stage needs its own owner authorization; none is authorized here. The
production switch (S5) is conditional on S4 passing and on a clean S4→S5
configuration equivalence check.

| Stage | Content | Exit evidence |
|---|---|---|
| S1 | `[layer1-freeze]` amendment covering the gate workflow install, the dedicated gate ruleset and bypass actor, required-check and strict up-to-date changes, and the staging branch in S4 | merged amendment |
| S2 authority | §5.3 steps 1-2: designate the authority, credential inventory, create the gate ruleset with its bypass actor | inventory record; ruleset snapshot |
| S3 shadow | §5.3 step 3: install the workflow by a reviewed PR, **not required**, posture `closed`; run on representative Core PRs on or after 2026-11-02 | per run: check identity, verdict, report; ADR-005 hits split into real violations and quotations; any `pull_request_target` platform difference; zero unexplained UNEVALUATED |
| S4 recovery validation (pre-promotion) | on a Core staging branch (for example `r0/recovery-staging`, cut from `main` after S3) targeted by a copy of the gate ruleset with the same bypass actor and strict up-to-date, the gate **required**: (a) a `.mneme/` change is REFUSED and blocked, then merged through a §5.2 bypass by the designated authority; (b) the bypass leaves `main-pr-only`-equivalent checks enforced; (c) posture flip to `open` with an UNEVALUATED case passing with a warning while a REFUSED case still blocks, then back to `closed` with re-run; (d) required-check removal and restore; (e) a non-authority account cannot bypass | per case: check run, merge response (200/405), rule-insights entry, §5.2 record; ruleset before/after snapshots. **S5 is not authorized unless every S4 case is as expected** |
| S4→S5 configuration equivalence | read-only, **immediately before S5**: compare the S4 staging configuration with production as it will be after S5. That means every active ruleset targeting `main` and the staging branch (rules, required-check contexts and app ids, strict up-to-date, bypass actors and modes, enforcement status, merge methods), the gate workflow blob on each branch, the `MNEME_CI_AVAILABILITY` value, and the Actions permissions. S4 proves the recovery mechanism on staging; it does not by itself prove the production rulesets interact the same way | a diff record of both snapshots. **Any difference that affects merge authorization blocks S5 until reviewed and accepted by the owner** |
| S5 switch | one change to the `main` gate ruleset: gate required, strict up-to-date on; drop the warn check from `main-pr-only` (R5); posture `closed` | ruleset before/after snapshots |
| S6 post-switch check | a compliant PR merges; the first real `.mneme/` change goes through a §5.2 bypass. A literal-rule VIOLATION is shown offline or in shadow, never by merging a violating change to `main` | per-case check run and merge response |
| S7 record | R0 results record; production promotion decision | merged record |

If S4 cannot run on a staging branch (for example, ruleset layering differs
from §5.1), the switch stays blocked until equivalent pre-promotion evidence
exists. No recovery path is first validated on production `main`.

## 8. Non-goals

No evaluator or adapter change, no new rule types, no multi-repository rollout,
no reopening of C4 or the CI1 lab, no DG1 decision-change semantics, no change
to the CLI malformed-memory contract, no ADR-029 upgrade.

## 9. Preliminary decision

**Production promotion: DEFER.** Not a C4 failure: production authorization has
not been justified yet. The blockers are conditions 2 and 6. Option A is the
accepted design direction for condition 6 and recovery (§6 R2); the switch
also depends on recovery validated before activation (§7 S4).
