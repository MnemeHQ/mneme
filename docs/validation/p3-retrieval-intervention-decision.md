# P3 — Retrieval Intervention Architecture Decision

Status: **DECISION RATIFIED by maintainer 2026-08-22 — Option A selected, B rejected-for-now,
C not justified. Nothing implemented; record only.**
Date: 2026-08-22
Mode: read-only. `decision_retriever.py`, `.mneme/project_memory.json`, benchmark fixtures, and all
ADRs are untouched.

---

## 1. Verified canonical baseline

| Item | Value |
|---|---|
| Local `main` | `f3aeb692fcf1ff45613337aec31bb932d7501dfa` |
| `origin/main` | identical (`git pull --ff-only`: up to date) |
| P2B merge ancestry | `f3aeb692` (`docs: P2B frozen-grid evaluation results`) confirmed ancestor of `main` |
| Live memory | `.mneme/project_memory.json`, sha256 `BBBE873F…BE9F9CA`, git blob `39b17fd4` |
| Retriever | `mneme/decision_retriever.py`, sha256 `8EA03377…1D7DD2` |

Authorities read before analysis: `docs/architecture/current-phase.md`,
`docs/architecture/layer1-freeze-e73ff7d.md`, Step 3C Retrieval-Tuning Charter
(`docs/plans/2026-05-09-step-3c-retrieval-tuning-charter.md`), ADR-017, ADR-019/ADR-020,
P1 diagnosis (`fe488efb`), P2A protocol lock (`07b324b7`), P2B results (`f3aeb692`).

## 2. Exact problem statement

Query Q5: `Add pagination to the insights listing page`. Query tokens after canonical
tokenization: `{add→stopped, pagination, insights, listing, page}`.

Canonical scoring against live memory:

| Decision | Scored matches | Score |
|---|---|---|
| `ADR-014` (Harness-Complementary Positioning Vocabulary; scope `positioning.harness_vocab`) | rationale ×2: `insights`, `page` | **1.0** |
| `ADR-016` (Site Governance Transfer; scope `repo.site_transfer`) | rationale ×2: `insights`, `page` | **1.0** |
| `workflow-001` | none | 0.0 |

The stable sort resolves the tie by insertion order, placing `ADR-014` first. Ratified ground truth
expects `ADR-016` first. Neither tied record matches any query token outside its imported
rationale markdown; the discriminating signal between them is absent from every scored field.

P2B confirmed from committed evidence (§3 table and §5 of
`docs/validation/p2b-intervention-evaluation-results.md`, merged at `f3aeb692`) that no C/F/T/W grid
variant changes this rank-1 outcome: floors act below rank 1; stopword and weight variants move both
tied scores equally or remove them.

## 3. Architecture constraints

1. **Layer-1 freeze (`e73ff7d`, restated in `current-phase.md`):** retrieval mechanics — bag-of-tokens
   scoring, fixed weights, stopword floor, **insertion-order tiebreak** — are frozen; no behavioral
   change without an explicit charter amendment.
2. **Step 3C charter:** sanctions `recall@1` as the sharpest legitimate tuning signal (§4, §7b);
   historically scoped tie-break changes as tunable with a deterministic test pinned first (§2, §5.5,
   §6). Under the freeze enclosure, that allowance is exercisable only through an explicit amendment;
   the test-pin requirement (§6) remains the minimum process bar for any tie-semantics change.
3. **Determinism contract:** rule-002 in canonical memory and freeze principle
   *deterministic > clever* require any tie resolution to be deterministic and auditable.
4. **Contradictory-decision invariant:** charter §5.6 — retrieval must continue surfacing both
   conflicting decisions; tie semantics may reorder but never suppress a tied record from top-K.
5. **ADR-017:** enforcement scope is independent of retrieval scope; memory-content and retrieval
   mechanics are separable surfaces.
6. **Benchmark pool freeze (charter §3):** the fixture corpus composition is locked; live `.mneme`
   content is a separate surface and is not covered by that lock.

## 4. Option analysis

### A. Governed-memory content / representation

**Mechanism changed:** the authored scored fields (`decision` title, `scope`, `constraints`) of live
`Decision` records — specifically, representing each decision's actual applicability surface in
`scope`, derived from its governing ADR text.

**Does it address Q5?** Partially verifiable today: ADR-016's authority demonstrably covers website
content pages — it supersedes the seven site ADRs including `site.insights_seo`
(`site.persona_pages`, etc.) and transfers ownership of mnemehq.com content and deployment to
`mnemehq-site`. That authority surface is currently represented only as `scope: repo.site_transfer`,
which shares zero query tokens with Q5. Authoring that surface faithfully (e.g., a scope entry
expressing "website content pages, including the insights listing") adds tokens derivable from the
ADR's own text.

**Legitimate representation vs probe tuning — the boundary:** added vocabulary is legitimate only
where it paraphrases authority the ADR already asserts. Adding `site.pages` / `insights` coverage is
derivable from the supersession clause. Adding the literal token `pagination` would be probe tuning
and is rejected: ADR-016 says nothing about pagination.

**Derivability standard (ratified boundary):** representation may make already-decided governance
more explicit when that meaning is directly supported by the source ADR. It must not introduce
query-specific vocabulary merely to improve retrieval on the validation probes.

**Generality:** this is not a one-query patch if applied as a standard — the underlying defect is
that live decisions rely on uncontrolled imported rationale prose for their lexical connection to the
work they govern. Q3 demonstrates the flip side: `ADR-016` ranks first there at 4.5 *only* because
imported prose happens to contain `deploy`/`marketing`/`site`. Rank quality on live memory currently
depends on prose accidents in both directions. A representation standard (scored fields must reflect
the decision's stated applicability) applies to every decision, not to Q5.

**Failure modes / regressions:** over-broad scope vocabulary inflates scores broadly and recreates
noise; per-decision authoring must cite ADR source text. Content changes shift the live retrieval
universe and therefore require re-running the frozen regression surface to confirm S1 is unaffected
(it is a different corpus, so no gate impact is expected, but it must be demonstrated, not assumed).

**Effect on frozen S1 benchmark semantics:** none — fixture corpus untouched; pool composition
unchanged; gates re-run to confirm.

**Requirement classification (ratified):** Option A requires **no retrieval-mechanics amendment**.
For ADR-backed decisions, any representation change must remain reproducible through the
ADR → compiler/import → memory path. If the change affects compiler-derived content or fields, update
the ADR source and regenerate/re-import the corresponding memory entry rather than manually diverging
`.mneme/project_memory.json`.

**Caution — frontmatter scope:** do not broaden an ADR's frontmatter `scope` casually. That field
participates in ADR precedence, so changing it is not merely retrieval representation. Prefer
clarifying already-decided ownership coverage in ADR content first, then regenerate the memory
representation through the compiler/import path.

### B. Retrieval tie semantics

**Mechanism changed:** resolution of equal-score ties (currently Stage-0-pinned insertion order,
`8d7a398`).

**Does it address Q5?** Not demonstrably. At equal score, the two records are indistinguishable in
every scored field except insertion position — there is no scored property on which a generic
deterministic rule could prefer `ADR-016`. Any rule that reliably picks `ADR-016` here would have to
be reverse-engineered from the desired answer, which is special-casing by another name and violates
the decision standard ("no special-case logic for Q5").

**Generality:** the tie class is real but the observed instance count is one. Changing global tie
semantics on a single observation exceeds what the evidence supports.

**Failure modes / regressions:** S1 comparability (P2B already showed retrieved-ID compositions
shift under scoring perturbations); the Stage-0 pin is a documented contract, so changing it
invalidates historical byte-identical retrieval claims; contradictory-decision surfacing must be
re-proven; determinism is preservable but must be test-pinned first (charter §6).

**Effect on frozen S1 benchmark semantics:** potentially material; every protected-scenario top-3
would need re-verification under the new rule.

**Requirement classification:** freeze amendment (retrieval mechanics) + tie-break test pinned
before change + fresh locked evaluation protocol.

### C. Another narrowly scoped mechanism

Not warranted: Option A addresses the observed failure mode at its source without code changes, so
the condition "A and B are insufficient" is not met. Consistent with the decision standard, no
candidate is introduced speculatively; embeddings/vector/LLM reranking remain rejected deferred
architecture.

## 5. Decision matrix

| Criterion | A — memory representation | B — tie semantics | C — other |
|---|---|---|---|
| Addresses observed Q5 failure | Yes, via derivable authority vocabulary | No evidence-backed rule exists; would be outcome-fitted | n/a |
| Generality beyond Q5 | High — fixes reliance on imported prose corpus-wide | Addresses tie class generally, but class observed once | — |
| Smallest justified change | Yes (content-only) | No (global mechanics, n=1 evidence) | — |
| Deterministic / auditable | Preserved | Preservable, but new contract | — |
| Frozen S1 guarantees | Untouched | Potentially material shifts | — |
| Special-casing risk | Managed by derivability standard | High in practice | — |
| Amendment requirement | None | Freeze amendment + test pin + new protocol | — |
| Validation burden | Memory PR + dual-surface re-run | Full new protocol | — |

## 6. Selected intervention class

**A/B/C disposition (ratified by maintainer, 2026-08-22):**

- **A — SELECTED.** Smallest evidence-backed intervention class; code-side `NO_CHANGE`.
- **B — REJECTED FOR NOW.** One observed tie is insufficient evidence to change globally frozen tie
  semantics, and there is no principled secondary ordering rule yet.
- **C — NOT JUSTIFIED.** No need to invent another retrieval mechanism until A is tested under a
  locked protocol.

Option A is selected subject to the derivability standard and the ADR → compiler/import → memory
reproducibility requirement (§4A), and the validation gate below.

Explicitly not selected: F/T/W adoption (P2B negative), role-aware R1–R6 code and the experimental
`rules: 1.5` retriever (P0 verdict), embeddings/vector/semantic reranking (deferred architecture).

If, at validation, faithful representation of ADR authority does **not** resolve Q5 (or regresses
other probes), the correct next step is to return to this decision review rather than iterating
content against the probe set — at which point Option B should be re-examined with an extended
tie-frequency diagnosis establishing how often tied rank-1 pairs occur on live memory.

## 7. Amendment requirement

- **Selected (A):** no retrieval-mechanics amendment. For ADR-backed decisions, any representation
  change must remain reproducible through the ADR → compiler/import → memory path: if the change
  affects compiler-derived content or fields, update the ADR source and regenerate/re-import the
  corresponding memory entry rather than manually diverging `.mneme/project_memory.json`. Frontmatter
  `scope` is precedence-participating and must not be broadened casually; prefer clarifying
  already-decided ownership coverage in ADR content first.
- **Rejected-for-now (B):** would require a freeze amendment naming tie semantics, a deterministic
  tie-break test pinned before implementation, and a newly locked evaluation protocol.

## 8. Implementation-validation gate (high level only)

1. Memory PR proposes scope/title representations for affected live decisions, each addition annotated
   with its ADR-source justification.
2. Evaluation protocol locked **before** results are inspected: frozen S1 regression suite (existing
   gates: 7/7 verdicts, recall@3 = 1.00) plus the ratified five-probe set plus an expanded
   live-memory probe set frozen in advance.
3. Acceptance: S1 gates green; probe rank-1 relevance improves with no new misses; no fixture edits;
   `mneme check --mode warn` clean.
4. Failure of the gate returns the question to decision review (Option B reconsideration with an
   extended tied-rank diagnosis) instead of permitting content iteration against probes.

## 9. Non-goals

- Editing `decision_retriever.py`, `.mneme/project_memory.json`, or any benchmark fixture in this phase
- Amending an ADR
- Implementing tests for a future change
- Running new candidate experiments
- Adopting F/T/W despite the P2B non-recommendation
- Restoring role-aware R1–R6 code or the experimental `rules: 1.5` retriever variant
- Embeddings, semantic search, vector retrieval, LLM reranking, or generalized relevance models
- Changing K, metric formulas, or the governed aggregation filter
- Tuning memory text solely to make the five P2 probes pass
- Starting P4
