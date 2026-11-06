# ADR-034 G1 numeric audit: local advisory experiment charter

**Status: CHARTER ACCEPTED (gate A).** Documentation only. Rulings O1 and O2
and the §4.2 constraint are accepted (owner ruling below). Merging this charter
makes it the reviewed protocol for one local, isolated experiment with the G1
whole-file numeric audit. It authorizes no change to any repository memory,
rule, workflow, ruleset, hook, CLI or ADR. Gate B (§8) needs the owner's
separate, explicit go-ahead.
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

**Revision direction (owner, 2026-11-06, on review of revision 1):** accept
O1 in principle with explicit isolation; O2 needs a narrower ruling, granted
as an explicit exception rather than a reinterpretation of the M4
restriction; observations from an unprotected audit memory must not be
presented as trustworthy enforcement evidence; "Run one local, isolated
advisory experiment with an existing numeric constraint and synthetic
inputs"; "Do not build the permanent advisory workflow yet."

**Gate A ruling (owner, 2026-11-06, on review of head `5d0dd3de`):** "Accept
O1 in principle and the narrow O2 exception for this local experiment only,
subject to selecting a qualifying constraint and completing PR review." The
§4.2 constraint was found appropriate: it is an existing documented
constraint, the matcher recognizes the module-level constant, and the
test-only environment override is excluded from the claim. "No CLI, hook,
canonical memory or required CI changes are needed."

## 1. Question

Does the M4-validated G1 audit (`mneme check --source-file`,
`FORBID_NUMERIC_ABOVE`, warn mode) give useful results on one real Mneme Core
constraint, when run locally from a memory that no enforcement surface reads,
and would that justify a persistent advisory workflow?

"Useful" is defined by the questions in §5.5. The charter does not ask whether numeric rules
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
Items marked **ruling** were decided by the owner at gate A (§8): both accepted.

### 3.1 A separate memory file is a supported input (finding)

ADR-020 §5 defines the policy root for "another explicitly supplied memory
file" as that file's parent directory; `mneme check --memory <path>` accepts
any path (`mneme/path_selectors.py`, `policy_root`). Inputs must resolve
inside that root, so the audit memory must sit at the root of the project it
governs (for the experiment, the disposable directory of §5.1). A file under a subdirectory would make that subdirectory the
policy root and every other path `PATH_APPLICABILITY_UNKNOWN`.

### 3.2 The required trusted gate does not read it (finding)

The pinned C4 adapter reads exactly `.mneme/project_memory.json` from the base
commit (`scripts/ci/adr033_c4_gate.py`, `MEMORY_REL`). A file elsewhere is
not an input to the gate's verdict. The gate's pinned evaluator (`0b74d410`)
classes numeric payloads as UNEVALUATED under the `closed` posture (C4 closure
§7), which is why the canonical memory must not carry the rule.

Side effect, relevant only to a future committed audit memory: a file outside
`.mneme/` and `.github/` is not protected by the gate, so any pull request
could edit it. This charter commits no audit memory (§3.5).

### 3.3 The hooks do not read it (finding, with one condition)

The Claude Code hook resolves memory from `MNEME_MEMORY` or by walking up to
`.mneme/project_memory.json` (`mneme/integrations/claude_code/hook.py`,
`find_memory`). An audit memory with any other name or location is never
discovered. **Condition:**
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
an ADR amendment. **Accepted** (owner, 2026-11-06), in principle, with the
isolation above.

### 3.5 Activation restriction: an explicit, narrow owner exception (ruling O2)

The M4 record lists "activation of `FORBID_NUMERIC_ABOVE` in any repository's
memory" as not authorized, and the Layer 1 freeze keeps the F2 restriction in
force. This charter does **not** reinterpret either restriction. Both stand
unchanged.

**O2 (owner):** grant one explicit exception, limited to the local experiment
in §5, on these terms:

- the numeric rule exists only in a disposable audit memory outside the
  repository, created for the experiment and deleted after it;
- no file in `MnemeHQ/mneme` gains a `FORBID_NUMERIC_ABOVE` rule, and
  `.mneme/project_memory.json` is untouched;
- no enforcement surface (required gate, hooks, Agent SDK, LangChain, MCP)
  reads the audit memory, and `MNEME_MEMORY` is never set to it;
- the exception ends when the results record (§8, gate B) merges.

A committed audit memory or any persistent workflow would need a new, separate
ruling. O2 does not cover it.

**Accepted** (owner, 2026-11-06) for this local experiment only, on the terms
above.

### 3.6 Determination

Conditional on O1 and O2, the separation is architecturally valid: the audit
memory is an explicitly supplied memory under ADR-020 §5, it is outside the
trusted gate's input and the hooks' discovery, and it holds no authority under
ADR-030/031. The canonical Decision Index and the trusted-input boundary are
unchanged. If either ruling is refused, the experiment does not run.

**Trust limitation.** An audit memory outside `.mneme/` is not protected by
the trusted gate (§3.2), and a local run has no host-event binding. Experiment
observations are therefore exploratory. They must never be presented as
trustworthy enforcement evidence, as an ADR-029 "relevant enforcement
observed" record, or as validation beyond M4.

## 4. Recognition scope

The experiment claims nothing beyond ADR-034's first slice:

- **Language:** Python `.py` files only, read whole from disk through
  `--source-file`.
- **Sources:** a module-level bare-name assignment to the declared `symbol`,
  and/or direct bare-name calls `function(...)` at the declared 0-based
  `position` (ADR-034 §2). Every declared source must be positively found
  (ADR-034 ruling O2): absence or ambiguity is `MATCHER_UNEVALUATED`, never a
  pass.
- **Values:** the recognized literal forms of ADR-034 §3 and §5a, compared
  against the exact authored decimal `max`, inclusive only.
- **Name resolution:** Python lexical scoping per §3a; indirect namespace
  rebinding is fail-closed.
- **Unevaluated by design:** keyword arguments, aliases, attribute calls,
  derived or computed constants, imported values, exclusive bounds, ranges,
  unit conversion, other languages.

### 4.1 Constraint selection

The experiment uses one constraint that:

1. restates a real constraint already recorded in Core (§3.4);
2. is expressible in the ADR-034 §2 contract, with its sources in recognized
   forms in the current code;
3. has narrow `include_paths`.

### 4.2 Selected constraint (accepted at gate A)

**Constraint:** the Claude Code hook's check timeout is at most 10 seconds.
It is documented in
[`docs/integrations/claude-code.md`](../integrations/claude-code.md) ("The
hook has a 10 s timeout and fails open on expiry") and implemented as the
module-level `_CHECK_TIMEOUT_SECONDS = 10` in
`mneme/integrations/claude_code/hook.py`. The Agent SDK, Antigravity and
Codex CLI integrations import the same constant.

**Contract** (ADR-034 §2, symbol only):

```text
- FORBID_NUMERIC_ABOVE:
    language: python
    symbol: _CHECK_TIMEOUT_SECONDS
    max: 10
    inclusive: true
    unit: seconds
    include_paths:
      - "mneme/integrations/claude_code/hook.py"
```

Canonical value:
`{"inclusive":true,"language":"python","max":"10","symbol":"_CHECK_TIMEOUT_SECONDS","unit":"seconds","v":1}`.

**Qualification run (2026-11-06, before gate A).** To confirm the baseline is
testable, and only that, one `--source-file` run used the §5.3 invocation on
a byte-identical copy of `hook.py` at `42ffdde5` (git blob `285ef854`,
SHA-256 `cb381e8c…8c5b`). It ran in a disposable directory outside the
repository, with `MNEME_MEMORY` unset. Result: exit 0, verdict `PASS`,
`evaluation_complete` true, rule `APPLIED`, governed path
`mneme/integrations/claude_code/hook.py`. No synthetic variant was run, and
the directory was deleted afterwards. This run is a selection check, not
experiment evidence.

**Known out-of-scope form.** `hook.py` also reads a test-only override,
`float(os.environ.get("MNEME_HOOK_CHECK_TIMEOUT_TEST", _CHECK_TIMEOUT_SECONDS))`.
That is not a declared source, and the audit does not see it. It is input for
§5.5 question 3.

## 5. Local experiment

### 5.1 Setup

- A disposable project directory outside the repository (for example a
  session scratch directory), holding the audit memory at its root and a
  `src/` tree.
- The audit memory carries only the §4.1 constraint, marked experimental and
  non-authoritative (§3.4).
- The CLI runs unmodified from a checkout of `main` at a recorded commit.

### 5.2 Inputs

1. **Baseline copy:** a byte-identical copy of the real file holding the
   constraint's sources, taken from the recorded `main` commit, with its
   SHA-256 recorded.
2. **Synthetic variants**, each a small edit of the baseline copy:
   - within the bound, at the bound, and above the bound;
   - each source in a recognized form and in an unrecognized form (for
     example a keyword argument, an alias, a computed value);
   - a declared source removed;
   - a shadowed or rebound name (§3a).

Each variant states its expected class (§5.4) before it is run.

### 5.3 Invocation

Exactly one form, for every input:

`python -m mneme.cli check --memory <audit memory> --source-file <file> --query <constraint label> --mode warn --json`

No `--input`, no `--target-path`, no `MNEME_MEMORY`.

### 5.4 Reporting of incomplete evaluations

Each input is reported in exactly one class:

| Class | Condition |
|---|---|
| `PASS` | exit 0, `verdict` PASS, `evaluation_complete` true |
| `FAIL` | `verdict` FAIL, `evaluation_complete` true |
| `FAIL_INCOMPLETE` | `verdict` FAIL, `evaluation_complete` false (M-a) |
| `INCOMPLETE` | `verdict` PASS, `evaluation_complete` false |
| `ERROR` | no parseable `mneme.check/v1` payload, or an operational error |

`INCOMPLETE`, `FAIL_INCOMPLETE` and `ERROR` are counted separately and are
never folded into `PASS`. Every non-`PASS` row records the numeric trace
outcome and reason.

### 5.5 Usefulness questions

The results record answers:

1. Does the baseline copy evaluate complete and `PASS`?
2. Do the within, at and above variants produce the expected classes?
3. Which realistic forms of the constraint fall outside the recognition scope,
   and how often does the real code base use them?
4. Is a persistent advisory workflow worth its cost: a `.github/` change by
   recorded bypass, an unprotected committed audit memory, and an observation
   period? Answer yes, no, or not yet, with reasons.

### 5.6 Stop rule

Stop and record the stop if any step would touch a file in the repository,
set `MNEME_MEMORY`, or require a CLI change.

## 6. Isolation invariants

1. `.mneme/project_memory.json` carries no `FORBID_NUMERIC_ABOVE` rule.
2. No file in the repository changes, except this charter and the results
   record.
3. The trusted gate's adapter, evaluator, ruleset, posture and memory input
   are unchanged.
4. No hook, settings file or workflow sets `MNEME_MEMORY` to the audit memory.
5. No CLI, matcher, enforcer, hook or ADR change is made.

## 7. Limitations

- Observations are exploratory (§3.6).
- One constraint in one code base, chosen by the owner; nothing generalizes.
- `--source-file` reads files from disk; it is not bound to a host event and
  gives no ADR-029 binding.
- Synthetic variants are authored with knowledge of the matcher, so they test
  the recognition scope, not blind detection.

## 8. Gates

| Gate | Content | Needs |
|---|---|---|
| A | This charter merged, with rulings O1 and O2 and the §4.2 constraint accepted (accepted 2026-11-06) | owner |
| B | Local experiment run (§5), a results record answering §5.5, and the disposable directory deleted | owner go-ahead after A |

Any persistent advisory workflow, committed audit memory or observation period
is outside this charter. If the §5.5 answer is "yes", it needs its own short
proposal and authorization.

## 9. Claims

On completion, the most the experiment can support is: *for one restated
constraint, the G1 audit classified the baseline copy and these synthetic
variants as recorded.*

Not claimed: enforcement, blocking, pre-write protection, CI numeric
enforcement, ADR-029 relevant enforcement, trustworthy enforcement evidence,
generalization to other rules or repositories, or any change to G2-1, R3 or
M4 outcomes.

## 10. Not authorized

- Any change to `.mneme/project_memory.json`, the trusted gate, rulesets, the
  posture variable, hooks, CLI, matcher or ADRs.
- A committed audit memory, an advisory workflow, or an observation period.
- Reinterpretation of the M4 or Layer 1 freeze activation restrictions beyond
  the O2 exception.
- G2-1 blocking activation, CI numeric enforcement, evaluator re-pinning, and
  R4.
