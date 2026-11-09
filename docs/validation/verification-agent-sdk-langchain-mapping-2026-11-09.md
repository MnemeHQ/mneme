# Verification: Agent SDK and LangChain evidence mapping

**Date:** 2026-11-09
**Pinned implementation:** `main` at `94a2b28f` (runtime unchanged since v0.11.0 `619d5405`)
**Type:** read-only mapping. No runtime, adapter, schema, CI, ADR or policy
change. Authorizes nothing.

## 1. Purpose and boundaries

This record completes step 1 ("residual mapping") of the bounded Verification
slice in [`docs/roadmap/README.md`](../roadmap/README.md). It maps the two
integration surfaces the
[ADR-029 evidence completeness audit](adr029-evidence-completeness-audit-2026-11-08.md)
(#761) did not cover to the six binding dimensions of
[ADR-029](../adr/ADR-029-enforcement-evidence-binding-semantics.md) §2. It
uses the same legend and the same accepted per-rule configuration ruling
(#761 §5.1).

Layering used here: **Governance** decides which decisions are authoritative
(ADR-031); **Guidance** injects them before work; **Enforcement** prevents or
rejects prohibited changes; **Verification** assesses what the evidence
records from those layers actually prove. This record is Verification only.
It decides no authority and changes no enforcement.

## 2. Surfaces

| Surface | Code | What it records |
|---|---|---|
| Claude Agent SDK adapter | `mneme/integrations/agent_sdk/adapter.py` (`MnemeAgentSdk`) | `trace`: an in-memory list of dicts, one per context injection and per gate decision. `GateResult`: returned to the caller, carries the full `mneme.check/v1` `payload` when the result is trusted |
| LangChain adapter + middleware | `mneme/integrations/langchain/adapter.py` (`MnemeLangChain`), `middleware.py` | Delegates every governed call to `MnemeAgentSdk.evaluate_mutation`, so it shares the same `trace` and `GateResult`. Adds its own trace entries only for unmapped-tool skips and un-annotatable `Command` results |

Both adapters run `mneme check --json` exactly as the Claude Code hook's
general path does: `--input <temp file of introduced content>`,
`--target-path <file>`, `--query "edit to <file>"`. Neither uses the hook's
routed `--proposed-new-file` path.

## 3. Completeness matrix

Legend as in #761 §3: **bound** = deterministic identifier in the surface's
own record for the same evaluation; **joined** = only by joining records the
surface did not emit itself; **absent** = not carried.

Two records exist per gate decision and they differ, so both are shown.

### 3.1 Literal-tier rules (`FORBID_LITERAL`)

| # | Dimension | `trace` enforcement entry | `GateResult.payload` (trusted results only) |
|---|---|---|---|
| 1 | control / provenance | **absent.** No Mneme version, no surface id. Delegated LangChain calls carry no `via` marker, so a LangChain decision is indistinguishable from an Agent SDK one | **absent.** Same as the CLI (#761 E-2): no `subject` record for literal-only checks |
| 2 | subject | **absent.** `file_path` only; no digest of the checked content | **absent.** No digest. For `Edit`/`MultiEdit` the checked input is the introduced lines, not the resulting file |
| 3 | decision | **absent** | **bound** on canonical memory (`decision_id`, `decision_version_id`) |
| 4 | rule | **absent** | **bound** (ADR-030 §7 `rule_id`) |
| 5 | applicability | **absent** | **bound** (`APPLIED` / `EXCLUDED` / `UNKNOWN` per rule) |
| 6 | outcome | **partial.** One `action` (`allow`/`deny`/`warn`/`fail_open`/`skip`) and `verdict` per event, not per rule; `reason` is free text | **partial.** Reject attributable via the violation's `rule_id`; allow is only the absence of a violation (#761 E-3) |
| – | configuration (per rule, #761 §5.1) | **absent** | **bound** via `rule_id` + `decision_version_id` |

### 3.2 Numeric rules (`FORBID_NUMERIC_ABOVE`)

Neither adapter routes a new-file `Write` through `--proposed-new-file`, so
the checker sees unverified input and every applied numeric rule is
`MATCHER_UNEVALUATED` (ADR-034 §6). The adapter docstrings already say no
pre-write numeric detection is claimed. Dimension 6 is never decided for a
numeric rule on these surfaces; the payload otherwise binds as in #761 §3.2.

### 3.3 Guidance records (`kind: "context_injection"`)

Context-injection entries carry `query`, `outcome`
(`INJECTED`/`EMPTY`/`NO_MEMORY`), retrieved `decision_ids` and `memory_path`.
They record Guidance, not enforcement: no version, rule, applicability or
outcome. They never count toward any ADR-029 level.

## 4. Probes

Run in the task worktree at `94a2b28f`, `mneme` 0.11.0, against the repo's
own canonical memory, calling the adapters directly (no SDK or LangChain
runtime needed):

| Call | Result | `trace` entry keys | `payload` |
|---|---|---|---|
| Agent SDK `Write` `docs/probe.md` with the ADR-005 forbidden install line, `warn` | `action=warn`, `verdict=FAIL` | `action, evaluation_complete, file_path, kind, reason, tool, verdict` | present; no `subject`; `ADR-005:FORBID_LITERAL:cbf4d27…`, `dver-d6631efd…`, `APPLIED`; violation with the same `rule_id` |
| Agent SDK `Write`, benign content | `action=allow`, `verdict=PASS` | same | present; same rule `APPLIED`, zero violations (allow inferred, not recorded) |
| LangChain `edit_file` on an existing file introducing the forbidden line, `strict` | `action=deny`, `verdict=FAIL` | same, `tool: "Edit"`, **no `via`** | present; same rule `APPLIED` |
| LangChain `edit_file` on a missing file | `action=fail_open` | same | absent (`MaterializeError`) |
| LangChain unmapped tool `shell` | `action=skip` | adds `via: "langchain"` | absent |

## 5. Findings

| ID | Finding | Kind |
|---|---|---|
| V-1 | **Neither surface reaches relevant enforcement observed for any rule type.** Best case is the in-memory `GateResult.payload`, which binds dimensions 3, 4, 5, per-rule configuration and the reject half of 6, the same as the CLI. Dimensions 1 and 2 are absent. This is execution observed. | scope fact |
| V-2 | **The `trace` drops all rule identity.** Its enforcement entries keep no `rule_id`, `decision_version_id`, applicability or digest. Any Verification built on `trace` alone is limited to "a gate ran and returned this action". | gap, adapter change |
| V-3 | **`GateResult.payload` is caller-held and discarded by the LangChain middleware.** `ToolGateMiddleware` uses only `action` and `reason`. A LangChain agent run keeps no identity-bearing record unless the caller calls `evaluate_tool_call` directly. | gap, adapter change |
| V-4 | **LangChain decisions carry no surface marker.** Delegated enforcement entries are written by the Agent SDK adapter without `via`, so control provenance cannot separate the two surfaces from the trace. | gap, adapter change |
| V-5 | **No subject digest anywhere**, and for `Edit`/`MultiEdit` the checked subject is the introduced lines. A claim about the resulting file is a different subject (ADR-029 §2 mismatch). | gap; partly by design |
| V-6 | **No pre-write numeric decision.** No `--proposed-new-file` routing, so numeric rules stay `MATCHER_UNEVALUATED`. The #761 E-1 path does not extend to these surfaces. | scope fact, consistent with adapter docs |
| V-7 | **Fail-open and skip are visible, not silent.** Every `fail_open` and `skip` is in `trace`, and the agent sees an UNEVALUATED marker. This meets ADR-029's fail-closed rule for *claims*: none of these can be read as enforcement. | conforming |
| V-8 | **The trace is in-memory and per-instance.** Nothing persists it, consistent with ADR-029 §7 (no evidence store). Verification needs the caller to capture it. | scope fact |

## 6. Consequences for the Verification slice

1. Step 1 (residual mapping) is complete. No v0.11.0 integration surface adds
   a relevant-enforcement path beyond #761 E-1.
2. The step 2 negative controls can include these surfaces with no runtime
   change. Expected result for each: at or below execution observed. This
   covers `fail_open` on materialization failure, unmapped-tool `skip`, and
   an `EXCLUDED` rule through `GateResult.payload`.
3. Closing V-2 to V-5 would mean adapter changes: keeping identity fields in
   `trace`, a surface marker, and a subject digest. Each is a runtime change
   and needs its own charter. None is authorized here. Literal-rule relevance
   would still be blocked by #761 E-2 and E-3, which these adapters inherit
   from the CLI.

## 7. What this record does not claim

- No surface or path is newly claimed as relevant enforcement observed.
- No coverage claim for LangChain tools outside `LANGCHAIN_FILE_TOOLS`, or
  for raw `StateGraph` graphs.
- No change to Audit tiers, enforcement behavior or the adapters' policy.
