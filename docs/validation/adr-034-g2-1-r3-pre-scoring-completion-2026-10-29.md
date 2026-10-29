# ADR-034 G2-1 R3: completed pre-scoring record

**Date:** 2026-10-29  
**Status:** **COMPLETED METADATA-ONLY PRE-SCORING RECORD, pending independent review and merge.** This record is not an unblind GO, and merging it is not one either.  
**Supersedes:** the interim NO-GO checklist merged from PR #707 as `9ad26b032db565aa79ed8e2ffe140ff55cf6fd62` (`adr-034-g2-1-r3-pre-scoring-completion-draft-2026-10-28.md`). That file stays as a historical archive. Where the two disagree, this record governs.  
**Scope:** ADR-034 G2-1 independent R3. Frozen pre-registration #699 (`6d86358e`), AT-SI amendment #701, held-out freeze #703, scorer handoff #704, harness #705 (`086bbbf7`), live-host characterization #708 (`2cab9390`).  
**Disposition:** R3 **SEALED**. G2-1 **FAIL**. No decryption, unblinding, concealed-case access or scoring has occurred. Nothing in the frozen protocol, corpus, labels, implementation, baseline or harness has changed.

## 0. Evidence terms

- **VERIFIED (V):** the independent verifier (§1) ran the stated read-only check itself, on the stated host, at the stated UTC time.
- **SCORER B (S):** scorer B's own check, recorded with its command, time and output digest in the Phase 1 package. Where the verifier re-hashed or re-derived it, the row says so.
- **OWNER (O):** an explicit owner ruling, cited by its GitHub comment.
- **AT SCORING (T):** a time-sensitive property that must be rechecked in the §8 preflight immediately before the run.

All host evidence comes from one Windows host, user `arxwn\mnemeagent`, SID `S-1-5-21-248010808-3713673497-1623073800-1008`, Medium integrity, not an administrator. The host rebooted at 2026-10-29T04:58:37Z. The verifier's checks at 13:19–13:25Z were all taken after that reboot.

## 1. Roles and identities

| Role | Identity | Independence evidence | Status |
|---|---|---|---|
| Owner and custodian | `arxwn\MnemeOwner`. Exclusive custodian of the owner secret key and the owner-controlled sealed originals; this is not a claim that no separately staged ciphertext copy or filename was visible to `MnemeAgent` (§6). | — | O |
| Author A | Session `7bf4599d-e496-4829-941e-26ed50820b66` | Excluded from scoring and from structural review | O |
| Scorer B | Claude Code session `3121484e-a5ab-4aad-85ae-ccca9d92a8a1`. Config `C:\Users\MnemeAgent\r3-work\r3-scorer-claude`. Workspace `C:\Users\MnemeAgent\r3-work\r3-scorer-workspace`. | Not author A (different session and config, per checkpoint-0 extract `5fc9799b…90a5`). Session created 2026-10-28T15:03:22Z, after D3 #697 merged at 2026-10-28T01:16:59Z, so it did not author D3. Owner key absent: the synthetic decrypt probe returned `No secret key`. | V + O (custody ruling 6485020187) |
| **Primary structural reviewer** and independent verifier | Claude Code session `a84f1b16-ff95-4f05-8ff6-b6ed3ad056ed`. Config `C:\Users\MnemeAgent\.claude-pr708-review`. Transcript created 2026-10-28T22:25:14Z. | Not author A or scorer B. Session started after #697 merged, so it did not author D3. Has not read any concealed, R1 or R2 corpus, any ciphertext, or author material. Re-confirmed after the reboot at 2026-10-29T13:19:17Z: same session, config and transcript creation time. | V + O (6485368507 item 3) |
| Backup structural reviewer | Scorer B, as above. Used only if the primary cannot act. | Independence from A and D3 verified above. D1 and D2 disclosures retained (§6). | V + O |

**Shared-account limitation (accepted residual risk).** Scorer B and both structural reviewers run as `MnemeAgent`. Windows ACLs therefore cannot separate their access to the corpus or the staging outputs. R3 §4.1 states that separate sessions or `CLAUDE_CONFIG_DIR`s under one account give no Windows-enforced confidentiality.

The owner accepted the residual risk in ruling **6498158192** (2026-10-29T13:35:43Z), subject to the sequential runbook in §7.
- **What the runbook does:** it reduces *accidental* early access and makes the order auditable.
- **What it does not do:** it does **not** provide technical isolation, and it does not prove that no read occurred.
- If reviewer and scorer separation cannot be substantiated at any step, the outcome is **NO-GO**; it is never silently waived.
- A separate non-admin reviewer account is the stronger design. It is out of scope for R3 unless separately reviewed.

## 2. Harness and checkout

| Item | Value | Reference / byte basis | Status |
|---|---|---|---|
| Harness merge | `086bbbf7556297f19f13cb2c5c2682687bcf41b4`, from accepted head `26b1fa01…`. 17/17 changed blobs identical. | GitHub | V (GitHub, recorded in #707) |
| Root tree / harness tree | `40c73b87e72eb89c2aba3a725b874a93f5f866d2` / `bde6c9d6ab464dc5a0576b7ba2d37b91490f3f46` | commit objects | V |
| Scoring checkout | `C:\Users\MnemeAgent\r3-work\r3-scorer-workspace\wt-r3-merged-086bbbf7`, detached at `086bbbf7`. Effective `core.autocrlf=false`, set in worktree scope `config.worktree`. System scope `C:/Program Files/Git/etc/gitconfig` has `true`. `git status --porcelain` is empty. The only ignored entries are three `__pycache__` dirs, whose newest file is 2026-10-28T20:34:30Z. | — | V at 2026-10-29T00:04Z, 01:33Z and 13:19Z (`--no-optional-locks`); T |
| Tracked files | 6,853/6,853 raw-equal to committed blobs | committed blob, raw, no normalization | V at 2026-10-29T00:04Z |
| 16 pinned files | 16/16 raw-equal. Table in the Phase 1 package §2, the same SHA-256 values as committed blobs. | committed blob, raw | V at 00:04Z, 01:33Z and 13:19Z; T |
| Harness `files_sha256`, 12 entries in the smoke reports | 12/12 equal to committed blobs | committed blob, raw | S |
| Targeted tests at `086bbbf7` | `232 passed, 0 failed, 0 skipped`, exit 0, rerun at 2026-10-29T00:23:33Z. Command in Phase 1 §5. Log `pytest-086bbbf7.log` SHA-256 `397440a1668d3d5d2627da2183f438be670bc38f8ad759ac0c2df40d8e5c90cb`. Includes the attribution negative controls in `tests/test_adr034_g2_1_r3_harness.py` (`404d2ade…d695`). | — | S; log hash and text re-checked by V |
| Public and synthetic smoke | Public 14/14 and synthetic 10/10, `NO_VERDICT_PUBLIC_SMOKE`, version pin matched. Reports `89f04f8a…d5a7` and `0ab5f36c…fcfc`. | — | S |

## 3. Implementation and baseline environments

All source-identity statements below name their reference and their byte basis, as the #707 §7 rule requires.

| Item | Implementation (`env\impl`) | Baseline (`env\base`) | Status |
|---|---|---|---|
| Source | `1b0957af01df3ad036b12698663e167ae413885e`, `mneme/` tree `656554d21ec1ef4ee474b6e6f69f681f0364a501` | `f8591102b2693379dabec9b5704862e194eca4ce`, tree `002fdddb254267d42a3810cfea669d75700372f2` | frozen |
| Wheel | `f2ed395a6517006971f49baf169b957c10d0dfff4784ad36b3bb53eb9c024289`, 557,421 bytes (frozen R3 §2) | `b24a2f8328855d2e41e6ae43eb16c7ae488afcc5944713e66300bc061f132421`, 545,569 bytes (built by scorer B) | V |
| Wheel provenance | Rebuilt from `git archive 1b0957af` with `core.autocrlf=true`, `build==1.6.1`, `setuptools==84.2.1`. Same 117 entry names and order; 117/117 uncompressed entries byte-identical, including `RECORD` and `METADATA`. Only ZIP timestamps differ. **Original builder, command and logs: unavailable** (retained limitation). | Built by scorer B at 2026-10-28T15:16:12Z. Command and build log `a6aaa7da…c539` in Phase 1 §4. | V + O (6485269158) |
| Wheel versus Git | Wheel equals `git archive` under system `core.autocrlf=true`: 111/111 raw. Against committed LF blobs: 4 raw-equal, 107 differ only by CRLF/LF, 0 substantive. | Same pattern against tree `002fdddb`: 4 / 107 / 0 | V (implementation); S (baseline) |
| Installed files versus wheel `RECORD` | 122/122 entries, 0 mismatches. `RECORD` `b61c4a97…e184`. | 122/122, 0 mismatches. `RECORD` `2b212cbe…f61b`. | S; V re-derived |
| `pip freeze` / `--all` | `253e5bc8…00c2` (= R3 §2) / `4ce67609…e910` | `5545c178…e7c2` / `2ac41c01…e211` | S; V re-hashed |
| `pip check` | clean | clean | S |
| Interpreter | CPython 3.12.10, pip 25.0.1, `mneme` 0.10.0 | same | S |
| Historical R2 baseline comparison | — | R2 `3497b5dd…` versus R3 `b24a2f83…`: 4 raw / 107 newline-only / 0 substantive. The R3 candidate is retained. | S + owner disposition in #707 |

Retained limitation: the CRLF payload bytes are the bytes actually installed and scored. Source equivalence is established only after line-ending normalization. No claim is made that line endings cannot affect any runtime observation.

## 4. Host

| Item | Value | Status |
|---|---|---|
| Executable | `C:\Users\MnemeAgent\.local\bin\claude.exe`, `2.1.312`, 298,690,208 bytes | V; T |
| SHA-256 | `6099672ebe5dcb518b67d1d32dde1e3360bc6bee1dae7f8d28a69c49acc7c865`. Equals the #708 characterization pin. | V at 00:40Z, 01:33Z and 13:19Z; T |
| Authenticode | Valid, signer Anthropic, PBC, thumbprint `60C2D9C51F09822FFF4F194DE9EEDB67451292D1` | V at 13:19Z |
| R3 §6.1 live-host characterization | Merged #708 `2cab9390` | V (document review) |

## 5. Filesystem, permissions and symlinks

**Final run root** `C:\Users\MnemeAgent\r3-work\r3-scorer-workspace\runs\r3-scoring-086bbbf7`:
- The merged `runner.check_work_dir` accepts it. No `.mneme` folder exists on any ancestor.
- It is empty (V at 01:33Z, 13:19Z and 13:25Z; T).
- **Symlink capability at this exact root:** the merged `runner.symlink_capability` returned `{"file": true, "dir": true, "capable": true}` at 2026-10-29T01:33:38Z, run as `env\test` python `-I -B` importing the LF checkout. The probe was removed and the root left empty (V). Scorer B's identical result at 00:23:45Z is corroboration (S).
- Rechecked as part of the §8 preflight (T).

**Protected directories** were created and configured by `MnemeOwner` after the reboot. The rights below are effective rights, worked out from each ACL against the `MnemeAgent` token. The token includes Everyone, Users, Authenticated Users, Interactive and Local. No deny ACEs exist, and `MnemeAgent` owns none of these objects. All checks were metadata-only, at 2026-10-29T13:19Z and 13:21Z (V).

| Path | Owner / inheritance | ACEs | `MnemeAgent` effective | Contents |
|---|---|---|---|---|
| `C:\` (ancestor) | TrustedInstaller | Users RX; Authenticated Users `AD` on the root itself plus `(OI)(CI)(IO)M` for children that inherit | Can create new top-level folders. **No delete-child right.** The Modify grant does not reach `C:\mneme-r3`, whose inheritance is off. | — |
| `C:\mneme-r3`, created 13:12:35Z | MnemeOwner / **protected** | MnemeAgent RX; MnemeOwner, Administrators and SYSTEM F | RX only: cannot add, delete, rename or re-ACL children | `corpus`, `results` only |
| `C:\mneme-r3\corpus`, created 13:14:12Z | MnemeOwner / inherits from the protected parent | as parent | **RX only**: cannot pre-create or modify plaintext | **empty** |
| `C:\mneme-r3\results`, created 13:16:11Z | MnemeOwner / **protected** | MnemeAgent M; MnemeOwner, Administrators and SYSTEM F | Modify: the staging area for the two harness outputs | **empty** |
| `C:\Users` (ancestor) | SYSTEM / protected | Users and Everyone RX | RX | — |
| `C:\Users\MnemeOwner\mneme-r3-custody` | not readable by `MnemeAgent` | Owner-reported from a `MnemeOwner` session: MnemeOwner, SYSTEM and Administrators F; no grant to `MnemeAgent` | **No access.** Reading attributes is denied, even with bypass-traverse enabled; the parent profile is also denied. | not visible |

The old `C:\dev` proposal is withdrawn and must not be used: `C:\dev` grants Authenticated Users Modify to everything beneath it.

**Public smoke tar:** `C:\Users\MnemeAgent\r3-work\r3-sealed-staging\public-smoke-NOT-RELEASED\r3-public-smoke.tar`, SHA-256 `feee204134fb4dd339f6efcbde9053c7d1f37a880f74f5ec411eb4cf2f5020a4` (= #703). V at 01:33Z and 13:19Z; T. The merged `public_smoke.verify` returns `verified: true` with 14 cases (S). The folder name `NOT-RELEASED` is historical: #704 authorizes public use.

## 6. Custody

- **Checkpoint-0 deviation:** accepted by owner ruling 6485020187. Evidence:
  - custody extract `5fc9799b93b1b472918ddb417b319188849a5b4888636967fe1bb77bcfd090a5` (22,497 bytes);
  - `checkpoint-0-identity-isolation.md` `389af9499a042a5c222d5f10fbd8c1e58f3b01833a42a7422f3f3e056c203a8b`;
  - Phase 1 package `7ff7b2bfd8c66040908b04eff5065ebb667a3235096171371f98499b1a1a1628` (38,684 bytes);
  - `evidence-707-scorer-b-2026-10-28.md` `47966f901ca4b69794b5d8d61a01b9978d3fc56d814287429103e32f3d0228be`.
  - All four were re-hashed unchanged at 13:19Z (V).
- **Ciphertext access by scorer B:** a name-and-size listing only. No file was opened, hashed or decrypted. The earlier word "listed" in `evidence-707` §7 is corrected by Phase 1 §9.
- **Retained disclosures:**
  - **D1:** checkpoint-0 timestamp inconsistency. The note was written at 15:08:27Z but refers to work to ~15:20Z and to a tar check that Phase 1 places at 17:50Z.
  - **D2:** an undisclosed `git remote/rev-parse/status/log` at 15:03:58Z in the public checkout `r3-work\mneme`. It returned public metadata only.
- **Limited workspace metadata check (V).** The verifier observed no timestamp changes at depth ≤ 2 within scorer B's workspace between 01:34Z and 13:19Z. This does not establish absence of changes at greater depth or in other locations. Scorer B's config folder was last modified at 04:54:22Z (before the reboot); its contents were not inspected.
- **Process baseline, recorded 2026-10-29T13:37:31Z (V):**
  - The only running `claude.exe` is PID 13856, created 13:18:38Z, command line `--resume a84f1b16-…`, which is the verifier.
  - Scorer B's transcript was last written at 04:54:22.12Z and its config dir at 04:54:22.74Z, both before the reboot.
  - `corpus`, `results` and the run root are empty.
  - This is the reference state for the §7 step 2 absence check.
- **Inventory retained as audit evidence:** `wt-review-705`, `runs\review705*` (public and synthetic only), `runs\merged086-smoke`, `runs\phase1-logs-20261029T002303Z`, and `extensions.worktreeConfig=true` in `mneme-public\.git\config`. None of these is a scoring input.

## 7. Structural review: accepted procedure, as pinned

Owner ruling 6485368507 item 3 accepts the #707 §6 criteria **unchanged**:
- identifiers `SC_lexical_families`, `AT_material_distinctness` and `public_vs_concealed_AT`;
- outcomes `present`, `missing` and `undetermined`, where `missing` means FAIL and `undetermined` means INCOMPLETE, treated as FAIL;
- the `r3-structural-v1` canonical JSON escrow recipe.

Owner ruling 6498158192 adds a **sequential runbook**. It provides operational protections only: no frozen gate, case or criterion changes. This record pins the runbook as follows.

1. **Before the unblind GO**
   - This record is independently reviewed and merged.
   - `C:\mneme-r3\corpus` stays **empty**, and concealed material stays sealed under `MnemeOwner`.
   - Implementation, wheels and harness stay unchanged.
2. **On the separate unblind GO, before plaintext is released**
   - Scorer B's Claude session and process are **stopped**.
   - The independent verifier documents scorer B's absence, metadata-only:
     - `Get-CimInstance Win32_Process -Filter "Name='claude.exe'"`: list PID, creation time, parent and command line. The only `claude.exe` processes must be the reviewer's own, identified by PID or parent chain. Any other process means STOP unless the owner accounts for it.
     - The `LastWriteTimeUtc` of scorer B's transcript `C:\Users\MnemeAgent\r3-work\r3-scorer-claude\projects\C--Users-MnemeAgent-r3-work-r3-scorer-workspace\3121484e-a5ab-4aad-85ae-ccca9d92a8a1.jsonl` and of its config dir are recorded. They must be **unchanged** at the end of the review window. Contents are never opened.
   - The verifier records the UTC time of this check.
   - The primary reviewer from §1 is the only authorized active agent. The backup is used only on an owner ruling that the primary cannot act, and only the reviewer who actually reviewed is recorded.
   - `MnemeOwner` alone decrypts, verifies both digests (§8, decryption layout) and extracts into `C:\mneme-r3\corpus`.
   - The owner records the **start-of-exposure** UTC time.
   - `MnemeAgent` stays read-only there. No plaintext goes into user-writable staging or author workspaces.
3. **Structural review only**
   - **Inputs:** only the released `case.json` fixtures under `C:\mneme-r3\corpus`, plus the frozen public AT case, read only.
   - **Not allowed:**
     - Mneme runs;
     - reading `C:\mneme-r3\results` or the run root;
     - gate, hook, checker or scoring output;
     - any contact with the scorer.
   - **Output:** only the three `r3-structural-v1` determinations.
   - The reviewer records its own session ID and start and end UTC times.
   - **STOP conditions:**
     - unexpected early access;
     - content outside the owner's release;
     - any attempt to modify the corpus;
     - uncertain role separation;
     - any change in scorer B's transcript or config timestamps.
4. **Owner escrow before scorer B restarts**
   - The reviewer gives the canonical bytes and their SHA-256 **directly to the owner**, never through `C:\mneme-r3\results` or any other agent-writable location.
   - The owner checks the format and writes the **exact bytes** to `C:\Users\MnemeOwner\mneme-r3-custody\r3-structural-v1.json`, which `MnemeAgent` cannot access.
   - The owner recomputes the SHA-256, confirms it matches, and posts **only**: the digest, `r3-structural-v1`, the reviewer identity and the owner commit UTC time.
   - The reviewer session then **ends** before scorer B is allowed to resume.
   - **Ordering evidence** is the owner-side record: start-of-exposure, escrow commit, reviewer end and scorer restart times, plus the verifier's process and transcript-timestamp checks. File mtimes written by the scorer are corroboration only, **not sufficient proof** of ordering.
5. **Only after the escrow**
   - Before ending its session, the independent verifier records a metadata-only readiness check on the fixed host, checkout, environments, run root and permissions, without running any gates or examining scorer output. The owner retains this pre-handoff verification and its UTC time. The released corpus's frozen hashes and integrity are separately owner-verified at release.
   - The structural reviewer/verifier session ends; the owner records its end time and escrow commitment before permitting Scorer B to restart. **No verifier and scorer Claude sessions run concurrently.**
   - Scorer B alone repeats the §8 metadata-only preflight immediately before execution, recording check outputs and UTC timestamps for owner retention. Any mismatch means STOP; no scoring command is run. This contemporaneous recheck is scorer-executed, **not** falsely labelled independently verified.
   - It then runs the exact §8 command **once**, unchanged. After completion and structural escrow, a reviewer independent of Scorer B can examine the preserved preflight metadata to corroborate the scoring-time pins, without changing the precommitted structural determinations or authorizing a rerun. Unverifiable scoring-time pins block a final PASS claim.
   - The rules of §8 and §9 apply.
6. **No revision**
   - Determinations are not revised after the escrow.
   - No retroactive conversion of `missing` or `undetermined` to `present`.
   - A numeric `decision.verdict` of PASS is never promoted to a full validation PASS unless all three determinations are `present`.

## 8. Pinned scoring command

The command was verified at 2026-10-29T13:25:01Z. It was parsed through the merged harness's own `main()` with `score` stubbed out, so nothing was scored or written (V):
- parse exit 0, harness `r3-harness/1` imported from the LF checkout;
- host-SHA format accepted, `--work` accepted by `check_work_dir` and empty;
- interpreters and tar present, both output parents exist, neither output exists yet;
- both outputs outside `--work` and outside `--corpus`, and distinct from each other;
- no `.pyc` written, checkout still clean.

```powershell
cd C:\Users\MnemeAgent\r3-work\r3-scorer-workspace\wt-r3-merged-086bbbf7
$env:PYTHONDONTWRITEBYTECODE = '1'
C:\Users\MnemeAgent\r3-work\r3-scorer-workspace\env\test\Scripts\python.exe -m benchmarks.adr034_g2_1_r3 score `
  --corpus C:\mneme-r3\corpus `
  --work C:\Users\MnemeAgent\r3-work\r3-scorer-workspace\runs\r3-scoring-086bbbf7 `
  --impl-python C:\Users\MnemeAgent\r3-work\r3-scorer-workspace\env\impl\Scripts\python.exe `
  --base-python C:\Users\MnemeAgent\r3-work\r3-scorer-workspace\env\base\Scripts\python.exe `
  --host-version 2.1.312 `
  --host-sha256 6099672ebe5dcb518b67d1d32dde1e3360bc6bee1dae7f8d28a69c49acc7c865 `
  --scoring concealed `
  --public-smoke-tar C:\Users\MnemeAgent\r3-work\r3-sealed-staging\public-smoke-NOT-RELEASED\r3-public-smoke.tar `
  --report C:\mneme-r3\results\r3-concealed-report.json `
  --observations C:\mneme-r3\results\r3-observations.json
```

Notes on the command:
- There is no `-I` flag, because the harness is imported from the current directory.
- One invocation runs both G7 passes.
- The harness does not enforce an empty `--work` or create output parents, so the preflight covers both.

**Decryption layout (owner).** `runner.load_corpus` searches all of `--corpus` for exactly one `MANIFEST.sha256`. It fails integrity with `file_outside_manifest_scope` if any file sits outside that manifest's directory.
- Decrypt and verify the ciphertext (`19846963bc53cb4e23a7d535ca1d6f970dfae9eabdf7364998e2809ede5e02d0`) and the plaintext tar (`3d468d2fc36cc32ad067f13035ccc44f9493ba7032fd41f069217486a88f61eb`) **inside custody**, not in `corpus`.
- Then **extract** the tar into `C:\mneme-r3\corpus`, so that the folder holds only the archive's contents: no `.tar`, `.gpg` or notes.
- Extract or copy; do not *move* files in from the profile. Moved files keep their source ACL and could be unreadable to `MnemeAgent`.
- Confirm the extracted entries show the inherited `MnemeAgent:(I)(RX)`.

**Preflight immediately before the run (T).** In accordance with §7 step 5, the independent verifier checks readiness **before** the scorer handoff and ends its session; Scorer B then repeats the checks **alone** immediately before scoring, preserving metadata-only output and timestamps for owner custody and later independent assessment. No simultaneous reviewer/scorer sessions are allowed. An independent reviewer may verify the preserved scoring-time evidence after the run, but must not revise structural determinations or claim a contemporaneous independent recheck.
- Host SHA and version.
- Checkout HEAD, clean status, effective `autocrlf=false`, 16/16 pinned files.
- Run root empty, plus `check_work_dir` and `symlink_capability` at the root (removing the probe).
- Interpreters present. For both `env\impl` and `env\base`: `pip freeze --all` hashes unchanged, and the installed files still match the wheel `RECORD` (122/122).
- Corpus integrity at owner release: the ciphertext and plaintext tar digests below were verified by the owner, and the corpus holds only the extracted archive.
- Public tar SHA.
- `C:\mneme-r3\results` empty; corpus ACLs unchanged.
- Escrow digest posted.
- **Any mismatch means STOP.**

**Stop and rerun rule.** A crash, an abort or an interrupted run means **STOP**:
- Preserve every output and the work root.
- Do not re-run without an explicit owner ruling.
- Never delete or edit a report.

## 9. Results custody and cleanup (owner)

**Owner confirmation, 2026-10-29 (option A).** The owner confirmed four things:
- the corpus, report, observations and custody paths above;
- that `MnemeAgent` being denied access to the custody vault is expected, and that the owner has verified the vault's ACL;
- that after scoring the owner will hash the outputs and securely transfer them into custody;
- that the owner will revoke `MnemeAgent`'s staging access.

1. **Immediately after exit**, the owner records the SHA-256 and size of `r3-concealed-report.json` and `r3-observations.json`. These are the evidence digests.
2. The owner **copies both outputs** into `C:\Users\MnemeOwner\mneme-r3-custody`, verifies that the copied digests match, and records the capture times.
   - Files the harness creates are owned by `MnemeAgent`, which therefore holds implicit `WRITE_DAC` on them.
   - So the owner then revokes `MnemeAgent`'s write access to `C:\mneme-r3\results`, and takes ownership of the staged files.
   - After the copy is verified, the staged `r3-observations.json` is deleted, or else access to it is restricted to the owner only.
3. The metadata-only results record states:
   - the unmodified `decision.verdict`;
   - `structural_review`;
   - the escrow digest;
   - the owner-level final outcome, separately.
   Observations are never published.
4. **Prompt custody close after a completed scoring run (not deferred until results-record merge):** once the owner has verified the hashes and secure custody copies of both outputs, stopped Scorer B, and preserved any required run-root or corpus evidence under the separately owner-approved custody-close procedure, the owner revokes `MnemeAgent`'s access to the released plaintext and removes the extracted plaintext from `corpus`. The owner then clears the run root **only after** required evidence has been securely retained and verified. Record exact actions, times, verification and any retained-material limitations in the custody-close evidence. The later metadata-only results review and merge use the retained evidence; they do not require leaving concealed plaintext accessible. **On crash, abort, disputed hashes or incomplete custody capture, preserve artifacts, prevent further access as safely possible and STOP for a separate owner ruling; do not delete evidence or re-run.**

## 10. Completion checklist (replaces #707 §7)

- [x] #705 merge `086bbbf7` verified on GitHub.
- [x] LF checkout verified: 6,853/6,853 and 16/16 raw, `autocrlf=false` in worktree scope. Rechecked post-reboot at 13:19Z (T at scoring).
- [x] Every source-identity statement names its reference, its `core.autocrlf` value and origin, and raw versus normalized (§2–§3).
- [x] Targeted tests (232) and attribution negatives at `086bbbf7`: S, with log hash checked by V.
- [x] D3 wheel, installed `RECORD`, freezes and `pip check` attested. Build provenance accepted by content reproduction (O 6485269158), with the limitation retained.
- [x] Baseline source equivalence; newly built R3 baseline wheel, `RECORD`, freezes and `pip check` attested.
- [x] Live-host characterization #708 merged. Scoring host equals the pin (V; T).
- [x] Scorer identity, key isolation and custody: owner ruling 6485020187, with D1 and D2 retained. Verifier observed no changes within the depth ≤ 2 scorer-workspace metadata inventory from 01:34Z to 13:19Z; this was not a complete filesystem or config-content audit (§6).
- [x] Symlinks at the exact final run root (V 01:33:38Z; T).
- [x] Public tar `feee2041…` and 14-case verification (V hash; S verify).
- [x] Structural criteria, outcome mapping and escrow recipe accepted (O 6485368507). Reviewer identities and hand-over procedure pinned (§1, §7).
- [x] Corpus, staging and custody paths, ACLs and parent rights verified (§5). Exact command dry-parsed against the merged harness (§8).
- [x] Option A staging and owner-custody paths confirmed. Post-scoring hashing, transfer and revocation of staging access confirmed by the owner (§9).
- [x] Owner accepts the shared-account residual risk and the sequential runbook pinned in §7 (O 6498158192, 2026-10-29T13:35:43Z).
- [ ] This record is independently reviewed and merged. The reviewer must not be its drafter (the §1 verifier) or scorer B.
- [ ] A separate, later **owner unblind GO**.

## 11. Disposition

Every pre-unblind technical item is evidenced, and every owner acceptance is recorded. What remains is the independent review and merge of this record, then a separate unblind GO, which is executed under the §7 runbook.

**NO-GO for unblind until those are complete. R3 SEALED. G2-1 FAIL. No retrospective PASS.**
