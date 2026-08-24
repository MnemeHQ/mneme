# Codex CLI integration

Mneme governance for OpenAI Codex CLI sessions: a trusted hook bundle that
preflights native `apply_patch` mutations before execution and audits every
artifact the session changed at turn end.

Validated against **Codex CLI 0.149.1** on **Windows** via `codex exec`,
pinned by binary SHA-256 (`validation/codex-cli/pinned-build.json`). Scope
qualification: tested on Windows via `codex exec`; interactive TUI modes,
other platforms, and other Codex versions are not separately proven.

## The claim

> Mneme preflights supported native Codex mutation paths, including
> `apply_patch` Add and Update operations, and can deny deterministic
> architectural violations before execution.

> Shell-based mutations are not reconstructed pre-execution. Mneme detects
> changed artifacts at Stop and audits their whole-file state as a backstop.

> If Codex modifies a file that was already dirty when the session began,
> that file becomes part of the session audit set and must satisfy
> whole-file policy at Stop.

All three statements are backed by live evidence:
`validation/codex-cli/evidence/runs/20260824T221910Z-m4a-gate`
(`analysis-m4a.md`) and the runs cited in the capability matrix below.

## Architecture

Three hook events, one script (`mneme/integrations/codex_cli/hook.py`):

| Event | Role |
|---|---|
| `SessionStart` | Captures the session baseline (repository snapshot) before any work. |
| `PreToolUse` (`^apply_patch$`) | Parses the proposal, snapshots current files where needed, checks **introduced content only** (ADR-018) through `mneme check --json`, and denies deterministic violations before execution. Also captures the baseline if SessionStart did not. |
| `Stop` | Diffs the repository against the session baseline and runs one **whole-file** check per changed surviving artifact — the backstop for surfaces without structured pre-execution data (shell writes, script-driven writes). |

Transport mapping (all shapes proven live):

| Gate result | Codex output |
|---|---|
| PASS / SKIP | none — no opinion |
| DENY | `permissionDecision: "deny"` (PreToolUse) / `decision: "block"` (Stop) |
| WARN | non-blocking `additionalContext`: `[mneme] WARN ...` |
| FAIL_OPEN | non-blocking `additionalContext`: `[mneme] UNEVALUATED ... NOT evaluated:` |

## Mutation-surface coverage

| Surface | Pre-execution | Backstop |
|---|---|---|
| `apply_patch` Add File (relative path observed) | ✅ governed | — |
| `apply_patch` Update File (absolute and relative observed) | ✅ governed | — |
| Bundled multi-operation patches (Add + Update, any order) | ✅ all operations evaluated; any violation denies the entire call | — |
| `apply_patch` Delete File | Recognized, **SKIP by design**: ADR-018 governs introduced content, and a pure deletion introduces nothing. No delete-protection is claimed or provided. | recorded in the Stop audit |
| Shell writes (redirection, cmdlets, script-driven, multi-file) | ❌ known coverage gap — path/content exist only inside command text; Mneme does not parse shells | ✅ whole-file audit at Stop |
| Script-driven interpreter writes | ❌ STOP-ONLY | ✅ whole-file audit at Stop |
| MCP tools / code mode | not yet probed | — |

## Failure semantics

Every degraded outcome is visible and never reported as governed:

- Unparseable checker output, launch failure, timeout, incomplete rule-path
  evaluation, or an unreadable target -> **FAIL_OPEN** with an explicit
  `[mneme] UNEVALUATED ... NOT evaluated:` diagnostic.
- For bundled calls, a definite violation denies the entire call even when a
  sibling operation could not be evaluated — the denial reason discloses
  which operations were never checked.
- Pure deletions resolve to SKIP by design (ADR-018); they are recorded in
  the Stop audit but no deletion protection exists.

## Dirty files

Files already dirty before the session are ignored unless Codex touches
them. Once Codex modifies a file, it enters the session audit set and must
satisfy **whole-file** policy at Stop — including violations that predate
the session. This is the audit enforcing a touched file's final state, not a
claim that Codex introduced every violation in it.

## Loop bounds

Stop blocks that trigger remediation are re-evaluated deterministically: a
real repair passes on the next Stop. A consecutive-block cap (8) releases
the loop with a visible warning rather than retrying forever.

## Trust model

SessionStart, PreToolUse, and Stop definitions must be reviewed and trusted
via `/hooks`. Codex stores **one trusted hash per**
`(hooks.json path, event, index)` **slot**: registering or re-trusting a
different command in the same slot silently evicts the previous definition's
trust until it is re-reviewed. If hooks appear inert after changing a
definition, re-run `/hooks`.

## Reproducing the evidence

See `validation/codex-cli/README.md`. The pinned binary, capability matrix,
per-run raw payloads, transcripts, manifests, and analyses live under
`validation/codex-cli/evidence/runs/`.
