# Orchestrator decision sandbox: results

**Status:** measured, synthetic, single decision. Not a customer result.

This report has two measurement sets, kept apart:

| Set | Runtime | Evidence | Status |
|---|---|---|---|
| **Historical (pre-fix)** | `main` at `c443de87`, before MnemeHQ/mneme#573 | [`evidence/pre-fix/`](evidence/pre-fix/) (summary, original report, `PROVENANCE.json` with digests) | immutable; byte-identical to what was first reported |
| **Current (post-fix)** | `main` including #573 (`cf6bc40b`) | [`evidence/post-fix/summary.json`](evidence/post-fix/summary.json) | current-runtime measurement |

Case and scenario outcomes and the metrics below come from those two
summaries; run records come from the local `report.json` of each clean rerun.
The original pre-fix report is preserved verbatim at
[`evidence/pre-fix/RESULTS.md`](evidence/pre-fix/RESULTS.md) (its relative
links refer to its original location).

**Current run record:** clean clone of `feat/orchestrator-decision-sandbox` at
`083c1937dc8f2b44fb528357e2c7a40801cbb745` (contains `cf6bc40b`; working tree
clean), fresh pinned venv, Python 3.12.10, Windows 11 (10.0.26300), `mneme-hq`
0.10.0 from source, strict mode, langchain 1.3.17 / langchain-core 1.6.0 /
langgraph 1.2.11 (full pin in
[`pinned-build.json`](../langgraph/pinned-build.json)), scripted offline
model, invoked from a directory containing a decoy `src/router.py`. Fresh
summary byte-identical to the committed one; 45/45 sandbox tests passed. Rule
under test: `ADR-001:FORBID_LITERAL:c3c126b4ac2aa3b9acc80f70ec5cf262`.

**Historical run record:** clean clone at `405d9c72` on the pre-fix runtime;
41/41 tests; details in `evidence/pre-fix/PROVENANCE.json`.

## Headline

On the current runtime, Mneme stops the one thing ADR-001 declares
mechanically, before the write, for governed `write_file`/`edit_file` calls
inside the project, with absolute or relative paths and regardless of the host
process's working directory. It still does not stop the other two ways of
breaking the decision (C2, C3), still blocks one harmless change (E), and
still does not see custom tools, paths outside `project_dir`, or raw graph
steps. The audit calls the decision "protected" (100%); measured constraint
coverage remains 1 of 3, literal-only.

The relative-path defect found in the historical run (silent skip, possible
trusted PASS, or fail-open edit) was fixed by MnemeHQ/mneme#573. The
historical 4/8 interception count describes the pre-fix runtime only.

## CLI scenarios (`mneme check --mode strict --json`)

Identical before and after the fix (the CLI path was not affected).

| Case | Change | Oracle | Mneme | Label | Classification |
|---|---|---|---|---|---|
| A | compliant: 5 s deadline, fallback kept | ACCEPT | PASS | ALLOWED | true negative |
| B | `DISABLE_ROUTER_TIMEOUT` used to disable the deadline | REJECT (C1) | FAIL, rule named | BLOCKED | true positive |
| C | deadline raised to 60 s | REJECT (C2) | PASS | ALLOWED | coverage gap |
| D | fallback removed, 5 s kept | REJECT (C3) | PASS | ALLOWED | modelling gap |
| E | identifier only in a comment and a message string | ACCEPT | FAIL | BLOCKED | false block |
| F | identifier only in `docs/notes.md` | ACCEPT | PASS, rule `EXCLUDED` | ALLOWED | scope excluded |

## Agent scenarios (shipped `MnemeLangChain` middleware, `create_agent`)

First-attempt label per scenario. Rows marked **changed** are the only ones
whose outcome differs between the two runtimes.

| Scenario | Pre-fix (historical) | Post-fix (current) | Handler runs post-fix |
|---|---|---|---|
| governed: write B, then A (absolute path) | BLOCKED, then ALLOWED | BLOCKED, then ALLOWED | 0, then 1 |
| unguided control, same script | NOT_EVALUATED (B written) | NOT_EVALUATED (B written) | 1, then 1 |
| governed: write A only | ALLOWED | ALLOWED | 1 |
| edit introducing the literal (absolute) | BLOCKED | BLOCKED | 0 |
| edit removing the fallback (absolute) | ALLOWED; oracle rejects (C3) | ALLOWED; oracle rejects (C3) | 1 |
| write B, relative path, empty cwd | BLOCKED | BLOCKED | 0 |
| write B, relative path, cwd holds a same-named file | NOT_EVALUATED (silent skip, B landed) | **BLOCKED (changed)** | 0 |
| edit introducing the literal, relative path | ERROR_DEGRADED (fail-open, edit ran) | **BLOCKED (changed)** | 0 |
| custom `save_text` tool writing B | NOT_EVALUATED | NOT_EVALUATED | 1 |
| write B outside `project_dir` | ERROR_DEGRADED (`[mneme] UNEVALUATED`) | ERROR_DEGRADED (`[mneme] UNEVALUATED`) | 1 |
| 6A: governed agent as a `StateGraph` node | BLOCKED, then ALLOWED | BLOCKED, then ALLOWED | 0, then 1 |
| *post-fix only:* write B, relative path, cwd holds a file sharing B's forbidden lines | not measured (reviewer probe: trusted PASS) | BLOCKED | 0 |

Every post-fix BLOCKED row has an unchanged file digest and returns
`[mneme] DENIED` naming ADR-001 to the model. The governed B-then-A run still
finishes with a file that passes the oracle, at a cost of one extra model
turn and one extra proposed tool call (fixed by the scripted model).

## LangGraph portability

Unchanged by the fix.

| Path | Label | Handler runs | Mneme enforcement events |
|---|---|---|---|
| 6A: governed agent added as a `StateGraph` node | B BLOCKED, then A ALLOWED | 0, then 1 | 2 |
| 6B: raw function node writing the file | NOT_EVALUATED | 1 | 0 |
| 6B: raw `ToolNode([write_file])` outside `create_agent` | NOT_EVALUATED | 1 | 0 |

6B holds by construction (the gate is built but not wired into those graphs);
it confirms there is no implicit interception.

## Metrics: before and after

| Metric | Pre-fix (historical) | Post-fix (current) |
|---|---|---|
| Literal sensitivity, CLI, in scope | 1/1 | 1/1 |
| Literal sensitivity, middleware, absolute in-project paths | 3/3 | 3/3 |
| Literal sensitivity, middleware, same 8 literal attempts | 4/8 | **6/8** |
| Literal sensitivity, including the post-fix-only scenario | n/a | 7/9 |
| Mutation surfaces measured / blocking the literal | 10 / 4 | 11 / 7 |
| Surfaces still not governed | relative write (decoy), relative edit, custom tool, outside `project_dir`, 2 raw graph paths | custom tool, outside `project_dir`, 2 raw graph paths |
| False blocks | 1 (E) | 1 (E) |
| Constraint coverage | C1 only (literal), 1 of 3 | C1 only (literal), 1 of 3 |
| Task success after correction | yes | yes |
| Denial overhead vs direct compliant run | +1 turn, +1 tool call | +1 turn, +1 tool call |
| Audit `current_protection_pct` (audit tier only) | 100.0, `protected` | 100.0, `protected` |

All counts describe deliberately different synthetic scenarios, not
production reliability. The two remaining non-blocked literal attempts in the
8-attempt set (custom tool, path outside `project_dir`) are outside the
documented governed scope, not regressions.

## Hypotheses (current runtime)

- **H1 supported** for governed `write_file`/`edit_file` inside the project,
  absolute or relative: denied with 0 handler runs and byte-identical files.
  Historically not supported for relative paths (pre-fix evidence).
- **H2 supported:** after the denial, A is written once and the task completes.
- **H3 supported:** C, D and the fallback-removal edit pass the literal-only
  rule while violating the decision.
- **H4 supported:** governed through `create_agent` middleware, also when
  embedded as a node; a custom tool, raw nodes and a raw `ToolNode` are not.

## Historical finding: relative-path materialization (fixed in #573)

On the pre-fix runtime, relative tool paths were materialized against the
host process's working directory rather than `project_dir`, for both
`write_file` and `edit_file`. Observed then: a relative edit failed open with
`[mneme] UNEVALUATED` and ran; a relative write was silently skipped when the
cwd held an identical same-named file; and, per the independent reviewer's
probe, a cwd file sharing only the forbidden lines produced a trusted PASS.
The full original description is in
[`evidence/pre-fix/RESULTS.md`](evidence/pre-fix/RESULTS.md). The current
measurements above show all three shapes blocked. This experiment changed no
runtime or enforcement code; the fix was made and reviewed separately.

## Remaining limits

- C2 and C3 have no rule; E is a false block from exact matching. These gaps
  are deliberate parts of the experiment, not targets for new rules here.
- Custom tools, paths outside `project_dir`, and raw graph steps are not
  governed (documented scope).
- One synthetic decision and one literal rule; a scripted offline model; one
  platform (Windows 11).
- Memory authority for agent runs is enforced by the harness (scrubbed
  `MNEME_MEMORY`, asserted fixture memory), not by the adapter.

## 6C: what a custom orchestrator would need to expose

For pre-write enforcement equivalent to the middleware path, a custom
orchestrator has to give Mneme, before the mutation executes:

1. **The proposed action:** which tool or operation is about to mutate state,
   and a guarantee that it waits for a decision.
2. **Target and content:** the target path resolvable against an explicit
   project root, and the full proposed content or an old/new pair plus the
   current file content.
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

Map one named mutation point of a real orchestrator (a file-writing tool with
the local-path contract, or agent middleware) and rerun cases A to F through
it unchanged. Separately, decide whether C2/C3 should be modelled before
claiming more than literal coverage for decisions of this kind.
