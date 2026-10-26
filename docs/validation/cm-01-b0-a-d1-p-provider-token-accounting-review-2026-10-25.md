# CM-01-B0-A D1-P — Provider Usage / Token Accounting Evidence Review

**Status:** PROVIDER-DOCUMENTATION REVIEW ONLY — no snapshot selected, no live API usage verified, no model call authorized, no D1-C freeze.
**Date checked:** 2026-10-25.
**Scope:** CM-01 B0-A issue #656, parent #640.
**Governance:** D0 #654 (merged `8060b9bc`); D1 design-resolution #655 (merged `4b8471149d49f6f4a2a4ddfd0d3601d59355c337`); ADR-017/022/023/027; B0-M remains mechanical-only PASS/VERIFIED.
**Sources:** official provider API documentation as available on the date above. This is documentary evidence, **not** a verified production/provider response, availability confirmation or permission to access credentials. The merged [D1 Erratum 1](./cm-01-b0-a-d1-erratum-1-proposal-2026-10-25.md) (PR #664) governs E-2 hard-gate attribution and E-4 cache-invariant token accounting; this document remains an unverified provider mapping review.

## 1. What the primary endpoint needs

One scenario-arm execution may involve multiple model API calls. The primary total must sum **all non-overlapping provider-reported input and output tokens** across every model request, including tool-call turns, code-generation turns, final response and infrastructure retries with reportable tokens.

The unit is **provider-reported token volume**, not billed cost, model-visible text characters, MCP bytes, local tokenizer output or the count of tool calls. Model-generated code and schema/prompt overhead count through provider-reported model usage; do not add a separate guessed number of "code tokens" or "tool schema tokens" if they are already part of input/output totals.

Use a **single pinned provider endpoint and model snapshot for both arms** in any approved confirmatory benchmark. A provider comparison is for selecting an endpoint and designing adapters, **not** for combining different provider usage schemes in one paired estimator.

Every provider request is recorded with exact model ID/snapshot, prompt/tool schema hashes, request ID, response ID, service tier if present, stream/nonstream mode, cache configuration, response/stop status, retry/recovery status, and an unmodified source usage object (secret-free). The normalized value includes a provenance field naming the mapping version.

### Normalized model request record (proposed, not implementation)

`request_id, scenario_id, repeat_id, arm, provider, endpoint, model_snapshot,
model_request_sequence, source_usage, source_usage_complete,
normalized_input_total, normalized_output_total, normalized_total,
cache_input_read, cache_input_written, thinking_or_reasoning_subset,
stop_reason, response_complete, mapping_version, mapping_errors`

The primary per-arm total is the sum of `normalized_total` across **all attempted provider requests** associated with that arm execution. If any attempted request has incomplete or irreconcilable usage, flag the arm and planned pair incomplete; `BENEFIT` and `NO-BENEFIT` cannot be awarded. Do not interpret missing usage as zero. Use the three-class failure attribution and correctness non-inferiority rule in merged D1 Erratum 1 proposal, E-2: harness-integrity failure (either arm) and treatment-attributable fabrication retain zero tolerance; ordinary wrong/missing identity and format errors use the paired correctness gate. Preserve the raw token ledger regardless of answer correctness.

## 2. Provider-specific mapping: documentary candidates

### Candidate A: Anthropic Messages API

Official documentation: https://platform.claude.com/docs/en/api/messages/create and https://platform.claude.com/docs/en/api/typescript/messages

Published response usage fields include:
- `input_tokens` — one input component.
- `cache_creation_input_tokens` — input tokens used in cache creation (separate additive input component).
- `cache_read_input_tokens` — input tokens read from prompt cache (separate additive input component).
- `output_tokens` — model output total.
- `output_tokens_details.thinking_tokens` — a **subset** of `output_tokens`, not an additional total.
- `cache_creation` ephemeral-duration breakdown — a **breakdown** of the cache-creation field, not an additional token component.

**Documentary candidate normalization:**

`normalized_input_total = input_tokens + cache_creation_input_tokens + cache_read_input_tokens`
`normalized_output_total = output_tokens`
`normalized_total = normalized_input_total + normalized_output_total`

This matches Anthropic's published statement that total input is the sum of the three input components. Add thinking tokens again **never**. Non-token `server_tool_use` counts are not input/output tokens and are excluded from the primary total.

**To verify before approval:** when components can be null/omitted, exact semantic meaning of absence for the chosen endpoint/snapshot; streamed terminal-usage completeness; response failure/timeout semantics; prompt-cache controls, cache read/write counters, raw body and header privacy handling; identical read-only tool function support in both arms. Do not silently turn a missing category into zero.

### Candidate B: OpenAI Responses API

Official documentation:
- https://developers.openai.com/api/reference/resources/responses/methods/create
- https://developers.openai.com/api/docs/guides/reasoning
- https://developers.openai.com/api/docs/guides/prompt-caching
- https://developers.openai.com/api/docs/guides/token-counting

Published response usage includes:
- `input_tokens` — **already includes** cached input tokens.
- `input_tokens_details.cached_tokens` — a **subset** of `input_tokens`.
- `input_tokens_details.cache_write_tokens` where available — cache-write **breakdown of input**, not a second additive input total.
- `output_tokens` — **already includes** reasoning tokens.
- `output_tokens_details.reasoning_tokens` — a **subset** of `output_tokens`.
- `total_tokens` — the top-level provider-reported model total.

**Documentary candidate normalization:**

`normalized_input_total = input_tokens`
`normalized_output_total = output_tokens`
`normalized_total = input_tokens + output_tokens`

When the endpoint returns `total_tokens`, assert `normalized_total == total_tokens`. **Do not add** cached, cache-write or reasoning subsets to those totals.

**To verify before approval:** exact response object for the chosen immutable snapshot; whether `usage` can be absent on failed/streamed/incomplete responses; cache policy and cache-write behavior of the chosen model; whether prompt caching can actually be disabled symmetrically; support for the same read-only function-calling and structured final-answer controls for both arms.

### Critical non-interchangeability

Anthropic reports cache-read and cache-create input tokens as *separately additive fields* relative to `input_tokens`; OpenAI's Responses usage includes cache tokens within `input_tokens`. Likewise, thinking/reasoning is a breakdown of output, not extra output. A generic "sum every numeric field" implementation is **wrong** and could reverse the benchmark conclusion.

The mappings above are **candidate formulas grounded in documentation**; the chosen provider's exact endpoint, SDK version and live responses still require separately authorized validation. Do not treat this document as evidence that a model exists, an API credential is present, or a token ledger has passed runtime tests.

## 3. Acceptance checks for an eventual provider adapter

Before any model-mediated pilot, independent model/metrics review must approve:

1. Model/endpoint snapshot and exact SDK/API schema, including provider-returned model ID versus requested alias.
2. Raw-usage source retention and field-level normalized mapping with **no overlaps**.
3. Complete provider-reported usage for successful, tool-use, incomplete, streamed and failed response classes. Unreported failed-request tokens produce `INCONCLUSIVE`, not zero.
4. Token subtotal reconciliation; cache and reasoning subcategories do not exceed their parent totals; missing required components fail mapping.
5. Same model snapshot, same model parameters and symmetric caching policy in D/C arms, with cache read/write volumes recorded individually. A cache-hit asymmetry alone does not invalidate the primary *token-volume* endpoint if every cache category is accounted exactly once; require identical configured cache policy and an independently verified cache-invariance reconciliation (merged D1 Erratum 1 proposal, E-4). If mapping is not invariant or complete, the primary metric is INCONCLUSIVE.
6. Every model-generated code attempt, tool-call turn, retry and final-answer request included once in the arm ledger; zero post-hoc omissions.
7. Equivalent model-visible functional affordances, while deliberately recording inherent direct-tool vs Code Mode wrapper/tool-schema differences as part of the bundled interface intervention.
8. Identical response schema/quality rules across both arms; exact decision identity remains a harder gate than efficiency.
9. Secret redaction, safe retention, provider metadata integrity, and a deterministic example-usage self-check with official-schema synthetic data only.
10. Independent review of the mapping, no primary-metric change after the preregistration freeze.

A future *authorized* live calibration response must validate the mapping. Synthetic examples can validate the arithmetic only; they do not prove real endpoint completeness.

## 4. Provider/model selection register (unresolved)

| Parameter | Documentary status | Required decision / evidence |
|---|---|---|
| Candidate provider | Anthropic and OpenAI usage schemas reviewed | Human selects one for first B0-A experiment |
| Specific immutable model snapshot | **BLOCKED** | Confirm documented, directly requestable stable ID; pin response model ID |
| Endpoint, API/SDK versions | **BLOCKED** | Approve and pin before model API test |
| Function/tool call support | Provider supports tool/function use in general | Validate chosen schema on both arms and final-answer format |
| Decoding, reasoning/effort, temperature | **BLOCKED** | Select mutually supported fixed settings, record effective defaults |
| Cache policy | Different documented counting conventions | Approve symmetric policy and direct observed completeness |
| Streaming | **BLOCKED** | Prefer simpler non-streaming for usage if compatible; confirm schema |
| Primary token mapping | **PROPOSED** formulas above | Validate real authorized response and preserve field-by-field mapping |
| Timeouts/retries | **PROPOSED** in D1 | Independent approval; failed usage must be handled |
| Model API permissions and credentials | **NOT AUTHORIZED** | Human approval, custody outside restricted guest |
| Allowed resource cap | **NOT AUTHORIZED** | Human approval before any billable request |
| Reviewer | Unassigned | Name independent model/usage reviewer |

No cross-provider performance, model-quality, latency, efficiency or suitability ranking is established here. **External validity remains one selected model snapshot and one frozen corpus.**

## 5. Outcome of this evidence review

**Documentary token mapping: PROPOSED, with official-field evidence.**
**Provider/snapshot choice: BLOCKED.**
**Runtime token mapping VERIFIED: NO.**
**B0-A pilot/implementation/confirmatory model/API calls: NOT AUTHORIZED.**
**D1-C preregistration: BLOCKED.**

Next step for issue #656: independent human-model reviewer examines this document and the frozen D1 design, then selects the *candidate* provider/model and approved calibration scope. That separate approval is not implied by merging this note.
