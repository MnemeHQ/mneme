---
id: ADR-031
title: "Decision Governance Semantics: Effective Resolution, Governance Change, and Evidence Identity (DG1)"
status: proposed
priority: foundational
date: 2026-10-07
scope: decision_index.governance_semantics
---

# ADR-031: Decision Governance Semantics (DG1)

**Status:** Proposed
**Date:** 2026-10-07
**Deciders:** Theo Valmis

---

## Context

D1 closed and shipped in `mneme-hq==0.10.0` (ADR-030, [D1 closeout](../architecture/d1-closeout.md)).
The persisted `decision_index` section is now the single durable canonical
authority: immutable version occurrences, an active-version pointer, explicit
`supersedes` relationships, and stable ADR-030 §7 rule identity.

The roadmap's next core-model step is **DG1: decision governance semantics**.
DG1 must answer three questions deterministically:

1. **Effective resolution.** Given authoritative state S and a governance
   context C, which decisions govern C, which do not, and why?
2. **Governance change.** Given authoritative snapshots S1 and S2, what
   effective governance changed, why, and what deterministically known
   scope and rules are affected?
3. **Evidence identity.** For an effective decision, which canonical
   decision version and canonical rule produced a given applicability and
   evaluation outcome?

An earlier DG1 brief assumed a clean slate. Reconciling it against the code
shipped in 0.10.0 shows that several governance semantics **already exist**,
spread across import, persistence, projection and enforcement, and that some
of them conflict with the brief's principles. This ADR records that
reconciliation and fixes the decisions everything downstream depends on. It
changes no runtime behavior.

### What 0.10.0 already does

**Precedence exists, at import time.**
`adr_compiler.resolve_precedence_partial` applies, in order:

```text
status == accepted
    -> explicit supersedes removes targets
    -> group by exact ADR `scope` string
    -> within a group: higher `priority` wins
    -> priority tie: newer ADR `date` wins
    -> date tie: ambiguity (scope skipped, never guessed)
```

Different scopes coexist, and broader and narrower scopes coexist (the
output is ordered most-specific-first). Only an **exact same-scope group** is
reduced to one winner. The input is the ADR corpus being imported, so
precedence is never evaluated across writers (a `cli-add` decision and an
ADR that share a scope string both stay active today).

`build_canonical_index` persists a same-scope loser as
`lifecycle_status="inactive"`. `priority` is not a field of
`CanonicalDecisionRecord`, so the canonical index records the **outcome** of
precedence but not its **reason**. `inactive` also covers an explicitly
`proposed` ADR, so two different causes share one lifecycle value.

The lifecycle analyzer already treats this as suspect: it emits
`SILENT_PRECEDENCE_ELIMINATION` when precedence removes an ADR that claims
active status. The ADR import diagnostic tells authors to "change priority,
or change date" to resolve a tie, so date is a documented authority lever
today.

**Decision scope is a retrieval signal.** The ADR `scope` value becomes
canonical `context_scope` and runtime `Decision.scope`. `DecisionRetriever`
gives scope overlap its highest field weight (2.0). The same string is also
the import-time precedence group key. It has never been decision
applicability, and ADR-023 §5 forbids it from silently becoming rule
applicability.

**"Applicable" is already an MCP name.** `decision.applicable_to`
(ADR-027) is documented as retrieval/context applicability: opaque
case-insensitive substring matching over scope hints and context scope. It
performs no governance or typed-rule evaluation.

**Effectiveness is resolved once, at load.** Projection keeps
`lifecycle_status == "active"` and drops everything else (ADR-023 §6). The
same `status == "active"` test is repeated independently in protection
candidate selection, protection activation precheck, Audit aggregation and
readiness. While effectiveness equals "lifecycle is active", load-time
projection is sufficient because the answer does not depend on the file or
action being evaluated.

**Enforcement evidence still uses surrogate identity.** The runtime `Rule`
carries no canonical identity, and `RuleEvaluation` identifies a rule by
`decision_id` + `rule_index` + `rule_value`. ADR-029 §4 deferred durable
evidence identity to D1 and forbade committing these surrogates as public
evidence identity.

**Two rule-identity formats are served today.** The persisted index uses
ADR-030 §7 identity (`<decision_id>:<RULE_TYPE>:<sha256(value, applicability)[:32]>`)
with a `decision_version_id`. The Decision MCP's `--adr-dir` mode builds its
index through the D0 adapter (`build_canonical_index`), which emits
positional rule IDs (`<decision_id>:FORBID_LITERAL:<index>`) and empty
version IDs.

**Unknown persisted fields are silently carried.** Probed against 0.10.0
(pinned by `tests/test_dg1a_compatibility_characterization.py`):

| Change to a canonical document | 0.10.0 loader | 0.10.0 canonical writer |
|---|---|---|
| unknown key at document root, `decision_index` root, or a decision / version / rule row | accepted, ignored | preserved on rewrite |
| unknown `relationships[].type` | rejected | n/a |
| unknown `lifecycle_status` value | rejected | n/a |
| `schema` other than `mneme.decision-index/v1` | rejected | n/a |

A governance field added additively to v1 would therefore be loaded,
preserved and ignored by a 0.10.0 binary. That binary would compute a
different effective set while reporting success.

**There is no governance history.** Version occurrences are immutable, but
supersession rewrites the target's `lifecycle_status` in place, and there is
no decision or evidence log (ADR-029 §7, ADR-030 non-goals). Past effective
state cannot be reconstructed from the current file alone.

**Mneme's own corpus never exercises same-scope precedence.** The 22
accepted ADRs in `docs/adr/` occupy 22 distinct scopes, so no group ever
reaches the priority or date step.

---

## Decision

### 1. One governance semantic model, three outputs

DG1 defines one deterministic resolver. Effective resolution is its primary
output. Governance change and evidence identity are derived from it, not
reimplemented:

```text
authoritative state S + GovernanceContext C
        |
        v
resolve_effective(S, C) -> EffectiveDecisionSet + ResolutionTrace
        |
        +--> resolve_change(S1, S2, C): compare resolve_effective(S1, C)
        |                               with resolve_effective(S2, C)
        |
        +--> evidence identity: effective decision version -> canonical rule
             -> ADR-020 applicability -> outcome (ADR-029 dimensions)
```

No authoritative DG1 answer may depend on retrieval score, LLM output,
insertion or file order, wall-clock time, source format, or source
popularity. Where state cannot be reconciled deterministically, DG1 returns
an explicit ambiguity and never selects a winner.

### 2. Precedence: priority stays, date stops carrying authority

- **Exact same-scope grouping is retained** as the current precedence
  semantic for ADR imports. Different scopes and broader/narrower scopes
  continue to co-govern.
- **`priority` is explicit, author-supplied governance precedence** and is
  retained.
- **ADR `date` is not governance authority.** A same-scope, same-priority
  tie becomes an ambiguity reported through the existing
  `resolve_precedence_partial` path. It is never broken by date. Removing the
  date step changes ADR import behavior and therefore ships as its own slice
  (DG1P, §11) with release notes, not inside DG1A or the parity resolver.
  DG1P must not silently deactivate a currently active decision on
  re-import; a newly ambiguous scope fails closed with an explicit report.
- **Precedence stays an import-time authority operation.** The resolver
  does not re-run ADR precedence from sources. It consumes the outcome that
  the explicit import operation persisted. Persisting the precedence
  **reason** (priority, winner, group) is required so the resolver can
  explain a loss; that data is introduced only under the schema rule in §8.
- **Cross-writer same-scope precedence is not introduced.** A decision from
  one writer never displaces a decision from another by sharing a scope
  string. Any such semantic needs its own decision.

### 3. Lifecycle stays four states; causes live in the trace

The ADR-030 §11 lifecycle vocabulary (`active | superseded | deprecated |
inactive`) is unchanged. DG1 does not overload it further. Why a decision is
not effective is a **resolution cause** carried in the `ResolutionTrace`:

| Cause | Meaning | Available from |
|---|---|---|
| `lifecycle_superseded` | an explicit `supersedes` relationship targets it | v1 data |
| `lifecycle_deprecated` | lifecycle is `deprecated` | v1 data |
| `lifecycle_inactive` | lifecycle is `inactive`; the reason was not recorded | v1 data |
| `precedence_lost` | lost exact same-scope precedence, with winner and priority | first v2 slice (§8) |
| `not_applicable` | decision applicability excludes the context | DG1B1 |
| `waived` | an authoritative waiver applies to the context | DG1B2 |

Over v1 data the resolver reports `lifecycle_inactive` and never guesses
whether an inactive record was a proposed ADR or a precedence loser.

### 4. Three applicability layers stay separate

```text
retrieval relevance     context_scope / Decision.scope / MCP decision.applicable_to
                        "is this useful context?"            (unchanged)

decision applicability  new, explicit canonical concept (DG1B1)
                        "does this authoritative decision govern C?"

rule applicability      ADR-020 include_paths / exclude_paths
                        "does this rule apply to this path?" (unchanged)
```

`context_scope` never becomes decision applicability. When decision
applicability is introduced (DG1B1), an absent value means **globally
eligible**, so every 0.10.0 decision keeps its present behavior.

### 5. Terminology

DG1 uses **effective**, **governs**, `resolve_effective`,
`EffectiveDecisionSet`, `ResolutionTrace`, `resolve_change` and
`DecisionChangeSet`. It never uses "applicable" for governance resolution.
MCP `decision.applicable_to` keeps its ADR-027 meaning unchanged. Exposing
DG1 results through MCP is an addition to ADR-027's approved tool set and
requires its own decision.

### 6. GovernanceContext is small and local

```text
GovernanceContext
    paths   repository-relative paths, normalized under ADR-020 rules
    as_of   explicit instant; the resolver never reads the clock
    labels  optional opaque project-local strings
```

- `paths` are used only where a DG1 semantic explicitly defines path-based
  governance. The parity resolver (DG1C) ignores them and must be invariant
  to them.
- `as_of` is required only once a time-bound semantic exists (DG1B2
  waivers). Same state + same context + same `as_of` gives the same result.
- `labels` carry no identity, team, role, directory or organization meaning.
  RBAC, SSO, directory authority and enterprise policy stay outside DG1
  (roadmap DG1 boundary).

### 7. Resolution placement and the Layer 1 charter

DG1C, DG1E and DG1D add no context-dependent semantics. The resolver over v1
data must reproduce the load-time projection exactly, so retrieval and
enforcement behavior are unchanged.

Context-dependent governance (decision applicability, waivers) makes the
effective set a function of the file or action, so resolution moves from
load time into each evaluation. That changes which decisions reach
enforcement. Under the Layer 1 freeze ("no behavioral change to retrieval or
enforcement without an explicit charter amendment"), **DG1B1, DG1B2, and any
DG1F step that changes enforcement inputs each require a merged charter**
before implementation, following the freeze doc's amendment procedure and
the #318 precedent. This ADR does not grant that amendment.

### 8. Persisted DG1 data requires schema v2

Because 0.10.0 silently carries unknown fields (Context table), **no field
that changes or explains resolution is added to `mneme.decision-index/v1`**.

- DG1 persisted governance data ships under `mneme.decision-index/v2`. A
  0.10.0 binary refuses a v2 document at load instead of misresolving it.
- The v1 to v2 transition is an explicit migration command, following
  ADR-030 §1's single-transition rule: no canonical writer migrates
  implicitly, and there is no repair.
- v2 is introduced once, by the first slice that needs persisted DG1 data,
  and carries every DG1 field known at that point (precedence reason,
  applicability, waiver slots), to avoid serial schema bumps.
- Release notes for that release state that binaries at or below 0.10.x
  cannot read v2 memory, as the 0.10.0 notes did for 0.9.2.

### 9. Governance change is snapshot-based

```text
resolve_change(before_snapshot, after_snapshot, context?) -> DecisionChangeSet
```

- Inputs are two complete canonical documents supplied by the caller (for
  example `project_memory.json` at two git revisions). Each must load under
  the same validation as any canonical read.
- DG1 compares supplied states. It never reconstructs history it was not
  given and adds no decision or event log.
- Change kinds are derived only by comparing the two resolver outputs:
  became effective, became ineffective (with cause), effective version
  changed, rule set changed, resolution cause changed, and (once DG1B1
  lands) governed scope changed.
- "Affected" is limited to what is mechanically known: decision IDs,
  version IDs, rule IDs and, where a context is supplied, its paths.
  Downstream organizational impact is out of scope.

### 10. Evidence identity

- The durable evidence identity chain is
  `decision_id -> decision_version_id -> rule_id` (ADR-030 §7 form) ->
  ADR-020 applicability -> subject -> outcome. This fills ADR-029 §4's
  deferred identity slots. ADR-029 §1-§6 semantics are unchanged.
- `rule_index` and `rule_value` may remain as display fields. They are never
  evidence identity.
- Evidence identity exists only where the authority carries it.
  Section-less memory (which 0.10.0 still loads, for example
  EventCatalog-bearing memory) has no canonical identity, so binding fails
  closed at ADR-029 dimension 3/4 and never upgrades to relevant
  enforcement observed.
- The D0 adapter's positional rule IDs are surrogates of the same class as
  `rule_index`. DG1E must either compute ADR-030 §7 identity in that path or
  mark its IDs as non-evidence identity. In both cases `--adr-dir` mode has
  no `decision_version_id`, so its evidence binding fails closed.
- **Evidence is current-run only.** No evidence store is added (ADR-029 §7).
  DG1 answers "what did this run evaluate, under which canonical decision
  version and rule"; it cannot answer "has this decision ever been observed
  enforcing", and no DG1 surface may imply it can.

### 11. Slice sequence

```text
DG1A  this ADR + roadmap/architecture wording        no behavior change
  |
DG1C  resolve_effective over v1 semantics only       no behavior change
      gate: effective set == load-time projection for every fixture
  |
DG1E  canonical identity through projection and      verdicts unchanged
      RuleEvaluation / Violation; ADR-029 binding    additive output only
  |
DG1D  resolve_change over two supplied snapshots     no behavior change
  |
DG1P  remove date as precedence authority            ADR import change
      (no schema change)                             release notes
  |
DG1B1 decision applicability (first v2 slice)        charter required
  |
DG1B2 exceptions / waivers                           charter required
  |
DG1F  surfaces consume one governance result         charter where enforcement
                                                     inputs change
  |
DG1G  adversarial fixtures + closeout
```

DG1B1 and DG1B2 are **evidence-gated**: each starts only with a concrete
repository or design-partner case that needs it. DG1C, DG1E and DG1D deliver
useful explanation, change and evidence answers on today's data without new
authority surfaces.

DG1F replaces the duplicated `status == "active"` checks (projection,
protection candidate selection and activation precheck, Audit aggregation,
readiness) with the shared resolver result, only after DG1C parity holds.
Retrieval ranking never becomes authoritative.

### 12. Waiver slot (semantics fixed now, implementation deferred)

So later work (DG2, O1A bridge) cannot invent incompatible exception
semantics, a waiver is fixed now as: an authoritative canonical object that
targets a decision (or decision version), is created only by an explicit
Mneme authority operation obeying ADR-030's writer discipline (verify before
mutate, atomic write, no repair, no implicit migration), has its own
lifecycle and provenance, is bounded by decision-applicability-style scope
and optionally by time evaluated only against `GovernanceContext.as_of`, and
**never mutates or deletes** the decision it targets. A decision under an
applicable waiver stays authoritative and is reported as not effective for
that context with cause `waived`. Producers (MCP, O1A, discovery) can never
create waivers (ADR-027).

### 13. DG1G fixture floor

DG1 closes only when deterministic fixtures pin at least: 0.10.0 parity;
different-scope co-governance; broader/narrower coexistence; same-scope
priority resolution; same-scope ambiguity (no date tiebreak, after DG1P);
supersession; lifecycle exclusion with honest `lifecycle_inactive` cause;
input-order invariance; irrelevant-decision invariance; context-path
invariance for the parity resolver; canonical rule identity through
enforcement; section-less fail-closed evidence; configured versus
execution-observed evidence (ADR-029 §6); and snapshot A to B change
explanations. Applicability and waiver fixtures (including expiry at an
explicit `as_of` and out-of-scope waivers) are added with their slices.

---

## Explicit non-goals

DG1 does not introduce: cross-repository federation (DG2); organization-wide
identity, RBAC/SSO or directory-based authority inference; hosted or
multi-tenant governance; an evidence store, decision log or event transport;
cross-system reconciliation or semantic auto-merge; LLM precedence or waiver
resolution; new rule types or a policy language; MCP tool additions (needs an
ADR-027 decision); changes to retrieval scoring, ADR-020 rule applicability,
Audit tier formulas (ADR-026) or frozen benchmark fixtures.

---

## Consequences

### Positive

- The governance semantics 0.10.0 already applies become explicit,
  explainable and shared instead of implied by import order and scattered
  `active` checks.
- Explanation, change and evidence-identity answers arrive before any new
  authority surface (DG1C, DG1E, DG1D).
- Removing date authority aligns import behavior with the deterministic
  principle the lifecycle analyzer already enforces as a warning.
- The schema-v2 rule turns a silent misresolution risk in older binaries
  into an explicit refusal.

### Negative / accepted trade-offs

- DG1P changes ADR import: a corpus that today resolves a same-priority tie
  by date will report ambiguity after DG1P. Authors must mark one ADR
  superseded or change priority. Mneme's own corpus is unaffected.
- Over v1 data the resolver cannot explain why an `inactive` decision is
  inactive. That stays unrecorded until the first v2 slice.
- Schema v2 makes mixed 0.10.x and later binaries on one memory file
  incompatible once a project migrates.
- `--adr-dir` MCP mode cannot provide decision-version evidence identity.

---

## Open questions for review

1. **Date authority (§2).** This ADR removes date as a precedence
   tiebreaker. The alternative is to accept date as an explicit,
   documented governance semantic and keep current import behavior. This is
   the highest-impact choice in the ADR and should be confirmed before
   acceptance.
2. **D0 adapter identity (§10).** Compute ADR-030 §7 rule identity in the
   `--adr-dir` path, or label its IDs as non-evidence identity.

---

## Related

- ADR-017 — Enforcement Scope Is Independent of Retrieval Scope
- ADR-020 — Explicit Path Applicability for Typed Rules
- ADR-023 — Canonical Decision Index and Runtime Projection Boundary
- ADR-026 — Audit Tier Semantics
- ADR-027 — Decision MCP Proposal Ingestion and Authority Boundary
- ADR-029 — Enforcement Evidence Binding Semantics
- ADR-030 — Canonical Decision Persistence, Version Identity, and Stable Rule Lineage
- [Layer 1 freeze](../architecture/layer1-freeze-e73ff7d.md) — amendment procedure
- [D1 closeout](../architecture/d1-closeout.md)
