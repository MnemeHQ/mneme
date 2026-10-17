# D6-Q1 — Opus review reconciliation and D5 boundary gate

**Date:** 2026-10-17  
**Status:** Q1 review corrections reconciled; **D5 repository boundary OPEN; Q2 BLOCKED**.  
**Source anchor:** `MnemeHQ/mneme` at `45cefa63`, read-only; accepted T-08 charter §§2–8, ADR-020, G3-B. Opus's **REVISE** findings come from the 2026-10-17 Opus validation, an unpublished working document. This note records the corrections accepted from it. **Status:** reconciliation record; it amends no ADR, charter, freeze or evidence.

## Accepted Q1 anchor

T-08 charter §2 already accepts the long-run invariant: **the repository being modified, located from the resolved write target, determines the governing memory—not the session `cwd`.** The charter accepts this as **direction, not as delivered behavior**: slice 1 implements only target-anchored memory discovery for direct writes with `MNEME_MEMORY` unset; V6, V4/V5 and the Bash, SessionStart and Stop boundaries are unchanged. It preserves nearest-memory lookup, parent fallback and `MNEME_MEMORY` precedence. Therefore **Q1 now concerns defining the repository boundary (D5)**, not choosing `cwd` versus target as the locator.

ADR-020's `policy_root(memory)` depends on the memory already selected; it does not independently identify the repository or establish verified authority.

## Corrections to the preliminary review

1. **Raw relative-path materialization** was already excluded by T-08 §3 and the V11 test docstring. `Edit`, `Write` and `MultiEdit` use the raw `file_path` to materialize proposed content. Potential checked-byte/fail-open effects are **adapter concerns**, not evidence that a different memory is selected.
2. **Repeated path resolution is not an established defect.** The hook passes the same target-path string to `mneme check` that it resolves for the memory walk; both call `Path.resolve()`. The string is absolute whenever payload `cwd` is set or `file_path` is absolute; for a relative target with empty `cwd`, the `mneme check` subprocess inherits the hook's working directory (`hook.py:569-576`), so resolution still agrees. Symlink mutation between check and actual write remains untested **adapter/TOCTOU** territory.
3. **Symlink evidence was overstated.** Both tests skip if link creation fails. Their recorded Windows PASS/SKIP outcomes are unknown; no live symlink probe was conducted.
4. **The target locator is already accepted** by charter §2. The unsolved architectural decision is where the repository/project ends, not which operation supplies the target location.

5. **Minor citation corrections.** `40ab0dd1` is a commit, not a tree: C4 ran from `f64d0900` with `mneme/` byte-identical to commit `40ab0dd1`. The Bash handler calls `find_memory` *after* heredoc target reconstruction, but the walk starts at the session `cwd`, not the reconstructed target (`hook.py:700-716`). The LIVE source for the slice-1 protected case is `docs/validation/dg1f-t08-slice1-live-reprobe-2026-10-15.md`; C1–C4 R0 controls ran on the `40ab0dd1` pin and are corroboration only.

**Adapter items (out of D6).** Corrections 1 and 2 leave two Claude Code adapter concerns: relative-path content materialization and symlink TOCTOU between check and write. They are not yet tracked anywhere; they need a separate adapter-validation issue before this note is treated as closing them out of D6.

These corrections supersede corresponding assertions in the 2026-10-16 preliminary review; they do not amend T-08 or the C1–C4 evidence.

## Remaining architectural gate: D5

Define a compatible repository/project boundary for **ordinary Git checkouts, non-Git projects, linked worktrees, nested repositories/submodules, and task worktrees inside another checkout** (`.claude/worktrees/`). A mandatory `.git`-directory requirement is **not accepted**. Explicitly decide whether and when the existing parent-directory memory fallback crosses the boundary.

**D4** nested-memory policy requires the same root definition but remains a separate decision. **G3-B** can bind independently verified authorization to a root and effective memory path only after D5 defines that root. **D3** out-of-root outcomes and **D6/Q2** external-memory precedence remain separately gated, with one dependency: D3 is still reachable through D6 (charter §8, D3 row), so a D6 precedence decision changes where D3 can occur.

**Gate:** Q1's review corrections are reconciled, but **Q1/D5 is not accepted until a compatibility-reviewed boundary definition is approved. Do not open Q2 before then.** C4 stays closed; C5/C6, implementation, new experiments, ADR/freeze amendments, cleanup, and changes to raw evidence, pins or worktrees remain unauthorized. This note is docs-only and does not choose a root algorithm.

**Sources:** [T-08 charter](2026-10-15-t08-target-path-memory-resolution-charter.md) · [hook](https://github.com/MnemeHQ/mneme/blob/45cefa63/mneme/integrations/claude_code/hook.py) · [tests](https://github.com/MnemeHQ/mneme/blob/45cefa63/tests/integrations/claude_code/test_hook_target_memory_resolution.py) · [path selectors](https://github.com/MnemeHQ/mneme/blob/45cefa63/mneme/path_selectors.py) · [ADR-020](https://github.com/MnemeHQ/mneme/blob/45cefa63/docs/adr/ADR-020-explicit-path-applicability-for-typed-rules.md) · [G3-B](2026-10-14-dg1f-g3b-eligibility-authorization-design.md).

**Next:** the D5 boundary contract is [2026-10-17-dg1f-t08-d5-repository-boundary-contract.md](2026-10-17-dg1f-t08-d5-repository-boundary-contract.md) (PROPOSED).
