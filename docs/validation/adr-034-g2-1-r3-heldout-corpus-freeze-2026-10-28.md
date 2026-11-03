# ADR-034 G2-1 R3 held-out corpus: post-seal freeze record

**Date:** 2026-10-28  
**Status:** OWNER DECRYPT-VERIFIED; **freeze takes effect on merge**.  
**Authorization:** R3 preregistration PR #699 (`6d86358e66734556400d92f9cbe28194a9763ac5`); accepted pre-unblind AT-SI amendment PR #701 (`e5b968ce313407f8caf55529b83e47e8b3eb781d`); pre-seal custody GO PR #702 (`390c649c371bb5f37af79fa5f78e0d0f241e67b0`).

This metadata-only record contains **no concealed case bytes, case identities, labels, author scratch or private key material**. It is a commitment to a newly authored held-out corpus, not a blind-scoring result.

## Frozen corpus and owner-only provenance

| Item | SHA-256 / observation |
|---|---|
| Concealed corpus plaintext deterministic tar | `3d468d2fc36cc32ad067f13035ccc44f9493ba7032fd41f069217486a88f61eb` |
| Concealed corpus owner-key ciphertext | `19846963bc53cb4e23a7d535ca1d6f970dfae9eabdf7364998e2809ede5e02d0` |
| Owner-only author provenance plaintext tar | `52f56cd608226fc2e45c9948f71a442ffc597fb944afd655917cf7572228c7e4` |
| Owner-only author provenance ciphertext | `07d0b06f3c11a3b67c280bb4b97aeca513ebd28ff3cdf7cdcf11cf3b46f7f17d` |
| Public smoke, separate unencrypted deterministic tar | `feee204134fb4dd339f6efcbde9053c7d1f37a880f74f5ec411eb4cf2f5020a4` |

The author reported normalized, sorted USTAR archives with zeroed timestamps and owner IDs, empty owner names, regular file mode `0644`, directory mode `0755`, and a sorted internal `MANIFEST.sha256` for each. The author built each archive twice and rechecked it in a separate process, with matching digests. The ciphertext was addressed only to the owner encryption subkey `C4370AB8829450C5`, without a symmetric-encryption packet. The author holds no decryption key.

**Archive inventory:** concealed corpus: 150 case files in 150 folders and 302 tar entries; provenance: 22 files in 4 folders and 28 tar entries; separate public smoke: 14 cases and 31 tar entries. The internal manifest files are included in the respective entry counts. Authoring provenance includes the generator, independently derived labels' source materials, ID salt/name map, isolation statement and superseded author-only cases, and is **not** supplied to scorer B.

## Frozen class distribution

| Class | Concealed | Public smoke |
|---|---:|---:|
| V | 16 | 1 |
| VP | 9 | 1 |
| C | 16 | 1 |
| US | 9 | 1 |
| UF | 11 | 1 |
| UP | 7 | 1 |
| X | 7 | 1 |
| L | 22 | 1 |
| LIT | 7 | 1 |
| W | 7 | 1 |
| P | 9 | 1 |
| SC | 14 | 1 |
| MR | 8 | 1 |
| AT | 8 | 1 |
| **Total** | **150** | **14** |

AT concealed subclasses: AT-S0 2, AT-SI 2, AT-SX 2, AT-W0 2. Public smoke represents 14/164 = 8.54% of the complete set and counts toward **no** concealed floor or scoring gate. Every mandated class minimum was marked satisfied by the author's independent structural review.

## Owner decrypt-verification

The owner transferred **only** the two ciphertext archives into the private-key custodian's restricted storage, verified both ciphertext SHA-256 digests, and checked the destination ACL. Only `MnemeOwner`, Administrators and SYSTEM have access; `MnemeAgent` has no access through that ACL.

The owner then ran the archive verification under the **`MnemeOwner`** account (after an earlier attempt under `MnemeAgent` correctly failed to access the owner-only directory). Both archives decrypted successfully in temporary owner-controlled storage.

For **each** archive, the verification script confirmed:
- Recovered plaintext tar SHA-256 matched the frozen digest above.
- Entry count matched the author-reported 302 (corpus) / 28 (provenance).
- No absolute or parent-directory-traversing tar member paths were present and no unsupported tar entry types were accepted by the validation checks.
- The extracted internal `MANIFEST.sha256` passed `sha256sum --status -c`.
- Owner verification reported `PASS` and PowerShell exit code **0**.
- Temporary verification plaintext was subject to a shell exit trap for cleanup.

This verifies cryptographic integrity and recoverability. It does **not** establish that fixture ADRs compile, that the application behaves as labelled, or that G1–G8 passed.

## Isolation and remaining handoff work

- Author A used the documented new Claude session and frozen author worktree, and reported no use of the D3 implementation for labels, no access to earlier held-out corpora and no Mneme execution during corpus authoring.
- Pre-seal synthetic isolation checks were completed for the actual author/sealer session and for an independent, synthetic-only PowerShell/Git Bash probe under the intended scorer Windows account. Both had no usable private key and failed owner-key synthetic decryption. The human owner explicitly accepted recorded residual limitations and approved **sealing only**.
- **The original concealed plaintext, `_authoring/` generator and labels, author-session transcripts/scratchpad, and plaintext tar staging still exist under the author Windows identity**. They must not be accessible to scorer B.
- Public smoke remains separate and **not released**. The scored corpus remains owner-held and encrypted.
- The owner must now authorize and supervise **targeted cleanup and verification**, while retaining the owner-only ciphertext, audit evidence and required public smoke. A separate verifier must document absence/inaccessibility of author content and the owner must issue a **new, distinct scorer-handoff GO/NO-GO** before any independent scorer session starts.
- The future scorer must pin its host, builds and independent harness, including public malformed-`rule_id` negatives, **before owner-authorized unblinding**.
- No G1–G8 result has yet been observed. R1 and R2 remain **FAIL**, and G2-1 remains **FAIL**. No retrospective PASS is claimed.

## Not authorized by this record

No corpus change, reopening of hidden labels, author/scorer transcript sharing, deletion of owner-held ciphertext, D3 implementation change, scorer startup, unblind, scoring, or R3 PASS is authorized by merging this metadata-only record.
