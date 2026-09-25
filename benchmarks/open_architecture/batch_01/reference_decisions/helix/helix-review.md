# Helix Reference Decision Review Packet

**Repository:** AZX-PBC-OSS/helix
**Pinned Commit:** 37d994370deba2512588b5c4efb7f03483e7308b
**Total Records (Planned):** 20
**Currently Drafted:** 5 (records 001–005)
**Records 006–020:** Not yet created
**Status:** Drafted; pending human review

---

## Summary by Sampling Category

| Category | Quota | Proposed | Drafted |
|---|---:|---:|---:|
| clear_explicit | 5 | 5 | 5 ✓ |
| scoped | 5 | 5 | 0 |
| lifecycle_or_supersession | 3 | 3 | 0 |
| ambiguous_or_conflicting | 3 | 3 | 0 |
| enforcement_potential | 2 | 2 | 0 |
| unusual_or_difficult | 2 | 2 | 0 |
| **Total** | **20** | **20** | **5** |

---

## Records for Review (001–005)

### clear_explicit (5)

| ID | ADR | Title | Classification | Authority | Key Decision |
|---|---|---|---|---|---|
| ref-helix-001 | 0020 | Static-only hosted apps in v1 | prescriptive | explicitly_accepted | Host static frontends only; all dynamic capability via `/_api/*` gateway |
| ref-helix-002 | 0015 | App-data three scopes (user/collection/shared) | prescriptive | explicitly_accepted | Three scopes with writer≠reader asymmetry; append-only collection |
| ref-helix-003 | 0018 | Upload-only deploys, immutable versions, preview→live pointer flip | prescriptive | explicitly_accepted | Upload-only deploys; immutable versions; atomic pointer flip for promote/rollback |
| ref-helix-004 | 0014 | Same-origin `/_api/*` gateway as single choke point | prescriptive | explicitly_accepted | Gateway at `/_api/*` on app origin; no CORS; session cookie authenticates |
| ref-helix-005 | 0003 | Dependency-minimal edge, hand-written SQL, no ORM | prescriptive | accepted | Dependency-minimal edge; no ORM; hand-written SQL; hand-rolled undici |

---

## Remaining Candidates (006–020) — Not Yet Drafted

### scoped (5)
- ref-helix-006 — ADR-0019: Subdomain-per-app isolation with host-scoped cookies
- ref-helix-007 — ADR-0017: Edge registry projection over Postgres LISTEN/NOTIFY
- ref-helix-008 — ADR-0006: SecretStore custody seam (dev envelope / prod Key Vault)
- ref-helix-009 — ADR-0016: Capability manifest + approval classifier
- ref-helix-010 — ADR-0008: LLM vendor key resolved by egress

### lifecycle_or_supersession (3)
- ref-helix-011 — ADR-0011: In-memory rate-limiting superseded by shared Postgres counter
- ref-helix-012 — ADR-0030: Repo-backed apps pull CI-built attested artifacts (Proposed)
- ref-helix-013 — ADR-0031: MCP-first delegated auth (Proposed)

### ambiguous_or_conflicting (3)
- ref-helix-014 — ADR-0007: Portal authz v0 (authenticated == authorized) with BOLA gap
- ref-helix-015 — ADR-0009: Relaxed CSP (revisit — supply-chain hardening)
- ref-helix-016 — ADR-0010: Anonymous writes to shared keys on public apps (revisit)

### enforcement_potential (2)
- ref-helix-017 — ADR-0013: Egress trust model (harden instruction seam; phased resolution)
- ref-helix-018 — ADR-0005: Egress SSRF + secret injection (deterministic controls; deployFirewall optional)

### unusual_or_difficult (2)
- ref-helix-019 — ADR-0035: Platform-owned service worker for offline capability
- ref-helix-020 — ADR-0028: Single-tenant customer-deployed model parameterizing 6 prior decisions

---

## Review Instructions

For each record (once all 20 are drafted), please:

1. **Accept** — Record is correct and complete
2. **Correct** — Modify specific fields (note which)
3. **Mark Ambiguous** — Record needs clarification
4. **Reject** — Record should not be in reference corpus (state why)

### Key Questions per Record

- Is the `source_location` accurate and verifiable in the pinned commit?
- Does the `normalized_decision` accurately reflect the source evidence?
- Are `classification`, `decision_domains`, `decision_purposes` using exact O1A vocabulary?
- Is `authority_status` correctly assigned per O1A meanings?
- Are `scopes`, `lifecycle`, `relationships` supported by evidence?
- Is `enforcement_potential` classification justified?
- Does `sampling_category` match the intended quota design?
- Any `ONTOLOGY_GAP` concerns?

### Special Cases to Note

1. **ref-helix-005 (ADR-0003)**: ONTOLOGY_GAP recorded — source explicitly states discipline enforced in review with no automated gate. Scalar `enforcement_potential` cannot represent both mechanical enforcement and review discipline.
2. **ref-helix-006–010, 016–020**: Not yet drafted. Source ADRs exist at pinned commit.
3. **ADR-0026/0030/0031**: ADR-0030 (Proposed) explicitly states ADR-0026 is NOT superseded; gates remain if hosted builds revisited. ADR-0031 (Proposed) has amendment narrowing scope after `hmac-timestamp` shipped.
4. **All records**: Must remain `human_review_status: pending` until Theo explicitly approves.

---

## Verification Checklist

- [ ] All 20 records present with unique `ref-helix-XXX` IDs
- [ ] All source locations point to valid lines in pinned commit `37d994370deba2512588b5c4efb7f03483e7308b`
- [ ] All taxonomy fields use exact O1A vocabulary
- [ ] No `cand-*` IDs used as reference IDs
- [ ] All `human_review_status` = "pending" (for drafted records)
- [ ] Sampling quota: 5/5/3/3/2/2 = 20 ✓
- [ ] No machine prediction fields present
- [ ] Corpus hash computed (after all 20 drafted)

---

## Boundary Confirmation

This corpus is research data only. It does not create canonical decisions, accepted proposals, rules, or enforcement evidence.

No frozen semantic execution code is part of this draft.
No scenarios, repository 3 classifier experiments, ontology redesign, or D1B work is included.

---

## Files Created (001–005)

- `benchmarks/open_architecture/batch_01/reference_decisions/helix/ref-helix-001.jsonl` — ADR-0020 (static-only apps)
- `benchmarks/open_architecture/batch_01/reference_decisions/helix/ref-helix-002.jsonl` — ADR-0015 (app-data three scopes)
- `benchmarks/open_architecture/batch_01/reference_decisions/helix/ref-helix-003.jsonl` — ADR-0018 (deploy model)
- `benchmarks/open_architecture/batch_01/reference_decisions/helix/ref-helix-004.jsonl` — ADR-0014 (same-origin gateway)
- `benchmarks/open_architecture/batch_01/reference_decisions/helix/ref-helix-005.jsonl` — ADR-0003 (dependency-minimal edge)

---

## Ontology-Gap Note (Corrected)

**Clause-level amendment / partial replacement not cleanly represented by whole-decision lifecycle**

The frozen `lifecycle_status` and `supersedes` fields model whole-ADR supersession. They cannot represent:
- ADR-0019's 2026-07-22 amendment reframing the eTLD+1 gap as a per-deployment topology (ADR-0028)
- ADR-0011's 2026-09 amendment changing `trustProxy` from hop-count to address-form (Fastify 5.12.1 removed hop-count form)
- ADR-0013's explicit phased Resolution (Step 1 ✅, Step 2 partial assert-when-present, Step 3 open)

---

**Please review and return with your decisions for records 001–005.**