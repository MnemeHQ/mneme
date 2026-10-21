# P0-A: Semantic constraint enforcement — validation charter

**Status:** **DRAFT** for owner review. Validation only. Accepting this charter
authorizes **no** change to `mneme/`, `docs/adr/`, `.mneme/`, the benchmark
suites, CI, or the Layer 1 freeze document. The decisions in section 10 must be
resolved before any experiment code is written.
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
5. **A–F supports one observation per gap.** Tuning methods against A–F alone
   overfits; the freeze's benchmark section calls adding scenarios to push a
   metric overfitting. Extension cases must therefore be authored and frozen
   **before** any method exists (section 5).
6. **A gate must not execute proposed code.** The oracle runs candidate source
   with `exec`. That is fine for a synthetic offline oracle, but proposed agent
   content can never be executed as gate input. So behavioral evidence for C3
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
| M3 | Static structural fallback: `ast`, `route` must contain a `try` whose handler catches `TimeoutError` (or a declared superclass) and returns the declared fallback symbol; any other shape is `UNEVALUATED` | C3 | Audit (whole file) |
| M4 | Behavioral: the oracle's timeout and normal-path probes, run as a project test after the mutation | C3, C2 | Post-mutation (not pre-execution) |

M4 is included only to measure the gap between what the static methods claim
and what behavior shows. Passing M4 never supports a pre-execution claim.

No method may call a model. Determinism is a requirement, not a metric.

## 5. Case sets

**Set 0 (frozen baseline):** cases A–F from #570, byte-identical. The runner
checks their digests against `validation/orchestrator-decision-sandbox/fixtures/cases.json`
at `04a1f989`.

**Set 1 (held-out extension):** authored, labelled by the corrected oracle,
digest-frozen and committed **before** any M1–M3 code is written, by an author
who does not write the detectors (D3). Proposed initial set:

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
| S | `os.environ.get("DISABLE_ROUTER_TIMEOUT")` controls the deadline | C1 via string key | adjudicated (D4): the oracle ACCEPTs with the env var unset, though the intent is violated |
| T | Edit: the single line `5.0` → `60.0` | C2 via introduced delta | violation |
| U | Edit: deletion-only removal of the `except` block | C3 via deletion | violation (gate structurally blind, audit only) |

Set 1 should hold roughly equal numbers of benign and violation cases. A case
added after methods exist goes into a separate, clearly marked **post-hoc** set
that never counts toward the section 7 criteria.

## 6. Verdicts and scoring

Each (method, case, question) triple yields exactly one verdict:
`VIOLATION`, `NO_VIOLATION` or `UNEVALUATED`. Each verdict is compared with the
oracle label:

| Oracle \ Method | VIOLATION | NO_VIOLATION | UNEVALUATED |
|---|---|---|---|
| violation | caught | **missed** (false negative) | unevaluated violation |
| benign | **false block** (`FALSE_POSITIVE`) | correct allow | unevaluated benign |

Reported per sub-constraint, per method, per question (gate vs audit):

- Violation catch rate, miss count, and unevaluated count (`UNEVALUATED` is
  never folded into either PASS or block).
- False-block count on benign cases.
- Determinism: two clean runs, byte-identical summaries.
- Evidence binding (ADR-029): each verdict records the decision ID, the rule or
  method ID, the case content digest, the question, and the runtime anchor.
- Audit truthfulness: what `mneme audit` reports for the decision, alongside
  measured coverage.

## 7. What counts as sufficient semantic proof

This section answers the prerequisite left open in Step 1. A method may be
described as **enforcing Cn for this decision shape** only if, across Set 0
and Set 1:

1. It misses **zero** oracle-labelled violations of Cn.
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

**C3 limit stated in advance:** static methods can at most establish that a
*recognized fallback form is present*. Showing that the fallback *behaves*
safely needs execution, which only a post-mutation boundary can do (M4). Unless
the owner decides otherwise (D5), P0-A does not claim pre-execution
enforcement of C3.

## 8. Hypotheses

- **HA1:** M1 removes the E and R false blocks without missing B, and catches
  none of the non-literal C1 cases (G, H, S).
- **HA2:** M2 catches C, I, K, T and the violating half of M, raises no false
  blocks on L or boundary-5, and returns `UNEVALUATED` on J.
- **HA3:** M3 catches D and N, returns `UNEVALUATED` on O rather than a false
  block, and on the gate question it cannot see U.
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

## 10. Decisions required before any experiment code

| ID | Decision | Recommendation |
|---|---|---|
| D1 | Authorize prototype detectors M1–M3 under `validation/semantic-constraint-p0a/`, never imported by `mneme/` | Authorize; it is the minimum needed to answer the question |
| D2 | Correct the oracle to record the deadline actually passed to `classify` (case K) before anything is frozen | Correct it, version it, keep the #570 oracle byte-identical as historical |
| D3 | Separate the Set 1 author from the detector author | Required: a separate agent session or reviewer writes and freezes Set 1 |
| D4 | Adjudicate the label for case S, where the oracle and intent disagree | The owner labels it before the freeze, and the rationale is recorded |
| D5 | Whether pre-execution C3 is in scope at all | No: report the static presence check and M4 behavior separately |

## 11. Deliverables (after D1–D5 are resolved)

1. The Set 1 fixtures, the corrected oracle and the digests, committed first
   in a separate commit.
2. Prototype methods M1–M3, a runner, and evidence (summary JSON/CSV, run
   records with versions and anchors).
3. `RESULTS.md` with per-method, per-constraint, per-question tables, the
   hypothesis outcomes, the section 7 verdict for each method, and the
   residual list.
4. A recommendation on whether to charter any new rule type. That
   recommendation is not a decision, and no ADR is written in this experiment.

## 12. Smallest next step

The owner resolves D1–D5. Then the Set 1 fixtures and the corrected oracle are
written and frozen as their own commit, before any detector exists.
