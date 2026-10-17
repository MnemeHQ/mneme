# Hook check latency benchmark: 2026-10-16

Plan: `docs/plans/2026-10-16-hook-check-latency-benchmark.md`. Tracking: MnemeHQ/mneme-growth-ops#60.

> **Correction (later on 2026-10-16):** the results below were measured without cached bytecode, so every run recompiled mneme from source. They overstate absolute latency. See [Correction: with cached bytecode](#correction-with-cached-bytecode) at the end; the decision is unchanged.

**Scope: Windows only, so the decision below is provisional.** The plan's first decision rule asks about "all platforms", and Linux and macOS have not been measured.

## Setup

| | |
|---|---|
| Machine | Windows 11 Home 10.0.26300, one dev laptop. No other workload was running (only idle `decision-mcp` servers), as checked by a process listing before the runs |
| Python | 3.12.10 |
| Code | `feat/hook-latency-benchmark` @ `96d856d` (after the review fix pass) |
| Harness | `benchmarks/hook_latency/run.py`, 50 runs + 5 warmup per cell, interleaved round-robin, started via `python -c` (not the `mneme-hook` console-script launcher) |
| Scenarios | PreToolUse `Write` of `import sqlite3` (allowed, exit 0) and `import psycopg2` (blocked, exit 2), using the claude_code fixture memory (one decision) |

Every run returned the expected verdict under both transports, in both install modes.

| Run | Install | `mneme_file` |
|---|---|---|
| `results/2026-10-16-win-editable.json` | editable, pinned to this worktree | worktree `mneme/__init__.py` |
| `results/2026-10-16-win-installed.json` | non-editable copy of the committed package in a scratch venv | venv `site-packages/mneme/__init__.py` |

**Deviations from the plan:**
- **No real wheel.** The installed run uses a non-editable copy (`git archive HEAD mneme`) instead of a built wheel. `setuptools` isn't installed, and fetching it would have been a download. Imports behave the same, because no editable finder is involved. Two caveats:
  - The scratch venv uses `--system-site-packages` to get its dependencies. That likely explains why its bare `python -c pass` is ~45 ms slower than the editable run's: two site directories' `.pth` files get processed. So absolute "installed" numbers run high compared with a clean install.
  - Console-script shims aren't measured in either mode. The real launcher would only add time.
- **No Linux run.** The only WSL distro is `docker-desktop`.

## Results (ms)

| Cell | editable p50 | editable p95 | installed p50 | installed p95 |
|---|---|---|---|---|
| `edit_allowed/subprocess` (today) | 505.8 | 542.9 | 615.6 | 646.7 |
| `edit_blocked/subprocess` (today) | 510.1 | 547.3 | 612.9 | 681.8 |
| `edit_allowed/inprocess` | 351.6 | 380.2 | 432.7 | 505.9 |
| `edit_blocked/inprocess` | 353.9 | 387.3 | 435.9 | 482.1 |
| `baseline/python_pass` | 74.9 | 80.4 | 120.3 | 128.3 |
| `baseline/import_hook` | 144.0 | 153.0 | 189.3 | 207.1 |
| `baseline/import_cli` (hook + `mneme.cli`) | 336.6 | 362.8 | 419.2 | 448.8 |

In-process saves 154–183 ms at p50. It cuts p95 by 22–30%.

## Attribution (p50 throughout, allowed / blocked)

| Component | editable | installed |
|---|---|---|
| (a) interpreter start (`python_pass`) | 75 | 120 |
| (b) hook import (`import_hook` − a) | 69 | 69 |
| (c) subprocess check (`subprocess` − `import_hook`) | 362 / 366 | 426 / 424 |
| (d) in-process check (`inprocess` − `import_hook`) | 208 / 210 | 243 / 247 |
| (e) `mneme.cli` import (`import_cli` − `import_hook`), measured | 193 | 230 |
| (d) − (e): memory load + rule evaluation | ~15 / ~17 | ~13 / ~17 |
| (c) − (d): second process | 154 / 156 | 183 / 177 |

- **(e) is now measured, not estimated.** Importing `mneme.cli` is about 93% of the check work. `mneme.cli` imports every subcommand's modules at load time (`-X importtime` shows `mneme.benchmark`, `mneme.protection`, `mneme.setup`, `mneme.adr_import` and `mneme.adr_freshness`/`adr_diagnostics` among the largest). Loading memory and evaluating rules takes about 15 ms for this one-decision fixture.
- **(c) − (d) is more than interpreter start.** It is larger than (a) because it also includes Windows process spawn and the imports the child repeats but the in-process run shares (stdlib and the `mneme` package).

## Decision (provisional: Windows only)

Applying the plan's rule:

| Rule | Result |
|---|---|
| Subprocess p95 ≤ 300 ms on all platforms? | **No** on Windows: 543–682 ms. The latency is real |
| In-process removes ≥ 40% of subprocess p95? | **No**: 22–30% |
| In-process still > 300 ms and (a) is most of it? (p50) | **No**: (a) is 75–120 ms of 352–436 ms |
| Check work (d) dominates? | **Yes**: 208–247 ms, ~93% of it the `mneme.cli` import |

**Next step:** cut what the `check` path imports. Two options: lazy imports in `mneme/cli.py`, or a slim check entry point that doesn't load every subcommand. That helps today's subprocess path too, with no change to how the check is run or to its failure behaviour. Rust stays parked, and #60 stays in Inbox.

*This departs from the plan.* Rule row 4 says to profile `MemoryStore.load` and `check_prompt`. The measurement shows those take about 15 ms, so the target moves to the CLI import.

## Not established

- Linux and macOS.
- A real wheel and the console-script launcher.
- Larger, real-world memory files, where load and evaluation (currently ~15 ms) could grow.
- Cold-cache first runs (warmups were discarded).
- **Watchdog limitation (in-process only):** the 10 s fail-open timer is a Python thread, so it cannot interrupt a check stuck inside a single C call that holds the GIL, such as catastrophic regex backtracking. The subprocess timeout can kill such a child. This needs addressing before in-process is ever considered for production.

## Correction: with cached bytecode

**What went wrong.** The harness inherited `PYTHONDONTWRITEBYTECODE=1` from the agent shell it was started from, and it ran in a fresh worktree with no `__pycache__`. Together those meant every run recompiled every `mneme` module from source. Real installs don't do that: the uv-installed `mneme-hq` has bytecode for every module on the check path. The harness now removes the variable and byte-compiles the measured package before timing (`fix/bench-bytecode`).

**Re-run:** 50 runs + 5 warmup per cell, every verdict correct, `settings.bytecode = "precompiled"`.

| p50 / p95 ms | editable 3.12 | installed copy 3.12 | uv `mneme-hq` interpreter 3.13 (pinned to branch) |
|---|---|---|---|
| `edit_*/subprocess` (today) | 426 / 446–453 | 491–502 / 555–571 | 551–554 / 592–595 |
| `edit_*/inprocess` | 272–273 / 287–292 | 321 / 352–363 | 382–386 / 419–422 |
| `baseline/python_pass` | 75 / 80 | 119 / 133 | 62 / 66 |
| `baseline/import_hook` | 132 / 145 | 177 / 205 | 185 / 200 |
| `baseline/import_cli` | 256 / 271 | 306 / 356 | 365 / 399 |

Files: `results/2026-10-16-win-{editable,installed,uvtool-py313}-bytecode.json`. The uv run uses the interpreter real hooks run under (`mneme-hq` via `uv tool`), with `PYTHONPATH` pinned to the branch code.

**Attribution (p50):**

| Component | editable | installed | uv 3.13 |
|---|---|---|---|
| (e) `mneme.cli` import (`import_cli` − `import_hook`) | 124 | 128 | 180 |
| (d) in-process check (`inprocess` − `import_hook`) | 140 | 144 | 199 |
| (d) − (e): memory load + evaluation | ~16 | ~16 | ~19 |
| (c) − (d): second process | 153–154 | 169–181 | 165–172 |
| In-process cut in p95 | 35–36% | 35–38% | 29–30% |

**What changes:**
- **Absolute latency is lower** than first reported. Today's subprocess p50 is 426–554 ms, not 506–616 ms. It's still above the plan's 300 ms threshold.
- **The `mneme.cli` import is still most of the check work:** 86–90% of (d).
- **In-process now cuts 29–38% of p95,** still under the plan's 40% bar.
- **The decision rows give the same answers:** the latency is real; in-process stays below 40%; interpreter start is not most of it; check work dominates.
- **Revised estimate for the planned lazy-import change:** importing only what `check` needs costs ~86–88 ms with bytecode, against ~156–158 ms for the full `mneme.cli` (separate measurements, 3.12). So the expected saving is about **70 ms per write**, not ~100 ms.

**New observation (uv 3.13 interpreter):** the hook's own import costs ~123 ms there, against ~58 ms on 3.12. The stdlib imports are heavier on that interpreter, and `difflib` alone is ~27 ms. That's a second lazy-import candidate, in `hook.py`. It hasn't been profiled further.

