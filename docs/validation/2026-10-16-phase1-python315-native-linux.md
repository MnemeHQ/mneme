# Hook latency Phase 1: Python 3.15, lazy imports, native floor, Linux (2026-10-16)

Tracking: MnemeHQ/mneme-growth-ops#60. Previous results: `2026-10-16-hook-check-latency-benchmark.md` (corrected with bytecode) and `2026-10-16-cli-lazy-imports.md` (#533).

**Question:** does upgrading Python (3.15, PEP 810 lazy imports) or replacing Python with a native checker change the decision on #60? All numbers are for the shipped path (hook → subprocess `mneme check`) on `main` after #533 and #534, with cached bytecode, 50 runs + 5 warmup per cell. Every run returned the expected verdict.

## Setup

| | Windows | Linux |
|---|---|---|
| Machine | Windows 11 laptop, idle | GitHub-hosted `ubuntu-latest` (shared VM; indicative only), run `38994469179` at `0627514` |
| Interpreters | uv-managed CPython 3.13.12 and 3.15.0 (both python-build-standalone) | `actions/setup-python` 3.13.16 and 3.15.0 |
| Dependencies | the same pure-Python PyYAML 6.0.1 copy (compiled extension removed) on `PYTHONPATH` for both; no site-packages | the same, via `pip --target` with the compiled extension removed |
| Results | `results/2026-10-16-win-uvpy{313,315}-clean.json`, `…-uvpy315-lazy-all.json` | `results/2026-10-16-linux-ci-py{313,315}.json`, `…-py315-lazy-all.json` |

*Lazy-all* means `PYTHON_LAZY_IMPORTS=all` (PEP 810 global mode), which applies to the hook process and the check process it starts. The Windows runs for each interpreter were separate sessions, not interleaved.

## Results: shipped path p50 (p95), ms

| | Windows | Linux |
|---|---|---|
| Python 3.13 | 429–431 (464–490) | 142.5–142.6 (145–148) |
| Python 3.15 | 370 (405–407), **−14%** | 139.4–139.7 (142), **−2%** |
| Python 3.15 + lazy-all | **261–264 (312–316), −39%** | **96–98 (98), −32%** |
| Native process spawn (`hostname.exe` / `true`) | 16.7–16.9 | 0.7–0.9 |
| Bare `python -c pass` (3.13 / 3.15) | 41 / 34 | 11 / 12 |

The `import_hook` and `import_cli` baseline cells mean nothing under lazy-all, because a bare `import X` no longer loads X. They are left out here.

## Native-checker bounds (estimates, using 3.13)

These are derived from measured cells. They are not a Rust prototype.
- "Native work" means loading memory and evaluating rules natively. In Python that step takes ~15–19 ms; native is assumed to take 2–20 ms.
- "Python hook" means `import_hook`, i.e. interpreter start plus the hook import.

| Path | Windows p50 | Linux p50 |
|---|---|---|
| Today | ~430 | ~142 |
| Native checker, Python hook kept: `import_hook` + native spawn + native work | ~190–210 | ~53–71 |
| Native hook and checker in one process: native spawn + native work | ~20–37 | ~3–21 |
| Python 3.15 lazy-all (measured, for comparison) | ~262 | ~97 |

## Correctness under lazy-all

- **Harness verdict gate:** every allowed and blocked run returned the right exit code on both OSes.
- **Mneme's tests with lazy-all in the check processes:** 434 passed, 2 skipped, on Windows 3.15. This covers `tests/integrations/claude_code` (hook end-to-end under both transports, including fail-open on a malformed memory), `test_check_json.py` and `test_check_modes.py`. The pytest process itself ran with `-X lazy_imports=normal`, while the check processes it starts inherited `PYTHON_LAZY_IMPORTS=all`.
- **Global lazy-all breaks pytest itself:** `ImportCycleError: cannot import name 'fnmatch'` while importing `_pytest`. So global mode can turn a working eager import graph into an error at first use. On the enforcement path, an import error at first use is a crash, and a crash fails open. That is why global lazy-all is not safe to rely on blindly.
- **3.15 normal mode:** 435 passed. Three `test_cli_import_budget.py` probes failed only because they clear `PYTHONPATH` and couldn't see the scratch PyYAML copy, an artifact of this setup.

## Findings

1. **On Linux, the shipped path already meets the 300 ms bar**, at ~142 ms p50. The latency problem is mostly Windows, where Python start and process spawn cost far more (native spawn 17 ms vs 0.9 ms; bare Python 41 ms vs 11 ms).
2. **Upgrading to 3.15 alone helps Windows (−14%) but barely changes Linux (−2%).** On Windows this is between two python-build-standalone builds, one session each, so treat it as indicative.
3. **Lazy loading is the large lever:** lazy-all cuts ~29–30% compared with plain 3.15 (32–39% compared with 3.13), bringing Windows p50 to ~262 ms. That is under the 300 ms bar, though p95 is ~312–316 ms. Global mode is a measurement tool, not something to ship.
4. **A native checker that keeps the Python hook** would land at about the same place as 3.15 lazy-all: ~190–210 ms vs ~262 ms on Windows, and ~53–71 vs ~97 ms on Linux. The decisive native gain only comes from **porting the hook too**, which means a second implementation of the hook's write-gating logic (Edit/MultiEdit materialization, introduced-content diff, Bash gate, Stop and session state) plus the checker's DG1 semantics.

## Decision (under the Phase 2 gate in #60)

- **Latency doesn't justify Rust.** Linux already passes; Windows reaches the bar through Python-side lazy loading. Rust stays parked unless a written **embedding or no-Python requirement** appears; then the compiled enforcement bundle ADR comes first.
- **Python-side next step, optional and separate:** controlled per-module lazy loading via `__lazy_modules__` on the hook and check path. It is ignored before 3.15, so it only adds savings on 3.15 and keeps the ≥3.11 floor. It is preferable to global mode because each module is chosen and tested. It needs an import-error-at-first-use test so a late import failure can't silently fail open.
- **#60 stays in Inbox.**

## Not established

- A controlled same-machine 3.13 vs 3.15 comparison with interleaved sessions.
- macOS.
- Real wheel or console-script installs.
- Large real-world memory files.
- What `__lazy_modules__` (as opposed to global lazy-all) would actually deliver.
- Native-checker numbers are bounds, not a prototype.
