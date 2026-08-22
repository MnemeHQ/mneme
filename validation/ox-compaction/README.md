# ox-compaction validation experiment

Question: does injecting the frozen Mneme architectural decision into the
OpenCode compaction checkpoint preserve architectural compliance after
compaction?

- Frozen Mneme SHA: `f7eac3875eae5dcb7f57ac55388567877c0ce692`
  (branch `validation/ox-compaction`; never merged automatically)
- OpenCode 1.18.21; model `opencode/x-preview-f-free`
- Design, gate, invalidation rules: `experiment-lock.json` (locked pre-run)
- Architecture boundaries honored: `architecture-alignment.md`

## Layout

| Path | Purpose |
|---|---|
| `fixture/template/` | Frozen fixture repo (repo-layer rule) |
| `prompts/` | Initial + continuation task text (identical both arms) |
| `frozen/guidance-frozen.txt` | Guidance from the production retrieval path, hash-pinned |
| `plugin/mneme-compaction-inject.js` | Treatment-only `experimental.session.compacting` adapter |
| `tools/freeze_guidance.py` | Runs real `DecisionRetriever -> format_decisions`, freezes output |
| `tools/score.py` | Deterministic functional/architecture/scope scorer |
| `tools/run_trial.py` | One full trial via OpenCode server API |
| `tools/run_all.py` | Frozen interleaved 10-run sequence |
| `tools/aggregate.py` | Aggregates to `results/final-result.json` |
| `runs/<run-id>/` | Per-run workspace, scores, session export, server log |
| `runs/_invalidated/` | Preserved invalid-run evidence with reasons |

## Arms

Both arms receive the identical initial prompt with the identical frozen
guidance block. Arm A compacts normally. Arm B additionally injects the
byte-identical guidance at `experimental.session.compacting`. Nothing else
differs: same model, fixture SHA, prompts, permissions, config home shape.

## Reproduce

```
python tools/run_all.py        # executes pending trials in frozen order
python tools/aggregate.py      # writes results/final-result.json
```
