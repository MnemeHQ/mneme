# Protection and evidence semantics: one traceable case and one capability gap

This packet is for external technical review of Mneme's current evidence
semantics. It contains one live traceable case and one finding that the
requested comparison case cannot yet be represented truthfully. It is pinned
to repository state
[`6a82ba47`](https://github.com/MnemeHQ/mneme/commit/6a82ba47) and uses only
artifacts already present in this repository or its git history.

The governing documents are
[ADR-024](../../adr/ADR-024-declared-test-evidence-ingestion.md),
[ADR-025](../../adr/ADR-025-trusted-test-execution-attestation.md),
[ADR-026](../../adr/ADR-026-audit-tier-semantics-and-mneme-potential.md), and
[ADR-029](../../adr/ADR-029-enforcement-evidence-binding-semantics.md).
[ADR-030](../../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md)
is later but still proposed; it specifies future stable decision-version and
rule identity and explicitly makes no enforcement-semantics change.

Two uses of **verified** must be kept separate:

- For a typed rule, Audit uses `evidence_confidence: "verified"` to mean that
  configured deterministic enforcement is present. ADR-026 makes an installed
  `FORBID_LITERAL` rule authoritative evidence of protection, and ADR-029 says
  runtime observation is not required for that `Protected` tier.
- For ADR-024 test evidence, `verified` means a trusted producer proved that
  the exact declared selector passed at the exact repository SHA. That state
  has no producer today: ADR-025 deliberately defers it.

Likewise, **matched** has two precise contexts. A runtime rule is relevant when
its applicability trace is `APPLIED`; a literal occurrence then creates a
`Violation`. An ADR-024 carrier is `matched_unverified` only when its SHA,
selector, and `passed` outcome exactly match a unique declaration. Neither kind
of match should be inferred from similarity, coverage, or the mere existence of
a control.

## Case 1 — Protected and verified

### Selected example

**ADR-005: Brand vs Package Namespace Enforcement**, specifically the rule
forbidding the bare distribution command `pip install ` + `mneme` (concatenate
the two fragments with no separator).

This document uses either that explicit concatenation or the JSON-equivalent
spelling `pip install mnem\u0065` when it must name the forbidden value. That
keeps the packet compliant with the live rule it is documenting without adding
an exemption or obscuring the value; the direct ADR and memory links show the
canonical unescaped source.

This is the cleanest live example because it is the only decision in the
repository's canonical memory that currently carries a typed deterministic
rule. The audit therefore reports exactly one Protected decision: ADR-005.
The selection is backed by the real ADR, live memory, implementation, committed
regression tests, and the commits that introduced and adopted the rule.

At this packet's verification point, `mneme protect status ADR-005` reports the
rule installed and the decision `protected`; `mneme check` on this document
reports the rule `APPLIED`, an aggregate `PASS`, and no violations. Mneme can
therefore prove that ADR-005 is configured, applicable to this artifact, and
currently passes. Those current facts do not prove a historical observation
about any earlier production change.

```text
Decision
↓
Rule
↓
Declared control
↓
Relevant change
↓
Matched
↓
Evaluation
↓
Verified evidence
↓
Protected
```

This is a repository-backed **review trace**, not one persisted event chain.
The repository proves each transition needed to validate the configured
control, but it does not store an ADR-029 observation binding a production
subject, control configuration, rule identity, and outcome in one record.
In this diagram, `Matched` means the exact forbidden literal matched and a
`Violation` was created; `APPLIED` alone means only that the rule was applicable.
`Verified evidence` means the Audit label for configured-and-validated typed
protection, not verified observation of the production change.

### Trace

1. **Architectural decision.** [ADR-005](../../adr/ADR-005-brand-vs-package-namespace-enforcement.md)
   distinguishes the `mneme-hq` distribution from the `mneme` import/CLI
   namespace. The ADR records the concrete supply-chain risk: the bare `mneme`
   PyPI name belongs to an unrelated project.

2. **Enforceable rule derived from it.** Under the ADR's `Constraints`
   section, the authored directive is exactly
   `FORBID_LITERAL: pip install ` + `mneme` (concatenated). The typed-literal
   contract comes from
   [ADR-019](../../adr/ADR-019-typed-literal-rule-contract.md), while
   [ADR-020](../../adr/ADR-020-explicit-path-applicability-for-typed-rules.md)
   defines whether a rule is `APPLIED`, `EXCLUDED`, or `UNKNOWN` for an
   artifact.

3. **Configured/active control.** The live
   [`.mneme/project_memory.json`](../../../.mneme/project_memory.json)
   record for `ADR-005` contains:

   ```json
   {"type": "FORBID_LITERAL", "value": "pip install mnem\u0065"}
   ```

   No `include_paths` or `exclude_paths` are present, so ADR-020 gives the rule
   global artifact applicability except for the exact automatic exemptions for
   its declaring ADR and canonical memory file. The isolated memory change
   [adopted the rule in commit `77f86b5d`](https://github.com/MnemeHQ/mneme/commit/77f86b5d2856eacd1d9b4e2dff3114784fe5711b).

4. **Real relevant changes.** [PR #246 / commit `a919b56a`](https://github.com/MnemeHQ/mneme/commit/a919b56ae64017957c3739b8ee007ce990cfc7f6)
   corrected four real violations in
   [`docs/qa-glossary.md`](../../qa-glossary.md), added the ADR-specific
   [`check_install_command.py`](../../../scripts/check_install_command.py)
   gate and
   [CI workflow](../../../.github/workflows/install-command-check.yml), and
   recorded a passing gate result plus a case the gate caught during the PR.
   Later, the real quickstart change
   [PR #327 / commit `cb815280`](https://github.com/MnemeHQ/mneme/commit/cb815280a43614e254071600a93acb364d75a1f8)
   added the correct distribution command.

   The typed-enforcement implementation change
   [commit `c8f29144`](https://github.com/MnemeHQ/mneme/commit/c8f2914425684834531cb67e874e534b51d0bcf2)
   also added a committed end-to-end regression in
   [`tests/test_adr_import_e2e.py`](../../../tests/test_adr_import_e2e.py).
   That regression evaluates the exact proposed content `pip install ` +
   `mneme` and `pip install mneme-hq`.

   The regression imports the repository's synthetic `ADR-201` fixture, not
   live ADR-005. It proves the typed rule mechanics only. The real ADR-005 to
   live-control binding comes separately from ADR-005 and the canonical-memory
   adoption commit; this packet does not relabel the fixture as ADR-005.

   The durable repository evidence is the committed test and commit history,
   not a claim that Mneme has persisted a production event for PR #327. No such
   subject-bound observation record exists.

5. **Why the rule matched.** For the forbidden test input, the global rule is
   `APPLIED`, and [`literal_in_text`](../../../mneme/rule_matcher.py) finds the
   exact case-sensitive literal with the required token boundary. For the
   correct `pip install mneme-hq` input, applicability is still `APPLIED`, but
   the literal does not match because `mneme` continues into `-hq`. The focused
   assertions are also pinned in
   [`tests/test_enforcer.py`](../../../tests/test_enforcer.py).

6. **Evaluator/control that ran.** PR #246's ADR-specific script scanned
   tracked repository files and failed on a matching install instruction; its
   committed regression suite is
   [`tests/test_check_install_command.py`](../../../tests/test_check_install_command.py).
   In the canonical Mneme path, [`check_prompt`](../../../mneme/enforcer.py)
   evaluates every typed rule, records a per-rule `RuleEvaluation`, and creates
   a typed `Violation` only when applicability is `APPLIED` and the literal
   matcher succeeds. [`mneme check --json`](../../../mneme/cli.py) serializes
   this result as `mneme.check/v1`; its JSON contract is pinned in
   [`tests/test_check_json.py`](../../../tests/test_check_json.py).

7. **Pass/fail decision.** The end-to-end regression asserts:

   - `pip install ` + `mneme` → `FAIL`;
   - `pip install mneme-hq` → `PASS`.

   The forbidden arm records a typed violation whose decision/rule binding is
   pinned by the focused enforcer and JSON tests. The compliant arm proves the
   longer, correct package name is not a false positive.

8. **Evidence recorded by Mneme.** At evaluation time, `EnforcementResult`
   records the aggregate verdict plus the per-rule applicability trace; on a
   forbidden match it also records the decision id, rule type/value, trigger,
   and input path in `Violation`. The committed tests are the durable evidence
   that those records are produced with the asserted outcomes.

   Audit separately reads the installed typed rule and returns
   `protection_tier: "protected"`,
   `evidence_confidence: "verified"`, and
   `mneme_guardrail: "FORBID_LITERAL: pip install mnem\u0065"` through
   [`assess_protection`](../../../mneme/enforcer.py). For this channel,
   `evidence_sources` is currently empty; Audit does not attach a persisted
   runtime event to the classification.

9. **Why `Protected` is allowed.** ADR-026 says installed deterministic
   enforcement outranks prose and is authoritative evidence of protection.
   ADR-029 preserves that rule as **configured and validated protection** and
   explicitly says runtime observation is never required for the Audit tier.
   Therefore ADR-005 earns `Protected` because the live decision is linked to
   an installed typed rule whose deterministic behavior is mechanically pinned,
   not because a particular production change has been stored as observed.

### What this case proves—and does not prove

It proves the decision→rule linkage, current configuration, deterministic
matching behavior, FAIL/PASS outcomes, and current Audit classification. It
does **not** prove an ADR-029-grade historical observation for a particular
production edit. The current trace lacks durable subject identity,
configuration identity, stable rule identity, and control provenance bound to
one stored event. ADR-029 deliberately deferred that carrier; proposed ADR-030
defines future stable identity slots but does not implement observation
persistence.

Calling this case “verified” is therefore correct only in the current Audit
sense: the configured deterministic protection is mechanically verified. It
must not be presented as a verified claim that PR #327, or any other production
change, was observed by this exact control.

## Case 2 — A live configured-but-never-exercised control is not currently representable

### Product capability finding

Michael's requested distinction is valid, but it is not a distinction the
current product can yet report. There is **no genuine Case 2 in the current
repository**. The canonical
[`.mneme/project_memory.json`](../../../.mneme/project_memory.json) contains one
typed rule and no `test_evidence` declarations. That one rule belongs to
ADR-005 and is already Case 1. The active workflows contain other repository
checks, but Audit does not bind them to a second live decision/control pair.

More fundamentally, current Mneme cannot prove the requested negative fact.
ADR-029 defines configured-and-validated protection, execution observed, and
relevant enforcement observed as independent dimensions, but explicitly ships
no persistence, evidence store, decision log, public evidence schema, or CLI
representation for the latter two dimensions. The runtime
[`RuleEvaluation`](../../../mneme/path_selectors.py),
[`Violation`](../../../mneme/enforcer.py), and `EnforcementResult` objects exist
only for the current evaluation.

The requested lifecycle is therefore a target state, not a state instantiated
by a live repository control:

```text
Decision
↓
Rule
↓
Declared control
↓
No relevant match observed yet   ← cannot currently be proved or reported
↓
No verification evidence yet     ← absence is not represented as history
```

### Why Audit cannot supply Case 2

The exact per-decision `mneme.audit/v1` representation contains only `id`,
decision metadata, `intent`, `protection_tier`, `mneme_guardrail`,
`evidence_confidence`, and `evidence_sources`; see
[`_audit_payload`](../../../mneme/cli.py). It has no activation time, execution
count, last-evaluated subject, relevant-match count, or observation-completeness
field.

For a typed rule, [`assess_protection`](../../../mneme/enforcer.py) immediately
returns `protection_tier: "protected"` and
`evidence_confidence: "verified"` from the installed rule, with
`evidence_sources: []`. That empty list does **not** mean “never exercised.” It
means this protection channel does not attach an observation source. Likewise,
a current passing repository scan proves only that no violation was found in
that scan; it says nothing about whether the control governed an earlier
relevant change.

Consequently, these histories are indistinguishable in current Audit output:

- a rule was activated and no relevant change ever entered its scope;
- the control evaluated relevant allowed changes, but no history was retained;
- the control rejected relevant changes, but no history was retained;
- the control never ran in an integration, even though the rule was configured.

### Why adding a small live rule would still be misleading

Adding another decision and typed rule could create another real configured
control, but it would not establish “never exercised.” It would also change
repository enforcement behavior and require a real architectural decision and
explicit activation; those artifacts cannot be invented merely to complete an
example. Even immediately after activation, Mneme would record configured
protection, not a trustworthy historical negative. Activation's mechanical
validation executions are intentionally different from a real relevant change.

No new control is added by this packet.

### Minimum product capability needed

The minimum truthful representation is an append-only or otherwise durable
enforcement-observation carrier implementing ADR-029's six bindings for every
recorded evaluation:

1. control and provenance, including Mneme version;
2. exact subject/action identity;
3. canonical decision identity and version;
4. stable rule/control identity and configuration;
5. applicability (`APPLIED`, `EXCLUDED`, or `UNKNOWN`);
6. attributable allow/reject outcome.

The report would also need an explicit observation-completeness boundary—for
example, the activation/configuration identity and time from which all relevant
enforcement surfaces are known to report. Without that completeness guarantee,
zero stored relevant observations still means only “none recorded,” not “none
occurred.” Audit must expose these dimensions separately from the existing
`Protected` tier and fail closed when any binding or coverage guarantee is
missing.

This belongs primarily under accepted
[ADR-029](../../adr/ADR-029-enforcement-evidence-binding-semantics.md), which
already defines the runtime-observation semantics and defers their carrier,
schema, and persistence. Proposed
[ADR-030](../../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md)
must land first or alongside it to supply stable decision-version and rule
identity. It does **not** belong under ADR-025 unless the control is specifically
test evidence requiring a trusted execution-attestation producer; ADR-025 does
not solve general runtime observation or completeness. A new ADR is appropriate
for the concrete observation schema, retention/completeness contract, and Audit
projection because ADR-029 deliberately left those choices open.

### Implementation implication

Durable observation work should follow the canonical persistence and stable
identity work in ADR-030. Once those identities exist, a separately reviewed
implementation can add the ADR-029 observation carrier, persistence, and Audit
projection, followed by an explicit completeness contract for which active
enforcement surfaces have reported since a configuration became effective.
ADR-025 remains separate: it is needed only when test evidence must cross the
trusted execution-attestation boundary. This packet defines no new ADR and
changes no runtime behavior.

### Mechanics appendix — synthetic ADR-024 fixture, not Case 2

The committed fixture in
[`tests/test_audit_test_evidence.py`](../../../tests/test_audit_test_evidence.py)
remains useful only for explaining the test-evidence state machine. Its
`dp-empty-input` test record declares
`tests/test_boundary.py::test_empty_input_rejected`. Passive Audit returns
`declared`, renders
`test:declared:tests/test_boundary.py::test_empty_input_rejected`, and does not
execute pytest or grant protection.

An exact-SHA, exact-selector, `passed` result would reach only
`matched_unverified`; the committed
[`test_valid_ci_evidence_does_not_protect`](../../../tests/test_ci_test_evidence.py)
pins that boundary. An authenticated GitHub claim still cannot reach
`verified`; ADR-025 defers the trusted producer required for that transition.

This fixture is synthetic test data in a temporary repository, has a minimal
`assert True` body, and is neither a live ADR nor an active repository control.
It must not be shown to Michael as the requested Case 2.

## Comparison

| Question | Case 1 — ADR-005 typed rule | Requested Case 2 — live unexercised control |
|---|---|---|
| Decision exists | Yes: accepted ADR-005 and live decision record | No qualifying second live decision/control pair |
| Rule declared | Yes: exact `FORBID_LITERAL` directive | No qualifying live rule |
| Control configured | Yes: live canonical memory | No qualifying second control |
| Relevant change observed | No ADR-029-grade stored observation; real changes and committed exact-input executions are independently traceable | Cannot be established; current Mneme retains no observation history |
| Rule matched | Yes in committed mechanics tests; `APPLIED` plus exact literal match creates a `Violation` | Cannot be established or negated historically |
| Evaluation executed | Yes in committed tests and the ADR-specific gate history; not persisted as one ADR-029-bound event | Cannot be established or negated historically |
| Verified evidence exists | Yes for configured/validated typed protection; **no** ADR-029-grade persisted event evidence | No representable live instance |
| Appropriate audit interpretation | `Protected`; do not infer a particular production action was observed | Do not manufacture a Case 2; report the observation/persistence gap |

## Semantic ambiguities exposed

1. `evidence_confidence: "verified"` is overloaded across channels. For a
   typed rule it means installed deterministic enforcement; in ADR-024 it names
   a stronger trusted execution-attestation state that is currently
   unreachable.
2. `Protected` is an Audit tier about configured/validated protection, not a
   statement that a real workflow has exercised the rule. ADR-029 makes that
   intentional, but readers can easily assume observation unless the report
   says otherwise.
3. `RuleEvaluation.outcome == APPLIED` records applicability, not whether the
   forbidden literal matched. The literal match is represented by a separate
   `Violation`; the overall PASS/FAIL verdict is aggregate.
4. The current runtime trace is useful but is not a durable ADR-029 evidence
   record. It lacks the complete, stable binding needed to assert relevant
   enforcement observation after the run.
5. The live repository has no second typed rule or ADR-024 declaration, and
   even a newly activated control could not truthfully be classified as “never
   exercised” without observation persistence plus a completeness boundary.
6. The activation workflow uses `verified` for a fresh canonical re-assessment
   of installed protection. That verifies configuration, not historical
   enforcement observation, despite phrases such as “independently observes
   real enforcement evidence” in activation documentation and code comments.

## External review questions

1. Can you tell exactly why Case 1 earns its protection status?
2. Is it unmistakable why a truthful Case 2 cannot yet be produced from current evidence?
3. Is any terminology likely to make a reader confuse configured protection with demonstrated protection?
