---
id: ADR-030
title: "Canonical Decision Persistence, Version Identity, and Stable Rule Lineage"
status: proposed
priority: foundational
date: 2026-09-16
scope: decision_index.persistence
---

# ADR-030: Canonical Decision Persistence, Version Identity, and Stable Rule Lineage

**Status:** Proposed
**Date:** 2026-09-16
**Deciders:** Theo Valmis

---

## Context

ADR-023 established the canonical Decision Index as Mneme's canonical decision
layer and the runtime `mneme.schemas.Decision` as its Layer 1 projection. D0
(ADR-023 validation, issue #358) proved the logical models and projection
parity but deliberately introduced no persistence: `CanonicalDecisionRecord`
is an in-memory view, and every production consumer still loads decisions
through `MemoryStore` / the ADR compiler path.

D2 (ADR-027) then shipped proposal ingestion and the accepted-proposal
authority path. Its D2C amendment recorded a bounded persistence choice:
accepted decisions are durably materialized as runtime-shaped entries in
`project_memory.json decisions[]`, and the canonical representation is
re-derived through the D0 adapter. That choice inverted ADR-023's intended
flow — the runtime ledger became the de-facto durable authority and the
canonical layer became derived — and it was explicitly recorded as bounded,
pending separately reviewed durable-canonical / runtime-loading work.

The consequences at the current architecture are concrete:

1. Accepted `ddec-*` decisions carry empty `CanonicalSourceEvidence`;
   producer provenance is reachable only through the proposal store.
2. ADR-imported decisions are typed `source_type="runtime"` by the generic
   adapter even when a verified `source{type, path, sha256}` block exists.
3. Canonical `rule_id` is position-derived
   (`<decision_id>:FORBID_LITERAL:<index>`), changes under unrelated rule
   reordering, and silently treats changed rule semantics at the same
   position as the same rule. ADR-029 §4 names these surrogates and bars
   them from becoming long-term public evidence identity until D1 settles
   canonical decision identity, decision versioning, and stable rule
   identity.
4. The Decision MCP serves canonical reads only from a supplied
   `--adr-dir`-derived index; accepted authoritative decisions are invisible
   to MCP consumers while remaining fully visible to Audit and enforcement.
5. Runtime-to-canonical adaptation loses relationships; producer
   `related_decision_ids` are proposal history only.

D1A — the architecture reconciliation completed against repository SHA
`6e5cf09b6a604b68d4610db82d9e7f83a681d99a` — resolved these boundaries.
This ADR records those conclusions as one bounded implementation decision
under ADR-023's contract. It introduces no new source adapters, no new rule
types, no MCP tool additions, and no enforcement-semantics change.

---

## Decision

### 1. One durable canonical authority

`project_memory.json` gains a versioned, schema-tagged top-level section
`decision_index` (`mneme.decision-index/v1`) which becomes the **sole durable
authority** for canonical architectural decisions.

- `mneme.schemas.Decision` remains the Layer 1 runtime projection required by
  ADR-023 §11. It does not become a second authority.
- `MemoryStore.decisions()` remains the compatibility API for all current
  runtime consumers (retrieval, enforcement, ConflictDetector, benchmark,
  Audit, protection). After migration, active canonical decision versions are
  projected into runtime `Decision[]` **in memory at load time** through the
  D0-proven projection path; no consumer code changes.
- A persisted legacy `decisions[]` representation may remain only during a
  bounded compatibility/deprecation window (as migration input, then as a
  derived, parity-verified snapshot for raw external readers and `[memory]`
  PR legibility). It is **never authoritative once `decision_index` exists**;
  its eventual removal is a separate, explicitly reviewed slice gated on a
  consumer inventory (D1F).
- No second canonical file, database, hosted service, ORM, graph database, or
  other persistence layer is introduced. One governed file preserves the
  single-writer atomic-write and reload-verify discipline D2C1 established
  and avoids the cross-file write-ordering hazard the ADR-027 D2C amendment
  deliberately avoided.

Only Mneme-owned, validated canonical write paths may write the
`decision_index` section. Producer and transport callers may never write it
directly or assert authority.

### 2. Legacy item migration

`MemoryStore` currently synthesizes runtime Decisions from legacy `items[]`
entries of type `rule` and `anti_pattern`. Those synthesized Decisions are
part of today's authoritative decision set (Audit, retrieval, enforcement
observe them), so they must enter the canonical index or the canonical and
runtime views diverge.

- Existing `items[]` entries remain preserved verbatim and forever as legacy
  MemoryItem/context data; the MemoryItem context pipeline
  (`hard_constraints()` injection) is unchanged.
- Their currently synthesized runtime Decision equivalents are migrated **once**
  into canonical decision records using the existing item IDs and the exact
  existing projected semantics (title-derived statement, content-derived
  constraint, anti-pattern field, `["general"]` scope, empty timestamps and
  status exactly as synthesized — parity is byte-level; nothing is invented).
- Once a valid `decision_index` section exists, the loader **must not**
  synthesize duplicate Decisions from those items. The legacy synthesis runs
  only when the section is absent, so pre-D1 memory files keep today's exact
  behavior (compatibility by section presence, not version sniffing).
- ID collisions between migrated items and existing canonical records fail
  closed; nothing is merged or overwritten.
- Migration is deterministic and idempotent: re-running is a byte-identical
  no-op.
- Flagged behavior change (release-noted, not hidden): after migration, new
  `rule`/`anti_pattern` items no longer synthesize Decisions; new decisions
  enter through explicit authority/ingestion paths.

### 3. Logical decision identity

Existing `decision_id` values remain unchanged. ADR frontmatter IDs, existing
runtime/memory IDs, explicit human-assigned IDs, and `ddec-*` IDs retain
their current identity. The D2C1 namespace rules (`dprop-` reserved,
proposal-id equality rejected) extend to all canonical writes, including
migration collision checks. No semantic or LLM-based identity matching is
introduced; identical- or similar-content identification remains a
human authority judgment.

### 4. Immutable decision-version occurrences

A logical canonical decision owns multiple immutable version occurrences.
Each version occurrence record carries:

- `version_id` — immutable occurrence identity;
- `content_digest` — deterministic digest of the immutable decision content
  (§6);
- `revision` — display/order metadata only, never identity, never used for
  resolution;
- frozen occurrence provenance (§10);
- immutable predecessor lineage (`supersedes_version_id`);
- occurrence timestamp — stored, excluded from identity.

Version occurrence identity:

```text
version_id = "dver-" + SHA-256(canonical_json([
    decision_id,
    content_digest,
    occurrence_source_identity,
    supersedes_version_id_or_sentinel
]))[:32]
```

- The existing 128-bit deterministic identity discipline is used (the same
  SHA-256 truncated to 32 hex as `dprop-`/`ddec-`), with pinned golden
  vectors.
- `occurrence_source_identity` is deterministic per authority path and uses
  no timestamps: for proposal acceptance, the already-pinned D2C1 identity
  inputs `[proposal_id, producer_key, content_fingerprint]`; for ADR import,
  `[decision_id, source_revision, "adr-import"]`; for legacy migration,
  `["legacy-items", decision_id]`.
- The first version uses a fixed no-predecessor sentinel (pinned literal).
- The explicit `active_version_id` on the logical decision is the **only**
  mechanism for resolving the active version. Timestamps, source modification
  times, source dates, and revision ordering may never resolve authority.
- Immutability is verified, not conventional: load-time re-derivation of
  `content_digest` and `version_id` must reproduce the stored values; a
  mismatch fails closed.

### 5. Occurrence retry/idempotency

Every authority operation that creates a version occurrence has an exact
**occurrence key**:

```text
(decision_id, content_digest, occurrence_source_identity, predecessor_version_id)
```

- A retry first resolves an already-persisted occurrence with that exact key
  and reuses it (idempotent no-op, no new occurrence).
- A retry **must not rederive the predecessor from the current active
  pointer** after a successful write: the predecessor is part of the recorded
  immutable occurrence key. After A1 → B, a retry of the A2 operation keys on
  B's `version_id` regardless of what is active at retry time, so a late
  retry can never create a phantom occurrence.
- This correctly represents and preserves:

  ```text
  A1 → B → A2
  ```

  as **three immutable occurrences** even when A1 and A2 have identical
  decision content and identical ADR source revisions: A1 keys on the
  no-predecessor sentinel, A2 keys on B. A1 and A2 share an equal
  `content_digest` but carry distinct `version_id`s and distinct frozen
  provenance. The full history is reconstructable from the persisted version
  records and lineage pointers alone — no event log.

### 6. Immutable decision content boundary

The immutable decision-version content consists only of organizational
decision intent:

- statement;
- rationale;
- decision/context scope;
- constraints;
- anti-patterns.

`content_digest` covers exactly these fields. Changing any of them requires
an explicit new version occurrence created by a Mneme authority action; no
process may silently mutate an existing version record.

The exact tiering:

**Tier 1 — immutable decision-version content** (in `content_digest`; change
⇒ new version): statement, rationale, decision/context scope, constraints,
anti-patterns.

**Tier 2 — immutable version-bound canonical entities/records** (not in
`content_digest`; separate canonical entities per ADR-023 §10):

- rules and rule applicability — separate canonical rule bindings (§7–§9);
  a change creates a new rule binding; an existing rule binding is never
  mutated. Rule bindings bind to the version active when derived/installed,
  with no silent carry-over across version creation;
- the version's provenance snapshot — frozen at occurrence write;
- version lineage (`supersedes_version_id`) — fixed at occurrence write;
- version `created_at` — fixed at occurrence write; excluded from identity.

**Tier 3 — authority-gated decision-level metadata** (mutable at the logical
decision; never rewrites any version record):

- declared test evidence (ADR-024 linkage added later);
- later source-provenance observations (append-only, referencing the
  `version_id` they describe; never rewrite the frozen snapshot);
- relationships (`supersedes`, decision-to-decision);
- lifecycle status;
- the active-version pointer;
- `updated_at`.

**Prohibited:** in-place mutation of any Tier 1 or Tier 2 record; rewriting a
rule binding's content; rewriting a provenance snapshot; deriving identity
from any timestamp.

Rules are not part of the decision content digest. Declared test evidence,
lifecycle state, relationships, later provenance observations, active-version
resolution, and operational timestamps must not silently mutate immutable
version content.

### 7. Canonical rule identity

Rules remain separate canonical entities as required by ADR-023 §4/§10.
Stable rule identity:

```text
rule_id = <decision_id>:<RULE_TYPE>:<SHA-256(canonical_json([value, applicability]))[:32]>
```

- The 128-bit hash length is deliberate: `rule_id` is already externally
  observable through MCP output (`rule_to_transport`,
  `derived_rule_ids`), participates in fail-closed
  `derived_rule_ids` integrity checks, and becomes a component of future
  ADR-029 evidence identity. It uses the same SHA-256/32-hex discipline as
  `dprop-`/`ddec-`/`dver-`; it is not truncated further.
- `rule_id` is independent of order and stable across decision versions when
  rule semantics (value and applicability) are unchanged. An unchanged rule
  carried into a new decision version keeps its `rule_id`.
- A changed rule value or applicability creates a different `rule_id`;
  changed semantics is never silently the same rule, and the old `rule_id`
  retires with the old version's rule set.
- Duplicate identical rule bindings within one version fail closed; no
  positional or suffix disambiguation exists.
- The D0 positional ID format (`<decision_id>:FORBID_LITERAL:<index>`) is
  superseded; migration assigns stable IDs deterministically from existing
  content with golden-vector pinning (§13).
- The `decision_id` prefix scopes rule identity; a bare content hash is
  rejected because lineage must be unambiguous.

### 8. Exact rule/version lineage

Every canonical rule binding identifies:

- `decision_id`;
- `decision_version_id`;
- `rule_id`;
- immutable per-version `sequence` (§9);
- rule payload (`value` plus type semantics);
- applicability (ADR-020 selectors).

The identity-grade historical binding used later by ADR-029 is:

```text
(decision_id, version_id, rule_id)
```

It names the exact historical rule instance: which logical decision, which
immutable version occurrence, which rule. The runtime's positional
`rule_index` + `rule_value` surrogates resolve to this tuple through the
canonical index — the slot ADR-029 §4 reserved.

Existing public `version` / `decision_version` values remain
revision/display fields for backwards compatibility and are **not**
identity-grade identifiers. `decision_version_id` is additive.

### 9. Rule ordering versus identity

Rule identity and ordering are separate.

- Each rule binding carries an immutable per-version `sequence` used **only**
  for runtime/protocol presentation order. Sequence carries no identity
  weight.
- `derived_rule_ids(version)` is a **read-time projection** over the canonical
  rule bindings bound to that `decision_version_id`, ordered by `sequence`
  ascending. It preserves the D0 derived-order semantics and is **not
  persisted** inside the immutable decision-version record.
- Runtime `Rule[]` projection uses the same sequence ordering, so existing
  positional `rule_index` behavior in enforcement, ConflictDetector, and
  protection traces remains byte-identical.
- Reordering an otherwise unchanged rule in a new decision version changes
  only that version's sequence binding; the stable `rule_id` does not change.
- Protection installation assigns the next deterministic sequence position
  (max existing sequence for that version + 1) and writes only a canonical
  rule binding. It **must not** mutate the owning immutable decision-version
  record, its `version_id`, or its `content_digest`; no existing sequence
  position is rewritten.
- Malformed, duplicate, or ambiguous sequence values — duplicate positions
  within one version, malformed values, bindings that do not resolve
  consistently to their claimed decision/version, or any ordering
  non-determinism — fail closed at load and are never repaired.

### 10. Provenance

Canonical decision versions carry a **minimal frozen provenance snapshot**
sufficient to satisfy ADR-023 §8 first-class provenance (source type,
locator, revision, observation time, verification status where honestly
known) without requiring the proposal store to interpret basic lineage:

- Accepted proposals: the snapshot preserves a reference to the immutable
  proposal identity (`proposal_id`, `producer_key`, `content_fingerprint`,
  `origin_classification`, `proposed_at`, `source_reference`) — values that
  are already immutable in the proposal store — plus the durable
  `accepted_decision_id` link in both directions. Full proposal history
  (batch context, full producer claims) remains in the proposal store.
- ADR imports retain deterministic source revision evidence: the
  `source_locator` and the existing `sha256` pin as `source_revision`,
  correcting the D0 adapter's blanket `runtime` typing of ADR-imported
  records.
- Legacy migration must not fabricate provenance: legacy records carry
  honest `runtime` typing and empty locators exactly as the synthesized
  shape produces today.
- Provenance never grants authority and never becomes trusted
  enforcement/test evidence. Producer provenance is never mapped into
  `CanonicalTestEvidence` or trusted execution evidence. ADR-024, ADR-025,
  and ADR-029 trust boundaries remain unchanged.

### 11. Lifecycle and relationships

- Proposal lifecycle (`proposed | accepted | rejected`) remains separate from
  canonical decision lifecycle. The D2B0 separation is re-pinned.
- Canonical decision lifecycle remains:

  ```text
  active | superseded | deprecated | inactive
  ```

  Version occurrences have immutable predecessor lineage but introduce **no
  second lifecycle state machine**: a version's effective state derives from
  the active pointer, and superseded versions remain retained and queryable.
- Same-decision version replacement (new occurrence + active-pointer move)
  must remain distinct from decision-to-decision `supersedes` (a
  relationship record that drives the target's lifecycle transition), exactly
  as the ADR corpus models supersession today.
- D1 must not invent `related_to` or promote producer
  `related_decision_ids` into authoritative relationships; they remain
  proposal history. Only already-sanctioned relationship semantics are
  included: `supersedes` (ADR-sanctioned), internal version lineage, and
  proposal provenance linkage. A canonical relationship requires an explicit
  future authority operation.

### 12. Unified loading/read boundary

After D1, one loader and one projection path serve every consumer:

```text
canonical Decision Index (decision_index section)
    → active-version resolution (explicit active_version_id)
    → Layer 1 runtime projection (D0 projector, sequence-ordered rules)
    → existing Audit / retrieval / enforcement / ConflictDetector /
      benchmark / protection consumers
```

The Decision MCP reads the same canonical Decision Index (read-only) instead
of deriving its canonical view from `--adr-dir`; `--adr-dir` remains an
import/validation source. Accepted decisions must therefore be visible
through MCP and Layer 1 governance from the same authoritative representation
— no restart-specific path, no second canonical store. MCP remains a thin
transport and does not own storage or authority.

A hand-edited `decisions[]` after migration is never silently adopted: the
loader warns and directs the author to explicit ingestion paths.

### 13. MCP compatibility

The MCP tool inventory (exactly six tools), input schemas, error contract,
and field names remain unchanged. Field-level treatment:

- `decision_id` remains stable.
- Existing `version` and `decision_version` values remain
  backwards-compatible revision/display fields (`"1"` for every existing
  record); their semantics are documented as non-identifying ordinals.
- `version_id`, `content_digest`, and `decision_version_id` are **additive**
  fields on canonical record / trace / rule payloads.
- `rule_id` and `derived_rule_ids` **values** migrate from positional IDs to
  stable content-derived IDs (§7). This migration is externally observable:
  it must be release-noted and golden-vector tested; the old positional ID
  is reconstructable **from the legacy derived order during migration** for
  audit tooling — it is not a continuing identity contract, and no dual
  old/new rule-ID authority is created (both formats are never emitted
  simultaneously).
- `derived_rule_ids` field names and ordering semantics (derived order via
  sequence) are unchanged; only identifier values change.
- `source_evidence` objects may gain additive keys
  (`source_revision`, `observed_at`) and accepted records change from empty
  to non-empty; `relationships` vocabulary is unchanged.

### 14. Validation gates

D1 extends the D0 parity philosophy. The existing D0 battery (G1–G9) is
neither weakened nor replaced; it is re-run over the new loading path with
unchanged fixtures. New gates:

- **G10 — Identity stability.** All existing `decision_id`s and
  `version == "1"` byte-identical pre/post migration. `rule_id` invariant
  under rule reordering and across version carry-over; changes when value or
  applicability changes; 128-bit golden vectors pinned; duplicate rule
  bindings and duplicate/malformed sequence positions fail closed.
- **G11 — Version occurrence identity and A → B → A.** Occurrence-keyed
  `version_id` derivation golden-vector pinned; A1 → B → A2 yields three
  distinct occurrences with equal `content_digest`s where content is
  identical; full history reconstructable from records + lineage; retry
  reuses the exact occurrence key and never rederives the predecessor from
  the active pointer (including a late-retry-after-B-is-active fixture);
  content rehash mismatch fails closed; `revision` and timestamps never
  resolve authority.
- **G12 — Exact version/rule lineage.** Every projected `Rule` traceable via
  `(decision_id, version_id, rule_id)`; `derived_rule_ids` verified as a
  pure sequence-ordered function of persisted bindings (recompute ==
  expose); projection fails closed on invalid bindings, sequence collisions,
  or ordering ambiguity; unchanged-rule carry-over keeps `rule_id` and binds
  the new `decision_version_id`.
- **G13 — Provenance retention.** Frozen snapshots present and immutable;
  accepted proposals resolvable to full store narrative; later observations
  append without rewriting snapshots; producer provenance never appears as
  trusted/test evidence; ADR records carry `source_revision`; legacy records
  fabricate nothing.
- **G14 — Lifecycle/supersession distinction.** Same-decision version
  replacement ≠ cross-id `supersedes`; no silent rule carry-over across
  version creation; producer `related_decision_ids` never materialize as
  canonical relationships; proposal vs canonical vocabularies never
  conflated.
- **G15 — Accepted-proposal MCP visibility.** Acceptance →
  `decision.get/search/trace` return the canonical record with no restart
  and no `--adr-dir` dependency; MCP canonical set == Audit set.
- **G16 — Runtime projection parity.** Full D0 G1–G6 battery over the
  load-time projection path with unchanged fixtures; legacy-item migrated
  Decisions byte-identical to today's synthesized equivalents; MemoryItem
  context pipeline unchanged.
- **G17 — Audit/enforcement/ConflictDetector/benchmark parity.** Identical
  tiers, verdicts, conflicts, and frozen benchmark results pre/post migration
  on real corpora.
- **G18 — Migration idempotency and collision failure.** Migrate twice →
  byte-identical section; item-ID vs canonical-ID collisions fail closed;
  section-less files load through the legacy path; deprecation-window
  snapshot verification catches corruption; reverse half-states fail closed
  (extending the D2C1 matrix).
- **G19 — MCP field compatibility.** §13 pinned by tests: stable fields
  byte-stable; additive fields present; rule-ID migration deterministic and
  golden-vector verified; no dual-ID emission.

### 15. Implementation sequence

Bounded post-ADR slices, each independently testable and squash-merged under
ADR-022; none is authorized by this ADR change:

- **D1B** — canonical persistence, models, migration, loader, and read-side
  projection (incl. legacy-item migration and deprecation-window snapshot).
- **D1C** — authority write-path switch and MCP canonical loading.
- **D1D** — versioning, ADR re-import, and supersession.
- **D1E** — protection/lifecycle writer migration and full parity closeout.
- **D1F** — optional later removal of the persisted `decisions[]`
  compatibility snapshot, gated by a consumer inventory; must never ride
  along in another slice.

---

## Explicit non-goals

D1 does not implement:

- enforcement-event persistence or any ADR-029 observed-enforcement
  implementation (D1 only leaves the identity slots clean);
- a decision/evidence log;
- exception/bypass lifecycle;
- trusted attestation (ADR-025 unchanged);
- new rule types;
- new source adapters;
- decision-conflict inference or a `DecisionConsistencyAnalyzer`;
- a general knowledge graph or new relationship kinds;
- hosted or enterprise infrastructure, cross-repository aggregation,
  multi-tenant governance;
- MCP tool additions or any producer authority capability;
- LLM or semantic identity inference;
- non-architecture decision classes;
- automatic semantic merge of decisions;
- any change to retrieval scoring, rule matching, applicability semantics,
  Audit tier formulas, or frozen benchmark fixtures.

---

## Consequences

### Positive

- ADR-023's canonical/runtime boundary becomes physically real: one durable
  authority, deterministic projection, and no duplicated decision state at
  rest after the deprecation window.
- ADR-029 receives exactly the identity chain it deferred to D1:
  `(decision_id, version_id, rule_id)`, with verifiable immutability
  (rehashable digests) and occurrence provenance that supports fail-closed
  stale-evidence detection later.
- Accepted decisions become visible through one authoritative set across
  MCP, Audit, and enforcement without restart-specific paths.
- Provenance becomes first-class on the canonical record without promoting
  producer claims or weakening the trust boundary.
- The A → B → A history is representable and reconstructable without an
  event log.

### Negative / accepted trade-offs

- `project_memory.json` grows a second schema section and becomes the
  authority for decisions, increasing the care required of `[memory]` PRs
  during the transition.
- The rule-ID format migration is externally observable and requires a
  release note and client communication even though no tool or field name
  changes.
- Hand-editing decisions (previously possible via `decisions[]`) is retired
  in favor of explicit authority paths — a deliberate ergonomics trade for
  authority integrity.
- Two decision representations coexist (one derived, persisted) during the
  bounded deprecation window, with parity verification as the cost of
  compatibility.

---

## Relationship to existing ADRs

- **ADR-023 — Canonical Decision Index and Runtime Projection Boundary:**
  unchanged. This ADR is an implementation ADR under its contract; §7
  explicitly left storage representation open ("ordinary deterministic
  file-backed records"), and §3/§10 already commit to versions, explicit
  active resolution, and stable rule lineage.
- **ADR-027 — Decision MCP Proposal Ingestion and Authority Boundary:**
  unchanged in authority semantics. Its D2C persistence boundary recorded
  itself as bounded and explicitly reserved "a later storage migration (a
  durable standalone canonical store, runtime loading from it) without
  changing canonical identity" — this ADR performs that migration. The
  fail-safe write order and recovery rules carry over to the new write
  target.
- **ADR-029 — Enforcement Evidence Binding Semantics:** unchanged. Its §4
  deferral ("identity representation is deliberately deferred to D1") is
  resolved by §4/§7/§8; its surrogate-identifier prohibition is honored by
  the stable `rule_id` and the identity tuple.
- **ADR-024 / ADR-025 —** declared/test-evidence and attestation trust
  boundaries unchanged; declared evidence remains decision-level metadata
  and never enters content digests or trusted channels.
- **ADR-017 / ADR-019 / ADR-020 —** retrieval/enforcement separation,
  typed-rule-only enforcement, and explicit path applicability unchanged;
  projection preserves runtime `Rule` semantics exactly.
- **ADR-026 —** Audit tier semantics unchanged.
- **ADR-022 —** all D1 slices remain subject to existing repository
  governance.

---

## Acceptance criterion

ADR-030 is satisfied when:

1. the `decision_index` section is the sole durable decision authority and
   all consumers (Layer 1 and MCP) load through the unified boundary;
2. legacy `items[]`, `decisions[]`, ADR imports, and accepted proposals
   migrate deterministically and idempotently with existing decision IDs,
   proposal IDs, and accepted-decision links unchanged; canonical rule IDs
   migrate only according to the explicitly versioned §13 compatibility
   contract;
3. version occurrence identity, occurrence-key retry, and the immutable
   content boundary behave exactly as specified (G10–G14);
4. accepted proposals are visible through MCP canonical reads (G15);
5. the D0 G1–G9 battery passes over the new loading path unchanged (G16),
   with Audit/enforcement/ConflictDetector/benchmark parity (G17);
6. migration idempotency, collision failure, and window integrity hold
   (G18); and
7. the §13 MCP field contract is pinned by tests (G19).

Until those conditions pass, the `decision_index` section is an
architecture contract, not a replacement runtime.

---

## Decision summary

Mneme will persist the canonical Decision Index as a schema-versioned
section of `project_memory.json` — the sole durable decision authority — and
project active versions in memory into the unchanged Layer 1 `Decision` API.
Logical decisions keep their existing IDs and own multiple immutable version
occurrences identified by predecessor-bound deterministic identity, resolved
only by an explicit active-version pointer, with retry idempotency by exact
occurrence key. Decision intent is immutable per version; rules remain
separate canonical entities with stable, order-independent, 128-bit
content-derived identity bound to exact versions by
`(decision_id, version_id, rule_id)`, ordered for presentation by immutable
per-version sequence. Provenance is frozen, referenced, and never
authorizing. Lifecycle vocabularies, trust boundaries, MCP tool inventory,
and all Layer 1 enforcement semantics remain unchanged.

## Related

- ADR-017 — Enforcement Scope Is Independent of Retrieval Scope
- ADR-019 — Typed Literal Rule Contract
- ADR-020 — Explicit Path Applicability for Typed Rules
- ADR-022 — Main Is PR and Squash Only
- ADR-023 — Canonical Decision Index and Runtime Projection Boundary
- ADR-024 — Declared Test-Evidence Ingestion for the Architecture Audit
- ADR-025 — Trusted Test-Execution Attestation (Deferred)
- ADR-026 — Audit Tier Semantics and Mneme Potential
- ADR-027 — Decision MCP Proposal Ingestion and Authority Boundary
- ADR-029 — Enforcement Evidence Binding Semantics
- D0 validation — `docs/validation/d0-decision-index-projection-parity.md`
- D2C1 validation — `docs/validation/d2c1-decision-authority.md`
- D1A architecture reconciliation (pinned SHA
  `6e5cf09b6a604b68d4610db82d9e7f83a681d99a`)
