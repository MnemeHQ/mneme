# ADR-034 G2-1 R3: pre-scoring completion record (DRAFT / NO-GO)

**Date:** 2026-10-28  
**Status:** **DRAFT / NO-GO. NOT a completed evidence record.**  
**Scope:** ADR-034 G2-1 independent R3; frozen R3 pre-registration (#699), accepted AT-SI amendment (#701), held-out freeze (#703), scorer handoff (#704), scorer harness PR #705 and owner interpretation record.  
**Authority:** This draft does **not** authorize a merge, unblind, decrypt, read concealed material, run concealed scoring, change a case/label, or claim validation PASS. Owner and independent verifier must approve a fully evidenced successor before a distinct owner unblind decision.

## 0. State and evidence rules

The protocol requires a **separate, merged metadata-only pre-scoring completion record** before owner-controlled decryption (R3 pre-registration §5 step 7 and §6.1). The current record is a *draft evidence checklist*, **not** that completion.

**Verified GitHub merge state, updated after the prior draft:** PR #705 is **merged** into `main` by squash commit `086bbbf7556297f19f13cb2c5c2682687bcf41b4` (accepted PR head `26b1fa01336db909231b8d341feb182f1c35122d`). GitHub confirmed `merged=true`, and a repository-API comparison confirmed **17/17 changed Git blobs identical** at the reviewed head and merge commit. PR #708's separately characterized Claude Code 2.1.312 host record was squash merged at `2cab939077f9f413ba3b33b41ce9249bf54cd3ce` after independent document-consistency review, with a disclosed limitation that raw run artifacts were not independently opened. PR #707 remains **open/draft/unmerged**. **This is verified remote Git source identity only**, not the bytes of scorer B's Windows checkout, the complete tree pin, or the installed build provenance.

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

**Scorer B public/synthetic access-history inventory (REPORTED, pending host verification):** Scorer B reports extracting the public smoke tar under the owner-authorized public-only handoff (#704), not concealed material, from `r3-sealed-staging/public-smoke-NOT-RELEASED/` into its probe workspace. The directory name `NOT-RELEASED` conflicts with the reported authorization to use this public material; the custody reviewer must verify the exact owner permission, actual contents and access history rather than inferring authority from the folder name. Its review tree `wt-review-705` and run folders `runs/review705*` contain public/synthetic inputs and probe artifacts. Before the custody recheck is signed, independently inventory the actual paths, contents/categories, ACL/accessibility and residual author artefacts; document whether each public/synthetic folder is retained or removed. Do **not** indiscriminately delete needed audit evidence or owner-held archives. Scorer B reports no access to concealed plaintext, ciphertext or owner author provenance; this is **REPORTED**, not independent custody verification.

**Scoring checkout Git configuration (REPORTED, custody inventory item):** Scorer B reports enabling `extensions.worktreeConfig=true` in its own clone to allow worktree-specific `core.autocrlf=false` for `wt-r3-merged-086bbbf7`. The recheck must inventory this configuration change as well as `wt-review-705`, `runs/review705*` and new LF-checkout probe outputs; it must not assume that worktree configuration is an access-control boundary.

**Strict custody:** The owner-only author provenance and earlier concealed corpora/results are never inputs to scorer B. Do not move concealed case files, ciphertext or keys into repository artifacts or this PR. On unexpected author material, **STOP/NO-GO**.

## 2. Harness and accepted tests

| Required pin | Candidate / reported source | Status |
|---|---|---|
| Scorer harness PR | #705 accepted at head `26b1fa01336db909231b8d341feb182f1c35122d`, **squash merged** on `main` as `086bbbf7556297f19f13cb2c5c2682687bcf41b4`; 17/17 changed Git blobs matched by connected repository inspection | VERIFIED GITHUB SOURCE; scoring machine pin OPEN |
| Merge commit, main tree, clean detached scoring checkout | At 2026-10-29T00:04Z an independent reviewer reports read-only verification of detached HEAD `086bbbf7556297f19f13cb2c5c2682687bcf41b4`, root tree `40c73b87e72eb89c2aba3a725b874a93f5f866d2`, harness tree `bde6c9d6ab464dc5a0576b7ba2d37b91490f3f46`, worktree `C:/Users/MnemeAgent/r3-work/r3-scorer-workspace/wt-r3-merged-086bbbf7`, and clean `git status`; all 6,853 tracked files matched Git blobs raw. Only ignored Python caches were present. Recheck immediately before scoring | INDEPENDENT REVIEWER VERIFIED AT TIMESTAMP; final scoring-time recheck OPEN |
| Every harness and README `.py/.md` byte SHA-256 | Independent reviewer reports 16/16 on-disk SHA-256 matches against independently fetched committed Git blobs at `086bbbf7`, with no CR bytes in these 16 files, on 2026-10-29T00:04Z. Effective **worktree** `core.autocrlf=false` from `.git/worktrees/wt-r3-merged-086bbbf7/config.worktree`; local/system values remain `true`. No newline normalization was used in the hash comparison. Full 16-hash reviewer output is not attached to this PR. The separate smoke report's 12 `harness.files_sha256` values have **not** been independently checked | REVIEWER-VERIFIED CHECKOUT AT TIMESTAMP; smoke binding and scoring-time recheck OPEN |
| Full relevant test SHA-256 | Record all `tests/test_adr034_g2_1_r3_*.py` and `scripts/run_test_battery.py` digest/pin; no test edits after the freeze | OPEN |
| Targeted independent tests | Scorer B reports a **new merged-LF-checkout run** at `086bbbf7`: `232 passed, 0 failed, 0 skipped`; earlier review at `6d0b64e9` and doc-only acceptance at `26b1fa01` remain historical | REPORTED; exact commands, host/run evidence and attached source log OPEN |
| Public smoke / synthetic operational test | Scorer B reports merged-LF-checkout public **14/14**, synthetic **10/10**, `NO_VERDICT_PUBLIC_SMOKE`; report's 12 harness file hashes match committed bytes and implementation version pin is `0.10.0`, matched | REPORTED; exact report hash/command/build binding OPEN |
| Attribution negative controls | Missing, empty, wrong, duplicate, non-string and extraneous rule IDs plus untrusted checker data; required by R3 §3 | REPORTED as reviewed; final exact-head test hashes/results OPEN |

A green PR battery is not the full main-only R3 harness battery. Record environment, commands, exit codes, counts and a clean worktree for the final source pin. **Scorer B's local evidence is reported to be in** `C:\Users\MnemeAgent\r3-work\r3-scorer-workspace\evidence-707-scorer-b-2026-10-28.md`; that Windows file is not attached to this PR or accessible to this reviewer. Do not infer its uninspected full SHA table or promote `REPORTED` to `VERIFIED FOR THIS RECORD` until the sanitized evidence is transferred and independently checked.

## 3. Pinned implementation and baseline

**Implementation (D3 accepted source):** R3 preregistration §2 lists commit `1b0957af01df3ad036b12698663e167ae413885e` and `mneme/` tree `656554d21ec1ef4ee474b6e6f69f681f0364a501`. It reports candidate wheel `mneme_hq-0.10.0-py3-none-any.whl`, SHA-256 `f2ed395a6517006971f49baf169b957c10d0dfff4784ad36b3bb53eb9c024289`, CPython 3.12.10, pip 25.0.1 and an installed freeze-file SHA-256 `253e5bc832f81786e3cac033724d09f1196889572cb87ad72445c125543a00c2`. These are **owner-reported preregistration candidates, not newly verified R3 scoring attestations**.

**Baseline:** Frozen pre-G2 parity source commit `f8591102b2693379dabec9b5704862e194eca4ce`, with previously accepted R2 `mneme/` Git tree `002fdddb254267d42a3810cfea669d75700372f2` (historical reference; must re-verify for R3). The merged [R2 completion record](adr-034-g2-1-r2-pre-scoring-completion-2026-10-27.md) documents a **historically independently reproduced** baseline wheel SHA-256 `3497b5dd83942ef5df06fe522acaaa7e6e2833759dfdd25daa8866f65dacd1b2`. Scorer B separately reports the R3 baseline wheel it built has SHA-256 `b24a2f8328855d2e41e6ae43eb16c7ae488afcc5944713e66300bc061f132421`. **These wheel hashes differ.** The R2 value is an eligible independent historical *comparison anchor*, not an automatic accepted R3 wheel pin. Establish whether the difference is only deterministic wheel metadata / newline policy by independently comparing payload and installed-file inventories against the same frozen source tree. R3's fresh baseline build, installed `RECORD` and dependency freeze remain OPEN.

**Baseline comparison addendum 1 (2026-10-28, scorer B REPORTED; independent addendum review OPEN):** The historical R2 wheel was owner-staged as the *single authorized artifact* at `C:/dev/mneme-r3-baseline-handoff/mneme_hq-0.10.0-py3-none-any.whl` and checked against full historical SHA-256 `3497b5dd83942ef5df06fe522acaaa7e6e2833759dfdd25daa8866f65dacd1b2`. Scorer B reports comparing that wheel read-only with its R3 baseline `b24a2f8328855d2e41e6ae43eb16c7ae488afcc5944713e66300bc061f132421` and the accepted pre-G2 tree `002fdddb254267d42a3810cfea669d75700372f2`: **111 corresponding Python files, 4 raw byte-identical, 107 CRLF/LF-only differences, 0 substantive source differences**; the historical R2 wheel's 111 files reportedly match the accepted tree raw byte-for-byte. Wheel metadata: `METADATA`, `WHEEL`, `entry_points.txt` and `top_level.txt` raw-identical; `LICENSE` differs only by newline; `RECORD` differs in 108 entries (107 sources plus license), while ZIP entry timestamps differ. No historical corpus, score, labels or harness access was authorized. **Evidence now preserved:** [Scorer B baseline comparison addendum transcription](adr-034-g2-1-r3-baseline-comparison-addendum-2026-10-28.md), reconstructed from the owner's uploaded transcript with the full comparison script and reported per-category evidence. Scorer B's **original Windows file** `evidence-707-scorer-b-addendum-1-baseline-2026-10-28.md` was reportedly 5,982 bytes, SHA-256 `4fe39830f67d13a15845c4b7705a6bb4fcefd87bfdd293c5968c1823285f4718`. The GitHub transcription has **different bytes**: it is not claimed to reproduce that checksum, and the two Windows wheels were not executed or read by this remote reviewer.

**Technical disposition, limited to source equivalence (ACCEPTED for candidate retention; no completed environment attestation):** Reviewed the full scorer B pasted comparison and its Python comparison script against R3 §6.1, R2 §2 and the merged historical R2 baseline completion record. Scorer B's hash-checked report shows **111 identical source-content files after line-ending normalization, 0 substantive differences**, and only the described packaging differences. R3 §6.1 requires a **newly built, independently pinned** baseline at `f8591102`; it does not require a byte-identical R2 archive. **Retain the existing scorer B R3 baseline wheel and `env/base`; do not replace or rebuild solely to reproduce `3497b5dd…`.** This accepts the **source-equivalence explanation**, not equality of the wheel archives or a claim that newline differences cannot affect every conceivable runtime observation. The reviewed comparison script reports (but does not fail closed on) Git tree and file-set equality; scorer B's asserted true values and its installation evidence still require independent host verification. The original addendum checksum cannot be independently confirmed from a reformatted paste. R3 source/installed `RECORD`/freeze attestation, environment reproducibility and G5 byte-level stdout/stderr/exit behavior remain **OPEN pending independent final verification**. Host **characterization record** §6.1 is now satisfied by merged #708; scoring-host runtime matching, custody, scoring root/command, structural criteria and unblind remain OPEN.

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

**Scorer B implementation observation (REPORTED only):** its pinned D3 wheel reportedly matches the R3 §2 digest `f2ed395a…`. A new build at `1b0957af…` reportedly produced a different wheel hash but identical payload for **111/111 package files**, with wheel metadata differing. Its installed package matches the wheel's `RECORD`, the installed dependency-freeze SHA matches the preregistered `253e5bc8…`, and `pip check` is clean. Scorer B also reports **107/111 installed source files differ bytewise from the committed LF Git blobs only in CRLF/LF line endings**, and all match after newline conversion. Read-only comparison of the frozen wheel and Git archive (§6.1 below) explains the different reference bases: the wheel's CRLF entries are consistent with a Windows checkout under system `core.autocrlf=true`, but **who built the wheel and the actual build environment remain OPEN**. Normalized equality versus Git blobs is not raw byte equality and does not replace exact wheel/installed-file attestation. The baseline installation similarly is reported internally consistent but independently unreferenced. The detailed file-by-file evidence is not yet available here.

Every full SHA must be recorded and verified before changing status to complete. Do not borrow R2 build hashes as evidence of R3 reproduction.

## 4. Claude Code scoring host and live-host test

R3 §6.1 required a **new, merged §8.B live-host characterization** using the R3 implementation because Claude Code 2.1.312 differs from the previously characterized 2.1.310 (#646). This requirement is satisfied at the **record/host-characterization level** by PR #708, squash merged as `2cab939077f9f413ba3b33b41ce9249bf54cd3ce`. The recorded host identity is Claude Code `2.1.312`, SHA-256 `6099672ebe5dcb518b67d1d32dde1e3360bc6bee1dae7f8d28a69c49acc7c865`, measured on ten public-fixture runs. The independent reviewer checked the executable and document consistency but did **not** independently inspect the raw ten-run envelopes/evidence; the owner accepted the record for merge. A scorer's current installation identity, command-line binding and reproducible pinned scoring environment remain separate OPEN gates.

| Required evidence | Status |
|---|---|
| Exact scorer machine and Windows user, Claude Code executable path and `claude --version` | OPEN for actual scorer B run environment; scorer B reports Claude Code 2.1.312 at `C:\\Users\\MnemeAgent\\.local\\bin\\claude.exe`. PR #708 established the separate characterization host identity, not scorer B's final runtime pin. |
| Executable SHA-256 (full 64 hex), shim/PATH origin, timestamp, signed provenance if available | Characterization pin VERIFIED in merged #708: `6099672ebe5dcb518b67d1d32dde1e3360bc6bee1dae7f8d28a69c49acc7c865`. Scorer B's exact current executable and invocation path remain OPEN for independent scoring-environment verification. |
| Separately executed, documented live host §8.B tests with R3 implementation; report/PR merged before unblind | **CLOSED for the §6.1 record prerequisite**: ten public-fixture runs documented and PR #708 independently reviewed and squash merged. The review did not open raw run artifacts. This is not a concealed-scoring result. |
| Exact `--host-version` and `--host-sha256` pinned to *verified* host | OPEN |
| Provenance binding and ability to reproduce the required pinned host throughout scoring | OPEN |

The host characterization pin is accepted by the owner through #708's merge. Scorer B's **actual scoring-host matching pin**, custody verification and separate owner unblind authorization remain OPEN; they cannot be inferred solely from #708 or scorer B's reports.

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

### 6.1 Scorer B sanitized-review packet (2026-10-28): reported evidence, not completion

A separate Claude reviewer **reports** reading and hashing only the 136-line Windows file `C:\Users\MnemeAgent\r3-work\r3-scorer-workspace\evidence-707-scorer-b-2026-10-28.md` and classifying its content as **CLEAN**: no concealed case material or labels, credentials, keys or author transcripts observed. It says it did not inspect any other scorer/staging folders, build artifacts or test logs, and did not run tests. **The reviewer reports hashing the original 136-line UTF-8/LF file at `C:\Users\MnemeAgent\r3-work\r3-scorer-workspace\evidence-707-scorer-b-2026-10-28.md`: 11,484 bytes, SHA-256 `47966f901ca4b69794b5d8d61a01b9978d3fc56d814287429103e32f3d0228be`, last modified `2026-10-28T20:40:42Z` (no BOM, no CR; ends with LF). The file itself, its original command logs and the full host file-hash table have not been transferred to or independently inspected by this remote PR author. The digest binds the reviewer's read of that Windows file at that time; owner-controlled retention and custody attestation remain OPEN.** Treat the sanitization result as a **reviewer-reported assessment**, not a host-level custody clearance or environment attestation. Transfer only reviewed metadata, not concealed material or owner secrets.

The reviewer also **reports direct read-only Git/source checks**: merged #705 harness parent and 17 changed files, tree prefix `bde6c9d6…`, 16 committed-blob SHA-256 values, and syntactic presence of the seven malformed-`rule_id` negative tests and positive control in the pinned test file (hash prefix `404d2ade…`). The negative tests' **execution** and `232 passed` remain scorer B reports without original output/report digests. The reviewer's local `origin/main` was stale at `086bbbf7`; current GitHub independently confirms #701 and #708 merged. It could not locate accepted #705 head `26b1fa01` in its local object store; §2 already records independent GitHub verification of the resulting merge.

| Attestation item | Evidence to date | Closure condition (still OPEN unless specified) |
|---|---|---|
| Sanitized scorer B evidence packet | Reviewer reports **CLEAN**, 136 UTF-8/LF lines, 11,484 bytes, SHA-256 `47966f901ca4b69794b5d8d61a01b9978d3fc56d814287429103e32f3d0228be` (read-only Windows-host verification on 2026-10-28) | **Full digest recorded**, but the owner must retain/attest to the identical original bytes and verify custody; CLEAN is not proof of access isolation |
| Harness 16 source hashes; 12 `harness.files_sha256` smoke fields | Reviewer reports committed-blob checks; scorer reports LF-only checkout | Record exact on-disk 16-file SHA table, `core.autocrlf=false`, clean detached checkout, merged Git blobs and exact smoke report/file correspondence |
| Targeted tests and attribution controls | Reviewer checked test definitions; scorer reports `232 passed, 0 failed, 0 skipped` | Pin actual commands, runtime, source/test SHA-256, result log digest and exit code; CI does not replace these main-only tests |
| Public and synthetic checks | Scorer reports public `14/14`, synthetic `10/10`, `NO_VERDICT_PUBLIC_SMOKE` | Full archive/manifest hash, exact smoke command, report digest, twelve harness hashes, and independent final checkout binding |
| D3 implementation | Scorer reports wheel `f2ed395a…4289` (557,421 bytes), installed manifest `d073dd14…df07`, freeze `253e5bc8…00c2`, `--all` freeze `4ce67609…e910` | Verify full wheel hash, build author/environment/provenance, raw installed-file `RECORD` and source inventory, Python and complete venv freezes. Normalized equality alone is insufficient |
| Fresh R3 baseline | Scorer reports source `f8591102`, tree `002fdddb`, wheel `b24a2f83…2132`, installed manifest `e4848c41…2cf2`, freeze `5545c178…7c2` | Independently pin **this R3 baseline wheel** and its build, package `RECORD`, complete installation/environment manifest and reproducible parity command |
| Claude Code host | **CLOSED for §6.1 characterization record** by merged #708; host `2.1.312` / `6099672e…c865` | **OPEN for final scorer runtime:** independently verify identical executable and path, exact `--host-version` and `--host-sha256` arguments and unmodified host bytes |
| Symlinks | Scorer reports file and directory symlinks at a development root | Retest at the **final scoring run root**, with Windows identity, path, output, exit status and digest |
| Scorer B independence and key exclusion | Self-report of not reading concealed files; no actual scorer-B recheck | Owner/independent reviewer verifies synthetic-only decryption denial, effective user/config and access to author/public/synthetic folders; record GO/NO-GO without opening concealed corpora |
| Structural decisions and command | Proposed §6 criteria; no owner acceptance or final command/run root | Owner explicitly accepts criteria, independent reviewer identity and outcome mapping; independently pin exact execution command, run root, preservation/STOP plan |
 
**Baseline identity is not a single interchangeable hash.** The #646 historical replay wheel (`6dfa470e…fabd6`), the #708 characterization-only baseline wheel (`8d788ece…7d30`), the separately accepted historical R2 baseline wheel (`3497b5dd83942ef5df06fe522acaaa7e6e2833759dfdd25daa8866f65dacd1b2`) and scorer B's candidate R3 baseline (`b24a2f83…2132`) have different roles. The frozen R3 §6.1 **requires the exact newly built R3 baseline wheel SHA-256 and installed environment to be independently pinned**, even when the common source is equivalent after newline normalization. Do not substitute an installed-manifest digest *instead of* the wheel pin, and do not use either historical/replay wheel as the R3 scoring artifact without an accepted protocol change. Existing candidate retention (§3) is not completed environment verification.

**Source-byte discrepancy resolved: different comparison references (reviewer-reported read-only verification, 2026-10-28; #709 withdrawn).** The reviewer checked the frozen implementation wheel (SHA-256 `f2ed395a6517006971f49baf169b957c10d0dfff4784ad36b3bb53eb9c024289`, 557,421 bytes; 111 `mneme/*.py` files, matching the file set from Git tree `656554d21ec1ef4ee474b6e6f69f681f0364a501`). Its two raw-byte comparisons used different references:

| Comparison reference | Raw-identical to wheel | CRLF/LF-only differences | Substantive differences |
|---|---:|---:|---:|
| `git archive 1b0957af mneme` with host system `core.autocrlf=true` (107 entries converted to CRLF) | 111/111 | 0 | 0 |
| Committed LF Git blobs at `1b0957af` | 4/111 (four integration `__init__.py` files with no line breaks) | 107 | 0 |
| `git archive` with `core.autocrlf=false` | 4/111 | 107 | 0 |

**Interpretation:** #708 §2's statement of 111/111 byte identity **with the Git archive** is consistent with the frozen wheel under the host's default `core.autocrlf=true`. The archive is affected by that setting and **is not the same reference as the committed LF blobs**. Scorer B's 4 raw matches and 107 newline-only differences are measurements against those blobs. An earlier review incorrectly reported LF archive output under `core.autocrlf=true` because the Git Bash `grep` command used to count CR bytes was unreliable; the reviewer corrected the measurement using a file-backed Python byte comparison and withdrew the earlier accusation. Proposed erratum #709 was **closed without merge**. No #708 correction is indicated by this archive-versus-wheel comparison.

**Limits:** The independent reviewer compared the **wheel contents**, not raw `site-packages` bytes in the #708 characterization venv or Scorer B's scoring venv. Those original installed-file inventories and `RECORD` attestations remain **OPEN**. The corrected comparison does not reconstruct the original #708 author's measurement method, independently validate its installed-file statement, or imply any change to the ten host characterization outcomes. The completed pre-scoring record must identify for **every source-byte identity statement** its reference (committed Git blob, Git archive, or checkout), effective `core.autocrlf` setting and configuration origin, and whether comparison is raw or line-ending-normalized.

**Runtime freeze difference:** The #708 characterization venv freeze `60dddbca…` differs from candidate scorer implementation freeze `253e5bc8…`; the reporter attributes this to additional build packages (`build`, `colorama`, `packaging`, `pyproject_hooks`). Preserve both facts, but do not infer unchanged runtime semantics without independent final environment verification.

**Custody inventory details:** The `public-smoke-NOT-RELEASED` naming discrepancy needs owner explanation. `runs/review705-pubcov` reportedly contains **relabelled public inputs solely for synthetic coverage probes**, not R3 concealed cases; these must not enter hidden-case counts. `wt-review-705`, `runs/review705*`, and `mneme-public/.git/config` (`extensions.worktreeConfig=true`) are inventory targets for independent review. `core.autocrlf=false` makes exact Git-byte validation possible; it is not a confidentiality boundary.

**Decision:** The packet supplies useful reported evidence and independent source-structure checks, but **no new pre-unblind gate is closed by it**. Incomplete/contradictory source attestations, missing final execution/custody evidence, or unexpected access to concealed or author material require **NO-GO**. PR #707 remains **DRAFT / NO-GO**, requires a separately reviewed completed record, and cannot authorize unblind, concealed scoring, a gate PASS or retrospective G2-1 PASS.

## 7. Exact pre-unblind completion gates (all OPEN unless independently evidenced)

- [x] PR #705 squash merge **verified on GitHub**: commit `086bbbf7556297f19f13cb2c5c2682687bcf41b4`, 17/17 changed Git blobs match reviewed head. This does not verify any local working-tree bytes.
- [x] Scorer B LF worktree point-in-time verification: independent reviewer reports clean detached `086bbbf7` checkout, 16/16 pinned file hashes and 6,853/6,853 tracked blobs equal to Git at 2026-10-29T00:04Z; effective worktree `core.autocrlf=false`. **Recheck immediately before actual scoring.** This does not close the separate smoke-report hash, custody or runtime attestations.
- [ ] Every source-identity attestation explicitly identifies its reference (committed Git blob, Git archive or checkout), effective `core.autocrlf` and configuration origin, and whether bytes were compared raw or normalized.
- [ ] Exact complete independent scorer B tests and synthetic attribution negatives rechecked at that merged commit; no unknown omissions.
- [ ] D3 source/wheel/installed-file manifest/dependency freeze independently attested.
- [x] Baseline **source-equivalence comparison reviewed and candidate retained**: distinct R2/R3 wheel hashes recorded and newline-only source difference explained. This check is **not** the complete environment attestation.
- [ ] Baseline source/tree, newly built wheel, installed-file `RECORD`, dependency freeze and actual scoring environment **independently attested**. Scorer B's observations and reproduced source-content equivalence do not, alone, complete this item.
- [x] R3 Claude Code 2.1.312 **live-host** characterization recorded under frozen §6.1, independently reviewed for documentary/source consistency, and merged as #708 (`2cab9390`); exact executable digest `6099672e…c865` documented and re-hashed by the reviewer. This does **not** attest scorer B's final runtime or the unpublished run artifacts.
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
