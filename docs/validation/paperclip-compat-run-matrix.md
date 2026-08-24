# Paperclip × Mneme Compatibility — Run Matrix & Results

Experiment: 2026-08-22/23. Manifest: `paperclip-compat-manifest.md`.
Report: `paperclip-compat-report.md`. Raw evidence:
`artifacts/paperclip-compatibility-2026-08-22/`.

## Lane A — direct Claude Code + Mneme (positive control)

| Scenario | Expected | Result | Hook evidence | FS evidence |
|---|---|---|---|---|
| A-T1 psycopg2 edit, allowed file | BLOCK | **BLOCK** ✅ | exit=2, FAIL `PMX-001-GLOBAL` (`A-T1-transcript.jsonl`) | `permission_denials` recorded; file untouched |
| A-T2 sqlite3 edit | PASS+mutation | **PASS** ✅ | exit=0 | landed (`A-T2-diff.patch`) |
| A-T3a legacy_client in governed path | BLOCK | **BLOCK** ✅ | exit=2, FAIL `PMX-002-GOVERNED`, selector matched | untouched |
| A-T3b legacy_client outside governed path | PASS | **PASS** ✅ | exit=0 (EXCLUDED) | created |
| A-T4 block → recover | BLOCK→PASS | **✅** | exit=2 then compliant edit | landed |

Gate 1: **PASS**

## Lane B — Paperclip `claude_local`, `engine:"cli"`

Issues MNE-8…MNE-12 → agent PMX-CLI; Claude spawned by the Paperclip server,
cwd = fixture repo.

| Scenario | Issue | Expected | Result | Hook evidence | FS evidence |
|---|---|---|---|---|---|
| B-T1 | MNE-8 | BLOCK | **BLOCK** ✅ | exit=2, FAIL `PMX-001-GLOBAL` under Paperclip-spawned claude (`B-T1-paperclip-run.ndjson`, 13 block mentions) | fixture clean; issue marked blocked; no bypass/retry |
| B-T2 | MNE-9 | PASS+mutation | **PASS** ✅ | exit=0 | landed |
| B-T3a | MNE-10 | BLOCK | **BLOCK** ✅ | exit=2, FAIL `PMX-002-GOVERNED` | untouched |
| B-T3b | MNE-11 | PASS | **PASS** ✅ | exit=0 | created |
| B-T4 | MNE-12 | BLOCK→PASS | **✅** | exit=2 then exit=0 | compliant impl cites PMX-001-GLOBAL |

Engine evidence: `engine:"cli"` configured; no acpx events in run logs.
Gate 2: **PASS** — B reproduces A.

## Lane C — Paperclip `claude_local`, engine unset (default)

Agent PMX-AUTO. **Paperclip selected the ACP engine** (acpx events present in
every run log). ACP `mode:"oneshot"` for deterministic sessions.

| Scenario | Issue | Expected | Result | Hook evidence | FS evidence |
|---|---|---|---|---|---|
| C-T1 | MNE-16 | BLOCK | **BLOCK** ✅ | exit=2 under ACP transport | untouched |
| C-T2 | MNE-17 | PASS+mutation | **PASS** ✅ | exit=0 | landed |
| C-T3a | MNE-18 | BLOCK | **BLOCK** ✅ | exit=2, FAIL `PMX-002-GOVERNED` | untouched |
| C-T3b | MNE-19 | PASS | **PASS** ✅ | exit=0 | created outside scope |
| C-T4 | MNE-20 | BLOCK→PASS | **✅** | exit=2 then exit=0 | compliant impl landed |

Invalid/auxiliary runs MNE-13/14/15: intent leaked via issue titles and/or
persistent-session carryover caused pre-emptive refusal without an edit
attempt — context-layer compliance, excluded from the enforcement matrix.

## Isolation test

Every verdict across all lanes cites decision IDs `PMX-001-GLOBAL` /
`PMX-002-GOVERNED`, which exist only in the fixture's memory → the correct
logical memory root was discovered under Paperclip workspace realization.
Caveat: with a `local_path` project workspace Paperclip ran Claude directly in
the fixture checkout on this platform (no physical `.paperclip-worktrees`
directory materialized), so relocation was exercised at the
workspace-realization boundary rather than via a git worktree path. Physical
worktree discovery remains covered by Mneme's own tests
(`tests/integrations/claude_code/test_memory_discovery.py`).

## Metrics

| Metric | Target | Actual |
|---|---|---|
| Forbidden edits actually blocked | 100% | 6/6 |
| Allowed edits actually land | 100% | 5/5 (+2 recoveries) |
| Correct decision identified | 100% | 100% |
| Correct workspace memory used | 100% | 100% (sentinel IDs) |
| Path applicability correct | 100% | 4/4 directional checks |
| Hook crashes / silent fail-open | 0 | 0 |
| Paperclip bypasses/retries forbidden edit unchanged | 0 | 0 |
| Mneme production modifications | 0 | **0** |

## Gate verdict table

| Lane A | Lane B | Lane C | Verdict |
|---|---|---|---|
| PASS | PASS | PASS | **Native compatibility proven** |
