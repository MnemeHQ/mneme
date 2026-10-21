# ADR-034 pre-registered evaluation criteria (draft)

**Status:** **DRAFT for owner review. Documentation only.** These are the
pre-registered criteria, proposed for the held-out validation of an
implementation of
[ADR-034](../adr/ADR-034-static-numeric-upper-bound-typed-rule.md)
(Proposed).

This document does **not** authorize:

- corpus authoring or a corpus freeze;
- a matcher implementation;
- an implementation charter;
- a Layer 1 amendment.

**Sequence** (from the design proposal §8, owner ruling N8):

1. ADR-034 is accepted, which freezes the rule contract.
2. These criteria are approved and frozen.
3. An independent session authors and freezes the held-out corpus.
4. Only then is the matcher implemented.
5. The implementation is scored against the frozen corpus.

**Honest framing:** P0-A's M2 prototype already exists and is visible. This is
a **held-out validation of a new implementation of an approved contract**,
not proof that the approach was devised blind.

## 1. What is evaluated

- **Implementation:** the `FORBID_NUMERIC_ABOVE` matcher as specified by
  ADR-034 §2–§6. It runs through the shipped check path on complete-source
  input, which is the G1 audit question only.
- **Not evaluated:**
  - the ADR-018 introduced-delta gate, beyond confirming that delta input is
    never passed;
  - keyword arguments and exclusive bounds;
  - C1-type disabled values, beyond confirming they are `UNEVALUATED`;
  - languages other than Python.

## 2. Corpus requirements (for the later freeze)

**Authorship:**

- The corpus is written by a session or author independent of the matcher
  implementer.
- It is frozen (bytes, labels, rationales, digests, ADR-034 commit, Python
  grammar version) in its own commit **before** any matcher code exists.
- It is not shown to the matcher implementer until scoring.

**Decision shapes:** at least **5** distinct ones, each with its own
`FORBID_NUMERIC_ABOVE` contract, for example:

- request timeout (seconds);
- retry count;
- connection-pool size;
- rate limit (per second);
- batch size.

At least one shape uses a symbol-only contract, one a call-only contract, and
one both.

**Case categories.** Minimum counts are per shape unless stated otherwise.

| Category | Label | Minimum |
|---|---|---|
| Recognized violation: literal above `max` (symbol source) | violation | 2 |
| Recognized violation: literal above `max` (call source) | violation | 2 |
| Recognized violation: folded literal arithmetic above `max` | violation | 1 |
| Boundary: exactly `max` (inclusive) | benign | 1 |
| Boundary: smallest representable step above `max` | violation | 1 |
| Recognized compliant: within `max`, all sources found | benign | 2 |
| Mixed: one source `EXCEEDS`, another `UNKNOWN` | violation (must be reported as a violation) | 1 |
| Unsupported forms (keyword argument, derived constant, alias, attribute call, `*args`, shadowing/rebinding) | label per decision intent; expected status `MATCHER_UNEVALUATED` | 3 |
| Missing declared source (symbol absent, or no call site) | expected status `MATCHER_UNEVALUATED` | 1 |
| Disabled values (`None`, `0`, negative, `inf`, bool) | expected status `MATCHER_UNEVALUATED` | 1 |
| Benign look-alikes (other symbol, other function, comment, string, docstring) | benign | 2 |
| Out-of-scope path (ADR-020 `EXCLUDED`) | not scored for matcher; applicability checked | 1 |

**Corpus-wide categories:**

| Category | Expected | Minimum |
|---|---|---|
| Parse failures (syntax beyond the pinned grammar, broken files) | `MATCHER_UNEVALUATED` / `PARSE_FAILURE` | 3 |
| Non-source inputs (prompt text, code fragments, introduced-delta text, stdin without a target path), including ones that parse and contain only compliant values | `MATCHER_UNEVALUATED` / `INCOMPLETE_SOURCE_INPUT`, **never no-violation** | 5 |

**Labels:**

- Each case is labelled at source level against its decision text: a
  violation or benign label, plus an expected matcher status where relevant.
- Each case records its category and a written rationale.
- Ambiguous cases are recorded as owner adjudications before the freeze, never
  resolved silently.

## 3. Metrics

These are reported separately per shape and in aggregate, for the audit
question only.

| Metric | Definition |
|---|---|
| Catch rate (recognized) | Violations caught ÷ violations whose every relevant source is in a recognized form |
| Misses (recognized) | Recognized violations reported as no violation or as unevaluated |
| False blocks | Benign cases reported as a violation |
| Unevaluated rate (violation) | Violation cases reported `MATCHER_UNEVALUATED` ÷ all violation cases |
| Unevaluated rate (benign) | Benign cases reported `MATCHER_UNEVALUATED` ÷ all benign cases |
| Coverage | Cases with a decided outcome (violation or no violation) ÷ all in-scope cases |
| Wrong unevaluated reason | `MATCHER_UNEVALUATED` with a reason that differs from the expected one |
| Unsafe pass | **Any** no-violation result on an unsupported form, a missing source, a disabled value, a parse failure or non-source input |
| Determinism | Two clean runs produce byte-identical summaries |
| Binding completeness | Share of verdicts carrying subject digest, `rule_id`, decision version, applicability, matcher status and reason, and outcome (ADR-029) |

## 4. Pass criteria (pre-registered)

The implementation **passes** only if **all** of the following hold.

**Hard gates:**

1. **Zero misses** on recognized violations.
2. **Zero false blocks.**
3. **Zero unsafe passes.**
4. **Mixed cases** are all reported as violations.
5. **Determinism:** two byte-identical runs.
6. **Binding completeness = 100%.**
7. **Golden vectors:** every ADR-034 §5 vector reproduces, and existing
   `FORBID_LITERAL` ids are byte-stable.

**Thresholds** (proposed; the owner may tighten them before the freeze):

8. **Coverage of recognized-form cases:** 100%. Every case in a recognized
   category gets a decided outcome.
9. **Corpus-wide coverage** is reported, with no pass threshold. A high
   unevaluated rate is a finding about scope, not a failure, **provided**
   gates 1–3 hold. The headline must state it in this form: "decided X of
   N; unevaluated Y of N".
10. **Wrong unevaluated reason:** at most **5%** of unevaluated cases. Any
    `INCOMPLETE_SOURCE_INPUT` misreported as anything other than unevaluated
    counts under gate 3.

**On failure:**

- Any failed hard gate means the type is **not** proposed for enforcement, and
  the result is reported as is.
- Fixes after scoring require a new held-out set for any claim; they cannot
  re-score on the same corpus.
- Corpus changes after the freeze are not permitted. A case added later goes
  into a marked post-hoc set that never counts toward these criteria.

## 5. Reporting

`RESULTS.md` reports:

- each metric, per shape and in aggregate;
- every miss, false block, unsafe pass and wrong reason, with the case;
- the full list of unevaluated cases by reason;
- the run anchors (ADR-034 commit, corpus freeze commit, implementation
  commit, Python version, OS).

It states plainly:

- the audit-only, Python-only and first-slice scope;
- that no pre-write protection is claimed;
- that no generalization beyond the held-out corpus is claimed.

## 6. Open items for the owner

| ID | Item | Proposed |
|---|---|---|
| E1 | Number of decision shapes | At least 5 |
| E2 | Wrong-reason tolerance | 5% |
| E3 | Whether a corpus-wide coverage floor is a pass gate | No: reported only (gate 9) |
| E4 | Whether real-world (open-source) code samples are included | Optional, only with clear licensing and no external-party identification; synthetic cases are the default |
