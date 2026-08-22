# Pre-generation Guidance Role Classifier Design

**Status:** R2 design locked; implementation pending R3  
**Date:** 2026-08-13  
**Scope:** deterministic role assignment for already-selected guidance decisions

## 1. Decision

R2 selects the **unique primary anchor** classifier.

Given the ordered output of `select_guidance_decisions()`:

1. if the list is empty, return no role assignments;
2. if the first decision has a strictly higher score than the second decision,
   assign the first decision `direct`;
3. assign every remaining decision `adjacent_constraint`; and
4. if two or more decisions tie for the highest score, assign no `direct` role
   and classify every selected decision as `adjacent_constraint`.

For a singleton list, the sole selected decision is the unique highest-scoring
candidate and is therefore `direct`.

The classifier produces at most one direct decision. It never changes the
selected IDs or their order.

## 2. Why this evidence is sufficient

The existing retriever already answers a deterministic relevance-ranking
question. Guidance-role classification interprets that ranking without adding
a second score formula:

- a unique highest-ranked decision is the strongest available task anchor;
- secondary decisions remain relevant constraints but are not additional
  implementation objectives; and
- an exact top-score tie is evidence that the current lexical signal cannot
  distinguish a direct anchor safely.

The tie rule is deliberately conservative. Demoting tied candidates may reduce
directive guidance, but it cannot turn an ambiguous related decision into
authorization for extra work.

This design uses no absolute threshold, ratio, margin, new weighting, or field
reweighting. It consumes only the ordering and scores already produced by the
locked retriever and selection gate.

## 3. Deterministic contract

### 3.1 Input preconditions

The input is the ordered, deduplicated list returned by
`select_guidance_decisions()` after its existing low-signal, minimum-score,
structured-match, K, and duplicate-ID gates.

R2 does not classify raw corpus decisions and does not bypass selection.

### 3.2 Output record

R3 must produce an immutable record for each selected decision containing:

- the original `ScoredDecision`;
- `role`, exactly `direct` or `adjacent_constraint`;
- one stable `reason_code`;
- one-based retrieval rank; and
- the unchanged score and per-field match counts for explanation.

### 3.3 Reason codes

| Reason code | Role | Meaning |
|---|---|---|
| `unique_highest_retrieval_rank` | `direct` | The candidate is the sole highest-scoring selected decision. |
| `secondary_retrieval_candidate` | `adjacent_constraint` | A unique direct anchor exists and this candidate ranks below it. |
| `top_score_tie_no_direct_anchor` | `adjacent_constraint` | The highest score is tied, so no candidate receives direct authority. |

If a top-score tie exists, lower-ranked candidates remain
`secondary_retrieval_candidate`; only candidates participating in the tie use
the tie reason.

### 3.4 Pseudocode

```text
classify(selected):
    if selected is empty:
        return []

    top_score = selected[0].score
    top_tie = length(selected) > 1 and selected[1].score == top_score

    for each candidate at zero-based index i:
        if i == 0 and not top_tie:
            role = direct
            reason = unique_highest_retrieval_rank
        else if candidate.score == top_score and top_tie:
            role = adjacent_constraint
            reason = top_score_tie_no_direct_anchor
        else:
            role = adjacent_constraint
            reason = secondary_retrieval_candidate
```

Scores are deterministic half-step sums in the current retriever. Tie
comparison is exact; R2 does not introduce an epsilon or tolerance.

## 4. Candidate comparison

| Candidate | Decision | Reason |
|---|---|---|
| Every selected decision is `direct` | Reject | This is the E66 failure mode: relevance becomes equal implementation authority. |
| Absolute score, score-gap, or ratio threshold | Reject | The observed 8.0 versus 2.0 incident does not justify a new numerical boundary. |
| Treat scope-only matches as adjacent | Reject | Secondary lexical noise also appears in constraint, anti-pattern, and decision fields; field origin alone is not a safe role boundary. |
| Add authored decision-level selectors or roles | Defer | This changes ADR/memory schemas and recreates terminology that conflicts with ADR-020's rule-level applicability boundary. |
| Infer or require a target path at prompt submission | Defer | The production hook does not receive a reliable target path and R1 forbids target inference. |
| Make every top-score tie `direct` | Reject | Ambiguous lexical evidence would grant multiple decisions implementation authority. |
| Unique primary anchor; all others adjacent | **Select** | Deterministic, explainable, threshold-free, and satisfies the locked evidence. |

## 5. Locked evidence

### 5.1 Existing retrieval suite

The unchanged 22-case retrieval fixture contains 18 cases with expected direct
decisions. Under the R2 design:

| Metric | Result |
|---|---:|
| Relevant cases | 18 |
| Expected decision assigned `direct` | 18/18 |
| Direct-decision macro recall | 1.00 |
| Secondary selected decisions assigned adjacent | 6 |
| Top-score ties | 0 |
| No-relevance cases with selected decisions | 0 |

This analysis reuses existing selected IDs and scores. It does not change or
reinterpret retrieval recall gates.

### 5.2 Four-case role characterization

| Case | Direct | Adjacent | Result |
|---|---|---|---|
| E66 authentication reproduction | `ADR-AUTH` | `ADR-STORAGE` | Expected |
| E66 storage adjacency | `ADR-STORAGE` | `ADR-AUTH` | Expected |
| Specific browser-auth prompt | `ADR-AUTH` | none | Expected |
| Unrelated copy control | none | none | Expected |

Direct recall remains 1.00, both known adjacent decisions receive an explicit
role, and no unexpected decision is introduced.

## 6. Safety invariants

The R1 role contract remains normative. In addition:

1. the classifier assigns at most one `direct` role;
2. every selected candidate receives exactly one role;
3. no selected ID is added, removed, reordered, or rescored;
4. a tie never grants direct authority;
5. `adjacent_constraint` never becomes an implementation objective;
6. role metadata never affects enforcement; and
7. classification is byte-stable for the same selected input.

R3 tests role assignment. R4's formatter tests the non-authorizing language and
ensures adjacent decisions cannot appear in an undifferentiated decision block.

## 7. Known limitations and falsification conditions

The unique primary anchor is a deliberately narrow MVP, not a semantic model.
It can be falsified if R3 finds any of the following:

- a locked expected decision is not the unique highest-ranked candidate;
- adversarial prompt paraphrases cause a known adjacent decision to rank first;
- a multi-domain prompt requires multiple direct decisions for correct behavior
  and conditional adjacent wording cannot preserve the constraints safely;
- stable insertion-order tie handling leaks into direct authority; or
- role assignment requires target-path or conversation state unavailable at
  `UserPromptSubmit`.

If falsified, return to R2 and revise the design under a new lock. Do not tune a
threshold against the failing examples.

## 8. R3 implementation boundary

R3 may implement a pure role-classification API and extend the characterization
evaluator. It must add focused tests for empty, singleton, unique-highest,
secondary, exact-tie, ordering, determinism, and locked-fixture behavior.

R3 must not:

- connect the classifier to `build_guidance()`;
- change the production formatter or canonical wording;
- change hooks, plugin configuration, retrieval, K, weights, or selection;
- modify the locked R1/R2 contracts or characterization classifications;
- change enforcement or ADR-020 applicability; or
- run Claude trials.

Production wiring remains R4, contingent on R3 gates passing.
