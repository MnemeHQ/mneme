# Custom tools and project boundaries

How an orchestrator's own file tools can ask Mneme's existing gate before
they change a file, and what Mneme does and does not cover at the edge of a
project. This is a **reference pattern**, not a new integration: it reuses
`MnemeLangChain.evaluate_tool_call` and `MnemeAgentSdk.evaluate_mutation`
unchanged. No runtime behavior, enforcement semantics or ADR changed to make
it work.

Design: [`docs/plans/2026-10-20-enforcement-coverage-custom-tools-and-project-boundary.md`](../plans/2026-10-20-enforcement-coverage-custom-tools-and-project-boundary.md)
(option 1B for custom tools, options 2A + 2C for the project boundary).
Evidence: the reference tests listed under [Evidence](#evidence). Everything
below describes behavior those tests pin; nothing here is a guarantee beyond
them.

---

## Self-governed is not intercepted

Two different things can govern a file mutation, and coverage claims must
keep them apart:

| Kind | How it is governed | Who guarantees it |
|---|---|---|
| **Intercepted** | The shipped middleware or hook sees the call before it runs: `write_file` / `edit_file` through [LangChain agent middleware](langchain-langgraph.md), `Write` / `Edit` / `MultiEdit` through the [Agent SDK](agent-sdk.md) and [Claude Code](claude-code.md) hooks | Mneme's adapter, for the tool names in its closed map |
| **Self-governed** | A custom tool calls the gate itself before mutating, and honours the answer | The orchestrator author, for each tool they wire |

The tool map stays closed. A custom tool (for example `save_text`) that
never calls the gate is **ungoverned**: the middleware records `skip` for it
and the mutation runs with no check and no `[mneme]` marker
(`test_unmapped_tool_still_skipped`, `test_unwired_tool_mutates_without_any_check`,
`test_unwired_tool_under_middleware_is_ungoverned`). Installing Mneme does not
make every mutation pass through it, and Mneme cannot prove that a custom
tool is wired. Report a wired custom tool as "self-governed", never as
"Mneme-intercepted", and count an unwired one as ungoverned.

## Custom-tool integration (option 1B)

A custom tool that wants Mneme's decision before it changes a file:

1. **Canonicalize the target once.** Resolve the path (`Path.resolve()`
   follows symlinks and removes `..`). Join a relative agent path to the
   project root yourself, so the gate always receives an absolute path.
2. **Apply your own boundary policy** to that canonical path (see
   [Project boundaries](#project-boundaries)). A refusal here is your
   policy, not a Mneme decision.
3. **Submit the same path and the exact bytes you will write** to the gate in
   a canonical shape:
   - `write_file` / `Write` with the **full resulting file content**, for any
     operation (save, append, template render, patch). The gate computes the
     introduced lines against the current file itself (ADR-018), so a
     violation already present in the file is not attributed to your change
     (`test_self_proposal_append_submitted_as_full_content`,
     `test_self_proposal_preexisting_literal_not_attributed`).
   - `edit_file` / `Edit` only when the tool really performs one exact
     replacement of `old_string` with `new_string`.
4. **Read only `GateResult.action` and `GateResult.reason`.** Verdict trust
   (`assess_verdict`) already happens inside the adapter. Do not parse
   `mneme check` output yourself or add a second verdict parser.
5. **Honour the action before mutating**, then write exactly what you
   submitted, to the path you submitted.

```python
from pathlib import Path
from mneme.integrations.langchain import MnemeLangChain

mneme = MnemeLangChain(project_dir=root)       # the same instance as the middleware
ROOT = Path(root).resolve(strict=True)

def save_text(path: str, text: str) -> str:
    target = (ROOT / path).resolve()           # canonical: symlinks followed, ".." removed
    if not target.is_relative_to(ROOT):        # orchestrator policy, not a Mneme verdict
        return "[orchestrator] REFUSED - target outside project root"
    data = text.encode("utf-8")                # the exact bytes that will be written
    result = mneme.evaluate_tool_call(
        "write_file", {"file_path": str(target), "content": data.decode("utf-8")}
    )
    if result.action == "deny":
        return "[mneme] DENIED - " + (result.reason or "architectural decision violated")
    if result.action == "allow":
        note = ""                              # the only trusted PASS
    elif result.action == "warn":
        note = ("\n[mneme] WARN - architectural decision flagged "
                "(warn mode; not blocked):\n" + result.reason)
    elif result.action == "fail_open":
        note = ("\n[mneme] UNEVALUATED - failing open, this mutation was "
                "NOT checked:\n" + result.reason)
    elif result.action == "skip":
        note = "\n[mneme] NOT EVALUATED - " + result.reason
    else:
        raise ValueError(f"unhandled gate action: {result.action!r}")
    try:
        target.write_bytes(data)               # same resolved path, same bytes
    except OSError as exc:
        return f"error: {exc}{note}"           # not mutated; keep the Mneme note
    return "saved" + note
```

This is illustrative application code, not a Mneme API. The tested reference
is `ReferenceFileTool` in
[`tests/integrations/custom_tool_reference.py`](../../tests/integrations/custom_tool_reference.py);
the Agent SDK form passes `Write` / `Edit` to
`MnemeAgentSdk.evaluate_mutation(..., cwd=<project root>)` instead
(`tests/integrations/agent_sdk/test_custom_tool_proposal.py`). The `DENIED`,
`WARN` and `UNEVALUATED` tags are the strings the shipped middleware emits
(`test_reference_tags_match_middleware`); the middleware emits nothing for a
skip, so `NOT EVALUATED` is application wording.

### Every outcome has exactly one treatment

| `action` | Mutation | Feedback to the agent | Report it as |
|---|---|---|---|
| `deny` | **not performed**; the file stays byte-identical | `[mneme] DENIED - <reason>`, naming the decision | Mneme block |
| `allow` | performed once | none required | trusted, complete PASS |
| `warn` | performed (existing warn-mode semantics) | `[mneme] WARN ... not blocked` kept visible | flagged, not blocked |
| `fail_open` | performed under the documented fail-open policy, unless the orchestrator refuses separately | `[mneme] UNEVALUATED ... NOT checked`, with the reason | unevaluated |
| `skip` | not decided by Mneme | the skip reason, never phrased as approval | not evaluated |

Only `allow` is a PASS. An unevaluated or skipped operation, and an operation
in a project with no Mneme memory, must never be presented as a trusted PASS
or as evidence of a successful architectural check.

Pinned by: `test_self_proposal_deny_prevents_mutation`,
`test_self_proposal_pass_executes`,
`test_self_proposal_warn_mode_proceeds_visibly`,
`test_self_proposal_fail_open_is_visible`,
`test_self_proposal_no_memory_is_not_a_pass` (no memory is a `skip`, not a
PASS), `test_self_proposal_untrusted_output_is_not_a_pass` (an inconsistent
or unparseable `mneme check` result is `fail_open`, never `allow`), and
`test_self_proposal_edit_missing_file_fails_open` (an edit whose current file
cannot be read fails open before any check runs).

### Same path, same bytes

The file Mneme evaluates must be the file the tool changes, with the same
content. Canonicalize once, check that canonical path, submit it, and write
the submitted bytes to it. A symlink inside the root that points outside it
resolves to the outside path: a confined tool refuses it before asking
Mneme, and an unconfined tool has it evaluated as the out-of-root target it
really is, never as the in-root link path a `src/**` rule would match
(`test_self_proposal_evaluated_path_and_bytes_match_mutation`,
`test_self_proposal_symlink_out_of_root_refused`).

The window between the check and the write (for example a symlink swapped
after evaluation) is a known limit of any check-then-act tool. It is
recorded here, not solved.

### Relative paths

Relative tool paths are resolved against the gate's `cwd`: `project_dir`
for `MnemeLangChain` (unless an explicit `cwd` is passed to
`evaluate_tool_call`), and the `cwd` argument for
`MnemeAgentSdk.evaluate_mutation`, never the host process's working directory
(`test_self_proposal_relative_path_uses_project_dir`). With an empty `cwd`,
the Agent SDK leaves relative paths relative to the process cwd (see
[agent-sdk.md](agent-sdk.md)): the current-file snapshot is read from the
process cwd, so the introduced lines can be computed against the wrong file,
and the result can be `skip` or `fail_open` with UNKNOWN applicability
(`TestEmptyCwdRelativePathDocumented`). The reference pattern avoids this by
always submitting an absolute canonical path.

### Under the shipped middleware

A self-governed custom tool can run inside an agent that also has Mneme's
middleware. The middleware records `skip` for the custom tool name and the
tool's own call records the real evaluation. Count the evaluated entry once
and ignore the middleware `skip` for coverage
(`test_middleware_skip_plus_inner_evaluation_counted_once`).

## Project boundaries

What happens to a write outside `project_dir` depends on the rule. It is
neither universally ungoverned nor universally blocked:

| Project memory | Out-of-root target | Result |
|---|---|---|
| Contains any path-scoped typed rule (`include_paths`) | that rule's applicability is `UNKNOWN` (ADR-020), so the whole evaluation is incomplete | `fail_open` (rendered `[mneme] UNEVALUATED` by the middleware or the reference tool), never `allow`, **even when an unscoped rule in the same memory is violated** (`test_out_of_root_scoped_rule_unknown_fails_open`, `test_dotdot_relative_escape_is_out_of_root`, `test_out_of_root_never_labeled_allowed`) |
| Only unscoped typed rules | each rule is `APPLIED` without path normalization | evaluated against the project's memory: in strict mode a violation is `deny` (`warn` in warn mode) and compliant content is `allow` (`test_out_of_root_unscoped_rule_applies`, single-rule memory) |

A memory that mixes both rule kinds gets the first row: an out-of-root write
is unevaluated, not blocked. The unscoped row characterizes current
behavior for an all-unscoped memory; the mixed-memory case follows from the
adapter checking evaluation completeness before the verdict and is not yet
pinned by its own test. If either changes, this page must change with it.

**Confinement is the orchestrator's policy (option 2C).** Mneme does not
decide which directories an orchestrator may write to. Orchestrators that
work across several directories or machines should define their permitted
roots themselves and refuse targets outside them before calling the gate
(`test_confined_tool_refuses_before_gate`). A refusal is reported as an
orchestrator refusal, with no `[mneme]` marker and no Mneme action.

**Remote and virtual backends are unsupported.** The gate's path semantics
are local-filesystem semantics. Same-named tools over virtual or remote
backends are not covered by this pattern; see
[langchain-langgraph.md](langchain-langgraph.md#scope).

### The refuse-on-UNEVALUATED wrapper is not fail-closed

The reference tests include an optional orchestrator wrapper that asks the
gate first and refuses a mutation Mneme could not evaluate
(`refuse_on_unevaluated` in
[`tests/integrations/custom_tool_reference.py`](../../tests/integrations/custom_tool_reference.py)).
It refuses only `fail_open` with `evaluation_complete: false`, which is an
**incomplete applicability evaluation** such as an out-of-root target under a
scoped rule (`test_orchestrator_refuse_on_unevaluated_wrapper`). It does
**not** refuse operational fail-opens, for example an edit whose current file
cannot be read: those are `fail_open` with `evaluation_complete: true` in the
existing `GateResult`, and the handler runs
(`test_wrapper_does_not_refuse_operational_fail_open`). A `deny` still stops
the handler (`test_wrapper_deny_does_not_run_handler`).

Do not describe this wrapper as universal fail-closed protection. Mneme's own
fail-open policy is unchanged; opt-in fail-closed handling is
[ADR-033](../adr/ADR-033-opt-in-fail-closed-enforcement.md)'s separate track
and is not provided by this pattern.

## Reporting and evidence

Keep orchestrator refusals separate from Mneme results in every count and
report. A refusal never becomes a Mneme block or rule violation, and it does
not change the Mneme result of the same attempt. The reference counter uses
these rows (`test_orchestrator_refusals_counted_separately_from_mneme_blocks`):

| Row | Source |
|---|---|
| `mneme_blocked` | `deny` |
| `trusted_pass` | `allow` only |
| `warned_not_blocked` | `warn` |
| `unevaluated` | `fail_open` |
| `not_evaluated` | `skip`, or the gate was not called |
| `orchestrator_refused` | the orchestrator's own refusal, counted separately |

`orchestrator_refused` is an extra tally: each attempt also keeps its Mneme
row (`not_evaluated` when a confined tool refused before calling the gate,
`unevaluated` when the wrapper refused a `fail_open`). Row totals can
therefore exceed the number of attempts.

Use the existing evidence concepts rather than a new contract: Mneme's
trace, the evidence dimensions of
[ADR-029](../adr/ADR-029-enforcement-evidence-binding-semantics.md), and the
CI1 principles (tracker #540) reused in the design's section 5A: trusted
result, evaluation completeness and negative space. Only a trusted, complete
result is a PASS, and what was not evaluated is reported as such. CI1
production merge blocking is not adopted; this page describes the
pre-mutation boundary only.

One limit is open: the trace records the canonical tool (`Write`) with no
call ID and no custom tool name (`test_trace_has_no_correlation_id`). Keep
your own call ID around the gate call if you need to correlate a proposal,
its verdict and the mutation.

## Evidence

All on `main` since MnemeHQ/mneme#581:

- [`tests/integrations/custom_tool_reference.py`](../../tests/integrations/custom_tool_reference.py):
  reference tool, outcome counter and refuse-on-UNEVALUATED wrapper (test code,
  not a Mneme API).
- [`tests/integrations/langchain/test_custom_tool_proposal.py`](../../tests/integrations/langchain/test_custom_tool_proposal.py):
  outcomes, same path and bytes, relative paths, full-content submission,
  trace shape, and two tests under the shipped middleware (need the
  `langchain` extra).
- [`tests/integrations/agent_sdk/test_custom_tool_proposal.py`](../../tests/integrations/agent_sdk/test_custom_tool_proposal.py):
  the same pattern through the Agent SDK gate, including the empty-`cwd`
  characterization.
- [`tests/integrations/langchain/test_project_boundary.py`](../../tests/integrations/langchain/test_project_boundary.py):
  scoped and unscoped out-of-root behavior, confinement, the wrapper and its
  limit, and separate counting. Real `mneme check` CLI throughout.

The original measurement of the gap is the orchestrator decision sandbox
([`validation/orchestrator-decision-sandbox/RESULTS.md`](../../validation/orchestrator-decision-sandbox/RESULTS.md)):
of its 8-attempt literal set, a custom tool and a write outside
`project_dir` were the two the shipped middleware did not block (raw graph
paths, outside that set, were also ungoverned).

## Out of scope

Automatic interception of custom tools (a Mneme-side tool map extension or
wrapper), Mneme-side fail-closed for out-of-root writes, shell and `execute`
tools, raw `StateGraph` nodes, and remote or virtual backends. Each would
need its own evidence and architecture approval.
