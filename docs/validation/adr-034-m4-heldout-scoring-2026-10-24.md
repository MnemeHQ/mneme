# ADR-034 M4 held-out scoring: results record (metadata only)

**Result:** **PASS** against the frozen protocol
([criteria](../plans/2026-10-21-adr-034-pre-registered-evaluation-criteria.md),
blob `7ca1f39e`, unchanged).

- All 12 gates pass, including 3a, and 161 of 161 cases match.
- There were 0 operational failures and no failure rows.
- Both mandatory V-2 integrity checks passed before the first scoring
  invocation.

This is the charter §10 artifact 5 for the
[M4 independent validation charter](../plans/2026-10-22-adr-034-m4-independent-validation-charter.md)
(#614, `d1159c89`; status #618). It contains no case source, labels,
rationales, contract text or answer-key content.

**What the result means.** The pinned G1 Python whole-file audit passes the
frozen protocol on the M4 synthetic corpus (charter §1). Nothing broader is
claimed; see "Claim scope".

## Run anchors

| Anchor | Value |
|---|---|
| Implementation under test | `f25f0e845f344944dc25d085bffafbd1855c5a7d`; `mneme/` tree `002fdddb254267d42a3810cfea669d75700372f2`, verified on the installed package at the start and end of each pass |
| Wheel | `mneme_hq-0.10.0-py3-none-any.whl`, SHA-256 `ea043a693dc6fd2968fe71da58ce54ee6367823d9548f22f1082e732e2cb01f4` |
| Harness | #621, squash `942de7b121994647e99e9b862b44cda784c0ae84`; detached clean checkout. `harness.py` `475d15ce2c88b5619889282d66d26a783ed224a8f77fd8c6a5b680ecb7dd6adb` and `m4_child.py` `84e47569d71769e517b5d9406ec881a903253f4ede52f9b563310c5963948357`, verified before the run and reported by the harness at run time. All seven pinned files matched |
| Pre-scoring record | [`adr-034-m4-pre-scoring-record-2026-10-23.md`](adr-034-m4-pre-scoring-record-2026-10-23.md) (merged `40f46186`, blob `b6370489`); the pinned scoring command was run unmodified, once |
| Scoring environment | CPython 3.12.10, Windows 11 (`Windows-11-10.0.26300-SP0`). Scoring venv `pip freeze` SHA-256 `255b8369c7b656cc67207fadbdd5c16183f9fdb2c4923b80e496621300d18df8`, re-verified immediately before the run |
| Old reader (gate 12) | `mneme-hq==0.10.0`, wheel SHA-256 `fc7e0ec7191e243e998055d34e5764e473aa439ecdc40c22a969acf376ec5312`; 105 installed files verified against the wheel `RECORD`. Venv `pip freeze` SHA-256 `d76eaff37ecacd9f08844de024c23a24a525e2aefe2fdcc087dfa1e9c6697f2c`, re-verified |
| Corpus | [freeze record](adr-034-m4-heldout-corpus-freeze-2026-10-23.md) (#619, `ee780442`). Ciphertext `1d745a522217abd9f5893e6b38922c3ea0290b4f2542ff731a265d7154764052`; plaintext tar `c6807c70a4b6c7e172f2a54ede62021a2bbebfc5d632ec9606486d15f5e7503f` (owner-verified at decryption) |
| Corpus integrity (harness preconditions) | `FILES.sha256` `aa1f578ddefbe2480bac0bd065c65fc3fcfec2b454da81c104d15fb883fc2177`, **195 of 195 OK**; 196 regular files, no extra files, no symlinks. `manifest.jsonl` `65dfc5ce8e42c1c307ade336790eea6cf444a250830fe8b73450d6cc159127ee`; 161 cases, frozen counts matched. W spec `W_SPEC.md` **matched** `6abeabfe9ab314ab8801381e9c11c0fa46a4a3001e266ec2416ce8826050cfd9` |
| Invocation | `--case-root-template "cases/{case_id}"`, `--w-spec W_SPEC.md`, exactly as pinned |
| Run window (UTC) | 2026-10-24T13:02:24Z to 13:09:43Z, both passes in one invocation |
| Decryption | By the owner only, after the pre-scoring record merged and under the step 4 authorization. The plaintext tar matched before extraction and was then shredded |
| Scorer | An independent session: not the corpus author, the implementer or the orchestrating session |

## Gates (criteria §5)

| Gate | Requirement | Result | Value |
|---|---|---|---|
| 1 | Zero misses in A and W | PASS | 0 |
| 2 | Zero false blocks in A and W | PASS | 0 |
| 3 | Zero unsafe passes | PASS | 0 |
| 3a | Every U/N case `MATCHER_UNEVALUATED` with the expected primary reason | PASS | 40 of 40 (U 25, N 15); unexpected U/N violations: 0 |
| 4 | Every A7 case: violation, `PARTIAL`, expected unknown sources and primary reason, `evaluation_complete=false` | PASS | 3 of 3 |
| 5 | Zero wrong primary reasons | PASS | 0 |
| 6 | Coverage A = 100% | PASS | 48/48 |
| 7 | Coverage W ≥ 95% | PASS | 50/50 |
| 8 | Set R matches | PASS | 18 of 18 (unevaluated-reason mismatches: 0) |
| 9 | Determinism: two byte-identical runs | PASS | identical summary SHA-256 (below) |
| 10 | Binding completeness = 100% | PASS | 161/161 |
| 11 | Golden rule IDs (3 numeric + ADR-005 literal), each by identity function, persisted memory and check trace | PASS | 4/4; `FORBID_LITERAL` ids stable |
| 12 | Old-reader refusal | PASS | 0.10.0 reads its own v1 memory (control). It refuses the pinned v2 numeric memory with `DecisionIndexPersistenceError`: no verdict, file unchanged |

**Headline (criteria §5 wording):**

- **S1:** "W decided 10 of 10; A decided 9 of 9; U unevaluated 5 of 5 (expected 5)."
- **S2:** "W decided 10 of 10; A decided 9 of 9; U unevaluated 5 of 5 (expected 5)."
- **S3:** "W decided 10 of 10; A decided 10 of 10; U unevaluated 5 of 5 (expected 5)."
- **S4:** "W decided 10 of 10; A decided 10 of 10; U unevaluated 5 of 5 (expected 5)."
- **S5:** "W decided 10 of 10; A decided 10 of 10; U unevaluated 5 of 5 (expected 5)."
- **Set R:** "R matched 18 of 18."

**Operational failures: 0.** Every payload passed the shipped hook trust
validator.

**Summary digests:**

| Summary | SHA-256 |
|---|---|
| Run 1 `summary.json` | `b12fde7783fb5c196dede5650fb8cabe242eb3370256db6b5ae2e8e9a69f3d4a` |
| Run 2 `summary.json` | `b12fde7783fb5c196dede5650fb8cabe242eb3370256db6b5ae2e8e9a69f3d4a` |
| Normalized, both runs | `fa4298ba0038d6cf0633b6373eee8e4398d325015e865fd63768fd8a345f5e0b` |
| Per-case `cases.jsonl`, both runs | `bed47f659e22c6361610d838f45741588838a30a9733985de8524c940ca0daba` |
| Final `summary.json` | `99154a9e12e1cf1baf9da1a6aa2a750ede5bbcf8dea3ef2b33f5d0adf21139c2` |

The per-case files were byte-identical across the two runs. The normalized
digest differs from the raw one only because the summary records its own
run-root string (Q14 below).

## Metrics (criteria §4)

**Per stratum.** Observed results are the matcher outcome, or `EXCLUDED` for
applicability-only cases.

| Stratum | Cases | Misses | False blocks | Unsafe passes | Unexpected U/N violations | Wrong primary reasons | Coverage | Binding | Observed results |
|---|---|---|---|---|---|---|---|---|---|
| A | 53 (48 scored + 5 A9) | 0 | 0 | 0 | – | 0 | A 48/48 | 53/53 | 23 VIOLATION, 25 NO_VIOLATION, 5 EXCLUDED (A9) |
| U | 25 | – | – | 0 | 0 | 0 | – | 25/25 | 25 UNEVALUATED |
| N | 15 (N1 3, N2a 8, N2b 4) | – | – | 0 | 0 | 0 | – | 15/15 | 15 UNEVALUATED |
| W | 50 | 0 | 0 | 0 | – | 0 | W 50/50 | 50/50 | 15 VIOLATION, 35 NO_VIOLATION |
| R | 18 | – | – | 0 | – | – | – | 18/18 | 4 VIOLATION, 8 NO_VIOLATION, 6 UNEVALUATED |
| **All** | **161** | **0** | **0** | **0** | **0** | **0** | | **161/161** | |

**By category:**

| Category | Results |
|---|---|
| A1, A2, A3, A5, A7 | 4, 6, 5, 5 and 3 violations, all decided |
| A4, A6, A8 | 5, 10 and 10 no-violation results, all credited (APPLIED, trusted, complete source) |
| U1, U2, U3, U4 | 10, 5, 5 and 5 unevaluated |
| N1 | 3 of 3 unevaluated |
| N2a | 8 of 8 unevaluated |
| N2b | 4 of 4 unevaluated |

Per shape, every scored stratum has 0 misses, 0 false blocks, 0 unsafe
passes and 0 wrong reasons; the headline gives the per-shape coverage.

**Aggregate unevaluated rates (reported, never a gate):**

- violation labels across A+W: 0/38;
- benign labels across A+W: 0/60;
- U: 25/25;
- N: 15/15.

**Other diagnostics (reported, not scored):**

- **Subject digests:** equal to the exact input bytes for 149/149
  `--source-file` cases and 12/12 `--input` cases.
- **Matcher status** equals the manifest's expected status for 161/161
  cases.
- **Manifest findings:** 5 informational findings only. These are the W label
  mix per shape, 7 within and 3 above `max` for each of S1–S5, matching the
  freeze record. There were no label inconsistencies.

## Failures (criteria §6, charter §10)

**None.** There is no miss, false block, unsafe pass, unexpected U/N
violation, wrong primary reason, A7 mismatch, set R mismatch, undecided A/W
case or binding gap. The per-case failure list is therefore empty.

**A9 (disclosure Q5).** A9 is scored for applicability only, and no frozen
§5 gate covers A9 correctness. A9 applicability matched **5 of 5**: each was
`EXCLUDED`. No A9 mismatch occurred, so no A9 finding is listed.

**N2 applicability (recorded, not scored; charter §5, M4-02).** The values
below are as emitted; `UNKNOWN` was not normalized. Every N2 case's scored
outcome was `MATCHER_UNEVALUATED` / `INCOMPLETE_SOURCE_INPUT`.

| N2 form | Location | Applicability |
|---|---|---|
| N2a | L1 (2 cases) | APPLIED |
| N2a | L2 (2 cases) | EXCLUDED |
| N2a | L3 (2 cases) | EXCLUDED |
| N2a | L4 (2 cases) | UNKNOWN |
| N2b | n/a (4 cases) | APPLIED |

## Integrity checks and variances

**V-2 is satisfied.** The two checks it left outstanding ran as harness
preconditions before the first scoring invocation. Both passed:

1. `FILES.sha256` verified **195 of 195** files, with no extra or special
   files.
2. The W spec bytes matched
   `6abeabfe9ab314ab8801381e9c11c0fa46a4a3001e266ec2416ce8826050cfd9`.

The M4 claim's condition on these checks (freeze record, "What stays
binding" item 3) is met.

**V-1 and V-2 are disclosed** as owner-accepted procedural variances:

- **V-1:** the owner decrypted both archives once each, solely to verify
  their hashes, before any harness or pre-scoring record existed. Nothing was
  extracted or inspected at that point. A plaintext exposure window on the
  owner's machine existed from authoring until the owner's shred on
  2026-10-23.
- **V-2:** the owner initially verified only the ciphertext and tar hashes.
  The inner-file and W-spec checks were deferred and then performed by the
  harness, as above.

Neither variance changed any gate, label or implementation behavior.

**Disclosure Q14 (gate 9).** Both passes ran at the same temporary-root
path. Each root was separately created, freshly copied from the corpus and
fully removed. The harness verified that the root was absent before each
pass and after the last, so determinism was tested at a repeated path. The
only normalization is replacing the run-root string (charter §6). Because
the path was shared, the raw summaries are identical as well.

**Disclosure Q11 (gate 10).** Only applicability-only A9 cases with a
consistent `EXCLUDED` trace may bind no matcher record. All 5 such cases
carried the subject digest, `rule_id`, decision version and applicability.

**No changes.** Between the pre-scoring record and this result, nothing in
the harness, corpus, manifest or implementation was edited, and nothing was
rerun with modified arguments. The command ran exactly once.

## Claim scope (charter §1, §11; criteria §6)

- **Claimed:** the pinned G1 Python whole-file audit (`FORBID_NUMERIC_ABOVE`,
  `mneme check --source-file`, implementation `f25f0e84`) passes the frozen
  protocol on the M4 synthetic corpus.
- **Not claimed:** pre-write (G2) protection, CI enforcement, generalization
  to real repositories or beyond the synthetic corpus, other languages, or any
  production enforcement claim.
- **G1 stays FAIL** (149/155, finding F-1). M4 does not edit, re-score or
  reinterpret the G1 record.
- **Blindness is partial.** F-1 and its correction were public before M4.
  "Blind" means the implementation was not fitted to these case bytes or
  labels.
- **The order is inverted.** The implementation existed before the corpus.
  Independence was enforced on the corpus author's reading instead (charter
  §7).
- **These are AI sessions under one owner.** The corpus author and the
  #607/#613 implementers share a model family, so their errors may be
  correlated.
- **No stdin transport.** Stdin-style text was represented as `--input`
  files.
- **Out of scope here (charter §11).** With numeric rules in memory,
  `mneme check --input` without `--target-path` exits 2 for every file. That
  matters for warn-mode governance checks.

**Private evidence (charter §10 item 6).** The per-case JSONL with the full
ADR-029 binding of each verdict, and both raw summaries, stay in owner
custody outside the repository.

## Not authorized by this record

- Any enforcement or production claim beyond the scope above.
- Activation of `FORBID_NUMERIC_ABOVE` in any repository's memory.
- Any amendment to ADR-034, the criteria, the G1 or M4 charters, the freeze
  records or the G1 results record.
- G2 pre-write evaluation or CI integration.
