# ADR-034 G1 held-out scoring: results record (metadata only)

**Result:** **FAIL** against the frozen protocol
([criteria](../plans/2026-10-21-adr-034-pre-registered-evaluation-criteria.md),
blob `7ca1f39e`).

- 9 of 12 gates pass, and 149 of 155 cases match the frozen key.
- All six failures are the N2 non-source cases, from one cause: Finding F-1.
- Recorded as is, under the protocol's failure policy. Nothing was tuned
  against the holdout.

This record contains no case source, labels or answer-key content.

## Run anchors

| Anchor | Value |
|---|---|
| Implementation under test (frozen) | `311744cb13b15b8b96009048e8304062187e049d` (PR [#607](https://github.com/MnemeHQ/mneme/pull/607)) |
| Contract / protocol | ADR-034 blob `6f4ea66d`; criteria blob `7ca1f39e` (protocol freeze `2298c946`); [G1 charter](../plans/2026-10-22-adr-034-g1-behavioral-charter.md) (#602) |
| Corpus | Sealed v1, archive SHA-256 `3f7280646ded7c43f74985ec112b8bfd85122094018e3fda786b83c610495769` ([freeze record](adr-034-heldout-corpus-freeze-2026-10-22.md), #600). 325/325 files matched `FILES.sha256` |
| Runtime | CPython 3.12.10, Windows 11 (10.0.26300) |
| Old reader | `mneme-hq==0.10.0` from PyPI (wheel SHA-256 `fc7e0ec7…6ec5312`) |
| Scorer | An independent session: not the corpus author, not the implementer, and not the orchestrating session |
| Decryption | By the owner only, after the implementation commit was frozen |
| Date | 2026-10-22 |

## Gates (criteria §5)

| Gate | Requirement | Result | Value |
|---|---|---|---|
| 1 | Zero misses in A and W | PASS | 0 |
| 2 | Zero false blocks in A and W | PASS | 0 |
| 3 | Zero unsafe passes | **FAIL** | 6 (all N2) |
| 3a | Every U/N case `MATCHER_UNEVALUATED` with the expected primary reason | **FAIL** | 28 of 34 (N2 0 of 6); unexpected U/N violations: 0 |
| 4 | Every A7 case: violation, `PARTIAL`, expected unknown source and reason, `evaluation_complete=false` | PASS | 3 of 3 |
| 5 | Zero wrong primary reasons | **FAIL** | 6 (all N2) |
| 6 | Coverage A = 100% | PASS | 48/48 |
| 7 | Coverage W ≥ 95% | PASS | 50/50 |
| 8 | Set R matches | PASS | 18 of 18 |
| 9 | Determinism: two byte-identical runs | PASS | identical summary SHA-256 |
| 10 | Binding completeness = 100% | PASS | 155/155 |
| 11 | Golden rule IDs (3 numeric + ADR-005 literal) | PASS | 4/4 |
| 12 | Old-reader refusal | PASS | released 0.10.0 refuses the numeric v2 memory, and never drops it silently |

**Headline:**

- **S1–S5:** "W decided 10 of 10; A decided 9 of 9 (S1, S2) or 10 of 10 (S3–S5);
  U unevaluated 5 of 5 (expected 5)".
- **Set R:** "R matched 18 of 18".
- **N1 (parse failure):** 3 of 3 correct.
- **N2 (non-source input):** 0 of 6 correct.

Operational failures: 0. Every payload passed the shipped hook trust
validator. The determinism normalization was limited to the per-run temp-root
path string.

## Finding F-1: non-source input without a target path

- **What the key expects:** the six N2 inputs (a prompt, code fragments,
  introduced deltas, stdin-style text) have no target path. They expect
  `MATCHER_UNEVALUATED` / `INCOMPLETE_SOURCE_INPUT`, per ADR-034 §6: such
  input "produces `MATCHER_UNEVALUATED` with `INCOMPLETE_SOURCE_INPUT`" and
  is "never a clean result".
- **What `311744cb` emits:** `mneme check --input <file>` with no
  `--target-path` uses the input file's own path for ADR-020 applicability.
  These inputs sat outside the rule's `include_paths`, so the numeric rule was
  `EXCLUDED`, no matcher record was produced, and the check returned a clean
  PASS (`evaluation_complete=true`, exit 0). That counts as an unsafe pass, an
  incorrect U/N outcome and a wrong primary reason.
- **Why:** charter §3 item 4 conditioned the `INCOMPLETE_SOURCE_INPUT` record
  on "an APPLIED numeric rule", while ADR-034 §6 does not. The implementation
  followed the charter.
- **Not scored (sensitivity only):** the same inputs placed inside
  `include_paths` produce the expected record. Placed outside the policy
  root, they produce path `UNKNOWN` (exit 2). Inventing a governed path was
  excluded by the owner's invocation ruling.
- **Scope of impact:** no source-file case was affected. There were no misses
  and no false blocks on any of the 98 A/W source cases.

## Disposition and claim scope

- **Fix:** F-1 is being fixed in a follow-up PR made **after** scoring. For
  numeric rules, `--input` without `--target-path` yields
  `MATCHER_UNEVALUATED` / `INCOMPLETE_SOURCE_INPUT` regardless of where the
  file sits, matching ADR-034 §6, with a charter §3 erratum. That behavior is
  verified by public regression tests, **not** by this blind holdout. The
  holdout is not re-scored, and the six N2 cases are not reused as blind
  evidence.
- **Claim:** `FORBID_NUMERIC_ABOVE` G1 whole-file audit (`--source-file`) is
  blind-validated on this synthetic held-out corpus for every stratum except
  N2:
  - A, W, U, N1 and R are all correct;
  - all A7 `PARTIAL` cases are correct;
  - determinism, binding, golden IDs and old-reader refusal all pass.
- **N2 non-source handling** is covered by the post-scoring fix and its
  public tests only.
- **Not claimed:** pre-write protection, CI enforcement, generalization beyond
  this synthetic corpus, or a full-protocol PASS.

## Custody note

The corpus was decrypted for scoring only after `311744cb` was frozen. The
scorer's per-case results stay local, outside the repository. The
confidentiality conditions in the freeze record remain in force for any
future blind evaluation built on new cases.
