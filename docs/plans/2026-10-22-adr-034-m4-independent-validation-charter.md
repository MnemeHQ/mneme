# ADR-034 / M4: independent validation charter (corrected whole-file numeric audit)

**Date:** 2026-10-22
**Status:** **PROPOSED.** The owner accepts it by merging this PR. Merging
freezes the M4 design below and nominates the implementation pin. It does
**not** authorize corpus authoring, harness work or scoring; each of those
needs its own owner authorization (§9).

**Repository baseline examined:** `MnemeHQ/mneme` `main` at
`f25f0e845f344944dc25d085bffafbd1855c5a7d`.

**Normative anchors (blobs at the baseline):**

- accepted [ADR-034](../adr/ADR-034-static-numeric-upper-bound-typed-rule.md),
  blob `6f4ea66d79ce3964d8cfd4b6a2d8e6f0ae2d86e9`;
- frozen [evaluation criteria](2026-10-21-adr-034-pre-registered-evaluation-criteria.md),
  blob `7ca1f39ed468df37a2290bfe54f0bf771d11341d` (protocol freeze `2298c946`);
- accepted [G1 behavioral charter](2026-10-22-adr-034-g1-behavioral-charter.md),
  including its §3 item 4 F-1 erratum, blob
  `23281aa0f56353dd8390582c6443b17adb0fa43a`;
- [v1 corpus freeze record](../validation/adr-034-heldout-corpus-freeze-2026-10-22.md),
  blob `3d1607060ad16f72c7a139b6299d24435b825bf6`, for its 17 confirmed
  interpretations and custody method only;
- [G1 results record](../validation/adr-034-g1-heldout-scoring-2026-10-22.md),
  blob `911463df6fb7aa54401d54389f342fbd8e4b3f54`;
- the ADR-034 G1 amendment in
  [`docs/architecture/layer1-freeze-e73ff7d.md`](../architecture/layer1-freeze-e73ff7d.md)
  (#603, `ec72ba9f`).

## 1. Purpose and claim scope

M4 is a new, independently pre-registered held-out validation of the
`FORBID_NUMERIC_ABOVE` G1 whole-file audit **after** the F-1 correction
(#613). It is required by criteria §5 ("On failure"): fixes after scoring need
a new held-out set for any claim.

**If every gate passes,** the only claim is: the pinned G1 Python whole-file
audit passes the frozen protocol on the M4 synthetic corpus.

**Never claimed by M4:** pre-write (G2) protection, CI enforcement,
generalization to real repositories or beyond the synthetic corpus, other
languages, or any change to the G1 outcome.

## 2. Relationship to G1

- **G1 stays FAIL** (149/155, finding F-1). M4 never edits, re-scores or
  reinterprets the G1 record.
- **Sealed v1 is never reused.** No v1 case, label, rationale, answer-key
  entry, case ID or G1 per-case result may be read, copied, adapted or used as
  a template by any M4 role. v1 custody conditions stay in force.
- **Public material stays public.** The 18 set R vectors, the 17 confirmed
  interpretations and the G1 results record are public and may be read. Set R
  is scored but is not blind evidence, as in G1.

## 3. Protocol: the frozen criteria, unchanged

M4 is scored under criteria blob `7ca1f39e` **as frozen**: the categories and
quotas (§2), the scoring partitions and denominators (§3), the metrics (§4),
all twelve gates including 3a (§5), the failure policy (§5) and the reporting
rules (§6). No gate, threshold, denominator or definition is restated,
reweighted or amended here.

This charter adds only what the criteria leave to a validation run:

- the implementation pin (§4);
- the invocation matrix (§5, ruling B1);
- the scoring harness and manifest schema (§6, ruling B2);
- roles and isolation (§7);
- corpus composition choices within the criteria floors, and custody (§8).

**Procedural sequence (M4-specific).** The criteria's sequence (owner ruling
N8) puts the corpus freeze before the implementation. In M4 the corrected
implementation already exists, so M4 pre-registers its own prospective
sequence (§9): pin the implementation, then author and freeze a new corpus
under the §7 isolation rules, then pin the harness, then decrypt and score.
This is an M4-only procedure. It reuses the criteria's scoring definitions
and gates unchanged, and it does not revise the historical G1 protocol or its
outcome.

Where this charter and the criteria disagree, the criteria win, and the
disagreement is a defect to be fixed by a reviewed amendment **before**
decryption.

## 4. Implementation pin

| Item | Pinned value |
|---|---|
| Commit | `f25f0e845f344944dc25d085bffafbd1855c5a7d` |
| `mneme/` tree | `002fdddb254267d42a3810cfea669d75700372f2` (identical at `b0dc1a14`, the #613 squash; #612 changed docs only) |
| Repository tree | `a55c1462a04302678485c11fc4a23e8987ba830d` |
| `pyproject.toml` blob | `8daae76f04fdd07f78b493fde845215839b6c59c` |
| Runtime | CPython **3.12.10** exactly (the pinned grammar) |
| Artifact | A wheel built from the pinned commit; its SHA-256 is recorded in the pre-scoring record |
| Dependencies | The repository has no lockfile and `PyYAML>=6.0` is unpinned. The scoring environment's full `pip freeze` output and its SHA-256 are recorded in the pre-scoring record, and both runs use that one environment |
| Old reader (gate 12) | `mneme-hq==0.10.0` from PyPI, installed in a separate environment; its full wheel SHA-256 is recorded |

**Rules:**

- Merges to `main` after the baseline do not move the pin. The scored code is
  whatever has `mneme/` tree `002fdddb…`; the harness verifies that tree hash
  before running and treats a mismatch as an operational failure.
- No implementation change is allowed between this charter's merge and the
  results record. A defect found by M4 is reported, never fixed and re-scored
  as blind (criteria §5).
- **Pin precondition (ruling B3):** the pin is scorable only after the
  `[layer1-freeze]` record of the #613 conformance correction is merged
  (§13, B3). That record changes no code, so the pin is unaffected.

## 5. Invocation matrix (ruling B1)

Every scored case runs through the shipped CLI of the pinned build, in strict
mode, with JSON output:

```text
mneme check --memory <case>/.mneme/project_memory.json \
  --query "audit" --mode strict --json <transport>
```

The query string is fixed. Numeric typed-rule evaluation is not limited by
retrieval relevance (ADR-017, G1 charter §2).

**Memory:** each case's memory is built by the pinned build from the
author-supplied ADR markdown (ADR-034 §2 authored form), with
`mneme adr import <contract_dir> --memory <case>/.mneme/project_memory.json --apply`.
An import failure is an operational failure (criteria §3).

| Stratum | Transport | Notes |
|---|---|---|
| A, W, U, N1, R | `--source-file <path>` | Path inside the policy root, a regular `.py` file, not a symlink (G1 charter §3) |
| A9 | `--source-file <path>` | Path that the shape's selectors exclude; scored for applicability only |
| **N2a** | `--input <path>`, **no** `--target-path` | The input file is placed at each of the four locations below |
| **N2b** | `--input <path> --target-path <governed path>` | The target path is one the rule's selectors APPLY to |

**N2a locations**, at least one case each:

1. L1: inside the rule's `include_paths`;
2. L2: inside the policy root but outside `include_paths`;
3. L3: at the policy root itself;
4. L4: outside the policy root.

**N2 expectations** follow ADR-034 §6 and G1 charter §3 item 4: every N2 case
is `MATCHER_UNEVALUATED` / `INCOMPLETE_SOURCE_INPUT`, decided before parsing,
never a clean result. An N2 case is scored only on that outcome and its
primary reason (criteria §3). Its path applicability (APPLIED, EXCLUDED or
UNKNOWN) is recorded but not scored.

**Not scored in M4:** `--input` with a `--target-path` that the selectors
EXCLUDE. That is an applicability outcome, not a non-source outcome, and the
criteria give it no stratum.

**Stdin:** `mneme check` has no stdin transport. "Stdin text" in criteria §2.5
is represented as stdin-style text in a file passed to `--input`. This is a
disclosed limitation, not a scored stdin path.

## 6. Scoring harness and manifest schema (ruling B2)

**Harness.**

- Written by the scorer (§7) **before decryption**, from this charter, the
  criteria and ADR-034 only, with no case data.
- Merged publicly under `scripts/` or `benchmarks/` in its own PR, and pinned
  by commit and SHA-256 in the pre-scoring record.
- It verifies the `mneme/` tree hash and the CPython version, builds each
  case's memory, applies the §5 invocation matrix, captures payload, exit code
  and trust-validator result, compares against the manifest, computes every
  criteria §4 metric and §5 gate, and writes per-case JSONL plus one summary
  JSON.
- **Normalization** (gate 9) is limited to replacing the per-run temporary
  root path string. Any other normalization is a protocol deviation and
  invalidates the run.
- Gate 11 (golden rule IDs) and gate 12 (old-reader refusal) are run by the
  harness against the pinned build and the §4 old reader.
- **After decryption the harness is not edited.** A harness defect found
  after decryption that would change any scored outcome, metric or gate
  **invalidates the M4 blind claim**. The results record reports the run as
  invalidated, with the defect disclosed. A corrected harness may replay the
  revealed cases for **diagnostics only**; a replay is never a blind result
  and never counts toward any gate. Any further blind claim needs a fresh,
  newly concealed corpus under a new pre-registration.

**Manifest schema.** One JSON object per case, in `manifest.jsonl` inside the
sealed archive. The author writes to this schema; the harness reads it.

| Field | Content |
|---|---|
| `case_id` | Opaque ID, not derived from any v1 ID and revealing nothing about the case content or label. Withheld from the freeze record; published only in the results record (§10) |
| `stratum`, `category`, `shape` | As in criteria §2 (`shape` is `R<n>` for set R) |
| `contract` | Relative path to the case's ADR markdown directory |
| `invocation` | `{transport: source_file \| input, path, target_path?, location?}`; `location` is `L1`..`L4` for N2a |
| `expected` | `{applicability, matcher_status, matcher_outcome, primary_reason, unknown_sources, evaluation_complete}` |
| `rationale` | Written source-level rationale (criteria §2.1) |

`unknown_sources` is a list of `{kind, line, reason}` and is required for A7.
Fields that do not apply are `null`, never omitted.

## 7. Roles and isolation

| Role | Who | Constraints |
|---|---|---|
| Owner | The repository owner | Adjudicates ambiguities before the freeze, holds the decryption key, decrypts only after the pre-scoring record is merged |
| Corpus author | A **new** session | See the read lists below |
| Scorer | A **new** session, not the corpus author | Writes and pins the harness before decryption; receives the corpus only after the pin and harness are verified; runs both scoring passes |
| Orchestrator | The session that drafted this charter | Coordinates only. Never authors, scores or sees case material |

**Barred from authoring and scoring:** the v1 corpus-author session, the G1
orchestrating session, the G1 scorer session, the #607 and #613
implementation sessions, and the M4 orchestrator. The v1 confidentiality
conditions continue to bar the v1 author and G1 orchestrator from any
implementation work.

**The corpus author may read:** ADR-034; the frozen criteria; G1 charter §3–§6
(the contract surface); the 17 confirmed interpretations in the v1 freeze
record, which are **binding** on M4 labels; this charter.

**The corpus author may not read:** `mneme/` numeric matcher, enforcer, CLI or
hook source; `tests/test_numeric_upper_bound_*` and their fixtures; the PR
bodies or diffs of #607 and #613; the G1 results record's F-1 section beyond
what this charter states; any v1 material or G1 transcript. The author records
an isolation statement listing what was read.

**New ambiguities** go to the owner as a sanitized brief, as in v1, and are
ruled on before the freeze. A ruling that would change ADR-034 stops M4 and
returns to architectural review.

## 8. Corpus composition and custody

**Composition.** Every criteria §2 floor is met. Choices within the floors:

| Stratum | Cases |
|---|---|
| A, scored (S1/S2/S3/S4/S5 = 9/9/10/10/10) | 48 |
| A9, applicability only (1 per shape) | 5 |
| U (5 per shape) | 25 |
| N1, parse failure | 3 |
| **N2, non-source input** | **12**: N2a 8 (2 per location L1–L4), N2b 4 |
| W (10 per shape) | 50 |
| R (public, not blind) | 18 |
| **Total** | **161** (143 concealed) |

**N2 content.** Across the 12 N2 cases, each criteria §2.5 kind appears at
least twice: prompt text, code fragment, introduced-delta text, stdin-style
text. **At least 6** N2 cases are valid Python that parses and contains only
compliant values for the rule. N2 cases are written from ADR-034 §6 and
criteria §2.5, and must not copy the #613 test fixtures.

**W.** A new W composition spec is written and its SHA-256 recorded before the
first W case is written (criteria §2.7).

**Custody**, following the v1 method:

- deterministic tar of the corpus with a sealed `FILES.sha256`;
- encryption to the owner's OpenPGP key (primary
  `88CE4C9F66A5F3CA7F1C0A484839E24F94E4F796`);
- owner integrity verification of the ciphertext, archive, inner files and
  W-spec hash. Verification on a local machine is preferred over a hosted
  shell; whichever is used is recorded;
- a public, metadata-only freeze record (§10 artifact 2).

## 9. Sequence and authorizations

Each step needs its own explicit owner authorization.

1. **This charter** (docs only) and the B3 `[layer1-freeze]` record. Both merged.
2. **Corpus authoring and the harness PR,** in parallel. They share only this
   charter. Then owner adjudication and the metadata-only freeze record.
3. **Pre-scoring record:** harness commit and SHA-256, wheel SHA-256,
   `pip freeze` SHA-256, CPython and OS, old-reader wheel SHA-256.
4. **Decryption and scoring:** two runs in one environment, then a
   metadata-only results record.

## 10. Evidence artifacts

1. **This charter** (public).
2. **Freeze record** (public, metadata only): plaintext and ciphertext
   SHA-256, file count, case counts per stratum and per N2 location, W-spec
   SHA-256 and timestamp, ambiguity rulings, the author's isolation statement,
   and the chronology.
3. **Harness PR** (public), pinned by commit and SHA-256.
4. **Pre-scoring record** (public), with the §9 step 3 hashes.
5. **Results record** (public, metadata only): all twelve gates, the
   per-shape headline in the criteria §5 wording, both summary SHA-256 values,
   operational-failure count, and the §11 disclosures. As criteria §6
   requires, it lists **every** miss, false block, unsafe pass, unexpected U/N
   violation and wrong primary reason **by case**: one row per failure with
   the opaque `case_id`, stratum, category, shape, failure classification,
   and expected versus observed matcher status, outcome and primary reason
   (for N2, also the invocation form and location). No case source,
   rationale or other label content is published.
6. **Private evidence** (owner custody, outside the repository): per-case JSONL
   with the full ADR-029 binding for each verdict, both raw summaries, and the
   case bytes behind every listed failure.

## 11. Disclosures and limits

- **Blindness is partial.** F-1 and its correction are public. "Blind" here
  means the implementation was not fitted to these case bytes or labels, not
  that the failure class was unknown.
- **Order is inverted.** The criteria's sequence (owner ruling N8) put the
  corpus before the implementation; M4's own sequence is in §3.
  In M4 the implementation exists first, so independence is enforced on the
  corpus author's reading (§7).
- **Session isolation, not organizational independence.** All roles are AI
  sessions under one owner. Errors may be correlated where author and
  implementer share a model family; using a different model for the corpus
  author is recommended but not required.
- **Synthetic corpus only;** no generalization claim (criteria §1, §6).
- **No stdin transport** is exercised (§5).
- **Operational consequence of #613, out of scope here:** with numeric rules in
  memory, `mneme check --input` without `--target-path` exits 2 for every
  file, including policy-source files. This matters for warn-mode governance
  checks if a numeric rule is ever imported into this repository's memory.

## 12. Not authorized by this charter

- Corpus authoring, harness implementation or scoring (each needs §9
  authorization).
- Any production code, test, schema or CLI change.
- Any amendment to ADR-034, the frozen criteria, the G1 charter, the v1 freeze
  record or the G1 results record.
- Access to sealed v1 or any G1 per-case material.
- G2 pre-write numeric evaluation, CI integration, availability-policy
  changes, `DecisionRetriever` or `ConflictDetector` behavior changes, or
  memory import of ADR-034.
- Any enforcement or production claim before M4 passes.

## 13. Owner rulings (proposed; accepted on merge)

| ID | Ruling | Where reflected |
|---|---|---|
| B1 | N2 invocation is pre-registered: N2a `--input` without `--target-path` at four locations, and N2b `--input` with an APPLIED `--target-path`; N2 = 12 | §5, §8 |
| B2 | The scoring harness is public, written by the scorer before decryption, pinned by commit and SHA-256, and reads a pre-registered manifest schema | §6 |
| B3 | #613 (enforcer, CLI and shared hook validator) is recorded in the Layer 1 freeze document as a conformance correction to the existing ADR-034 G1 amendment, citing ADR-034 §6 and the charter §3 erratum. It authorizes nothing new and is a precondition for scoring the pin | §4; separate `[layer1-freeze]` PR |

## 14. Review history

- **First review (2026-10-22): ACCEPT WITH REQUIRED CORRECTIONS.**
  - R1: M4's prospective sequence is pre-registered as M4-specific; the
    scoring definitions and gates are reused unchanged and the G1 protocol is
    not revised (§3).
  - R2: a post-decryption harness correction that changes any scored result
    invalidates the blind claim; replays on revealed cases are diagnostic
    only (§6).
  - R3: the public results record lists every failure by opaque case ID, as
    criteria §6 requires, with case content kept private (§6, §10).
