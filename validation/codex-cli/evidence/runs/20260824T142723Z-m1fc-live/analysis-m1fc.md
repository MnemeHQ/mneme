# M1f-c analysis — bundled apply_patch enforcement, live (run 20260824T142723Z)

Production hook (trusted-only, no bypass), pinned 0.149.1 (SHA re-verified),
scoped FORBID_LITERAL rule, one bundled call per case: Update `service.py` +
Add `helper.py`.

## Three cases

| Case | Bundle content | Outcome |
|---|---|---|
| 1 | compliant Update + compliant Add | **both land** (`M service.py`, `? helper.py`); `PreToolUse Completed`, silent PASS |
| 2 | violating Update + compliant Add | **neither lands**; denied with `[operation 1 (service.py)] mneme: FAIL ... [ADR-BUNDLE] FAIL "FORBIDDEN_TOKEN_XYZ"` |
| 3 | compliant Update + violating Add | **neither lands**; denied with `[operation 2 (helper.py)] mneme: FAIL ... [ADR-BUNDLE] FAIL "FORBIDDEN_TOKEN_XYZ"` |

The denial reasons identify the exact violating operation and path in both
positions — there is no "only the first operation is checked" hole and no
"only one operation blocked" partial application.

## Checklist

- One bundled `apply_patch` -> one aggregate decision: YES, all three arms.
- PostToolUse: production config registers PreToolUse only (M1d-b scope
  decision), so PostToolUse lines cannot appear; absence is uniform across
  all three cases ("only for the fully compliant call" holds vacuously and
  is consistent with registered-hook probes R0/M1e-a/M1f-a where exactly one
  PostToolUse followed each allowed patch).
- Denied bundles leave the worktree unchanged: YES (both deny cases clean).
- Denial reason identifies violating operation/path: YES, both positions.
- Unevaluated-operation disclosure: covered by unit tests
  (`test_deny_plus_unevaluated_discloses_the_unevaluated_operation`);
  not reachable live here because both operations were readable/valid by
  construction.
- Pin re-verified; trusted-only; no bypass: YES.

## Harness defect found during validation

First attempt invalidated (`_invalidated/20260824T142537Z-m1fc-live`): the
runner's case definitions omitted the `*** Update File:` header line from
the embedded patch bodies, so Codex received a grammatically invalid patch
and rejected it itself. Fixed in the probe only.

## Verdict

> **M1f-c exit gate: MET** — a bundled native apply_patch is evaluated
> operation-by-operation, and any violation in either position denies the
> entire call on pinned Codex CLI 0.149.1 / Windows / `codex exec`.
