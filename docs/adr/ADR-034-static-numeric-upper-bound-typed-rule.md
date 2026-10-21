---
id: ADR-034
title: "Static Numeric Upper-Bound Typed Rule for Python (Proposed)"
status: proposed
priority: normal
date: 2026-10-21
scope: enforcement.typed_rules
---

# ADR-034: Static Numeric Upper-Bound Typed Rule for Python

**Status:** **Proposed, revision 4.**

Revision 4, per the
[review of `394371c1`](https://github.com/MnemeHQ/mneme/pull/590#issuecomment-6318200921):

- O6 is resolved as (a), the exact authored decimal bound;
- `int`-only exponents, stated as an intentional subset of M2;
- the M2 parity statement is narrowed to the comparison step, with
  recognition-domain differences listed separately.

Revision 3, per the
[review of `3b671664`](https://github.com/MnemeHQ/mneme/pull/590#issuecomment-6317899163):

- a normative mixed-source record (`PARTIAL`, §4);
- value-based equality and new boundary rows (§5a);
- open question O6. This is a draft for owner review. It is
**not accepted**. A proposed ADR is imported as inactive and has no
enforcement effect.

Revision 2 records the owner's O1–O5 rulings and resolves the blocking
repairs from the
[review of `e4f2fd2a`](https://github.com/MnemeHQ/mneme/pull/590#issuecomment-6317687350):

- numeric evaluation semantics (new §5a);
- the authoring grammar for `max`;
- the mixed-source scoring precedence.

That review also recorded that drafting this ADR had not been separately
authorized after #589. Revising this draft in place is permitted; nothing
beyond that is.

Acceptance of this ADR would confer **no** implementation authority, held-out
corpus freeze, implementation charter or Layer 1 amendment. Each of those is a
separate decision. The pre-registered evaluation criteria are in
[`docs/plans/2026-10-21-adr-034-pre-registered-evaluation-criteria.md`](../plans/2026-10-21-adr-034-pre-registered-evaluation-criteria.md).

**Date:** 2026-10-21
**Deciders:** Theo Valmis
**Builds on:**

- the merged design proposal
  [`2026-10-21-m2-numeric-bound-rule-design-proposal.md`](../plans/2026-10-21-m2-numeric-bound-rule-design-proposal.md)
  (#589, `7dc02e81`), including the owner's N1–N8 rulings in its section 9;
- the P0-A charter and offline results (#578, #582, #586).

**Source anchor:** `main` @ `7dc02e81`. Line numbers refer to that commit.

## Context

`FORBID_LITERAL` (ADR-019) is the only typed rule. It cannot express "this
value must not exceed N": a 60-second deadline violates a 5-second maximum
without containing any forbidden literal.

The P0-A experiment measured a static detector for this, M2, on one synthetic
Python router:

- It caught 4 of 5 bound violations, with no false block and no miss.
- A derived bound (J) stayed `UNEVALUATED`.
- The case set was visible, keyword arguments and exclusive bounds were not
  exercised, and there was no gate coverage evidence.

That is bounded offline capability, not enforcement.

The design proposal mapped every pipeline stage. Each one is `FORBID_LITERAL`-only
today:

- **Parsing:** `adr_constraints.py:48-53, 190-213`.
- **Compilation:** `adr_compiler.py:47-56` and `decision_index.py:265-311`.
- **Schema:** `schemas.py:51-53`.
- **Persistence:** the loader accepts only a `{"value"}` payload
  (`decision_index_persistence.py:1981-1984`).
- **Identity:** `rule_identity.py:50-58`.
- **Evaluation:** `enforcer.py:253-257` and `conflict_detector.py:142`.
- **Hook trust validation:** `hook.py:365-378`.

It also confirmed two hazards:

- A type admitted without a matcher would be traced `APPLIED` and silently
  PASS.
- The hook's trust validator would treat a matcher-incomplete payload as
  *inconsistent* (untrusted) rather than as unevaluated.

## Decision (proposed)

### 1. A new, separately specified rule type

The proposed type name is `FORBID_NUMERIC_ABOVE`, following the `FORBID_`
family. **Open question O1** lists the alternatives.

It is a new rule type under ADR-019 §9. `FORBID_LITERAL`'s parsing, matching,
identity and payloads are unchanged.

### 2. Authored contract (first slice only)

A structured directive under `## Constraints`:

```text
- FORBID_NUMERIC_ABOVE:
    language: python
    symbol: ROUTER_DEADLINE_S
    call:
      function: classify
      position: 1
    max: 5
    inclusive: true
    unit: seconds
    include_paths:
      - "src/**"
```

| Field | Required | Contract |
|---|---|---|
| `language` | yes | Exactly `python`. Any other value is an authoring error |
| `symbol` | at least one of `symbol` and `call` | A Python identifier. Its module-level bare-name assignment is a value source |
| `call.function` | with `call` | A Python identifier. Only **direct bare-name** calls `function(...)` are sources |
| `call.position` | with `call` | A non-negative integer, **0-based** positional index. Keyword matching is **not** part of this slice |
| `max` | yes | A **plain, unquoted** YAML scalar whose **raw text** matches the authoring grammar of §5. It must be strictly greater than zero (O5) |
| `inclusive` | yes | Must be literally `true`. Exclusive bounds are **not** part of this slice; `false` is an authoring error, not a silent default |
| `unit` | yes | A non-empty label for documentation and diagnostics. It is **never** converted |
| `include_paths` | yes | ADR-020 selectors. There is no global form |
| `exclude_paths` | no | ADR-020 selectors |

Unknown keys, duplicate keys and missing required keys are authoring errors.
The YAML loader already rejects duplicate keys (`adr_constraints.py:119-145`).
`FORBID_LITERAL`'s scalar form has no equivalent here: only the structured form
is valid.

### 3. Recognition scope and positive source discovery

**Recognized value forms are an intentional subset of M2's syntax** (P0-A
`m2_static_bound.py` 1.0.0):

- numeric literals;
- unary `+`/`-`;
- binary `+ - * / // % **` over recognized operands;
- **`**` only with an `int` exponent** (by type) of magnitude at most 64.

**Narrower than M2.** M2 accepted any finite numeric exponent of magnitude at
most 64, including fractional or float exponents. This first slice treats
every **non-`int` exponent** as `UNKNOWN` with `UNRECOGNIZED_FORM`. That
covers fractional exponents (`4 ** 0.5`), integer-valued floats (`2 ** 2.0`)
and anything that could produce a complex result (`(-8) ** 0.5`).

**Not folded:** `bool` operands; division by zero; overflow; the range
guards of §5a.

Folding never executes source. How a recognized form is **evaluated and
compared** is defined in §5a. That is **not** equivalent to M2, either in
recognition domain or in comparison; §5a lists both kinds of difference.

**Value sources:**

- the single module-level assignment to `symbol`;
- the argument at `position` of each direct `function(...)` call in the
  module.

If that argument is the bare `symbol` name, it resolves to the symbol's
recognized value.

Each source is classified as `WITHIN`, `EXCEEDS` or `UNKNOWN`. `NO_VIOLATION`
requires **positive discovery of every declared source**. Each of the
following makes the source `UNKNOWN`:

- the symbol is absent, assigned more than once, or rebound anywhere in the
  module;
- no direct call site exists;
- the function is shadowed, rebound or escapes as a value;
- a call uses `*args`/`**kwargs`, or has fewer arguments than `position + 1`;
- the value is outside the recognized forms;
- the value is non-numeric or disabled (`None`, bool, string, zero, negative,
  infinite or NaN). That is a C1-type question, which this rule does not
  claim.

There are no optional sources (O2 ruling): a declared source that is absent
is always `UNKNOWN`.

### 4. Outcome semantics

There are three dimensions, and they are never collapsed into one another:

1. **Path applicability (ADR-020):** `APPLIED`, `EXCLUDED` or `UNKNOWN`.
   Unchanged and type-independent.
2. **Per-rule matcher status (new):**
   - `RECOGNIZED`: every declared source was positively recognized;
   - `PARTIAL`: at least one source was recognized as `EXCEEDS` **and** at
     least one source is `UNKNOWN`;
   - `MATCHER_UNEVALUATED`: there is no recognized `EXCEEDS` source and at
     least one source is `UNKNOWN`.

   `PARTIAL` and `MATCHER_UNEVALUATED` carry the `UNKNOWN` sources, each with
   a reason from `PARSE_FAILURE`, `UNRECOGNIZED_FORM`, `SOURCE_NOT_FOUND`,
   `AMBIGUOUS_BINDING` or `INCOMPLETE_SOURCE_INPUT`.

   Matcher uncertainty is never expressed as path `UNKNOWN`.
3. **Operational checker status:** unchanged trust and ADR-033 availability
   handling. It is never relabelled as a rule outcome.

**Per-rule record (normative).** For an `APPLIED` rule on trusted
complete-source input, the outcome and the matcher status are recorded as
separate fields. The unknown sources are never discarded because a violation
is decisive.

| Sources | Outcome | Matcher status | Unknown sources recorded | Contributes `evaluation_complete=false` |
|---|---|---|---|---|
| Any `EXCEEDS`, no `UNKNOWN` | **violation** | `RECOGNIZED` | none | no |
| Any `EXCEEDS`, any `UNKNOWN` | **violation** | `PARTIAL` | each, with reasons; primary reason by the priority below | **yes** |
| No `EXCEEDS`, any `UNKNOWN` | unevaluated | `MATCHER_UNEVALUATED` | each, with reasons; primary reason by priority | **yes** |
| All `WITHIN` | no violation | `RECOGNIZED` | none | no |

The violation trigger reports the source line, the recognized runtime value,
`max` and `unit`. A `PARTIAL` result is therefore a **FAIL verdict with
`evaluation_complete=false`**.

- **CLI:** reports both the violation and the unknown sources. The exit code
  follows the M-a target (§8); today's incomplete exit 2 already coincides
  with strict FAIL.
- **Trust validators:** must accept FAIL together with
  `evaluation_complete=false` when the incompleteness is attributable to
  `PARTIAL`/`MATCHER_UNEVALUATED` records or applicability `UNKNOWN`. They
  must reject it otherwise.

A violation is a deterministic FAIL, as in ADR-019 §5. The precedence in
rule 1 applies to label authoring and scoring as well: a case with a
recognized `EXCEEDS` source is a **violation**, whatever unsupported forms
appear elsewhere in it.

**Reason priority.** When several `MATCHER_UNEVALUATED` reasons apply, the
**primary** reason, the one reported first and scored, is the first that
applies in this order:

1. `INCOMPLETE_SOURCE_INPUT`: decided from the input contract, before parsing.
2. `PARSE_FAILURE`.
3. `AMBIGUOUS_BINDING`: rebinding, shadowing, or the function escaping as a
   value.
4. `SOURCE_NOT_FOUND`.
5. `UNRECOGNIZED_FORM`: this also covers out-of-range values and disabled
   values under §5a.

All applicable reasons may be listed, but only the primary one is scored.

**`evaluation_complete`** remains a *derived aggregate*: false if any rule's
applicability is `UNKNOWN` or any rule's matcher status is `PARTIAL` or
`MATCHER_UNEVALUATED`. The JSON payload must carry each rule's matcher status
and reason explicitly. Every consumer's consistency validator must accept a
matcher-incomplete payload as **trusted** (unevaluated, or a violation with
`PARTIAL`), by checking that the aggregate equals "applicability `UNKNOWN`
or matcher `PARTIAL`/`MATCHER_UNEVALUATED`".
That covers the hook (`hook.py:365-378`), the Agent SDK and LangChain. The
validator change belongs to the implementation charter.

### 5. Persistence and identity (P1, conditional)

`Rule.value` holds a **canonical serialized string**:
`canonical_json` (`rule_identity.py:22-29`: sorted keys, compact separators,
ASCII) of the object below.

| Key | Contents |
|---|---|
| `v` | The contract version, `1` |
| `language` | `"python"` |
| `symbol` | Present only if authored |
| `call` | Present only if authored: `{"function", "position"}` |
| `max` | The canonical decimal **string** |
| `inclusive` | `true` |
| `unit` | As authored |

**Authoring grammar for `max`.** The grammar is checked on the YAML node's
**raw scalar text before type construction**. That is necessary because the
YAML loader turns `05`, `0x5` and `1_000` into integers, `.5` and `5.` into
floats, and `5e0` into a string, so the parsed value cannot distinguish them.

| Rule | Detail |
|---|---|
| Must be a plain scalar | Quoted scalars are rejected, so `"5"` and `'5'` are not accepted |
| Raw text grammar | `^(0|[1-9][0-9]{0,17})(\.[0-9]{1,9})?$`: up to 18 integer digits and up to 9 fraction digits |
| Rejected spellings | Sign, leading zeros, a bare `.5` or `5.`, exponent notation (`5e0`, `5.0e0`), underscores, hex or octal, `.inf`/`.nan`, booleans, null |
| Value | Must be strictly greater than zero (O5) |

**Canonical stored form.** The authored text is normalized textually, never
through a float:

- trailing fractional zeros are stripped;
- a fraction that becomes empty is dropped.

So `5`, `5.0` and `5.000` all store as `"5"`, and `2.50` stores as `"2.5"`.
The stored string must match `^(0|[1-9][0-9]*)(\.[0-9]*[1-9])?$` and be
greater than zero. The loader re-validates it and never rewrites it.

### 5a. Numeric evaluation semantics

**Decision: the value the pinned Python runtime would compute, compared
exactly with the authored decimal bound.**

1. **Evaluation.** A recognized expression is evaluated with **pinned CPython
   numeric semantics**, by applying the corresponding `operator` functions to
   `int` and `float` operands. Folding never executes the module.
   - `int` has arbitrary precision; `float` is IEEE-754 binary64 with
     round-half-even.
   - Mixed `int`/`float` operations produce a float.
   - `/` is true division; `//` and `%` use Python floor semantics.
   - `**` only with an `int` exponent of magnitude at most 64 (§3). Any
     other exponent is `UNKNOWN`.
   - These are exactly the values the program would produce at runtime.
2. **Operand and result bounds.** Any of the following makes the source
   `UNKNOWN`, with reason `UNRECOGNIZED_FORM` (out of range), and is never
   judged:
   - any intermediate or final `int` whose magnitude exceeds 10^30;
   - any `float` operation that raises `OverflowError` or
     `ZeroDivisionError`;
   - a result that is infinite or NaN.
3. **Comparison.** The resulting runtime value `x` is compared **exactly**
   with the stored decimal `max`, as `Fraction(x)` against `Fraction(max)`.
   `x` violates when `Fraction(x) > Fraction(max)`. Any `x <= 0` (disabled)
   makes the source `UNKNOWN`.

**Rationale.** The rule governs the value the program actually uses. Exact
rational evaluation of the *source text* would judge `0.1 + 0.2` as equal to
`0.3`, but the program computes `0.30000000000000004`, which exceeds a bound
of `0.3`. Comparing that runtime value exactly against the *authored* decimal
avoids a second rounding of the bound.

**Where this differs from M2.** This is **not** a detector-equivalence
claim. The differences fall into two kinds.

1. **Comparison step only.** When both M2 and this rule successfully
   evaluate the *same finite source value*, they disagree only when `max` is
   not exactly representable in binary64, because M2 compared against the
   bound as a Python float.
   - A literal `0.1` against `max: 0.1` is within under M2 and a
     **violation** here.
   - A literal `0.3` against `max: 0.3` is within under both.
   - `0.1 + 0.2` against `max: 0.3` is a violation under both.
2. **Recognition domain.** This rule recognizes fewer forms, so some sources
   M2 judged are `UNKNOWN` here:
   - `10 ** 31` exceeds `max: 5` under M2, but is `UNKNOWN` here because of
     the int range guard above 10^30;
   - `4 ** 0.5` (`2.0`) is within `max: 5` under M2, but is `UNKNOWN` here
     because the exponent is not an `int`;
   - `2 ** 2.0` is `UNKNOWN` here for the same reason;
   - an overflowing or non-finite result was a disabled value (C1) under M2,
     and is `UNKNOWN` here.

   Other restrictions in §2–§6 can also yield `UNKNOWN` where M2 decided:
   positive source discovery, complete-source input and the O5 positivity
   rules.

**Pre-registered boundary behavior** (CPython 3.12; part of the contract and
of the evaluation corpus):

| Source expression | Runtime value | `max` | Result |
|---|---|---|---|
| `0.1 + 0.2` | `0.30000000000000004` | `0.3` | violation |
| `0.3` | `0.3` (binary64, below 0.3 exactly) | `0.3` | within |
| `5.000000000000001` | `5.000000000000001` | `5` | violation |
| `5.0000000000000001` | `5.0` (rounded at parse) | `5` | within |
| `10 / 2`, `4.5 + 0.5`, `1 / 3 * 15` | `5.0` | `5` | within |
| `11 // 2`, `-1 % 6` | `5` | `5` | within |
| `2 ** 3` | `8` | `5` | violation |
| `2 ** 2` | `4` | `4` | within (exactly equal) |
| `0.1` | `0.1000000000000000055511…` | `0.1` | **violation**: the matching text is not an equal value (O6 (a)) |
| `2.5`, `0.75` | exactly `2.5`, `0.75` (dyadic) | the same | within (exactly equal) |
| `2 ** 65` | not folded (exponent above 64) | `5` | `UNKNOWN` |
| `4 ** 0.5` | not folded (non-`int` exponent) | `5` | `UNKNOWN` |
| `2 ** 2.0` | not folded (non-`int` exponent) | `5` | `UNKNOWN` |
| `10 ** 31` | an `int` above 10^30 | `5` | `UNKNOWN` |
| `1e308 * 10` | infinite | `5` | `UNKNOWN` |
| `1 / 0` | `ZeroDivisionError` | `5` | `UNKNOWN` |

The pinned runtime is recorded with every evaluation. A change of interpreter
needs this table re-verified before any claim.

**Equality is defined on values, not on source text.** A source equals the
bound only when `Fraction(x) == Fraction(max)`. A literal spelled like `max`
is equal only when its binary64 value is exactly the decimal, which requires
`max` to be dyadic (for example `2.5` or `0.75`). For a non-dyadic `max`, a
same-spelled float literal is either above it (`0.1`) or below it (`0.3`).

**O6, resolved (owner ruling, 2026-10-21): option (a), the exact authored
decimal bound.** The author-declared canonical decimal is the authority. The
bound is never converted to binary64 or otherwise rounded.

Consequences:

- An author who writes `max: 0.1`, with code that sets the literal `0.1`,
  gets a **violation**, because Python's `0.1` is slightly above the exact
  decimal. This is the rule as declared, not a matcher false positive. It is
  deliberately strict and may surprise authors.
- **Diagnostics must state it:** for a violation, show the exact runtime value
  next to the authored bound, and say that no implicit tolerance applies.
- **Documentation must explain** that for non-dyadic bounds a same-spelled
  float literal may be above or below the bound.
- **Any tolerance or rounded-bound policy** would be a separate, explicit
  future contract. It is never an implicit default and never a relaxation of
  this one.

The alternative, considered and rejected for this slice, was rounding the
bound once to the nearest binary64.

**Identity:** `rule_id_of` is unchanged:
`<decision>:FORBID_NUMERIC_ABOVE:sha256([value, applicability])[:32]`. The
existing payload shape and the hook's `violation.rule == rule_value` join
(`hook.py:830-841, 906-909`) are preserved.

**Golden vectors,** computed with `rule_identity` at `7dc02e81` with
`include_paths: ["src/**"]`:

| Contract | `rule_id` |
|---|---|
| Existing: ADR-005's global `FORBID_LITERAL` (its install-command literal) | `ADR-005:FORBID_LITERAL:cbf4d271068507ddb12c33abd765e333` (matches persisted memory) |
| symbol `ROUTER_DEADLINE_S` + call `classify`@1, max `5` | `ADR-001:FORBID_NUMERIC_ABOVE:29b880066c98c7db4abb997f7cbbb096` |
| symbol only, max `5` | `ADR-001:FORBID_NUMERIC_ABOVE:19aa8ed962b7e693ffe3d71804cf4c7c` |
| call `classify`@1 only, max `2.5` | `ADR-001:FORBID_NUMERIC_ABOVE:e74969fb22bd8988d5fae6133a8b7a57` |

For example, the first new row's canonical value is:

```text
{"call":{"function":"classify","position":1},"inclusive":true,"language":"python","max":"5","symbol":"ROUTER_DEADLINE_S","unit":"seconds","v":1}
```

**P1 acceptance gates.** Each must be proven by the implementation charter's
regression matrix:

1. canonical serialization, as above;
2. strict validation at authoring **and** at load, with no load-time rewrite
   of persisted content;
3. byte-stable round trip through parse, compile, persist, load, project and
   re-serialize;
4. stable semantic identity: same contract, same id; any semantic change, new
   id;
5. golden vectors for old and new ids;
6. readable diagnostics that render the contract in human terms, not the raw
   JSON;
7. old readers fail closed and downgrade is refused. Persisting this type
   requires schema **v2** with a declared `semantic_features` value. The
   proposed value is `numeric_upper_bound_rule` (**open question O3**). It
   must never appear in v1 memory.

If any gate cannot be met, the fallback is P2 (a structured `rule_payload`
with an extended identity hash). P2 would be a separate amendment to this
ADR.

### 6. Input contract: complete source only

The rule may report no violation **only** on a verified, complete Python
source file read from a trusted target path. That path resolves against the
explicit project root, and ADR-020 applicability is `APPLIED`.

- **Never a clean result:** a prompt, a code fragment, an introduced-delta
  text or stdin text without a target path produces `MATCHER_UNEVALUATED`
  with `INCOMPLETE_SOURCE_INPUT`, even if it parses.
- **File kind** comes from the input contract, never from whether the text
  parses.
- **Grammar:** the pinned runtime's `ast`. A file that does not parse
  produces `MATCHER_UNEVALUATED` with `PARSE_FAILURE`.

How the check surface conveys "complete Python source at path P" is decided in
the implementation charter. It could be a flag, a subcommand or a payload
field.

### 7. Surface: whole-file audit only (G1)

The first slice runs only as a complete-source audit or check.

- **No pre-write protection is claimed.** The ADR-018 introduced-delta gate
  does not evaluate this rule.
- **On the gate path,** the hook, the Agent SDK and LangChain see delta text,
  which is never complete source. They must report the rule as
  `MATCHER_UNEVALUATED` / `INCOMPLETE_SOURCE_INPUT`. They must never pass it
  silently.
- **No CI integration** is claimed or authorized.
- **Delta-attributed evaluation (G2)** would need a separate ADR amendment and
  charter.

### 8. Mixed results (M-a, target contract)

A trusted, correctly bound violation for one applicable rule stays
actionable even when other rules or sources are unevaluated. Unknown alone
never denies.

The per-surface precedence is the table in the design proposal, §4.4. It is
adopted as the **target**, and it differs from today's hook, which proceeds
on any incompleteness (`hook.py:684-686`). Changing that is a behavioral
change, owned by the implementation charter.

### 9. Conflict detector and evidence

- **Conflict detector: enforcement-only.** The response-text
  `ConflictDetector` does not evaluate this type. Its skip must be reported as
  noncoverage, not presented as a conflict-free PASS.
- **Evidence (ADR-029):** before any claim that enforcement was observed, the
  same evaluation must bind:
  - the subject digest;
  - the `rule_id` and decision version;
  - applicability;
  - matcher status and reason;
  - the attributable outcome.

  This extends the existing `RuleEvaluation` / `Violation` /
  `EnforcementResult` chain. There is no parallel engine.

### 10. Implementation invariant

`FORBID_NUMERIC_ABOVE` joins `VALID_RULE_TYPES` only in the **same change**
that adds its matcher, its per-rule matcher status, and the consumer
validator updates. Otherwise it would be traced `APPLIED` and silently PASS
(`enforcer.py:231-257`).

These sites must each be decided explicitly in the charter, either "literal
only, documented" or "extended":

- protection activation (`protection.py:102,838`);
- preservation (`cli.py:1081-1107`);
- governability (`enforcer.py:388-392`);
- readiness guardrails;
- evidence identity (`decision_governance.py:379-389`);
- the MCP and EventCatalog serializers.

## Consequences

**Positive:**

- Decisions can express numeric limits that a forbidden literal cannot.
- Matcher uncertainty becomes visible as a first-class, per-rule status
  rather than a hidden PASS.
- `FORBID_LITERAL` behavior and ids are unchanged.

**Negative / accepted trade-offs:**

- Python-only and recognition-bound: many real forms (keyword arguments,
  derived constants, aliases, attribute calls) are `UNEVALUATED` in the first
  slice.
- Audit-only: no pre-write protection.
- Requires a check-payload and validator contract change across three
  consumers, and a schema v2 feature.
- `UNEVALUATED` rates may be high. The pre-registered criteria make that
  visible rather than hiding it.

## Owner rulings (provisional, 2026-10-21; binding only if this ADR is accepted)

| ID | Ruling |
|---|---|
| O1 | Type name **`FORBID_NUMERIC_ABOVE`** |
| O2 | **No optional sources.** Every declared source must be positively found and inspected. Absence or ambiguity without another recognized violation is `MATCHER_UNEVALUATED`, never a pass |
| O3 | v2 `semantic_features` value **`numeric_upper_bound_rule`**. It requires backwards-reader refusal tests, no v1 semantics and golden tests. It does not by itself approve the persistence implementation |
| O4 | `call.position` is **0-based** |
| O5 | **`max <= 0` is rejected at authoring.** Positivity is consistent across `max` (§5 grammar), recognized source values (`x <= 0` is disabled, so `UNKNOWN`, §5a) and diagnostics |
| O6 | **Resolved: (a), the exact authored decimal bound.** No implicit tolerance or rounding. Diagnostics and documentation must make the consequence explicit. See §5a |

## Not decided here

- The held-out corpus.
- The implementation charter and `[layer1-freeze]` amendment.
- The JSON payload field names.
- The complete-source flag spelling.
- G2.
- Keyword arguments, exclusive bounds, ranges, units, constant propagation and
  other languages.
- P0-B.

## Related

- ADR-017 (retrieval vs enforcement)
- ADR-018 (introduced delta)
- ADR-019 (typed literal contract, §9)
- ADR-020 (path applicability)
- ADR-029 (evidence binding)
- ADR-030 (persistence and identity)
- ADR-031 (governance, §8 and §10)
- ADR-033 (availability)
- Design proposal (#589)
- P0-A (#578, #582, #586)
