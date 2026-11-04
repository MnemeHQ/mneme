# ADR-034 G2-1 R3: results and owner custody-close evidence

**Date:** 2026-10-29  
**Status:** DRAFT RESULTS RECORD. Independent post-scoring results review and merge are pending.  
**Outcome:** **R3 FAIL**. This is not a retrospective PASS for G1 or G2-1, and no rerun is authorized.  
**Evidence basis:** owner-reported terminal outputs and frozen metadata collected during the one authorized R3 scoring run. This draft does **not** assert that its author independently inspected private custody artifacts.

## 1. Frozen references and scoring identity

- Architecture: ADR-034; preregistration PR #699, amendment #701, freeze #703, handoff #704, merged harness PR #705 and live-host characterization #708.
- Accepted pre-scoring record: PR #710, `docs/validation/adr-034-g2-1-r3-pre-scoring-completion-2026-10-29.md`; frozen document SHA-256 `36389acb5d3b9429fe4824e5da33d6499c4f4818eb35eca4f0dfae8bf18e657a`.
- Harness commit: `086bbbf7556297f19f13cb2c5c2682687bcf41b4`.
- Candidate source: `1b0957af01df3ad036b12698663e167ae413885e`; scored wheel SHA-256 `f2ed395a6517006971f49baf169b957c10d0dfff4784ad36b3bb53eb9c024289`.
- Baseline source: `f8591102b2693379dabec9b5704862e194eca4ce`; wheel SHA-256 `b24a2f8328855d2e41e6ae43eb16c7ae488afcc5944713e66300bc061f132421`.
- Claude Code 2.1.312 executable SHA-256 `6099672ebe5dcb518b67d1d32dde1e3360bc6bee1dae7f8d28a69c49acc7c865`.
- Scorer B: Claude Code session `3121484e-a5ab-4aad-85ae-ccca9d92a8a1`. Primary structural reviewer: `a84f1b16-ff95-4f05-8ff6-b6ed3ad056ed`. The owner accepted a *shared-Windows-account* residual risk in the pre-scoring record; distinct sessions are **not** OS-enforced isolation.
- Owner-approved scoring GO: PR #710 comment `6500764755`. One authorized scoring execution began `2026-10-29T15:24:09.9380185Z` and ended `2026-10-29T15:29:42.9793670Z`. Harness exit code 0 means the scoring invocation completed, **not** that the benchmark passed.
- **Preflight history retained, not collapsed into a single PASS:** Scorer B's first §8 preflight at `2026-10-29T15:13:20Z`–`15:13:32Z` was **NO-GO** because owner release-integrity evidence was not yet documented. Owner addendum [#710 comment 6500655537](https://github.com/MnemeHQ/mneme/pull/710#issuecomment-6500655537) transcribed pre-existing ciphertext/plaintext-hash and post-extraction checks, without reclassifying the original preflight. Scorer B subsequently reported a §8 **PASS** at `2026-10-29T15:18:54Z`, `preflight.json` SHA-256 `d973cecea910c3ffee7a3aee283e921e36af0c1d98395ab136bb657dadd86f6c`. The owner cited these facts in the one-run GO [#710 comment 6500764755](https://github.com/MnemeHQ/mneme/pull/710#issuecomment-6500764755).
- A later pre-execution scorer preflight was reported as **26/26 PASS** at approximately `2026-10-29T15:23:48.75Z`. The private logs directory `preflight-logs-20261029T152342Z` was included in the owner-retained validation logs archive; the 15:18 `preflight.json` hash must **not** be assumed to identify the later check. An independent post-scoring reviewer has not yet inspected the preserved preflight files or corroborated the later 26/26 status.

### Post-unblind ordering evidence and gaps

- **Exposure start (owner-reported):** `2026-10-29T14:45:51.5205122Z`, at release of the protected plaintext corpus, as documented in [#710 comment 6500655537](https://github.com/MnemeHQ/mneme/pull/710#issuecomment-6500655537). The release inventory reported one manifest, 150 cases and zero reparse points; access was inherited read-only for `MnemeAgent`.
- **Primary structural review:** Reviewer session `a84f1b16-ff95-4f05-8ff6-b6ed3ad056ed` reported completion at `2026-10-29T14:55:43Z`. This is a reviewer-reported completion marker, **not** an independently verified session termination timestamp.
- **Escrow:** owner-reported canonical structural artifact commit `2026-10-29T15:06:25.7117312Z`, digest `aca7a09af4bec66a791aab2ef2c95beb4b22931f5aff8b3e57e155440ba7570c`; public metadata commitment [#710 comment 6500395460](https://github.com/MnemeHQ/mneme/pull/710#issuecomment-6500395460) posted before scoring.
- **Gap:** the primary reviewer's verified process/session end time and the precise time Scorer B restarted were **not established in the currently available public evidence**. A first scorer preflight at 15:13Z is not a substitute for a documented scorer restart time or proof of no concurrent sessions. The scorer and reviewer operated under the same Windows account. The independent post-scoring reviewer must assess §7 order evidence and retain this limitation, not backfill missing timestamps.

## 2. Frozen outcomes

| Assessment | Recorded outcome |
|---|---|
| Unmodified numeric `decision.verdict` | **FAIL** |
| Numerical cases | **144/150 passed; 6 failed** |
| Independent structural review: `AT_material_distinctness` | `present` |
| Independent structural review: `SC_lexical_families` | **`missing`** |
| Independent structural review: `public_vs_concealed_AT` | `present` |
| Owner-level final R3 outcome | **FAIL** |

The recorded pre-scoring structural assessment is `SC_lexical_families=missing`. Under the frozen criteria, **any required SC family missing is enough for an overall R3 FAIL**, irrespective of numeric scoring. The structural reviewer's narrative reported absent comprehension-binding, nested-function-binding and indirect-namespace-mutation families across the 14 SC cases. **Provenance boundary:** these three family names are reviewer-reported explanatory detail; the author has **not** inspected the owner-held hashed `r3-structural-v1.json` to determine whether they are actually present in its committed rationale. Do not represent that detail as independently authenticated by the escrow hash until a custody-authorized reviewer verifies it. The sealed structural determinations themselves remain unchanged. The numerical FAIL is separately retained as-is. Neither the corpus nor the implementation, harness, baseline, labels or rubric is changed here. The six case-level observations remain **private** and are not included in this record.

**Owner-extracted numeric gate summary (not yet independently verified):** The owner ran a read-only PowerShell check over the unchanged private report, verified its previously recorded SHA-256 `d9ab08946cb795a2dff08ffdb36138ca99f8399782bf9b0c3243563c6df4c566`, checked `scoring=concealed`, `decision.verdict=FAIL`, `decision.cases_scored=150`, `decision.cases_passed=144`, and confirmed the eight expected `per_gate` keys. This table copies **only** the resulting aggregate counts:

| Gate | Applicable denominator | Failed gate entries |
|---|---:|---:|
| G1 | 132 | 6 |
| G2 | 104 | 6 |
| G3 | 150 | 6 |
| G4 | 54 | 6 |
| G5 | 40 | 6 |
| G6 | 150 | 6 |
| G7 | 150 | 6 |
| G8 | 150 | 6 |

The owner script reported `NUMERICAL REPORT: VERIFIED` and `GATE COUNT EXTRACTION: PASS`. **Limitations:** This is an owner-run read of a private report, not a fresh independent inspection by the PR drafter or post-scoring reviewer. Each gate reported six failed entries; this does **not** prove they are the same six case IDs or 48 distinct failed cases. Gate denominators reflect *applicability* rather than 150 for every gate. The output deliberately contains no private case IDs, concealed inputs or raw observations. Independent verification of arithmetic and retained-report identity remains required before merge.

**Owner-side escrow verification (post-scoring; not an independent review):** The owner read the existing private `r3-structural-v1.json` without modifying it. The SHA-256 check matched `aca7a09af4bec66a791aab2ef2c95beb4b22931f5aff8b3e57e155440ba7570c`; the prior read-only size check passed for 2,377 bytes. A corrected PowerShell parse confirmed a root JSON array of exactly three records. The final owner-side validation reported `STRUCTURAL DETERMINATIONS: VERIFIED` after checking the exact four keys (`id`, `determination`, `opaque_case_refs`, `rationale`) and these ordered values:

| Structural record | Escrowed determination |
|---|---|
| `AT_material_distinctness` | `present` |
| `SC_lexical_families` | **`missing`** |
| `public_vs_concealed_AT` | `present` |

The first owner PowerShell parse attempted to count records with an expression that produced an unexpected count and correctly stopped; the corrected parser reported `ROOT_TYPE: System.Object[]`, `RECORD_COUNT: 3`, and `STRUCTURAL RECORD COUNT: PASS`, followed by the determinations check above. The hash and artifact remained unchanged. **Not verified by these public outputs:** private `rationale` contents, opaque-case-reference values, reserialization against the canonical-byte recipe, reviewer-before-scorer process separation, or an independent custodian's reproduction. The owner-reported check does not remove the need for independent authorized review.

Structural escrow JSON SHA-256: `aca7a09af4bec66a791aab2ef2c95beb4b22931f5aff8b3e57e155440ba7570c`. The owner escrowed it before numerical scoring. Original G1 result and correction history remain historical and unchanged; R3 does not replace them.

## 3. Owner custody: preserved artifacts

The following are *owner-reported*, hash-checked private vault artifacts, not repository attachments:

| Owner-retained artifact | Bytes when separately recorded | SHA-256 |
|---|---:|---|
| `r3-concealed-corpus-verified.tar` | not recorded in this draft | `3d468d2fc36cc32ad067f13035ccc44f9493ba7032fd41f069217486a88f61eb` |
| `r3-concealed-report.json` | **173559** | `d9ab08946cb795a2dff08ffdb36138ca99f8399782bf9b0c3243563c6df4c566` |
| `r3-observations.json` | **2827454** | `331d324f5123558b50cfe306eff0dd687daba25cdf3d40fcc02017be661e745f` |
| `r3-run-root-evidence-20261029.tar` | not recorded in this draft | `1c6b90e9ae1e9c246fb8b01ab2a2f4fd4fc306a873a6b8f4ce76d6251a78c687` |
| `r3-validation-logs-evidence-20261029.tar` | not recorded in this draft | `39dee1647986deeb868a2c269376bd53e4eb046e6ea67e2e258f1f5ed06484e4` |
| `r3-structural-v1.json` | 2377 canonical bytes | `aca7a09af4bec66a791aab2ef2c95beb4b22931f5aff8b3e57e155440ba7570c` |

Owner capture and integrity evidence:
- Report and observations secure vault capture: `2026-10-29T15:35:41.5865134Z`; staged results owner-locked: `15:38:03.1758476Z`.
- `MnemeAgent` corpus access grants revoked by owner: `15:42:46.1573391Z`.
- Run-root archive verified from Agent profile at `15:49:57.0400027Z`: 1,953 TAR entries, 6 symlinks, 0 hardlinks; owner vault copy verified `15:56:10.1882733Z`.
- Logs archive verified at `16:03:39.9605797Z`: 382 TAR entries, 1 symlink, 0 hardlinks; owner vault copy verified `16:06:41.7914569Z`.
- Temporary transfers were ACL-locked after verified custody: run archive `15:57:22.9024433Z`, logs archive `16:07:08.4465854Z`.
- **Four-artifact** custody preflight (corpus tar, report, observations, scoring-run archive): owner-reported PASS at `2026-10-29T15:58:27.3590365Z`. This check **did not include** the validation logs archive, whose copy was verified later at `16:06:41.7914569Z`.
- **Six-artifact** custody-close check: the later owner script checked the four preceding artifacts **plus** the validation logs archive and structural escrow before writing the private custody-close JSON. It reported PASS; the final record hash and completion timestamp were printed at `2026-10-29T16:10:05.2886993Z`. No claim is made that all six had passed at 15:58Z.
- Extracted corpus removed `15:59:42.5594528Z`; original scoring run root removed `16:08:46.3669049Z`, both by owner/scorer-reported terminal checks.

**Owner custody-close private record:** `r3-custody-close-20261029.json`, SHA-256 `48d95b392a8657413fe1f1ad4a3badc5601adbb9b1998180e7f28e2c959004e2`, created and checked `2026-10-29T16:10:05.2886993Z`. It retains event timestamps and known hashes. The two report/observations byte sizes were supplied **after** record creation, so are carried in **this** draft rather than silently editing the hashed private record. **Deviation from #710 §9 step 1:** available evidence does not establish that these file sizes were recorded *immediately after scoring* as required, even though hashes and later owner vault custody checks are recorded. Retain this timing limitation for independent review.

## 4. Limitations and no-overclaim boundary

1. The recorded terminal output establishes **owner-reported** custody and cleanup, not an independent forensic audit. The draft author cannot access the owner vault or rehash its contents directly.
2. The verified run-root archive and validation-log archive are retained privately. Some earlier smoke, test and review directories remain in the Agent workspace; this custody-close record does **not** claim global forensic erasure of all potentially derived materials, nor secure media wiping.
3. The restricted staging and temporary transfer directories remain ACL-locked. They are not asserted to have been deleted.
4. The accepted shared-account residual risk, wheel reproduction provenance limitation, and CRLF/raw-versus-normalized limitations from the pre-scoring record remain operative.
5. A successful harness process exit and `144/150` are **not** an R3 PASS. The separate structural failure is not collapsed into or erased by the numerical result.
6. No concealed cases, raw observations, detailed hidden responses, or owner private key appear in this repository record.
7. Per-gate counts have been **owner-extracted and published only as aggregates**, but independent confirmation is pending. Escrow rationale wording, the verified reviewer termination and scorer restart time also remain **unverified/open**. The available public evidence supports the overall FAIL but does not prove every custody/order requirement was met. An earlier separate independent reviewer reported **BLOCKED** on PR #711, pending owner-authorized private evidence review. A fresh independent review on 2026-11-04 (Claude Desktop session `402ef02b`, Claude Code transcript `1322e3a0-7c09-48d4-857e-c2d181e82279`; a different session but the same Windows account and model family as the §6 drafter) returned **REQUEST CHANGES**. Its four wording/provenance findings on §6 are addressed in this revision. Its private-evidence items remain open until the owner runs the read-only checks or records them as limitations.
8. **Additional disclosure (post-scoring, 2026-11-04 or shortly before; exact time not recorded).** During the D4.1 diagnosis (§6), the owner uploaded the **entire** private `r3-concealed-report.json` to an external ChatGPT assistant session, instead of only the intended grouped category output. The assistant reported that the upload matched SHA-256 `d9ab08946cb795a2dff08ffdb36138ca99f8399782bf9b0c3243563c6df4c566`. The report holds case identifiers and per-case gate metadata, but no concealed fixture source, ADR text or raw observations. This is a disclosure outside the owner vault. It does not change any frozen artifact or the R3 outcome, but it **disqualifies** the R3 corpus and its case identifiers as held-out material for any future validation. Besides case identifiers, the report carries per-case class, subclass and visibility, gate applicability and results, and notes that can embed fixture-derived rule IDs (for example `unknown_reason_set_differs:<rule_id>`). Whether the external chat and uploaded file were deleted is **not recorded**. The file should not be shared further.

## 5. Required independent results review before merge

- [ ] A post-scoring reviewer other than scorer B, primary structural reviewer and this record's drafter confirms independence and access to the retained *owner-authorized* evidence.
- [ ] Reviewer verifies the unchanged private report's `decision.verdict`, exact numerical gates and supporting arithmetic (including **case-free `per_gate` counts**), and separately reconciles the escrowed `structural_review` to the committed digest and the family's explanatory provenance.
- [ ] Reviewer confirms the reported custody-close record/digests, scope of retained evidence, late-recorded output sizes, and the stated access/cleanup limitations.
- [ ] Reviewer evaluates the missing §7 session-end/restart ordering evidence; absent evidence must remain an explicit limitation and must not be replaced by inferred timestamps.
- [ ] Reviewer confirms the final outcome is **FAIL** and that neither G1 nor the original blind corpus was reopened.
- [ ] Independent review, required GitHub checks, and merge complete.

**Disposition as of drafting:** R3 scoring and owner custody-close reported complete; final metadata-only results record **not yet independently reviewed or merged**. No scoring rerun is authorized.

## 6. Post-scoring diagnostic addendum (D4.1 and D4.2, 2026-11-04)

**Status:** diagnostic only. Nothing below changes the frozen corpus, labels, harness, oracle, report or the **R3 FAIL** outcome, and no rerun is requested. The conclusions use the frozen harness source at `086bbbf7`, the scored implementation source at `1b0957af`, the published aggregates in §2 and one category read of the private report, performed by an external assistant (§6.2, §4 item 8).

### 6.1 The six numerical failures are unscored cases (from code, given the owner-extracted aggregates)

In the frozen harness, G8 fails only in two ways:

- **Case-level error path** ([`gates.py` `score_case`](../../benchmarks/adr034_g2_1_r3/gates.py)). This covers observation and oracle errors, memory compile failure, guard failures and oracle conflicts. It sets **every** gate G1-G7 to `applies: True` with failure `case_not_scored`.
- **Scorer exception** (`score_case_safely`). This sets the same fan-out.

A third route, corpus-integrity failure, would mark all 150 cases. The report records `cases_passed=144` and exactly 6 G8 failures. Every G8 failure is a failed case, so the 6 G8 cases are the 6 failed cases.

This has two consequences:

- The identical count of 6 for every gate in §2, including G5 (denominator 40), is this fan-out. It is not 48 independent failures.
- No completed case recorded a behavioural gate mismatch.

Given the owner-extracted aggregates in §2, the §2 limitation "this does not prove they are the same six case IDs" is resolved by the code. Those aggregates are themselves not yet independently verified.

### 6.2 D4.1: G8 failure categories (external-assistant read, not owner-reproduced)

**Provenance.** The owner did **not** run the intended grouped, metadata-only read. Instead the owner uploaded the full report to an external ChatGPT assistant (§4 item 8). That assistant reported that the file matched the report hash (`d9ab0894…c4566`) and computed the grouping of `cases[].gates.G8.failures` for the failed concealed cases shown below. Neither the owner nor an independent reviewer has reproduced these counts with an owner-run, read-only command. Until one does, they are assistant-reported. The harness emits these categories without case content by design.

| G8 category | Cases |
|---|---:|
| `oracle_conflict:label_numeric_rule_id_not_derived` | 4 |
| `oracle_conflict:expected_cause` | 2 |
| **Total unscored** | **6** |

Each case carried a single category (also assistant-reported; owner check A verifies it via `FAILED_CASES_WITH_1_G8_ENTRIES = 6`). The custody consequence of how this read was shared is recorded in §4 item 8.

### 6.3 D4.2: classification against the frozen contract

**`label_numeric_rule_id_not_derived` (4): label-side.**

- **What fires it.** The conflict compares **labels with the oracle only**. It fires when a labelled numeric `rule_id` is absent from the numeric rule IDs the oracle derives from the fixture ADRs (`oracle.py` `_cross_check`). The implementation is not consulted.
- **The oracle's identity derivation matches the implementation's formula.** Both use the ADR-030 §7 formula: oracle `rule_id_of` vs `mneme/rule_identity.py`. Both apply the same ADR-034 §5 canonical value: oracle `_numeric_rule`/`canonical_max` vs `NumericContract.as_object`/`canonicalize_max`. One minor difference, keyword rejection in `numeric_rule.is_identifier`, would surface as a compile failure, not as this conflict.
- **The memory guard gives only partial corroboration.** Where a case compiles memory, `runner.memory_guard` compares all compiled rule IDs with all oracle-derived rule IDs. A difference would have added `compiled_rule_ids_differ_from_derived`, and each affected case carried a single category. For a fixture with no memory, though, the guard compares nothing. The guard also covers all rule types, while the conflict concerns numeric IDs only. It therefore does not establish what the implementation derives for these four cases.
- **Conclusion.** The frozen label names a numeric rule ID that the oracle does not derive from the case's own ADRs. This is a label-contract conflict. The most likely cause is an authoring-generator identity error.

**`expected_cause` (2): label or vocabulary side, most likely.**

- **The conflict is between the label's own fields.** Like every oracle conflict, it compares the oracle with the labels, not with the implementation. In a routed case, the oracle's `exp.cause` depends only on the derived violations and `evaluation_complete` (`oracle.py` `derive`). Both are checked against the labels (`evidence.violations` and `evidence.evaluation_complete` in `_cross_check`), and neither conflicted, because each case carried a single category. A conflict on the cause alone therefore means the label's `expected_cause`, mapped through `CAUSE_TO_RECORD`, disagrees with the label's own violation and completeness fields. In unrouted or unchecked cases, the cause is compared raw against `legacy_unrouted` or `not_checked`.
- **The oracle is not a full model of the hook's cause logic.** The scored hook (`mneme/integrations/claude_code/hook.py` at `1b0957af`) can return `fail_open` for an incomplete evaluation whose violation is not M-a actionable (`mixed_violation_actionable`). It also has `availability_refusal` and `not_run` causes. The oracle refuses (strict) or defers (warn) whenever a violation exists, and models none of those. This does not affect the classification above, but the oracle's cause model should not be described as identical to the implementation's.
- **The likely mechanism is a vocabulary mismatch.** The label may use a value outside the four-entry AMB-R2-08 map (`contract.CAUSE_TO_RECORD`), for example record vocabulary in place of corpus vocabulary. Alternatively, an unrouted or unchecked case may carry a routed cause.
- **Not verified.** The exact derived and labelled values sit in the private `r3-observations.json` conflict strings. Reading them is not required for the conclusion below.

### 6.4 What this does and does not establish

- **Establishes, given the §2 aggregates and the §6.2 categories:** 144 concealed cases completed with no behavioural gate mismatch. The six unscored cases arise from label/oracle contract conflicts.
- **No implementation defect is demonstrated.** Implementation behaviour on the six cases was observed but never compared with expectations, so neither a defect nor its absence is established for them.
- **Does not establish:** that the six cases would have passed, or that R3 passed. Unscored cases correctly fail closed. The structural `SC_lexical_families=missing` determination stands independently.

### 6.5 Process corrections for any future blind validation

These apply only to future validations. They are not retroactive.

1. **Pre-seal oracle dry run.** Before sealing, run the frozen oracle over the authored corpus and require zero oracle conflicts. This would have caught all six R3 conflicts without unblinding.
2. **Explicit SC family floors.** The R2 §4.2 family list carried only outcome floors. R3's one-per-family structural criterion was fixed after the corpus was frozen (corpus freeze `80b20ee0`, 2026-10-28; criteria in #710, 2026-10-29). Any future preregistration must state per-family coverage before authoring starts.
3. **Separate unscored from failed in reporting.** Keep the fail-closed verdict, but report G8 unscored cases separately instead of counting them as applicable failures of G1-G7.
