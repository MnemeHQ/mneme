# ADR-001: Cache Strategy

Status: Accepted

Decision: This project must use Postgres-backed caching only.

Do not introduce Redis, Memcached, or external cache services.
All cache reads and writes must go through `src/cache.py`.

Rationale: The product runs in regulated enterprise environments where infrastructure must stay simple, auditable, and consistent across deployments.
