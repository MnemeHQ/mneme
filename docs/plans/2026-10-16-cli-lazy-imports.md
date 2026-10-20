# CLI Lazy Imports for the Check Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `mneme check`, the command `mneme-hook` runs on every write, stop importing the eleven modules that only other subcommands need. That should save about 64 ms per write on the hook's subprocess path, with no change to behaviour.

**Architecture:** Move module-level imports that the check path doesn't use from `mneme/cli.py` into the command functions that use them. Check-path names stay at module level. No `__getattr__` magic, no new entry point, no change to how the hook starts the check. A subprocess guard test pins the set of modules a check run may load.

**Tech Stack:** Python ≥ repo floor, pytest, `ruff` (local verification only).

**Spec:** MnemeHQ/mneme-growth-ops#60, comment 2026-10-16 "Correction: … without cached bytecode", and `docs/validation/2026-10-16-hook-check-latency-benchmark.md` § "Correction: with cached bytecode".

**Repo:** `MnemeHQ/mneme`, branch `refactor/cli-lazy-imports` from `main`, after MnemeHQ/mneme#532 merges, because Task 2 uses its bytecode-fixed harness. Squash-merge. Move this plan into the mneme repo's `docs/plans/` at execution start.

## Global Constraints

- **No behaviour change for any subcommand:** same output, exit codes and `mneme.check/v1` JSON.
- **These stay module-level in `mneme/cli.py`,** because the check path or the parser needs them, or tests patch them on `cli`:
  - `argparse`, `json`, `re`, `sys`, `datetime`, `Path`
  - `collect_adr_diagnostics`, `FreshnessIssue`, everything from `mneme.adr_import`, `ADRParseError` and `ADRValidationError`. These are already loaded by the check path through `adr_freshness`.
  - `DEFAULT_MAX_DECISIONS` and `format_decisions` from `context_builder`, which the parser uses at L1904, L1929 and L2052.
  - `GovernanceContext` and `resolve_effective`, which tests patch.
  - Everything from `decision_index_persistence`, which the check path already loads.
  - `DecisionRetriever`, `EnforcementResult`, `Severity`, `check_prompt`, `generate_protection_report`, `MemoryStore`.
- **These become function-local imports:** `mneme.integrations.eventcatalog`, `mneme.benchmark`, `mneme.benchmark_report`, `mneme.cursor_generator`, `mneme.decision_add`, `mneme.decision_authority`, `mneme.decision_proposal_store`, `mneme.protection`, `mneme.readiness`, `mneme.setup`, `mneme.setup_state`.
- Each function-local import is the **first statement** of the function that uses the name. It never goes inside a `try`, so an `except SomeError` clause can never refer to a name that hasn't been bound yet. Keep the existing alias names, e.g. `compile_for_import as ec_compile_for_import`.
- **Out of scope:**
  - No change to `mneme/integrations/claude_code/hook.py`. The `difflib` observation is a separate follow-up.
  - No change to `mneme/__main__.py`.
  - No change to the hook's command line.

## Review Focus

1. **Undefined names on rarely run paths.** If a function uses a moved name without importing it locally, it only fails with `NameError` when that subcommand runs. *Check: Task 1 Step 5 runs `ruff check --select F821 mneme/cli.py`, which must be clean.*
2. **Tests that patch moved names on `cli`.** Tests that do `setattr(cli, "<moved name>", …)` would silently patch a name nothing reads any more. There are four: `test_d1e4_eventcatalog_retirement.py:126` (`ec_compile_for_import`), `test_decision_authority_cli.py:503` (`activate_protection`), `:645` (`DecisionAuthorityService`) and `:504` (`generate_protection_report`, which stays module-level, so leave it). *Check: Task 1 Step 4 moves the first three to patch the source module (e.g. `mneme.protection.activate_protection`). Each must still fail when its spy raises.*
3. **A check run loading lazy modules through another route.** For example, the `--applicability-preview` branch, or the hook's real argv. *Test: `test_check_run_does_not_load_subcommand_modules` runs the hook's exact argv shape, with and without `--applicability-preview`.*
4. **Help output for every subcommand.** Building the parser must not touch moved names. *Test: `test_every_subcommand_help_still_renders`.*
5. **Exceptions raised by moved modules are still caught.** For example, `ProtectionError` and `SetupError` handlers. *Check: the full suite stays green; Rule 1 above guarantees each name is bound before its `try`.*

---

### Task 1: Guard tests and lazy imports in `mneme/cli.py`

**Files:**
- Modify: `mneme/cli.py`: the import block at L53–L110, plus the first lines of every function that uses a moved name
- Modify: `tests/test_d1e4_eventcatalog_retirement.py:126` and `tests/test_decision_authority_cli.py:503,645`
- Create: `tests/test_cli_import_budget.py`
- Modify: `scripts/run_test_battery.py`, to add `tests/test_cli_import_budget.py` to `GATE_CLI_PATHS`

**Interfaces:**
- Produces: `LAZY_MODULES: tuple[str, ...]` in `tests/test_cli_import_budget.py`, listing the eleven modules from the Global Constraints, used by Task 2's notes.

- [ ] **Step 1: Write the failing tests** in `tests/test_cli_import_budget.py`. Each probe runs in a fresh `sys.executable` subprocess, with `PYTHONPATH` set to the repo root and `cwd` set to a temp project made from `tests/integrations/claude_code/fixtures/project_memory.json`:

```python
def test_import_cli_does_not_load_subcommand_modules():
    # probe: "import sys, mneme.cli; print([m for m in LAZY if m in sys.modules])"
    assert loaded == []

@pytest.mark.parametrize("preview", [False, True])
def test_check_run_does_not_load_subcommand_modules(tmp_path, preview):
    # probe runs mneme.cli.main(["check", "--memory", M, "--input", I, "--query", "edit to storage_db.py",
    #   "--mode", "strict", "--json", "--target-path", T] + (["--applicability-preview", "x"] if preview else []))
    # inside contextlib.redirect_stdout, then prints the loaded LAZY modules to stderr as JSON
    assert loaded == []

def test_every_subcommand_help_still_renders():
    # for each name in cli._build_parser()'s subparsers choices: cli.main([name, "--help"]) raises SystemExit(0)
```

- [ ] **Step 2: Run them to confirm they fail.** Run `python -m pytest tests/test_cli_import_budget.py -v`. Expected: the two import tests FAIL and list all eleven modules; the help test PASSES, because it's a regression guard.
- [ ] **Step 3: Make the imports lazy** to the Global Constraints rules. Delete each moved `from … import …` at module level, and add it as the first statement of every function that references any of its names. Use `grep -n "\b<name>\b" mneme/cli.py` to find the users of each name.
- [ ] **Step 4: Retarget the three test patches** to the source module, e.g. `monkeypatch.setattr("mneme.protection.activate_protection", _fail)`. Leave `generate_protection_report` on `cli`.
- [ ] **Step 5: Verify.** Run these, expecting the results shown:
  - `ruff check --select F821,F811,F401 mneme/cli.py` → "All checks passed!"
  - `python -m pytest tests/test_cli_import_budget.py -v` → 4 passed
  - `python -m pytest -q` → the same pass count as `main` plus the new tests, 0 failed
  - `python scripts/run_test_battery.py --help` runs, and `tests/test_test_policy.py` passes
- [ ] **Step 6: Commit.** `git commit -m "refactor(cli): lazy-import subcommand-only modules off the check path"`.

---

### Task 2: Measure and report

**Files:**
- Create: `docs/validation/2026-10-XX-cli-lazy-imports.md`
- Create: `benchmarks/hook_latency/results/2026-10-XX-win-{editable,uvtool-py313}-lazy.json`

- [ ] **Step 1: Run the harness on an idle machine.** Use #532's harness, which precompiles bytecode:
  - `python benchmarks/hook_latency/run.py --python python --runs 50 --warmup 5 --out benchmarks/hook_latency/results/<date>-win-editable-lazy.json`
  - The same with `--python C:/Users/hi/AppData/Roaming/uv/tools/mneme-hq/Scripts/python.exe` and output `…-uvtool-py313-lazy.json`

  Expected: exit 0 for both.
- [ ] **Step 2: Compare** against `2026-10-16-win-{editable,uvtool-py313}-bytecode.json`. Record, per run:
  - (e) = `import_cli` − `import_hook`, before and after
  - the `edit_*/subprocess` p50 and p95, before and after

  **Acceptance:** the editable (e) drops by at least 50 ms (expected ~64 ms). If it doesn't, profile with `python -X importtime -c "import mneme.cli"` and record what is still loading, before claiming any result.
- [ ] **Step 3: Write the validation doc** with the setup, a before/after table and the deltas. List what wasn't covered: Linux/macOS, and real wheel installs. Commit it with the results: `git commit -m "docs: CLI lazy-import latency results"`.
- [ ] **Step 4: Report back.** Comment on MnemeHQ/mneme-growth-ops#60 with the before/after subprocess p50/p95 and the (e) delta. #60 stays in Inbox.

---

## Out of scope / follow-ups

- **`hook.py`'s own import cost on the uv 3.13 interpreter** (~123 ms; `difflib` ~27 ms). It needs its own profile first: `difflib` is used on the Edit path, so making it lazy may save nothing for Edits.
- **The remaining check-path cost** (~96 ms: `yaml` via `adr_parser`, `dataclasses`/`inspect`, `fnmatch`). A second wave, if Task 2's result justifies it.
- **In-process transport, a long-running check process, Rust:** all still parked under #60.
