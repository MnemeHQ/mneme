---
id: ADR-034
title: "Static Numeric Upper-Bound Typed Rule for Python"
status: accepted
priority: normal
date: 2026-10-21
scope: enforcement.typed_rules.numeric_upper_bound
---

# ADR-034: Static Numeric Upper-Bound Typed Rule for Python

**Status:** **Accepted as an architectural design contract** (owner decision,
2026-10-21,
[authorization on #590](https://github.com/MnemeHQ/mneme/pull/590#issuecomment-6318845775)).

The accepted content is revision 4, as reviewed and merged in #590. That is
squash commit `17e69f7f`, from approved head `311b297b`. This acceptance
changes only the status wording.

**Amended:** 2026-10-24 — G2 pre-write evaluation of new-file `Write`
(§6a, §7a), owner rulings G2-O1 to G2-O6. The amendment is a design
contract only: it authorizes no implementation and claims no pre-write
protection (see "G2 amendment (2026-10-24)" below).
**Amended:** 2026-10-26: relevant-enforcement attribution with several applied numeric rules (§7b, owner ruling D1, from the G2-1 blind validation FAIL in #666). Per-rule attribution is authoritative, and the event-level value is existential. It authorizes no implementation.
**Amended:** 2026-10-26: function-source name resolution follows Python lexical scoping (§3a, owner ruling D2, from the G2-1 blind validation FAIL in #666). It authorizes no matcher change.
**Amended:** 2026-10-27: evidence attribution of non-numeric refusals (§7c, owner rulings D3-1 to D3-4, from the G2-1 R2 FAIL in #692). The evidence record names every violation a trusted, coherent payload reports, with or without a subject. Those identities are attribution only, never relevance. It authorizes no implementation.

**What acceptance means.** Acceptance establishes what a future implementation
must satisfy. It does **not** establish that Mneme enforces numeric bounds:
no `FORBID_NUMERIC_ABOVE` matcher exists.

**What acceptance does not authorize** (each is a separate decision):

- a held-out corpus;
- a matcher, runner, CLI, SDK, hook or CI change;
- v2 feature activation or memory migration;
- an implementation charter or Layer 1 amendment;
- any production enforcement claim.

**Activation boundary.** ADR-034's scope, `enforcement.typed_rules.numeric_upper_bound`,
is distinct from ADR-019's `enforcement.typed_rules`. ADR precedence keeps
one winner per exact scope, so a shared scope would leave ADR-034 silently
shadowed by ADR-019, or, at equal priority, would drop both. With the
distinct scope, ADR-034 becomes eligible as active decision authority on a
future ADR import, alongside ADR-019, as a **retrieval-only** decision: it
has no `## Constraints` directives and declares no mechanically enforceable
rule.

**No authority import, project-memory update, typed-rule registration or
enforcement activation is authorized** as part of this acceptance.

Any later change to the contract is a separately reviewed amendment, never a
post-hoc adjustment.

**Revision history (#590):**

- **Revision 4,** per the
  [review of `394371c1`](https://github.com/MnemeHQ/mneme/pull/590#issuecomment-6318200921):
  - O6 resolved as (a), the exact authored decimal bound;
  - `int`-only exponents, an intentional subset of M2;
  - the M2 parity statement narrowed to the comparison step.
- **Revision 3,** per the
  [review of `3b671664`](https://github.com/MnemeHQ/mneme/pull/590#issuecomment-6317899163):
  - the normative mixed-source record (`PARTIAL`, §4);
  - value-based equality (§5a);
  - O6 raised.
- **Revision 2,** per the
  [review of `e4f2fd2a`](https://github.com/MnemeHQ/mneme/pull/590#issuecomment-6317687350):
  - O1–O5 rulings;
  - numeric evaluation semantics (§5a);
  - the authoring grammar for `max`;
  - mixed-source scoring precedence.

  That review also recorded that the first draft had not been separately
  authorized after #589.

The pre-registered evaluation criteria, **frozen** together with this
acceptance, are in
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

## Decision

### 1. A new, separately specified rule type

The type name is `FORBID_NUMERIC_ABOVE`, following the `FORBID_` family
(O1 ruling).

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

### 3a. Function-source name resolution follows Python lexical scoping (amendment 2026-10-26, owner ruling D2)

**Why.** The G2-1 blind validation (results record
[`adr-034-g2-1-blind-scoring-results-2026-10-25.md`](../validation/adr-034-g2-1-blind-scoring-results-2026-10-25.md),
#666 `cec27ea9`, verdict **FAIL**) exposed a gap, diagnosed as D2. §3 says
the function source becomes `UNKNOWN` when "the function is shadowed,
rebound or escapes as a value". It doesn't say **where** a shadowing binding
takes effect.

The shipped matcher reads it as "any other binding of the name, anywhere in
the module" (`mneme/numeric_rule.py:742-760`). Under that reading:

- a same-named method `def` in an unrelated class makes the whole call
  source `AMBIGUOUS_BINDING`;
- that holds even for a proven module-level direct call;
- under availability `open`, a genuinely violating write can then proceed
  unevaluated.

Python does not resolve names that way. On 2026-10-26 the owner ruled that
the following is normative. It replaces that reading **for the function
(`call`) source**.

**1. Call sites are resolved one at a time, by Python's lexical rules.** For
each direct bare-name call `function(...)`, the name is resolved at that
call site, in this order:

1. the enclosing function's local scope, which covers parameters,
   assignments, `def`, `class`, `import`, `for`/`with`/`except` targets and
   walrus targets;
2. the scopes of any enclosing functions;
3. the module scope.

A **class body's scope is not visible from the functions nested inside it**,
methods included. For a statement written directly in a class body, the
class scope comes first.

**2. A binding only matters where it resolves.**
- **Resolves to the declaration:** a call site that resolves to the single
  module-level declaration (AMB-01) is a source, classified under §3 and
  §5a.
- **Resolves to another binding:** a call site that resolves to any other
  binding is that call site's own `UNKNOWN` / `AMBIGUOUS_BINDING` source.
  Examples are a parameter, a local name, an enclosing function's name, or a
  class-body binding seen from that same class body. The call site is never
  ignored, so the rule can never come out clean through it.
- **No call site resolves to it:** a binding that no direct call site
  resolves to has **no effect** on the call source. For example, a
  same-named method `def` in a class body does not shadow the module
  function for calls outside that class body.

**3. Rebinding and escape at module scope still make the whole source
`AMBIGUOUS_BINDING`.** That covers:
- a second module-level binding of the name, or any module-level
  reassignment, `del`, or conditional or `try`-guarded definition;
- a `global function` declaration in any scope;
- any load of the name that resolves to the module declaration other than
  as the callee of a direct call. That is the escape case, as before.

**4. If resolution can't be decided, the result is unevaluated, never
clean.** Two situations count:
- the module uses a construct that defeats static resolution: `exec`/`eval`,
  `globals()`/`locals()`/`vars()` writes, star imports, `nonlocal` or
  `global` touching the name, `__builtins__` manipulation, and similar;
- the matcher otherwise cannot decide a call site's binding
  deterministically.

In either case the affected call sites, or the whole source if the scope is
unbounded, are `UNKNOWN` / `AMBIGUOUS_BINDING`. A clean result is never
assumed.

**5. Unchanged.** Method and attribute calls (`self.function(...)`,
`obj.function(...)`) are not direct bare-name calls, so they are not
sources. Absence of every source is still `SOURCE_NOT_FOUND` (O2). The
`symbol` source keeps its §3 wording. Reason priorities (§4) are
unchanged.

**6. Consequences.**
- **Not authorized here.** This amendment authorizes **no** matcher change.
  Implementing it is a separate, reviewed change to the shared matcher
  (`mneme/numeric_rule.py`). It needs scope-resolution regressions: class
  body versus method, parameter, nested function, enclosing scope,
  comprehension, `global`/`nonlocal`, dynamic constructs, and the D2 shapes.
- **M4 and G1.** The recognition boundary of the M4-validated matcher
  changes, and so does the effect of v1/M4 interpretation AMB-07.
  - **Before:** a same-named parameter shadowed the whole source.
  - **After:** it makes only the call sites inside that function `UNKNOWN`.

  M4's PASS (#628) remains evidence for its pinned build only. Its results
  are preserved and not re-scored. A post-change G1 audit claim is **not**
  covered by M4. The change must regression-test the shared matcher against
  the public M4 R vectors and the G1 regression suite. Any new G1 blind
  claim needs its own validation.
- **G2-1.** The FAIL stays exactly as recorded. Any later PASS needs a new
  pre-registration that adopts this section and §7b, plus a newly authored,
  independently held-out corpus.

**Not decided here: the `symbol` source.** The same question applies to a
class-body assignment, or a function-local assignment, of the governed
**symbol**. It is outside D2. The §3 reading ("rebound anywhere in the
module") stays in force for symbols until a separate ruling.

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
   value is `numeric_upper_bound_rule` (O3 ruling). It must never appear in
   v1 memory.

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

### 6a. Complete proposed source for a new file (amendment 2026-10-24)

Accepted with owner rulings G2-O1 to G2-O6 below. Source anchors in §6a and
§7a refer to `main` @ `0d367fc6`. The reviewed design record is the
[G2 proposal](../plans/2026-10-24-adr-034-g2-new-file-write-amendment-proposal.md)
(revision 2, `08e0f9ac`; merged in #630 as `97143065`).

A second complete-source input kind, **`proposed_new_source`**, is
recognized. It is distinct from `complete_source_file` (G1) and never
reported as it.

**Preconditions.** The checker establishes all of these itself, at
evaluation time, from the governed target path. If any of preconditions 1–4
fails, the input is unverified and §6's `INCOMPLETE_SOURCE_INPUT` applies.

If precondition 5 fails, the result is an **operational error**: a
non-verdict exit, untrusted under ADR-033 §2.

- **Never a verdict or PASS.** The result is never a verdict, never PASS and
  never a legacy fallback.
- **No legacy result exists.** The legacy `--input` path has no defined
  verdict for undecodable text, so there is no unverified result to fall
  back to.
- **Same as G1.** This matches `--source-file`.
- **Stricter, not wider.** It is still "unverified" in the sense of §6,
  because no complete-source claim is made. It is realized in the stricter
  direction (no result at all).

1. **Verified absence.** An `lstat` of the governed target raises "not
   found". Any other outcome is not absence and never becomes a
   `proposed_new_source` subject:
   - the target exists (any file type, including an empty file);
   - the target is a symlink or dangling link;
   - the check raises permission, I/O or other errors.
2. **No link components.** The parent directory resolves strictly. Its
   lexical and resolved forms are equal under `os.path.normcase`, as for G1
   (`cli.py:546-556`).
3. **Inside the policy root.** The target is under the ADR-020 policy root of
   the memory actually loaded, and normalizes to a policy-root-relative
   governed path.
4. **Python file kind.** The target suffix is `.py`. File kind comes from the
   contract and target path, never from whether the bytes parse (§6).
5. **UTF-8.** The proposed text decodes as strict UTF-8.

**Subject.** The subject is the UTF-8 encoding of the complete proposed text,
exactly as the checker received it. Its SHA-256 is the subject digest. It is
evaluated once by the unchanged M4 matcher, without import or execution.

**Target binding.** This invariant belongs to the
`proposed_new_source` kind itself. It is not inherited from the G1
`--source-file` branch, whose guard (`cli.py:646-658`) runs only when
`source_file is not None` and would never run on the new path.

The subject records one governed path: the policy-root-relative
normalization of the absence-verified target from precondition 3. ADR-020
applicability for every typed rule must be evaluated against exactly that
governed path. Every applicability record that carries an `input_path` must
equal it.

Any mismatch, or a governed path that cannot be established, is an
operational error (non-verdict exit, untrusted under ADR-033 §2). It is never
a verdict and never a fallback to unverified input.

**Evidence class.** The subject record names `proposed_new_source` as
its input kind. On its own, it is an evaluation of a hypothetical subject (any caller can
submit any bytes for an absent path), never "relevant
enforcement observed".

**Outcomes.** §4 applies unchanged, including O2:

- a proposed file missing any declared source is `MATCHER_UNEVALUATED` /
  `SOURCE_NOT_FOUND`, never `NO_VIOLATION`;
- a proposed file that does not parse is `PARSE_FAILURE`;
- a recognized `EXCEEDS` alongside an unknown source is `PARTIAL`, which is a
  FAIL.

**Digest scope.** The digest identifies the bytes that were evaluated. It is
not a claim about the bytes the host later writes, which may differ (for
example in line endings or a byte-order mark).

### 7. Surface: whole-file audit only (G1)

The first slice runs only as a complete-source audit or check.

- **No pre-write protection is claimed.** The ADR-018 introduced-delta gate
  does not evaluate this rule.
- **On the gate path,** the hook, the Agent SDK and LangChain see delta text,
  which is never complete source. They must report the rule as
  `MATCHER_UNEVALUATED` / `INCOMPLETE_SOURCE_INPUT`. They must never pass it
  silently.
- **No CI integration** is claimed or authorized.
- **Amended 2026-10-24:** §7a specifies the pre-write contract for new-file
  `Write` only. Nothing is claimed until it is implemented and independently
  validated.
- **Delta-attributed evaluation (G2)** would need a separate ADR amendment and
  charter.

### 7a. Surface: pre-write gate for new-file `Write` (G2, amendment 2026-10-24)

**Routing.** On the Claude Code `PreToolUse` direct-write surface, a `Write`
event is routed to the `proposed_new_source` input kind when its resolved
target meets the §6a preconditions. That routing is single-path: when it
applies, it replaces the `--input` delta invocation for that event.

**Unchanged events.** Every other direct-write event keeps today's ADR-018
delta path, and its numeric rules stay `INCOMPLETE_SOURCE_INPUT`:

- `Write` to an existing, empty, unreadable or ambiguous target;
- `Edit` and `MultiEdit`.

The hook's "unreadable `Write` target is new" shortcut (`hook.py:93-107`) stays in force
for literal rules, but it never establishes §6a absence.

**Legacy parity.** The G1 freeze requires byte-identical
`mneme.check/v1` payloads and exit codes for checks with no numeric rule
(`layer1-freeze-e73ff7d.md:903-904`). G2 keeps this guarantee and makes it
stricter: parity holds whenever no `FORBID_NUMERIC_ABOVE` rule is
**`APPLIED`** at the governed target.

In that case, the routed check must produce exactly the stdout payload and
exit status of the legacy invocation: the same carrier bytes passed as
`--input`, with `--target-path` set to the same target. Parity is defined at
this checker level, on the same carrier. This covers each of these cases:

- memory with no numeric rule (no `subject` record, as today);
- numeric rules that are all `EXCLUDED` or `UNKNOWN` at the target (today's
  unverified `subject` record, unchanged).

Unlike G1's `--source-file`, which emits a `subject` record even when no
numeric rule exists (`cli.py:407-412`), the G2 path never adds or relabels a
`subject` record unless a numeric rule is applied.

Literal-rule verdicts are unaffected by construction, because for a
verified-absent target the checked text is identical to today's introduced
content (`hook.py:156`). The one exception is the carrier-encoding correction
below. Any other departure from parity would be a separate reviewed
behavioral change. None is proposed.

**Routed carrier encoding (authorized, routed-only correction).** A routed
event's carrier holds exactly `content.encode("utf-8")`, written in binary
mode.

Today's hook writes its carrier in text mode (`hook.py:794-798`). On Windows
that translates line endings, and CRLF content comes back with doubled line
breaks. For a routed event whose content contains CR, the text checked (by
both literal and numeric rules) can therefore differ from what today's hook
would have checked.

- **Explicitly authorized.** This difference is authorized and limited to
  routed events.
- **No historical parity claim.** No hook-level parity with today's behavior
  is claimed for such events.
- **Unrouted path unchanged.** It keeps its text-mode carrier byte for byte.
  Its CRLF defect is a pre-existing finding, left for a separate reviewed
  fix.

**Host-event binding.** A claim that a real `Write` was governed needs
one record, made by the hook as the enforcing control, that binds all of the
following:

- **Control provenance:** surface (Claude Code `PreToolUse` hook), Mneme
  version, and the pinned host version.
- **Host event:** `tool_name` `Write`, the `file_path` and `cwd` as received,
  and the host-supplied event identifiers that the pinned host provides (for
  example `session_id`, and a tool-call id where present), as established by
  a pinned live test before any support claim.
- **Join:** the SHA-256 of the UTF-8 `tool_input.content` the hook passed to
  the checker. It must equal the checker's subject digest.
- **Rule and outcome:** rule ID, decision version, governed path,
  applicability, matcher status, and the hook's allow/refuse outcome.

Without this record, or if any field mismatches, evidence stays at
"execution observed" or below (ADR-029 §2, fail closed).

This record is the control's own provenance, not an authenticated host
attestation. No ADR-025 attestation is claimed. Its representation is left to
the G2-1 charter, with no new persistence, telemetry or event system
(ADR-029 §3, ADR-033 §7).

**Verdict handling.** The existing trust validation (`assess_verdict`), M-a
precedence (§8, `hook.py:522-533`) and strict/warn behavior apply unchanged:

| Matcher result on `proposed_new_source` | Hook outcome (strict) |
|---|---|
| `RECOGNIZED` / `VIOLATION` | Block before mutation (exit 2), actionable reason |
| `PARTIAL` / `VIOLATION` | Block before mutation; unknown sources reported; never "fully verified" |
| `RECOGNIZED` / `NO_VIOLATION` | Proceed (subject to other rules) |
| `MATCHER_UNEVALUATED` | Unevaluated. ADR-033 availability policy decides; never a compliance PASS |
| Untrusted or crashed checker | Unchanged ADR-033 / #260 handling |

**Availability.** G2 changes no ADR-033 policy. Under default `open`,
unevaluated results proceed with diagnostics. Under AUTHORIZED `closed`, they
are refused as `EVALUATION_INCOMPLETE`.

Because of O2, an in-scope new file that lacks a declared source (a
helper, a test) is unevaluated, so under `closed` it is refused. G2 narrows
the Layer 1 freeze's recorded F2 consequence
(`layer1-freeze-e73ff7d.md:939-944`) only for verified-new files that contain every declared source. The
F2 activation restriction stays in force for closed-availability paths.

**Other consumers.** The Agent SDK and LangChain consumers are out of scope.
They keep §7's delta semantics.

### 7b. Relevant-enforcement attribution with several applied numeric rules (amendment 2026-10-26, owner ruling D1)

**Why.** The G2-1 blind validation (results record
[`adr-034-g2-1-blind-scoring-results-2026-10-25.md`](../validation/adr-034-g2-1-blind-scoring-results-2026-10-25.md),
#666 `cec27ea9`, verdict **FAIL**) exposed a gap, diagnosed as D1. §7a
and G2-1 Amendment 1 A1.3 define relevance for **one** attributable numeric
outcome. They do not say how the outcomes of several applied numeric rules
in one event combine. The owner ruled on 2026-10-26 to make the following
normative.

**1. Per-rule attribution is authoritative.** Under ADR-029 §2, evidence
binds to one specific decision, rule, subject and attributable outcome. So
"relevant enforcement observed" is a claim about **one applied numeric
rule**. For a rule R it holds only when:

- R's matcher record is complete and decided (`RECOGNIZED`, or `PARTIAL`
  with an established violation);
- the hook disposition is attributable to R's outcome under the A1.3 table;
- the common bindings hold: host identity, event, subject, digest, target
  and provenance.

**No inheritance between rules.** A rule never inherits another rule's
relevance:

- an unevaluated rule, an `EXCLUDED` rule, or a rule unrelated to the
  disposition always has per-rule relevance `false`;
- this holds even when another rule in the same event was relevantly
  enforced.

**2. Event-level relevance is existential.** The event-level value is
`true` if and only if **at least one** applied numeric rule has per-rule
relevance `true`. It means exactly that. It **never** claims that every
applied rule was evaluated, that the action is compliant, or anything about
another rule.

**3. Completeness is a separate fact.** `evaluation_complete` (§4) and the
event-level relevance value are independent and are both reported. An event
can be relevantly enforced for one rule and incomplete overall.

| Rule A | Rule B | Event-level relevance | Per-rule (A / B) | Evaluation complete |
|---|---|---|---|---|
| Violated, strict refusal attributable to A | Unevaluated | `true` (A only) | `true` / `false` | no |
| Violated, strict refusal attributable to A | Recognized clean | `true` (A only) | `true` / `false` | yes |
| Recognized clean, event proceeds | Recognized clean, event proceeds | `true` (both) | `true` / `true` | yes |
| Violated, but the refusal came only from an unrelated (non-numeric) rule | Unevaluated | `false` | `false` / `false` | no |

**4. What changes, and what does not.**
- **Blocking decisions do not change.** The hook's blocking decisions, the
  matcher and the strict/warn and availability behavior are unchanged.
- **The evidence validator changes.** It is
  `relevant_enforcement_observed()` in
  `mneme/integrations/claude_code/hook.py`, which currently returns `true`
  only when every applied numeric rule is decided. It must:
  - separate the record-wide completeness check from per-rule attribution;
  - keep the common checks for host, event, subject, digest, target and
    provenance;
  - return the existential event value;
  - expose per-rule relevance.
- **That change needs its own review.** It needs regression tests,
  including every row of the table above, and a review of the evidence
  validator.
- **Not authorized here.** This amendment does not authorize that change,
  and it does not authorize any change arising from D2. D2 (whether a
  same-named method `def` in a class body shadows the module function) is
  adjudicated separately.

**5. No retroactive effect.** The G2-1 blind validation stays **FAIL**,
exactly as recorded. This ruling does not re-score, reinterpret or upgrade
it. Any later G2-1 PASS claim needs:

- a new pre-registration that adopts this definition;
- a newly authored, independently held-out corpus;
- the failure policy of the original pre-registration (§6).

### 7c. Evidence attribution of non-numeric refusals (amendment 2026-10-27, owner rulings D3-1 to D3-4)

**Why.** The G2-1 revalidation R2 scored **FAIL**. Its results record is
[`adr-034-g2-1-r2-blind-scoring-results-2026-10-27.md`](../validation/adr-034-g2-1-r2-blind-scoring-results-2026-10-27.md)
(#692 `591ef687`, custody close #693 `fb11bd00`). The post-scoring
diagnosis, D3, found the cause.

- **Enforcement was correct.** A routed `Write` with no applied numeric
  rule was refused by a literal rule.
- **The evidence record was not.** Its `violations` list was empty, so the
  refusal could not be attributed to the rule that caused it.

The checker leaves out the subject record by design (G2-1 charter §5.2
rule 3). The hook's evidence record copied violation identities only when
that subject was present.

The design is in the accepted proposal,
[`2026-10-27-adr-034-d3-literal-attribution-proposal.md`](../plans/2026-10-27-adr-034-d3-literal-attribution-proposal.md)
(#694 `38c28a0b`). The owner adopted Option A, and the following is
normative.

**1. Violation identities come from every trusted, coherent payload.**

- **What the record carries.** The §7a host-event record's `violations`
  list carries the identity (`rule_id`, `rule_type`) of every violation
  that the checker payload reports. This holds whether or not the payload
  carries a `proposed_new_source` subject.
- **"Trusted" means consistency, not authentication.** It means only that
  the payload passed the hook's consumer consistency checks (G2-1 charter
  §5). It is not authenticated evidence.
- **Untrusted payloads carry nothing.** If the payload is untrusted,
  inconsistent or missing, `violations` stays empty.
- **Unchanged:** the `subject` and `rules` fields, and when they are
  filled.

**2. These identities are attribution only, never relevance.**

- **What they are.** A violation identity is the checker's own report of
  which rule it found violated.
- **What they do not support.** They never support "relevant enforcement
  observed" (§7a, §7b) for any rule. Under ADR-029 §2, that claim still
  needs the full binding: host, event, subject, digest, target and an
  attributable numeric outcome.
- **No inheritance (§7b.1).** A refusal by a non-numeric rule is never
  attributed to a numeric rule.

**3. A malformed identity attributes nothing.** A violation entry whose
`rule_id` is missing, empty or not a string never counts as attribution to
any rule. This holds even when its `rule_type` names a known rule type
such as `FORBID_LITERAL`.

- Implementations and evaluation contracts must treat such an entry as
  unattributed.
- They must cover this with synthetic regression tests.

**4. What changes, and what does not.**

- **Changes:** how the evidence record is built (`build_evidence_record` in
  `mneme/integrations/claude_code/hook.py`). Only the population of
  `violations` changes.
- **Does not change:**
  - blocking decisions, hook outcomes, exit codes and stderr;
  - strict/warn and availability behavior;
  - the matcher and numeric applicability;
  - the `mneme check --json` payload, including the conditional subject
    record;
  - the disposition cause vocabulary;
  - `relevant_enforcement_per_rule`, `relevant_enforcement_observed` and
    `recorded_evaluation_complete`.
- **Schema (D3-2).** The schema stays `mneme.hook_evidence/v1`: no field is
  added, removed or retyped. A consumer that must tell pre-D3 records from
  post-D3 records keys on the implementation pin.

**5. Review, tests and authorization.** The change needs:

- its own implementation PR, with the regression and parity tests in
  proposal §5 and the §3 malformed-identity tests;
- a review against ADR-029, §7a, §7b and this section.

This amendment does not authorize that change.

**6. No retroactive effect (D3-4).** R1 and R2 stay **FAIL**, exactly as
recorded. G2-1 stays **FAIL**.

Any later G2-1 PASS claim needs R3:

- a new pre-registration that pins the D3 implementation and adopts §1–§3;
- a newly authored, independently held-out corpus and a new scorer;
- the pre-R3 key-custody control stated in #693 §9.5.

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
- Audit-only: no pre-write protection. §7a (2026-10-24) specifies a
  pre-write contract for new-file `Write`; it is not implemented.
- Requires a check-payload and validator contract change across three
  consumers, and a schema v2 feature.
- `UNEVALUATED` rates may be high. The pre-registered criteria make that
  visible rather than hiding it.

## Owner rulings (2026-10-21; binding with this ADR's acceptance)

| ID | Ruling |
|---|---|
| O1 | Type name **`FORBID_NUMERIC_ABOVE`** |
| O2 | **No optional sources.** Every declared source must be positively found and inspected. Absence or ambiguity without another recognized violation is `MATCHER_UNEVALUATED`, never a pass |
| O3 | v2 `semantic_features` value **`numeric_upper_bound_rule`**. It requires backwards-reader refusal tests, no v1 semantics and golden tests. It does not by itself approve the persistence implementation |
| O4 | `call.position` is **0-based** |
| O5 | **`max <= 0` is rejected at authoring.** Positivity is consistent across `max` (§5 grammar), recognized source values (`x <= 0` is disabled, so `UNKNOWN`, §5a) and diagnostics |
| O6 | **Resolved: (a), the exact authored decimal bound.** No implicit tolerance or rounding. Diagnostics and documentation must make the consequence explicit. See §5a |

## G2 amendment (2026-10-24)

Owner acceptance: 2026-10-24, of revision 2 (`08e0f9ac`) of the
[G2 proposal](../plans/2026-10-24-adr-034-g2-new-file-write-amendment-proposal.md),
after two architecture reviews: ACCEPT WITH REQUIRED CORRECTIONS (F1–F3) on
revision 1, then APPROVE on revision 2. §6a and §7a are that revision's §4
text, with proposal-internal references replaced by source anchors.

| ID | Ruling |
|---|---|
| G2-O1 | **Verified-absent `Write` only.** Existing files, including empty ones, stay on the ADR-018 delta path |
| G2-O2 | **`proposed_new_source`** is a distinct input kind, never reported as `complete_source_file` |
| G2-O3 | **The checker establishes absence** at evaluation time, never the caller. Submitted bytes are a hypothetical subject; only the hook's host-event binding (§7a) supports "relevant enforcement observed" |
| G2-O4 | **Single-path routing** for qualifying events, no double invocation, with the §6a target-binding invariant and exact legacy parity when no numeric rule is `APPLIED` |
| G2-O5 | **ADR-033 unchanged.** The Layer 1 freeze's F2 activation restriction stays in force for closed-availability paths |
| G2-O6 | **Transport spelling deferred** to the G2-1 charter, which must define the precise trust and invocation boundary before implementation |

**Claim boundary.** Once implemented and independently validated, the claim
would be: on Claude Code `PreToolUse`, a `Write` to a verified-absent `.py`
target inside the policy root is blocked before mutation, in strict mode, when
the complete proposed source has a recognized `FORBID_NUMERIC_ABOVE`
violation. Explicitly not covered: the race between evaluation and write;
equality of evaluated and landed bytes; existing-file `Write`, `Edit`,
`MultiEdit`, deletion, renames and shell mutations; the Agent SDK, LangChain,
Stop and CI; and host behavior when the hook fails to run.

**Reconciliation (2026-10-24, from the review of the G2-1 charter, #634).**
Two clarifications are folded into §6a/§7a in the same docs pass. They make
the contract stricter and do not widen it:

1. **Precondition 5.** An invalid UTF-8 carrier is an operational error,
   never `INCOMPLETE_SOURCE_INPUT` (§6a, ruling G2C-O6).
2. **Routed carrier.** The routed carrier is byte-exact. This is an
   authorized, routed-only correction of today's Windows text-mode line
   ending handling, with no hook-level historical parity claim (§7a).

**Not authorized by this amendment** (each is a separate decision):

- any hook, CLI, matcher, enforcer, SDK, LangChain or CI change;
- the G2-1 behavioral charter, a `[layer1-freeze]` amendment, or a G2
  validation corpus;
- any change to M4 matcher semantics, `DecisionRetriever`, `ConflictDetector`,
  `FORBID_LITERAL` semantics, memory persistence, or ADR-018, ADR-020,
  ADR-029 or ADR-033;
- import of ADR-034 into project memory, or activation of
  `FORBID_NUMERIC_ABOVE` on any path;
- any enforcement or production claim.


## Not decided here

- The held-out corpus.
- The implementation charter and `[layer1-freeze]` amendment.
- The JSON payload field names.
- The complete-source flag spelling.
- G2 beyond the §6a/§7a new-file `Write` contract: the G2-1 charter, the
  transport spelling (G2-O6), existing-file delta attribution and CI.
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
- G2 proposal (#630) and M4 results (#628)
