# ADR-034 M4 scoring harness

The public scoring harness for the M4 independent held-out validation of the
corrected ADR-034 `FORBID_NUMERIC_ABOVE` whole-file Python audit
([charter](../../docs/plans/2026-10-22-adr-034-m4-independent-validation-charter.md)
§6, ruling B2). It scores the pinned build (`mneme/` tree `002fdddb…`) against
the decrypted M4 corpus under the
[frozen criteria](../../docs/plans/2026-10-21-adr-034-pre-registered-evaluation-criteria.md)
(blob `7ca1f39e`), with no change to any gate, threshold, denominator or
definition.

It was written before decryption, from the M4 charter, the
[M4 freeze record](../../docs/validation/adr-034-m4-heldout-corpus-freeze-2026-10-23.md),
the criteria, ADR-034, the G1 charter §3-§6 and the CLI payload. **It contains
no case data.** Its tests use a small synthetic corpus
(`tests/adr034_m4_synthetic_corpus.py`) written from ADR-034 and the criteria
alone.

Charter §6: after decryption this harness is not edited. A harness defect
found then that would change any scored outcome, metric or gate invalidates
the M4 blind claim.

## Files

| File | Role |
|---|---|
| `harness.py` | Preconditions, the two scoring passes, scoring, gates, summaries |
| `m4_child.py` | Child entry point: every call into the build under test and into the old reader runs through it |

## Running it (scoring step only; not authorized by the harness PR)

```text
python benchmarks/adr034_m4/harness.py score \
  --corpus <decrypted corpus root, the directory holding FILES.sha256> \
  --case-root-template "<each case's policy root, relative to the corpus root>" \
  --old-reader-python <python of the separate mneme-hq==0.10.0 environment> \
  --old-reader-wheel <path>/mneme_hq-0.10.0-py3-none-any.whl \
  --python <python of the scoring environment with the pinned wheel installed> \
  --out <new or empty directory>
```

Exit status: `0` PASS, `1` FAIL, `2` INVALID or REFUSED. Results are written
to `--out`:

- `run-1/cases.jsonl`, `run-2/cases.jsonl`: one record per case, with every
  step's argv, exit code and stderr, the full check payload, the trust
  validator result, the observation and its score. Private evidence (charter
  §10 item 6): these hold absolute paths and full payloads.
- `run-1/summary.json`, `run-2/summary.json`: the run summaries compared by
  gate 9.
- `summary.json`: the result, every gate, the headline, every metric, the
  failure list and both summary SHA-256 values.

`--w-spec <relative path>` names the W composition spec; by default it is
located as the one corpus file whose SHA-256 is the frozen W-spec digest.
`--keep-run-roots` keeps the per-run corpus copies (decrypted case bytes);
by default they are deleted after each pass.

## Preconditions (any failure refuses to score)

Checked before any case runs; a refusal is recorded in `summary.json`.

1. The scoring interpreter is **CPython 3.12.10** exactly.
2. The git tree hash of the `mneme/` package that interpreter actually
   imports is **`002fdddb254267d42a3810cfea669d75700372f2`**. The hash is
   computed from the files on disk (git blob and tree objects, mode 100644,
   `__pycache__` skipped), so an installed wheel is checked as installed.
   It is re-checked at the start and end of each pass.
3. `FILES.sha256` at the corpus root has digest `aa1f578d…2177` and verifies
   **195 of 195** entries (variance V-2, first check).
4. The corpus holds exactly those 195 files plus `FILES.sha256` (the freeze
   record's 196 regular files), and no symlinks or special files.
5. `manifest.jsonl` has the frozen digest `65dfc5ce…27ee`.
6. The W spec matches **`6abeabfe9ab314ab8801381e9c11c0fa46a4a3001e266ec2416ce8826050cfd9`**
   (variance V-2, second check), re-hashed from its bytes.
7. Every manifest record has the charter §6 fields and vocabulary, and
   follows the charter §5 invocation matrix.
8. The case counts equal the freeze record: 161 cases; A 48 scored
   (S1-S5 = 9/9/10/10/10, A1-A8 = 4/6/5/5/5/10/3/10) plus A9 5 (one per
   shape); U 25 (5 per shape; U1-U4 = 10/5/5/5); N1 3, N2a 8 (2 per L1-L4),
   N2b 4; W 50 (10 per shape); set R R1-R18 once each.
9. Every case's policy root (from `--case-root-template`) is an existing,
   unshared directory without a memory file, and each contract directory and
   input file exists.
10. The old reader reports distribution `mneme-hq` 0.10.0, has no
    `mneme.numeric_rule` module, imports a different `mneme/` from the build
    under test, and its installed files match the given wheel's `RECORD`
    hashes, with no extra files. The wheel's full SHA-256 is recorded.

Each pass also re-verifies `FILES.sha256` on its own copy of the corpus.

## One pass

Each pass creates a fresh temporary root (one path, reused by both passes
and deleted after each), copies the corpus into it and runs every case
there, so the decrypted corpus is never written to. Per case (charter §5,
freeze record "harness consequence"):

```text
mneme init --path <case>/.mneme/project_memory.json
mneme adr import <contract_dir> --memory <case>/.mneme/project_memory.json --apply
mneme check --memory <case>/.mneme/project_memory.json --query "audit" --mode strict --json <transport>
```

| Case | Transport |
|---|---|
| A (A1-A9), U, N1, W, R | `--source-file <path>` |
| N2a | `--input <path>`, no `--target-path` |
| N2b | `--input <path> --target-path <case>/<target_path>` |

All paths are passed absolute. Manifest `path` and `contract` resolve
against the corpus root and `target_path` against the case's policy root
(ruling M4-04). A relative `--target-path` would otherwise be resolved
against the working directory. An init or import failure, a check timeout,
a payload the shipped hook trust validator (`assess_verdict`, strict) rejects,
or a payload without exactly one `FORBID_NUMERIC_ABOVE` trace is an
**operational failure**, and any operational failure makes the run INVALID
(criteria §3).

Then gate 11 and gate 12 run inside the same root.

**Child processes.** The harness never imports `mneme`. Every call runs as
`<python> -P m4_child.py <command>`. `cli` runs `mneme.cli` through `runpy`,
exactly as `python -m mneme.cli`; `probe` reports the imported package;
`trust` applies the shipped hook validator; `identity` calls the shipped
`rule_identity`. Each child has an audit hook that denies name resolution and
connections to anything but loopback. Each runs with `PYTHON*`, `MNEME_*` and
`VIRTUAL_ENV` removed from the environment, and with an empty working
directory (so `mneme check`'s default `--adr-dir docs/adr` is absent and its
warn-only freshness diagnostics stay empty). `PYTHONHASHSEED` is deliberately
not fixed, so gate 9 can catch hash-order nondeterminism.

## Scoring definitions

The observed fields are those of the single numeric trace, exactly as
emitted. `UNKNOWN` is never normalized (M4-02). Each case gets one observed
result:

| Result | Trace |
|---|---|
| `VIOLATION`, `NO_VIOLATION`, `UNEVALUATED` | its `matcher_outcome` |
| `EXCLUDED` | no matcher record, applicability `EXCLUDED` (a clean result) |
| `PATH_UNKNOWN` | no matcher record, applicability `UNKNOWN` (exit 2, not a clean result) |

Expectations: set R is scored against the criteria §2.6a table, by the R
index in `shape`. U and N cases expect `MATCHER_UNEVALUATED` with the
manifest's primary reason. Every other case uses its manifest label.

| Criteria item | Implemented as |
|---|---|
| Miss | A1-A8 or W, label violation, result not `VIOLATION` |
| False block | A1-A8 or W, label benign, result `VIOLATION` |
| Unsafe pass | any U or N case, or any case labelled unevaluated, whose result is `NO_VIOLATION` or `EXCLUDED` |
| Unexpected U/N violation | U or N, result `VIOLATION` |
| Wrong primary reason | U, N, or A/W labelled unevaluated, whose `primary_reason` differs (including `null`) |
| Decided (coverage) | applicability `APPLIED` and result `VIOLATION` or `NO_VIOLATION`; a `PARTIAL` violation is decided |
| Unevaluated rates | result `UNEVALUATED`, over violation and benign labels in A+W, and separately over U and N |
| Binding completeness | subject digest, `rule_id`, `decision_version_id`, applicability, `matcher_status`, `matcher_outcome`, a `primary_reason` field and the same subject digest on the trace; any numeric violation joins that trace. The **only** exemption from the matcher fields is an applicability-only A9 case whose trace is a consistent `EXCLUDED` result with no numeric violation (ruling Q11) |
| Gate 3a | every U and N case: `matcher_status` `MATCHER_UNEVALUATED`, `matcher_outcome` `UNEVALUATED` and the expected primary reason; a decided outcome or an inconsistent status/outcome pair fails |
| Gate 4 | every A7 case: `VIOLATION`, `PARTIAL`, `evaluation_complete=false`, the expected primary reason, and `unknown_sources` equal to the expected list as a multiset of `(kind, line, reason)` |
| Gate 7 | decided W / W cases >= 95/100, compared exactly |
| Gate 8 | all 18 set R cases match outcome and, where unevaluated, reason |
| Gate 9 | the two run summaries are byte-identical after replacing the run-root string |
| Gate 11 | each ADR-034 §5 vector reproduces three ways: the shipped `rule_identity`, the persisted memory after a real import, and the check trace (plus the canonical value text) |
| Gate 12 | 0.10.0 reads its own v1 literal memory (control); on the pinned build's v2 numeric memory it exits non-zero, prints no verdict payload, raises `DecisionIndexPersistenceError` and leaves the file unchanged |

**A9 (ruling Q5).** A9 is scored for applicability only, and no frozen §5
gate covers A9 correctness; the harness adds none. `a9_applicability`
(matched k of 5, `gating: false`) and an `a9_applicability_mismatch` row for
every mismatch are always reported, even when all twelve gates pass. An
unmatched A9 case is not correct.

Reported but never gating: A9 applicability (matched k of 5), N2
applicability per case, `evaluation_complete` outside A7, matcher status
against the manifest, subject digest against the input bytes, the U and N
outcome counts, and the manifest label findings.

The **headline** follows criteria §5: per shape, `W decided X of 10; A decided
Y of N_A; U unevaluated Z of 5 (expected 5).`, and `R matched M of 18.` The
**failure list** has one row per (case, classification), by opaque `case_id`,
with the charter §10 fields: stratum, category, shape, classification,
expected and observed matcher status, outcome and primary reason, and for N2
the invocation form and location. No case source, rationale or label text
is included.

**Result:** REFUSED if a precondition fails; INVALID on any operational
failure; PASS only if all twelve gates pass; otherwise FAIL.

## Gate 9 normalization

Normalization replaces only the per-run temporary root path string, as it
appears in the JSON the harness writes. One N2a L4 diagnostic quotes the
input path with Python `repr`, which spells the root a second way. Rather
than widen normalization, both passes use the **same** root path, created
fresh and removed each time, so the summaries are expected to be
byte-identical even before normalization. Both raw and normalized digests
are reported.

Disclosure (ruling Q14): determinism is therefore tested at a repeated path.
This is valid only because each run root is separately created, freshly
copied and fully removed. The harness refuses, and the run is INVALID, if the
root exists before either pass or after the last one.

Every summary carries these A9, binding and gate 9 statements under
`disclosures`.

## Tests

`tests/test_adr034_m4_harness.py` covers:

- every gate, both failing and passing;
- every precondition refusal;
- the N2a and N2b transports;
- A7 partial handling;
- the normalization limit.

It also runs a two-pass end-to-end score of the synthetic corpus against the
pinned build in the repository. It is main-only (`GATE_EXCLUSIONS`).
`tests/test_adr034_m4_harness_old_reader.py` runs the full protocol including
gate 12. It is skipped unless `MNEME_M4_OLD_READER_PYTHON` and
`MNEME_M4_OLD_READER_WHEEL` point at a `mneme-hq==0.10.0` environment and its
wheel.
