# Modonome Reference Decision Review Packet

**Repository:** enumind/modonome
**Pinned Commit:** 7a4d5244dcb6879b6aa646105b39297aa6d0a5a2
**Total Records:** 20 (10 reviewed)
**Status:** 10 reviewed; 10 remaining

---

## Summary by Sampling Category

| Category | Quota | Selected |
|---|---:|---:|
| clear_explicit | 5 | 5 |
| scoped | 5 | 5 |
| lifecycle_or_supersession | 3 | 0 |
| ambiguous_or_conflicting | 3 | 0 |
| enforcement_potential | 2 | 0 |
| unusual_or_difficult | 2 | 0 |
| **Total** | **20** | **10** |

---

## Batch 1 Records (Reviewed)

| Reference | Source ADR | Title |
|---|---|---|
| ref-modonome-001 | ADR-001 | Two-tier self-governance model |
| ref-modonome-002 | ADR-002 | Shadow mode removal/deferral |
| ref-modonome-003 | ADR-004 | MODONOME_ARMED runtime enforcement |
| ref-modonome-004 | ADR-005 | event/type metrics field-name correction |
| ref-modonome-005 | ADR-005 | Per-item transition logging |

---

## Batch 2 Records (Reviewed)

| Reference | Source ADR | Title |
|---|---|---|
| ref-modonome-006 | ADR-006 | Checker context independence |
| ref-modonome-007 | ADR-006 | Rework cap |
| ref-modonome-008 | ADR-007 | Claim atomicity (one lease per turn) |
| ref-modonome-009 | ADR-008 | Human CODEOWNERS approval |
| ref-modonome-010 | ADR-010 | Owner promotion gate |

---

## Original Draft Preservation

### Batch 1 Draft Preservation

**Draft Corpus Hash (SHA256):** `71c75a1bed42aad6b380a9984b1145703ecbcaf863e80c114832ca63b8608f05`

This hash is computed over the concatenated original draft JSONL files:
- `ref-modonome-001.jsonl` (original)
- `ref-modonome-002.jsonl` (original)
- `ref-modonome-003.jsonl` (original)
- `ref-modonome-004.jsonl` (original)
- `ref-modonome-005.jsonl` (original)

The hash was computed before any corrections were applied. This preserves the exact original draft state for first-pass scoring.

### Batch 2 Draft Preservation

**Batch 2 Draft Corpus Hash (SHA256):** `f1bd282b9d43e8803b636968cd77c803666d96c44f1b15c62c475c31e293e7a2`

Individual original draft hashes (recorded before correction):
- `ref-modonome-006.jsonl`: `80f8cf3bca8cbc55d1fc33464ea7e0c436ddc56ab706bd3e410e32961891049a`
- `ref-modonome-007.jsonl`: `de6b8b6a4e4e1d38c4a89cb6467bf87a8e00554f86addf745b4040832e7e152d`
- `ref-modonome-008.jsonl`: `de94e5b84e8de54ff996e713fee354650d28df2206ce8a9adf90b1a0a7f6dce6`
- `ref-modonome-009.jsonl`: `520f2a5fdb53c47eee5712bfb66ad9f42c202f2989390eb76f003b536e5cda43`
- `ref-modonome-010.jsonl`: `714dd1e6ba3ff8f5058e22300f2d1db479614409ddcb804fa98c0b6ceffd0b2d`

---

## Original Nemotron Semantic Exact-Pass for Batch 1

**0/5 (0%)** — All five records required semantic corrections per Theo's approved review.

---

## Original Nemotron Semantic Exact-Pass for Batch 2

**1/5 (20%)** — ref-modonome-006 passed; ref-modonome-007 through ref-modonome-010 required semantic corrections per approved review.

---

## Review Instructions

For each record, please:
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

---

## Special Cases to Note (Approved Corrections)

### ref-modonome-001 (ADR-001)
- effective_date must be null (ADR date does not establish decision effective date)
- raw_evidence/source_location must narrow to the tier split only (lines 18-26)
- Remove work-item queue mechanics, ratchet mechanics from evidence/decision
- normalized_decision must be the tier split only
- Re-evaluate domains/purposes to minimum supported by tier split

### ref-modonome-002 (ADR-002)
- effective_date must be null
- raw_evidence must match exact ADR enumeration (if files not enumerated in ADR, remove from scopes/decision)
- Remove `deprecate` purpose (shadow mode deferred, not deprecated)
- Remove `scripts/` from scopes (future implementation scope ≠ current decision)
- Future WI-011 remains future/deferred intent only

### ref-modonome-003 (ADR-004)
- effective_date must be null
- Remove `allocate_ownership` from purposes
- Re-evaluate `deployment_infrastructure` domain (may reduce to `security_privacy` only)
- Purposes: prefer minimum exact (`constrain`/`prohibit`)

### ref-modonome-004 (ADR-005)
- effective_date must be null
- raw_evidence must match exact source (L24-L25 only)
- Remove "causing all counters to show zero" if not in exact source range
- `standardize` purpose only; remove `constrain` unless independently supported
- Verify `schemas/metrics.schema.json` path is in exact source

### ref-modonome-005 (ADR-005)
- effective_date must be null
- Remove generic `constrain` purpose; `require_evidence` is the specific supported purpose
- Verify `.modonome/metrics.jsonl` path is in exact source; do not strengthen provenance
- Keep isolated from per-run logging

---

## Human Review Status

| Reference | Status |
|---|---|
| ref-modonome-001 | reviewed |
| ref-modonome-002 | reviewed |
| ref-modonome-003 | reviewed |
| ref-modonome-004 | reviewed |
| ref-modonome-005 | reviewed |
| ref-modonome-006 | reviewed |
| ref-modonome-007 | reviewed |
| ref-modonome-008 | reviewed |
| ref-modonome-009 | reviewed |
| ref-modonome-010 | reviewed |

---

## Original First-Pass Score

- **MODONOME BATCH 1 ORIGINAL SEMANTIC EXACT-PASS: 0/5**
- **MODONOME BATCH 2 ORIGINAL SEMANTIC EXACT-PASS: 1/5**

These scores apply to the ORIGINAL drafts before correction and must not be recalculated from corrected records.

---

## Files Changed (Batch 1 Corrections)

- `benchmarks/open_architecture/batch_01/reference_decisions/modonome/ref-modonome-001.jsonl`
- `benchmarks/open_architecture/batch_01/reference_decisions/modonome/ref-modonome-002.jsonl`
- `benchmarks/open_architecture/batch_01/reference_decisions/modonome/ref-modonome-003.jsonl`
- `benchmarks/open_architecture/batch_01/reference_decisions/modonome/ref-modonome-004.jsonl`
- `benchmarks/open_architecture/batch_01/reference_decisions/modonome/ref-modonome-005.jsonl`

---

## Files Changed (Batch 2)

- `benchmarks/open_architecture/batch_01/reference_decisions/modonome/ref-modonome-006.jsonl`
- `benchmarks/open_architecture/batch_01/reference_decisions/modonome/ref-modonome-007.jsonl`
- `benchmarks/open_architecture/batch_01/reference_decisions/modonome/ref-modonome-008.jsonl`
- `benchmarks/open_architecture/batch_01/reference_decisions/modonome/ref-modonome-009.jsonl`
- `benchmarks/open_architecture/batch_01/reference_decisions/modonome/ref-modonome-010.jsonl`

---

## Verification Checklist

- [x] All 10 records present with unique `ref-modonome-XXX` IDs
- [x] All source locations point to valid lines in pinned commit `7a4d5244dcb6879b6aa646105b39297aa6d0a5a2`
- [x] All taxonomy fields use exact O1A vocabulary
- [x] All `human_review_status` = "reviewed" for 001–010
- [x] Sampling quota progress: `clear_explicit` = 5/5 ✓, `scoped` = 5/5 ✓
- [x] No machine prediction fields present
- [x] Original first-pass scores recorded: Batch 1: 0/5, Batch 2: 1/5
- [x] Draft corpus hashes recorded:
  - Batch 1: `71c75a1bed42aad6b380a9984b1145703ecbcaf863e80c114832ca63b8608f05`
  - Batch 2: `f1bd282b9d43e8803b636968cd77c803666d96c44f1b15c62c475c31e293e7a2`
- [x] All corrections applied per approved review
- [x] No relationships added (all remain `[]`)
- [x] Architecture isolation maintained

---

## Boundary Confirmation

This corpus is research data only. It does not create canonical decisions, accepted proposals, rules, or enforcement evidence.

No frozen semantic execution code is part of this draft.
No scenarios, repository 3 work, classifier experiments, ontology redesign, or D1B work is included.