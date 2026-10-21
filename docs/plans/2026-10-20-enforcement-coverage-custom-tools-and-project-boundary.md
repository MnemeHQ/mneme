# Enforcement coverage: custom tool interception and project-boundary handling

**Status:** **PROPOSED.** Design only. Capability assessment and
regression-test proposal; authorizes no implementation. No change to
`mneme/`, `docs/adr/`, `.mneme/`, CI, the Layer 1 freeze document or the
sandbox evidence. Any runtime or policy change named below needs its own
charter and, where it touches enforcement behavior, a `[layer1-freeze]`
amendment under the Amendment Procedure.
**Workstream:** P1 enforcement coverage. Feeds the separate P0 orchestrator
governance track; does not cover semantic enforcement (deadline or fallback
rules, C2/C3 in the sandbox), which is a separate effort.
**Source anchor:** `MnemeHQ/mneme` `main` @ `04a1f989` (includes the
relative-path fix #573 `cf6bc40b` and the sandbox #570). Line numbers refer to
that commit.
**Evidence:**
[`validation/orchestrator-decision-sandbox/RESULTS.md`](../../validation/orchestrator-decision-sandbox/RESULTS.md)
and
[`evidence/post-fix/summary.json`](../../validation/orchestrator-decision-sandbox/evidence/post-fix/summary.json),
scenarios `unmapped_tool_literal` and `write_outside_project_dir`.

## 1. Why this document exists

After #573 the shipped LangChain middleware blocked 6 of the 8 literal
attempts in the sandbox's fixed attempt set (7 of 9 including the post-fix-only
partial-decoy scenario). The two attempts that still mutate are not matcher
misses. Both sit at the edge of the documented governed scope:

| Gap | Scenario | Post-fix label | Mneme action | Handler runs | Final oracle |
|---|---|---|---|---|---|
| 1. Custom tool | `unmapped_tool_literal` (`save_text` writes B) | `NOT_EVALUATED` | `skip`, verdict `null`, 0 checker calls | 1 | rejects (`C1_DISABLED`) |
| 2. Project boundary | `write_outside_project_dir` (`write_file` writes B outside the root) | `ERROR_DEGRADED` | `fail_open`, verdict `PASS`, `evaluation_complete` false | 1 | rejects (`C1_DISABLED`) |

Source: `summary.json` → `agent_scenarios.<scenario>.attempts[0]`;
RESULTS.md agent table rows "custom `save_text` tool writing B" and "write B
outside `project_dir`" (lines 75-76); pinned by
`test_unmapped_tool_not_governed` and `test_out_of_root_path_is_not_allowed`
(`validation/orchestrator-decision-sandbox/tests/test_sandbox.py:305-318`).

This document assesses what it would take to close each gap with existing
surfaces, which frozen semantics each option touches, and which regression
tests would pin the result. It does not decide for the P0 track how an
orchestrator should be governed overall.

## 2. Current behavior

### 2.1 Gap 1: a tool outside the closed tool map

- `LANGCHAIN_FILE_TOOLS` maps exactly `write_file → Write` and
  `edit_file → Edit`
  (`mneme/integrations/langchain/adapter.py:74-77`).
- `MnemeLangChain.evaluate_tool_call` returns `ACTION_SKIP` for any other name,
  records a trace entry `reason: "not a governed langchain file tool"` and
  makes no checker call (`adapter.py:134-142`, `164-176`).
- The middleware passes `request.tool_call["name"]` and `args` unchanged and
  always sets `cwd=gate.project_dir`
  (`mneme/integrations/langchain/middleware.py:91-98`).
- The integration contract says so explicitly: "The tool map is deliberately
  closed; extending it is the only way a new tool becomes governed", and
  "arbitrary custom-tool mapping" is out of scope for the milestone
  (`docs/integrations/langchain-langgraph.md:64-73`). `docs/integrations/README.md`
  lists custom tools as a bypass surface.

So `save_text` is outside the governed scope by design. The sandbox confirms
the documented behavior; it is not a defect.

### 2.2 What the gate already accepts from any caller

The gate underneath the middleware is public Python:

- `MnemeAgentSdk.evaluate_mutation(tool_name, tool_input, cwd)` accepts the
  canonical names `Write`, `Edit`, `MultiEdit`
  (`mneme/integrations/claude_code/hook.py:61-65`;
  `mneme/integrations/agent_sdk/adapter.py:180-260`). It materializes
  introduced content (ADR-018), resolves a relative `file_path` against `cwd`
  for both the snapshot and `--target-path` (#573;
  `agent_sdk/adapter.py:351-354`), runs `mneme check --json`, and returns a
  `GateResult` with `action`, `verdict`, `evaluation_complete`, `reason`,
  `payload`.
- `MnemeLangChain.evaluate_tool_call(tool_name, tool_input, cwd="")` does the
  same for the two LangChain names and defaults `cwd` to `project_dir`
  (`langchain/adapter.py:143-147`).
- `mneme check --memory --input --query --mode --target-path --json` is the
  process boundary used by both (`agent_sdk/adapter.py:356-365`).

Neither method requires that the call come from the middleware. A custom tool,
or the orchestrator around it, can call them today. What is missing is a
documented contract for doing so, and tests that prove the pattern.

### 2.3 Gap 2: a write outside `project_dir`

- Memory is discovered from `project_dir` (or the explicit `memory` override),
  not from the target (`agent_sdk/adapter.py:332-336`). An out-of-root write is
  therefore still evaluated against the project's memory.
- ADR-020 Decision 5 derives the policy root from the memory file; Decision 6
  says a scoped rule whose input path is outside that root "is not matched and
  produces an explicit `PATH_APPLICABILITY_UNKNOWN` diagnostic", and that
  integrations "retain their documented transport failure policy, but must
  expose the reason".
- Implementation: `evaluate_path_selectors` returns `UNKNOWN` when
  normalization fails for a scoped rule (`mneme/path_selectors.py:255-262`).
  The CLI reports `evaluation_complete: false`; the adapter maps that to
  `ACTION_FAIL_OPEN` with `format_applicability_reason`
  (`agent_sdk/adapter.py:237-246`).
- The LangChain policy table makes "incomplete evaluation" a visible fail-open:
  the handler executes and the result carries `[mneme] UNEVALUATED ... NOT
  checked` (`langchain-langgraph.md:110-116`). The sandbox observed exactly
  that (`unevaluated_tag: true`, handler ran, B landed).

**Asymmetry not measured by the sandbox (code reading only).** For an
**unscoped** typed rule (no `include_paths`), `evaluate_path_selectors`
returns `APPLIED` before any normalization, even when the path cannot be
normalized (`path_selectors.py:229-240`). An out-of-root write is then checked
against the project's literal rules and can be denied. The sandbox rule is
scoped to `src/**`, so it only exercised the UNKNOWN branch. Boundary behavior
therefore depends on how each rule is authored, not on the boundary itself.
Section 6 proposes a characterization test before anyone relies on this.

### 2.4 ADR-033 does not cover this surface

ADR-033 (accepted 2026-10-20) adds an opt-in `closed` availability policy, but
only for Claude Code `PreToolUse` on `Edit|Write|MultiEdit` (§3, §6), and lists
broad rollout to other providers and managed agents as a non-goal. The C2a
charter ships routing with no verifier, so no code path can refuse on
availability yet. For the LangChain and Agent SDK adapters the availability
policy is, and remains, fail-open.

## 3. Constraints on any option

Every option below is judged against these. An option that breaks one needs
architectural approval before it can be chartered.

| Constraint | Source |
|---|---|
| Retrieval and enforcement stay separate; no new rule types or matcher semantics | ADR-017, ADR-019, ADR-020 Decision 11 |
| Only introduced content is checked at the edit gate | ADR-018 |
| Path applicability semantics (`APPLIED`/`EXCLUDED`/`UNKNOWN`, root derivation) unchanged | ADR-020 Decisions 3, 5-7 |
| Fail-open stays the default availability policy; UNEVALUATED is never relabeled as a violation or a PASS | ADR-033 §1, §3, §7; integration policy table |
| Decision authority, persistence and lineage untouched | ADR-023, ADR-030, ADR-031 |
| The Decision MCP tool list is an authority boundary (exactly six tools); MCP ingestion is not enforcement | ADR-027 §3, `mneme/decision_mcp.py` module docstring |
| No behavioral change to retrieval or enforcement without a charter amendment | Layer 1 freeze, Amendment Procedure |
| Synthetic evidence only; sandbox post-fix evidence stays byte-identical | sandbox `test_committed_summary_matches_fresh_run` |

## 4. Gap 1 options: custom tool interception

The 6C list in RESULTS.md (lines 154-175) defines what a pre-write gate needs
from a mutation point: the proposed action and a guarantee that it waits;
target and content (full proposed content, or old/new plus current content);
a deterministic decision channel; applicability context (project root,
memory); correlation. Each option is scored against that list.

### Option 1A: explicit tool-map registration in Mneme

Add a constructor parameter (for example a per-instance map from a custom
tool name to a canonical name plus an argument mapping) so `save_text(path,
text)` is translated to `Write(file_path, content)` by the middleware.

- **6C fit:** full. Same channel, same trace, same handler-not-called deny.
- **Contract:** consistent with the letter of "extending it is the only way a
  new tool becomes governed", but changes the map from closed-by-code to
  open-by-declaration. The application would assert the local-file contract
  for a tool Mneme cannot inspect, which is the same risk the doc already
  flags for same-named tools over virtual or remote backends.
- **Touches:** `mneme/integrations/langchain/adapter.py` and the integration
  doc. Changes which mutations are enforced, so it needs a charter and a
  `[layer1-freeze]` amendment. No ADR change if the argument mapping is pure
  renaming into existing canonical shapes.
- **Risk:** a wrong declaration (an append tool declared as `Write`) produces
  a wrong introduced delta: false blocks on pre-existing content, or missed
  literals. Mneme cannot detect the mismatch.

### Option 1B: documented "propose mutation" call (recommended)

The custom tool, or the orchestrator code that executes it, computes the
proposed result in a canonical shape and asks the gate before mutating:

```python
mneme = MnemeLangChain(project_dir=root)          # same instance as the middleware

def save_text(path: str, text: str) -> str:
    target = resolve_inside(root, path)            # orchestrator's own boundary policy
    result = mneme.evaluate_tool_call(
        "write_file", {"file_path": str(target), "content": text}
    )
    if result.action == "deny":
        return result.reason                       # returned to the model, nothing written
    note = unevaluated_note(result)                # required when action == "fail_open"
    target.write_text(text, encoding="utf-8")
    return "saved" + note
```

(Illustrative only; `resolve_inside` and `unevaluated_note` are application
code, not Mneme APIs.)

Any custom operation (append, template render, patch) is submitted as the
**full proposed file content** under `write_file`/`Write`; the gate computes
the introduced delta against the current file itself. `edit_file`/`Edit` is
only correct when the tool really performs a single exact replacement.

- **6C fit:** action and wait guarantee are owned by the orchestrator; target,
  content, decision channel and applicability context reuse the gate
  unchanged. Correlation is partial: the orchestrator holds its own call ID
  around the call, but Mneme's trace records the canonical tool (`Write`) with
  no call ID and no custom tool name (`agent_sdk/adapter.py:384-413`).
- **Contract:** no change to the closed map. The middleware still records
  `skip` for `save_text`; the inner call records the real evaluation. The doc
  gains a section describing the call, the canonical shapes, the obligation to
  honor `deny` before mutating and to surface `fail_open` visibly.
- **Touches:** documentation and tests only. No runtime, ADR or freeze change.
- **Risk:** governance depends on the orchestrator author calling the gate and
  honoring the result. Mneme cannot prove a custom tool is wired, so a custom
  tool that does this is "self-governed", not "Mneme-intercepted", in every
  coverage claim.

### Option 1C: a Mneme-supplied tool wrapper

Mneme ships a helper that wraps an arbitrary callable with a canonical
translation and returns a governed tool.

- Same semantics and same declaration risk as 1A, plus a new public API.
  Runtime change in `mneme/`; charter and freeze amendment required. Offers
  little over 1B, whose wrapper is a few lines of application code.

### Option 1D: `mneme check --json` from a non-Python orchestrator

Call the CLI directly with `--input` holding the introduced content and
`--target-path` the resolved target.

- Works without Python bindings, but the caller must reimplement introduced-
  delta selection (ADR-018; whole-file input attributes pre-existing violations
  to the write, the #259 regression shape) and the #484 verdict-trust checks
  (ADR-033 §2). Higher risk of a parallel verdict parser. Acceptable only as a
  documented fallback for non-Python orchestrators; not the recommended path.

### Option 1E: route through the Decision MCP (rejected)

The Decision MCP exposes exactly six approved tools for proposal ingestion
and reads; ADR-027 §3 states MCP ingestion is not enforcement, and the tool
list is part of the authority boundary. Adding a pre-write evaluation tool
would amend ADR-027. Rejected for this workstream.

### Recommendation for Gap 1

**1B**, documentation and tests only. It closes the gap for any orchestrator
willing to call the gate, needs no runtime or frozen-semantics change, keeps
the tool map closed, and keeps coverage claims honest (self-governed, not
intercepted). Revisit 1A in its own charter only if 1B regression evidence
shows the argument-mapping step is where integrators make mistakes.

Two known limits stay open and are recorded rather than fixed here:

- **Correlation.** Neither `evaluate_tool_call` nor `GateResult` carries a call
  ID. An optional pass-through correlation field on the trace would be a small
  additive runtime change; it touches the enforcement trace (ADR-029 evidence
  binding concepts) and needs its own charter.
- **Double recording.** With the custom tool registered under the middleware,
  the trace holds one `skip` (middleware) and one evaluated entry (inner
  call). Coverage reporting must count the evaluated entry and not treat the
  skip as a gap. The tests below pin this.

## 5. Gap 2 options: project-boundary handling

### Option 2A: out of scope, documented precisely (status quo)

Keep the current behavior and state it fully in the integration doc: Mneme
governs mutations inside the memory's policy root; outside it, scoped rules
are `UNKNOWN` (visible fail-open) and unscoped rules still apply (section
2.3). Multi-machine and remote targets are outside Mneme's local-path
semantics, as the doc already says for remote backends.

- **Touches:** documentation only. **Risk:** the asymmetry is surprising;
  documenting it without a test invites drift.

### Option 2B: explicitly unevaluated for every rule outside the root

Classify any target outside the policy root as unevaluated before rule
evaluation, so unscoped rules no longer apply outside the root either.

- Makes behavior uniform, but changes ADR-020 Decision 3 ("no selectors means
  global applicability") for out-of-root inputs and changes which writes are
  denied today. Needs an ADR-020 amendment, a charter and a freeze amendment.
  **Not proposed;** listed so the trade-off is on record.

### Option 2C: blocked by the orchestrator's own policy (recommended, with 2A)

The orchestrator, not Mneme, decides that writes outside the project root are
not allowed. Two layers, both outside `mneme/`:

1. **Root confinement in the tool.** File tools resolve the target and refuse
   any path outside their configured root before calling the gate (the
   `resolve_inside(root, path)` step in option 1B). This is the strongest
   control and does not depend on Mneme at all.
2. **Refusal on UNEVALUATED (optional).** An outer middleware or the
   orchestrator loop calls `evaluate_tool_call` and refuses when `action ==
   "fail_open"` and `evaluation_complete` is false. The refusal is the
   orchestrator's decision and is labeled as such; Mneme's verdict stays
   UNEVALUATED (ADR-033 §1 and §7 forbid presenting an operational refusal as
   a rule FAIL). The shipped middleware has no hook for this, so it must be a
   separate wrapper that decides before the tool handler runs.

- **Touches:** documentation and tests only.
- **Risk:** each orchestrator implements its own policy; Mneme cannot claim it.

### Option 2D: Mneme-side fail-closed for LangChain and the Agent SDK

Extend ADR-033's `closed` availability policy to these adapters.

- Out of ADR-033 scope (§3, §6 and the non-goal on other providers), and C2a
  has no verifier yet. Needs an ADR-033 amendment or a new ADR, a charter and
  a freeze amendment. **Deferred** to the ADR-033 follow-up track; not part of
  this workstream.

### Multi-directory and multi-machine orchestrators

- **Several local roots:** one `MnemeLangChain` per root, routing each
  proposed mutation by its resolved target. This mirrors T-08 slice 1
  (target-based memory selection), which exists only for the Claude Code hook.
  Building it into the adapter would be a runtime change; under 2A + 2C the
  orchestrator routes.
- **Several machines or remote stores:** local-path semantics do not describe
  the mutation target. Out of scope; the only honest label is unevaluated.

### Recommendation for Gap 2

**2A + 2C.** No change to fail-open behavior or policy scope. Document the
boundary semantics including the scoped/unscoped asymmetry, recommend root
confinement in orchestrator tools, and describe the optional refuse-on-
UNEVALUATED wrapper as orchestrator policy. 2B and 2D need architectural
approval and are not proposed here.

## 6. Regression-test proposal

All fixtures synthetic. Two homes, kept apart so the merged post-fix sandbox
evidence stays byte-identical.

### 6.1 Unit and integration tests (`tests/integrations/`)

Use the existing `project` fixture and `check_result_for` stub runner pattern
from `tests/integrations/langchain/test_adapter.py` and
`tests/integrations/agent_sdk/test_adapter.py`, plus the real-checker relative
path helpers in `tests/integrations/relative_paths.py`.

`tests/integrations/langchain/test_custom_tool_proposal.py` (Gap 1, option 1B):

| Test | Setup | Expected |
|---|---|---|
| `test_unmapped_tool_still_skipped` | `evaluate_tool_call("save_text", …)` | `skip`, 0 checker calls (control; complements `test_unlisted_tools_skipped_with_zero_checker_calls`) |
| `test_self_proposal_deny_prevents_mutation` | reference `save_text` calls `evaluate_tool_call("write_file", {abs path, B})`, runner FAIL | `deny`; file digest unchanged; 1 checker call; `--target-path` == resolved target |
| `test_self_proposal_pass_executes` | same with A, runner PASS | `allow`; file written; 1 checker call |
| `test_self_proposal_relative_path_uses_project_dir` | relative path, process cwd holds a decoy (real checker) | `deny`; decoy not read; target unchanged |
| `test_self_proposal_append_submitted_as_full_content` | tool appends a line with the literal; submits full resulting content as `write_file` | `deny`; only the appended line is introduced (ADR-018) |
| `test_self_proposal_preexisting_literal_not_attributed` | target already contains the literal; tool appends a compliant line | `allow` (no #259-shape false block) |
| `test_self_proposal_fail_open_is_visible` | runner `complete=False` | `fail_open`; tool result carries `[mneme] UNEVALUATED`; never reported as `allow` |
| `test_self_proposal_edit_missing_file_fails_open` | `edit_file` shape on a missing target | `fail_open` from `MaterializeError` |
| `test_middleware_skip_plus_inner_evaluation_counted_once` | custom tool under `build_middleware()`, shared instance | trace has 1 `skip` (`save_text`) and 1 evaluated entry; 1 checker call |
| `test_trace_has_no_correlation_id` | inspect trace entry | records `Write`, not `save_text`, and no call ID (characterizes the open limit) |

`tests/integrations/langchain/test_project_boundary.py` (Gap 2), real checker:

| Test | Setup | Expected |
|---|---|---|
| `test_out_of_root_scoped_rule_unknown_fails_open` | rule with `include_paths: ["src/**"]`, absolute target outside root | `fail_open`, `evaluation_complete` false, reason names `PATH_APPLICABILITY_UNKNOWN` |
| `test_out_of_root_unscoped_rule_applies` | same literal, rule without selectors | `deny` (characterization of section 2.3; if it fails, the doc must describe the observed behavior instead) |
| `test_dotdot_relative_escape_is_out_of_root` | `src/../../outside/router.py` relative to `project_dir` | scoped rule: `fail_open`, never `allow` |
| `test_out_of_root_never_labeled_allowed` | scoped rule, compliant content outside root | `fail_open`, not `allow` |
| `test_confined_tool_refuses_before_gate` | reference tool with root confinement | 0 checker calls; nothing written; refusal text not tagged `[mneme]` |
| `test_orchestrator_refuse_on_unevaluated_wrapper` | reference outer wrapper over the gate | handler not run; Mneme trace action stays `fail_open`; refusal labeled as orchestrator policy |

`tests/integrations/agent_sdk/test_custom_tool_proposal.py`: the deny, pass
and relative-path rows above, through `MnemeAgentSdk.evaluate_mutation("Write",
…, cwd=root)`, plus `test_empty_cwd_relative_path_documented` pinning that an
empty `cwd` resolves relative paths against the process cwd
(`docs/integrations/agent-sdk.md:66-68`).

### 6.2 Sandbox extension (live agent, scripted model)

Add new scenarios in a **separate summary** (for example
`evidence/coverage/summary.json` produced by a separate runner flag), so
`evidence/post-fix/summary.json` and
`test_committed_summary_matches_fresh_run` stay unchanged. Reuse the existing
baseline builder, oracle, rule ID and `LABELS`.

| Scenario | Tool path | Expected Mneme label | New field `orchestrator_outcome` | Final oracle |
|---|---|---|---|---|
| `unmapped_tool_literal` (control, rerun) | `save_text`, no proposal | `NOT_EVALUATED` | `none` | reject |
| `custom_tool_self_proposal_literal` | `save_text` with the 1B call, writes B | `BLOCKED` | `none` | accept (file unchanged) |
| `custom_tool_self_proposal_b_then_a` | B denied, then A | `BLOCKED`, `ALLOWED` | `none` | accept |
| `write_outside_project_dir` (control, rerun) | `write_file` outside root | `ERROR_DEGRADED` | `none` | reject |
| `write_outside_project_dir_unscoped_rule` | same, fixture variant with an unscoped copy of the rule | predicted `BLOCKED` (recorded as a prediction; a mismatch is reported, not fixed) | `none` | accept |
| `write_outside_project_dir_confined_tool` | root-confined `write_file` | `NOT_EVALUATED` (0 checker calls) | `REFUSED` | accept |
| `write_outside_project_dir_refuse_unevaluated` | outer refuse-on-UNEVALUATED wrapper | `ERROR_DEGRADED` | `REFUSED` | accept |

Measurement rules for the new set:

- For self-proposal scenarios the tool body runs, so `handler_calls` is 1 even
  on a deny. Add `mutations_executed` (digest changed) and use it, with the
  `[mneme] DENIED` tag, as the BLOCKED evidence.
- `orchestrator_outcome` is separate from the Mneme label. An orchestrator
  refusal never counts as a Mneme block in any metric.
- Report "self-governed custom tool" and "orchestrator-refused out-of-root"
  as their own metric rows. The existing 6/8 (7/9) literal-sensitivity figures
  are not recomputed with these scenarios.
- Tests: `test_self_proposal_blocks_without_mutation`,
  `test_controls_unchanged_from_post_fix`,
  `test_orchestrator_refusal_not_counted_as_mneme_block`,
  `test_unscoped_out_of_root_prediction_recorded`,
  `test_post_fix_summary_untouched`.

## 7. What would change, by option

| Option | `mneme/` | ADRs | Freeze amendment | Integration docs | Tests |
|---|---|---|---|---|---|
| 1A registration | yes | none if pure renaming | yes | yes | yes |
| **1B propose-mutation** | no | none | no | yes | yes |
| 1C wrapper | yes | none | yes | yes | yes |
| 1D CLI direct | no | none | no | yes (fallback) | optional |
| 1E Decision MCP | yes | ADR-027 | yes | yes | yes |
| **2A documented scope** | no | none | no | yes | yes |
| 2B uniform unevaluated | yes | ADR-020 | yes | yes | yes |
| **2C orchestrator policy** | no | none | no | yes | yes |
| 2D fail-closed rollout | yes | ADR-033 | yes | yes | yes |
| Correlation ID passthrough | yes | none expected (ADR-029 concepts reused) | yes | yes | yes |

## 8. Proposed next steps (each its own PR, none started)

1. The tests in 6.1 that need no runtime change, with the reference
   `save_text`, root-confined tool and refuse-on-UNEVALUATED wrapper living in
   test code.
2. Integration doc update (`langchain-langgraph.md`, `agent-sdk.md`): a
   "custom tools" section describing 1B, and a "project boundary" section
   describing 2A/2C, including the scoped/unscoped asymmetry once
   `test_out_of_root_unscoped_rule_applies` pins it.
3. Sandbox coverage set in 6.2, as a separate evidence directory.
4. Only on owner approval: a charter for a correlation field, and any of 1A,
   2B or 2D.

## 9. Out of scope

Semantic enforcement of C2/C3 and any new rule type; orchestrator governance
(P0 track); shell/`execute` and raw `StateGraph` paths; virtual or remote
backends; changes to fail-open defaults or ADR-033 scope; any change to the
merged sandbox evidence.
