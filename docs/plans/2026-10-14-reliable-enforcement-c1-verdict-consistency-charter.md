# Reliable Enforcement C1 — Verdict-consistency defect-correction charter (proposed)

**Status:** PROPOSED — requires architecture review and the matching Layer 1
freeze authorization before any implementation merge. **Not** an implementation,
approval, ADR-033 authorization, or C1b authorization.
**Source anchor:** `MnemeHQ/mneme` `main` at
`da6dafbc0f648cb7f8913bcadd83e8a6d23d92dc` (DG1F blocking-semantics matrix,
PR #501).
**Governing contracts:** [ADR-021](../adr/ADR-021-shell-preflight-and-stop-session-delta.md)
(fail-open transport policy); [ADR-017](../adr/ADR-017-enforcement-scope-vs-retrieval-scope.md)
and [ADR-020](../adr/ADR-020-explicit-path-applicability-for-typed-rules.md)
(strict/warn enforcement and rule-path applicability);
[ADR-023](../adr/ADR-023-canonical-decision-index-and-runtime-projection-boundary.md),
[ADR-029](../adr/ADR-029-enforcement-evidence-binding-semantics.md),
[ADR-030](../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md),
[ADR-031](../adr/ADR-031-decision-governance-semantics.md) (canonical authority
and evidence); the [Layer 1 freeze](../architecture/layer1-freeze-e73ff7d.md).
**Kept separate:** the proposed ADR-033 and the reliable-enforcement C0 charter
in PR #483 (draft) are **not** part of this charter.

## 1. Problem (issue #260)

`parse_verdict` trusted any payload that parsed, had `schema ==
"mneme.check/v1"` and named PASS/WARN/FAIL. It ignored the requested `mode`,
the violation record shape, whether the verdict agreed with its violations, and
the process exit code. A contradictory result — for example PASS with exit 1 —
was treated as authoritative. This is a **defect in how verdict trust is
established**, not a change to enforcement policy.

## 2. Authorized change — exactly this

Only the correction implemented in **PR #484** (`fix/hook-verdict-consistency`,
#260): `hook.assess_verdict(stdout, returncode, requested_mode)` returns a
`VerdictAssessment` and trusts a payload **only** when the envelope, violation
records, aggregate, requested mode and exit code are mutually coherent (per
#484's documented rules). An incoherent result **fails open** (ADR-021) with a
diagnostic that never echoes proposed content; `parse_verdict` no longer raises
`TypeError` on an unhashable verdict. Every shipped consumer of `parse_verdict`
routes through `assess_verdict` with the mode it requested.

No other behavior is authorized by this charter.

## 3. Explicitly preserved (unchanged by C1)

1. **Fail-open policy (ADR-021).** Every untrusted, unparseable, incomplete or
   contradictory result still **fails open**; no fail-closed or
   availability-strict mode is introduced.
2. **strict/warn semantics (ADR-017, ADR-020).** Coherent strict/warn verdicts
   keep existing enforcement; rule-path applicability is unchanged.
3. **Canonical decision authority (ADR-023, ADR-030) and evidence identity
   (ADR-029, ADR-031).** Untouched; no authority or evidence semantics change.
4. **Retrieval, ConflictDetector, enforcer, rule matching.** Untouched.
5. **`mneme.check/v1` payload and CLI exit codes.** Untouched.
6. **Frozen benchmark fixtures and methodology.** Untouched.
7. **`.mneme/project_memory.json`.** Untouched.

## 4. Explicitly NOT authorized

- ADR-033 availability states or any availability policy; **#483 stays separate
  and proposed**.
- Missing-memory eligibility/witness changes (a #483 gate).
- Any fail-closed enforcement, new schema, CLI/MCP surface, or new engine.
- DG1F-C1b applicability exclusion; DG1B2 waivers.
- Any claim that a returned block is honoured by the host harness (the G1 gap
  in the merged blocking-semantics matrix).

## 5. Layer 1 freeze authorization required (sequence step 2)

Because C1 changes how invalid verdicts are handled at the enforcement
boundary, the Layer 1 freeze requires prior authorization. Before #484 may
merge, a matching `[layer1-freeze]` amendment must merge under the freeze
Amendment Procedure (rationale anchored to a charter already made elsewhere,
§3(b)), referencing this merged charter. That amendment authorizes **only** the
verdict-trust correction and must restate the preserved items in §3; it does not
authorize enforcement-scope or availability changes.

## 6. Required acceptance evidence

Before any implementation merge, the following must be demonstrated (reusing,
not duplicating, #484's tests):

- `tests/integrations/claude_code/test_hook_verdict_consistency.py` (30 tests)
  and the per-surface contradictory-result tests, plus the #260 case verbatim;
- `tests/integrations/check_contract.py` pinned against the real CLI shape;
- the hook exit-code table equals `mneme.cli._EXIT_CODES_BY_MODE`;
- full canonical suite and gate battery green;
- the frozen benchmark unchanged (7/7 scenarios, Layer 2 pass rate 100%);
- no change to retrieval/enforcement scope or to any §3 item.

## 7. Sequence

1. Merge this charter.
2. Merge the matching `[layer1-freeze]` amendment.
3. Revalidate and squash-merge #484 under ADR-022.
4. Then start **G4** (offline failure-scenario tests) reusing #484's merged
   `tests/integrations/check_contract.py`.

**C1b remains locked; ADR-033 remains proposed; DG1B2 remains evidence-gated.**
