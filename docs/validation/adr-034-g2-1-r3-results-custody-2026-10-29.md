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

**Unverified numeric detail:** the sealed numerical report includes a `per_gate` breakdown, but the case-free per-gate counts have not been independently extracted and verified for this draft. Do **not** infer that six failed cases imply exactly six failed gates. A custody-authorized reviewer must reconcile the unmodified `decision.verdict`, per-gate arithmetic and total 144/150 without publishing case identifiers, raw observations or concealed inputs.

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
7. Per-gate counts, escrow rationale wording, the verified reviewer termination and scorer restart time remain **unverified/open**. The available public evidence supports the overall FAIL but does not prove every custody/order requirement was met. The separate independent reviewer reported **BLOCKED** on PR #711, pending these facts and owner-authorized private evidence review.

## 5. Required independent results review before merge

- [ ] A post-scoring reviewer other than scorer B, primary structural reviewer and this record's drafter confirms independence and access to the retained *owner-authorized* evidence.
- [ ] Reviewer verifies the unchanged private report's `decision.verdict`, exact numerical gates and supporting arithmetic (including **case-free `per_gate` counts**), and separately reconciles the escrowed `structural_review` to the committed digest and the family's explanatory provenance.
- [ ] Reviewer confirms the reported custody-close record/digests, scope of retained evidence, late-recorded output sizes, and the stated access/cleanup limitations.
- [ ] Reviewer evaluates the missing §7 session-end/restart ordering evidence; absent evidence must remain an explicit limitation and must not be replaced by inferred timestamps.
- [ ] Reviewer confirms the final outcome is **FAIL** and that neither G1 nor the original blind corpus was reopened.
- [ ] Independent review, required GitHub checks, and merge complete.

**Disposition as of drafting:** R3 scoring and owner custody-close reported complete; final metadata-only results record **not yet independently reviewed or merged**. No scoring rerun is authorized.
