# ADR-034 pre-registered evaluation criteria (draft, revision 3)

**Status:** **DRAFT for owner review, revision 3. Documentation only.**
Revision 3 addresses the
[review of `3b671664`](https://github.com/MnemeHQ/mneme/pull/590#issuecomment-6317899163):

- a hard gate for unsupported (U) and non-decidable (N) cases;
- value-based equality for boundaries;
- independently pinned contracts for set R;
- normative expectations for mixed-source results;
- per-shape headline denominators. These
are the pre-registered criteria, proposed for the held-out validation of an
implementation of
[ADR-034](../adr/ADR-034-static-numeric-upper-bound-typed-rule.md)
(Proposed).

Revision 2 records the owner's E1–E4 rulings and repairs from the
[review of `e4f2fd2a`](https://github.com/MnemeHQ/mneme/pull/590#issuecomment-6317687350).

This document does **not** authorize:

- corpus authoring or a corpus freeze;
- a matcher implementation;
- an implementation charter;
- a Layer 1 amendment.

**Sequence** (design proposal §8, owner ruling N8):

1. ADR-034 is accepted, which freezes the rule contract, including the §5a
   numeric semantics.
2. These criteria are approved and frozen.
3. An independent session authors and freezes the held-out corpus.
4. Only then is the matcher implemented.
5. The implementation is scored against the frozen corpus.

**Honest framing:** P0-A's M2 prototype already exists and is visible. This is
a **held-out validation of a new implementation of an approved contract**,
not proof that the approach was devised blind. Synthetic evidence supports no
generalization claim.

## 1. What is evaluated

- **Implementation:** the `FORBID_NUMERIC_ABOVE` matcher as specified by
  ADR-034 §2–§6, including §5a. It runs through the shipped check path on
  complete-source input, which is the G1 audit question only.
- **Not evaluated:**
  - the ADR-018 introduced-delta gate, beyond confirming that delta input is
    never passed;
  - keyword arguments and exclusive bounds;
  - languages other than Python.

## 2. Corpus design

### 2.1 Authorship and freeze

- The corpus is written by a session or author independent of the matcher
  implementer.
- Every case is labelled at source level against its decision text, with its
  category, expected outcome, expected primary reason (where unevaluated) and
  a written rationale.
- Ambiguities are adjudicated by the owner **before** the freeze.
- The freeze commit records the case bytes, labels, rationales, SHA-256
  digests, the ADR-034 commit and the CPython version.
- The corpus is not shown to the matcher implementer until scoring.

**Label precedence** (ADR-034 §4) applies when labels are authored:

1. A case with a recognized `EXCEEDS` source is labelled **violation**,
   whatever unsupported or missing sources appear elsewhere in it.
2. Only cases with no recognized `EXCEEDS` source may carry an expected
   `MATCHER_UNEVALUATED`.
3. The expected primary reason follows ADR-034's reason priority.

### 2.2 Decision shapes, by declared source mode (E1)

There are **exactly 5** decision shapes, each with its own contract and a
positive `max`:

| Shape | Source mode | Example decision |
|---|---|---|
| S1 | symbol only | request timeout in seconds, **`max: 2.5`** (dyadic) |
| S2 | call only, single call site | retry count, integer `max` |
| S3 | symbol and call | connection-pool size, integer `max` |
| S4 | symbol and call | rate limit per second, **`max: 0.75`** (dyadic) |
| S5 | call only, **multiple call sites** (at least 3 per positive case) | batch size, integer `max` |

Shape maxima must be integers or dyadic decimals, so that a value exactly
equal to `max` is constructible (ADR-034 §5a: equality is defined on values,
not on source text). The freeze verifies `Fraction(float(literal)) ==
Fraction(max)` for every A4 case. Non-dyadic bounds are exercised only in set
R (§2.6a).

### 2.3 Stratum A: adjudicated recognized cases (per-shape quotas)

Counts are exact minimums **per shape** for the modes listed. A dash means
the category does not apply to that mode.

| Category | Label / expected | symbol-only (S1) | call-only (S2) | both (S3, S4, each) | multi-call (S5) |
|---|---|---|---|---|---|
| A1 Literal above `max`, symbol source | violation | 2 | – | 1 | – |
| A2 Literal above `max`, call source | violation | – | 2 | 1 | 2 (exactly one call site above) |
| A3 Folded literal arithmetic above `max` | violation | 1 | 1 | 1 | 1 |
| A4 Boundary: a runtime value **provably equal** to `max` (`Fraction(x) == Fraction(max)`, verified at the freeze) | benign | 1 | 1 | 1 | 1 |
| A5 Boundary: `max` plus the pre-registered increment (§2.6), whose runtime value is **verified** to exceed `max` exactly | violation | 1 | 1 | 1 | 1 |
| A6 Within `max`, all declared sources found | benign | 2 | 2 | 2 | 2 (all call sites within) |
| A7 Mixed: one recognized source above `max`, another `UNKNOWN` | violation, with matcher status `PARTIAL`, the expected unknown source and primary reason, and `evaluation_complete=false` (ADR-034 §4) | – | – | 1 | 1 |
| A8 Benign look-alikes (other symbol or function, comment, string, docstring) | benign | 2 | 2 | 2 | 2 |
| A9 Out-of-scope path (ADR-020 `EXCLUDED`) | applicability only | 1 | 1 | 1 | 1 |

**Per-shape stratum A totals** (A1–A8, scored): S1 = 9, S2 = 9, S3 = 10,
S4 = 10, S5 = 10. **Corpus total:** 48 scored, plus 5 applicability-only.

**Corpus-level floors by source mode,** derived from the table and checkable
at the freeze:

- symbol-source violations (A1): at least 4;
- call-source violations (A2): at least 6, including at least 2 multi-call;
- mixed (A7): at least 3.

### 2.4 Stratum U: unsupported and undecidable probes (per shape)

Every case here has **no** recognized `EXCEEDS` source, by construction. A
probe that also contains an exceeding source is reclassified as A7.

| Category | Expected status | Expected primary reason | Per shape |
|---|---|---|---|
| U1 Keyword argument, derived constant, alias, or attribute call carrying the value | `MATCHER_UNEVALUATED` | `UNRECOGNIZED_FORM`, or `SOURCE_NOT_FOUND` where the declared positional source is then absent | 2 |
| U2 Rebinding, shadowing, function escaping as a value, `*args`/`**kwargs` | `MATCHER_UNEVALUATED` | `AMBIGUOUS_BINDING` (`UNRECOGNIZED_FORM` for star-args) | 1 |
| U3 Declared source absent (symbol missing, or no call site) | `MATCHER_UNEVALUATED` | `SOURCE_NOT_FOUND` | 1 |
| U4 Disabled or out-of-range value (`None`, `0`, negative, `inf`, bool, int above 10^30, overflow) | `MATCHER_UNEVALUATED` | `UNRECOGNIZED_FORM` | 1 |

That is 5 per shape, 25 across the corpus.

### 2.5 Stratum N: non-decidable inputs (corpus-wide)

| Category | Expected | Minimum |
|---|---|---|
| N1 Parse failures (syntax beyond the pinned grammar, broken files) | `MATCHER_UNEVALUATED` / `PARSE_FAILURE` | 3 |
| N2 Non-source inputs (prompt text, code fragments, introduced-delta text, stdin without a target path), **including inputs that parse and contain only compliant values** | `MATCHER_UNEVALUATED` / `INCOMPLETE_SOURCE_INPUT` | 5 |

### 2.6 Boundary increment (resolves "smallest representable step")

Under ADR-034 §5a, the source value is the pinned-runtime value, compared
exactly. The A5 increment is therefore **pre-registered per shape**, as a
literal source expression frozen with the corpus:

- **Integer `max`** (S2, S3, S5): the source literal `max + 1`, for example
  `4` against `max: 3`.
- **Dyadic decimal `max` with k fraction digits** (S1, S4): the source
  literal `max` plus 10^-(k+1). For example, `2.51` against `max: 2.5`, and
  `0.751` against `max: 0.75`. The freeze **must verify**
  `Fraction(float(literal)) > Fraction(max)` and record the literal, its
  runtime value and the check. If the check fails, a larger pre-registered
  increment is chosen and recorded before the freeze.

### 2.6a Set R: numeric-semantics cases with independent contracts

Set R is **separate from the five shapes and excluded from their quotas**.
Each R case has its **own** single-source contract (symbol only, `language:
python`, its own `max`). The contract is pinned in the freeze next to the
case, and each case is source-adjudicated and scored against its expected
outcome. **Minimum: 16 cases**, exactly these:

| R | Source expression | Contract `max` | Expected |
|---|---|---|---|
| R1 | `0.1 + 0.2` | `0.3` | violation |
| R2 | `0.3` | `0.3` | within |
| R3 | `5.000000000000001` | `5` | violation |
| R4 | `5.0000000000000001` | `5` | within |
| R5 | `10 / 2` | `5` | within |
| R6 | `4.5 + 0.5` | `5` | within |
| R7 | `1 / 3 * 15` | `5` | within |
| R8 | `11 // 2` | `5` | within |
| R9 | `-1 % 6` | `5` | within |
| R10 | `2 ** 3` | `5` | violation |
| R11 | `2 ** 65` | `5` | `MATCHER_UNEVALUATED` / `UNRECOGNIZED_FORM` |
| R12 | `10 ** 31` | `5` | `MATCHER_UNEVALUATED` / `UNRECOGNIZED_FORM` |
| R13 | `1e308 * 10` | `5` | `MATCHER_UNEVALUATED` / `UNRECOGNIZED_FORM` |
| R14 | `1 / 0` | `5` | `MATCHER_UNEVALUATED` / `UNRECOGNIZED_FORM` |
| R15 | `2 ** 2` (`**` exactly at the bound) | `4` | within |
| R16 | `0.1` (same spelling as a non-dyadic bound) | `0.1` | violation (pending O6) |

R1–R14 are the 14 source expressions in ADR-034 §5a's boundary table. These
expectations hold under O6 option (a). If the owner chooses (b), R2 and R16
(and any other affected row) are re-adjudicated **before** the freeze.

### 2.7 Stratum W: representative supported workload (E3)

The independent author writes **10 files per shape (50 in total)** following a
**composition spec frozen before the cases are written**:

- **Style:** ordinary application modules in a natural style, using only
  forms the contract supports for the value sources. Other unrelated code is
  allowed and encouraged.
- **No adversarial constructs** aimed at the value sources.
- **Mix:** about 70% within `max` and about 30% above, per shape.
- **The spec is written without reference to any matcher output.**

W cases are labelled like stratum A.

### 2.8 Stratum O (optional, E4)

Licensed open-source excerpts, which must be reviewed for licence and must
identify no outside party. They are reported separately and never count
toward any gate or toward generalization.

## 3. Scoring partitions and denominators

| Observation | Treatment |
|---|---|
| **Operational failure** (check not run, crash, timeout, untrusted payload) | Invalidates the run. Scoring needs **zero** operational failures; it is never counted as any outcome |
| **ADR-020 `EXCLUDED`** (A9) | Scored for applicability only. Excluded from every matcher denominator |
| **Strata A, W and set R** (`APPLIED`, trusted, complete source) | Matcher outcome scored against the label. For A7, matcher status and unknown-source reason are also scored |
| **Stratum U** | Correct only if `MATCHER_UNEVALUATED` with the expected primary reason. Excluded from the coverage denominators |
| **Stratum N** | Correct only if `MATCHER_UNEVALUATED` with the expected primary reason. Excluded from the coverage denominators. Any no-violation counts as an unsafe pass |

A compliant (no-violation) result is credited **only** for `APPLIED`, trusted,
complete-source cases in strata A or W, or in set R.

## 4. Metrics

These are reported per shape, per stratum and in aggregate, for the audit
question only.

| Metric | Definition |
|---|---|
| Misses | Recognized violations (A, W) reported as no violation or as unevaluated |
| False blocks | Benign cases (A, W) reported as a violation |
| Unsafe passes | Any no-violation on U or N, or on a case whose label requires unevaluated |
| Unexpected violations on U/N | Any violation reported on a U or N case. U and N contain no recognized `EXCEEDS` source by construction |
| Wrong primary reason | Unevaluated cases (U, N, and any A/W case expected unevaluated) whose primary reason differs from the pre-registered one |
| Coverage A | Decided outcomes ÷ stratum A cases |
| Coverage W | Decided outcomes ÷ stratum W cases |
| Aggregate unevaluated rates | Reported for violation and benign labels across A + U + W, and separately for U and N |
| Determinism | Two clean runs produce byte-identical summaries |
| Binding completeness | Share of verdicts carrying subject digest, `rule_id`, decision version, applicability, matcher status and primary reason, and outcome (ADR-029) |

## 5. Pass criteria (pre-registered)

The implementation **passes** only if **every** gate holds:

1. **Zero misses** in strata A and W.
2. **Zero false blocks** in strata A and W.
3. **Zero unsafe passes.**
3a. **Every U and N case returns `MATCHER_UNEVALUATED` with its expected
    primary reason.** Both a violation and a no-violation are failures. The
    separately reported counts of unsafe passes and of unexpected violations
    on U/N remain visible.
4. **Every A7 mixed case** is reported as a violation, with matcher status
   `PARTIAL`, the expected unknown source and primary reason, and
   `evaluation_complete=false`.
5. **Zero wrong primary reasons** on adjudicated cases (E2).
6. **Coverage A = 100%.**
7. **Coverage W ≥ 95%** (E3). The owner may tighten this before the freeze.
   It must not be relaxed after the freeze.
8. **Every set R case** (R1–R16) matches its pre-registered expected outcome
   and, where unevaluated, its primary reason.
9. **Determinism:** two byte-identical runs.
10. **Binding completeness = 100%.**
11. **Golden vectors:** every ADR-034 §5 vector reproduces, and existing
    `FORBID_LITERAL` ids are byte-stable.
12. **Old-reader refusal:** a reader without `numeric_upper_bound_rule`
    refuses v2 memory containing the type. It is never dropped silently.

**Always reported, never a gate:** U and N outcome counts, the aggregate
unevaluated rates, and stratum O. The headline states, per shape:

> "W decided X of 10; A decided Y of N_A; U unevaluated Z of 5 (expected 5)."

N_A is that shape's actual stratum A quota: 9 for S1 and S2, 10 for S3–S5.
Set R is reported as "R matched M of 16".

**On failure:**

- Any failed gate means the type is **not** proposed for enforcement, and the
  result is reported as is.
- Fixes after scoring require a new held-out set for any claim; they cannot
  re-score on the same corpus.
- Cases added after the freeze go into a marked post-hoc set that never
  counts toward any gate.

## 6. Reporting

`RESULTS.md` reports every metric per shape and stratum, and lists every miss,
false block, unsafe pass and wrong reason with its case. It records the run
anchors: ADR-034 commit, corpus freeze commit, implementation commit, CPython
version, OS.

It states plainly:

- the audit-only, Python-only and first-slice scope;
- that no pre-write protection is claimed;
- that no generalization beyond the synthetic held-out corpus is claimed.

## 7. Owner rulings (provisional, 2026-10-21)

| ID | Ruling | Where reflected |
|---|---|---|
| E1 | Five shapes; quotas partitioned by declared source mode, with floors for symbol-only, call-only, both and multi-call | §2.2–2.4 |
| E2 | 0% wrong primary reasons on adjudicated cases; reason priority pre-registered (ADR-034 §4) | §5 gate 5 |
| E3 | 100% decided for supported forms (stratum A), plus a separate, pre-registered coverage floor on representative workloads (stratum W, ≥ 95%); unsupported probes reported but not gating coverage | §2.7, §5 gates 6–7 |
| E4 | Synthetic corpus is primary; licensed open-source excerpts optional, as a separately labelled stratum; no generalization claim | §2.8 |
