# M3 analysis — Stop changed-tree audit, live (run 20260824T215341Z)

Production hooks: SessionStart + PreToolUse(^apply_patch$) + Stop, all
trusted (`087ba51c…` / `0f18ec6e…` / `b94f774e…`), pinned 0.149.1
(SHA re-verified), no bypass.

## Case results

| Case | Expected | Observed |
|---|---|---|
| c1 forbidden shell write | baseline pre-exists -> Stop blocks naming file/rule -> remediation passes | ✅ `SessionStart Completed` before mutation; shell write landed; `Stop Blocked`; model **removed** the file ("workspace no longer contains the hook-rejected artifact"); next `Stop Completed`; `shell_made.txt` gone from final worktree |
| c2 compliant shell write | clean pass | ✅ `SessionStart` → `Stop Completed`, zero blocks |
| c3 dirty untouched | not blamed | ✅ `preexisting.py` visible to the agent, untouched; `Stop Completed`, zero blocks |
| c4 dirty touched | audited | ✅ **4 consecutive Stop Blocks**; model finally removed the forbidden token while preserving its appended line; `Stop Completed`. Final file contains no FORBIDDEN token and keeps `"# codex was here"` |

## Loop bounds

c4 exercised the loop pressure directly: 4 consecutive blocks (< cap of 8),
resolved by genuine remediation, then a clean completion. No infinite loop;
the cap never had to fire. `stop_hook_active` was not relied upon — loop
safety comes from deterministic re-evaluation plus the cap, as designed.

## Unevaluated visibility

No unevaluated artifacts occurred in these cases (all small UTF-8 files);
the disclosure path (`systemMessage`, never a silent clean result) is
covered by unit tests (`test_unevaluated_artifact_disclosed_not_claimed_governed`,
cap test).

## Semantic observation for the record (M3 design consequence)

Whole-file audit semantics mean that once Codex *touches* an already-dirty
file, pre-existing violations inside it are attributed to the session until
the whole file complies (c4: four blocks until the pre-existing token was
removed). This matches the agreed M3 boundary ("dirty before session AND
modified by Codex -> audited") and ADR-018's audit-vs-gate split, but it is
a user-visible behavior worth documenting in the integration docs: **the
audit demands whole-file compliance of every file the session changed, not
only the session's own delta lines.**

## Harness defects (separate from Codex/Mneme behavior)

Two invalidated attempts this milestone:

1. `_invalidated/20260824T213620Z`: missing `import os` — crashed before any
   codex invocation.
2. `_invalidated/20260824T215021Z`: subprocess stdout reader crashed decoding
   non-ASCII Codex output under cp1252; fixed with explicit UTF-8 +
   errors="replace".

Also: `summary.json`'s automated `blocks` counter searched exec stdout for a
reason string that is delivered to the hook channel instead, so it recorded
0 everywhere. The transcripts are authoritative; counts above were derived
from `hook: Stop Blocked|Completed` lines.

## Verdict

> **M3 exit gate: MET** — all four live cases plus bounded remediation pass
> on pinned Codex CLI 0.149.1 / Windows / `codex exec`.
