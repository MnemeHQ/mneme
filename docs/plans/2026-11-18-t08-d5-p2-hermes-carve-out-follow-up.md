# T-08 D5 + P2: Hermes experimental carve-out, follow-up to #829 (PROPOSED)

> **PROPOSED: architecture amendment proposal only**, for independent review and owner acceptance.
>
> This is a read-only follow-up to the accepted [Antigravity carve-out proposal](2026-11-18-t08-d5-p2-antigravity-carve-out-proposal.md) (#829, `0ad042aa`). It edits no other document. It changes no runtime code, harness, pin, test, evidence, ADR or Layer 1 freeze. It runs nothing, does not touch OpenCode S1 (#824), and authorizes nothing.
>
> **Anchor:** `MnemeHQ/mneme` `main` at `0ad042aa`.

## 0. Proposal

**Owner direction (2026-11-18):**
- defer Hermes H6a and H6b validation alongside Antigravity H4a;
- keep both integrations on their existing P2-first behavior;
- prioritize OpenCode S1 validation and its suitability for the ContextOS experiment;
- keep OpenCode's intended H7 inclusion, with **no host-gate exception for OpenCode**.

**Proposal:**
- **Add Hermes as the second consumer in #829's D5 Amendment A1.** It is assessed on its own facts in §1.
- **Hermes keeps the P2-first contract on `main`.** Its paths H6a and H6b become **`DEFERRED (not run)`** and never PASS. Phase 2 claims no repository-boundary enforcement and no host-visible warning for Hermes.
- **Hermes's integration, tests, the #828 H6 harness arms and all evidence stay intact.**
- **The A1 list is closed at two:** Antigravity and Hermes. Adding to it needs its own separately reviewed D5 amendment. Owner direction excludes OpenCode.
- This **supersedes parts of #829** (listed in §2.1). The revised probe sequence is in §4.

## 1. Hermes, assessed on its own facts

| Aspect | Hermes at `0ad042aa` | Compared with Antigravity |
|---|---|---|
| **Selection call** | One method, `MnemeHermes._memory()` (`hermes/adapter.py:258-262`). An explicit constructor `memory=` wins, and is selected only if it `is_file()`. Otherwise it is `resolve_memory(Path(self.project_dir)).path`. | Antigravity calls `resolve_memory` per event (`antigravity/adapter.py:244`). |
| **Start point and granularity** | **The discovery start point is fixed; the selection is not cached.** `project_dir` is fixed per gate instance: the plugin builds one gate at `register` (`plugin.py:77-84`) with `project_dir` set to the process working directory (`plugin.py:53-54`), and every tool call evaluates against `gate.project_dir`. But the memory is **re-resolved on every invocation**: `context_for_turn` and each gate call `_memory()` independently (`adapter.py:143`, `:291`, `:417`, `:499`), using the same fixed `project_dir` or explicit override. The start point does not depend on the edit target. | Antigravity starts at each event's `cwd`. |
| **What consumes the selection** | **Two output paths use the same resolution method, through separate calls:** context injection (`context_for_turn`; `ContextInjection.memory_path`; an empty injection at `:145`; the H6b path) and the three gates (`write_file`, `patch`, `terminal`; the H6a path). | Antigravity has one gate path. |
| **Explicit override** | The constructor `memory=` is an explicit path, not discovery (D5 §2; Q2 O3). It is **unaffected** by P2-first, Phase 2 and this exception. **Existing gap:** charter §4 says constructor overrides record `source: explicit`, but Hermes never calls `explicit_selection` (`memory_selection.py:97-100`), so no such record exists. This proposal records the gap and does not fix it. | Antigravity has no explicit path. |
| **Reporting today** | Missing memory gives `ACTION_SKIP` with `"no project memory"` (`:295`, `:419`, `:501`). The selection reason is **not recorded anywhere**, because `GateResult.reason` reaches the embedding host (charter A2 §5.2.4 item 1; A2-6). Rows 2 and 7 leave no record. | The same: no record on Antigravity either. |
| **Code shared with other hosts** | Hermes selects only through `resolve_memory` (`adapter.py:43-45`), and imports helpers from `claude_code.hook` (`adapter.py:46-58`). The Agent SDK and LangChain select through the Agent SDK adapter (`test_p2_first_consumer_parity.py:131-138`). **The exception therefore does not reach H5a, H5b or H5c.** An embedder that runs both Hermes and the Agent SDK or LangChain gets diverging selections in rows 4 and 5. | Antigravity also imports `claude_code.hook` helpers (`antigravity/adapter.py:72`) and selects only through `resolve_memory`. Neither host shares selection code with another adapter. |
| **Tests** | `tests/integrations/test_p2_first_consumer_parity.py::test_hermes` (`:141-147`) is the §7.5 consumer-parity case. It exercises **only `context_for_turn`**. `tests/integrations/test_p2_first_same_selection.py::test_hermes` (`:261`) is the §7.8 "same selection, unchanged output" case: row 1 against row 2, over both `context_for_turn` and `evaluate_tool_call`. `tests/integrations/hermes/` (six files) covers the context, gate, e2e, identity, wiring and relative-path behavior. | Antigravity has its own parity case. |
| **Evidence** | Dispatch-layer only, on hermes-agent `0.19.0`, with no live model session (`docs/integrations/hermes.md:76`). The #828 harness holds the H6 arms. D3 was refuted there (injected context is persisted as `api_content`). Candidate T stays unapproved (D4). | Antigravity has no run, and a verified `2.8.1` artifact. |
| **Classification** | Already **Experimental** (`docs/integrations/README.md:35`). | Listed as Native (#829 E0, separate). |

**What follows for Hermes specifically:**
1. **Hermes re-enters as a whole consumer, or not at all.** H6a and H6b resolve memory through separate `_memory()` calls, from the same fixed start point. If only one path moved to B1, those separate calls would use different discovery semantics (B1 on one path, the unbounded walk on the other), so one gate instance could govern its context and its gates from different memories. Re-entry needs **both H6a and H6b passing on one pin**.
2. **Divergence follows the fixed start point.** For a given `project_dir`, each invocation's unbounded walk can pick a memory where a B1 host might pick none (rows 4 and 5). That is the same row-4/5 divergence as Antigravity (#829 §2), and it is independent of which file is edited.
3. **The explicit `memory=` path needs no exception text,** because it is outside implicit discovery.
4. **No E0 analogue is needed.** Hermes is already Experimental, so `hermes.md` needs only a sentence (§2).

## 2. Minimum additional changes (delta on #829 §3)

Each row adds to #829's list, and nothing in it is removed. Everything below is applied in the same single docs-only amendment PR as #829 §3. That PR is the separately reviewed D5 amendment that adds Hermes to A1.

| Document | Delta |
|---|---|
| **D5 Amendment A1** | The **closed** list is **Antigravity and Hermes**. Both stay on the P2-first walk and make no host-visible claim. D5 §5.1 is met for each because neither adopts B1. The §5.3 and §8 exclusions name both. Adding any other consumer needs its own separately reviewed D5 amendment, and owner direction excludes OpenCode. |
| **Charter Amendment A3** | **I1 and I4:** both consumers are excluded, and I4-P2F continues for both. **§3.1 and §3.2:** the unbounded mode serves both. **§4:** the Hermes row is deferred. **§5:** H6 also moves to the "deferred (experimental)" row, and the "six organizing gates" and "twelve output paths" wording (`:156-158`) is qualified to "listed". **§5.1 (A1) "no per-host exception" (`:170`), §11 C3 and §12 step 3:** "except the D5 A1 exceptions". **§5.2.5:** Phase 2 needs **H1, H2, H3 and H5** with every listed path, **and H7: Phase 2 cannot freeze until H7 is defined and passes**, unless the owner decides otherwise separately. **§5.2.7 (`:420`, "H2–H6 probes proceed by adoption"), §5.2.8 (`:428`) and A2-7 (`:446`, "All of H1–H6"):** qualified the same way. **§7.5:** `test_p2_first_consumer_parity.py::test_hermes` expects the unbounded selection in Phase 2, and a **new gate-path case** asserts that Hermes asks for the unbounded mode on the context path **and** on a gate path. **§7.8:** `test_p2_first_same_selection.py::test_hermes` is unchanged. **§8:** no Hermes live evidence. **§9:** the Phase 2 freeze authorizes B1 and I3 for the non-excepted consumers only. **§10:** Hermes's P2-first behavior is preserved. **Re-entry rule:** both H6a and H6b pass on one hermes-agent pin, plus Hermes's own `[layer1-freeze]` amendment and the parity flip. Hermes re-enters independently of Antigravity. **Failure rule:** an H6 failure goes to the owner and blocks no other consumer. |
| **Q2 Amendment A2** | The relaxed reporting clauses and the "land together" departure extend to Hermes. |
| **Probe scope Amendment A5** | **H6a and H6b leave the batch order** as `DEFERRED (not run)`. They stay in the §8 summary but are not §6 labels and never pass. The revised sequence (§4) uses **A5 batch names** ("A5 batch 1", "A5 batch 2"), to avoid a clash with the existing `dg1f-t08-d5-p2-batch2-host-path/` artifacts. Evidence records are keyed by gate, per §8. A4 §4.5.2's at-risk rationale lapses for every deferred path. |
| **Batch-2 harness README** | The pointer says the **whole batch-2 harness (H4a, H6a, H6b) is for deferred paths**. It is kept intact, and no later batch condition depends on it. D3 (refuted), D4 (T unapproved) and D5 stay recorded. |
| **`docs/integrations/hermes.md`** | One sentence: the T-08 Phase 2 boundary (B1) does not apply to Hermes, and no selection notice is host-visible on it. The status stays Experimental. |
| **Readiness assessment (#823)** | **No edit.** Through the charter amendment, P10 ("H6 BLOCKED (at risk)") becomes "deferred". P11's "needs P5–P10" becomes "needs P5–P7, P9 and H7". P14 reads "every consumer except Antigravity and Hermes". #829 §3 also missed P11 and the charter passages above; this delta covers them for both consumers. |
| **ADR-033 and the Layer 1 freeze** | **No change,** for the reasons in #829 §3. |

### 2.1 Passages of the accepted #829 that this supersedes

The amendment PR follows this proposal wherever #829 says otherwise:
- `:19`, `:58` and `:102` (the exception is "Antigravity only"; "Any other consumer, OpenCode included, needs its own D5 amendment"): the A1 list is now **Antigravity and Hermes**. Adding Hermes is done by that reviewed D5 amendment PR. `:16` ("B1 … apply to every other consumer") now also excludes Hermes.
- `:63` (the §5 gate rule "unchanged for H1, H2, H3, H5 and H6") and `:99` ("H1, H2, H3, H5 and H6 are unchanged"): **H6 is now deferred too**, so these read "H1, H2, H3 and H5".
- `:17`, `:72`, `:114` (E5) and `:121` (§7 step 3): **batch 2 is no longer H6a and H6b.** There is no H6 live run.
- `:64` (§5.2.5): the required gates are H1, H2, H3 and H5, plus H7.
- `:71` (Q2 A2, "For Antigravity only"): it extends to Hermes.
- `:73` (harness README pointer): the whole batch-2 harness is deferred.
- `:130` (not authorized, "batch 2"): read as the H6 paths.

## 3. OpenCode H7: kept as a formal requirement, with no exception

- **OpenCode will be a consumer.** OpenCode S1 (#824, draft) calls `resolve_memory`, so once it lands it is an implicit-discovery consumer (readiness S1).
- **Inclusion still needs formal steps.** The owner intends to include it as H7. That requires its own reviewed charter amendment (an OpenCode §4 row and H7 output paths), probe-scope paths and a pin.
- **No exception covers it.** The A1 list excludes OpenCode, so once OpenCode is a consumer, Phase 2 cannot freeze until H7 is defined and passes, unless the owner decides otherwise separately (§2).
- **#824 is unchanged here.** Its scope is narrow: new-file Python `write` with `FORBID_LITERAL`; `edit`, patch, shell and non-`.py` targets are `NOT_COVERED`. Whether the ContextOS workflow exercises that surface is a separate S1 validation question.

## 4. Revised probe sequence (none of it authorized here)

| Step | Paths | Harness | Status |
|---|---|---|---|
| done | H1a, H1b, H1c | H1 harness | `PASS` (#808) |
| **A5 batch 1** | **H2a** (D1 targeted re-run), **H2b**, **H5c** | **existing**: H2b and H5c each need an extension PR with offline self-tests (H2b a new Stop `systemMessage` emitter in `validation/codex-cli/probe/`; H5c an extension of `validation/langgraph/probe/probe_m0.py`; probe scope §5). H2a reuses the existing harness, plus rollout collection under D1. | not started |
| **A5 batch 2** | **H3a**, **H5a**, **H5b** | new: Kiro (`--v3` driver); the Agent SDK script with operator credentials | not started |
| **H7** | OpenCode output paths, still to be defined | to be designed | **formal requirement outstanding** (§3) |
| deferred | H4a, H6a, H6b | #828 harness, kept | `DEFERRED (not run)`; run on concrete need |

**Preconditions:**
- **H2a's D1 targeted re-run** is valid only if the implementation keeps `codex_cli/hook.py:_context_output`'s shape unchanged, and only on the same pin (probe scope §10 D1).
- **Pins are checked before each batch:** codex-cli `0.149.1`, Kiro `2.19.2 --v3`, and the langchain/langgraph pins (§7). The Agent SDK version and model are pinned when its harness is built (§7). Whether they are still installable is unchecked (readiness P6). A re-pin needs a reviewed amendment.

**Gates:**
- **A4's positive gate applies between batches.** A5 batch 2 starts only after every A5 batch-1 path passes, or on an owner decision.
- **A4's failure rule also holds H7.** A failing label in any batch goes to the owner (charter §5) before any further batch, H7 included, starts. Apart from that rule, H7 is scheduled by owner priority once its charter and probe-scope amendment is accepted, and it does not wait for batches 1 and 2 to complete.
- **The Phase 2 freeze needs every listed gate to pass:** H1 (done), H2, H3, H5 and H7.

**Why this order:** with both at-risk paths deferred, A4's reason to front-load them is gone. The order returns to the probe scope's original D5 order, existing harnesses first.

## 5. What this does not weaken

- **H1, H2, H3 and H5 are unchanged,** with every path, their pins, the one-pin-per-gate rule and the §6 labels.
- **H4a, H6a and H6b are `DEFERRED (not run)`** and never PASS. Neither Antigravity nor Hermes claims host visibility or Phase 2 boundary behavior.
- **Neither consumer's governance drops below `main` today.** Both keep the accepted P2-first behavior. Hermes's explicit `memory=` path is unchanged, and so is its existing gap of not recording `source: explicit`.
- **The exception list is closed at two.** OpenCode and every other consumer have no exception, and H5 (Agent SDK, LangChain) is not reached by the Hermes exception.
- **Readiness gaps S1–S7 all remain open,** and E0 stays separate.
- **Phase 2 stays NOT READY and BLOCKED.**

## 6. Decisions requested of the owner

| # | Decision | Recommendation |
|---|---|---|
| F1 | Add Hermes to D5 A1 (a closed list of two), on the P2-first contract | **Yes.** Same reasoning as #829 O1: no new silent skips. |
| F2 | Hermes re-enters only as a whole consumer: H6a and H6b both pass on one pin | **Yes.** Both paths resolve from the same start point through separate calls; splitting them would mix discovery semantics (§1). |
| F3 | Supersede the #829 passages in §2.1, and adopt the §4 sequence (A5 batches 1 and 2; H7 mandatory for the freeze and bound by A4's failure rule) | **Yes.** |
| F4 | Apply #829 §3 and this §2 together in one docs-only amendment PR | **Yes.** It avoids an intermediate state where Hermes is still mandatory. |

## 7. Not authorized by this proposal

- applying any amendment, from #829 or from here;
- any runtime, harness, pin, test or evidence change, including the gate-path parity case;
- any change to PR #824;
- any probe or live run, including A5 batches 1 and 2, H7, H4a, H6a and H6b;
- harness extension PRs, host installs and credential use;
- Hermes candidate T;
- treating any deferred path as PASS, or changing any earlier label: H1 stays `PASS`, G3 stays `PARTIAL`;
- Phase 2 implementation, or any release.
