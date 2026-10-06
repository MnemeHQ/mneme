---
id: ADR-030
title: "Canonical Decision Persistence, Version Identity, and Stable Rule Lineage"
status: accepted
priority: foundational
date: 2026-09-16
scope: decision_index.persistence
---

# ADR-030: Canonical Decision Persistence, Version Identity, and Stable Rule Lineage

**Status:** Accepted
**Date:** 2026-09-16
**Amended:** 2026-10-05 — accepted after reconciliation against the merged D1B/D1C implementation; lifecycle-conformance correction and other reconciliation amendments recorded (see "Implementation reconciliation" below)
**Amended:** 2026-10-05 — D1E0 architecture decisions: binding authority and protection continuity (§9a), canonical `add_decision` identity (§4), EventCatalog canonical apply retired for D1, and the D1E order and release gate (§15) (see "D1E0 amendment" below)
**Amended:** 2026-10-06 — D1E1 migration contract: `mneme decision-index migrate`, lossless-or-refuse migration with recursive representability validation, EventCatalog migration consequence, and comparison against bindings that predate `binding_authority` (§9a, §12, §15); `mneme decision-index migrate` as the sole section-less-to-canonical transition, withdrawing implicit migration from canonical writers (§1, §12, §15)
**Deciders:** Theo Valmis

---

## Acceptance record (2026-10-05)

Promoted from `proposed` to `accepted` after reconciling this ADR against what
the D1 slices actually shipped. Acceptance means this is the persistence,
identity, and lineage architecture Mneme has decided to implement. It does
**not** mean every slice is complete: D1D–D1F remain open, and the
"Acceptance criterion" section below still defines when the ADR is
*satisfied*.

Implementation evidence at acceptance:

- **D1B** (issue #423, PR #424) — persisted `mneme.decision-index/v1`
  section, deterministic migration of native `decisions[]` and legacy
  `items[]`, content/version/rule identity re-derivation at load, and
  load-time Layer 1 projection through `MemoryStore`.
- **D1C** (PR #440) — accepted proposals write the persisted index with a
  frozen proposal provenance snapshot; the Decision MCP reads that same index
  with no restart and no `--adr-dir` authority.
- **Live memory cutover** (PR #441) — this repository's
  `.mneme/project_memory.json` carries the authoritative section.
- **D1 containment** (PR #444) — once the section exists, every remaining
  legacy `decisions[]` writer refuses before any mutation.

The reconciliation found the merged slices consistent with this ADR's
architecture, with the divergences listed under "Implementation
reconciliation". Each is resolved there by amending this ADR or by assigning
explicit work to a named slice. The most significant is the lifecycle
conformance correction (§12): migration ends Layer 1 participation for
legacy non-active decisions, as accepted ADR-023 §6 already requires.

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
types, no MCP tool additions, and no enforcement-semantics change for
decisions eligible for Layer 1 projection. The one runtime-visible lifecycle
effect is the explicitly authorized conformance correction in §12: legacy
non-active decisions stop participating in Layer 1, as ADR-023 §6 already
requires.

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

Conversely, once a top-level `decision_index` section exists, no legacy writer
may mutate `decisions[]`. The test is section presence alone. A writer that
has not been migrated to a canonical authority operation must refuse before
any mutation and leave the file byte-identical, rather than write a snapshot
that the loader will then reject (D1 containment, PR #444). Section-less
pre-D1 files keep their legacy writer behaviour.

**Single transition (D1E1).** `mneme decision-index migrate` (§12) is the
sole supported transition from section-less memory to canonical
`decision_index` memory. Canonical writers must fail with
`DecisionIndexMigrationRequired` when they encounter section-less memory, and
must never migrate implicitly. That covers ADR import, proposal acceptance,
and every later canonical writer. Migration is an explicit authority
transition, never a side effect of another authority action. The two
directions are therefore symmetric:

```text
section-less memory → legacy writers only; canonical writers refuse
canonical memory    → canonical writers only; legacy writers refuse
the only bridge     → mneme decision-index migrate (preview, then --apply)
```

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
  `[decision_id, source_revision, "adr-import"]`; for legacy `items[]`
  migration, `["legacy-items", decision_id]`; and for pre-D1 native
  `decisions[]` records that carry neither verified ADR provenance nor an
  accepted-proposal occurrence identity,
  `["legacy-decisions", decision_id]`. The last form is migration identity
  only: it does not fabricate source provenance or grant new authority.
- **Canonical `mneme add_decision`** (D1E0) is an explicit human authority
  path with its own identity, `["cli-add", decision_id]`. It carries no
  timestamp.
  - It creates only a first occurrence, with the no-predecessor sentinel, and
    honest `runtime` provenance (empty locator and revision). It never claims
    ADR or proposal origin.
  - An exact retry (same `decision_id` and same content) resolves to the
    persisted occurrence and changes nothing.
  - The same `decision_id` with different content fails closed. `add_decision`
    is not an edit or version-evolution surface.
- The first version uses the fixed no-predecessor sentinel `"-"`. The literal
  is part of the version-identity contract and is golden-vector pinned.
- The explicit `active_version_id` on the logical decision is the **only**
  mechanism for resolving the active version. Timestamps, source modification
  times, source dates, and revision ordering may never resolve authority.
- Immutability is verified, not conventional: load-time re-derivation of
  `content_digest` and `version_id` must reproduce the stored values; a
  mismatch fails closed.
- **Migration-identity rebind (the only exception to §6's no-rewrite
  rule).** A `["legacy-decisions", decision_id]` identity is a placeholder
  that migration assigns when no truthful occurrence identity is known. If an
  accepted proposal in the proposal store later proves that the decision was
  created by that acceptance, the Mneme authority path may replace the
  placeholder **once** with the proposal occurrence identity. It may also
  replace the empty provenance with the proposal snapshot (§10). This
  rewrites that version's `version_id` and the `decision_version_id` of its
  rule bindings. The rebind is allowed only when the version:
  - is the decision's active version;
  - has no predecessor;
  - carries exactly the `legacy-decisions` identity.

  Content, `content_digest`, rule IDs, sequence, lifecycle, and timestamps
  must stay byte-identical. The new `version_id` must not collide with any
  existing occurrence. No other identity, including any `adr-import` or
  proposal identity, is ever rebound. (Shipped in D1C:
  `rebind_legacy_initial_occurrence`.)

### 5. Occurrence retry/idempotency

Every authority operation that creates a version occurrence has an exact
**occurrence key**:

```text
(decision_id, content_digest, occurrence_source_identity, predecessor_version_id)
```

A caller distinguishes a retry from a new authority operation only by the
predecessor it supplies:

- **An unpinned invocation is a new authority operation.** It takes the
  version active when it starts as its predecessor.
- **A retry carries the predecessor recorded for the original operation.** It
  never re-derives the predecessor from the active pointer, so its occurrence
  key is the original operation's key.
- **Reapplying identical content and source is not automatically a retry.**
  Deliberately reapplied as a new operation after a later version has become
  active, it legitimately produces another occurrence (A2 below).
- **The "already active occurrence" no-op is separate from retry resolution.**
  A new operation whose `content_digest` and `occurrence_source_identity` both
  already match the active occurrence creates nothing. That is an
  optimization over the active version only. It is distinct from resolving a
  retry by its exact historical occurrence key, which searches the whole
  version history and includes the predecessor.

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
- The occurrence lookup covers the decision's **whole version history**, not
  only the active version. D1C's accepted-proposal retry currently compares
  against the active version only. That is correct while a proposal-backed
  decision has exactly one occurrence. But a late retry after a later version
  would then fail closed as an ID collision instead of resolving to its
  persisted occurrence. Any slice that adds a version-evolution path for
  proposal-backed decisions must first make that retry resolve by exact
  occurrence key.

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
  with no silent carry-over across version creation. Carrying a
  `protection` or `legacy_unknown` binding into a new version is explicit
  and governed by §9a, and its `binding_authority` is part of the immutable
  binding;
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
- applicability (ADR-020 selectors);
- `binding_authority` (D1E0, §9a): the immutable classification of why the
  binding exists.

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

### 9a. Binding authority and protection continuity (D1E0)

The problem this section closes: version evolution (D1D) re-derives a new
version's rules from its source and carries nothing silently (§6). A rule
installed by protection, or a pre-D1 rule whose origin is unknown, would then
disappear when the source changes. This was reproduced on `main` after D1D: an
unrelated edit to an ADR, re-imported, removed a protection-installed rule.

**Binding authority.** Every rule binding carries an immutable
`binding_authority`:

```text
version | protection | legacy_unknown
```

- `version`: derived from the owning version's source, or installed by the
  authority operation that created the version.
- `protection`: installed by `mneme protect activate`.
- `legacy_unknown`: an origin that cannot be honestly reconstructed.
- `binding_authority` is not part of `rule_id`. The same rule semantics keep
  the same stable `rule_id` (§7) whatever the authority.
- **Transport and semantics boundary.** `binding_authority` is persisted
  canonical/internal authority metadata for D1:
  - it is not emitted through MCP (§13, G19);
  - it does not change the ADR-029 identity tuple
    `(decision_id, version_id, rule_id)`;
  - it does not alter Audit tiers, enforcement, or rule matching.

  It governs only whether a binding may lapse across version evolution.
- **No backfill.** Bindings persisted before this field existed stay
  byte-identical. A missing field is read as `legacy_unknown`. That includes
  bindings migrated by D1B and bindings written by D1D ADR import before the
  field was implemented. Writing the field onto an existing binding would be
  an in-place change to an immutable Tier 2 record and is prohibited. Adding
  the field is a backward-compatible change within
  `mneme.decision-index/v1`.
- **Migration writes `legacy_unknown`.** Pre-D1 native rules migrated after
  this field exists are written as `legacy_unknown`, because migration cannot
  tell ADR-derived rules from rules that legacy protection appended to
  `decisions[]`.
- **Comparing against bindings that predate the field.** When an exact
  historical binding is compared, for example a §5 retry resolving to an
  occurrence persisted before the field existed, a binding whose
  `binding_authority` is **actually absent** matches on every other field
  exactly, and its authority is not compared. This applies to that
  comparison only. An explicitly persisted `legacy_unknown` is a real
  conservative classification and is never interchangeable with `version`.
- New bindings always persist the field explicitly.

**Continuity invariant.** A `protection` or `legacy_unknown` binding cannot
disappear between version occurrences unless the operation that creates the
version explicitly authorizes its release. The rules below apply when a new
version B is created over an active version A, for each rule R bound to A as
`protection` or `legacy_unknown`. A's historical binding is never moved or
edited.

- **B's source still derives R (same `rule_id`).** B carries exactly one
  binding for R, never a duplicate. That binding keeps the stronger
  classification (`protection` or `legacy_unknown`) unless R is explicitly
  released. Downgrading it to `version` silently would only postpone the loss
  to the next version.
- **R is explicitly released and B's source still derives R.** B carries one
  `version` binding for R.
- **R is explicitly released and B's source does not derive R.** B carries no
  binding for R.
- **R is explicitly preserved and B's source does not derive R.** The
  preservation is revalidated deterministically against B: the same
  protection validation applies to B's content, and applicability is
  unchanged. If revalidation passes, B carries a new binding for R with the
  same `rule_id` and authority. If it fails, or the rule's semantics would
  change, version creation fails. Protection is never silently dropped or
  altered.
- **Neither preserved nor released, and B's source does not derive R.**
  Version creation **fails closed**.
- Preservation and release are explicit and per binding, never a broad
  preserve-all switch, and are named by `rule_id`, for example
  `--preserve-protection <rule_id>` and `--release-protection <rule_id>`.
  The exact CLI spelling is settled in D1E2; these per-binding semantics are
  fixed here. `legacy_unknown` gets the same treatment even though it cannot
  honestly be claimed to originate from protection.
- **Ordering.** B's source-derived rules come first, in their source order.
  Bindings preserved without being re-derived follow at `max(sequence) + 1`,
  keeping their previous relative order.
- **Retry consistency.** Preservation and release change Tier 2 bindings but
  not `content_digest` or the occurrence source identity, so they are not
  part of the occurrence key. On a retry that resolves to an existing
  occurrence (§5), the requested preservation/release outcome must match the
  persisted bindings of that occurrence exactly. Otherwise the retry fails
  closed rather than reinterpreting the same `version_id` with different
  Tier 2 semantics.
- No event log is introduced. The transition can be reconstructed from A's
  retained bindings and B's bindings and authorities alone.
- An accepted-proposal retry keeps excluding `rules`, `test_evidence`, and
  `updated_at` from proposal-owned identity verification (D1C), so canonical
  protection enrichment of an accepted decision survives a retry of its
  acceptance.

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
- An ADR import's `source_revision` is the hash of the **exact bytes from
  which that version's content was parsed**. It is captured when the source
  is read for compilation and is never recomputed from the file on disk at
  write time. Otherwise a source edited between compile and apply would pin
  one file revision to another revision's content. It would also change the
  occurrence key (§5), so a legitimate retry would be rejected as stale.
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

  This is ADR-023 §6's vocabulary. `inactive` is the existing
  non-authoritative bucket: an explicitly `proposed` ADR, or an accepted
  same-scope precedence loser. Only `active` is eligible for Layer 1
  projection. `superseded`, `deprecated`, and `inactive` are retained for
  lineage and never projected.

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

The MCP server therefore requires a memory file that already carries a valid
`decision_index` section. It fails closed otherwise and never reconstructs
authority from `decisions[]`. This removes the pre-D1 proposal-store-only
startup mode. A supported way to give a memory file the section is
consequently part of D1: an explicit migration command, plus a
section-bearing scaffold from `mneme init`. It is assigned to D1E (§15) and
must land before any release ships the MCP canonical read path.

**Migration entry point (D1E1).** This command is the only transition from
section-less to canonical memory (§1). No canonical writer migrates
implicitly. The public command is:

```text
mneme decision-index migrate --memory <path>            # preview, no write (default)
mneme decision-index migrate --memory <path> --apply    # write the previewed migration
```

- **One read.** The source bytes are read once. The preview and the written
  result are derived from that single migration result.
  - `--apply` writes only if the file still holds exactly those bytes
    immediately before the atomic replace. Otherwise it refuses and writes
    nothing.
  - This is an optimistic guard within the existing single-writer discipline,
    not a locking system.
- **Three inputs.**
  - Section-less valid memory previews, then migrates on `--apply`.
  - Already-canonical valid memory is reported as migrated; `--apply` is a
    byte-identical no-op.
  - Invalid canonical memory is refused. Migration is never a repair path.
- **What the preview shows:** the §12 lifecycle-conformance effects (which
  non-active decisions leave Layer 1), the one-time `items[]` migration and
  the fact that new `rule`/`anti_pattern` items will stop synthesizing
  decisions (§2), and the `legacy_unknown` classification of migrated rules
  (§9a).
- **No force, repair, or loss-acknowledgment option.** Mneme never authorizes
  destroying durable decision metadata.
- **Migration is lossless or it refuses.** Validation is recursive and
  applies to legacy `decisions[]` rows, because that is where reconstructing
  the canonical record and rebuilding the compatibility snapshot would
  otherwise destroy information. A row may contain only:
  - the representable decision fields: `id`, `decision`, `rationale`, `scope`,
    `constraints`, `anti_patterns`, `rules`, `test_evidence`, `created_at`,
    `updated_at`, `status`, `source`;
  - rule records with only `type`, `value`, `include_paths`, `exclude_paths`;
  - test evidence with only `selector` and `sha`;
  - a `source` only when it is a valid `adr` source (`type`, `path`, `sha256`)
    whose path resolves to that decision.

  Anything else fails before any write, naming the exact record and field.
  That includes unknown decision, rule, or evidence fields, EventCatalog
  source metadata, and malformed or unresolvable ADR source metadata. Unknown
  top-level project-memory sections are not refused, because canonical
  writers preserve them.
- **EventCatalog consequence.** Section-less memory that contains legacy
  EventCatalog-imported decisions (`source.type: eventcatalog`) or other
  unrepresentable metadata **cannot migrate in D1**. It stays section-less on
  the compatibility path until a future EventCatalog canonical provenance
  contract exists. This is stronger than retiring EventCatalog canonical apply
  (§15, D1E4), and it must be release-noted.
- **Missing-section MCP error.** When memory has no section, MCP reports that
  migration is required and points to the preview first, then `--apply`. It
  never auto-migrates. Invalid canonical state is reported as invalid, without
  suggesting migration.
- **Serialization.** Canonical writers share one serialization:
  `json.dumps(..., indent=2) + "\n"`.

A hand-edited `decisions[]` after migration is never silently adopted. The
loader verifies the persisted snapshot against the canonical projection and
**fails closed** on any divergence; it does not warn and continue. Legacy
writers are refused before they can create that divergence (§1). Authors are
directed to explicit authority and ingestion paths.

**Lifecycle conformance at migration.** D1 preserves enforcement semantics
for every decision eligible for Layer 1 projection. Migration also brings
legacy lifecycle handling into conformance with accepted ADR-023 §6: only
`active` canonical decisions project into Layer 1 governance. Before D1, the
section-less loader returned every native `decisions[]` entry regardless of
`status`, and the runtime consumers do not filter by status.

After migration, legacy `superseded`, `deprecated`, and `inactive` decisions
are retained canonically but no longer take part in any of these:

- retrieval;
- enforcement (including their typed rules);
- ConflictDetector;
- benchmark runtime sets;
- the Audit decision set. The Audit report's `total_decisions` count and its
  per-decision list drop those entries. Audit tier percentages, which were
  already computed over `active` decisions only, do not change.

The derived `decisions[]` compatibility snapshot carries active decisions
only. Decisions compiled from ADR sources were already active-only, so the
correction affects only the legacy `decisions[]` path. This is an explicitly
authorized correction, not a regression. It must be release-noted with the
first release that ships D1 migration.

### 13. MCP compatibility

The MCP tool inventory (exactly six tools), input schemas, error contract,
and field names remain unchanged. Field-level treatment:

- `decision_id` remains stable.
- Existing `version` and `decision_version` values remain
  backwards-compatible revision/display fields (`"1"` for every existing
  record); their semantics are documented as non-identifying ordinals.
- `version_id`, `content_digest`, and `decision_version_id` are **additive**
  fields on canonical record / trace / rule payloads. On a canonical record,
  `decision_version_id` carries the same value as `version_id`. Rule payloads
  also gain the additive presentation field `sequence` (§9), which carries no
  identity.
- `rule_id` and `derived_rule_ids` **values** migrate from positional IDs to
  stable content-derived IDs (§7). This migration is externally observable:
  it must be release-noted and golden-vector tested; the old positional ID
  is reconstructable **from the legacy derived order during migration** for
  audit tooling — it is not a continuing identity contract, and no dual
  old/new rule-ID authority is created (both formats are never emitted
  simultaneously). For a migrated first occurrence, migration assigns
  `sequence` in the legacy derived order, so the old ID is
  `<decision_id>:<RULE_TYPE>:<sequence>` (every current rule is
  `FORBID_LITERAL`). The persisted bindings are sufficient; no separate
  mapping table is persisted.
- The rule-ID value change must be release-noted with the first release that
  ships D1 persistence. The merged D1B/D1C slices did not include that note.
  It is a release gate, not an optional follow-up.
- `derived_rule_ids` field names and ordering semantics (derived order via
  sequence) are unchanged; only identifier values change.
- `source_evidence` objects may gain additive keys
  (`source_revision`, `observed_at`) and accepted records change from empty
  to non-empty; `relationships` vocabulary is unchanged. Proposal-backed
  evidence additionally carries the §10 proposal reference keys
  (`proposal_id`, `producer_key`, `content_fingerprint`,
  `origin_classification`, `proposed_at`, `source_reference`,
  `accepted_decision_id`). ADR and runtime evidence never carries them. The
  transport also emits `verification_status` only for proposal-backed
  evidence. It is persisted for every source type and is currently always
  empty.
- `binding_authority` (§9a) is **not** emitted through MCP. Rule transport
  payloads keep their current field set. Exposing the field would require an
  explicit future amendment to this section and G19.

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
- **G16/G17 scope.** Parity is required for decisions eligible for Layer 1
  projection. The §12 lifecycle-conformance correction is explicitly excluded
  from both gates. It needs its own fixture: a pre-D1 memory with `active`
  and non-active native decisions, including a non-active decision that
  carries a typed rule. The fixture proves that active decisions keep exact
  runtime parity, and that non-active decisions are retained canonically but
  absent from the projection, the compatibility snapshot, enforcement, and
  the Audit decision set. A parity corpus that contains only `active`
  decisions (such as this repository's live memory) cannot by itself satisfy
  G16/G17. This fixture is required before D1D merges.
- **G18 — Migration idempotency and collision failure.** Migrate twice →
  byte-identical section; item-ID vs canonical-ID collisions fail closed;
  section-less files load through the legacy path; deprecation-window
  snapshot verification catches corruption; reverse half-states fail closed
  (extending the D2C1 matrix).
- **G19 — MCP field compatibility.** §13 pinned by tests: stable fields
  byte-stable; additive fields present; rule-ID migration deterministic and
  golden-vector verified; no dual-ID emission; `binding_authority` absent
  from every MCP rule payload (§9a).
- **G20 — Binding authority and protection continuity (§9a, D1E0).** Tests
  must prove each of the following:
  - **No silent loss:** version evolution that would drop a `protection` or
    `legacy_unknown` binding fails closed, including the reproduced case of
    an unrelated ADR edit.
  - **Same-rule satisfaction:** a re-derived identical `rule_id` yields one
    binding that keeps the stronger authority.
  - **Explicit preserve:** the binding is revalidated, created on the new
    version with the same `rule_id`, and a failed revalidation fails closed.
  - **Explicit release:** the rule is downgraded to `version` or omitted, as
    the §9a table specifies.
  - **Missing-field read:** a missing field reads as `legacy_unknown`, and
    existing rows stay byte-identical.
  - **Migration:** migration writes `legacy_unknown`.
  - **Ordering:** source-derived rules come first, then preserved bindings in
    their previous relative order.
  - **Retry consistency:** a retry whose preserve/release request differs
    from the persisted bindings fails closed. Stale-predecessor behaviour is
    unchanged.
  - **Accepted-proposal retry:** a retry succeeds after canonical protection
    enrichment.
  - **`cli-add`:** the identity is golden-vector pinned, an exact retry is a
    no-op, and a different-content same-ID call fails closed.

### 15. Implementation sequence

Bounded post-ADR slices, each independently testable and squash-merged under
ADR-022; none is authorized by this ADR change:

- **D1B** — canonical persistence, models, migration, loader, and read-side
  projection (incl. legacy-item migration and deprecation-window snapshot).
  *Merged (#424).*
- **D1C** — authority write-path switch and MCP canonical loading.
  *Merged (#440); live memory cut over in #441; legacy writers contained in
  #444.*
- **D1D** — versioning, ADR re-import, and supersession. Includes the §10
  parsed-bytes `source_revision` binding and the §14 lifecycle-conformance
  fixture. *Merged (#443); §5 retry wording clarified in #446.*
- **D1E** — protection/lifecycle writer migration and full parity closeout.
  The order is fixed. `init`/`setup` become canonical **last**, so that every
  supported writer can already operate on canonical files before new
  projects are created with the section:
  1. **D1E0** — architecture decisions (this amendment): §9a binding
     authority and protection continuity, the §4 `cli-add` identity, and the
     EventCatalog decision below.
  2. **D1E1** — the opt-in `mneme decision-index migrate` command (preview by
     default, lossless-or-refuse, guarded atomic apply), a clean MCP error
     when memory is missing the section (§12), and `binding_authority`
     persistence plumbing (§9a): migrated rules are written as
     `legacy_unknown`, newly created ADR-derived rules as `version`, and a
     missing field reads as `legacy_unknown`. D1E1 also **withdraws the
     implicit migration** that D1C proposal acceptance and D1D ADR import
     performed on section-less targets. Those writers, and the canonical
     append, evolve, supersede, and rebuild primitives, now refuse
     section-less memory with `DecisionIndexMigrationRequired` (§1). No
     preserve/release, no continuity enforcement, and no `init`/`setup` change
     yet.
  3. **D1E2** — canonical `mneme protect activate`: writes `protection`
     bindings (§9, §9a). Also the per-binding preserve/release operations,
     and fail-closed continuity enforcement in ADR version evolution,
     including for `legacy_unknown`.
  4. **D1E3** — canonical `mneme add_decision` with the `["cli-add",
     decision_id]` identity and `runtime` provenance (§4). The command is
     kept; it is documented in the README and quickstart.
  5. **D1E4** — EventCatalog: the canonical `eventcatalog import --apply`
     is **retired for D1**. Read and preview remain. Section-less legacy
     targets may keep the legacy apply path during the compatibility window.
     Canonical targets refuse it (the #444 guard). Defining an EventCatalog
     canonical provenance contract would be a separate future decision; it
     is not prohibited, but it would widen D1.
  6. **D1E5** — `mneme init` and `mneme setup` create memory that carries an
     empty `decision_index` section.
  7. **D1E6** — parity closeout (G16–G20), release notes, and the release
     gate below.

  **Accepted interim state (unreleased, D1E1 to D1E5).** Until D1E5, no single
  memory mode supports every writer:

  - section-less memory: the legacy `add_decision`, `protect`, and
    EventCatalog apply work, explicit migration is available, and canonical
    writers refuse;
  - canonical memory: ADR import, proposal authority, and canonical reads
    work, and legacy writers refuse.

  D1E2 to D1E4 close the writer gaps, and D1E5 makes new projects canonical by
  default. This state is acceptable only because D1 is unreleased; the
  release gate below applies.
- **D1F** — optional later removal of the persisted `decisions[]`
  compatibility snapshot, gated by a consumer inventory; must never ride
  along in another slice.

**Release gate.** No release may ship D1 persistence until all of the
following hold. Until then, released artifacts must not include D1B/C/D.

- the §12 migration entry point exists (D1E1);
- **no silent loss of `protection` or `legacy_unknown` bindings** across
  version evolution (§9a, G20). This is a release blocker independent of
  D1E2's other work: pre-D1 rules migrate as indistinguishable bindings, so
  until §9a is enforced, an ADR re-import can already drop a pre-D1
  protection rule on `main`;
- release notes cover:
  - the §12 lifecycle-conformance correction;
  - the §13 rule-ID value change;
  - the retirement of EventCatalog canonical apply, which becomes
    unavailable for every new project once D1E5 lands;
  - that memory containing legacy EventCatalog-imported decisions or other
    unrepresentable `decisions[]` metadata cannot migrate in D1 and stays on
    the section-less compatibility path (§12);
  - the incompatibility of older `mneme-hq` binaries (≤ 0.9.2), whose legacy
    writers mutate `decisions[]` directly and make a migrated file fail to
    load. No in-file version marker is added, because an older binary would
    ignore it.

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

Accepting this ADR does not mean these conditions already hold. Since D1B
and D1C, the `decision_index` section is already the runtime read authority
for any memory file that carries it. Until all seven conditions pass, D1 is
an **incomplete transition**: that authority is real, but the version
evolution, writer migration, and parity closeout it depends on are not yet
finished.

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
authorizing. Lifecycle vocabularies, trust boundaries, and the MCP tool
inventory remain unchanged. Layer 1 enforcement semantics are unchanged for
every projection-eligible decision. Migration only brings legacy non-active
decisions into conformance with ADR-023's active-only projection (§12).

---

## Implementation reconciliation (2026-10-05)

This ADR was reconciled against the merged D1B/D1C implementation before
acceptance. Each divergence is resolved below, either by amending this ADR to
match a deliberate implementation choice or by assigning explicit work.
Section numbering is unchanged.

| # | Divergence | Resolution | Where |
| --- | --- | --- | --- |
| R1 | Migration drops legacy non-active decisions from Layer 1, but the ADR claimed "no enforcement-semantics change" and broad G16/G17 parity. | ADR amended. This is an authorized conformance correction under accepted ADR-023 §6. Parity is scoped to projection-eligible decisions. A dedicated fixture and a release note are required. | Context, §12, §14, Decision summary |
| R2 | §12 said a hand-edited `decisions[]` makes the loader warn; the loader fails closed. Legacy writers could create that divergence. | ADR amended to fail-closed. Section-presence containment of legacy writers recorded (#444). | §1, §12 |
| R3 | D1C rewrites a `legacy-decisions` placeholder occurrence in place when binding a pre-cutover accepted proposal, which §6 prohibits. | ADR amended with one bounded, once-only, migration-identity-only exception. | §4 |
| R4 | D1C accept retry checks only the active version, not the exact occurrence key across history. | Recorded as correct for single-occurrence decisions. Required before any version-evolution path for proposal-backed decisions. | §5 |
| R5 | D1D draft (#443) recomputes ADR `source_revision` from disk at apply time. | ADR made explicit: the revision is bound to the parsed bytes. Assigned to D1D. | §10, §15 |
| R6 | MCP now requires a section-bearing memory file, but no supported way to create one exists (`mneme init` produces a section-less file). | Migration entry point and `init` scaffold assigned to D1E. Release gate added. | §12, §15 |
| R7 | The rule-ID value change shipped without a release note; positional-ID reconstruction was unspecified. | Release note made a release gate. Reconstruction specified from migration `sequence`. | §13, §15 |
| R8 | Additive MCP fields `sequence` and proposal-only evidence keys were not listed; `decision_version_id` duplicates `version_id` on records. | §13 field list completed. | §13 |
| R9 | `mneme add_decision` and EventCatalog import were not assigned to any slice. | Assigned to D1E with an explicit decision required. | §15 |
| R10 | `inactive` was used without tying it to ADR-023's lifecycle vocabulary. | Clarified as ADR-023's non-authoritative, non-projecting bucket. | §11 |

---

## D1E0 amendment (2026-10-05)

These architecture decisions came out of a pressure test of the D1E scope
after D1D merged (#443). They are recorded before any D1E implementation.

| # | Finding | Decision | Where |
| --- | --- | --- | --- |
| E1 | Version evolution re-derives rules from source, so a protection-installed rule (or a pre-D1 rule of unknown origin) is silently dropped by an unrelated ADR edit. Reproduced on `main`. | Immutable `binding_authority` (`version`/`protection`/`legacy_unknown`). A missing field reads as `legacy_unknown`, with no backfill. A continuity invariant: carry-over only when explicit, per-binding preserve/release, a same-rule collapse that keeps the stronger authority, fixed ordering, and retry consistency. Fail closed otherwise. | §6, §8, §9a, G20 |
| E2 | `mneme add_decision` matched no authority identity in §4. | Kept as a canonical authority path with identity `["cli-add", decision_id]`, `runtime` provenance, first occurrence only, idempotent exact retry, different content fails closed. | §4, G20 |
| E3 | EventCatalog had no D1 canonical writer contract. | Canonical apply is retired for D1. Read and preview remain, and the legacy section-less path is bounded by the compatibility window. A future canonical contract is not prohibited. | §15 |
| E4 | Making `init` canonical before the writers would block every new project. | D1E order fixed, with `init`/`setup` last. A clean MCP migration error comes early. | §12, §15 |
| E5 | Pre-D1 protection rules on migrated memory are already exposed to silent loss on `main`. | Release blocker: no silent loss of `protection`/`legacy_unknown` across version evolution. | §15 |
| E6 | Migration already discarded unrepresentable legacy metadata. EventCatalog provenance and unknown fields survived only in the raw snapshot, and the next canonical write erased them (reproduced). | Lossless-or-refuse migration with recursive validation and no force option. EventCatalog-bearing memory stays section-less in D1. Absent `binding_authority` acts as a wildcard only in exact historical-binding comparison. | §9a, §12, §15 |
| E7 | Implicit migration inside D1C acceptance, D1D ADR import, and the canonical primitives bypassed the lossless migration check. Reproduced: ADR import on section-less memory erased an EventCatalog decision's provenance. | `mneme decision-index migrate` is the sole transition. Canonical writers refuse section-less memory with `DecisionIndexMigrationRequired`, giving a symmetric writer boundary. The interim state is accepted while D1 is unreleased. | §1, §12, §15 |

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
