# Mneme YC Demo

A tiny demo showing Mneme's core thesis:

> AI code generation increases throughput faster than human review capacity. Mneme prevents architectural drift before generated code reaches review.

## Demo flow

1. Show the ADR in `docs/adr/ADR-001-cache-strategy.md`.
2. Show `src/service_bad_ai_output.py`: AI introduced Redis, violating the ADR.
3. Run:

```bash
python mneme_check_demo.py src/service_bad_ai_output.py
```

4. Show the strict-mode block.
5. Show `src/service_good_mneme_output.py`: AI follows the approved cache abstraction.
6. Run:

```bash
python mneme_check_demo.py src/service_good_mneme_output.py
```

7. End with: Mneme enforces prior engineering decisions before generation/review.

## One-command walkthrough

```bash
bash run_demo.sh
```

## YC narration

"Here is a tiny repo with an accepted architectural decision: caching must use the approved Postgres-backed abstraction, not Redis. Without Mneme, a coding agent optimizes for performance and introduces Redis. Mneme retrieves the relevant decision and blocks the change in strict mode. When the agent is given Mneme's context, it produces compliant code using the approved abstraction. This is the core product: architectural governance for AI-assisted development before code reaches review."
