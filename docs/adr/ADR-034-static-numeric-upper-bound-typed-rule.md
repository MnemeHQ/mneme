---
id: ADR-034
title: "Static Numeric Upper-Bound Typed Rule for Python (Proposed)"
status: proposed
priority: normal
date: 2026-10-21
scope: enforcement.typed_rules
---

# ADR-034: Static Numeric Upper-Bound Typed Rule for Python

**Status:** **Proposed.** This is a draft for owner review. It is **not
accepted**. A proposed ADR is imported as inactive and has no enforcement
effect.

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
| `max` | yes | A finite number, normalized to the canonical decimal form of §5. `bool`, NaN, Infinity and non-numbers are rejected |
| `inclusive` | yes | Must be literally `true`. Exclusive bounds are **not** part of this slice; `false` is an authoring error, not a silent default |
| `unit` | yes | A non-empty label for documentation and diagnostics. It is **never** converted |
| `include_paths` | yes | ADR-020 selectors. There is no global form |
| `exclude_paths` | no | ADR-020 selectors |

Unknown keys, duplicate keys and missing required keys are authoring errors.
The YAML loader already rejects duplicate keys (`adr_constraints.py:119-145`).
`FORBID_LITERAL`'s scalar form has no equivalent here: only the structured form
is valid.

### 3. Recognition scope and positive source discovery

**Recognized value forms are exactly M2's** (P0-A `m2_static_bound.py`
1.0.0):

- numeric literals;
- unary `+`/`-`;
- binary `+ - * / // % **` over recognized operands;
- **not folded:** `bool` operands; `**` with an exponent above 64 in
  magnitude; division by zero; overflow.

Folding never executes source.

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

**Open question O2:** is a declared source that is absent always `UNKNOWN`, or
may the author mark a source optional? This ADR proposes **always `UNKNOWN`**.

### 4. Outcome semantics

There are three dimensions, and they are never collapsed into one another:

1. **Path applicability (ADR-020):** `APPLIED`, `EXCLUDED` or `UNKNOWN`.
   Unchanged and type-independent.
2. **Per-rule matcher status (new):**
   - `RECOGNIZED`;
   - `MATCHER_UNEVALUATED`, with one reason from `PARSE_FAILURE`,
     `UNRECOGNIZED_FORM`, `SOURCE_NOT_FOUND`, `AMBIGUOUS_BINDING` or
     `INCOMPLETE_SOURCE_INPUT`.

   Matcher uncertainty is never expressed as path `UNKNOWN`.
3. **Operational checker status:** unchanged trust and ADR-033 availability
   handling. It is never relabelled as a rule outcome.

**Rule outcome** for an `APPLIED` rule on trusted complete-source input:

1. Any `EXCEEDS` source: **violation**, even if another source is `UNKNOWN`.
   The trigger reports the source line, the recognized value, `max` and
   `unit`.
2. Otherwise, any `UNKNOWN` source: `MATCHER_UNEVALUATED`, with a reason.
3. Otherwise: no violation.

A violation is a deterministic FAIL, as in ADR-019 §5.

**`evaluation_complete`** remains a *derived aggregate*: false if any rule's
applicability is `UNKNOWN` or any rule's matcher status is
`MATCHER_UNEVALUATED`. The JSON payload must carry each rule's matcher status
and reason explicitly. Every consumer's consistency validator must accept a
matcher-incomplete payload as **trusted unevaluated**, by checking that the
aggregate equals "applicability `UNKNOWN` or matcher `MATCHER_UNEVALUATED`".
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

**Canonical decimal string for `max`:**

- **Grammar:** `^-?(0|[1-9][0-9]*)(\.[0-9]*[1-9])?$`. `-0` is rejected.
- **Normalization:** authored numbers are converted exactly, so `5`, `5.0`
  and `"5"` all normalize to `"5"`.
- **Rejected:** exponent notation, non-finite values and `bool`.

**Comparison** uses exact rational arithmetic between the folded source value
and `max`, so it is deterministic and has no float rounding.

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

## Open questions for the owner

| ID | Question | Proposed answer |
|---|---|---|
| O1 | Type name | `FORBID_NUMERIC_ABOVE`. Alternatives: `NUMERIC_UPPER_BOUND`, `MAX_NUMERIC` |
| O2 | Optional sources | No: every declared source must be positively discovered |
| O3 | `semantic_features` value | `numeric_upper_bound_rule` |
| O4 | `call.position` base | 0-based, matching Python's `ast` `args` index |
| O5 | Negative `max` | Permitted by the grammar. Disabled source values (zero or negative) are `UNEVALUATED` regardless, so a non-positive `max` would make every recognized source either disabled or exceeding. Reject `max <= 0` at authoring? Proposed: **reject** |

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
