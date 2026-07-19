# Architectural drift prevention -- runnable walkthrough

This is the runnable companion to the [Architectural drift prevention
flagship demo](https://mnemehq.com/demo/architectural-drift/). It
simulates a three-step timeline of agent-produced changes and exercises
the real Mneme enforcement pipeline against each proposed diff.

## What this proves

The flagship narrative claims two things:

1. **Without a governance layer, drift propagates.** Each agent's
   proposed change is locally reasonable; the system as a whole still
   diverges from the architectural invariants the team encoded.
2. **With Mneme, the first divergence is blocked upstream.** The retry
   converges within constraints, and downstream agents build on the
   corrected codebase by construction.

This script demonstrates property (2) end-to-end using the real
`mneme check` CLI. Property (1) is shown by contrast -- the script
prints the no-governance timeline as narrative and runs the enforcer
against a would-be Agent B Redis diff to show the same WARN that would
have fired upstream.

## What this does NOT claim

- There is **no LLM call**. The "agent" diffs are fixture text files
  in this directory. The point is governance coherence, not multi-agent
  runtime sophistication.
- The orchestration is sequential and scripted on purpose. The proof
  surface for this demo is the **enforcement output**, which is
  deterministic and reproducible.

## How to run

```bash
# From the repo root (after pip install -e .):
cd examples/architectural-drift
python run.py
```

Requires the `mneme` package on `PYTHONPATH`. Either install it from
this repo's root, or `pip install mneme-hq`.

## Files

| File | Purpose |
|---|---|
| `project_memory.json` | Minimal decision corpus encoding ADR-001 (JSON-only storage) and ADR-003 (no ORM) |
| `agent_a_redis_cache.txt` | Agent A's first draft -- introduces Redis (violates ADR-001) |
| `agent_a_retry_json_cache.txt` | Agent A's retry after ADR-001 injection -- in-process JSON cache |
| `agent_b_session_redis.txt` | What Agent B would produce without governance (Redis) |
| `agent_b_session_repository.txt` | What Agent B produces with governance (Repository over JSON) |
| `run.py` | The walkthrough |

## Expected output (abbreviated)

```
== Without a governance layer -- drift propagation ==

  Monday  | Agent A  | 'speed up user lookup'
          |          | --> adds redis-py, wires a cache layer
          | Verdict  | (no check ran)
  ...
  Friday  | Architect notices. ADR-001 silently dead.

== With Mneme -- upstream block + retry convergence ==

-- Step 1: Agent A's first draft (Redis cache) -- expect WARN
  $ -m mneme check --memory ... --input agent_a_redis_cache.txt ...

WARN  [ADR-001] no redis -- trigger: redis
      JSON storage only -- no external database.

Result: WARN

-- Step 2: Agent A's retry after ADR-001 injection -- expect PASS
  ...
Result: PASS
```

Same `project_memory.json` for both timelines. The only difference is
that the with-governance timeline actually runs the enforcer against
each diff before it would have landed.
