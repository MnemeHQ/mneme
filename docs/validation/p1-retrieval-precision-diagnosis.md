# P1 Diagnosis: Retrieval Precision on Canonical `main`

Status: **read-only diagnosis complete — no retriever, fixture, or enforcement changes made**
Date: 2026-08-22
Scope: canonical `main` (`b8379788`) only. The archived experimental retriever
(`archive/r1-r6-experimental-tree-2026-08-22`, variant hash `F86B3BA2…`) was **excluded entirely**;
all traces ran against `mneme/decision_retriever.py` as committed on `main` (hash `8EA03377…`,
five-field weights, no typed-rule term).

---

## 0. Corpus scope clarification

The benchmark uses a **frozen 11-decision corpus** (`examples/project_memory.json`: three native
decisions plus legacy-migrated `anti-*`/`rule-*` records) that has diverged from the repo's current
`.mneme/project_memory.json` (15 decisions). The Layer-1 freeze defines the benchmark as a
regression/integrity instrument over that fixed pool and does not make a production or
generalization claim.

Both measurement surfaces were exercised during this diagnosis:

| Surface | Corpus | Result |
|---|---|---|
| Frozen benchmark regression | `examples/project_memory.json` | recall@3 = 1.00, protected-scenario precision@3 = 0.333 — reproduces the shipped report exactly |
| Canonical live-memory probes | `.mneme/project_memory.json` | protected benchmark IDs absent from this corpus by design; probes show off-topic rank-1 retrievals (§4) |

Benchmark metrics are therefore **fixture-scoped** and are labeled as such throughout this report.

## 1. Which benchmark queries produce each false positive?

Reproduced top-3 (canonical retriever, `--memory examples/project_memory.json`, K=3):

| Scenario | Protected | Top-3 | Precision@3 |
|---|---|---|---|
| feature_boundary_violation | `anti-002` (#1) | `anti-002`, `mneme_no_agents_v1`, `anti-003` | 0.33 |
| framework_abstraction_violation | `anti-001` (#1) | `anti-001`, `anti-002`, `mneme_storage_json` | 0.33 |
| infra_scope_creep_violation | `anti-002` (#1) | `anti-002`, `mneme_no_agents_v1`, `rule-004` | 0.33 |
| retrieval_complexity_violation | `mneme_retrieval_deterministic` (#1) | + `rule-002`, `rule-005` | 0.33 |
| storage_backend_violation | `mneme_storage_json` (#1) | + `rule-003`, `rule-002` | 0.33 |

All protected benchmark decisions rank first in the frozen scenarios. Under the frozen K=3 fixture
shape (one expected ID, zero acceptable IDs), precision@3 is structurally constrained and is not an
appropriate tuning target; the Step 3C charter records this explicitly.

## 2. Which field/token overlap caused each score?

Token-level trace (weight × matched tokens):

| False positive | Score | Decisive overlap |
|---|---|---|
| `mneme_no_agents_v1` (feature_boundary) | 3.5 | `anti_patterns` ×3 via `agents`, `multi`; `rationale` via `mneme` |
| `anti-003` (feature_boundary) | 2.5 | `decision`+`anti_patterns` ×2.5 via **`between`** ("state between sessions") |
| `anti-002` (framework_abstraction) | 3.0 | `constraints` ×3 via **`layer`**, **`mneme`** |
| `mneme_storage_json` (framework_abstraction) | 1.5 | `anti_patterns` ×1.5 via **`layer`** ("storage layer") |
| `mneme_no_agents_v1` (infra_scope_creep) | 4.0 | `loops`, `tool` — near-duplicate record of the protected decision |
| `rule-004` (infra_scope_creep) | 3.0 | `constraints` ×3 via **`services`**, **`this`** |
| `rule-002` (retrieval_complexity) | 2.5 | `retrieval` in title + constraints |
| `rule-005` (retrieval_complexity) | 2.5 | `system` in title + constraints |
| `rule-003` (storage_backend) | 3.5 | `decision` ×2 + `constraints` via **`memory`, `project`** (title: "Separate project memory…") |
| `rule-002` (storage_backend) | 1.5 | `memory` |

## 3. Observed overlap mechanisms

1. **Fixed top-K padding**: slots 2–3 always fill, including at score 0.0 (`openai_provider_violation`
   surfaces three decisions at 0.0).
2. **Function-word tokens survive tokenization**: `len(w) >= 4` admits `what`, `should`, `this`,
   `between`, `using`. `_STOPWORDS` covers only six short verbs.
3. **Rationale-field prose**: migrated `rationale` fields embed imported ADR markdown; generic words
   in that prose produce 0.5× hits that accumulate across many tokens.
4. **Corpus duplication and self-reference** (fixture corpus): `mneme_no_agents_v1` ≈ `anti-002`;
   the token `mneme` appears in most records' own text.
5. **Shared domain vocabulary**: `rule-002`/`rule-005` are about retrieval/systems — topically
   adjacent to the retrieval-complexity query rather than mis-scored.
6. **No stemming**: `agent`/`agents` count separately.

## 4. Live-memory probes (separate diagnostic surface)

Probes against current `.mneme/project_memory.json` show off-topic rank-1 retrievals:

> Query: *"What database should we use for analytics?"*
> → #1 `ADR-001` (**positioning & messaging rules**) score 2.0, from four rationale-token
> collisions: `what`, `should`, `database`, `analytics`. Two are interrogative function words.

> Query: *"Can we switch the newsletter to Mailchimp?"*
> → three decisions surfaced at **score 0.0** (`format_decisions(min_score=0.0)` keeps zero scores,
> `context_builder.py:132`).

Other probes (*deploy site*, *CLI rewrite*, *pagination*) returned top results dominated by small
rationale-token counts (1–3 hits) with no clearly relevant decision at rank 1.

The live-memory probes show two distinct failure modes:

- **Tail noise:** low- or zero-relevance decisions fill ranks 2–3.
- **Top-rank noise:** generic lexical overlap against long rationale prose can place an irrelevant
  decision at rank 1.

These failure modes are not measured by the frozen benchmark scenarios, where protected decisions
rank first.

## 5. Candidate interventions (none implemented)

| Option | Change surface | Addresses |
|---|---|---|
| **L. Labeling/reporting** | State the benchmark's frozen-corpus scope in methodology artifacts; continue reporting recall@1 as the tuning signal; report canonical-live-memory probes separately as diagnostics | Interpretation scope, not behavior |
| **C. Memory-content hygiene** | Dedupe near-duplicate records; separate ADR prose from governance fields | Both modes, at the source; touches fixture corpus if applied to `examples/`, requiring re-baselining |
| **F. Injection floor** | Inject only decisions above a score floor | Tail noise only; does not address top-rank noise |
| **T. Tokenizer extension** | Function-word stopwords / stemming | Both modes partially; named frozen surface |
| **W. Field/weight reform** | Restructure `rationale`, re-weigh fields | Top-rank noise; changes field contribution for every query that overlaps rationale text |

## 6. Amendment analysis

Per the frozen architecture (retrieval mechanics protected; ADR-017 separates enforcement from
retrieval; Step 3C freezes memory-pool composition):

- **Requires explicit amendment:** F (alters selection semantics), T (tokenizer is named frozen
  surface), W (weights/fields).
- **Does not require a retrieval amendment:** L (reporting only) and C applied to live `.mneme`
  content only — with the caveat that C applied to the fixture corpus requires an explicit
  re-baselining decision, which this diagnosis does not make.

## Verdict

The frozen benchmark retrieval is functioning as designed: all protected decisions rank first, and
precision@3 ≈ 0.333 is structurally pinned by the K=3 fixture shape rather than being a Layer-1
quality signal. Layer-1 metrics remain valid as regression metrics for the frozen corpus; they do not
measure retrieval quality against the current live memory.

Separate live-memory probes show lexical-noise failures that the frozen benchmark does not measure:
low-relevance padding in ranks 2–3, and off-topic rank-1 retrievals driven by function-word overlap
against long rationale prose. The two modes affect different parts of retrieval: top-rank noise
changes the first injected decision, while tail noise affects lower-ranked slots.

No retrieval change is selected by this diagnosis. The next step is to evaluate candidate
interventions against both the frozen regression corpus and current live-memory probes, then
determine whether an architecture amendment is required.
