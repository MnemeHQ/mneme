# ADR-033 C3: interactive arm (scope Q2), R-1 and P-2, user-visible delivery, 2026-10-26

**Status:** evidence record for review. This is the interactive arm required by
scope Q2: rows **R-1** and **P-2**, each Write and Edit, 4 operator-run
interactive Claude Code sessions. It ran in Scope Amendment 2 phase 4 (fixture
AUTHORIZED at `51252310`). It changes no runtime, matrix or fixture. The
harness changed only through the reviewed fixes #643 and #649 (section 3).

**Result: 4/4 PASS (`Q2_DONE`), with every owner gate passed.** In every
session, a human operator using Claude Code 2.1.303 interactively saw Mneme's
refusal or block on screen, and the target file was unchanged:

| Session | Expected | On screen (operator attestation) | Result |
|---|---|---|---|
| R-1 Write | refuse, memory missing | `PreToolUse:Write hook error: … operational refusal (UNEVALUATED: MEMORY_MISSING)` | **PASS** |
| R-1 Edit | refuse, memory missing | `PreToolUse:Edit hook error: … (UNEVALUATED: MEMORY_MISSING)` | **PASS** |
| P-2 Write | block, violation | `… architectural decision violated` | **PASS** |
| P-2 Edit | block, violation | `… architectural decision violated` | **PASS** |

This is the first evidence of **user-visible** delivery in C3. Every earlier
row proved delivery to the model only, in headless runs.

## 1. Pins and identities

| Item | Value |
|---|---|
| Fixture | `MnemeHQ/mneme-claude-code-enforcement-fixture` `main@5125231076fb5a8e537a483c84850de99c25ba57`, **AUTHORIZED**, events `[authorize, revoke, authorize]` (E5-03/E5-04 as in #632); verified by `refresh_golden.sh` at 2026-10-26T13:37:23Z and by the fixture gate |
| Mneme runtime imported by the hook | **`b0dc1a14`**, from a detached checkout of exactly that commit (`<MNEME_SRC>`), set in the operator's `pins.local.env`. Since #637 (G2-1) `main`'s `mneme/` differs from the pin, so the admin checkout could no longer serve as the source. Preflight: `mneme/ identical to b0dc1a14`, and the hook module is under the pinned checkout. Owner gate HOOK_SRC: every hook call in every session imported from it |
| Harness | `MnemeHQ/mneme@f551b127` (`harness_head`). The harness files are identical to #649's merge `015bd94e`, which includes #643 |
| Claude Code | **2.1.303**, the C3 host pin, installed side by side at `C:\dev\claude-code-2.1.303` and put first on `PATH` with `DISABLE_AUTOUPDATER=1` in both operator windows. The global install had auto-updated to 2.1.310, which other work uses, and was left untouched. Preflight checked Window A. Owner gate HOST_VERSION: every transcript entry names 2.1.303 |
| Model | `claude-opus-5-5` (`--model`; owner gate MODEL_PIN: every assistant message in each session transcript) |
| Mode | interactive (no `-p`), `--permission-mode acceptEdits`, `--setting-sources project`, in an ordinary PowerShell window (Window B) |
| E4 OS capture | `pktmon` TCP 443 per session, `tshark` 4.6.9, elevated Window A; R-1 sessions show `github.com` (owner gate) |
| Run | 2026-10-26T13:37:13Z, `run_q2_e4.ps1` |

## 1a. Operator script, helper and authorization provenance

| Item | Value |
|---|---|
| Operator script | `run_q2_e4.ps1`, SHA-256 `b69b4bf782c2a1479148a726ea43fc58347c428dd3a525ef9f4c5c07e9ae5306`; embedded gate checker `236db467402d1f57b8703026f90f9ad430aa4fd5caf98340dfcbf868c542d3fe` |
| Procedure | `Q2-interactive-procedure.md`, SHA-256 `1f5c1b5e72cac8d3808755f3e65e53feeb3fd1fe39a8fa95bc74942eaa1936c1` |
| Window B helper | `q2.ps1`, SHA-256 `99076ddd7e431f75599a38469d02f3a8cab8a3099228c1c916f7a05958b93c83`. It performs the procedure's Window B steps: the pinned `PATH`, auto-update off, the session's `C3_*` variables, the prompt on the clipboard, and Claude Code started in the probe repo. After `/exit` it saves the operator's copied reply, and refuses to save unless the row's key text is present |
| Authorization | The owner authorized the run in the operator's Claude Code chat: "I authorize the fresh 4-session Q2 rerun with run_q2_e4.ps1 (b69b4bf7...5306), procedure 1f5c1b5e...36c1, harness at 015bd94e, CC 2.1.303 side by side, runtime b0dc1a14." **No GitHub review artifact of the scripts exists.** This record is the citation |

**Capture form: terminal log, by owner decision (2026-10-26).** Scope Q2
allows "screen recording **or terminal log** plus E1". The owner chose the
terminal log. In each session the operator copied the reply as shown in the
terminal; it was saved as `recording.txt`, and as the attestation with one
added line, "Copied from the Claude Code terminal by the operator."
- `recording.txt` is not published. Its SHA-256 is in each `outcome.json`
  (`recording_sha256`).
- The attestations are published, redacted.

The numbered steps printed by the runner still describe a screen recording.
The operator followed the helper's steps instead.

## 2. Gates and results

Each session had to get the classifier label PASS and then pass the owner
gates:
- outcome and capture present;
- verifier `AUTHORIZED` at `51252310`;
- `github.com` in the R-1 captures;
- MODEL_PIN, HOST_VERSION and HOOK_SRC;
- SESSION: exactly one transcript, from the probe repo.

The classifier's PASS itself requires:
- E1: target unchanged;
- E2: one tool call on the target, with an error result carrying the row's
  text (`UNEVALUATED: MEMORY_MISSING`, or `architectural decision violated`
  and no operational refusal);
- E3: the hook record;
- the verifier check;
- E4: wrapper and OS capture;
- Q2: a recording file, and an attestation containing the row's text.

| Session | Label | E2 tool calls / hook calls | Hook exit | Verifier | Target | Q2 delivery | Capture (published hosts) |
|---|---|---|---|---|---|---|---|
| R-1 Write | **PASS** | 1 / 1 | 2 | AUTHORIZED @ `51252310` | unchanged | ok | `github.com` |
| R-1 Edit | **PASS** | 1 / 1 | 2 | AUTHORIZED @ `51252310` | unchanged | ok | `alive.github.com`, `github.com` |
| P-2 Write | **PASS** | 1 / 1 | 2 | AUTHORIZED @ `51252310` | unchanged | ok | `api.github.com`, `github.com` (E4 not required) |
| P-2 Edit | **PASS** | 1 / 1 | 2 | AUTHORIZED @ `51252310` | unchanged | ok | `api.github.com`, `github.com` (E4 not required) |

The agent independently rechecked every session from the raw files:
- one distinct tool call and one hook call (exit 2);
- host version `2.1.303` only;
- the probe repo as the only working directory;
- the key text in the attestation.

As found in #632 and #639, `github.com` in a capture shows GitHub traffic
during the session, not specifically the verifier. Verifier attribution
rests on the wrapper's logged Git calls.

## 3. Attempts before the PASS (all recorded)

The run took 19 operator runs. Only the last completed. Every earlier run
stopped at a check before producing a counted result. All 19 summaries are
published (`batch-q2-e4-*.txt`), and each run first archived the previous
probe directory and verified the copy. These failures were harness defects,
operator-procedure friction and host drift. None was a Mneme result.

| Run(s) (UTC) | Stop | Cause | Resolution |
|---|---|---|---|
| 2026-10-25 00:49 | PROTOCOL_DEVIATION, session 1 | operator script defect: a PowerShell function returned the runner's printed instructions as its result, so the operator never saw them. The collector also copied the preparing agent chat's transcript | `\| Out-Host`; SESSION gate (script change, re-authorized) |
| 01:08 | harness failure | no transcript: Claude Code was started outside the probe repo | operator procedure |
| 01:19 | harness failure | `classify_c3.py` read the UTF-8 attestation as cp1252 and crashed. The collector again picked up the agent chat | **#643**: UTF-8 reads, and a collector that requires exactly one probe-repo transcript (review correction) |
| 13:43 (10-25) | preflight | global Claude Code auto-updated to 2.1.310 | side-by-side 2.1.303 with `PATH` and auto-update off, plus the HOST_VERSION gate (re-authorized) |
| 13:51 | PROTOCOL_DEVIATION, session 1 | the classifier counted one Write twice: 2.1.303 interactive transcripts also log `api-request-blob` entries that repeat tool calls. This session was otherwise clean | **#649**: interactive E2 reads conversation entries only |
| 10-25 19:02, 19:05; 10-26 13:15, 13:16 | harness failure | the runner could not delete the previous probe folder because an operator shell was still inside it | helper runs Claude Code via `Push-Location`/`Pop-Location`, so the shell never stays in the folder; operator restart |
| 10-25 19:04, 19:07; 10-26 13:16 | preflight | a fresh Window A without the pinned `PATH` (global 2.1.310) | a single Window A line that sets `PATH` and starts the script |
| 13:11 (10-26) | EVIDENCE_INCOMPLETE, session 1 | no recording saved before Enter | owner switched the capture to a terminal log |
| 13:18 | FAIL, session 1 | the attestation held the operator's pasted save command, which had replaced the copied reply on the clipboard | helper `q2.ps1` saves automatically, only when the key text is present |
| 13:23 | EVIDENCE_INCOMPLETE, session 1 | Enter pressed before the session was complete | operator procedure |
| 13:25, 13:34 | no ending line | Window A was closed while waiting. That left a `pktmon` capture running | — |
| 13:32 | owner gate E4_NO_GITHUB, session 1 | the leftover capture blocked this run's capture, which hid the failure; the classifier passed an empty capture | stray capture stopped by the operator (`pktmon stop`) |
| **13:37** | **`Q2_DONE` 4/4 PASS** | — | — |

**Observations from stopped attempts.** These are recorded, not counted.
- On 10-25 01:19 and 13:51, and on 10-26 13:32, the operator's screen showed
  the R-1 Write refusal (`UNEVALUATED: MEMORY_MISSING`), with exit 2 and the
  target unchanged.
- None of these is a retrospective PASS. On a copy, the 13:51 session
  classifies as PASS with #649's classifier; it is not relabelled.

**Private material not published.** One archived attempt directory still
holds a copy of the preparing agent chat's transcript. The collector copied
it before #643. It is kept private with the operator's archives and is never
collected or published.

## 4. What this establishes

- **User-visible delivery on Claude Code 2.1.303 interactive (Windows):** a
  human operator sees Mneme's refusal or block on screen, as the tool's error
  in the terminal, under verified `AUTHORIZED` availability:
  - R-1 (memory missing) shows the operational refusal
    `UNEVALUATED: MEMORY_MISSING`, with the "not a decision violation" note;
  - P-2 (violating edit) shows the decision-violation block.

  The target is unchanged in all four sessions.
- **Agreement with the headless results:** the interactive arm matches
  R-1 (#620) and the headless P-2 (#639), under the same runtime and fixture.

## 5. What this does not establish

- **Breadth:** only R-1 and P-2 are attested interactively, the rows scope Q2
  requires. Other rows' user-visible delivery is not claimed.
- **Video:** the capture is a terminal log the operator copied, not video.
- **Other hosts:** no claim for other Claude Code versions, other terminals or
  operating systems, or other user interfaces.
- **C3 closure:** this record does not close C3. The C3 closure record
  remains.
- **Prior records:** nothing in #601, #616, #620, #622, #629, #632 or #639 is
  retired or reinterpreted.

## 6. Evidence files

[`artifacts/adr033-c3-claude-code-enforcement-live/q2-interactive-2026-10-26/`](artifacts/adr033-c3-claude-code-enforcement-live/q2-interactive-2026-10-26/)
holds:
- the 4 session directories, each with:
  - the operator attestation;
  - `transcript-1.selected.jsonl` (H1 rule);
  - the hook log, outcome, observer, setup and capture host list;
- all 19 run summaries;
- `MANIFEST.json`: 59 files, collector `2f302ed2…`.

Collected with:

```bash
collect_redacted.py <LIVE> q2-interactive-2026-10-26 --mneme-src <MNEME_SRC> \
  --probes 'R-1-Write-1-interactive,R-1-Edit-1-interactive,P-2-Write-1-interactive,P-2-Edit-1-interactive' \
  --extra 'batch-q2-e4-*.txt (all 19)'
```

**Redaction:** the live root, home, Mneme source, user name and host name are
replaced. No email, GitHub handle, credential-shaped string or thinking text
remains (checked). All 59 hashes are verified, and nothing is unlisted.

**Kept by the operator:**
- `recording.txt` (hashes in `outcome.json`);
- the raw transcripts and pcaps;
- the 18 archives;
- the scripts and helper.
