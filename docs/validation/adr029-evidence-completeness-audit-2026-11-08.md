# ADR-029 evidence completeness audit against v0.11.0

**Date:** 2026-11-08
**Pinned implementation:** `main` at `619d5405` (v0.11.0 tag `619d5405`)
**Type:** read-only audit. No runtime, CLI, schema, hook, CI, ADR or policy
change. Authorizes nothing.

## 1. Purpose and boundaries

This record maps every evidence surface that v0.11.0 ships to the six binding
dimensions of [ADR-029](../adr/ADR-029-enforcement-evidence-binding-semantics.md)
§2, and states where "relevant enforcement observed" is achievable today and
where it is not.

It is the first step of the Evidence & Evaluation track, run in parallel with
the ADR-031 decision-governance audit. Ownership rule, unchanged from ADR-031
§10: **decision governance determines which decisions are authoritative;
evidence verifies and records what happened under them.** Nothing here
decides authority, applicability, waivers or relevance policy.

It feeds the draft roadmap slice
[#579](https://github.com/MnemeHQ/mneme/pull/579) (unmerged, written
2026-10-21, before v0.11.0). §7 lists what #579 needs to reconcile.

## 2. Surfaces audited

| Surface | Schema | Source |
|---|---|---|
| CLI | `mneme.check/v1` (`mneme check --json`) | `mneme/cli.py` `_applicability_record`, `_violation_record`, `_subject_record` |
| Agent-host pre-write hook | `mneme.hook_evidence/v1` | `mneme/integrations/claude_code/hook.py` `build_evidence_record`, `relevant_enforcement_per_rule` |
| CI merge gate | `mneme.c4.gate-report/v1` (adapter-internal) | `scripts/ci/adr033_c4_gate.py`, [github-actions-c4-gate.md](../integrations/github-actions-c4-gate.md) |

The carriers underneath all three are the runtime trace types
`RuleEvaluation` (`mneme/path_selectors.py`), `Violation` and
`EnforcementResult` (`mneme/enforcer.py`), as ADR-029 §3 requires. DG1E
(ADR-031 §10) added `decision_version_id` and ADR-030 §7 `rule_id` to both
`RuleEvaluation` and typed `Violation`; `mneme/decision_governance.py`
`EvidenceIdentity` checks their structure.

## 3. Completeness matrix

Legend: **bound** = deterministic identifier present in the surface's own
output for the same evaluation; **joined** = present only by joining records
the surface did not emit itself; **absent** = not carried; **n/a** = not in
scope for that surface.

### 3.1 Literal-tier rules (`FORBID_LITERAL`)

| # | Dimension | CLI `mneme.check/v1` | Hook `hook_evidence/v1` | CI `c4.gate-report/v1` |
|---|---|---|---|---|
| 1 | control / provenance | **absent.** `surface` and `surface_version` live only inside the `subject` record, which is omitted for literal-only checks | **bound.** `surface`, `mneme_version`, host `version` + `executable_sha256` | **joined.** Adapter SHA-256, evaluator commit + wheel hash, recorded by the adapter from workflow inputs, not by the evaluator |
| 2 | subject | **absent.** No digest for literal-only or unverified input | **partial.** `carrier_sha256` always; `checker.subject` only for `proposed_new_source` | **joined.** Per-file content SHA-256 + head SHA from the adapter; no git blob id |
| 3 | decision | **bound** on canonical memory (`decision_id` + `decision_version_id`) | **bound** for violations only (`rule_id`); no `decision_version_id` in the literal violation entry | **partial.** Extract keeps `decision_id`, `rule_id`, `outcome`; drops `decision_version_id` (still in raw `stdout`) |
| 4 | rule | **bound** (ADR-030 §7 `rule_id`) | **bound** for violations (§7c attribution) | **bound** in extract and raw output |
| 5 | applicability | **bound** (`APPLIED` / `EXCLUDED` / `UNKNOWN` per rule) | **absent** for literal rules (`rules` holds numeric rules only) | **bound** |
| 6 | outcome | **partial.** Reject is attributable (violation names `rule_id`). Allow is never recorded per rule: it is only the absence of a violation | **partial.** Reject attributable to a named rule; cause stays `other_rule`; §7c says attribution, never relevance | **partial.** Per-file classification and aggregate, not per rule |
| – | configuration (ADR-029 §4 slot) | **absent.** `memory_path` only, and only inside `subject` | **absent** | **bound.** Trusted memory blob + source commit |

### 3.2 Numeric rules (`FORBID_NUMERIC_ABOVE`, ADR-034)

| # | Dimension | CLI | Hook | CI |
|---|---|---|---|---|
| 1 | control / provenance | **bound** (`subject.surface`, `surface_version`, `runtime`) | **bound** | n/a: gate treats numeric/`subject` payloads as UNEVALUATED |
| 2 | subject | **bound** (`subject_sha256` on subject and per rule) | **bound** for new-file `Write` (`proposed_new_source`, digest = carrier) | n/a |
| 3 | decision | **bound** | **bound** (`decision_version_id` per rule) | n/a |
| 4 | rule | **bound** | **bound** | n/a |
| 5 | applicability | **bound** | **bound** | n/a |
| 6 | outcome | **bound** (`matcher_status`, `matcher_outcome`) | **bound** and attributed to the hook disposition (§7b) | n/a |
| – | configuration | **absent** (`memory_path` only) | **absent** | n/a |

## 4. End-to-end probe (literal, CLI)

Run from the administrative checkout at `619d5405`, `mneme` 0.11.0, against the
repo's own canonical memory:

```text
mneme check --memory .mneme/project_memory.json --input <probe.md> \
  --target-path docs/probe.md --query "install package" --mode warn --json
```

Input: one line naming the forbidden install command (ADR-005).

Observed payload keys: `applicability`, `evaluation_complete`, `freshness`,
`mode`, `schema`, `verdict`, `violations`. No `subject`.

- applicability: one trace, `ADR-005`, rule
  `ADR-005:FORBID_LITERAL:cbf4d271…`, `decision_version_id`
  `dver-d6631efd…`, `APPLIED`;
- violation: `typed_rule`, same `rule_id` and `decision_version_id`.

Result: dimensions 3, 4, 5 and the reject half of 6 are bound in one payload.
Dimensions 1, 2 and configuration are absent. Per ADR-029 §2 this is
**execution observed**, never relevant enforcement observed.

## 5. Findings

| ID | Finding | Kind |
|---|---|---|
| E-1 | **Relevant enforcement observed is achievable in v0.11.0 on exactly one path:** the agent-host hook, a `FORBID_NUMERIC_ABOVE` rule, a new-file `Write`, and a pinned host identity. `relevant_enforcement_per_rule` already implements the fail-closed per-rule check for it. Every literal-rule observation on every surface stops at execution observed. | scope fact |
| E-2 | CLI omits control/provenance and subject for literal-only checks. This is by design (G2-1 charter §5.2 rule 3, D3 proposal §1), not a defect, but it caps every literal CLI observation at dimension 1/2. | gap, needs owner ruling to change |
| E-3 | No surface records a per-rule **allow** for literal rules. An `APPLIED` rule with no violation is an inferred allow, which ADR-029 §2 ("attributable allow/reject result is recorded for that rule") does not accept. | gap, runtime change |
| E-4 | Configuration identity is carried only by the CI gate (memory blob). CLI and hook cannot detect the ADR-029 §2 "mismatched configuration" case on their own. | gap, runtime change |
| E-5 | **The production CI gate does not run v0.11.0.** Its evaluator is pinned to the CI1-approved build of `0b74d410` (2026-10-17). CI evidence on Core is evidence about that build, not about v0.11.0. Any v0.11.0 CI claim needs a re-pin under the CI1/R0 process. | scope fact |
| E-6 | The CI gate's applicability extract drops `decision_version_id`. It survives in the raw `stdout`, so nothing is lost, but the structured record cannot bind dimension 3 without re-parsing. | minor, adapter-only |
| E-7 | Section-less memory and the `--adr-dir` view still produce no canonical `decision_version_id`; `EvidenceIdentity.complete` is false and binding fails closed at dimension 3, as ADR-031 §10 requires. Confirmed by code; not re-probed here. | conforming |
| E-8 | CI1 and C4 already recorded literal CI evidence as "execution observed with near-complete binding" and did not claim relevance ([C4 closure §5](adr033-c4-closure-2026-10-26.md), [CI1 reconciliation row 5](ci1-production-readiness-reconciliation-2026-10-20.md)). This audit agrees and finds nothing in v0.11.0 that changes it. | consistent with prior records |

## 6. ADR-029 §6 scenarios at v0.11.0

| Scenario | Achievable today? | Where |
|---|---|---|
| A. Installed, validated, never run | yes | any surface |
| B. Ran, rule `EXCLUDED` | yes, recorded as execution observed | CLI, CI (hook: numeric only) |
| C. `APPLIED`, attributable allow/reject, provenance | **numeric only, hook only** | E-1 |
| D. CI control ran, coverage unprovable | yes, at execution observed | CI |
| E. Mismatched SHA / path / selector / rule version | detectable by the hook's common-binding check (numeric) and by `RuleEvaluation` equality; configuration mismatch detectable in CI only | E-4 |

## 7. What #579 needs to reconcile before approval

1. Its four-layer mapping should cite the v0.11.0 surfaces in §2, including
   the hook's existing relevance evaluator (E-1), which #579 predates.
2. The pinned one-decision/two-checkpoint fixture must state which evaluator
   build each checkpoint runs (E-5).
3. Literal-rule relevance cannot be reached without at least E-2, E-3 and E-4
   being resolved. Each is a runtime change and needs its own charter and
   owner ruling, as #579 already says for "any missing required runtime
   field".
4. Negative controls that need no runtime change and can run now against
   v0.11.0: missing decision identity (section-less memory, `--adr-dir`),
   mismatched `decision_version_id` / `rule_id`, `EXCLUDED` rule,
   `evaluation_complete: false`, stale subject digest (hook, numeric).
   Waiver evidence stays out until DG1B2 semantics land.

## 8. What this record does not claim

- No surface or path is newly claimed as "relevant enforcement observed".
- No production-readiness, coverage or fleet-evidence claim.
- No change to Audit tiers (ADR-026) or to Protected semantics.
- No authorization for any runtime, schema, gate re-pin or evidence-store
  work.
