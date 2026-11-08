# Hook Check Latency Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure end-to-end PreToolUse latency of `mneme-hook` with today's subprocess `mneme check` against an experimental in-process check. The result decides whether issue #60 has a real performance problem, and if so, whether Python architecture changes are enough without Rust.

**Architecture:** Add a benchmark-only in-process check that sits behind the existing `_invoke_check` interface in the hook and returns the same `CompletedProcess` shape. It runs `mneme.cli.main` with the same argv. An env var turns it on, and only the PreToolUse path uses it. A separate harness launches the hook as a fresh process per run, the way Claude Code does. It times both transports on allowed and blocked edits, under editable and wheel installs.

**Tech Stack:** Python 3 (repo's existing floor), pytest, stdlib only (`subprocess`, `time.perf_counter`, `statistics`, `contextlib`, `threading`).

**Spec:** Issue [MnemeHQ/mneme-growth-ops#60](https://github.com/MnemeHQ/mneme-growth-ops/issues/60), comments 2026-10-16: the baseline and "each write starts Python twice".

**Repo:** All code tasks are in `MnemeHQ/mneme` (local `C:\dev\mneme`), cut from `main` at or after `527485e6`. Branch `feat/hook-latency-benchmark`, merged by squash. Before execution, move this plan into the mneme repo's `docs/plans/`.

## Global Constraints

- The production default stays `subprocess`. With `MNEME_HOOK_CHECK_TRANSPORT` unset, hook behaviour is byte-for-byte what it is today.
- The in-process transport is **benchmark-only**. It is not documented as a user option and must not be the default anywhere, including the plugin config and the CI hooks config.
- No change to Layer 1 semantics, decision selection, verdict computation, `mneme.check/v1` JSON, or exit codes.
- No change to fail-open behaviour on the subprocess path. Any production change to failure behaviour needs a separate architecture review (ADR-027 context).
- Only the PreToolUse `_run_check` path may use the in-process transport. The Stop and rename callers (`hook.py` ~L816, ~L824, ~L954) stay on subprocess, because they count a `None` result as "untrusted" and report it rather than exiting.
- Timeout stays `_CHECK_TIMEOUT_SECONDS = 10`.
- Hook stdout and stderr stay ASCII-only (existing hook rule).

## Review Focus

1. **Hung check in-process.** If the check runs past 10 s, the watchdog must end the hook process with exit 0 and the existing "Failing open" stderr line. A plain timer that returns while the check keeps running is not enough. *Test: Task 2, `test_inprocess_timeout_fails_open`.*
2. **Crashing check in-process.** A malformed memory file raises inside `cli.main`, where in subprocess mode the child exits non-zero with a traceback. In-process mode must turn the exception into the same shape (returncode 1, traceback on stderr, empty stdout) so `assess_verdict` reaches the same fail-open branch. *Test: Task 1, `test_inprocess_crash_matches_subprocess_shape`.*
3. **argparse `SystemExit`.** A stale or invalid argv makes argparse call `sys.exit(2)`. In-process mode must catch `SystemExit` and return its code, not kill the hook. *Test: Task 1, `test_inprocess_systemexit_becomes_returncode`.*
4. **Leaks between the CLI and the hook process.** `cli.main` calls `_force_utf8_stdio()`, which reconfigures `sys.stdout` and `sys.stderr`. In-process mode must leave the hook's real streams untouched, so redirect both before the call. *Test: Task 1, `test_inprocess_does_not_touch_real_streams`.*
5. **Version pinning.** In-process mode must run the `mneme.cli` from the same package tree as the hook. That is the guarantee `_child_env()` gives today. *Test: Task 1, `test_inprocess_uses_hook_package_tree`.*

---

## File Structure

| File | Responsibility |
|---|---|
| `mneme/integrations/claude_code/inprocess_check.py` (create) | `run_check_inprocess(argv) -> CompletedProcess`: run `mneme.cli.main` with captured streams; no policy |
| `mneme/integrations/claude_code/hook.py` (modify ~L202–252, L519–574, L576–590) | Pick the transport and start the watchdog; PreToolUse path only |
| `tests/integrations/claude_code/test_inprocess_check.py` (create) | Parity of returned results and Review Focus 2–5 |
| `tests/integrations/claude_code/test_hook_e2e.py` (modify) | Run the existing e2e cases under both transports |
| `benchmarks/hook_latency/run.py` (create) | Harness: scenarios × transports × N runs → JSON + markdown summary |
| `benchmarks/hook_latency/README.md` (create) | How to run it, editable vs wheel, how to read the output |
| `tests/test_hook_latency_harness.py` (create) | Unit tests for the harness's stats and scenario-correctness check |
| `docs/validation/2026-10-XX-hook-check-latency-benchmark.md` (create, Task 4) | Recorded results and the decision |

---

### Task 1: In-process check runner with parity tests

**Files:**
- Create: `mneme/integrations/claude_code/inprocess_check.py`
- Test: `tests/integrations/claude_code/test_inprocess_check.py`

**Interfaces:**
- Consumes: `mneme.cli.main(argv: list[str] | None) -> int` (unchanged).
- Produces: `run_check_inprocess(argv: list[str]) -> subprocess.CompletedProcess[str]`. Here `argv` is the argument list **after** `-m mneme`, e.g. `["check", "--memory", ..., "--json"]`. The returned `.args` is `argv`, and `.returncode`, `.stdout` and `.stderr` are filled in. It never raises for `Exception` or `SystemExit` coming from `cli.main`.

- [ ] **Step 1: Write the failing tests.** Use the `project` fixture pattern and `FIXTURE` from `test_hook_e2e.py`. Write an input file containing `import psycopg2` for the blocked case and `import sqlite3` for the allowed case. Build `argv = ["check", "--memory", str(mem), "--input", str(inp), "--query", "edit to storage_db.py", "--mode", "strict", "--json", "--target-path", str(target)]`.

```python
def test_inprocess_matches_subprocess_blocked(project): ...
    # sub = subprocess.run([sys.executable, "-m", "mneme", *argv], capture_output=True, text=True, env=hook._child_env())
    # inp = run_check_inprocess(argv)
    assert inp.returncode == sub.returncode
    assert json.loads(inp.stdout) == json.loads(sub.stdout)
    assert json.loads(inp.stdout)["verdict"] in {"WARN", "FAIL"}

def test_inprocess_matches_subprocess_allowed(project): ...
    assert inp.returncode == sub.returncode == 0
    assert json.loads(inp.stdout) == json.loads(sub.stdout)

def test_inprocess_crash_matches_subprocess_shape(project):      # Review Focus 2
    # memory file = "{ this is not valid json"
    assert inp.returncode != 0 and sub.returncode != 0
    assert inp.stdout == ""
    assert "Traceback" in inp.stderr
    assert hook.assess_verdict(inp.stdout, inp.returncode, "strict").payload is None

def test_inprocess_systemexit_becomes_returncode():               # Review Focus 3
    r = run_check_inprocess(["check", "--no-such-flag"])
    assert r.returncode == 2

def test_inprocess_does_not_touch_real_streams(project):          # Review Focus 4
    before = (sys.stdout, sys.stderr)
    run_check_inprocess(argv)
    assert (sys.stdout, sys.stderr) == before

def test_inprocess_uses_hook_package_tree():                     # Review Focus 5
    import mneme.cli, mneme.integrations.claude_code.hook as h
    assert Path(mneme.cli.__file__).resolve().parents[1] == h._PACKAGE_ROOT
```

- [ ] **Step 2: Run them to confirm they fail.** Run `pytest tests/integrations/claude_code/test_inprocess_check.py -v`. Expected: collection error, `ModuleNotFoundError: mneme.integrations.claude_code.inprocess_check`.

- [ ] **Step 3: Implement `run_check_inprocess(argv)`.** Use `contextlib.redirect_stdout` and `redirect_stderr` into two `io.StringIO`, then call `mneme.cli.main(argv)`. On `SystemExit as e`, set the returncode to `e.code if isinstance(e.code, int) else 1`. On any other `Exception`, write `traceback.format_exc()` to the captured stderr and use returncode 1. Import `mneme.cli` lazily inside the function, so the subprocess path never pays its import cost.

- [ ] **Step 4: Run them to confirm they pass.** Same command. Expected: 6 passed.

- [ ] **Step 5: Commit.** `git add` the two files, then `git commit -m "feat(hook): benchmark-only in-process check runner"`.

---

### Task 2: Transport selection and watchdog in the hook (PreToolUse only)

**Files:**
- Modify: `mneme/integrations/claude_code/hook.py`. Add constants near L202. Add a `transport` parameter to `_invoke_check` (L519). Make `_run_check` (L586) pass the resolved transport.
- Modify: `tests/integrations/claude_code/test_hook_e2e.py`
- Test: `tests/integrations/claude_code/test_hook_transport.py` (create)

**Interfaces:**
- Consumes: `run_check_inprocess` (Task 1).
- Produces:
  - `_TRANSPORT_ENV_VAR = "MNEME_HOOK_CHECK_TRANSPORT"` and `_VALID_TRANSPORTS = ("subprocess", "inprocess")`.
  - `resolve_transport() -> str`: returns `"subprocess"` when the variable is unset, empty or unknown.
  - `_invoke_check(..., transport: str = "subprocess")`: same return contract as today.
  - Only `_run_check` passes `resolve_transport()`. The calls at ~L816, ~L824 and ~L954 stay unchanged and keep the default.

- [ ] **Step 1: Write the failing tests** in `test_hook_transport.py`:

```python
@pytest.mark.parametrize("value,expected", [
    (None, "subprocess"), ("", "subprocess"), ("bogus", "subprocess"),
    ("inprocess", "inprocess"), (" INPROCESS ", "inprocess"),   # strip+lower, like resolve_mode
])
def test_resolve_transport(monkeypatch, value, expected): ...

def test_stop_path_never_uses_inprocess(monkeypatch):
    # env = inprocess; monkeypatch run_check_inprocess to raise AssertionError;
    # drive the Stop-event case from test_stop_boundary.py; it must complete normally

def test_inprocess_timeout_fails_open(project):                  # Review Focus 1
    # Real child hook process, blocked-edit envelope on stdin, env:
    #   MNEME_HOOK_CHECK_TRANSPORT=inprocess, MNEME_HOOK_CHECK_TIMEOUT_TEST=1, MNEME_HOOK_TEST_STALL_SECONDS=5
    assert proc.returncode == 0
    assert "failing open" in proc.stderr.lower()
    assert elapsed_s < 4
```

Also parametrize every test in `test_hook_e2e.py` with `transport in ("subprocess", "inprocess")` via `monkeypatch.setenv(_TRANSPORT_ENV_VAR, transport)`. They must all pass unchanged, including `test_malformed_memory_fails_open_against_real_cli` and the warn-mode `defer` case.

- [ ] **Step 2: Run them to confirm they fail.** Run `pytest tests/integrations/claude_code/test_hook_transport.py tests/integrations/claude_code/test_hook_e2e.py -v`. Expected: `ImportError` for `resolve_transport`.

- [ ] **Step 3: Implement it.** In `_invoke_check`, when `transport == "inprocess"`:
  - Write the temp input file exactly as today.
  - Build the same argv without the `sys.executable, -m, mneme` prefix.
  - Start a daemon `threading.Timer(timeout, _inprocess_timeout)`. `_inprocess_timeout` prints `mneme-hook: check could not run (timed out after {timeout}s, in-process). Failing open.` to `sys.__stderr__`, flushes, and calls `os._exit(0)`.
  - Call `run_check_inprocess`, cancel the timer in `finally`, and keep the existing temp-file unlink.

  For the test, the timeout comes from `float(os.environ.get("MNEME_HOOK_CHECK_TIMEOUT_TEST", _CHECK_TIMEOUT_SECONDS))`, read **only** on the in-process branch. The stall is a `time.sleep(float(os.environ["MNEME_HOOK_TEST_STALL_SECONDS"]))` before `run_check_inprocess`, only when that variable is set. Both variables carry a `# benchmark/test seam` comment.

- [ ] **Step 4: Run them to confirm they pass.** Run `pytest tests/integrations/claude_code -v`. Expected: all pass, the e2e cases twice each. Then run the full suite with `pytest -q`. Expected: same pass count as `main` plus the new tests, with no new failures.

- [ ] **Step 5: Commit.** `git commit -m "feat(hook): MNEME_HOOK_CHECK_TRANSPORT benchmark switch (PreToolUse only)"`.

---

### Task 3: Latency harness

**Files:**
- Create: `benchmarks/hook_latency/run.py` and `benchmarks/hook_latency/README.md`
- Test: `tests/test_hook_latency_harness.py`

**Interfaces:**
- Produces:
  - `summarize(samples_ms: list[float]) -> dict` with keys `n, p50, p95, max, mean`. Uses `statistics.quantiles(samples, n=100, method="inclusive")`, where index 49 is p50 and index 94 is p95. Rounded to 0.1 ms.
  - `SCENARIOS: dict[str, Scenario]`, where `Scenario = NamedTuple(envelope_tool: str, new_string: str, expected_exit: int)`. The two required scenarios are `edit_allowed` (`"import sqlite3"`, exit 0) and `edit_blocked` (`"import psycopg2"`, exit 2).
  - `run_once(python: str, project: Path, scenario: Scenario, transport: str) -> tuple[float, int, str]`: wall-clock ms, exit code, stderr.
  - CLI: `python benchmarks/hook_latency/run.py --python <interp> --runs 50 --warmup 5 --out <file.json>`.

**Behaviour the tests pin:**
- Each run is a **fresh process**: `[python, "-c", "from mneme.integrations.claude_code.hook import cli_main; cli_main()"]`, with the envelope on stdin and `cwd` set to the temp project. This is how Claude Code starts the hook.
- The project is created once per invocation from `tests/integrations/claude_code/fixtures/project_memory.json`, and the target file is re-seeded before every run.
- Runs are interleaved round-robin across (scenario × transport) so that thermal or cache drift affects every cell equally. Warmups are discarded.
- Any run whose exit code ≠ `expected_exit` puts the harness in error: it exits 1, prints the cell, and writes no summary. A fast wrong answer is a failure, not a result.
- Two baseline cells are timed with the same runner: `python -c pass` and `python -c "import mneme.integrations.claude_code.hook"`.
- Output JSON records `python_version`, `platform.platform()`, `mneme.__file__` (shows editable vs wheel), the git SHA, the run settings, and per-cell `summarize` plus the raw samples.
- A markdown table goes to stdout with one row per cell: p50, p95, max, and the in-process minus subprocess delta for each scenario.

- [ ] **Step 1: Write the failing tests:**

```python
def test_summarize_known_values():
    s = summarize([float(i) for i in range(1, 101)])
    assert s["n"] == 100 and s["p50"] == 50.5 and s["p95"] == 95.05 and s["max"] == 100.0

def test_wrong_exit_code_fails_harness(tmp_path, monkeypatch):
    # monkeypatch run_once to return (10.0, 0, "") for edit_blocked
    assert main(["--python", sys.executable, "--runs", "2", "--warmup", "0", "--out", str(tmp_path/"o.json")]) == 1
    assert not (tmp_path / "o.json").exists()

def test_real_smoke_both_transports(tmp_path):
    rc = main(["--python", sys.executable, "--runs", "2", "--warmup", "0", "--out", str(tmp_path/"o.json")])
    data = json.loads((tmp_path/"o.json").read_text())
    assert rc == 0
    assert {"edit_allowed/subprocess", "edit_allowed/inprocess", "edit_blocked/subprocess", "edit_blocked/inprocess", "baseline/python_pass", "baseline/import_hook"} <= set(data["cells"])
```

- [ ] **Step 2: Run them to confirm they fail.** Run `pytest tests/test_hook_latency_harness.py -v`. Expected: `ModuleNotFoundError`.
- [ ] **Step 3: Implement `run.py`** to the interfaces and behaviour above. Write a README covering both install modes: editable (`pip install -e .`) and wheel (`python -m build` → `python -m venv .bench-wheel` → `.bench-wheel/Scripts/pip install dist/*.whl`, then `--python .bench-wheel/Scripts/python`).
- [ ] **Step 4: Run them to confirm they pass.** Same command. Expected: 3 passed.
- [ ] **Step 5: Commit.** `git commit -m "feat(bench): hook PreToolUse latency harness"`.

---

### Task 4: Run, record, decide

**Files:**
- Create: `docs/validation/2026-10-XX-hook-check-latency-benchmark.md`
- Create: `benchmarks/hook_latency/results/<date>-<os>-<editable|wheel>.json`, one per run

- [ ] **Step 1: Windows, editable.** Run `python benchmarks/hook_latency/run.py --python python --runs 50 --warmup 5 --out benchmarks/hook_latency/results/<date>-win-editable.json`. Expected: exit 0, all 6 cells present.
- [ ] **Step 2: Windows, wheel.** Same, with `--python .bench-wheel/Scripts/python` and output `...-win-wheel.json`. Confirm `mneme_file` in the JSON points into `.bench-wheel`, not the repo.
- [ ] **Step 3: Linux, wheel.** Use WSL or a disposable Ubuntu box with the same SHA. Output `...-linux-wheel.json`.
- [ ] **Step 4: Attribute the cost.** For each run, write down:
  - (a) `baseline/python_pass` p50
  - (b) `import_hook` − (a)
  - (c) `edit_*/subprocess` − `import_hook`: the second interpreter plus check work
  - (d) `edit_*/inprocess` − `import_hook`: check work without the second interpreter

  Then (c) − (d) ≈ the cost of the second interpreter.
- [ ] **Step 5: Write the validation doc.** Include the setup (machine, Python version, SHA, install mode), the tables, the attribution, and the decision under the rule below. Commit the doc and results JSON: `git commit -m "docs: hook check latency benchmark results"`.
- [ ] **Step 6: Report back.** Comment on growth-ops issue #60 with a link to the doc, the three p95 numbers per platform, and the decision. Leave Stage = Inbox unless the decision rule says otherwise.

**Decision rule** (proposed; confirm before running):

| Result | Next step |
|---|---|
| Subprocess p95 ≤ 300 ms on all platforms | Not a real problem. Move #60 to *Parked / Rejected* with the evidence attached |
| In-process removes ≥ 40% of subprocess p95 | Open an architecture review for in-process (timeout, isolation, fail-open). Rust stays parked |
| In-process p95 is still > 300 ms, and (a) is most of it | Interpreter startup dominates. A native launcher (Rust or similar) becomes the next spike; #60 → *Discovery* |
| Check work (d) dominates | Profile `MemoryStore.load` and `check_prompt` before thinking about any language change |

---

## Out of scope

Persistent-service transport (path 2 in #60) and any native or Rust launcher (path 3). Both only make sense after Task 4's attribution. Also out of scope: Kiro, Codex and other hook adapters, CI-level enforcement, and any change to production failure behaviour.
