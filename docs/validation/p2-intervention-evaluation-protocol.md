# P2A — Intervention Evaluation Protocol (LOCK)

Status: **protocol only — no candidate results generated or inspected**
Date: 2026-08-22
Predecessor: [P1 diagnosis](p1-retrieval-precision-diagnosis.md) (merged `fe488efb`)
Gate discipline: this file is committed and reviewed **before** any P2B execution.
After lock, the protocol is executed unchanged; all grid values are reported, including
unfavorable ones; no value may be added after outcomes are seen.

---

## 1. Environment pins

| Item | Value |
|---|---|
| Canonical `main` commit | `fe488efb8017fb34411e398a893f933e8b03734e` |
| `mneme/decision_retriever.py` | sha256 `8EA03377…1D7DD2`, git blob `ac9a1c13` |
| `mneme/context_builder.py` | sha256 `73B08965…66FE6DEA`, git blob `b7ec6fc7` |
| `mneme/benchmark.py` | sha256 `DCB970E1…636DD5`, git blob `377be8d8` |
| `mneme/memory_store.py` | sha256 `0BC7BC9E…474AE6D`, git blob `836bb37f` |
| Frozen benchmark corpus `examples/project_memory.json` | sha256 `955792E2…CEE265C`, git blob `b07c4bee` |
| Live memory `.mneme/project_memory.json` | sha256 `BBBE873F…BE9F9CA`, git blob `39b17fd4` |

The archived experimental retriever (`archive/r1-r6-experimental-tree-2026-08-22`,
hash `F86B3BA2…`) is excluded from every candidate.

## 2. Evaluation surfaces

| Surface | Corpus | Role |
|---|---|---|
| S1 — frozen regression | `examples/project_memory.json` (11 decisions) | Regression instrument; must not degrade |
| S2 — live-memory probes | `.mneme/project_memory.json` (15 decisions) | Retrieval-quality diagnostic |

## 3. Probe set (frozen — five queries, verbatim from P1 §4)

| # | Query string (exact) |
|---|---|
| Q1 | `What database should we use for analytics?` |
| Q2 | `Can we switch the newsletter to Mailchimp?` |
| Q3 | `How do we deploy the marketing site?` |
| Q4 | `Should we rewrite the CLI in Rust?` |
| Q5 | `Add pagination to the insights listing page` |

No sixth query is inferred or added. The probe set is fixed before any candidate run.

### Relevance judgment method

Labels proposed by the investigating agent, **amended and ratified by the maintainer at protocol
review before execution** (ratified 2026-08-22). Labels are frozen thereafter.

| # | Label | Rationale for label |
|---|---|---|
| Q1 | *(none)* | Current live memory contains no storage/database decision; any injection is noise |
| Q2 | *(none)* | No vendor/platform-provider selection decision exists in live memory |
| Q3 | *(expected: `ADR-016`)* | ADR-016 transfers source and deployment ownership of mnemehq.com to `MnemeHQ/mnemehq-site` and names `PUBLISHING.md` there as the canonical deployment-governance source — it directly governs deployment questions |
| Q4 | *(none)* | No language/rewrite-scope decision exists |
| Q5 | *(expected: `ADR-016`)* | ADR-016 records that core no longer owns active website governance (scope `repo.site_transfer`); an insights-listing change is directly governed by that ownership transfer — the correct outcome is retrieval of `ADR-016`, routing the work to `mnemehq-site` |

Q1/Q2/Q4 deliberately remain *none*: lexical overlap with tangential memory text
(analytics, marketing, CLI vocabulary) does not make a decision relevant, and labeling such
overlap as relevant would weaken the diagnostic.

## 4. Candidate definitions

Baseline B0 = canonical retriever, unchanged, on both surfaces.

### C — Memory-content hygiene (live memory copy only)

Mechanical transforms applied to a working copy of `.mneme/project_memory.json`;
the canonical file itself is never modified:

- **C1 rationale-prose separation:** replace each Decision's `rationale` with its first
  sentence if that sentence is ≤ 240 characters, else with `decision` text verbatim.
  Grid: `rationale_mode ∈ {first_sentence, decision_text}`.
- **C2 near-duplicate marking:** none — live memory currently exhibits no exact duplicate pair
  (duplication was a fixture-corpus property). C2 is recorded as *not applicable on S2*;
  it remains defined so P2B cannot silently add it.

### F — Injection floor (simulation wrapper around retrieval output)

Inject only decisions with `score ≥ floor`. Grids:

- absolute: `floor_abs ∈ {0.5, 1.0, 1.5, 2.0, 2.5}`
- relative: `floor_rel ∈ {0.25, 0.33, 0.50}` × top-score of the query

Applied identically on both surfaces.

### T — Tokenizer extension

Extended stopword sets, mechanically enumerated:

- **T1 interrogatives/demonstratives:** `{what, when, where, which, would, could, should,
  this, that}`
- **T2 = T1 ∪ function prepositions/conjunctions:** `{using, between, without, about,
  into, onto, while}`
- stemming: **not** included in any T variant (recorded as out of grid, not deferred silently)

Grid: `stopwords ∈ {T1, T2}`.

### W — Field/weight reform

- **W1 rationale demotion:** weight `rationale ∈ {0.0, 0.25}` (baseline 0.5)
- **W2 rationale cap:** cap rationale match count at `cap ∈ {1, 2}` per decision
- combinations: W1×W2 evaluated jointly → grid size 2 × 2 = 4

Total planned runs: B0 (both surfaces) + C (2 variants) + F (8 values) + T (2 variants)
+ W (4 variants), each on S1 and S2.

## 5. Metrics

- **S1 regression gates (per candidate):**
  - shipped benchmark verdicts: 7/7 PASS (no WEAK_RETRIEVAL regressions);
  - recall@3 = 1.00 across the n=5 protected scenarios;
  - `layer1_retrieved_ids` changes vs B0 are **recorded, not gated**;
  - precision@3 is recorded but structurally constrained under K=3 — reported per Step 3C, never used as a gate or tuning signal;
  - recall@1 is reported as the sharper ranking signal.
- **S2 diagnostic metrics:** rank-1 relevance rate, MRR, tail-injection count, zero-score injection count.

## 6. Amendment classification (pre-declared)

| Candidate | Requires architecture amendment if adopted? |
|---|---|
| C on live `.mneme` content | No (memory content operation); fixture-corpus application would require re-baselining decision |
| F | Yes — alters injection/selection semantics |
| T | Yes — tokenizer is named frozen surface |
| W | Yes — field weights/structure are frozen surface |

Offline evaluation of any candidate without adoption does not amend production retrieval.

## 7. Execution rules (P2B, after lock)

1. Run B0 once on both surfaces to fix baseline numbers.
2. Run every grid value from §4 exactly once; report the complete grid including unfavorable results.
3. No new parameter value, variant, or probe may be introduced after any outcome has been seen.
4. Any protocol deviation voids the affected runs and must be recorded in the P2B report.
5. Output: evidence table + amendment classification + recommendation of **at most one** next
   intervention. No production implementation in P2B.

---

*Lock hash: SHA-256 of this file is recorded in the locking commit message. Any edit after lock
requires a new protocol version and re-review.*
