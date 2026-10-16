# Reliable Enforcement C0 — proposed Layer 1 behavior charter

**Date:** 2026-10-13
**Status:** Proposed, specification only. NOT implementation authority before review/acceptance.
**Proposed governing ADR:** [ADR-033](../adr/ADR-033-opt-in-fail-closed-enforcement.md)
**Prerequisite defect:** [#260](https://github.com/MnemeHQ/mneme/issues/260)
**Scope:** Mneme Core OSS; one Claude Code PreToolUse proof first.

## Why a charter is required

The frozen Layer 1 contract at `docs/architecture/layer1-freeze-e73ff7d.md` disallows changes to enforcement behavior without an explicit charter. The existing Claude Code hook is deliberately fail-open when the checker fails. #260 shows that the same hook may accept internally contradictory checker output as authoritative. Introducing even opt-in blocking on operational failure is a behavior change, though it must **not** change deterministic rule matching or the meaning of a trusted result.

This charter proposes an exception for **enforcement-result trust and availability handling** only. It does not amend the frozen benchmark, deterministic matcher, retrieval weights, ConflictDetector, or Layer 1 exit metrics; it must not retroactively rewrite the frozen baseline.

## Verified architecture boundaries

| Existing boundary | Current source | C0 constraint |
|---|---|---|
| CLI check/v1 and result payload | `mneme/cli.py` `_check_payload`, `_cmd_check` | Preserve verdict semantics; distinguish incomplete operation from actual violations |
| Result/typed applicability | `mneme/enforcer.py`, ADR-020 | Reuse applicability trace; UNKNOWN is operational, not PASS |
| Claude Code decision adapter | `mneme/integrations/claude_code/hook.py` | Validate stdout + exit + requested mode before trusting result |
| Default fail-open behavior | `tests/integrations/claude_code/test_hook_verdict.py` | Preserve for unopted projects; change conflicting test only with explicit regression |
| PreToolUse/Stop separation | ADR-018, ADR-021 | First milestone is direct-file pre-write gate; Stop is not prevention |
| Canonical project authority/activation | ADR-023/030/031, `mneme/setup_state.py`, `mneme/protection.py` | No second decision store; setup cannot activate protection implicitly |
| Evidence binding | ADR-029, ADR-031 | Unevaluated refusal is not a decision violation or proven relevant enforcement |

## Bounded proposal

1. Resolve issue #260's coherence hole before adding an availability-strict policy. A parseable PASS with an impossible exit code is an **untrusted** result.
2. Separate policy verdict (`PASS/WARN/FAIL`) from evaluation state (complete/incomplete/untrusted/not-run/skip), initially inside an adapter-level classifier rather than a new public evidence schema.
3. Introduce an **opt-in** availability `open|closed` behavior independent of strict/warn. `open` remains the default and must exhibit default-parity. `closed` may refuse an eligible direct write when trustworthy evaluation is unavailable, explaining **UNEVALUATED**.
4. Bind opt-in to an explicitly protected project, preserving setup/activation contracts. Missing memory cannot be used as evidence of opt-in; the separate eligibility witness and configuration precedence must be reviewed before C2.
5. Prove the one supported Claude Code PreToolUse surface end-to-end before extending provider support. Verify host level command-hook failure handling on a pinned version. A missing hook registration is outside the protection guarantee.
6. Keep existing CI and benchmarks unchanged; add separate failure-injection tests.

## Proposed acceptance matrix

| Scenario | Existing/default behavior to preserve | Proposed opted-in PreToolUse behavior |
|---|---|---|
| Complete, coherent PASS | Proceed | Proceed |
| Complete, coherent WARN/FAIL | Existing strict/warn behavior | Existing strict/warn behavior |
| Coherent result but UNKNOWN applicability | Disclose unevaluated; proceed | Disclose unevaluated; refuse supported direct write |
| Checker process timeout or exception | Disclose unevaluated; proceed | Disclose unevaluated; refuse supported direct write |
| Contradictory PASS with nonzero code | Currently wrongly trusted; after #260 untrusted and fail-open | Untrusted; refuse supported direct write |
| Missing project memory; no independent protected-project opt-in | No block | No block; cannot infer opt-in |
| Missing memory with independently proved project opt-in | Existing fail-open | Must refuse supported direct write; design gate pending |
| Out-of-scope or non-mutating event | Preserve existing skip | Preserve skip |
| Unsupported Bash mutation | Preserve ADR-021 class-B behavior | Not in first guarantee |
| Hook missing entirely / Stop backstop error | Not guaranteed | Not covered by first proof; require separate host/boundary validation |

**Mixed partial violations:** no guessed precedence. C1 must characterize current payload and prescribe reporting so an operational block cannot be mislabeled a complete rule verdict.

## Deliberate architecture exclusions

- No change to `decision_retriever.py`, `conflict_detector.py`, rule matcher, selectors or frozen benchmark cases.
- No new ADR-031 decision applicability, precedence, waivers, v2 persistence or governance inference.
- No automatic fail-closed on `mneme init`, `setup`, non-protected repos or missing memory without independent opt-in proof.
- No blanket denial of shell commands, no universal write-path guarantee, and no Stop-time undo.
- No provider fan-out or Data Engine dependency.

## Review gates before code

- [ ] Accept ADR-033 and this explicit charter; reconcile with ADR-017/018/020/021/023/029/030/031.
- [ ] Confirm a backward-compatible v1 complete/incomplete/trust matrix, including missing `evaluation_complete`, wrong mode, malformed records, expected CLI exit codes, and #260's contradictory PASS fixture.
- [ ] Select and review a project-scoped eligibility witness that remains checkable when `project_memory.json` is missing, without an alternative decision authority.
- [ ] Pin Claude Code host version and experimentally verify not-launched/crash/timeout behavior with `onFailure: "block"` (>=2.1.295 documented), plus real file unchanged when a gate refuses.
- [ ] Lock first-slice host surface and honest coverage statement; retain ADR-021 Stop and class-B exclusions.
- [ ] Specify deterministic, separate regression suite and frozen benchmark parity command/evidence.
- [ ] Amend the current-phase operational guidance only when this charter is accepted; do not rewrite `layer1-freeze-e73ff7d.md` to rationalize the new behavior.

## C0 deliverable and next execution order

C0 is the documentation-only proposed ADR plus this proposed charter. No runtime, benchmark, config, hook, CI or canonical memory changes are authorized by this PR.

After acceptance: **C1 (#260) → C2 failure policy/eligibility → C3 Claude Code live proof → C4 regression/CI/docs**. One bounded PR per execution slice, following ADR-022.
