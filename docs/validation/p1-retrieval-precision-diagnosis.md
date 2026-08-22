# P1 Diagnosis: Retrieval Precision on Canonical `main`

Status: **read-only diagnosis complete — no retriever, fixture, or enforcement changes made**
Date: 2026-08-22
Scope: canonical `main` (`b8379788`) only. The archived experimental retriever
(`archive/r1-r6-experimental-tree-2026-08-22`, variant hash `F86B3BA2…`) was **excluded entirely**;
all traces ran against `mneme/decision_retriever.py` as committed on `main` (hash `8EA03377…`,
five-field weights, no typed-rule term).

---

## 0. Premise correction (found during reproduction)

The shipped claim "recall@3 = 1.00, precision@3 = 0.33" was reproduced exactly — but only against
the **demo fixture corpus** `examples/project_memory.json` (11 decisions incl. legacy-migrated
`anti-*`/`rule-*` records), which is what generated `examples/benchmarks/reports/results.json`.

Against the **canonical live memory** `.mneme/project_memory.json` (15 decisions: `workflow-001`,
`encoding_001`, `ADR-001…ADR-020`), the same benchmark currently yields
**recall@3 = 0.00 / precision@3 = 0.00** for all five protected scenarios — not because retrieval got
worse, but because the protected IDs (`mneme_storage_json`, `mneme_retrieval_deterministic`,
`anti-001`, `anti-002`) do not exist in that corpus. The fixtures are stale relative to canonical memory.

Both facts matter for the verdict below.

---

## 1. Which benchmark queries produce each false positive?

Reproduced top-3 (canonical retriever, `--memory examples/project_memory.json`, K=3):

| Scenario | Protected | Top-3 | Precision@3 |
|---|---|---|---|
| feature_boundary_violation | `anti-002` (#1) | `anti-002`, `mneme_no_agents_v1`, `anti-003` | 0.33 |
| framework_abstraction_violation | `anti-001` (#1) | `anti-001`, `anti-002`, `mneme_storage_json` | 0.33 |
| infra_scope_creep_violation | `anti-002` (#1) | `anti-002`, `mneme_no_agents_v1`, `rule-004` | 0.33 |
| retrieval_complexity_violation | `mneme_retrieval_deterministic` (#1) | + `rule-002`, `rule-005` | 0.33 |
| storage_backend_violation | `mneme_storage_json` (#1) | + `rule-003`, `rule-002` | 0.33 |

**Key structural observation:** the protected decision ranks **#1 in all five scenarios**. The
precision@3 deficit comes entirely from slots 2–3 being force-filled by fixed top-K.

## 2. Which field/token overlap caused each score?

Token-level trace (weight × matched tokens):

| False positive | Score | Decisive overlap |
|---|---|---|
| `mneme_no_agents_v1` (feature_boundary) | 3.5 | `anti_patterns` ×3 via `agents`, `multi`; `rationale` via `mneme` |
| `anti-003` (feature_boundary) | 2.5 | `decision`+`anti_patterns` ×2.5 via **`between`** ("state between sessions") |
| `anti-002` (framework_abstraction) | 3.0 | `constraints` ×3 via **`layer`**, **`mneme`** |
| `mneme_storage_json` (framework_abstraction) | 1.5 | `anti_patterns` ×1.5 via **`layer`** ("storage layer") |
| `mneme_no_agents_v1` (infra_scope_creep) | 4.0 | `loops`, `tool` — near-duplicate of the protected record itself |
| `rule-004` (infra_scope_creep) | 3.0 | `constraints` ×3 via **`services`**, **`this`** |
| `rule-002` (retrieval_complexity) | 2.5 | `retrieval` in title + constraints (topically adjacent rule) |
| `rule-005` (retrieval_complexity) | 2.5 | `system` in title + constraints |
| `rule-003` (storage_backend) | 3.5 | `decision` ×2 + `constraints` via **`memory`, `project`** (title: "Separate project memory…") |
| `rule-002` (storage_backend) | 1.5 | `memory` |

Outside-fixture probe (canonical `.mneme` corpus) found the same mechanism at its worst:

> Query: *"What database should we use for analytics?"*
> → #1 `ADR-001` (**positioning & messaging rules**) score 2.0, driven by **four rationale-token
> collisions: `what`, `should`, `database`, `analytics`** — two of them interrogative function words.
> Cause: migrated `rationale` fields embed whole imported ADR markdown documents, so generic English
> prose mass-produces 0.5× hits that outrank genuine signal.

Also confirmed: *"Can we switch the newsletter to Mailchimp?"* produces three decisions at
**score 0.0**, which still inject because `format_decisions(min_score=0.0)` keeps zero scores
(`context_builder.py:132`).

## 3. Root-cause classification

Ranked by measured contribution:

1. **Fixed top-K padding with no relevance floor** (mechanics): slots 2–3 always fill, even at score
   0.0. This alone accounts for ~half the precision deficit; rank-1 is already correct in 7/7.
2. **Function-word tokens survive tokenization**: `len(w) >= 4` admits `what`, `should`, `this`,
   `between`, `using`. `_STOPWORDS` covers only six short verbs.
3. **Rationale-field noise**: legacy migration stuffed full ADR prose into `rationale`; at 0.5× per
   token across long prose, noise sums above true signal (ADR-001 case above).
4. **Corpus duplication & self-reference**: `mneme_no_agents_v1` ≈ `anti-002` express one concept
   twice (native vs migrated); the token `mneme` appears in nearly every record's own text and acts
   as a universal booster.
5. **Shared domain vocabulary in a narrow corpus**: `rule-002`/`rule-005` are genuinely about
   retrieval/systems — topically adjacent, not misranked; K=3 converts adjacency into false positives.
6. **No stemming**: `agent`/`agents` count separately (minor; cuts both ways).

Not causes: scoring weights behaved as specified; ranking order among relevant records was correct;
enforcement untouched (7/7 preserved throughout this diagnosis).

## 4. Are the false positives reproducible outside benchmark fixtures?

Yes — demonstrated above against `.mneme/project_memory.json` with natural developer queries:
interrogative-function-word rationale collisions put an off-topic positioning ADR at rank #1, and
out-of-domain queries still inject three score-0 decisions. The mechanism is a property of the
canonical retriever + memory content, not of the fixture corpus. (Conversely, the *specific* 1.00/0.33
numbers are fixture-bound: they do not reproduce against canonical memory today.)

## 5. Smallest prospective intervention(s)

Ordered by invasiveness; **none implemented here**.

| Option | Change surface | Expected effect on precision@3 |
|---|---|---|
| **R. Metric/reporting fix** | Report precision@1 alongside @3; stop averaging vacuous control scenarios | Corrects the narrative; no behavior change. Rank-1 precision is 7/7 today |
| **C. Corpus hygiene** | Dedupe `mneme_no_agents_v1`/`anti-002`; de-self-reference `Mneme` tokens; separate ADR prose from governance fields | Removes duplicate FPs and rationale noise at the source |
| **F. Injection floor** | Inject only decisions scoring ≥ a fraction of top score (or absolute floor > 0) | Directly eliminates slot-padding; largest behavioral gain |
| **T. Tokenizer extension** | Extend `_STOPWORDS` with interrogatives/function words; optional stemming | Removes `what`/`should`/`this`/`between` collisions |
| **W. Weight/field reform** | Demote or restructure `rationale`; re-weigh fields | Addresses the deepest cause (noise source) but largest blast radius |

**Smallest genuinely effective pair:** F (floor) + T (function-word stopwords). C is prerequisite
hygiene for any honest re-measurement but is a memory-content operation, not a retriever change.

## 6. Amendment analysis

Per the frozen architecture (retrieval mechanics protected; ADR-017 separates enforcement from
retrieval):

- **Requires explicit amendment:** F (alters effective K/selection semantics), T (tokenizer is named
  frozen surface), W (weights/fields).
- **Does not require a retrieval amendment:** R (measurement/reporting only) and C (memory content),
  with one caveat each — R edits a citeable methodology artifact (`RESULTS.md`), and C mutates
  `examples/project_memory.json`, which doubles as the benchmark fixture, so any fixture-affecting
  change needs an explicit re-baselining decision rather than silent tuning.

## Verdict

Precision@3 = 0.33 is **not a ranking failure** — it is (a) fixed-K padding without a floor,
(b) function-word token leakage, and (c) rationale-prose noise from migrated memory, compounded by a
duplicated demo corpus. The single most consequential non-code fact: **the shipped benchmark numbers
describe the demo fixture corpus, while the canonical `.mneme` memory has drifted so far that its
protected IDs no longer exist** — so Layer-1 metrics currently measure neither production nor reality
without an explicit statement of which corpus is under test.

Recommended sequence: R + C first (no amendment, restores meaningful measurement), then a single
prospective amendment covering F + T if precision beyond rank-1 remains unsatisfactory.
