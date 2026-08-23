# P2B — Intervention Evaluation Results (Frozen Grid Execution)

Status: **results record — no adoption, no amendment proposed, no production changes**
Date: 2026-08-22
Protocol: [P2A lock](p2-intervention-evaluation-protocol.md), operative hash `DF70FCAC6AED410081952DC99DF97E9709DAABDC02B56E5B13FEB736068D5B8E`

---

## 1. Execution integrity

| Item | Value |
|---|---|
| Operative P2A lock | merged `07b324b7` (protocol head `639c7e18`) |
| Protocol hash | `DF70FCAC…68D5B8E` |
| Variants executed | 17 = B0 + C(2) + F(8) + T(2) + W(4) |
| Surfaces | S1 frozen regression (`examples/`, 11 records) and S2 live-memory probes (`.mneme/`); each variant run once per surface |
| Protocol deviations | **zero** |
| Production / retriever / fixture / memory changes | **none** — execution used a read-only harness replicating canonical scoring, byte-verified against the real `DecisionRetriever` before any candidate ran |

Environment note: code and corpus hashes match every §1 pin of the protocol. The only repository
delta since the pinned commit `fe488efb` is documentation (the protocol itself).

## 2. Baseline B0

### S1 frozen-regression metrics

| Metric | B0 |
|---|---|
| Benchmark verdicts | 7/7 PASS-capable |
| mean recall@3 | 1.000 |
| mean precision@3 (n=5 protected) | 0.333 |
| recall@1 rate | 1.000 |

### S2 live-memory probes — per-query ranked IDs/scores

| Probe | Rank 1 | Rank 2 | Rank 3 |
|---|---|---|---|
| Q1 database/analytics *(none expected)* | `ADR-001` 2.0 (rationale ×4) | `ADR-002` 1.5 | `rule-memory-pr-isolation` 1.5 |
| Q2 newsletter/Mailchimp *(none expected)* | `workflow-001` **0.0** | `encoding_001` **0.0** | `ADR-002` **0.0** |
| Q3 deploy marketing site *(expected `ADR-016`)* | **`ADR-016` 4.5** ✓ | `ADR-014` 1.5 | `rule-public-boundary` 1.5 |
| Q4 CLI rewrite Rust *(none expected)* | `rule-memory-pr-isolation` 1.5 | `ADR-002` 0.5 | `ADR-004` 0.5 |
| Q5 pagination insights page *(expected `ADR-016`)* | `ADR-014` **1.0** ✗ | `ADR-016` **1.0** | `workflow-001` **0.0** |

B0 S2 summary: rank-1 relevance (Q3,Q5) = 0.500; MRR = 0.750; tail injections (ranks 2–3,
irrelevant, all probes) = 9; zero-score injections = 4.

**Q5 is a tied-score case:** `ADR-014` and `ADR-016` both score exactly 1.0
(`rationale: insights`, `page` — two hits each at weight 0.5). The frozen sort is stable, so the tie
resolves by existing insertion order, which places `ADR-014` first.

## 3. Complete candidate table

S1 gates for every row: verdicts PASS-capable and recall@3 = 1.00 → **all 17 variants PASS**.
Changed retrieved IDs are listed under the table; all other rows match B0's top-3 exactly.

| Variant | S1 recall@3 | S1 prec@3 | S1 rec@1 | S1 gate | S2 rank-1 (Q3,Q5) | S2 MRR | S2 tail inj. | S2 zero-score inj. |
|---|---|---|---|---|---|---|---|---|
| **B0** | 1.000 | 0.333 | 1.000 | PASS | 0.500 | 0.750 | 9 | 4 |
| C1:first_sentence | 1.000 | 0.333 | 1.000 | PASS | 0.500 | 0.500 ↓ | 10 ↑ | 10 ↑ |
| C1:decision_text | 1.000 | 0.333 | 1.000 | PASS | 0.500 | 0.500 ↓ | 10 ↑ | 10 ↑ |
| F:abs=0.5 | 1.000 | 0.333 | 1.000 | PASS | 0.500 | 0.750 | 6 | 0 |
| F:abs=1.0 | 1.000 | 0.333 | 1.000 | PASS | 0.500 | 0.750 | 4 | 0 |
| F:abs=1.5 | 1.000 | 0.333 | 1.000 | PASS | 0.500 | 0.500 ↓ | 4 | 0 |
| F:abs=2.0 | 1.000 | 0.400 | 1.000 | PASS | 0.500 | 0.500 ↓ | 0 | 0 |
| F:abs=2.5 | 1.000 | 0.400 | 1.000 | PASS | 0.500 | 0.500 ↓ | 0 | 0 |
| F:rel=0.25 | 1.000 | 0.333 | 1.000 | PASS | 0.500 | 0.750 | 8 | 3 |
| F:rel=0.33 | 1.000 | 0.333 | 1.000 | PASS | 0.500 | 0.750 | 8 | 3 |
| F:rel=0.50 | 1.000 | 0.533 | 1.000 | PASS | 0.500 | 0.750 | 4 | 3 |
| T1 | 1.000 | 0.333 | 1.000 | PASS | 0.500 | 0.750 | 9 | 7 ↑ |
| T2 | 1.000 | 0.333 | 1.000 | PASS | 0.500 | 0.750 | 9 | 7 ↑ |
| W w=0,cap=1 | 1.000 | 0.333 | 1.000 | PASS | 0.500 | 0.500 ↓ | 10 ↑ | 10 ↑ |
| W w=0,cap=2 | 1.000 | 0.333 | 1.000 | PASS | 0.500 | 0.500 ↓ | 10 ↑ | 10 ↑ |
| W w=0.25,cap=1 | 1.000 | 0.333 | 1.000 | PASS | 0.500 | 0.750 | 9 | 4 |
| W w=0.25,cap=2 | 1.000 | 0.333 | 1.000 | PASS | 0.500 | 0.750 | 9 | 4 |

↑ / ↓ mark movements against B0. No row is omitted; unfavorable results are reported as measured.

**S1 `layer1_retrieved_ids` changes vs B0 (recorded, not gated):**

| Variant / scenario | B0 top-3 → candidate top-3 |
|---|---|
| F:abs=2.0, F:abs=2.5 / framework_abstraction_violation | `anti-001, anti-002, mneme_storage_json` → `anti-001, anti-002` |
| F:abs=2.0, F:abs=2.5 / storage_backend_violation | `mneme_storage_json, rule-003, rule-002` → `mneme_storage_json, rule-003` |
| F:rel=0.50 / framework_abstraction_violation | as above → `anti-001, anti-002` |
| F:rel=0.50 / infra_scope_creep_violation | `anti-002, mneme_no_agents_v1, rule-004` → `anti-002` |
| F:rel=0.50 / storage_backend_violation | `mneme_storage_json, rule-003, rule-002` → `mneme_storage_json, rule-003` |
| T2 / feature_boundary_violation | `anti-002, mneme_no_agents_v1, anti-003` → `anti-002, mneme_no_agents_v1, mneme_storage_json` |

All other variants reproduce B0's protected-scenario top-3 exactly.

## 4. Observed effects by candidate family

Measurements first; interpretation is separated and marked.

### C — rationale prose separation

Measured: rank-1 relevance unchanged (Q3 stays rank 1). Q5 changes from `ADR-016@rank2` to MISS.
MRR falls 0.750 → 0.500 on both variants. Zero-score injections rise 4 → 10. Tail noise rises
9 → 10. S1 unchanged everywhere.

Interpretation: rationale text currently contributes the retrieval signal that connects site-governance
decisions to site-related queries in the live corpus; removing it removed signal, not only noise.

### F — injection floor

Measured: no floor value changes any rank-1 outcome on either surface (rank-1 relevance stays 0.500;
MRR 0.750 until floors ≥1.5 drop Q5's rank-2 hit and reduce it to 0.500). Absolute floors ≥0.5
eliminate zero-score injections. Tail noise decreases monotonically with floor height:
9 → 6 (0.5) → 4 (1.0) → 0 (2.0+), but floors ≥1.5 also remove Q5's true positive at rank 2.
Relative floor 0.50 reduces tail noise to 4 while preserving both true retrievals, and trims S1
padding (precision@3 0.333 → 0.533, recorded not gated).

Interpretation: floors act only below the top rank; they cannot alter a rank-1 ordering.

### T — stopword extension

Measured: rank-1 relevance and MRR unchanged (Q3 rank 1, Q5 rank 2 on both T1 and T2).
Tail noise unchanged at 9. Zero-score injections rise 4 → 7. One S1 top-3 composition change
(feature_boundary: `anti-003` → `mneme_storage_json`) with gates unaffected.

Interpretation: within this grid, function-word stopwords did not produce a measured improvement
on either surface.

### W — rationale demotion/capping

Measured: w=0 removes Q5's `ADR-016` retrieval entirely (MISS) and drops MRR to 0.500;
w=0.25 preserves the B0 pattern exactly (rank-1 0.500, MRR 0.750, tail 9, zero-score 4).
Caps made no additional difference at either weight.

Interpretation: same direction as C — rationale weight reductions remove live-corpus signal.

## 5. Q5 tie analysis

Both decisions score 1.0 via identical mechanics:

| Decision | Rationale hits | Matches | Score |
|---|---|---|---|
| `ADR-014` (Harness-Complementary Positioning Vocabulary) | `insights`, `page` | rationale ×2 × 0.5 | 1.0 |
| `ADR-016` (Site Governance Transfer) | `insights`, `page` | rationale ×2 × 0.5 | 1.0 |

The frozen sort is stable; insertion order places `ADR-014` first, so the ratified relevant decision
for Q5 appears at rank 2.

**None of the candidates in the locked grid changes this rank-1 outcome.** Every F value acts below
the top rank or truncates the list; every T/W/C value shifts both tied scores together or removes
them equally. This statement is scoped to the evaluated grid; it does not establish what any
mechanism outside the grid would do.

## 6. Amendment classification

Per the pre-declared classification in the protocol:

| Candidate family | Amendment required if adopted |
|---|---|
| C on live `.mneme` content | No |
| C applied to fixture corpus | Re-baselining decision required |
| F | Yes |
| T | Yes |
| W | Yes |

No amendment is proposed by this report.

## 7. P2B conclusion

The evaluated grid did not identify a code-side retrieval intervention that improves the Q5 rank-1
failure while preserving the frozen regression contract. `F:rel=0.50` reduces lower-ranked noise but
does not change rank-1 relevance. Rationale reduction is not supported as a general remedy because
rationale text contributes relevant retrieval signal as well as lexical noise. Q5 is a tied-score case
under canonical scoring and is resolved by the frozen insertion-order tie-break.

P2B therefore does not recommend adopting F, T, or W from the evaluated grid. Any next intervention
should be selected in a separate P3 decision after reviewing whether the Q5 failure is better
addressed through governed-memory content, retrieval tie semantics, or another explicitly scoped
mechanism.
