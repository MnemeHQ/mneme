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
- Scorer's preflight immediately before scoring: 26/26 checks reported PASS; retained for independent review.

## 2. Frozen outcomes

| Assessment | Recorded outcome |
|---|---|
| Unmodified numeric `decision.verdict` | **FAIL** |
| Numerical cases | **144/150 passed; 6 failed** |
| Independent structural review: `AT_material_distinctness` | `present` |
| Independent structural review: `SC_lexical_families` | **`missing`** |
| Independent structural review: `public_vs_concealed_AT` | `present` |
| Owner-level final R3 outcome | **FAIL** |

The structural reviewer found absent lexical families associated with comprehension binding, nested-function binding and indirect namespace mutation in the 14 SC cases. That structural failure is independently sufficient to fail the frozen R3 criteria, regardless of the numerical result. The numerical FAIL is also retained as-is. Neither the corpus nor the implementation, harness, baseline, labels or rubric is changed here. The six case-level observations remain **private** and are not included in this record.

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
- Final six-artifact custody check: PASS at `15:58:27.3590365Z` for the first four then retained logs and structural escrow were separately verified in the custody-close creation step at `16:10Z`.
- Extracted corpus removed `15:59:42.5594528Z`; original scoring run root removed `16:08:46.3669049Z`, both by owner/scorer-reported terminal checks.

**Owner custody-close private record:** `r3-custody-close-20261029.json`, SHA-256 `48d95b392a8657413fe1f1ad4a3badc5601adbb9b1998180e7f28e2c959004e2`, created and checked `2026-10-29T16:10:05.2886993Z`. It retains event timestamps and known hashes. The two report/observations byte sizes were supplied after record creation, so are carried in **this** draft rather than silently editing the hashed private record.

## 4. Limitations and no-overclaim boundary

1. The recorded terminal output establishes **owner-reported** custody and cleanup, not an independent forensic audit. The draft author cannot access the owner vault or rehash its contents directly.
2. The verified run-root archive and validation-log archive are retained privately. Some earlier smoke, test and review directories remain in the Agent workspace; this custody-close record does **not** claim global forensic erasure of all potentially derived materials, nor secure media wiping.
3. The restricted staging and temporary transfer directories remain ACL-locked. They are not asserted to have been deleted.
4. The accepted shared-account residual risk, wheel reproduction provenance limitation, and CRLF/raw-versus-normalized limitations from the pre-scoring record remain operative.
5. A successful harness process exit and `144/150` are **not** an R3 PASS. The separate structural failure is not collapsed into or erased by the numerical result.
6. No concealed cases, raw observations, detailed hidden responses, or owner private key appear in this repository record.

## 5. Required independent results review before merge

- [ ] A post-scoring reviewer other than scorer B, primary structural reviewer and this record's drafter confirms independence and access to the retained *owner-authorized* evidence.
- [ ] Reviewer verifies the unchanged private report's `decision.verdict`, exact numerical gates and supporting arithmetic, and separately reconciles the escrowed `structural_review` to the committed digest.
- [ ] Reviewer confirms the reported custody-close record/digests, scope of retained evidence, and the stated access/cleanup limitations.
- [ ] Reviewer confirms the final outcome is **FAIL** and that neither G1 nor the original blind corpus was reopened.
- [ ] Independent review, required GitHub checks, and merge complete.

**Disposition as of drafting:** R3 scoring and owner custody-close reported complete; final metadata-only results record **not yet independently reviewed or merged**. No scoring rerun is authorized.
