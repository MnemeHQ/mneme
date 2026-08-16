# Pre-generation Guidance Applicability Diagnosis

**Status:** diagnosis and characterization benchmark complete  
**Date:** 2026-08-13  
**Production guidance behavior:** unchanged  
**Production-effectiveness A/B:** paused; no runs started  
**Protected E66 collection:** unchanged

## Finding

`ADR-STORAGE` entered all three guided authentication runs through the intended
lexical retrieval path, not through enforcement or ADR-020 path applicability.
The defect is that prompt guidance has no guidance-role classification stage
between relevance selection and formatting.

For the locked authentication prompt:

```text
Implement browser authentication state for account login.
```

the current deterministic scores are:

| Decision | Score | Match evidence | Classification for this task |
|---|---:|---|---|
| `ADR-AUTH` | 8.0 | decision=2, scope=2, constraint=1, rationale=1 | Direct constraint |
| `ADR-STORAGE` | 2.0 | scope=1 (`login`) | Adjacent context |

The selection threshold is strictly greater than 1.0, K is 3, and a scope
match is structured evidence. `ADR-STORAGE` therefore passes selection. The
formatter renders both results as identical `DECISION` blocks and the header
does not say that decisions constrain only the requested work or prohibit
adjacent implementation.

The current call boundary is also important: `UserPromptSubmit` supplies the
prompt and working directory. Although the E66 fixture records
`target = src/auth.py`, the production `build_guidance()` call receives no
target path. It cannot apply target-aware decision filtering at this stage.

## Architectural classification

| Candidate cause | Classification | Evidence |
|---|---|---|
| Retrieval relevance | Contributing, not a weighting-formula defect | A broad authored scope term (`login`) creates a valid but weak lexical match. The retriever returns explainable evidence exactly as designed. |
| Guidance role classification | **Primary missing layer** | Selection flows directly into formatting; there is no direct-versus-adjacent role. |
| Guidance wording | Contributing amplifier | Equal-status blocks and no scope-limiting instruction allow a relevant constraint to be interpreted as extra requested work. |
| ADR-020 rule applicability | Not the mechanism involved | ADR-020 selectors belong to individual typed rules and require an artifact path. Neither ADR in this incident contains such a rule. |
| Enforcement | Not involved | The mechanism run supplied no `PreToolUse` feedback; enforcement ran offline only after Claude exited. |
| Task ambiguity | Not the leading cause | The locked target was `src/auth.py`, fixture modules were separate, and none of the three baseline auth runs expanded into storage. |

This preserves ADR-017: retrieval still determines context and does not limit
deterministic enforcement. It also preserves ADR-020: typed-rule path
applicability remains a separate edit-time stage.

## Trace confirmation

All three treatment auth runs received `ADR-AUTH, ADR-STORAGE`. Runs 1 and 2
first attempted `src/sessions.py`; run 3 first attempted `src/auth.py`. Every
final diff changed both `src/auth.py` and `src/sessions.py`.

## Locked characterization benchmark

The new benchmark is intentionally separate from the frozen retrieval fixture:

- fixture: `tests/fixtures/guidance_applicability/cases.json`
- fixture SHA-256:
  `2408DD615BB54E3BB8E03B8A28CA1BE9CDC0670E5C4BBA6C04541BA902BADEAB`
- memory SHA-256:
  `983BAA775AAF38AB36C5D83CA07379C16F72A931BD7568BBA58D13C25B2C45DD`
- evaluator: `python -m mneme.guidance_applicability_eval tests/fixtures/guidance_applicability/cases.json`

The four cases pin the exact E66 auth failure, the symmetric storage/auth
adjacency, a specific auth prompt, and an unrelated control.

| Metric | Baseline |
|---|---:|
| Snapshot matches | 4/4 |
| Direct decision recall@3 | 1.00 |
| Adjacent decisions emitted without a role | 2 |
| Unexpected decisions | 0 |
| Diagnosis reproduced | yes |

This is a characterization baseline, not a claim that adjacent decisions must
always be removed. A remediation may suppress adjacent context or retain it in
an explicitly non-authorizing role. The locked direct/adjacent classifications
must not be rewritten to make a candidate pass.

## Remediation boundary

Do not change retrieval weights, K, the existing retrieval fixture, ADR-017
enforcement behavior, or ADR-020 typed-rule applicability in the first repair.

The remediation sequence is a narrow guidance-only program:

1. freeze `direct` and `adjacent_constraint` semantics and non-authorizing
   wording;
2. design deterministic role classification without changing retrieval;
3. evaluate the classifier and formatter against locked benchmarks;
4. change production guidance only after those gates pass;
5. run the full mechanical regression suite; and
6. create a new lock and isolated mechanism campaign without overwriting E66.

The characterization does not yet select a scoring heuristic. In particular,
“drop every single-token scope match” must be evaluated across the full corpus
before adoption; it is not assumed safe from this one incident.

## Checkpoints, effort, and recommended models

| Checkpoint | Work | Effort | Recommended model/effort | Exit condition |
|---|---|---:|---|---|
| R1 | Freeze role semantics and canonical non-authorizing wording | Medium | `gpt-5.6-sol`, high | Contract frozen; no classifier or runtime change |
| R2 | Design and compare deterministic role classifiers | Medium-high | `gpt-5.6-sol`, high | One explainable classifier selected without retrieval changes |
| R3 | Evaluate candidate classifier and formatter | Medium | `gpt-5.6-sol`, high | Role benchmark and existing retrieval gates pass |
| R4 | Change production guidance behind the existing opt-in | Medium-high | `gpt-5.6-sol`, high | Role-aware output implemented; hooks and enforcement boundaries preserved |
| R5 | Full mechanical and adversarial regression | Medium | `gpt-5.6-terra`, medium for runs; `gpt-5.6-sol`, high for failures | Full suite, plugins, latency, and prompt matrix pass |
| R6 | Freeze new execution lock, then run a fresh mechanism campaign | High external-run effort | `gpt-5.6-sol`, high for lock; Claude Code `sonnet`, effort `high` for trials | New lock and artifacts; compliance and scope guardrails pass |
