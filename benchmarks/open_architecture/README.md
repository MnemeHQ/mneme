# O1A Open Architecture Benchmark

This directory contains the executable and reproducible benchmark definition for the Mneme Open Architecture Project.

## Batch 01

Repositories:

1. `mbeacom/adrkit`
2. `GSA-TTS/agentic-coding-quickstart`
3. `AZX-PBC-OSS/helix`
4. `muhammetsafak/archlint`
5. `enumind/modonome`

Target:

- 20 manually reviewed decisions per repository
- 10 applicability scenarios per repository
- 100 validated decisions total
- 50 applicability scenarios total

## Core rule

Benchmark research data is not canonical project authority.

No inferred candidate may be automatically promoted into the Canonical Decision Index.

## Storage

Batch 01 uses SQLite as the durable local research store.

Use structured JSON or JSONL exports for deterministic benchmark artifacts and CI.

Runtime SQLite files are local state and are not committed.

## Reproducibility requirements

Every run must retain:

- repository SHA
- Mneme SHA
- Mneme version
- benchmark schema version
- taxonomy version
- classifier version
- configuration hash

Do not overwrite historical analysis runs.

## Baseline rule

Run all Batch 01 repositories against one frozen Mneme build before modifying semantic behaviour.

Record failures first.

Improve second.

Rerun third.
