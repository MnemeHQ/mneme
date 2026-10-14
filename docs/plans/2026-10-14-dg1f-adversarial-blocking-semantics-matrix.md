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
  implementation is authorized while the ADR and charter remain proposed, with
  gates: accept ADR+charter; pin the check-v1 consistency matrix; probe pinned
  Claude Code live behavior; lock tests and parity. **Unmerged; not presupposed.**
- **PR #484 (C1, open; CI green).** Implements coherent verdict validation
  (`hook.assess_verdict`) across the shipped consumers and keeps every fail-open
  surface. It closes #260. Its review point #1 asks to confirm sequencing
  against #483 before merge. **Unmerged.**
- **PR #498 (merged).** The consumer inventory this matrix extends.

**Dependency consequence.** #484 changes *how a verdict is judged trustworthy*,
not *whether an operation is blocked on failure*. Its coherence tests are
**not on `main`** and are cited below as **`#484` evidence**; `main`'s tests
cover the failure-behavior rows. Neither proves host-harness enforcement.

## 2. What #484 already proves (do not duplicate)

`tests/integrations/claude_code/test_hook_verdict_consistency.py` (30 tests,
`#484`) plus the per-surface contradictory-result tests (**all `#484`-only**)
establish that a payload is trusted only when envelope, violation records,
aggregate, requested-mode and exit code are mutually coherent; an **incoherent**
result **fails open** with a non-echoing diagnostic; coherent strict/warn
results keep existing enforcement; the exit-code table matches
`mneme.cli._EXIT_CODES_BY_MODE`.

#484 answers *"is this verdict trustworthy?"* It does **not** answer *"when
evaluation fails, does this integration actually permit or block the action, and
does the host enforce it?"*

## 3. Failure scenarios × surfaces (with evidence class)

Scenarios: **S1** missing project memory · **S2** invalid/unreadable canonical
memory · **S3** unparseable/malformed verdict · **S4** contradictory verdict ·
**S5** incomplete evaluation (`evaluation_complete:false`) · **S6** child CLI
launch failure / interpreter missing · **S7** timeout · **S8** materialization
failure · **S9** unknown path applicability (ADR-020 `UNKNOWN`) · **S10** wrong
schema / stale CLI · **S11** absent verdict payload.

**Behavior:** `B` blocks (deny) · `S` **silent permit / no-op — the operation is
permitted with no agent-visible diagnostic** · `V` permit with a visible/
disclosed diagnostic · `?` not established · `—` not applicable.
**Evidence class (second letter):** `t` direct offline test cited below · `i`
inferred from source only · `u` untested/not established.

A cell is `behavior+class`, e.g. `St` = silent permit, test-cited; `Vi` = visible
permit, source-inferred; `?u` = unknown.

| Surface | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 | S9 | S10 | S11 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CLI `mneme check` | —t | —t | — | — | Bt | —t | ?u | — | Bt | —t | — |
| CC PreToolUse edit gate | Si | ?u | Vt | Vt | Vt | Vt | ?u | ?u | Vt | Vt | ?u |
| CC Bash/heredoc preflight | Si | ?u | Vt | Vt | Vt | Vt | ?u | ?u | Vt | Vt | ?u |
| CC Stop session-delta | Si | Vt | Vt | Vt | Vt | Vt | ?u | Vt | Vt | Vt | Vt |
| Codex gate | St | ?u | Vt | Vt | Vt | Vt | Vt | ?u | ?u | Vt | ?u |
| Codex Stop audit | Si | ?u | Vt | Vt | Vt | ?u | ?u | ?u | ?u | ?u | ?u |
| Kiro | St | ?u | Vt | Vt | Vt | Vt | Vt | Vt | ?u | Vt | ?u |
| Agent SDK | ?u | ?u | Vt | Vt | Vt | Vt | ?u | Vt | ?u | ?u | ?u |
| LangChain | ?u | ?u | Vt | Vt | Vt | Vt | ?u | Vt | ?u | ?u | ?u |
| Hermes | ?u | ?u | Vt | Vt | Vt | Vt | ?u | ?u | ?u | ?u | ?u |
| Antigravity | ?u | ?u | Vt | Vt | Vt | Vt | ?u | ?u | ?u | ?u | ?u |
| Decision MCP | — | ?u | — | — | — | — | — | — | — | — | — |
| Protection / Audit / readiness | — | ?u | — | — | — | — | — | — | — | — | — |

**S1 is a silent skip, not a visible failure, on every hook that discovers
memory.** Source-confirmed: `mneme/integrations/claude_code/hook.py` edit gate
(`if memory is None: return 0`, ~L498) and `stop_event` (`if memory is None:
return 0`, ~L692); `mneme/integrations/codex_cli/gate.py` ("no project memory ->
SKIP"); `mneme/integrations/codex_cli/stop_audit.py` (`_find_memory_for` →
`return None`). Test-confirmed: `tests/integrations/kiro/test_failopen.py::
test_no_project_memory_quiet_zero`. The Stop **SessionStart** no-op test
(`test_absent_memory_is_a_no_op`, `tests/integrations/claude_code/test_stop_boundary.py`)
exercises **SessionStart, not Stop**, so Stop's S1 rests on source, not on that
test.

Representative evidence (all cited failure-behavior tests are on `main`; the
coherence/contradictory tests are `#484`-only):

- **CC PreToolUse / mode:** `tests/integrations/claude_code/test_hook_verdict.py`
  (`test_unparseable_stdout_with_exit_two_fails_open`,
  `test_traceback_with_exit_one_fails_open`,
  `test_unknown_path_applicability_fails_open_with_reason`,
  `test_stale_runtime_warns_that_enforcement_is_inactive`), `test_hook_mode.py`.
- **CC Stop:** `tests/integrations/claude_code/test_stop_boundary.py`
  (`test_corrupt_baseline_degrades_visibly`,
  `test_crashing_checker_fails_open_with_diagnostics`).
- **Codex gate:** `tests/integrations/codex_cli/test_gate.py`
  (`test_incomplete_evaluation_fails_open_with_applicability_reason`,
  `test_malformed_verdict_json_fails_open`, `test_wrong_schema_fails_open`,
  `test_timeout_fails_open`, `test_launch_failure_fails_open`,
  `test_parse_failure_fails_open_as_not_evaluated`).
- **Codex Stop audit:** `tests/integrations/codex_cli/test_stop_audit.py`
  (`test_unevaluated_artifact_disclosed_not_claimed_governed`).
- **Kiro:** `tests/integrations/kiro/test_failopen.py` (S3–S8, S10).
- **Agent SDK:** `tests/integrations/agent_sdk/test_adapter.py`
  (`test_operational_failure_fails_open`, `test_materialize_failure_fails_open`,
  `test_unparseable_verdict_fails_open_visibly`).
- **LangChain:** `tests/integrations/langchain/test_adapter.py`
  (`test_materialize_failure_fails_open`, `test_operational_failure_fails_open`,
  `test_forbidden_write_blocked_with_target_path`).
- **Hermes:** `tests/integrations/hermes/test_adapter_gate.py`
  (`test_check_launch_failure_fails_open`, `test_incomplete_evaluation_fails_open`).
- **Antigravity:** `tests/integrations/antigravity/test_adapter_gate.py`
  (`test_malformed_hook_input_fails_open`, `test_incomplete_evaluation_fails_open`).
- **`#484`-only (not on `main`):** the S4 contradictory rows —
  `test_contradictory_verdict_fails_open_visibly` (agent_sdk, antigravity,
  hermes, langchain, kiro), `test_contradictory_verdict_fails_open`
  (codex gate), `test_contradictory_checker_result_is_disclosed_not_blocked`
  (codex stop audit), `test_contradictory_checker_result_never_blocks` (CC Stop),
  and all of `tests/integrations/claude_code/test_hook_verdict_consistency.py`.

Cells marked `t` are the adapter's **returned action** as asserted offline; they
are **not** proof the host harness honours it (see G1).

## 4. Uncovered scenarios and gaps

| ID | Gap | Why it matters | What would close it |
|---|---|---|---|
| **G1** | **Harness enforcement is unproven.** Offline tests assert the adapter's `deny`/`block` return, not that the host actually prevents the mutation. | A returned block the harness ignores is false protection. | A pinned live/pinned-harness probe verifying no mutation (#483 C3). Out of offline scope. |
| **G2** | **CI consumers are unaudited.** Which jobs invoke `mneme check`, and whether a bad verdict blocks, is unmapped. | A fail-open CI step silently passes. | Per-workflow inventory + an offline test that a bad verdict fails the step (or is documented non-blocking). |
| **G3** | **Missing-memory policy is unsettled** and currently a **silent skip** (S1). | Whether "no memory" should be inactive/unevaluated (permit) or an operational failure is an eligibility/witness decision. | #483 gate 1 before any change. |
| **G4** | **Per-surface coverage is uneven.** The `?u` cells (notably S2 invalid canonical memory; S7 timeout; S9/S11 on several surfaces; all S1 on Agent SDK/LangChain/Hermes/Antigravity) have no direct test. | Absence of a test is not evidence of safe behavior. | A bounded offline matrix filling only the empty cells, reusing `tests/integrations/check_contract.py` (`#484`). |
| **G5** | **Incomplete-vs-untrusted is only an adapter-level distinction.** #484 classifies trust; the *policy* is ADR-033 scope. | The matrix characterizes current behavior; it does not decide availability policy. | ADR-033 / C0 charter (#483). |

## 5. Bounded offline validation matrix — proposed next step (not authorized here)

A separate bounded offline work item may add only the missing `u` cells from G4,
reusing #484's `check_contract.py` and existing per-surface tests, asserting per
surface: the returned action, the visibility of any fail-open, and that no
mutation is claimed as governed when evaluation failed. It must run fully
offline, reuse rather than duplicate #484, change **no** runtime/CLI/MCP/schema/
`.mneme`/benchmark/freeze behavior, and record G1/G2/G3 as out-of-offline-scope.

## 6. Bottom line

- **Established offline today:** every shipped consumer *identifies* an
  untrustworthy or absent verdict and — except for **S1 missing memory, which is
  a silent skip on the memory-discovering hooks** — fails open with a visible
  diagnostic; coherent strict/warn results keep existing enforcement. This holds
  for `main` for the failure-behavior tests; the **S4 contradictory rows and the
  coherence suite are #484-only evidence**, not yet on `main`.
- **Not proven:** that the host harness actually blocks on the adapter's block
  (G1); that CI blocks on a bad verdict (G2); the missing-memory policy (G3); and
  the `u` cells (G4).
- This preflight makes **no** end-to-end fail-closed claim and authorizes no
  enforcement change. **C1b remains locked.**
