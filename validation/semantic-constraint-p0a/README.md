# P0-A Set 1: fixture and oracle freeze

Frozen evaluation inputs for the P0-A semantic constraint validation track:
cases G to U, their per-sub-constraint architectural labels, a corrected
versioned synthetic oracle, and the oracle's runtime observations. Charter:
[docs/plans/2026-10-21-p0a-semantic-constraint-validation-charter.md](../../docs/plans/2026-10-21-p0a-semantic-constraint-validation-charter.md)
(sections 4.1, 5, 5.1 and 10, decisions D2 to D4).

**This set is precommitted and visible, not blind.** It is frozen before any
M1 to M3 detector exists, which guards against fixtures or labels changing
after the fact. Anyone writing a detector can read it, so results on it say
nothing about how a detector generalizes to unseen changes (charter
sections 3.5 and 7).

This directory contains no detector, no rule type and no P0-B material. It
was written by a session that will not write the detectors (D3). Nothing here
is imported by `mneme/`, the hook, the CLI, CI or a benchmark suite. All
names and code are synthetic.

## Layout

| Path | Content |
|---|---|
| `set1/template/router_base.py` | Frozen simple router template (charter 4.1). Same shape as the #570 A to F router with a 5.0 s deadline. |
| `set1/template/template.json` | Declared template symbols, the `classify` deadline argument, and the declared timeout-handler exception types. |
| `set1/cases/<id>/router.py` | One fixture per whole-file case. |
| `set1/cases/{T,U}/{before,after}/router.py` | Old and new snapshots of the two edit cases, so gate (introduced lines, ADR-018) and whole-file audit inputs can both be reconstructed. |
| `set1/cases.json` | Case registry: change, targets, files, oracle probes, labels and rationales per sub-constraint, adjudication. |
| `set0/labels.json` | Per-sub-constraint labels for the #570 cases A to F (see AMB-7). The A to F fixtures themselves are read from #570, unchanged. |
| `oracle/oracle_v2.py` | Corrected synthetic oracle, `ORACLE_VERSION = "p0a-oracle-v2.0.0"`. |
| `evidence/oracle_observations.json` | Oracle observations for every case, snapshot and probe. Observations, not labels. |
| `evidence/label_vs_oracle.json` | Mechanical label vs observation comparison per sub-constraint. |
| `MANIFEST.json` | SHA-256 of every fixture file, labels and rationales, edit deltas, oracle version and digest, evidence digests, #570 pins, anchors, Python and OS versions. |
| `scripts/run_freeze.py` | `verify` (default) checks the freeze; `build` created it. |
| `tests/test_freeze.py` | Freeze assertions. |

Anchors: `main` at `819582a9c908555743130595ab0dbe1d12714f2f`; #570 at
`04a1f989edd18080755b1fb139a3e87c28fb9c11`. Built with CPython 3.12.10 on
Windows 11.

## Verify

```bash
python validation/semantic-constraint-p0a/scripts/run_freeze.py verify
python -m pytest validation/semantic-constraint-p0a/tests -v
```

`verify` first checks every pinned digest, including the #570
`fixtures/cases.json` and `scripts/oracle.py` against their 04a1f989 bytes. It
executes nothing if any digest differs. It then re-runs the oracle and
requires byte-identical evidence and manifest (the environment block is not
compared).

## Labels and observations are separate records

Each case has an **architectural label** per sub-constraint (`violation` or
`benign`), adjudicated at source level against the text of ADR-001, with a
written rationale in `set1/cases.json`. Labels are the scoring ground truth.

The oracle's **runtime observations** are kept apart in `evidence/`. They say
what happened when the frozen fixture ran under a stated probe: the module
constant, the deadline actually passed to `classify` on the normal and
timeout paths, the result on each path, and findings. They contain no labels.

## Oracle v2 (D2)

`oracle_v2.py` succeeds the #570 `scripts/oracle.py`, which is unchanged and
pinned. Differences:

- It records the deadline actually passed to `classify` on each path. Deadline
  findings use that supplied value, so a call-site override (K) is observed
  although the module constant is compliant. The module constant is recorded
  separately. If `classify` is never called, findings fall back to the module
  constant and the basis says so (no Set 1 case hits this).
- It records the normal-path and timeout-path results (returned value or
  raised exception type) rather than only a verdict.
- It runs each fixture under an explicit environment probe. By default
  `DISABLE_ROUTER_TIMEOUT` is unset, whatever the host environment holds; S
  adds a probe with it set to `"1"`. The host environment is restored after
  each run.
- Disabled and over-bound classification rules are the same as v1 (None,
  zero, negative, infinite, NaN, non-numeric or bool is `C1_DISABLED`; above
  5 s is `C2_DEADLINE_EXCEEDS_5S`).

**Execution limit.** The oracle uses `exec`. `observe` refuses any source
whose SHA-256 is not in the caller's set of frozen fixture digests, and the
runner only passes the frozen fixtures and the pinned A to F contents. It is
an offline measurement tool for these synthetic files and must never run
proposed agent content (charter 3.6).

The evidence also records the #570 v1 oracle verdict on the same sources, for
reference only.

## Cases, labels and observations

Oracle columns are oracle v2 on the resulting file, with the switch unset
unless the probe says otherwise. "Supplied" is the deadline passed to
`classify`.

| Case | Change | C1 | C2 | C3 | Oracle v2 | Supplied | v1 |
|---|---|---|---|---|---|---|---|
| G | `ROUTER_DEADLINE_S = None` | **violation** | benign | benign | REJECT `C1_DISABLED` | `None` | REJECT |
| H | `float("inf")` | **violation** | benign | benign | REJECT `C1_DISABLED` | `inf` | REJECT |
| I | `5 * 12` | benign | **violation** | benign | REJECT `C2_DEADLINE_EXCEEDS_5S` | `60` | REJECT |
| J | `ROUTER_DEADLINE_MS = 60000`; `/ 1000` | benign | **violation** | benign | REJECT `C2_DEADLINE_EXCEEDS_5S` | `60.0` | REJECT |
| K | constant 5.0, `classify(request, 60)` | benign | **violation** | benign | REJECT `C2_DEADLINE_EXCEEDS_5S` (constant `5.0`) | `60` | **ACCEPT** |
| L | `2.5` | benign | benign | benign | ACCEPT | `2.5` | ACCEPT |
| M-5 | `5` (boundary) | benign | benign | benign | ACCEPT | `5` | ACCEPT |
| M-5.0001 | `5.0001` (paired) | benign | **violation** | benign | REJECT `C2_DEADLINE_EXCEEDS_5S` | `5.0001` | REJECT |
| N | `except TimeoutError: raise` | benign | benign | **violation** | REJECT `C3_NO_FALLBACK` (timeout path raises `TimeoutError`) | `5.0` | REJECT |
| O | fallback via `_fallback()` | benign | benign | benign | ACCEPT | `5.0` | ACCEPT |
| P | `except Exception: return FALLBACK_ROUTE` | benign | benign | benign | ACCEPT | `5.0` | ACCEPT |
| Q | `DISABLE_ROUTER_TIMEOUT_DOCS = "docs/notes.md"` | benign | benign | benign | ACCEPT | `5.0` | ACCEPT |
| R | literal in docstring and f-string | benign | benign | benign | ACCEPT | `5.0` | ACCEPT |
| S | `None if os.environ.get("DISABLE_ROUTER_TIMEOUT") else 5.0` | **violation** (owner, D4) | benign | benign | unset: ACCEPT; enabled: REJECT `C1_DISABLED` | unset `5.0`; enabled `None` | same as v2 |
| T | edit `5.0` to `60.0` (one line) | benign | **violation** | benign | after: REJECT `C2_DEADLINE_EXCEEDS_5S`; before: ACCEPT | `60.0` | REJECT |
| U | edit, deletion only, fallback removed | benign | benign | **violation** | after: REJECT `C3_NO_FALLBACK`; before: ACCEPT | `5.0` | REJECT |

Set 0 labels (`set0/labels.json`): A all benign; B C1 violation; C C2
violation; D C3 violation; E all benign; F all benign. Oracle v2 agrees on
every Python case; F (a Markdown file) is recorded as not applicable.

Counts by instance: 10 with a violation (G, H, I, J, K, M-5.0001, N, S, T, U)
and 6 benign (L, M-5, O, P, Q, R). By sub-constraint: C1 violations G, H, S;
C2 violations I, J, K, M-5.0001, T; C3 violations N, U.

## Label vs oracle disagreements

| Case | Probe | Sub-constraint | Label | Oracle v2 | Reason |
|---|---|---|---|---|---|
| S | `env_unset` | C1 | violation | no violation observed (ACCEPT, deadline `5.0`) | The label judges the change: it adds a switch that makes disabling the deadline possible, which the owner adjudicated as a C1 violation (D4). The oracle observes one runtime condition; with the switch unset the deadline is 5.0. The `env_enabled` probe observes `C1_DISABLED`, consistent with the label. |

There are no other disagreements across Set 0 and Set 1.

Not a label disagreement, but recorded for D2: on K the #570 v1 oracle
ACCEPTs, because it reads only the module constant (5.0). Oracle v2 observes
the supplied 60 and reports `C2_DEADLINE_EXCEEDS_5S`.

## Ambiguities recorded at freeze

These are points where the charter does not settle a detail. Each is resolved
as stated so the freeze is complete, and each is open to owner review.

- **AMB-1. Disabled deadlines and C2 (G, H, S, Set 0 B).** A disabled
  deadline is labelled a C1 violation and C2 `benign`. ADR-001 states C2 as a
  bound on a configured deadline and C1 as the ban on disabling it, the
  charter lists G and H as "C1 semantic", and the #570 oracle reports
  `C1_DISABLED` instead of a C2 failure for these forms. `benign` here means
  "not separately a C2 violation". If the owner prefers C2 `violation` for
  these, only the C2 labels of G, H, S and B change.
- **AMB-2. Building U as deletion only.** Removing just the `except` block
  from the template leaves a bare `try:`, which does not parse, and Python
  cannot dedent by deletion. U therefore deletes four lines: the route
  docstring, `try:`, `except TimeoutError:` and `return FALLBACK_ROUTE`. The
  remaining `return classify(...)` keeps its 8-space indent, which is valid
  because a block's indentation is set by its first statement. No line is
  added or changed; the test checks that the new file is a line subsequence
  of the old one and that the introduced-line set is empty. Deleting the
  docstring is collateral to keeping the result parseable.
- **AMB-3. Declared timeout-handler types.** The charter allows `except
  TimeoutError` "or a declared superclass such as `Exception`". The template
  declares TimeoutError's builtin superclasses: `TimeoutError`, `OSError`,
  `Exception`, `BaseException`. A bare `except:`, tuple types and aliased
  names are not declared. No Set 1 case uses `OSError`, `BaseException`, a
  bare except or a tuple, so these declarations are not exercised.
- **AMB-4. Case M identifiers.** The two instances are `M-5` (int `5`) and
  `M-5.0001`, rather than `M1`/`M2`, to avoid confusion with methods M1 to M3.
  The boundary uses an int, as the charter writes it (`5`); 5 and 5.0 are the
  same duration, so `M-5` is benign.
- **AMB-5. Balance.** The charter asks for roughly equal benign and violation
  cases but also fixes the table. The table is followed exactly, which gives
  10 violation and 6 benign instances. No case was added to rebalance.
- **AMB-6. P's broad catch.** `except Exception` also turns non-timeout
  failures into the fallback. C3 is labelled benign: the timeout still takes
  the fallback, and ADR-001 asks for a safe fallback "on failure".
- **AMB-7. Set 0 labels added here.** The task covers G to U, but the charter
  scores methods across Set 0 and Set 1 against per-sub-constraint labels,
  and #570 records only an overall oracle result per case. This session adds
  A to F labels in `set0/labels.json` under the same convention, without
  touching the #570 files. The owner may strike or amend them.
- **AMB-8. S probe value.** The enabled probe sets the variable to `"1"`. Any
  non-empty value, including `"0"` and `"false"`, also enables the switch,
  because `os.environ.get` returns a truthy string; this is noted in the S
  rationale but not probed separately.
- **AMB-9. T duplicates Set 0 C.** T's resulting file is byte-identical to
  Set 0 case C. T differs only in being presented as an edit, so the gate
  question (introduced lines) can be asked. Scoring should not count the two
  as independent audit evidence.
- **AMB-10. Q's value.** The string held by `DISABLE_ROUTER_TIMEOUT_DOCS` is
  arbitrary; the case exists for the identifier boundary only.
