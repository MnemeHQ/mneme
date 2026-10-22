# C3 finding F-R2: the "visible proceed" diagnostic is not delivered (assessment)

**Status:** assessment and options for owner decision. Documentation only. It
changes no runtime code, runs nothing, and authorizes no change. Batch R stays
stopped at the R-1 gate.
**Input:** Batch R evidence record (#601), R-1 Edit-2.
**Governing text:** [ADR-033](../adr/ADR-033-opt-in-fail-closed-enforcement.md)
§4.3; C2a charter §3.7; C2b charter §§5.3 R2, 8.

## 1. The finding

In R-1 Edit-2, a transient DNS failure made the verifier return
`AUTHORIZATION_UNVERIFIABLE(DNS)`. As specified (ADR-033 §4.3, C2b R2) the
hook did not refuse. It wrote this diagnostic to **stderr** and exited **0**:

```
mneme-hook: availability AUTHORIZATION_UNVERIFIABLE(DNS); evaluation=NOT_RUN; availability did not refuse.
mneme-hook: canonical memory missing.
mneme-hook: check not run
```

Claude Code applied the edit. The `tool_result` the model received says only
"The file … has been updated successfully." The string `UNVERIFIABLE`
occurs **zero times** in that probe's stream-json. The model continued with no
signal that enforcement was unavailable.

ADR-033 §4.3 requires "**a visible proceed**", and requires that "the diagnostic
reaches a host-visible channel". C2a §3.7 and C2b §8 deliberately claimed only
"emitted, not delivered" until C3. **C3 has now shown the shipped channel is
not delivered**, so the "visible proceed" requirement is unmet on Claude Code
2.1.303.

## 2. Why: the channel was never a delivery channel

| Source | What it says about an exit-0 PreToolUse hook |
|---|---|
| Claude Code hooks reference ("Where output goes") | stderr on exit 0 is never seen by Claude (debug logging only). stdout on exit 0 goes to the debug log for PreToolUse |
| `hook.py` `_emit_stop_feedback` docstring (existing code) | "Claude never sees stderr from an exit-0 hook (debug log only)" |
| T-08 A1 (#563) | An exit-0 Stop `systemMessage` appeared only as a transcript `hook_system_message` attachment, never in stream-json. Rule R4 classifies it `NOT_DELIVERED` |
| C3 R-1 Edit-2 (#601) | The exit-0 stderr diagnostic is absent from everything the host emitted |

So F-R2 is not a host bug or a flaky result. Every exit-0 path of the
direct-write hook writes to stderr, and stderr on exit 0 is by documentation
invisible to the model. The C2a/C2b decision to keep stderr and defer the
delivery claim was correct. C3 resolved that open question negatively.

## 3. Channels a PreToolUse hook can use without blocking

From the hooks reference (current docs; verify against 2.1.303 before pinning)
and this repository's live evidence:

| Channel (exit 0 unless noted) | Reaches the model | Reaches the user | Blocks the tool | Repo evidence |
|---|---|---|---|---|
| stderr / plain stdout | No | Debug log only | No | C3 R-1 Edit-2: not delivered |
| `hookSpecificOutput.additionalContext`, no `permissionDecision` | **Yes**: "added to Claude's context alongside the tool result" | Not documented | No | **H1a-edit, Claude Code 2.1.202 headless: `DELIVERED_TO_AGENT`; the tool ran and the file was as expected, identical to the control** (#551/#553 reclassification) |
| Top-level `systemMessage` | Not documented | "Warning message shown to the user" (behavior for PreToolUse and headless not documented) | No | Stop path only: `NOT_DELIVERED` to the agent (A1) |
| Exit code other than 0 or 2 | Not documented | Transcript notice with the first stderr line | No | None. Contradicts the hook spec ("the shim only exits 0 or 2") |
| `permissionDecision: "ask"` | In `-p`: denied, reason to Claude | Permission prompt | **Effectively yes** | None |
| `permissionDecision: "allow"` + reason | No (debug log) | No | No (auto-approves) | None |
| PostToolUse `additionalContext` / exit 2 | Yes, after the write | Not documented | No (already written) | None for PostToolUse |

## 4. Options (smallest first)

**Option 1: emit `additionalContext` on the UNVERIFIABLE proceed (recommended).**

On the direct-write path, when a local declaration is present, authorization
is `AUTHORIZATION_UNVERIFIABLE`, and the hook is about to exit 0, also write
one JSON object to stdout:

```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse",
  "additionalContext": "Mneme availability verification was unavailable (AUTHORIZATION_UNVERIFIABLE: DNS). This edit was allowed without fail-closed verification."}}
```

- **It is the only documented channel that reaches the model without blocking,**
  and the only one with live delivery evidence in this repository (H1a-edit).
- **It does not change the allow/deny outcome:** exit 0, no `permissionDecision`,
  so permissions are neither auto-approved nor tightened, and ADR-033 §4.3
  ("no availability-policy refusal") holds.
- **Wording:** factual, not imperative, per the hooks guidance that imperative
  hook text can trip prompt-injection defenses. No submitted content (ADR-033
  §7).
- **stderr stays as it is,** for logs and the debug channel.
- **Interaction to resolve in the charter:** warn mode's `_emit_defer` already
  writes a stdout JSON object with `permissionDecision: "defer"`, and the docs
  say `additionalContext` is **ignored** when `permissionDecision` is `"defer"`.
  The rare case "UNVERIFIABLE and a warn-mode violation in the same call" needs
  a defined single-object shape, or an explicit accepted gap. Strict mode,
  which the fixture uses, is unaffected: a strict FAIL exits 2, and its stderr
  already reaches the model.
- **Proof needed:** H1a's evidence is from Claude Code **2.1.202**. Delivery on
  the pinned **2.1.303** must be shown live (a U-row or R-1-style probe), with
  the C3 classifier extended to look for the diagnostic in the model-bound
  transcript or stream entries.
- **Authority:** this is a runtime output change at the frozen direct-write
  boundary. It needs a bounded charter amendment to C2b §8 (the diagnostic
  channel) and its own `[layer1-freeze]` amendment before any code.

**Option 2: add a top-level `systemMessage` for the user (complement, not a
substitute).** It may make the proceed visible to a human in interactive
sessions, but its PreToolUse and headless behavior is undocumented, and the
only repo evidence (A1, Stop) is `NOT_DELIVERED` to the agent. It is useful
only alongside Option 1, and only once the interactive arm (scope Q2) shows it.
Not needed to close F-R2 for the model.

**Rejected:**
- **Exit 1 / other non-zero codes:** undocumented model delivery, a misleading
  "hook error" label, and it breaks the hook spec's 0-or-2 contract.
- **`permissionDecision: "ask"`:** in headless mode it denies, and in
  interactive mode it prompts. Either turns UNVERIFIABLE into a refusal or a
  gate, which ADR-033 §4.3 forbids under Architecture A.
- **PostToolUse:** only after the write, and a new hook surface outside
  ADR-033 §6's PreToolUse scope. Unnecessary given Option 1.

## 5. F-R1 (recorded, no change proposed)

A single transient DNS failure let through an edit that a verified-AUTHORIZED
repository should refuse. That is ADR-033's accepted Architecture A behavior
(the disclosed verifier-denial limit), now observed accidentally on a real
host. It is recorded as an **accepted limitation**. Caching, retries, a grace
window or Architecture B would each need a separate architectural decision,
and this assessment proposes none. Option 1 does not fix F-R1. It makes F-R1
visible to the agent when it happens.

## 6. Related observation (out of scope)

`docs/integrations/claude-code.md` describes warn mode as "Surface warning to
Claude". The warn-mode `defer` reason has no live delivery evidence, and per
the docs `permissionDecisionReason` for non-deny decisions is not shown to
Claude. That claim is unverified. It is noted for a separate review and does
not affect C3.

## 7. Sequence if Option 1 is chosen

1. Owner decision on Option 1, including the warn-mode `defer` interaction.
2. A C2b §8 charter amendment plus a `[layer1-freeze]` amendment (docs).
3. An implementation PR (hook output plus tests), with the C3 classifier
   checking for model-bound delivery of the UNVERIFIABLE diagnostic.
4. A live re-probe on 2.1.303, then the authorized narrow R-1 re-run. #601's
   original FAIL stays recorded and is never overwritten.
