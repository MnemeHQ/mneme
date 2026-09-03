# Main PR-Only Enforcement — 2026-08-25

P0.5 repository hardening. A direct push to `main` occurred during dogfooding despite the prose rule in CLAUDE.md ("squash merge only", worktree lifecycle). This plan finishes the enforcement loop at the correct execution boundaries without becoming a broad workflow-policy workstream.

**Classification:** P0.5 — finish before the next substantial integration workstream. Core effort ≈ half a day; ~1 day with careful tests/docs.

---

## Validated context (do not re-derive)

- Guard architecture lives in `scripts/check_worktree_context.py` (#311) + `scripts/new_task_worktree.py` and versioned hook `scripts/githooks/pre-commit` (#312), installed once via `git config core.hooksPath scripts/githooks`. The same directory serves `pre-push` automatically — **no new guard mechanism**.
- `pre-commit` skips worktrees without `.mneme/task_context.json` (e.g., the administrative checkout). The pre-push rule must **not** inherit that skip: its condition is the *push destination*, not the local worktree identity.
- ADR-010 already establishes the squash-merge taxonomy invariant; the new ADR layers the *enforcement boundary* decision on top of it, it does not replace it.
- Squash merges performed through the GitHub UI never invoke local git hooks, so blocking every local push to `main` cannot break the accepted workflow.

---

## Scope

| Step | Change | Effort | Now |
|---|---|---|---|
| 1 | GitHub ruleset: block direct pushes to `main`, require PR; enable squash as the only allowed merge method | ~15–30 min | Yes |
| 2 | ADR-022: PR + squash-only invariant and enforcement boundaries | ~30–60 min | Yes |
| 3 | `scripts/githooks/pre-push`: block any push whose remote destination is `refs/heads/main` | ~2–4 hrs incl. tests | Yes |
| 4 | Focused adversarial tests | ~1–2 hrs | Yes |
| 5 | CI provenance/audit check for commits reaching `main` outside PR flow | ~1–2 hrs | **Defer** — revisit only if ruleset audit evidence proves insufficient |

---

## Sequence

### 0. Provision the task worktree

```bash
python scripts/new_task_worktree.py ci/main-pr-only-guard
```

All development happens in that worktree; this administrative checkout stays untouched.

### 1. Lock the authoritative boundary (GitHub)

Configure on github.com before any code lands, so the fix protects even this change's own merge:

- Ruleset on branch `main` (Rules → Rulesets, preferred over legacy branch protection):
  - Restrict creation / deletion / updates of matching branches → blocks direct pushes and force-pushes.
  - Require a pull request before merging.
- Repo settings → Pull Requests: allow **squash merging only** (disable merge commits and rebase merging).

Record the settings screenshot/location in the ADR so future maintainers don't have to rediscover whether squash-only lives in the ruleset or repo settings.

### 2. Record the decision (ADR-022)

File: `docs/adr/ADR-022-main-is-pr-and-squash-only.md`

Responsibility separation (the core content):

- **GitHub ruleset = authoritative remote enforcement.** Nothing on `main` arrives except via a PR that squash-merges.
- **Mneme local guard = early deterministic feedback.** Catches the violation at the developer's terminal with an actionable message; not authoritative, can be overridden explicitly.
- **CI = audit/recovery only** (deferred, step 5). Not primary enforcement.

The ADR must state the precise rule being enforced locally and the explicit administrative override, so the bypass is documented rather than discovered. Reference ADR-010 for naming/squash conventions; reference the dogfooding incident as motivation.

### 3. Implement the smallest local rule

New file: `scripts/githooks/pre-push`

Condition — exactly this, nothing broader:

> Reject any push whose destination is protected `main`, regardless of local branch identity or whether the remote ref already exists.

Implementation notes:

- Read stdin lines of the form `<local-ref> <local-sha> <remote-ref> <remote-sha>`.
- Block whenever `remote-ref` is `refs/heads/main`; this covers creation, normal update, force-push, and deletion.
- **Do NOT implement** "you may never commit while checked out on main." Local commits on `main` in the administrative checkout are legitimate; only the *push* is gated.
- No skip via absence of `.mneme/task_context.json` — the rule keys on destination ref, so it applies uniformly in every worktree including the administrative checkout.
- Failure message must identify the governing decision and remediation, e.g.:

  ```
  [push-guard] BLOCKED: direct push to main.
    Governing decision: ADR-022 (main is PR + squash-only; GitHub ruleset is authoritative).
    Fix: commit to a task branch and open a PR (python scripts/new_task_worktree.py <branch>).
    Administrative/recovery override: MNEME_ALLOW_MAIN_PUSH=1 (use deliberately, never routinely).
  ```

- Override: environment variable `MNEME_ALLOW_MAIN_PUSH=1`. This satisfies "explicit administrative/recovery behavior defined" and "no bypass that silently becomes the default path" — it requires deliberate action on every invocation and prints nothing quietly.

CLAUDE.md: add one sentence under the existing Agent Execution Context Guard section noting the pre-push gate installs together with `core.hooksPath scripts/githooks` (no separate setup step).

### 4. Prove it adversarially

New file: `tests/test_pre_push_main_guard.py`, following the real-git-repos-in-`tmp_path` style of `tests/test_check_worktree_context.py`.

Minimum cases:

| Case | Expected |
|---|---|
| feature branch → remote feature branch | PASS |
| local `main` → `origin/main` (fast-forward) | BLOCK |
| local `main` → `origin/main` (force/non-fast-forward) | BLOCK |
| create remote `main` (remote ref absent) | BLOCK |
| delete remote `main` (`:main`) | BLOCK |
| normal PR/squash simulation (feature push, then simulated server-side squash) | PASS |
| `MNEME_ALLOW_MAIN_PUSH=1` on direct main push | PASS with visible override notice |
| dirty worktree present | irrelevant — rule unaffected (documented as non-applicable) |
| failure message content | names ADR-022 + remediation |

Also assert the hook reads stdin correctly when invoked exactly as git invokes it (args: remote name, remote URL; multiple ref lines on stdin).

Gates before merge:

```bash
python -m pytest tests/test_pre_push_main_guard.py tests/test_check_worktree_context.py
python -m pytest tests/            # full suite
mneme check --mode warn
```

Plus live E2E in the sandbox: attempt a scripted direct push to a throwaway protected ref, verify block; verify feature-branch push passes.

### 5. Deferred: CI provenance/audit check

Out of scope now. Revisit trigger: if the ruleset's audit log doesn't provide the evidence wanted for "how did this commit reach main," add a CI check that verifies every `main` commit is a squash merge with a PR reference. Track as a follow-up issue, not in this PR.

---

## PR shape

One PR: `ci/main-pr-only-guard` → contains ADR-022, `scripts/githooks/pre-push`, `tests/test_pre_push_main_guard.py`, CLAUDE.md sentence, plan doc. Branch name follows taxonomy; squash commit title: `ci: enforce PR + squash-only on main (ruleset + pre-push guard)`.

Ordering within the PR: step 1 (GitHub settings) is done outside the PR but first, so the PR itself must arrive via PR — immediate self-test of the invariant.

## Explicitly out of scope

- Any general "workflow policy engine."
- Blocking commits on local `main`.
- CI provenance checks (step 5).
- Changes to `.mneme/project_memory.json` (not a `[memory]` task).
