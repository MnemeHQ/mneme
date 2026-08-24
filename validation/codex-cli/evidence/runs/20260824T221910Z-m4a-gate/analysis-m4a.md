# M4a — final adversarial claim gate (run 20260824T221910Z)

Production architecture as shipped (SessionStart + PreToolUse ^apply_patch$ +
Stop, all trusted; pinned Codex CLI 0.149.1, binary SHA re-verified at run
start; no bypass). Ten adversarial cases, ALL PASS.

## Case results

| Case | Claim proven | Key evidence |
|---|---|---|
| t01 Add violation | pre-exec DENY; file never lands | `PreToolUse Blocked`; helper.py absent |
| t02 Update violation | pre-exec DENY; existing file byte-identical | `PreToolUse Blocked`; service.py == pre-run bytes |
| t03 bundle, violating Update | whole-call DENY, no partial mutation | Blocked; helper.py absent AND service.py unchanged |
| t04 bundle, violating Add | whole-call DENY from the second position | Blocked; helper.py absent |
| t05 Delete | recognized, SKIP-by-design; **no protection claimed** | deletion proceeds; zero PreToolUse blocks |
| t06 shell violation | allowed past the coverage gap, **caught at Stop** | no pre-exec block; 1 Stop block; final file clean of token after remediation |
| t07 script-driven violation (STOP-ONLY surface) | same backstop | no pre-exec block; 1 Stop block; final clean |
| t08 dirty untouched | ignored — not blamed on Codex | zero blocks; dirty file intact |
| t09 dirty touched | **whole-file audit applies**: Stop blocks until file fully compliant | 3 Stop blocks; final file has appended line and NO forbidden token |
| t10 corrupted memory | fail-open, visibly; never DENY, never fake-PASS | file lands; unevaluated diagnostic reached agent context |

Remediation loops were exercised live in t06/t07/t09 (each required at least
one Stop block before compliance) and the loop cap is pinned by unit test
(`test_remediation_passes_and_block_cap_bounds_loops`).

## Frozen claim wording

**Pre-exec claim:**

> Mneme preflights supported native Codex mutation paths, including
> `apply_patch` Add and Update operations, and can deny deterministic
> architectural violations before execution.

**Coverage qualification:**

> Shell-based mutations are not reconstructed pre-execution. Mneme detects
> changed artifacts at Stop and audits their whole-file state as a backstop.

**Dirty-file consequence:**

> If Codex modifies a file that was already dirty when the session began,
> that file becomes part of the session audit set and must satisfy
> whole-file policy at Stop.

## Harness note

First gate attempt (`summary.json` superseded by this run's) had two FAILs
caused by the checker comparing post-deny bytes against an LF-re-encoded
seed constant instead of the case's own on-disk CRLF baseline — the same
newline trap documented since M1e-a. Fixed in the checker only; both cases
then pass with byte-identical files.
