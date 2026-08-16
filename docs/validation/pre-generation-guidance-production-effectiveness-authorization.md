# Production-path Guidance Effectiveness A/B Authorization

**Decision:** conditional GO, prospective authorization only  
**Status:** authorized to lock and review; trials not started  
**Date:** 2026-08-14  
**Execution owner:** the Codex task that creates the fresh execution lock; no
second task may execute or resume campaign slots

## Decision boundary

Authorize one controlled production-path effectiveness A/B to determine
whether automatic pre-generation guidance improves Claude's first coding
attempt or reduces the work required to reach a compliant attempt.

This decision does not reopen, reinterpret, rerun, or amend R6. R6 remains
permanently **FAIL** under its frozen gate. The post-R6 storage 2x2 remains
supporting diagnosis only and does not retroactively make R6 pass.

The authorization supersedes only the failed-R6 prerequisite that prevented a
limited production-effectiveness evaluation from starting. It does not
supersede any frozen input, metric, claim gate, guardrail, contamination
control, invalidation rule, or stopping rule in the locked design and scoring
protocol.

## Frozen design and protocol

- Design lock:
  `docs/validation/pre-generation-guidance-confirmatory-design-lock.json`
  (`1FF5E24CDA85458D27C1115BB51307DD9BBA6562B3F97660C191DE67E15183FA`)
- Scoring protocol:
  `docs/validation/pre-generation-guidance-live-ab.md`
  (`8029EACBB4C8032A491486CE881E9415966C27606DA7CC2631CEA868EA4BF604`)
- Evaluation: `production_effectiveness` only
- Schedule: the frozen 42 slots, comprising seven tasks, two arms, and three
  repetitions in the frozen paired order
- Claim boundary: the controlled fixture and its seven task types only

Neither frozen file may change. The fresh execution lock must fail closed if
either hash changes.

## Conditions of authorization

1. Create a new execution manifest for the current role-aware implementation.
2. Hash and lock every executable campaign input, including the current
   `mneme/guidance.py`, the preserved R6 runner imported for shared capture
   primitives, the production-only runner, package runtime modules, plugin
   configuration, Python and Claude executables, and Mneme entry-point shims.
3. Use the production plugin in both arms. Change only `MNEME_GUIDANCE` between
   arms. Keep strict `PreToolUse` enforcement enabled in both arms.
4. Allow normal model discovery of `.mneme/project_memory.json` in both arms;
   do not reuse the mechanism-isolation setting that denies model access to
   the memory file.
5. Preserve fresh repositories and sessions, disabled auto-memory and
   `CLAUDE.md`, disabled skills and slash commands, empty MCP configuration,
   the frozen model/tool configuration, paired ordering, raw event streams,
   first-attempt capture, blinding, and independent scoring.
6. Before the first trial, independently verify the authorization, manifest,
   runtime hashes, 42-slot schedule, production memory access, and injection
   delivery classifier.
7. Only the designated Codex task may execute campaign slots. Existing scored
   slots must never be silently rerun or overwritten.

## Injection-delivery outcome contract

For every governed treatment slot, the exact role-aware guidance frozen for
that task must be present in a successful production `UserPromptSubmit` hook
response before the first assistant event and therefore before the first
attempted edit.

A missing, empty, mismatched, duplicate, or late governed-treatment injection
is a **scored treatment operational failure**. Preserve the run in its frozen
slot. It may not be excluded, relabelled as a technical invalidation, or rerun.
Stop the campaign immediately and investigate before spending another run.

Unexpected automatic guidance in a baseline slot is an arm-isolation failure.
Preserve its evidence and stop immediately; do not continue until a prospective
re-lock resolves the contamination. A treatment control prompt that receives
irrelevant guidance remains a scored product outcome rather than a technical
invalidation.

## Stop conditions

Stop immediately if any frozen or execution-locked input changes, the Claude
Code version or resolved model changes, arm isolation fails, the first
pre-feedback attempt cannot be identified, or event-order evidence is missing
or contradictory. Apply the frozen protocol's distinction between pre-turn
technical invalidations and post-turn scored outcomes without modification.

## Permitted conclusion

The strongest allowable positive conclusion is:

> Automatic pre-generation guidance demonstrated incremental effectiveness
> through the production Claude Code integration in a controlled seven-task
> fixture.

Do not claim effectiveness across varied real-world repositories. A failed or
inconclusive result must be reported under the frozen outcome-specific gates
and guardrails without weakening the baseline or changing the claim boundary.

## Execution state

This authorization permits creation and review of the fresh execution lock.
It does **not** itself start a trial. The production campaign remains
`AUTHORIZED_NOT_STARTED` until the fresh manifest and its independent review
both pass.
