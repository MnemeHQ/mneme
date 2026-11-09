# DG1F-C2: lifecycle-authority consolidation charter

**Status: PROPOSED.** Behavioral charter for a **preparatory** DG1F increment.
C2 consolidates lifecycle authority; it **does not complete** ADR-031 §11
runtime convergence on the shared resolver result, which stays open (§2). On
merge it defines the contract and acceptance evidence for C2. **It authorizes
no implementation by itself.** Implementation also needs a separate
`[layer1-freeze]` amendment (§7), which has its own review and approval.
**Architecture anchor:** `MnemeHQ/mneme` `main` at `23f022c9` (ADR-031 erratum
#763), on top of `v0.11.0` (`619d5405`).
**Basis:** [DG1 v0.11.0 architecture reconciliation](../validation/dg1-v0110-architecture-reconciliation-2026-11-08.md)
(#762), including its independent review (§10).
**Governs:** the C2 increment only. Not C1b, DG1B2, DG1G or any change to which
decisions reach enforcement.

## 1. Governing authority and starting behavior

- [ADR-031](../adr/ADR-031-decision-governance-semantics.md) §11 says DG1F
  replaces the duplicated `status == "active"` checks (projection, protection
  candidate selection and activation precheck, Audit aggregation, readiness)
  with the shared resolver result, after DG1C parity holds. §7 requires a
  merged charter wherever a DG1F step changes enforcement inputs. Tracker
  [#497](https://github.com/MnemeHQ/mneme/issues/497) requires each consumer
  to be individually chartered and validated.
- The Layer 1 freeze forbids these surfaces from consuming the resolver result
  without a new amendment: the DG1B1 amendment
  ([`layer1-freeze-e73ff7d.md`](../architecture/layer1-freeze-e73ff7d.md),
  "Not authorized by this amendment") and the C1a amendment, which keeps that
  prohibition for every runtime consumer other than the C1a preview.
- **Starting behavior at the anchor** (verified in the reconciliation, §2/§4):
  - The lifecycle rule "only `active` governs" is written five times:
    projection `PROJECTABLE_LIFECYCLE_STATUSES` (`decision_projection.py:52`),
    the resolver `_EFFECTIVE_LIFECYCLE` (`decision_governance.py:83`), the
    shared Audit aggregator `_build_report` (`enforcer.py:1335`, used by
    `mneme audit`, readiness, `find_candidates` and `github_evidence.py:439`),
    protection candidates (`protection.py:170`) and precheck
    (`protection.py:212`), and CI evidence matching (`evidence.py:241`).
  - Only the dg1c parity tests keep projection and resolver equal.
  - On canonical memory the runtime checks never fire, because projection has
    already removed non-active decisions. They act only on section-less
    memory, where `Decision.status` comes from the file
    (`decision_index_persistence.py:328`) and the resolver refuses the memory.
  - `GovernanceContext(labels=())` is the default and cannot express "context
    not supplied", so a context-free resolver call reports applicability-scoped
    decisions as `not_applicable` while every enforcement surface applies them.

## 2. What C2 is

C2 is **preparatory lifecycle-authority consolidation, not a new enforcement
capability.** It makes one object the lifecycle authority, makes the resolver
safe for context-free use, and pins today's cross-surface behavior with golden
tests.

**C2 is not completion of ADR-031 §11.** §11 requires runtime consumers to
converge on the **shared resolver result**. Under C2, consumers share only the
lifecycle predicate the resolver also uses; they keep receiving
`list[Decision]` and never receive a `GovernanceResolution`. Eliminating
duplicated lifecycle logic is not decision-governance convergence:

- Full resolver-result convergence (protection, Audit, readiness, evidence and
  any CLI/agent/MCP consumer acting on `resolve_effective` output, including
  its causes, trace and applicability) **remains open** under tracker #497's
  "DG1F — other runtime consumer convergence" item.
- It needs its own charter and `[layer1-freeze]` amendment. Nothing in this
  charter or its freeze amendment authorizes it, and no C2 result may be cited
  as satisfying it.

**No verdict changes.** C2 changes no protection verdict, Audit count or tier,
activation candidate, precheck result or message, evidence match, readiness
count, `mneme check` / hook / CI / MCP output, or exit code. Duplicated code is
never removed by changing an observable result; where a check cannot be
converged without changing output, it stays as it is and is recorded.

## 3. Contract

### 3.1 One lifecycle authority

- Define the rule once, next to `VALID_LIFECYCLE_STATUSES` in
  `mneme/decision_index.py`: a frozen set of governing lifecycle statuses
  (`{"active"}`) and one predicate over a lifecycle/status string.
- **Projection** uses it. `PROJECTABLE_LIFECYCLE_STATUSES` stays as a public
  name bound to the same object, so importers see no change.
- **Resolver** uses it in place of `_EFFECTIVE_LIFECYCLE`.
- **Runtime consumers** use it in place of their literal checks:
  `enforcer.py:1335`, `protection.py:170`, `protection.py:212`,
  `evidence.py:241`. Readiness follows through `_build_report`.
- These consumers keep receiving `list[Decision]`. They **do not call
  `resolve_effective`**: it needs the canonical index, refuses section-less
  memory, and would add a second load path. Sharing the predicate is **not**
  consumption of the resolver result (§2); the freeze amendment (§7) must
  authorize predicate sharing only and say that resolver-result consumption
  stays prohibited.
- **Out of scope, unchanged:** ADR import and graph statuses (`adr_import.py`,
  `adr_lifecycle.py`, `adr_freshness.py`), the EventCatalog importer, and
  `availability_authority.py` activation state. They describe import-time
  graph or activation state, not runtime governance.
- `check_prompt` and `_enforcement_scope` gain **no** status filter (§3.3).

### 3.2 Three-state governance context

- `GovernanceContext.labels` distinguishes three states:
  - **not supplied** (`None`, the new default);
  - **supplied, no labels** (`()`);
  - **supplied, with labels**.
- When labels are **not supplied**, the resolver does not evaluate decision
  applicability. A lifecycle-eligible decision is **conservatively included**:
  applicability is unknown, so the decision is kept rather than excluded
  (ADR-031 §11). Its trace step is `applicability: context_not_supplied`.
- **Conservative inclusion is not proof of applicability.** A conservatively
  included decision that declares required labels has not been shown to apply
  to any context. The resolution must say so in data, not only in prose:
  `applicability_evaluated` is `false` for every decision, and no output,
  message or change set may present it as matched, applicable or governing a
  specific context. `resolve_change` keeps refusing to compare a not-supplied
  resolution with a supplied one.
- Each `DecisionResolution` gains a `lifecycle_eligible` field, filled
  regardless of context, and an `applicability_evaluated` field. The
  resolution records whether context was supplied.
- Supplied-context behavior (both supplied states) is unchanged.
- The C1a preview always supplies labels, so its output is unchanged.
- The resolver semantics id bumps (proposed
  `mneme.governance-semantics/dg1f-c2-1`). `resolve_change` already refuses to
  compare resolutions across semantics versions or contexts
  (`decision_governance.py:531-534`); that refusal stays and is tested.
- The default changes from supplied-empty to not supplied at the two resolver
  defaults (`decision_governance.py:234`, `:589`). This is a library-semantics
  change with no runtime consumer today; it is listed in the implementation PR
  and the release notes.

### 3.3 Legacy section-less memory

- Behavior is preserved exactly:
  - `Decision.status` keeps coming from the file;
  - `mneme check`, hooks and CI keep enforcing superseded and deprecated
    legacy decisions (reconciliation D-1);
  - Audit, protection and evidence keep excluding them, now through the shared
    predicate, with identical results.
- The resolver keeps refusing section-less memory. C2 adds no in-memory
  canonical view; that would touch ADR-031 §8 and ADR-030's no-implicit-
  migration rule and needs its own decision.
- The divergence is pinned by characterization tests, not fixed.

### 3.4 Integrity findings

- `supersession_lifecycle_conflict` and `dangling_supersedes` stay reported
  only. They never exclude a decision, never fail a consumer and never turn a
  result into an error.
- C2 consumers do not receive findings at all; they use the predicate.
- The C1a preview's rule (findings make the preview unavailable,
  `cli.py:518`) is C1a-authorized and unchanged.
- A resolver `ValueError` is never caught and turned into "no decisions".

### 3.5 Kept as-is and recorded

- `protect validate` on a superseded canonical decision keeps reporting
  "not found" (`cli.py:1145`), because projection removed it. C2 does not
  switch the lookup to the canonical index.
- Audit's `total_decisions` and `decisions` list keep including non-active
  legacy decisions for provenance (`enforcer.py:1383-1384`); only counts and
  tiers exclude them.

## 4. Required acceptance evidence

**Goldens first.** Before any production code changes, a separate commit
captures golden outputs from the anchor and the implementation must reproduce
them byte for byte.

| Consumer output | canonical v1 | canonical v2 + applicability | canonical + supersession conflict | canonical + dangling `supersedes` | section-less with superseded/deprecated | legacy `items[]` |
|---|---|---|---|---|---|---|
| `mneme audit` text and `--json` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `mneme protect list` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `mneme protect validate` (active, superseded, unknown id) | ✓ | ✓ | ✓ | ✓ | ✓ | n/a |
| `mneme protect status` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| readiness counts (setup) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `match_ci_evidence` incl. a shared selector across active + superseded | ✓ | ✓ | n/a | n/a | ✓ | n/a |
| `github_evidence` `_build_report` path | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `mneme check` text and `--json`, strict and warn | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `mneme check --applicability-preview` (stderr) | ✓ | ✓ | ✓ (UNAVAILABLE) | ✓ (UNAVAILABLE) | ✓ (UNAVAILABLE) | n/a |

**Negative and mutation tests** (each must fail if its guard is removed):

1. Applicability not dropped: under not-supplied context, an applicability-scoped
   decision is conservatively included with `context_not_supplied` and
   `applicability_evaluated = false`, and is never reported as `matched`;
   under supplied-empty it stays `not_applicable` (unchanged).
2. Findings never block: a conflict or dangling `supersedes` changes no
   consumer output.
3. Legacy D-1 preserved: a superseded section-less decision still FAILs
   `mneme check` and is still excluded from Audit counts.
4. Evidence ambiguity preserved: a superseded legacy decision sharing a selector
   with an active one does not make the selector ambiguous.
5. Single authority: projection, resolver and every runtime consumer read the
   same predicate object; a test that changes the governing set in one place
   changes all of them (and is reverted in the test).
6. No caught `ValueError`: a malformed index raises through every resolver
   entry point.
7. Cross-semantics refusal: `resolve_change` refuses a `dg1b1-1` resolution
   against a `dg1f-c2-1` one.

**Regression floor:** all existing DG1 tests (217 at the anchor, updated only
where §3.2's default change requires it, each update listed in the PR), the
full gate battery, and the frozen benchmark 7/7.

## 5. Explicit non-goals

C2 does not: change which decisions reach `check_prompt`, the retrieval-gated
tier, hooks, CI, MCP or `decision.applicable_to`; consume DG1B1 applicability
in any runtime path; add a context declaration, trusted context source, waiver,
schema field or semantic feature; change ADR-026 tier formulas, ADR-020 rule
applicability or frozen benchmark fixtures; fix legacy D-1; change the trusted
CI gate's evaluator pin (CI R0); or touch C1b, DG1B2 or DG1G.

## 6. Risks

| Risk | Control |
|---|---|
| A consumer output changes silently | goldens captured before code; byte comparison |
| Context-free resolution drops a protective decision | three-state context; test 1 |
| Legacy behavior "fixed" in passing | §3.3; test 3 |
| The default-context change surprises a library caller | listed in PR and release notes; no runtime caller today |
| The predicate becomes a second authority | it replaces all five copies; test 5 |
| C2 is mistaken for ADR-031 §11 completion | §2 and §7 keep resolver-result convergence open on #497; the freeze amendment authorizes predicate sharing only |
| Conservative inclusion read as "applies" | `applicability_evaluated = false`; never reported as `matched`; test 1 |

## 7. Approval sequence

1. This charter: review and merge. Authorizes nothing to run.
2. `[layer1-freeze]` amendment: a separate PR naming the C2 consumers,
   authorizing lifecycle-predicate sharing only (§3.1), the three-state
   context with conservative inclusion, and this evidence. It restates that
   resolver-result consumption by runtime consumers stays prohibited.
   Separate approval.
3. Goldens commit, then implementation PR, with independent review against §4.
4. Results recorded on tracker #497, with the §11 resolver-result convergence
   item left open. No DG1F or DG1 completion claim follows from C2.
