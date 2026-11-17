# ADR-034 D3: attribution of non-numeric refusals in hook evidence (proposal)

**Status:** PROPOSED, for review. It changes no code and no ADR. It
authorizes nothing until the owner rules on §6 and the review accepts it.

**Why.** The G2-1 revalidation R2 scored **FAIL**
([results record](../validation/adr-034-g2-1-r2-blind-scoring-results-2026-10-27.md),
#692 `591ef687`, custody close #693 `fb11bd00`). G6 failed 2 of 143
concealed cases, both class LIT.

**What the post-scoring diagnosis (D3) found** at the pinned implementation
`dbab816f`:

- **Enforcement was correct.** Each write was refused before mutation (exit
  2, strict), and the target stayed absent.
- **The evidence record did not say which rule refused it.** The record had
  cause `other_rule`, `rules: []` and `violations: []`, so no consumer can
  tell a literal-rule refusal apart from any other non-numeric refusal.

This proposal uses only the public diagnosis in #692 §5. It uses no
concealed-case content.

## 1. Mechanism (from #692 §5, re-checked against `main`)

1. **The checker omits the subject record. This is by design.**
   - `mneme/cli.py` adds `payload["subject"]` only when the input kind is
     `complete_source_file`, or when `CheckResult.has_numeric_rules` is
     true.
   - G2-1 charter §5.2 rule 3 requires this: `proposed_new_source` is
     reported only when a numeric rule applied.
   - So a routed `--proposed-new-file` check with no applicable numeric rule
     produces a trusted payload that has its literal violation but no
     subject.
2. **The hook gates violation identities on the subject.**
   `build_evidence_record` in `mneme/integrations/claude_code/hook.py`
   fills `rules` and `violations` only when
   `_subject_kind(payload) == "proposed_new_source"`. Without a subject,
   both stay `[]`, even though the trusted payload names the violated rule.
3. **The cause is coarse by design.** `_verdict_cause` returns `other_rule`
   for any block or deferral with no numeric violation. The record's only
   field that could attribute the refusal (`violations`) is the one step 2
   empties.

**Who is affected.** Any routed `Write` whose trusted check refuses or
defers because of a non-numeric rule, when no numeric rule is APPLIED to
the target. That covers:

- literal-only memories;
- memories whose numeric rules produced no applicability record for the
  target.

## 2. What must not change

- **Blocking.** Every hook outcome, exit code, stderr text and strict/warn
  or availability decision stays byte-identical (ADR-034 §7b.4, ADR-033).
- **The checker payload.** The `mneme check --json` payload, including the
  conditional subject record (charter §5.1 and §5.2 rules 1–3), stays
  byte-identical. Only the hook's evidence record changes.
- **Relevance.** `relevant_enforcement_per_rule`,
  `relevant_enforcement_observed` and `recorded_evaluation_complete` give
  identical results for every record. "Relevant enforcement observed" stays
  a claim about one applied numeric rule, under the ADR-029 bindings
  (§3).
- **Without the evidence log.** When `MNEME_HOOK_EVIDENCE_LOG` is unset, the
  hook writes nothing, as today (charter §6.3).

## 3. ADR-029 and ADR-034 review

**ADR-029 §2 (binding).**
- Evidence supports a claim only when it binds decision, rule, subject and
  an attributable outcome (row C of the ADR-029 table).
- A violation identity without a subject binding is **not** that evidence.
  It is the record's own account of which rule the checker reported.
- The proposal keeps that boundary:
  - `_common_bindings_hold` still requires a trusted `proposed_new_source`
    subject, its digest, the target and at least one numeric rule;
  - so a record with no subject still yields per-rule `{}` and event-level
    `false`, exactly as today.

**ADR-029 (attributable outcome).** Naming the violated rule makes the
refusal *attributable* in the record, which is what G6's cause check tests.
It does not make it *relevant enforcement* of a numeric rule. ADR-034 §7b.1
("no inheritance") already says that a refusal by an unrelated non-numeric
rule is never attributed to a numeric rule. `_disposition_attributable`
already requires cause `numeric_violation` and a numeric violation named
for the rule, so the extra identities cannot satisfy it.

**ADR-034 §7a (host-event binding) and charter §6.2.** These require, for
each applied numeric rule, the rule and outcome fields. They do not forbid
identities of other violated rules. The record already carries them
whenever a subject exists: for example, the 5 concealed LIT cases that
passed in R2 had `FORBID_LITERAL` in `violations` next to a numeric rule
(#692 §5). So D3 removes an inconsistency: the same refusal is reported
differently depending on whether an unrelated numeric rule also applied.

**ADR-034 §7b.4.** Blocking and the matcher do not change. The evidence
record's construction changes, so §7b.4's requirement applies by analogy:
the change needs its own review and regression tests (§5).

**Trust boundary.** Identities are copied only from a **trusted** payload,
meaning `assessment.payload is not None` (it passed the consumer trust
checks, charter §5). An untrusted, inconsistent or missing payload still
gives `violations: []`, as today.

## 4. Options

### Option A (recommended): emit violation identities from every trusted payload

In `build_evidence_record`:

- **Move it out of the subject gate.** The `violations` list (identities
  only: `rule_id`, `rule_type`) moves out of the `proposed_new_source`
  branch. It is filled from every trusted payload.
- **Keep the subject gate for the rest.** `subject` and `rules` stay inside
  the branch, unchanged.
- **Leave the other code alone.** `_verdict_cause`, the cause vocabulary,
  the checker and every validator are unchanged.

Effect:

- **On the two R2 failures:** the record would read cause `other_rule` with
  `violations` naming the literal rule's `rule_id` and
  `rule_type: FORBID_LITERAL`. Under the reviewed R2 harness mapping
  (AMB-R2-08, Q2), that maps to `literal_violation`.
- **On records that already have a subject:** they are unchanged.
- **On relevance:** relevance stays as it is.

Risk:

- the smallest change, in one function;
- no schema shape change, because the field already exists with this
  element shape;
- no change to enforcement.

### Option B: add a `literal_violation` disposition cause

This adds a cause to `_DISPOSITION_CAUSES`, and `_verdict_cause` returns it
when only `FORBID_LITERAL` violations are reported.

- **It widens a closed vocabulary.** That vocabulary is checked by
  `_common_bindings_hold`, and consumers pin it (the R2 harness and future
  harnesses).
- **It doesn't remove the inconsistency on its own.** The record would
  still not name *which* literal rule refused, so ADR-029's per-rule
  identity would still be missing. It would need Option A anyway.
- **Not recommended.**

### Option C: have the checker always emit a subject for `--proposed-new-file`

**Rejected.** It contradicts charter §5.2 rule 3, which reports the kind
only when a numeric rule applied. It changes the checker payload, and it
would let a non-numeric record pass the subject-kind checks that guard
numeric relevance.

## 5. Proposed tests (for the implementation PR, once authorized)

**Regression tests** in `tests/integrations/`, built with public synthetic
fixtures only:

1. **A literal-only refusal.** Memory with only `FORBID_LITERAL`, routed
   `Write` to a verified-absent `.py` target, strict mode. The hook refuses
   with exit 2, the target stays absent, and the record has:
   - cause `other_rule` and `checker.subject: null`;
   - `rules: []`;
   - `violations` that name exactly the literal rule's `rule_id`;
   - per-rule `{}`, event-level `false`, and `evaluation_complete`
     unchanged.
2. **A numeric rule that doesn't apply.** Memory with `FORBID_LITERAL` and a
   `FORBID_NUMERIC_ABOVE` rule that produces no applicability record for the
   target. The expected record is the same as test 1.
3. **A literal violation in warn mode.** The hook defers, and the record
   names the literal rule with cause `other_rule`.
4. **Untrusted or inconsistent payloads.** `violations` stays `[]`.
5. **No regression:**
   - every existing record with a `proposed_new_source` subject (the D1
     per-rule table rows, mixed literal and numeric) is byte-identical;
   - the existing `test_numeric_g2_per_rule_attribution.py` and
     `test_numeric_upper_bound_g2_hook.py` pass unchanged.
6. **Parity.** Hook stdout, stderr and exit codes are byte-identical before
   and after, both with the evidence log set and with it unset.
7. **The validators.** The relevance functions return identical values on
   records with and without the new identities, including a crafted record
   with a subject but no numeric rule. They must stay `{}` / `false`.

**Full suite.** The full canonical suite must pass. The R1 and R2 harnesses
(`benchmarks/adr034_g2_1/`, `benchmarks/adr034_g2_1_r2/`) are not modified.

## 6. Owner rulings requested

| ID | Question | Recommended |
|---|---|---|
| **D3-1** | Fix approach | **Option A:** violation identities from every trusted payload; `subject`, `rules`, the cause and the validators unchanged |
| **D3-2** | Evidence schema | **Keep `mneme.hook_evidence/v1`.** No field is added, removed or retyped. The change fills a field that today is empty in one routing case. A future harness that needs to tell pre-D3 records apart from post-D3 records can key on the implementation pin |
| **D3-3** | Where the rule is written | **A short ADR-034 amendment, §7c**, after this proposal is accepted. It states that the evidence record names every violated rule reported by a trusted payload, whether or not a subject is present, and that such identities never support relevance (§3) |
| **D3-4** | Effect on R2 | **None.** R2 stays FAIL, as recorded in #692. A G2-1 PASS needs R3: a new pre-registration that pins the D3 implementation, a new independent corpus and a new scorer. The pre-R3 key-custody control in #693 §9.5 must be met first |

## 7. Sequence after acceptance

Each step needs its own go-ahead.

1. **This proposal:** review, owner rulings D3-1 to D3-4, then merge.
2. **The ADR-034 §7c amendment.** A docs PR, if D3-3 is adopted.
3. **The implementation PR.** A new implementer session that did not author
   or score R1 or R2, with the §5 tests. It is reviewed against ADR-029,
   ADR-034 §7b/§7c and the parity requirement.
4. **R3.** Pre-registration, corpus, harness, completion record, scoring and
   results, following the R2 sequence.

## 8. Not authorized by this proposal

- Any change to `mneme/`, the harnesses, the corpus or labels, or the
  evidence schema.
- Any re-scoring or reinterpretation of R1 or R2.
- Any R3 work, or any change to the owner key.
- Any PASS, enforcement or production claim. **G2-1 stays FAIL.**

## Isolation statement

The orchestrating session wrote this proposal from:

- the public #692 diagnosis;
- the code on `main`;
- ADR-029, ADR-034 §7a/§7b, the G2-1 charter §5–§6.3, and the R2
  pre-registration.

It has never seen concealed case content, labels or provenance material.
