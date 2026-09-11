# P1.2 Architecture Audit Redesign — Design Document

> **Amendment (2026-09-11, ADR-023):** after the first Design Partner
> diagnostic exposed that tier classification depended on record shape
> (byte-identical decision text changed tier when a structured constraint
> was added) and that Identified Mneme Potential counted only records
> immediately expressible by existing rule types, the tier semantics and
> the Potential formula were amended. Tier intent is now judged from the
> decision text (prescriptive vs advisory); Potential =
> (Mneme-ready + Requires modelling) / protection-relevant. See
> `docs/adr/ADR-023-audit-tier-semantics-and-mneme-potential.md`. The
> sections below record the original P1.2 freeze.

## Executive Summary

The current Architecture Audit reports a single "Coverage" percentage (~5% on Mneme repo) that counts all ADRs, agent instructions, and config evidence in one denominator but only credits directly compilable Mneme rules. This makes well-governed repositories appear almost completely ungoverned.

**Target model:** Three-tier classification (Protected / Mneme-ready / Requires modelling / Guidance) producing two primary metrics:
- **Current Protection** — percentage of *protection-relevant* decisions that already have deterministic protection
- **Identified Mneme Potential** — percentage of *protection-relevant* decisions that have identified Mneme guardrails (Protected + Mneme-ready)

**Semantic invariant:** 100% means every architectural constraint appropriate for deterministic enforcement has protection. Guidance-only intent never dilutes the denominator. Mneme Potential is **earned by findings**, not assumed.

---

## 1. Current Scoring & Data Flow

### 1.1 Existing Governability Assessment (enforcer.py:324–434)

```python
GovernabilityTier = Literal["enforceable", "partial", "guidance"]

@dataclass
class GovernabilityAssessment:
    decision_id: str
    tier: GovernabilityTier
    has_literal_rules: bool              # FORBID_LITERAL
    has_single_term_anti_patterns: bool  # always enforced
    has_multi_term_anti_patterns: bool   # retrieval-gated
    has_no_constraints: bool             # "no X" → WARN
    applicable_paths: tuple[str, ...]
    confidence: float                    # 1.0 / 0.7 / 0.0
```

**Tier logic:**
| Tier | Criteria | Confidence | Enforcement behavior |
|------|----------|------------|---------------------|
| enforceable | FORBID_LITERAL ∨ single-term anti-pattern | 1.0 | Always enforced corpus-wide |
| partial | multi-term anti-pattern ∨ "no X" constraint | 0.7 | Retrieval-gated (top-K) / WARN only |
| guidance | none of the above | 0.0 | Retrieval/context only |

### 1.2 Current "Coverage" Implicit Calculation

No explicit audit command exists. The ~5% figure derives from:
- **Denominator**: All ADRs + agent instructions (CLAUDE.md) + config evidence
- **Numerator**: Only decisions with `has_literal_rules == True` (typed FORBID_LITERAL rules)
- **Missing**: Single-term anti-patterns, CI gates, hooks, shell preflights, deterministic scripts

### 1.3 Benchmark Metrics (benchmark.py / benchmark_report.py)

| Layer | Metric | Purpose |
|-------|--------|---------|
| Layer 1 | Recall@K, Precision@K, Irrelevant Injection Rate | Retrieval quality |
| Layer 2 | Pass Rate (violations caught), WEAK/WEAK_RETRIEVAL | Enforcement effectiveness |
| Enforcement Quality | False Positive Rate (benign controls) | Over-blocking risk |

---

## 2. Recommended Semantic Model

### 2.1 Core Unit: Protection-Relevant Decision (P1.2 Freeze)

**Decision:** The scored unit in P1.2 is a **protection-relevant decision** — an active Decision that declares at least one mechanically enforceable constraint.

**Rationale:** Full semantic constraint extraction (one ADR → multiple discrete constraints) is not yet built. P1.2 classifies each decision according to the *strongest* deterministic protection state found for that decision.

**Limitation (documented in output):** A decision may contain multiple constraints; P1.2 does not yet decompose them independently. Future milestones will move to constraint-level scoring.

### 2.2 Four-Tier Classification (Internal Ontology)

| Internal Tier | User-Facing Label | Definition |
|---------------|-------------------|------------|
| `protected` | **Protected** | Decision has *verified* deterministic enforcement (Mneme typed rule with path match, verified CI gate, verified hook, verified script) |
| `mneme_ready` | **Mneme-ready** | Decision is mechanically enforceable *and* the Audit can identify a concrete Mneme guardrail today (FORBID_LITERAL without path match, single-term anti-pattern with clear literal candidate) |
| `requires_modelling` | **Requires further modelling** | Decision is mechanically enforceable in principle but the Audit cannot yet identify a safe Mneme guardrail (multi-term anti-pattern that could be decomposed, ambiguous "no X" that might be literal-izable) |
| `guidance` | **Guidance** | Decision is *not appropriate* for deterministic enforcement (architectural principles, preferences, contextual guidance, pure prose) |

**Protection-Relevant Decisions** = `protected` + `mneme_ready` + `requires_modelling` (denominator)

**Guidance decisions** are excluded from the denominator entirely.

### 2.3 Determining Tier per Decision

```
FOR EACH active Decision:
  # Step 1: Intent classification (independent of evidence)
  has_typed_rule = any(rule.type == "FORBID_LITERAL" for rule in decision.rules)
  has_single_term_ap = any(_is_literal_rule(ap) for ap in decision.anti_patterns)
  has_multi_term_ap = any(not _is_literal_rule(ap) for ap in decision.anti_patterns)
  has_no_constraint = any(re.match(r"^no\s+", c.strip(), re.IGNORECASE) for c in decision.constraints)

  IF has_typed_rule OR has_single_term_ap:
      intent = "deterministic"      # protection-relevant
  ELIF has_multi_term_ap OR has_no_constraint:
      intent = "deterministic"      # protection-relevant but weaker
  ELSE:
      intent = "guidance"           # NOT protection-relevant

  # Step 2: Protection status (evidence-based)
  IF intent == "guidance":
      tier = "guidance"
  ELSE:
      # Check for verified deterministic enforcement
      verified = check_verified_enforcement(decision)  # Mneme typed rule w/ path match, verified CI, etc.
      IF verified:
          tier = "protected"
      ELSE:
          # Check Mneme-readiness: can we identify a concrete guardrail today?
          mneme_ready = check_mneme_readiness(decision)  # FORBID_LITERAL exists but no path match, or clear single-term AP → literal candidate
          IF mneme_ready:
              tier = "mneme_ready"
          ELSE:
              tier = "requires_modelling"
```

### 2.4 Evidence Confidence (Separate from Intent)

| Evidence Level | Meaning | Used For |
|----------------|---------|----------|
| `verified` | Deterministic enforcement confirmed (Mneme rule applies, CI gate validated, hook validated) | Credits **Protected** |
| `candidate` | Enforcement-like artifact found but linkage uncertain (CI file exists but token match unconfirmed) | Annotates **Mneme-ready** / **Requires modelling** — does not upgrade tier |
| `none` | No enforcement evidence detected | Baseline |

**Key principle:** Intent classification (deterministic vs guidance) and evidence confidence are separate axes. Unverified CI does not make a guidance decision "protectable," and lack of evidence does not make a deterministic decision "guidance."

---

## 3. Formulas

### 3.1 Definitions

| Symbol | Meaning |
|--------|---------|
| `P` | Count of **Protected** decisions (verified enforcement) |
| `M` | Count of **Mneme-ready** decisions (guardrail identified) |
| `R` | Count of **Requires modelling** decisions (enforceable but no guardrail identified) |
| `G` | Count of **Guidance** decisions (excluded from denominator) |
| `PR = P + M + R` | **Protection-Relevant** decisions (denominator) |

### 3.2 Current Protection

```
Current Protection = P / PR × 100%
```

**Interpretation:** Of all decisions that warrant deterministic enforcement, what fraction already has verified protection?

### 3.3 Identified Mneme Potential

```
Identified Mneme Potential = (P + M) / PR × 100%
```

**Interpretation:** If Mneme implemented every *identified* guardrail today, what fraction would be covered? This is **not 100% by definition** — it reflects actual findings.

### 3.4 Protection Gap (Actionable)

```
Protection Gap = (M + R) / PR × 100%
```

**Interpretation:** Decisions that are protection-relevant but not yet protected.

---

## 4. Schema / API Changes

### 4.1 New Types (enforcer.py or new audit.py)

```python
# Internal classification (not all exposed to UI)
DecisionProtectionTier = Literal["protected", "mneme_ready", "requires_modelling", "guidance"]
EvidenceConfidence = Literal["verified", "candidate", "none"]

@dataclass
class DecisionProtectionAssessment:
    decision_id: str
    decision_text: str
    status: Literal["active", "superseded", "deprecated"]
    
    # Intent (determined from decision content alone)
    intent: Literal["deterministic", "guidance"]
    
    # Protection status (evidence-based)
    protection_tier: DecisionProtectionTier
    
    # Evidence
    evidence_confidence: EvidenceConfidence
    evidence_sources: list[str]  # e.g. ["mneme:FORBID_LITERAL", "ci:github-action-name"]
    
    # Mneme-readiness detail
    mneme_guardrail: str | None  # e.g. "FORBID_LITERAL: psycopg2" or None
    
    # Confidence for UI
    confidence: float  # 1.0 protected, 0.7 mneme_ready, 0.4 requires_modelling, 0.0 guidance

@dataclass
class ArchitectureProtectionReport:
    # Counts
    total_decisions: int
    protection_relevant: int          # PR = P + M + R
    protected: int                    # P
    mneme_ready: int                  # M
    requires_modelling: int           # R
    guidance: int                     # G
    
    # Metrics
    current_protection_pct: float     # P / PR
    identified_mneme_potential_pct: float  # (P + M) / PR
    protection_gap_pct: float         # (M + R) / PR
    
    # Per-decision breakdown
    decisions: list[DecisionProtectionAssessment]
```

### 4.2 New CLI Subcommand

```bash
mneme audit --memory .mneme/project_memory.json --adr-dir docs/adr [--repo-root .] [--json]
```

**Exit codes:** 0 = success, 1 = warnings (candidate evidence present), 2 = error

### 4.3 JSON Output Schema (`mneme.audit/v1`)

```json
{
  "schema": "mneme.audit/v1",
  "summary": {
    "total_decisions": 14,
    "protection_relevant": 9,
    "protected": 4,
    "mneme_ready": 3,
    "requires_modelling": 2,
    "guidance": 5,
    "current_protection_pct": 44.4,
    "identified_mneme_potential_pct": 77.8,
    "protection_gap_pct": 55.6
  },
  "decisions": [
    {
      "decision_id": "ADR-005",
      "decision_text": "Code-bearing surfaces MUST use lowercase mneme namespace",
      "status": "active",
      "intent": "deterministic",
      "protection_tier": "protected",
      "evidence_confidence": "verified",
      "evidence_sources": ["mneme:FORBID_LITERAL", "ci:check-install-command"],
      "mneme_guardrail": "FORBID_LITERAL: MnemeHQ",
      "confidence": 1.0
    },
    {
      "decision_id": "ADR-002",
      "decision_text": "Internal tooling must not be committed to public repo",
      "status": "active",
      "intent": "deterministic",
      "protection_tier": "mneme_ready",
      "evidence_confidence": "none",
      "evidence_sources": [],
      "mneme_guardrail": "FORBID_LITERAL: internal-tooling",
      "confidence": 0.7
    }
  ]
}
```

---

## 5. UI / Export Changes

### 5.1 Terminal Output (Default)

```
Architecture Protection Audit
==============================

Decisions discovered:        14
Protection-relevant:          9
  Protected today:            4
  Mneme-ready:                3
  Requires further modelling: 2
  Guidance-only:              5

Current Protection:           44%
Identified Mneme Potential:   78%

Per-decision breakdown:
  ADR-005  Brand vs Package Namespace       PROTECTED       (FORBID_LITERAL + CI gate)
  ADR-017  Enforcement Scope                PROTECTED       (FORBID_LITERAL)
  ADR-019  Typed Literal Rule Contract       PROTECTED       (FORBID_LITERAL)
  ADR-020  Path Applicability                PROTECTED       (FORBID_LITERAL + paths)
  ADR-002  Repo Boundary                     MNEME-READY     (single-term AP → literal candidate)
  ADR-010  Automation Artifact Governance    MNEME-READY     (single-term AP → literal candidate)
  ADR-009  Encoding Enforcement              MNEME-READY     (CI candidate; linkage unverified)
  ADR-014  Harness Vocabulary                REQUIRES MODELLING (multi-term prose)
  ADR-001  Positioning & Messaging           GUIDANCE        (principles only)
  ...
```

### 5.2 Markdown Export (`--markdown FILE`) — PR2

GitHub-flavored table + summary, suitable for PR comments or docs.

### 5.3 CI Integration — Deferred

- Exit code 0 always (audit is informational)
- `--fail-below` deferred to post-pilot milestone
- JSON output for dashboarding

---

## 6. Migration & Backward Compatibility

### 6.1 No Breaking Changes

- Existing `assess_governability()` remains unchanged (used by CLI, hook, benchmark)
- New `assess_protection()` function added alongside
- Benchmark suite continues using Layer 1/2 metrics unchanged

### 6.2 Legacy "Coverage" Deprecation

- If any internal code references "coverage percentage," map to `current_protection_pct`
- Document that old metric conflated guidance with enforceable constraints

### 6.3 Decision Status Filtering

- Only `active` decisions count toward protection-relevant
- `superseded`/`deprecated`/`inactive` appear in report with `status` field but excluded from `PR`
- Superseding ADR inherits constraints from superseded (compiler already handles this)

---

## 7. Acceptance Tests

### 7.1 Unit Tests (enforcer.py / new audit.py)

| Test | Expected |
|------|----------|
| Decision with FORBID_LITERAL + matching path → Protected | tier=protected, evidence=verified |
| Decision with FORBID_LITERAL but no path match → Mneme-ready | tier=mneme_ready, guardrail=FORBID_LITERAL |
| Single-term anti-pattern ("psycopg2") → Mneme-ready | tier=mneme_ready, guardrail=FORBID_LITERAL: psycopg2 |
| Multi-term anti-pattern ("open() without encoding") → Requires modelling | tier=requires_modelling |
| "no postgres" constraint → Requires modelling | tier=requires_modelling (could be literalized) |
| Decision with no constraints → Guidance | tier=guidance, not protection-relevant |
| External CI gate with verified token match → Protected | evidence=verified, tier=protected |
| External CI gate with unverified match → Mneme-ready (not Protected) | evidence=candidate, tier=mneme_ready |

### 7.2 Integration Tests (CLI)

| Scenario | Expected Output |
|----------|-----------------|
| Mneme repo (current state) | ~14 decisions, 9 protection-relevant, 4 protected, 3 mneme-ready, 2 requires modelling, 5 guidance |
| Empty memory file | 0 decisions, 0 protection-relevant, Current Protection=N/A |
| Decision with only Guidance constraints | protection-relevant=0, Current Protection=N/A (display "—") |

### 7.3 Golden Master Test

- Freeze current Mneme repo audit output as baseline
- Re-audit after each Mneme rule addition shows Current Protection increasing, Protection Gap decreasing

### 7.4 Semantic Contract Tests (Must Pass)

| Test | Requirement |
|------|-------------|
| Guidance exclusion | A decision classified as `guidance` **never** enters `protection_relevant` denominator (Current Protection or Identified Mneme Potential). |
| Evidence cannot upgrade Guidance | Candidate/verified enforcement evidence on a `guidance` decision does not change its tier — intent classification is evidence-independent. |
| Mneme-ready requires explicit guardrail | A decision cannot be `mneme_ready` unless `mneme_guardrail` field is non-empty and describes a concrete deterministic mechanism (e.g., "FORBID_LITERAL: <token>"). |
| Reconstructability | Every percentage in `summary` must be exactly recomputable from the `decisions` array alone (no hidden state). |

---

## 8. Files / Modules Likely Affected

| File | Change Type |
|------|-------------|
| `mneme/enforcer.py` | Add `assess_protection()` + `DecisionProtectionAssessment`, `ArchitectureProtectionReport` types |
| `mneme/cli.py` | Add `audit` subcommand |
| `mneme/adr_import.py` | Reuse `compile_for_import()` for ADR-sourced decisions |
| `mneme/schemas.py` | No change (Decision model already supports rules/constraints) |
| `mneme/path_selectors.py` | Reuse `evaluate_path_selectors()` for path-scoped rule credit |
| `tests/test_enforcer.py` | Add `test_assess_protection_*` |
| `tests/test_cli_audit.py` | New test file for audit command |
| `docs/adr/ADR-XXX-architecture-audit-model.md` | New ADR documenting the model |

---

## 9. Explicitly Deferred (Post-P1.2)

| Item | Reason |
|------|--------|
| Semantic constraint extraction (parsing prose → discrete constraints) | Requires LLM or complex NLP; not in current architecture |
| Cross-repo enforcement evidence (monorepo, submodules) | Out of scope for single-repo pilot |
| Historical trend tracking (Protection over time) | Needs persistence layer; M2+ |
| Drift detection (constraints added but not enforced) | Requires ADR change detection; M2+ |
| Weighted constraints (criticality, blast radius) | All decisions equal in P1.2 |
| Auto-fix suggestions (generate FORBID_LITERAL from anti-pattern) | LLM-assisted; M2+ |
| Dashboard / web UI | CLI + JSON sufficient for pilot |
| `--fail-below` CI gate | Premature for scoring model still being validated |

---

## 10. Recommended Implementation Sequence

### PR 1: Semantic Model + Audit Results (~350 lines)

**Files:**
- `mneme/enforcer.py` — add `assess_protection()`, `DecisionProtectionAssessment`, `ArchitectureProtectionReport`
- `mneme/cli.py` — add `audit` subcommand with terminal + JSON output
- `tests/test_enforcer.py` — unit tests for `assess_protection()`
- `tests/test_cli_audit.py` — integration tests

**Scope:** Decision-level assessment using existing `GovernabilityAssessment` + path selector evaluation + external evidence detection (CI workflows, hooks, scripts). Four-tier classification with separate intent/evidence axes.

**Validation:** Run `mneme audit` on Mneme repo → matches expected output in §5.1.

### PR 2: Product Surfaces (~200 lines)

**Files:**
- `mneme/cli.py` — add `--markdown` flag
- `mneme/audit_report.py` (new) — `format_audit_markdown()`, `format_audit_json()`
- `docs/adr/ADR-XXX-architecture-audit-model.md` — formalize the model
- `CHANGELOG.md` — entry for P1.2

**Scope:** Polish output formats, document the semantic model, baseline persistence for re-audit comparison.

---

## 11. Example Output for Mneme Repo (Projected)

```
$ mneme audit --memory .mneme/project_memory.json --adr-dir docs/adr

Architecture Protection Audit
==============================

Decisions discovered:        14
Protection-relevant:          9
  Protected today:            4
  Mneme-ready:                3
  Requires further modelling: 2
  Guidance-only:              5

Current Protection:           44%
Identified Mneme Potential:   78%

Per-decision breakdown:
  ADR-005  Brand vs Package Namespace       PROTECTED       (FORBID_LITERAL + scripts/check_install_command.py)
  ADR-017  Enforcement Scope                PROTECTED       (FORBID_LITERAL: "main", "enforcement")
  ADR-019  Typed Literal Rule Contract       PROTECTED       (FORBID_LITERAL rules)
  ADR-020  Path Applicability                PROTECTED       (FORBID_LITERAL with include_paths)
  ADR-002  Repo Boundary                     MNEME-READY     (anti_pattern: "internal tooling" → literal candidate)
  ADR-010  Automation Artifact Governance    MNEME-READY     (anti_pattern: "claude/" prefix → literal candidate)
  ADR-009  Encoding Enforcement              MNEME-READY     (CI script detected; linkage candidate)
  ADR-014  Harness Vocabulary                REQUIRES MODELLING (multi-term prose constraints)
  ADR-001  Positioning & Messaging           GUIDANCE        (principles, no mechanical constraints)
```

This design is minimal, evidence-based, deterministic, explainable to a design partner, and supports baseline → re-audit comparison in M1. The Mneme Potential metric is earned by findings, not assumed.