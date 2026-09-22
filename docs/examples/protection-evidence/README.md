# Protection and evidence semantics: two traceable cases

This packet is for external technical review of Mneme's current evidence
semantics. It is pinned to repository state
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

## Case 2 — Configured but not yet verified

### Repository finding

The live `.mneme/project_memory.json` contains **no** `test_evidence`
declaration. Consequently, the repository does not currently contain a
legitimate deployed decision/control instance that is declared and configured
in ADR-024's test-evidence channel but has not yet matched a relevant result.
Manufacturing one for this packet would cross the trust boundary ADR-024 is
designed to protect.

The closest real repository-backed state is the committed fixture in
[`tests/test_audit_test_evidence.py`](../../../tests/test_audit_test_evidence.py):
`dp-empty-input` declares
`tests/test_boundary.py::test_empty_input_rejected`, and
`test_declared_selector_alone_does_not_protect` proves that the passive audit
records the declaration but does not execute it or grant protection. This is a
test-created temporary git repository, not Mneme's live project memory and not
a standalone ADR in `docs/adr`; that limitation is material.

```text
Decision
↓
Rule
↓
Declared control
↓
No relevant match observed yet
↓
No verification evidence yet
```

### Trace of the closest fixture state

1. **Architectural decision.** The committed fixture decision is
   `dp-empty-input`: “Reject empty input before calling the model.” It represents
   a deterministic boundary from the Design Partner diagnostic described in
   ADR-024, but in this repository it exists only as test data.

2. **Rule.** The requirement is deterministic, but it has no installed Mneme
   typed rule. Its declared enforcement mechanism is a test selector rather
   than a `Rule` object.

3. **Configured control.** The fixture decision carries:

   ```json
   {
     "test_evidence": [
       {"selector": "tests/test_boundary.py::test_empty_input_rejected"}
     ]
   }
   ```

   The fixture creates the selector file and a real temporary git commit so
   passive validation can resolve the repository HEAD and file. This makes the
   declaration usable, not verified.

4. **Current evidence state.** [`verify_test_evidence`](../../../mneme/evidence.py)
   returns `declared`, and Audit renders
   `test:declared:tests/test_boundary.py::test_empty_input_rejected`. The test
   pins `protection_tier: "requires_modelling"`,
   `evidence_confidence: "none"`, `protected == 0`, and 0% current protection.

5. **Evidence absent.** There is no exact-SHA CI result matched to the exact
   selector, no authenticated CI claim, and no trusted execution attestation.
   Ordinary Audit executes only the passive `git rev-parse HEAD` check; an
   execution-sentinel test proves it does not invoke pytest or import the
   fixture's `conftest.py`.

6. **Why configuration is not protection.** The decision record asserts only
   that this selector is intended to enforce the decision. It does not prove
   the test ran, passed, ran at this SHA, tested the claimed boundary, or was
   reported by a producer the repository could not forge. ADR-024 therefore
   permits annotation but forbids an upgrade to `Protected`.

7. **Event needed to advance.** A supplied `mneme.test-evidence/v1` document
   with the exact HEAD SHA, exact uniquely declared selector, and exact
   `outcome: "passed"` would move the entry only to `matched_unverified`,
   rendered as `test:ci-claim:<selector>@<sha>`. The committed
   [`test_valid_ci_evidence_does_not_protect`](../../../tests/test_ci_test_evidence.py)
   pins that transition and confirms it still does not protect. An
   authenticated GitHub run/artifact can reach `authenticated_ci_claim`, also
   not protection. Moving to `verified` would require the cryptographically
   trusted Mneme-controlled producer described—and explicitly deferred—in
   ADR-025. No event available in the current implementation can do that.

The fixture's test body is deliberately minimal (`assert True`), so it proves
the evidence-state boundary, not that empty-input rejection is genuinely
implemented. That is another reason this fixture cannot be promoted as a real
deployed Case 2.

## Comparison

| Question | Case 1 — ADR-005 typed rule | Case 2 — closest ADR-024 fixture |
|---|---|---|
| Decision exists | Yes: accepted ADR-005 and live decision record | Yes as committed test data only; no repository ADR/live record |
| Rule declared | Yes: exact `FORBID_LITERAL` directive | Deterministic requirement plus declared selector; no typed `Rule` |
| Control configured | Yes: live canonical memory | Yes inside the temporary-repository fixture only |
| Relevant change observed | No ADR-029-grade stored observation; real changes and committed exact-input executions are independently traceable | No |
| Rule matched | Yes: forbidden input yields `APPLIED` plus exact literal match | No result carrier was supplied, so state remains `declared` |
| Evaluation executed | Yes: `check_prompt` asserts FAIL and PASS arms | No repository test execution; passive validation only |
| Verified evidence exists | Yes for configured/validated typed protection; **no** ADR-029-grade persisted event evidence | No; test-evidence `verified` is unreachable today |
| Appropriate audit interpretation | `Protected`; do not infer a particular production action was observed | `Requires modelling` with declared annotation; not Protected |

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
5. The live repository has no ADR-024 declaration, so a deployed
   “configured-but-unverified test control” example does not yet exist. The
   closest fixture proves the semantics but must not be described as project
   evidence.

## External review questions

1. Can you tell exactly why Case 1 earns its protection status?
2. Is it unmistakable that Case 2 has a configured control but lacks verification evidence?
3. Is any terminology likely to make a reader confuse configured protection with demonstrated protection?
