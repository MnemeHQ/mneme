# Design proposal: a static numeric-bound typed rule (from P0-A M2)

**Status:** **DRAFT proposal, documentation only.** Authorized by the owner on
2026-10-21 in the
[P0-A closure decision](https://github.com/MnemeHQ/mneme/pull/586#issuecomment-6316909730).
That decision authorizes drafting this proposal **only**. It does not accept a
rule type, authorize an ADR in `docs/adr/`, amend the Layer 1 freeze, or
authorize any change to `mneme/`, `.mneme/`, CI or the benchmark suites. This
document presents options and a recommendation for each open question. It
does **not** finalize a rule spelling, a schema or behavior. The owner decides
whether any of it proceeds to a formal ADR and a Layer 1 behavioral charter.
**Source anchor:** `MnemeHQ/mneme` `main` @ `21eabe8a`. Line numbers refer to
that commit.
**Evidence base:** P0-A charter
([`2026-10-21-p0a-semantic-constraint-validation-charter.md`](2026-10-21-p0a-semantic-constraint-validation-charter.md)),
Set 1 freeze (#582, `f5c910bc`), and offline detector results (#586,
`21eabe8a`, `validation/semantic-constraint-p0a/RESULTS.md`).

## 1. What is being proposed, and what is not

**In question:** whether the C2 capability of the P0-A detector M2 can become
an explicit typed rule. That capability is a static, upper-bound check on a
declared Python numeric value and on the matching argument at the call sites
of a declared function.

**Evidence, and its limits:**

- M2 caught 4 of 5 C2 violations (C, I, K, M-5.0001) with no false block and
  no miss.
- J, a bound derived from another constant, was `UNEVALUATED`.
- At the introduced-delta gate, M2 caught the one violation instance (T).
- All of this is **one synthetic router**, **Python only**, and a **visible,
  precommitted** case set. It establishes bounded offline detection
  capability, not production enforcement, and not generalization.

**Out of scope for this proposal:**

- C1 (disabled deadlines): M2 caught 1 of 4, with 3 `UNEVALUATED`.
- C3 (fallback structure).
- M1 (token-aware literals).
- Any general semantic or policy engine.
- Languages other than Python.
- P0-B, which is owned by a separate session.

## 2. The current pipeline a second rule type must pass through

ADR-019 §7 requires a typed rule to survive the whole pipeline. Today every
stage is specific to `FORBID_LITERAL`:

| Stage | Today (anchor `21eabe8a`) | Consequence for a second type |
|---|---|---|
| Authoring and parsing | `VALID_KINDS` (`adr_constraints.py:48-53`); structured bodies only for `FORBID_LITERAL` (`:190-193`); only the keys `value`, `include_paths`, `exclude_paths` (`:207-213`) | Needs its own structured grammar and validation |
| Compilation | `_directive_to_rule` compiles only `FORBID_LITERAL` (`adr_compiler.py:47-56`); the canonical mirror hardcodes it (`decision_index.py:265-311`) | Both must route the new kind |
| Schema | `RuleType = Literal["FORBID_LITERAL"]`, `VALID_RULE_TYPES` (`schemas.py:51-53`); `Rule.value: str` must be non-empty (`:156-179`) | The rule has no structured payload |
| Persistence | Every writer emits `rule_payload: {"value": ...}`; the loader rejects any other payload field in v1 and v2 (`decision_index_persistence.py:1981-1984`) | Extra fields fail closed at load |
| Identity | `rule_id = <decision>:<TYPE>:sha256([value, applicability])[:32]` (`rule_identity.py:50-58`; ADR-030 §7, ADR-031 §10) | Identity covers only `value` and applicability |
| Applicability | `evaluate_path_selectors` does not depend on rule type (`path_selectors.py:205-286`) | Reusable as is (ADR-020 §1) |
| Evaluation | The enforcer traces every typed rule but only `FORBID_LITERAL` can fail (`enforcer.py:231-257`); the conflict detector skips all other types (`conflict_detector.py:142`) | **Admitting a type without a matcher would silently PASS** |
| "Unevaluated" | Exists only as path `UNKNOWN`, which sets `evaluation_complete=false`, CLI exit 2, `INCOMPLETE` (`cli.py:519-543`) | No outcome for "rule applied, matcher could not decide" |
| Gate | The hook checks only introduced lines (`hook.py:147-196`) and skips edits that introduce nothing (`:1169-1173`); `evaluation_complete=false` fails open (`:684-686`) | A line fragment is not parseable Python |
| Evidence | `RuleEvaluation` trace (`path_selectors.py:43-67`); no subject digest, no per-rule outcome field (ADR-029 dimensions 2 and 6) | Binding is incomplete for any rule today |
| Other `FORBID_LITERAL`-only sites | `protection.py:102,838`; `cli.py:1081-1107`; `enforcer.assess_governability` (`:388-392`); `decision_governance.py:379-389`; MCP and EventCatalog serializers | Each needs an explicit decision |

**Invariant for any future implementation:** the new type must not join
`VALID_RULE_TYPES` before its matcher, its `UNEVALUATED` outcome and its
diagnostics exist in the same change. Otherwise, by the evaluation row above,
it would be traced as `APPLIED` and silently PASS. That would break ADR-019 §9
and ADR-033 §1 ("never manufacture a PASS").

## 3. Question 1: the authored rule contract

The owner's instruction is not to finalize spelling or schema by inference.
Below are the contract elements and the options for each. The directive name
is written `<NUMERIC_BOUND>` throughout as a placeholder.

| Element | Options | Recommendation |
|---|---|---|
| **Language** | (a) Python only, parsed with the runtime's `ast`; (b) language-tagged with Python as the only accepted value | (b): require `language: python` explicitly, so other languages fail at authoring rather than silently not matching |
| **Value sources** | (a) a declared module-level symbol only; (b) a declared call-site argument only; (c) both, each optional, at least one required | (c), as measured in P0-A (K shows the call-site source is necessary) |
| **Symbol identity** | (a) a bare module-level `Name` assignment; (b) also class attributes and keyword defaults | (a). Any rebinding of the symbol elsewhere in the module is `UNEVALUATED` (as in M2) |
| **Call-site identity** | (a) a direct call to a bare name, `f(...)`; (b) also `obj.f(...)`; (c) import-alias aware | (a). Attribute calls, aliases, and the function escaping as a value are `UNEVALUATED`, never silently ignored |
| **Argument position** | (a) positional index; (b) keyword name; (c) both, matched together | (c), stated explicitly. A missing argument, `*args` or `**kwargs` is `UNEVALUATED` |
| **Bound** | (a) upper only; (b) lower and upper; (c) a named range | (a) for the first slice, with an explicit `inclusive: true` or `false` and no default |
| **Unit** | (a) unitless number in the author's stated unit; (b) unit-aware conversion | (a). Unit names are documentation only and never converted, so J-like derivations stay `UNEVALUATED` |
| **Recognized value forms** | (a) numeric literals; (b) plus folding of literal arithmetic (M2's set); (c) plus same-module constant propagation | (b), exactly as M2 implements it, including its exponent, division-by-zero and overflow limits. (c) is a later, separately evaluated extension |
| **Non-numeric or disabled values** (`None`, `0`, `inf`, strings) | (a) `UNEVALUATED` under an upper-bound rule; (b) violation | (a). A disabled deadline is C1, which this rule does not claim; treating it as compliant or as a violation would both overclaim |
| **Path applicability** | ADR-020 `include_paths`/`exclude_paths`, required | Required. This rule has no meaningful global form |

An illustrative shape, **not a proposed spelling**:

```text
- <NUMERIC_BOUND>:
    language: python
    symbol: ROUTER_DEADLINE_S
    call: { function: classify, position: 1, keyword: deadline }
    max: 5
    inclusive: true
    unit: seconds
    include_paths: ["src/**"]
```

## 4. Question 2: `UNEVALUATED` as a distinct outcome

**Problem.** Today the only "could not evaluate" state is path `UNKNOWN`. A
numeric-bound rule adds a second kind: the rule applies to the file, but the
matcher could not decide. That covers a parse failure, an unrecognized
expression, a rebinding, or an unsupported call form. These must never become
`PASS` or `NO_VIOLATION`, and must never be reported as a violation
(ADR-033 §1).

**Per-rule outcome (proposed, M2 semantics).** Each value source is classified
as `WITHIN`, `EXCEEDS` or `UNKNOWN`. The rule outcome is then:

1. Any `EXCEEDS`: **violation**, even if other sources are `UNKNOWN`. A
   recognized violation is never hidden by an unknown source.
2. Otherwise, any `UNKNOWN`: **unevaluated**.
3. Otherwise: **no violation**.

**How unevaluated surfaces** (option U1 is recommended):

| Option | CLI | Hook / SDK gate | Risk |
|---|---|---|---|
| **U1:** reuse `evaluation_complete=false` with a new, non-path reason kind (for example `MATCHER_UNEVALUATED`) in the per-rule trace | `INCOMPLETE`, exit 2 in both modes (as today) | Fails open with a diagnostic by default; refuses only under ADR-033 authorized closed availability | Low: reuses the existing contract. The reason must not be path-worded |
| **U2:** a new per-rule outcome field plus a new verdict value | New `mneme.check` schema version | Every consumer, including the trust checks (`hook.py:343-418`), must change | High: schema break |
| **U3:** report unevaluated as WARN | WARN | Defers or denies | **Rejected:** it reports unknown as a violation, which ADR-033 §1 forbids |

**Four states that must stay distinct:**

| State | Meaning | Where it lives today |
|---|---|---|
| `NO_VIOLATION` / PASS | Every value source recognized and within the bound | Verdict `PASS` |
| Violation | At least one recognized source exceeds the bound | `FAIL` with a typed violation |
| **Unevaluated** (new reason kind) | The rule applies, but the matcher could not decide | `evaluation_complete=false` (U1) |
| **Operational failure** | The check did not run, crashed, timed out, or returned an untrusted or inconsistent payload | Unchanged: the existing trust checks and ADR-033 availability routing (`hook.py:636-681`; `availability.py`) |

Operational failure is **not** a rule outcome. It must not be relabelled as
unevaluated or as PASS. This proposal does not change its handling.

**What each surface can safely report under U1:**

| Surface | Unevaluated | Violation |
|---|---|---|
| CLI `--mode strict` | `INCOMPLETE`, exit 2 | `FAIL`, exit 2 |
| CLI `--mode warn` | `INCOMPLETE`, exit 2 (incompleteness is exit 2 in both modes today, `cli.py:519-520`) | Reported, exit 0 |
| Claude Code hook | Proceeds with a diagnostic, by default (ADR-033 §3); refuses only under authorized closed availability, which no shipped verifier grants today | Strict: deny. Warn: defer |
| Agent SDK and LangChain middleware | `fail_open`: the tool runs with `[mneme] UNEVALUATED` (`integrations/agent_sdk/adapter.py:217-246`). There is no ADR-033 routing on this path | Strict: `DENIED`, handler not run. Warn: `WARN` |

None of these surfaces turns unevaluated into compliance. This proposal does
not invent any fail-closed behavior.

**Mixed case: a recognized violation plus an unknown source.** Under U1, the
payload has a FAIL violation **and** `evaluation_complete=false`. Today the
hook fails open whenever evaluation is incomplete, even when violations are
present (`hook.py:684-686`; C2a charter §2). The gate would therefore **let
through an edit with a recognized violation** whenever another source in the
same file is unknown. The owner must choose:

- **M-a (recommended):** a recognized violation is decided on its own. If the
  violation's evidence is complete for that rule, deny in strict mode;
  unevaluated status from other rules or sources does not cancel it.
  Requires a hook change, which is a behavioral charter item.
- **M-b:** keep today's fail-open on any incompleteness, and document that a
  numeric-bound violation can pass the gate in mixed files.

## 5. Question 3: the introduced-delta gate vs the whole-file audit

**Constraint.** ADR-018 passes only the introduced lines to the checker.
Introduced lines are generally not parseable Python, and a bound's value can
live on an untouched line. In P0-A, the runner evaluated the whole resulting
file and kept a gate violation only if its evidence touched an introduced
line. The shipped hook cannot do that today.

| Option | What the gate evaluates | Contract change | What it can claim |
|---|---|---|---|
| **G1:** audit only | Nothing at the gate; `mneme check --input <whole file>` and CI | None | Standing compliance after mutation. No pre-write claim |
| **G2:** whole file, attributed to the delta | The materialized resulting file, plus introduced line ranges. A violation counts only if its evidence lines intersect the delta | New checker input (resulting file plus delta ranges) and hook changes; ADR-018 amendment or an explicit per-type exception | Pre-write detection when the violating value is on an introduced line (T-like) |
| **G3:** whole file, unattributed | The materialized resulting file | Hook change; diverges from ADR-018 §1 | Blocks edits that touch a file with a pre-existing violation (breaks ADR-018's intent) |

**Recommendation: G1 first. G2 only after it is separately chartered and
evaluated.** In either case, the evidence states plainly that:

- **T is one gate instance.** It is not evidence of general pre-write
  protection.
- **Deletion-only edits** (the U shape) introduce nothing and are skipped by
  the gate (`hook.py:1169-1173`). This rule cannot change that.
- **Context dependencies** (a value set on an untouched line, or a call
  through an alias) are visible only to the whole-file audit, or are
  `UNEVALUATED`.

## 6. Question 4: compatibility with ADR-019, 020, 029, 030 and 031

| Contract | Requirement | Proposed handling (options for the owner) |
|---|---|---|
| ADR-019 §1, §9 | A new, separately specified type; `FORBID_LITERAL` unchanged; unknown types and blank values invalid | A new kind with its own strict structured grammar; no change to `FORBID_LITERAL` parsing or matching |
| ADR-019 §5 | A match is a deterministic FAIL, with the rule type in diagnostics | Same, with the source line, the folded value and the bound in the trigger text |
| ADR-019 §6 | Only canonical policy sources are exempt | Reuse the type-independent exemption (`path_selectors.py:184-226`) |
| ADR-020 §9, §11 | Allowed keys enumerated per rule type; applicability adds no matcher semantics | Enumerate this type's keys; Python-awareness lives in the matcher, not in applicability |
| ADR-030 §7, §8 | `rule_id` hashes `[value, applicability]`; changed semantics need a new id | **P1:** keep `value: str` as a canonical serialized contract (sorted-key JSON of the authored fields), so the existing `rule_id` algorithm, loader and join keys are unchanged. **P2:** a structured `rule_payload` under a new v2 `semantic_feature`, with the identity hash extended to cover it. Recommendation: P1 for the first slice (no change to the identity algorithm), with golden vectors |
| ADR-031 §8 | New persisted semantics need v2, closed key sets and a declared `semantic_features` entry | Under P1 the payload key set is unchanged, but the rule type is new. Declare a `semantic_features` entry so older readers fail closed rather than misread it. Owner decision |
| ADR-031 §10, ADR-029 §2-3 | One `rule_id` algorithm; extend the existing trace; APPLIED, EXCLUDED and UNKNOWN never collapse | Extend `RuleEvaluation` with a matcher-status reason (U1). Add a per-rule outcome and the subject digest (ADR-029 dimensions 2 and 6), which are missing for all rule types today, as part of the same charter or a prerequisite |
| Conflict behavior | The conflict detector skips non-literal types (`conflict_detector.py:142`) | Decide explicitly: either the numeric-bound type is enforcement-only (no response-conflict semantics) and the skip is documented, or it gets an equivalent evaluation. Recommendation: enforcement-only |
| Hook rename join | `violation.rule` must equal `applicability.rule_value` (`hook.py:830-841, 906-909`) | Under P1 both carry the same canonical string |
| Other literal-only sites | Protection activation, preservation, governability, readiness guardrails, MCP and EventCatalog | Enumerate each one in the charter and decide either "literal only, documented" or "extended" |
| Backward compatibility | Existing memory loads unchanged; `FORBID_LITERAL` ids and payloads are byte-stable | Golden vectors for existing ids; old readers given a new-type memory must fail closed, never drop the rule |

## 7. Question 5: independent evaluation before any enforcement claim

P0-A's set was visible to the detector author. Before any claim beyond
"bounded offline capability", a **held-out** evaluation is needed:

1. **Independence.**
   - A separate session authors and freezes the corpus and its labels **before**
     the matcher implementation exists, and the corpus is not shown to the
     matcher's author until scoring.
   - Labels are source-adjudicated against each decision's text, as in P0-A
     §5.1.
2. **Breadth.**
   - Several decision shapes with the same contract: timeouts, retry counts,
     pool sizes, rate limits, batch sizes.
   - Both value sources and both argument forms (positional and keyword).
   - Edit cases with before/after snapshots for gate scoring, including
     deletion-only edits and violations whose value is on an untouched line.
   - Benign look-alikes: other symbols, other functions, comments, strings,
     test files outside `include_paths`.
   - Unsupported forms (aliases, attribute calls, propagation) that must be
     `UNEVALUATED`.
3. **Metrics,** reported separately per question (audit and gate):
   - violation catch rate and misses;
   - false blocks on benign cases;
   - `UNEVALUATED` on violations and on benign cases;
   - parse failures.
   Plus two clean byte-identical runs.
4. **Pre-registered criteria,** set by the owner before scoring:
   - **zero** false blocks and **zero** misses within the declared recognition
     scope;
   - every out-of-scope form returns `UNEVALUATED`;
   - a reported (not hidden) `UNEVALUATED` rate, with any ceiling the owner
     sets.
   Failure on any criterion means the type is not proposed for enforcement.
5. **Supported language scope:** Python, on the `ast` grammar of the pinned
   runtime. Syntax newer than that grammar parses as a failure and returns
   `UNEVALUATED`.
6. **Gate scoring** is done only under the gate option the owner chose
   (section 5), and never as a general pre-write claim.

## 8. Proposed sequence (each step needs its own authorization)

1. **This proposal:** the owner decides the options in sections 3 to 7.
2. **Held-out corpus freeze,** by an independent session (section 7), before
   any matcher exists.
3. **Formal ADR** for the rule type in `docs/adr/`, recording the chosen
   contract, outcome semantics, persistence option and gate option.
4. **Layer 1 behavioral charter** and `[layer1-freeze]` amendment (Amendment
   Procedure §4), covering the enforcement-input change, the hook and SDK
   behavior, the literal-only sites, and the regression matrix.
5. **Implementation** behind that charter, with the
   "no `VALID_RULE_TYPES` entry without a matcher" invariant (section 2).
6. **Scoring** against the frozen held-out corpus, then the owner decides on
   any enforcement claim.

## 9. Owner decisions requested

| ID | Decision | Recommendation |
|---|---|---|
| N1 | Rule contract elements (section 3) | As recommended in the section 3 table; spelling deferred to the ADR |
| N2 | How unevaluated surfaces (section 4) | U1 (`evaluation_complete=false` with a non-path matcher reason) |
| N3 | Mixed recognized violation plus unknown source at the gate | M-a (a recognized violation stands); behavioral charter item |
| N4 | Gate option (section 5) | G1 (audit only) first; G2 only after a separate charter |
| N5 | Persistence and identity (section 6) | P1 (canonical string `value`, existing `rule_id` algorithm) plus a declared `semantic_features` entry |
| N6 | Conflict detector | Enforcement-only, with the skip documented |
| N7 | Evidence gaps (subject digest, per-rule outcome) | Close them in the same charter as a prerequisite to any claim |
| N8 | Held-out evaluation and its pre-registered criteria (section 7) | Required before the ADR is accepted |

## 10. Non-goals

- Implementing, accepting or activating any rule.
- Editing `docs/adr/`, the Layer 1 freeze, `mneme/`, `.mneme/`, CI or the
  benchmarks.
- C1, C3, M1, or a general semantic engine.
- Languages other than Python.
- P0-B.
