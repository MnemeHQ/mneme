# Pre-generation Architectural Guidance Charter

**Status:** approved implementation charter  
**Date:** 2026-08-13  
**Scope:** deterministic task-to-decision retrieval and Claude Code prompt-time guidance

## 1. Purpose

This charter permits Mneme to add deterministic architectural guidance before
Claude Code generates a proposal while preserving the independent edit-time
enforcement boundary.

The product contract is:

> **Guide before generation; enforce before write.**

The new layer is guidance, not deterministic enforcement. A retrieved decision
can shape Claude's first proposal, but the existing `PreToolUse` edit gate remains
the authority that allows or blocks a proposed write.

## 2. Historical reconciliation

The Layer 1 freeze describes the original pipeline as prompt-boundary
intervention. The shipped Claude Code integration subsequently established a
different concrete boundary: `PreToolUse` checks proposed edits immediately
before they are written. ADR-017 then separated relevance retrieval from
enforcement scope, ADR-018 limited edit checks to introduced content, ADR-019
introduced typed literal rules, and ADR-020 added explicit artifact-path
applicability.

This charter does not rewrite that history. It defines the current architecture:

1. **Historical Layer 1 mechanism:** programmatic callers could retrieve and
   inject decisions before an LLM call.
2. **Current Claude Code enforcement:** a `PreToolUse` hook deterministically
   evaluates a proposed edit before the file write.
3. **New Claude Code guidance:** a `UserPromptSubmit` hook retrieves decisions
   from the current task and adds compact context before Claude processes it.

This is the explicit charter amendment required by the Layer 1 freeze. It
permits deterministic task-to-decision retrieval for pre-generation guidance
while preserving the retrieval/enforcement separation established by ADR-017.

## 3. Non-negotiable contracts

### 3.1 Retrieval and enforcement remain separate

- Retrieval answers which decisions are relevant enough to show.
- Enforcement answers whether proposed introduced content violates an
  applicable rule.
- A retrieval miss never converts an edit-time violation into permission.
- The guidance hook never blocks a user prompt.
- The existing edit hook is not weakened, bypassed, or merged with guidance.

### 3.2 Current-prompt-only MVP

Guidance is derived solely from the current submitted prompt. Mneme does not
infer missing task context from conversation history in this release.

Consequences:

- A descriptive prompt such as `Add persistent session storage` can retrieve
  storage decisions.
- Follow-ups such as `yes`, `do it`, or `continue` normally inject nothing.
- Transcript summarization, session state, and task carry-forward are out of
  scope.

### 3.3 Low-signal prompts inject nothing

The `DecisionRetriever` empty-token fallback is not eligible for automatic
guidance. A prompt that produces no meaningful query tokens, no positive-scoring
decision, or no result above the guidance confidence gate returns no context.

No-context is a valid, safe outcome. The hook must not pad a prompt with arbitrary
decisions merely to fill K.

### 3.4 Path applicability is descriptive until a path exists

At `UserPromptSubmit` time, the eventual target artifact is often unknown.
ADR-020 applicability therefore cannot be evaluated as `APPLIED` or `EXCLUDED`.

For every retrieved typed rule, guidance must preserve and display:

- rule type and value;
- `include_paths`, when present; and
- `exclude_paths`, when present.

The wording must describe conditional applicability, for example:

```text
RULE: install legacy-client is forbidden
APPLIES WHEN editing: docs/**
EXCLUDES: docs/history/**
```

It must not claim that a scoped rule applies to the current task. Definitive path
applicability remains an edit-time operation once a target path is known.

### 3.5 Deterministic, local, and bounded

- The guidance hook makes no model, network, embedding, or vector-database call.
- Same prompt plus same memory produces byte-identical selected IDs and context.
- Canonical K remains `DEFAULT_MAX_DECISIONS == 3`.
- Output is compact and capped below Claude Code's 10,000-character spillover
  boundary; the implementation budget is 8,000 characters.
- The hook fails open on missing memory, malformed input, timeout, or runtime
  error and emits no accidental stdout context.

## 4. Evaluation before retrieval changes

A dedicated task-to-decision evaluation is created outside the frozen benchmark
fixtures. It contains:

- a fixed decision corpus;
- development and holdout task splits;
- expected and acceptable decision IDs;
- explicitly safety-critical cases;
- no-relevance and low-signal cases; and
- a versioned schema with a lock date.

The existing `DecisionRetriever` is evaluated unchanged first. Scoring changes
are allowed only if a predeclared gate fails. If the gates pass, Checkpoint 3
closes with no retriever modification.

Any allowed scorer change must remain deterministic and explainable, retain K=3,
preserve the existing benchmark invariants, and leave embeddings, learned
weights, and probabilistic reranking out of scope.

## 5. Launch gates

### 5.1 Retrieval gates

- Existing benchmark: 7/7 PASS.
- Existing governed recall@3: 1.00.
- Existing governed recall@1: 5/5.
- Safety-critical task recall@3: 1.00.
- Locked holdout macro recall@3: at least 0.90.
- Low-signal prompts: zero injected decisions.
- No-relevance false-injection rate: at most 0.10.
- Determinism: repeated runs have byte-identical selected IDs and context.

### 5.2 Runtime gates

- Context length: at most 8,000 characters.
- Local prompt-hook p95 target: below 500 ms on the release test machine.
- Hard hook timeout: 5 seconds.
- Missing/invalid memory and invalid hook envelopes fail open without stdout.
- Plugin and legacy installer configurations remain idempotent and valid.

### 5.3 Outcome gate

On a locked live-model task set, first-proposal architectural compliance must
improve versus the no-guidance baseline without increasing post-generation
enforcement failures in unrelated cases. Retrieval metrics are supporting
evidence; this behavioral comparison is the release claim gate.

## 6. Implementation checkpoints

### Checkpoint 1 — Charter

**Deliverable:** this approved contract.  
**Pass condition:** retrieval/enforcement separation, ADR-020 applicability,
current-prompt-only behavior, conditional scorer work, and launch gates are
explicit.

### Checkpoint 2 — Locked evaluation

**Deliverable:** versioned task corpus, evaluator, development/holdout split,
and unchanged-retriever baseline report.  
**Pass condition:** fixtures are immutable during scorer work and every metric
is reproducible from the repository.

### Checkpoint 3 — Conditional retrieval diagnosis

**Deliverable:** failure analysis and either a no-change decision or the smallest
principled deterministic scorer repair.  
**Pass condition:** all retrieval gates pass without changing frozen benchmark
semantics or fixtures.

### Checkpoint 4 — Guidance core

**Deliverable:** reusable selection and compact formatting API with typed-rule
selectors, confidence/noise gating, deduplication, and context budgeting.  
**Pass condition:** unit tests pin byte output, low-signal behavior, selector
wording, and the 8,000-character ceiling.

### Checkpoint 5 — Claude Code integration

**Deliverable:** opt-in `UserPromptSubmit` command hook plus plugin and legacy
installer configuration.  
**Pass condition:** valid `additionalContext` is emitted only for confident
matches; every operational failure fails open; `PreToolUse` behavior is
unchanged.

### Checkpoint 6 — Reliability and outcome validation

**Deliverable:** focused/full test results, plugin validation, latency evidence,
manual cross-platform smoke instructions, and the live-model A/B protocol.  
**Pass condition:** mechanical gates pass. The feature remains opt-in until the
live-model outcome gate has external results.

### Checkpoint 7 — Documentation and release handoff

**Deliverable:** accurate architecture, installation, configuration, limitation,
and claim language plus release checklist.  
**Pass condition:** public wording says `pre-generation architectural guidance`,
not `pre-generation enforcement`, and records the opt-in/outcome-gate status.

## 7. Out of scope

- Transcript or conversation-history summarization.
- Session/task carry-forward.
- LLM-based classification or reranking in the hook.
- Embeddings, vector stores, or learned weights.
- Cross-repository or organizational policy retrieval.
- Prompt blocking, prompt rewriting, or automatic remediation.
- Bash-write coverage or changes to the edit-time gate.
- Other coding harnesses in the first release.
- Changes to K or the frozen benchmark fixture set.
