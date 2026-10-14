# DG1F — Adversarial blocking-semantics validation matrix (read-only preflight)

**Status:** source- and test-inspected **evidence inventory**, not a behavioral
charter, approval, implementation plan, or Layer 1 freeze amendment. No C1b
exclusion, waiver, new API, or enforcement change is authorized by this
document. It reuses existing regression tests as evidence and does **not**
duplicate them.
**Source anchor:** `MnemeHQ/mneme` `main` at
`60b02af37c16233176bd77941da0f3e5e225ec88` (verdict-consistency fix, PR #484;
coverage re-audited after it merged).
**Governing contracts:** [ADR-031](../adr/ADR-031-decision-governance-semantics.md)
§4/§6–§7/§11–§12; [ADR-017](../adr/ADR-017-enforcement-scope-vs-retrieval-scope.md);
[ADR-020](../adr/ADR-020-explicit-path-applicability-for-typed-rules.md);
[ADR-021](../adr/ADR-021-shell-preflight-and-stop-session-delta.md);
[ADR-029](../adr/ADR-029-enforcement-evidence-binding-semantics.md);
[ADR-030](../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md);
the merged [C1 charter](2026-10-13-dg1f-applicability-only-charter.md); the
[reliable-enforcement C1 charter](2026-10-14-reliable-enforcement-c1-verdict-consistency-charter.md);
and the [consumer inventory](2026-10-14-dg1f-consumer-trust-boundary-inventory.md).

## 1. Architecture dependencies

- **PR #483 (C0, draft).** Proposes ADR-033 (separate opt-in availability
  handling from architectural strict/warn; trusted-complete / incomplete /
  untrusted / skipped states) and a Layer 1 C0 charter. It states no
  implementation is authorized while the ADR and charter remain proposed.
  **Unmerged; not presupposed.**
- **PR #484 (C1, merged).** Coherent verdict validation (`hook.assess_verdict`)
  across the shipped consumers, keeping every fail-open surface; closes #260.
  **Merged as `60b02af3`** after the C1 charter (#503) and the matching
  `[layer1-freeze]` amendment (#504). Its tests are now **on `main`.**
- **PR #498 (merged).** The consumer inventory this matrix extends.

**Dependency consequence.** #484 changes *how a verdict is judged trustworthy*,
not *whether an operation is blocked on failure*. Neither proves host-harness
enforcement (G1).

## 2. What the verdict-consistency work proves (do not duplicate)

`tests/integrations/claude_code/test_hook_verdict_consistency.py` plus the
per-surface contradictory-result tests establish that a payload is trusted only
when envelope, violation records, aggregate, requested-mode and exit code are
mutually coherent; an **incoherent** result **fails open** with a non-echoing
diagnostic; coherent strict/warn results keep existing enforcement; the
exit-code table matches `mneme.cli._EXIT_CODES_BY_MODE`.

That answers *"is this verdict trustworthy?"* It does **not** answer *"when
evaluation fails, does this integration actually permit or block the action, and
does the host enforce it?"*

## 3. Failure scenarios × surfaces (with evidence class)

Scenarios: **S1** missing project memory · **S2** invalid/unreadable canonical
memory · **S3** unparseable/malformed verdict · **S4** contradictory verdict ·
**S5** incomplete evaluation (`evaluation_complete:false`) · **S6** child CLI
launch failure / interpreter missing · **S7** timeout · **S8** materialization
failure · **S9** unknown path applicability (ADR-020 `UNKNOWN`) · **S10** wrong
schema / stale CLI · **S11** absent verdict payload.

**Behavior:** `B` blocks (deny) · `S` **silent permit / no-op — permitted with
no agent-visible diagnostic** · `V` permit with a visible/disclosed diagnostic ·
`E` **operational error / non-zero exit — the command reports failure or raises;
this does not by itself establish that a downstream agent was prevented** · `?`
not established · `—` not applicable.
**Evidence class (second letter):** `t` direct offline test cited below · `i`
inferred from source only · `u` untested/not established.

A cell is `behavior+class`, e.g. `St` = silent permit, test-cited; `Vi` = visible
permit, source-inferred; `?u` = unknown. A cell is upgraded from `u` to `t` only
where a **surface-specific** test asserts that behavior for **that** surface; a
test on a sibling surface (e.g. the edit gate) does not upgrade Bash/Stop.

| Surface | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 | S9 | S10 | S11 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CLI `mneme check` | Et | Et | — | — | Et | — | — | — | Et | — | — |
| CC PreToolUse edit gate | Si | ?u | Vt | Vt | Vt | Vt | Vt | Vt | Vt | Vt | ?u |
| CC Bash/heredoc preflight | Si | ?u | Vt | Vt | Vt | Vt | ?u | ?u | Vt | Vt | ?u |
| CC Stop session-delta | Si | Vt | Vt | Vt | Vt | Vt | ?u | Vt | Vt | Vt | Vt |
| Codex gate | St | ?u | Vt | Vt | Vt | Vt | Vt | ?u | ?u | Vt | ?u |
| Codex Stop audit | St | ?u | ?u | Vt | Vt | ?u | ?u | ?u | ?u | ?u | ?u |
| Kiro | St | Vt | Vt | Vt | Vt | Vt | Vt | Vt | ?u | Vt | ?u |
| Agent SDK | St | ?u | Vt | Vt | Vt | Vt | Vt | Vt | Vt | ?u | Vt |
| LangChain | St | ?u | Vt | Vt | Vt | Vt | ?u | Vt | Vt | ?u | ?u |
| Hermes | St | ?u | Vt | Vt | Vt | Vt | ?u | ?u | ?u | ?u | ?u |
| Antigravity | St | ?u | Vt | Vt | Vt | Vt | ?u | ?u | ?u | ?u | ?u |
| Decision MCP | — | ?u | — | — | — | — | — | — | — | — | — |
| Protection / Audit / readiness | — | ?u | — | — | — | — | — | — | — | — | — |

**S1 is a silent skip, not a visible failure, on every hook that discovers
memory.** Where a test proves only a successful return, the cell is `Si`
(source-confirmed), not `St`: the CC edit gate and `stop_event` return `0` on
`memory is None`, and the CC tests `test_no_memory_returns_zero` /
`test_absent_memory_passthrough` assert only `rc == 0`, which does not by itself
prove that no agent-visible diagnostic was emitted. Cells are `St` where the
test asserts an explicit silent action or empty output: Codex gate
`test_no_project_memory_skips`, Codex Stop `test_missing_memory_is_a_silent_no_op`,
Kiro `test_no_project_memory_quiet_zero`, Agent SDK `test_no_memory_skipped`,
LangChain `test_no_memory_skips_mapped_tool_without_checker_call`, Hermes
`test_no_project_memory_has_no_opinion`, Antigravity `test_no_memory_has_no_opinion`.
The SessionStart no-op test (`test_absent_memory_is_a_no_op`) exercises
**SessionStart, not Stop**, so it does not upgrade Stop.

**CLI is not a blocking seam.** `mneme check` exits non-zero on a missing or
invalid memory (`E`, S1/S2) and on incomplete or `UNKNOWN` evaluation (exit 2,
`E`, S5/S9), but those are operational results the caller must interpret; they
do **not** by themselves establish that a downstream agent action was prevented
(G1/G2).

Representative evidence (all on `main` after #484 merged):

- **CLI:** `tests/test_dg1f_g4_cli_memory_failures.py` (corrupt canonical memory
  and malformed JSON are operational errors, never a PASS).
- **CC PreToolUse / mode:** `test_hook_main.py` (`test_no_memory_returns_zero`,
  `test_subprocess_timeout_fails_open`, `test_materialize_failure_fails_open`),
  `test_hook_verdict.py` (`test_unparseable_stdout_with_exit_two_fails_open`,
  `test_unknown_path_applicability_fails_open_with_reason`,
  `test_stale_runtime_warns_that_enforcement_is_inactive`), `test_hook_mode.py`.
- **CC Bash/heredoc:** `test_shell_gate_dispatch.py` (`test_absent_memory_passthrough`),
  `test_shell_preflight.py`. Timeout/materialization are **not** asserted here.
- **CC Stop:** `test_stop_boundary.py` (`test_corrupt_baseline_degrades_visibly`,
  `test_crashing_checker_fails_open_with_diagnostics`,
  `test_contradictory_checker_result_never_blocks`).
- **Codex gate:** `test_gate.py` (`test_no_project_memory_skips`,
  `test_incomplete_evaluation_fails_open_with_applicability_reason`,
  `test_malformed_verdict_json_fails_open`, `test_wrong_schema_fails_open`,
  `test_timeout_fails_open`, `test_launch_failure_fails_open`,
  `test_contradictory_verdict_fails_open`).
- **Codex Stop audit:** `test_stop_audit.py`
  (`test_missing_memory_is_a_silent_no_op` (S1),
  `test_contradictory_checker_result_is_disclosed_not_blocked`,
  `test_unevaluated_artifact_disclosed_not_claimed_governed`).
- **Kiro:** `test_failopen.py` (S1, S3–S8, S10), `test_e2e.py`
  (`test_corrupt_memory_fails_open_against_real_cli`, S2).
- **Agent SDK:** `test_adapter.py` (`test_no_memory_skipped`,
  `test_unknown_evaluation_never_becomes_pass` (S9 adapter handling of an
  `UNKNOWN` trace), `test_operational_failure_fails_open`,
  `test_timeout_fails_open_visibly` (S7),
  `test_absent_verdict_payload_fails_open` (S11),
  `test_materialize_failure_fails_open`,
  `test_unparseable_verdict_fails_open_visibly`,
  `test_contradictory_verdict_fails_open_visibly`).
- **LangChain:** `test_adapter.py` (same set plus
  `test_no_memory_skips_mapped_tool_without_checker_call`).
- **Hermes:** `test_adapter_gate.py` (`test_check_launch_failure_fails_open`,
  `test_incomplete_evaluation_fails_open`,
  `test_no_project_memory_has_no_opinion`).
- **Antigravity:** `test_adapter_gate.py` (`test_malformed_hook_input_fails_open`,
  `test_incomplete_evaluation_fails_open`, `test_no_memory_has_no_opinion`).

Cells marked `t` are the adapter's **returned action** as asserted offline; they
are **not** proof the host harness honours it (see G1).

## 4. Uncovered scenarios and gaps

| ID | Gap | Why it matters | What would close it |
|---|---|---|---|
| **G1** | **Harness enforcement is unproven.** Offline tests assert the adapter's `deny`/`block` return, not that the host actually prevents the mutation. | A returned block the harness ignores is false protection. | A pinned live/pinned-harness probe verifying no mutation (#483 C3). Out of offline scope. |
| **G2** | **CI consumers are unaudited.** Which jobs invoke `mneme check`, and whether a bad verdict blocks, is unmapped. | A fail-open CI step silently passes. | Per-workflow inventory + an offline test that a bad verdict fails the step (or is documented non-blocking). |
| **G3** | **Missing-memory policy is unsettled** and currently a **silent skip** (S1). | Whether "no memory" should be inactive/unevaluated (permit) or an operational failure is an eligibility/witness decision. | #483 gate 1 before any change. |
| **G4** | **Residual per-surface gaps.** After the coverage re-audit and the G4 tests, the genuinely untested cells are: S2 invalid canonical memory (all surfaces except Kiro and the CLI); S7 timeout on CC Bash/Stop, LangChain, Hermes, Antigravity; S9 on Codex gate/Stop, Kiro, Hermes, Antigravity; S11 absent verdict payload on most surfaces; and Codex Stop audit S3/S6–S11. | Absence of a test is not evidence of safe behavior. | A bounded offline module filling only these cells, reusing `tests/integrations/check_contract.py`. |
| **G5** | **Incomplete-vs-untrusted is only an adapter-level distinction.** #484 classifies trust; the *policy* is ADR-033 scope. | The matrix characterizes current behavior; it does not decide availability policy. | ADR-033 / C0 charter (#483). |

## 5. Bounded offline validation matrix — the G4 work item

A bounded offline work item adds only the genuinely untested cells from G4,
reusing `tests/integrations/check_contract.py` and existing per-surface tests,
asserting per surface: the returned action, the visibility of any fail-open, and
that no mutation is claimed as governed when evaluation failed. It runs fully
offline, reuses rather than duplicates the verdict-consistency tests, changes
**no** runtime/CLI/MCP/schema/`.mneme`/benchmark/freeze behavior, and records
G1/G2/G3 as out-of-offline-scope.

## 6. Bottom line

- **Established (tested or source-confirmed `t`/`i` cells only):** among those
  cells, every shipped hook *identifies* an untrustworthy or absent verdict and —
  except for **S1 missing memory, which is a silent skip on the
  memory-discovering hooks** — fails open with a visible diagnostic; coherent
  strict/warn results keep existing enforcement. The **`u` cells are not
  established** and are excluded from this statement. The **CLI is an
  operational-error surface, not a blocking seam** (S1/S2/S5/S9 are `E`).
- **Not proven:** that the host harness actually blocks on the adapter's block
  (G1); that CI blocks on a bad verdict (G2); the missing-memory policy (G3); and
  the residual `u` cells (G4).
- This preflight makes **no** end-to-end fail-closed claim and authorizes no
  enforcement change. **C1b remains locked.**
