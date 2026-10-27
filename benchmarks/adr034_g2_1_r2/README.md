# ADR-034 G2-1 R2 scoring harness

The scoring harness for the G2-1 revalidation R2. It scores the corrected
build `dbab816f` (G2-1 plus D1 and D2) against the sealed R2 held-out corpus.
It follows these frozen records:

- the [R2 pre-registration](../../docs/validation/adr-034-g2-1-revalidation-preregistration-2026-10-26.md),
  including revision 2 (R2V-F1 to R2V-F3) and Amendment 1 (R2A1.1 to R2A1.7);
- the [R1 pre-registration](../../docs/validation/adr-034-g2-1-validation-preregistration-2026-10-25.md)
  that R2 inherits, including revision 2 and Amendments 1 and 2;
- the [R2 freeze record](../../docs/validation/adr-034-g2-1-r2-heldout-corpus-freeze-2026-10-27.md)
  (#687).

It implements gates G1 to G8 as R2 §5 restates them, the G2V-F2 symlink rule
and the §6 failure policy. No gate, class, denominator or definition is
changed.

**Who wrote it, and from what.** The R2 scorer session wrote it before
decryption. Sources read:

- the three records above;
- ADR-034, §3a, §6a, §7a and §7b;
- the §8.B live-host record (#646), for the host identity;
- the R2 public smoke folder `C:/dev/mneme-heldout-034-g2r2-public/`
  (README, MANIFEST and the 13 cases), after its manifest was verified;
- the pinned hook source at `dbab816f`, for its interface only: the entry
  point, the environment seams, the evidence record fields and the three
  evidence functions;
- the pinned R1 harness `benchmarks/adr034_g2_1/`. Code was copied from it;
  it is not imported or modified.

**What it contains.** No concealed case data. Its unit tests use synthetic
cases the scorer wrote (`tests/adr034_g2_1_r2_synthetic_corpus.py`). An
opt-in test runs the 13 public smoke cases through the pinned builds; those
cases are not copied into this repository.

**After decryption,** the harness is not edited (pre-registration §6). A
harness fix then voids blind status for that run.

## Files

| File | Role |
|---|---|
| `harness.py` | `build`, `probe-symlinks` and `score`: preconditions, fixtures, both passes, gates, summaries |
| `observe_shim/sitecustomize.py` | Observation shim, copied from R1 with its own log variable (`MNEME_G2R2_OBSERVE_LOG`) |

## Commands

```text
python benchmarks/adr034_g2_1_r2/harness.py build --out <new dir> --python <CPython 3.12.10>
python benchmarks/adr034_g2_1_r2/harness.py probe-symlinks [--dir <dir>]
python benchmarks/adr034_g2_1_r2/harness.py score \
  --corpus <decrypted corpus root, the directory holding FILES.sha256> \
  --impl-python <env python, dbab816f> --impl-wheel <its wheel> \
  --baseline-python <env python, f8591102> --baseline-wheel <its wheel> \
  --host-version <pinned host version> --host-sha256 <pinned executable SHA-256> \
  --out <new or empty dir> [--run-root <dir>] [--corpus-tar <plaintext tar>] \
  [--public-smoke <public smoke folder>]
```

- **`build`** is the R1 routine with R2 pins. It archives each pinned commit
  from git and checks its `mneme/` tree. It builds a wheel with
  `pip wheel --no-deps`, with `SOURCE_DATE_EPOCH` fixed. It installs each
  wheel into its own venv. `build.json` records each wheel's SHA-256 and each
  environment's `pip freeze --all` SHA-256.
- **`probe-symlinks`** is the G2V-F2 probe. Exit 0 means capable.
- **`score`** exits `0` for PASS, `1` for FAIL or INCOMPLETE, and `2` for
  REFUSED.

The host identity is always an input. It is never hard-coded. After the
pre-scoring re-pin (R2 §3), it is the #646 identity or a new live-host
record's.

### Wheel hashes at the pins (CPython 3.12.10, Windows)

| Build | Commit | `mneme/` tree | Wheel SHA-256 |
|---|---|---|---|
| Implementation | `dbab816f…b345` | `6cb14c2b…e5e4` | `50955f0d3648b392469e60b2e1df72d8043b578db0c5066c9a4763b549223056` |
| Baseline | `f8591102…94eca4ce` | `002fdddb…72f2` | `3497b5dd83942ef5df06fe522acaaa7e6e2833759dfdd25daa8866f65dacd1b2` |

Two independent builds gave byte-identical wheels: one ran the R1 build
routine with the R2 pins, the other ran this harness's `build`. The
completion record restates these hashes. It also records the scoring
environments' `pip freeze` digests. Those digests depend on the venv path,
because the wheel is installed from a `file:` URL.

## Preconditions (any failure: REFUSED, nothing scored)

1. **The host identity.** `--host-version` is non-empty, and
   `--host-sha256` is a lowercase SHA-256.
2. **The run root.** It is new, it has no link component or short-name
   form, and no ancestor holds a `.mneme` directory.
3. **The two environments.**
   - Each is **CPython 3.12.10**.
   - The git tree hash of the `mneme/` it imports is `6cb14c2b…e5e4` for
     the implementation and `002fdddb…72f2` for the baseline.
   - The installed `mneme/` files are exactly the wheel's `RECORD`.
   - The two environments import different directories.
   - Both trees are re-checked after scoring.
4. **The corpus.**
   - `FILES.sha256` has digest `70d35226…49c0d`, lists 605 files, and all
     605 verify.
   - The corpus holds exactly those files, plus `FILES.sha256`, and no
     links.
   - If `--corpus-tar` is given, its SHA-256 is `17a46379…2dcfe1`.
5. **The case roots.** A case root is a directory holding `MANIFEST.json`
   and `cases/`. It may be the corpus root itself or one level down,
   because the README describes both `concealed/` and `public-smoke/`
   folders. Every case directory is named `r2-` plus 10 hex digits.
6. **The class counts.** The concealed counts, taken from each
   `case.json`'s `public_smoke` flag and class, equal the freeze record's
   table: 143 cases.
7. **The public smoke folder, when given.** `--public-smoke` must match
   `PUBLIC_FILES.sha256`, with digest `b60394c0…ab0c` and 57 entries. Every
   case in it is public smoke, and no case ID is shared with the corpus.

`MANIFEST.json` is cross-checked: the case set, its sort order, and each
case's class and public-smoke flag. Any difference is reported as a
finding, never as a refusal. A malformed case is kept and fails G8. That
includes a missing key, a mismatched ID or class, availability other than
`open`, a non-boolean flag, a non-list `numeric_rules`, or a duplicate in
`applied_numeric_rule_ids`.

## One pass, per case

Each case is materialized at `<run root>/w/c` (`<CASE>`), with `repo/` and
`outside/` beneath it. The steps follow README steps 1 to 7 and run in this
order.

### 1. Memory (R2A1.2, AMB-R2-06)

This step runs on a fresh fixture copy.

1. The harness runs `mneme init --path` with the **implementation** build.
2. It then runs `mneme adr import <dir> --memory <file> --apply`, over
   `memory.compile_from`, in that order:
   - **one import of the directory,** when the list is exactly that
     directory's own sorted `ADR-*.md` listing, which is the order the
     pinned importer reads;
   - **otherwise, one import per file,** in list order, with only that file
     visible in its directory.

Any of the following is a **G8 case failure**, never an exclusion:

- a nonzero exit;
- a `compile_from` entry the fixture lacks or the importer cannot read;
- a `compile_from` ADR whose front-matter `id` is missing from the compiled
  memory.

The same memory bytes are used for both builds. An empty `compile_from`
means no memory, which is the missing-memory path.

### 2. Implementation hook

1. **A fresh fixture copy,** with the compiled memory.
2. **Placeholder substitution.** `${REPO}`, `${OUTSIDE}` and `${CASE}` are
   replaced inside the raw envelope text, only in the JSON string literals
   that hold them. Each token becomes its native absolute path. The
   forward-slash remainder is joined with native separators.
3. **Byte preservation.** Every other byte is unchanged, and the harness
   checks that `tool_input.content` is unchanged.
4. **Fail closed.** An unknown token, a token that is not at the start of
   its string, or a second token is a G8 failure.
5. **The run.** `python -m mneme.integrations.claude_code.hook` runs with
   the envelope on stdin, in the envelope's `cwd`.
6. **Capture.** The harness captures raw stdout, stderr and the exit
   status, the target's state before and after, the evidence log and the
   shim log.
7. **The build's evidence values.** While the fixture is still in place,
   the implementation build's interpreter computes, for each evidence
   record and with the pinned host identity:
   - `relevant_enforcement_per_rule()`;
   - `relevant_enforcement_observed()`;
   - `recorded_evaluation_complete()`.

   These are the R2 §5 G6 values. The harness never computes relevance
   itself.

### 3. Baseline hook

The same run as step 2, on a fresh copy, with the same memory bytes.

### 4. Checker parity pair

Where G5 checker-level parity applies, the harness runs `mneme check` with
`--proposed-new-file` and then with `--input`. Both runs use one carrier
holding `content.encode("utf-8")`, the same `--target-path`, `--query` and
`--mode`.

The hook environment, the observation shim and the failure split (a
scoring-process failure versus an observed outcome) are unchanged from R1.
See the R1 harness README.

## Gates, as implemented

Gates are computed over **concealed** cases only. Public smoke cases run in
the same passes but are written to `smoke_cases.jsonl` and
`smoke_summary.json`, so they never reach a gate, G7 included (G2V-F4).

| Gate | Applies to | Fails when |
|---|---|---|
| **G1** | every case | (a) a case expected to block is observed with any exit other than 2. Expected to block: every strict V or VP case, and every case of any class (SC, MR and LIT included) labelled `hook_exit` 2 or `disposition` `refused`. A1.4 cases carry `baseline_observed` in both labels, so they never expect a block. (b) a rule labelled non-clean (outcome `VIOLATION` or `UNEVALUATED`, or status `PARTIAL` or `MATCHER_UNEVALUATED`) has any observed trace, in the checker payload or the evidence record, with `NO_VIOLATION`. (c) the **build's** per-rule relevance is `true` for a rule whose label is not `true`, or its event-level value is `true` where the label is not |
| **G2** | classes C, US, UF, UP, X, L, W and P, plus every SC or MR case labelled `hook_exit` 0 (R2V-F1). Never a `legacy_baseline_observed` case, and never a case labelled `literal_violation` (the LIT exception) | the observed exit is 2 |
| **G3** | every case | after an exit 2 the target exists; the target changed at all; or `lstat` existence after the hook differs from `target_exists_after_hook` |
| **G4** | classes US, UF, UP, VP, SC and MR | a rule with an expected `primary_reason` has no observed trace, or has any trace with a different `primary_reason`. Unknown-source reasons are compared as **sets**, and only for label conformance (R2A1.2, AMB-R2-05) |
| **G5**, hook level | P, X and L, plus any `legacy_baseline_observed` case, but never a routed case (label `routed`) whose content contains CR | Amendment 2 scope (the baseline raised): the A2.2 comparison fails. Otherwise: the builds differ in exit status, raw stdout bytes or raw stderr bytes. Copied unchanged from R1 |
| **G5**, checker level | routed P and X, plus every case the routed-CR exception moved off hook-level parity | `--proposed-new-file` and `--input` differ in exit status or stdout bytes |
| **G6** | every case | see below |
| **G7** | the run | the two passes' `cases.jsonl` or `summary.json` differ in any byte |
| **G8** | every concealed case | any scoring-process failure, a malformed case, a memory compile failure, or the case was not executed |

### G6 (R2 §5, R2V-F3, R2A1.6)

**Unrouted cases.** For a case labelled `evidence_record_expected: false`,
any G2 record is a failure.

**Routed cases.** Otherwise, there must be exactly one record. The harness
then checks the following.

1. **Bindings.** The R1 digest and path join holds. That covers the surface,
   the host identity, the event fields and identifiers, the carrier digest,
   the subject, and every rule's identity, digest and governed path.
2. **Outcome.** `hook_outcome` equals both the observed disposition and the
   `disposition` label.
3. **Mode.** `disposition.mode` equals `hook_mode`.
4. **Cause.** The **mapped** cause (below) equals `expected_cause`.

The four §5 steps then run in order.

1. **Rule-ID set.** The record's `rules[].rule_id` list has no duplicate,
   and as a set it equals the expected set. If it does not, the case fails
   here, **and no value is checked**.
2. **Per-rule relevance.** The build's `relevant_enforcement_per_rule()` has
   exactly the expected set as its keys, and its values equal
   `relevant_enforcement_per_rule`.
3. **Event-level relevance.** The build's `relevant_enforcement_observed()`
   equals `relevant_enforcement_observed`.
4. **`evaluation_complete`.** The build's `recorded_evaluation_complete()`
   equals `evaluation_complete`. `null` is a distinct value here.

**Routed fallbacks (R2A1.6, as corrected by R2 Amendment 2).** For a case
marked `g6_routed_fallback`, the expectation is fixed whatever the other G6
labels say:

| Item | Expected |
|---|---|
| Rule-ID set | `{}` |
| Per-rule relevance | `{}` |
| Event-level relevance | `false` |
| `evaluation_complete` | **`false`** (A2R2.2; R2A1.6 had `null`) |
| Records | exactly one must exist |

**How the stored label is read (A2R2.3).** The sealed corpus stores `null`
for these cases. The harness reads the expected value as `false`, keyed on
the `g6_routed_fallback` flag alone, never on a case identity. No other
label is reinterpreted, in that case or any other.

**What fails step 4.** An untrusted or absent value fails it, meaning
`recorded_evaluation_complete()` returns `None`. Any value other than
`false` also fails it.

**Other labels.** A label that otherwise disagrees with R2A1.6 does not
change the expectation. It is reported as the non-gating finding
`label_inconsistent_with_r2a1_6`. A stored `null` or `false`
`evaluation_complete` is consistent.

**Reporting (A2R2.4).** Every run summary has an `r2_amendment_2` block:

- `applied: true`;
- the number of flagged cases;
- their G6 pass and fail counts, by class.

The headline repeats it.

**`EXCLUDED` rules (R2A1.2, AMB-R2-07).** A rule that appears only as
`EXCLUDED` (label `rule_id_form_verified: false`) is never in an applied
set, so G6 never gates its `rule_id`. Label conformance reports a missing
match for it under a separate informational code.

### Cause mapping (R2A1.2, AMB-R2-08)

The mapping is fixed here, before decryption, and reported in every summary
(`cause_mapping`). Its inputs are the record's `disposition.cause` and the
`rule_type` values in its `violations` list. It never reads labels.

| Record `disposition.cause` | Record `violations` | Mapped `expected_cause` |
|---|---|---|
| `numeric_violation` | includes a `FORBID_LITERAL` violation | `numeric_and_literal_violation` |
| `numeric_violation` | no `FORBID_LITERAL` violation | `numeric_violation` |
| `other_rule` | a `FORBID_LITERAL` violation, and no numeric one | `literal_violation` |
| `no_violation` | any | `no_violation` |
| `fail_open` | any | `fail_open` |
| anything else: `other_rule` without a literal violation, `availability_refusal`, `not_run`, or no cause | any | unmapped. This is always a G6 cause mismatch |

**Why it is derived this way.** It comes from the pinned hook and the public
smoke cases:

- The hook sets `numeric_violation` when the trusted payload reports any
  numeric violation, and `other_rule` for a refusal or deferral without one.
- The record's `violations` list carries the payload's violation identities,
  with `rule_id` and `rule_type`, only when the subject is
  `proposed_new_source`.
- The public LIT case (`literal_violation`) is observed as `other_rule`,
  with one `FORBID_LITERAL` violation.
- The public smoke cases cover four of the five values. Only
  `numeric_and_literal_violation` is not observed in them.

### Result

- **REFUSED** if a precondition fails.
- **INCOMPLETE**, which is a validation FAIL, if the symlink probe fails,
  whatever the gates show.
- Otherwise **PASS** only if all eight gates pass, and **FAIL** if not.

### Reported, never gating

- **The label-conformance count.** It covers the following labels and
  checks:
  - `hook_exit` and `disposition`;
  - `routed`, `checker_invoked` and `subject_kind`;
  - every numeric rule field, including the unknown-source reason **set**;
  - `content_utf8_sha256` and `routed_cr_parity_exception`;
  - R2A1.6 label consistency, and the labels' own G6 consistency (the
    per-rule keys equal the applied set, and the event value is the OR of
    the per-rule values).

  A G1–G8 PASS is never a statement of 100% label agreement.
- **The build's per-rule values, and each record's mapped cause.**
- **The Amendment 2 summary and the G5 stderr diagnostics,** unchanged from
  R1.
- **The smoke results,** and whether the two passes were identical for them.

## Outputs

| Path | Contents |
|---|---|
| `run-<n>/cases.jsonl` | One record per concealed case: raw stdout and stderr (base64), evidence records, the build's evidence values, shim captures, target states, every gate verdict. **Private evidence**: it holds case content and paths. Custody follows R2 §8 step 6 |
| `run-<n>/summary.json` | Metadata only: per-gate pass, applicable and failure counts, failing cases by opaque `case_id`, class and reason code, and label-conformance counts. Compared by G7 |
| `run-<n>/smoke_*.json[l]` | The same, for public smoke cases (non-gating) |
| `summary.json` | Metadata only: result, headline, all gates, pins, cause mapping, inputs, build probes, corpus checks, symlink probe, harness file digests, disclosures, timestamps |

## Tests

**`tests/test_adr034_g2_1_r2_harness.py`** (main-only). It covers:

- **Pins:** the pins against the pre-registration and the freeze record.
- **Preconditions:**
  - corpus verification and refusals;
  - nested case roots;
  - the public-smoke manifest pin;
  - malformed cases, which fail G8.
- **Materialization:**
  - placeholder substitution, which uses native paths and keeps content
    bytes, including BOM, CR and lone surrogates;
  - fail-closed placeholder handling;
  - links and outside folders;
  - a symlink failure, which is a G8 failure.
- **Memory:** both memory-import paths, which compile identical rules; a
  compile failure is a G8 failure.
- **Gates:** every gate on hand-built observations:
  - G1(a/b/c) for SC, MR and LIT;
  - G2's SC and MR coverage, and its exclusions;
  - G3's label;
  - G4 for SC and MR, with the reason set kept non-gating;
  - G5, including routed CR at checker level only, and Amendment 2;
  - G6 steps 1 to 4 in order, including a duplicate, a missing or an extra
    ID, a value check suppressed after a step-1 failure, the empty set, the
    R2A1.6 fallback expectation, and the unrouted, mode, cause and binding
    failures;
  - G8.
- **The cause mapping:** every row.
- **End to end:** two passes over 13 synthetic cases, with the repository
  source as both builds. Every gate passes, G7 holds, and the smoke case is
  kept out of `cases.jsonl` and `summary.json`.
- **Routed fallbacks (R2 Amendment 2):** a trusted `false` passes step 4 for a flagged case and an untrusted `null` fails it; the flag alone, never a case identity, triggers the reading; an end-to-end synthetic fallback passes every gate; the `r2_amendment_2` summary counts are checked.

**`tests/test_adr034_g2_1_r2_harness_smoke.py`** is opt-in. It needs these
variables:

- `MNEME_G2R2_SMOKE_DIR`;
- `MNEME_G2R2_IMPL_PYTHON` and `MNEME_G2R2_IMPL_WHEEL`;
- `MNEME_G2R2_BASELINE_PYTHON` and `MNEME_G2R2_BASELINE_WHEEL`;
- `MNEME_G2R2_HOST_VERSION` and `MNEME_G2R2_HOST_SHA256`.

It verifies the public folder against its pinned manifest. It then runs the
full `score` protocol, two passes, over the 13 public smoke cases on the
pinned wheels. On 2026-10-27, with the #646 host identity, the result was:

- 13 of 13 cases clean on every gate;
- the passes identical;
- 0 label mismatches.

## Owner and reviewer decisions on the open questions

- **Q1 (routed-fallback `evaluation_complete`): resolved by R2 Amendment 2
  (#689).**
  - **The finding.** Before decryption, on scorer-written synthetic content
    only, a routed link-component fallback was observed at the pinned source.
    Its record carries `checker.trusted: true`, no subject, `rules: []` and
    the legacy payload's `evaluation_complete: false`.
  - **The owner's ruling.** The owner corrected the expectation to `false`
    (A2R2.2), read through the flag (A2R2.3). An untrusted `null` fails.
  - **How it is pinned.** The tests tell the two values apart, and an
    end-to-end synthetic fallback passes every gate.
- **Q2 to Q8:** these are listed in the PR body and wait for the reviewer.
  Decisions are recorded here before the harness is pinned in the
  pre-scoring completion record.
