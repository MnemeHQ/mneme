# C3 runtime re-pin to #613: impact assessment (2026-10-22)

**Status:** for review. This is a harness-only change. It moves the C3 harness
pin `PIN_MNEME_BASE` from `5a20b360` (#608, F-R2) to `b0dc1a14` (#613,
ADR-034 F-1). It changes:

- no runtime code;
- no historical evidence;
- no scenario definition (`matrix.py`);
- no fixture.

It authorizes no live run. The next C3 batch needs its own authorization.

**The F-R2 result stays pinned to `5a20b360`.** The F-R2 live proof (#616,
`635fb018`) ran with `mneme/` identical to `5a20b360`, recorded in every
probe's observer. Re-pinning does not extend that result to #613, and this
assessment does not validate #613 live.

## 1. Why re-pin

`main` moved past the pin. #613 (`b0dc1a14`) is the only commit since
`5a20b360` that touches `mneme/`. `mneme/` on `main` (`635fb018`) is identical
to `b0dc1a14`.

The preflight requires `mneme/` to equal the pin. Without a re-pin, every
later C3 run against `main` fails the preflight. That is correct behavior, and
it is why the F-R2 PR's offline self-test had to use a detached checkout at
`5a20b360`.

## 2. What #613 changes

The change has 8 hunks in three files:

| File | Change |
|---|---|
| `mneme/enforcer.py` | Adds `SourceSubject.target_path_declared`. In `check_prompt`, for an unverified input **without a target path**, each `FORBID_NUMERIC_ABOVE` rule that is not APPLIED gets the non-source matcher record (`MATCHER_UNEVALUATED` / `INCOMPLETE_SOURCE_INPUT`), so the result is never clean |
| `mneme/cli.py` | `--input` passes `target_path_declared = --target-path given`. The `subject` record carries `target_path_declared` for unverified input |
| `mneme/integrations/claude_code/hook.py` | Two hunks, both in the shared numeric-trace validator: `matcher_incomplete_records`, `_numeric_trace_problem` and `_numeric_record_problem`. Under the same condition, every numeric trace must carry exactly the non-source record |

**Unchanged by #613**, per its own description and its tests:
- `--input` **with** `--target-path`;
- `--source-file`;
- `FORBID_LITERAL`;
- payloads and exit codes for checks with no numeric rule (the 18-scenario
  byte-identity golden).

## 3. Impact on C3

| C3 element | Path through #613 | Impact |
|---|---|---|
| Fixture memory | One decision `C3-DEC` with one `FORBID_LITERAL` rule (`psycopg2`). No numeric rule | Every numeric branch added by #613 is unreachable. Checks with no numeric rule are byte-identical (#613 golden) |
| Direct-write hook check | `_invoke_check` runs `mneme check --input <temp> ... --json` and adds `--target-path` whenever the event resolves a target. Every C3 probe is a Write or Edit with an absolute `file_path` | Always the with-target case, which #613 leaves unchanged |
| Payload validator (`hook.py`) | `_numeric_record_problem` returns early when the payload has no numeric trace | Not exercised by C3 payloads |
| Availability (C2a/C2b, F-R2 §17) | `availability.py` and `availability_authority.py` are unchanged between the pins. #613's hook hunks do not touch `handle_event`, `emit_availability` or `write_proceed_context` | None. Refusal categories, the verifier, routing and the §17.2 diagnostic are unchanged |
| Bash and Stop handlers | Outside the C3 scope | Not assessed |
| Scenario rows, expectations, classifier, collector | Not modified by this PR | None |

**Expected effect on C3 outcomes: none.** Every C3 row should produce the same
hook exit, stderr, stdout and payload as at `5a20b360`. This is established
offline (section 4) and by reading the code. It is not established live; the
next authorized batch records it.

## 4. Deterministic checks (this PR)

Both checks ran against `mneme/` at `b0dc1a14`:

1. **C3 offline self-test:** `selftest/run_selftest.sh`, with
   `C3_ST_MNEME_SRC` set to the administrative checkout at `main@635fb018`. Its
   `mneme/` equals the new pin, so the preflight passes.
   - **Result:** `SELFTEST OK (not live evidence)`, 51 ok, 0 FAIL.
   - This covers every offline row, including the D-2 F-R2 delivery cases and
     the FR2 batch gate. It uses a stub host, so it is not live evidence.
2. **Runtime regression tests** (CPython 3.12.10, Windows 11):
   - `tests/integrations/claude_code` (C2a, C2b, C2b Amendment 1) plus
     `tests/test_numeric_upper_bound_g1.py` (ADR-034, including #613's F-1
     section): **855 passed, 3 skipped**;
   - full suite: **3896 passed, 10 skipped**.

## 5. Not changed, not claimed

- Historical evidence (#601, #616, the ABSENT batch) is untouched. Each record
  keeps the pin it ran with: `7d1a8bb7` for ABSENT and Batch R, `5a20b360` for
  F-R2.
- No claim is made about #613 under a live host.
- Batch R stays stopped. No live run is authorized by this change.
- F-R1 is unchanged.
