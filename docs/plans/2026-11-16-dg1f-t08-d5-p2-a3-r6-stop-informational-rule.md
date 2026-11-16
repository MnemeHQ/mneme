# DG1F T-08 D5 + P2: A3 evidence-classification rule review, R6 Stop `informational` echo (PROPOSED: rule only)

**Status:** **PROPOSED, for independent review.** Docs only. It does **not** reclassify anything. Acceptance would authorize none of the following:
- a classifier code change;
- a reclassification run;
- a re-run or live probe;
- the H1 gate record;
- a runtime change, freeze amendment, charter or implementation.

It follows the separate-step precedent (#551 → #552 → #553; R4: #561 → #562 → #563; R5: #796 → #798 → #800): rule, then implementation, then offline reclassification, each separately approved (§7).

**Depends on:** the A3 live evidence record (#804, PROPOSED at the time of writing, head `766b9570`). This note should not be reviewed for acceptance before #804 is accepted, because it reads that record's artifacts.

**Anchor:** `main` @ `c9480c11`, plus #804 @ `766b9570` for the evidence.

**Inputs:**
- the accepted probe scope (#545), §3, and its Amendments A1 (§4.2, #555) and A3 (§4.4, #802);
- the accepted rules R1–R3 ([#551](2026-10-17-dg1f-t08-d5-p2-h1-classifier-rules.md)), R4 ([#561](2026-10-19-dg1f-t08-d5-p2-a1-hook-system-message-rule.md)) and R5 ([#796](2026-11-11-dg1f-t08-d5-p2-a2-r5-host-record-rule.md)), as implemented in `classify_h1.py` and `classify_a1.py` at `c9480c11`;
- the A3 evidence record `docs/validation/dg1f-t08-d5-p2-host-path-h1c-a3-2026-11-16.md` (#804) and its artifacts `…/live-a3-2026-11-16/`. This note answers that record's next step 1.

## 1. Why a rule review

The A3 headless run (`H1c-sm` vs `H1c-sm-ctl`, Claude Code `2.1.310`) came out `INCONCLUSIVE` for one reason only:

> `unexplained host-event difference between arms (emitter ['informational'], control [])`

Every other criterion held: no host interference, one Stop invocation per arm, no `stop_hook_active` re-entry, equal permissions, equal indicators, normal end, workspace unchanged, and no model-bound nonce location. The combined H1c label is `INCONCLUSIVE` only because the headless label is.

The as-run classifier made the right call. A1 (§4.2) and A3 (§4.4) both predicted this collision and left it to a reviewed rule. The A1 category table already says the event's **nonce location** is `host_output`. What no rule covers is the strict **subtype comparison** in `host_events()`, which flags any `system` subtype (other than `init` and R3's `thinking_tokens`) present in one arm only, nonce or not.

Without a rule, every headless Stop `systemMessage` run on `2.1.310` is `INCONCLUSIVE` whatever happens, because the host surfaces the notice on the stream by design.

Adopting a rule changes how evidence is **read**, never what the host did.

## 2. What the evidence shows

**Published files** (#804) plus a **read-only check of the raw archive** `C:\dev\d5p2-h1c-a3-archive\2026-11-16`. The archive verified 56/56 against `2026-11-16.SHA256SUMS` (listing SHA-256 `17c73d1a…`) on 2026-11-16 before the check. The check is not a reclassification.

| Observation | Headless emitter `H1c-sm` | Headless control `H1c-sm-ctl` |
|---|---|---|
| Raw stream events | 5: `system:init`, `assistant` (thinking, omitted), `assistant` (text `OK NO-PROBE-TOKEN`), **`system:informational`**, `result:success` | 3: `system:init`, `assistant` (text), `result:success` |
| `system` events other than `init` | **Exactly one**, subtype `informational` | **None** |
| That event's keys (raw) | exactly `type`, `subtype`, `content`, `level`, `session_id`, `uuid` | – |
| That event's `level` | `notice` | – |
| That event's `content` | **equals exactly** `Stop says: ` + `S`, where `S` is the `systemMessage` string in the `emitted` JSON of the emitter's hook-log record | – |
| Hook log | **exactly one** record; `hook_event_name: Stop`, `stop_hook_active: false`, mode `stop-systemmessage` | exactly one record, mode `noop`, emitted nothing |
| Position | after the last `assistant` event, immediately before `result` | – |
| Indicator keys (`decision`, `blocked`, `retry`, `continue`, `stopReason`, …) in that event | **None** | – |
| Nonce elsewhere | transcript `hook_success` `stdout` (R2) and `hook_system_message` `content` (R4), both `host_output`. In no `api-request-blob`; not echoed | none |

**Interactive arms (for context, not covered by R6).** The interactive run is already labelled `DELIVERED_TO_USER_ONLY` (capture-reviewed). Its evidence is the UI capture and transcript, not stream events, so R6 does not touch it.

**What is not known.** No host documentation was consulted for the `informational` subtype beyond A1's note that it may be an `SDKInformationalMessage`. The `Stop says: ` prefix was observed for one event type (Stop), on one host version, n = 1. Whether other hook events use the same shape (for example `SessionStart says: …`) is not known and not covered.

## 3. Proposed rule

### R6: the host's stream echo of the probed Stop `systemMessage` is left out of the subtype comparison, narrowly

**Rule.** In `host_events()`, one stream-json event is left out of the strict subtype comparison between arms if, and only if, **all** of these hold:

1. **(S1) Shape.** `type` is `"system"`, `subtype` is `"informational"`, and `level` is `"notice"`.
2. **(S2) Path and arm.** The path's spec event is `Stop` (H1c), and the arm is the **emitter** arm. In a control arm R6 never applies, so any `informational` event there is still compared.
3. **(S3) Emitter attribution.** The arm's hook log has **exactly one** `Stop` record, with `stop_hook_active` false, whose `emitted` text parses as a JSON object with a string `systemMessage`, called `S`.
4. **(S4) Exact derivation.** `content` equals exactly `"Stop says: " + S`. No prefix match, no trimming, no case folding.
5. **(S5) Uniqueness.** Exactly one event in the arm meets S1–S4. If two or more do, none is excluded.
6. **(S6) Position.** The event comes after the arm's last `assistant` event and before the `result` event.

Otherwise the event stays in the comparison, and the existing rule applies unchanged: any one-sided subtype gives `INCONCLUSIVE`.

**Safeguard (as R3).** An excluded event is **still scanned for indicator fields**. If it ever carries `decision`, `permissionDecision`, `blocked`, `retry`, `continue`, `stopReason` or a similar field, the indicator comparison applies exactly as today, and a one-sided indicator still gives `INCONCLUSIVE`. R6 removes a subtype-count comparison, not a safety check.

**Unchanged.** The event's nonce location is still categorised `host_output` by the existing A1 table, and recorded in `nonce_locations`. It is never delivery. Unclassified-first still applies. R1–R5 are unchanged.

**What R6 does not do:**
- **No delivery claim.** The event is host output to the stream consumer. It adds no agent or developer delivery. Developer delivery for H1c still comes only from the interactive capture review.
- **No general exemption.** It does not exempt `informational` events in general, or any event not tied to the emitter's single Stop invocation by exact text.
- **No masking of interference.** A re-entered Stop (`stop_hook_active` true, or more than one Stop record) fails S3, so the event stays compared, and the Stop lifecycle control (`stop_invocations_equal`) is checked exactly as today.
- **No retroactive effect.** No earlier archive (H1 2026-10-17, A1 2026-10-19, A2 2026-11-11) has an `informational` event in any raw `events.jsonl` (read-only search, 2026-11-16), so their labels cannot change.

**For:**
- **Exact derivation from the emitter's own output.** The excluded event must be a fixed host wrapping (`Stop says: `) of the exact string the emitter logged. Any other text, or a format change in a later host version, falls back to the comparison and a review.
- **Predicted, not discovered after the fact.** A1 and A3 both named this collision before the run. R6 is the narrowest reading that resolves it.
- **Conservative error.** If the event did in fact signal a host flow decision, the indicator scan, the Stop lifecycle control and the interference checks would still catch it. R6 cannot turn a run with interference into a pass.

**Limits, stated for the record:**
- one host version (`2.1.310`), one model (`claude-opus-5-5`), n = 1, headless;
- one hook event (Stop); one `systemMessage` per invocation;
- the host's internal meaning of `informational` is unknown. R6 relies on the field content and its exact derivation, not on documentation.

## 4. Alternatives considered

| Option | Effect | Assessment |
|---|---|---|
| **A. R6 as proposed (narrow, Stop, emitter arm, exact derivation)** | The A3 headless pair can reach a label, if every other condition holds. | **Proposed.** Narrowest reading that removes the block. |
| B. Exclude every `informational` subtype, as R3 did for `thinking_tokens` | Same effect here. | **Not proposed.** `informational` events may carry host notices unrelated to the probe (for example a permission or policy notice). R3's basis was content that varies with model reasoning; that does not hold here. |
| C. A prefix match on `Stop says:` | Tolerates text variation. | **Not proposed.** It would accept emitter-controlled or unrelated text that starts with the label. |
| D. Exclude the event in both arms | Same effect here. | **Not proposed.** A control-arm `informational` event would be unexplained and must stay visible. |
| E. Drop the strict subtype comparison for Stop paths | Same effect here. | **Rejected.** Removes the safeguard that caught the event. |
| F. Re-run with a different collector or output format | Avoids a rule. | **Not proposed.** The host emits the event itself; a re-run on `2.1.310` would show it again. The archive is sufficient, subject to the completeness check (§7). |

## 5. What R6 would change, by reasoning only (not a reclassification)

This section projects the effect so the reviewer can judge the rule. **It is not a result.** Only an authorized offline reclassification establishes labels.

| Run | As classified | Under R1–R6 (projected) | Why |
|---|---|---|---|
| A3 headless (`H1c-sm`) | `INCONCLUSIVE` | likely `NOT_DELIVERED` | The only reason is removed. No model-bound location, no echo, transcript collected, controls hold, no interference. `NOT_DELIVERED` is the expected headless result for a notice meant for the developer only. |
| A3 interactive (`H1c-sm-int`) | `DELIVERED_TO_USER_ONLY` | unchanged | R6 does not touch the interactive classifier. |
| **A3 combined H1c (A1)** | `INCONCLUSIVE` | likely **`DELIVERED_TO_USER_ONLY`** (`h1c_passes_under_a1: true`) | `combine()`: one host version, neither run `INCONCLUSIVE`/`NOT_EXECUTED`, no interference, interactive `DELIVERED_TO_USER_ONLY`. That label is in `PASSING` and meets D5 §5.1. |
| H1 2026-10-17, A1 2026-10-19, A2 2026-11-11 | unchanged | unchanged | None has an `informational` event. |

## 6. Effect on the open gates

None directly. If the projection holds after an authorized reclassification, all three H1 paths would have passing labels on **one host version**, `2.1.310`:
- H1a-edit, H1a-bash and H1b-start: `DELIVERED_TO_AGENT` (A2 under R1–R5, #800);
- H1c: `DELIVERED_TO_USER_ONLY` (A3 under R1–R6, projected).

**H1 stays NOT MET** until a separate H1 gate record combines them. No mixed-version combination is needed (A2-1 does not arise). H2–H6, the `[layer1-freeze]` amendment, P2-first, G3, DG1G and DG1 are unaffected.

## 7. If accepted: the procedure (each step a separate go-ahead)

1. **Classifier change.** One harness PR:
   - `host_events()` takes the arm's hook records and the path spec, and leaves out at most one event meeting S1–S6. The indicator scan still covers it.
   - `RULES_ID` becomes `"as-run table + R1-R6 (#551, #561, #796, #<this PR>)"`. `classify_a1.py` inherits it through `A1_ID`.
   - The `classify_a1.py` "Known collision" docstring paragraph points to R6.

   **Regression tests** (`selftest/test_r6_classifier.py`):
   - positive: the A3 shape → excluded; subtypes compare equal;
   - S1: `level` other than `notice`, or another subtype → compared (`INCONCLUSIVE`);
   - S2: the same event in a **control** arm → compared (`INCONCLUSIVE`); the same event on an H1a or H1b path → compared;
   - S3: zero Stop records; two Stop records; `stop_hook_active` true; `emitted` not JSON, not an object, or without a string `systemMessage` → compared;
   - S4: one extra or missing character, a different prefix (`Stop said: `, `SessionStart says: `), or another nonce → compared;
   - S5: two qualifying events → both compared;
   - S6: the event before the last `assistant` event, or after `result` → compared;
   - safeguard: an otherwise qualifying event carrying `continue` or `stopReason` → excluded from the subtype comparison but the indicator is one-sided → `INCONCLUSIVE`;
   - no effect: H1, A1 and A2 subset replays keep their labels, and every R1–R5 test passes unchanged.
2. **Offline reclassification of the A3 archive**, with no host session, following #553, #563 and #800:
   - verify `C:\dev\d5p2-h1c-a3-archive\2026-11-16` against `2026-11-16.SHA256SUMS` before and after;
   - run the merged classifier on the archive: `headless` with pin `2.1.310 (Claude Code)` and model `claude-opus-5-5`, the unchanged interactive outcome, then `combine`;
   - re-record an **omitted-material completeness check**: every unpublished transcript entry, raw event and stderr line, checked for each arm's nonce;
   - publish `outcome_a1_headless.r1r6.json` and `outcome_a1.r1r6.json` beside the unchanged as-run outcomes, plus an append-only addendum to the #804 record. A repo-only replay of the published subset is a subset check, never an independent reproduction.
3. **H1 gate record** (its own go-ahead): combines A2 (#800) and A3 under R1–R6 on `2.1.310`.

Combining any two of these steps needs explicit owner authorization.

## 8. Decisions requested of the reviewer

| # | Decision | Recommendation |
|---|---|---|
| R6-1 | Exclude the event from the subtype comparison (not re-categorise it) | **Yes.** Its nonce location is already `host_output`; only the comparison is blocked. |
| R6-2 | Narrow (Stop, emitter arm, one event, exact derivation, position) vs. a general `informational` exemption | **Narrow** (B, C, D rejected). A format change falls back to the comparison and a review. |
| R6-3 | Keep the indicator scan on the excluded event | **Yes** (R3 safeguard). |
| R6-4 | Sequence | **Separate steps** (§7). |

## 9. Not decided here

- The host's internal meaning of `informational`.
- Whether other hook events surface a `systemMessage` on the stream, and any rule for them.
- The H1 gate record, H2–H6.
- Repeatability (n = 1) or other host versions.
- Any runtime change, including Mneme's own Stop output (`_emit_stop_feedback`, #550), freeze amendment, P2-first charter or implementation.
