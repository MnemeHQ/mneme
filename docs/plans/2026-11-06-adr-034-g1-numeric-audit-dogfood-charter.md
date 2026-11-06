# ADR-034 G1 numeric audit: warn-only dogfood charter

**Status: CHARTER PROPOSAL.** Documentation only. Merging this charter makes
it the reviewed protocol for deciding whether, and how, Mneme Core may dogfood
the G1 whole-file numeric audit. It authorizes no memory file, rule, workflow,
ruleset, hook, CLI or ADR change. Each gate in §9 needs the owner's separate,
explicit authorization.
**Date:** 2026-11-06.
**Repository:** `MnemeHQ/mneme`; Core baseline `42ffdde5` (#711).
**Governing decisions:** [ADR-034](../adr/ADR-034-static-numeric-upper-bound-typed-rule.md)
§§2-3, 6-7; [ADR-020](../adr/ADR-020-explicit-path-applicability-for-typed-rules.md)
§5; [ADR-030](../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md);
[ADR-031](../adr/ADR-031-decision-governance-semantics.md);
[ADR-033](../adr/ADR-033-opt-in-fail-closed-enforcement.md);
ADR-029; [Layer 1 freeze](../architecture/layer1-freeze-e73ff7d.md) (F2
restriction, unchanged).
**Prior evidence:** M4 results [#628](../validation/adr-034-m4-heldout-scoring-2026-10-24.md)
(PASS, 12/12 gates, 161/161 cases); G2-1 R3 results #711 (FAIL); C4 closure
#682 §7; R0 closure #742 §5 and operating-status decision #743.

**Authorization (owner, 2026-11-06, Mneme Core conversation, recorded on the
owner's behalf):** "Draft a read-only G1 dogfood charter, not an
implementation PR. It should establish whether the accepted architecture
permits a separate, explicitly non-authoritative audit memory without
weakening the canonical Decision Index or trusted-input boundary. Only if that
separation is architecturally valid should the charter authorize a future
warn-only audit workflow using existing CLI flags. The charter should also
define the permitted Python recognition scope, how incomplete evaluations are
reported, and how the experiment remains isolated from the required gate and
blocking hooks." Decision recorded with it: "G1 dogfood remains a candidate,
not authorized for activation. G2-1, CI numeric enforcement and R4 remain
deferred."

## 1. Question

Is the M4-validated G1 audit (`mneme check --source-file`,
`FORBID_NUMERIC_ABOVE`, warn mode) operationally useful on Mneme Core's own
pull requests, when run from a memory that no enforcement surface reads?

"Useful" is measured in §7. The charter does not ask whether numeric rules
should be enforced, and its outcome cannot support any enforcement claim.

## 2. Evidence basis

### 2.1 What is validated

M4 validated the pinned G1 Python whole-file audit on a synthetic corpus
(implementation `f25f0e84`). Its claim scope excludes pre-write protection, CI
enforcement, real repositories and production use, and its record lists
"activation of `FORBID_NUMERIC_ABOVE` in any repository's memory" as not
authorized. G2-1 pre-write blocking has no passing blind run (R1, R2, R3 all
FAIL).

### 2.2 CLI compatibility probe (2026-11-04, `main` at `42ffdde5`)

A read-only probe ran on a disposable synthetic project outside the
repository, comparing a literal-only memory with the same memory plus one
`FORBID_NUMERIC_ABOVE` rule scoped to `src/**`. All runs in `--mode warn`:

| Invocation | Literal only | Literal + numeric |
|---|---|---|
| `--input docs/clean.md` | exit 0, PASS | exit 2, INCOMPLETE |
| `--input docs/literal.md` (literal violation) | exit 0, FAIL | exit 2, FAIL (evaluation incomplete) |
| `--input src/clean.py`, with or without `--target-path` | exit 0, PASS | exit 2, INCOMPLETE |
| `--input docs/clean.md --target-path docs/clean.md` | exit 0, PASS | exit 0, PASS (numeric rule EXCLUDED) |
| `--input docs/literal.md --target-path docs/literal.md` | not run | exit 0, FAIL |
| `--source-file src/clean.py` (within bound) | exit 0, PASS | exit 0, PASS, evaluation complete |
| `--source-file src/over.py` (above bound) | exit 0, PASS | exit 0, FAIL |

Findings:

1. `--input` without `--target-path` is intentionally never clean when a
   numeric rule is in memory (ADR-034 F-1, pinned by
   `test_f1_input_without_target_path_is_never_clean`). This is a fail-closed
   property. **No CLI change is justified.**
2. `--source-file` is the supported, complete G1 path for in-scope `.py` files.
3. `--input` with `--target-path` keeps literal evaluation intact outside the
   numeric rule's scope.
4. Core's advisory [`mneme-check.yml`](../../.github/workflows/mneme-check.yml)
   uses bare `--input`. If a numeric rule entered the canonical memory, every
   in-scope row would become `UNKNOWN`, including literal FAILs.

CLI compatibility is resolved. Activation safety is not: the required trusted
gate and the hooks consume the canonical memory (§3.2, §3.3).

## 3. Architecture determination

Each item below is a finding against the merged code and ADRs at `42ffdde5`.
Items marked **ruling** need the owner's decision at gate B (§9).

### 3.1 A separate memory file is a supported input (finding)

ADR-020 §5 defines the policy root for "another explicitly supplied memory
file" as that file's parent directory; `mneme check --memory <path>` accepts
any path (`mneme/path_selectors.py`, `policy_root`). Inputs must resolve
inside that root, so a memory meant to govern repository paths must sit at the
repository root. A file under a subdirectory would make that subdirectory the
policy root and every other path `PATH_APPLICABILITY_UNKNOWN`.

### 3.2 The required trusted gate does not read it (finding)

The pinned C4 adapter reads exactly `.mneme/project_memory.json` from the base
commit (`scripts/ci/adr033_c4_gate.py`, `MEMORY_REL`). A file elsewhere is
not an input to the gate's verdict. The gate's pinned evaluator (`0b74d410`)
classes numeric payloads as UNEVALUATED under the `closed` posture (C4 closure
§7), which is why the canonical memory must not carry the rule.

Side effect: because the file is outside `.mneme/` and `.github/`, the gate
does not protect it. Any pull request can edit the audit memory. This is
acceptable only because the audit is advisory, and it is recorded as a
limitation (§8).

### 3.3 The hooks do not read it (finding, with one condition)

The Claude Code hook resolves memory from `MNEME_MEMORY` or by walking up to
`.mneme/project_memory.json` (`mneme/integrations/claude_code/hook.py`,
`find_memory`). A root-level audit file is never discovered. **Condition:**
`MNEME_MEMORY` must never point at the audit memory, in any workflow, hook
configuration or documented setup. With that condition, the Layer 1 freeze F2
consequence (closed-availability edits refused on APPLIED numeric paths) is
not triggered.

### 3.4 Authority: the audit memory is not a decision source (ruling O1)

ADR-030 and ADR-031 make the `decision_index` section of
`.mneme/project_memory.json` the single authoritative decision set. An audit
memory therefore cannot be a second source of project decisions. The charter
proposes that it is permissible only as a **non-authoritative experimental
input**, with all of the following:

- its name and `meta.description` state that it is experimental and
  non-authoritative;
- its decision text restates an architectural constraint that already exists
  in the canonical memory, an accepted ADR, or code documented as a
  constraint; it introduces no new decision;
- no MCP server, Audit, retriever, import or export path reads it;
- audit results are observations, never governance verdicts, and are never
  cited as ADR-029 "relevant enforcement observed".

**O1 (owner):** accept a non-authoritative audit memory on these terms without
an ADR amendment. Recommended: accept. Alternative: require a `proposed` ADR
carrying the contract first (heavier; adds no isolation).

### 3.5 Is this "activation"? (ruling O2)

The M4 record and the Layer 1 freeze restrict *activation* of
`FORBID_NUMERIC_ABOVE`. Their stated concern is enforcement surfaces: the edit
gate under closed availability (F2) and enforcement claims. Under §3.2 and
§3.3, no enforcement surface reads the audit memory.

**O2 (owner):** rule that a numeric rule in the non-authoritative audit
memory, read only by the advisory audit workflow, is **not** activation under
the M4 record or F2. Recommended: so rule, recorded in the gate C PR, with no
`[layer1-freeze]` amendment. If the owner rules otherwise, gate C needs a
`[layer1-freeze]` amendment first.

### 3.6 Workflow changes (finding)

A new workflow file lives under `.github/`, which the required gate refuses.
Gate D therefore needs the R0 §5.2 recorded human bypass, as for #485.

### 3.7 Determination

Conditional on O1 and O2, the separation is architecturally valid: the audit
memory is an explicitly supplied memory under ADR-020 §5, it is outside the
trusted gate's input and the hooks' discovery, and it holds no authority under
ADR-030/031. The canonical Decision Index and the trusted-input boundary are
unchanged. If either ruling is refused, the dogfood stops at gate B.

## 4. Recognition scope

The audit claims nothing beyond ADR-034's first slice:

- **Language:** Python `.py` files only, read whole from disk through
  `--source-file`.
- **Sources:** a module-level bare-name assignment to the declared `symbol`,
  and/or direct bare-name calls `function(...)` at the declared 0-based
  `position` (ADR-034 §2). Every declared source must be positively found
  (O2 of ADR-034): absence or ambiguity is `MATCHER_UNEVALUATED`, never a pass.
- **Values:** the recognized literal forms of ADR-034 §3 and §5a, compared
  against the exact authored decimal `max`, inclusive only.
- **Name resolution:** Python lexical scoping per §3a; indirect namespace
  rebinding is fail-closed.
- **Unevaluated by design:** keyword arguments, aliases, attribute calls,
  derived or computed constants, imported values, exclusive bounds, ranges,
  unit conversion, other languages.

### 4.1 Rule selection criteria (applied at gate C)

The rule chosen for the dogfood must:

1. restate a real constraint already recorded in Core (§3.4);
2. be expressible in the §2 contract with its sources in recognized forms in
   the current code, so that a clean run is `PASS` with evaluation complete;
3. have narrow `include_paths` covering only the files that hold the
   declared sources;
4. be confirmed by a disposable `--source-file` run on the gate C head,
   with the result recorded in the gate C PR.

An illustrative candidate is the hook's `_CHECK_TIMEOUT_SECONDS` in
`mneme/integrations/claude_code/hook.py`. It is not selected by this charter.

## 5. Proposed audit workflow (gate D design)

- A **new, separate** workflow file. `mneme-check.yml` and
  `mneme-trusted-gate.yml` are not modified.
- Trigger `pull_request` on `main`; permissions `contents: read`,
  `pull-requests: write` (sticky comment only).
- Selects changed `.py` files matching the audit rule's `include_paths`; for
  each, runs
  `python -m mneme.cli check --memory <audit memory> --source-file <file> --query <PR title + path> --mode warn --json`.
  No other invocation is used. Files outside scope are not checked.
- Never sets `MNEME_MEMORY`.
- Every step is non-blocking: exit codes 0 and 2 are both recorded, and the
  job never fails because of a verdict.
- **Not** added to `mneme-ci-gate` or any ruleset, and never a required check.

### 5.1 Reporting of incomplete evaluations

Each checked file is reported in exactly one row with these classes:

| Class | Condition |
|---|---|
| `PASS` | exit 0, `verdict` PASS, `evaluation_complete` true |
| `FAIL` | `verdict` FAIL, `evaluation_complete` true |
| `FAIL_INCOMPLETE` | `verdict` FAIL, `evaluation_complete` false (M-a) |
| `INCOMPLETE` | `verdict` PASS, `evaluation_complete` false |
| `ERROR` | no parseable `mneme.check/v1` payload, or an operational error |

`INCOMPLETE`, `FAIL_INCOMPLETE` and `ERROR` are counted separately and are
never folded into `PASS`. The comment shows the numeric trace outcome and
reason for every non-`PASS` row. The summary heading states that the audit is
advisory and non-authoritative.

## 6. Isolation invariants

These hold throughout. Any breach is a stop rule (§7.2).

1. `.mneme/project_memory.json` carries no `FORBID_NUMERIC_ABOVE` rule.
2. The trusted gate's adapter, evaluator, ruleset, posture and memory input
   are unchanged.
3. No hook, settings file or workflow sets `MNEME_MEMORY` to the audit memory.
4. The audit workflow is not a required check.
5. No CLI, matcher, enforcer, hook or ADR change is made for the dogfood.

## 7. Observation and usefulness

### 7.1 Observation window and measures (gate E)

The window is fixed at gate E as a number of in-scope pull requests or a
period, whichever comes first (recommended: 20 in-scope PRs or 4 weeks).
Recorded per run: the class counts of §5.1, run time, and the trace reason for
every non-`PASS`. Recorded per FAIL: whether the owner confirms it as a true
violation. The question in §1 is answered from:

- the incomplete rate (`INCOMPLETE` + `FAIL_INCOMPLETE` + `ERROR` over all
  rows);
- confirmed versus disputed FAILs;
- whether any finding changed a pull request.

No threshold turns these into an enforcement claim.

### 7.2 Stop rules

Stop the experiment and record the stop if:

- any §6 invariant is breached;
- the audit workflow affects the required gate's result or any merge;
- the audit memory is edited outside a reviewed PR that names this charter.

## 8. Limitations

- The audit memory is unprotected by the trusted gate (§3.2); its contents are
  trusted only as far as PR review.
- Results come from one rule in one repository, chosen by the owner; they do
  not generalize.
- `--source-file` reads the PR head's files from disk; it is not bound to a
  host event and gives no ADR-029 binding.
- The workflow runs on `pull_request`; fork PRs and first-time contributors are
  not considered.

## 9. Gates

| Gate | Content | Needs |
|---|---|---|
| A | This charter merged | review |
| B | Rulings O1 (§3.4) and O2 (§3.5) | owner |
| C | Rule selection (§4.1) and the audit memory file at the repository root, in a PR that does not touch `.mneme/` | owner authorization after B |
| D | Audit workflow file (§5), merged by recorded bypass (§3.6) | owner authorization after C |
| E | Observation window (§7.1) | owner authorization after D |
| F | Results record with the §7 measures; workflow and audit memory removed or kept by owner decision | owner |

## 10. Claims

On completion, the most the dogfood can support is: *on Mneme Core pull
requests during the window, the G1 audit of one restated constraint produced
these class counts and these owner-confirmed findings.*

Not claimed: enforcement, blocking, pre-write protection, CI numeric
enforcement, ADR-029 relevant enforcement, generalization to other rules or
repositories, or any change to G2-1, R3 or M4 outcomes.

## 11. Not authorized

- Any change to `.mneme/project_memory.json`, the trusted gate, rulesets, the
  posture variable, hooks, CLI, matcher or ADRs.
- The audit memory file, the rule, the workflow, or the observation window
  (gates C to E).
- G2-1 blocking activation, CI numeric enforcement, evaluator re-pinning, and
  R4.
