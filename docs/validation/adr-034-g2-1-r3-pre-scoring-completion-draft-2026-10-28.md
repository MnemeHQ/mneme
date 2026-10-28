# ADR-034 G2-1 R3: pre-scoring completion record (DRAFT / NO-GO)

**Date:** 2026-10-28  
**Status:** **DRAFT / NO-GO. NOT a completed evidence record.**  
**Scope:** ADR-034 G2-1 independent R3; frozen R3 pre-registration (#699), accepted AT-SI amendment (#701), held-out freeze (#703), scorer handoff (#704), scorer harness PR #705 and owner interpretation record.  
**Authority:** This draft does **not** authorize a merge, unblind, decrypt, read concealed material, run concealed scoring, change a case/label, or claim validation PASS. Owner and independent verifier must approve a fully evidenced successor before a distinct owner unblind decision.

## 0. State and evidence rules

The protocol requires a **separate, merged metadata-only pre-scoring completion record** before owner-controlled decryption (R3 pre-registration §5 step 7 and §6.1). The current record is a *draft evidence checklist*, **not** that completion.

**Verified GitHub merge state, updated after the prior draft:** PR #705 is **merged** into `main` by squash commit `086bbbf7556297f19f13cb2c5c2682687bcf41b4` (accepted PR head `26b1fa01336db909231b8d341feb182f1c35122d`). GitHub confirmed `merged=true`, and a repository-API comparison confirmed **17/17 changed Git blobs identical** at the reviewed head and merge commit. PR #707 remains **open/draft/unmerged**. **This is verified remote Git source identity only**, not the bytes of scorer B's Windows checkout, the complete tree pin, or the installed build provenance.

Evidence provenance terms:
- **FROZEN SOURCE:** values already committed in earlier accepted metadata-only freeze records; they are anchors, not new checks performed for this draft.
- **REPORTED:** scorer B / owner statements in the handoff, not independently inspected host artifacts.
- **OPEN:** primary evidence missing, stale, incomplete, or not separately attested. An OPEN row cannot silently become PASS.
- **VERIFIED FOR THIS RECORD:** only when the reviewer includes the actual command/tool, host identity, timestamp, digest, run path, result and independent corroboration. No runtime field below currently qualifies.

**Owner GO/NO-GO:** **NO-GO.** The following sections have open requirements. The harness merge is now known, but the completed successor must pin actual LF checkout bytes, environment/host/custody evidence and all required structural-review decisions before a distinct owner unblind authorization.

## 1. Contract, corpus and roles

| Required authority / anchor | Evidence now | Status |
|---|---|---|
| R3 preregistration, including R1/R2 inherited G1–G8, 128 concealed minimum over 14 classes | Merged R3 protocol #699 | FROZEN SOURCE |
| R3 AT-SI replacement; AT-S0/SI/SX/W0 floor 2 each | Accepted amendment #701 | FROZEN SOURCE |
| Frozen concealed plaintext deterministic tar SHA-256 | `3d468d2fc36cc32ad067f13035ccc44f9493ba7032fd41f069217486a88f61eb` | FROZEN SOURCE, not re-opened |
| Frozen owner-key ciphertext SHA-256 | `19846963bc53cb4e23a7d535ca1d6f970dfae9eabdf7364998e2809ede5e02d0` | FROZEN SOURCE, owner custody |
| Sealed count and distribution | 150 concealed cases, 14 classes, including eight AT (2 each subtype); counted only after authorized release | FROZEN SOURCE |
| Frozen public archive SHA-256 | `feee204134fb4dd339f6efcbde9053c7d1f37a880f74f5ec411eb4cf2f5020a4` | FROZEN SOURCE; renewed scorer archive/manifest verification OPEN |
| Public classes and fraction | 14 public smoke, one per class; public 14/164 = 8.54%, excluded from concealed gates and floors | FROZEN SOURCE |
| Scorer handoff authority | #704: owner-authorized public-only independent scorer B after targeted cleanup; shares Windows user with author A under conditional isolation | FROZEN SOURCE, not an unblind GO |
| Scorer B actual effective identity, config dir, session, host, workspace, integrity level, isolation statement | Independently pin exact current session; do not reuse author A or prior hidden corpora | OPEN |
| Owner-key isolation recheck in actual scoring session B | Synthetic-only probe, secret-key access denial, **reviewer session/worktree and prior public/synthetic probe inventory (see below)**, and independent custodian attestation; no hidden plaintext access | OPEN |

**Scorer B public/synthetic access-history inventory (REPORTED, pending host verification):** Scorer B reports extracting the **released public smoke tar**, not concealed material, from `r3-sealed-staging/public-smoke-NOT-RELEASED/` into its probe workspace. Its review tree `wt-review-705` and run folders `runs/review705*` contain public/synthetic inputs and probe artifacts. Before the custody recheck is signed, independently inventory the actual paths, contents/categories, ACL/accessibility and residual author artefacts; document whether each public/synthetic folder is retained or removed. Do **not** indiscriminately delete needed audit evidence or owner-held archives. Scorer B reports no access to concealed plaintext, ciphertext or owner author provenance; this is **REPORTED**, not independent custody verification.

**Scoring checkout Git configuration (REPORTED, custody inventory item):** Scorer B reports enabling `extensions.worktreeConfig=true` in its own clone to allow worktree-specific `core.autocrlf=false` for `wt-r3-merged-086bbbf7`. The recheck must inventory this configuration change as well as `wt-review-705`, `runs/review705*` and new LF-checkout probe outputs; it must not assume that worktree configuration is an access-control boundary.

**Strict custody:** The owner-only author provenance and earlier concealed corpora/results are never inputs to scorer B. Do not move concealed case files, ciphertext or keys into repository artifacts or this PR. On unexpected author material, **STOP/NO-GO**.

## 2. Harness and accepted tests

| Required pin | Candidate / reported source | Status |
|---|---|---|
| Scorer harness PR | #705 accepted at head `26b1fa01336db909231b8d341feb182f1c35122d`, **squash merged** on `main` as `086bbbf7556297f19f13cb2c5c2682687bcf41b4`; 17/17 changed Git blobs matched by connected repository inspection | VERIFIED GITHUB SOURCE; scoring machine pin OPEN |
| Merge commit, main tree, clean detached scoring checkout | Merged commit verified as `086bbbf7556297f19f13cb2c5c2682687bcf41b4`; scorer B **reports** tree prefix `bde6c9d6…` at both head and merge and detached LF worktree `wt-r3-merged-086bbbf7`. Record complete tree SHA, absolute checkout path, config, clean `git status` and platform readback from the scorer's evidence file | REMOTE MERGE VERIFIED; full tree/local pin OPEN |
| Every harness and README `.py/.md` byte SHA-256 | **Mandatory LF checkout**: the R3 report hashes actual on-disk `.py/.md` bytes. Scorer B reports ordinary Windows `core.autocrlf=true` converted all 16 pinned text files to CRLF, making their working hashes differ from committed blobs. A fresh detached worktree with `core.autocrlf=false` reportedly made all 16 match. Recompute and record complete on-disk SHA-256 for all 16 pinned files and compare with Git blobs; compare the 12 `harness.files_sha256` entries in the smoke report. Check the actual worktree's Git configuration and clean status. No newline normalization is permitted *during* hash verification | REPORTED LF fix; exact local bytes/table OPEN |
| Full relevant test SHA-256 | Record all `tests/test_adr034_g2_1_r3_*.py` and `scripts/run_test_battery.py` digest/pin; no test edits after the freeze | OPEN |
| Targeted independent tests | Scorer B reports a **new merged-LF-checkout run** at `086bbbf7`: `232 passed, 0 failed, 0 skipped`; earlier review at `6d0b64e9` and doc-only acceptance at `26b1fa01` remain historical | REPORTED; exact commands, host/run evidence and attached source log OPEN |
| Public smoke / synthetic operational test | Scorer B reports merged-LF-checkout public **14/14**, synthetic **10/10**, `NO_VERDICT_PUBLIC_SMOKE`; report's 12 harness file hashes match committed bytes and implementation version pin is `0.10.0`, matched | REPORTED; exact report hash/command/build binding OPEN |
| Attribution negative controls | Missing, empty, wrong, duplicate, non-string and extraneous rule IDs plus untrusted checker data; required by R3 §3 | REPORTED as reviewed; final exact-head test hashes/results OPEN |

A green PR battery is not the full main-only R3 harness battery. Record environment, commands, exit codes, counts and a clean worktree for the final source pin. **Scorer B's local evidence is reported to be in** `C:\Users\MnemeAgent\r3-work\r3-scorer-workspace\evidence-707-scorer-b-2026-10-28.md`; that Windows file is not attached to this PR or accessible to this reviewer. Do not infer its uninspected full SHA table or promote `REPORTED` to `VERIFIED FOR THIS RECORD` until the sanitized evidence is transferred and independently checked.

## 3. Pinned implementation and baseline

**Implementation (D3 accepted source):** R3 preregistration §2 lists commit `1b0957af01df3ad036b12698663e167ae413885e` and `mneme/` tree `656554d21ec1ef4ee474b6e6f69f681f0364a501`. It reports candidate wheel `mneme_hq-0.10.0-py3-none-any.whl`, SHA-256 `f2ed395a6517006971f49baf169b957c10d0dfff4784ad36b3bb53eb9c024289`, CPython 3.12.10, pip 25.0.1 and an installed freeze-file SHA-256 `253e5bc832f81786e3cac033724d09f1196889572cb87ad72445c125543a00c2`. These are **owner-reported preregistration candidates, not newly verified R3 scoring attestations**.

**Baseline:** Frozen pre-G2 parity source commit `f8591102b2693379dabec9b5704862e194eca4ce`, with previously accepted R2 `mneme/` Git tree `002fdddb254267d42a3810cfea669d75700372f2` (historical reference; must re-verify for R3). The merged [R2 completion record](adr-034-g2-1-r2-pre-scoring-completion-2026-10-27.md) documents a **historically independently reproduced** baseline wheel SHA-256 `3497b5dd83942ef5df06fe522acaaa7e6e2833759dfdd25daa8866f65dacd1b2`. Scorer B separately reports the R3 baseline wheel it built has SHA-256 `b24a2f8328855d2e41e6ae43eb16c7ae488afcc5944713e66300bc061f132421`. **These wheel hashes differ.** The R2 value is an eligible independent historical *comparison anchor*, not an automatic accepted R3 wheel pin. Establish whether the difference is only deterministic wheel metadata / newline policy by independently comparing payload and installed-file inventories against the same frozen source tree. R3's fresh baseline build, installed `RECORD` and dependency freeze remain OPEN.

**Baseline comparison addendum 1 (2026-10-28, scorer B REPORTED; independent addendum review OPEN):** The historical R2 wheel was owner-staged as the *single authorized artifact* at `C:/dev/mneme-r3-baseline-handoff/mneme_hq-0.10.0-py3-none-any.whl` and checked against full historical SHA-256 `3497b5dd83942ef5df06fe522acaaa7e6e2833759dfdd25daa8866f65dacd1b2`. Scorer B reports comparing that wheel read-only with its R3 baseline `b24a2f8328855d2e41e6ae43eb16c7ae488afcc5944713e66300bc061f132421` and the accepted pre-G2 tree `002fdddb254267d42a3810cfea669d75700372f2`: **111 corresponding Python files, 4 raw byte-identical, 107 CRLF/LF-only differences, 0 substantive source differences**; the historical R2 wheel's 111 files reportedly match the accepted tree raw byte-for-byte. Wheel metadata: `METADATA`, `WHEEL`, `entry_points.txt` and `top_level.txt` raw-identical; `LICENSE` differs only by newline; `RECORD` differs in 108 entries (107 sources plus license), while ZIP entry timestamps differ. No historical corpus, score, labels or harness access was authorized. **Evidence now preserved:** [Scorer B baseline comparison addendum transcription](adr-034-g2-1-r3-baseline-comparison-addendum-2026-10-28.md), reconstructed from the owner's uploaded transcript with the full comparison script and reported per-category evidence. Scorer B's **original Windows file** `evidence-707-scorer-b-addendum-1-baseline-2026-10-28.md` was reportedly 5,982 bytes, SHA-256 `4fe39830f67d13a15845c4b7705a6bb4fcefd87bfdd293c5968c1823285f4718`. The GitHub transcription has **different bytes**: it is not claimed to reproduce that checksum, and the two Windows wheels were not executed or read by this remote reviewer.

**Technical disposition, limited to source equivalence (ACCEPTED for candidate retention; no completed environment attestation):** Reviewed the full scorer B pasted comparison and its Python comparison script against R3 §6.1, R2 §2 and the merged historical R2 baseline completion record. Scorer B's hash-checked report shows **111 identical source-content files after line-ending normalization, 0 substantive differences**, and only the described packaging differences. R3 §6.1 requires a **newly built, independently pinned** baseline at `f8591102`; it does not require a byte-identical R2 archive. **Retain the existing scorer B R3 baseline wheel and `env/base`; do not replace or rebuild solely to reproduce `3497b5dd…`.** This accepts the **source-equivalence explanation**, not equality of the wheel archives or a claim that newline differences cannot affect every conceivable runtime observation. The reviewed comparison script reports (but does not fail closed on) Git tree and file-set equality; scorer B's asserted true values and its installation evidence still require independent host verification. The original addendum checksum cannot be independently confirmed from a reformatted paste. R3 source/installed `RECORD`/freeze attestation, environment reproducibility and G5 byte-level stdout/stderr/exit behavior remain **OPEN pending independent final verification**. Host §6.1, custody, scoring root/command, structural criteria and unblind also remain OPEN.

| Verification requirement for **both** installed environments | Status |
|---|---|
| Git commit/tree/source archive identity, source commit checked out cleanly | OPEN |
| Fresh R3 build command, deterministic conditions, full wheel SHA-256 | OPEN |
| Baseline reference and source-equivalence assessment | **ACCEPTED FOR CANDIDATE RETENTION** on scorer B's 111-file newline-only comparison and independently documented historical R2 source/tree/wheel; original Windows addendum hash and full local execution not reproduced by this reviewer. Remaining environment/RECORD/freeze checks OPEN |
| Package `RECORD` and **complete installed-file inventory** vs wheel | OPEN |
| `mneme/` installed source inventory vs accepted pinned tree | OPEN |
| Exact Python executable, version and interpreter source; implementation and baseline in independent venvs | OPEN |
| `pip freeze --all` full text and SHA-256 in the **actual scoring venvs** | OPEN |
| Dependency integrity, `pip check`, executable runtime manifest and clean checkout | OPEN |
| Implementation `mneme` package version equals independently frozen `0.10.0`; reported hook evidence version also checked separately | OPEN (version-string equality alone insufficient) |

**Scorer B implementation observation (REPORTED only):** its pinned D3 wheel reportedly matches the R3 §2 digest `f2ed395a…`. A new build at `1b0957af…` reportedly produced a different wheel hash but identical payload for **111/111 package files**, with wheel metadata differing. Its installed package matches the wheel's `RECORD`, the installed dependency-freeze SHA matches the preregistered `253e5bc8…`, and `pip check` is clean. Scorer B also reports **107/111 installed source files differ bytewise from Git sources only in CRLF/LF line endings**, and all match after newline conversion. This normalized equality is useful explanatory evidence but **is not raw byte equality** and does not replace exact wheel/installed-file attestation. The baseline installation similarly is reported internally consistent but independently unreferenced. The detailed file-by-file evidence is not yet available here.

Every full SHA must be recorded and verified before changing status to complete. Do not borrow R2 build hashes as evidence of R3 reproduction.

## 4. Claude Code scoring host and live-host test

R3 §6.1 requires a **new, merged §8.B live-host characterization** using the R3 implementation because Claude Code 2.1.312 is different from the previously characterized 2.1.310 (#646). A scorer's local install digest or a synthetic replay is not live-host proof.

| Required evidence | Status |
|---|---|
| Exact scorer machine and Windows user, Claude Code executable path and `claude --version` | OPEN; scorer B reports Claude Code 2.1.312 at `C:\\Users\\MnemeAgent\\.local\\bin\\claude.exe` (its own observation; actual scoring-host characterization not yet independently accepted) |
| Executable SHA-256 (full 64 hex), shim/PATH origin, timestamp, signed provenance if available | OPEN; scorer B reports its locally observed executable SHA-256 `6099672ebe5dcb518b67d1d32dde1e3360bc6bee1dae7f8d28a69c49acc7c865` (**REPORTED**, not the independently accepted host pin) |
| Separately executed, documented live host §8.B tests with R3 implementation; report/PR merged before unblind | OPEN |
| Exact `--host-version` and `--host-sha256` pinned to *verified* host | OPEN |
| Provenance binding and ability to reproduce the required pinned host throughout scoring | OPEN |

The host re-pin and execution authorization are **owner tasks outside scorer B's self-reported observations**.

## 5. Filesystem, public archive and runtime readiness

| Requirement | Evidence and action | Status |
|---|---|---|
| File + directory symlink capability on the actual scoring host and run directory | Scorer B reports file + directory link support under its **development** run folder. Repeat at the exact final scorer run root, after pinning its path/ACLs, and capture probe output, OS identity and exit status | REPORTED development probe; final run-root OPEN |
| First-pass L pre-mutation evidence | Scorer B approved synthetic nine-shape symlink classification; confirm exact merged harness code and tests | REPORTED, merged pin OPEN |
| Separate public tar exact hash + its internal manifest and 14-class inventory | Scorer B reports hash match against #703 and merged verifier acceptance of the tar's internal manifest and **14 cases / 14 distinct classes**; independently check its command/output and exact digest from the evidence file | REPORTED; transcript/attestation OPEN |
| Concealed ciphertext and owner decryption custody | Owner alone checks frozen ciphertext hash and private-key access when authorizing unblind; scorer B may not pre-read it | FROZEN SOURCE, scoring-time owner check OPEN |
| Concealed plaintext archive `MANIFEST.sha256`, safe entries, 150-case count | Verify at **authorized** decryption/score boundary only; **never** require pre-unblind scorer access | PENDING AFTER UNBLIND |
| Two equivalent scorer passes; G7 stability; G1–G8 metadata-only report and optional owner-retained raw observations | Required future execution, NOT completed | PENDING AFTER UNBLIND |
| Score command pinned to merged harness + implementations + actual host | Insert reviewed exact command with real paths and SHA values; never guess | OPEN |
| Evidence retention, access, post-score encrypted evidence and custody cleanup | Separate owner-approved close procedure | OPEN |

## 6. Structural determination procedure: **freeze before unblind, execute before gate scoring**

R3's accepted pre-unblind interpretation record adds required structural determinations. The numeric `decision.verdict` is unchanged; `structural_review.final_claim_ready` remains **false** until the owner independently closes these requirements. **A gate-only PASS must never be published as a full R3 PASS while any structural determination is open.**

**Proposed owner disposition, requires explicit pre-unblind acceptance:**
- `present`: reviewed against frozen structural criteria; eligible for a complete claim only if every other applicable gate and completion requirement passes.
- `missing`: frozen required coverage demonstrably absent; **R3 final validation FAIL**, even if `decision.verdict` is PASS.
- `undetermined`: evidence does not justify either finding; **R3 INCOMPLETE, treated as validation FAIL**, never a narrowed PASS (analogous to R1's symlink-capability `INCOMPLETE`). No retroactive review into `present` after scoring or knowledge of gate failures. This is an owner-level completion disposition, **not** a new `gates.decide` verdict.
- If numerical gates independently FAIL, the R3 validation remains FAIL regardless of structural status. No attempt to change hidden labels, corpus or implementation is permitted.

**Independence and timing:**
1. **Before any unblind:** owner names the structural reviewer and backup, accepts this exact checklist and status mapping, pins the accepted harness and reviewer session. Scorer B can serve as reviewer only if independent from author A and D3 implementation. A second reviewer is optional. Record evidence method before reviewing cases.
2. **After separate owner-authorized unblind, before *any* G1–G8 scoring execution or per-case results are shown to the reviewer:** structural reviewer reads only the authorized, frozen decrypted `case.json` fixtures (including the separate released public AT). **Author labels are embedded in each `case.json` and may be visible; visibility is unavoidable and is not, by itself, a protocol breach after authorized unblind.** Independently verify structural presence from fixture source and declaration rather than accepting an author's label as proof. **Generated checker output, hook output, G1–G8 gate results, scoring report and diagnosis must not be consulted.** No Mneme runs, implementation tuning, re-labelling or corpus mutation during review.
3. Record exactly one metadata-only determination for each pending identifier using the **canonical JSON artifact and hash recipe below**. The owner/custodian commits or escrows the canonical artifact privately and records its SHA-256 **before** running the G1–G8 scoring command. The reviewer must not consult gate results in preparing or revising the determinations.
4. Scorer then runs the frozen two passes. The final metadata-only results record reproduces the unmodified `decision.verdict`, `structural_review` (including `final_claim_ready` and three determinations), hash of the sealed structural assessment, and the owner-level final outcome separately. No manual override of G1–G8 or post-hoc reclassification.

**Canonical structural-determination artifact (proposed pre-unblind format):**

Write a **JSON array with exactly three objects**, one per ID, ordered lexicographically by `id`:
`AT_material_distinctness`, `SC_lexical_families`, `public_vs_concealed_AT`.
Each object has **exactly** the four fields below:

- `id`: one of the three frozen identifiers;
- `determination`: `present`, `missing` or `undetermined`;
- `opaque_case_refs`: array of unique, lexicographically sorted **opaque case IDs** only (no paths, rule values or code); empty only when nothing can be evidenced;
- `rationale`: a short metadata-only assessment, containing no source excerpt, filesystem path, ADR text, hidden label, selector or numeric threshold from concealed cases.

Serialization and commitment: construct the three records, sort by `id`, then serialize the array using Python `json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")`. Hash **exactly those UTF-8 bytes**, with **no BOM and no trailing newline**, using SHA-256. The artifact must not include gate outputs or implementation observations. The owner privately escrows the exact artifact and publishes **only its SHA-256, schema/serialization version `r3-structural-v1`, reviewer identity, timestamp and custody attestation** before any gate scoring. A scorer/verifier can reproduce the digest from those bytes. This hash is a commitment to the pre-score judgment, not a determination that all three are present.

**Exact criteria, frozen before opening concealed case files:**

| Pending identifier | Structural evidence for `present`; otherwise `missing` or `undetermined` |
|---|---|
| `SC_lexical_families` | **At least one concealed SC case demonstrating each named R2 §4.2 mechanism**, without inventing a numeric per-family gate floor: (1) same-named method `def` in a class body with call sites **inside AND outside that class**; (2) parameter binding; (3) local binding; (4) comprehension binding; (5) nested-function binding; (6) enclosing-scope resolution; (7) `global`/`nonlocal`; (8) indirect namespace mutation; (9) a namespace-related string used as plain data. Parameter/local/comprehension/nested are **four separate presence checks**, but may occur in the same concealed case if independently evidenced. Distinct classes/outcome quotas remain only those already frozen in R2 §4.2. |
| `AT_material_distinctness` | Assess each concealed AT subclass pair for real material difference in applied literal/numeric rule meaning or source behavior, not merely ADR ID, filename, selector-directory string or path renames. Reconfirm AT-SI's two independently derived literal identities **and** different include scopes, AT-SX's separate exclude-selector mechanism, and the AT-W0 literal-only vs excluded-numeric variants. Any materiality ambiguity is `undetermined`, not assumed `present`. |
| `public_vs_concealed_AT` | Compare the separate frozen public AT case and **every** concealed AT case for distinct proposed source, ADR meaning/source and literal-rule identity, consistent with R3 §3. Merely a changed name/path/ID or SHA is not sufficient to assert independent semantics; record opaque references only. |

**Owner acceptance of operational precision: OPEN.** These proposed criteria must be accepted or corrected **before unblind** and must not retroactively become new numerical case floors. After scoring, `missing` and `undetermined` may not be converted into `present` to improve a PASS claim.

## 7. Exact pre-unblind completion gates (all OPEN unless independently evidenced)

- [x] PR #705 squash merge **verified on GitHub**: commit `086bbbf7556297f19f13cb2c5c2682687bcf41b4`, 17/17 changed Git blobs match reviewed head. This does not verify any local working-tree bytes.
- [ ] LF-only scoring checkout attested: final directory uses `core.autocrlf=false` with actual on-disk byte hashes equal to Git blobs and complete harness/test files pinned.
- [ ] Exact complete independent scorer B tests and synthetic attribution negatives rechecked at that merged commit; no unknown omissions.
- [ ] D3 source/wheel/installed-file manifest/dependency freeze independently attested.
- [x] Baseline **source-equivalence comparison reviewed and candidate retained**: distinct R2/R3 wheel hashes recorded and newline-only source difference explained. This check is **not** the complete environment attestation.
- [ ] Baseline source/tree, newly built wheel, installed-file `RECORD`, dependency freeze and actual scoring environment **independently attested**. Scorer B's observations and reproduced source-content equivalence do not, alone, complete this item.
- [ ] R3 Claude Code 2.1.312 **live-host** characterization independently executed and **merged**; exact executable digest and host pin verified.
- [ ] Actual scorer account/session/key-isolation and no-author-material custody recheck approved by owner.
- [ ] Symlink capability demonstrated in actual scoring environment and run root.
- [ ] Frozen public tar/manifest and verified distinct-class inventory checked at final scoring checkout.
- [ ] Structural criteria, reviewer independence, order, outcome mapping and pre-gate hash/commit rule explicitly accepted by owner.
- [ ] Reviewed exact scoring command, environment paths, preservation strategy and stop conditions pinned.
- [ ] This completed metadata-only record independently reviewed and merged.
- [ ] Separate, later **owner unblind GO** explicitly issued.

## 8. Current disposition

**NO-GO for unblind and concealed scoring.** No R3 blind scoring was performed by drafting this file. None of the OPEN attestations is claimed complete. Scorer B's harness acceptance concerns public/synthetic tests only. A future completed version must replace each OPEN with independently reviewable evidence, preserving both the original source anchor and actual observation.

**G2-1 remains FAIL. R3 remains sealed. No retrospective PASS.**
