# Architecture alignment record — ox-compaction experiment

Date: 2026-08-21. Frozen Mneme SHA: `f7eac3875eae5dcb7f57ac55388567877c0ce692`.

## Confirmed architectural boundaries (this tree)

- `mneme/decision_retriever.py` — deterministic weighted-token retrieval
  (`DecisionRetriever.retrieve()`, weights in module docstring). No mutation.
- `mneme/context_builder.py:129` — `format_decisions()` is this tree's
  production agent-facing decision formatter (`[Mneme decisions applied]` block).
- `mneme/pipeline.py` — wires MemoryStore → retriever → formatter → LLM →
  `ConflictDetector`. Not modified.
- `mneme/conflict_detector.py` — post-generation audit only; untouched.
- Enforcement, path applicability, ADR compilation, production ranking and
  formatting: untouched.

## What the experiment reuses

Exactly the production path of this frozen tree:

```
MemoryStore.load() -> DecisionRetriever.retrieve(prompt) -> format_decisions(scored)
```

Executed once against the fixture memory; output frozen and hash-pinned
(`frozen/guidance-frozen.txt`, sha256 recorded in `experiment-lock.json`).

## Recorded deviation (not a change)

The R1–R6 role-classification mechanism (`build_guidance`,
`classify_guidance_roles`) referenced by the canonical pre-generation-guidance
closeout does **not exist** at this SHA; it lives only in a divergent sibling
working copy. Per the freeze policy it was neither imported nor recreated.
Consequence: results are scoped to "decision persistence across compaction at
Mneme f7eac387", not to role-aware guidance.

## Production boundaries respected

- No new parallel retrieval algorithm; the treatment plugin performs **no**
  retrieval — it re-emits the frozen text verbatim (hash-checked).
- No production file under `mneme/` is modified by this experiment.
- Experimental code is confined to `validation/ox-compaction/**`.
- The closed pre-generation-guidance R6 experiment is not reopened; this is a
  separate compaction-persistence mechanism question.
