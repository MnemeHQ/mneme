# OpenCode E1 implementation charter — existing-file `.py` edit coverage

**Status:** PROPOSED — not implementation authorization. Implementation may begin
only after owner acceptance of this package and after the Layer 1 freeze
amendment in §15 is effective.
**Date:** 2026-11-18
**Base:** `main` at `3ada77415306ea41b977c035e833f6cff3ec1314` (S1 merged).
**Predecessor:** OpenCode S1 write surface, charter merged through PR #832.
**Probe evidence:** `evidence/out/16-e1-edit-semantics.json`
(`cdb7ccf0149c7fa3a4c66a82485056b40a21ba328398d91324d7c2a60b4a250d`),
verdict recorded in the E1 compatibility report in the S1-A evidence package.

This charter is documentation only. It does not change Core, ADRs, memory,
benchmarks, the support matrix or any integration status.

## 1. Decision summary

E1 extends the existing OpenCode integration from *verified-new-file* `write` to
**existing-file `.py` `edit`**, evaluated with **ADR-018 introduced-delta
semantics** through the **canonical materialisation and enforcement** already used
by the Claude Code adapter. It adds no engine, no rule type and no new file class.

The host probe established that the native `edit` tool is **conditionally
compatible** with `_materialize_change()`: identical results for unique matches and
for `replaceAll: true`, conditioned on one field-name normalisation and on
mirroring the host's unique-match rule.

Maximum evidence claim remains `EXECUTION_OBSERVED`, and on this host it remains
**unreachable** because `callID` is absent — so the claim ceiling is `none`.

## 2. Scope

In scope:

- tool id `edit`, existing `.py` target inside the selected memory's policy root;
- complete `oldString` / `newString` payload, with or without `replaceAll`;
- `FORBID_LITERAL` rules only;
- canonical `mneme check` as the only enforcement engine;
- shared `resolve_memory`, `rule_id_for`, `assess_verdict` and
  `_materialize_change` / `introduced_between` internals;
- introduced-delta evaluation per ADR-018;
- the existing S1 `write` surface, unchanged.

Non-goals:

- non-`.py` files, new file types, or speculative extension points;
- `MultiEdit`, patch/hunk payloads, whole-file rewrite of an existing file;
- deletion, rename, chmod;
- shell, MCP, custom tools;
- Stop/session-delta enforcement, CI, gateway admission;
- waivers, new rule types, `FORBID_NUMERIC_ABOVE`;
- support-matrix promotion or any support-level statement;
- any Core, ADR, memory or benchmark change.

## 3. Accepted owner decisions

1. E1 covers existing `.py` edits only.
2. ADR-018 introduced-delta semantics govern the edit gate.
3. Canonical materialisation and enforcement are reused; no parallel matcher.
4. Time-of-check/time-of-use resistance is `NOT_ESTABLISHED` and is recorded, not
   claimed.
5. Two approval gates only: this package, and the final merge.

## 4. Host pin and probe results

Host: OpenCode `2.3.0`, V2 plugin API, Linux `linux/amd64`, image
`sha256:ec0643a1…df5ced`, binary
`9e0cb0e096666f955c3f72d1b517fd2cb5cca65c2876e1012492d955fc974a7b`.
Windows G0 pin `f1aacb96…09bed` remains historical and is not asserted for Linux.

Probe (disposable files, no plugin, no memory):

| Case | Host result |
| --- | --- |
| Unique match | applies the replacement |
| Multiple matches, no flag | **refuses**: `Found 3 matches for oldString, but expected exactly one. Add more surrounding context to make oldString unique, or set replaceAll to true to replace every occurrence.` |
| No match | **refuses**: `Could not find oldString in <file>. It must match exactly, including whitespace and indentation.` |
| `oldString == newString` | **refuses**: `No changes to apply: oldString and newString are identical.` |
| `replaceAll: true`, 3 matches | replaces **all three** |

Canonical comparison:

| Case | Canonical | Landed | Verdict |
| --- | --- | --- | --- |
| Unique | equal | equal | compatible |
| `replaceAll: true` | equal **only when `replaceAll` is mapped to `replace_all`** | all occurrences | **blocking if unmapped** |
| Ambiguous | would replace the first | host refuses, nothing lands | divergent, non-blocking |
| No match | `MaterializeError` | host refuses | compatible |
| Identical | unchanged content, empty delta | host refuses | compatible |

**Blocking requirement:** OpenCode uses `replaceAll`; canonical `_replace_count()`
reads `replace_all`. Unmapped, a replace-all edit is evaluated on a
single-replacement delta while the host lands every replacement, leaving later
occurrences unexamined.

## 5. Architecture and file boundaries

Changed files (all S1-introduced; no new modules):

```text
integrations/opencode-plugin/index.ts      forward `edit` events; version 0.2.0
integrations/opencode-plugin/package.json  version bump
integrations/opencode-plugin/README.md     document the edit surface
mneme/integrations/opencode/bridge.py      edit branch + input normalisation
tests/integrations/opencode/test_bridge_contract.py   unit coverage
tests/integrations/opencode/test_e1_offline.py        new; directory already gated
```

New test file is covered by the existing `GATE_SHIPPED_PATHS` entry
(`tests/integrations/opencode` is prefix-matched by
`tests/test_test_policy.py`); no gate registration change is required.

Prohibited: `mneme/cli.py`, `mneme/enforcer.py`,
`mneme/integrations/claude_code/hook.py` (reuse, do not modify),
`mneme/integrations/memory_selection.py`, `mneme/decision_governance.py`,
`mneme/decision_index_persistence.py`, `mneme/decision_retriever.py`,
`mneme/conflict_detector.py`, `.mneme/`, `docs/adr/`, `validation/`,
`benchmarks/`, the support matrix.

If any prohibited file must change, stop and seek a separate charter.

## 6. Interfaces

Plugin to bridge — the S1 envelope is unchanged; `tool` becomes `edit` and the
input carries the host fields:

```json
{
  "schema": "mneme.opencode.bridge/v1",
  "tool": "edit",
  "input": {
    "path": "<host path>",
    "oldString": "<host old string>",
    "newString": "<host new string>",
    "replaceAll": true
  },
  "sessionDirectory": "…",
  "sessionID": "…", "callID": null, "agent": "…",
  "messageID": "…", "eventID": "…"
}
```

Bridge to plugin: unchanged `mneme.opencode.decision/v1`. `decision` remains the
sole enforcement-control input; `reason` is read only for the existing and
canonical diagnostics (S1 §6 as amended).

**Normalisation obligation (mandatory, blocking):**

```text
oldString  -> old_string
newString  -> new_string
replaceAll -> replace_all
```

No other field is read by the bridge for control.

## 7. Behaviour and decision matrix

| Observation | Decision | Claim | Host action |
| --- | --- | --- | --- |
| `TRUSTED_COMPLETE`, `APPLIED` + `FAIL`, `strict` | `block` | `none*` | throw; no write |
| `TRUSTED_COMPLETE`, `APPLIED` + `FAIL`, `warn` | `allow` + `Mneme WARN: warn_mode_violation` | `none*` | proceed |
| `TRUSTED_COMPLETE`, `APPLIED` or `EXCLUDED` + `PASS` | `allow` | `none*` | host writes |
| Introduced delta empty (pure deletion, identical strings) | `skip` (`empty_introduced_content`) | `none` | host proceeds or refuses its own no-op |
| `oldString` not found in the current file | `unevaluated` (`old_string_not_found`) | `none` | host refuses |
| More than one match and `replaceAll` not true | `unevaluated` (`ambiguous_old_string`) | `none` | host refuses |
| Target missing | `unsupported` (`target_missing`) | `none` | host errors |
| Non-`.py` target | `unsupported` (`non_python_target`) | `none` | default-open |
| Target unreadable / non-UTF-8 | `unevaluated` (`unreadable_target`) | `none` | default-open |
| Target outside policy root | `unevaluated` (`target_outside_policy_root`) | `none` | default-open |
| No memory | `skip` (`no_memory`) | `none` | proceed |
| `authority.json` mismatch | `setup_invalid` | `none` | proceed + `NOT_PROTECTED` |
| Missing/mismatched bridge schema | `unevaluated` | `none` | proceed |
| Non-`edit`/`write` tool | not intercepted; `NOT_COVERED` | none | proceed |

`*` `EXECUTION_OBSERVED` requires all six host identifiers. This host supplies no
`callID`, so the literal claim is `none` for every host event. The gate still
enforces; the claim ceiling does not move.

Only a trusted complete literal `FAIL` in effective `strict` mode may block.
`warn` never blocks.

## 8. Materialisation contract

1. Resolve the target against the session directory (never process cwd), require
   an existing `.py` file inside the selected memory's policy root.
2. Read the current content once, as UTF-8.
3. Build the tool input with the §6 normalisation and call
   `hook._materialize_change()`; do not reimplement replacement logic.
4. On `MaterializeError` map to `unevaluated` with the reason from §7.
5. Compute `hook.introduced_between(current, proposed)`; empty → `skip`.
6. Invoke the checker on the introduced delta via `_invoke_check`, with
   `--target-path` set to the real target.
7. Mirror the host's ambiguity rule: if `oldString` occurs more than once and
   `replaceAll` is not true, return `unevaluated` (`ambiguous_old_string`) without
   evaluating, because the host will refuse the edit.

**Fidelity requirement (E1-F1):** for every host event, the bytes the host lands
must equal the canonical `proposed` content. This is the edit analogue of I-10 and
must be demonstrated, not assumed. It is the primary success criterion for E1.

## 9. Evidence and claim ceiling

E1 records, per decision, the S1 evidence projection plus:

- `materialisation.current_sha256` — the file content read by the bridge;
- `materialisation.proposed_sha256` — the canonical proposed content;
- `materialisation.evaluated_sha256` — the introduced delta actually checked;
- `materialisation.replacement_count` — 1 or all;
- `materialisation.ambiguous`, `materialisation.found` — booleans.

`content_sha256` denotes the **evaluated text** for both tools. S1 records are
unchanged in meaning (for a new file the evaluated text is the complete content).

Claim ceiling, evidence separation (`host_witness: null`) and the six-identifier
gate are unchanged from S1.

## 10. Test matrix

Unit / contract (`test_bridge_contract.py`):

| ID | Case | Assertion |
| --- | --- | --- |
| E1-U1 | Input normalisation | `oldString`/`newString`/`replaceAll` map to the canonical keys |
| E1-U2 | Ambiguity rule | multiple matches without `replaceAll` → `unevaluated`, no checker call |
| E1-U3 | No-match rule | absent `oldString` → `unevaluated` |
| E1-U4 | Empty delta | identical strings → `skip` |
| E1-U5 | Non-`.py` | exactly `unsupported` / `non_python_target` |
| E1-U6 | Missing target | exactly `unsupported` / `target_missing` |
| E1-U7 | Root escape | target outside policy root → `unevaluated` |
| E1-U8 | `write` regression | existing S1 payloads still normalise and decide identically |

Live host (`test_e1_offline.py` with a fake host; validator repeats on the real host):

| ID | Case | Expected |
| --- | --- | --- |
| E1-01 | Edit introduces a forbidden literal, `strict` | `block`; host refuses; file byte-identical |
| E1-02 | Same, `warn` | `allow` + `Mneme WARN: warn_mode_violation`; file changes |
| E1-03 | Compliant edit | `allow`; file changes |
| E1-04 | Remediation: edit removes an existing violation | `allow` (introduced-delta, not whole-file) |
| E1-05 | Pre-existing violation untouched elsewhere in the file | `allow` |
| E1-06 | Ambiguous `oldString`, no flag | `unevaluated`; host refuses; file unchanged |
| E1-07 | No match | `unevaluated`; host refuses; file unchanged |
| E1-08 | `replaceAll: true`, violation in a later occurrence | **`block`** — the regression test for the mapping obligation |
| E1-09 | Existing non-`.py` file | `unsupported` / `non_python_target` |
| E1-10 | Target outside policy root | `unevaluated` |
| E1-11 | Authority mismatch | `setup_invalid` + `NOT_PROTECTED`; no claim |
| E1-12 | Non-`edit`/`write` tool | `NOT_COVERED`; not intercepted |
| E1-13 | Missing `callID` | claim `none`; no synthesis |
| E1-14 | Materialisation fidelity | landed == canonical `proposed` for unique and replace-all |
| E1-15 | Pure deletion | allowed; introduced delta empty → `skip`; file changes |
| E1-16 | S1 `write` regression | block / allow / existing-target rows unchanged |

Race probe (recorded, not a pass):

| ID | Case | Classification |
| --- | --- | --- |
| E1-R1 | File changes between bridge read and host write | `DETECTED` / `UNDETECTED_RACE` |
| E1-R2 | Target replaced by a symlink between read and write | `DETECTED` / `UNDETECTED_RACE` |
| E1-R3 | Target replaced by a hardlink between read and write | `DETECTED` / `UNDETECTED_RACE` |

Any undetected case sets `race_resistance: NOT_ESTABLISHED` and is recorded as a
documented bypass.

## 11. Validation protocol

1. Pinned Linux environment from S1-A (`sha256:ec0643a1…df5ced`), OpenCode
   `2.3.0`, Python `3.14.10`, model `opencode-go/deepseek-v4.1-flash`.
2. Full E1 matrix plus the S1 `write` regression rows, live host.
3. File-state witnesses before and after every host action.
4. Host refusal witness recorded separately from the bridge record.
5. Materialisation fidelity recorded per event (E1-F1).
6. Evidence bundle versioned; S1 evidence untouched.
7. Independent validator, not the implementer.

## 12. Success criteria

- Every matrix row observed as specified.
- E1-F1 holds for unique and replace-all edits.
- E1-08 blocks: a replace-all edit whose violation sits in a later occurrence.
- S1 `write` behaviour unchanged.
- Claim ceiling `none` on host events without `callID`, with no synthesized
  identifiers.
- CI: gate battery, trusted gate, provenance, encoding, architecture, install
  command, `mneme check --mode warn` all green.
- No support-level statement anywhere.

## 13. Closure requirements

- exact PR head and tree;
- implementation, plugin and test hashes;
- CI run links;
- independent verdict with evidence manifest hash;
- residual limitations: `race_resistance: NOT_ESTABLISHED`, `claim: none` without
  `callID`, edit/shell/patch out of scope;
- merge recommendation;
- final owner authorization. No merge without it.

## 14. Stop conditions

1. Host edit semantics prove incompatible with canonical materialisation after
   normalisation.
2. The host's ambiguity rule cannot be mirrored without engine changes.
3. Any shared Core change becomes necessary.
4. A frozen architectural requirement cannot be met.
5. Any need for a file type other than `.py`.
6. The `write` surface would regress.
7. The freeze amendment is absent or rejected.
8. Any requirement to claim a support level.

## 15. Layer 1 freeze determination

**A Layer 1 freeze amendment is required.** E1 expands a blocking enforcement
surface onto a file class S1 did not cover (existing `.py` files), which changes
what can be blocked in a repository. Even though the engine is untouched, the
surface expansion is the freeze-relevant fact, and S1 set the precedent of a
matching `[layer1-freeze]` amendment alongside a bounded charter.

The amendment is documentation-only, authorizes exactly the E1 surface, and
preserves retrieval and enforcement semantics. Exact text:
the companion `[layer1-freeze]` amendment. No Core change, no new engine, no new rule type.

## 16. Authorization gates

**Gate 1 — this package.** Owner accepts the charter and the freeze amendment.
Both merge before implementation starts.

**Gate 2 — final merge.** After Stage 2 returns the closure package, the owner
authorizes or rejects the merge. No per-test approvals.

## 17. No support claim

This charter makes no support-level declaration and does not authorize a
support-matrix change.
