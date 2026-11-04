# CI rollout R0 S6: post-switch checks on `main` (2026-11-03)

**Status: RECORD (metadata only).** Records the two R0 S6 checks after the S5
switch: an ordinary compliant merge under the required gate, and the first
genuine `.mneme/` change merged through the designated human bypass. **Both
came out as specified.** The gate stays required, `MNEME_CI_AVAILABILITY` is
`closed`, and no ruleset changed. S7 (closure, trigger-line cleanup, the
production promotion decision) remains; promotion stays **DEFERRED**.
**Governing documents:** [R0 charter](../plans/2026-10-26-ci-r0-production-rollout-readiness-charter.md)
§5.2 and §7 S6; [S5 record](ci-r0-s5-activation-2026-11-03.md) (#737).

## 1. Ordinary compliant merge

The S5 record PR #737 (docs only) passed every required check including
`mneme trusted gate`, and merged as `b86e9fd4`. GitHub rule suite 4878942932:
actor `TheoV823`, result **`pass`** (no bypass used).
Evidence: `rule-suite-737-ordinary.json`.

## 2. First genuine `.mneme/` change through the recorded bypass

**Change:** #598, "feat(dogfood): register Mneme Claude Code hooks for repo
development": `.claude/settings.json` (new), `.gitignore`,
`.mneme/README.md`. A legitimate owner change opened 2026-10-22, not a test
artifact.

**Authorizations (owner, 2026-11-03, recorded on the owner's behalf, via
forwarded reviews):** first S6 preparation only ("update #598 against current
main, collect the actual REFUSED gate result, and prepare the §5.2 bypass
record. Stop before the bypass merge."), then the merge: "I approve the
recorded human-authority bypass of PR #598 at the reviewed head
`956fe3d2460044a4c2509387f33f426e65a1c29f`."

| Step | Result |
|---|---|
| Hook re-verification on current `main` + #598 (throwaway worktree) | Write introducing the ADR-005 literal exit 2 (ADR-005 FAIL); `mneme-hq` Write, plain Bash, `SessionStart`, `Stop` exit 0; no stray files |
| Branch update to `main` | head `956fe3d2`, 0 behind, still the same three files |
| Gate | run 41638485557, check run 125925621401: **REFUSED** (`policy`) for `.mneme/README.md`; `.claude/settings.json` and `.gitignore` `VERIFIED_PASS`; posture `closed`, strict; `base_sha` = `merge_base` = `b86e9fd4` (main tip); report SHA-256 `baafabcb840d674d60425ccb0652e5c90e04e4cad9ecba799d31a5724d5d9e1d` (kept private: it echoes the ADR-005 literal) |
| Other required checks | all pass (PR battery, mojibake/BOM, provenance, install command); merge state BLOCKED by the gate only |
| §5.2 record | in the PR body before merge: owner approval with date and head, protected path, reason, check-run identity |
| Pre-merge reconfirmation | head unchanged, 0 behind, checks unchanged after the body edit re-ran provenance, posture `closed`, gate ruleset active |
| Bypass merge by `TheoV823` | **200**, 2026-11-03 12:54:38Z, request `FBA7:250593:205AB1E:69E84AF:6AE9D98B`; squash `60bdfcc0` |
| GitHub rule suite 4879223848 | actor `TheoV823`, result **`bypass`**, `b86e9fd4` → `60bdfcc0`; every `main-pr-only` rule `pass`; `mneme-ci-gate` `required_status_checks` `fail` (the bypassed part) |

Evidence: [`ci-r0-s6-post-switch-2026-11-03/`](ci-r0-s6-post-switch-2026-11-03/)
(`merge-598-response.txt`, `rule-suite-598-bypass.json`,
`rule-suite-737-ordinary.json`, `EVIDENCE-SHA256SUMS`).

## 3. After-state

Both rulesets active and unchanged; effective rules on `main` unchanged;
posture `closed`. #598 is now in effect: Claude Code sessions in this
repository run the Mneme hook (`PreToolUse` on `Edit|Write|MultiEdit|Bash`,
`SessionStart`, `Stop`).

## 4. Limits and non-claims

- The bypass was performed by the owner's administrator-capable login, which
  agents can also reach in the dogfooding environment (R6). The per-bypass
  record is procedure; GitHub enforced only the bypass-actor rule.
- Interactive Claude Code sessions under the new tracked hooks are not yet
  independently observed; only the registered command was re-verified.
- Fork and first-time-contributor PRs remain unobserved.
- No ADR-029 "relevant enforcement observed" claim.

## 5. S6 status and next

On merge of this record with the owner's acceptance, S6 closes. S7 remains:
remove the four `r0/recovery-staging` trigger lines added by #731 (a reviewed
PR; it changes `.github/`, so it is itself REFUSED and needs a recorded
bypass), the final R0 evidence record, and the production promotion decision,
each with owner authorization.
