# ADR-034 G2-1 held-out corpus: freeze record (metadata only)

**Status:** **FROZEN** on 2026-10-25, by owner decision. The owner freezes
the corpus by merging this record.

**What the corpus is for.** This sealed corpus is the held-out corpus for
the G2-1 §8.D independent blind validation. It follows:

- the [G2-1 validation pre-registration](adr-034-g2-1-validation-preregistration-2026-10-25.md):
  #644 `17c58a8a`, plus Amendment 1 in #647 `7edc99bc`;
- the accepted [G2-1 charter](../plans/2026-10-24-adr-034-g2-1-behavioral-charter.md).

**What this record contains.** It contains **no** case bytes, case IDs,
labels, expected outcomes or answer-key content. The corpus stays encrypted
until the pre-scoring completion record merges and the owner decrypts for
scoring.

**What it does not use.** It is a new corpus. No M4 or v1 material was
accessed or reused.

## Frozen commitment

| Item | Value |
|---|---|
| Corpus, plaintext tar SHA-256 | `de8b70faa7ab5267628d6f488811ead48a6c088c1880872e61ec85a2bbd233f8` (391 entries: 390 corpus files and `FILES.sha256`) |
| Inner `FILES.sha256` | covers all 390 corpus files; its own SHA-256 is `67ecd146f49c290c20e97387bb8ef478817bd57ba6ad3c4a18256281f6ac2dbc` |
| Corpus, ciphertext SHA-256 | `016a6134bc71f5c531981c101373dad8c562b83da24dcd9b154644ad85205ae4` |
| Composition spec v1, hashed before any case was written | `a0b5e5ea39ab2ef69288157aff0eaf029c0a900b7c854ae3d08944b583760c47` |
| Composition spec v2, final, after Amendment 1 reconciliation | `eb7cccdcaee92a45e5b8d4c12de60b6aee4f215be08da34989ff71557df75321` |
| Encrypted to | the owner's OpenPGP key: primary `88CE4C9F66A5F3CA7F1C0A484839E24F94E4F796`, encryption subkey `C4370AB8829450C5`. Only the owner holds the private key |
| Build | deterministic tar: sorted entries, fixed mtime, uid and gid 0, no owner names. Rebuilt once, byte-identical |
| Sealed location | `C:/dev/mneme-heldout-034-g2-sealed/` (the owner's machine; never committed) |

**Authoring provenance** is kept separately and never given to the scorer.
It contains:

- the authoring scripts and the ID salt;
- both composition specs;
- the deviations log;
- the sanitized ambiguity brief;
- the author's isolation statement.

| Item | Value |
|---|---|
| Provenance plaintext tar SHA-256 | `501b111c130844d607a70b6772965463c17c98635566cd6b174df47392f59563` (12 files, with `PROVENANCE_FILES.sha256`) |
| Provenance ciphertext SHA-256 | `d8750c4ebd21515566bb35bfc2e7b8526cc9e85d27e6f7d45a0c07195ff60585`, encrypted to the same owner key |

## Owner verification

On 2026-10-25 the owner decrypted both ciphertexts on the owner's local
machine, through subkey `C4370AB8829450C5`. Each plaintext tar was written
only to `%TEMP%`, hashed, and deleted straight away. Both hashes matched:

- corpus `de8b70fa…33f8`;
- provenance `501b111c…9563`.

## Case counts

Every pre-registration §4 floor counts **concealed** cases only
(revision 2, G2V-F4). Every floor is met.

| Class | Concealed | Public smoke | Floor |
|---|---:|---:|---:|
| V | 18 | 1 | 15 |
| VP | 9 | 0 | 8 |
| C | 18 | 1 | 15 |
| US | 9 | 1 | 8 |
| UF | 10 | 1 | 8 |
| UP | 7 | 0 | 6 |
| X | 7 | 0 | 6 |
| L | 21 | 1 | 18 |
| LIT | 7 | 0 | 6 |
| W | 7 | 1 | 6 |
| P | 9 | 1 | 8 |
| **Total** | **122** | **7** | **104** |

**Public smoke cases.** There are 7, under the 10% limit, each from a
different class. They are in `public_smoke/` inside the sealed folder, for
harness development only. They are excluded from every gate denominator.

## Authoring history (metadata)

1. **Labels written from the contract only.** The corpus was written by an
   isolated author session, using only the documents the pre-registration §7
   allows. Its isolation statement is in the provenance archive.
2. **Floors confirmed under revision 2.** The author checked the corpus
   against pre-registration revision 2 and confirmed the floors. No cases
   were added and no labels changed.
3. **Owner rulings.** The owner ruled on the sanitized ambiguity brief: 13
   entries, 4 needing a ruling. The rulings became Amendment 1, merged in
   #647.
4. **Reconciliation with Amendment 1.**
   - 29 cases were relabelled.
   - 1 case moved from US to L.
   - 1 concealed US case was added.
   - The self-check then reported 0 errors.
5. **Sealing.** The corpus was sealed after #647 merged.

**Plaintext deletion.** Recorded in the deletion addendum below once the
author confirms it.

## Not authorized by this record

- Decryption for scoring. That waits for the scorer's harness PR and the
  pre-scoring completion record (pre-registration §8, steps 4 and 5).
- Giving the scorer the provenance archive.
- Any change to the corpus, the pre-registration gates or the
  implementation pin `6e26c534`.
- Any blind-validation, enforcement or production claim.

## Isolation statement (orchestrator)

The orchestrating session wrote this record from the author's metadata-only
reports and the owner's verification output. It has never seen case content,
labels or the provenance archive.
