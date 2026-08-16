# Pre-generation Guidance Validation Report

**Date:** 2026-08-13  
**Revision under test:** local working tree based on `c1d29e9`  
**Outcome:** mechanical gates pass; diagnostic live runs excluded;
confirmatory outcome gates pending

## Checkpoint results

| Gate | Evidence | Result |
|---|---|---|
| Frozen benchmark | 7/7 PASS; recall@3 = 1.00; governed recall@1 = 5/5 | PASS |
| Locked guidance evaluation | holdout macro recall@3 = 1.00; safety-critical recall@3 = 1.00; no-relevance false injection = 0; low-signal injection = 0 | PASS |
| Guidance determinism and budget | Unit tests pin repeat output, K <= 3, and context <= 8,000 characters | PASS |
| Full test suite | 602 passed, 5 skipped | PASS |
| Python compilation | `python -m compileall -q mneme tests scripts` | PASS |
| Claude plugin schema | `claude.cmd plugin validate integrations/claude-code-plugin --strict` | PASS |
| Local latency | 500 runs: median 4.061 ms, p95 4.835 ms, max 6.962 ms | PASS |
| Protocol-discovery campaign | 15 valid runs retained as diagnostics; 27 remaining trials paused; all excluded from confirmatory scoring | DIAGNOSTIC |
| Confirmatory mechanism-isolation A/B | Revised protocol locked; new harness and 42 new runs required | PENDING |
| Confirmatory production-effectiveness A/B | Revised protocol locked; new harness and 42 new runs required | PENDING |

The PowerShell `claude.ps1` shim was blocked by the machine's script execution
policy. Re-running the same validator through the installed `claude.cmd` shim
passed; this was a launcher-policy issue, not a plugin validation failure.

## Reliability coverage

Automated tests cover:

- guidance disabled by default and explicit environment override precedence;
- valid `UserPromptSubmit` `additionalContext` output;
- empty, follow-up, unrelated, and rationale-only prompts emitting no context;
- missing, malformed, and unreadable memory failing open without stdout;
- memory-discovery and guidance-build errors failing open;
- typed-rule selector wording without false path-applicability claims;
- plugin exec-form hooks, 5-second prompt timeout, and existing 30-second edit
  timeout;
- legacy installer upgrade and idempotency; and
- packaging of all three console entry points.

The existing `PreToolUse` integration suite passed unchanged. This supports the
two-layer contract: prompt guidance is additive and edit enforcement remains the
deterministic gate. Diagnostic live runs also exposed negative-context false
blocks in that gate; they are tracked as separate guardrail evidence and do not
change the guidance mechanism claim.

## Manual cross-platform smoke

Run these steps on Windows, macOS, and Linux before a public runtime/plugin
release:

1. Install the candidate runtime in an isolated environment and confirm
   `mneme`, `mneme-hook`, and `mneme-guidance-hook` resolve on `PATH`.
2. Load `integrations/claude-code-plugin` and enable guidance.
3. Submit `Add persistence for user sessions.` in a fixture repository. Confirm
   the model receives the SQLite decision before its first proposal.
4. Submit `yes`. Confirm the guidance hook emits no context.
5. Submit an unrelated task. Confirm it emits no context.
6. Corrupt a disposable memory file. Confirm the prompt proceeds, stdout has no
   hook payload, and stderr reports fail-open behavior.
7. Attempt a directly edited typed-rule violation. Confirm the independent
   `PreToolUse` hook still warns/blocks according to enforcement mode.
8. Perform a shell-based write and confirm the documented limitation remains:
   `PreToolUse` does not cover Bash writes; audit with `/mneme:review`.

## Release disposition

The implementation is suitable for an opt-in candidate. It is not yet eligible
for a default-on change or a claim that guidance improves model compliance. The
original 15 live runs are protocol-discovery diagnostics only. Separate locked
mechanism-isolation and production-effectiveness evaluations are the remaining
outcome gates.
