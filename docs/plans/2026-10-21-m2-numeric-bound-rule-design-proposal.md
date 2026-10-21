# Design proposal: a static numeric-bound typed rule (from P0-A M2)

**Status:** **DRAFT proposal, revision 2, documentation only.** Authorized by
the owner on 2026-10-21 in the
[P0-A closure decision](https://github.com/MnemeHQ/mneme/pull/586#issuecomment-6316909730).
Revision 2 incorporates the owner's N1–N8 rulings from the
[design review of `7eeb1609`](https://github.com/MnemeHQ/mneme/pull/589#issuecomment-6317223239).

This document records design direction only. It does **not**:

- accept a rule type;
- finalize a directive name or schema, which is deferred to a formal ADR
  review;
- authorize an ADR in `docs/adr/`, a held-out corpus freeze, a Layer 1
  amendment, or any change to `mneme/`, `.mneme/`, CI or the benchmark
  suites.

**Central principle:** Mneme must never claim a decision was satisfied when
its rule could not be completely evaluated.

**Source anchor:** `MnemeHQ/mneme` `main` @ `21eabe8a`. Line numbers refer to
that commit.
**Evidence base:**

- P0-A charter
  ([`2026-10-21-p0a-semantic-constraint-validation-charter.md`](2026-10-21-p0a-semantic-constraint-validation-charter.md))
- Set 1 freeze (#582, `f5c910bc`)
- Offline detector results (#586, `21eabe8a`,
  `validation/semantic-constraint-p0a/RESULTS.md`)

## 1. What is being proposed, and what is not

**In question:** whether the C2 capability of the P0-A detector M2 can become
an explicit typed rule. That capability is a static, inclusive upper-bound
check on a declared Python numeric value and on a declared positional
argument at direct call sites of a declared function.

**Evidence, and its limits:**

- M2 caught 4 of 5 C2 violations (C, I, K, M-5.0001) with no false block and
  no miss.
- J, a bound derived from another constant, was `UNEVALUATED`.
- All of this is **one synthetic router**, **Python only**, and a **visible,
  precommitted** case set.
- The P0-A set did **not** exercise keyword-argument matching or exclusive
  bounds.
- The single gate case (T) and the deletion-only case (U) are **not**
  evidence of gate coverage.
- What this establishes is bounded offline detection capability. It is not
  production enforcement and not generalization.

**Out of scope:**

- C1 (disabled deadlines) and C3 (fallback structure).
- M1 (token-aware literals).
- Any general semantic or policy engine.
- Languages other than Python.
- The introduced-delta pre-write gate (N4).
- P0-B, which is owned by a separate session.

## 2. The current pipeline a second rule type must pass through

ADR-019 §7 requires a typed rule to survive the whole pipeline. Today every
stage is specific to `FORBID_LITERAL`:

| Stage | Today (anchor `21eabe8a`) | Consequence for a second type |
|---|---|---|
| Authoring and parsing | `VALID_KINDS` (`adr_constraints.py:48-53`); structured bodies only for `FORBID_LITERAL` (`:190-193`); keys limited to `value`, `include_paths`, `exclude_paths` (`:207-213`) | Needs its own strict structured grammar |
| Compilation | `_directive_to_rule` compiles only `FORBID_LITERAL` (`adr_compiler.py:47-56`); the canonical mirror hardcodes it (`decision_index.py:265-311`) | Both must route the new kind |
| Schema | `RuleType = Literal["FORBID_LITERAL"]`, `VALID_RULE_TYPES` (`schemas.py:51-53`); `Rule.value: str`, non-empty (`:156-179`) | No structured payload |
| Persistence | Writers emit `rule_payload: {"value": ...}`; the loader rejects any other payload field in v1 and v2 (`decision_index_persistence.py:1981-1984`) | Extra fields fail closed at load |
| Identity | `rule_id = <decision>:<TYPE>:sha256([value, applicability])[:32]` (`rule_identity.py:50-58`; ADR-030 §7, ADR-031 §10) | Identity covers only `value` and applicability |
| Applicability | `evaluate_path_selectors` does not depend on rule type (`path_selectors.py:205-286`) | Reusable as is (ADR-020 §1) |
| Evaluation | The enforcer traces every typed rule but only `FORBID_LITERAL` can fail (`enforcer.py:231-257`); the conflict detector skips other types (`conflict_detector.py:142`) | **Admitting a type without a matcher would silently PASS** |
| "Unevaluated" | Only path `UNKNOWN`, which sets `evaluation_complete=false`, CLI exit 2, `INCOMPLETE` (`cli.py:519-543`) | No per-rule matcher status |
| Hook trust validator | Rejects a payload whose `evaluation_complete` disagrees with the presence of applicability `UNKNOWN` (`hook.py:365-378`) | A non-path incompleteness would be judged an **inconsistent payload** |
| Hook verdict mapping | `evaluation_complete=false` proceeds, even when a FAIL violation is present (`hook.py:684-686`) | A recognized violation can pass when anything else is incomplete |
| Evidence | `RuleEvaluation` trace (`path_selectors.py:43-67`); no subject digest, no per-rule outcome (ADR-029 dimensions 2 and 6) | Binding is incomplete for any rule today |
| Other `FORBID_LITERAL`-only sites | `protection.py:102,838`; `cli.py:1081-1107`; `enforcer.assess_governability` (`:388-392`); `decision_governance.py:379-389`; MCP and EventCatalog serializers | Each needs an explicit decision |

**Invariant for any future implementation (confirmed by the owner):** the new
type must not join `VALID_RULE_TYPES` before its matcher, its per-rule matcher
status and its diagnostics exist in the same change. Otherwise, by the
evaluation row above, it would be traced as `APPLIED` and silently PASS.

## 3. Rule contract (N1, conditionally approved)

The directive name and schema are **not** finalized here; that is deferred to
a formal ADR review. The placeholder `<NUMERIC_BOUND>` is used throughout.

### 3.1 First committed claim (what P0-A evidence supports)

| Element | First-slice contract |
|---|---|
| Language | Python only, declared explicitly (`language: python`); any other value is an authoring error |
| Value sources | At least one is required: a declared module-level symbol (bare-name assignment), and/or a declared function's direct bare-name call sites `f(...)` with a declared **positional** argument index |
| Recognized value forms | Numeric literals and M2's already characterized literal-arithmetic folding, with its exponent, division-by-zero and overflow limits. Nothing else |
| Bound | **Inclusive** upper bound only |
| Unit | Declared explicitly; documentation only, **never converted** |
| Path applicability | ADR-020 `include_paths`/`exclude_paths`, required. There is no global form |

### 3.2 Explicitly excluded from the first claim

These require new, pre-registered evidence before they can be part of any
claim:

- keyword-argument matching;
- exclusive bounds;
- lower bounds or ranges;
- unit conversion;
- same-module constant propagation (the J shape);
- attribute calls (`obj.f(...)`);
- import aliases.

### 3.3 Positive source discovery

The rule may report `NO_VIOLATION` only when it has **positive evidence** that
every declared value source was found and inspected. Each of these yields
`UNEVALUATED`, never a pass:

- a declared symbol that is absent, assigned more than once, or rebound
  anywhere in the module;
- a declared function with no direct call site in an applicable file;
- a call that is shadowed or rebound, or a function that escapes as a value;
- a call with `*args`/`**kwargs`, or with fewer arguments than the declared
  position;
- any value outside the recognized forms;
- a value that is non-numeric or disabled (`None`, a bool, a string, zero,
  negative, infinite, NaN). Such a value is a C1 question, which this rule
  does not claim.

**Owner question for the ADR:** must a file with the symbol but no call site
(or the reverse) be `UNEVALUATED`, or may a source declared as optional be
absent? The default proposed here is "every declared source must be
positively found".

### 3.4 Complete-source input requirement

A Python AST rule may produce a clean result **only on a verified, complete
Python source file at a trusted target path**. Prompts, code fragments,
isolated lines and partial edit text must never receive `NO_VIOLATION`, even
if they happen to parse. For the first slice this means:

- **The input is a whole file read from a trusted path.** That path resolves
  against the explicit project root and is subject to ADR-020 applicability.
  This is not the `--input` text of an arbitrary prompt or a delta.
- **File kind is established by contract, not inferred from parseability.**
  The applicable path must name a Python source file. Any input not marked
  as complete source (a prompt, a delta, stdin text with no target path)
  yields `UNEVALUATED`.
- **A file that does not parse yields `UNEVALUATED`** (a parse failure),
  never a violation and never a pass.
- **The supported grammar is the pinned runtime's `ast`.**

How the check surface carries "complete source of kind Python at path P"
(a new flag, a separate subcommand, or a payload field) is an ADR and charter
decision. It is not settled here.

An illustrative shape, **not a proposed spelling**:

```text
- <NUMERIC_BOUND>:
    language: python
    symbol: ROUTER_DEADLINE_S
    call: { function: classify, position: 1 }
    max: 5
    inclusive: true
    unit: seconds
    include_paths: ["src/**"]
```

## 4. Outcome semantics (N2) and mixed results (N3)

### 4.1 Three independent dimensions, never collapsed

| Dimension | Values | Owner |
|---|---|---|
| Path applicability (ADR-020) | `APPLIED`, `EXCLUDED`, `UNKNOWN` | Unchanged; type-independent |
| **Per-rule matcher status** (new) | `RECOGNIZED` or `MATCHER_UNEVALUATED`, with an identifiable reason (for example `PARSE_FAILURE`, `UNRECOGNIZED_FORM`, `SOURCE_NOT_FOUND`, `AMBIGUOUS_BINDING`, `INCOMPLETE_SOURCE_INPUT`) | New, per rule and per evaluation |
| Operational checker status | Ran and trusted, or not run / crashed / timed out / untrusted payload | Unchanged: existing trust checks and ADR-033 availability routing (`hook.py:636-681`; `availability.py`) |

Matcher uncertainty must **never** be expressed as path `UNKNOWN`. Operational
failure is **not** a rule outcome, and must not be relabelled as matcher
status or as PASS.

### 4.2 Per-rule result (target semantics)

Only for an `APPLIED` rule with a trusted, complete-source input:

1. **Any recognized source exceeds the bound:** `VIOLATION`, even if another
   source is unrecognized.
2. **Otherwise, any required source is unrecognized or not found:**
   `MATCHER_UNEVALUATED`, with a reason.
3. **Otherwise** (every declared source positively recognized and within the
   bound): `NO_VIOLATION`.

### 4.3 U1, revised

`evaluation_complete` stays as it is: a **derived aggregate**, false if any
rule's applicability is `UNKNOWN` or any rule's matcher status is
`MATCHER_UNEVALUATED`. It is **not** a substitute for the per-rule matcher
status and reason, which the trace and the JSON payload must carry
explicitly.

**Revised risk assessment:** the hook's trust validator currently requires
`evaluation_complete` to equal "no applicability `UNKNOWN`"
(`hook.py:373-378`). A payload that is incomplete only because of matcher
status would therefore be classified as **inconsistent, meaning untrusted**,
which is operational failure. That is the wrong category, even though both
paths happen to proceed today. U1 therefore requires a future change to the
`mneme.check` JSON contract and to every consumer's consistency validator:
the hook, the Agent SDK and the LangChain middleware. The validator must
accept matcher-incomplete payloads as **trusted unevaluated**, and must check
that the aggregate equals "applicability `UNKNOWN` **or** matcher
`MATCHER_UNEVALUATED`". This ruling implements no new status.

### 4.4 Mixed results: target contract M-a (not today's behavior)

A **trusted, correctly bound** `VIOLATION` for one applicable rule stays
actionable even when other sources or rules are unevaluated. **Unknown
alone never causes a deny.** Precedence, as a target contract for a separate
behavioral charter:

| Surface | Trusted violation present (others may be unevaluated) | Only unevaluated (no violation) | Operational failure |
|---|---|---|---|
| CLI `--mode strict` | `FAIL`, exit 2, unevaluated rules listed | `INCOMPLETE`, exit 2 | Error, as today |
| CLI `--mode warn` | Violation reported, unevaluated rules listed. The exit code needs a charter decision, because today incompleteness forces exit 2 in both modes (`cli.py:519-520`) | `INCOMPLETE`, exit 2 (as today) | Error, as today |
| Claude Code hook, strict | Deny | Proceed with a diagnostic (ADR-033 §3); refuse only under authorized closed availability | Existing trust and availability routing |
| Claude Code hook, warn | Defer | Proceed with a diagnostic | As above |
| Agent SDK / LangChain, strict | `DENIED`, handler not run | `fail_open` with `[mneme] UNEVALUATED`. There is no ADR-033 routing on this path today | Existing `fail_open` |
| Agent SDK / LangChain, warn | `WARN` | As above | As above |

**Today's behavior differs:** the hook proceeds whenever
`evaluation_complete=false`, even with a FAIL present (`hook.py:684-686`).
Moving to M-a is a behavioral change that needs its own reviewed charter.
Under G1 (section 5), the first slice does not run through these gates at
all, so the table is the target for a later gate decision. It is not part of
the first slice.

## 5. Surface boundary (N4): G1, whole-file audit only

For the first slice, the rule runs **only** on a full-source audit or check
with the trustworthy file-kind and path contract of section 3.4. It does
**not** run at the ADR-018 introduced-delta pre-write gate, and it carries
**no pre-write protection claim**.

- **G2 (whole file attributed to the delta) is a separate future question.**
  It would need its own charter, an ADR-018 amendment or a per-type
  exception, and gate-specific evidence.
- **T is one gate instance and U is a deletion-only edit.** Neither is gate
  coverage evidence, and the gate skips edits that introduce nothing
  (`hook.py:1169-1173`).
- **This proposal does not claim or authorize CI integration.** A CI check
  is a separate enforcement surface with its own review.
- **The gate surfaces cannot be safe yet.** Until the gate integrations can
  carry complete-source input and per-rule matcher status, the type must be
  either ignored by gate surfaces with that noncoverage visible, or reported
  as `MATCHER_UNEVALUATED` with `INCOMPLETE_SOURCE_INPUT`. It must never be
  silently passed. Which of the two applies is a charter decision.

## 6. Compatibility (N5, N6, N7)

### 6.1 Persistence and identity: P1 provisionally preferred (N5)

**P1:** keep `Rule.value` as a single typed, canonical serialized string, so
that the existing `{"value"}` payload shape, the `rule_id` algorithm and the
hook's `violation.rule == rule_value` join (`hook.py:830-841, 906-909`) are
unchanged.

P1 is **not** an assumed safe shortcut. Each item below is an explicit review
gate that must be specified and proven in the ADR and charter before
acceptance:

1. **Canonical serialization:**
   - exact field set and field order;
   - no implicit defaults, since every field is explicit (including
     `inclusive`);
   - escaping rules;
   - canonical numeric representation, which rejects NaN, Infinity, bool, and
     JSON numbers outside the supported range or precision, and fixes how
     `5`, `5.0` and `5e0` are normalized.
2. **Strict validation:** unknown or missing fields, a wrong type, or a
   non-canonical input is rejected at authoring and at load. Load-time
   normalization never silently rewrites persisted content.
3. **Round trip:** parse, compile, persist, load, project and re-serialize is
   byte-stable.
4. **Stable semantic identity:** a semantically identical contract gets the
   same `rule_id`, and any semantic change gets a new one (ADR-030 §7).
5. **Golden vectors:** for existing `FORBID_LITERAL` ids (byte-stable) and
   for new-type ids.
6. **Readable diagnostics:** the CLI and the trace render the contract in
   human terms, not as raw serialized text.
7. **Old readers fail closed, and downgrade is refused:**
   - Declare a supported **v2 `semantic_features`** value, as ADR-031 §8
     requires, so that a reader without it refuses the memory.
   - Never place the new semantics in v1, or in an opaque string an older
     consumer could ignore or pass through as if it were a literal.
   - Upgrade and downgrade paths are specified, and downgrade is refused.

P2 (a structured `rule_payload` with an extended identity hash) remains the
alternative if any P1 gate cannot be met.

### 6.2 Conflict detector (N6): enforcement-only, visible limitation

The new type is **enforcement-only**. Response-text `ConflictDetector` matching
is not retrofitted to AST semantics. Its skip
(`conflict_detector.py:142`) must, however, be **visible**: a conflict result
that skipped numeric-bound rules must report that noncoverage in future
interfaces and in evidence claims. It must not present itself as a
comprehensive, conflict-free PASS. No engine change is authorized now.

### 6.3 Evidence (N7): required before "enforcement observed"

Before any claim that relevant enforcement was **observed**, the same
evaluation must bind, under ADR-029:

- the subject digest;
- the rule and configuration identity;
- applicability;
- the per-rule matcher and evaluation status;
- an attributable outcome.

This reuses the existing `RuleEvaluation` / `Violation` / `EnforcementResult`
chain and canonical IDs. There is no parallel evidence engine and no
unrelated global redesign. The necessary additions (subject digest and
per-rule outcome, which are missing for every rule type today) are scoped in
the behavioral charter.

### 6.4 Other contracts

| Contract | Handling |
|---|---|
| ADR-019 §1, §9 | A new, separately specified type. `FORBID_LITERAL` parsing, matching and identity are unchanged |
| ADR-019 §5 | A violation is a deterministic FAIL. Its diagnostics show the source line, the recognized value and the bound |
| ADR-019 §6 | Reuse the type-independent canonical policy exemption (`path_selectors.py:184-226`) |
| ADR-020 §9, §11 | Allowed keys enumerated for this type. Python-awareness lives in the matcher, not in applicability |
| Other literal-only sites | Protection activation, preservation, governability, readiness guardrails, MCP and EventCatalog are each decided explicitly in the charter, either "literal only, documented" or "extended" |

## 7. Independent evaluation (N8)

The M2 prototype already exists and is visible. The next evaluation is
therefore a **held-out validation of a new implementation** of an approved
contract. It is **not** proof that the approach was devised blind.

**Sequencing:** the held-out freeze happens **after** the rule contract and
the metrics plan are frozen and approved, and **before** any new matcher is
written. **This review authorizes no corpus work.**

**What is frozen** (by an independent session):

- held-out cases;
- source-adjudicated labels;
- the frozen contract specification;
- the supported Python grammar version;
- disjoint audit metrics. Gate metrics apply only if a future gate option is
  chartered.

The corpus should cover several decision shapes with the same contract
(timeouts, retry counts, pool sizes, rate limits, batch sizes). It should
include benign look-alikes, out-of-scope paths, unsupported forms that must
be `UNEVALUATED`, parse failures, and non-source inputs that must never pass.

**Pre-registered criteria,** set before implementation:

- zero false blocks and zero misses on **positively recognized** cases;
- every unsupported or ambiguous case `UNEVALUATED`;
- `UNEVALUATED` rates reported for violation and benign cases, with
  **explicit coverage and unknown-rate thresholds** that make a high unknown
  rate visible rather than hidden;
- two deterministic, byte-identical runs.

Failing any criterion means the type is not proposed for enforcement.

## 8. Proposed sequence (each step needs its own authorization)

1. **This proposal**, revised and approved as design direction.
2. **Formal ADR review** that freezes the rule contract (name, schema, the P1
   gates of section 6.1, the outcome semantics of section 4) and the
   pre-registered metrics plan of section 7.
3. **Held-out corpus freeze** by an independent session, against that frozen
   contract and plan, before any matcher exists.
4. **Layer 1 behavioral charter** and `[layer1-freeze]` amendment (Amendment
   Procedure §4). It covers:
   - the enforcement-input change;
   - the complete-source contract;
   - per-rule matcher status and JSON trust validation;
   - M-a precedence;
   - visible gate and conflict-detector noncoverage;
   - the evidence additions;
   - the literal-only sites;
   - the regression matrix.
5. **Implementation** behind that charter, with the "no `VALID_RULE_TYPES`
   entry without a matcher" invariant.
6. **Scoring** against the frozen held-out corpus. The owner then decides on
   any claim.

## 9. Owner rulings (recorded 2026-10-21)

| ID | Ruling | Where reflected |
|---|---|---|
| N1 | Conditional: Python; positional, direct bare-name calls and/or declared symbol; characterized literal folding; inclusive upper bound; explicit units with no conversion; positive source discovery; complete-source input only. Keyword and exclusive bounds are excluded from the first claim. Name and schema are deferred to the ADR | §3 |
| N2 | U1 with per-rule matcher status, distinct from path applicability and operational failure; `evaluation_complete` is a derived aggregate; the JSON trust contract must be updated | §4.1–4.3 |
| N3 | M-a as a target contract for a separate behavioral charter; no deny on unknown alone; strict, warn and operational failure differentiated | §4.4 |
| N4 | G1 only: full-source audit/check. No pre-write claim; G2 is a separate future question; no CI claim | §5 |
| N5 | P1 provisionally preferred, subject to explicit canonicalization, validation, round-trip, identity, golden-vector, diagnostic and old-reader gates, plus a declared v2 `semantic_features` value | §6.1 |
| N6 | Enforcement-only, with visible conflict-detector noncoverage | §6.2 |
| N7 | Complete ADR-029 binding before "enforcement observed"; reuse the existing trace | §6.3 |
| N8 | Held-out validation of a new implementation; freeze after the contract and metrics are approved and before the matcher exists; explicit thresholds | §7, §8 |

## 10. Non-goals

- Implementing, accepting or activating any rule.
- Freezing a corpus, writing an ADR, or amending the Layer 1 freeze.
- Editing `mneme/`, `.mneme/`, CI or the benchmarks.
- The introduced-delta gate, keyword arguments, exclusive bounds, C1, C3, M1,
  or a general semantic engine.
- Languages other than Python.
- P0-B.
