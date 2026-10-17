# Hook check latency benchmark: 2026-10-16

Plan: `docs/plans/2026-10-16-hook-check-latency-benchmark.md`. Tracking: MnemeHQ/mneme-growth-ops#60.

## Setup

| | |
|---|---|
| Machine | Windows 11 Home 10.0.26300, single dev laptop, otherwise idle (only idle `decision-mcp` servers running) |
| Python | 3.12.10 |
| Code | `feat/hook-latency-benchmark` @ `578e61f` |
| Harness | `benchmarks/hook_latency/run.py`, 50 runs + 5 warmup per cell, interleaved round-robin |
| Scenarios | PreToolUse `Write` of `import sqlite3` (allowed, exit 0) and `import psycopg2` (blocked, exit 2), using the claude_code fixture memory |

Every run returned the expected verdict under both transports, in both install modes.

| Run | Install | `mneme_file` |
|---|---|---|
| `results/2026-10-16-win-editable.json` | editable, pinned to this worktree | worktree `mneme/__init__.py` |
| `results/2026-10-16-win-installed.json` | non-editable copy of the committed package in a scratch venv | venv `site-packages/mneme/__init__.py` |

**Deviations from the plan:**
- **No real wheel.** The installed run uses a non-editable copy (`git archive HEAD mneme`) instead of a built wheel. `setuptools` isn't installed, and fetching it would have been a download. Imports behave the same, because no editable finder is involved. The harness runs `python -c`, not the console-script launcher, so wheel entry-point shims aren't measured either way.
- **No Linux run.** The only WSL distro is `docker-desktop`. Still to do.

## Results (ms)

| Cell | editable p50 | editable p95 | installed p50 | installed p95 |
|---|---|---|---|---|
| `edit_allowed/subprocess` (today) | 562.9 | 644.3 | 615.1 | 659.8 |
| `edit_blocked/subprocess` (today) | 561.6 | 668.7 | 611.7 | 658.3 |
| `edit_allowed/inprocess` | 398.1 | 500.3 | 431.4 | 470.4 |
| `edit_blocked/inprocess` | 391.8 | 433.8 | 428.0 | 460.6 |
| `baseline/python_pass` | 74.0 | 81.5 | 117.2 | 127.1 |
| `baseline/import_hook` | 149.8 | 167.7 | 189.7 | 208.0 |

In-process saves 165–184 ms at p50 and 144–235 ms at p95. That is a 22–35% cut in p95.

## Attribution (p50, allowed / blocked)

| Component | editable | installed |
|---|---|---|
| (a) interpreter start | 74 | 117 |
| (b) hook import | 76 | 72 |
| (c) second interpreter + check work (subprocess − import_hook) | 413 / 412 | 425 / 422 |
| (d) check work in-process (inprocess − import_hook) | 248 / 242 | 242 / 238 |
| (c) − (d) ≈ second interpreter | 165 / 170 | 183 / 184 |

**What makes up (d).** In a separate quick measurement (`-X importtime`, plus timed imports, three runs), importing `mneme.cli` took about 2.6× as long as importing the hook. It pulls in every subcommand's modules at import time, for example `mneme.benchmark`, `mneme.protection`, `mneme.setup`, `mneme.adr_import` and `mneme.adr_freshness`/`adr_diagnostics`. Scaling that ratio to the benchmark's ~76 ms hook import puts the `mneme.cli` import at roughly 200 ms of the ~245 ms in (d). This is an estimate: the quick measurement ran ~1.6× slower overall than the benchmark, and it was not profiled inside the harness. Loading memory and evaluating rules is the remainder, and small, for this fixture.

## Decision

Applying the plan's rule:

| Rule | Result |
|---|---|
| Subprocess p95 ≤ 300 ms on all platforms? | **No**: 644–669 ms. The latency is real |
| In-process removes ≥ 40% of subprocess p95? | **No**: 22–35% |
| In-process p95 > 300 ms and (a) is most of it? | **No**: (a) is 74–117 ms of 434–500 ms |
| Check work (d) dominates? | **Yes**: ~240–250 ms, mostly the `mneme.cli` import |

**Next step: profile before any language change.** The cheapest candidate is not Rust, and not keeping a process running between writes. It is not loading every subcommand's modules when only `check` is needed: lazy imports in `mneme/cli.py`, or a slim check entry point. That would help the subprocess path too, with no change to how the check is run or to its failure behaviour. Rust stays parked, and #60 stays in Inbox.

**Not established:**
- Linux and macOS numbers.
- A real wheel/console-script install.
- Larger, real-world memory files, where load and evaluation could matter more.
- Cold-cache first runs (warmups were discarded).
