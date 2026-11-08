# ADR-034 G2-1 R3: independently reviewed scorer handoff and owner GO

**Date:** 2026-10-28  
**Decision:** **GO to start new independent scorer B for PUBLIC harness development ONLY**; owner explicitly approved after metadata-only cleanup verification. **No concealed unblind, scoring, corpus/implementation changes, production claim or retrospective PASS.**  
**Contract:** frozen R3 pre-registration PR #699, AT-SI amendment PR #701, owner pre-seal custody GO PR #702 (`390c649c371bb5f37af79fa5f78e0d0f241e67b0`), and owner-verified corpus freeze PR #703 (`80b20ee0d17497145e48774c37cbc210a9c8a690`). Follow §4.2 and §5.  
**Source of observations:** Human-owner-executed local PowerShell/Git Bash outputs and author-reported metadata, reviewed by the separate ChatGPT orchestration/review session. This is **not** a third-party forensic examination or independent remote execution on the Windows host.

## 1. Role and custody pin

| Role | Identity / state |
|---|---|
| Human owner and key custodian | `MnemeOwner`, Standard Windows account, owner-only decryption and custody |
| Author A/public-key sealer | `arxwn\MnemeAgent` Standard account, Medium integrity; Claude Code 2.1.312 author session `7bf4599d-e496-4829-941e-26ed50820b66` exited by owner before cleanup; author worktree pinned at `6d86358e66734556400d92f9cbe28194a9763ac5` |
| Pre-seal scoring-environment probe | Separate human-operated PowerShell/Git Bash session on `arxwn\MnemeAgent`; disposable synthetic probe only, before corpus sealing; no scorer B started |
| Separate review actor | This ChatGPT orchestration session, which reviewed owner-provided metadata and GitHub's frozen protocol, not concealed contents, the author session or scorer implementation |
| New scorer B | **Not yet started at the instant of this record.** Must be new Claude Code process/conversation, not a resume/fork of A, under `arxwn\MnemeAgent`, separately pinned version/config/working directory and isolated from all author content; session ID and runtime observations to be recorded after start, before unblind |
| Administrator `hi` | Excluded from scorer execution and from any agent's private-key operations |

The sequential handoff reuses the same Standard Windows account. Separate agent sessions/configuration are **not** a Windows ACL security boundary; the handoff is conditional on observed absence of scorer-readable author materials, with residual limitations below.

## 2. Owner-verified sealed corpus

- Concealed corpus: **150** cases over 14 classes; 14 distinct public smoke cases, excluded from scored denominators. Author-only provenance sealed separately.
- Corpus ciphertext SHA-256: `19846963bc53cb4e23a7d535ca1d6f970dfae9eabdf7364998e2809ede5e02d0`.
- Author provenance ciphertext SHA-256: `07d0b06f3c11a3b67c280bb4b97aeca513ebd28ff3cdf7cdcf11cf3b46f7f17d`.
- Human owner transferred only ciphertext to `MnemeOwner` custody. Copy hashes verified; owner storage ACL showed `MnemeOwner`, Administrators and SYSTEM, but not `MnemeAgent`.
- Under `MnemeOwner`, both ciphertexts were successfully decrypted and validated: canonical plaintext archive SHA-256, entry counts, safe tar entry types/paths and internal `MANIFEST.sha256` checks all passed; exit 0. Verification used a temporary directory with exit-trap cleanup.
- In the post-cleanup owner-operated `MnemeAgent` shell, listing owner-custody directory raised `UnauthorizedAccessException` and printed **PASS: Owner custody denied**. The concealed source archive remains private; the author provenance archive is **never** made available to scorer B.
- This verification is about custodial integrity and access, not the correctness or executability of concealed cases. Fixture compilation against the implementation is an **G8** concern during blind validation, not a pre-handoff feedback loop.

## 3. Targeted author-side cleanup and inspection (owner-reported)

**Five confirmed sensitive locations removed under `MnemeAgent`:**
1. `r3-work/r3-author-heldout/concealed`;
2. `r3-work/r3-author-heldout/_authoring`;
3. `r3-work/r3-sealed-staging/plaintext-DO-NOT-DISTRIBUTE`;
4. `r3-work/r3-author-claude` (isolated author `CLAUDE_CONFIG_DIR`);
5. The author A session subtree `AppData/Local/Temp/claude/.../7bf4599d-e496-4829-941e-26ed50820b66`, including the author's script scratch.

The removal command printed **REMOVED** for all five, and subsequent targeted absence inventory was requested. Both public smoke directories and staging `ciphertext` folder were checked **PRESERVED: True**. The owner performed follow-up workspace checks: `r3-author-heldout` contained no unexpected children beyond `public`; `r3-sealed-staging` had no unexpected children beyond `ciphertext`, `public-smoke-NOT-RELEASED` and metadata-only `STAGING_README.txt`.

**History and workspace review:**
- `~/.claude`: 930 files enumerated; **0** matching filenames and **0** content matches for the recorded R3 author-session ID and characteristic R3 paths under the scan's text-file type and size limits.
- `AppData/Local/Temp/claude`: 0 files on enumerated scan.
- `~/.claude.json`: no R3-path/session references for the reviewed patterns.
- PowerShell PSReadLine history initially had R3 references; owner ran targeted in-place removal, then reported **remaining R3 references: 0**. This proves those patterns are absent from the retained history file, not that every possible concealed string was examined.
- Author worktree `git status --porcelain=v1 --untracked-files=all`: 0 changes. Only ignored file: `.mneme/task_context.json`; the owner verified exact `branch,worktree` schema, matching branch and path, all True. The file is generated by the repository's normal worktree guard and is **retained**, not treated as author leakage.
- Post-cleanup `r3-work` top-level inventory showed only `.venv`, `mneme`, `r3-author-heldout`, `r3-author-worktree`, `r3-dist`, `r3-implementation`, `r3-sealed-staging`, `r3-pip-freeze.txt`. Only the expected author-heldout and staging child entries were present.
- Earlier pre-seal access review denied `MnemeAgent` access to fourteen owner-private/earlier validation folders in the shared development root; the earlier separate synthetic probe verified no local usable owner private key and decryption refusal (encrypt exit 0, decrypt exit 2, `No secret key`).

**No remaining scorer-readable concealed R3 material was identified in the checked paths.** Neither this record nor the owner's acceptance proves system-wide forensic erasure. No unrelated worktree or configuration was deleted.

## 4. Residual limitations, review and owner decision

- Original access to a now-removed, key-looking export on a former volume had unknown historical exposure. Owner previously accepted the inability to prove lack of historical copies; this handoff does not claim key rotation.
- File searches were bounded and pattern/extension/size-based. An unreadable location or opaque cache is **not** certified clean. User-provided command outputs did not directly expose or check every alternate drive, remote backup, VSS snapshot or SSD remnant.
- Reviewer had no direct host connection and relied on human-owner-operated command outputs. These checks are operationally adequate **within the owner's accepted conditional topology and observed evidence**, not cryptographic proof of absence or an external security audit.
- Any discovered accessible hidden label, author transcript, old concealed result or usable owner secret must immediately revoke this GO and stop scorer B. If an independence condition cannot be verified, use stronger isolation instead of waiving the protocol.

**Independent review conclusion:** A different session from author A reviewed the actual reported cleanup paths, account, ACL, probe, worktree, Claude history and shell history evidence against frozen R3 §4.2. No *known* remaining accessible hidden author material was found. The human owner was explicitly asked for a distinct GO to start a new scorer B session using only the frozen public contract and public smoke. The human owner answered **YES** on 2026-10-28. This is a prospective handoff authorization, not a post-hoc claim of a passed validation.

## 5. Narrow authorization and mandatory stop points

**Authorized after this record merges:**
- Start **one new Claude Code session B**, with its own fresh `CLAUDE_CONFIG_DIR`, separate from deleted A config, in a separate new scoring-work directory. Never resume, branch/fork or reuse A history.
- Access only frozen normative ADR-034/R3 contract (including accepted amendments) and the 14 public smoke fixtures. The public smoke tar SHA-256 frozen in #703 is `feee204134fb4dd339f6efcbde9053c7d1f37a880f74f5ec411eb4cf2f5020a4`.
- Develop an **independent** R3 scorer/harness from the normative contract; demonstrate at least the frozen §3 synthetic malformed-`rule_id` negative cases and positive control, **before unblind**. No prior concealed corpora/results, D3 regression fixtures or prior scoring harness tuning.
- Pin the new B session ID, executable version, effective identity, integrity, config/work directory, isolation statement and observed remaining controls after startup. Run the required synthetic GPG/custody recheck **in actual B context before unblind**, and record results metadata-only.
- Prepare source/build/wheel/baseline/host characterization and harness/test hashes in the **pre-scoring completion record**. Merge it before the owner makes any separate unblind decision.

**Not authorized:** Opening/copying any concealed plaintext, decrypting owner ciphertext under the agent account, reading author provenance, changing labels/corpus/implementation or the frozen gates, running G1–G8 blind scoring, or claiming a PASS. Any surprise author materials encountered by B before unblind require immediate stop and owner incident review. R1/R2 and G2-1 remain **FAIL**.
