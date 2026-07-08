# /concepts/ Fragmentation Audit & Consolidation Plan

**Date:** 2026-07-08
**Author:** Growth ops (audit session)
**Status:** For review — audit + recommendations only. **Nothing merged, redirected, or created by this document.**
**Scope:** The 32 pages under `https://mnemehq.com/concepts/`.

---

## 1. Why this audit exists

The 2026-07-06 Bing Webmaster **AI Performance** capture showed 25 cited `mnemehq.com` pages. Of the **32** `/concepts/` pages, only **3** are cited:

| Cited concept page | Citations |
|---|---|
| `architectural-drift` | 6 |
| `deterministic-enforcement` | (cited) |
| `agentic-ide-governance` | (cited) |

**Leading hypothesis (confirmed by this audit): keyword cannibalization.** Authority for the core query families — *governance*, *drift*, *provenance*, *continuity*, *verification* — is split across a dozen-plus near-synonym pages. No single page accumulates enough topical authority, internal-link equity, or distinctness to become the citable answer for its query family. AI answer engines (and Google) pick **one** best source per intent; when five pages say almost the same thing, none of them wins.

This is deliberately an **audit-first** exercise. The recommendations in §4 are proposed for review. Do **not** execute merges/redirects from this document.

### Method
For each page we captured: `<title>`, `<meta name="description">`, `<h1>`, and the on-page definition capsule. Primary target term is inferred from slug + title + definition. Citation status is per the Bing AI Performance capture above. The 32-slug list was verified against `https://mnemehq.com/sitemap.xml` on 2026-07-08 — **exact match, no drift** from the working list.

---

## 2. Full page inventory (all 32)

Legend — **Cited?**: ✅ cited in AI answers · ⬜ not cited. **Role** (recommended, see §4): 🟢 canonical · 🟡 satellite/long-tail keeper · 🔴 merge/redirect candidate.

| # | Slug | Primary target term / query | Cited? | What it actually covers (one line) | Cluster | Role |
|---|---|---|:--:|---|---|:--:|
| 1 | `architectural-governance` | "architectural governance" / "governance for AI code" | ⬜ | Governance system that encodes team decisions as machine-evaluable constraints enforced at generation time | A · Governance | 🟢 |
| 2 | `governance-infrastructure` | "governance infrastructure" | ⬜ | Platform layer that encodes, distributes, versions, enforces decisions across agents | A · Governance | 🔴 |
| 3 | `ai-governance-infrastructure` | "AI governance infrastructure" | ⬜ | "Deterministic enforcement layer preserving architectural intent" — framed as inevitable next category | A · Governance | 🔴 |
| 4 | `autonomous-software-engineering-governance` | "autonomous software engineering governance" | ⬜ | Enforcement layer preserving constraints across AI-driven execution systems | A · Governance | 🔴 |
| 5 | `model-independent-governance` | "model-independent governance" | ⬜ | Governance rules kept outside any one model/prompt/IDE; repo-native control layer | A · Governance | 🟡 |
| 6 | `governance-before-generation` | "governance before generation" | ⬜ | Enforcement-timing thesis: constrain the agent *before* it writes, not at review | A · Governance | 🟢 |
| 7 | `runtime-governance` | "runtime governance" | ⬜ | Enforcement across long-running autonomous execution environments | A · Governance | 🔴 |
| 8 | `ai-operating-layer` | "AI operating layer" | ⬜ | Coordination layer translating human intent into multi-system execution | A/F · Governance/Paradigm | 🔴 |
| 9 | `architectural-drift` | "architectural drift" | ✅ (6) | Compound degradation in codebase coherence from AI-inconsistent code, propagating uncorrected | B · Drift | 🟢 |
| 10 | `ai-agent-drift` | "AI agent drift" | ⬜ | Agent-side divergence from intended architecture across sessions, providers, context resets | B · Drift | 🔴 |
| 11 | `multi-agent-architectural-drift` | "multi-agent architectural drift" / "parallel coding agents" | ⬜ | Divergence when multiple parallel agents each make locally reasonable changes | B · Drift | 🟡 |
| 12 | `intent-debt` | "intent debt" | ⬜ | Gap between what a system should preserve and what agents are actually constrained to follow | B · Drift | 🟡 |
| 13 | `governance-provenance` | "governance provenance" | ⬜ | Per-rule lineage: trace each active rule back to ADR, supersession chain, originating discussion | C · Provenance | 🔴 |
| 14 | `enforcement-provenance` | "enforcement provenance" | ⬜ | Every verdict traces to decision record + precedence rule + source ADR — a citable chain | C · Provenance | 🟢 |
| 15 | `artifact-provenance` | "artifact provenance for AI agents" | ⬜ | Record of plans/diffs/screenshots/test outputs from agent runs; review trails vs governance | C · Provenance | 🟡 |
| 16 | `governance-propagation` | "governance propagation" | ⬜ | A single compiled decision reaches every agent/CI run with identical semantics + verdict | C · Provenance | 🔴 |
| 17 | `deterministic-enforcement` | "deterministic enforcement" | ✅ | Same governance check → same verdict for same inputs, always | D · Enforcement | 🟢 |
| 18 | `verification-contracts` | "verification contracts" | ⬜ | Pre-registered, machine-evaluable assertions about what a check must prove | D · Enforcement | 🟢 |
| 19 | `agent-verification` | "agent verification" | ⬜ | Proving an autonomous run preserved intent, constraints, invariants — not just that it completed | D · Enforcement | 🔴 |
| 20 | `precedence-semantics` | "precedence semantics" | ⬜ | How a governance system resolves conflicts when two decisions apply to one file | D · Enforcement | 🟡 |
| 21 | `architectural-compiler` | "architectural compiler" | ⬜ | Pipeline converting ADRs into machine-evaluable constraint records (parse→validate→resolve→emit→enforce) | D · Enforcement | 🟡 |
| 22 | `executable-architectural-intent` | "executable architectural intent" / "maintaining architectural intent" | ⬜ | Knowledge promoted from documentation into enforceable constraints binding agents at generation | D · Enforcement | 🟢 |
| 23 | `decision-continuity` | "decision continuity" | ⬜ | Architectural decisions stay enforced across agents, sessions, time | E · Continuity | 🟢 |
| 24 | `multi-agent-continuity` | "multi-agent continuity" | ⬜ | Decisions persist across agents so none re-derives what the team already decided | E · Continuity | 🔴 |
| 25 | `reliable-delegation` | "reliable delegation" | ⬜ | Operating model: delegate to agents only when work is verifiably inside constraints | E · Continuity | 🟡 |
| 26 | `ai-native-sdlc` | "AI-native SDLC" | ⬜ | Software delivery designed from first principles for agents as primary generators | F · Paradigm | 🟡 |
| 27 | `agentic-development` | "agentic development" (+ "agent-first development") | ⬜ | Paradigm where AI agents are the primary code generators | F · Paradigm | 🟢 |
| 28 | `objective-driven-development` | "objective-driven development" | ⬜ | Define a desired outcome; an agent iterates code until the condition is met | F · Paradigm | 🟡 |
| 29 | `spec-driven-development` | "spec-driven development" | ⬜ | Structured spec as source of truth for implementation | F · Paradigm | 🟡 |
| 30 | `execution-surfaces` | "execution surfaces" | ⬜ | Every place an agent leaves an artifact (code, commits, PRs, CI, manifests, docs) | F · Paradigm | 🔴 |
| 31 | `agentic-ide-governance` | "agentic IDE governance" | ✅ | Control layer keeping autonomous agents aligned inside IDEs (Antigravity, Cursor, Claude Code, Copilot) | G · IDE governance | 🟢 |
| 32 | `antigravity-governance` | "antigravity governance" (branded) | ⬜ | Architectural control for agent-first IDEs, Antigravity-specific | G · IDE governance | 🟡 |

**Counts:** 🟢 canonical **10** · 🟡 satellite keeper **11** · 🔴 merge/redirect candidate **11**.

---

## 3. Overlap clusters — where the cannibalization is

### Cluster A — Governance (8 pages) — **the worst cannibalization**
`architectural-governance` · `governance-infrastructure` · `ai-governance-infrastructure` · `autonomous-software-engineering-governance` · `model-independent-governance` · `governance-before-generation` · `runtime-governance` · `ai-operating-layer`

Five of these (`architectural-governance`, `governance-infrastructure`, `ai-governance-infrastructure`, `autonomous-software-engineering-governance`, `runtime-governance`) are **functionally the same definition** — "the enforcement layer that encodes architectural decisions as machine-evaluable constraints and enforces them across AI agents." They differ only in the modifier in front of "governance." An answer engine asked *"what is governance for AI coding agents"* sees five ~equivalent candidates and cites none with confidence. This is the single biggest driver of the under-citation problem.

- **Genuinely distinct within the cluster:** `governance-before-generation` (a *timing* thesis + slogan, not a synonym for the layer) and `model-independent-governance` (a *portability* angle — governance that survives model/IDE swaps). These carry an idea the umbrella page doesn't.
- **Near-duplicate filler:** `governance-infrastructure`, `ai-governance-infrastructure`, `autonomous-software-engineering-governance`, `runtime-governance` — each is the umbrella concept with a different adjective.
- `ai-operating-layer` overlaps both Cluster A and Cluster F (it's a paradigm/coordination framing that resolves into "…becomes a governance system").

### Cluster B — Drift (4 pages)
`architectural-drift` ✅(6) · `ai-agent-drift` · `multi-agent-architectural-drift` · `intent-debt`

`architectural-drift` is the **proven winner** (6 citations) and owns the head term. `ai-agent-drift` is a near-duplicate targeting essentially the same query with a weaker phrasing — it splits equity away from the page that already works. `multi-agent-architectural-drift` targets a *distinguishable* long-tail ("parallel / multiple coding agents"). `intent-debt` is a distinct *framing* (debt metaphor) and a defensible keeper.

### Cluster C — Provenance (4 pages)
`governance-provenance` · `enforcement-provenance` · `artifact-provenance` · `governance-propagation`

`governance-provenance` and `enforcement-provenance` are **near-duplicates** — both mean "trace every rule/verdict back to its source ADR + precedence chain." `artifact-provenance` is genuinely **different** (evidence of what an agent run *did* — plans, diffs, screenshots; the page itself draws the "provenance explains what happened / governance constrains what's allowed" line). `governance-propagation` is about *distribution/consistency* of enforcement — closer to Cluster A/D than to provenance.

### Cluster D — Enforcement & verification mechanism (6 pages)
`deterministic-enforcement` ✅ · `verification-contracts` · `agent-verification` · `precedence-semantics` · `architectural-compiler` · `executable-architectural-intent`

Mostly distinct mechanism concepts, **except** `verification-contracts` vs `agent-verification` — these overlap on the "verification" query (contract = the pre-registered assertion; verification = the act of proving a run conformed). `deterministic-enforcement` is already cited and clearly owns its term. `precedence-semantics`, `architectural-compiler`, and `executable-architectural-intent` are distinct and defensible.

### Cluster E — Continuity (3 pages)
`decision-continuity` · `multi-agent-continuity` · `reliable-delegation`

`decision-continuity` and `multi-agent-continuity` are **near-duplicates** — "decisions persist across agents/sessions/time." `architectural-drift` (the cited page) already links to `decision-continuity`, giving it internal-link equity. `reliable-delegation` is a distinct operating-model concept — keeper.

### Cluster F — AI-native paradigm / SDLC (6 pages, incl. overlap with A)
`ai-native-sdlc` · `agentic-development` · `objective-driven-development` · `spec-driven-development` · `execution-surfaces` · (`ai-operating-layer`)

`spec-driven-development` and `objective-driven-development` are **externally-recognized named methodologies** with independent search demand — keepers, distinct. `agentic-development` and `ai-native-sdlc` overlap on "the AI-native paradigm" head term. `execution-surfaces` is thin and niche. `ai-operating-layer` overlaps here and in Cluster A.

### Cluster G — IDE / agent-platform governance (2 pages)
`agentic-ide-governance` ✅ · `antigravity-governance`

`agentic-ide-governance` is **cited** and is the natural canonical for "governance inside coding IDEs/agents." `antigravity-governance` targets a **branded long-tail** ("Google Antigravity") and is a legitimate satellite — but must point its authority *at* the canonical, not compete with it.

---

## 4. Consolidation plan (PROPOSED — not executed)

**Guiding principle (from positioning memory):** lead vocabulary is **"engineering / architectural guardrails."** *"Governance"* is overloaded (reads as GRC/compliance/model-risk — wrong buyer) and is demoted to *selective/SEO* use. Enemy = **architectural drift**. Category noun = *"Engineering Governance for AI Coding Agents"* (kept selectively for the hero/category surface, not as the lead in every concept). Canonical-term tiebreakers below apply that ranking: prefer **architectural** over generic **AI**; prefer the term that already earns citations; collapse adjective-swap synonyms into one page.

**Capability-honesty guardrail (applies to all canonical copy):** pre-generation enforcement is **shipped**; drift **detection**, conflict detection, and provenance *traces* are **roadmap**. Canonical pages must frame drift as what Mneme *prevents by enforcing decisions at generation time*, not something it auto-detects.

### Cluster A — Governance → collapse 8 into 3
| Page | Recommendation | Rationale |
|---|---|---|
| `architectural-governance` | 🟢 **CANONICAL** (the governance concept) | On-positioning ("architectural"), cleanest definition, natural hub. Absorb the strongest lines from the merged pages. |
| `governance-before-generation` | 🟢 **KEEP — distinct canonical** | Timing thesis + slogan; not a synonym. Cross-link to `architectural-governance`. |
| `model-independent-governance` | 🟡 **KEEP — satellite** (portability angle) | Distinct differentiator (survives model/IDE swaps). Add rel-canonical-style cross-link to `architectural-governance`; trim overlap. |
| `governance-infrastructure` | 🔴 **MERGE → `architectural-governance`**, 301 | Adjective-swap duplicate. Fold "platform layer" framing in as a section. |
| `ai-governance-infrastructure` | 🔴 **MERGE → `architectural-governance`**, 301 | Adjective-swap duplicate; "AI governance" also risks the wrong (model-risk/GRC) query. |
| `autonomous-software-engineering-governance` | 🔴 **MERGE → `architectural-governance`**, 301 | Adjective-swap duplicate. |
| `runtime-governance` | 🔴 **MERGE → `architectural-governance`** (or `agentic-ide-governance`), 301 | "Long-running execution" angle can be one section of the canonical. |
| `ai-operating-layer` | 🔴 **MERGE → `architectural-governance`** or `agentic-development`, 301 | Weakest, most abstract; overlaps two clusters. |

### Cluster B — Drift → keep the winner, feed it
| Page | Recommendation | Rationale |
|---|---|---|
| `architectural-drift` | 🟢 **CANONICAL** (proven, 6 citations) | Do not disturb the structure that already earns citations (see Deliverable 3). |
| `ai-agent-drift` | 🔴 **MERGE → `architectural-drift`**, 301 | Near-duplicate splitting equity from the page that already wins. |
| `multi-agent-architectural-drift` | 🟡 **KEEP — satellite** ("parallel agents" long-tail) | Distinguishable intent; subordinate it with a prominent cross-link to `architectural-drift`; trim head-term overlap. |
| `intent-debt` | 🟡 **KEEP** (distinct "debt" framing) | Cross-link to `architectural-drift`. |

### Cluster C — Provenance → collapse the two near-duplicates
| Page | Recommendation | Rationale |
|---|---|---|
| `enforcement-provenance` | 🟢 **CANONICAL** for provenance | More precise (verdict→decision→precedence→ADR chain); "enforcement" is the on-brand mechanism word. |
| `governance-provenance` | 🔴 **MERGE → `enforcement-provenance`**, 301 | Near-duplicate ("per-rule lineage"). |
| `artifact-provenance` | 🟡 **KEEP — distinct concept** | Agent-run evidence / review trails ≠ rule lineage. Cross-link, don't merge. |
| `governance-propagation` | 🔴 **MERGE → `deterministic-enforcement`** (consistency of enforcement) or `architectural-governance`, 301 | It's about identical-verdict distribution — belongs with enforcement, not provenance. |

### Cluster D — Enforcement / verification → one merge only
| Page | Recommendation | Rationale |
|---|---|---|
| `deterministic-enforcement` | 🟢 **CANONICAL** (cited) | Owns its term already. |
| `executable-architectural-intent` | 🟢 **CANONICAL** (maps to grounding query "maintaining architectural intent") | Optimized in Deliverable 3. |
| `verification-contracts` | 🟢 **CANONICAL** for "verification" | Keep; absorb `agent-verification`. |
| `agent-verification` | 🔴 **MERGE → `verification-contracts`**, 301 | Overlaps on the "verification" query. |
| `precedence-semantics` | 🟡 **KEEP** (distinct: conflict resolution) | — |
| `architectural-compiler` | 🟡 **KEEP** (distinct: ADR→constraint pipeline) | Cross-link to `executable-architectural-intent`. |

### Cluster E — Continuity → collapse near-duplicate
| Page | Recommendation | Rationale |
|---|---|---|
| `decision-continuity` | 🟢 **CANONICAL** | Broader, cleaner; already receives internal links from `architectural-drift`. |
| `multi-agent-continuity` | 🔴 **MERGE → `decision-continuity`**, 301 | Near-duplicate. |
| `reliable-delegation` | 🟡 **KEEP** (distinct operating model) | — |

### Cluster F — Paradigm / SDLC → keep the named methodologies, thin the rest
| Page | Recommendation | Rationale |
|---|---|---|
| `agentic-development` | 🟢 **CANONICAL** for the paradigm | **Also the redirect target for the (nonexistent) slug `agent-first-development`** — map that term here, do not create a new page. |
| `spec-driven-development` | 🟡 **KEEP** (named methodology, external demand) | — |
| `objective-driven-development` | 🟡 **KEEP** (named methodology) | — |
| `ai-native-sdlc` | 🟡 **KEEP** but differentiate from `agentic-development` | Overlaps the paradigm head term; sharpen to the "SDLC redesign" angle or merge if overlap persists. |
| `execution-surfaces` | 🔴 **MERGE → `architectural-governance`** or `agentic-ide-governance`, 301 | Thin/niche; a section elsewhere serves it. |

### Cluster G — IDE governance → keep both, subordinate the brand page
| Page | Recommendation | Rationale |
|---|---|---|
| `agentic-ide-governance` | 🟢 **CANONICAL** (cited) | — |
| `antigravity-governance` | 🟡 **KEEP — branded satellite** | Point authority at `agentic-ide-governance` via prominent cross-link; keep the "Antigravity" long-tail. |

### Net effect (proposed)
- **32 → ~21 live concept pages** (10 canonical + 11 satellites), with **11 pages 301-redirected** into their canonical.
- Every redirect consolidates internal-link equity and topical authority onto one page per intent — the mechanism that lets a single page cross the citation threshold, as `architectural-drift` already has.

---

## 5. Gap analysis — missing definitional pages

The cluster map exposes two high-intent terms with **no canonical concept page**, both on the preferred lead vocabulary:

| Candidate slug | Verdict | Rationale |
|---|---|---|
| `ai-coding-agent-guardrails` | **CREATE — new canonical** (highest priority) | Directly matches the **#1 lead phrase ("guardrails")** from `mneme-messaging-vocabulary`. No concept page owns "guardrails" today despite it being the primary vocabulary. **Note:** an *insight* already exists at `/insights/ai-coding-agent-guardrails/` — the new concept page should be the **definitional** counterpart (what it is), cross-linked to that insight (the argument). This is the single clearest content gap. |
| `engineering-governance-for-ai-agents` | **FOLD, do not create a near-duplicate** | This is the **category noun** — but standing it up as a separate `/concepts/` page would re-open the exact Cluster A cannibalization we're closing (it is a synonym of `architectural-governance`). Recommendation: make it the **H1/category framing on the canonical `architectural-governance` page** (or a dedicated `/engineering-governance/` category/pillar page *outside* `/concepts/`), not a 12th governance concept page. Reserve "engineering governance" for that single SEO surface. |

Do **not** create either page in this task — flagged for the post-review build phase.

---

## 6. Sequencing (recommended, for after review)
1. **Approve** canonical picks and redirect map (this doc).
2. **Optimize the 2 proven canonicals** — done in this PR (`architectural-drift`, `executable-architectural-intent`).
3. Apply the definition-block template to the remaining 🟢 canonicals (one cluster at a time), absorbing the best lines from their 🔴 merge sources *before* redirecting.
4. Execute 301s for the 11 🔴 pages; verify no orphaned internal links; update `sitemap.xml`.
5. Build the `ai-coding-agent-guardrails` concept page (§5).
6. Re-capture Bing AI Performance in ~4–6 weeks; measure citation lift on the consolidated canonicals.

**Do not proceed past step 2 until this plan is reviewed.**
