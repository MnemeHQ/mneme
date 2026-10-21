# P0-A: Semantic constraint enforcement — validation charter

**Status:** **DRAFT, revision 3**, for final owner confirmation. Validation only.
The owner resolved D1–D5 in the
[PR #578 review](https://github.com/MnemeHQ/mneme/pull/578#issuecomment-6310714497)
(2026-10-21), and section 10 records those decisions. This revision also
incorporates the four requested wording and measurement corrections, and
revision 3 defines the M3 recognition contract (section 4.1) per the
[revision 2 review](https://github.com/MnemeHQ/mneme/pull/578#issuecomment-6310847609).
Accepting this charter authorizes **no** change to `mneme/`, `docs/adr/`,
`.mneme/`, the benchmark suites, CI, or the Layer 1 freeze document. **No
experiment implementation is authorized** until this charter is approved and
the independently frozen Set 1 commit exists (section 12).
**Source anchor:** `MnemeHQ/mneme` `origin/main` @ `04a1f989`.
**Baseline evidence:** MnemeHQ/mneme#570 (`04a1f989`,
`validation/orchestrator-decision-sandbox/`), measured on the runtime that
includes MnemeHQ/mneme#573 (`cf6bc40b`).
**Governing contracts:** ADR-018 (introduced-delta at the edit gate), ADR-019
(typed literal rule contract), ADR-029 (evidence binding), ADR-031
(decision governance semantics), Layer 1 freeze `e73ff7d` (charter discipline,
benchmark expansion freeze and its 2026-08-24 enforcement-quality exception).
**Sibling track:** P0-B (orchestrator execution governance) is a separate
charter. It is still waiting on a verified orchestrator control point, and
nothing here depends on it.

## 1. Question

Given one accepted decision with three sub-constraints, can a **deterministic,
source-aware** method correctly decide whether a proposed change violates each
sub-constraint, **without** raising false blocks on compliant changes and
**without** reporting PASS for forms it does not understand?

The question concerns the decision. Execution is P0-B's concern. Every method
here is evaluated offline as a pure function from (decision, proposed change)
to a verdict.

## 2. Decision under test

The decision is the synthetic `ADR-001` from #570, unchanged: *"The routing
validator must enforce a five-second maximum deadline and take a safe fallback
path on failure. The timeout must not be explicitly disabled."*

| ID | Sub-constraint | Current enforcement (#570, post-fix) |
|---|---|---|
| C1 | Deadline not disabled | Only the literal `DISABLE_ROUTER_TIMEOUT` under `src/**`, via `FORBID_LITERAL` |
| C2 | Deadline ≤ 5 s | None |
| C3 | Safe fallback on deadline | None |

## 3. Reconciliation with existing contracts (gaps in the Step 1 assessment)

The Step 1 assessment holds against the repository. The points below are
missing from it or understated, and the experiment design depends on them.

1. **The case E false block is contract-correct.** ADR-019 §2 specifies exact,
   case-sensitive matching. §6 gives no general exemption, and §9 says other
   matching semantics require **another explicit rule type** and that
   `FORBID_LITERAL` "must not silently change meaning". So distinguishing code
   from comments or strings is not a fix to `FORBID_LITERAL`. It is a
   candidate for a new rule type, which would need its own ADR and charter.
2. **C1 is broader than the literal.** The #570 oracle treats a `None`, zero,
   negative, infinite, NaN or non-numeric deadline as `C1_DISABLED`. Cases A–F
   contain no C1 violation without the literal. On the evidence, C1's
   protection is literal-only, which is narrower than "partial".
3. **The gate and the audit ask different questions (ADR-018).** The edit gate
   checks introduced lines and the audit checks whole files. A change that only
   **deletes** lines introduces nothing: the hook proceeds when an edit
   introduces no non-blank content (C2a charter §2). Removing a fallback by
   pure deletion is therefore invisible to any introduced-delta gate, whatever
   detector sits behind it. Each candidate method must declare which question
   it answers.
4. **The oracle itself is incomplete.** `oracle.py` checks the module constant
   `ROUTER_DEADLINE_S`, not the deadline actually passed to `classify`. A
   change that keeps `ROUTER_DEADLINE_S = 5.0` but calls
   `classify(request, 60)` passes the oracle while violating C2. The oracle has
   to be corrected and frozen before any method is scored (section 10, D2).
   More generally, a behavioral oracle cannot ground every label: case S
   shows a change that the oracle accepts but that still violates the
   decision's intent. Labels are therefore adjudicated at the source level
   and reported alongside the oracle's runtime observations (section 5.1).
5. **A–F supports one observation per gap.** Tuning methods against A–F alone
   overfits; the freeze's benchmark section calls adding scenarios to push a
   metric overfitting. Extension cases must therefore be authored and frozen
   **before** any method exists (section 5). A precommitted set is still
   visible to the detector author, though. It protects against fixtures being
   changed after the fact, but it is **not** a blind evaluation and does not
   show generalization.
6. **A gate must not execute proposed code.** The oracle runs candidate source
   with `exec`. That is acceptable only for the known, frozen synthetic
   fixtures in this offline experiment; proposed agent content can never be
   executed as gate input. So behavioral evidence for C3
   belongs to a post-mutation boundary (tests or CI), not the pre-execution
   gate.
7. **An unrecognized form must not produce PASS.** A static checker that
   returns PASS for `ROUTER_DEADLINE_S = 5 * 12` or a value derived from
   another constant repeats the defect class fixed in #573: a trusted PASS for
   a subject that was never actually evaluated. Unrecognized forms must yield
   `UNEVALUATED`.
8. **ADR-029 also applies to P0-A.** Step 1 cites evidence binding only for
   P0-B. Every P0-A verdict has to bind to the decision, the rule or method,
   the content digest, and the question asked.
9. **The audit over-claims.** `mneme audit` reports the decision as 100%
   `protected` while measured constraint coverage is 1 of 3. Step 1 leaves this
   out. The experiment records this discrepancy and does not fix it.
10. **The existing vocabulary should be reused.** The enforcement-quality
    regression suite (#318) already defines `violation` / `benign` scenarios
    and `FALSE_POSITIVE`. P0-A uses the same terms but stays **outside** both
    benchmark suites, so no benchmark change is involved.
11. **Claim scope.** One decision shape, Python only, one synthetic file. No
    result here generalizes beyond that without a further experiment.

## 4. Candidate methods

Each method is a prototype that lives only under the experiment directory. None
is wired into `mneme/`, the hook, the middleware or the CLI. M1–M3 may parse
source (`tokenize`, `ast`) but must **never** execute it.

| ID | Method | Targets | Boundary |
|---|---|---|---|
| M0 | Shipped `FORBID_LITERAL` via `mneme check --mode strict --json` (the #570 path) | C1-literal | Gate and audit (baseline) |
| M1 | Lexical-context literal: Python `tokenize`, matching `NAME` tokens only; comments, strings and docstrings excluded | C1-literal, E | Gate (introduced lines) and audit |
| M2 | Static bound: `ast`, module-level assignment to the declared symbol plus the deadline argument at each `classify` call; VIOLATION if not `0 < value ≤ 5` or a disabled form; recognized forms are numeric literals and constant folding of literal arithmetic only; anything else is `UNEVALUATED` | C2, semantic C1 | Audit (whole file); gate result reported separately |
| M3 | Static structural fallback: `ast` analysis of `route` against the frozen simple router template. Its recognized positive, negative and unevaluated forms are defined in section 4.1 | C3 | Audit (whole file) |
| M4 | Behavioral: the oracle's timeout and normal-path probes, run as a project test after the mutation | C3, C2 | Post-mutation (not pre-execution) |

M4 is included only to measure the gap between what the static methods claim
and what behavior shows. Passing M4 never supports a pre-execution claim.

### 4.1 M3 recognition contract

M3 analyzes only the **frozen simple router template**. That template is a
module-level function `route` that calls `classify`, together with a declared
fallback symbol `FALLBACK_ROUTE`, as in the A–F fixtures. The template and
symbol names are frozen in the Set 1 commit. M3 has exactly four outcomes:

| Recognized form | M3 verdict (C3) | Cases |
|---|---|---|
| On the template, the `classify` call has **no enclosing timeout handler** | `VIOLATION` | D; U at the whole-file audit |
| A recognized timeout handler (`except TimeoutError` or a declared superclass such as `Exception`) that **re-raises** instead of returning the fallback | `VIOLATION` | N |
| A recognized timeout handler that **returns `FALLBACK_ROUTE`** | `NO_VIOLATION`, for static structure only | A, P |
| Any other routing or fallback form, including delegation through a helper such as `_fallback()` | `UNEVALUATED` | O |

M3 never infers a violation just because the syntax is unfamiliar. A form
missing from the first three rows is `UNEVALUATED`, never `VIOLATION`. That
includes a handler that returns some other value, a non-timeout exception
type, a `route` that differs from the template, or `classify` reached
indirectly.

`NO_VIOLATION` from M3 means that a recognized fallback **structure** is
present. It does not mean the fallback **behaves** safely, which only M4 can
observe, after the mutation.

**Gate vs audit (ADR-018).** M3 answers the whole-file audit question. A
deletion-only change (U) leaves the template with no handler, so the audit
reports `VIOLATION`. The introduced-delta gate sees no added content for U,
however, so U must never be reported as stopped at the gate.

No method may call a model. Determinism is a requirement, not a metric.

## 5. Case sets

**Set 0 (frozen baseline):** cases A–F from #570, byte-identical. The runner
checks their digests against `validation/orchestrator-decision-sandbox/fixtures/cases.json`
at `04a1f989`.

**Set 1 (precommitted extension):** a separate author or session that does not
write the detectors creates G–U and labels them (D3). The labels are reviewed
against ADR-001. The fixture bytes, the labels, the digests and the oracle
version are then frozen in their **own commit**, before any M1–M3 code exists.
Set 1 is visible, not held out: it guards against fixtures changing after the
fact, and results on it are not evidence of generalization. Proposed initial
set:

| ID | Change | Targets | Expected label |
|---|---|---|---|
| G | `ROUTER_DEADLINE_S = None`, no literal | C1 semantic | violation |
| H | `ROUTER_DEADLINE_S = float("inf")` | C1 semantic | violation |
| I | `ROUTER_DEADLINE_S = 5 * 12` | C2 folded | violation |
| J | `ROUTER_DEADLINE_MS = 60000`; `ROUTER_DEADLINE_S = ROUTER_DEADLINE_MS / 1000` | C2 indirect | violation (M2 expected `UNEVALUATED`) |
| K | Constant kept at 5.0; `classify(request, 60)` at the call site | C2 call-site override | violation (needs D2) |
| L | `ROUTER_DEADLINE_S = 2.5` | C2 benign | benign |
| M | `ROUTER_DEADLINE_S = 5` (boundary) and `5.0001` (paired) | C2 boundary | benign / violation |
| N | `except TimeoutError: raise` | C3 | violation |
| O | Fallback returned through a helper `_fallback()` | C3 benign, unusual shape | benign (M3 expected `UNEVALUATED`, not VIOLATION) |
| P | `except Exception: return FALLBACK_ROUTE` | C3 benign, broad catch | benign |
| Q | Longer identifier `DISABLE_ROUTER_TIMEOUT_DOCS` | ADR-019 §3 boundary | benign |
| R | Literal only in a docstring and an f-string | C1 false-block variant | benign |
| S | `os.environ.get("DISABLE_ROUTER_TIMEOUT")` controls the deadline | C1 via a configuration switch | **violation** (D4, owner-adjudicated). Runtime observation: the oracle ACCEPTs with the variable unset; an enabled-switch probe is required (section 5.1) |
| T | Edit: the single line `5.0` → `60.0` | C2 via introduced delta | violation |
| U | Edit: deletion-only removal of the `except` block | C3 via deletion | violation (gate structurally blind, audit only) |

Set 1 should hold roughly equal numbers of benign and violation cases. A case
added after methods exist goes into a separate, clearly marked **post-hoc** set
that never counts toward the section 7 criteria.

### 5.1 Labels and oracle observations

Each case carries two separate records. Neither is quietly merged into the
other.

- **Architectural label** (`violation` or `benign`, per sub-constraint): the
  ground truth for scoring. It is adjudicated at the source level against
  ADR-001's text and reviewed before the freeze. Where the owner adjudicated a
  label (S), the rationale is recorded with the fixture.
- **Oracle runtime observations:** what the corrected oracle observed when it
  executed the frozen fixture. For example: the deadline actually supplied to
  `classify`, the result on the timeout path, and the result on the normal
  path. These are observations under stated conditions, not labels.

Wherever the two disagree, both are reported, together with the reason. For
S, the oracle runs twice: once with the variable unset, where ACCEPT is
expected, and once with the switch enabled, where it is expected to find
`C1_DISABLED`. If the enabled-switch probe cannot be evaluated, the fixture
documents why, and the label still stands.

**Corrected oracle (D2).** This is a new, versioned synthetic oracle. The #570
`oracle.py` stays byte-identical as historical evidence. The new oracle
records the deadline actually passed to `classify`, including call-site
overrides (K), as well as the module constant. Its semantics and version are
frozen in the Set 1 commit, before any scoring. It executes only the known,
frozen synthetic fixtures.

## 6. Verdicts and scoring

Each (method, case, question) triple yields exactly one verdict:
`VIOLATION`, `NO_VIOLATION` or `UNEVALUATED`. Each verdict is compared with the
architectural label (section 5.1). Where the oracle observation disagrees with
the label, it is reported next to the verdict:

| Label \ Method | VIOLATION | NO_VIOLATION | UNEVALUATED |
|---|---|---|---|
| violation | caught | **missed** (false negative) | unevaluated violation |
| benign | **false block** (`FALSE_POSITIVE`) | correct allow | unevaluated benign |

Reported per sub-constraint, per method, per question (gate vs audit):

- Violation catch rate, miss count, and unevaluated count. `UNEVALUATED` is a
  separate metric, always reported, and never folded into either PASS or
  block.
- Label and oracle disagreements, listed per case.
- False-block count on benign cases.
- Determinism: two clean runs, byte-identical summaries.
- Evidence binding (ADR-029): each verdict records the decision ID, the rule or
  method ID, the case content digest, the question, and the runtime anchor.
- Audit truthfulness: what `mneme audit` reports for the decision, alongside
  measured coverage.

## 7. What counts as sufficient semantic proof

This section answers the prerequisite left open in Step 1.

**Detection capability is not enforcement.** M1–M3 are offline detectors that
are not connected to any mutation gate. Passing this experiment shows
**detector capability in an offline experiment**. It does not show that Mneme
enforces C1, C2 or C3, and no result may be described as shipped enforcement.
Turning a detector into enforcement requires its own ADR (a new rule type,
per ADR-019 §9), a Layer 1 behavioral charter, and integration evidence under
ADR-029.

A method may be described as **having demonstrated offline detection
capability for Cn, on this decision shape and within its declared recognition
scope** only if, across Set 0 and Set 1:

1. It misses **zero** violations of Cn, scored against the architectural
   labels (section 5.1).
2. It raises **zero** false blocks on benign cases.
3. Every form outside its declared recognition scope returns `UNEVALUATED`,
   never `NO_VIOLATION`.
4. It is deterministic and never executes proposed content.
5. Its verdicts meet the binding in section 6.
6. The claim names its scope: decision shape, language, recognized forms, and
   question (gate or audit).

A method that fails any of these is reported as **partial**, with its misses,
false blocks and unevaluated forms listed. A method that meets them on the
audit question but not the gate question is reported for the audit only.

Meeting the criteria never removes the `UNEVALUATED` count. A method that
meets every in-scope assertion while returning `UNEVALUATED` on J or O is
still reported with those cases listed. Its result is bounded by its
recognition scope and must not be stated as a general compliance claim.

Because Set 1 is visible and precommitted rather than blind (section 5),
results describe performance on Set 0 and Set 1 only. They do not show how a
detector would generalize to unseen changes.

**C3 limit (D5, owner decision):** pre-execution behavioral enforcement of C3
is excluded. On the whole-file audit question, M3 reports only the recognized
forms in section 4.1. That is either a recognized violation (no handler on the
template, or a re-raising handler) or a *recognized static fallback structure*.
Every other form is `UNEVALUATED`. M4 tests behavior *after the mutation*.
Neither establishes pre-execution behavioral enforcement of C3. Case U, a
deletion-only change, may be detected by the whole-file audit but stays
outside the ADR-018 introduced-delta gate. It is never reported as stopped at
the gate.

## 8. Hypotheses

- **HA1:** M1 removes the E and R false blocks without missing B, and catches
  none of the non-literal C1 cases (G, H, S). For S, the literal appears only
  inside a string: M0's exact match catches it, while M1, which excludes
  strings, misses it.
- **HA2:** M2 catches C, I, K, T and the violating half of M, raises no false
  blocks on L or boundary-5, and returns `UNEVALUATED` on J.
- **HA3:** Under the section 4.1 contract, M3:
  - returns `VIOLATION` on D (no handler on the template) and on N (a handler
    that re-raises);
  - returns `NO_VIOLATION`, for static structure only, on A and P;
  - returns `UNEVALUATED` on O, not a false block;
  - returns `VIOLATION` on U at the whole-file audit, while U is not reported
    as stopped at the introduced-delta gate.
- **HA4:** Unrecognized shapes leave a residual that no static method in M1–M3
  closes without widening its recognized forms. The size of that residual is
  the main input to any later rule-type decision.

## 9. Non-goals

- Changing `FORBID_LITERAL` semantics (ADR-019 §9) or adding a rule type to
  the runtime.
- Any change to `mneme/`, the hook, the middleware, the CLI, `.mneme/`, CI, or
  either benchmark suite.
- A general semantic policy engine, LLM-based judging, or regex rules.
- Languages other than Python, or decisions other than ADR-001.
- Any execution-governance claim (P0-B).
- Amending the Layer 1 freeze. If results justify new rule types, each one
  gets its own ADR and behavioral charter (Amendment Procedure §4).

## 10. Owner decisions (resolved 2026-10-21)

Recorded from the
[PR #578 review](https://github.com/MnemeHQ/mneme/pull/578#issuecomment-6310714497).

| ID | Decision | Disposition |
|---|---|---|
| D1 | Offline M1–M3 prototypes | **Design scope conditionally authorized**, only under `validation/semantic-constraint-p0a/`. No runtime imports, rules, hooks, CLI, CI, benchmark or freeze changes. **Not implementation authorization** until this charter passes final review and the independently frozen Set 1 commit exists. |
| D2 | Oracle correction | **Approved.** A new, versioned synthetic oracle; #570's oracle preserved byte-identically. It captures the deadline actually supplied to `classify`, including call-site overrides, and keeps runtime observations separate from labels. Its semantics are frozen before scoring, and it executes only known synthetic fixtures (section 5.1). |
| D3 | Independent Set 1 | **Required.** A separate author or session creates and labels G–U. The labels are reviewed against ADR-001, and the fixture bytes, digests and oracle version are frozen in their own prior commit. This is a precommitted evaluation set, not evidence of generalization. |
| D4 | Case S | **VIOLATION (C1, architectural intent).** The new environment-variable switch makes disabling the deadline possible. The unset-environment ACCEPT is kept as a runtime observation, and an enabled-switch probe is added or documented as unevaluable (section 5.1). |
| D5 | Pre-execution C3 | **Excluded.** M3 reports recognized static fallback structure on the audit question, and M4 tests behavior after mutation. U stays outside the introduced-delta gate (section 7). |

## 11. Deliverables (after final charter approval)

1. The Set 1 fixtures, labels and adjudication rationale, the corrected and
   versioned oracle, and the digests. They are written by an author
   independent of the detectors and committed first, in their own commit.
2. Prototype methods M1–M3, a runner, and evidence (summary JSON/CSV, run
   records with versions and anchors).
3. `RESULTS.md` with per-method, per-constraint, per-question tables, the
   hypothesis outcomes, the section 7 verdict for each method, and the
   residual list.
4. A recommendation on whether to charter any new rule type. That
   recommendation is not a decision, and no ADR is written in this experiment.

## 12. Smallest next step

D1–D5 are resolved. The remaining steps run in this order:

1. The owner gives final review of this revised charter.
2. The owner authorizes the independent fixture-and-oracle freeze.
3. A separate session writes Set 1 and the corrected oracle and freezes them as
   their own commit.
4. Only after that commit exists may M1–M3 implementation be authorized.
