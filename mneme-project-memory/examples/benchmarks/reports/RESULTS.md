## Mneme Benchmark Results

| Scenario | Verdict | Baseline | Enhanced | Recall@K | Precision@K | Irrelevant | Notes |
|---|---|---|---|---|---|---|---|
| feature_boundary_violation | PASS | 3 | 0 | 1.00 | 0.33 | yes | autogen, crewai, src/agents/coordinator.py |
| framework_abstraction_violation | PASS | 2 | 0 | 1.00 | 0.33 | yes | langchain, langchain-anthropic, src/chains/main.py |
| infra_scope_creep_violation | PASS | 4 | 0 | 1.00 | 0.33 | yes | redis, celery, src/agents/worker.py |
| openai_provider_violation | PASS | 2 | 0 | -- | -- | -- | openai, mneme/providers/openai.py |
| pydantic_dependency_creep | PASS | 2 | 0 | -- | -- | -- | pydantic, mneme/schemas.py |
| retrieval_complexity_violation | PASS | 4 | 0 | 1.00 | 0.33 | yes | sentence-transformers, chromadb, src/embeddings/encoder.py |
| storage_backend_violation | PASS | 5 | 0 | 1.00 | 0.33 | yes | sqlalchemy, alembic, psycopg2-binary |

## Summary

**Layer 2 (enforcement)** — 7/7 violations caught (100% pass rate).

**Layer 1 (retrieval, n=5)** — mean Recall@3 1.00, mean Precision@3 0.33, irrelevant injection rate 100%.

**By category:**

- **anti_pattern**: 2/2 PASS
- **architecture**: 2/2 PASS
- **scope**: 3/3 PASS