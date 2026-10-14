# DG1F — Adversarial blocking-semantics validation matrix (read-only preflight)

**Status:** source- and test-inspected **evidence inventory**, not a behavioral
charter, approval, implementation plan, or Layer 1 freeze amendment. No C1b
exclusion, waiver, new API, or enforcement change is authorized by this
document. It reuses existing regression tests as evidence and does **not**
duplicate them.
**Source anchor:** `MnemeHQ/mneme` `main` at
`396c4dcc42d6b2fb4ccaaf0f1f07d57982bb7c6d` (DG1F enforcement-consumer
inventory, PR #498).
**Governing contracts:** [ADR-031](../adr/ADR-031-decision-governance-semantics.md)
§4/§6–§7/§11–§12; [ADR-017](../adr/ADR-017-enforcement-scope-vs-retrieval-scope.md);
[ADR-020](../adr/ADR-020-explicit-path-applicability-for-typed-rules.md);
[ADR-021](../adr/ADR-021-shell-preflight-and-stop-session-delta.md);
[ADR-029](../adr/ADR-029-enforcement-evidence-binding-semantics.md);
[ADR-030](../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md);
the merged [C1 charter](2026-10-13-dg1f-applicability-only-charter.md); and the
[consumer inventory](2026-10-14-dg1f-consumer-trust-boundary-inventory.md).

## 1. Architecture dependencies reviewed first

- **PR #483 (C0, draft).** Proposes ADR-033 (separate opt-in availability
  handling from architectural strict/warn; trusted-complete / incomplete /
  untrusted / skipped states) and a Layer 1 C0 charter. It states no
  implementation is authorized while the ADR and charter remain proposed, and
  sets four gates: accept ADR+charter; pin the check-v1 consistency matrix;
  probe pinned Claude Code live behavior and verify no mutation; lock tests and
  benchmark parity. **Unmerged; not presupposed here.**
- **PR #484 (C1, open; CI green).** Implements coherent verdict validation
  (`hook.assess_verdict`) across the shipped consumers and keeps every
  fail-open surface. It closes #260. Its own review point #1 asks to confirm its
  sequencing against #483 before merge. **Unmerged.**
- **PR #498 (merged).** The consumer inventory this matrix extends; it already
  flags the blocking-seam gap and the unaudited CI consumers.

**Dependency consequence.** #484 changes *how a verdict is judged trustworthy*
(it does not change *whether an operation is blocked on failure*). This matrix
therefore cites #484 tests for the trust-classification rows and existing
`main` tests for the failure-behavior rows, and marks the harness/CI rows that
neither proves.

## 2. What #484 already proves (do not duplicate)

`tests/integrations/claude_code/test_hook_verdict_consistency.py` (30 tests,
PR #484) plus the per-surface contradictory-result tests establish:

- a payload is trusted only when envelope, violation records, aggregate,
  requested-mode and exit code are mutually coherent;
- an **incoherent** result **fails open** (ADR-021 transport policy) with a
  non-echoing diagnostic — it never blocks;
- coherent strict/warn results keep existing enforcement;
- the exit-code table matches `mneme.cli._EXIT_CODES_BY_MODE`.

#484 answers *"is this verdict trustworthy?"* It does **not** answer *"when
evaluation fails, does this integration actually permit or block the action,
and does the harness enforce it?"* — the question below.

## 3. Failure scenarios (columns) and consuming surfaces (rows)

Scenarios: **S1** missing project memory · **S2** invalid/unreadable canonical
memory · **S3** unparseable/malformed verdict · **S4** contradictory verdict ·
**S5** incomplete evaluation (`evaluation_complete:false`) · **S6** child CLI
launch failure / interpreter missing · **S7** timeout · **S8** materialization
failure · **S9** unknown path applicability (ADR-020 `UNKNOWN`) · **S10** wrong
schema / stale CLI · **S11** absent verdict payload.

Legend: **B** = blocks (deny), **P** = permits (fail open), **V** = permits but
visible/disclosed, **—** = not applicable. Evidence is a test path (on `main`
unless marked `#484`).

| Surface | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 | S9 | S10 | S11 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CLI `mneme check` | err | err | n/a | n/a | exit 2 | err | err | n/a | exit 2 | err | n/a |
| CC PreToolUse edit gate | P | P | P | P | V | P | P | P | V | V | P |
| CC Bash/heredoc preflight | P | P | P | P | V | P | P | P | V | V | P |
| CC Stop session-delta | V | V | V | V | V | V | V | V | V | V | V |
| Codex gate | P | P | P | P | V | P | P | P | P | P | P |
| Codex Stop audit | V | V | V | V | V | V | V | V | V | V | V |
| Kiro | P | P | P | P | V | P | P | P | P | V | P |
| Agent SDK | P | P | P | P | V | P | P | P | P | P | P |
| LangChain | P | P | P | P | V | P | P | P | P | P | P |
| Hermes | P | P | P | P | V | P | P | P | V | P | P |
| Antigravity | P | P | P | P | V | P | P | P | P | P | P |
| Decision MCP | — | err | — | — | — | — | — | — | — | — | — |
| Protection / Audit / readiness | — | err | — | — | — | — | — | — | — | — | — |

Representative evidence (not exhaustive):

- **CC PreToolUse / mode:** `tests/integrations/claude_code/test_hook_verdict.py`
  (`test_unparseable_stdout_with_exit_two_fails_open`,
  `test_traceback_with_exit_one_fails_open`,
  `test_unknown_path_applicability_fails_open_with_reason`,
  `test_stale_runtime_warns_that_enforcement_is_inactive`),
  `test_hook_mode.py`, `test_hook_verdict_consistency.py` (`#484`).
- **CC Stop:** `tests/integrations/claude_code/test_stop_boundary.py`
  (`test_absent_memory_is_a_no_op`, `test_corrupt_baseline_degrades_visibly`,
  `test_crashing_checker_fails_open_with_diagnostics`,
  `test_contradictory_checker_result_never_blocks`, `#484`).
- **Codex gate:** `tests/integrations/codex_cli/test_gate.py`
  (`test_incomplete_evaluation_fails_open_with_applicability_reason`,
  `test_malformed_verdict_json_fails_open`, `test_wrong_schema_fails_open`,
  `test_contradictory_verdict_fails_open`, `test_timeout_fails_open`,
  `test_launch_failure_fails_open`, `test_parse_failure_fails_open_as_not_evaluated`).
- **Codex Stop audit:** `tests/integrations/codex_cli/test_stop_audit.py`
  (`test_contradictory_checker_result_is_disclosed_not_blocked`,
  `test_unevaluated_artifact_disclosed_not_claimed_governed`).
- **Kiro:** `tests/integrations/kiro/test_failopen.py` (18 tests spanning S1,
  S3–S8, S10).
- **Agent SDK:** `tests/integrations/agent_sdk/test_adapter.py`
  (`test_unparseable_verdict_fails_open_visibly`,
  `test_contradictory_verdict_fails_open_visibly`,
  `test_operational_failure_fails_open`, `test_materialize_failure_fails_open`).
- **LangChain:** `tests/integrations/langchain/test_adapter.py` (same set plus
  `test_forbidden_write_blocked_with_target_path`).
- **Hermes:** `tests/integrations/hermes/test_adapter_gate.py`
  (`test_non_heredoc_command_passes_unevaluated`,
  `test_missing_update_snapshot_is_disclosed_not_guessed`,
  `test_incomplete_evaluation_fails_open`).
- **Antigravity:** `tests/integrations/antigravity/test_adapter_gate.py`
  (`test_malformed_hook_input_fails_open`, `test_incomplete_evaluation_fails_open`).

Cells are the adapter's **returned action** (block/permit/visible) as asserted
offline. They are **not** proof that the host harness honours it (see G1).

## 4. Uncovered scenarios and gaps (the actual finding)

| ID | Gap | Why it matters | What would close it |
|---|---|---|---|
| **G1** | **Harness enforcement is unproven.** Offline tests assert the adapter's `deny`/`block` return, not that the host (Claude Code, Codex, Kiro, Antigravity, Hermes) actually prevents the mutation. | A returned block that the harness ignores would be a false sense of protection. | A pinned, live/pinned-harness probe that triggers a violation and independently verifies no file mutation (#483 C3 gate). Out of offline unit scope. |
| **G2** | **CI consumers are unaudited.** Which GitHub Actions jobs invoke `mneme check`, and whether a missing/malformed/incomplete verdict blocks the protected action, is not mapped. | CI is a primary enforcement seam; a fail-open CI step silently passes. | A per-workflow inventory + an offline test that a malformed/missing verdict makes the CI step fail (or is explicitly documented as non-blocking). |
| **G3** | **Missing-memory policy is unsettled.** S1 yields permit/no-op on several surfaces (e.g. CC Stop `test_absent_memory_is_a_no_op`, Kiro quiet-zero). | Whether "no memory" should be inactive/unevaluated (permit) or an operational failure is an eligibility/witness decision, not a mechanical one. | #483 gate 1 (settle eligibility/witness when memory is missing) before any change. |
| **G4** | **Per-surface scenario coverage is uneven.** Not every surface has an explicit S2 (corrupt canonical), S7 (timeout) or S9 (path `UNKNOWN`) test; MCP and protection/Audit/readiness have no blocking verdict by design. | Absence of a test is not evidence of safe behavior. | A small per-surface scenario matrix filling only the empty cells, reusing `tests/integrations/check_contract.py` (`#484`) rather than new doubles. |
| **G5** | **Incomplete-vs-untrusted is only an adapter-level distinction.** #484 classifies trust; the *policy* (what the product should do when evaluation is incomplete or unavailable) is ADR-033 scope. | The matrix characterizes current behavior; it does not decide future availability policy. | ADR-033 / C0 charter decision (#483), not this preflight. |

## 5. Bounded offline validation matrix — proposed next step (not authorized here)

A separate, bounded offline work item may add only the missing cells from G4,
reusing #484's `check_contract.py` and existing per-surface tests, asserting for
each surface: the returned action, the visibility of any fail-open, and that no
mutation is claimed as governed when evaluation failed. It must:

- run fully offline (no network, no live harness) and reuse #484 tests instead
  of duplicating them;
- change **no** runtime behavior, CLI/MCP surface, schema, `.mneme` authority,
  benchmark fixture, or Layer 1 freeze baseline;
- record G1/G2/G3 as **out-of-offline-scope** and require separate evidence
  (live probe; CI inventory; eligibility decision) before any fail-closed claim.

It does not authorize C1b, DG1B2, ADR-033 implementation, or any change to
enforcement.

## 6. Bottom line

- **Proven offline today:** every shipped consumer *identifies* an untrustworthy
  or absent verdict and *fails open visibly*; coherent strict/warn results keep
  existing enforcement (#484 + existing suites).
- **Not proven:** that the host harness actually blocks on the adapter's block
  (G1), that CI blocks on a bad verdict (G2), and the missing-memory policy (G3).
- This preflight makes **no** end-to-end fail-closed claim and authorizes no
  enforcement change. **C1b remains locked.**
