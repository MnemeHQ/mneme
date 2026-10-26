# ADR-034 G2-1 §8.D blind scoring: results record (metadata only)

**Date:** 2026-10-25
**Verdict: FAIL.** G4 and G6 fail. G2-1 §8.D independent blind validation
does not pass, and G2-1 does not close.

**What this record is.** The results record of pre-registration §8 step 6
([pre-registration](adr-034-g2-1-validation-preregistration-2026-10-25.md),
with Amendments 1 and 2). Scoring followed the merged
[pre-scoring completion record](adr-034-g2-1-pre-scoring-completion-2026-10-25.md)
(#665, `43d28d6d`) exactly.

**What it contains.** No case bytes, values or labels beyond what a
failure's mechanism needs. Cases are named by opaque `case_id` and class
only.

## 1. Setup and verified preconditions

All of these were verified before any case ran. `score` repeats each as a
precondition.

| Item | Verified value |
|---|---|
| Decryption | by the owner, to `C:/dev/g2-1-scoring/plaintext/g2-1-heldout-corpus.tar` (outside the repository) |
| Plaintext tar SHA-256 | `de8b70faa7ab5267628d6f488811ead48a6c088c1880872e61ec85a2bbd233f8`, equal to the freeze record (391 regular members) |
| `FILES.sha256` | `67ecd146f49c290c20e97387bb8ef478817bd57ba6ad3c4a18256281f6ac2dbc`; 390 of 390 entries verify; exactly those files plus `FILES.sha256` |
| Class counts | equal to the freeze record: 122 concealed, 7 public smoke |
| Harness | clone at `c0aba6b48dec1a814143b8385087f0b0d2dbca32`, clean, `core.autocrlf=false`; `harness.py` `76e5f8c19c53166429a273f184a7e5097a2a92bb53258c4d8806ce54fb5d1175`; shim `5663ac006457e591fb6c2ad7c5ff1deaad790e1190cae2a01ed58575f862b918` (both also recorded by `score`) |
| Implementation build | wheel `e35d98915a02bff31bf8915225389b31653daad12245a673e11c8a3069cc96b5`, tree `34ccbf62…6d66`, `pip freeze` `7620df07…da57`, CPython 3.12.10 |
| Baseline build | wheel `3497b5dd83942ef5df06fe522acaaa7e6e2833759dfdd25daa8866f65dacd1b2`, tree `002fdddb…72f2`, `pip freeze` `220d6cd8…f86a`, CPython 3.12.10 |
| Symlink probe | `capable: true`, both before scoring and inside `score` |
| Host identity input | `2.1.310` / `f9a3920634ae3b961ee92c2eb58d0051f5f8852b120983d0a4f57b6a5efeba61` (§8.B, #646) |

**Scoring command.** It ran once, from `C:/dev/g2-1-scoring/mneme` at
`c0aba6b4`. That one invocation runs both passes at the same run-root path,
then G7. Exit status 1 (FAIL).

```text
python benchmarks/adr034_g2_1/harness.py score \
  --corpus C:/dev/g2-1-scoring/corpus/g2-1-heldout-corpus \
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

The corpus root inside the tar is `g2-1-heldout-corpus/`. The harness was
not edited after decryption.

## 2. Results (122 concealed cases)

| Gate | Result | Failing / applicable |
|---|---|---|
| G1 Unsafe pass | PASS | 0 / 122 |
| G2 False block | PASS | 0 / 84 |
| G3 No mutation | PASS | 0 / 122 |
| G4 Reasons | **FAIL** | 1 / 35 |
| G5 Parity (hook and checker level, Amendment 2) | PASS | 0 / 37 |
| G6 Evidence | **FAIL** | 3 / 122 |
| G7 Determinism | PASS | raw harness report `0 / 129`; the comparison covers the 122 concealed cases (see the G7 disclosure in §4); the two runs are byte-identical |
| G8 Completeness | PASS | 0 / 122 (no scoring-process failure) |

**G7 identity.** Each per-run file has the same SHA-256 in run 1 and run 2:

| Per-run file | SHA-256 (run 1 = run 2) |
|---|---|
| `cases.jsonl` | `a8dbf76fa4e028ecabe7a17f97c88174cf1435ca3142f86c35c183a61da880fc` |
| `summary.json` | `e2e5f66757bed8abf5429efd35e26583253f31104b9768b7263ca9d312e202d4` |

## 3. Failures and diagnosis

The diagnosis was authorized by the owner after scoring. Diagnostic replays
are diagnostic only and change nothing.

**Every classification below is PROVISIONAL.** It is the scorer's
diagnostic reading, not conclusive proof that an implementation defect or a
label error is ruled out. The four case failures and the overall FAIL stand
exactly as observed, whatever any later ruling decides.

The classes:

- **IMPLEMENTATION DEFECT:** the build departs from the contract;
- **LABEL ERROR:** the label departs from the contract;
- **HARNESS DEFECT:** the harness mis-scored the case;
- **AMBIGUOUS:** the contract does not decide the case.

| Case | Class | Gate (reasons) | Diagnosis |
|---|---|---|---|
| `g2h-3c14e161e8` | V | G6 (`relevant_enforcement_observed`) | **AMBIGUOUS** (D1), provisional |
| `g2h-c30ea85ef5` | V | G6 (`relevant_enforcement_observed`) | **AMBIGUOUS** (D1), provisional |
| `g2h-aa1649b8a0` | US | G4 (`primary_reason`) | **AMBIGUOUS** (D2), provisional |
| `g2h-6eacd08e5d` | C | G6 (`cause`, `relevant_enforcement_observed`, `…_per_rule`) | **AMBIGUOUS** (D2), provisional |

**D1: case-level relevance with more than one applied numeric rule.**

Both cases have two applied numeric rules. One is violated, and the hook
refuses in strict mode, attributably to that rule. The other is unevaluated
in one case and recognized clean in the other. The harness's per-rule values
equal the labels exactly in both cases. Only the single case-level value
differs:

| Reading | Rule | `3c14e161e8` | `c30ea85ef5` |
|---|---|---|---|
| Labels | `true` when a numeric violation's refusal is attributable | `true` | `true` |
| Harness | conjunction of per-rule A1.3 values (#651 Q2, accepted provisionally) | `false` | `false` |
| Implementation's own validator (diagnostic replay) | every applied rule decided, and the disposition attributable | `false` | `true` |

**Governing clauses:**

- Amendment 1 A1.3 defines `relevant_enforcement_observed` per scenario, for
  one attributable numeric outcome;
- G6 requires one expected value per case;
- charter §6.2 records "each applied numeric rule".

None of them defines how per-rule relevance combines into a case value when
more than one numeric rule applies.

**Two separate points:**

1. **The contract gap.** ADR-034's attribution definition has a genuine gap
   at the case level: it doesn't say how several numeric rules' attribution
   combines into one case value.
2. **The scoring interpretation.** The conservative conjunction (#651 Q2)
   was explicitly accepted for this harness before decryption, and it
   decided these two G6 failures. That the labels disagree with it is a fact
   about this pre-registered interpretation. It is kept distinct from the
   contract gap, and it does not change the observed failures.

**D2: a same-named method `def` in a class body.**

In both cases a class body defines a method with the declared call
function's name.

- **US case:** the only call is a method call, so no direct bare-name call
  exists.
- **C case:** a module-level function of that name exists, and a compliant
  direct bare-name call is present.

The build's matcher (`mneme/numeric_rule.py:742-760`, the M4-validated
matcher, unchanged by G2-1) treats any binding of the name other than the
single module-level declaration as shadowing or rebinding. The whole call
source therefore becomes `AMBIGUOUS_BINDING` (ADR-034 §4 priority 3). The
labels follow Python scoping, where a class-body `def` binds only in the
class namespace. They expect:

- US: `SOURCE_NOT_FOUND` (priority 4);
- C: `RECOGNIZED`/`NO_VIOLATION`, relevance `true` and cause `no_violation`.

The C case's G6 failures (`cause`, relevance) follow from the matcher result:
it was unevaluated and proceeded as `fail_open`.

**Governing clauses:**

- ADR-034 §3: "the function is shadowed, rebound or escapes as a value";
- the v1 confirmed interpretations that bind ADR-034 labels
  ([`adr-034-heldout-corpus-freeze-2026-10-22.md`](adr-034-heldout-corpus-freeze-2026-10-22.md)):
  - AMB-03: calls in method bodies count "when not shadowed";
  - AMB-07: a same-named parameter shadows.

None of them decides whether a same-named method `def` in a class body
shadows or rebinds the module function. In both cases the build's reading
is the conservative one (unevaluated, never clean). G1 passes, and neither
case is an unsafe pass or a false block.

D2 has **competing interpretations** (Python scoping against "rebound
anywhere in the module"). Settling it needs a future architectural ruling.

**Provisionally, no failure is classified as an implementation defect, a
label error or a harness defect.** All four are read as resting on D1 and
D2. These readings do not prove that such defects are absent. Each gap needs
an owner ruling or an ADR-034 amendment before any new corpus is written.

## 4. Disclosures

- **Amendment 2.** It applied to **2 cases, both class L**. In both, the raw
  stdout, stderr and exit bytes did **not** match between the builds. Both
  passed the Amendment 2 comparison:
  - compared byte for byte: stdout, exit status, the ordered exception
    summary lines, the chain separators and all non-traceback stderr;
  - left out: only the traceback frame lines;
  - scope: decided by the baseline's own run (a nonzero exit with a complete
    traceback block).

  No other G5 case needed the traceback diagnostic.
- **Label conformance (non-gating, its own count).** 2 of 122 concealed
  cases disagree with at least one ungated label; 120 agree in full. Both are
  the D2 cases (`g2h-6eacd08e5d`: `matcher_status`, `matcher_outcome`,
  `unknown_source_reasons`; `g2h-aa1649b8a0`: `primary_reason`,
  `unknown_source_reasons`), provisionally classified **AMBIGUOUS** (D2).
  This count is never folded into the gates.
- **G7 denominator (harness reporting defect).** The raw harness report
  reads G7 PASS `0/129`. That count wrongly includes the 7 public smoke
  cases, which the pre-registration excludes from every gate denominator
  (G2V-F4).
  - **What G7 actually compares:** the concealed-only files,
    `run-<n>/cases.jsonl` and `run-<n>/summary.json`. That is the **122
    concealed cases** across two byte-identical runs.
  - **The smoke cases** are written to separate files that G7 does not
    compare, so they did not affect the G7 verdict.
  - **Effect:** the denominator is a reporting defect in the frozen harness.
    It does not change the observed PASS. The harness is not edited after
    decryption (pre-registration §6), so the raw output is kept here as reported, for
    auditability.
- **Public smoke cases (non-gating, outside every denominator).** All 7 pass
  every gate, with 0 label mismatches, and are identical across both passes.
- **Synthetic scoring is not live-host evidence.** The harness computed
  `relevant_enforcement_observed` from evidence records and the pinned §8.B
  host identity (Amendment 1 A1.3). No "relevant enforcement observed",
  enforcement or production claim is made.

## 5. Failure policy (pre-registration §6)

- **G2-1 validation FAILS** on G4 and G6.
- **This corpus is not re-scored.** Replays on it are diagnostic only.
- **Nothing was tuned**, and the harness, implementation, corpus and labels
  are unchanged.
- **The path to a PASS claim.** Any fix, ruling, label correction or ADR-034
  amendment arising from D1 or D2 needs a **new held-out corpus and a new
  pre-registration** before G2-1 can claim PASS.

## 6. Output artifacts

They were written outside the repository, under `C:/dev/g2-1-scoring/out/`.
They are now held only in the encrypted evidence archive (§7).

| File | SHA-256 |
|---|---|
| `summary.json` (final, with timestamps; not compared by G7) | `c2e7eb8de5efbf9cd2e7d02b112baf88fcecb23672624033ed23ca8f1e3a68a8` |
| `run-1/cases.jsonl` = `run-2/cases.jsonl` (private evidence) | `a8dbf76fa4e028ecabe7a17f97c88174cf1435ca3142f86c35c183a61da880fc` |
| `run-1/summary.json` = `run-2/summary.json` | `e2e5f66757bed8abf5429efd35e26583253f31104b9768b7263ca9d312e202d4` |
| `run-1/smoke_cases.jsonl` = `run-2/…` | `b69af19ba7b8c7d1b5feea60459c3879f3b497a3b2200b552dd8855b7a0a293a` |
| `run-1/smoke_summary.json` = `run-2/…` | `0b9c876de4b2cef8e9ce147052e4e438c6f2a0f22ea95d2e14eea55404d80b30` |

## 7. Custody (metadata only)

**Evidence archive.** A deterministic tar holds every scoring output and the
scorer's diagnosis evidence:

- the 9 scoring output files listed in §6 (the final `summary.json`, plus the four
  per-run files for each of the two runs);
- `diagnosis/diagnosis.md`;
- an inner manifest, `EVIDENCE_FILES.sha256`
  (`51b899f8a06ef541b90ac2953299c353266ca577e40dc66d0dffd0e7002b4cda`).

The tar has sorted entries, a fixed mtime of 2026-10-25T00:00:00Z, and
uid/gid 0. It is encrypted to the owner key (primary
`88CE4C9F66A5F3CA7F1C0A484839E24F94E4F796`, encryption subkey
`C4370AB8829450C5`).

| Item | SHA-256 |
|---|---|
| Evidence tar (plaintext) | `c57eec8f4dddfa55252024a18a7163ad4b193b7e8faa7d07d750a12c6112641c` |
| Evidence ciphertext `C:/dev/mneme-heldout-034-g2-sealed/g2-1-scoring-evidence.tar.gpg` | `a332fcbdd50ed7cf89c053cda3e2234ca5785054a4988ffc920885fc3a0fd916` |

**Owner verification (2026-10-26).**

- The owner decrypted the evidence ciphertext through subkey
  `C4370AB8829450C5` into `%TEMP%`.
- The decrypted tar hashed to `c57eec8f…641c`, matching the tar above.
- The temporary copy was deleted, and its absence was confirmed.

**Plaintext removal.** This is verified file absence. Deletion does not prove
physical erasure on an SSD, and no unrecoverability claim is made. After the
owner's verification, these locations were deleted, and each was then
confirmed absent:

| Path | Held | State |
|---|---|---|
| `C:/dev/g2-1-scoring/plaintext/` | the decrypted corpus tar | absent |
| `C:/dev/g2-1-scoring/corpus/` | the extracted corpus | absent |
| `C:/dev/g2-1-scoring/out/` | the scoring outputs | absent |
| `C:/dev/g2-1-scoring/diagnosis/` | the diagnosis notes | absent |
| `C:/dev/g2-1-scoring/evidence/` | the plaintext evidence tar | absent |

No harness run root remains: `C:/dev/g2-1-scoring/run` and the default
`%TEMP%` run roots are absent.

**Kept, and re-hashed after removal.** Both match their recorded values:

| File | SHA-256 |
|---|---|
| Evidence ciphertext | `a332fcbdd50ed7cf89c053cda3e2234ca5785054a4988ffc920885fc3a0fd916` |
| Sealed corpus ciphertext `g2-1-heldout-corpus.tar.gpg` | `016a6134bc71f5c531981c101373dad8c562b83da24dcd9b154644ad85205ae4`, as in the freeze record |

**What remains under `C:/dev/g2-1-scoring/`.** None of it holds case
content:

- the pinned harness clone;
- the two build environments;
- `build.log`;
- `score.log`, which holds only the gate headline and the result line.

## 8. Isolation statement (scorer)

**Read for scoring and this record:**

- the pre-registration with Amendments 1 and 2;
- the freeze record;
- the §8.B record;
- the pre-scoring completion record;
- the merged harness;
- the decrypted corpus:
  - all cases through the harness;
  - for diagnosis, after scoring and as authorized, the four failing cases'
    `case.json`, `envelope.json` and `expected.json`;
- the scoring outputs;
- for diagnosis:
  - `mneme/numeric_rule.py` and `mneme/integrations/claude_code/hook.py` at
    `6e26c534`;
  - the v1 and M4 freeze records;
  - the G1 charter.

**Not read, opened or copied:**

- the provenance archive;
- `SEAL_RECORD.md`;
- any corpus-author, implementation or orchestrator transcript or note.

The ciphertexts were never opened by the scorer; decryption was the
owner's.
