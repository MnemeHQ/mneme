# ADR-034 G2-1 R2 blind scoring: results record (metadata only)

**Date:** 2026-10-27

**Verdict: FAIL** (exit status 1). G6 fails on 2 of 143 concealed cases.
All other gates pass. The R2 revalidation does not pass, and **G2-1 stays
FAIL**.

**What this record is.** It is the results record for R2 pre-registration
§8 step 6
([R2 pre-registration](adr-034-g2-1-revalidation-preregistration-2026-10-26.md),
with R2 Amendments 1 and 2). Scoring followed the merged
[R2 pre-scoring completion record](adr-034-g2-1-r2-pre-scoring-completion-2026-10-27.md)
(#690, `6fbe6297`) exactly. The harness, builds and labels were not edited
after decryption.

**What it contains.** No case bytes, literal values, case file paths or
label content beyond the cause-check fields named in §4. Cases are named by
opaque `case_id` and class only.

**What it does not claim.** No enforcement claim, "relevant enforcement
observed" claim or production claim.

## 1. Setup and verified preconditions

Every item below was verified before any case ran. `score` repeats each one
as a precondition.

| Item | Verified value |
|---|---|
| Decryption | by the owner, through subkey `C4370AB8829450C5`. Ciphertext `32b3510a660b997452d6fb2ff25ad8f0731ada82a8dc2093aa2930821643bf38` matched. Written to `C:/dev/g2-1-r2-scoring/plaintext/g2-1-r2-heldout-corpus.tar`, outside the repository |
| Plaintext tar SHA-256 (step 1) | `17a46379cfbb04ec41cc7e740a9f52ce1f94e48e154a2178987ca56af22dcfe1`, equal to the freeze record (#687) |
| Extraction (step 2) | exit 0, to `C:/dev/g2-1-r2-scoring/corpus/g2-1-r2-heldout-corpus/` |
| `FILES.sha256` (step 3) | `70d35226584bead131929deb41e3e3f59a5307d0ae34fe49b29426692a749c0d` |
| Entries (step 4) | 605 of 605 OK, 0 failed. Exactly those files plus `FILES.sha256`, with 0 links |
| Class counts | equal to #687: 143 concealed, 13 public smoke. The harness reported no corpus findings |
| Harness | clone at `d1eda40e9864296aa289945b27249cbaa74b47b4`, clean before and after scoring |
| Implementation build | wheel `50955f0d3648b392469e60b2e1df72d8043b578db0c5066c9a4763b549223056`, tree `6cb14c2b…e5e4`, `pip freeze` `c37736ef…5de0`, CPython 3.12.10, 111 installed files matching the wheel |
| Baseline build | wheel `3497b5dd83942ef5df06fe522acaaa7e6e2833759dfdd25daa8866f65dacd1b2`, tree `002fdddb…72f2`, `pip freeze` `7202877c…d4e5`, CPython 3.12.10, 111 installed files matching the wheel |
| Host identity input | `2.1.310` / `f9a3920634ae3b961ee92c2eb58d0051f5f8852b120983d0a4f57b6a5efeba61` (#646; the re-pin in #690 matched) |
| Symlink probe | `capable: true`, `error: null`, inside `score` |

**Harness digests,** recorded by `score` in `summary.json` and compared with
the #690 §1 pins:

| File | `summary.json` | Pin | Match |
|---|---|---|---|
| `harness.py` | `0a54eec6ffd3f7f8d3a2d0ab015b3ee6664e35e3559e49d49d58b77afc9a8232` | same | yes |
| `observe_shim/sitecustomize.py` | `9ba833115634aec4bb00e986d74cd2f26f17327e941bc35900487faafaeadc13` | same | yes |

**Scoring command.** The #690 §8 command ran once, from
`C:/dev/g2-1-r2-scoring/mneme`, between 2026-10-27T18:33:08Z and
18:46:46Z. It exited with status 1 (FAIL). That one invocation runs both
passes at the same run-root path, and then G7.

**Final `summary.json` SHA-256:**
`e8b09f70399389bf107da57b655362b629b524cec3a3fa9bb3dcbd35b2ae4abc`.

## 2. Gates

The counts give the failing cases out of the cases each gate applies to,
over the 143 concealed cases.

| Gate | Failing / applicable | Result |
|---|---|---|
| G1 | 0 / 143 | pass |
| G2 | 0 / 95 | pass |
| G3 | 0 / 143 | pass |
| G4 | 0 / 61 | pass |
| G5 | 0 / 35 | pass |
| **G6** | **2 / 143** | **FAIL** |
| G7 | 0 / 143 | pass |
| G8 | 0 / 143 | pass |

**G5 under the carried R1 Amendment 2.** 2 cases were in scope, both class L.
Both pass under that rule, and neither was byte-identical before it applied.
There were no stderr diagnostics.

**G7 identity.** The two passes are byte-identical:

| File | Run 1 SHA-256 | Run 2 SHA-256 |
|---|---|---|
| `cases.jsonl` | `956bbc34f835389983bc6a76731be3e3bd31e15e50a810d4cd3b8c83078fecf1` | same |
| per-run `summary.json` | `f70bf0b38c38c72ed65030a7501c629496b793ee616b80c30f901e06b5e90afb` | same |

## 3. Non-gating results

**Label conformance:** 0 of 143 concealed cases have a mismatch, and 143
agree fully.

**R2 Amendment 2:** it was applied. The `g6_routed_fallback` flag marks 2
cases, both class L, and both pass G6 with a trusted `evaluation_complete`
of `false`. No case is excluded from any gate.

**Public smoke** (`--public-smoke`, which does not gate):

- the manifest `b60394c0…ab0c` verifies, 57 of 57;
- all 13 of 13 cases are clean on every gate;
- the two passes are identical;
- there are 0 label-conformance mismatches;
- no case ID is shared with the corpus.

## 4. G6 failures

| `case_id` | Class | G6 check | Expected | Observed |
|---|---|---|---|---|
| `r2-5052ef6ddd` | LIT | cause | `expected_cause` = `literal_violation` | `disposition.cause` = `other_rule`, with `violations` = `[]`. The harness's cause table gives `unmapped:other_rule` |
| `r2-7bff51945c` | LIT | cause | `expected_cause` = `literal_violation` | `disposition.cause` = `other_rule`, with `violations` = `[]`. The harness's cause table gives `unmapped:other_rule` |

**Where this check runs.** The cause check runs inside `score_g6` after the
record join, the outcome check and the mode check, and before the ordered
steps. The harness's cause table (AMB-R2-08, accepted in the #688 review as
Q2) maps `other_rule` to `literal_violation` only when the record's own
`violations` list names a `FORBID_LITERAL` rule and no numeric rule.

**Everything else about these two cases passed:**

- There is exactly one evidence record.
- `schema` is `mneme.hook_evidence/v1`.
- `hook_outcome` is `refused`, the hook exited with status 2, and the mode
  is `strict`.
- The rule-ID set (empty), per-rule relevance (`{}`), event-level relevance
  (`false`) and `evaluation_complete` (trusted `true`) all match.
- G1 through G5, G7 and G8 pass. The write was blocked.

## 5. Post-scoring diagnosis (does not change the verdict)

This diagnosis was authorized by the owner after scoring. Its scope was
limited to:

- the two failing cases' plaintext;
- their run-1 and run-2 evidence;
- the pinned implementation's installed source.

Nothing was re-run, and the harness, builds and labels were not edited. The
verdict stays FAIL.

**Classification: (a) implementation.** `dbab816f` emits
`disposition.cause = other_rule` with an empty `violations` list for a
block decided by a literal rule. The label `literal_violation` is correct
for these cases. The harness table reads only the record's own fields, so
no table could recover the literal identity from this record.

**The mechanism, in the pinned source:**

1. **The checker omits the subject record.** With `--json`, `mneme check`
   builds its payload in `mneme/cli.py`. It adds a `subject` record only
   when the input kind is `complete_source_file`, or when
   `CheckResult.has_numeric_rules` is true. That property, in
   `mneme/enforcer.py`, is true when any applicability record has rule type
   `FORBID_NUMERIC_ABOVE`.

   The routed pre-write call (`--proposed-new-file`) produces neither. So in
   both failing cases the trusted payload carried the literal violation but
   no `subject`. That is permitted: in `hook.py`,
   `_ACCEPTED_SUBJECT_KINDS["proposed_new_file"]` includes `None`.
2. **The hook then drops the violation identities.**
   `build_evidence_record` in
   `mneme/integrations/claude_code/hook.py` fills `rules` and `violations`
   only when `_subject_kind(payload) == "proposed_new_source"`. With no
   subject, both stay `[]`, and `checker.subject` is `null`.
3. **The cause is set without them.** `_verdict_cause` returns `other_rule`
   for any block with no numeric violation. So the record shows a trusted,
   complete refusal with cause `other_rule` and no rule identities.

**Why the other LIT cases pass.** These were checked from derived scoring
metadata only. The other 5 concealed LIT cases, and the public LIT smoke
case, had a numeric applicability record, so their subject record was
present. Their `violations` lists name `FORBID_LITERAL`, plus
`FORBID_NUMERIC_ABOVE` where that rule fired. They therefore map correctly.

In the two failing cases there was no numeric applicability record:

- one case's compiled memory holds only `FORBID_LITERAL`;
- the other's also holds a `FORBID_NUMERIC_ABOVE` rule, but that rule
  produced no applicability record for the target (`rules` = `[]`).

**What this does and does not affect:**

- **Not affected: enforcement.** The literal block itself is correct: exit
  2, `refused`, target absent, and parity holds.
- **Affected: the evidence record's attribution.** A refusal by a non-numeric
  rule, on a routed write with no numeric applicability, cannot be told
  apart in the record from a refusal by any other non-numeric rule.

This is the gap that G6's cause check (R2 §5, with the AMB-R2-08 mapping)
detects. Changing the hook, the CLI or the harness is outside this record.

## 6. Custody

Custody close is **on hold**, pending the owner's approval. These are still
in place under `C:/dev/g2-1-r2-scoring/`, outside the repository:

- the plaintext tar;
- the extracted corpus;
- the run root;
- the outputs, including both `cases.jsonl` files.

The sealed folder was not touched.

## 7. Isolation statement (scorer)

**Read during scoring and diagnosis:**

- the R2 pre-registration and its amendments;
- the #687, #690 and #646 records;
- the harness at `d1eda40e`;
- the pinned implementation's installed `mneme/` source;
- the scoring outputs;
- for the two failing cases only, their `case.json`, `expected.json` and
  compiled-memory rule types.

The diagnosis also used derived scoring metadata of the other LIT cases (no
case bytes): rule types, whether a subject was present, and violation rule
types.

**Not read:**

- any other concealed case's plaintext;
- any provenance material;
- any author transcript or note;
- the sealed folder.

No gpg operation was run by the scorer.

## 8. Not authorized by this record

- **Custody close:** encrypting the evidence, or shredding or deleting any
  plaintext.
- **Fixes:** any fix to `mneme/`, the harness or the labels, and any
  re-scoring of R2.
- **Claims:** any PASS, enforcement or production claim. **R2 is FAIL. G2-1
  stays FAIL.**
