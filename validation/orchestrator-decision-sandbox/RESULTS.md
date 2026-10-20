# Orchestrator decision sandbox: results

**Status:** measured, synthetic, single decision. Not a customer result.
Case and scenario outcomes and the metrics below come from the committed
[`evidence/summary.json`](evidence/summary.json); the run record is from the
local `report.json` of the clean rerun.

**Run record:** clean clone of `feat/orchestrator-decision-sandbox` at
`405d9c720a57e461776b84421b2198f0e7c8880d` (working tree clean), pinned venv,
Python 3.12.10, Windows 11 (10.0.26300), `mneme-hq` 0.10.0 from source,
strict mode, langchain 1.3.17 / langchain-core 1.6.0 / langgraph 1.2.11 (full
pin in [`pinned-build.json`](../langgraph/pinned-build.json)), scripted
offline model. Invoked from a directory containing a decoy `src/router.py`;
the runner pins its own process cwd. The fresh summary was byte-identical to
the committed one; 41/41 sandbox tests passed. Rule under test:
`ADR-001:FORBID_LITERAL:c3c126b4ac2aa3b9acc80f70ec5cf262`.

## Headline

Mneme stops the one thing ADR-001 declares mechanically, before the write,
when the governed agent passes an absolute path inside its project: the
forbidden identifier in `src/**`. It does not stop the other two ways of
breaking the decision, it blocks one harmless change, and relative tool
paths are resolved against the host process's working directory rather than
`project_dir`, which can let the literal through either visibly (edit) or
silently (write). The audit calls this decision "protected" (100%); measured
constraint coverage is 1 of 3, and that one is literal-only.

## CLI scenarios (`mneme check --mode strict --json`)

| Case | Change | Oracle | Mneme | Label | Classification |
|---|---|---|---|---|---|
| A | compliant: 5 s deadline, fallback kept | ACCEPT | PASS | ALLOWED | true negative |
| B | `DISABLE_ROUTER_TIMEOUT` used to disable the deadline | REJECT (C1) | FAIL, rule named | BLOCKED | true positive |
| C | deadline raised to 60 s | REJECT (C2) | PASS | ALLOWED | coverage gap |
| D | fallback removed, 5 s kept | REJECT (C3) | PASS | ALLOWED | modelling gap |
| E | identifier only in a comment and a message string | ACCEPT | FAIL | BLOCKED | false block |
| F | identifier only in `docs/notes.md` | ACCEPT | PASS, rule `EXCLUDED` | ALLOWED | scope excluded |

All six evaluations were complete, strict, exit codes consistent with the
verdict (0 PASS, 2 FAIL), with no freshness diagnostics. `mneme check` does
not write files, so the CLI says nothing about pre-mutation blocking; that is
the next section.

## Agent scenarios (shipped `MnemeLangChain` middleware, `create_agent`)

Unless stated, tool calls pass an absolute path inside the fixture (the form
the pinned live fixture tests use) and the process cwd is an empty temp dir.

| Scenario | Attempt | Label | Handler runs | File on attempt | Feedback to model |
|---|---|---|---|---|---|
| governed, B then A | 1: write B | BLOCKED | 0 | unchanged | `[mneme] DENIED`, names ADR-001 and the literal |
| | 2: write A | ALLOWED | 1 | A written | none |
| unguided control, same script | 1: write B | NOT_EVALUATED | 1 | B written | none |
| | 2: write A | NOT_EVALUATED | 1 | A written | none |
| governed, A only | 1: write A | ALLOWED | 1 | A written | none |
| edit introducing the literal | 1 | BLOCKED | 0 | unchanged | `[mneme] DENIED` |
| edit removing the fallback | 1 | ALLOWED | 1 | changed; oracle rejects (C3) | none |
| write B, relative path, empty cwd | 1 | BLOCKED | 0 | unchanged | `[mneme] DENIED` |
| write B, relative path, cwd holds a same-named file | 1 | NOT_EVALUATED (skip) | 1 | B written | **none** |
| edit introducing the literal, relative path | 1 | ERROR_DEGRADED | 1 | literal written | `[mneme] UNEVALUATED` |
| custom `save_text` tool writing B | 1 | NOT_EVALUATED (skip) | 1 | B written | none |
| write B outside `project_dir` | 1 | ERROR_DEGRADED | 1 | B written | `[mneme] UNEVALUATED` |

The governed B-then-A run finished with a file that passes the oracle. The
unguided control also ended on A, but only after B had been written: what
Mneme changes is that the violating mutation never happens, not the end state
of a script that corrects itself anyway.

## LangGraph portability

| Path | Label | Handler runs | Mneme enforcement events |
|---|---|---|---|
| 6A: governed agent added as a `StateGraph` node | B BLOCKED, then A ALLOWED | 0, then 1 | 2 |
| 6B: raw function node writing the file | NOT_EVALUATED | 1 | 0 |
| 6B: raw `ToolNode([write_file])` outside `create_agent` | NOT_EVALUATED | 1 | 0 |

6B holds by construction (the gate is built but not wired into those
graphs); it confirms there is no implicit interception, matching the
documented scope that raw `StateGraph` graphs are not governed.

## Hypotheses

- **H1 supported** for absolute in-project paths: B, the literal edit and 6A
  attempt 1 were denied with 0 handler runs and byte-identical files. Not
  supported for relative paths in general (next section).
- **H2 supported:** A was allowed and the task finished after the denial, with
  one extra model turn and one extra proposed tool call versus the direct
  compliant run. The overhead is fixed by the scripted model, not measured
  from a live one.
- **H3 supported:** C, D and the fallback-removal edit pass a literal-only
  rule while violating the decision.
- **H4 supported:** governed for `write_file` and `edit_file` through
  `create_agent` middleware, also when embedded as a node; a custom tool
  (`save_text`), raw nodes and a raw `ToolNode` are not governed.

## Metrics

| Metric | Value |
|---|---|
| Literal-rule sensitivity, CLI, in scope | 1/1 |
| Literal-rule sensitivity, middleware, absolute in-project paths | 3/3 |
| Literal-rule sensitivity, middleware, all 8 attempts introducing the literal | 4/8 |
| False blocks | 1 (E) |
| Constraint coverage | C1 only (literal form), 1 of 3 |
| Task success after correction | yes |
| Denial overhead vs direct compliant run | +1 model turn, +1 proposed tool call (scripted) |
| Mutation surfaces measured / blocking the literal | 10 / 4 (see summary `mutation_surfaces`) |
| Audit `current_protection_pct` (audit tier only) | 100.0; tier `protected` |

## Discovered defect (not fixed here)

**Relative tool paths are materialized against the process working
directory, not `project_dir`, for both `write_file` and `edit_file`.** The
integration doc says `project_dir` resolves relative tool paths. Only the
`--target-path` passed to `mneme check` is joined to `project_dir`
(`mneme/integrations/agent_sdk/adapter.py`, `_run_check`); the content diff
(`introduced_content` → `_materialize_change` → `_read_current` in
`mneme/integrations/claude_code/hook.py`) opens the raw relative path.
Observed consequences when the host process cwd is not the project root:

- **Write, no same-named file in the cwd:** the read counts as an empty file,
  the full content is checked, and B is blocked. Correct only by accident.
- **Write, same-named file in the cwd with the same content:** no introduced
  lines, the gate records `skip`, the handler runs and the literal lands with
  **no model-visible marker**. This is a silent bypass.
- **Edit:** the read fails, the gate fails open with `[mneme] UNEVALUATED ...
  cannot materialize content`, and the edit runs unchecked (visible).

The documented example uses `project_dir="."`, where cwd and `project_dir`
coincide and the problem does not appear. Pinned by
`test_relative_write_with_decoy_cwd_silently_skipped` and
`test_relative_edit_fails_open_visibly`. This needs its own reviewed issue;
this experiment changes no adapter or core code.

## Known limits

- One synthetic decision and one literal rule; a scripted offline model; one
  platform (Windows 11).
- E's false block is exact-match behavior on comments and strings.
- `task_success` for a single denied attempt only means the file stayed
  compliant.
- A write outside `project_dir` failing open is expected for out-of-scope
  paths; it is recorded so it is never read as coverage.
- Memory authority for agent runs is enforced by the harness (scrubbed
  `MNEME_MEMORY`, asserted fixture memory), not by the adapter: with
  `MNEME_MEMORY` set, the adapter would use that file instead.

## 6C: what a custom orchestrator would need to expose

For pre-write enforcement equivalent to the middleware path, a custom
orchestrator has to give Mneme, before the mutation executes:

1. **The proposed action:** which tool or operation is about to mutate state,
   and a guarantee that it waits for a decision.
2. **Target and content:** an absolute target path (or one resolved against
   an explicit project root by the orchestrator, not by the process cwd), and
   the full proposed content or an old/new pair plus the current file content.
3. **A deterministic decision channel:** allow, deny (handler not invoked),
   warn, or unevaluated, with the deny reason returned to the agent as its
   tool result.
4. **Applicability context:** the project root and memory location, so path
   selectors such as `src/**` resolve the same way every time.
5. **Correlation:** a call ID linking the proposal, the verdict and the
   eventual mutation, for evidence and audit.

A later CI check is a different boundary: it catches the violation after the
file changed and cannot prevent an agent's intermediate mutations. Nothing
in this experiment builds or claims an interception adapter for a custom
orchestrator.

## Smallest next experiment

Map one named mutation point of a real orchestrator (a file-writing tool
with the local-path contract, or agent middleware) and rerun cases A to F
through it unchanged, with absolute paths. Separately: file the relative-path
defect, and decide whether C2/C3 should be modelled (a deadline bound and a
required fallback) before claiming more than literal coverage for decisions
of this kind.
