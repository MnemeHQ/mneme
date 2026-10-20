# Orchestrator Decision Sandbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** EXECUTED on this branch. Results:
[`validation/orchestrator-decision-sandbox/RESULTS.md`](../../validation/orchestrator-decision-sandbox/RESULTS.md).
Deviations from the tasks below, made after an independent adversarial
review: supported-path agent scenarios pass absolute in-project paths;
relative-path writes and edits are measured as separate scenarios (empty and
decoy process cwd) because the hook materializes relative paths against the
process cwd; the runner pins its process cwd, scrubs `MNEME_MEMORY` and mode
env, and asserts the middleware's memory is the fixture's; an unmapped custom
tool scenario was added for H4; the pin gate checks all eight pinned packages.

**Goal:** Show, with one synthetic accepted decision and reproducible evidence,
whether a governed decision changes an agent's file-mutation outcome, how much
legitimate work it blocks, which bypasses remain, and what the smallest
integration for a LangGraph-based orchestrator would be.

**Architecture:** A self-contained fixture under
`validation/orchestrator-decision-sandbox/`: one synthetic ADR with a
path-scoped `FORBID_LITERAL`, a tiny synthetic router module, six candidate
cases (A to F), and a functional oracle that judges architectural acceptability
independently of Mneme. Runners build a fresh fixture memory per case in a temp
directory, then drive (1) the shipped `mneme check` / `mneme audit` CLI and (2)
the shipped `MnemeLangChain` middleware through `create_agent` with a scripted
offline model, including embedded-`StateGraph` (6A) and raw-graph (6B)
contrasts. No enforcement, adapter or canonical-memory code changes.

**Tech Stack:** Python 3.12.10, `mneme-hq` from this worktree (editable),
langchain 1.3.17 / langchain-core 1.6.0 / langgraph 1.2.11 (exact pin from
`validation/langgraph/pinned-build.json`), pytest.

**Spec:** Section "Spec (restated)" below. Executors work from this section
only.

## Spec (restated)

**Hypotheses.**
- H1: a governed `write_file`/`edit_file` call that introduces the declared
  forbidden literal is denied before its handler runs; the target stays
  byte-identical.
- H2: a compliant write is allowed; after receiving the denial, the same task
  finishes with a compliant correction. Record attempts and completion.
- H3: a semantically invalid change without the literal passes a literal-only
  rule. This is a coverage gap to report, not an experiment failure.
- H4: coverage is narrow. A `create_agent` agent with Mneme middleware is
  governed for the two mapped file tools, also when embedded as a `StateGraph`
  node; raw graph nodes and unmapped tools are not governed.

**Synthetic decision (ADR-001, fictional).** "The LLM routing validator must
enforce a five-second maximum deadline and take a safe fallback path on
failure. The timeout must not be explicitly disabled." Sub-constraints:
C1 deadline must not be disabled; C2 deadline must be at most 5 s; C3 a safe
fallback is required. One typed rule: `FORBID_LITERAL DISABLE_ROUTER_TIMEOUT`
with `include_paths: ["src/**"]`. Only the literal aspect of C1 is enforced;
C2 and C3 are stated as unenforced.

**Cases.** Each runs from a fresh copy of the same baseline.

| ID | Target | Content | Oracle | Predicted CLI | Classification |
|---|---|---|---|---|---|
| A | `src/router.py` | 5 s deadline, working fallback, no literal | ACCEPT | ALLOWED | TRUE_NEGATIVE |
| B | `src/router.py` | uses `DISABLE_ROUTER_TIMEOUT` as code to disable the deadline | REJECT | BLOCKED | TRUE_POSITIVE |
| C | `src/router.py` | deadline 60 s, fallback kept, no literal | REJECT | ALLOWED | COVERAGE_GAP (C2) |
| D | `src/router.py` | 5 s deadline, fallback removed, no literal | REJECT | ALLOWED | MODELLING_GAP (C3) |
| E | `src/router.py` | compliant code; literal only in a comment and a log string | ACCEPT | BLOCKED | FALSE_BLOCK |
| F | `docs/notes.md` | literal in prose; `src/` unchanged | ACCEPT | ALLOWED (rule EXCLUDED) | SCOPE_EXCLUDED |

**Outcome labels (exhaustive):** `BLOCKED`, `ALLOWED`, `WARNED`,
`NOT_EVALUATED`, `ERROR_DEGRADED`. An error, an incomplete evaluation, or a
missing observation is never `ALLOWED`.

**Per-case evidence row:** case ID, sub-constraint, oracle, Mneme verdict,
label, enforcement surface (`cli`, `middleware_pre_tool`, `none`), write
handler count, SHA-256 before/after, oracle result on the end state, agent
completion, notes.

**Required checks:** (1) literal true positive; (2) compliant acceptance;
(3) semantic false negative; (4) false-block control; (5) path scope;
(6) middleware pre-mutation prevention; (7) agent correction and completion;
(8) embedded graph behavior; (9) raw graph path flagged NOT_EVALUATED;
(10) reproducibility from a clean checkout.

**Metrics, reported separately:** literal-rule sensitivity within scope;
false-block count; constraint coverage across C1/C2/C3 (expected 1 of 3,
partial); task success after correction; extra turns and tool calls caused by
the denial; mutation surfaces governed versus bypassable. The audit's
`current_protection_pct` is recorded as audit-tier output only and never
presented as behavioral coverage.

**Stop and raise a blocker if:** the run would write to any memory outside the
temp fixture; strict mode is not in effect; installed langchain/langgraph
versions differ from the pin; a result cannot be attributed to the proposed
mutation; or the run needs network access or a remote mutation boundary.

## Pre-plan probe (2026-10-20, scratch directory, not evidence)

Run against `origin/main` source with the fixture as working directory:
B `FAIL` (rule `ADR-001:FORBID_LITERAL:c3c126b4…`, outcome `APPLIED`);
C `PASS`; E `FAIL` for both comment and string forms; F `PASS` with
applicability `EXCLUDED`; `mneme audit` reports `current_protection_pct: 100.0`.
Two traps found: running `mneme check` from the repo root (a) resolves
`--target-path` against the wrong root, giving `evaluation_complete: false`,
outcome `UNKNOWN` and verdict `PASS` with exit code 2, and (b) pulls the repo's
own `docs/adr` into freshness diagnostics. Every CLI call in this plan
therefore runs with `cwd=<fixture root>`.

## Global Constraints

- Synthetic only. No partner, customer, or project names; no "design partner"
  wording; no private audit text or inferences; no screenshots. Applies to
  source, fixtures, prompts, logs, commit messages, PR text and issues.
- No network, no provider keys, no live model in this plan. A live
  Claude Code run is out of scope.
- Do not modify `mneme/` (core, enforcement, adapters), `docs/adr/`,
  the repo's `.mneme/project_memory.json`, user/global Mneme memory, or
  `.github/workflows/`. A defect found in core is reported, not fixed here.
- Never call `mneme protect activate`.
- Strict mode everywhere (`--mode strict`, `MnemeLangChain(mode="strict")`).
- Exact pins: langchain 1.3.17, langchain-core 1.6.0, langgraph 1.2.11,
  Python 3.12.10.
- All CLI invocations: `python -m mneme.cli ...` with `cwd` = the per-case
  fixture root.
- Write candidate content as bytes (`Path.write_bytes(content.encode("utf-8"))`)
  so digests are newline-stable on Windows.
- Raw run output is git-ignored. Only the deterministic `evidence/summary.json`,
  `evidence/summary.csv` and hand-written docs are committed.
- Work only in `C:/dev/mneme/.worktrees/feat-orchestrator-decision-sandbox` on
  `feat/orchestrator-decision-sandbox`. Run
  `python scripts/check_worktree_context.py` before starting and before every
  commit.
- Do not merge. The PR stops at review.

## Review Focus

1. **Incomplete evaluation reported as a pass.** `mneme check` can return
   verdict `PASS` with `evaluation_complete: false` (seen in the probe). It
   must be labelled `ERROR_DEGRADED`. Pinned in Task 4
   (`test_incomplete_evaluation_is_degraded`).
2. **Version drift.** This machine has langchain 1.4.0 / langchain-core 1.6.3
   installed globally. Running unpinned must stop, not quietly record results.
   Pinned in Task 1 (`test_drift_raises_blocker`).
3. **Carry-over between cases.** A mutation from one case leaking into the
   next would fake results. Pinned in Task 3
   (`test_each_baseline_is_byte_identical`).
4. **Tool path outside the fixture.** An agent writing to an absolute path
   outside `project_dir` gets `UNKNOWN` applicability. It must surface as
   `ERROR_DEGRADED`/UNEVALUATED, never `ALLOWED`. Pinned in Task 5
   (`test_out_of_root_path_is_not_allowed`).
5. **Repo memory touched.** A runner bug writing to the repo's
   `.mneme/project_memory.json` would break governance. Pinned in Task 3
   (`test_repo_memory_untouched`).

---

## File map

All paths are under `validation/orchestrator-decision-sandbox/`.

| Path | Responsibility |
|---|---|
| `README.md` | purpose, scope limits, setup from clean checkout, run command |
| `.gitignore` | ignores `evidence/runs/` |
| `adr/ADR-001.md` | the synthetic decision (copied to `docs/adr/` in each fixture) |
| `synthetic_app/src/router.py` | baseline compliant router |
| `synthetic_app/docs/notes.md` | baseline out-of-scope doc |
| `fixtures/cases.json` | cases A to F (content, target, oracle, prediction, classification) |
| `scripts/oracle.py` | functional C1/C2/C3 oracle, independent of Mneme |
| `scripts/sandbox_lib.py` | pins gate, baseline builder, digests, case loader, labels |
| `scripts/run_cli_checks.py` | CLI runner (A to F, plus one audit) |
| `scripts/run_langgraph_checks.py` | governed/ungoverned agent loops, 6A, 6B |
| `scripts/run_sandbox.py` | entry point: runs both, writes evidence |
| `tests/test_sandbox.py` | all assertions below |
| `evidence/README.md` | evidence rules and field definitions |
| `evidence/summary.json`, `evidence/summary.csv` | deterministic committed summary |
| `RESULTS.md` | technical report, metrics, 6C extension note |

Tests live outside `testpaths` (`["tests"]`), so default CI does not collect
them. Adding them to CI is a later, separate change.

---

### Task 1: Pinned environment and blocker gate

**Files:**
- Create: `scripts/sandbox_lib.py` (pins section only), `tests/test_sandbox.py`,
  `README.md` (setup section), `.gitignore`

**Interfaces:**
- Produces: `class BlockerError(RuntimeError)`;
  `pin_drift() -> dict[str, tuple[str, str | None]]` (package → (pinned,
  installed), only mismatches, for langchain, langchain-core, langgraph);
  `assert_pinned() -> None` (raises `BlockerError` listing the drift);
  `SANDBOX: Path`, `REPO_ROOT: Path`.

- [ ] **Step 1:** Create the venv outside the repo (`.venv-sandbox` is not
  git-ignored): `python -m venv C:/dev/venvs/orchestrator-sandbox`, then
  `C:/dev/venvs/orchestrator-sandbox/Scripts/python -m pip install -e ".[dev,langchain]" langchain==1.3.17 langchain-core==1.6.0 langgraph==1.2.11`.
  Expected: `pip show` reports exactly those three versions. Every
  `.venv-sandbox/Scripts/python` below means this interpreter.
- [ ] **Step 2:** Write `test_pins_match_validated_build` (asserts
  `pin_drift() == {}`) and `test_drift_raises_blocker` (monkeypatch
  `importlib.metadata.version` to return `"1.4.0"` for langchain; assert
  `assert_pinned()` raises `BlockerError` naming `langchain 1.3.17 != 1.4.0`).
- [ ] **Step 3:** Run
  `.venv-sandbox/Scripts/python -m pytest validation/orchestrator-decision-sandbox/tests -k pin -v`.
  Expected: FAIL (module missing).
- [ ] **Step 4:** Implement the pins section of `sandbox_lib.py`, reading
  `validation/langgraph/pinned-build.json`.
- [ ] **Step 5:** Rerun. Expected: 2 passed.
- [ ] **Step 6:** Commit `feat(validation): sandbox pin gate for orchestrator decision sandbox`.

### Task 2: Synthetic decision, app, cases and oracle

**Files:**
- Create: `adr/ADR-001.md`, `synthetic_app/src/router.py`,
  `synthetic_app/docs/notes.md`, `fixtures/cases.json`, `scripts/oracle.py`
- Test: `tests/test_sandbox.py`

**Interfaces:**
- Produces:
  - ADR-001 frontmatter: `id: ADR-001`, `status: accepted`,
    `priority: foundational`, `date: 2026-10-20`, `scope: routing`,
    `supersedes: []`. Body states C1/C2/C3 and says only the C1 literal is
    enforced. `## Constraints` holds exactly one structured
    `FORBID_LITERAL` with `value: DISABLE_ROUTER_TIMEOUT` and
    `include_paths: ["src/**"]`.
  - Router contract (all cases implement it): module constant
    `ROUTER_DEADLINE_S`, constant `FALLBACK_ROUTE = "safe-default"`,
    `route(request: str, classify: Callable[[str, float], str]) -> str`.
    `classify` receives the deadline and raises `TimeoutError` when it would
    exceed it.
  - `cases.json`: list of objects with keys `id`, `sub_constraint`,
    `target_path`, `content`, `oracle` (`ACCEPT`|`REJECT`), `predicted_cli`
    (`BLOCKED`|`ALLOWED`), `classification` (values from the Spec table).
  - `oracle.evaluate(router_source: str) -> OracleResult` with
    `OracleResult(accept: bool, failures: list[str])`; failures use the codes
    `C1_DISABLED`, `C2_DEADLINE_EXCEEDS_5S`, `C3_NO_FALLBACK`, `LOAD_ERROR`.
    C1: deadline is `None`, `0`, negative or `inf`, or the source disables it
    via a flag. C2: deadline > 5. C3: `route()` with a classify that raises
    `TimeoutError` does not return `FALLBACK_ROUTE`.
  - `sandbox_lib.load_cases() -> list[Case]` (frozen dataclass mirroring the
    JSON keys).

- [ ] **Step 1:** Write `test_oracle_matches_case_table`: for each case,
  oracle on the end-state router (for F, the unchanged baseline router)
  returns `accept` equal to `case.oracle == "ACCEPT"`; C fails with
  `C2_DEADLINE_EXCEEDS_5S`, D with `C3_NO_FALLBACK`, B with `C1_DISABLED`.
  Write `test_case_literal_placement`: `DISABLE_ROUTER_TIMEOUT` appears in
  B, E and F content and nowhere in A, C, D or the baseline router.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Create the files above. Fictional names only.
- [ ] **Step 4:** Run; expect PASS.
- [ ] **Step 5:** Commit `feat(validation): synthetic ADR, router cases and functional oracle`.

### Task 3: Per-case baseline builder

**Files:**
- Modify: `scripts/sandbox_lib.py`
- Test: `tests/test_sandbox.py`

**Interfaces:**
- Produces: `build_baseline(dest: Path) -> Baseline`, where
  `Baseline(root: Path, memory: Path, rule_id: str, decision_version_id: str,
  baseline_sha256: str, import_preview: str)`. Steps inside: copy
  `synthetic_app/` to `dest`; copy `adr/ADR-001.md` to `dest/docs/adr/`;
  `mneme init` (cwd=dest); `mneme adr import docs/adr --memory
  .mneme/project_memory.json --dry-run` must exit 0 and list the rule;
  then `--apply` must exit 0. `rule_id` comes from a `mneme check --json`
  applicability entry on the baseline router. `baseline_sha256` is a digest
  over the sorted (relative path, file sha256) pairs of `src/` and `docs/`
  (excluding `.mneme/`). Also `sha256_bytes(b: bytes) -> str` and
  `sha256_file(p: Path) -> str | None`.

- [ ] **Step 1:** Write tests:
  `test_baseline_has_one_scoped_rule` (memory `decision_index` has one active
  decision `ADR-001`; `rule_id` starts with `ADR-001:FORBID_LITERAL:`; the
  preview text contains `include_paths: src/**`);
  `test_each_baseline_is_byte_identical` (two baselines in different temp
  dirs have equal `baseline_sha256`);
  `test_repo_memory_untouched` (SHA-256 of `REPO_ROOT/.mneme/project_memory.json`
  is identical before and after building a baseline);
  `test_no_repo_adr_freshness_leak` (a `mneme check --json` on the baseline
  has an empty `freshness` list).
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement `build_baseline`. Use
  `subprocess.run([sys.executable, "-m", "mneme.cli", ...], cwd=dest,
  capture_output=True, text=True, env=<os.environ with PYTHONPATH=REPO_ROOT>)`.
- [ ] **Step 4:** Run; expect PASS.
- [ ] **Step 5:** Commit `feat(validation): isolated per-case fixture baseline`.

### Task 4: CLI scenarios A to F

**Files:**
- Create: `scripts/run_cli_checks.py`
- Modify: `scripts/sandbox_lib.py` (labels)
- Test: `tests/test_sandbox.py`

**Interfaces:**
- Consumes: `build_baseline`, `load_cases`, `oracle.evaluate`.
- Produces: `label_from_check(payload: dict | None, exit_code: int) -> str`
  (`None`/unparseable → `ERROR_DEGRADED`; `evaluation_complete` false →
  `ERROR_DEGRADED`; `FAIL` → `BLOCKED`; `WARN` → `WARNED`; `PASS` →
  `ALLOWED`); `run_cli_case(case: Case, workdir: Path) -> dict` returning a
  row with keys `case`, `surface="cli"`, `verdict`, `label`, `rule_ids`,
  `applicability_outcomes`, `exit_code`, `input_sha256`,
  `target_sha256_before`, `target_sha256_after`, `oracle_accept`,
  `oracle_failures`, `classification_observed`, `stdout_path`, `stderr_path`;
  `run_audit(workdir: Path) -> dict` (stores the `mneme.audit/v1` summary
  under key `audit_tier_only`).
  `classification_observed` is computed from oracle and label: ACCEPT+ALLOWED
  → TRUE_NEGATIVE (or SCOPE_EXCLUDED when applicability is `EXCLUDED`),
  REJECT+BLOCKED → TRUE_POSITIVE, REJECT+ALLOWED → COVERAGE_GAP or
  MODELLING_GAP by the failing sub-constraint, ACCEPT+BLOCKED → FALSE_BLOCK.

- [ ] **Step 1:** Write `test_cli_case_outcomes` parametrized over A to F:
  label equals `predicted_cli`, `classification_observed` equals the case's
  `classification`, target digest before == after (CLI never writes), B and
  E carry the baseline `rule_id`, F's applicability outcome is `EXCLUDED`.
  Write `test_incomplete_evaluation_is_degraded`:
  `label_from_check({"verdict": "PASS", "evaluation_complete": False}, 2) == "ERROR_DEGRADED"`,
  plus `None` and `{}` payloads also give `ERROR_DEGRADED`.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement. The candidate is written to
  `workdir/candidate.<ext>` and passed as `--input` with
  `--target-path <case.target_path> --query "router deadline fallback"
  --mode strict --json`, cwd = fixture root. Save stdout/stderr into the run
  directory.
- [ ] **Step 4:** Run; expect 7 passed.
- [ ] **Step 5:** Commit `feat(validation): CLI scenarios A-F with separate oracle`.

### Task 5: Governed and ungoverned agent loops

**Files:**
- Create: `scripts/run_langgraph_checks.py`
- Test: `tests/test_sandbox.py`

**Interfaces:**
- Consumes: `build_baseline`, `load_cases`, `oracle.evaluate`,
  `assert_pinned`.
- Produces: `ScriptedChatModel` (same shape as
  `tests/integrations/langchain/test_live_fixture.py`: replays a list of
  `{"content", "tool_calls"}` specs, `bind_tools` returns self; copy it, do
  not import from `tests/`); `make_file_tools(root: Path, counter:
  collections.Counter) -> list` returning `write_file(file_path, content)`
  and `edit_file(file_path, old_string, new_string)`, each incrementing
  `counter[tool_name]` before writing bytes;
  `run_agent(root: Path, script: list[dict], governed: bool) -> dict` with
  keys `handler_calls` (per attempt), `digests` (after each tool call),
  `tool_messages` (texts), `final_oracle`, `completed`, `model_turns`,
  `trace` (from `mneme.trace` when governed, else `[]`).
  Governed uses `MnemeLangChain(project_dir=str(root), mode="strict")` and
  `create_agent(model, tools, middleware=mneme.build_middleware())`.

- [ ] **Step 1:** Write tests:
  `test_governed_denies_b_then_completes_with_a`: script = write B, write A,
  finish. Assert first attempt handler count 0 and digest unchanged from
  baseline; first `ToolMessage` contains `[mneme] DENIED` and `ADR-001`;
  second attempt handler count 1; final file bytes equal A's content;
  `final_oracle.accept`; `completed`.
  `test_ungoverned_control_executes_b`: same script, `governed=False`; first
  attempt handler count 1 and the post-B digest equals `sha256_bytes(B)`.
  `test_edit_introducing_literal_denied` and `test_edit_removing_fallback_allowed`
  (edit_file on the baseline router; the second is the D gap through the
  introduced-delta path: label `ALLOWED`, oracle rejects).
  `test_out_of_root_path_is_not_allowed`: governed write of B to an absolute
  path in a sibling temp dir; the result is not `ALLOWED` (expect a
  `[mneme] UNEVALUATED` note or a denial), and the row label is
  `ERROR_DEGRADED` or `BLOCKED`. Record whichever the adapter produces; if it
  is a clean pass, stop and raise it as a finding.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement. Tool `file_path` arguments are relative
  (`src/router.py`) and resolved against `root` inside the tool body.
- [ ] **Step 4:** Run; expect PASS.
- [ ] **Step 5:** Commit `feat(validation): governed vs ungoverned scripted agent loop`.

### Task 6: LangGraph portability, 6A and 6B

**Files:**
- Modify: `scripts/run_langgraph_checks.py`
- Test: `tests/test_sandbox.py`

**Interfaces:**
- Produces: `run_embedded(root: Path, script: list[dict]) -> dict`
  (compiled governed agent added with
  `StateGraph(MessagesState).add_node("governed_agent", agent)`, edges
  START → governed_agent → END; same result keys as `run_agent` plus
  `node="governed_agent"`); `run_raw_node(root: Path, content: str) -> dict`
  (a plain function node that writes B directly, and a second variant using
  `langgraph.prebuilt.ToolNode([write_file])` fed a hand-built `AIMessage`
  tool call; both on fresh baselines; keys `variant`, `handler_calls`,
  `digest_after`, `trace_entries`, `label`).

- [ ] **Step 1:** Write `test_embedded_agent_still_governed` (B denied with
  handler count 0, A allowed once, the parent graph's message list contains
  the denial `ToolMessage`) and `test_raw_graph_paths_not_governed` (both
  variants: handler count 1, digest changed to `sha256_bytes(B)`, zero Mneme
  trace entries, label `NOT_EVALUATED`).
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement. If `ToolNode` cannot run outside an agent at the
  pinned versions, record the variant with label `ERROR_DEGRADED` and the
  exception text; the plain-function variant is still required.
- [ ] **Step 4:** Run; expect PASS.
- [ ] **Step 5:** Commit `feat(validation): embedded vs raw StateGraph governance contrast`.

### Task 7: Evidence, summary and reproducibility

**Files:**
- Create: `scripts/run_sandbox.py`, `evidence/README.md`,
  `evidence/summary.json`, `evidence/summary.csv`
- Test: `tests/test_sandbox.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `main(argv) -> int` (exit 0 only when every row matches its
  prediction and no row is `ERROR_DEGRADED` outside the documented 6B
  fallback; exit 1 otherwise; exit 3 on `BlockerError`). Writes
  `evidence/runs/<UTC stamp>/` (git-ignored) with `report.json` (env:
  Python, OS, `git rev-parse HEAD`, full `pip freeze`, pins, strict mode,
  `baseline_sha256`, `rule_id`, commands), `transcript.txt`, per-call
  stdout/stderr, then `MANIFEST.sha256` last.
  `build_summary(report: dict) -> dict` keeps only deterministic fields
  (case rows without paths or timestamps, required checks 1 to 10 with
  `PASS`/`FAIL`, and the metrics from the Spec) and is written to
  `evidence/summary.json` (sorted keys, 2-space indent, trailing newline) and
  `evidence/summary.csv`.

- [ ] **Step 1:** Write `test_summary_is_deterministic` (two runs produce
  byte-identical `summary.json`), `test_committed_summary_matches_fresh_run`,
  and `test_labels_are_exhaustive` (every row label is one of the five
  labels).
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement. Metrics: sensitivity = blocked REJECT cases
  carrying the literal / REJECT cases carrying the literal (expected 1/1);
  false blocks = ACCEPT cases labelled BLOCKED (expected 1, E); constraint
  coverage = sub-constraints with any enforcing rule (expected 1 of 3,
  C1 literal only); surfaces governed vs bypassable (expected 3 governed:
  `write_file`, `edit_file`, embedded agent node; 2 bypassable: raw function
  node, raw `ToolNode`); denial overhead = extra model turns and tool calls
  versus the ungoverned control.
- [ ] **Step 4:** Run `.venv-sandbox/Scripts/python validation/orchestrator-decision-sandbox/scripts/run_sandbox.py`,
  commit the produced `summary.json`/`summary.csv`, then run the tests.
  Expected: exit 0; tests pass.
- [ ] **Step 5:** Commit `feat(validation): deterministic sandbox evidence summary`.

### Task 8: Report and README

**Files:**
- Create: `RESULTS.md`; complete `README.md`

- [ ] **Step 1:** `README.md`: purpose, the "partial protection" framing,
  exact setup and run commands from a clean checkout, what is out of scope
  (live models, shell/execute tools, remote backends, custom orchestrators).
- [ ] **Step 2:** `RESULTS.md`, from the committed summary only: per-case
  table; H1 to H4 each marked SUPPORTED / NOT SUPPORTED with the row that
  shows it; metrics; the audit's 100% figure quoted as audit tier only, next
  to the 1-of-3 constraint coverage; known limits (scripted model, Windows
  only, one decision); section "6C: what a custom orchestrator must expose"
  covering the proposed mutation before execution, target path and proposed
  content, a deterministic allow/deny response channel, applicability
  context, correlation IDs, and the difference between pre-write blocking
  and a later CI check. No new adapter is built or claimed.
- [ ] **Step 3:** Clean-checkout reproduction: fresh clone of the branch into
  a temp dir, new pinned venv, run `run_sandbox.py`, confirm `summary.json`
  is byte-identical. Record the commit SHA in `RESULTS.md`.
- [ ] **Step 4:** Commit `docs(validation): orchestrator decision sandbox results`.

### Task 9: Repo gates and PR (no merge)

- [ ] **Step 1:** `python scripts/run_test_battery.py gate` and
  `mneme check --mode warn` per repo instructions. Expected: no new failures.
- [ ] **Step 2:** Confidentiality pass, run by the operator outside the repo
  with a private term list (the list never enters the repo): grep the diff,
  commit messages and PR body. Expected: zero hits.
- [ ] **Step 3:** Open the PR titled
  `feat(validation): synthetic orchestrator decision sandbox (A-F, LangGraph 6A/6B)`
  with an `## Execution provenance` block, validated with
  `python scripts/check_pr_provenance.py --body-file <file>`.
- [ ] **Step 4:** Stop at review. Do not merge.

## Out of this repository

These belong to the private side and are not tasks in this PR:
- The one-page findings note for the external reviewer, written from
  `RESULTS.md` once the PR is reviewed.
- The two reviewer questions (are the four router changes representative;
  is there an isolated mutation point worth a later experiment).
- Any experiment against a real orchestrator, which needs its own scope,
  approval and a private environment.
