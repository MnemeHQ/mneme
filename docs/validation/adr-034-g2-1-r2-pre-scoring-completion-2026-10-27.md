# ADR-034 G2-1 R2 pre-scoring completion record (metadata only)

**Date:** 2026-10-27
**Status:** PROPOSED. Merging it completes R2 pre-registration §8 step 5.
Decryption needs a separate owner go-ahead after this record merges.

**What this record is.** The R2 pre-registration
([§8 step 5](adr-034-g2-1-revalidation-preregistration-2026-10-26.md))
requires R1-PR §8 step 5 plus the §3 host re-pin before decryption. That
step pins the harness, the builds, the environment, the host, the corpus
anchors and the scoring command. This record adds those pins and nothing
else.

It changes nothing that the R2 pre-registration, R2 Amendment 1 or R2
Amendment 2 (#689) fixed: no gate, class, floor, denominator, failure
policy, implementation pin or corpus anchor.

**What it contains.** No case bytes, concealed case IDs, labels or results.
The corpus is still encrypted. Nothing has been scored. G2-1 stays FAIL
until an R2 results record says otherwise.

## 1. Harness pin

| Item | Value |
|---|---|
| Harness PR | #688, merged as `d1eda40e9864296aa289945b27249cbaa74b47b4` |
| Final reviewed head of #688 | `945c1b8016fb7dc73e7ffb863dfdfc4f9d041bb5` (review accepted at this head) |
| Git tree of `benchmarks/adr034_g2_1_r2/` at `d1eda40e` | `d01fcaa96b54066250659d24feb9335c31fa5b91` |
| `harness.py` SHA-256 (blob `f2f4d8dd…`) | `0a54eec6ffd3f7f8d3a2d0ab015b3ee6664e35e3559e49d49d58b77afc9a8232` |
| `observe_shim/sitecustomize.py` SHA-256 (blob `4af95c5a…`) | `9ba833115634aec4bb00e986d74cd2f26f17327e941bc35900487faafaeadc13` |
| `README.md` SHA-256 (blob `05e7f1c2…`) | `00b505553aa787f7ce1e012134f3e7a325cabcc3f7da15cde3c84daa8313faa8` |

Every scoring run writes the `harness.py` and shim SHA-256 values into its
`summary.json` (harness file digests). Both must equal the values above.

**Harness checkout.** Scoring runs from a standalone local clone of this
repository, outside `C:/dev/mneme`, detached at `d1eda40e`:
`C:/dev/g2-1-r2-scoring/mneme`.

The clone was made with `core.autocrlf=false` and `core.longpaths=true`, so
the working files are the git blobs byte for byte. The three SHA-256 values
above were taken from the working files and from the blobs, and they agree.
The clone's working tree is clean.

## 2. Builds

Built fresh, outside `C:/dev/mneme`, with the merged harness's own `build`
command, run from the clone with the base interpreter in §3:

```text
python benchmarks/adr034_g2_1_r2/harness.py build --out C:/dev/g2-1-r2-scoring/build --python <base interpreter, §3>
```

`build` does the following:

1. archives each pinned commit from git;
2. checks the archive's `mneme/` tree;
3. builds the wheel with `pip wheel --no-deps` and
   `SOURCE_DATE_EPOCH=1792886400`;
4. installs the wheel into its own venv.

| | Implementation | Baseline |
|---|---|---|
| Commit | `dbab816f92143875c1ed7c7d24e4403dedc3b345` | `f8591102b2693379dabec9b5704862e194eca4ce` |
| `mneme/` tree | `6cb14c2b48554482e62685395062bb581dfed5e4` | `002fdddb254267d42a3810cfea669d75700372f2` |
| Wheel | `mneme_hq-0.10.0-py3-none-any.whl` | `mneme_hq-0.10.0-py3-none-any.whl` |
| Wheel SHA-256 | `50955f0d3648b392469e60b2e1df72d8043b578db0c5066c9a4763b549223056` | `3497b5dd83942ef5df06fe522acaaa7e6e2833759dfdd25daa8866f65dacd1b2` |
| `pip freeze --all` SHA-256 | `c37736efe5012f52110edd62f2d762f967ff7bec8326bd1914527f5f2bec5de0` | `7202877cf5430722221e89eb15a4d4d5a15e4f15f953f6eb018ee4917b45d4e5` |
| Interpreter | CPython 3.12.10 | CPython 3.12.10 |
| Environment python | `C:/dev/g2-1-r2-scoring/build/venv-implementation/Scripts/python.exe` | `C:/dev/g2-1-r2-scoring/build/venv-baseline/Scripts/python.exe` |
| Wheel path | `C:/dev/g2-1-r2-scoring/build/dist-implementation/` | `C:/dev/g2-1-r2-scoring/build/dist-baseline/` |

**Reproduction.** Both wheels reproduce, byte for byte, the digests in the
merged harness README (#688). Those digests came from two earlier
independent builds. The baseline wheel is also byte-identical to the R1
baseline wheel.

**Path-dependent freeze digests.** The `pip freeze --all` digests depend on
the venv path, because each wheel is installed from a `file:` URL. They
therefore differ from the #688 pre-builds, and they are pinned here for
these two environments only.

**Verified for this record** with the harness's own `verify_builds`:

- both environments are CPython 3.12.10;
- each imported `mneme/` has its pinned tree;
- each install matches its wheel's `RECORD` (111 `mneme/` files each);
- the two environments import different directories;
- each `pip freeze --all` digest equals the value above.

`score` repeats these checks before scoring and re-checks both trees
afterwards.

## 3. Environment

| Item | Value |
|---|---|
| OS | Windows 11 Home 10.0.26300; `platform.platform()` = `Windows-11-10.0.26300-SP0` |
| Developer Mode | on (`AppModelUnlock\AllowDevelopmentWithoutDevLicense = 1`) |
| Base interpreter | CPython 3.12.10 (`tags/v3.12.10:0cc8128`, MSC v.1943, AMD64), `C:/Users/hi/AppData/Local/Microsoft/WindowsApps/PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0/python.exe` |
| Effective encodings in each build's child | `sys.getfilesystemencoding()` = `utf-8`; `locale.getpreferredencoding(False)` = `cp1252` (both builds, measured by the harness's own interpreter probe) |

**Constructed child environment.** It is unchanged from R1 (R1 completion
record §3), with one difference: the observation log variable is
`MNEME_G2R2_OBSERVE_LOG`. Nothing else is inherited from the scoring shell.

- These variables pass through when set: `SYSTEMROOT`, `WINDIR`, `COMSPEC`,
  `PATHEXT`, `SYSTEMDRIVE`, `NUMBER_OF_PROCESSORS`,
  `PROCESSOR_ARCHITECTURE`, `OS`, `LANG`, `LC_ALL`, `LC_CTYPE`.
- `PATH` is the environment's own `Scripts` directory, then
  `%SYSTEMROOT%\System32`.
- `TEMP`, `TMP` and `TMPDIR` are a fresh per-run scratch directory, and so
  are `HOME` and `USERPROFILE`.
- Hook runs also get:
  - the shim `PYTHONPATH`;
  - `MNEME_G2R2_OBSERVE_LOG`;
  - `MNEME_HOOK_MODE`;
  - `MNEME_HOOK_EVIDENCE_LOG`;
  - `MNEME_HOOK_EVIDENCE_HOST_VERSION` and `_SHA256`, set from the §5
    inputs;
  - the case's `hook.extra_env`.

## 4. Symlink capability

Run from the clone at `d1eda40e`, with the base interpreter, in the
directory that will hold the run root:

```text
python benchmarks/adr034_g2_1_r2/harness.py probe-symlinks --dir C:/dev/g2-1-r2-scoring
```

The output, verbatim:

```json
{
  "capable": true,
  "error": null
}
```

The exit status was 0. The probe creates a file link, a directory link and
a dangling link, reads them back, and removes them. **The result: capable.**
The scoring run repeats the probe at the run root's parent and records it in
`summary.json`. If the probe fails then, the result is INCOMPLETE.

No ancestor of `C:/dev/g2-1-r2-scoring` holds a `.mneme` directory. Both
`C:/dev` and `C:/` were checked.

## 5. Host re-pin (R2 §3)

The installed Claude Code was re-recorded on 2026-10-27 at
`2026-10-27T16:17:55Z`:

| Item | Re-recorded now | #646 (`adr-034-g2-1-live-host-2026-10-25.md`) | Match |
|---|---|---|---|
| `claude --version` | `2.1.310 (Claude Code)` | `2.1.310 (Claude Code)` | yes |
| Package `version` | `2.1.310` | `2.1.310` | yes |
| Shim on `PATH` | `C:\Users\hi\AppData\Roaming\npm\claude.cmd`, which calls the executable below | same | yes |
| Executable | `C:\Users\hi\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe` | same | yes |
| Executable SHA-256 | `f9a3920634ae3b961ee92c2eb58d0051f5f8852b120983d0a4f57b6a5efeba61` | `f9a3920634ae3b961ee92c2eb58d0051f5f8852b120983d0a4f57b6a5efeba61` | yes |

**Result: both match.** Under R2 §3, the carried-forward #646 record stands,
and no new live-host session is required. `score` receives the #646
identity exactly:

| Input | Value |
|---|---|
| `--host-version` | `2.1.310` |
| `--host-sha256` | `f9a3920634ae3b961ee92c2eb58d0051f5f8852b120983d0a4f57b6a5efeba61` |

The scorer uses these values to compute relevance through the pinned
build's own functions. That is synthetic replay, never live-host evidence.
Recording the identity does not authenticate it.

## 6. Public smoke integrity at the pinned harness

| Item | Value |
|---|---|
| Public smoke folder | `C:/dev/mneme-heldout-034-g2r2-public/` (outside the sealed folder) |
| `PUBLIC_FILES.sha256` SHA-256 | `b60394c0076f41f8dd0845c6b290347522bea36d42340050686f04bc3547ab0c` |
| Entries | 57; all 57 re-verified for this record (`sha256sum -c`: 57 OK, 0 failed) |

The opt-in smoke test was run from the clone at `d1eda40e`, on the two §2
environments, with the §5 host identity:

```text
python -m pytest tests/test_adr034_g2_1_r2_harness_smoke.py tests/test_adr034_g2_1_r2_harness.py
```

It was run with these environment variables:

- `MNEME_G2R2_SMOKE_DIR` = the public smoke folder;
- `MNEME_G2R2_IMPL_PYTHON`, `_IMPL_WHEEL`, `_BASELINE_PYTHON` and
  `_BASELINE_WHEEL` = the §2 paths;
- `MNEME_G2R2_HOST_VERSION` and `_HOST_SHA256` = the §5 values.

**Result: 92 passed, 0 failed, 0 skipped.** That is the 2 smoke tests plus
the 90 harness unit tests.

- The smoke test verifies the pinned manifest first.
- All **13 of 13** public smoke cases pass every gate, in two passes.
- G7 shows the two passes identical.
- There are 0 label-conformance mismatches.
- R2 Amendment 2 is reported as applied.

## 7. Corpus anchors

These values are copied from the merged
[R2 freeze record](adr-034-g2-1-r2-heldout-corpus-freeze-2026-10-27.md)
(#687, `09666394f34032726bb0cea28f1ff107f66f2d75`). The scorer hashed
nothing in the sealed folder for this record.

| Item | Value |
|---|---|
| Corpus ciphertext SHA-256 | `32b3510a660b997452d6fb2ff25ad8f0731ada82a8dc2093aa2930821643bf38` |
| Corpus plaintext tar SHA-256 | `17a46379cfbb04ec41cc7e740a9f52ce1f94e48e154a2178987ca56af22dcfe1`, with 606 entries and root `g2-1-r2-heldout-corpus/` |
| Inner `FILES.sha256` SHA-256 | `70d35226584bead131929deb41e3e3f59a5307d0ae34fe49b29426692a749c0d`, covering 605 files |
| Concealed cases | 143 |
| Encrypted to | primary `88CE4C9F66A5F3CA7F1C0A484839E24F94E4F796`, subkey `C4370AB8829450C5` |
| Sealed folder | `C:/dev/mneme-heldout-034-g2r2-sealed/` |

**Concealed cases by class, from #687:**

| Class | V | VP | C | US | UF | UP | X | L | LIT | W | P | SC | MR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Cases | 16 | 10 | 17 | 9 | 10 | 7 | 7 | 19 | 7 | 7 | 9 | 15 | 10 |

The harness pins these anchors:

- `FILES.sha256` `70d35226…`, with 605 files;
- the per-class concealed counts above;
- the plaintext tar `17a46379…`, checked through `--corpus-tar`.

Any mismatch refuses scoring.

## 8. Post-decryption verification and scoring commands

**Locations, all outside the repository and never committed:**

| Path | Holds |
|---|---|
| `C:/dev/g2-1-r2-scoring/plaintext/g2-1-r2-heldout-corpus.tar` | the decrypted tar, written by the owner |
| `C:/dev/g2-1-r2-scoring/corpus/` | the extracted tar; the corpus root is `C:/dev/g2-1-r2-scoring/corpus/g2-1-r2-heldout-corpus/` |
| `C:/dev/g2-1-r2-scoring/run/` | the run root, new at scoring time |
| `C:/dev/g2-1-r2-scoring/out/` | the outputs, new or empty at scoring time |

**Verification before any case runs.** The scorer runs these steps in order
and stops at the first mismatch:

```text
# 1. Tar hash: must equal 17a46379cfbb04ec41cc7e740a9f52ce1f94e48e154a2178987ca56af22dcfe1
sha256sum C:/dev/g2-1-r2-scoring/plaintext/g2-1-r2-heldout-corpus.tar

# 2. Extract
mkdir C:/dev/g2-1-r2-scoring/corpus
tar -xf C:/dev/g2-1-r2-scoring/plaintext/g2-1-r2-heldout-corpus.tar -C C:/dev/g2-1-r2-scoring/corpus

# 3. FILES.sha256 itself: must equal 70d35226584bead131929deb41e3e3f59a5307d0ae34fe49b29426692a749c0d
sha256sum C:/dev/g2-1-r2-scoring/corpus/g2-1-r2-heldout-corpus/FILES.sha256

# 4. Every listed file: must report 605 OK and 0 failed
cd C:/dev/g2-1-r2-scoring/corpus/g2-1-r2-heldout-corpus && sha256sum -c FILES.sha256
```

`score` also enforces these checks as preconditions:

- the tar hash, through `--corpus-tar`;
- the `FILES.sha256` digest;
- 605 of 605 entries verified;
- no extra files and no links;
- the concealed counts by class.

**Scoring.** One invocation runs both passes at the same run-root path, and
then G7. The command, run from `C:/dev/g2-1-r2-scoring/mneme` at `d1eda40e`
with the base interpreter:

```text
python benchmarks/adr034_g2_1_r2/harness.py score \
  --corpus C:/dev/g2-1-r2-scoring/corpus/g2-1-r2-heldout-corpus \
  --corpus-tar C:/dev/g2-1-r2-scoring/plaintext/g2-1-r2-heldout-corpus.tar \
  --impl-python C:/dev/g2-1-r2-scoring/build/venv-implementation/Scripts/python.exe \
  --impl-wheel C:/dev/g2-1-r2-scoring/build/dist-implementation/mneme_hq-0.10.0-py3-none-any.whl \
  --baseline-python C:/dev/g2-1-r2-scoring/build/venv-baseline/Scripts/python.exe \
  --baseline-wheel C:/dev/g2-1-r2-scoring/build/dist-baseline/mneme_hq-0.10.0-py3-none-any.whl \
  --host-version 2.1.310 \
  --host-sha256 f9a3920634ae3b961ee92c2eb58d0051f5f8852b120983d0a4f57b6a5efeba61 \
  --public-smoke C:/dev/mneme-heldout-034-g2r2-public \
  --run-root C:/dev/g2-1-r2-scoring/run \
  --out C:/dev/g2-1-r2-scoring/out
```

- **Exit status:** 0 is PASS, 1 is FAIL or INCOMPLETE, and 2 is REFUSED.
- **`--public-smoke`** re-checks the pinned public manifest. It runs the 13
  public cases without gating, and it checks that no case ID is shared with
  the corpus.
- **The corpus root.** If the extracted tree does not have
  `g2-1-r2-heldout-corpus/FILES.sha256` at the path above, the scorer stops
  and reports this. The corpus root is not guessed.

**The outputs** go under `C:/dev/g2-1-r2-scoring/out/`:

- `run-1/` and `run-2/`;
- `summary.json`;
- the per-case `cases.jsonl` files. These are private evidence, because
  they hold case bytes and paths.

## 9. What happens next

Each step needs its own go-ahead where one is stated.

1. **This record merges.**
2. **The owner decrypts** (owner go-ahead). The corpus ciphertext is
   decrypted from the sealed folder, through subkey `C4370AB8829450C5`, to
   `C:/dev/g2-1-r2-scoring/plaintext/g2-1-r2-heldout-corpus.tar`.
3. **The scorer verifies,** with the §8 steps, before any case runs.
4. **Scoring.** The §8 command runs once. It covers two passes, G1–G8,
   R2 Amendments 1 and 2, and the carried R1 rules.

   The harness is not edited after decryption. A harness fix at that point
   voids blind status.
5. **The results record.** This is a metadata-only results record PR. It:
   - names failing cases by opaque `case_id` and class only;
   - includes the R2 Amendment 2 summary, which gives the flagged count and
     G6 by class;
   - includes the label-conformance count;
   - says plainly if any gate fails.
6. **Custody close.** Evidence is encrypted to the owner key. Every
   plaintext copy is shredded and confirmed absent: the tar, the extracted
   corpus, the run root and `cases.jsonl`.

## 10. Isolation statement (scorer)

**Read for this record:**

- the R2 pre-registration, with Amendments 1 and 2;
- R1-PR §8 and the R1 completion record, for its format;
- the R2 freeze record (#687);
- the §8.B live-host record (#646);
- the harness at `d1eda40e` and its README;
- `git` metadata for the pinned commits;
- the build output of the fresh build;
- the public smoke folder, hashed and run.

**Not read, opened, hashed or copied:**

- anything in `C:/dev/mneme-heldout-034-g2r2-sealed/`;
- any R1 corpus, scoring or evidence location;
- any provenance material;
- any corpus-author transcript or note.

No gpg operation was run. No case content outside the 13 public smoke cases
has been seen.

## 11. Not authorized by this record

- **Decryption.** It needs a separate owner go-ahead after this record
  merges.
- **Further change.** Scoring is not authorized, nor is any change to the
  harness, the builds, the labels, the pre-registration or the corpus.
- **Claims.** No R2 PASS claim, enforcement claim, "relevant enforcement
  observed" claim or production claim is made. G2-1 stays FAIL.
