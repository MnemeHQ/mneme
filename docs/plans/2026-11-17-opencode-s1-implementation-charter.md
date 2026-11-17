# OpenCode S1 implementation charter

**Status:** PROPOSED — not implementation authorization. Implementation may begin
only after the implementation authorization gate in §16.1 is satisfied and this
charter is merged.
**Date:** 2026-11-17
**Base:** `b9b40ef8f5cf1dcf80087bba40a5becf12a88f1b`, Mneme `0.11.0`.
**Contract:** [PR #610](https://github.com/MnemeHQ/mneme/pull/610).
**G0 evidence:** isolated probe on OpenCode `2.3.0` (V2 API); summary at
`C:\Users\hi\AppData\Local\Temp\opencode\mneme-g0-evidence-20261117\SUMMARY.json`
(SHA-256 `16f5d3e837613f53128028d3e419c384ea5e7ba5b7064d897111e2ac8b44710d`).

This charter is documentation only. It does not change Core, ADRs, memory,
benchmarks, the support matrix or any integration status. It does not claim
native support, production readiness or relevant enforcement observed.

## 1. Decision summary

S1 is the smallest OpenCode pre-mutation integration: a **verified-new-file
`write`** with **complete content**, evaluated against **`FORBID_LITERAL` only**,
through the canonical `mneme check` engine, P2-first memory selection and shared
verdict trust. Its maximum evidence claim is **execution observed**.

Three claim boundaries are explicit:

- S1 does **not** use `--proposed-new-file` and makes **no ADR-034 G2 claim**.
  The target is verified absent by the host/bridge precondition, not by the
  checker's `proposed_new_source` route.
- S1 uses the `--input` audit invocation **only** under the ADR-018 §3 equivalence:
  a verified-absent target has no prior content, so the complete proposed content
  *is* the introduced set. This is a narrow equivalence, not a general
  whole-file gate.
- Historical V1/Sonnet evidence is evidence about V1 and Sonnet. It does not
  establish V2 or DeepSeek enforcement. G0 establishes host mechanics on V2
  2.3.0 only; it is not a DeepSeek enforcement run.

## 2. Scope

In scope:

- a new-file `write` whose target is verified absent at evaluation time;
- complete proposed content, delivered by the host event;
- `FORBID_LITERAL` rules only;
- canonical `mneme check` as the only enforcement engine;
- shared memory selection (`resolve_memory`), rule identity (`rule_id_for`) and
  verdict trust (`assess_verdict`);
- a thin host plugin and a Python bridge that supply transport only;
- test-local evidence with an execution-observed ceiling.

Non-goals:

- existing-file overwrite, `edit`, patch or hunk payloads;
- `FORBID_NUMERIC_ABOVE`, waivers, new rule types;
- arbitrary shell, MCP or custom tools, deletion, rename;
- Stop, CI, gateway admission, resource governance;
- production evidence persistence or a public evidence schema;
- fail-closed availability or any new authorization model;
- support-matrix promotion or a support-level statement in any new document;
- any Core, ADR, memory or benchmark change.

## 3. Accepted owner decisions

1. New-file `write` only, complete content, `FORBID_LITERAL` only.
2. Canonical `mneme check` and shared verdict trust.
3. P2-first memory selection.
4. Authority-pin mismatch proceeds with a visible `NOT_PROTECTED` diagnostic and
   no evidence claim.
5. Default-open availability on untrusted or missing evaluation.
6. No Core changes and no new enforcement engine.
7. Test-local evidence only; no production persistence.
8. Maximum literal claim: `EXECUTION_OBSERVED`.

## 4. Host pins: feasibility versus evidence

### 4.1 G0 feasibility pin (verified, not the S1 evidence pin)

| Element | Verified value |
| --- | --- |
| Host | OpenCode `2.3.0`, V2 plugin API |
| Binary SHA-256 | `f1aacb96863cea80e84020ff3e53c9f6831f444ef68e7e57aef08d27fee09bed` |
| Registration | default export `{ id, setup(ctx) }`; `ctx.tool.hook("execute.before", cb)` |
| Mutation tool | `write` |
| Input keys | `path`, `content` |
| Content | complete string; created file hash equals input hash in G0 |
| Paths | relative and absolute both accepted |
| Event keys | `tool`, `sessionID`, `agent`, `messageID`, `id`, `input` |
| Per-event cwd | absent |
| Authoritative directory | `ctx.session.get({ sessionID }).location.directory` |
| Blocking | throwing aborts the write; host reports `status: "error"` |
| Configuration | project `opencode.json`, `plugins` array, local directory |
| Activation proof | effective-config inspection plus a behavioural probe |
| `plugin list` | does not list local plugins; not accepted as activation proof |

G0 caveats carried into S1:

- one project and one session were exercised; cross-directory and multi-session
  resolution must be tested in S1;
- only `write` was exercised; `edit` and patch payloads are unsupported;
- the probe used Claude Haiku 4.5; host mechanics are model-independent, but the
  S1 evidence run must use the target model and record it;
- no race or atomicity property was established.

### 4.2 Pre-validation evidence environment

The final runtime image, host OS, component hashes, memory schema and target
model are **not** implementation prerequisites. They cannot exist before the
implementation is built. They are recorded at the pre-validation evidence gate in
§16.2, after implementation and before any evidence claim.

## 5. Architecture and file boundaries

New files only:

```text
mneme/integrations/opencode/__init__.py
mneme/integrations/opencode/bridge.py
integrations/opencode-plugin/package.json
integrations/opencode-plugin/index.ts
integrations/opencode-plugin/README.md
tests/integrations/opencode/conftest.py
tests/integrations/opencode/test_bridge_contract.py
tests/integrations/opencode/test_integration_identity.py
tests/integrations/opencode/test_s1_offline.py
tests/integrations/opencode/fixtures/…
```

Prohibited changes: `mneme/cli.py`, `mneme/enforcer.py`,
`mneme/integrations/claude_code/hook.py`,
`mneme/integrations/memory_selection.py`, `mneme/decision_governance.py`,
`mneme/decision_index_persistence.py`, `mneme/decision_retriever.py`,
`mneme/conflict_detector.py`, `.mneme/`, `docs/adr/`, `validation/`,
`benchmarks/`, `docs/integrations/README.md`.

No new document — including `integrations/opencode-plugin/README.md` — may state
or imply a support level. Only a separate support-matrix decision can do that.

If any shared module must change, stop and seek a separate charter and, where
applicable, a Layer 1 freeze amendment.

## 6. Interfaces

Plugin to bridge (stdin, one JSON object):

```json
{
  "schema": "mneme.opencode.bridge/v1",
  "tool": "write",
  "input": { "path": "<host path>", "content": "<complete content>" },
  "sessionDirectory": "<ctx.session.get({sessionID}).location.directory>",
  "sessionID": "…",
  "callID": "…",
  "agent": "…",
  "messageID": "…",
  "eventID": "…"
}
```

Bridge to plugin (stdout, one JSON object):

```json
{
  "schema": "mneme.opencode.decision/v1",
  "decision": "allow|block|unevaluated|skip|unsupported|setup_invalid",
  "reason": "…",
  "claim": "execution_observed|none",
  "evidence": {}
}
```

Exit 0 for any decision. A nonzero exit is a transport failure and is treated as
`unevaluated`.

The plugin reads only `decision`. It does not parse the checker payload.

**The bridge never mutates the target.** It may `lstat` the target to prove
absence, and it invokes the checker on a temporary carrier outside the governed
root. It never creates, writes, deletes, renames or chmods the target. Only the
host applies the write, and only after an `allow`.

The bridge also cannot observe the host's refusal. A `block` decision is the
bridge's output; whether the host actually refused is a separate host-side fact.
The charter records that as **host prevention observed** (§10), separate from
checker execution. Neither is inferred from the other.

## 7. Behaviour and decision matrix

| Observation | Applicability | Effective mode | Decision | Evidence | Host action |
| --- | --- | --- | --- | --- | --- |
| `TRUSTED_COMPLETE` | `APPLIED` + `FAIL` | `strict` | `block` | checker execution + host prevention witness | throw; no write |
| `TRUSTED_COMPLETE` | `APPLIED` + `FAIL` | `warn` | `allow` | checker execution | proceed + warning |
| `TRUSTED_COMPLETE` | `APPLIED` or `EXCLUDED` + `PASS` | `strict` or `warn` | `allow` | checker execution | host writes |
| `UNKNOWN` | any | either | `unevaluated` | none | proceed + diagnostic |
| `INCOMPLETE` | any | either | `unevaluated` | none | proceed + diagnostic |
| `UNTRUSTED` / `COMPLETENESS_UNSTATED` | any | either | `unevaluated` | none | proceed + diagnostic |
| launch error / timeout | none | either | `unevaluated` | none | proceed + diagnostic |
| no memory | none | either | `skip` | none | proceed + diagnostic |
| unlisted tool or non-complete payload | none | either | `unsupported` | none | proceed + diagnostic |
| `authority.json` mismatch | none | either | `setup_invalid` | none | proceed + `NOT_PROTECTED` diagnostic |

Only a trusted complete literal `FAIL` in effective `strict` mode may block. `warn`
never blocks.

`allow` is the only outcome that is a **trusted policy permission**. `unevaluated`,
`skip`, `unsupported` and `setup_invalid` may proceed under the explicit
default-open posture, but they are **not** Mneme-authorized protection and carry no
claim that Mneme permitted or protected the write.

## 8. Authority pin

`authority.json` is an expectation pin, never a selector or resolver. The bridge
loads `MemoryStore`, locates the decision and matches
`(decision_id, version_id, rule_id, value, include_paths)` using `rule_id_for`.

A mismatch yields `setup_invalid`, default-open: the write proceeds, the
diagnostic says `NOT_PROTECTED`, and no evidence is claimed. It is not a rule
violation and does not introduce a new blocking policy.

## 9. Availability and failures

OpenCode S1 adopts **default-open** as an explicit owner decision. It is **not**
derived from ADR-033 §3, whose failure matrix applies to Claude Code `PreToolUse`
only (§6), and the §4 authorization contract binds to the `.claude` declaration
and does not transfer.

Untrusted, incomplete, missing or failed evaluation is `unevaluated` and proceeds
with a visible diagnostic. No OpenCode fail-closed authorization is claimed. A
future closed posture requires its own charter and a host-validated authorization
mechanism.

Mode is resolved through `resolve_mode` after removing
`CLAUDE_PLUGIN_OPTION_MODE`; the bridge records the effective mode and source.
Mode is violation policy, not availability. In effective `strict` mode a trusted
complete literal `FAIL` blocks; in `warn` the same evaluation proceeds with a
visible warning and does not block.

## 10. Evidence and claim ceiling

Evidence is **test-local only**. It is written only when
`MNEME_OPENCODE_EVIDENCE_LOG` is set. There is no automatic production
persistence, no public schema and no support claim. `hook_evidence/v1` is not
reused.

The record is a **projection**, not a parallel enforcement model. It copies the
canonical checker applicability record verbatim (`rule_id`,
`decision_version_id`, `outcome`) and the host event identifiers, and it never
substitutes for `RuleEvaluation`, `Violation` or `EnforcementResult`. No claim is
derived from the record alone.

Record fields: host generation/version, plugin id, bridge version, Mneme version
and source commit or wheel hash, memory path/schema/selection reason/`walk`,
target path, event content SHA-256, canonical applicability entries,
observation state, decision, mode and mode source, claim level, the raw host
event identifiers, and the host-side refusal witness (tool status/error and
target state) where applicable. The refusal witness is populated by the test
harness or validator, never by the bridge. No source content and no credentials.

Two evidence facts are separate and must not be merged:

**Checker execution observed** requires:

1. a canonical `TRUSTED_COMPLETE` checker payload for this event;
2. the rule present as `APPLIED` or `EXCLUDED` with its canonical identity;
3. the raw host event identifiers present: `tool`, `sessionID`, `callID`,
   `agent`, `messageID`, `eventID`.

This is the literal-rule ceiling and is the only basis for
`EXECUTION_OBSERVED`.

**Host prevention observed** requires a host-side witness that the write was
refused: the host tool status/error and the target being absent. It is a host
observation, not an ADR-029 evidence level and not relevance. A block record may
carry both facts, but the host witness is not inferred from the bridge's `block`
return and does not upgrade the literal claim.

`UNKNOWN`, `INCOMPLETE`, `UNTRUSTED`, `skip`, `unsupported`, `setup_invalid` and
transport failures yield `none`. Never relevance.

## 11. Byte fidelity

Byte fidelity is a **test-local check**, not a platform guarantee. ADR-034
explicitly declines to claim equality between evaluated and landed bytes; S1 does
not claim it either.

Tests compare the host event content SHA-256, the carrier SHA-256 and the
host-written file SHA-256 for LF, CRLF, non-ASCII and no-trailing-newline
fixtures. Inequality is a failed test and a stop condition for that host.

The shared unrouted `_invoke_check` uses a text-mode carrier. A byte-exact carrier
is an ADR-034 §7a **routed-only** authorized correction; adopting it for S1 is a
reviewed shared change requiring a Layer 1 amendment, not a local workaround.

## 12. Test design and matrix

### 12.1 Invariants

- The bridge process performs no target mutation. The test snapshots the whole
  governed root and the target parent before and after the bridge call, and runs
  the bridge under a Python audit hook that fails on any write/open-for-write
  under the governed root. A fake host applies the write only after an `allow`.
- The carrier must be outside the governed root and removed afterwards.
- After a block, the target must be **absent**, not merely "unchanged".
- A skip, missing hook, tool denial or unevaluated result never counts as
  execution observed.
- Evidence comparisons are normalized: strip timestamps, session IDs, call IDs
  and host paths from the comparison projection. Separately assert that the raw
  record still contains the host event identifiers.
- The canonical applicability entries are compared against the checker payload;
  a record that diverges fails.

### 12.2 Unit tests

| ID | Test | Assertion |
| --- | --- | --- |
| U-01 | Absolute target | Passed through unchanged |
| U-02 | Relative + session directory | Joined to session directory |
| U-03 | Relative, no session directory | `unevaluated`; never adapter cwd |
| U-04 | Unknown tool id | `unsupported`; claim `none` |
| U-05 | Hunk/patch payload | `unsupported`; claim `none` |
| U-06 | Corpus fixture | 1 decision, 1 `FORBID_LITERAL`, no legacy content |
| U-07 | Checker argv | `--input`, `--target-path`, no `--top`, no filters |
| U-08 | Memory selection | P2-first reason and `walk` recorded |
| U-09 | Mode | Claude variable suppressed; default `strict`; `warn` never blocks |
| U-10 | Authority mismatch | `setup_invalid`, default-open, claim `none` |
| U-11 | State mapping | Coherent/incoherent/incomplete/unknown matrix |
| U-12 | Claim ceiling | All non-trusted states, skip, unsupported and setup_invalid = `none` |
| U-13 | Bridge immutability | Target absent/unchanged after bridge; no writes under governed root |
| U-14 | Normalization | Fingerprint stable across timestamps/session IDs |
| U-15 | Raw identifiers | Raw record retains `tool`, `sessionID`, `callID`, `agent`, `messageID`, `eventID`; normalized projection strips session/call IDs only |
| U-16 | Canonical projection | Applicability entries copied verbatim; divergence fails |
| U-17 | Carrier isolation | Carrier outside governed root; removed after the call |

### 12.3 Integration-identity tests

Modelled on `tests/integrations/hermes/test_integration_identity.py`: required
imports present, no local diff, parser, resolver, matcher or scoring logic.

### 12.4 Offline integration tests

| ID | Case | Expected |
| --- | --- | --- |
| I-01 | Verified-absent forbidden literal | `block`; fake host writes nothing; target absent |
| I-02 | Verified-absent compliant | `allow`; fake host writes; functional check |
| I-03 | Out-of-scope rule | `allow` + `EXCLUDED`; claim `execution_observed` |
| I-04 | Existing target | exactly `unsupported` with reason `existing_target` |
| I-05 | No memory | exactly `skip`; claim `none` |
| I-06 | Incoherent checker stub | exactly `unevaluated`; claim `none` |
| I-07 | Wrong memory | selection reason recorded; no false claim |
| I-08 | Wrong mode | exactly `allow` with claim `execution_observed`; no block and no host refusal under `warn` |
| I-09 | Cross-directory session | relative target resolves to session directory |
| I-10 | Byte fidelity (LF/CRLF/non-ASCII/no trailing newline) | event/carrier/file hashes compared for all four fixtures; inequality fails |
| I-11 | Absent hook | no evaluation; no claim |
| I-12 | Race cases: (a) target appears after absence proof; (b) target appears between evaluation and write; (c) symlink introduced at the target; (d) hardlink substituted | Each outcome is `DETECTED` or `UNDETECTED_RACE`; any undetected sets aggregate `race_resistance: NOT_ESTABLISHED` and is a documented bypass, never a pass |
| I-13 | Authority mismatch | `setup_invalid`; visible NOT_PROTECTED; claim `none` |
| I-14 | Host-side block witness | fake host records refusal; bridge return alone is insufficient |

### 12.5 Canonical test battery

Run the repository's applicable tests for changed areas, plus the new
`tests/integrations/opencode/` suite. Do not modify the benchmark suite.

## 13. Independent validation handoff

The implementer must not grade its own implementation as independently validated.
Handoff package:

- pinned OpenCode host `2.3.0` and the exact plugin build hashes;
- DeepSeek V4.1 model identity for the target validation, separate from G0's
  Claude run;
- setup and activation instructions, including effective-config proof and a
  behavioural probe;
- synthetic repository and decision fixture;
- exact BLOCK/ALLOW/negative-space criteria;
- sanitized evidence and host-side file-state witnesses;
- source and configuration SHA-256 values;
- explicit unsupported surfaces and race limitations.

The validator records the host-side result; the implementation's own evidence is
not accepted as independent validation.

## 14. Layer 1 freeze determination

**A Layer 1 freeze amendment is required.** S1 adds a blocking enforcement surface
on a new host. ADR-033's implementation gates and the ADR-034 reconciliation
require a matching `[layer1-freeze]` amendment alongside the bounded
implementation charter. New files alone do not exempt the surface.

The amendment must be accepted and recorded in the implementation authorization
gate (§16.1) before implementation. There is no charter-level waiver: any change to this requirement
is itself an ADR-level decision, not an implementation choice.

A byte-exact carrier or any shared-code change is a separate reviewed change and
requires its own freeze classification.

## 15. Stop conditions

1. Host event lacks complete content or pre-mutation blocking.
2. Pinned tool identifier is not `write` with `path` and `content`.
3. Relative path cannot be resolved from an authoritative session directory.
4. Any CLI, enforcer, hook, memory-selection, governance or retriever change is
   required.
5. Byte fidelity cannot be demonstrated on the pinned host.
6. Fail-closed availability is requested.
7. Authority-mismatch behaviour changes from default-open.
8. Literal relevance or numeric support is requested.
9. Fixture corpus cannot be reduced to one literal rule without filtering.
10. Any test would require the bridge to mutate the target.
11. The Layer 1 amendment is absent or rejected.
12. Any new document states or implies a support level.

## 16. Authorization gates

Two gates, in order. Passing one does not imply the other.

### 16.1 Implementation authorization gate

Implementation may begin only when **all** of the following are true:

1. this charter is accepted by the owner;
2. owner acceptance is recorded against the exact reviewed commit of this charter
   and the exact reviewed commit of the Layer 1 freeze amendment;
3. this charter is merged;
4. the Layer 1 freeze amendment in §14 is accepted and merged;
5. the bounded host contract is verified: OpenCode 2.3.0 V2, tool `write` with
   `path` and `content`, complete content, session-directory resolution, and
   throw-before-mutation;
6. the implementation boundary is new files only.

Acceptance is an owner statement on the PR. It is not a fill-in record inside this
document, and green CI is not acceptance.

### 16.2 Pre-validation evidence gate

This gate applies after implementation and before any evidence claim. It does not
block implementation. Every value is recorded in the validation package:

- final runtime image digest;
- OpenShell version;
- host version and host OS used for validation;
- Python version;
- memory schema (`v1` or `v2`);
- plugin, bridge and checker SHA-256;
- DeepSeek V4.1 model identity;
- independent validator identity and environment;
- sanitized evidence copies and file-state witnesses;
- source and configuration hashes.

The implementation may be built and unit-tested before this gate. No checker
execution observation, host prevention observation or validation claim may be made
until it is satisfied.
