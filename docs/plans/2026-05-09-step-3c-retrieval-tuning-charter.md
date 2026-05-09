# Step 3C Retrieval-Tuning Charter

**Status:** active charter for the next benchmark-step before any retrieval-tuning work begins
**Anchor commit:** `2423995` (Step 3B merge on `origin/main`)
**Authority source:** `.mneme/project_memory.json`, ADRs in `docs/adr/`, benchmark methodology at `site/benchmark/index.html`

---

## 1. Context

After Step 3B the benchmark is governance-valid and regression-useful, but **not yet a trustworthy selectivity-evaluation system**. Suite headline as of `2423995`:

| metric | value | nature |
|---|---|---|
| pass_rate | 7/7 (1.00) | Layer 2 enforcement |
| mean recall@3 (governed n=5) | 1.00 | Layer 1 retrieval |
| mean precision@3 (governed n=5) | 0.333 | Layer 1 retrieval |
| irrelevant_injection_rate (governed n=5) | 1.00 | Layer 1 retrieval |
| K (runtime + benchmark) | 3 | aligned per Step 3A |

Two of the seven scenarios (`pydantic_dependency_creep`, `openai_provider_violation`) declare `expected_protected_decision_ids: []` because their cited governance items (`pref-001`, `dec-005`, `fact-002`) are not in the retrievable `Decision` pool. They contribute to suite pass count but are excluded from suite-level Layer 1 means.

Step 3C is intended to improve retrieval *selectivity* — reducing irrelevant retrievals that share lexical surface area with governance queries. This charter exists to keep Step 3C from optimizing the metric instead of the system.

---

## 2. In scope — Step 3C IS allowed to optimize

- **`DecisionRetriever` scoring internals** ([decision_retriever.py](../../mneme-project-memory/mneme/decision_retriever.py)):
  - `_tokenize` (stopwords, length floor, punctuation handling, optional stemming).
  - `_WEIGHTS` per-field scoring weights.
  - Tag-boosting, priority-weighting, or any additional scoring layer composed on top of the existing field-overlap formula.
  - Tie-break behavior, **provided** a deterministic test is added before the change (see §6).
- **`acceptable_decision_ids`** population on existing scenarios, **only when** the added IDs are semantically related-but-not-required for that specific scenario (see §5 — this is the gaming surface).
- Adding new test coverage for retrieval determinism, tie-breaking, or pool-mismatch regression.

## 3. Out of scope — Step 3C non-goals

Locked by this charter. Any of these requires a separate methodology decision and ADR before being touched:

- **K (`DEFAULT_MAX_DECISIONS`)** — fixed at 3. Runtime/benchmark parity per Step 3A is non-negotiable.
- **Layer 1 metric semantics** — recall@K formula, precision@K formula, irrelevant-injection definition, and the `governed = [r for r in results if r.layer1_expected_ids]` aggregation filter.
- **Layer 2 verdict logic** — PASS / FAIL / WEAK / WEAK_RETRIEVAL / MALFORMED triggers.
- **Assertion DSL** — `forbidden_dependency` / `forbidden_path_pattern` matching semantics, the `refused: true` short-circuit, structured-fixture schema.
- **Existing fixture content** — `query.txt`, `with_mneme.txt|.json`, `without_mneme.txt|.json`, `expected_failure_terms`, `expected_protected_decision_ids`. Step 3C is a retrieval pass, not a fixture pass.
- **Memory pool composition** — `MemoryStore.load()` migration of `preference` / `architecture_decision` / `fact` / `example` items into the `Decision` retrieval pool. Even though this is not a fixture or methodology change, it changes the retrieval universe — muddying before/after comparison against the `2423995` baseline and making selectivity attributions ambiguous. Step 3C tunes retrieval behavior **against the current pool only** (3 native + 5 migrated `rule` + 3 migrated `anti_pattern` = 11 `Decision` records). The `pydantic_dependency_creep` / `openai_provider_violation` pool gap is acknowledged and deferred to a separate work item under its own charter.
- **Synthetic fixture inflation** — adding new scenarios solely to move headline numbers. New scenarios are in scope only when they cover a real governance gap (e.g. stale/superseded retrieval, tied-score behavior).
- **ADR scan, dashboard, live-mode** — explicitly deferred.

## 4. Metric authority

| metric | authority | role in Step 3C |
|---|---|---|
| `pass_rate` (Layer 2) | **authoritative** | merge gate — must remain 1.00 |
| `recall@3` per governed scenario | **authoritative** | regression guard — see §7 |
| `recall@1` per governed scenario | **authoritative when reported** | sharpest tuning signal — see §7 |
| `WEAK_RETRIEVAL` count | **authoritative** | must remain 0 across the suite |
| `precision@3` (suite mean and per-scenario) | **advisory** | fixture-shape constrained — see §7 |
| `irrelevant_injection_rate` (suite) | **advisory** | fixture-shape constrained — see §7 |
| `irrelevant_injection` per scenario | **advisory** | useful for noise tracing, not a tuning target |
| `protected_decision_ids_hit` | authoritative | proves the expected ID was retrieved at all |

"Advisory" does not mean unimportant. It means **a movement in this metric does not, by itself, prove a retrieval-quality change**. Movements must be explained against fixture shape and pool state before being claimed as a win (see §8).

## 5. Non-negotiable benchmark invariants

These properties of the suite must hold across every Step 3C PR. Violating any is a merge-blocker.

1. **K = 3** at runtime and benchmark, per `DEFAULT_MAX_DECISIONS`. Asserted by `tests/test_cli_benchmark.py` and the Step 3A.ii alignment tests.
2. **All shipped fixtures PASS** — `pytest mneme-project-memory/tests/test_benchmark.py::test_run_suite_all_scenarios_pass` is green.
3. **Suite count = 7** — `test_run_suite_loads_all_benchmark_scenarios` green; bump only when a real governance gap is filled.
4. **`recall = 1.0` for every governed scenario** — pinned by `test_runner_existing_fixtures_still_pass`. A regression here means an expected_id fell out of top-K.
5. **Determinism** — same query + same memory file produce the same ranked list (rule-002 in canonical memory). Tie-break behavior changes require a test pin first.
6. **Faithful retrieval on contradictory governance** — `test_runner_handles_contradictory_decisions_in_retrieval` continues to surface both conflicting decisions. The runner does not silently pick a winner; that is an ADR-precedence concern.
7. **Duplicate-ID dedup** — `test_runner_dedups_decisions_with_duplicate_ids_via_memory_file` and `test_layer1_dedups_decisions_with_duplicate_ids_first_seen_wins` continue to hold. `MemoryStore` may carry duplicates; `score_layer1` dedups via seen-set, first-seen wins.
8. **No silent TXT fallback on shipped fixtures** — `test_run_suite_on_shipped_fixtures_emits_no_warnings` stays green. Every fixture carries both JSON siblings.
9. **MALFORMED short-circuit honesty** — Layer 1 numbers are recorded on MALFORMED results, per the Step 3B contract. Step 3C must not regress this.
10. **`mneme check --mode warn`** clean against governance source.

## 6. Merge-blocking regression signals

A Step 3C PR must not merge if any of the following appear in CI output, even if `pass_rate` remains 1.00:

- Any governed-scenario `recall@3 < 1.0`.
- Any scenario verdict ≠ `PASS` or `WEAK_RETRIEVAL` flipped on for a previously-passing scenario.
- Any `protected_decision_ids_hit` regression — i.e. the expected ID was retrieved at K=3 in `2423995` but is not retrieved on this PR.
- A new `UserWarning` from the TXT-fallback path on shipped fixtures.
- Determinism violation — same query + same memory file produces different ranked lists across test runs.
- Tied-score behavior change without an accompanying tie-break test.
- Any change to a non-goal in §3 without a separate methodology ADR.

## 7. Why these metrics behave the way they do

This section is load-bearing for §4 and §8. Read before tuning.

### 7a. Why `recall@3` remains the primary regression guard

`recall@3` is the only Layer 1 metric whose value reflects retrieval correctness directly:

- It measures whether each scenario's `expected_protected_decision_ids` survived the K=3 cutoff.
- It is independent of K-padding for governed scenarios at the current shape (`|expected_ids| = 1` for all 5 governed scenarios).
- It has zero headroom upward (already 1.0) — it can only regress. That is exactly what we want from a regression guard.
- It is governed by `WEAK_RETRIEVAL` semantics: a scenario where `enhanced_count == 0` but `recall < 1.0` is downgraded from PASS, preventing coincidental passes from masking retrieval failure.

A drop in `recall@3` is therefore unambiguous evidence of a retrieval regression and must block merge.

### 7b. Why `recall@1` is the sharpest tuning signal currently available

`recall@1` is not in the headline summary, but it is computable per-scenario from `layer1_retrieved_ids[0]`:

- At Step 3B baseline, `recall@1 = 4/5 = 0.8` across governed scenarios. Only `feature_boundary_violation` ranks `mneme_no_agents_v1` ahead of its expected `anti-002` — the two are near-synonyms by construction, so the rank-1 mis-pick is genuine retrieval ambiguity, not a fixture artefact.
- `recall@1` has actual headroom: it can move from 0.8 toward 1.0.
- A retrieval-tuning change that improves rank-1 precision on the existing fixtures will register here without methodology change.
- Movement at `recall@1` is the single best evidence that selectivity improved on the queries the suite already covers.

Step 3C SHOULD report `recall@1` per scenario in its PR description even though the headline summary does not surface it. A Step 3C PR that holds `recall@3 = 1.0` and lifts `recall@1` from 0.8 → 1.0 is the canonical successful change.

### 7c. Why `precision@3` and `irrelevant_injection_rate` are fixture-shape constrained

Both metrics are functions of fixture shape, not of retrieval quality, given the current suite:

- `K = 3`, fixed.
- `|expected_ids| = 1` for all 5 governed scenarios.
- `|acceptable_decision_ids| = 0` for all 5 governed scenarios.

Under those conditions, the maximum attainable per-scenario precision is `1/3 ≈ 0.333`, achieved when the expected ID is among the top 3 with two non-relevant escorts. That is the current state for all 5 governed scenarios — hence the suite mean is 0.333.

`irrelevant_injection` is `True` whenever any of the 3 retrieved IDs lies outside `expected ∪ acceptable`. With `|expected| = 1` and `|acceptable| = 0`, two of three retrieved must always be outside that set. Hence `irrelevant_injection = True` deterministically and the suite rate is 1.0.

**Movement in either metric without a fixture-shape change is mathematically impossible from retrieval-tuning alone.** A claim of "precision improved" therefore requires one of:
- `acceptable_decision_ids` populated (changes the relevant set, not retrieval quality).
- K changed (out of scope per §3).
- `|expected_ids|` per scenario changed (fixture change, out of scope per §3).
- A new scenario shape introduced (must satisfy §3 anti-inflation criterion).

These are advisory metrics for Step 3C. Treat them as constants until a methodology decision unlocks them.

## 8. How to interpret retrieval-selectivity improvements under the current fixture shape

A retrieval-tuning change in Step 3C will primarily manifest as:

1. **Changes to `layer1_retrieved_ids` per scenario** — the actual ranked list. Read these. They are the primary observability surface.
2. **Movement in `recall@1` per scenario** — the sharpest dial.
3. **Movement in the noise tail** — which IDs occupy ranks 2–3 across scenarios. At Step 3B baseline, the dominant noise is `rule-002`, `rule-003`, `rule-005` (generic lexical overlap on tokens like "project", "memory", "decisions"). A tuning change that suppresses these will surface as different IDs in those slots.

What a successful Step 3C PR looks like in numbers, given current fixture shape:

- `pass_rate`: still 1.00.
- `recall@3` per governed scenario: still 1.0.
- `recall@1` per governed scenario: improved (e.g. 0.8 → 1.0).
- `precision@3`: **unchanged at ~0.333**. This is expected. Do not chase it.
- `irrelevant_injection_rate`: **unchanged at 1.00**. This is expected. Do not chase it.
- `layer1_retrieved_ids` for noise-prone queries: visibly different in slots 2–3.

What a *suspicious* Step 3C PR looks like:

- `precision@3` jumps from 0.333 → ~0.667 or higher → **investigate `acceptable_decision_ids` population for honesty per §5 / checklist below**.
- `irrelevant_injection_rate` drops sharply → **same investigation**.
- `recall@3` holds at 1.0 but the noise tail is unchanged → tuning probably had no effect; the change may be a no-op.
- New IDs appear in `layer1_retrieved_ids` that weren't in the Step 3B 11-Decision pool (3 native + `rule-001…005` + `anti-001…003`) → pool migration occurred; out of scope per §3 — block.
- New scenarios appear → they must satisfy §3 anti-inflation criterion or be reverted.

---

## 9. Reviewer anti-overfitting checklist

Apply this checklist on every Step 3C tuning PR. Each item is a yes/no question; "yes" advances; "no" blocks merge until resolved.

### Metric-shape honesty
- [ ] If `precision@3` moved, did `acceptable_decision_ids` get populated? If yes, is each newly-added ID semantically related-but-not-required for that scenario? Spot-check at least 2 scenarios.
- [ ] If `irrelevant_injection_rate` moved, is the change explained by `acceptable_decision_ids` (legitimate) rather than a metric-formula tweak (out of scope)?
- [ ] Was `K` changed? If yes — block; this is a methodology change requiring an ADR.
- [ ] Was the `governed` aggregation filter changed? If yes — block; same.

### Retrieval-quality honesty
- [ ] Is `recall@3 = 1.0` for every governed scenario in the new run?
- [ ] Did `recall@1` move? Report per-scenario diff in PR description.
- [ ] Are new `layer1_retrieved_ids` for at least 2 governed scenarios different from `2423995` baseline? If identical, the tuning may be a no-op.
- [ ] Did any `protected_decision_ids_hit` regress? If yes — block.

### Pool / fixture honesty
- [ ] Was any new memory item type promoted into the `Decision` retrieval pool (e.g. `preference`, `fact`, `example`, `architecture_decision`)? If yes — block; out of scope per §3. Verify the pool count in `len(store.decisions())` is still 11 against the baseline memory.
- [ ] Was any shipped scenario's `query.txt`, `with_mneme.*`, `without_mneme.*`, `expected_failure_terms`, or `expected_protected_decision_ids` changed? If yes — block; out of scope per §3.
- [ ] Were new scenarios added? If yes, do they cover a real governance gap (stale/superseded retrieval, tied-score behavior, pool-mismatch) rather than inflate the count? If they exist solely to move headline numbers — block.

### Determinism honesty
- [ ] Does `pytest -p no:randomly mneme-project-memory/tests/` still pass?
- [ ] If tied-score behavior was changed, is there a new test pinning the new contract before the change?
- [ ] Does `mneme check --mode warn` remain clean?

### Adversarial-suite preservation
- [ ] Do all 5 governance-integrity tests still pass (`test_runner_handles_contradictory_decisions_in_retrieval`, `test_runner_dedups_decisions_with_duplicate_ids_via_memory_file`, `test_layer1_irrelevant_injection_stress_at_default_k`, `test_layer1_handles_empty_id_decision_robustly`, `test_layer1_dedups_decisions_with_duplicate_ids_first_seen_wins`)?
- [ ] Do all 5 parser-trivia MALFORMED tests still pass?
- [ ] Does `test_run_suite_on_shipped_fixtures_emits_no_warnings` still pass?

### Reporting honesty
- [ ] Does the PR description state, in plain language, what retrieval property changed and why the recall@1 movement (or lack thereof) supports the claim?
- [ ] Does the PR explicitly acknowledge that any precision@3 / irrelevant_injection movement is a function of `acceptable_decision_ids` population, not retrieval quality?

---

## 10. Exit criteria for Step 3C

Step 3C is complete when:

1. All §5 invariants hold.
2. All §9 checklist items pass.
3. `recall@1` is reported per-scenario in the merged PR description, and the suite-level `recall@1` is documented as a new advisory metric in `examples/benchmarks/reports/RESULTS.md`.
4. The dominant noise-tail change is documented (e.g. "rule-002 no longer surfaces on storage queries because tag-boost on `storage` outranks generic lexical overlap").

A Step 3C PR that meets these without violating any §3 non-goal is mergeable. Anything beyond that is a separate work item under its own charter.
