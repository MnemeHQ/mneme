# T-08 D5 + P2: Hermes experimental carve-out, follow-up to #829 (PROPOSED)

> **PROPOSED: architecture amendment proposal only**, for independent review and owner acceptance.
>
> This is a read-only follow-up to the accepted [Antigravity carve-out proposal](2026-11-18-t08-d5-p2-antigravity-carve-out-proposal.md) (#829, `0ad042aa`). It edits no other document. It changes no runtime code, harness, pin, evidence, ADR or Layer 1 freeze. It runs nothing, does not touch OpenCode S1 (#824), and authorizes nothing.
>
> **Anchor:** `MnemeHQ/mneme` `main` at `0ad042aa`.

## 0. Proposal

**Owner direction (2026-11-18):**
- defer Hermes H6a and H6b validation alongside Antigravity H4a;
- keep both integrations on their existing P2-first behavior;
- prioritize OpenCode S1 validation and its suitability for the ContextOS experiment;
- keep OpenCode's intended H7 inclusion, with **no host-gate exception for OpenCode**.

**Proposal:**
- Add **Hermes** as the second named consumer of #829's exception, on its own facts (§1).
- Hermes keeps the P2-first contract on `main`. H6a and H6b become **`DEFERRED (not run)`**, never PASS. Phase 2 claims no repository-boundary enforcement and no host-visible warning for Hermes.
- Hermes's integration, tests, the #828 H6 harness arms and all evidence stay intact.
- The exception remains a **named list** (Antigravity, Hermes). It extends to nothing else.
- This **supersedes #829's E5:** batch 2 is no longer H6a/H6b. The revised sequence is in §4.

## 1. Hermes, assessed on its own facts

| Aspect | Hermes at `0ad042aa` | Compared with Antigravity |
|---|---|---|
| **Selection call** | One method, `MnemeHermes._memory()` (`hermes/adapter.py:258-262`). An explicit constructor `memory=` wins (selected only if it `is_file()`); otherwise `resolve_memory(Path(self.project_dir)).path`. | Antigravity calls `resolve_memory` per event (`antigravity/adapter.py:244`). |
| **Start point** | `project_dir`, fixed per gate instance. The plugin sets it to the process working directory (`plugin.py`, `make_gate`). | Antigravity starts at each event's `cwd`. A Hermes session therefore resolves one memory for its lifetime. |
| **What consumes the selection** | **Two output paths share it:** context injection (`context_for_turn`, `ContextInjection.memory_path`, the H6b path) and the three gates (`write_file`, `patch`, `terminal`, the H6a path). | Antigravity has one gate path. |
| **Explicit override** | The constructor `memory=` is an explicit path, not discovery (Q2 O3). It is **unaffected** by P2-first, Phase 2 and this exception. | Antigravity has no explicit path. |
| **Reporting today** | Missing memory gives `ACTION_SKIP` with `"no project memory"` (`:295`, `:419`, `:501`) and an empty injection. The selection reason is **not recorded anywhere**: `GateResult.reason` reaches the embedding host, so it cannot carry it (charter A2 §5.2.4 item 1; A2-6). Rows 2 and 7 leave no record. | The same: no record on Antigravity either. |
| **Tests** | `tests/integrations/test_p2_first_same_selection.py::test_hermes` (`:261`) pins the selection across `context_for_turn` and `evaluate_tool_call`. `tests/integrations/hermes/` (six files) covers the context, gate, e2e, identity, wiring and relative-path behavior. | Antigravity has its own parity case in the same file. |
| **Evidence** | Dispatch-layer only, at hermes-agent `0.19.0`, with no live model session (`docs/integrations/hermes.md`). The #828 harness has the H6 arms. D3 was refuted there (injected context is persisted as `api_content`). Candidate T stays unapproved (D4). | Antigravity has no run and a verified `2.8.1` artifact. |
| **Classification** | Already **Experimental** (`docs/integrations/README.md:35`). | Listed as Native (#829 E0, separate). |

**What follows from these facts, specific to Hermes:**
1. **Hermes re-enters as a whole consumer, or not at all.** One selection feeds both H6a and H6b. Applying B1 to one path while the other stays unbounded would give a Hermes session two governing memories. So re-entry needs **both H6a and H6b passing on one pin**, not either one.
2. **Divergence is per session, not per event.** `project_dir` is fixed, so within a Hermes session the unbounded walk picks one memory, and a B1 host might pick none (rows 4 and 5). This is the same rows-4/5 divergence as Antigravity (#829 §2), at session granularity.
3. **The explicit `memory=` path needs no exception text.** It is outside implicit discovery, and so outside D5 (D5 §2).
4. **No E0 analogue is needed.** Hermes is already Experimental. `hermes.md` only needs a sentence saying the Phase 2 boundary does not apply.

## 2. Minimum additional changes (delta on #829 §3)

Each row adds to #829's list; nothing there is removed. Every change is applied in the same single docs-only amendment PR.

| Document | Delta for Hermes |
|---|---|
| **D5 Amendment A1** | The named list becomes **Antigravity and Hermes**. Both stay on the P2-first walk, and both make no host-visible claim. D5 §5.1 is met for each because neither adopts B1. The §5.3 and §8 exclusions name both. **Any other consumer still needs its own D5 amendment.** |
| **Charter Amendment A3** | I1 and I4: both consumers are excluded, and I4-P2F continues for both. §3.1/§3.2: the unbounded mode serves two consumers. §4: the Hermes row becomes deferred. §5: **H6 also moves to the "deferred (experimental)" row**. §5.2.5: Phase 2 needs **H1, H2, H3 and H5**, every listed path, plus H7 once formally defined (§3). §11 C3 and §12 step 3 read "except the D5 A1 exceptions". §7.1/§7.5: `test_hermes` expects the P2-first (unbounded) selection in Phase 2, plus an unbounded-under-boundary case for `context_for_turn` **and** a gate, together. §9: the Phase 2 freeze authorizes B1 and I3 for the non-excepted consumers only. §10: Hermes's P2-first behavior is preserved. **Re-entry rule for Hermes:** both H6a and H6b pass on one hermes-agent pin, plus its own `[layer1-freeze]` amendment and the parity flip; it re-enters independently of Antigravity. **Failure rule:** an H6 failure goes to the owner and blocks no other consumer. |
| **Q2 Amendment A2** | The relaxed reporting clauses and the "land together" departure extend to Hermes as well. |
| **Probe scope Amendment A5** | **H6a and H6b leave the batch order** as `DEFERRED (not run)`. They stay in the §8 summary, are not §6 labels, and never pass. **#829's "batch 2 becomes H6a and H6b" is withdrawn.** The revised sequence is in §4. A4 §4.5.2's at-risk rationale lapses for both deferred paths. |
| **Batch-2 harness README** | The pointer now says the **whole batch-2 harness (H4a, H6a, H6b) is for deferred paths**. It is kept intact, and no batch-3 condition depends on it. D3 (refuted), D4 (T unapproved) and D5 stay recorded. |
| **`docs/integrations/hermes.md`** | One sentence: the T-08 Phase 2 boundary (B1) does not apply to Hermes, and no selection notice is host-visible on it. Status stays Experimental. |
| **ADR-033, Layer 1 freeze, readiness assessment (#823)** | **No change,** for the same reasons as #829 §3. Through the charter amendment, readiness P10 ("H6 BLOCKED (at risk)") becomes "deferred". |

## 3. OpenCode H7: kept as a formal requirement, with no exception

- OpenCode S1 (#824, draft) reuses `resolve_memory` (#821), so it becomes an implicit-discovery consumer when it lands (readiness S1).
- **The owner intends to include it as H7.** That inclusion still needs its own reviewed charter amendment (an OpenCode §4 row and H7 output paths), probe-scope paths and a pin.
- **Neither D5 A1 nor this follow-up names OpenCode.** So once OpenCode is a consumer, Phase 2 cannot freeze without H7 passing, or without a separate owner decision that this proposal does not make.
- This proposal changes nothing in #824 and makes no claim about its coverage. That PR's scope is narrow: verified-new-file Python `write` with `FORBID_LITERAL`. Whether the ContextOS workflow exercises that surface is a separate S1 validation question.

## 4. Revised probe sequence (none of it authorized here)

| Step | Paths | Harness | Status |
|---|---|---|---|
| done | H1a, H1b, H1c | H1 harness | `PASS` (#808) |
| **batch 2** | **H2a** (the D1 targeted re-run), **H2b**, **H5c** | existing: `validation/codex-cli/probe/`, `validation/langgraph/probe/` | not started |
| **batch 3** | **H3a**, **H5a**, **H5b** | new: Kiro, and the Agent SDK with credentials | not started |
| **H7** | OpenCode output paths, still to be defined | to be designed | **formal requirement outstanding.** It is scheduled by owner priority once its charter and probe-scope amendment is accepted, and it does not wait for batches 2 or 3. |
| deferred | H4a, H6a, H6b | #828 harness, kept | `DEFERRED (not run)`; run on concrete need. |

- **A4's positive gate still applies, batch to batch:** batch 3 starts only after every batch-2 path passes, or on an owner decision. A failing label goes to the owner (charter §5).
- **The Phase 2 freeze still needs every listed gate to pass:** H1 (done), H2, H3, H5, and H7 once defined.
- **Order rationale:** with both at-risk paths deferred, A4's reason to front-load them is gone. Batch 2 goes back to the probe scope's original D5 order (existing harnesses first), and the new-harness paths follow.

## 5. What this does not weaken

- **H1, H2, H3 and H5 are unchanged,** with every path, their pins, the one-pin-per-gate rule and the §6 labels.
- **H4a, H6a and H6b are `DEFERRED (not run)`,** never PASS. Neither Antigravity nor Hermes claims host visibility or Phase 2 boundary behavior.
- **Neither consumer's governance drops below `main` today.** Both keep accepted P2-first behavior, and Hermes's explicit `memory=` path is unchanged.
- **The exception is a named list of two.** OpenCode, and every other consumer, has no exception.
- **Readiness gaps S1–S7 all remain open,** and E0 stays separate.
- **Phase 2 stays NOT READY and BLOCKED.**

## 6. Decisions requested of the owner

| # | Decision | Recommendation |
|---|---|---|
| F1 | Add Hermes as the second named D5 A1 consumer, on the P2-first contract | **Yes.** Same reasoning as #829 O1: no new silent skips. |
| F2 | Hermes re-enters only as a whole consumer: H6a and H6b both pass on one pin | **Yes.** One selection feeds both paths (§1). |
| F3 | Withdraw #829 E5. The revised sequence: batch 2 is H2a, H2b and H5c; batch 3 is H3a, H5a and H5b; H7 by owner priority once defined | **Yes.** |
| F4 | Apply #829 §3 and this §2 together in one docs-only amendment PR | **Yes.** One PR avoids an intermediate state where Hermes is still mandatory. |

## 7. Not authorized by this proposal

- applying any amendment, from #829 or from here;
- any runtime, harness, pin, test or evidence change;
- any change to PR #824;
- any probe or live run, including batches 2 and 3, H7, H4a, H6a and H6b;
- installing a host, or using credentials;
- Hermes candidate T;
- treating any deferred path as PASS, or changing any earlier label: H1 stays `PASS`, G3 stays `PARTIAL`;
- Phase 2 implementation, or any release.
