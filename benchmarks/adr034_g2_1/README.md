# ADR-034 G2-1 §8.D scoring harness

The scoring harness for the G2-1 independent blind validation of the
pre-write numeric check for new-file `Write`
([charter](../../docs/plans/2026-10-24-adr-034-g2-1-behavioral-charter.md) §8.D).
It scores the implementation pin `6e26c534` against the sealed held-out
corpus under the frozen
[pre-registration](../../docs/validation/adr-034-g2-1-validation-preregistration-2026-10-25.md)
(revision 2, Amendment 1, and Amendment 2 from #652): gates G1-G8, the G2V-F2 symlink rule and the
§6 failure policy. No gate, class, denominator or definition is changed.

It was written by the scorer session before decryption. Sources read:

- the pre-registration and Amendment 1;
- the [freeze record](../../docs/validation/adr-034-g2-1-heldout-corpus-freeze-2026-10-25.md);
- the G2-1 charter, and ADR-034 §4-§7a;
- the §8.B live host record (PR #646), for the hook invocation form and the
  host-identity variables;
- from the sealed folder, only `LAYOUT.md`, `PUBLIC_SMOKE.json`,
  `public_smoke/`, `FILES.sha256` and `seal_tool.py`;
- the M4 harness, as a structural precedent only;
- the pinned hook source at `6e26c534`, for its interface only: the entry
  point, the environment seams and the evidence record fields.

**It contains no concealed case data.** Its tests use synthetic cases the
scorer wrote (`tests/adr034_g2_1_synthetic_corpus.py`). An opt-in test runs
the seven public smoke cases through the pinned builds; those cases are not
copied into this repository.

After decryption the harness is not edited (pre-registration §6). A harness
fix then voids blind status for that run.

## Files

| File | Role |
|---|---|
| `harness.py` | `build`, `probe-symlinks` and `score`: preconditions, fixtures, both passes, gates, summaries |
| `observe_shim/sitecustomize.py` | Observation shim, on `PYTHONPATH` for both builds' hook processes (see below) |

## Commands

```text
python benchmarks/adr034_g2_1/harness.py build --out <new dir> --python <CPython 3.12.10>
python benchmarks/adr034_g2_1/harness.py probe-symlinks [--dir <dir>]
python benchmarks/adr034_g2_1/harness.py score \
  --corpus <decrypted corpus root, the directory holding FILES.sha256> \
  --impl-python <env python, 6e26c534> --impl-wheel <its wheel> \
  --baseline-python <env python, f8591102> --baseline-wheel <its wheel> \
  --host-version <§8.B host version> --host-sha256 <§8.B executable SHA-256> \
  --out <new or empty dir> [--run-root <dir>] [--corpus-tar <plaintext tar>]
```

- **`build`** archives each pinned commit from git, checks its `mneme/` tree,
  builds a wheel with `pip wheel --no-deps` (`SOURCE_DATE_EPOCH` fixed), and
  installs it into its own venv. It needs network access for the build
  backend and the runtime dependencies. `build.json` records each wheel's
  SHA-256 and each environment's `pip freeze --all` SHA-256.
- **`probe-symlinks`** is the G2V-F2 probe: it creates a file link, a
  directory link and a dangling link, and reads them back. Exit 0 means
  capable.
- **`score`** exit status: `0` PASS, `1` FAIL or INCOMPLETE, `2` REFUSED.

The host identity is always an input, taken from the §8.B record. It is never
hard-coded.

## Preconditions (any failure: REFUSED, nothing scored)

1. `--host-version` is non-empty and `--host-sha256` is a lowercase SHA-256.
2. The run root is new, has no link component or short-name form, and no
   ancestor holds a `.mneme` directory (LAYOUT step 4).
3. Each environment is **CPython 3.12.10**. The git tree hash of the
   `mneme/` it imports (computed from the files on disk) is
   `34ccbf62…6d66` for the implementation and `002fdddb…72f2` for the
   baseline. Its installed `mneme/` files are exactly the given wheel's
   `RECORD`. The two environments import different `mneme/` directories.
   Both trees are re-checked after scoring.
4. `FILES.sha256` has digest `67ecd146…2dbc`, lists 390 files, and all 390
   verify. The corpus holds exactly those files plus `FILES.sha256`, with no
   links or special files. If `--corpus-tar` is given, its SHA-256 is
   `de8b70fa…33f8`.
5. The per-class counts from `expected.json` equal the freeze record
   (122 concealed, 7 public smoke).

`CASE_INDEX.json` and `PUBLIC_SMOKE.json` are cross-checked and any
difference is reported as a finding. Their exact shape is not specified, so
it is never a reason to refuse. A malformed case is kept and fails G8.

## One pass, per case

Each pass creates the run root, runs every case, and removes the root. Both
passes use the same root path. Per case, at `<run root>/w/ws` (one path,
reused by every case):

1. **Memory.** Materialize the fixture per LAYOUT step 2. Compile
   `docs/adr` with the implementation build (`mneme init --path`, then
   `mneme adr import --apply`, in the repo). Check the decision ids and typed
   rules against `memory.expected_typed_rules`. A mismatch or failure is a
   G8 failure.
2. **Implementation hook.** Fresh fixture copy, plus the compiled memory
   bytes. Substitute `{{WS}}`/`{{REPO}}` in the raw envelope text, JSON-escaped,
   so every other envelope byte reaches the hook unchanged. Run
   `python -m mneme.integrations.claude_code.hook` with the envelope on stdin.
   Capture raw stdout, stderr and exit, the target state before and after,
   the evidence log, and the shim log.
3. **Baseline hook.** The same, on a fresh copy, with the same memory bytes.
4. **Checker parity pair**, where G5 checker level applies: on a fresh copy,
   run `mneme check` with `--proposed-new-file` and then `--input`. Both use
   one binary carrier holding `content.encode("utf-8")`, the same
   `--target-path`, `--query "edit to <file_path>"` and `--mode`.

**Hook environment.** The environment is constructed, and both builds get the
same one:

- nothing inherited except the OS basics (`SYSTEMROOT` and similar);
- `PATH` is the env's own directory plus `System32`;
- `TEMP`, `TMP`, `TMPDIR`, `HOME` and `USERPROFILE` point at fresh per-run
  scratch;
- `MNEME_HOOK_MODE` is the case mode;
- `MNEME_HOOK_EVIDENCE_LOG` is set;
- `MNEME_HOOK_EVIDENCE_HOST_VERSION` and `MNEME_HOOK_EVIDENCE_HOST_SHA256`
  are the inputs;
- the case's `extra_env` is added.

The process cwd is the envelope's `cwd` when that is an existing directory,
otherwise the workspace.

**Observation shim.** `PYTHONPATH` carries `observe_shim/` for both builds.
The hook passes its environment to its `python -m mneme check` child. In that
child only, the shim records:

- the argument vector, with the carrier path replaced by `<CARRIER>`;
- the carrier's SHA-256;
- a copy of the text written to stdout (the check payload).

It never writes to stdout or stderr, and it passes every write through
unchanged. A test pins that stdout, stderr and exit are identical with and
without it.

**Failures.** A launch failure, a timeout (120 s), a fixture or memory error,
a symlink that cannot be created, or any harness exception is a
**scoring-process failure**. It counts as a G8 failure of that case and is
never an exclusion. A hook that exits with a captured traceback is an
**observed outcome** (A1.4).

## Gates, as implemented

Gates are computed over **concealed** cases only. Public smoke cases are run
in the same passes but written to separate files (`smoke_cases.jsonl`,
`smoke_summary.json`), so they never reach a gate, G7 included (G2V-F4).

| Gate | Applies to | Fails when |
|---|---|---|
| **G1** | every case | (a) a strict V or VP case, or a LIT case with expected `hook_exit` 2, is observed with any exit other than 2; (b) a numeric rule expected non-clean (outcome `VIOLATION`/`UNEVALUATED` or status `PARTIAL`/`MATCHER_UNEVALUATED`) has any observed trace (checker payload or evidence record) with `NO_VIOLATION`; (c) the scorer-computed relevance is true where the label is not true, for the case or any rule |
| **G2** | classes C, US, UF, UP, X, L, W, P; not `expected_from_baseline`; no expected literal violation | observed exit 2 |
| **G3** | every case | after an exit 2 the target exists; the target state changed at all; or the `target_after_hook` label does not hold (`absent`, `unchanged`, `unchanged_link_and_referent`, `unchanged_dangling_link`) |
| **G4** | classes US, UF, UP, VP | for a rule with an expected primary reason: no observed trace, or any trace with a different `primary_reason` |
| **G5** hook level | P, X, L except routed with CR content; plus any case labelled `parity_with_baseline_hook` or `expected_from_baseline` | **Amendment 2 scope** (the baseline's own run exited nonzero with at least one traceback block): the builds differ in stdout, exit, the ordered exception summary lines, the ordered chain separators, or any stderr line outside a traceback block, or the current build did not raise. **Otherwise:** they differ in exit, raw stdout bytes or raw stderr bytes; a traceback-normalized comparison is then recorded as a diagnostic (`gating: false`) |
| **G5** checker level | routed P and X; plus any case labelled `parity_with_input_carrier` | `--proposed-new-file` and `--input` differ in exit or stdout bytes |
| **G6** | every case | routed (`g2_evidence_record_expected`): not exactly one record; any binding problem; `hook_outcome` differs from the observed disposition or the label; `disposition.mode` differs from the case mode; `disposition.cause` differs from the expected cause; relevance differs from the label, for the case or per rule. Unrouted: any record |
| **G7** | the run | the two passes' `cases.jsonl` or `summary.json` differ in any byte |
| **G8** | every concealed case | any scoring-process failure, or the case was not executed |

**Result:**

- REFUSED if a precondition fails;
- INCOMPLETE (a validation FAIL) if the symlink probe fails, whatever the
  gates show;
- otherwise PASS only if all eight gates pass, and FAIL if not.

**Amendment 2 (G5, #652).** Scope is decided only by the pinned baseline's
observed run of the case, never by the labels or the current build. A
traceback block runs from `Traceback (most recent call last):` to its
summary line, the first following line that is not indented. Only the
lines between the two (the frames) are left out. For every case in scope
the harness records:

- both builds' raw stdout and stderr;
- the raw stdout and stderr diffs;
- the A2.2 result and its failure reasons.

The summary's `amendment_2` block gives the cases in scope per class, how
many had identical raw bytes, and how many passed A2.2, plus a description
of the comparison. A case where only the current build raised is out of
scope and stays raw-byte.

**Binding problems (G6)**, checked against the substituted envelope and the
host input:

- `surface` is `claude_code.PreToolUse`, and `mneme_version` is non-empty;
- the host identity equals the inputs;
- `tool_name`, `file_path` and `cwd` are as received;
- `identifiers` equal every string `*_id` key in the envelope;
- `carrier_sha256` equals SHA-256(`content` as UTF-8);
- when a subject is present: it is trusted, of kind `proposed_new_source`,
  and its digest matches; `absence_verified` is true; and `target_path`
  equals the resolved `file_path` under `normcase`;
- every rule is `APPLIED`, with a `rule_id`, a decision version, the
  subject's governed path, the carrier digest and the matcher fields.

**Relevance (Amendment 1 A1.3)** is computed by the harness from the record,
never taken from the build. A rule is relevant only when every binding holds
and a subject is present, and its outcome is attributable:

- `RECOGNIZED`/`NO_VIOLATION` with the hook outcome `proceeded`;
- or a violation (`RECOGNIZED`, or `PARTIAL` with a non-input reason) that
  the record reports as violated, `refused` in strict mode or `deferred` in
  warn mode.

`MATCHER_UNEVALUATED`, or a disposition caused only by another rule, is
never relevant. The case value is the conjunction over its applied numeric
rules, and false if there are none.

**Expected cause (G6)** is derived from the labels:

- `refused`/`deferred` gives `numeric_violation` when `numeric` is in
  `block_attributed_to`, else `other_rule`;
- `proceeded` gives `fail_open` when an applied numeric rule is
  `MATCHER_UNEVALUATED` or `PARTIAL`, else `no_violation`.

See open question Q1.

**Reported, never gating:**

- label conformance: `hook_exit`, `hook_disposition`, `hook_invokes`,
  `hook_routed`, `subject_kind`, `trusted_proposed_source`, the numeric rule
  fields, the `unknown_source_reasons` multiset, `content_utf8_sha256`, and
  `g2_false_block_gate_applies` against the registered G2 rule;
- the G5 stderr diagnostics;
- the smoke results and their pass-to-pass identity.

## Outputs

| Path | Contents |
|---|---|
| `run-<n>/cases.jsonl` | One record per concealed case: raw stdout and stderr (base64), evidence records, shim captures, target states, every gate verdict. **Private evidence** (it holds case content and paths) |
| `run-<n>/summary.json` | Per-gate pass, applicable, failures, and failing cases by opaque `case_id`, class and reason codes. Compared by G7 |
| `run-<n>/smoke_*.json[l]` | The same for public smoke cases (non-gating) |
| `summary.json` | Result, headline, all gates, pins, inputs, build probes (wheel and `pip freeze` SHA-256s, encodings, platform), corpus checks, symlink probe, harness file digests, disclosures, timestamps |

## Tests

- `tests/test_adr034_g2_1_harness.py` (main-only) covers:
  - every gate, failing and passing, on hand-built observations;
  - the A1.3 relevance table and every binding mismatch;
  - Amendment 2: an in-scope pass on frame-only differences, a message
    mismatch, a chained-exception mismatch, "only the baseline raised",
    "only the current build raised", out-of-scope raw bytes, and the
    per-class summary;
  - preconditions and refusals;
  - envelope substitution byte preservation, fixture materialization, and
    the symlink G8 path;
  - shim transparency;
  - smoke exclusion and G7.

  It also runs a two-pass end-to-end score of 14 or 15 synthetic cases, with
  the repository source as both builds.
- `tests/test_adr034_g2_1_harness_smoke.py` is opt-in. It needs
  `MNEME_G2H_SMOKE_DIR`, `MNEME_G2H_IMPL_PYTHON`/`_WHEEL`,
  `MNEME_G2H_BASELINE_PYTHON`/`_WHEEL` and `MNEME_G2H_HOST_VERSION`/`_SHA256`.
  It runs the full `score` protocol over the seven public smoke cases, on
  the pinned builds.

## Open questions (for the owner, before decryption)

These are listed in the harness PR. Each is implemented as described above
until ruled otherwise. A ruling that changes scoring means a harness change
**before** decryption.

- **Q1 (G6 cause).** G6 requires the "expected cause". No label carries one,
  and the cause vocabulary (`numeric_violation`, `other_rule`,
  `no_violation`, `fail_open`, …) is the implementation's, not the charter's.
  The harness derives it as above. Should G6 score the cause this way, or
  score only outcome, mode and relevance?
- **Q2 (relevance, several rules).** Case-level relevance for a case with
  more than one applied numeric rule is taken as the conjunction (false if
  none). Per-rule values are compared to `…_per_rule`.
- **Q3 (G1(a) set).** G1(a) is taken literally: strict V and VP, and LIT
  with expected exit 2. A case of another class labelled `refused` is not in
  G1(a); it appears only in label conformance.
- **Q4 (G5 and the labels).** Labels can add cases to G5, never remove them:
  the class rule ∪ `parity_with_baseline_hook` ∪ `expected_from_baseline` at
  hook level, and routed P/X ∪ `parity_with_input_carrier` at checker level.
  The routed-CR exception uses the `hook_routed` label.
- **Q5 (G3 and the label).** G3 also requires `target_after_hook` to hold,
  beyond "absent after a block, never changed".
- **Q6 (how matcher results are observed).** G1(b) and G4 read the checker
  payload that the hook's own child wrote, captured by the shim (plus the
  evidence record rules for G1(b)). Is a `PYTHONPATH` observation shim on the
  scored run acceptable? The alternative is an uninstrumented hook run plus a
  separate checker replay.
- **Q7 (environment pins).** Hook-level bytes depend on the constructed
  environment: the locale encoding (no `PYTHONIOENCODING`/`PYTHONUTF8`; cp1252
  on the pinned Windows host), the envelope `cwd` as process cwd, and
  per-run `TEMP`. The completion record should state these.
- **Q8 (lone-surrogate cases): resolved by Amendment 2 (#652).** Both
  builds raise `UnicodeEncodeError` on lone-surrogate content, with frames
  that differ (line 920 against 797, and different site-packages paths).
  Under raw-byte A1.4 every such case would have failed G5 by construction.
  The owner adopted Amendment 2 before decryption, and the harness
  implements it. On the pinned wheels, a synthetic lone-surrogate case is
  now in scope: its raw stderr differs, and it passes A2.2.
- **Q9 (symlinks).** This machine cannot create symlinks without privilege
  (`WinError 1314`). Scoring here would be INCOMPLETE. The scoring
  environment needs Developer Mode or an elevated shell, shown by
  `probe-symlinks` in the completion record.
- **Q10 (fixture details LAYOUT leaves open).**
  - symlink targets are created with native separators on Windows;
  - `memory: null` means no memory file;
  - with no `docs/adr`, only `mneme init` runs;
  - the memory is compiled with the repo as cwd;
  - `mneme init` writes a wall-clock `meta.created`, so raw memory bytes are
    outside G7.
- **Q11 (G7 scope).** G7 compares the concealed per-case records (raw
  output bytes included) and the run summary. The final `summary.json` has
  timestamps and is not compared.
