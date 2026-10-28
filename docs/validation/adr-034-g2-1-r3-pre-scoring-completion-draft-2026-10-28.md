# ADR-034 G2-1 R3: pre-scoring completion record (DRAFT / NO-GO)

**Date:** 2026-10-28  
**Status:** **DRAFT / NO-GO. NOT a completed evidence record.**  
**Scope:** ADR-034 G2-1 independent R3; frozen R3 pre-registration (#699), accepted AT-SI amendment (#701), held-out freeze (#703), scorer handoff (#704), scorer harness PR #705 and owner interpretation record.  
**Authority:** This draft does **not** authorize a merge, unblind, decrypt, read concealed material, run concealed scoring, change a case/label, or claim validation PASS. Owner and independent verifier must approve a fully evidenced successor before a distinct owner unblind decision.

## 0. State and evidence rules

The protocol requires a **separate, merged metadata-only pre-scoring completion record** before owner-controlled decryption (R3 pre-registration §5 step 7 and §6.1). The current record is a *draft evidence checklist*, **not** that completion.

**Snapshot from connected GitHub inspection at drafting:** PR #705 was reported `open/draft/merged=false` at head `26b1fa01336db909231b8d341feb182f1c35122d`; `main` did not yet contain `benchmarks/adr034_g2_1_r3/`. The user's message states that PR #705 was merged, but no verified merge commit on main is available in this record. **Merge verification is OPEN; do not use GitHub's proposed `merge_commit_sha` field as evidence of a completed merge.** Refresh this field before preparing the completion record.

Evidence provenance terms:
- **FROZEN SOURCE:** values already committed in earlier accepted metadata-only freeze records; they are anchors, not new checks performed for this draft.
- **REPORTED:** scorer B / owner statements in the handoff, not independently inspected host artifacts.
- **OPEN:** primary evidence missing, stale, incomplete, or not separately attested. An OPEN row cannot silently become PASS.
- **VERIFIED FOR THIS RECORD:** only when the reviewer includes the actual command/tool, host identity, timestamp, digest, run path, result and independent corroboration. No runtime field below currently qualifies.

**Owner GO/NO-GO:** **NO-GO.** The following sections have open requirements. This draft may be reviewed before PR #705 merges, but its completion successor must identify the exact merged harness and all environment evidence.

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
| Owner-key isolation recheck in actual scoring session B | Synthetic-only probe, secret-key access denial, access inventory and reviewer attestation; no hidden plaintext access | OPEN |

**Strict custody:** The owner-only author provenance and earlier concealed corpora/results are never inputs to scorer B. Do not move concealed case files, ciphertext or keys into repository artifacts or this PR. On unexpected author material, **STOP/NO-GO**.

## 2. Harness and accepted tests

| Required pin | Candidate / reported source | Status |
|---|---|---|
| Scorer harness PR | #705 reviewed and accepted at head `26b1fa01336db909231b8d341feb182f1c35122d` | REPORTED acceptance; **main merge OPEN** |
| Merge commit, main tree, clean detached scoring checkout | Record actual merge commit SHA, `benchmarks/adr034_g2_1_r3/` Git tree SHA, checkout path, `git status` and tree-vs-head comparison | OPEN |
| Every harness and README `.py/.md` byte SHA-256 | Recalculate from the *merged* tree and scorer-installed checkout; compare to PR head rather than assuming squash bytes match | OPEN |
| Full relevant test SHA-256 | Record all `tests/test_adr034_g2_1_r3_*.py` and `scripts/run_test_battery.py` digest/pin; no test edits after the freeze | OPEN |
| Targeted independent tests | Scorer B reports `232 passed, 0 failed, 0 skipped` on previously reviewed `6d0b64e9`; doc-only `26b1fa01` subsequently accepted | REPORTED; exact merged-tree evidence OPEN |
| Public smoke / synthetic operational test | Scorer B reports 14/14 public and 10/10 scorer synthetic with `NO_VERDICT_PUBLIC_SMOKE`, no concealed inputs | REPORTED; rerun/pin against completed scoring environments OPEN |
| Attribution negative controls | Missing, empty, wrong, duplicate, non-string and extraneous rule IDs plus untrusted checker data; required by R3 §3 | REPORTED as reviewed; final exact-head test hashes/results OPEN |

A green PR battery is not the full main-only R3 harness battery. Record environment, commands, exit codes, counts and a clean worktree for the final source pin.

## 3. Pinned implementation and baseline

**Implementation (D3 accepted source):** R3 preregistration §2 lists commit `1b0957af01df3ad036b12698663e167ae413885e` and `mneme/` tree `656554d21ec1ef4ee474b6e6f69f681f0364a501`. It reports candidate wheel `mneme_hq-0.10.0-py3-none-any.whl`, SHA-256 `f2ed395a6517006971f49baf169b957c10d0dfff4784ad36b3bb53eb9c024289`, CPython 3.12.10, pip 25.0.1 and an installed freeze-file SHA-256 `253e5bc832f81786e3cac033724d09f1196889572cb87ad72445c125543a00c2`. These are **owner-reported preregistration candidates, not newly verified R3 scoring attestations**.

**Baseline:** Frozen pre-G2 parity *source commit* `f8591102b2693379dabec9b5704862e194eca4ce`. Its accepted source/tree identity must be independently verified. Scorer B reports building a baseline wheel with SHA prefix `b24a2f83…`; a prefix and one scorer-built wheel are **not** an accepted independent reference. Older R2 baseline wheel SHA-256 in the R2 completion record is historical evidence, not automatic R3 proof.

| Verification requirement for **both** installed environments | Status |
|---|---|
| Git commit/tree/source archive identity, source commit checked out cleanly | OPEN |
| Fresh R3 build command, deterministic conditions, full wheel SHA-256 | OPEN |
| Independent baseline reference digest and reproduction check (record provenance if a reproducible wheel differs) | OPEN |
| Package `RECORD` and **complete installed-file inventory** vs wheel | OPEN |
| `mneme/` installed source inventory vs accepted pinned tree | OPEN |
| Exact Python executable, version and interpreter source; implementation and baseline in independent venvs | OPEN |
| `pip freeze --all` full text and SHA-256 in the **actual scoring venvs** | OPEN |
| Dependency integrity, `pip check`, executable runtime manifest and clean checkout | OPEN |
| Implementation `mneme` package version equals independently frozen `0.10.0`; reported hook evidence version also checked separately | OPEN (version-string equality alone insufficient) |

Every full SHA must be recorded and verified before changing status to complete. Do not borrow R2 build hashes as evidence of R3 reproduction.

## 4. Claude Code scoring host and live-host test

R3 §6.1 requires a **new, merged §8.B live-host characterization** using the R3 implementation because Claude Code 2.1.312 is different from the previously characterized 2.1.310 (#646). A scorer's local install digest or a synthetic replay is not live-host proof.

| Required evidence | Status |
|---|---|
| Exact scorer machine and Windows user, Claude Code executable path and `claude --version` | OPEN; scorer B reports version 2.1.312 |
| Executable SHA-256 (full 64 hex), shim/PATH origin, timestamp, signed provenance if available | OPEN; scorer B reports SHA prefix `6099672e…` only |
| Separately executed, documented live host §8.B tests with R3 implementation; report/PR merged before unblind | OPEN |
| Exact `--host-version` and `--host-sha256` pinned to *verified* host | OPEN |
| Provenance binding and ability to reproduce the required pinned host throughout scoring | OPEN |

The host re-pin and execution authorization are **owner tasks outside scorer B's self-reported observations**.

## 5. Filesystem, public archive and runtime readiness

| Requirement | Evidence and action | Status |
|---|---|---|
| File + directory symlink capability on the actual scoring host and run directory | Re-run harness probe on actual pinned checkout/run root; record outputs and errors | OPEN |
| First-pass L pre-mutation evidence | Scorer B approved synthetic nine-shape symlink classification; confirm exact merged harness code and tests | REPORTED, merged pin OPEN |
| Separate public tar exact hash + its internal manifest and 14-class inventory | Verify from frozen separately distributed public tar, using merged `public_smoke.verify`; include command and metadata-only result | OPEN |
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
2. **After separate owner-authorized unblind, before *any* G1–G8 scoring execution or per-case results are shown to the reviewer:** structural reviewer reads *only the authorized, frozen decrypted case files* (including the separate released public AT), **not** the generated checker/hook results, score labels or diagnosis. No Mneme runs, gate scoring, implementation tuning or corpus mutation during review.
3. For each pending identifier, record `present/missing/undetermined`, opaque case IDs and non-disclosing structural rationale. Hash the determination artifact and owner-commit/escrow its hash **before** running the G1–G8 scoring command. The reviewer must not consult gate results in preparing or revising the determinations.
4. Scorer then runs the frozen two passes. The final metadata-only results record reproduces the unmodified `decision.verdict`, `structural_review` (including `final_claim_ready` and three determinations), hash of the sealed structural assessment, and the owner-level final outcome separately. No manual override of G1–G8 or post-hoc reclassification.

**Exact criteria, frozen before opening concealed case files:**

| Pending identifier | Structural evidence for `present`; otherwise `missing` or `undetermined` |
|---|---|
| `SC_lexical_families` | **At least one concealed SC case demonstrating each named R2 §4.2 mechanism**, without inventing a numeric per-family gate floor: (1) same-named method `def` in a class body with call sites **inside AND outside that class**; (2) parameter binding; (3) local binding; (4) comprehension binding; (5) nested-function binding; (6) enclosing-scope resolution; (7) `global`/`nonlocal`; (8) indirect namespace mutation; (9) a namespace-related string used as plain data. Parameter/local/comprehension/nested are **four separate presence checks**, but may occur in the same concealed case if independently evidenced. Distinct classes/outcome quotas remain only those already frozen in R2 §4.2. |
| `AT_material_distinctness` | Assess each concealed AT subclass pair for real material difference in applied literal/numeric rule meaning or source behavior, not merely ADR ID, filename, selector-directory string or path renames. Reconfirm AT-SI's two independently derived literal identities **and** different include scopes, AT-SX's separate exclude-selector mechanism, and the AT-W0 literal-only vs excluded-numeric variants. Any materiality ambiguity is `undetermined`, not assumed `present`. |
| `public_vs_concealed_AT` | Compare the separate frozen public AT case and **every** concealed AT case for distinct proposed source, ADR meaning/source and literal-rule identity, consistent with R3 §3. Merely a changed name/path/ID or SHA is not sufficient to assert independent semantics; record opaque references only. |

**Owner acceptance of operational precision: OPEN.** These proposed criteria must be accepted or corrected **before unblind** and must not retroactively become new numerical case floors. After scoring, `missing` and `undetermined` may not be converted into `present` to improve a PASS claim.

## 7. Exact pre-unblind completion gates (all OPEN unless independently evidenced)

- [ ] PR #705 is verified **merged**, with actual merge SHA and main tree; recomputed byte hashes all match the reviewed harness.
- [ ] Exact complete independent scorer B tests and synthetic attribution negatives rechecked at that merged commit; no unknown omissions.
- [ ] D3 source/wheel/installed-file manifest/dependency freeze independently attested.
- [ ] Baseline source/tree, rebuild, wheel and installed-file/dependency manifests independently attested with an independent reference.
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
