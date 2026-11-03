# ADR-034 G2-1 R2 held-out corpus: freeze record (metadata only)

**Status:** **FROZEN** on 2026-10-27, by owner decision. The owner freezes
the corpus by merging this record.

**What the corpus is for.** This sealed corpus is the new, independently
held-out corpus for the G2-1 revalidation R2. It follows:

- the [R2 pre-registration](adr-034-g2-1-revalidation-preregistration-2026-10-26.md):
  #683 `f26000f7`, plus R2 Amendment 1 in #686 `c1748bfd`;
- the R1 pre-registration that R2 inherits
  ([`adr-034-g2-1-validation-preregistration-2026-10-25.md`](adr-034-g2-1-validation-preregistration-2026-10-25.md)),
  including its Amendments 1 and 2;
- the implementation pin `dbab816f` (tree `6cb14c2b`).

**What this record contains.** It contains **no** case bytes, case IDs,
labels, expected outcomes or answer-key content. The corpus stays encrypted
until the R2 pre-scoring completion record merges and the owner decrypts for
scoring.

**What it does not use.** It is a new corpus, written by a new author
session. No R1, M4 or v1 corpus material was accessed or reused.

## Frozen commitment

| Item | Value |
|---|---|
| Corpus, plaintext tar SHA-256 | `17a46379cfbb04ec41cc7e740a9f52ce1f94e48e154a2178987ca56af22dcfe1` (606 entries: 605 corpus files and `FILES.sha256`; root `g2-1-r2-heldout-corpus/`) |
| Inner `FILES.sha256` | covers all 605 corpus files; its own SHA-256 is `70d35226584bead131929deb41e3e3f59a5307d0ae34fe49b29426692a749c0d` |
| Corpus, ciphertext SHA-256 | `32b3510a660b997452d6fb2ff25ad8f0731ada82a8dc2093aa2930821643bf38` |
| Encrypted to | the owner's OpenPGP key: primary `88CE4C9F66A5F3CA7F1C0A484839E24F94E4F796`, encryption subkey `C4370AB8829450C5`. Only the owner holds the private key |
| Build | deterministic GNU tar: sorted entries, regular files only, no pax headers, mtime `2026-10-27T00:00:00Z`, uid and gid 0, empty owner names, mode 0644. Built twice, byte-identical |
| Sealed location | `C:/dev/mneme-heldout-034-g2r2-sealed/` (the owner's machine; never committed) |

**Authoring provenance** is kept separately and is never given to the
scorer. It contains:

- the format specification (README);
- the counts;
- the author's isolation statement;
- the sanitized ambiguity brief, with the owner's rulings and both
  reconciliations.

| Item | Value |
|---|---|
| Provenance plaintext tar SHA-256 | `858443f11ae1ce667dc1691217303fe79be2a036597ba434a7b7dba880054e2b` (4 files) |
| Provenance ciphertext SHA-256 | `a0284f4cd6b79a05d58b8204da0648bab34aeaea8cf69523ee551796fa75238a`, encrypted to the same owner key |

## Owner verification

On 2026-10-27 the owner decrypted both ciphertexts on the owner's local
machine, through subkey `C4370AB8829450C5`. Each plaintext tar was written
only to `%TEMP%`, hashed and then deleted. All four hashes matched:

- corpus ciphertext `32b3510a…3bf38`;
- provenance ciphertext `a0284f4c…5238a`;
- corpus tar `17a46379…2dcfe1`;
- provenance tar `858443f1…054e2b`.

The orchestrator also re-hashed both ciphertexts in the sealed folder.
Both matched.

## Case counts

Every R2 §4.2 floor counts **concealed** cases only. Every floor is met.

| Class | Concealed | Public smoke | Floor |
|---|---:|---:|---:|
| V | 16 | 1 | 15 |
| VP | 10 | 1 | 8 |
| C | 17 | 1 | 15 |
| US | 9 | 1 | 8 |
| UF | 10 | 1 | 8 |
| UP | 7 | 1 | 6 |
| X | 7 | 1 | 6 |
| L | 19 | 1 | 18 |
| LIT | 7 | 1 | 6 |
| W | 7 | 1 | 6 |
| P | 9 | 1 | 8 |
| SC | 15 | 1 | 10 |
| MR | 10 | 1 | 6 |
| **Total** | **143** | **13** | **120** |

**Public smoke cases.** There are 13 of 156, or 8.33%, under the 10% limit.
There is one per class. They are kept outside the sealed corpus, for
harness development only, and are excluded from every gate denominator.
They are released to the R2 scorer only after this record merges.

**Author-reported coverage, as metadata:**

- **L:** at least 2 of each of the 9 required kinds.
- **Byte variety:** at least 2 each of LF, CRLF, lone CR and non-ASCII in
  V, C and L, plus 2 empty-content L cases.
- **SC:** 4 recognized-violation, 3 recognized-clean and 7
  `AMBIGUOUS_BINDING` cases, plus 1 `PARTIAL`.
- **MR:** §7b rows 1–3, plus 2 native row-4 analogues (§4.3).

**Format note.** Every case's `expected.json` carries an additive boolean,
`g6_routed_fallback`, which marks routed-fallback cases under R2A1.6. The
R2 harness reads it. The public README documents it.

## Authoring history (metadata)

1. **Isolated authoring.** The corpus was written by a new, isolated author
   session, using only the documents R2 §7 allows. Its isolation statement
   is in the provenance archive.
   - **Disclosure accepted by the owner (R2A1.4):** the author also read
     ADR-019, a public ADR, for `FORBID_LITERAL` directive syntax.
2. **Ambiguity brief.** The author raised 12 items, AMB-R2-01 to AMB-R2-12.
   The owner's rulings are R2 Amendment 1, merged in #686 `c1748bfd`.
   - First reconciliation: 0 labels changed.
3. **Rulings revised on review.** Review of #686 led the owner to revise
   AMB-R2-01 (R2A1-F1) and the function part of AMB-R2-04 (R2A1-F2).
   - Second reconciliation: 3 concealed labels changed (L 2, SC 1), 0 public
     cases changed, every floor still met.
4. **Sealing.** The corpus was sealed after #686 merged and the orchestrator
   gave its go-ahead.

## Plaintext deletion

**Plaintext deletion (author-confirmed, 2026-10-27).** The owner had
decrypt-verified all four hashes. After that, the author deleted every
plaintext copy and confirmed each was absent:

- **The authoring folder** `C:/dev/mneme-heldout-034-g2r2/`, with
  everything in it:
  - the concealed cases;
  - `_authoring/`, which held the generator, the ID salt and the name map;
  - `_seal/`, which held the plaintext tars;
  - the original public smoke folder;
  - the top-level brief, isolation statement and counts. These are kept in
    the provenance ciphertext.
- **The author session's scratchpad.** It was emptied, and now holds 0
  entries. The author reports making no other copies.

**What "absent" means.** Absence was confirmed at the file-system level.
That is not proof of physical erasure on an SSD, and no unrecoverability
is claimed.

**Public smoke cases.** They were moved to
`C:/dev/mneme-heldout-034-g2r2-public/`. Before the source was deleted,
the copy was verified byte-identical. The folder holds:

- 57 files, covering 13 cases;
- a deterministic manifest, `PUBLIC_FILES.sha256`: sorted lines of the
  form `sha256  relpath`, with LF line endings. It has 57 entries, and all
  verified.

The manifest's SHA-256 is
`b60394c0076f41f8dd0845c6b290347522bea36d42340050686f04bc3547ab0c`. The
R2 pre-scoring completion record pins this value.

**The sealed folder.** Both ciphertexts were re-checked against
`CIPHERTEXT.sha256`, and both matched. A deletion addendum was appended to
`SEAL_RECORD.md`.

**The author's transcript.** The author session's own transcript contains
case content. It must never be shared, forked or exported.

## Not authorized by this record

- Decryption for scoring. That waits for the R2 scorer's harness PR and the
  R2 pre-scoring completion record, including the §3 host re-pin (R2
  pre-registration §8, steps 4 and 5).
- Giving the scorer the provenance archive.
- Any change to the corpus, the R2 gates or the implementation pin
  `dbab816f`.
- Any blind-validation, enforcement or production claim.

## Isolation statement (orchestrator)

The orchestrating session wrote this record from the author's
metadata-only reports and the owner's verification output. It has never
seen case content, labels or the provenance archive.
