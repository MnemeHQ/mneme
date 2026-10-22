# ADR-033 C3: ABSENT batch (P-6) evidence record, 2026-10-22

**Status:** evidence record for review. It records one live batch under the
accepted C3 scope ([#592](../plans/2026-10-21-reliable-enforcement-c3-live-validation-scope.md))
using the merged harness (#595, fix #596). It changes no runtime code and
authorizes nothing further: the AUTHORIZED and REVOKED phases, the interactive
arms and C4 each need their own go-ahead.

> **Deleting the local declaration can silently disable opt-in fail-closed
> protection.** This batch does not test that limit.

**What this batch establishes:** the **default-open control**. With a verified
`VERIFIED_ABSENT` baseline, compliant `Write` and `Edit` calls from a real
Claude Code host proceed, and the live verifier is consulted and does not
refuse. **It does not establish fail-closed enforcement.**

## 1. Pins and identities

| Item | Value |
|---|---|
| Fixture | `MnemeHQ/mneme-claude-code-enforcement-fixture` (public, ruleset 25553918 `main-pr-only`) |
| Fixture baseline | `main@2ddec27a72bde96fc110c0f87a3cf6b9243c5ac7`, phase ABSENT (protection active for `C3-DEC`, no availability declaration) |
| Fixture activation (E5) | Fixture PR #1, head `98084700`, squash-merged by `TheoV823` at 2026-10-21T22:17:21Z as `2ddec27a`. Human-attested, **not independent review**: author and merger are one identity, and the record was read with the owner's credential (`E5-01-activation.json`) |
| Mneme harness | `MnemeHQ/mneme@49e2c19a` (harness #595 plus stdin fix #596) |
| Mneme runtime imported by the hook | `C:\dev\mneme`, `mneme/` identical to C2b `7d1a8bb7` (preflight) |
| Claude Code | 2.1.303, headless `-p`, `--permission-mode acceptEdits`, `--setting-sources project` |
| Model | `claude-opus-5-5` (passed as `--model`; every init event matched) |
| Host | Windows 11 (10.0.26300), Git 2.47.1.windows.2, Python 3.12.10 |
| E4 OS capture | `pktmon` (TCP 443, full packets) per probe, `tshark` 4.6.9 for TLS server names, elevated operator PowerShell outside Claude Code |
| Run window | 2026-10-22T09:21:04Z to 09:23:18Z |

## 2. Results

Row P-6 (scope §5.2): local declaration present (an unmerged enrollment, built
from local memory), canonical memory deleted, compliant edit. Expected:
**proceed**, verifier `VERIFIED_ABSENT`.

| Probe | Label | E1 target | E2 host result | E3 hook | Verifier (wrapper) | E4 wrapper | E4 OS capture | E7 model |
|---|---|---|---|---|---|---|---|---|
| P-6 Write 1 | **PASS** | changed | `is_error: false` | exit 0 | `VERIFIED_ABSENT` @ `2ddec27a`, 1.94 s | fixture URL only | `github.com` | ok |
| P-6 Write 2 | **PASS** | changed | `is_error: false` | exit 0 | `VERIFIED_ABSENT` @ `2ddec27a`, 1.93 s | fixture URL only | `github.com` | ok |
| P-6 Edit 1 | **PASS** | changed | `is_error: false` | exit 0 | `VERIFIED_ABSENT` @ `2ddec27a`, 2.12 s | fixture URL only | `github.com` | ok |
| P-6 Edit 2 | **PASS** | changed | `is_error: false` | exit 0 | `VERIFIED_ABSENT` @ `2ddec27a`, 2.25 s | fixture URL only | `github.com` | ok |
| P-6 MultiEdit 1 | **PROTOCOL_DEVIATION** | unchanged | no call | no record | none | n/a | no fixture host | ok |
| P-6 MultiEdit 2 | **PROTOCOL_DEVIATION** | unchanged | no call | no record | none | n/a | `api.github.com` (unrelated; no verifier ran) | ok |

The probe runner first labelled the four passing probes EVIDENCE_INCOMPLETE,
because the OS capture is added after the probe. The operator script then
wrote `netcap-sni.txt` and re-ran the classifier, which gave PASS. Without a
capture, the rows stay EVIDENCE_INCOMPLETE.

Delivery levels do not apply: P-6 is a proceed row, with nothing to deliver.

## 3. Findings needing review

- **F1. MultiEdit is not offered by the pinned host.** Claude Code 2.1.303's
  init tool list has `Edit`, `Write` and `NotebookEdit`, and no `MultiEdit`.
  In both MultiEdit probes the model reported that the tool does not exist and,
  as instructed, did not work around it. The classifier's PROTOCOL_DEVIATION
  is correct. **Consequence:** every MultiEdit cell in the C3 matrix (R, P
  and D rows) cannot be executed on this host version. The hook matcher
  `Edit|Write|MultiEdit` is unaffected. Changing the matrix (drop MultiEdit
  for this pin, or record it as not offered) is an owner decision. This record
  does not make it.
- **F2. No Anthropic API host in any TCP-443 capture.** Claude Code completed
  model calls in every probe, but no `anthropic.com` or `claude.ai` server name
  appears. This is **unexplained**. A plausible cause is QUIC (UDP 443), which
  the TCP filter excludes. It does not affect E4's purpose: the verifier's Git
  traffic is TCP HTTPS, and its server name (`github.com`) was captured in
  every probe that ran the verifier.
- **F3. Unrelated host noise.** The captures also contained unrelated OS and
  application hosts (from 0 to 9 per probe). Only GitHub, Anthropic and Claude
  host names are published, with a count of the others. The full lists and raw
  captures stay with the operator. None contained a forbidden host.

## 4. Non-evidence (preserved separately)

Two earlier attempts on 2026-10-21 (harness `91abddb5`) are **not evidence**:
attempt 1 hung on console stdin, and in attempt 2 the batch runner's stdin
leaked into `claude -p`, so rows were skipped and one probe was contaminated.
Fixed by #596. Both are kept only by the operator, under
`_non-evidence/` with a README. They are not collected, classified or cited
here.

## 5. Claims ceiling

This record claims, for Claude Code 2.1.303 on Windows 11 with the pins above:
with a `VERIFIED_ABSENT` baseline and canonical memory missing, compliant
`Write` and `Edit` calls proceed. The live HTTPS verifier is consulted and
reports `VERIFIED_ABSENT` at the fixture tip, and contacts only the fixture
URL. That is the default-open control.

It claims nothing about: fail-closed refusal (AUTHORIZED phase), REVOKED,
verification failure, MultiEdit (F1), user-visible delivery, other hosts or
versions, Bash, Stop or CI.

## 6. Evidence files

Under [`artifacts/adr033-c3-claude-code-enforcement-live/absent-2026-10-22/`](artifacts/adr033-c3-claude-code-enforcement-live/absent-2026-10-22/):
one folder per probe (`observer.txt`, `prompt.txt`, `setup.json`,
`hook-registration.json`, `events.jsonl`, `hook-log.jsonl`, `outcome.json`,
`target.before`/`target.after` where present, `netcap-sni.txt`),
`MANIFEST.json` (source and published SHA-256 of the 56 collected probe
files, and the collector hash), plus `batch-summary.txt` (the operator
script's summary) and `E5-01-activation.json`, which are copied as-is and are
not in the manifest. The collected files are byte-identical to the manifest
(0 mismatches at commit). Operator
paths and the user name are redacted (`<LIVE>`, `<HOME>`, `<MNEME_SRC>`,
`<USER>`). Screen recordings, packet captures and full host lists are not
published.
