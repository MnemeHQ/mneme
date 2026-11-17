# DG1F T-08 D5 + P2: H1 gate record, Claude Code (2026-11-16)

> **H1 gate: PASS** (PROPOSED for independent review). Every H1 path has an accepted passing label, all recorded on **one host version**, `2.1.310 (Claude Code)`, with model `claude-opus-5-5`. **Nothing is classified or re-run here.** The record combines accepted outcomes only.
>
> The gate rule is in the [probe scope §6](../plans/2026-10-17-dg1f-t08-d5-p2-host-path-probe-scope.md), from the charter: H*n* passes only when **every** path under it is `DELIVERED_TO_AGENT`, `DELIVERED_TO_USER_ONLY` or `EVIDENCE_REUSED`. Under charter §5 (A2-1), one gate's paths share one pin.

## 1. Inputs (accepted records only)

| Path | Shape | Accepted label | Rules | Host version | Source record | Outcome file (SHA-256) |
|---|---|---|---|---|---|---|
| H1a-edit | PreToolUse (Edit) `hookSpecificOutput.additionalContext` | `DELIVERED_TO_AGENT` | R1–R5 | `2.1.310` | A2 live run #795, reclassified #800 | `live-a2-2026-11-11/H1a-edit/outcome.r1r5.json` (`5e7e8f84…`) |
| H1a-bash | PreToolUse (Bash) `hookSpecificOutput.additionalContext` | `DELIVERED_TO_AGENT` | R1–R5 | `2.1.310` | #795, #800 | `live-a2-2026-11-11/H1a-bash/outcome.r1r5.json` (`9b3caad9…`) |
| H1b-start | SessionStart `hookSpecificOutput.additionalContext` | `DELIVERED_TO_AGENT` | R1–R5 | `2.1.310` | #795, #800 | `live-a2-2026-11-11/H1b-start/outcome.r1r5.json` (`5b303f4a…`) |
| H1c | Stop, top-level `systemMessage` (Amendment A1, re-pinned by A3) | `DELIVERED_TO_USER_ONLY` | R1–R6 (A1) | `2.1.310` | A3 live run #804, reclassified #807 | `live-a3-2026-11-16/outcome_a1.r1r6.json` (`d26d80be…`) |

**Notes on the inputs:**
- **H1c's passing label** is the combined A1 outcome: headless `NOT_DELIVERED` (no interference, R6) and interactive `DELIVERED_TO_USER_ONLY`. A `DELIVERED_TO_USER_ONLY` label passes any path under D5 §5.1 (developer **or** agent).
- **The owner accepted the A3 interactive screenshot evidence** for this run on 2026-11-16 (#804 record §8.3). That run deviated from A1 §4.2's continuous-recording requirement, and the deviation is recorded there.
- **Different rule sets (R1–R5 for A2, R1–R6 for A3) do not matter here.** R6 can only act on a Stop path's `informational` echo, and #806's no-effect replays show it never fires on the A2 evidence, whose labels are unchanged.
- **The 2.1.202 H1 evidence** (#549/#553, and A1 headless #563) is history and is **not** combined here. Charter §5 keeps one gate on one pin.

## 2. Computation

[`harness/h1_gate.py`](artifacts/dg1f-t08-d5-p2-h1-host-path/harness/h1_gate.py) reads the four published outcome files above and applies the gate rule. It fails closed: a missing file, a missing label or host version, any other label, mixed versions, or a missing path gives `NOT MET`. Its 9 tests (`selftest/test_h1_gate.py`) cover:
- a passing set;
- every non-passing label;
- a missing outcome;
- mixed and unrecorded host versions;
- the real published files.

Its output is [`h1-gate-2026-11-16.json`](artifacts/dg1f-t08-d5-p2-h1-host-path/h1-gate-2026-11-16.json): `result: PASS`, `host_version: 2.1.310 (Claude Code)`, no problems.

## 3. What H1 passing establishes, and what it does not

**It establishes**, for Claude Code `2.1.310` with `claude-opus-5-5`, headless (plus interactive for H1c), n = 1 per path:
- the accepted candidate output shapes reach their intended audience, without demonstrated host interference:
  - **H1a and H1b:** the agent (`additionalContext` on PreToolUse Edit and Bash, and on SessionStart);
  - **H1c:** the developer (top-level `systemMessage` at Stop). The original Stop `additionalContext` shape is ruled out by its forced continuation (#549).

**It does not establish:**
- **The D5 + P2 freeze gate.** That needs **all of H1–H6** under the accepted scope. H2–H6 (Codex, Kiro, Antigravity, Agent SDK, Hermes) are not started.
- Any other Claude Code version or model, or repeatability.
- That Mneme emits these shapes. Nothing is implemented, and `_emit_stop_feedback` (#550) is unchanged.
- G3, DG1G or DG1 closure. All stay **open**.

## 4. Not authorized by this record

- H2–H6;
- a P2-first or charter amendment;
- the `[layer1-freeze]` amendment;
- implementation;
- any runtime change.
