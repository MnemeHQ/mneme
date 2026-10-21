# Reliable Enforcement C2a — PreToolUse availability routing charter

**Status:** **ACCEPTED** by the owner on 2026-10-20 (merges via PR #574).
Documentation only. Acceptance authorizes **no implementation** until the
section 9 `[layer1-freeze]` amendment merges. This charter does not edit the
Layer 1 freeze document; the
matching `[layer1-freeze]` amendment is drafted in section 9 and is opened as a
separate PR only after this charter merges (Amendment Procedure §3(b)). No code,
test, hook, plugin, CI, ruleset or `.mneme/` change.
**Governing decision:** [ADR-033](../adr/ADR-033-opt-in-fail-closed-enforcement.md)
(accepted 2026-10-20, #483 `78459d1a`), implementation gates 2 and 4.
**Source anchor:** `MnemeHQ/mneme` `main` @ `78459d1a`. Line numbers refer to
that commit.
**Builds on:** the C1 verdict-consistency charter and PR #484 (`60b02af3`);
T-08 slice 1 (#514 charter, #515 amendment, #517 `2a445142`, #518 live
re-probe); the DG1F `AUTHORIZATION_UNVERIFIABLE` spec (#513); G3 and G3-B
(#512).
**Excluded by owner decision:** live host validation (ADR-033 gate C3) and CI
implementation (gate C4). No new experiment.

## 1. What C2a is

C2a is the first, bounded slice of ADR-033 gate 4 for the Claude Code
`PreToolUse` direct-write surface (`Edit|Write|MultiEdit`). It adds the
**routing and classification** that ADR-033 §§2-4 require, behind a verifier
interface, and a deterministic regression matrix. It changes nothing for a
repository without a local declaration.

### 1.1 Scope finding: C2a cannot refuse on availability

ADR-033 permits an availability refusal only when authorization is verified as
`AUTHORIZED` (§4.4 precedence), and its gate 2 requires the baseline
verification, enrollment and revocation design to be pinned **before any
behavior change**. That design is not in this charter's approved scope.

Therefore C2a ships a verifier **interface with no verifier**. For a
repository with a local declaration, the verifier result is always
`AUTHORIZATION_UNVERIFIABLE` with reason `VERIFIER_CONFIG_MISSING`, which under
Architecture A means a visible proceed (ADR-033 §4.3). **No C2a code path can
produce an availability refusal.** The verifier, the declaration's identity and
activation fields, and the enrollment and revocation operations are deferred to
a separate **C2b** charter (section 8).

### 1.2 The Architecture A limitation, preserved

To be repeated in every assurance claim that builds on C2a:

> **Deleting the local declaration can silently disable opt-in fail-closed
> protection.**

This is the owner's statement of ADR-033 §4.0, which says: "a repository whose
declaration has been deleted is indistinguishable from one that was never
enrolled", and lists deletion of the declaration under "Not guaranteed".

C2a's detection step is the mechanism behind this limitation: no declaration
means no trigger.

## 2. Current behavior (anchor `78459d1a`)

`handle_event` (`hook.py:1106`) resolves memory from the edited target
(`hook.py:1130`, T-08 slice 1) and returns `0` at once when none is found
(`hook.py:1131`). It also proceeds (exit 0) when content cannot be
materialized (`:1140`), when the edit introduces no non-blank content
(`:1143`), when the checker returns no observation (`:643`), when the
observation is untrusted (`_run_check`), and when `evaluation_complete` is
`false` (`:670`). The last case proceeds even when the payload carries matched
violations, because the payload includes `violations` whatever the completeness
(`cli.py:388`, `:405`). Historical payloads without `evaluation_complete` are
treated as complete (`hook.py:359`).

## 3. Authorized change (only after the section 9 amendment merges)

### 3.1 Local-declaration detection, before the memory early return

- Before `hook.py:1131`, walk up from the same start directory as T-08 slice 1
  (`_direct_write_memory_start(event)`) to the **first ancestor containing a
  `.mneme/` directory**. That directory is the policy root for this purpose.
- The local declaration is `<policy root>/.mneme/availability.json`. Detection
  does not depend on whether `project_memory.json` exists, so a declaration
  survives the loss of memory (ADR-033 §4.4 "Declaration present and valid;
  memory missing").
- `MNEME_MEMORY` is **not** consulted for locating the declaration. A
  difference between the effective memory (`find_memory`, which honors
  `MNEME_MEMORY`) and the declaration's `memory_path` is recorded as an SS-3
  mismatch (ADR-033 §4.1).
- **No declaration:** the code path is exactly today's, with byte-identical
  output, the same exit codes and zero network activity (default-open parity,
  ADR-033 §4.3).

### 3.2 Declaration format (v1, minimal)

```json
{
  "schema": "mneme.availability/v1",
  "availability": "closed",
  "memory_path": ".mneme/project_memory.json"
}
```

- Exactly these three keys are required in C2a. Unknown keys are preserved and
  ignored.
- The repository-identity, activation-binding and review fields required by
  ADR-033 §4.1 are **reserved for C2b** and must be added additively.
- A file that is not valid JSON, lacks a required key, or has another value is
  **present but invalid**. In C2a it is treated like any present declaration
  (verification unavailable), with the parse problem named in the diagnostic.
- C2a adds no command that writes this file.

### 3.3 Verifier interface

- A single function returns one of `AUTHORIZED`, `REVOKED`, `VERIFIED_ABSENT`,
  `AUTHORIZATION_UNVERIFIABLE(reason)`, using the reason set of ADR-033 §4.3.
- C2a's only implementation returns
  `AUTHORIZATION_UNVERIFIABLE(VERIFIER_CONFIG_MISSING)`, makes no network call
  and reads no git configuration.
- The routing code must handle all four outcomes per the ADR-033 §4.4 matrix,
  so C2b only replaces the implementation. Those branches are exercised in C2a
  through the test seam only, never in shipped behavior.

### 3.4 Evaluation-state classifier

An internal classifier, built on the existing `assess_verdict` (#484) without a
second parser, labels each check observation:

| State | Meaning |
|---|---|
| `TRUSTED_COMPLETE` | Coherent payload, `evaluation_complete` true |
| `COMPLETENESS_UNSTATED` | Coherent historical payload without `evaluation_complete` |
| `INCOMPLETE` | Coherent payload, `evaluation_complete` false (with or without matched violations) |
| `UNTRUSTED` | Incoherent or malformed observation |
| `NOT_RUN` | No observation (launch error, timeout, materialization failure) |
| `SKIPPED` | Out-of-scope event or proven empty introduced delta |

The labels are conceptual (ADR-033 §2): no public JSON schema change and no
change to `mneme check` output.

### 3.5 Historical payloads

On the no-declaration path, a payload without `evaluation_complete` is handled
exactly as today. On the declaration path it is classified
`COMPLETENESS_UNSTATED`, which ADR-033 §2 forbids treating as proof of a
complete evaluation under `closed`. In C2a this affects only the diagnostic.

### 3.6 Mixed partial results (precedence pinned)

A coherent payload with `evaluation_complete: false` **and** one or more
matched violations:

- **No-declaration path:** unchanged (proceed, today's diagnostic). Changing it
  would break default-open parity.
- **Declaration path, verification unavailable (all of C2a):** proceed, and the
  diagnostic lists the matched violations as **matched in a partial
  evaluation**, never as a complete rule verdict.
- **Declaration path, `AUTHORIZED` (C2b onward; specified now, not reachable in
  C2a):** refuse as operational UNEVALUATED, listing the matched violations as
  partial. The refusal is never labelled a rule FAIL.

### 3.7 Diagnostics on the declaration path

The diagnostic names the verification outcome and reason, the classifier state,
and any SS-3 mismatch or parse problem, without echoing submitted content
(ADR-033 §7). It uses the hook's existing stderr diagnostic channel.

**Delivery is not claimed.** Whether an exit-0 hook diagnostic reaches the user
is unproven: the T-08 A1 headless evidence classified host delivery of a hook
`systemMessage` as NOT_DELIVERED (#563). C2a therefore claims only that the
diagnostic is emitted. ADR-033 §4.3's "visible proceed" is met only once live
evidence (gate C3) shows delivery. Until then, every C2a claim says "emitted".

## 4. Regression matrix (deterministic, offline)

New fixtures under `tests/fixtures/availability_policy/v1/` and tests under
`tests/integrations/claude_code/`. They use the real hook entry point and real
`mneme check`, with no network access (sockets patched to fail).

| # | Case | Expected |
|---|---|---|
| P1 | No declaration, each existing hook fixture class (PASS, WARN, strict FAIL, incomplete, untrusted, crash, missing memory, empty delta) | **Byte-identical** stdout, stderr and exit to `main` @ `78459d1a` |
| P2 | No declaration, network sockets disabled | Same as P1; no socket opened |
| D1 | Valid declaration, memory present, complete PASS | Proceed; UNVERIFIABLE(VERIFIER_CONFIG_MISSING) diagnostic |
| D2 | Valid declaration, strict trusted FAIL | **Blocks exactly as today** (exit 2, same reason text) plus the verification diagnostic |
| D3 | Valid declaration, memory missing | Proceed; diagnostic names missing memory and unavailable verification |
| D4 | Invalid declaration (bad JSON, missing key, wrong value) | Proceed; diagnostic names the parse problem |
| D5 | Valid declaration, `MNEME_MEMORY` set to other memory | Proceed; SS-3 mismatch named; the check result reported as not bound to the declared memory |
| D6 | Valid declaration, historical payload without `evaluation_complete` | Proceed; `COMPLETENESS_UNSTATED` named |
| D7 | Valid declaration, incomplete evaluation with a matched violation | Proceed; violations listed as matched in a partial evaluation |
| D8 | Valid declaration, untrusted observation / crash / timeout | Proceed; `UNTRUSTED` or `NOT_RUN` named |
| D9 | Declaration deleted (the §1.2 limitation) | Identical to P1: no trigger, nothing reported |
| S1 | Routing via the test seam with `AUTHORIZED`, `REVOKED`, `VERIFIED_ABSENT` | Outcomes match ADR-033 §4.4. **Seam only**; shipped verifier cannot return these |
| B1 | Frozen canonical benchmark | Unchanged: 7/7 scenarios, Layer 2 pass rate 100% |
| B2 | Full test suite and PR battery | Pass; no existing test changed except to add parity assertions |

## 5. Explicitly preserved

- `mneme check` CLI, its output, exit codes and the malformed-memory crash path
  (CI1.4 §7 condition 4 stays a separate decision).
- `find_memory`, `MNEME_MEMORY` precedence and T-08 slice 1 selection.
- strict/warn semantics, `assess_verdict`, `DecisionRetriever`,
  `ConflictDetector`, ADR-020 applicability, the frozen benchmark.
- Bash, SessionStart and Stop handlers (ADR-021 behavior unchanged).
- `decision_index` as sole decision authority (ADR-030 §1); the declaration
  holds no decisions or rules.

## 6. Explicitly NOT authorized

- Any availability refusal; any verifier that contacts a remote or reads git
  configuration; any enrollment, issuance or revocation command.
- The C2b declaration fields (identity, activation binding, review record).
- Any change to Bash, SessionStart or Stop, to CI workflows, rulesets or
  Actions policy, or to other agent integrations.
- Live host validation (gate C3) and CI implementation (gate C4).
- Changing `mneme check` or the malformed-memory behavior.
- Claiming that the diagnostic is delivered or that any repository is
  protected by C2a.

## 7. Required acceptance evidence (for the implementation PR)

- Sections 3.1-3.7 implemented exactly; nothing else changed.
- The full section 4 matrix passing, with P1 parity measured against `main` @
  `78459d1a` (the comparison method is recorded in the PR).
- The frozen benchmark result (B1) and the full suite (B2).
- A statement in the PR that C2a cannot refuse on availability (§1.1), repeats
  the §1.2 limitation verbatim, and claims diagnostics as emitted, not
  delivered (§3.7).

## 8. Deferred, separately gated

- **C2b charter:** the verifier (live query of a protected ref, Mneme-selected
  revision, no ambient git configuration), the declaration's identity,
  activation and review fields, enrollment/issuance/revocation operations, and
  the first reachable availability refusal. Its own `[layer1-freeze]`
  amendment.
- **C3:** live Claude Code proof, including diagnostic delivery (§3.7) and the
  spec's U, T, RV, S and P groups (ADR-033 gate 5).
- **C4:** CI implementation under ADR-033 §5, with P7/P8 approval and the CI1
  rollout gate (CI1.4 §7 condition 9).
- **Condition 4:** the malformed-memory CLI decision.

## 9. Proposed `[layer1-freeze]` amendment (draft; not applied here)

To be opened as a separate PR titled
`[layer1-freeze] Authorize ADR-033 C2a PreToolUse availability routing`,
appended to `docs/architecture/layer1-freeze-e73ff7d.md` after this charter
merges:

> **Amendment — authorize ADR-033 C2a PreToolUse availability routing
> (YYYY-MM-DD)**
>
> This is an authorization for **routing, classification and diagnostics at one
> boundary**. It does not authorize any availability refusal, verifier,
> enrollment or revocation, fail-closed enforcement, or any change to other
> boundaries.
>
> **Change:** at the Claude Code direct-write boundary (`handle_event`, `mneme/integrations/claude_code/hook.py`),
> detect a local `.mneme/availability.json` declaration before the memory
> early return. Without a declaration, behavior is byte-identical to `main`.
> With one, run today's check path unchanged and emit a diagnostic that names
> `AUTHORIZATION_UNVERIFIABLE(VERIFIER_CONFIG_MISSING)`, the evaluation state,
> and any SS-3 mismatch or partial-evaluation violations.
>
> **Sections referenced:** the Freeze Anchor **Status** clause and the
> Amendment Procedure.
>
> **Rationale (Amendment Procedure §3(b)).** A distinct behavioral charter was
> already merged: Reliable Enforcement C2a charter (PR #NNN, squash `<sha>`),
> under accepted ADR-033 (#483, `78459d1a`). No behavior change is
> retroactively justified.
>
> **Governing authority:** accepted ADR-033, ADR-021, ADR-017, ADR-020,
> ADR-029, ADR-030, ADR-031; the merged C1 (#260) and T-08 slice-1 charters.
>
> No other code path is authorized.

## 10. Sequence

1. This charter PR: review and merge.
2. The section 9 `[layer1-freeze]` PR: review and merge.
3. One implementation PR meeting section 7.
4. Later, each under its own approval: C2b charter, then C3 and C4.

## 11. Open questions

- **Q1. Policy-root rule.** Section 3.1 takes the first ancestor with a `.mneme/`
  directory. A nested `.mneme/` without a declaration therefore hides an outer
  declaration. That matches how `find_memory` stops at the first memory, but it
  should be confirmed in review.
- **Q2. Declaration filename.** `availability.json` is proposed; C2b may need to
  rename it before any enrollment command exists. Renaming is free until C2b.
- **Q3. Diagnostic channel.** Section 3.7 uses stderr. Whether a structured
  host-output field is better depends on C3 evidence and is left to C2b/C3.
