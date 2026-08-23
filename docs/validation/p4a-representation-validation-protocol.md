# P4A — Representation-Change Validation Protocol (LOCK)

Status: **protocol only — the ADR-backed representation change has not been drafted; no candidate
content exists; no results generated or inspected**
Date: 2026-08-23
Authority: ratified [P3 decision](p3-retrieval-intervention-decision.md) §8 gate (merged `a4e810ed`)
Gate discipline: identical to P2A — this file is committed and reviewed **before** any drafting or
evaluation. After lock it is executed unchanged; all results are reported including unfavorable ones;
no value may be added after outcomes are seen.

---

## 1. Environment pins

| Item | Value |
|---|---|
| Canonical `main` | `a4e810ed268652522f3ca2715e8f4c52b5680021` (#307, P3 record) |
| `mneme/decision_retriever.py` | sha256 `8EA0337791C4BD04CC46079487FA9EBF9CEC639B81C4E01319017F2A6E1D7DD2` (unchanged since P2A pin) |
| Frozen benchmark corpus `examples/project_memory.json` | sha256 `955792E2CF1AD2CE35963A2A5A072478C8563623BA5B9B21ACB6C1FD0CEE265C` |
| Live memory `.mneme/project_memory.json` | sha256 `BBBE873FD697941F172F2683C2EC285DBF67030B12AE2A0F44B704457BE9F9CA` |
| Import path | `mneme adr import <adr_dir> --memory <path> [--dry-run\|--apply] [--update-existing]`; compiler modules `mneme/adr_compiler.py`, `mneme/adr_import.py` |

The archived experimental retriever (`F86B3BA2…`) remains excluded.

## 2. Surfaces

| Surface | Corpus | Role |
|---|---|---|
| S1 frozen regression | `examples/project_memory.json` (11 records) | Regression instrument; gates must hold |
| S2 live-memory probes | `.mneme/project_memory.json` | Diagnostic for representation change |

## 3. Probe set

### 3a. Ratified core probes (unchanged from P2A)

| # | Query string (exact) | Ratified label |
|---|---|---|
| Q1 | `What database should we use for analytics?` | none |
| Q2 | `Can we switch the newsletter to Mailchimp?` | none |
| Q3 | `How do we deploy the marketing site?` | expected: `ADR-016` |
| Q4 | `Should we rewrite the CLI in Rust?` | none |
| Q5 | `Add pagination to the insights listing page` | expected: `ADR-016` |

### 3b. Expanded probes (ratified 2026-08-23, frozen before execution)

Expansion rule used: one natural developer query per distinct governance family in live memory that a
governing decision demonstrably answers, plus two negative controls spanning families with no
governing decision. No probe is derived from planned ADR-016 wording.

Labels below were proposed by the investigating agent, reviewed by the maintainer, amended
(E1 query reworded; E2/E3/E4 relabeled), and **ratified on 2026-08-23**. Frozen thereafter.

| # | Query string (exact) | Ratified label | Governing source |
|---|---|---|---|
| E1 | `Can I push a one-line governance change directly to main without a PR?` | expected: `workflow-001` | workflow-001 governs meaningful governance/architectural changes reaching main without PR review; the ratified phrasing targets that boundary rather than arbitrary typo fixes |
| E2 | `Our release script writes a JSON report without setting an encoding — is that fine?` | expected: `ADR-009`; acceptable: `encoding_001` | ADR-009 is the ADR-backed primary: automation file writes must specify explicit encodings; `encoding_001` also directly governs |
| E3 | `For PyPI, should the package be named mneme or mneme-hq?` | expected: `ADR-005` | ADR-005 sets the distribution name (`mneme-hq`), matching current `pyproject.toml`. **`ADR-004` is deliberately not relevant here**: its PyPI statement conflicts with the later/current ADR-005 contract and current package metadata — counting it relevant would score a contradictory answer as correct. This pre-existing ADR-004/ADR-005 inconsistency is recorded, not fixed, inside P4A |
| E4 | `Where should a new internal ops dashboard script live?` | expected: `ADR-002`; acceptable: `rule-public-boundary` | ADR-002 sets the repository boundary for internal operational tooling; `rule-public-boundary` reaches the retrievable pool via legacy-rule migration and states the same boundary, so an otherwise-correct retrieval must not be counted as noise |
| E5 | `We want to forbid an exact install-command literal in onboarding docs — how is that encoded?` | expected: `ADR-019`; acceptable: `ADR-020` | ADR-019 defines how `FORBID_LITERAL` is authored; ADR-020 is legitimately adjacent because the query names onboarding docs as the governed artifact |
| N1 | `What framework should we use for the mobile app?` | *(none)* | no mobile decision exists in live memory |
| N2 | `Should we migrate CI from GitHub Actions to CircleCI?` | *(none)* | no CI-vendor selection decision exists in live memory |

Metrics over governed probes = Q3, Q5, E1–E5. Negative controls contribute only noise metrics.
**Relevant IDs for a probe = expected ∪ acceptable** under its ratified label.

## 4. Candidate-change definition constraints (from ratified P3)

The representation change, when drafted, must satisfy all of:

1. **Derivability standard:** added vocabulary makes already-decided governance more explicit only
   where directly supported by the source ADR; no query-specific vocabulary introduced to improve
   retrieval on these probes.
2. **Reproducibility path:** changes flow ADR source → compiler/import → memory. Any
   `.mneme/project_memory.json` diff must be reproducible via the §1 import path; manual divergence
   is not permitted.
3. **Frontmatter `scope` caution:** precedence-participating; not broadened casually. Ownership
   coverage is clarified in ADR content first, then regenerated.
4. **No retrieval-code changes:** `DecisionRetriever`, weights, tokenizer, K, tie-break untouched.

## 5. Pre-flight inventory (before drafting, after lock)

Record in the change PR:

- which fields of the target memory entries are compiler-derived vs hand-authored today;
- the exact regeneration command sequence;
- a round-trip check: regenerate/import without content edits and diff against the current live
  memory, recording any pre-existing divergence before the representation change touches anything.

## 6. Baseline and metrics

**B0′ baseline** is measured once under this protocol (S1 + full probe set) before the drafted change
is evaluated. Expected to match known values; any mismatch halts execution and is investigated as a
protocol deviation.

Gates (all must hold):

| Gate | Requirement |
|---|---|
| G1 | S1 verdicts PASS-capable (7/7) and mean recall@3 = 1.00 |
| G2 | **Preservation:** no governed probe that is a top-K relevance hit under B0′ (i.e., contains at least one relevant ID, where relevant = expected ∪ acceptable) becomes a miss after the representation change |
| G3 | **Intervention objective:** Q5 resolves `ADR-016` at rank 1 |
| G4 | Rank-1 relevance rate across governed probes is ≥ B0′ |

G2 is a preservation gate only: the P3-authorized change preserves unrelated retrieval; it is not
responsible for repairing any pre-existing miss among the expanded probes. G3 is the single
intervention-specific success condition.

Recorded, not gated: `layer1_retrieved_ids` compositions; precision@3 (structurally constrained);
tail-injection counts; zero-score injection counts; recall@1 reported per governed probe.

## 7. Execution rules

1. Drafting of the ADR-source clarification occurs only after this protocol is locked.
2. One evaluation run of the drafted change on both surfaces; complete results reported.
3. No new probes, labels, thresholds, or content variants may be introduced after any outcome is seen.
4. Content iteration against observed probe results is prohibited; if gates fail, the question returns
   to decision review (P3 §8 item 4), including possible reconsideration of Option B with an extended
   tied-rank diagnosis.
5. Any deviation voids the affected runs and must be recorded in the results report.

---

*Lock hash: SHA-256 of this file is recorded in the locking commit message.*
