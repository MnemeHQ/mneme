# P0-A offline detector experiment (M1 to M3): results

**Nothing here is shipped enforcement.** M1 to M3 are offline prototypes
under `validation/semantic-constraint-p0a/detectors/`. None is imported by
`mneme/`, the hook, the middleware, the CLI, CI or a benchmark suite, and none
is connected to any mutation gate. These results establish, at most, bounded
offline detection capability on one synthetic decision shape (ADR-001), one
language (Python), one synthetic file and a precommitted, visible case set.
They say nothing about how a detector generalizes to unseen changes (charter
sections 3.5, 3.11 and 7).

Charter: [docs/plans/2026-10-21-p0a-semantic-constraint-validation-charter.md](../../docs/plans/2026-10-21-p0a-semantic-constraint-validation-charter.md).
Authorization: owner comment on #582 (post-merge checkpoint, M1 to M3 offline
experiment authorized). Frozen inputs: this directory at `f5c910bc`, unchanged.

## Anchors and reproducibility

| Item | Value |
|---|---|
| Freeze commit | `f5c910bc0cad7a5cd9bf99ba3c831cdc5ba016bd` |
| `MANIFEST.json` SHA-256 | recorded in `evidence/detectors/summary.json` (`anchors.manifest_sha256`) |
| Oracle | `p0a-oracle-v2.0.0`, SHA-256 `3a6c54fd...4890` |
| #570 anchor (Set 0) | `04a1f989edd18080755b1fb139a3e87c28fb9c11` |
| Code commit the runs used | `ab0e5209` (tree clean for this directory, the #570 directory and `mneme/`) |
| Runtime | CPython 3.12.10, Windows 11 (`Windows-11-10.0.26300-SP0`) |
| M0 runtime | `mneme` 0.10.0 imported from this checkout (installed `mneme-hq` metadata reads 0.8.0 from a stale editable install; the run record shows the module actually loaded) |

Two runs, each from a fresh process with bytecode caches removed and an empty
output directory, produced byte-identical `summary.json` and `summary.csv`
(`evidence/detectors/reproducibility.json`, `byte_identical: true`). The run
records with versions are in `evidence/detectors/runs/run-{1,2}/`.

Before evaluating anything, every run calls `run_freeze.verify()` and checks
that `HEAD` contains `f5c910bc`. A digest mismatch stops the run with exit 3.

Reproduce:

```bash
python validation/semantic-constraint-p0a/scripts/run_freeze.py verify
python validation/semantic-constraint-p0a/scripts/run_detectors.py --out <empty dir 1>
python validation/semantic-constraint-p0a/scripts/run_detectors.py --out <empty dir 2>
python validation/semantic-constraint-p0a/scripts/run_detectors.py --compare <dir 1> <dir 2> --out <file>
python -m pytest validation/semantic-constraint-p0a/tests -v
```

## Methods

| ID | Version | What it is | Question(s) answered | Targets |
|---|---|---|---|---|
| M0 | shipped `mneme check --mode strict --json` | `FORBID_LITERAL DISABLE_ROUTER_TIMEOUT` on `src/**`, invoked exactly as in #570 (fresh fixture per subject via the #570 `sandbox_lib`, cwd = fixture root) | audit (whole file; ADR-018 section 2) | C1 literal; C2 and C3 have no rule, but the decision-level verdict is reported |
| M1 | `p0a-m1-lexical/1.0.0` | `tokenize`; the literal matches only as a whole `NAME` token | audit; gate | C1 (literal aspect) |
| M2 | `p0a-m2-static-bound/1.0.0` | `ast`; module constant plus the deadline argument of every `classify` call; numeric literals and folding of literal arithmetic only | audit; gate | C1 (disabled forms), C2 |
| M3 | `p0a-m3-structural-fallback/1.0.0` | `ast`; charter section 4.1 contract on the frozen template | audit; gate | C3 |
| M4 | `p0a-oracle-v2.0.0` | oracle v2 `observe` on the frozen fixture, through the frozen digest allow-list, exactly as `run_freeze` runs it | post-mutation | C1, C2, C3 (observations) |

M1 to M3 only parse. They do not `exec`, `eval` or import proposed source, call
a model or use the network; a test scans their source for such calls and
another checks that a side-effecting fixture is not executed. M4 executes the
frozen fixtures, so it never supports a pre-execution claim.

**Questions.** `audit` asks whether the resulting whole file violates the
sub-constraint. `gate` asks the ADR-018 question: does what the edit
*introduces* violate it? It is posed only for T and U, the two cases with
frozen before and after snapshots. The detector runs over the resulting file;
the gate keeps a `VIOLATION` only if its evidence touches an introduced line,
and an edit with no introduced lines is `UNEVALUATED` at the gate (the shipped
hook proceeds on such an edit, ADR-018 section 5). `post_mutation` is M4's.

**Scoring rules** (all from the owner rulings on #582):

- Labels are the frozen architectural labels. Oracle observations are never
  labels.
- F (documentation-only, path-excluded, AMB-7) gets a verdict from every
  method but is excluded from every in-scope denominator.
- T's resulting file is byte-identical to C (AMB-9). On audit and
  post-mutation it is reported but not scored; C counts once. T is scored
  only at the gate.
- U is never reported as stopped at the gate (AMB-2, D5).
- A disabled deadline is a C1 violation; C2 `benign` for it means "not
  separately assessed", not compliant (AMB-1). M2 follows the same
  convention: it reports a disabled deadline under C1 and gives C2
  `NO_VIOLATION` with reason `DISABLED_ATTRIBUTED_TO_C1`. The decision still
  fails on C1.
- A method's verdict on a sub-constraint it does not target is
  `UNEVALUATED` (`NOT_TARGETED`) and not scored. M0 is the exception: the
  shipped check reports a decision-level PASS with `evaluation_complete:
  true`, so its C2 and C3 verdicts are scored as the `NO_VIOLATION` claim it
  makes, with the reason `NO_RULE_FOR_SUBCONSTRAINT`.
- M4's scored row uses the default probe (`env_unset`). S's `env_enabled`
  probe is reported as a supplemental row.

**Bindings (ADR-029 style).** Every verdict row in `summary.json` carries the
decision ID, method ID and version, question, sub-constraint, target path and
applicability, case content SHA-256 (and the before SHA-256 for the gate),
freeze commit, manifest SHA-256 and oracle version; M0 rows also carry the
rule ID. The summary binds method and runner source digests.

## Results: whole-file audit (Set 0 A to E and Set 1 G to U; F and T excluded)

`V` = VIOLATION, `ok` = NO_VIOLATION, `U` = UNEVALUATED. Denominators: C1 has
4 violations (B, G, H, S); C2 has 5 (C, I, J, K, M-5.0001); C3 has 3 (D, N, U).
There are 20 scored subjects per sub-constraint.

| Method | Sub-constraint | Caught | Missed | False blocks | Unevaluated (violation) | Unevaluated (benign) | Section 7 |
|---|---|---|---|---|---|---|---|
| M0 | C1 | 2/4 (B, S) | 2 (G, H) | 2 (E, R) | 0 | 0 | partial |
| M0 | C2 | 0/5 | 5 (C, I, J, K, M-5.0001) | 0 | 0 | 0 | partial |
| M0 | C3 | 0/3 | 3 (D, N, U) | 0 | 0 | 0 | partial |
| M1 | C1 | 1/4 (B) | 3 (G, H, S) | 0 | 0 | 0 | partial |
| M2 | C1 | 1/4 (G) | 0 | 0 | 3 (B, H, S) | 1 (J) | criteria 1 and 2 met; 3 of 4 violations unevaluated |
| M2 | C2 | 4/5 (C, I, K, M-5.0001) | 0 | 0 | 1 (J) | 3 (B, H, S) | criteria 1 and 2 met; J unevaluated |
| M3 | C3 | 3/3 (D, N, U) | 0 | 0 | 0 | 1 (O) | criteria 1 and 2 met; O unevaluated |

## Results: ADR-018 introduced-delta gate (T and U only)

T introduces one line (line 3, `ROUTER_DEADLINE_S = 60.0`). U introduces none.

| Method | Sub-constraint | T | U | Result |
|---|---|---|---|---|
| M1 | C1 | ok (benign: correct allow) | U (benign) | no violation instance; not assessable |
| M2 | C1 | ok (benign: correct allow) | U (benign) | no violation instance; not assessable |
| M2 | C2 | **V (violation: caught)** | U (benign) | 1/1 caught |
| M3 | C3 | ok (benign: correct allow) | **U (violation: unevaluated)** | 0/1; U is not stopped at the gate |

U's C3 violation is caught only by the whole-file audit (M3) and by the
post-mutation oracle (M4). At the gate it is `UNEVALUATED`, and the shipped
hook would let the edit through. **U is not stopped at the gate by any
method.**

## Results: post-mutation reference (M4, default probe)

| Sub-constraint | Caught | Missed | False blocks | Unevaluated |
|---|---|---|---|---|
| C1 | 3/4 (B, G, H) | 1 (S) | 0 | 0 |
| C2 | 5/5 | 0 | 0 | 0 |
| C3 | 3/3 | 0 | 0 | 0 |

M4 re-ran oracle v2 and reproduced the committed freeze observations exactly
(`m4_matches_frozen_observations: true`). M4 is not a pre-execution method,
and it executes code, so its results support no gate claim.

## Per-case verdicts

### C1

| Case | Label | M0 | M1 | M2 | M4 |
|---|---|---|---|---|---|
| A | benign | ok | ok | ok | ok |
| B | violation | V | V | U | V |
| C | benign | ok | ok | ok | ok |
| D | benign | ok | ok | ok | ok |
| E | benign | **V (false block)** | ok | ok | ok |
| F | benign (excluded) | ok | U | U | U |
| G | violation | **ok (missed)** | **ok (missed)** | V | V |
| H | violation | **ok (missed)** | **ok (missed)** | U | V |
| I, K, L, M-5, M-5.0001, N, O, P, Q | benign | ok | ok | ok | ok |
| J | benign | ok | ok | U | ok |
| R | benign | **V (false block)** | ok | ok | ok |
| S | violation | V | **ok (missed)** | U | **ok (missed)**; `env_enabled`: V |
| T | benign (excluded, = C) | ok | ok | ok | ok |
| U | benign | ok | ok | ok | ok |

### C2

| Case | Label | M0 | M2 | M4 |
|---|---|---|---|---|
| C, I, K, M-5.0001 | violation | **ok (missed)** | V | V |
| J | violation | **ok (missed)** | U | V |
| B, H, S | benign | ok | U | ok |
| other benign (A, D, E, G, L, M-5, N, O, P, Q, R, U) | benign | ok | ok | ok |
| T | violation (excluded, = C; gate only) | ok | V | V |

### C3

| Case | Label | M0 | M3 | M4 |
|---|---|---|---|---|
| D, N, U | violation | **ok (missed)** | V | V |
| O | benign | ok | U | ok |
| other benign | benign | ok | ok | ok |

The full machine-readable table, with reasons and evidence lines per verdict,
is `evidence/detectors/summary.csv`.

**M0 baseline consistency.** M0's A to F labels equal the committed #570
post-fix CLI labels (`m0_matches_570_cli_labels.all_match: true`). On Set 1,
M0 additionally blocks R (false block: literal in a docstring and f-string)
and S (the literal appears inside `os.environ.get("DISABLE_ROUTER_TIMEOUT")`).

**Audit truthfulness (charter 3.9).** `mneme audit` on the #570 baseline still
reports the decision as `protected`, 100% protection, while the measured
audit coverage of the shipped path is C1 2/4 with 2 false blocks, C2 0/5 and
C3 0/3. This experiment records the discrepancy and does not change it.

## Label vs oracle disagreements

| Case | Probe | Sub-constraint | Label | Oracle v2 (M4) | Reason |
|---|---|---|---|---|---|
| S | `env_unset` | C1 | violation | NO_VIOLATION | Owner-adjudicated label (D4): adding the switch violates C1 even while unset. The oracle observes one runtime condition, deadline 5.0. The `env_enabled` probe (`"1"`) observes `C1_DISABLED`, consistent with the label. Other truthy values such as `"0"` are not probed (AMB-8). |

There are no other disagreements. This matches the freeze's
`evidence/label_vs_oracle.json`.

## Hypotheses (charter section 8)

Each prediction is checked mechanically in `summary.json` (`hypotheses`).

**HA1: supported.** M1 removes both false blocks (E, R: `NO_VIOLATION`), still
catches B, and catches none of the non-literal C1 cases G, H, S. For S, M0's
exact match catches the literal inside the string and M1, which excludes
strings, misses it. On C1 as a whole, M1 is therefore not better than M0 at
catching: it trades two false blocks (E, R) for one additional miss (S).

**HA2: supported.** M2 catches C, I, K, M-5.0001 on the audit and T at the
gate; raises no false block on L or M-5; and returns `UNEVALUATED` on J.

**HA3: supported.** M3 returns `VIOLATION` on D and N, `NO_VIOLATION` (static
structure only) on A and P, `UNEVALUATED` on O (not a false block), and
`VIOLATION` on U at the whole-file audit. At the introduced-delta gate U is
`UNEVALUATED`, not stopped.

**HA4: supported.** With the declared recognized forms, a residual remains that
no static method closes:

- Audit: H (C1, `float("inf")`, a call), S (C1, a switch through
  `os.environ.get` and a conditional expression) and J (C2, a value derived
  from another constant). B (C1, a conditional expression) is unevaluated by
  M2 but caught lexically by M1.
- Gate: U (C3, deletion only) is invisible to any introduced-delta gate,
  whatever detector sits behind it.
- Unevaluated benign forms that would need recognition to pass rather than
  stay unknown: O (fallback through a helper), and B, H, S for C2.

Closing any of these needs a wider recognized form (named-constant
propagation, a small vocabulary of disabled-form calls, interprocedural
fallback resolution, or a configuration-switch pattern), each of which is a
scope decision, not a fix.

## Section 7 verdicts per method

Criteria 4 to 6 hold for M1 to M3 in this run: two clean runs are
byte-identical, the detectors never execute content (tests), every verdict is
bound, and the scope is named here. Criteria 1 to 3 differ per sub-constraint
and question.

- **M1, C1, audit: partial.** Misses G, H, S. False blocks: none.
  Unevaluated: none. M1 has no way to mark a non-literal form as outside its
  scope, so out-of-scope violations come back as `NO_VIOLATION`, which fails
  criterion 3. Within the literal aspect alone (B, E, Q, R), it behaves as
  declared. At the gate, M1 is not assessable: no C1 violation instance
  exists (T and U are C1 benign).
- **M2, C1, audit: demonstrated offline detection capability within declared
  scope** (Python, ADR-001 shape, module constant and `classify` deadline
  argument as literals or folded literal arithmetic, whole-file audit). No
  miss and no false block, but **3 of 4 C1 violations are `UNEVALUATED`**
  (B, H, S); only G is caught. J is unevaluated benign. This is a narrow
  scope, not a C1 compliance claim.
- **M2, C2, audit: demonstrated offline detection capability within declared
  scope** (same scope). Catches 4 of 5; J (derived constant) is
  `UNEVALUATED`; B, H, S are unevaluated benign. No miss, no false block.
- **M2, C2, gate: demonstrated within declared scope on one instance** (T).
  One violation instance is not a basis for any broader statement.
- **M3, C3, audit: demonstrated offline detection capability within declared
  scope** (charter 4.1 template, whole-file audit, static structure only).
  Catches D, N, U; O is `UNEVALUATED`. `NO_VIOLATION` from M3 means a
  recognized fallback structure, not safe behavior.
- **M3, C3, gate: not demonstrated.** The only violation, U, is deletion-only
  and `UNEVALUATED`; the gate cannot see it. M3's C3 result stands for the
  audit only.
- **M0 (baseline): partial on C1, C2 and C3.** C1 misses G, H and false-blocks
  E, R; C2 misses all five; C3 misses all three. Unevaluated: none (the
  shipped check reports a complete PASS for forms it has no rule for).
- **M4 (post-mutation reference): partial on C1** (misses S with the switch
  unset; catches it with the switch enabled), complete on C2 and C3 for these
  fixtures. M4 runs after mutation and executes code; it is a measurement
  reference, not a candidate pre-execution method.

## Residual list

1. C1 disabled through a call (`float("inf")`, H): no static method catches it.
2. C1 disabled through a configuration switch read from the environment (S):
   only M0's context-free literal match catches it, and only because the
   switch's name contains the forbidden literal. A switch with any other name
   would be missed by M0 and M1 and unevaluated by M2.
3. C1 disabled through a conditional expression on a code flag (B): caught by
   M0 and M1 only because the flag is the literal; unevaluated by M2.
4. C2 bound derived from another constant (J): unevaluated by M2.
5. C3 fallback removed by pure deletion (U): visible only to a whole-file
   audit; never to the ADR-018 gate.
6. C3 fallback through a helper (O): unevaluated by M3 (benign, so no harm,
   but no pass either).
7. C2 and C1 for a call-site deadline that is not a literal or the declared
   constant: unevaluated by M2 (synthetic tests only; no frozen case).
8. Handler types other than `TimeoutError` and `Exception`: declared in the
   template (AMB-3) and unit-tested, but not measured by any frozen case. No
   coverage is claimed for `OSError`, `BaseException`, bare `except`, tuples
   or aliases.
9. Every result is on one visible, precommitted case set and one decision
   shape. Generalization is unmeasured.

## Owner rulings preserved

AMB-1 to AMB-10 are applied as ruled on #582: AMB-1 (C2 benign for disabled
deadlines means not separately assessed); AMB-2 (U deletion-only, gate vs audit
kept distinct); AMB-3 (handler type list declared, not validated); AMB-4
(M-5 and M-5.0001 scored as separate, digest-bound cases); AMB-5 (10
violating and 6 benign Set 1 instances, no cases added); AMB-6 (P benign for
ADR-001 only, not a general approval of broad catches); AMB-7 (F excluded
from denominators); AMB-8 (S enabled probe `"1"` only); AMB-9 (C and T not
independent audit evidence); AMB-10 (Q's value is arbitrary).

**Oracle digest limitation.** `oracle_v2.observe` trusts the caller-supplied
digest set. This runner builds that set with `run_freeze.frozen_digests()`
after `run_freeze.verify()` passes, so SHA validation holds only as a
property of this trusted offline workflow. It is not an independent sandbox or
security boundary of the oracle API, and the oracle must not be pointed at
arbitrary or agent-supplied content.

## Changes made after seeing results

- Before the runner existed, the detectors were run once over the frozen
  subjects to check that they executed. After that run, the detection logic
  was not changed. The only detector edits were a refactor (moving the shared
  `bindings` helper into `common.py`, renaming a local variable that shadowed
  it) and removal of a redundant `complex` check in M2's classifier that was
  already covered by `_is_number`. Verdicts were identical before and after.
- After a first full run, the runner's section 7 status label was refined
  from a binary "demonstrated or partial" to also distinguish "not
  assessable" (no violation instance) and "not demonstrated" (every violation
  unevaluated), because the binary label called the M3 gate result
  "demonstrated" with zero catches. Verdicts and counts did not change. A
  cross-check of M0 against the #570 CLI labels was also added.
- The M3 guard-clause allowance (`if <test>: return <expr>` before the classify
  site) was written from charter section 4.1, which places Set 0 case A in the
  `NO_VIOLATION` row; A was visible when it was written. It is the only
  recognition rule that admits a statement beyond the template.

## Recommendation

Results here support, at most, considering whether to charter a rule type.
The candidates the evidence points at are a token-aware literal type (M1:
removes the E and R false blocks but loses S) and a static bound type for a
declared deadline symbol (M2: no miss, no false block, but a large
`UNEVALUATED` share on C1). C3 detection is template-bound, audit-only and
structural (M3), and the gate cannot see deletion-only removals. Any rule type
would need its own ADR (ADR-019 section 9), a Layer 1 behavioral charter and
integration evidence under ADR-029. This is not a decision, and no ADR is
written here.
