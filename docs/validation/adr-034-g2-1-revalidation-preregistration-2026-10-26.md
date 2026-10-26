# ADR-034 G2-1 revalidation pre-registration (R2: corrected build, new held-out corpus)

**Date:** 2026-10-26
**Status:** PROPOSED. Once merged, this pre-registration is frozen, and with
it the corrected implementation it pins. Changing it afterwards needs a
dated, owner-approved amendment that is merged **before** decryption. No
change is allowed after unblinding.

**Authorization:** on 2026-10-26 the owner approved freezing the corrected
build and running a new independent blind validation. This follows the G2-1
FAIL, the D1 and D2 rulings, and the merged fixes.

**Revision 2** (2026-10-26) answers the pre-merge review, which requested
changes. It makes three protocol corrections. None of them is based on any
case content.

- **R2V-F1:** G2 false blocks now cover the SC and MR cases that are expected
  to proceed (§5).
- **R2V-F2:** the owner ruled on 2026-10-26 that §7b table row 4 is stated
  noncoverage for R2. MR covers rows 1–3 as native events, plus a native
  analogue of row 4 (§4.2, §4.3).
- **R2V-F3:** G6 first checks that the record carries **exactly** the
  expected set of applied numeric rule IDs, and only then checks their
  values (§4.1, §5).

**What this record is.** It is the new pre-registration that the following
records require for any later G2-1 PASS:

- the G2-1 results record
  ([`adr-034-g2-1-blind-scoring-results-2026-10-25.md`](adr-034-g2-1-blind-scoring-results-2026-10-25.md),
  #666 `cec27ea9`, verdict **FAIL**);
- ADR-034 §3a (D2) and §7b (D1);
- the D1/D2 freeze amendment (#670 `3b142bcb`).

It is called **R2**, and it is a separate validation. R2 re-scores, reuses
and reinterprets nothing from the first run (R1). Whatever R2's outcome, the
R1 FAIL stays final.

**What it inherits.** R2 inherits R1's pre-registration
([`adr-034-g2-1-validation-preregistration-2026-10-25.md`](adr-034-g2-1-validation-preregistration-2026-10-25.md),
"R1-PR") **as merged, including revision 2, Amendment 1 and Amendment 2**,
except where a section below replaces it. A reference such as "R1-PR §5 G3"
means that text applies to R2 unchanged.

**Normative anchors:**

- [ADR-034](../adr/ADR-034-static-numeric-upper-bound-typed-rule.md): §3a,
  §6a, §7a, §7b and the G2 amendment;
- the [G2-1 charter](../plans/2026-10-24-adr-034-g2-1-behavioral-charter.md),
  §3–§8, including the §5.1 erratum (G2C-R1);
- the G2-1 and D1/D2 entries in
  [`layer1-freeze-e73ff7d.md`](../architecture/layer1-freeze-e73ff7d.md).

## 1. Claim under test

The claim is R1-PR §1, unchanged. In addition, every numeric outcome
and evidence label is read under ADR-034 §3a (function-source resolution by
Python lexical scoping) and §7b (per-rule attribution).

"Relevant enforcement observed" keeps R1-PR §1's limit: it may be claimed
only for events produced by a pinned live host, never for synthetic replay
alone.

## 2. Implementation pin (the freeze)

| Item | Value |
|---|---|
| Implementation commit (`main` after D2, #675 squash) | `dbab816f92143875c1ed7c7d24e4403dedc3b345` |
| `mneme/` tree at that commit | `6cb14c2b48554482e62685395062bb581dfed5e4` |
| Contains | G2-1 (#637 `6e26c534`), D1 (#674 `5eede03f`), D2 (#675 `dbab816f`) |
| Pre-G2 parity baseline | `f8591102b2693379dabec9b5704862e194eca4ce` (same as R1) |
| Runtime | CPython 3.12.10 |

**What the freeze means.** From this record's merge until the R2 results
record merges:

- the `mneme/` tree under test is `6cb14c2b…`;
- scoring uses wheels built from exactly this commit and the baseline;
- their SHA-256 values go in the completion record.

**Later commits to `main`.** These don't move the pin. A fix to the hook,
CLI or matcher that lands after scoring starts voids blind status for R2
(R1-PR §2, the M4 rule).

**Why the baseline is unchanged.** P, X and L parity is measured against
behavior before G2. D1 changes only the evidence validator, and D2 only the
numeric matcher's function source. Neither affects stdout, stderr or exit
status for a case with no applied numeric rule.

## 3. §8.B live host

**Carried forward.** The §8.B record
([`adr-034-g2-1-live-host-2026-10-25.md`](adr-034-g2-1-live-host-2026-10-25.md),
#646 `f551b127`) established five facts about Claude Code 2.1.310: the
envelope identifiers, complete `content`, exit 2 leaving the target absent,
missing-parent behavior and host identity. D1 and D2 don't change any of
these: none is a property of the matcher or of the evidence validator. They
carry forward as they are.

**Re-pin the host before decryption.** The completion record re-records the
installed Claude Code version and the executable's SHA-256.

- **If they match #646:** the carried-forward record stands.
- **If either differs:**
  1. a new live-host session runs R1-PR §3's minimum runs again, with the new
     host pin and a wheel built at the §2 commit;
  2. it records the results in a metadata-only record PR;
  3. that PR merges before decryption.

  The R2 scoring pin is then that new host identity.

## 4. Corpus

**A new corpus.** It is newly authored and independently held out. Classes,
labels, the public/concealed split, byte-contract variety and stated
noncoverage follow R1-PR §4, Amendment 1 and Amendment 2, with the changes
below.

### 4.1 Labels under §3a and §7b

- **Function source (§3a).** Every expected numeric label for the function
  (`call`) source is written by resolving each direct bare-name call site
  under Python's lexical rules:
  - a call site that resolves to the module declaration is a source;
  - a call site that resolves to any other binding is that call site's own
    `UNKNOWN` / `AMBIGUOUS_BINDING`;
  - a binding no call site resolves to has no effect;
  - module-level rebinding, `global`, escape and undecidable resolution make
    the whole source `AMBIGUOUS_BINDING`.
- **Symbol source.** The `symbol` source keeps ADR-034 §3 as written
  ("rebound anywhere in the module"), because §3a leaves it **undecided**.
  - The corpus may include symbol cases, labelled under §3.
  - No case's expected label may depend on how a future symbol ruling would
    resolve a class-body or function-local rebinding of the symbol. Any such
    case goes to the owner's ambiguity brief, not into the corpus.
- **Evidence (§7b).** Each routed case is labelled with four things:
  - **the expected applied-rule set (R2V-F3):** the set of `rule_id` values
    of numeric rules that are `APPLIED` to the target. The author derives
    it independently, from the fixture's memory and ADR-020 applicability,
    never from an observed record. A case with no applied numeric rule
    labels the set as explicitly empty (`{}`);
  - the expected **per-rule** `relevant_enforcement_observed` for every
    `rule_id` in that expected set;
  - the expected **event-level** value: true exactly when at least one
    per-rule value is true;
  - the expected record-wide `evaluation_complete`.

  A1.3's table still gives each rule's value, applied per rule. No rule
  inherits another rule's relevance.

### 4.2 Classes and minimum counts

R1-PR §4's eleven classes and floors are kept. Two classes are added, so
the total floor rises from 104 to **120**.

| Class | Scenario | Expected | Min |
|---|---|---|---|
| **SC** | Routed, strict. Each case has one **function source** whose call sites need §3a scoping to resolve: a same-named method `def` in a class body (inside and outside that class); a parameter, local, comprehension or nested-function binding of the name; enclosing-scope resolution; `global` / `nonlocal`; indirect namespace mutation; a namespace-related string used as plain data | The §3a label, and the matching exit and disposition. Covers recognized-violation, recognized-clean and `AMBIGUOUS_BINDING` outcomes, at least 2 cases of each | 10 |
| **MR** | Routed. Two or more applied numeric rules in one event, under `open`. Must include ADR-034 §7b table rows 1–3, at least once each, plus at least 2 cases of the **native row-4 analogue** (§4.3). The rest is the author's choice | The hook disposition; the applied-rule set; each rule's per-rule relevance; the event-level value; `evaluation_complete` | 6 |
| | **Floor total** (104 + 16) | | **120** |

**The distribution rules stay as in R1-PR §4.** Floors count concealed,
scored cases only. At most 10% of cases may be public smoke cases, each
from a different class. Smoke cases never count toward a floor or a gate
denominator.

### 4.3 §7b row 4: stated noncoverage (owner ruling R2V-F2, 2026-10-26)

**What row 4 describes.** The ADR-034 §7b table's row 4 is: rule A violated,
rule B unevaluated, and a refusal that comes **only** from an unrelated,
non-numeric control.

**Why it can't be a native event here.** At the pinned build, the hook
attributes the refusal to the numeric rule whenever the trusted payload
reports a numeric violation. Every scored class runs under `open`
availability, so there is no competing availability refusal.

The public D1 regressions can only reach row 4 in one of two ways, and
neither counts as an ordinary event:

- a closed-availability run, which R1 lists as noncoverage;
- a record mutated by hand.

**The owner's ruling:**

- **Row 4 is stated noncoverage for R2.** It is not scored as a routed
  event. No tampered or constructed record is presented as a native
  event.
- **Its behavior stays pinned by the public D1 regression tests only.** R2
  makes no blind-validation claim for it.
- **MR must include a native analogue instead,** at least 2 cases. In each:
  - two or more numeric rules are applied;
  - every applied numeric rule is `NO_VIOLATION` or unevaluated;
  - a `FORBID_LITERAL` violation causes a strict refusal.

  **Expected:** exit 2, with every rule's per-rule relevance labelled under
  A1.3 per rule. A rule whose outcome is unevaluated, or whose
  `NO_VIOLATION` does not explain the literal refusal, is `false`.

  The analogue tests the same "no credit for an unrelated refusal, no
  inheritance" property, using real hook output.
- **No availability or gate change.** Availability stays `open` in every
  scored class. R1's noncoverage of AUTHORIZED closed availability stands.
  No new gate or denominator is added.

## 5. Gates

The gates are R1-PR §5 G1–G8 with Amendments 1 and 2, including
symlink capability as a PASS requirement. The changes:

- **G2 False block (R2V-F1)** also covers every SC and MR case labelled as
  expected to proceed. That includes a recognized-clean SC case, an
  `AMBIGUOUS_BINDING` SC case and MR row 3. Any such case observed with
  exit 2 counts as a **G2 false block**, not just a G6 or generic failure.
  The only exception is a case labelled as expected to block because of a
  `FORBID_LITERAL` violation, such as the native row-4 analogue (the LIT
  exception). Zero false blocks are still required.
- **G4 Reasons** also covers SC and MR. Every unevaluated rule or call site
  must have its expected primary reason.
- **G6 Evidence** is restated under §7b. Every routed case must have exactly
  one complete G2 record that joins by digest and path, with the expected
  cause and mode. The scorer then checks the following, in order:
  1. **Rule-ID set (R2V-F3).** The record's numeric `rule_id` values must
     **equal** the expected applied-rule set exactly: no missing ID, no
     extra ID, and no duplicate. For a case labelled `{}`, the record
     carries no numeric rule. If the set doesn't match, the case fails G6
     before any value is checked.
  2. **Per-rule relevance,** for every `rule_id` in the expected set, as
     computed by the pinned build's `relevant_enforcement_per_rule()` with
     the pinned host identity. The result's keys must equal the expected
     set.
  3. **Event-level relevance,** from `relevant_enforcement_observed()`.
  4. **Record-wide `evaluation_complete`,** from
     `recorded_evaluation_complete()`.

  The case fails G6 if any of the four differs from its label. No unrouted
  case may have a G2 record.

**The G1 unsafe-pass rule now covers the new classes.** A strict SC or MR
case expected to block counts as an unsafe pass if it is observed
proceeding, whatever its labels. So does a case expected to have a
non-clean numeric result that is observed clean, and a per-rule relevance
claim of `true` that the label doesn't expect.

## 6. Failure policy

R1-PR §6 applies unchanged: any gate failure fails R2, there is no tuning,
and a harness fix after decryption voids blind status.

**If R2 fails, R3 is required.** A post-R2 fix needs a new
pre-registration and a new corpus (R3). R2's corpus is never reused for a
claim.

## 7. Roles and isolation

Roles are those of R1-PR §7, all filled by **new** sessions. A session that
has seen any G2-1 case content, label or diagnosis evidence may not author
or score R2.

**Barred from authoring and scoring R2:**

| Session or material | Why |
|---|---|
| The R1 corpus author (`local_ed1c5a45`) and its transcript. Never forked or shared | Wrote the R1 corpus |
| The R1 scorer (`local_33c2756e`) and its transcript | Saw R1 corpus content and diagnosis evidence |
| The G2-1 implementation session (`local_bd4b7cd2`) | Implementation |
| The D1 implementation session (`local_3b243386`) | Implementation |
| The D2 implementation session (`local_f3d8f9ec`) | Implementation |
| This orchestrator session | Coordinates only |
| The archived M4 author and scorer sessions | Prior validation roles |

**Off limits to every R2 role, before and after sealing:**

- the R1 sealed folder `C:/dev/mneme-heldout-034-g2-sealed/`, the R1
  scoring folder `C:/dev/g2-1-scoring/`, and any R1 evidence archive;
- the R1 author's working folder `C:/dev/mneme-heldout-034-g2/`.

**What the R2 corpus author may read:**

- everything R1-PR §7 allows, with ADR-034 read **as it now stands**,
  including §3a and §7b;
- this record;
- the R1 results record (#666). It is metadata only, and its D1 and D2
  descriptions are already part of ADR-034.

**What the R2 corpus author may not read:** everything R1-PR §7 bars. In
addition:

- the D1 and D2 PR diffs and bodies (#674, #675);
- `tests/test_numeric_call_scope_resolution.py`;
- any D1 or D2 test file.

The author works only in `C:/dev/mneme-heldout-034-g2r2/`. It writes its
cases from the ADRs and this record, never from memory of any earlier case,
and records an isolation statement.

**The R2 scorer** writes a **new** harness under
`benchmarks/adr034_g2_1_r2/`. It may copy code from the pinned R1 harness
`benchmarks/adr034_g2_1/`, but must not modify it. The new harness
implements §4.1 labels and §5 G6 as restated here, and is built from this
record and R2's public smoke cases only.

## 8. Sequence

1. **This pre-registration (the freeze).** Docs only. Merge.
2. **Corpus authoring.** A new author session writes the corpus and stops
   before sealing. Ambiguities go to the owner as a sanitized brief.
3. **Sealing.** The R1-PR §8 step 3 method:
   - a deterministic tar with `FILES.sha256`;
   - gpg encryption to owner key `88CE4C9F66A5F3CA7F1C0A484839E24F94E4F796`;
   - the owner decrypt-verifies;
   - plaintext deletion;
   - a metadata-only freeze record PR.
4. **Harness PR.** Written by a new scorer session.
5. **Pre-scoring completion record.** R1-PR §8 step 5, plus the §3 host
   re-pin. Any required live-host re-run merges first.
6. **Scoring.** The owner decrypts. Then:
   - two scoring runs;
   - a metadata-only results record PR;
   - custody close: evidence encrypted, plaintext shredded.

G2-1 closes only on a PASS results record from R2, or from a later round.

## 9. Not authorized by this record

- Any code change to `mneme/`, or any change to `benchmarks/adr034_m4/` or
  `benchmarks/adr034_g2_1/`.
- Re-scoring, reuse or reinterpretation of R1, M4 or v1 material.
- Any change to the `symbol` source's resolution.
- Any enforcement, "relevant enforcement observed" or production claim
  before step 6 passes.
- A new G1 (whole-file audit) claim. M4's PASS stays evidence for its own
  pinned build only (freeze amendment #670).
- Activating `FORBID_NUMERIC_ABOVE` in this repository's memory.
