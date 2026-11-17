# ADR-034 M4 pre-scoring record (metadata only)

**Status:** **PROPOSED** on 2026-10-23. The owner accepts it by merging this
record. This is charter §9 step 3 of the
[M4 independent validation charter](../plans/2026-10-22-adr-034-m4-independent-validation-charter.md)
(#614, `d1159c89`; status #618, `a54eefda`). It pins the harness, the build,
the scoring environment and the exact scoring command **before** any
decryption for scoring.

This record contains **no** case bytes, case IDs, labels, expected outcomes,
rationales or contract text. The scorer session that wrote it has never had
access to:

- the sealed corpus or its ciphertext;
- the provenance archive;
- sealed v1;
- any other session.

The corpus stays encrypted. G1 stays FAIL (149/155).

**Governing documents:**

- the M4 charter;
- the frozen [evaluation criteria](../plans/2026-10-21-adr-034-pre-registered-evaluation-criteria.md)
  (blob `7ca1f39e`, unchanged);
- the [M4 corpus freeze record](adr-034-m4-heldout-corpus-freeze-2026-10-23.md)
  (#619, `ee780442`);
- the scoring harness PR [#621](https://github.com/MnemeHQ/mneme/pull/621).

## 1. Harness pin

The harness was merged by #621 as squash commit
**`942de7b121994647e99e9b862b44cda784c0ae84`**, after review repairs F-1 and
F-2. These are the file SHA-256 values at that commit, identical to the
reviewed PR head `79680992`:

| File | SHA-256 |
|---|---|
| `benchmarks/adr034_m4/harness.py` | `475d15ce2c88b5619889282d66d26a783ed224a8f77fd8c6a5b680ecb7dd6adb` |
| `benchmarks/adr034_m4/m4_child.py` | `84e47569d71769e517b5d9406ec881a903253f4ede52f9b563310c5963948357` |
| `benchmarks/adr034_m4/README.md` | `a99b15d7f954802dd23bc22ff7dcbb1b8c4eedac8074b7c22b2e1a918be32a01` |
| `tests/adr034_m4_synthetic_corpus.py` | `58ca391bdecb61dc977d740e70f7140c3cda1cf0d3092ec1e3a4208984185d12` |
| `tests/test_adr034_m4_harness.py` | `67ab21871270c72f929d5ac24c5a4cf5ace7813f2470bfaf2f28c3a5245d92c3` |
| `tests/test_adr034_m4_harness_old_reader.py` | `754e02f9d235039e2d3a2b36f3e0dcd3aabdfb6d0415b696874590288a9d9746` |
| `scripts/run_test_battery.py` (test classification only) | `c1d166f319d36d45b3d8b19a909751618a53b7824ea68bef417294aa9a1399ce` |

Every scoring summary reports the SHA-256 of `harness.py` and `m4_child.py`
as computed at run time (`harness_sha256`). They must equal the values above.
A mismatch, or any harness edit after decryption, invalidates the M4 blind
claim (charter §6).

## 2. Implementation and build pin

| Item | Value |
|---|---|
| Implementation commit | `f25f0e845f344944dc25d085bffafbd1855c5a7d` (charter §4) |
| `mneme/` tree | `002fdddb254267d42a3810cfea669d75700372f2`, unchanged at `942de7b1` |
| Wheel | `mneme_hq-0.10.0-py3-none-any.whl`, built with `pip wheel --no-deps` from a clean detached checkout of `f25f0e84` (removed afterwards) |
| Wheel SHA-256 | **`ea043a693dc6fd2968fe71da58ce54ee6367823d9548f22f1082e732e2cb01f4`** |
| Installed `mneme/` tree | `002fdddb254267d42a3810cfea669d75700372f2`, verified by the harness on the installed package files |
| Runtime | CPython **3.12.10** (`tags/v3.12.10:0cc8128`, MSC v.1943 64 bit (AMD64)) |
| OS | Windows 11, `Windows-11-10.0.26300-SP0` (`ver`: 10.0.26300.9711) |

The wheel build is not byte-reproducible, because zip entries carry file
timestamps. The pinned artifact is this specific wheel file. The installed
tree hash is what ties it to the pinned source.

## 3. Scoring environment

All paths are outside the repository, under `C:\dev\m4-scoring-env\`. Both
scoring runs use this one environment; the harness runs both passes in a
single invocation.

| Environment | Path |
|---|---|
| Scoring venv (pinned wheel) | `C:\dev\m4-scoring-env\scoring-venv\` |
| Old-reader venv (gate 12) | `C:\dev\m4-scoring-env\oldreader-venv\` |
| Pinned wheel | `C:\dev\m4-scoring-env\wheels\mneme_hq-0.10.0-py3-none-any.whl` |
| Old-reader wheel | `C:\dev\m4-scoring-env\oldreader-wheel\mneme_hq-0.10.0-py3-none-any.whl` |

**Scoring venv `pip freeze`.** The output file `scoring-venv.pip-freeze.txt`
has these digests:

- **SHA-256 of the bytes as written** (CRLF):
  **`255b8369c7b656cc67207fadbdd5c16183f9fdb2c4923b80e496621300d18df8`**
- SHA-256 of the same text with LF line endings, as in the block below:
  `9a1656afa634ceabc5a1029681bd12f730ee56156458f0a4becbe41e6b6675bd`

```text
annotated-types==0.8.0
anthropic==2.2.0
anyio==4.15.1
docstring_parser==0.18.0
h11==0.16.0
httpcore2==2.16.0
httpx2==2.16.0
idna==3.20
jiter==0.18.0
mneme-hq @ file:///C:/dev/m4-scoring-env/wheels/mneme_hq-0.10.0-py3-none-any.whl#sha256=ea043a693dc6fd2968fe71da58ce54ee6367823d9548f22f1082e732e2cb01f4
opentelemetry-api==1.45.1
pydantic==2.14.1
pydantic_core==2.50.1
python-dotenv==1.2.4
PyYAML==6.0.3
sniffio==1.3.1
truststore==0.10.5
typing-inspection==0.4.4
typing_extensions==4.16.0
```

**Old reader (charter §4, gate 12).** This is `mneme-hq==0.10.0` from PyPI,
installed in a separate CPython 3.12.10 venv.

| Item | Value |
|---|---|
| Old-reader wheel SHA-256 | **`fc7e0ec7191e243e998055d34e5764e473aa439ecdc40c22a969acf376ec5312`** (matches the truncated value in the G1 results record) |
| Wheel files verified against its `RECORD` | 105 |
| Old-reader venv `pip freeze`, SHA-256 of the bytes as written (CRLF) | **`d76eaff37ecacd9f08844de024c23a24a525e2aefe2fdcc087dfa1e9c6697f2c`** |
| Same, with LF line endings | `60f921ee37669e19f33024be523750a2ccaa1a1997dd7a713a7717082c764bb5` |

The old-reader freeze is identical to the scoring freeze above except for the
`mneme-hq` line:

```text
mneme-hq @ file:///C:/dev/m4-scoring-env/oldreader-wheel/mneme_hq-0.10.0-py3-none-any.whl#sha256=fc7e0ec7191e243e998055d34e5764e473aa439ecdc40c22a969acf376ec5312
```

Both builds report version `0.10.0`. The harness tells them apart by:

- the installed-tree pin;
- separate install locations;
- the absence of `mneme.numeric_rule` in the old reader;
- the old reader's wheel `RECORD` verification and its wheel SHA-256.

## 4. Environment smoke test (synthetic, not scoring)

The merged harness at `942de7b1` was run on its **synthetic** fixture corpus
(`tests/adr034_m4_synthetic_corpus.py`, no M4 case data) against exactly
these two environments.

- It used the real M4 build pins: CPython 3.12.10, tree `002fdddb`, the
  ADR-034 golden vectors and the old-reader checks. Only the corpus digests
  and counts were the fixture's.
- The driver script was `C:\dev\m4-scoring-env\smoke_synthetic.py`
  (SHA-256 `fd1e05021050ddbb7f5f0b890d4d9f42d15f2b69ce2d09457987c208ea502b25`).

| Result | Value |
|---|---|
| Overall | **PASS**: all 12 gates (1, 2, 3, 3a, 4, 5, 6, 7, 8, 9, 10, 11, 12) pass; 0 operational failures |
| Gate 9 | both run summaries byte-identical, SHA-256 `22a0495caf7b245d362f4b21fff54b07c7c19a0f646080c2f6170d773c046105` |
| Gate 11 | 4 of 4 ADR-034 golden IDs reproduced (identity function, persisted memory, check trace) |
| Gate 12 | the old reader reads its own v1 memory, and refuses the pinned v2 numeric memory (`DecisionIndexPersistenceError`, no verdict, file unchanged) |
| Smoke `summary.json` SHA-256 | `bfbc2c87369e328b80aff86a6950c1d7f927259b4c745024e7cebf7fed25c46c` |

This establishes only that the environment and harness work together. It is
not evidence about the M4 corpus.

## 5. The scoring command (pinned)

Run from a clean checkout of `942de7b1`, whose harness files match §1, with
the scoring venv's interpreter:

```text
C:\dev\m4-scoring-env\scoring-venv\Scripts\python.exe benchmarks\adr034_m4\harness.py score ^
  --corpus <DECRYPTED_CORPUS_ROOT> ^
  --case-root-template "cases/{case_id}" ^
  --w-spec W_SPEC.md ^
  --python C:\dev\m4-scoring-env\scoring-venv\Scripts\python.exe ^
  --old-reader-python C:\dev\m4-scoring-env\oldreader-venv\Scripts\python.exe ^
  --old-reader-wheel C:\dev\m4-scoring-env\oldreader-wheel\mneme_hq-0.10.0-py3-none-any.whl ^
  --out <NEW_EMPTY_OUTPUT_DIRECTORY>
```

- `<DECRYPTED_CORPUS_ROOT>` is the extracted directory that holds
  `FILES.sha256`, `manifest.jsonl` and `W_SPEC.md`.
- `--case-root-template "cases/{case_id}"` and `--w-spec W_SPEC.md` are the
  layout metadata confirmed for #621 (open questions 1–4).
- No other flag is used. In particular, `--keep-run-roots` is not used, so
  each per-run copy of the decrypted corpus is deleted after its pass.
- Exit status: `0` PASS, `1` FAIL, `2` INVALID or REFUSED.

## 6. Corpus anchors (from the freeze record)

| Item | Value |
|---|---|
| Ciphertext SHA-256 | `1d745a522217abd9f5893e6b38922c3ea0290b4f2542ff731a265d7154764052` |
| Plaintext tar SHA-256 | `c6807c70a4b6c7e172f2a54ede62021a2bbebfc5d632ec9606486d15f5e7503f` |
| `FILES.sha256` SHA-256 (195 corpus files) | `aa1f578ddefbe2480bac0bd065c65fc3fcfec2b454da81c104d15fb883fc2177` |
| `manifest.jsonl` SHA-256 (161 cases) | `65dfc5ce8e42c1c307ade336790eea6cf444a250830fe8b73450d6cc159127ee` |
| W composition spec SHA-256 | `6abeabfe9ab314ab8801381e9c11c0fa46a4a3001e266ec2416ce8826050cfd9` |

The owner checks the ciphertext and tar digests at decryption. The harness
refuses to score unless `FILES.sha256`, the manifest and the W spec match
their pins (charter §6).

## 7. Binding conditions carried forward

**Variances V-1 and V-2** (freeze record) stay disclosed and binding:

- **V-1:** the owner decrypted both archives before any harness or
  pre-scoring record existed, solely to verify their hashes.
- **V-2:** the owner did not check the 195 inner files or the W-spec bytes
  before the freeze.

**The two outstanding V-2 checks are mandatory, before the first scoring
invocation, and the harness performs them as preconditions:**

1. `FILES.sha256` must verify **195 of 195** files, with no extra files.
2. The W spec bytes must match
   `6abeabfe9ab314ab8801381e9c11c0fa46a4a3001e266ec2416ce8826050cfd9`.

Any mismatch is an operational failure. The harness records REFUSED, nothing
is scored, and the run is invalid (criteria §3). **Any M4 validation claim is
conditional on both checks passing.** The results record must disclose V-1
and V-2.

**Gate 9 normalization.** The only normalization is replacing the per-run
temporary-root path string, as it appears in the harness's JSON. Any other
normalization is a protocol deviation that invalidates the run (charter §6).

**Disclosures accepted on #621** (also written into every summary under
`disclosures`):

- **Q5, A9:** A9 is scored for applicability only, and no frozen §5 gate
  covers it. The harness reports A9 as matched k of 5, with every mismatch
  listed by case. A9 mismatches do not change PASS/FAIL, and an unmatched A9
  case is not reported as correct.
- **Q14, gate 9:** both passes run at one repeated temporary-root path. Each
  root is separately created, freshly copied and fully removed. The harness
  verifies the root is absent before each pass and after the last, so
  determinism is tested at a repeated path.
- **Q11, gate 10:** only an applicability-only A9 case with a consistent
  `EXCLUDED` trace may bind no matcher record.

## 8. Sequence (charter §9) and what this record does not authorize

1. This record is reviewed and merged by the owner.
2. **Decryption and scoring** need a **separate, explicit owner
   authorization** after that merge. **Only the owner decrypts.** The
   decrypted corpus is handed to the scorer, who runs the §5 command once.
   That single invocation performs both scoring passes in the §3 environment.
3. A metadata-only results record follows, under charter §10.

This record does **not** authorize decryption, scoring, any harness or
implementation change, or any amendment to ADR-034, the criteria, the
charters or the freeze records.

## Isolation statement

The scorer session wrote the harness (#621) and this record. It never
accessed:

- the sealed M4 corpus or its ciphertext;
- the provenance archive;
- `C:\dev\mneme-heldout-034\` or the other sealed folders;
- any `.gpg` file, or gpg itself;
- the corpus-author session or any other session's transcript.

Layout metadata for #621 (questions 1–4) reached it only as owner-relayed
summaries, which contained no case content. It built the environments in §3
from public sources: the pinned repository commit, and PyPI for the old
reader and the dependencies.
