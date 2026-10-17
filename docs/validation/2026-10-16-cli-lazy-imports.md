# CLI lazy imports: hook latency results (2026-10-16)

Plan: `docs/plans/2026-10-16-cli-lazy-imports.md`. Tracking: MnemeHQ/mneme-growth-ops#60. Baseline: `docs/validation/2026-10-16-hook-check-latency-benchmark.md` § "Correction: with cached bytecode".

## Change

`mneme/cli.py` no longer imports eleven modules at load time that only other subcommands use: `mneme.integrations.eventcatalog`, `benchmark`, `benchmark_report`, `cursor_generator`, `decision_add`, `decision_authority`, `decision_proposal_store`, `protection`, `readiness`, `setup`, `setup_state`. Each one is imported as the first statement of the command functions that use it.

`tests/test_cli_import_budget.py` checks this in a fresh interpreter. It covers importing `mneme.cli`, a full `check --json` run with and without `--applicability-preview`, and `--help` for every subcommand. How the hook starts the check, its subprocess, its timeout and its fail-open behaviour are all unchanged.

## Setup

Windows 11 Home 10.0.26300, idle. Harness `benchmarks/hook_latency/run.py` with cached bytecode (precompiled, `PYTHONDONTWRITEBYTECODE` removed), 50 runs + 5 warmup per cell, interleaved. Every run returned the expected verdict. Code: `refactor/cli-lazy-imports` @ `a978263`, compared with the `*-bytecode.json` baseline taken from `main` before this change.

| Run | Interpreter | Results |
|---|---|---|
| editable | Python 3.12.10, pinned to the worktree | `results/2026-10-16-win-editable-lazy.json` |
| uv tool | `mneme-hq` uv interpreter, Python 3.13.12 (what real hooks run under), pinned to the worktree | `results/2026-10-16-win-uvtool-py313-lazy.json` |

## Results (ms)

| Cell | editable p50 before → after | editable p95 before → after | uv 3.13 p50 before → after | uv 3.13 p95 before → after |
|---|---|---|---|---|
| `edit_allowed/subprocess` (shipped path) | 426.0 → 366.0 (−60.0) | 445.7 → 387.9 (−57.8) | 551.4 → 461.4 (−90.0) | 592.1 → 489.9 (−102.2) |
| `edit_blocked/subprocess` (shipped path) | 426.7 → 367.4 (−59.3) | 452.9 → 391.5 (−61.4) | 554.0 → 461.8 (−92.2) | 595.2 → 495.5 (−99.7) |
| `edit_allowed/inprocess` (benchmark-only) | 271.8 → 212.1 | 286.7 → 234.1 | 386.3 → 289.4 | 422.4 → 315.1 |
| `edit_blocked/inprocess` (benchmark-only) | 273.4 → 214.4 | 292.3 → 230.2 | 382.4 → 289.7 | 418.9 → 315.2 |

**CLI import, (e) = `import_cli` − `import_hook` (p50):**
- editable: 123.6 → 64.1 ms (−59.5)
- uv 3.13: 180.3 → 90.7 ms (−89.6)

Acceptance (editable (e) drops by ≥ 50 ms): **met.**

## Reading

- **The shipped hook path gets 58–102 ms faster per write.** That's a 14–17% cut in subprocess p50, with no change to how the check runs.
- **The saving is bigger on the real uv 3.13 interpreter** (~90 ms) than on 3.12 (~60 ms), matching that interpreter's heavier imports.
- **The shipped path is still above the plan's 300 ms threshold:** p50 366 ms (3.12) and 461 ms (uv 3.13). What remains:
  - the hook's own import: ~58 ms on 3.12, ~122 ms on 3.13, including `difflib` at ~27 ms
  - the check path's own imports: `yaml` via `adr_parser`, `dataclasses`/`inspect`, `fnmatch`
  - the second process start

## Not established

- Linux and macOS.
- A real wheel / console-script install. The uv run uses the real interpreter, but pinned to the branch code, not an installed build.
- Large real-world memory files.
- Cold first runs.
