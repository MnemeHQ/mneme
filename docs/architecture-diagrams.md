# Mneme HQ architecture diagrams

Mermaid sources for the Mneme HQ architecture set. GitHub renders these inline,
they version with the code, and they export to SVG for the site, decks, and
analyst briefings. The on-site (mnemehq.com) versions are hand-authored inline
SVG using the brand `.diag-*` primitives; these Mermaid sources are the
developer-facing, diff-able source of truth for the same diagrams.

## 1. Where Mneme sits

The single most important diagram: where the engineering governance layer fits
between coding agents and generated code.

```mermaid
flowchart TD
  Dev[Developer]
  Agents["Claude Code / Cursor / Codex"]
  Mneme["Mneme HQ<br/>Engineering Governance Layer for AI Coding Agents"]
  Eval{Policy evaluation}
  Code["Architecturally compliant code"]
  Guidance[Guidance]

  Dev --> Agents --> Mneme
  Mneme --- ADRs[ADRs]
  Mneme --- Standards[Standards]
  Mneme --- Rules[Engineering rules]
  Mneme --- Memory[Project memory]
  ADRs --> Eval
  Standards --> Eval
  Rules --> Eval
  Memory --> Eval
  Eval -->|Allow| Code
  Eval -->|Reject| Guidance
  Guidance -->|retry| Agents
```

## 2. Generation flow

What happens at runtime when an agent generates code under governance.

```mermaid
flowchart TD
  Prompt[Prompt] --> Agent[Agent] --> Ctx[Load context]
  Ctx --> ADRs[ADRs]
  Ctx --> Rules[Engineering rules]
  Ctx --> Memory[Project memory]
  Ctx --> Standards[Standards]
  ADRs --> Gen[Generate]
  Rules --> Gen
  Memory --> Gen
  Standards --> Gen
  Gen --> Check{Governance check}
  Check -->|Pass| Merge[Merge]
  Check -->|Reject| Explain[Explain violation] --> Regen[Regenerate] --> Gen
```

## 3. Engineering governance model

How heterogeneous sources of engineering intent unify into governance the
engine can enforce.

```mermaid
flowchart TD
  Specs[Specifications] --> SG[Structured governance]
  AD[Architecture decisions] --> SG
  CS[Coding standards] --> SG
  PM[Project memory] --> SG
  BP[Best practices] --> SG
  CR[Compliance rules] --> SG
  SG --> Engine[Mneme engine] --> Agents[AI coding agents]
```

## 4. Multi-agent governance

One set of rules, applied identically across every agent a team uses.

```mermaid
flowchart TD
  Cursor[Cursor] --> Mneme[Mneme]
  Claude[Claude Code] --> Mneme
  Codex[Codex] --> Mneme
  OpenHands[OpenHands] --> Mneme
  Goose[Goose] --> Mneme
  Continue[Continue] --> Mneme
  Mneme --> R[Same rules]
  Mneme --> A[Same architecture]
  Mneme --> S[Same standards]
```

## 5. Decision lifecycle

From an architectural decision to enforcement against agent-generated change.

```mermaid
flowchart LR
  W[ADR written] --> Rev[Review] --> Ap[Approve] --> Idx[Mneme indexes]
  Idx --> Req[Agent requests context] --> Enf[Rule enforced] --> Vio[Violation detected]
```

## 6. With vs without Mneme

The comparison that lands fastest in a sales or analyst conversation.

```mermaid
flowchart TD
  subgraph Without["Without governance"]
    direction TB
    P1[Prompt] --> AG[Agent guesses] --> Drift[Architecture drifts] --> RC[Review catches some] --> Prod1[Production]
  end
  subgraph With["With Mneme"]
    direction TB
    P2[Prompt] --> ML[Mneme loads intent] --> AF[Agent follows architecture] --> RV[Review verifies] --> Prod2[Production]
  end
```

## 7. Position in the AI engineering stack

Where engineering governance sits as a layer, alongside CI/CD, testing, and
code review rather than replacing them.

```mermaid
flowchart TD
  App[Applications] --> AICA[AI coding agents]
  AICA --> Mneme["Mneme HQ — Engineering governance layer"]
  Mneme --> PK["Project knowledge: ADRs - Standards - Memory"]
  PK --> Infra["Git - CI/CD - Tests - Infrastructure"]
```

---

**Maintenance:** keep these in sync with the on-site SVG versions. When a
diagram changes, update the Mermaid source here first (it is the diff-able
source of truth), then regenerate or hand-edit the brand SVG on the site.
