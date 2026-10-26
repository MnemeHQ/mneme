# CI production rollout R0: readiness charter (Mneme Core)

**Status: PROPOSED.** Read-only charter. Merging it records the owner's rulings
in §6 and nothing else. **It authorizes no workflow, ruleset, required-check,
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
PRs do this is unmeasured (§7 S2).

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
| 7 | GitHub after 2026-11-02 | never observed | **E** | shadow-phase runs on Core on or after 2026-11-02 (§7 S2) |
| 8 | Production-shaped coverage | one literal rule, lab ruleset | **E** | shadow-phase results on representative Core PRs, including how often ADR-005 fires on documents that quote the forbidden literal |
| 9 | Separate authorization | not started | process | this charter, then a `[layer1-freeze]` amendment |

Conditions 1 and 5 stay separate: admin controls decide whether the gate can be
weakened; ADR-029 decides whether its evidence is attributable. Fixing one does
not fix the other.

## 5. First decision: governed decision update, bootstrap and recovery

A gate that protects `.mneme/` and `.github/` refuses (a) its own installation
PR, (b) every legitimate decision update, (c) its own later fixes. The lab
solved (a) with a recorded ruleset disable; that leaves every check off for the
window and is not a production route.

All three are the same operation: **an authorized human merges one reviewed PR
whose required gate check is REFUSED.** R0 should use one route for all three.

| Option | Mechanism | Assessment |
|---|---|---|
| **A (recommended)** | Add one ruleset bypass actor (the repository admin role, or a named owner account), `bypass_mode: pull_request`. The gate stays required for everyone else. Each bypass merge is a squash of a reviewed PR whose body records the REFUSED check run, the reason, and the owner's approval | Native GitHub, no new code, no window where checks are off, auditable from the PR and check run. Residual is exactly P7/P8 (an admin can bypass), which condition 1 already carries |
| B | Disable and re-enable the ruleset per change (lab method) | All required checks off during the window; easy to forget to re-enable; no per-PR audit link |
| C | Trusted decision-update workflow (label or signed approval read by the gate) | New trust surface and code; needs DG1 decision-update semantics (ADR-030/031). Out of R0 scope; a later replacement for A |

**Recommendation: A**, with these bindings:

- `bypass_mode: pull_request` only, never `always`; direct pushes to `main`
  stay blocked (ruleset and the ADR-022 pre-push guard).
- The bypass actor is a human role. Agent sessions must not hold a token that
  can use it; R0 records the current token inventory as part of condition 1.
- Each bypass merge carries in its PR body: the REFUSED check run id, the
  changed protected paths, and the owner's approval text.
- **Rollback (pre-authorized):** set `MNEME_CI_AVAILABILITY=open` for runner or
  evaluator unavailability; remove the gate from the ruleset's required checks
  for a gate defect. Either is recorded on #540 within the same day, and the
  gate is restored only through a reviewed PR.

Option A does not create a DG1 decision-change semantics; it is an
administrative route under P7/P8. That boundary is recorded, not hidden.

## 6. Owner rulings requested on merge

| ID | Ruling | Recommendation |
|---|---|---|
| R1 | Adopt the §2 boundary | yes |
| R2 | Bootstrap, decision updates and recovery use §5 Option A | yes |
| R3 | Starting posture | `closed`: an unavailable evaluation blocks; rollback to `open` is pre-authorized |
| R4 | Accept conditions 1, 4 and 5 as bounded residuals (§4) | yes |
| R5 | Keep `mneme-check.yml` as an advisory comment but drop `mneme check --mode warn` from the required checks when the gate becomes required | yes; two checks with different trust models must not both look like the governance gate |

## 7. Stages after this charter

Each stage needs its own owner authorization; none is authorized here.

| Stage | Content | Exit evidence |
|---|---|---|
| S1 | `[layer1-freeze]` amendment covering `.github/workflows/` gate install, ruleset bypass, required-check and strict up-to-date changes | merged amendment |
| S2 shadow | install the gate workflow (via the §5 bypass, which is its first real use), **not required**; posture `closed`; run on representative Core PRs, on or after 2026-11-02 | for each run: check identity, verdict, report; ADR-005 hits split into real violations and quotations; any `pull_request_target` platform difference; zero unexplained UNEVALUATED |
| S3 switch | one ruleset change: add the gate as required, strict up-to-date on, drop the warn check (R5) | ruleset before/after snapshot |
| S4 controlled cases | on Core: compliant PR merges; a `.mneme/` change is REFUSED then merged via bypass; posture flip to `open` and back is recorded. A literal-rule VIOLATION is shown offline or in shadow, not by merging a violating change | per-case check run and merge response |
| S5 record | R0 results record; production promotion decision | merged record |

## 8. Non-goals

No evaluator or adapter change, no new rule types, no multi-repository rollout,
no reopening of C4 or the CI1 lab, no DG1 decision-change semantics, no change
to the CLI malformed-memory contract, no ADR-029 upgrade.

## 9. Preliminary decision

**Production promotion: DEFER.** Not a C4 failure: production authorization has
not been justified yet. The blockers are conditions 2 and 6; the first decision
is §5.
