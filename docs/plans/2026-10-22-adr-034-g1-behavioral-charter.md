# ADR-034 / G1: Layer 1 behavioral charter (whole-file numeric audit)

**Date:** 2026-10-22
**Status:** **ACCEPTED** by the owner on 2026-10-22, after two architecture
reviews:

- first review: ACCEPT WITH REQUIRED FIXES (F1–F3);
- second review: ACCEPT, with one clarification, which is incorporated in §7.

Accepting this charter authorizes **no implementation**. Implementation
requires the separate, reviewed `[layer1-freeze]` amendment described in §9.

**Repository baseline examined:** `MnemeHQ/mneme` `main` at
`e299874201f4a84e06df2188e04e4152a3ceee87`.

**Normative anchors:**

- accepted [ADR-034](../adr/ADR-034-static-numeric-upper-bound-typed-rule.md),
  blob `6f4ea66d79ce3964d8cfd4b6a2d8e6f0ae2d86e9`;
- frozen [evaluation criteria](2026-10-21-adr-034-pre-registered-evaluation-criteria.md),
  blob `7ca1f39ed468df37a2290bfe54f0bf771d11341d`;
- the frozen corpus commitment
  [`docs/validation/adr-034-heldout-corpus-freeze-2026-10-22.md`](../validation/adr-034-heldout-corpus-freeze-2026-10-22.md)
  (merge `e2998742`);
- ADR-017, 018, 019, 020, 023, 029, 030, 031 and 033;
- [`docs/architecture/layer1-freeze-e73ff7d.md`](../architecture/layer1-freeze-e73ff7d.md).

## 1. Purpose and scope

Implement one new deterministic typed rule, `FORBID_NUMERIC_ABOVE`, for
whole-file Python audit (G1) through the existing check and enforcement
pipeline. It must:

- distinguish a violation, a proved absence of violation, and an unevaluated
  result;
- preserve existing `FORBID_LITERAL` behavior;
- bind each claimed result to the exact checked bytes and the active decision
  and rule.

**Not part of this slice:**

- pre-write numeric enforcement (G2) and any CI gate;
- new availability policy, decision applicability or retrieval authority;
- any change to `DecisionRetriever` ranking or `ConflictDetector`
  response-text semantics;
- MCP enforcement;
- new numeric forms or other languages;
- memory import of ADR-034 itself;
- P0-B;
- any inspection of the corpus by the matcher author.

There is no production claim until independent held-out scoring passes.

**Layer 1 boundary:** the feature changes typed-rule enforcement behavior and
JSON evidence. Accepting this charter is not a Layer 1 freeze amendment.
Before implementation, obtain the explicit, reviewed `[layer1-freeze]`
amendment required by the freeze document's Amendment Procedure, referencing
this charter. No retroactive amendment.

## 2. Verified shipped baseline and hazards

| Existing surface | Verified at `e2998742` | Necessary change / boundary |
|---|---|---|
| Rule model / importer | `schemas.py` has `RuleType = Literal["FORBID_LITERAL"]`; `adr_constraints.py`, `adr_compiler.py` and `decision_index.py` compile literal rules only | Admit the numeric type only together with its parser, validator, matcher and consumer handling, in one delivery. Never create a silent APPLIED/PASS |
| Persistence / identity | The `decision_index_persistence.py` v2 `semantic_features` supported set does not include `numeric_upper_bound_rule`; the canonical rule payload is `{"value": ...}`; `rule_id_for` exists | Extend with an explicit v2 feature. Preserve the canonical `Rule.value` / `rule_id` algorithm and all old IDs. Old readers reject the feature |
| Enforcement | `enforcer.py:197–270` evaluates typed literals; `EnforcementResult.evaluation_complete` sees only path `UNKNOWN` | Add numeric rule records, per-rule matcher status and reasons. Derive aggregate completeness from both dimensions |
| CLI | `mneme check --input ... [--target-path ...]` reads input text; `mneme.check/v1` at `cli.py:367–426`; exit 2 on incompleteness | Add an explicit, safe whole-file transport. Keep legacy input semantics. Give reasoned incomplete output |
| Hook | `claude_code/hook.py:365–378` rejects non-path incompleteness; `:684–686` proceeds even on FAIL plus incomplete | Recognize matcher incompleteness. Keep trusted violations actionable even when unrelated numeric checks are unknown |
| Other consumers | The Agent SDK and LangChain consume check observations in their own adapters | Align validator and result classification for the new optional matcher fields. Claim no gate coverage for numeric rules |
| Corpus | v1 sealed, 155 cases; the author and orchestrating transcripts are restricted | The matcher implementer must not access the corpus or answer key. Scoring happens only after the implementation is frozen |

**`ConflictDetector`** continues to evaluate response text as before. It must
report numeric-rule noncoverage explicitly in `ConflictDetectionResult`, or
reject a legacy bare-list result as incomplete. An empty conflict list must
never be presented as a complete numeric check (ADR-034 §9).

**`DecisionRetriever`** is unchanged. Numeric typed-rule evaluation, like
typed-literal evaluation, is not limited by top-K relevance (ADR-017).

## 3. Input and invocation contract (G1 only)

```text
mneme check --memory .mneme/project_memory.json \
  --source-file src/router.py \
  --query "audit router" --mode strict --json
```

1. **Mutually exclusive inputs.** `--source-file` is an alternative to the
   existing `--input`; the two are mutually exclusive. It cannot be combined
   with `--target-path`, and there is no `--project-root` argument. Legacy
   `--input`, `--target-path`, JSON, modes and default behavior are unchanged
   for existing rule sets.
2. **One root.** The only root for this audit is the existing ADR-020 policy
   root, `path_selectors.policy_root(memory_path)`, derived from the memory
   file actually loaded.
   - Resolve `--source-file` to a real, regular `.py` file within that root.
   - Use the existing `normalize_input_path(source_file, memory_path)` for the
     policy-root-relative applicability path.
   - Reject nonexistent files, directories, out-of-root paths and source
     symlinks (a conservative first-slice restriction).
   - Never fall back to a caller-declared alternate root, and never trust
     `--target-path` as evidence of source identity.
3. **One snapshot.** Read the resolved file's bytes once, decode them as
   strict UTF-8, hash those exact bytes with SHA-256, and evaluate that same
   snapshot.
   - Bind the resolved path, the loaded memory path, the normalized
     applicability path and the digest in the audit record.
   - Never import or execute the source.
   - The existing ADR-020 selector evaluator must use exactly the same
     normalized governed path. A mismatch is an operational error, never a
     guessed APPLIED or EXCLUDED.
4. **Anything else is not complete source.** A caller-supplied `--input` file,
   a materialized delta, a prompt, stdin, or input with only a claimed
   `--target-path` is not verified complete source. For an APPLIED numeric
   rule it yields `MATCHER_UNEVALUATED` / `INCOMPLETE_SOURCE_INPUT`. That is
   decided before any AST parsing, even if the text happens to parse.
5. **Failures.**
   - A `--source-file` request that cannot be safely read or bound
     (including a path, encoding or I/O mismatch) is an operational error,
     never PASS.
   - A readable complete file that fails the pinned CPython 3.12.10 grammar
     yields `MATCHER_UNEVALUATED` / `PARSE_FAILURE`.
   - This feature does not independently authenticate the chosen memory
     source. Do not change `MNEME_MEMORY` precedence, DG1 resolution or
     memory discovery.
6. **What the digest means.** A subject digest identifies the checked byte
   snapshot. It is not a promise that the live file stayed unchanged
   afterwards; TOCTOU is outside this slice.

**Review disposition I1: ACCEPTED, with F1.** `--source-file` provides the
complete-source transport, and the existing `policy_root(memory)` defines its
one valid project boundary. No second root is introduced.

## 4. Numeric rule authoring, persistence and identity

- **Contract.** Implement exactly ADR-034 §2–§5a:
  - Python only;
  - `symbol` and/or a direct bare-name `call.function` with a zero-based
    `position`;
  - a positive, inclusive `max`;
  - a documented `unit`, never converted;
  - required ADR-020 `include_paths`, and optional `exclude_paths`.

  Reject unknown or duplicate keys and invalid rule structure.
- **`max` handling.**
  - Validate the raw, plain YAML scalar text of `max` against ADR-034's
    grammar before YAML coercion.
  - Canonicalize it as strict decimal text, never as a float.
  - Store a canonical JSON string in `Rule.value`: sorted object keys,
    version `v=1`, `max` as a string, no unapproved defaults.
  - Revalidate strictly at load. Never rewrite persisted malformed data.
- **Identity.** Preserve the P1 identity
  `<decision>:FORBID_NUMERIC_ABOVE:sha256([value, applicability])[:32]`.
  Existing literal-rule identities stay byte-stable. Verify ADR-034's four
  golden vectors.
- **Persistence.**
  - Persist the new rule only under `mneme.decision-index/v2`, with
    `semantic_features` containing `numeric_upper_bound_rule`.
  - Reject it in v1.
  - Old binaries must reject the new feature, never silently skip it.
  - Refuse downgrade.
  - There is no silent fallback to P2: a P1 failure returns to architectural
    review.
- **Atomic availability.** Update the rule schema, the authoring compiler and
  its mirror, persistence, the matcher, and the audit payload and consumer
  validators together, before any writable or accepted memory can contain the
  new type. An installation missing any required part must reject unsupported
  persisted rules, never PASS.

## 5. Deterministic matcher semantics

For an APPLIED rule and trusted complete source, parse with the pinned grammar
and never execute code.

Source discovery covers:

- the single module-level symbol assignment, when declared;
- every direct bare-name call site in the whole module AST, including nested
  function and method bodies, subject to the accepted shadowing rule.

When both are declared, symbol and call are independent sources.

- **Recognized forms only:**
  - numeric literal expressions, unary `+`/`-`, and binary
    `+ - * / // % **`;
  - the exponent must have runtime `int` type and magnitude ≤ 64.

  Do not resolve derived constants, aliases, keyword-passed governed values,
  attribute calls, units, ranges or conversions.
- **Evaluation.**
  - Evaluate literal arithmetic with pinned CPython `int`/binary64 numeric and
    `operator` semantics.
  - Each of these is `UNKNOWN` / `UNRECOGNIZED_FORM`:
    - `bool`;
    - disabled values (`x <= 0`);
    - non-finite values;
    - division by zero and overflow;
    - any intermediate or final `int` with magnitude above 10^30.
- **Comparison.** Compare the computed runtime value `x` exactly with the
  decimal-authored `max`: a violation is `Fraction(x) > Fraction(max)`. There
  is no tolerance and no rounding of the bound. Diagnostics for non-dyadic
  limits must explain the strict comparison, for example that source `0.1`
  can violate `max: 0.1`.
- **Required sources.** Every declared source is required. An absent,
  ambiguously bound, unknown-expression or missing positional source must
  never become a compliant PASS. Implement all 17 confirmed interpretations
  from the public, metadata-only corpus freeze record, never by viewing hidden
  cases.
- **Reason priority:** `INCOMPLETE_SOURCE_INPUT` > `PARSE_FAILURE` >
  `AMBIGUOUS_BINDING` > `SOURCE_NOT_FOUND` > `UNRECOGNIZED_FORM`.

## 6. Result, evidence and consumer contract

There are three independent dimensions:

1. ADR-020 path applicability: `APPLIED` | `EXCLUDED` | `UNKNOWN`;
2. numeric matcher status: `RECOGNIZED` | `PARTIAL` | `MATCHER_UNEVALUATED`;
3. operational trust and availability, which is unchanged.

An EXCLUDED numeric rule produces an applicability trace and no matching
claim. It is not a matcher failure.

| Sources for an applied numeric rule | Per-rule outcome | Matcher status | Complete? |
|---|---|---|---|
| Any `EXCEEDS`, no unknown | violation (FAIL) | `RECOGNIZED` | Yes |
| Any `EXCEEDS`, plus unknown | violation (FAIL) | `PARTIAL`, with all unknown reasons | No |
| No `EXCEEDS`, any unknown | unevaluated | `MATCHER_UNEVALUATED`, with reasons | No |
| All sources known and `WITHIN` | no violation | `RECOGNIZED` | Yes |

**Additive `mneme.check/v1` representation (review R1: ACCEPTED).**

- Keep all existing `applicability[]` and `violations[]` fields and the
  existing rule-string join.
- On each applicable numeric rule's trace, add:
  - `matcher_status`;
  - `matcher_outcome` (`VIOLATION` | `NO_VIOLATION` | `UNEVALUATED`);
  - `primary_reason` (nullable);
  - `unknown_sources`, a list of `{kind, line, reason}`, with a deterministic
    position or occurrence discriminator only if needed;
  - `subject_sha256`.

  `rule_id` and `decision_version_id` stay present.
- Add a top-level check subject record, holding `subject_sha256` and the
  source input kind, for audit.
- A recognized violation includes the source line, the exact computed value,
  the authored `max`, the unit, and the strict-comparison explanation.
- Existing fields and existing literal payloads stay stable.

**Completeness and consumers:**

- **`evaluation_complete` is derived.** It is false if and only if an
  applicable rule has matcher status `PARTIAL` or `MATCHER_UNEVALUATED`, or
  any rule has path `UNKNOWN`. Otherwise it is true.
  - All consumers verify it against the per-rule records.
  - For a numeric APPLIED trace, missing or invalid matcher fields must never
    be read as complete or trusted.
  - A legacy payload with no numeric records keeps its existing compatibility
    semantics.
- **Mixed-result precedence (M-a).** A trusted, correctly bound known
  violation stays actionable even alongside unrelated unevaluated records.
  - **Strict mode:** FAIL with `evaluation_complete=false` and CLI exit 2 is
    valid when the per-rule evidence proves the mixed result.
  - **No proved violation:** if there is any applicable uncertainty, report
    INCOMPLETE with exit 2, never PASS.
  - **`--mode warn`:** for a known violation mixed with incompleteness, keep
    the existing incomplete-exit convention (exit 2), with `verdict=FAIL` and
    an explicit `evaluation_complete=false`. Warn-mode consumers emit a
    non-blocking warning.
  - Process exit 2 alone is never a policy violation.
- **Consumer trust.** Revise the Claude Code hook and the Agent SDK's shared
  verdict logic (which LangChain uses) to accept correctly explained matcher
  incompleteness and reject contradictory aggregates. Preserve
  schema/mode/exit/violation coherence and historical payload compatibility.
  - **The Agent SDK fix is a real behavioral change:** today it fails open
    whenever `evaluation_complete=false`, even with a proved FAIL.
  - **At the gate,** delta input means numeric is always unevaluated. An
    existing trusted `FORBID_LITERAL` strict violation must still block under
    the default availability-open policy, even when numeric adds incomplete
    status.
  - **With only uncertainty,** the default availability-open policy still
    fails open, with a visible diagnostic.
  - Do not change availability defaults.
- **F2: closed availability is explicitly incompatible.** On the edit gate, a
  numeric rule applicable to the modified path yields `MATCHER_UNEVALUATED` /
  `INCOMPLETE_SOURCE_INPUT`, because the gate provides only delta input, so
  `evaluation_complete=false`.
  - **The consequence:** with an authorized closed availability declaration
    (ADR-033/C2b), the existing `availability.py` routing refuses that
    otherwise ordinary governed edit as `EVALUATION_INCOMPLETE`.
  - **There is no first-slice exception.** Do not reinterpret `UNKNOWN`, skip
    the numeric rule, or weaken an authorized closed policy just to allow
    edits.
  - **Scope:** this applies to supported, nonempty edit events on APPLIED
    numeric paths. Excluded and provably empty events keep their existing
    skip behavior.
  - **Mixed with a literal violation:** if a trusted literal violation is also
    detected, keep its violation evidence, and never mislabel the
    availability refusal as a numeric violation.
- **G1 operating guidance.** Do not activate `FORBID_NUMERIC_ABOVE` on paths in
  repositories that use authorized closed availability, until a separately
  approved G2 edit-gate evaluation can establish completeness.
  - Before activation, check the repository's approved availability posture.
  - If it is closed, decline numeric-rule activation, or require the owner to
    remove the closed policy explicitly through its existing authorized
    process.
  - This is operational guidance, not a new policy selector or silent runtime
    exception.
- **Scope of consumer changes.** Consumer behavior changes are strictly:
  - result transport;
  - faithful precedence between unknown results and known violations;
  - regression preservation.

  They do not enable numeric enforcement at the pre-write gate. Any consumer
  beyond the three named must be characterized as noncoverage, or updated
  before any broader claim.
- **ADR-029 binding.** Record, in the same evaluation:
  - the evaluation surface and version;
  - the digest of the subject actually checked;
  - decision, version and rule identity;
  - applicability;
  - matcher status and reasons;
  - the attributable outcome.

  Without every binding, no claim of "relevant enforcement observed" may be
  made. Do not create a new evidence database or alter Audit tiers.

**Review disposition R1: ACCEPTED.** Keep the additive `mneme.check/v1`.
Older readers reject the new persisted `numeric_upper_bound_rule` semantic
feature, so they can never load the numeric memory that emits these records.
**Mandatory regression:** checks with no numeric rules produce byte-identical
JSON before and after the change, including ordering, optional fields and
exit codes. No existing v1 consumer may silently reinterpret current payloads.

## 7. Adjacent surfaces: explicit dispositions

| Surface | First-slice disposition |
|---|---|
| `protection.py` activation and automated proposal generation | Literal-only. Must not propose or activate numeric rules through legacy literal workflows. Manual, validated ADR rule compilation is separate |
| `cli.py` preservation path | Preserve existing typed rules losslessly. Reject unsupported canonical numeric rules rather than dropping or misrepresenting them. No numeric preservation heuristics |
| `enforcer.assess_governability`, protection readiness / Audit | Literal-only scoring until dedicated, validated G1 audit coverage semantics exist. A configured numeric rule does not automatically count as pre-write Protected. Show noncoverage instead of an inflated protection score |
| `decision_governance.py` evidence identity | Extend only as needed for exact canonical numeric rule identity and version binding. No new resolver or waiver policy |
| MCP / EventCatalog serializers | Round-trip the canonical typed rule, or report explicit unsupported/noncoverage. No silent omission, invented PASS, or claim of numeric blocking. No new MCP surface |
| `ConflictDetector` | See F3 below |
| CI and non-Claude hooks | No numeric enforcement claim. Any unrelated consumer that interprets completeness must be assessed for regression before release |

**F3: `ConflictDetector`.** Response-text matching is unchanged, and
noncoverage is reported explicitly.

- **`evaluate()`:** in `ConflictDetector.evaluate`, add an additive
  `ConflictDetectionResult.noncoverage` trace. It identifies every encountered
  `FORBID_NUMERIC_ABOVE` rule by decision, version and rule ID, with reason
  `NOT_EVALUATED_ON_RESPONSE_TEXT`. No numeric matching is performed.
- **`detect()`:** the legacy list-only `detect()` API cannot carry notes. For
  a decision set containing numeric rules, it must raise a dedicated
  noncoverage exception or diagnostic, never return an apparently complete
  empty list.
- **Unchanged behavior:** decision sets with no numeric rules keep
  byte-identical and behavior-identical results. Callers that display conflict
  results must show the noncoverage note. Neither an absence of conflicts nor
  applicability completeness implies numeric coverage.
- **Completeness is unaffected.** Numeric-rule noncoverage is reported but
  does not make `ConflictDetectionResult.evaluation_complete` false. The
  pipeline propagates the noncoverage note through `PipelineResult`, without
  treating it as a successful numeric evaluation.

## 8. Acceptance tests and sequencing

**A. Pre-implementation review.** Completed: two architecture reviews, with
F1–F3 and the §7 clarification resolved, and accepted by the owner. The owner
must still approve the separate `[layer1-freeze]` amendment. No reviewer who
may implement the matcher gets corpus access.

**B. Implementation, only after the amendment is approved.**

- **Scope:** parser, canonical persistence, matcher, status and evidence, CLI
  audit transport, consumer trust adaptation, and conflict noncoverage.
- **Delivery:** either one reviewable, bounded change, or a series that
  cannot enable the new rule until it is ready end to end, atomically.
- Keep existing tests green.
- **Isolation:** implement in a new, isolated session with no access to the
  corpus-author or orchestrating sessions or their transcripts, the encrypted
  case archive, or the answer key.

**C. Regression matrix, before unblinding:**

1. **Authoring and persistence:** authoring grammar and rejection; canonical
   JSON bytes; round trip through parse, compile, persist, load and project;
   v1 refusal; v2 feature declaration; old-reader refusal; downgrade refusal.
2. **Golden rule IDs:** ADR-034's three numeric vectors plus the existing
   ADR-005 literal vector. No drift in current `FORBID_LITERAL` behavior or in
   retrieval ordering.
3. **Numeric semantics:** CPython 3.12.10 boundary vectors R1–R18, which are
   public, covering float-versus-decimal strictness, non-`int` exponents,
   overflow and no execution. Also parse failures and unsupported inputs and
   their reasons.
4. **Source discovery:**
   - symbol, call, both, and multi-call scope;
   - shadowing and escape;
   - all declared sources, no source, and non-source input;
   - excluded paths and applicability `UNKNOWN`;
   - `PARTIAL` keeps its unknown-source evidence while emitting FAIL.
5. **CLI:**
   - JSON coherence and the exit matrix: strict and warn; complete and
     incomplete; mixed FAIL plus incomplete;
   - readable human diagnostics;
   - deterministic output with stable ordering.

   Existing no-numeric `mneme.check/v1` payloads and their exits stay
   byte-identical before and after. No scoring-protocol normalization
   amendment is authorized.
6. **Hook, Agent SDK and LangChain:**
   - (a) **Open availability:** an existing literal violation still blocks in
     strict mode, even with a numeric `INCOMPLETE_SOURCE_INPUT` on the delta.
     Warn mode stays non-blocking, and an unknown-only result proceeds with a
     visible diagnostic.
   - (b) **Authorized closed declaration:** an ordinary nonempty edit on an
     APPLIED numeric-governed path is refused as `EVALUATION_INCOMPLETE`, even
     with no proved violation. An EXCLUDED or empty event is not blocked by
     the numeric rule alone.
   - (c) **Mixed:** a trusted literal violation together with incompleteness
     keeps both facts, even when closed availability routes first.
   - (d) **Contradictions:** a contradictory payload is untrusted, and
     historical no-numeric payloads stay unchanged.

   No claim of pre-write numeric detection.
7. **Evidence binding:** the subject digest of the same source bytes,
   `rule_id`, decision version, applicability, matcher status and reason, and
   outcome. No "observed enforcement" claim when any binding is incomplete.
8. **F3 conflict noncoverage:**
   - `ConflictDetector.evaluate` reports numeric noncoverage deterministically,
     with correct rule identity, and does not change `evaluation_complete`;
   - the list-only `detect()` path refuses to present such a decision set as
     fully checked;
   - existing literal-only conflict outputs and semantics are unchanged;
   - a strict pipeline run with a numeric rule in memory does not raise for
     noncoverage alone;
   - a caller's "no conflicts" message cannot imply numeric coverage.
9. **Adjacent consumers:**
   - adjacent consumers and reports never treat unsupported numeric rules as
     silently verified or Protected;
   - no unauthorized changes to `DecisionRetriever`, CI, hook registration or
     governance authority;
   - `ConflictDetector` gains only noncoverage reporting, never numeric
     detection.

**D. Independent held-out validation.** Freeze the implementation commit
before a separate, owner-authorized offline scoring run against sealed v1
(155 cases), with the benchmark author and implementer kept separate.

Run the frozen protocol unchanged. It requires:

- zero misses, false blocks, unsafe passes, unexpected U/N violations and
  wrong reasons;
- every U/N case unevaluated, with the correct primary reason;
- A7 reported as `PARTIAL`;
- coverage of 100% for A and at least 95% for W;
- R at 18/18;
- two byte-identical runs;
- 100% evidence binding;
- golden IDs and old-reader refusal.

Report failures honestly. Do not tune against the same revealed holdout and
call the result blind. The frozen protocol gives the full denominators and the
failure policy.

## 9. `[layer1-freeze]` amendment scope (separate PR and review)

After this charter is accepted, a PR titled
`[layer1-freeze] ADR-034 G1 whole-file numeric audit` adds a bounded
authorization to the Layer 1 freeze document.

It **permits** only:

- the specified `FORBID_NUMERIC_ABOVE` first-slice whole-file audit;
- the necessary schema, CLI and result-consumer extensions;
- explicit `ConflictDetector` noncoverage diagnostics.

It **pins** this charter and its regressions.

It **preserves**:

- deterministic retrieval;
- existing typed literals;
- prompt enforcement;
- pre-write coverage limits.

It **states explicitly** that it does not authorize CI, pre-write numeric
denial, agent orchestration, or ADR-033 availability-policy changes.

It **records** that G1 numeric checks cause closed-availability refusal for
nonempty edits on APPLIED paths, and that numeric rules must not be activated
there until a separate G2 authorization.

The freeze amendment is a prerequisite for the behavioral implementation, not
a post-hoc ratification.

## 10. Review history

- **Initial review: ACCEPT WITH REQUIRED FIXES.**
  - F1: two roots → the single ADR-020 policy root.
  - F2: the closed-availability refusal on delta input → stated, tested, and
    covered by activation guidance.
  - F3: the silent `ConflictDetector` skip → explicit noncoverage.

  I1 (`--source-file`) and R1 (additive JSON v1) were accepted.
- **Second review: ACCEPT**, with one clarification: noncoverage does not make
  `ConflictDetectionResult.evaluation_complete` false, and it propagates
  through `PipelineResult`. This is incorporated in §7.
- **Owner acceptance:** 2026-10-22.
