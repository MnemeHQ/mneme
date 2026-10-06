# M2 — Cursor × Mneme Enforcement Matrix

Experiment: Cursor × Mneme hook compatibility (validation branch
`validation/cursor-hook-compatibility`).

## Environment

| Item | Value |
|---|---|
| Platform | Windows, Cursor IDE 3.17.8 (x64) |
| Transport | Claude `.claude/settings.local.json` imported by Cursor (third-party skills) |
| Hook command | `python .claude/wrapper.py` → `mneme-hook.exe` |
| Memory | Typed `FORBID_LITERAL` sentinels `CUR-001` (global), `CUR-002` (scoped `.cursor/**/*`) |
| Baseline commit | fixture + wrapper frozen at the M1 head |

## Deterministic (hook-level) cells

Run with `python validation/cursor-hook-compat/m2_enforcement_matrix.py`.

| Test | Scenario | Expected | Observed | Decision |
|---|---|---|---|---|
| T1 | allowed direct write (clean) | ALLOW + mutate | **ALLOW** | — |
| T2 | governed violation, global literal (Write) | BLOCK before mutation | **BLOCK** | `CUR-001` |
| T2b | governed violation, global literal (Edit) | BLOCK before mutation | **BLOCK** | `CUR-001` |
| T4a | scoped literal outside `.cursor/` | ALLOW (rule inapplicable) | **ALLOW** | — |
| T4b | scoped literal inside `.cursor/` | BLOCK | **BLOCK** | `CUR-002` |
| T5 | new/whole-file write, forbidden | BLOCK or classify unsupported | **BLOCK** | `CUR-001` |
| T7a | env-pinned memory (`MNEME_MEMORY`) | correct sentinel | **BLOCK** | `CUR-001` |
| T7b | cwd discovery (no override) | correct sentinel via `find_memory` | **BLOCK** | `CUR-001` |
| T8 | Shell / redirection write | coverage or bypass | **ALLOW — bypass** | — |
| T9 | Delete / rename surface | coverage or bypass | **ALLOW — bypass** | — |
| T10 | hook failure (crash, launch failure) | fail-open/closed recorded | **fail-open** | — |

### T10 detail

- Malformed memory → `mneme check` exits non-zero, hook prints
  `no parseable verdict from mneme check ... Failing open.` and exits 0.
- Hook binary unavailable → wrapper prints
  `could not launch mneme-hook.exe. Failing open.` and exits 0.

Both are fail-open, consistent with the documented transport failure policy.

### T8/T9 detail

The Claude-compat matcher is `Write|Edit|MultiEdit`. Cursor's `Shell` (mapped from
Claude `Bash`) and `Delete` tools do not match, and `mneme-hook.py`'s
`should_check` only accepts `Edit`/`Write`/`MultiEdit`. Shell redirection and
delete/rename therefore bypass architectural enforcement. `beforeShellExecution`,
`beforeMCPExecution`, and the Tab hooks are not configured.

## Interactive (agent-only) cells — pending

| Test | Scenario | Expected |
|---|---|---|
| T3 | block → recover | agent receives reason, retries with allowed alternative |
| T6 | multi-file task | every underlying mutation recorded; partial-application classified |

## Notes

- The fixture originally declared the sentinels as multi-term `anti_patterns`.
  Those are retrieval-gated (enforced only for top-N retrieved decisions), so
  the hook's `"edit to <file>"` query did not enforce them. M1 was corrected to
  typed `FORBID_LITERAL` rules, which are always enforced (ADR-017/ADR-019).
