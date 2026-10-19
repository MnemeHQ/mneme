# DG1F T-08 D5 + P2: A1 evidence-classification rule review, `hook_system_message` (PROPOSED: rule only)

**Status:** **PROPOSED**, for independent review. Docs only. It does **not** reclassify anything. Accepting it would authorize no classifier code change, no reclassification run, no live probe (including the A1-interactive run), no runtime change and no freeze amendment (§6). This follows the R1–R3 precedent (#551 → #552 → #553).

**Anchor:** `main` @ `626941df`.

**Inputs:**
- the accepted probe scope (#545) §3, §6 and Amendment A1 §4.2 (#555);
- the accepted A1 harness (#556), including `classify_a1.py`, which reuses the `classify_h1.py` table with R1–R3 (#551, #552);
- the A1-headless evidence record `docs/validation/dg1f-t08-d5-p2-host-path-h1c-a1-headless-2026-10-19.md` and its artifacts `…/live-a1-headless-2026-10-19/` (#560, **draft, not merged**; this note should merge after it). §6 decision 1 of that record is the question this note answers.

## 1. Why a rule review

The A1-headless run came out `INCONCLUSIVE`, and the only reason was one nonce location that the table doesn't recognise. Every §4.2 interference criterion held: one Stop invocation per arm, no `stop_hook_active`, no permission difference, a normal `result`, and no host-event or indicator difference after R3. The as-run classifier made the right call: it had never seen this entry type.

The question also blocks the next run. `classify_a1.py interactive` applies the same unclassified-first rule, so without a rule for this location the A1-interactive run would be `INCONCLUSIVE` **whatever its capture shows**. That makes this review a precondition for that run, not an afterthought.

Adopting a rule changes how evidence is **read**, never what the host did.

## 2. What the evidence shows (published files, both arms, plus a raw completeness check)

| Observation | Emitter `H1c-sm` | Control `H1c-sm-ctl` |
|---|---|---|
| Transcript `attachment` with `attachment.type: "hook_system_message"` | **Exactly one**, after the model's reply, with `hookEvent: "Stop"`, `hookName: "Stop"` and `content` equal, byte for byte, to the `systemMessage` value the emitter wrote (`hook-log.jsonl` `emitted`). It has no `stdout`, `exitCode` or `command` field. | **None** |
| Transcript `attachment` with `attachment.type: "hook_success"` | One, immediately before it, with the same `toolUseID`; `stdout` is the emitter's raw JSON. That is already `host_output` under R2. | **None.** The no-op printed nothing. |
| Transcript `hook_additional_context` | **None.** The emitter has no `hookSpecificOutput` (A1 shape). | None |
| Stream-json | **No event carries the nonce:** no `system` event and no informational message. | No nonce |
| Entries after the `hook_system_message` | Only `last-prompt`. There was no further user or assistant entry: the session ended. | Same session shape |
| Model reply | `OK` and `NO-PROBE-TOKEN`. That was expected, because Stop fires after the only turn. | Same |

**Completeness check (read-only, raw files in `C:\dev\d5p2-h1c-a1-live`, 2026-10-19; to be repeated and recorded by any authorized reclassification run):**
- each arm had 7 transcript entries that weren't published: 2 `queue-operation`, `deferred_tools_delta`, `agent_listing_delta`, `skill_listing`, `ai-title` and `last-prompt`;
- none of them contains the nonce, and neither do the omitted thinking blocks or `claude.stderr.txt`;
- no raw stream-json event contains it.

**Host documentation**, as recorded in the accepted Stop-path decision (#554 §2): `systemMessage` is a "warning message shown to the user", and in stream-json it "can arrive as an `SDKInformationalMessage`". The headless run showed no such stream message, so in this host and mode the notice went only to the session transcript.

## 3. Proposed rule

### R4: a Stop `hook_system_message` is host output, narrowly

**Rule.** A transcript entry with `type: "attachment"` and `attachment.type: "hook_system_message"` is categorised `host_output` only if **all** of these hold:
1. `attachment.hookEvent` equals the probed event;
2. the probe's own emitter invoked that event in this arm (`hook-log.jsonl`), the same test as R1 condition 2;
3. the nonce occurrence is in `attachment.content`.

Any `hook_system_message` entry failing a condition stays `unclassified`.

**What R4 does not do:**
- it **never** counts as delivery to the agent **or** the developer. Developer delivery still comes only from the A1-interactive capture (§4.2). Agent delivery still needs a `model_bound` location;
- it **never** masks another location. Every other location is categorised exactly as before, and unclassified-first still applies to all of them.

**For:**
- the entry is the host's own record of a hook's `systemMessage`, typed as such, and carries only the message text plus hook identifiers;
- it exists only when the emitter emitted and never in the control, and its content equals the emitted message exactly;
- the host documents `systemMessage` as a message for the user, not as model input, which is the opposite of `hook_additional_context` (R1), documented and recorded as context;
- `host_output` is the category the accepted §4.2 already assigns to the same notice when it surfaces in stream-json. Classifying the transcript copy the same way keeps one notice from receiving two categories depending on where the host logged it.

**Limits, stated for the record:**
- **This run cannot show whether the host later feeds a `hook_system_message` to the model.** The session ended after Stop, so no later model request exists to inspect, and no echo was possible. R4 rests on the documentation and the entry's shape, not on an observed model request. That limit is the same kind R1 accepted when it took the host's transcript record as delivery evidence.
- **The error is bounded and conservative.** If the entry were in fact model input, R4 would under-report agent delivery, never over-report it. R4 on its own can only produce `NOT_DELIVERED` for the headless run. A passing H1c label still needs the interactive capture to show the notice to the developer (`DELIVERED_TO_USER_ONLY`), which D5 accepts as a pass for any path. Under the alternative (§4, option B) the passing label would be `DELIVERED_TO_AGENT` instead, so the choice changes the recorded audience, not the gate.

## 4. Alternatives considered

| Option | Effect | Assessment |
|---|---|---|
| **A. R4 as proposed (`host_output`, narrow)** | Headless becomes `NOT_DELIVERED`; the interactive run can decide developer delivery. | **Proposed.** Matches the documentation and §4.2's existing treatment of the stream copy, and errs toward under-claiming. |
| B. `model_bound`, like R1 | Headless becomes `DELIVERED_TO_AGENT`. | **Not proposed.** It would claim agent delivery with no model request after the entry, no echo and documentation that says the opposite. That is over-claiming. |
| C. Leave it `unclassified` and probe model-boundness: a scripted follow-up turn after Stop, asking for the token | Would test whether the next model request carries it. | **Not proposed now.** It needs a scope amendment, a harness change and a new run. Even then an echo alone can't establish delivery (scope §3 step 3). It stays available if the reviewer judges the §3 limit unacceptable. |
| D. A new category (for example `developer_notice`) | Same outcome as A, with a separate label. | **Not proposed.** It adds a category the label table (§6) doesn't use and changes nothing downstream. |

## 5. What R4 would change, by reasoning only (not a reclassification)

This section projects the effect so the reviewer can judge the rule. **It is not a result.** Only an authorized offline reclassification run establishes labels.

| Run | As classified | Under R1–R4 (projected) | Why |
|---|---|---|---|
| A1-headless (`H1c-sm` vs `H1c-sm-ctl`) | INCONCLUSIVE | likely `NOT_DELIVERED`, with `side_effect_observed: false` and `a1.host_interference` empty | Both nonce locations become `host_output` (R2, R4); there is no `model_bound` location and no echo; the transcript was collected; every control held |
| A1-interactive | not run | depends on the capture | Under R4 the same entry would no longer force `INCONCLUSIVE`. A passing label then requires the capture-reviewed developer view (`DELIVERED_TO_USER_ONLY`) and no host-induced interference. |
| H1c under A1 (`combine`) | not computable | `DELIVERED_TO_USER_ONLY` **only if** the interactive run passes | `combine` treats a headless `NOT_DELIVERED` as clean (no interference) and takes the developer-delivery label from the interactive run |

**The H1 gate stays NOT MET** until the interactive run passes and the combined H1c label is recorded.

## 6. If accepted: the procedure (each step a separate go-ahead)

1. **Classifier change.** One harness PR changes `classify_h1.py` `categorise()` for R4 and bumps `RULES_ID` to `"as-run table + R1-R4 (#<this PR>)"`; `classify_a1.py`'s `A1_ID` inherits it. Regression tests:
   - R4 positive gives `host_output`;
   - wrong `hookEvent` → unclassified;
   - emitter did not invoke → unclassified;
   - nonce outside `attachment.content` → unclassified;
   - R4 never yields `DELIVERED_TO_AGENT` by itself;
   - R4 does not mask a co-present unclassified location;
   - an interactive case where R4 lets capture-reviewed developer delivery reach `DELIVERED_TO_USER_ONLY`.
2. **Offline reclassification of the A1-headless run**, with no host session, following #553:
   - archive the raw root `C:\dev\d5p2-h1c-a1-live` and verify it against #560's `MANIFEST.json`;
   - run the merged classifier on the archive, and re-record the completeness check from §2;
   - publish `outcome_a1_headless.r1r4.json` next to the unchanged as-run file, plus an append-only addendum to the #560 record. A repo-only replay is a subset check, never an independent reproduction.
3. **The A1-interactive run**, separately authorized, classified under the accepted rules.

## 7. Not decided here

- Whether the host ever feeds `hook_system_message` to the model in a later turn (option C).
- The shipped `_emit_stop_feedback` behavior (#550, investigation only).
- H2a's targeted re-run, and H2–H6.
- Any runtime change, freeze amendment or implementation.
