# Modonome Reference Decision Review Packet

**Repository:** enumind/modonome
**Pinned Commit:** 7a4d5244dcb6879b6aa646105b39297aa6d0a5a2
**Total Records:** 20 (5 drafted in Batch 1)
**Status:** 5 reviewed; 15 remaining

---

## Summary by Sampling Category

| Category | Quota | Selected |
|---|---:|---:|
| clear_explicit | 5 | 5 |
| scoped | 5 | 0 |
| lifecycle_or_supersession | 3 | 0 |
| ambiguous_or_conflicting | 3 | 0 |
| enforcement_potential | 2 | 0 |
| unusual_or_difficult | 2 | 0 |
| **Total** | **20** | **5** |

---

## Batch 1 Records (Drafted)

| Reference | Source ADR | Title |
|---|---|---|
| ref-modonome-001 | ADR-001 | Two-tier self-governance model |
| ref-modonome-002 | ADR-002 | Shadow mode removal/deferral |
| ref-modonome-003 | ADR-004 | MODONOME_ARMED runtime enforcement |
| ref-modonome-004 | ADR-005 | event/type metrics field-name correction |
| ref-modonome-005 | ADR-005 | Per-item transition logging |

---

## Original Draft Preservation

**Draft Corpus Hash (SHA256):** `71c75a1bed42aad6b380a9984b1145703ecbcaf863e80c114832ca63b8608f05`

This hash is computed over the concatenated original draft JSONL files:
- `ref-modonome-001.jsonl` (original)
- `ref-modonome-002.jsonl` (original)
- `ref-modonome-003.jsonl` (original)
- `ref-modonome-004.jsonl` (original)
- `ref-modonome-005.jsonl` (original)

The hash was computed before any corrections were applied. This preserves the exact original draft state for first-pass scoring.

---

## Original Nemotron Semantic Exact-Pass for Batch 1

**0/5 (0%)** — All five records required semantic corrections per Theo's approved review.

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

---

## Original First-Pass Score

**MODONOME BATCH 1 ORIGINAL SEMANTIC EXACT-PASS: 0/5**

This score applies to the ORIGINAL drafts before correction and must not be recalculated from corrected records.

---

## Files Changed (Batch 1 Corrections)

- `benchmarks/open_architecture/batch_01/reference_decisions/modonome/ref-modonome-001.jsonl`
- `benchmarks/open_architecture/batch_01/reference_decisions/modonome/ref-modonome-002.jsonl`
- `benchmarks/open_architecture/batch_01/reference_decisions/modonome/ref-modonome-003.jsonl`
- `benchmarks/open_architecture/batch_01/reference_decisions/modonome/ref-modonome-004.jsonl`
- `benchmarks/open_architecture/batch_01/reference_decisions/modonome/ref-modonome-005.jsonl`

---

## Verification Checklist

- [x] All 5 records present with unique `ref-modonome-XXX` IDs
- [x] All source locations point to valid lines in pinned commit `7a4d5244dcb6879b6aa646105b39297aa6d0a5a2`
- [x] All taxonomy fields use exact O1A vocabulary
- [x] All `human_review_status` = "reviewed"
- [x] Sampling category: `clear_explicit` = 5 ✓
- [x] No machine prediction fields present
- [x] Corpus hash computed and recorded above
- [x] Original first-pass score recorded: 0/5
- [x] Draft corpus hash recorded: `71c75a1bed42aad6b380a9984b1145703ecbcaf863e80c114832ca63b8608f05`
- [x] All corrections applied per approved list above
- [x] No relationships added (all remain `[]`)
- [x] Architecture isolation maintained

---

## Boundary Confirmation

This corpus is research data only. It does not create canonical decisions, accepted proposals, rules, or enforcement evidence.

No frozen semantic execution code is part of this draft.
No scenarios, repository 3 work, classifier experiments, ontology redesign, or D1B work is included.