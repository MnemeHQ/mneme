# Governance continuity across multiple actors -- runnable walkthrough

This is the runnable companion to the [Governance continuity flagship
demo](https://mnemehq.com/demo/multi-agent-governance/). Three actors
touch the same Python service sequentially. They share no memory with
each other -- they share only the compiled decision corpus emitted by
the [ADR compiler](https://mnemehq.com/demo/adr-compiler/).

## What this proves

The flagship narrative claims that as AI execution becomes distributed
and persistent, the governance layer is what keeps architectural
invariants coherent across actors. This script demonstrates the
*coherence* property directly:

1. **Actor A** introduces a Redis cache, gets blocked by ADR-001,
   retries, converges.
2. **Actor B** opens a fresh session with no memory of Actor A.
   Reads the corrected codebase. Builds session storage on the same
   JsonStore primitive. PASS by construction.
3. **Actor C** does a remediation pass. Proposes consolidating with
   SQLAlchemy. ADR-003 fires. The conflict surfaces as a structured
   verdict, not a silent block -- a human can amend the ADR or approve
   an explicit override.

The verdict format is identical for all three actors. The corpus is
identical on disk for all three actors. That's the continuity.

## What this does NOT claim

- There is **no multi-agent runtime**. No async queues, no
  orchestration framework, no LLM coordination. The "actors" are
  scripted diff producers in this directory.
- The orchestration is sequential. That is the proof surface that
  matters for this category: governance coherence is the small,
  testable property; multi-agent orchestration is a different problem.

## How to run

```bash
# From the repo root (after pip install -e .):
cd examples/multi-agent-governance
python run.py
```

## Files

| File | Purpose |
|---|---|
| `project_memory.json` | Shared decision corpus (ADR-001 JSON-only storage, ADR-003 no ORM) |
| `actor_a_first_draft.txt` | Actor A first draft -- introduces Redis (violates ADR-001) |
| `actor_a_retry.txt` | Actor A retry after ADR-001 surfaced -- in-process memo |
| `actor_b_compliant.txt` | Actor B session storage -- built on JsonStore primitive |
| `actor_c_remediation_with_orm.txt` | Actor C remediation -- proposes SQLAlchemy (violates ADR-003) |
| `actor_c_remediation_compliant.txt` | Actor C remediation -- shared JsonStore base (compliant) |
| `run.py` | The walkthrough |

## Expected verdicts

| Step | Expected verdict |
|---|---|
| Actor A.1 (Redis cache) | FAIL -- ADR-001 |
| Actor A.2 (retry, in-process memo) | PASS |
| Actor B (session storage on JsonStore) | PASS |
| Actor C.1 (consolidate with SQLAlchemy) | FAIL -- ADR-003 |
| Actor C.2 (consolidate with shared JsonStore) | PASS |

Same enforcer, same corpus, deterministic output across actors.
