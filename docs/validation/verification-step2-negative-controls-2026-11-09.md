# Verification step 2: ADR-029 negative controls against v0.11.0

**Date:** 2026-11-09
**Authorization:** owner approval of Verification step 2 (bounded negative-control
validation), 2026-11-09, under the
[roadmap Verification slice](../roadmap/README.md) (#579, #768).
**Implementation:** `main` at `101f3f42`. The runtime (`mneme/`) is identical to
v0.11.0 (`619d5405`): `git diff 619d5405 101f3f42 -- mneme/` is empty.
`mneme.__version__` reports `0.11.0`. Python 3.12.10, Windows.
**Type:** validation record. No runtime, adapter, CI, evaluator pin, frozen
benchmark or waiver change. No earlier result is upgraded.

## 1. Result

**18 of 18 controls meet their expectation.** All 17 negative controls stay at or
below execution observed, and the positive baseline reaches relevant
enforcement observed.

**One qualification decides how to read that.** In 4 negative controls (C1c, C2a,
C2c, C5a), the shipped function `relevant_enforcement_per_rule` returns `True`
for the claimed rule. Those claims fail closed only because of consumer-side
checks: the complete `(decision_id, decision_version_id, rule_id)` match
required by the [#761 §5.1 ruling](adr029-evidence-completeness-audit-2026-11-08.md),
and a subject-digest match against the record's `carrier_sha256`. The function
on its own does not make a version-specific or subject-specific claim fail
closed. This is the consumer obligation already ruled on, now shown
empirically. It is reported here, not corrected (step 2 boundary).

## 2. Method

The harness is
[`artifacts/verification-step2-negative-controls/run_controls.py`](artifacts/verification-step2-negative-controls/run_controls.py).
It drives only the shipped producers, in process:

- `mneme check --json` through `mneme.cli.main`;
- the Claude Code hook through `hook.handle_event`, with the evidence seam on
  (`MNEME_HOOK_EVIDENCE_LOG`, pinned host `("2.1.303", "ab"*32)`) and the
  in-process checker transport, strict mode, default (open) availability;
- `MnemeAgentSdk.evaluate_mutation` and `MnemeLangChain.evaluate_tool_call`.

**Fixtures** are built deterministically in a temporary directory with
`tests/canonical_fixtures.canonical_document`. Two decisions: `LIT-1`
(`FORBID_LITERAL psycopg2`, global) and `ADR-034T` (`FORBID_NUMERIC_ABOVE`, max
5 seconds on `ROUTER_DEADLINE_S`, `include_paths: ["src/**"]`).

| Fixture | Change | `ADR-034T` identity |
|---|---|---|
| `v1_canonical` | baseline | `dver-86427d8a…`, `…:FORBID_NUMERIC_ABOVE:29b88006…` |
| `v2_canonical` | decision text revised | new version `dver-768f9263…`, **same** `rule_id` |
| `v3_canonical` | bound 5 → 10 | same version, **new** `rule_id` `…:3e08297f…` |
| `sectionless_literal` | no `decision_index`, `LIT-1` only | none |
| `sectionless_numeric` | no `decision_index`, both decisions | none (load refused) |

**Claim assessment** (harness-side, from accepted contracts only):

- **Hook record:** relevant only if `relevant_enforcement_per_rule(record,
  HOST)[claimed rule_id]` is `True` **and** the record's rule entry matches the
  claimed `decision_version_id`, with `decision_id` taken from the `rule_id`
  prefix (#761 §5.1) **and**, when the claim names a subject, its digest equals
  `carrier_sha256`. Otherwise execution observed if the checker was trusted,
  else not executed.
- **`mneme check` payload:** no relevance assessor exists for this surface
  (#761 E-1, E-2), so at most execution observed. Identity is reported through
  `EvidenceIdentity`.
- **Agent SDK / LangChain:** `fail_open` and `skip` evaluate nothing (not
  executed). A trusted gate result is at most execution observed (#769).

Levels: not executed < execution observed < relevant enforcement observed.

**Reproduce** from the repository root:

```bash
python docs/validation/artifacts/verification-step2-negative-controls/run_controls.py
```

It rewrites
[`results.json`](artifacts/verification-step2-negative-controls/results.json)
and exits 1 if any control misses its expectation. Two consecutive runs
produced byte-identical output; temporary paths are scrubbed to `<project>`.

## 3. Controls: expected versus actual

`fn` = `relevant_enforcement_per_rule` for the claimed rule; `id` = complete
identity match; `subj` = claimed subject digest equals `carrier_sha256`.

| ID | Control | Expected | Actual | fn | id | subj | Key observation |
|---|---|---|---|---|---|---|---|
| P1 | Baseline: hook refuses `ROUTER_DEADLINE_S = 60` in new `src/new.py`; claim matches | relevant | **relevant** | True | True | True | exit 2, `refused`, `numeric_violation` |
| **1. Missing canonical decision identity** |
| C1a | Section-less memory, literal violation via `mneme check` | ≤ execution | execution | – | – | – | verdict FAIL; `LIT-1` `decision_version_id` empty; `EvidenceIdentity.complete` False (missing `decision_version_id`) |
| C1b | Section-less memory with a numeric rule, CLI and hook | ≤ execution | **not executed** | False | False | True | CLI raises `DecisionIndexMigrationRequired`; hook gets no parseable verdict, record `trusted: false`, `rules: []`, `proceeded`, cause `fail_open` |
| C1c | Genuine P1 record; claim omits `decision_version_id` | ≤ execution | execution | **True** | False | True | fails closed only on identity |
| **2. Mismatched decision version or rule identity** |
| C2a | Genuine V1 record; claim names V2 (same `rule_id`, new version) | ≤ execution | execution | **True** | False | True | fails closed only on the version comparison |
| C2b | Genuine V1 record; claim names the V3 rule (bound changed) | ≤ execution | execution | False | False | True | claimed `rule_id` absent from the record |
| C2c | Record's `decision_version_id` rewritten to V2; claim names V1 | ≤ execution | execution | **True** | False | True | the function checks only that the version is non-empty |
| **3. Excluded rule applicability** |
| C3a | Numeric rule `EXCLUDED` (target `docs/new.py`) via `mneme check --proposed-new-file` | ≤ execution | execution | – | – | – | verdict PASS; trace `EXCLUDED`, identity complete |
| C3b | Same through the hook; claim names the numeric rule | ≤ execution | execution | False | False | True | record `rules: []`, `proceeded`, cause `no_violation` |
| **4. Incomplete evaluation** |
| C4a | Unverified `--input`, numeric rule `APPLIED` | ≤ execution | execution | – | – | – | `evaluation_complete: false`; `MATCHER_UNEVALUATED`, `INCOMPLETE_SOURCE_INPUT` |
| C4b | Hook new-file `Write` of `ROUTER_DEADLINE_S = compute()` | ≤ execution | execution | False | True | True | `MATCHER_UNEVALUATED`, `UNRECOGNIZED_FORM`; `proceeded`, cause `fail_open` |
| **5. Stale subject digest (numeric hook path)** |
| C5a | Genuine record for content A; claim about later content B | ≤ execution | execution | **True** | True | False | fails closed only on the subject comparison |
| C5b | Record's subject and rule digests rewritten to B; carrier stays A | ≤ execution | execution | False | True | False | common-binding check rejects the internal mismatch |
| **6. Agent SDK / LangChain fail-open and skip (#769)** |
| C6a | Agent SDK `Edit` of a missing file | not executed | not executed | – | – | – | `fail_open`, no payload |
| C6b | Agent SDK non-mutating tool (`Read`) | not executed | not executed | – | – | – | `skip` |
| C6c | LangChain unmapped tool (`shell`) | not executed | not executed | – | – | – | `skip`, trace has `via: "langchain"` |
| C6d | LangChain `edit_file` of a missing file | not executed | not executed | – | – | – | `fail_open`, trace has **no** `via` (#769 V-4) |
| C6e | Agent SDK trusted deny (literal) | ≤ execution | execution | – | – | – | `deny`/FAIL; trace keeps no rule identity (#769 V-2) |

## 4. Findings

| ID | Finding | Kind |
|---|---|---|
| N-1 | **All negative controls fail closed as evidence claims under the accepted consumer rules.** None reaches relevant enforcement observed. | result |
| N-2 | **`relevant_enforcement_per_rule` alone over-reports in 4 of 17 negatives** (C1c, C2a, C2c, C5a). It keys by `rule_id`, checks `decision_version_id` only for non-emptiness, and validates digests only for consistency inside the record, not against an external claim. A consumer that uses its boolean without the complete identity and subject comparison would accept a wrong-version or stale-subject claim. Already a ruled consumer obligation (#761 §5.1); now demonstrated. Moving the comparison into code needs separate authorization. | finding, consumer obligation |
| N-3 | **Section-less memory with a numeric rule is refused at load** (`DecisionIndexMigrationRequired`). Under the default open availability posture the hook then lets the write proceed with cause `fail_open` and an untrusted record. No evidence claim results, but the write is not governed. | observation; ADR-033 posture behavior, unchanged |
| N-4 | **Incomplete numeric evaluation proceeds under the default open posture.** C4b proceeded with cause `fail_open` and an `APPLIED`, `MATCHER_UNEVALUATED` rule. The record keeps the identity, so it stays execution observed and never reaches relevance. | observation; ADR-033/034 behavior, unchanged |
| N-5 | **Excluded applicability leaves no rule entry in the hook record** (C3b `rules: []`). A claim about an excluded rule cannot be supported, which is correct. But the hook record alone cannot show that the rule was considered and excluded; the `mneme check` payload can (C3a). | observation |
| N-6 | The #769 adapter findings reproduce: `fail_open`/`skip` evaluate nothing, the trace keeps no rule identity, and delegated LangChain entries carry no `via`. | consistent with #769 |

## 5. What this record does not claim

- No new relevant-enforcement path. P1 is the existing #761 E-1 path.
- No authenticity: the hook record is the control's own provenance, not an
  attestation (ADR-034 §7a, ADR-025). Consistently forged records are out of
  scope.
- No coverage of closed availability, warn mode, fork PRs, CI, or the
  `--adr-dir` view.
- No change to any earlier result, and no authorization of step 3 (frozen
  end-to-end fixture) or of any runtime change.
