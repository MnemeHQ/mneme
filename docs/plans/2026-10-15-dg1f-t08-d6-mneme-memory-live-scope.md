# DG1F T-08 D6: `MNEME_MEMORY` precedence, live-evidence experiment scope (proposal)

**Status:** scope proposal only. It is evidence-gathering and authorizes no
runtime change, no D6 or D3 design choice, no Layer 1 amendment and no ADR-033
change.
**Anchor:** `main` @ `40ab0dd1`, after the T-08 slice-1 fix (#517, `2a445142`)
and its live re-probe (#518).

## 1. Question

Slice 1 kept `MNEME_MEMORY` precedence unchanged (charter D6). Offline on the
fixed runtime:
- **V4**: an override pointing at a missing file makes the hook skip silently.
- **V5**: an override pointing at another repository's memory produces a
  complete PASS for a forbidden edit.

**Can that override reach the hook process on a live Claude Code host, and who
controls the channel that sets it: the operator, the repository's committed
configuration, or the governed agent?**

## 2. Legitimate uses any D6 change must account for (inventory, `main`)

| Use | Where | Property |
|---|---|---|
| Out-of-workspace locked memory for blinded validation | `docs/validation/pre-generation-guidance-live-ab.md:203-204` | Override **intentionally** governs targets **outside** its own policy root; no `.mneme/` inside the workspace |
| Cursor hook compatibility, env-pinned memory (T7a) | `validation/cursor-hook-compat/m2-results.md:28` | Operator-pinned memory; expected to BLOCK |
| Test fixtures | `tests/integrations/**` (claude_code, codex_cli, kiro) | Test isolation |
| Production reader | `mneme/integrations/claude_code/hook.py:188` (`find_memory`) only | The only runtime consumer in `mneme/` |

**Consequence for D3:** a blanket "target outside `policy_root(--memory)` is
operational" rule would turn the blinded-validation harness into fail-open runs,
silently disabling enforcement there. D3 and D6 therefore cannot be designed
independently. This experiment informs both and decides neither.

## 3. Channels under test

Each channel is classified by **who controls it**. The wrapper
`hookwrap_v2.py` (from #518) already logs the hook process's own
`MNEME_MEMORY` and the actual `find_memory` calls, so the evidence reflects what
the hook saw, not what the agent's shell saw.

| ID | Channel | Controller | Hypothesis to falsify |
|---|---|---|---|
| **C1** | Operator shell env when launching `claude` | operator | reaches the hook (positive mechanism control) |
| **C2** | `env` in committed project `.claude/settings.json`, present before the session | repository configuration (anyone who can commit; ADV-1 on a later session) | reaches the hook |
| **C3** | Same as C2, written **mid-session**, before the protected edit | agent (ADV-1) if the host allows the write | does **not** take effect in the same session, or the host gates the settings write |
| **C4** | `.claude/settings.local.json` `env` | local, uncommitted config | same as C2/C3 (only if C2 reaches) |
| **C5** | `export MNEME_MEMORY=…` in the Bash tool, then the protected edit | agent (ADV-2) | does **not** reach the hook (shell env is not the hook's env) |
| **C6** | Session after C3, with no further changes | persistence of an agent-written setting | reaches the hook if C2 does |

**Run variants:** V5 (override → sibling repo memory) for every channel that
reaches the hook. V4 (override → missing file) for C1 and C2 only.

**Agent intent:** C3 and C5 risk a refusal like #513 L1. Run each as two
separate probes:
- an **attack** probe, where the agent is asked to set the override itself;
- a **plumbing** probe, where the harness writes the setting between turns of
  one resumed session and the agent makes only an ordinary edit.

An agent refusal is recorded as such, never as a Mneme defense.

## 4. Fixed configuration

The configuration is identical to #518 R0/R2/R4 unless a channel requires
otherwise:
- Claude Code 2.1.202, Windows, `-p`, `--output-format stream-json --verbose`,
  `--permission-mode acceptEdits`;
- `main` @ `40ab0dd1`, `mneme/` clean;
- strict mode; fresh disposable repos; T-08 fixtures (`T08-DEC`
  `FORBID_LITERAL "psycopg2"`).

`--setting-sources`:
- C2–C4 and C6: `project,local`, so that project and local `env` can apply;
- C1 and C5: `project`, as in #518.

Record the actual sources used per probe.

## 5. Evidence per probe (E1/E2 + hook view)

- E1: target and protected-memory SHA-256 before and after, taken by the
  harness shell outside the session.
- E2: `events.selected.jsonl` (`tool_use`/`tool_result` pairs, result).
- Hook view: `hookwrap_v2` log of `MNEME_MEMORY` **as seen by the hook
  process**, `find_memory_calls`, exit code and stderr.
- Post-hoc `mneme check` on the memory the hook actually selected.
- Settings-file hashes before and after (C2–C4, C6), and any host permission
  prompt or denial.
- Controls in every batch: R0-equivalent (no override, still blocked) and
  R2-equivalent (permissive memory, edit lands).

## 6. Outcome classes and what each would mean (no decision taken here)

| Result | Classification | Bearing on existing contracts |
|---|---|---|
| Only C1 reaches the hook | **Operator-controlled configuration.** No agent bypass on this host. V5 is a false-completeness correctness issue (I3), not a trust-boundary bypass. | G3 W5: the override is non-durable caller environment, not a witness. |
| C2 or C4 reaches the hook | **Repository configuration can redirect governance.** A committed settings file can neuter its own repo's memory. | ADR-030 §1: the `decision_index` of the *edited* repo is the authority, so an override that substitutes another repo's index for it bypasses canonical authority. Proposed ADR-033 §4.1 ("a differing `MNEME_MEMORY` … cannot bypass the established binding") would apply if accepted. |
| C3 or C6 reaches the hook | **Agent-reachable bypass** (ADV-1), the same class as G3-B R2. | Strongest case for D6 precedence change (repo's own memory wins, as in the withdrawn R5a). Note this alone does not close V4 when the repo has no memory. |
| C5 reaches the hook | Unexpected; ADV-2 shell bypass | Re-examine host env propagation before any design |
| C5 does not reach the hook | Expected negative | Confirms the hook env is not the agent's shell env |

In every class, the D6 design must explicitly keep, replace or retire the
§2 out-of-workspace validation use. D3 must not be adopted in a form that makes
that use silently fail open.

## 7. Non-authorization

No code, hook, CLI, schema, settings-default or documentation-claim change.
No `[layer1-freeze]` amendment, no D3/D6 design choice, no ADR-033 acceptance.
The result is recorded as a new validation record in its own evidence PR.
Interactive mode and other hosts or versions are out of scope.
