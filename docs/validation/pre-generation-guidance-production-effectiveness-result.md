# Pre-generation guidance production-effectiveness campaign result

Date completed: 2026-08-16

## Decision

The frozen campaign completed successfully, but it did **not** establish the frozen positive production-effectiveness claim.

Automatic pre-generation guidance showed directional gains in the controlled seven-task fixture: treatment produced two more governed compliant first attempts and two more functionally completed runs than baseline, with no increase in scope or operational failures. The compliance gain was below the frozen threshold, and the efficiency result is not claimable under the frozen protocol because four paired outcomes had no observed first-compliant attempt and the protocol did not predefine how to rank or impute them.

R6 remains `PERMANENT_FAIL_UNCHANGED`. This campaign does not retroactively alter R6.

## Execution integrity

| Item | Result |
|---|---:|
| Frozen execution lock SHA-256 | `AE01F8DEC22BB5777E7773211483544F6271F12AC394E9D5F1983D1B141FB9D5` |
| Scheduled / valid runs | 42 / 42 |
| Invalidations / reruns | 0 / 0 |
| Delivery / contamination / operational failures | 0 / 0 / 0 |
| Claude Code version | 2.1.202 |
| Resolved experimental model | `claude-sonnet-5` |
| Blinded packages | 42 |
| Unscoreable cases | 0 |
| Independent reviewers | 2 |
| Adjudicated reviewer disagreements | 15 dimensions across 15 trials |

All governed treatment runs contained the expected guidance before the first assistant event or edit. Baseline and control runs contained no injected policy context. The frozen ordering, paired structure, raw event evidence, and arm isolation were preserved.

The final independent read-only audit found zero open blockers. It rehashed all 637 entries in the raw artifact manifest, validated all 42 preserved runs, reconciled the blinding map and both reviewer sheets through adjudication, and reproduced all 42 machine run rows and 21 paired rows from raw evidence.

## Outcomes

| Frozen outcome | Baseline | Treatment | Difference | Disposition |
|---|---:|---:|---:|---|
| Governed first-attempt compliance | 11/15 | 13/15 | +2 | **FAIL**: frozen minimum was +3 |
| Functional completion, all runs | 13/21 | 15/21 | +2 | Guardrail passed |
| Governed scope expansions | 0/15 | 0/15 | 0 | Guardrail passed |
| Control scope expansions | 0/6 | 0/6 | 0 | Guardrail passed |
| Delivery failures | 0/21 | 0/21 | 0 | Guardrail passed |
| Operational failures | 0/21 | 0/21 | 0 | Guardrail passed |

All frozen guardrails passed. Because the primary compliance gate failed, the campaign cannot support the allowed positive incremental-effectiveness claim.

## Post-hoc diagnostic — not part of frozen scoring

This diagnostic was added after the frozen campaign was completed, scored, and independently audited. It does not recode any run, alter any denominator, change either claim gate, or modify the campaign's `FAIL` disposition.

Both remaining governed treatment failures were `typed-1` clarification-without-edit outcomes. In both runs:

- `DecisionRetriever` selected the applicable `ADR-INSTALL` decision;
- role-aware classification identified it as a direct decision;
- the expected guidance was injected before the first assistant event;
- delivery, ordering, isolation, and runtime integrity checks passed; and
- Claude explicitly observed the negative constraint and avoided the forbidden `legacy-client` literal.

The failure arose from insufficient positive decision content. The task requested the required client installation command, while the authoritative decision and fixture specified only that `legacy-client` was forbidden. They did not identify the supported replacement package, command, registry, or installation tool. With no authoritative positive choice available, two treatment runs safely requested clarification and made no edit. Under the frozen protocol, those no-attempt outcomes remain correctly scored as non-compliant and incomplete.

Treatment repetition 3 does not resolve that information gap. It wrote `pip install fixture-service-client`, but that replacement had no authoritative source in the fixture or decision store. Its nominal success therefore reflects an unsupported model guess that happened to satisfy the frozen negative-literal condition, not additional architectural guidance supplied by Mneme.

Post-hoc causal classification:

- primary cause: `INSUFFICIENT_POSITIVE_DECISION_CONTENT`;
- behavioral outcome in the two failures: `SAFE_CLARIFICATION_ABSTENTION`;
- frozen scoring outcome: `NO_ATTEMPT / NON-COMPLIANT`;
- retrieval, role classification, injection, timing, and negative-constraint uptake: passed;
- conflict detection and deterministic enforcement: not implicated.

No change to `DecisionRetriever`, `ConflictDetector`, role-aware formatting, injection, or deterministic enforcement is justified by this diagnosis. Mneme should continue to preserve the boundary `authoritative decision content → retrieval → role classification → injection → agent`; it must not manufacture a missing architectural choice.

For a future benchmark—not a change to this closed campaign—any governed task that expects implementation rather than abstention should have authoritative decision content containing enough positive, actionable information to perform the requested work. That is a fixture-validity requirement, not a new Mneme product feature.

## Paired work-to-compliance result

There were 15 governed task/repetition pairs:

- Both arms reached a compliant attempt in 11 pairs. Among those pairs, the median tool-call reduction was 25%, and treatment used fewer calls in 8 of 11.
- Treatment alone reached a compliant attempt in 2 pairs.
- Neither arm reached a compliant attempt in 2 pairs.

A failure-ranked sensitivity analysis favors treatment in 10 of 15 pairs, but this ranking was not defined by the frozen protocol. The frozen requirement was a median reduction of at least 20% and treatment using fewer calls in at least 9 of 15 pairs. Because four pairs contain null first-compliant counts, the efficiency gate is conservatively recorded as `NOT_CLAIMABLE_AS_FROZEN`; the 10/15 sensitivity result is not substituted for the frozen estimand.

## Deterministic enforcement

The deterministic gate remained active and independent. It rejected two first attempts, one in each arm and none in controls. Both rejected attempts were adjudicated architecturally compliant, so the campaign observed no reviewer-confirmed architectural violation caught by enforcement in this fixture.

## Supported conclusion

> Automatic pre-generation guidance showed directional gains in the controlled seven-task fixture (+2 governed compliant first attempts and +2 completed tasks), with no scope or operational penalty, but did not satisfy a frozen positive claim gate.

No effectiveness conclusion is supported across varied real-world repositories.

## Sealed evidence

- Machine-readable result: `docs/validation/artifacts/pre-generation-guidance-production-effectiveness-2026-08-14/production_effectiveness/production-effectiveness-result-20260816.json`  
  SHA-256: `8F71F2AD2C4E003782EDE0FC7B2583A71D49DF1E9A65941ABC20A19F02A32AEE`
- Raw artifact manifest: `docs/validation/artifacts/pre-generation-guidance-production-effectiveness-2026-08-14/production_effectiveness/artifact-manifest-20260816.json`  
  SHA-256: `B1733439C52573394E2C5324AFA8DBF6927A47B49C2761CD4761A6AE7CF3D746`
- Adjudicated blinded scores: `docs/validation/artifacts/pre-generation-guidance-production-effectiveness-2026-08-14/production_effectiveness/blinded_scores/adjudicated-scores-20260816.json`  
  SHA-256: `E5B9D1021D2ECA5CF8FC5492B88D0680F406034560A95DA5D88F363450EFB666`
- Frozen authorization: `docs/validation/pre-generation-guidance-production-effectiveness-authorization.md`  
  SHA-256: `008A5910F99BD6C85A6E8526C464C05EF5499CA28202F9FC1793A0E52AD9DBD0`
- Frozen execution lock: `docs/validation/pre-generation-guidance-production-effectiveness-execution-lock.json`  
  SHA-256: `AE01F8DEC22BB5777E7773211483544F6271F12AC394E9D5F1983D1B141FB9D5`
