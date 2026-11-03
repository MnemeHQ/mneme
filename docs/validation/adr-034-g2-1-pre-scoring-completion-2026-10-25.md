# ADR-034 G2-1 §8.D pre-scoring completion record (metadata only)

**Date:** 2026-10-25
**Status:** PROPOSED. Merging it completes pre-registration §8 step 5.
Decryption needs a separate owner go-ahead after this record merges.

**What this record is.** The pre-registration
([§8 step 5](adr-034-g2-1-validation-preregistration-2026-10-25.md)) requires
a short record before decryption that pins the harness, the builds, the
environment, the corpus anchors and the scoring command. It adds those pins
and nothing else.

It changes nothing that the pre-registration, Amendment 1 (#647) or
Amendment 2 (#652) fixed: no gate, class, floor, denominator, failure policy,
implementation pin or corpus anchor.

**What it contains.** No case bytes, case IDs, labels or results. The
corpus is still encrypted. Nothing has been scored.

## 1. Harness pin

| Item | Value |
|---|---|
| Harness PR | #651, merged as `c0aba6b48dec1a814143b8385087f0b0d2dbca32` |
| Git tree of `benchmarks/adr034_g2_1/` at that commit | `a47ccfcfbfef8f66ad4dbcc34b27096e12c9813d` |
| `harness.py` SHA-256 (blob `877b2505…`) | `76e5f8c19c53166429a273f184a7e5097a2a92bb53258c4d8806ce54fb5d1175` |
| `observe_shim/sitecustomize.py` SHA-256 (blob `7fa9f5d4…`), the observation shim (Q6) | `5663ac006457e591fb6c2ad7c5ff1deaad790e1190cae2a01ed58575f862b918` |
| `README.md` SHA-256 (blob `e973a268…`) | `3efe002a4a3234b8334b52a1f6c219664cf11c5837edcd19ed7ac25d6586641d` |

The tree equals the final reviewed head of #651 (`cfe5a48a`).

Every scoring run writes `harness.py` and the shim's SHA-256 into its
`summary.json` (`harness` digests). Both must equal the values above.

**Harness checkout.** Scoring runs from a standalone local clone of this
repository, outside `C:/dev/mneme`, detached at `c0aba6b4`:
`C:/dev/g2-1-scoring/mneme`.

The clone sets `core.autocrlf=false` and `core.longpaths=true`. Without
`autocrlf=false`, Git for Windows' system default (`autocrlf=true`) writes
CRLF working files, and the on-disk harness bytes no longer match the
SHA-256 values above. This was observed while preparing the record and
corrected before any build or probe. The clone's working tree is clean.

## 2. Builds

Built fresh outside `C:/dev/mneme` with the merged harness's own `build`
command, from the clone:

```text
python benchmarks/adr034_g2_1/harness.py build --out C:/dev/g2-1-scoring/build --python <CPython 3.12.10>
```

`build` archives each commit from git, checks its `mneme/` tree, builds the
wheel with `pip wheel --no-deps` and `SOURCE_DATE_EPOCH=1792886400`, and
installs it into its own venv.

| | Implementation | Baseline |
|---|---|---|
| Commit | `6e26c534dd78703f811da7d76168f2e2aaaaa23e` | `f8591102b2693379dabec9b5704862e194eca4ce` |
| `mneme/` tree | `34ccbf62b90bac2d6e5e277386a400ac78d86d66` | `002fdddb254267d42a3810cfea669d75700372f2` |
| Wheel | `mneme_hq-0.10.0-py3-none-any.whl` | `mneme_hq-0.10.0-py3-none-any.whl` |
| Wheel SHA-256 | `e35d98915a02bff31bf8915225389b31653daad12245a673e11c8a3069cc96b5` | `3497b5dd83942ef5df06fe522acaaa7e6e2833759dfdd25daa8866f65dacd1b2` |
| `pip freeze --all` SHA-256 | `7620df078d872ab1c71f9753b854d682477c37e12187d96cf9b7884ed590da57` | `220d6cd8ba0492f2bca13adcee7818f9ce1a947aa24176a541afd373275af86a` |
| Environment python | `C:/dev/g2-1-scoring/build/venv-implementation/Scripts/python.exe` | `C:/dev/g2-1-scoring/build/venv-baseline/Scripts/python.exe` |
| Wheel path | `C:/dev/g2-1-scoring/build/dist-implementation/` | `C:/dev/g2-1-scoring/build/dist-baseline/` |

**Reproduction.** Both wheels reproduce, byte for byte, the digests the
scorer recorded in #651 from two earlier builds (`e35d9891…96b5` and
`3497b5dd…d1b2`). The §8.B wheels differ because that build did not fix
`SOURCE_DATE_EPOCH`. The `mneme/` trees are the same.

**Verified for this record** with the harness's own `verify_builds`: both
environments are CPython 3.12.10; each imported `mneme/` has its pinned tree;
each install matches its wheel's `RECORD` (111 `mneme/` files each); and each
`pip freeze --all` digest equals the value above.

`score` re-verifies every build pin before scoring and again afterwards:

- the interpreter is CPython 3.12.10;
- each imported `mneme/` matches its tree hash;
- each install matches its wheel's `RECORD`.

## 3. Environment (Q7)

| Item | Value |
|---|---|
| OS | Windows 11 Home, `Microsoft Windows NT 10.0.26300.0`; `platform.platform()` = `Windows-11-10.0.26300-SP0` |
| Developer Mode | on (`AppModelUnlock\AllowDevelopmentWithoutDevLicense = 1`), enabled by the owner |
| Base interpreter | CPython 3.12.10 (`tags/v3.12.10:0cc8128`, MSC v.1943, AMD64), `C:/Users/hi/AppData/Local/Microsoft/WindowsApps/PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0/python.exe` |
| Effective encodings in each build's child | `sys.getfilesystemencoding()` = `utf-8`; `locale.getpreferredencoding(False)` = `cp1252` (both builds, measured by the harness's own interpreter probe) |
| `PYTHONIOENCODING`, `PYTHONUTF8` | unset in the scoring shell, and never passed to children (the constructed environment carries no `PYTHON*` variable except the shim's `PYTHONPATH`) |

**Working directory.** Each hook process runs in the envelope's `cwd`, after
substitution, when that is an existing directory, and otherwise in the case
workspace. Memory is compiled with the case repository as cwd. The
checker parity pair uses the same cwd as the hook.

**Constructed child environment.** Nothing else is inherited:

- passed through when set: `SYSTEMROOT`, `WINDIR`, `COMSPEC`, `PATHEXT`,
  `SYSTEMDRIVE`, `NUMBER_OF_PROCESSORS`, `PROCESSOR_ARCHITECTURE`, `OS`,
  `LANG`, `LC_ALL`, `LC_CTYPE`;
- `PATH` = the environment's own `Scripts` directory, then
  `%SYSTEMROOT%\System32`;
- `TEMP`, `TMP`, `TMPDIR` = a fresh per-run scratch `tmp` directory;
- `HOME`, `USERPROFILE` = a fresh per-run scratch `home` directory;
- for hook runs only:
  - `PYTHONPATH` = the shim directory;
  - `MNEME_G2H_OBSERVE_LOG`;
  - `MNEME_HOOK_MODE` = the case mode;
  - `MNEME_HOOK_EVIDENCE_LOG`;
  - `MNEME_HOOK_EVIDENCE_HOST_VERSION` and `MNEME_HOOK_EVIDENCE_HOST_SHA256`
    (§5);
  - the case's `hook.extra_env`.

Both builds get the same environment. The hook is started as
`python -m mneme.integrations.claude_code.hook`, envelope on stdin.

## 4. Symlink capability (G2V-F2)

Run from the clone at `c0aba6b4`, with the base interpreter above, in the
directory that will hold the run root:

```text
python benchmarks/adr034_g2_1/harness.py probe-symlinks --dir C:/dev/g2-1-scoring
```

Output, verbatim:

```json
{
  "capable": true,
  "error": null
}
```

Exit status 0. The probe creates a file link, a directory link and a dangling
link, reads them back, and removes them. **Result: capable.** The scoring run
repeats the probe at the run root's parent and records it in `summary.json`.
If it fails then, the result is INCOMPLETE.

No ancestor of `C:/dev/g2-1-scoring` holds a `.mneme` directory (checked:
`C:/dev`, `C:/`).

## 5. Host identity

Taken from the merged §8.B record
([`adr-034-g2-1-live-host-2026-10-25.md`](adr-034-g2-1-live-host-2026-10-25.md),
#646, `f551b127`), and passed to `score` exactly as:

| Input | Value |
|---|---|
| `--host-version` | `2.1.310` |
| `--host-sha256` | `f9a3920634ae3b961ee92c2eb58d0051f5f8852b120983d0a4f57b6a5efeba61` |

These are the values §8.B set through `MNEME_HOOK_EVIDENCE_HOST_VERSION` and
`MNEME_HOOK_EVIDENCE_HOST_SHA256`. Under Amendment 1 A1.3 the scorer uses
them to compute `relevant_enforcement_observed`. That is synthetic replay,
never live-host evidence.

## 6. Corpus anchors

Copied from the merged
[freeze record](adr-034-g2-1-heldout-corpus-freeze-2026-10-25.md) (#648,
`6db33994`):

| Item | Value |
|---|---|
| Corpus ciphertext SHA-256 | `016a6134bc71f5c531981c101373dad8c562b83da24dcd9b154644ad85205ae4` |
| Corpus plaintext tar SHA-256 | `de8b70faa7ab5267628d6f488811ead48a6c088c1880872e61ec85a2bbd233f8` (391 entries) |
| Inner `FILES.sha256` SHA-256 | `67ecd146f49c290c20e97387bb8ef478817bd57ba6ad3c4a18256281f6ac2dbc` (390 files) |
| Encrypted to | primary `88CE4C9F66A5F3CA7F1C0A484839E24F94E4F796`, subkey `C4370AB8829450C5` |
| Sealed folder | `C:/dev/mneme-heldout-034-g2-sealed/` |

The sealed folder's public copy of `FILES.sha256` re-hashes to
`67ecd146…2dbc` (checked for this record). The ciphertexts were not opened,
read or hashed by the scorer.

The harness pins these anchors: `FILES.sha256` `67ecd146…`, 390 files, the
per-class counts (122 concealed, 7 public smoke), and, through
`--corpus-tar`, the plaintext tar `de8b70fa…`. Any mismatch refuses scoring.

## 7. Scoring command

One invocation runs both passes (pass 1 and pass 2 at the same run-root
path) and G7. The command, from `C:/dev/g2-1-scoring/mneme` at `c0aba6b4`:

```text
python benchmarks/adr034_g2_1/harness.py score \
  --corpus C:/dev/g2-1-scoring/corpus/<root holding FILES.sha256> \
  --corpus-tar C:/dev/g2-1-scoring/plaintext/g2-1-heldout-corpus.tar \
  --impl-python C:/dev/g2-1-scoring/build/venv-implementation/Scripts/python.exe \
  --impl-wheel C:/dev/g2-1-scoring/build/dist-implementation/mneme_hq-0.10.0-py3-none-any.whl \
  --baseline-python C:/dev/g2-1-scoring/build/venv-baseline/Scripts/python.exe \
  --baseline-wheel C:/dev/g2-1-scoring/build/dist-baseline/mneme_hq-0.10.0-py3-none-any.whl \
  --host-version 2.1.310 \
  --host-sha256 f9a3920634ae3b961ee92c2eb58d0051f5f8852b120983d0a4f57b6a5efeba61 \
  --run-root C:/dev/g2-1-scoring/run \
  --out C:/dev/g2-1-scoring/out
```

`python` is the base interpreter in §3. Exit status: 0 PASS, 1 FAIL or
INCOMPLETE, 2 REFUSED.

**Outputs, all outside the repository, under `C:/dev/g2-1-scoring/out/`:**

- `run-1/` and `run-2/`;
- `summary.json`;
- the per-case `cases.jsonl` files, which are private evidence: they hold
  case bytes and paths.

The `<root holding FILES.sha256>` placeholder is the directory inside the
extracted tar that holds `FILES.sha256`. It is written down in the results
record. The tar's internal prefix is not public, so it is not guessed here.

## 8. What happens next

Each step needs its own go-ahead where stated.

1. **This record merges.**
2. **The owner decrypts** (owner go-ahead). The corpus ciphertext from the
   sealed folder is decrypted through subkey `C4370AB8829450C5` to
   `C:/dev/g2-1-scoring/plaintext/g2-1-heldout-corpus.tar`. That location is
   outside the repository and is never committed.
3. **The scorer checks before any case runs:**
   - the tar's SHA-256 equals `de8b70fa…33f8`;
   - the tar is extracted to `C:/dev/g2-1-scoring/corpus/`;
   - the extracted `FILES.sha256` hashes to `67ecd146…2dbc` and verifies 390
     of 390.

   `score` repeats all of these as preconditions. Any mismatch stops scoring.
4. **Scoring.** The command in §7 runs once: two passes, G1–G8, Amendments 1
   and 2. The harness is not edited after decryption. A harness fix then
   voids blind status (§6).
5. **Results record.** A metadata-only results record PR. It names failing
   cases by opaque `case_id` and class only, includes the Amendment 2 in-scope
   counts by class and the label-conformance count, and says plainly if any
   gate fails.
6. **Custody close.** Evidence is encrypted to the owner key, and every
   plaintext copy is shredded and confirmed absent:
   - the tar;
   - the extracted corpus;
   - the run root;
   - `cases.jsonl`.

## 9. Isolation statement (scorer)

**Read for this record:**

- the pre-registration with Amendments 1 and 2;
- the freeze record (#648);
- the §8.B live host record (#646);
- the harness at `c0aba6b4` and its README;
- `git` metadata for the pinned commits;
- the build log and `build.json` of the fresh build;
- from the sealed folder, `FILES.sha256` only (hashed).

**Earlier, for the harness (#651):**

- the G2-1 charter and ADR-034 §4–§7a;
- the M4 harness;
- the pinned `hook.py`, for its interface only;
- from the sealed folder, `LAYOUT.md`, `PUBLIC_SMOKE.json`, `public_smoke/`,
  `FILES.sha256` and `seal_tool.py`.

**Not read, opened or copied:**

- any `*.tar.gpg`;
- `SEAL_RECORD.md`;
- any provenance material;
- any corpus-author, implementation or orchestrator transcript or note.

No case content outside the 7 public smoke cases has been seen.

## 10. Not authorized by this record

- Decryption, which needs a separate owner go-ahead after this record
  merges.
- Scoring, or any change to the harness, the builds, the pre-registration
  or the corpus.
- Any enforcement, "relevant enforcement observed" or production claim.
