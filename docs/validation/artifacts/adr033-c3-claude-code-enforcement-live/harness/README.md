# ADR-033 C3 harness: live Claude Code enforcement validation

**Status: harness only. NOT RUN.** This directory holds evidence tooling for
the accepted C3 scope
([#592](../../../../plans/2026-10-21-reliable-enforcement-c3-live-validation-scope.md)).
It changes no Mneme runtime code. It does not seed, push to or change the
fixture repository, and it authorizes no live run: seeding the fixture (step
3a below) and each batch (step 3b) need the owner's explicit go-ahead.

> **Deleting the local declaration can silently disable opt-in fail-closed
> protection.** C3 does not test that limit as protection (scope §3).

## What C3 must show (scope §1)

1. **Non-mutation:** a refused edit does not reach the file (E1).
2. **Delivery:** the operational refusal reaches the model as a host error
   (E2) and, in the interactive arm, the user (Q2).
3. **Boundaries:** compliant edits land; REVOKED, VERIFIED_ABSENT and
   UNVERIFIABLE never refuse on availability; a trusted strict FAIL still
   blocks.

A hook exit code alone is never sufficient.

**Scope Amendment 1 (2026-10-22):** Claude Code 2.1.303 does not offer MultiEdit, so the
matrix schedules `Write` and `Edit` only. A tool missing from the host's init tool list is
labelled `NOT_OFFERED` (N/A, neither PASS nor FAIL).

**C2b charter §17.5 (F-R2 live proof, harness only; the run needs its own
authorization):** the F-R2 live proof (#616) ran with `mneme/` at `5a20b360`
(#608). That result stays pinned to `5a20b360`.

**Runtime pin history:**

| Pin | Change | Used by |
|---|---|---|
| `7d1a8bb7` | C2b (#591) | ABSENT batch, Batch R (#601) |
| `5a20b360` | F-R2 (#608), plus #607 | F-R2 live proof (#616) |
| `b0dc1a14` | #613 (ADR-034 F-1), current | Later C3 batches |

The impact of #613 on C3 is assessed in
[`2026-10-22-c3-runtime-repin-613-assessment.md`](../../../../plans/2026-10-22-c3-runtime-repin-613-assessment.md).
Moving the pin does not validate #613 live; each later batch records the pin
it ran with. See [F-R2 delivery](#f-r2-delivery-c2b-charter-175).

## Files

| File | Role |
|---|---|
| `pins.env` | Pinned versions, fixture URL, fixed live root. Operator paths go in the untracked `pins.local.env` |
| `preflight.sh` | Read-only check of every pin; refuses inside a Claude Code session |
| `matrix.py` | The scope §5 rows: phase, mutations, expected outcome, expected verifier result, E4 need |
| `seed_fixture.sh` | Prepares one fixture change (`activate`, `authorize`, `revoke`) on a local branch with the real CLI. **Never pushes** |
| `refresh_golden.sh` | One HTTPS clone of the fixture per phase; aborts unless the live baseline is in that phase |
| `setup_c3_probe.py` | Builds one probe repository from the golden clone and applies the row's operator mutations |
| `hookwrap_c3.py` | Observation wrapper around the unmodified hook: E3 (exit, stderr, stdout, envelope session and transcript path), verifier results and Git argv (E4 wrapper half), R-7/H-2 stalls |
| `run_c3_probe.sh` | One probe: hashes before/after (E1), `claude -p` stream-json (E2) plus the session transcript, classification. `--interactive` for Q2 |
| `run_c3_batch.sh` | All rows of a batch × tools × repetitions (default 2, E9). `FR2`: D-2 with its paired controls, then the R3 pair comparison |
| `classify_c3.py` | Labels each probe PASS, FAIL, EVIDENCE_INCOMPLETE, PROTOCOL_DEVIATION, RECORDED or NOT_OFFERED; checks F-R2 delivery on proceed rows; `--pair` compares a D-2 probe with a control |
| `collect_transcript.py` | Copies the session transcript: the interactive arm's (E2 stand-in) and, with `--headless`, the `claude -p` session's (F-R2 delivery) |
| `collect_redacted.py` | Copies evidence into the repo with paths, user and host name redacted; publishes session transcripts only as `*.selected.jsonl` (H1 rule; raw SHA-256 in the manifest); `--probes`/`--extra` select probes and batch summaries from a shared live root; fails on credential-shaped text |
| `safe_rmtree.py` | The only recursive delete, confined to the live root |
| `selftest/` | Offline self-test with a stub `claude` and a local `file://` remote. Not evidence |

## Procedure (operator, from an external Git Bash, never inside Claude Code)

### 0. Pins and preflight

Create `pins.local.env` next to `pins.env`:

```bash
MNEME_SRC_W='C:\path\to\clean\mneme\checkout'   # mneme/ must equal PIN_MNEME_BASE
MNEME_SRC_U='/c/path/to/clean/mneme/checkout'
PY='C:\path\to\python.exe'                        # no spaces; has mneme's dependencies
```

Then `bash preflight.sh` must print `OK`. If Claude Code has moved past
`PIN_CLAUDE_VERSION`, update the pin in a reviewed commit before running;
never run against an unpinned version.

### 1. Self-test (offline)

```bash
C3_ST_PY="$PY" C3_ST_MNEME_SRC="$MNEME_SRC_W" bash selftest/run_selftest.sh
```

It must end with `SELFTEST OK (not live evidence)`. It includes negative
controls: a host that ignores the hook must FAIL, and an agent that makes no
call must be a PROTOCOL_DEVIATION.

**What the self-test does and does not establish.**

- **Verifier path.** The self-test remote is a local `file://` bare
  repository. The hook wrapper calls `verify(root, allow_file=True)`. That is
  the shipped verifier code end to end: the same `origin` read, Git
  environment, revision selection, declaration and chain validation,
  activation check and routing. Two things differ. The scheme allowlist also
  admits `file`, and Git gets `-c protocol.file.allow=always`. So the
  self-test exercises the verifier's **logic** against real authorize and
  revoke commits. It does **not** exercise HTTPS transport, TLS,
  anonymous-read behavior or forge reachability. Only a live run against the
  fixture's HTTPS URL can establish a verified `AUTHORIZED` baseline through
  the production path. The shipped hook never passes `allow_file`
  (`tests/integrations/claude_code/test_availability_c2b.py::test_hook_never_passes_the_test_transport`).
- **Host path.** The stub `claude` runs the registered hook and applies the
  edit only on exit 0. It is not Claude Code. Its tool results prove nothing
  about delivery or non-mutation by a real host.
- **Delivery levels.** `outcome.json` reports three levels separately:
  `emitted` (the hook's own stderr and exit, E3), `model_delivered` (the
  host's `tool_result`, E2) and `user_visible` (the interactive arm, Q2). In
  the self-test, `model_delivered` is `stub_only` and `user_visible` is
  `not_tested`.

**Row coverage (24 rows).**

| Rows | Offline self-test | Live only |
|---|---|---|
| F-R2 (D-2 with P-1 and D-1 controls, batch `FR2`) | Delivered, host-output-only, tool_result-only, missing, no-transcript and injected-control cases; the FR2 batch with its pair comparisons and its gate (failed, incomplete, done, `--recheck`) | The real 2.1.303 transcript (whether the host records the attachment at all) |
| R-1..R-7, P-1..P-7, D-1..D-5, H-1 (20) | Exercised with the stub host and the `file://` remote; labels must match the matrix | Real host (E2, E7), HTTPS verifier path, E4 OS capture, E9 repetitions |
| U-1, U-2, U-3 (3) | Not exercised (needs a Git-only network block) | All evidence |
| H-2 (1) | Not exercised (host hook-timeout behavior cannot be stubbed meaningfully) | All evidence |
| Interactive arms R-1, P-2 | Not exercised | Q2 recording and operator attestation |

### 2. Fixture seeding (step 3a, owner go-ahead; a human merges each PR)

The fixture moves through three phases. Each change is prepared locally by
`seed_fixture.sh`, then pushed and merged through a PR by a human. The merge
is recorded as **human-attested**, never as independent review (ADR-033
§4.5).

| Order | Command | Baseline after merge | Batches run in this phase |
|---|---|---|---|
| 1 | `seed_fixture.sh activate` | ABSENT (protection active, no declaration) | `ABSENT` (P-6) |
| 2 | `seed_fixture.sh authorize` (interactive) | AUTHORIZED | `R`, `P`, `U`, `D`, `H`, interactive arms |
| 3 | `seed_fixture.sh revoke` (interactive) | REVOKED | `REVOKED` (P-5) |

P-6 needs a local declaration the baseline lacks. `setup_c3_probe.py` writes
it from the local memory, so P-6 can run in phase ABSENT before step 2.

Before each phase: `bash refresh_golden.sh <ABSENT|AUTHORIZED|REVOKED>`.

### 3. Batches (step 3b, owner go-ahead per batch)

```bash
bash run_c3_batch.sh ABSENT        # after `refresh_golden.sh ABSENT`
bash run_c3_batch.sh R             # after `refresh_golden.sh AUTHORIZED`
bash run_c3_batch.sh P
bash run_c3_batch.sh D
bash run_c3_batch.sh H
bash run_c3_batch.sh U             # with the Git-only block below
bash run_c3_batch.sh REVOKED       # after `refresh_golden.sh REVOKED`
```

**Batch U: blocking the forge for Git only** (scope Q3). `claude` itself needs
the network, so block only Git's HTTPS helper, as administrator, after
`refresh_golden.sh AUTHORIZED`:

```powershell
New-NetFirewallRule -DisplayName "C3 block git https" -Direction Outbound -Action Block `
  -Program "C:\Program Files\Git\mingw64\libexec\git-core\git-remote-https.exe"
```

The runner refuses U rows unless an anonymous `git ls-remote` of the fixture
now fails. Remove the rule afterwards:
`Remove-NetFirewallRule -DisplayName "C3 block git https"`.

**E4 OS capture** (scope Q3). For rows with `e4=True`, capture traffic during
the probe as administrator (`pktmon start --capture --pkt-size 0 -f c3.etl`,
then `pktmon stop` and `pktmon etl2pcap c3.etl`). Extract the TLS server names
(`tshark -r c3.pcapng -Y tls.handshake.extensions_server_name -T fields -e
tls.handshake.extensions_server_name | sort -u`) into the probe's
`out/netcap-sni.txt`, then re-run `classify_c3.py <out> <model-pin>`. Without
that file the row is EVIDENCE_INCOMPLETE. The capture file itself stays with
the operator; only the host-name list is published.

### 4. Interactive arm (scope Q2: R-1 and P-2 only)

```bash
bash run_c3_probe.sh R-1 Write 1 --interactive
bash run_c3_probe.sh P-2 Edit 1 --interactive
```

The runner prints the exact commands and prompt, waits while you run Claude
Code in a new terminal with screen recording on, then collects the session
transcript. Save the recording as `out/recording.<ext>` and write what Claude
Code showed you in `out/operator-attestation.txt`. The classifier requires
both. The recording is never published; its SHA-256 is.

### 5. Collection and evidence record

```bash
"$PY" -E -P collect_redacted.py "C:\dev\mneme-c3-live" ../<batch-dir> --mneme-src "$MNEME_SRC_W"
```

Then open one evidence-record PR per batch with the collected files, the batch
summary, the as-run harness head, and the merge record of each fixture PR
(E5: who merged, merge order; read with a credential the agent does not
hold).

## F-R2 delivery (C2b charter §17.5)

**Status: harness ready, NOT RUN.** The live run needs the owner's separate
authorization. It does not re-run R-1, resume Batch R or change the fixture.

**What counts.** On a headless proceed row whose verifier is UNVERIFIABLE (D-2,
and U-1/U-3 if they are run), `classify_c3.py` requires the §17.2 text in the
R1 entry of the session transcript. The text in any other model-bound entry,
such as a user turn or a `tool_result`, is recorded but never passes. The H1
rules apply (H1 record §7; #551, #561):

- **R1:** a transcript `hook_additional_context` attachment for `PreToolUse`,
  with the text in `attachment.content`, whose hook invocation emitted the
  object (`hook-log.jsonl` stdout). If the attachment names a `toolUseID`, it
  must be the probed call.
- **R2, R4:** a `hook_success` attachment (the hook's own stdout) or a
  `hook_system_message` attachment is host output, never delivery. So are
  stream-json `system` events, the hook's stdout and stderr, and debug logs.
- **R3:** the pair comparison leaves `thinking_tokens` out of the
  stream-json `system` subtypes, and still compares permission indicators.

The hook's stdout must also be exactly the one §17.2 object (`emitted`). A
missing transcript is `EVIDENCE_INCOMPLETE`. Text found only as host output is
a `FAIL` ("host output only"). `outcome.json` reports this under
`diagnostic` (`expected`, `emitted`, `model_delivered`, `host_output`,
`user_visible`, and every location of the text with its category), separate
from the refusal `delivery` levels. `user_visible` is always `not_tested`: a
headless run never shows user delivery.

**Controls.** Every other headless proceed row must show no diagnostic: empty
hook stdout and no `Mneme availability:` text in stream-json or the transcript.
The §17.5 pair is set in `matrix.FR2_ROWS`, all in phase AUTHORIZED:

| Row | Role | Verifier | Diagnostic |
|---|---|---|---|
| D-2 | `origin` removed, memory deleted, compliant edit | `UNVERIFIABLE:VERIFIER_CONFIG_MISSING` | delivered (R1) |
| P-1 | AUTHORIZED control: compliant edit | `AUTHORIZED` | absent |
| D-1 | ABSENT control: local declaration deleted (C2a no-declaration path) | not run | absent |

The VERIFIED_ABSENT proceed (P-6) needs the fixture in phase ABSENT. The
fixture stays AUTHORIZED, so P-6 is checked offline only (and by its own
`ABSENT` batch if the fixture is ever in that phase again).

**Run (only after authorization).** After `refresh_golden.sh AUTHORIZED`, with
E4 capture for D-2 (row `e4=True`):

```bash
bash run_c3_batch.sh FR2 2
```

Each probe line must be `PASS`, and each `PAIR D-2/<control> <tool> <rep>` line
`PAIR_OK` (written to `D-2-<tool>-<rep>/out/pair-<control>.json`). Only then does
the batch end `BATCH_DONE FR2`. Otherwise it ends, with exit 1, either:

- `BATCH_FAILED FR2`: any FAIL, deviation or pair mismatch;
- `BATCH_INCOMPLETE FR2`: only missing evidence.

D-2 is always incomplete at first, because its `netcap-sni.txt` is added after
the probe (E4 OS capture, above). Add it, then run
`bash run_c3_batch.sh FR2 2 --recheck`. This re-classifies the existing
evidence and re-applies the gate without running Claude Code again. Passing
establishes model-bound delivery on 2.1.303 headless only. It does not
establish user-visible delivery, and it does not fix F-R1: an unverifiable
baseline still lets the edit proceed.

## Evidence per row (scope §6)

| ID | Source here |
|---|---|
| E1 | `observer.txt` BEFORE/AFTER target hashes, taken by the runner outside the session |
| E2 | `events.jsonl` (headless) or `transcript-*.jsonl` (interactive): the `tool_use` and its `tool_result`, bound by `tool_use_id` |
| F-R2 | `transcript.jsonl` (headless session transcript, kept by the operator; published as `transcript.selected.jsonl`): the R1 `hook_additional_context` attachment; `pair-*.json` for the R3 comparison |
| E3 | `hook-log.jsonl` from `hookwrap_c3.py` |
| E4 | `hook-log.jsonl` verifier Git argv (wrapper half) and `netcap-sni.txt` (OS half) |
| E5 | Fixture PR merge records, added to the evidence record |
| E7 | `observer.txt`: Claude Code version, init model, Mneme head, Git, OS, hashes of every settings scope |
| E8 | P-1, P-3, P-4 in every phase that has them |
| E9 | `run_c3_batch.sh` refuses fewer than 2 repetitions |

## Claims ceiling

Unchanged from scope §7. Batch H is recorded only. Agent-driven attacks are
out of scope. Nothing here applies to other hosts, versions, Bash, Stop, CI
(C4) or private repositories.
