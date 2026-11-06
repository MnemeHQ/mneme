# ADR-034 G1 numeric audit: local experiment results (gate B)

**Status: RESULTS RECORD.** Documentation only. Records gate B of the
[local experiment charter](../plans/2026-11-06-adr-034-g1-numeric-audit-local-experiment-charter.md)
(#750, merged `4e43de45`). With this record merged, the O2 exception ends
(charter §3.5).
**Date:** 2026-11-06.
**Authorization (owner, 2026-11-06):** "Yes, run gate B".
**Code under test:** `main` at `4e43de45`, CLI and matcher unmodified.

**Trust limitation (charter §3.6).** These are exploratory observations from
an unprotected, local audit memory with no host-event binding. They are not
enforcement evidence, not an ADR-029 "relevant enforcement observed" record,
and not validation beyond M4.

## 1. Setup

- **Disposable directory:** a session scratch directory outside the
  repository, holding `audit_memory.json` at its root and the input at
  `mneme/integrations/claude_code/hook.py`. Created at the start of the run,
  deleted at 2026-11-06T13:25:48Z (§5).
- **Audit memory:** a single decision, `AUDIT-HOOK-TIMEOUT`, with meta
  description "EXPERIMENTAL, NON-AUTHORITATIVE audit memory". It holds the
  charter §4.2 rule exactly. Canonical value:
  `{"inclusive":true,"language":"python","max":"10","symbol":"_CHECK_TIMEOUT_SECONDS","unit":"seconds","v":1}`;
  rule id `AUDIT-HOOK-TIMEOUT:FORBID_NUMERIC_ABOVE:8fc42aa70c5bd349e0e0b9b42fc96ae2`.
- **Invocation:** one form for every input, run in the disposable directory
  with `MNEME_MEMORY` removed from the environment:
  `python -m mneme.cli check --memory audit_memory.json --source-file mneme/integrations/claude_code/hook.py --query "hook check timeout" --mode warn --json`.
- **Baseline:** `hook.py` blob `285ef854` at `4e43de45`, unchanged since the
  qualification run; SHA-256 `cb381e8c…`.
- **Expectations frozen before the run:** the variant definitions and their
  expected classes and primary reasons were written and hashed at
  2026-11-06T13:24:25Z, before the first invocation (variant file SHA-256
  `c9c7d982…1e4c`; runner `c0f9326d…04a8`; memory builder `b3cf777a…d034d0`).
  Expectations follow ADR-034 §3, §4 and §5a. The raw results file
  (SHA-256 `22cbb700…e870`) stays in the session scratch directory; it is
  not committed.

## 2. Results

Classes are those of charter §5.4. In `--mode warn`, `FAIL` exits 0 and every
incomplete evaluation exits 2. Path applicability was `APPLIED` for every
input.

| ID | Variant (edit of the baseline) | Expected | Observed | Matcher status | Primary reason | Input SHA-256 |
|---|---|---|---|---|---|---|
| V00 | baseline, byte-identical | PASS | **PASS** | RECOGNIZED | – | `cb381e8c` |
| V01 | `= 5` | PASS | **PASS** | RECOGNIZED | – | `dbeb4285` |
| V02 | `= 9.5` | PASS | **PASS** | RECOGNIZED | – | `3aad8a91` |
| V03 | `= 10.0` (at bound) | PASS | **PASS** | RECOGNIZED | – | `7e4b781f` |
| V04 | `= 11` | FAIL | **FAIL** | RECOGNIZED | – | `0f40dd42` |
| V05 | `= 10.001` | FAIL | **FAIL** | RECOGNIZED | – | `a616f2aa` |
| V06 | `= 5 * 3` (recognized arithmetic) | FAIL | **FAIL** | RECOGNIZED | – | `eebd769a` |
| V07 | `= 60 / 6` (recognized arithmetic) | PASS | **PASS** | RECOGNIZED | – | `6c7b9cb5` |
| V08 | `: int = 60` (annotated) | FAIL | **FAIL** | RECOGNIZED | – | `60e1fd26` |
| V09 | `= int('60')` | INCOMPLETE | **INCOMPLETE** | MATCHER_UNEVALUATED | UNRECOGNIZED_FORM | `59d67097` |
| V10 | alias: `= _DEFAULT_CHECK_TIMEOUT` (that name `= 60`) | INCOMPLETE | **INCOMPLETE** | MATCHER_UNEVALUATED | UNRECOGNIZED_FORM | `cce2e3c2` |
| V11 | `= float(os.environ.get('MNEME_X', 60))` | INCOMPLETE | **INCOMPLETE** | MATCHER_UNEVALUATED | UNRECOGNIZED_FORM | `630a6990` |
| V12 | `= 0` (disabled value) | INCOMPLETE | **INCOMPLETE** | MATCHER_UNEVALUATED | UNRECOGNIZED_FORM | `026889a4` |
| V13 | declared source removed | INCOMPLETE | **INCOMPLETE** | MATCHER_UNEVALUATED | SOURCE_NOT_FOUND | `0d540782` |
| V14 | second module-level `= 5` appended | INCOMPLETE | **INCOMPLETE** | MATCHER_UNEVALUATED | AMBIGUOUS_BINDING | `de265eed` |
| V15 | `= 60`, later rebound `= 5` | INCOMPLETE | **INCOMPLETE** | MATCHER_UNEVALUATED | AMBIGUOUS_BINDING | `81ca54c1` |
| V16 | `+= 5` appended | INCOMPLETE | **INCOMPLETE** | MATCHER_UNEVALUATED | AMBIGUOUS_BINDING | `5ca7a23a` |
| V17 | function-local `_CHECK_TIMEOUT_SECONDS = 60` | INCOMPLETE | **INCOMPLETE** | MATCHER_UNEVALUATED | AMBIGUOUS_BINDING | `8faa636a` |
| V18 | `globals()['_CHECK_TIMEOUT_SECONDS'] = 60` appended | INCOMPLETE | **PASS** | RECOGNIZED | – | `46fe0d0a` |
| V19 | `del _CHECK_TIMEOUT_SECONDS` appended | INCOMPLETE | **INCOMPLETE** | MATCHER_UNEVALUATED | AMBIGUOUS_BINDING | `01c9f9ce` |
| V20 | syntax error appended | INCOMPLETE | **INCOMPLETE** | MATCHER_UNEVALUATED | PARSE_FAILURE | `58f718a9` |

**Totals:** 21 inputs; 20 observed as expected, 1 mismatch (V18).
PASS 8 (7 expected + V18), FAIL 5, FAIL_INCOMPLETE 0, INCOMPLETE 11, ERROR 0.
No input produced `FAIL_INCOMPLETE` or `ERROR`. Every non-`PASS` row's trace
carried the matcher status and reason shown.

### 2.1 Finding F-G1-1: dynamic namespace write to the symbol is not detected (fail-open)

V18 appends `globals()['_CHECK_TIMEOUT_SECONDS'] = 60` to an otherwise
compliant module. At runtime the module value is 60, which exceeds the bound.
The audit returned `PASS`, `evaluation_complete` true, matcher status
`RECOGNIZED`, outcome `NO_VIOLATION`.

- **Against the spec:** ADR-034 §3 makes the symbol source `UNKNOWN` when it
  is "rebound anywhere in the module", and the ADR's invariant is that matcher
  uncertainty is never a clean result. A namespace-mapping write is a
  rebinding the matcher cannot rule out, so the expected outcome was
  `MATCHER_UNEVALUATED` / `AMBIGUOUS_BINDING`.
- **Cause (read only):** `mneme/numeric_rule.py` implements dynamic-construct
  detection (`_DYNAMIC_NAMES`: `exec`, `eval`, `globals`, `locals`, `vars`,
  `__builtins__`, plus namespace attributes) for function-source resolution
  under §3a rule 4. ADR-034 §3a leaves the symbol source on its §3 wording
  and says "Not decided here" for further symbol cases, and the symbol path
  does not apply that detection. The regression tests for dynamic constructs
  (`tests/test_numeric_call_scope_resolution.py`) cover call sources only.
- **Scope:** a synthetic, adversarial form. It does not occur in the code base
  (§3, Q3). It is still a fail-open path in a matcher whose contract is
  fail-closed. Not run against M4's pinned build (`f25f0e84`); that build
  predates #675 and has no dynamic-construct detection at all. M4's recorded
  PASS is not changed by this record.
- **Not done here:** no matcher, test or ADR change (charter §6, §10). A fix
  needs its own reviewed change to the shared matcher.

## 3. Usefulness questions (charter §5.5)

**Q1. Does the baseline copy evaluate complete and `PASS`?** Yes: V00 exit 0,
`PASS`, `evaluation_complete` true, `RECOGNIZED`, path `APPLIED`.

**Q2. Do within, at and above variants produce the expected classes?** Yes.
Within (V01, V02, V07) and at bound (V03) were `PASS`; above (V04, V05, V06,
V08) were `FAIL`, including the smallest decimal step above the bound
(V05, `10.001`), recognized arithmetic (V06) and an annotated assignment
(V08).

**Q3. Which realistic forms fall outside the recognition scope, and how often
does the code base use them?** Read-only survey of `mneme/` at `4e43de45`:

- **The governed constant itself is in scope.** Every module-level numeric
  timeout or limit constant matching common names (`*TIMEOUT*`, `*SECONDS`,
  `*_S`, `*LIMIT*`, `*MAX*`, `*SIZE*` and similar) is a literal or literal
  arithmetic: 20 of 20. The four other matches are strings or compiled
  regexes, not numbers.
- **Its consumers are out of scope by design.** Six other modules import
  `_CHECK_TIMEOUT_SECONDS` and pass it as a `timeout=` keyword argument
  (agent_sdk, antigravity, codex_cli `gate.py` and `stop_audit.py`, hermes,
  kiro). Imported values and keyword arguments are unevaluated (charter §4).
  The constraint still covers them only because they import the one governed
  definition; if a consumer replaced the import with its own literal, this
  rule would not see it.
- **The test-only environment override** at `hook.py:985` is a computed value
  (out of scope, as recorded in charter §4.2; V11 shows the same shape is
  `INCOMPLETE` when it is the governed assignment).
- **Inline timeouts elsewhere are keyword arguments:** `timeout=10`
  (`audit_pairing.py:135`, `github_evidence.py:217`, `:242`) and
  `timeout=60` (`session_state.py:78`). A call-source rule over these would be
  unevaluated, since ADR-034 recognizes positional arguments of bare-name
  calls only.

So, for this code base, the matcher sees named module constants well and
does not see how timeouts are actually passed at call sites.

**Q4. Is a persistent advisory workflow worth its cost?** **No, not now.**
- The governed constant is one line that has not needed protection, and the
  real exposure (consumers with their own literals, keyword-argument timeouts)
  is outside the recognition scope.
- F-G1-1 is a fail-open path; an advisory workflow should not run on a
  matcher with a known fail-open until it is fixed.
- The cost recorded in the charter is unchanged: a `.github/` change by
  recorded bypass, an unprotected committed audit memory, and an observation
  period, for one constraint.

Revisit only if several constraints in recognized forms are worth guarding
and F-G1-1 is fixed.

## 4. Stop rule and isolation (charter §5.6, §6)

The stop rule was not triggered. Checked after the run:

1. `.mneme/project_memory.json` carries no `FORBID_NUMERIC_ABOVE` rule
   (0 occurrences).
2. No repository file changed during the run (clean `git status` in the
   administrative checkout and in this record's worktree); this record is the
   only change.
3. Trusted gate adapter, evaluator, ruleset, posture and memory input:
   untouched.
4. `MNEME_MEMORY` was unset in the session and removed from the child
   environment.
5. No CLI, matcher, enforcer, hook or ADR change.

## 5. Disposal

The disposable directory (audit memory and all 21 inputs) was deleted at
2026-11-06T13:25:48Z and confirmed absent. Inputs are reproducible from the
baseline blob and the variant table above.

## 6. Claims

Supported: *for one restated constraint, the G1 audit at `4e43de45`
classified the baseline copy and these 21 synthetic inputs as recorded: 20 as
expected, and one dynamic rebinding (V18) as a clean `PASS` contrary to
ADR-034 §3.*

Not claimed: enforcement, blocking, pre-write protection, CI numeric
enforcement, ADR-029 relevant enforcement, trustworthy enforcement evidence,
generalization to other rules or repositories, or any change to M4, G2-1 or
R3 outcomes. Variants were authored with knowledge of the matcher (charter
§7); this is not blind detection.

## 7. Outcome

- Gate B complete. The O2 exception ends when this record merges.
- No persistent workflow, committed audit memory or observation period.
- R4, G2-1 blocking and CI numeric enforcement remain deferred.
- Candidate follow-up, not started: a reviewed matcher change applying
  dynamic-construct detection to the symbol source (F-G1-1), with
  regressions.
