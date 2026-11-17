# CI rollout R0 S2: dedicated gate ruleset created, disabled (2026-11-02)

**Status: RECORD (metadata only).** Records one executed S2 action and its
read-only verification. **It authorizes no later stage.** No Mneme check is
required, no workflow, variable, Actions setting, adapter, evaluator or
existing ruleset changed, and no enforcement is active. Production promotion
stays **DEFERRED**.
**Governing documents:** [R0 charter](../plans/2026-10-26-ci-r0-production-rollout-readiness-charter.md)
§5.1, §5.3 and §7 S2 (#684 `e6c80c07`; owner ruling R6, #718 `f4258751`) and the
[Layer 1 freeze](../architecture/layer1-freeze-e73ff7d.md) R0 amendment, S2 row
(#685 `6c320902`).

## 1. Authorization

Owner instruction (2026-11-02, Mneme Core conversation, recorded on the
owner's behalf): the S2 authorization is limited to creating `mneme-ci-gate`
with no rules and disabled enforcement; configuring exactly one human bypass
actor, `TheoV823`, in `pull_request` mode; capturing before and after
evidence; and making no change to existing rulesets or CI. No S3-S5
activation is authorized. If the GitHub API rejects the shape, stop rather
than substitute a different configuration.

## 2. What was done

One `POST /repos/MnemeHQ/mneme/rulesets` with the body in
[`gate-ruleset-spec.json`](ci-r0-s2-gate-ruleset-2026-11-02/gate-ruleset-spec.json)
(SHA-256 `4085cf0d…`), run by the owner's local administrator `gh` login
(`TheoV823`) at 2026-11-02 19:15:57 GMT. GitHub answered **201 Created**
(request id `D635:2F5CEB:B85CB:254C8F:6AE8E16C`).

| Field | Value |
|---|---|
| id / name | `26391853` / `mneme-ci-gate` |
| target / ref | branch / `refs/heads/main` |
| enforcement | `disabled` |
| rules | none |
| bypass actors | exactly one: `User` id `54006786` (`TheoV823`), `bypass_mode: pull_request` |

The spec was compared with the intended configuration before the call
(identical) and the resulting ruleset was compared with the spec after it
(identical on name, target, enforcement, conditions, bypass actors and rules).

## 3. Verification (read-only)

Before and after snapshots are in
[`ci-r0-s2-gate-ruleset-2026-11-02/`](ci-r0-s2-gate-ruleset-2026-11-02/)
with `EVIDENCE-SHA256SUMS`.

| Check | Result |
|---|---|
| Rulesets on the repository | before: `main-pr-only` (22196895); after: `main-pr-only` (active) and `mneme-ci-gate` (disabled) |
| `main-pr-only` | byte-identical JSON before and after (`fadc3443…`); `updated_at` unchanged `2026-09-12`; no bypass actors; same five required contexts |
| Effective rules on `main` | identical before and after (`a4d21f9f…`): `pull_request`, `deletion`, `non_fast_forward`, `required_status_checks`, all from `main-pr-only` |
| Repository variables | 0, unchanged |
| Actions permissions | unchanged (`enabled`, `allowed_actions: all`, SHA pinning not required) |
| Workflows, adapter, evaluator, `.mneme/` | not touched |
| `mneme-agent` | collaborator, role `write`; not in any bypass list; `main-pr-only` still `current_user_can_bypass: never` |

## 4. Findings

- **GitHub accepts this shape.** An empty `rules` array, a `User` bypass actor
  and `bypass_mode: pull_request` on a repository ruleset were all accepted.
  This settles the open question in charter §5.3 step 2.
- **Disabled ruleset, no effect.** With `enforcement: disabled` and no rules the
  ruleset changes no merge decision. The reported
  `current_user_can_bypass: pull_requests_only` for the administrator login is
  recorded, not relied on; bypass behavior is tested on the active staging copy
  in S4.
- **Required before S5.** S1's S5 row lists adding the required check and strict
  up-to-date in this ruleset but not switching it from `disabled` to `active`.
  That activation needs to be covered by a `[layer1-freeze]` clarification
  before the S5 authorization. It does not block S2.

## 5. Limits and non-claims

- Nothing in this record shows the gate blocks, refuses or recovers anything;
  those are S3-S5 questions.
- **R6 applies.** The creating login is administrator-capable and agent-reachable
  in the existing dogfooding environment, an accepted bounded P7/P8 residual.
  This is not a claim of administrator-resistant enforcement, and no ADR-029
  evidence claim is made.
- The credential inventory was completed on 2026-11-02 and is **kept private**
  by design (charter §5.1). Its conclusion: the non-admin validation identity
  `mneme-agent` holds no bypass authority and the R6 residual is recorded.
- The bypass authority has not been exercised. The per-bypass record procedure
  (charter §5.2) is unchanged.

## 6. Rollback

`DELETE /repos/MnemeHQ/mneme/rulesets/26391853`. The ruleset is disabled and
has no rules, so removal changes no behavior.

## 7. S2 closure and next stage

On merge of this record with the owner's acceptance, S2 closes as: the
dedicated gate ruleset exists, disabled, with one human bypass actor, and the
credential inventory is complete under R6. The next stage, S3 (install the
pinned workflow, not required; shadow runs on or after 2026-11-02), needs its
own owner authorization.
