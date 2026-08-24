# M1f-a analysis — multi-operation apply_patch probe (run 20260824T133347Z)

Pinned Codex CLI 0.149.1 (SHA verified at run start) / Windows / `codex exec`,
trusted logger hooks, no bypass. Prompt requested two changes in a SINGLE
apply_patch invocation: modify seeded `service.py` AND add `helper.py`.

## The eight facts

1. **One call, not several.** Exactly one PreToolUse apply_patch event in the
   allow arm; both operations arrived inside a single `tool_input.command`.
   Multi-operation bundling is real on this build.

2. **Exact grammar observed** (`events-allow/events/0002-*.json`):

   ```
   *** Begin Patch
   *** Update File: service.py        <- RELATIVE path this time
   @@
    def existing():
   -    return 1
   +    return 42
   *** Add File: helper.py            <- second operation, no separator token:
   +def assist():                        operations are adjacent headers
   +    return 7
   *** End Patch
   ```

3. **Operation ordering**: source order preserved — Update first, Add second,
   matching the model's presentation order. No reordering observed.

4. **Path forms**: BOTH operations used relative paths here, whereas M1e-a's
   standalone Update used an absolute path. Conclusion so far: path form is
   chosen per invocation by the model/protocol, not per operation type.
   Parsers must accept both forms for every operation kind.

5. **Independent reconstructability**:
   - `helper.py`: byte-exact match to the `+` lines (LF) against the recorded
     post-allow sha256.
   - `service.py`: introduced content is exact at line level; exhaustive
     per-line EOL search again yields a UNIQUE mixed-EOL byte result
     (rewritten hunk region LF, untouched regions CRLF) — identical pattern
     to M1e-a. Byte-exact final-state prediction remains out of reach and out
     of scope; ADR-018 introduced-content derivation is deterministic.

6. **Deny rejects the ENTIRE tool call**: deny arm shows one PreToolUse ->
   Blocked; NEITHER mutation landed (`seed_changed=False`,
   `helper_added=False`, clean worktree). Transcript: "the single
   `apply_patch` invocation was blocked ... No files were modified."

7. **Allow lands all proposed mutations**: `service.py` modified AND
   `helper.py` added (worktree status `M service.py` + `? helper.py`),
   single PostToolUse for the one tool call.

8. **PostToolUse**: allow -> exactly one PostToolUse after the single
   PreToolUse; deny -> absent (PreToolUse + Stop only). Stop fired in both.

## Architectural acceptance rule (restated)

> Every operation in a multi-file proposal must be evaluated before allowing
> the tool call. One blocking violation denies the entire `apply_patch`.
> Partial interpretation or partial enforcement is forbidden.

Codex semantics align with this natively: deny is per-tool-call, so a parser
that evaluates ALL operations and reports any violation maps directly onto
the proven transport.

## Parser implications for M1f-b (not yet implemented)

- `_single_operation` must become an operation-list walk; each operation
  parsed independently against its own snapshot needs (Update requires the
  snapshot; Add does not).
- Multiple Updates may target different files -> snapshot lookup per path.
- Evaluation is all-or-nothing at the gate level: parse every operation
  first; any parse failure = FAIL_OPEN "proposal not evaluated"; any policy
  violation = DENY covering the whole call.
