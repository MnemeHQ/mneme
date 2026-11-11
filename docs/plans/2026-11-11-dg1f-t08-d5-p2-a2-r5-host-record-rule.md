# DG1F T-08 D5 + P2: A2 evidence-classification rule review, R5 `host_record` (PROPOSED: rule only)

**Status:** **PROPOSED**, for independent review. Docs only. It does **not** reclassify anything. Accepting it would authorize none of the following:
- a classifier code change;
- a reclassification run;
- a re-run or live probe;
- an H1c/A1 re-pin;
- a runtime change, freeze amendment, charter or implementation.

It follows the separate-step precedent (#551 → #552 → #553, and R4: #561 → #562 → #563): rule, then implementation, then offline reclassification, each separately approved (§7).

**Anchor:** `main` @ `cf7c33c9`.
**Revision 2 (2026-11-11):** answers the #796 review. R1 checks the hook event but not the tool, and both H1a paths share `PreToolUse`. So R5 now ties each record to a **tool-attributed anchor**: an R1-qualifying entry whose `hookName`, `toolUseID` and emitter invocation all name the path's expected tool (§3). Wrong-tool negative tests are added (§7). R1–R4 are unchanged, and nothing is reclassified.

**Inputs:**
- the accepted probe scope (#545), §3 and §6, and its Amendment A2 (§4.3, #794);
- the accepted rules R1–R3 ([#551](2026-10-17-dg1f-t08-d5-p2-h1-classifier-rules.md)) and R4 ([#561](2026-10-19-dg1f-t08-d5-p2-a1-hook-system-message-rule.md)), as implemented in `classify_h1.py` at `4c1c270e`;
- the accepted A2 evidence record [`docs/validation/dg1f-t08-d5-p2-host-path-h1-a2-2026-11-11.md`](../validation/dg1f-t08-d5-p2-host-path-h1-a2-2026-11-11.md) (#795), and its published artifacts `…/live-a2-2026-11-11/`. This note answers that record's §6 "for review" item, under the narrowness requirements stated there.

## 1. Why a rule review

The A2 run came out `INCONCLUSIVE` on all three paths (H1a-edit, H1a-bash and H1b-start, on Claude Code `2.1.310`). The only reason was two nonce locations the category table does not recognise.

Every other criterion held:
- the paired controls held;
- permission decisions were equal;
- stream host events were identical;
- turn counts were equal;
- the R1 model-bound location was present;
- the nonce was echoed.

The as-run classifier made the right call: it had never seen these two entry shapes. Without a rule for them, any later 2.1.310 run on these paths is `INCONCLUSIVE` whatever happens.

Adopting a rule changes how evidence is **read**, never what the host did.

## 2. What the evidence shows

**Published files** (the A2 collector publishes `rendered` on `hook_*` entries and a nonce-line excerpt of `api-request-blob` entries; #795 §1), plus a **read-only check of the raw archive** `C:\dev\d5p2-h1-a2-archive\2026-11-11`. The archive is integrity-verified against its sums; this check is not a reclassification.

| Observation | All three emitter arms | Paired no-op controls |
|---|---|---|
| R1-qualifying `hook_additional_context` entry | **Exactly one.** `hookEvent` is the probed event, this arm's emitter invoked it, and the nonce is in `attachment.content`. `content` holds exactly one item. | **None** |
| Tool identity of that entry | **`hookName`** is `PreToolUse:Edit`, `PreToolUse:Bash` or `SessionStart`. On H1a, **`toolUseID`** equals the `id` of the transcript `tool_use` whose `name` is the expected tool: `Edit`, or `Bash`. In H1a-edit the `Read` call has a different id. The emitter's **`hook-log.jsonl` envelope** has `hook_event_name` equal to the probed event and `tool_name` equal to the expected tool (`null` for SessionStart). For H1b, `toolUseID` is the literal `SessionStart` and there is no `tool_use`. The paired `hook_success` entry carries `hookName` `SessionStart:startup`; that is R2's entry and is not used by R5. | – |
| That entry's `rendered` and `renderedRole` | `renderedRole: "system"`. `rendered` holds exactly one item, whose `content` **equals exactly** `<system-reminder>\n{L} hook additional context: {C}\n</system-reminder>`. `C` is the entry's `attachment.content[0]`. `L` is `PreToolUse:Edit`, `PreToolUse:Bash` or `SessionStart`: the probed event, plus `:` and the matcher's tool for tool events. | n/a |
| `api-request-blob` entries carrying the nonce | **Exactly one**, with `message.role: "system"`. **Exactly one line** of its text contains the nonce, and that line **equals exactly** `{L} hook additional context: {C}` with the same `L` and `C`. For H1a it is the whole one-line text; for H1b it is one line of 58. | **None** carry the emitter's nonce |
| `rendered` carrying the nonce on any other entry | **None.** Other attachment types (for example `environment`) carry `rendered` text without the nonce. | – |
| Any other transcript entry carrying the nonce | **None**, apart from those already categorised: `hook_success` stdout (R2) and assistant text (`echo`). | – |
| The same entry types on 2.1.202 | Neither `rendered` nor `api-request-blob` occurs anywhere in the H1 (2026-10-17) or A1 (2026-10-19) archives. | – |

**What is not known.** No host documentation was consulted for `rendered`, `renderedRole` or `api-request-blob`, so the note relies only on recorded evidence. The names suggest a rendering of the hook context and a record of request content, and `role: system` suggests the system part of a model request. **This run cannot establish either reading.** No observed model request can be tied to the blob, beyond the model's echo, which R1 already accounts for.

## 3. Proposed rule

### R5: two host records of R1-qualifying context are `host_record`, narrowly

**New category, `host_record`:** the host's own record or rendering of content that **another rule already classifies**. It is recorded in `nonce_locations`. It **never** counts as delivery to the agent or the developer, it is **never** sufficient for any label on its own, and it **never** masks another location. For labels, it behaves exactly like `host_output`: classified, not delivery. The label logic does not change; unclassified-first still applies.

`L` is the path's **expected label**: the probed event, followed by `:<tool>` when the path's spec names a tool (`PreToolUse:Edit`, `PreToolUse:Bash`), and the bare event otherwise (`SessionStart`).

Both parts below depend on a **tool-attributed anchor**: a transcript `hook_additional_context` attachment that meets R1's three conditions **and** the attribution conditions 4–6. R1 itself checks the event but not the tool, and both H1a paths share `PreToolUse`, so R5 does not rely on R1 alone for attribution. A1 to A3 are R1's conditions; A4 to A6 are the tool attribution:
1. **(A1)** `attachment.hookEvent` equals the probed event;
2. **(A2)** this arm's emitter invoked that event (`hook-log.jsonl`);
3. **(A3)** the nonce is in `attachment.content`;
4. **(A4)** `attachment.hookName` equals `L` exactly;
5. **(A5)** for a tool path, `attachment.toolUseID` equals the `id` of a `tool_use` in this arm's transcript whose `name` is the expected tool;
6. **(A6)** for a tool path, the emitter's hook-log record that emitted the nonce has an envelope with `hook_event_name` equal to the probed event **and** `tool_name` equal to the expected tool.

For a lifecycle path (no tool in the spec), conditions 5 and 6 do not apply, and condition 4 requires `hookName` to be the bare event. An R1-qualifying entry that fails any of conditions 4–6, for example evidence from the wrong tool under the right event, is **not** an anchor. R5 never classifies a location against it.

**R5a: `rendered` on an anchor.** A nonce occurrence at `rendered[i].content` is `host_record` only if **all** of these hold:
1. the entry itself is a tool-attributed anchor;
2. `renderedRole` is `"system"`;
3. `rendered` and `attachment.content` have the same length;
4. for **every** `i`, `rendered[i].content` equals exactly `<system-reminder>\n{L} hook additional context: {attachment.content[i]}\n</system-reminder>`.

Otherwise it stays `unclassified`. `rendered` on any other entry type is not covered, including a non-anchor `hook_additional_context`, `hook_system_message`, `hook_success` and non-hook attachments.

**R5b: `api-request-blob` text.** A nonce occurrence at `message.content[j].text` of a transcript entry with `type: "api-request-blob"` is `host_record` only if **all** of these hold:
1. `message.role` is `"system"`;
2. the arm has at least one tool-attributed anchor. That includes condition 6, the emitter's invocation for the probed event and expected tool;
3. **every** line of that text containing the nonce equals exactly `{L} hook additional context: {C}`, where `C` is an item of a **tool-attributed anchor's** `attachment.content`.

Otherwise it stays `unclassified`, including any partial match, extra text, other role, another event or tool label (such as `PreToolUse:Bash` in the Edit arm), or a nonce line that matches no anchor's content.

**R1 itself is unchanged.** R1 still classifies an R1-qualifying entry from the wrong tool as `model_bound`. At label level, the classifier already counts emitter invocations only for the expected tool (`classify()`, `tool_name` filter), so a wrong-tool invocation gives "emitter not invoked" and `INCONCLUSIVE`. Whether R1 should also gain the tool conditions is a separate rule question (§9), not decided here.

**What R5 does not do:**
- **No delivery claim:** it makes no claim that the host fed either record to the model, and it adds no delivery evidence. Delivery still comes only from a `model_bound` location (R1 or the earlier table).
- **No unlocking without R1:** it cannot turn a run without R1 delivery into a passing label. Without an R1-qualifying entry, both parts fail and the location stays `unclassified`, so the result is `INCONCLUSIVE`.
- **No masking:** every other location is categorised exactly as before.
- **No retroactive effect:** it changes nothing for evidence that lacks these entry types, including the H1 and A1 archives.

**For:**
- **Event and tool matching and emitter attribution are explicit:** R5 does not merely inherit them from R1. The anchor must match the event (A1), the exact label (A4), the tool's own `tool_use` (A5) and the emitter invocation for that event and tool (A2, A6). The blob's label must match the expected tool too.
- **Exact derivation:** each R5 location must be a fixed, host-added wrapping of the R1 content: the event label prefix, plus the `<system-reminder>` wrapper for `rendered`. Any other text, or a format change in a later host version, falls back to `unclassified` and a review.
- **The distinction is kept:** `host_record` asserts neither model input (`model_bound`) nor host output to the stream consumer (`host_output`). That is the distinction the #795 review asked to preserve.
- **Conservative error:** if either record is in fact model input, R5 under-reports agent delivery and never over-reports it. Any passing label still rests on R1 alone.

**Limits, stated for the record:**
- **One version and one run:** the shapes were observed on `2.1.310` only, n = 1 per path, headless.
- **One `content` item:** R5a's equality condition was observed only with one `content` item.
- **Unknown blob semantics:** whether `api-request-blob` is the exact request, a deduplicated store or something else is unknown. R5 does not depend on it.

## 4. Alternatives considered

| Option | Effect | Assessment |
|---|---|---|
| **A. R5 as proposed (`host_record`, narrow, tied to R1)** | The three A2 paths can reach a label from R1, if every other condition holds. | **Proposed.** It is the narrowest reading that removes the block without any delivery claim. |
| B. R5b → `model_bound` | The blob becomes independent agent-delivery evidence. | **Not proposed.** It rests on undocumented semantics, and R1 already covers delivery. Would over-claim if the blob is not the request. |
| C. Both → `host_output` | The same label effect as A. | **Not proposed.** It describes a possible request-content record as output that is not model input, which the evidence does not show. It blurs the distinction the #795 review asked to keep. |
| D. A prefix match instead of exact derivation | Tolerates text variation. | **Not proposed.** It would accept emitter-controlled or unrelated text that happens to begin with the label. |
| E. Relax unclassified-first for these entry types | The same label effect. | **Rejected.** It removes the safeguard that caught them. |
| F. Re-run with another host version or collector | Avoids a rule. | **Not proposed.** The host recorded these entries itself, so a re-run on `2.1.310` would show them again. The archive is sufficient, subject to the reclassification's completeness check (§7). |

## 5. What R5 would change, by reasoning only (not a reclassification)

This section projects the effect so the reviewer can judge the rule. **It is not a result.** Only an authorized offline reclassification establishes labels.

| Run | As classified | Under R1–R5 (projected) | Why |
|---|---|---|---|
| A2 H1a-edit, H1a-bash, H1b-start | INCONCLUSIVE (×3) | likely `DELIVERED_TO_AGENT` (×3) | Both unrecognised locations per path meet R5a or R5b in the read-only check (§2). The R1 location gives delivery, and every other condition held (#795 §3). |
| A2 listed-path result | NOT MET | likely PASS, **still not the H1 gate** | H1c is not in A2 |
| H1 2026-10-17, A1 2026-10-19 | unchanged | unchanged | Neither entry type occurs there |

## 6. Effect on the open gates

None directly. Even a projected A2 PASS would show only that the two §4 candidate shapes reach the agent on `2.1.310` for H1a and H1b. **H1 stays NOT MET** until H1c passes on an accepted pin, under A1 or a re-pinned A1. Mixed-version combination is not decided (A2-1). P2-first, the `[layer1-freeze]` amendment, G3, DG1G and DG1 are unaffected.

## 7. If accepted: the procedure (each step a separate go-ahead)

1. **Classifier change.** One harness PR:
   - `categorise()` returns `host_record` for R5a and R5b. It needs the arm's R1-qualifying content and the path spec's `L`, so `nonce_locations` passes them.
   - The category table docstring gains `host_record`.
   - `RULES_ID` becomes `"as-run table + R1-R5 (#551, #561, #<this PR>)"`. `classify_a1.py` inherits it.

   **Regression tests:**
   - R5a: positive → `host_record`; `renderedRole` other than `system` → unclassified; rendered text with any extra or missing character, or a length mismatch with `content` → unclassified; `rendered` on an entry with the wrong `hookEvent`, or where the emitter was not invoked → unclassified; `rendered` on `hook_system_message`, `hook_success` or a non-hook attachment → unclassified.
   - R5b: positive → `host_record`; role `user` or other → unclassified; a nonce line with the wrong event or tool label, a prefix or suffix, or content matching no anchor → unclassified; a second, non-matching nonce line in the same text → unclassified; no anchor in the arm → unclassified (`INCONCLUSIVE`); emitter not invoked → unclassified.
   - **Wrong tool under the right event** (review of #796). In each case the entry still meets R1, so this shows that R1 alone is not used. Each case stays `unclassified` for both R5a and R5b, with the label `INCONCLUSIVE`:
     - on the H1a-edit path, an R1-qualifying entry with `hookName` `PreToolUse:Bash`;
     - on the H1a-edit path, a `toolUseID` that matches the `Read` call's `tool_use`;
     - a `toolUseID` that matches no `tool_use`;
     - an emitter hook-log envelope with `tool_name` `Bash`;
     - a blob line labelled `PreToolUse:Bash` whose content matches the Edit anchor;
     - on H1b, an anchor whose `hookName` is not exactly `SessionStart`.
   - Labels: R1 plus R5 locations and nothing else → `DELIVERED_TO_AGENT`; R5 locations plus a co-present unrecognised location → `INCONCLUSIVE`; `host_record` never yields a delivery label without R1.
   - No effect: H1 and A1 subset replays keep their labels, and every R1–R4 test passes unchanged.
2. **Offline reclassification of the A2 archive**, with no host session, following #553 and #563:
   - verify `C:\dev\d5p2-h1-a2-archive\2026-11-11` against `2026-11-11.SHA256SUMS` before and after;
   - run the merged classifier on the archive, with the version pin `2.1.310 (Claude Code)` and model `claude-opus-5-5`;
   - re-record an **omitted-material completeness check**: every transcript entry, raw event and stderr line not published, checked for each arm's nonce;
   - publish `outcome.r1r5.json` beside each unchanged as-run `outcome.json`, plus an append-only addendum to the #795 record. A repo-only replay of the published subset is a subset check, never an independent reproduction.

Combining step 1 with this rule review, or with step 2, would change this sequence and needs explicit owner authorization.

## 8. Decisions requested of the reviewer

| # | Decision | Recommendation |
|---|---|---|
| R5-1 | Category for the two locations | **`host_record`** (A), not `model_bound` (B) or `host_output` (C) |
| R5-2 | Exact derivation from R1 content, versus a prefix match | **Exact** (D rejected): a format change falls back to `unclassified` and a review |
| R5-3 | Tie R5 to a **tool-attributed** R1-qualifying anchor in the same arm (A1–A6) | **Yes**: R5 can never unlock a label without R1, and never attributes a record to the wrong tool under the right event |
| R5-4 | Sequence | **Separate steps** (§7); combining needs explicit owner authorization |

## 9. Not decided here

- Whether either record is model input.
- Whether R1 itself should gain the tool conditions A4–A6. R1 is unchanged here.
- Any H1c/A1 re-pin, or the A1 interactive run.
- H2–H6.
- Mixed-version gate combination (A2-1).
- Any runtime change, freeze amendment, P2-first charter or implementation.
