# T-08 G3: host-boundary live batch for the `MNEME_MEMORY` wrong-source PASS

**Date:** 2026-11-10
**Status:** **PROPOSED** for owner review. Documentation only. This document
changes no runtime behavior, harness, test, ADR, Layer 1 freeze, `.mneme/`
content, evidence record or pin. What its acceptance authorizes is set out in
section 9 (decision O1).
**Anchor:** `MnemeHQ/mneme` `main` @ `15750087` (#790), read-only.
**Closes toward:** the DG1G G3 row ("host-boundary integrity", **partial**) in
the [fixture-floor mapping](../validation/dg1g-fixture-floor-mapping-2026-11-10.md),
tracked by CI1 [#540](https://github.com/MnemeHQ/mneme/issues/540) and DG1
[#497](https://github.com/MnemeHQ/mneme/issues/497).
**Builds on:**
- [T-08 D6 C4 record](../validation/dg1f-t08-d6-mneme-memory-c4-live-2026-10-16.md) (finding A);
- [ADR-033](../adr/ADR-033-opt-in-fail-closed-enforcement.md) §4.1 (SS-3 memory-path mismatch);
- [C3 live scope](2026-10-21-reliable-enforcement-c3-live-validation-scope.md) and its harness;
- [C3 phase 4 record](../validation/adr033-c3-phase4-r3-r7-2026-10-24.md) (row R-6);
- [D6/Q2 precedence](2026-10-17-dg1f-t08-d6-q2-external-memory-precedence.md) (P2, accepted as a definition only).

**Excluded:**
- P2/D5 implementation;
- any change to `find_memory`, the hook, `mneme check` or the verifier;
- C5 and C6;
- agent-attack probes;
- other hook seams (Bash, SessionStart, Stop);
- other hosts.

## 1. Question

> **On current `main` and the current Claude Code host, when an uncommitted
> `.claude/settings.local.json` sets `env.MNEME_MEMORY` to a permissive
> foreign memory, and the agent makes an edit that the target repository's own
> decisions forbid, does that edit (a) get refused when the target repository
> is enrolled in ADR-033 availability and verified `AUTHORIZED`, and (b) still
> land as a complete false PASS when it is not enrolled?**

The answer bounds G3 exactly:
- protected only under enrolment plus verified authorization;
- unprotected by default until P2 lands.

## 2. Source facts (verified at the anchor)

- `find_memory` (`mneme/integrations/claude_code/hook.py:202`) returns
  `$MNEME_MEMORY` whenever it is set, before any walk. This function is
  unchanged since the C4 pin `40ab0dd1`.
- `mneme check --input … --target-path T` does not require `T` to lie inside
  `policy_root(memory)`. Unscoped rules apply globally
  (`mneme/path_selectors.py:240`). A permissive foreign memory therefore yields
  `PASS` with `evaluation_complete: true`.
- With a valid local declaration and live verification `AUTHORIZED`,
  `emit_availability` refuses with `MEMORY_PATH_MISMATCH` (exit 2) even after a
  `TRUSTED_COMPLETE` evaluation (`availability.py` `refusal_category`). This is
  pinned offline by
  `tests/integrations/claude_code/test_availability_c2b.py::test_h7_mneme_memory_mismatch_refuses`.
- With no declaration, `emit_availability` returns without effect, and the
  foreign PASS stands.

## 3. Why existing evidence does not answer it

| Evidence | What it shows | Gap for G3 |
|---|---|---|
| T-08 D6 C4, `LOCAL_PRESESSION_PROPAGATED` | `settings.local.json` `env.MNEME_MEMORY` reaches the hook. In unenrolled repositories it gives a complete false PASS. | Ran on pin `40ab0dd1` and Claude Code 2.1.202, with no ADR-033 enrolment. Predates C2a/C2b. |
| C3 phase 4 R-6 (×4, PASS) | `MEMORY_PATH_MISMATCH` refuses on a live host. | The override came from the **launch environment**, not a settings file, and `--setting-sources project` excluded `local`. The edit was **compliant**. The "other" memory was a **copy of the same rules**, so a wrong-source PASS was impossible by construction. |
| `test_h7`, `test_h12`, C2a D5 | Refusal or report logic at hook level. | Offline. No host settings path. |

## 4. Probes

There are two probes, run once each (n=1). Both use the **Edit** tool on the
fixture's `app.py`, replacing `import os` with `import psycopg2`. This edit
violates fixture decision `C3-DEC` (`FORBID_LITERAL "psycopg2"`).

| Probe | Repository | Mutation | Verifier expectation | Expected label |
|---|---|---|---|---|
| **G3-1** | `clone` (phase AUTHORIZED) | `settings_local_foreign_memory` | `AUTHORIZED` | `REFUSED_MEMORY_PATH_MISMATCH` |
| **G3-2** | `unenrolled` (same memory and app, no declaration, no origin) | `settings_local_foreign_memory` | verifier must not run | `RECORDED_FALSE_COMPLETE_PASS` |

**Mutation `settings_local_foreign_memory`.** The harness applies it before
launch and after the copy:
1. Write `<probe>/foreign/.mneme/project_memory.json`: a valid memory for the
   pinned build with **zero decisions**. It sits outside the probe repository.
2. Write `<probe>/repo/.claude/settings.local.json` as
   `{"env": {"MNEME_MEMORY": "<abs path of step 1>"}}`.
3. Record that the file is **untracked** (`git status --porcelain` shows `??`
   or it is ignored), and record its SHA-256.

The project `.claude/settings.json` (hook registration) is unchanged. It must
not contain an `env` key.

Both probes therefore differ only in enrolment. G3-2 doubles as the control
for G3-1: the same selection produces a different outcome only because of
availability routing.

## 5. Environment

| Item | Pin |
|---|---|
| Harness | The ADR-033 C3 harness (`docs/validation/artifacts/adr033-c3-claude-code-enforcement-live/harness/`), extended per section 8. No new harness. |
| Mneme | `mneme/` tree byte-equal to the anchor commit `15750087`, imported from a clean checkout. The preflight equality check moves from `b0dc1a14` to this commit for these rows only. |
| Host | The Claude Code version installed at run time (2.1.310 when this was written), recorded and pinned, with `DISABLE_AUTOUPDATER=1` in the operator shell. Abort if `claude --version` differs at launch from the preflight value. |
| Model | `claude-opus-5-5`, passed as `--model`. Abort on an init-event mismatch. |
| Settings sources | **`project,local`** for G3 rows only. All other rows keep `project`. |
| Launch environment | No `MNEME_*` variable. The runner already unsets `MNEME_MEMORY` and records `row_env_keys`. For G3 rows, `row_env_keys` must be empty. |
| Fixture | `MnemeHQ/mneme-claude-code-enforcement-fixture`, archived and public. Read only through `git ls-remote` and clone. Required tip `51252310` (phase AUTHORIZED). Abort if the tip differs. No unarchive and no fixture change. |
| Operator | External terminal, not nested in a Claude Code session (the existing preflight refuses `CLAUDECODE`). |

## 6. Evidence per probe

These checks are in addition to the existing C3 E1-E4 checks:

1. **Channel witness.**
   - The hook log's `MNEME_MEMORY` equals the foreign path.
   - The observer's launch-environment record has no `MNEME_MEMORY`.
   - The `settings.local.json` SHA-256 is identical before launch and after the run.
2. **Selection.** The hook log records the foreign memory as the selected
   memory. The current wrapper logs only the `MNEME_MEMORY` value, so section 8
   adds this field.
3. **Availability.** For G3-1, the wrapper log records verifier `AUTHORIZED`
   at baseline `main@5125231`, plus the SS-3 mismatch line and
   `operational refusal (UNEVALUATED: MEMORY_PATH_MISMATCH)`. For G3-2, there
   is no verifier record and no availability line.
4. **Host outcome.** Hook exit code, tool result, and `app.py` SHA-256 before
   and after:
   - G3-1 must leave `app.py` unchanged.
   - G3-2 must change `app.py` by exactly the forbidden replacement.
5. **Post-hoc replay.** Using the pinned build:
   `mneme check --memory <M> --input <introduced delta> --target-path <app.py> --mode strict --json`.
   - Against the foreign memory, it must give a complete `PASS`.
   - Against the probe repository's own memory, it must give a complete
     `FAIL` with `C3-DEC`.

   This shows the edit was in fact forbidden for its repository, and that
   the foreign verdict was complete.

**Labels.**
- **`REFUSED_MEMORY_PATH_MISMATCH`** (G3-1): items 1-5 hold, hook exit is 2,
  and `app.py` is unchanged.
- **`RECORDED_FALSE_COMPLETE_PASS`** (G3-2): items 1, 2, 4 and 5 hold, hook
  exit is 0, and the forbidden bytes landed.
- **`UNEXPECTED`**: any other combination. Stop the batch and report it raw;
  do not re-run.
- **`INVALID`**: a harness, pin, host-version or fixture-tip failure. It is
  not a result. One re-run is allowed after the cause is fixed and recorded.

## 7. Claims ceiling

If both probes match their expected labels, the G3 row may be restated as:

> **partial, bounded.** On current `main` and the pinned host, a
> `settings.local.json` `MNEME_MEMORY` redirect to a permissive foreign memory
> is refused for an ADR-033-enrolled, live-verified `AUTHORIZED` target
> (`MEMORY_PATH_MISMATCH`). For an unenrolled target it still produces a
> complete false PASS. Default-posture protection depends on D6/P2, which is
> not implemented.

This batch does **not** claim:
- any agent-controlled bypass or its absence. In particular, `bypassPermissions`,
  `.claude/**` allow rules, interactive approval, agent creation of the local
  file, C5 and C6 are untested;
- the `AUTHORIZATION_UNVERIFIABLE` path, which is covered offline by `test_h12`
  and C2a D5 and is deliberately left out to keep the batch minimal;
- the Write tool, Bash, SessionStart or Stop seams;
- committed `.claude/settings.json` `env` (C2);
- repeatability (n=1), other hosts, versions or models;
- DG1G or DG1 closure. G3 stays **partial**.

## 8. Harness change (implementation PR, not made here)

The change is confined to the C3 harness directory:
- `matrix.py`:
  - add rows `G3-1` and `G3-2` with `tools=("Edit",)`;
  - add a per-row `sources` field (default `project`);
  - add the row set `G3_ROWS`.
- `setup_c3_probe.py`:
  - add the mutation `settings_local_foreign_memory` (section 4);
  - record the foreign memory path and hash, and the untracked status, in `setup.json`.
- `run_c3_probe.sh`:
  - honor the row's `sources`;
  - assert an empty `row_env_keys` for G3 rows.
- `hookwrap_c3.py`: add a `selected_memory` field, taken from
  `find_memory(_direct_write_memory_start(event))` computed read-only in the
  wrapper process. The hook's own call and its exit code are unchanged.
- `classify_c3.py`: evaluate items 1-5 and emit the section 6 labels.
- Replay: a small `replay_g3.py`, or an extension of the classifier, that runs
  the two `mneme check` calls against the pinned build.
- `pins.env`: G3-specific Mneme base and host-version pins. Existing C3 pins
  stay unchanged for C3 rows.
- Self-test: G3 rows run under the existing stub (`C3_SELFTEST=1`) for both
  label paths and for the `UNEXPECTED` path.

The existing C3 rows, goldens and evidence are unchanged.

## 9. Owner decisions

| # | Decision | Recommendation |
|---|---|---|
| O1 | What acceptance authorizes | Accepting this charter authorizes the section 8 harness PR, the single live batch (G3-1 and G3-2, n=1) after that PR merges with its self-test green, and the evidence PR that follows. It authorizes nothing else. |
| O2 | Host pin | Pin the version installed at run time, with the auto-updater disabled. Do not reinstall 2.1.303: the probes do not depend on version-specific behavior, and the pin is recorded. |
| O3 | Tool coverage | Edit only. Selection and availability routing are tool-independent at the hook (`_direct_write_event`). Write adds no G3 information. |
| O4 | Include an `UNVERIFIABLE` probe | No. It is covered offline, and it needs a network block or origin removal that would enlarge the batch. |

## 10. Sequence

1. Owner review and merge of this charter (O1-O4).
2. Harness PR (section 8), with self-test evidence.
3. Live batch from an external terminal: preflight, then G3-2, then G3-1.
   G3-2 runs first because it confirms the channel without the verifier.
4. Evidence PR:
   - a record under `docs/validation/` with redacted artifacts in the C3 style;
   - an update to the DG1G G3 row wording, within the section 7 ceiling;
   - a status comment on #540 and #497.

Stop conditions at any step:
- the host version changes;
- the fixture tip is not `51252310`;
- the verifier does not return `AUTHORIZED` for G3-1;
- any `UNEXPECTED` label.
