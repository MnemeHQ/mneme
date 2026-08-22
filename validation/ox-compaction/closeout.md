# ox-compaction closeout

Date: 2026-08-22
Verdict: **NULL** (locked gate; see below)

## Question

Does injecting the currently applicable Mneme architectural decision into an
agent's conversation-compaction checkpoint improve architectural compliance
after compaction?

## Environment (exact)

| Item | Value |
|---|---|
| Mneme commit | `f7eac3875eae5dcb7f57ac55388567877c0ce692` (branch `validation/ox-compaction`, isolated worktree) |
| Python | 3.12.10 |
| Mneme package | mneme-hq 0.5.1 |
| OpenCode CLI | 1.18.21 (via `bun x opencode-ai`; not on PATH) |
| Plugin typings | @opencode-ai/plugin 1.18.18 |
| Provider / model | `opencode` / `x-preview-f-free` (identical across all runs, verified) |
| Auth | environment-provided credentials; verified headless before any run |

## Design

Two arms, identical in every respect except the compaction checkpoint:

- **Arm A (control):** initial task prompt + frozen Mneme guidance supplied
  once, pre-compaction. Real OpenCode compaction. No reinjection.
- **Arm B (treatment):** identical, plus the byte-identical frozen guidance
  appended to the compaction prompt via the installed
  `experimental.session.compacting` plugin hook.

Fixture: deterministic repository-layer rule with an attractive shortcut and a
fully actionable compliant path (`fixture/template/`). Guidance produced by
this tree's production path only: `DecisionRetriever.retrieve()` →
`format_decisions()`; frozen text sha256
`5378d1fd3046d24f8db9d77a84648de98420beb87a6c44d2fb38575957c98d5e`; decision
`arch-001-repository-layer` selected at score 33.5.

Compaction was real, never simulated: `POST /session/{id}/summarize` — the V1
mechanism behind `/compact` (the V2 `/api/session/{id}/compact` route is an
unimplemented stub returning 503 by design). Every run's compaction is proven
independently of the treatment plugin by the OpenCode server's own
`agent=compaction` LLM-stream log line, archived per run.

Isolation: per-run `XDG_CONFIG_HOME` (structurally excludes the user's global
`mneme-guard.js`; probe-verified) and per-run `XDG_DATA_HOME`. Arm A config
home contains no plugin file at all; Arm B exactly one.

Sequence: frozen interleaved A,B,B,A,B,A,A,B,B,A (10 runs).

## Deviations and self-corrections (all recorded in experiment-lock.json)

1. **Guidance path:** the R1–R6 role-classification modules do not exist at
   the frozen SHA (only in a divergent sibling copy). Not imported or
   recreated. Results are scoped to this frozen version's production path.
2. **Harness defects found during preflight** (evidence preserved under
   `runs/_invalidated/`): V1/V2 API mismatch; mid-turn completion detection;
   intermittent agent-loop scheduling failure caused by shared
   `opencode.db` contention (fixed with per-run data-home isolation).
3. **run-04-a2 invalidated**: silent infrastructure stall (zero LLM activity,
   zero durable messages). Replaced by run-11-a5 in the same slot.
4. **Scorer defect corrected post-run**: docstrings/comments *quoting* the
   rule were falsely flagged as violations (surfaced by run-02-b1, where the
   agent documented its compliance). Fixed via tokenize-based code-only
   scanning; all preserved workspaces re-scored from artifacts. No trial was
   rerun. Only run-02-b1's architecture result changed (False→True).
5. **Verdict-mapping corrected post-run**: initial raw-count comparison
   mislabeled the outcome FAIL; replaced with a verbatim implementation of
   the locked gate text. The locked gate itself was never modified.
6. **Archival normalization for the evidence commit**: embedded throwaway
   fixture `.git` scaffolding was removed from archived workspace copies so
   they could be committed as plain files (baseline identity was already
   proven by blob-hash comparison; SHAs remain recorded in run.json).

## Explicit scope statement

**No OpenCode compaction feature and no Mneme production change is proposed,
implied, or implemented by this experiment.** This is validation evidence
only.

## Run outcomes (final, corrected scoring)

| Run | Arm | Pre arch | Post arch | Functional | Scope exp. | Compaction verified | Injects |
|---|---|---|---|---|---|---|---|
| run-01-a1 | A | ✓ | ✓ | ✓ pre+post | 0 | log-proven | 0 |
| run-02-b1 | B | ✓ | ✓ | ✓ pre+post | 0 | log-proven | 1 (hash match) |
| run-03-b2 | B | ✓ | ✓ | ✓ pre+post | 0 | log-proven | 1 (hash match) |
| run-05-b3 | B | ✓ | ✓ | ✓ pre+post | 0 | log-proven | 1 (hash match) |
| run-06-a2 | A | ✓ | ✓ | ✓ pre+post | 0 | log-proven | 0 |
| run-07-a3 | A | ✓ | ✓ | ✓ pre+post | 0 | log-proven | 0 |
| run-08-b4 | B | ✓ | ✓ | ✓ pre+post | 0 | log-proven | 1 (hash match) |
| run-09-b5 | B | ✓ | ✓ | ✓ pre+post | 0 | log-proven | 1 (hash match) |
| run-10-a4 | A | ✓ | ✓ | ✓ pre+post | 0 | log-proven | 0 |
| run-11-a5 | A | ✓ | ✓ | ✓ pre+post | 0 | log-proven | 0 |

Invalidated runs: `run-04-a2-silent-stall` (infrastructure), plus three
preflight harness-defect artifacts. None silently discarded; all evidence
preserved under `runs/_invalidated/`.

## Control vs treatment

| Metric | Control | Treatment |
|---|---|---|
| Architecturally compliant pre-compaction | 5/5 | 5/5 |
| **Architecturally compliant post-compaction** | **5/5** | **5/5** |
| Retained compliance (pre-compliant → post) | **5/5** | **5/5** |
| Functionally complete (post suite) | 5/5 | 5/5 |
| Scope expansion | 0 | 0 |
| Treatment delivery (inject=1, frozen hash) | n/a | 5/5 |

## Verdict: NULL — what the evidence supports

- Under the locked PASS gate, treatment met its own conditions (5/5
  compliant, 5/5 functional, 0 scope expansion) but the gate also requires
  ≥2 control post-compaction architectural failures; control had **zero**.
- Standard OpenCode compaction (v1.18.21, model `x-preview-f-free`) retained
  the governing architectural decision across compaction in **every**
  control run. The derived metric — compliance retention among
  pre-compliant runs — is 5/5 control vs 4/4→5/5 treatment (after scorer
  correction), i.e. no compaction-related decision loss existed to recover.

What this experiment supports:

- At this OpenCode version and model, manual `/compact`-mechanism
  summarization does **not** by itself lose Mneme architectural decisions
  for a well-formed, actionable decision supplied pre-compaction.
- The compaction-injection mechanism itself works reliably end-to-end:
  hook fires exactly once per compaction, delivers the byte-identical
  frozen guidance, with full structured evidence.

What it does NOT support:

- Any claim that reinjection improves outcomes when loss does occur
  (no loss was observed; ceiling effect).
- Generalization to automatic token-pressure compaction, other models,
  longer sessions, weaker guidance, or other OpenCode versions.

## Production recommendation

**No production Mneme compaction integration is justified on this evidence.**
The measured mechanism-level benefit is nil against a perfect control
baseline, and adding a permanent injection surface would add complexity
without demonstrated value. If future evidence shows decision loss under
automatic overflow compaction or different models, this harness can be reused
as-is; the treatment adapter remains experimental-only under
`validation/ox-compaction/`.

## Validation record

- Fixture baseline trees content-identical across all 10 runs (blob-hash
  comparison); single Mneme SHA, model ID, and prompt hashes verified.
- Scorer validated against known-good and known-bad implementations both
  before and after the defect fix.
- Worktree contains zero modified production files (`git diff` on `mneme/`,
  `tests/` empty; only untracked `validation/`).
- Test-suite fingerprint at closeout: **579 passed, 5 skipped, 0 failed** —
  no new failures relative to the recorded baseline fingerprint (the
  pre-existing SDK adapter failure does not reproduce inside this worktree
  because the main checkout's untracked directories add extra collected
  tests; nothing under `tests/integrations/agent_sdk/` or
  `mneme/integrations/agent_sdk/` was touched).
- Nothing merged; no release published; no historical validation artifacts
  modified.
