# M1e-d analysis — Update File gate wiring, live content-based denial
# (run 20260824T132248Z)

Production entrypoint (`mneme/integrations/codex_cli/hook.py` -> gate ->
parser -> `mneme check --json`), pinned 0.149.1 (SHA re-verified), trusted
hooks only, no bypass.

## Trust state at run time

PreToolUse slot held a fresh hash (`sha256:087ba51c...`, written 08:22 UTC,
immediately before the run) after the human `/hooks` re-trust of the
production definition. The prior invalidation
(`_invalidated/20260824T130644Z-m1ed-live`) documented how the M1e-a logger
re-trust had evicted production trust from the single-hash slot; that
single-slot eviction behavior is now observed three times and must go into
install docs: **registering or re-trusting any other definition in the same
`(hooks.json path, event, index)` slot silently disarms the previous one**.

## deny_update — Mneme-content-based denial of an Update File

| Requirement | Result |
|---|---|
| PreToolUse received the Update proposal | YES — `hook: PreToolUse` |
| Gate snapshotted the existing file once | YES — parser validated hunks against it (a mismatch would have FAIL_OPENed instead of denying) |
| Parser derived the forbidden introduced line | YES — blocked command report shows `+    return "FORBIDDEN_TOKEN_XYZ"` |
| `mneme check` returned the SCOPED violation | YES — `[ADR-UPD] FAIL "FORBIDDEN_TOKEN_XYZ" ... path: service.py`; the rule carries `include_paths: ["service.py"]`, so applicability proves the real resolved file reached `--target-path` |
| Production hook emitted the proven deny | YES — `hook: PreToolUse Blocked`; agent reported "`service.py` was not changed." |
| Existing file byte-for-byte unchanged | YES — `seed_changed=False` |
| PostToolUse absent | YES — not registered in the production config (per M1d-b scope) and no such line appears; registered-hook probes (R0/M1e-a) separately prove PostToolUse follows allowed patches and is absent on denial |
| Stop still fires | Same registration note; R0/M1e-a prove Stop fires in both outcomes |

No WARN/UNEVALUATED context leaked into developer context in either case
(checked session rollouts): strict DENY stayed silent-context, exactly as
mapped.

## pass_update — compliant Update

File changed as requested; `hook: PreToolUse Completed` (silent PASS, no
opinion); no block; no unexpected diagnostics.

## Verdict

> **M1e-d exit gate: MET** — one compliant existing-file modification
> succeeded, and one policy-violating existing-file modification was blocked
> pre-execution by a real scoped Mneme rule on pinned Codex CLI 0.149.1 /
> Windows / `codex exec`.

Add File and Update File — the two dominant coding mutations — are now both
genuinely end-to-end governed. Delete, multi-file, shell, Stop audit, TUI
coverage, and parser generalization remain out of scope.
