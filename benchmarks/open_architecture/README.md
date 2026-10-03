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

## Staged Benchmark Protocol

Batch 01 is structured into three decoupled evaluation stages:

### Stage A — Discovery
- **Input**: Pinned repository sources at frozen commit SHAs.
- **Execution**: `discover_sources` followed by `HeuristicExtractor`.
- **Output**: Dynamically identified `cand-*` `ExtractedCandidate` evidence spans.
- **Identity**: `cand-*` represents dynamic discovery identity; `ref-*` represents frozen benchmark ground-truth identity. These namespaces are never rewritten or treated as equal.
- **Matching rule**: A dynamic candidate $C$ matches a frozen reference $R$ iff $C$'s source path matches one of $R$'s source-file components, and $C$'s line interval has a non-empty intersection with one of $R$'s line intervals for that source-file component. No semantic/LLM matching; no IoR or IoC threshold.
- **Primary metrics**:
  - Discovery Recall: $(\text{frozen reference decisions overlapped by } \ge 1 \text{ candidate}) / (\text{all frozen reference decisions})$
  - Discovery Precision: $(\text{extracted candidates overlapping } \ge 1 \text{ frozen reference decision}) / (\text{all extracted candidates})$
- **Model calls**: Exactly 0.

### Stage B — Semantic Classification
- **Population**: Exactly the frozen 100 human-reviewed reference decisions (20 per repository). Dynamic 5,459-candidate heuristic extraction output is NOT the classifier baseline population.
- **Tasks**: Exactly the eight frozen semantic tasks per decision.
- **Expected logical task count**: $100 \times 8 = 800$ logical classifier tasks (provider retries may produce additional HTTP attempts).
- **ClassifierTask mapping**:
  - `candidate_id` = `reference_decision_id`
  - `repository_identifier` = `repository`
  - `repository_commit_sha` = `repository_commit_sha`
  - `source_path` = `source_file`
  - `source_location` = `source_location`
  - `raw_statement` = `raw_evidence`
  - `source_context` = `raw_evidence`
  - `taxonomy_version` = `0.1`
- **Evidence invariance**: The same frozen evidence is supplied across all classifier backends. Predictions are evaluated against frozen human labels.

### Stage C — Governing Decision Set (GDS)
- **Input**: Classified representation of the 20 frozen reference decisions per repository, preserving `ref-*` as `DecisionCandidate.candidate_id`.
- **Scenarios**: Evaluated against the 10 frozen applicability scenarios belonging to the repository (`expected_governing_decision_ids` use `ref-*`).
- **Projection**: Project `ref-*` `DecisionCandidate` instances through the existing frozen projection; retrieve using the existing frozen `DecisionRetriever` (`score_gt_zero` policy).
- **Evaluation**: Both predicted IDs and expected scenario IDs are `ref-*`. Compute GDS precision, recall, and F1 (headline metric). GDS never compares `cand-*` IDs directly with `ref-*` IDs.

## Scenario Identity and Provenance

Two scenario identities are kept strictly distinct:
1. **Frozen Batch 01 Scenario Corpus Identity**: `2ff8751955fd64a33316aca6692dc803` — the deterministic hash of all 50 canonical scenarios across all five repositories (stored in `baseline.yaml` as `scenario_corpus.content_hash`).
2. **Per-Repository Execution Subset Identity**: The hash of the actual 10 scenarios evaluated for a given repository (recorded in `RunMetadata.scenario_content_hash`).

`RunMetadata.scenario_content_hash` is not redefined and `RunMetadata` is not modified. The future Batch 01 harness will bind global benchmark provenance outside the frozen `RunMetadata` contract using a research-only batch provenance envelope containing:
- `baseline_id`
- `baseline_configuration_hash`
- `reference_corpus_hash`
- `scenario_corpus_hash`
- per-repository `RunMetadata`

## Frozen Baseline Identities

- `semantic_mneme_sha`: `3673c36855fb1e30d46942ce826c50be4888df5e`
- `reference_corpus` hash (Batch 01 v0.1): `0455bd66aae52551c35b37a63c2d185f` (100 decisions, 20/repo). Historical baseline executions (B0, Arm A, Arm B) remain bound to this exact hash.
- `reference_corpus` hash (Batch 01 v0.2-grounding): `700a569e24bf90707ba14ff65eea2ab5` (100 decisions, 20/repo). Applies the grounding correction for `ref-gsa-agentic-coding-quickstart-005` (`relationships: []`).
- `scenario_corpus` hash: `2ff8751955fd64a33316aca6692dc803` (50 scenarios, 10/repo)

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
