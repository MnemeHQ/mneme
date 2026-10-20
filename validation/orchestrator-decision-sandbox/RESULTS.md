# Orchestrator decision sandbox: results

**Status:** measured, synthetic, single decision. Not a customer result.
Every number below comes from the committed
[`evidence/summary.json`](evidence/summary.json).

**Run record:** clean clone of `feat/orchestrator-decision-sandbox` at
`1aba0ae6e6448bd9449c8a23d60620447748cd0f`, fresh venv, Python 3.12.10,
Windows 11 (10.0.26300), `mneme-hq` 0.10.0 from source, strict mode,
langchain 1.3.17 / langchain-core 1.6.0 / langgraph 1.2.11 (full pin in
[`pinned-build.json`](../langgraph/pinned-build.json)), scripted offline
model. The fresh summary was byte-identical to the committed one; 33/33 sandbox
tests passed. Rule under test: `ADR-001:FORBID_LITERAL:c3c126b4ac2aa3b9acc80f70ec5cf262`.

## Headline

Mneme stops the one thing ADR-001 declares mechanically, before the write,
on the supported paths: the forbidden identifier in `src/**`. It does not
stop the other two ways of breaking the decision, it blocks one harmless
change, and two mutation paths through the governed agent fail open.
The audit calls this decision "protected" (100%); measured constraint
coverage is 1 of 3, and that one is literal-only.

## CLI scenarios (`mneme check --mode strict --json`)

| Case | Change | Oracle | Mneme | Label | Classification |
|---|---|---|---|---|---|
| A | compliant: 5 s deadline, fallback kept | ACCEPT | PASS | ALLOWED | true negative |
| B | `DISABLE_ROUTER_TIMEOUT` used to disable the deadline | REJECT (C1) | FAIL, rule named | BLOCKED | true positive |
| C | deadline raised to 60 s | REJECT (C2) | PASS | ALLOWED | coverage gap |
| D | fallback removed, 5 s kept | REJECT (C3) | PASS | ALLOWED | modelling gap |
| E | identifier only in a comment and a message string | ACCEPT | FAIL | BLOCKED | false block |
| F | identifier only in `docs/notes.md` | ACCEPT | PASS, rule `EXCLUDED` | ALLOWED | scope excluded |

All six evaluations were complete (`evaluation_complete: true`), strict, with
no freshness diagnostics. The CLI never wrote the target. A CLI verdict is
not pre-mutation evidence; that is the next section.

## Agent scenarios (shipped `MnemeLangChain` middleware, `create_agent`)

| Scenario | Attempt | Label | Handler runs | File unchanged on attempt | Feedback to model |
|---|---|---|---|---|---|
| governed, B then A | 1: write B | BLOCKED | 0 | yes | `[mneme] DENIED`, names ADR-001 and the literal |
| | 2: write A | ALLOWED | 1 | no (A written) | none |
| unguided control, same script | 1: write B | NOT_EVALUATED | 1 | no (B written) | none |
| | 2: write A | NOT_EVALUATED | 1 | no | none |
| governed, A only | 1: write A | ALLOWED | 1 | no | none |
| edit introducing the literal (absolute path) | 1 | BLOCKED | 0 | yes | `[mneme] DENIED` |
| edit removing the fallback (absolute path) | 1 | ALLOWED | 1 | no; oracle rejects (C3) | none |
| edit introducing the literal (relative path) | 1 | ERROR_DEGRADED | 1 | no; literal landed | `[mneme] UNEVALUATED` |
| write B outside `project_dir` | 1 | ERROR_DEGRADED | 1 | no; literal landed | `[mneme] UNEVALUATED` |

The governed B-then-A run finished with a file that passes the oracle. The
unguided control also ended on A, but only after B had been written to disk:
the difference Mneme makes is that the violating mutation never happens, not
the end state of a script that corrects itself anyway.

## LangGraph portability

| Path | Label | Handler runs | Mneme enforcement events |
|---|---|---|---|
| 6A: governed agent added as a `StateGraph` node | B BLOCKED, then A ALLOWED | 0, then 1 | 2 |
| 6B: raw function node writing the file | NOT_EVALUATED | 1 | 0 |
| 6B: raw `ToolNode([write_file])` outside `create_agent` | NOT_EVALUATED | 1 | 0 |

A gate for the same project existed in-process during 6B; nothing routed
those paths through it, and Mneme recorded nothing. This is the documented
scope ("does NOT make arbitrary raw `StateGraph` graphs governed"), now
observed.

## Hypotheses

- **H1 supported** on supported paths: B and the absolute-path literal edit
  were denied with 0 handler runs and byte-identical files (CLI B, governed
  attempt 1, edit literal, 6A attempt 1).
- **H2 supported:** A was allowed and the task finished after the denial, with
  one extra model turn and one extra proposed tool call versus the direct
  compliant run. The overhead is fixed by the scripted model, not measured
  from a live one.
- **H3 supported:** C, D and the fallback-removal edit pass a literal-only
  rule while violating the decision.
- **H4 supported:** governed for `write_file` and `edit_file` through
  `create_agent` middleware, also when embedded as a node; raw nodes and a
  raw `ToolNode` are not governed.

## Metrics

| Metric | Value |
|---|---|
| Literal-rule sensitivity, CLI, in scope | 1/1 |
| Literal-rule sensitivity, middleware, supported in-project paths | 3/3 |
| Literal-rule sensitivity, middleware, all attempts introducing the literal | 3/5 (relative-path edit and out-of-project write fail open) |
| False blocks | 1 (E) |
| Constraint coverage | C1 only (literal form), 1 of 3 |
| Task success after correction | yes |
| Denial overhead vs direct compliant run | +1 model turn, +1 proposed tool call (scripted) |
| Mutation surfaces blocking the literal | 3 of 7 measured (see summary `mutation_surfaces`) |
| Audit `current_protection_pct` (audit tier only) | 100.0; tier `protected` |

## Discovered defect (not fixed here)

**Relative `edit_file` paths are read from the process working directory,
not `project_dir`.** The integration doc says `project_dir` resolves relative
tool paths. That holds for `write_file` (the target path is joined to
`project_dir` before `mneme check`), but edit materialization
(`introduced_content` → `_materialize_change` in
`mneme/integrations/claude_code/hook.py`) opens the raw relative path. When
the process cwd is not the project root, the read fails, the gate fails open
with `[mneme] UNEVALUATED ... cannot materialize content`, and the edit runs
unchecked. The failure is visible to the model and on `mneme.trace`, so it is
not silent, but the literal landed. Reproduced by
`test_edit_relative_path_fails_open_visibly`. This needs its own reviewed
issue; this experiment changes no adapter or core code.

## Known limits

- One synthetic decision and one literal rule; a scripted offline model; one
  platform (Windows 11).
- E's false block is exact-match behavior on comments and strings; whether it
  matters depends on how often a decision's identifier appears in prose
  inside governed paths.
- `task_success` for a single denied attempt only means the file stayed
  compliant.
- A write outside `project_dir` failing open is expected behavior for
  out-of-scope paths, recorded so it is never mistaken for coverage.

## 6C: what a custom orchestrator would need to expose

For pre-write enforcement equivalent to the middleware path, a custom
orchestrator has to give Mneme, before the mutation executes:

1. **The proposed action:** which tool or operation is about to mutate state,
   and a guarantee that it waits for a decision.
2. **Target and content:** the target path, resolvable against a known
   project root, and the full proposed content or an old/new pair from which
   the introduced lines can be derived without reading ambiguous paths.
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
through it unchanged. Separately: file the relative-path defect, and decide
whether C2/C3 should be modelled (a deadline bound and a required fallback)
before claiming more than literal coverage for decisions of this kind.
