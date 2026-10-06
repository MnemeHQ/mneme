# M3 — Cursor × Mneme Compatibility Verdicts

Experiment: Cursor × Mneme hook compatibility (validation-only).
Branch: `validation/cursor-hook-compatibility`.

Result line:

> **Transport: PASS · Direct edits: PASS · Full mutation coverage: PARTIAL**

## Verdict 1 — Transport compatibility: PASS (with a thin adapter)

**The existing Mneme Claude enforcement core is reusable unchanged, but
Cursor 3.17.8 requires a thin transport adapter for BOM normalization and
explicit deny translation.**

- The hook's `parse_event` consumes Cursor's `preToolUse` payload
  (`tool_name`, `tool_input`, `cwd`) without modification.
- Two transport differences were proven live:
  1. **BOM normalization.** Cursor prefixes hook stdin with a UTF-8 BOM
     (`EF BB BF`). Windows/Python text decoding turns those bytes into
     `ï»¿`, so the hook rejects the envelope as "bad envelope". Reading bytes
     and decoding with `utf-8-sig` consumes the BOM.
  2. **Explicit deny translation.** In the tested Cursor 3.17.8 GUI path,
     Mneme's normal Claude-style exit `2` did **not** stop the write;
     translating the same decision into
     `hookSpecificOutput.permissionDecision = "deny"` did.
- Isolation holds: sentinel decision IDs `CUR-001` / `CUR-002` appear in every
  verdict, proving the correct memory root is selected under both the
  env-pinned (T7a) and cwd-discovery (T7b) modes.
- Feedback reaches the agent: the denial reason is visible and actionable (T3).

## Verdict 2 — Direct-edit enforcement: PASS

Cursor `Write` mutations (which also carry Claude `Edit`) are deterministically
governed before mutation:

| Cell | Result |
|---|---|
| T1 allowed write | ALLOW |
| T2 governed violation (Write) | BLOCK, `CUR-001` |
| T2b governed violation (Edit) | BLOCK, `CUR-001` |
| T4a scoped literal outside `.cursor/` | ALLOW (inapplicable) |
| T4b scoped literal inside `.cursor/` | BLOCK, `CUR-002` |
| T5 whole-file write | BLOCK, `CUR-001` |
| T3 block → recover | PASS |
| T6 multi-file, partial application | PASS (2/3; blocked file not written) |

Determinism note: enforcement is only deterministic for **typed
`FORBID_LITERAL` rules** (always evaluated, ADR-017/019). Legacy multi-term
`anti_patterns` are retrieval-gated (enforced only for top-N retrieved
decisions), so they are unsuitable for a gate-style edit hook. The M1 fixture
was corrected accordingly.

## Verdict 3 — Mutation-surface completeness: PARTIAL

Enforcement covers the direct-edit surface only.

- **Covered:** Cursor `Write` (and the Claude `Edit` route that maps onto it).
- **Bypassed (empirical):**
  - T8 — Shell / redirection write (`printf ... > file`): ALLOW / bypass.
  - T9 — Delete / rename: ALLOW / bypass.
- **Not configured:** MCP writes, Tab edits, and any other Cursor native
  surfaces. The Claude-compat matcher is `Write|Edit|MultiEdit`; Cursor's
  `Shell` and `Delete` tools do not match, and `mneme-hook`'s `should_check`
  accepts only `Edit`/`Write`/`MultiEdit`.
- Cursor exposes additional native surfaces (`beforeShellExecution`,
  `beforeMCPExecution`, `afterFileEdit`, Tab hooks) with `failClosed: true`
  available. Wiring them is a separate scope.

## Decision gate: C — Adapter required (thin transport adapter)

- The existing `mneme-hook` executes correctly once the payload arrives; no
  changes to `Pipeline`, `DecisionRetriever`, or typed-rule semantics.
- The adapter is responsible only for: BOM normalization and
  exit-2 → explicit deny translation.
- Conditional follow-up (separate scope): evaluate a native
  `.cursor/hooks.json` package with `failClosed: true` and matchers widened to
  `Shell` / `Delete` (and MCP/Tab surfaces) to raise mutation coverage.
- Not pursued: a Cursor-specific decision model, retriever, or enforcement
  engine.

## Explicitly out of scope

Cursor Rules generation; marketplace/plugin packaging; retrieval or rule
applicability changes; general shell-command semantic parsing; stop-hook
working-tree audit; cloud/enterprise deployment.
