# ADR-034 held-out corpus: v1 freeze record (metadata only)

**Status:** **FROZEN** on 2026-10-22, by owner decision. Sealed v1 is the
frozen held-out corpus for validating a future implementation of
[ADR-034](../adr/ADR-034-static-numeric-upper-bound-typed-rule.md) against
the frozen
[evaluation criteria](../plans/2026-10-21-adr-034-pre-registered-evaluation-criteria.md)
(protocol freeze `2298c946`). No v2 was produced: the corpus author confirmed
that every case, label, expected status and primary reason in v1 already
follows the 17 confirmed rulings below.

This record contains **no** case bytes, case IDs, labels, expected outcomes,
answer-key content or decrypted material. The corpus stays encrypted and
concealed from the future matcher implementer until scoring.

## Frozen commitment

| Item | Value |
|---|---|
| Archive (plaintext tar) SHA-256 | `3f7280646ded7c43f74985ec112b8bfd85122094018e3fda786b83c610495769` (deterministic GNU tar; 326 files; 1,136,640 bytes) |
| Ciphertext SHA-256 | `c7dd61224ab3f8681459503c461cefd7c6c8dc9441cfaf751592ac303e52a890` (121,075 bytes) |
| Encrypted to | Owner's OpenPGP key, primary `88CE4C9F66A5F3CA7F1C0A484839E24F94E4F796`, encryption subkey `41AC9C0FAA3454FBA5491150C4370AB8829450C5`. The private key is held only by the owner |
| W composition spec SHA-256 | `346821cb67c712b7827fb3c9f4234efb442bc2069e8fa7e36ca199592b030255` (hashed 2026-10-21T21:44:46Z) |
| Pinned contracts | ADR-034 blob `6f4ea66d` and criteria blob `7ca1f39e` at `2298c946`; CPython 3.12.10 |
| Sanitized ambiguity brief SHA-256 | `2bab4b9fa42d7481e431c062a0c668a947457aecd1b00fac1607abcfa33e5105` |

## Case counts (all frozen minimums met)

| Stratum | Count |
|---|---|
| A, scored (S1/S2/S3/S4/S5 = 9/9/10/10/10) | 48 |
| A9, applicability only | 5 |
| U, unsupported (5 per shape) | 25 |
| N1, parse failure | 3 |
| N2, non-source input | 6 |
| W, representative workload (10 per shape) | 50 |
| R, published numeric-semantics vectors (public contract tests, not blind evidence) | 18 |
| **Total** | **155** |

## Confirmed interpretations (all reading (a); no ADR-034 amendment)

| AMB | Ruling |
|---|---|
| 01 | A single unaliased module-level import of `f` is its declaration. Only a later or other binding is rebinding |
| 02 | Governed value passed by keyword, so the positional source is absent: `SOURCE_NOT_FOUND` |
| 03 | Direct `f(...)` calls anywhere in the module count, including inside function and method bodies (when not shadowed) |
| 04 | Explicit keyword arguments for other parameters don't defeat the positional source. Only star-unpacking does |
| 05 | Star-args call: `UNRECOGNIZED_FORM` |
| 06 | `f` only imported under an alias and called through it: `SOURCE_NOT_FOUND` |
| 07 | `f` shadowed by a parameter, with the function as its default, makes the whole call source `AMBIGUOUS_BINDING` |
| 08 | Symbol assigned in two conditional branches: `AMBIGUOUS_BINDING` |
| 09 | Introduced-delta input: `INCOMPLETE_SOURCE_INPUT`, decided before parsing |
| 10 | Unparseable complete file: `PARSE_FAILURE` |
| 11 | Infinite float literal: non-finite, `UNRECOGNIZED_FORM` |
| 12 | A mixed case's unknown source is identified by source kind, 1-based line and reason. Verified unique per line in all A7 cases |
| 13 | The author may choose shape-contract parameters within the criteria. The five contracts are pinned, and the only deviation is one documented A9 `exclude_paths` case |
| 14 | The author may choose R-case presentation details. Published expressions and bounds are unchanged |
| 15 | In symbol+call mode, the declared symbol is a source in its own right |
| 16 | Exclusion by an exclude selector and missing every include selector are both ADR-020 `EXCLUDED` |
| 17 | Reading the symbol elsewhere (for example as a keyword value to unrelated calls) is neither a rebinding nor a source |

## Accepted validation evidence and its limits

- **Integrity (owner, offline):** in Google Cloud Shell under a separate
  Google account, in a browser without AI extensions:
  - ciphertext and kit hashes;
  - the decrypted archive hash;
  - all 325 inner files against the sealed `FILES.sha256`;
  - the W-spec hash and its sealed timestamp.

  All passed. Cloud Shell is cloud-hosted, not offline. The decrypted files
  and the key were deleted afterwards, but provider-side erasure is not
  provable.
- **Brief completeness:** 17/17 entries, with identical IDs and severities
  (scripted).
- **Semantic fidelity:** 17/17 match on question and preferred reading. The
  owner supplied the originals, and the comparison was made by an AI session
  that is not the corpus author. This is not a human-only audit.
- **W-spec chronology:** a metadata-only extraction of the author-session
  transcript shows the spec hashed at 21:44:45Z and the first W-case write at
  21:50:46Z. The record has an unbroken parent chain and monotonic
  timestamps, and the spec was not edited after hashing. This is procedural
  evidence, not independent timestamps.

## Confidentiality conditions (binding until scoring)

- The future matcher implementer must have **no access** to:
  - the corpus-author session or its transcript, which contains the
    plaintext;
  - the orchestrating session that coordinated this work. During the
    fidelity review, two case IDs and one intended verdict were exposed to
    it;
  - the Google account used for verification.
- Both AI sessions above are permanently barred from implementing the matcher.
- Decryption for scoring happens only after the matcher implementation is
  frozen, under a separately authorized scoring step.

## Not authorized by this freeze

- Matcher implementation.
- Memory import.
- `VALID_RULE_TYPES` changes.
- Layer 1 amendment.
- Any enforcement claim.

The next milestone is the Layer 1 behavioral charter for
`FORBID_NUMERIC_ABOVE`.
