# DG1B2: canonical waivers (behavioral charter)

**Status: PROPOSED.** Behavioral charter for DG1B2 under ADR-031 §12. On merge
it fixes the contract and acceptance evidence for the first waiver increment.
**It authorizes no implementation by itself.** Implementation also needs a
separate `[layer1-freeze]` amendment (§9) with its own review and approval.
**Anchor:** `MnemeHQ/mneme` `main` at `27c92223` (#783).
**Basis:** [ADR-031](../adr/ADR-031-decision-governance-semantics.md) §3, §4,
§6, §7, §8, §12, §13;
[ADR-030](../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md)
writer discipline;
[ADR-027](../adr/ADR-027-decision-mcp-proposal-ingestion-and-authority-boundary.md)
producer boundary; the
[DG1B2 waiver evidence packet](../validation/dg1b2-waiver-evidence-packet-2026-11-10.md)
(#783, evidence gate satisfied); the
[DG1B1 charter](2026-10-08-dg1b1-decision-applicability-charter.md)
(precedent); tracker [#497](https://github.com/MnemeHQ/mneme/issues/497).

## 1. Governing authority and starting behavior

- ADR-031 §12 fixes waiver semantics: an authoritative canonical object that
  targets a decision (or decision version), is created only by an explicit
  Mneme authority operation obeying ADR-030 writer discipline (verify before
  mutate, atomic write, no repair, no implicit migration), has its own
  lifecycle and provenance, is bounded by decision-applicability-style scope
  and optionally by time evaluated only against `GovernanceContext.as_of`,
  and never mutates or deletes the decision it targets. A decision under an
  applicable waiver stays authoritative and is not effective for that context,
  with cause `waived`. Producers (MCP, O1A, discovery) never create waivers
  (ADR-027).
- ADR-031 §7: DG1B2 needs a merged charter before implementation; §8: any
  persisted waiver data is a declared v2 semantic feature with closed key sets.
- **Starting behavior at the anchor:** no waiver representation exists. The
  `waived` cause is reserved only in ADR-031 §3; the code defines no such
  constant. `GovernanceContext.as_of` is accepted as an opaque non-empty string
  and never parsed. Canonical
  authority operations (for example `mneme decision accept`) are local CLI
  commands that follow ADR-030 writer discipline and record no actor identity.
  Enforcement takes its decision set from projection; only the C1a preview and
  the three C3a reporting consumers call the resolver, the latter with labels
  not supplied.

## 2. Scope: DG1B2a now, DG1B2b later

A waiver only changes what users see once some consumer acts on it. Making
enforcement honour a waiver means excluding a decision from enforcement for a
context, which needs a trusted source for that context and for `as_of`: the
same unsolved prerequisites as DG1F-C1b. This charter therefore splits DG1B2:

- **DG1B2a (this charter):** the canonical waiver record, the explicit
  authority operations that create and revoke it, resolver evaluation with
  cause `waived`, change reporting, read-only listing, and the safeguards in
  §3.5. Waivers become authoritative, explainable and auditable.
  **No enforcement input changes:** projection, `mneme check`, hooks, CI,
  MCP and the C3a consumers behave exactly as today.
  **One informational reporting consumer:** the existing C1a preview may
  display a `waived` resolution computed from caller-asserted labels (§3.7).
  That display is non-authoritative: it is not an enforcement input, not a
  production decision set, and no authoritative consumer excludes a decision
  because of it.
- **DG1B2b (= ADR-031 §11 "waiver-aware DG1F convergence"; not authorized):** any authoritative consumer (enforcement, CI, hooks, MCP, the C3a
  reporting consumers or any production decision set) that excludes a
  decision because of a waiver. It needs a trusted
  context and `as_of` source, an explicit fail-safe contract, its own charter
  and its own `[layer1-freeze]` amendment, and is sequenced with DG1F-C1b.

DG1B2a alone does not let a team stop a false violation in `mneme check`. It
makes the exception a first-class, reviewable record that later increments
can act on safely.

## 3. Contract (DG1B2a)

### 3.1 The waiver record

- Persisted only under `mneme.decision-index/v2` with a new declared semantic
  feature named `decision_waivers`. v1 memory refuses waiver writes
  with the existing migration message; a reader that does not support the
  feature refuses the document (ADR-031 §8).
- Closed key set (ADR-031 §8). Proposed fields:

| Field | Required | Meaning |
|---|---|---|
| `waiver_id` | yes | deterministic id over the creation fields only, fixed in §3.1.2. Re-issuing a waiver with identical creation fields after revocation is refused; a changed field (for example a new approval reference) produces a new id. |
| `target_decision_id` | yes | the waived decision |
| `target_decision_version_id` | yes | the exact decision version the waiver binds to (`dver-…`) |
| `scope.required_labels` | yes, non-empty | decision-applicability-style scope (DG1B1 label containment) |
| `valid_from`, `valid_until` | no | optional RFC 3339 UTC instants (`YYYY-MM-DDTHH:MM:SSZ`), validated at write and at load; `valid_from` < `valid_until` when both are present; evaluated only against `GovernanceContext.as_of` |
| `requester` | yes | opaque identity string of who asked for the waiver |
| `approver` | yes | opaque identity string of who authorized it; must differ from `requester` |
| `approval_reference` | yes | where the authorization is recorded (for example a review, resolution or ticket URL) |
| `reason` | yes | why the exception exists |
| `status` | yes | `active` or `revoked` |
| `revocation` | when revoked | `revoked_by`, `revocation_reference`, `reason` |
| `created_at` | yes | provenance timestamp written by the authority operation, same shape as `valid_from` |

- **Non-empty scope is required, as a deliberate DG1B2a limitation.** A
  temporary global waiver can be a legitimate exception, so this is not a
  claim that unscoped waivers are conceptually deprecation. DG1B2a excludes
  them because a global waiver removes a decision everywhere, which is the
  hardest case to tell apart from retirement and the one with the largest
  blast radius once DG1B2b gives waivers runtime effect. Retirement keeps its
  existing lifecycle operations (§3.6). Allowing global waivers later needs a
  charter amendment.
- **Rule-level and path-scoped waivers are out of scope.** ADR-031 §12 targets
  a decision or decision version and uses decision-applicability-style scope;
  rule-level or ADR-020-path scope would be new semantics.

#### 3.1.1 Persistence location

- Waivers live in a new top-level array `waivers` on the v2
  `decision_index` root, added to the closed root key set beside
  `decisions`, `versions` and `rules`. They are not nested in decision rows
  (a waiver is its own canonical object with its own lifecycle, ADR-031 §12,
  and must survive changes to its target's active version) and never live in
  `extensions` (ADR-031 §8a: semantic data is a declared feature, not an
  extension).
- `waivers` is present if and only if `semantic_features` declares
  `decision_waivers`. A `waivers` key without the feature, the feature without
  a `waivers` key, or an empty `waivers` array is a load-time refusal. Revoked
  records are retained, so once a waiver is written the array never becomes
  empty.
- Row key sets are closed: the fields in the table above; `scope` contains
  only `required_labels`; `revocation` contains only `revoked_by`,
  `revocation_reference` and `reason`. Optional keys (`valid_from`,
  `valid_until`) are omitted when absent, never written as `null`.
  `revocation` is present if and only if `status == "revoked"`.

#### 3.1.2 Identity and canonical serialization

- `waiver_id = "wvr-" + sha256_hex(payload)[:32]`, using the ADR-030
  identity helpers in `mneme/rule_identity.py` (`canonical_json`:
  `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=True`; SHA-256 of
  its UTF-8 bytes), where `payload` is the JSON array, in this order:
  `[target_decision_id, target_decision_version_id, required_labels,
  valid_from, valid_until, requester, approver, approval_reference, reason]`.
  `required_labels` is the sorted, de-duplicated list (DG1B1 normalization);
  an absent `valid_from` or `valid_until` is `null` in the payload. No other
  field participates.
- Normalization before hashing is limited to label sort and de-duplication.
  All other strings are hashed exactly as written; timestamps must already be
  in the `YYYY-MM-DDTHH:MM:SSZ` shape, so no time normalization exists.
- The loader recomputes every `waiver_id` and refuses a mismatch, and
  refuses duplicate ids, as it already does for `version_id` and `rule_id`.
- The writer stores `required_labels` sorted and de-duplicated, sorts the
  `waivers` array by `waiver_id`, and writes through the existing canonical
  memory writer (same file formatting as the rest of the document).
  `revoke-waiver` changes only `status` and adds `revocation`; the id is
  unchanged.
- The `wvr-` prefix, the payload order and the 32-hex truncation are part of
  the public contract. Changing any of them is a new semantic feature, not an
  implementation detail.

### 3.2 Resolver semantics

Evaluation order for each decision:

1. Lifecycle (unchanged): non-governing lifecycle → existing cause; waivers are
   not evaluated.
2. Applicability (unchanged): `not_applicable` stays `not_applicable`; waivers
   are not evaluated.
3. **Waivers:** the decision is `ineffective` with cause `waived` only if at
   least one waiver satisfies **all** of:
   - `status == "active"`;
   - `target_decision_id` and `target_decision_version_id` equal the
     decision's active version;
   - labels were **supplied** and contain every `scope.required_labels` entry;
   - if `valid_from` or `valid_until` is present, `as_of` was supplied, parses
     as RFC 3339 UTC, and lies within the window (`valid_from` ≤ `as_of` <
     `valid_until`). `as_of` is parsed only here; `GovernanceContext`
     validation is unchanged. A missing or unparseable `as_of` means the
     waiver does not apply (trace reason `as_of_missing` or `as_of_invalid`).

   The trace records a `waiver` step with the matching `waiver_id`s, or the
   reason none applied.

**Fail closed to the decision.** In every other case the waiver does not
apply and the governing decision **remains effective** for that context:
revoked, expired or not yet valid; `as_of` not supplied for a time-bound
waiver; labels not supplied (C2 not-supplied context) or not matching; or a
waiver bound to a version other than the active one. A waiver bound to a
non-active version also yields a finding (proposed
`waiver_version_mismatch`), reported only, never blocking (C2 rule).

Waivers are evaluated for global decisions (no declared applicability) as
well as label-scoped ones; the CNCF-modelled positive is global. Multiple
matching waivers are all reported, with ids sorted deterministically.

**Integrity: the resolver never raises on a waiver.** Malformed waiver data
(unknown keys, bad values, a missing feature declaration) is a load-time
refusal under the v2 contract. Semantic problems are non-blocking findings:
a waiver whose target decision does not exist (proposed
`dangling_waiver_target`) and a waiver bound to a non-active version
(`waiver_version_mismatch`). A waiver on a decision that is superseded,
deprecated or inactive is never evaluated (step 1). Existing findings such as
`supersession_lifecycle_conflict` are unaffected and still never block.

The decision itself is never mutated. Precedence, supersession and
applicability semantics are unchanged.

### 3.3 Authority operations

- Two explicit Mneme authority operations, as CLI commands (names fixed by
  the implementation PR), for example `mneme decision waive` and
  `mneme decision revoke-waiver`. They are the **only** writers of waiver
  records.
- Both follow ADR-030 writer discipline: verify the canonical state before
  mutating, write atomically, reload and verify, never repair, never migrate
  implicitly (v1 memory → refuse with the migration message).
- `waive` refuses unless the target decision exists, is lifecycle-active,
  the bound version is its active version, scope is non-empty, `requester`,
  `approver`, `approval_reference` and `reason` are present, and
  `approver != requester`.
- `revoke-waiver` sets `status` to `revoked` and records the revocation; it
  never deletes the record. Waiver records are otherwise immutable.
- Expiry is never written by a clock: an expired waiver stays `active` in the
  file and simply does not apply at an `as_of` past `valid_until`.

### 3.4 What authority means, honestly

Mneme does not authenticate identities (ADR-031 §6: no RBAC, SSO or directory
authority). `requester` and `approver` are recorded claims, and the
requester/approver distinctness rule is a string check only. Where a
repository protects `.mneme/` with a reviewed change path, a waiver is as
trustworthy as that review. In Core today that path is CI R0's bounded
dogfooding on `main`: the trusted gate refuses `.mneme/` changes, which merge
only through one recorded human bypass actor, a procedure rather than
administrator-resistant enforcement. Mneme provides no such protection by
default in adopter repositories. The charter claims nothing beyond this, and
the #497 host-side controls (G1, G3) stay open.

### 3.5 Self-authorization safeguards

- No producer path creates, edits or revokes waivers: the Decision MCP tool
  set is unchanged (ADR-027), and the proposal store cannot carry or
  materialize a waiver; accepting a proposal never creates one.
- Hooks, the C1a preview, Audit, protection and every other runtime surface
  never write waivers.
- Requester/approver distinctness is enforced at write time; an agent identity string
  used as `approver` is not detectable by Mneme and is covered by the review
  trust root in §3.4.
- Implicit approvals (for example an approval embedded in code review, as in
  the Kubernetes candidate in the evidence packet) are evidence a human may
  turn into a waiver through §3.3, never a waiver by themselves.

### 3.6 Waiver, applicability and supersession stay distinct

| Situation | Mechanism | Result |
|---|---|---|
| Decision declares where it governs | applicability (DG1B1) | `not_applicable` outside its labels |
| Decision is replaced | supersession / lifecycle | `lifecycle_superseded`; no waiver involved |
| Decision governs here, but an authorized, bounded exception applies | waiver (DG1B2a) | `waived`; decision unchanged and still effective everywhere else |

The evidence packet's cases become fixtures (§4): the CNCF picolibc/Hyperlight
case (modelled with an explicit Mneme decision and version; the CNCF policy
SHA is provenance only) as the positive; the DfE CSP carve-out as an
applicability negative; a supersession negative.

### 3.7 Outputs

- `GovernanceResolution`: cause `waived`, a `waiver` trace step, and a new
  `waiver_ids` field on `DecisionResolution`; semantics id bumps (proposed
  `mneme.governance-semantics/dg1b2a-1`). The C2 test that pins the current
  semantics id changes deliberately and is not counted as a golden diff.
- `resolve_change`: a decision becoming or ceasing to be waived appears
  through the existing kinds (`became_ineffective`, `became_effective`,
  `resolution_cause_changed`); waiver ids travel on the resolutions. A waiver
  change that does not alter any resolution for the given context produces
  no change entry; the listing covers it. For example, adding a second
  waiver that matches an already-waived decision leaves the resolution
  unchanged and produces no entry. **`resolve_change` is therefore not a
  waiver lifecycle audit**, and DG1B2a provides none: the listing shows
  current waiver state, and history (creation, revocation, superseded
  approvals) is reconstructed only from version control of the memory file.
- A read-only waiver listing (for example `mneme decision waivers`).
- **C1a preview (informational, non-authoritative):** it supplies
  caller-asserted labels but no `as_of`, so untimed label-scoped waivers
  would show as `waived`. The preview output must label that resolution as
  informational; it is not an enforcement input and does not change what
  `mneme check` or any other §3.8 surface enforces or reports. Any waiver finding
  (`dangling_waiver_target`, `waiver_version_mismatch`) makes the preview
  report PREVIEW UNAVAILABLE through its existing finding gate. Both outputs
  appear only for memory that contains waivers, which no memory does today;
  existing preview output is unchanged and pinned by the C2 goldens. The
  finding gate is not narrowed by this charter.

### 3.8 Unchanged

Projection (waivers never affect it), `mneme check` stdout, JSON and exit
codes, hooks, CI gates, MCP tools and responses, `decision.applicable_to`,
Audit, setup readiness, `protect list/status/validate/activate`, evidence
matching, ADR-026 formulas, ADR-020 rule applicability, retrieval, and
benchmark fixtures, for well-formed waiver memory read by a binary that
supports the waiver feature. The C3a consumers resolve with labels not
supplied, so no waiver ever applies to them (§3.2). Older readers refuse
waiver memory (§6).

## 4. Required acceptance evidence

**Goldens first:** C2 and C3a goldens unchanged, byte for byte, on Linux CI
and a local Windows run.

**Fixtures and tests** (each negative must fail if its guard is removed):

1. Positive: CNCF-modelled waiver, label-scoped, no time bound → `waived`
   with matching labels; decision effective without them.
2. Expiry at `as_of`: synthetic time-bound waiver (no real time-bound case was
   found; the fixture is labelled synthetic) → `waived` inside the window,
   effective before `valid_from` and at or after `valid_until`, effective when
   `as_of` is not supplied.
3. Out-of-scope labels; labels not supplied → decision effective.
4. Revoked waiver → decision effective; record retained.
5. Version mismatch: waiver bound to an older version after a new decision
   version → decision effective plus `waiver_version_mismatch` finding.
6. Applicability negative (DfE-modelled carve-out) and supersession negative →
   no waiver semantics involved.
7. Authority: `waive` refuses missing fields, empty scope, `approver ==
   requester`, inactive targets and non-active versions; v1 memory refuses
   with the migration message; writes are atomic and reload-verified; no
   repair.
8. Self-authorization: the MCP tool set is unchanged; proposal acceptance
   cannot create a waiver; no runtime surface writes waivers.
9. v2 contract: closed waiver key set, feature declaration required, readers
   without the feature refuse the document; `waivers` without the feature,
   the feature without `waivers`, and an empty `waivers` array each refuse;
   `null` optional keys refuse; `revocation` present iff revoked.
9a. Identity and serialization (§3.1.2): a golden `waiver_id` for a fixed
   payload; label order and duplicates do not change the id; every creation
   field does; `status`, `revocation` and `created_at` do not; a tampered id
   and a duplicate id each refuse at load; rows are written sorted by
   `waiver_id`; revocation keeps the id.
10. Projection and every §3.8 surface unchanged with waivers present.
11. Time and integrity edge cases: unparseable `as_of`; multiple waivers with
    deterministically sorted ids; a waiver on a superseded or deprecated
    decision (not evaluated); a waiver on a decision that also has a
    `supersession_lifecycle_conflict` finding; a waiver on a `not_applicable`
    decision (labels match the waiver but not the decision, so it stays
    `not_applicable`); a dangling waiver target (finding, no raise).
12. C1a preview: a waiver finding produces PREVIEW UNAVAILABLE; a `waived`
    resolution is labelled informational, and `mneme check` output for the
    same memory and change is unchanged.
13. A reader without the waiver feature (for example `mneme-hq==0.11.0`)
    refuses waiver memory.

**Regression floor:** all DG1 tests, the full gate battery, the frozen Layer 1
benchmark (7/7) and an independent review against this section.

## 5. Explicit non-goals

DG1B2a does not: let any runtime consumer act on waivers (DG1B2b); provide a
trusted context or `as_of` source; authenticate identities; add rule-level or
path-scoped waivers; add licence semantics or import external exception
registries; expire waivers by reading the clock; infer waivers from PR
approvals or other implicit signals; add MCP tools; or change schema v1.

## 6. Risks and controls

| Risk | Control |
|---|---|
| A waiver silently weakens enforcement | DG1B2a has no authoritative consumer; the C1a preview display is informational only (§2, §3.7); DG1B2b needs its own charter and freeze amendment |
| Waiver identity drifts between implementation and later readers | id derivation, persistence location and serialization fixed in §3.1.1 and §3.1.2; loader recomputes ids |
| `resolve_change` mistaken for a waiver audit trail | §3.7 states it is not one; history comes from version control |
| An agent grants itself a waiver | only the explicit CLI operations write; no producer, hook or MCP path; `.mneme/` changes go through the reviewed path (§3.4) |
| A waiver outlives the decision it was granted against | exact version binding; mismatch never applies and is reported |
| Time handling depends on the clock | expiry only at a supplied `as_of`; missing `as_of` → waiver does not apply |
| Waivers used for retirement | non-empty scope required in DG1B2a (deliberate limitation, §3.1); lifecycle operations stay the route for retirement |
| Missing or conflicting context drops protection | fail closed to the decision in every unclear case |
| Overclaiming authority | §3.4 states the trust root and its limits |
| Older binaries, and the CI R0 pinned evaluator, refuse memory containing waivers, so `check`, hooks, MCP and the trusted gate fail on it | ADR-031 §8 release notes; bump the trusted-gate evaluator pin before any waiver is written to Core memory |
| A malformed waiver row fails the whole load for every surface | write-time validation by the only writers (§3.3); load-time refusal is the intended v2 behavior |
| Requester, approver and revocation identities persist in committed memory and git history (personal data) | record opaque handles, not personal details; document this for adopters; revoked records are retained by design |

## 7. Decisions for the owner before merge

1. Accept the DG1B2a / DG1B2b split, with no authoritative consumption in
   DG1B2a.
2. Require non-empty scope as a deliberate DG1B2a limitation (§3.1).
3. Accept the trust-root statement in §3.4 (Mneme records identity claims
   and does not authenticate them; the repository's reviewed `.mneme/` change
   path is the authority check).
4. Accept the additive C1a preview behavior in §3.7, explicitly
   informational and non-authoritative.
5. Accept the persistence location and identity contract in §3.1.1 and
   §3.1.2 as public and frozen with this charter.

## 8. Recording

After the implementation merges, a #497 completion record lists what DG1B2a
delivered and keeps DG1B2b, DG1F-C1b and DG1G open.

## 9. Approval sequence

1. This charter: independent review and merge. Authorizes nothing to run.
2. `[layer1-freeze]` amendment: a separate PR authorizing exactly DG1B2a
   (§3), restating §3.1.1, §3.1.2, §3.8 and §5. Separate approval.
3. Goldens confirmation and fixtures, then the implementation PR, with
   independent review against §4.
