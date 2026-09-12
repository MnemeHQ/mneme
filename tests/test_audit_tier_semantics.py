"""P1.2 Architecture Audit tier semantics (ADR-026 hardening).

Regression tests for the two P0 defects found by the first real Design
Partner diagnostic (sagarika29/ai-system-architect):

1. Tier classification must derive from what the architectural decision
   MEANS (deterministic requirement vs advisory statement), not from which
   structured fields happen to be populated. Adding a syntactic structure
   or a constraint field must not, by itself, move a decision out of
   guidance.

2. "Identified Mneme Potential" must count decisions that are
   deterministically enforceable in principle (Mneme-ready + Requires
   modelling), not only decisions immediately expressible by existing rule
   types. Guidance never enters the numerator or the denominator.

The Design Partner boundaries corpus is used as a regression fixture from
docs/architecture-boundaries-base.md (sagarika29/ai-system-architect);
the repository itself is not modified and no partner-specific wording is
special-cased in the implementation.
"""
import json
from pathlib import Path

from mneme.enforcer import (
    assess_protection,
    generate_protection_report,
    propose_literal_rule,
)
from mneme.schemas import Decision, Rule


# ── Part C.1: structure invariance ───────────────────────────────────────────

ADVISORY_TEXT = "Prefer simple architectures where practical."
DETERMINISTIC_TEXT = (
    "Generated output must contain all required architecture sections; "
    "otherwise fail closed."
)


def test_structural_constraint_cannot_flip_advisory_text():
    """Byte-identical guidance text stays Guidance when a structural
    constraint field is added (P0 finding #1, guidance direction)."""
    without = assess_protection(Decision(id="d1", decision=ADVISORY_TEXT))
    with_constraint = assess_protection(Decision(
        id="d2",
        decision=ADVISORY_TEXT,
        constraints=["no empty descriptions"],
    ))

    for report in (without, with_constraint):
        assert report.intent == "guidance"
        assert report.protection_tier == "guidance"
        assert report.mneme_guardrail is None

    report = generate_protection_report([
        Decision(id="d1", decision=ADVISORY_TEXT),
        Decision(id="d2", decision=ADVISORY_TEXT, constraints=["no empty descriptions"]),
    ])
    assert report.guidance == 2
    assert report.protection_relevant == 0
    assert report.current_protection_pct == 0.0
    assert report.identified_mneme_potential_pct == 0.0


def test_deterministic_text_tier_stable_under_structural_constraint():
    """Byte-identical deterministic text keeps its tier when a structural
    constraint field is added — structure alone changes nothing."""
    without = assess_protection(Decision(id="d1", decision=DETERMINISTIC_TEXT))
    with_constraint = assess_protection(Decision(
        id="d2",
        decision=DETERMINISTIC_TEXT,
        constraints=["no empty descriptions"],
    ))

    for report in (without, with_constraint):
        assert report.intent == "deterministic"
        assert report.protection_tier == "requires_modelling"
        assert report.mneme_guardrail is None


def test_advisory_statement_remains_guidance():
    """A truly advisory statement is Guidance (evidence-independent)."""
    report = assess_protection(Decision(
        id="d1",
        decision="Prefer simple architectures where practical.",
        rationale="Complexity budget",
    ))
    assert report.intent == "guidance"
    assert report.protection_tier == "guidance"


def test_deterministic_text_without_rule_type_is_requires_modelling():
    """A genuinely deterministic architectural requirement is
    Requires-modelling even when no supported rule type can encode it."""
    report = assess_protection(Decision(id="d1", decision=DETERMINISTIC_TEXT))
    assert report.intent == "deterministic"
    assert report.protection_tier == "requires_modelling"
    assert report.mneme_guardrail is None

    aggregate = generate_protection_report([report and Decision(
        id="d1", decision=DETERMINISTIC_TEXT,
    )])
    assert aggregate.protection_relevant == 1
    assert aggregate.requires_modelling == 1
    assert aggregate.guidance == 0


def test_literal_prohibition_is_mneme_ready_from_text_alone():
    """A supported deterministic literal prohibition is Mneme-ready —
    derived from the decision text without structured fields."""
    decision = Decision(
        id="d1",
        decision="Generated recommendations must not use the term `seamless`.",
    )
    report = assess_protection(decision)
    assert report.intent == "deterministic"
    assert report.protection_tier == "mneme_ready"
    assert report.mneme_guardrail == "FORBID_LITERAL: seamless"

    proposal = propose_literal_rule(decision)
    assert proposal is not None
    assert proposal.type == "FORBID_LITERAL"
    assert proposal.value == "seamless"
    assert proposal.include_paths is None


def test_literal_prohibition_stays_mneme_ready_with_field_backing():
    """The pre-existing path (single-term anti-pattern field) still yields
    Mneme-ready with the same guardrail."""
    decision = Decision(
        id="d1",
        decision="Generated recommendations must not use the term `seamless`.",
        anti_patterns=["seamless"],
    )
    report = assess_protection(decision)
    assert report.protection_tier == "mneme_ready"
    assert report.mneme_guardrail == "FORBID_LITERAL: seamless"
    assert propose_literal_rule(decision).value == "seamless"


def test_typed_rule_is_protected_regardless_of_text():
    """Installed deterministic enforcement is Protected — the PROTECTED
    definition is evidence-linked, independent of prose."""
    decision = Decision(
        id="d1",
        decision=ADVISORY_TEXT,
        rules=[Rule(type="FORBID_LITERAL", value="sqlite")],
    )
    report = assess_protection(decision)
    assert report.protection_tier == "protected"
    assert report.evidence_confidence == "verified"


def test_interpretation_needing_prohibition_stays_requires_modelling():
    """A deterministic prohibition whose literal is not explicit is never
    guessed into a Mneme-ready guardrail from text alone."""
    decision = Decision(
        id="d1",
        decision="The service must not depend on external database infrastructure.",
    )
    report = assess_protection(decision)
    assert report.intent == "deterministic"
    assert report.protection_tier == "requires_modelling"
    assert report.mneme_guardrail is None


# ── Mixed advisory + prescriptive wording (ADR-026 precedence) ───────────────

# Qualified/advisory wording must not become deterministic merely because it
# also contains words such as `must`, `never`, or `enforce`.
MIXED_ADVISORY_TEXTS = [
    "We should never use SQLite.",
    "Where practical, services must reject invalid input.",
    "Consider whether this must be enforced.",
    "We should consider using SQLite.",
]

# Unequivocal requirements (no advisory qualifier) remain deterministic.
UNEQUIVOCAL_TEXTS = [
    "The system must reject invalid input.",
    "The pipeline never deploys unvalidated changes.",
]


def test_mixed_advisory_wording_does_not_become_deterministic():
    """Advisory wording outranks prescriptive markers: qualified prose stays
    Guidance even when it contains `must`, `never`, or `enforce`."""
    for text in MIXED_ADVISORY_TEXTS:
        report = assess_protection(Decision(id="d1", decision=text))
        assert report.intent == "guidance", text
        assert report.protection_tier == "guidance", text
        assert report.mneme_guardrail is None, text


def test_unequivocal_requirements_remain_deterministic():
    """Unequivocal `must` requirements and `never` prohibitions (no advisory
    qualifier) remain deterministic."""
    for text in UNEQUIVOCAL_TEXTS:
        report = assess_protection(Decision(id="d1", decision=text))
        assert report.intent == "deterministic", text
        assert report.protection_tier == "requires_modelling", text


def test_contraction_prohibition_remains_deterministic():
    """A `can't` prohibition is not neutralized by the advisory `can`
    marker — the lookahead keeps prohibitions prescriptive."""
    report = assess_protection(Decision(
        id="d1",
        decision="Services can't depend on postgres directly.",
    ))
    assert report.intent == "deterministic"
    assert report.protection_tier == "requires_modelling"


def test_advisory_prose_with_installed_typed_rule_is_protected():
    """Installed deterministic enforcement is authoritative: a decision with
    an active typed rule is Protected regardless of advisory prose (ADR-026
    enforcement precedence), while descriptive structure alone never
    upgrades Guidance."""
    enforced = Decision(
        id="d1",
        decision=ADVISORY_TEXT,
        rules=[Rule(type="FORBID_LITERAL", value="sqlite")],
    )
    report = assess_protection(enforced)
    assert report.protection_tier == "protected"
    assert report.evidence_confidence == "verified"


# ── Part C.5: Potential calculation ──────────────────────────────────────────


def test_potential_covers_ready_and_requires_modelling_not_protected():
    """Potential = (Mneme-ready + Requires modelling) / protection-relevant.

    Guidance is excluded from numerator and denominator; Protected counts
    toward the denominator only."""
    decisions = [
        Decision(
            id="p1",
            decision="Store data in sqlite",
            rules=[Rule(type="FORBID_LITERAL", value="sqlite")],
        ),
        Decision(
            id="m1",
            decision="Generated recommendations must not use the term `seamless`.",
        ),
        Decision(id="r1", decision=DETERMINISTIC_TEXT),
        Decision(id="g1", decision=ADVISORY_TEXT),
    ]
    report = generate_protection_report(decisions)

    active = [d for d in report.decisions if d.status == "active"]
    p = sum(1 for d in active if d.protection_tier == "protected")
    m = sum(1 for d in active if d.protection_tier == "mneme_ready")
    r = sum(1 for d in active if d.protection_tier == "requires_modelling")
    g = sum(1 for d in active if d.protection_tier == "guidance")
    assert (p, m, r, g) == (1, 1, 1, 1)
    assert report.protection_relevant == p + m + r == 3

    assert report.current_protection_pct == round(p / 3 * 100, 1)
    assert report.identified_mneme_potential_pct == round((m + r) / 3 * 100, 1)
    assert report.protection_gap_pct == round((m + r) / 3 * 100, 1)
    assert report.current_protection_pct + report.identified_mneme_potential_pct == 100.0


def test_potential_excludes_guidance_even_when_dominant():
    """A guidance-heavy corpus does not dilute the metric; with no
    protection-relevant decisions the potential is 0, not inflated."""
    decisions = [
        Decision(id=f"g{i}", decision=ADVISORY_TEXT) for i in range(5)
    ]
    report = generate_protection_report(decisions)
    assert report.guidance == 5
    assert report.protection_relevant == 0
    assert report.identified_mneme_potential_pct == 0.0
    assert report.current_protection_pct == 0.0


def test_report_deterministic_for_identical_inputs():
    """Identical inputs produce byte-identical reports."""
    decisions = [
        Decision(
            id="p1",
            decision="Store data in sqlite",
            rules=[Rule(type="FORBID_LITERAL", value="sqlite")],
        ),
        Decision(
            id="m1",
            decision="Generated recommendations must not use the term `seamless`.",
        ),
        Decision(id="r1", decision=DETERMINISTIC_TEXT),
        Decision(id="g1", decision=ADVISORY_TEXT),
    ]
    first = generate_protection_report(decisions)
    second = generate_protection_report(decisions)

    def _snapshot(report):
        return (
            report.schema,
            report.total_decisions,
            report.protection_relevant,
            report.protected,
            report.mneme_ready,
            report.requires_modelling,
            report.guidance,
            report.current_protection_pct,
            report.identified_mneme_potential_pct,
            report.protection_gap_pct,
            tuple(
                (d.id, d.intent, d.protection_tier, d.mneme_guardrail,
                 d.evidence_confidence, tuple(d.evidence_sources))
                for d in report.decisions
            ),
        )

    assert _snapshot(first) == _snapshot(second)


# ── Part D: Design Partner boundaries regression fixture ────────────────────

# Decisions transcribed from docs/architecture-boundaries-base.md in
# sagarika29/ai-system-architect (the diagnostic corpus). Used read-only as
# a regression fixture; the repository itself is untouched.
DP_BOUNDARIES = [
    Decision(
        id="dp-empty-input",
        decision="Reject empty input before calling the model.",
    ),
    Decision(
        id="dp-required-fields",
        decision="Enforce required fields before calling the model.",
    ),
    Decision(
        id="dp-output-contract",
        decision=(
            "Validate the generated output contract and fail closed when "
            "required sections are missing."
        ),
    ),
    Decision(
        id="dp-pattern-selection",
        decision="Architecture pattern selection can remain probabilistic.",
    ),
    Decision(
        id="dp-practical-rule",
        decision="If a decision can be unit tested, it should be deterministic.",
    ),
    Decision(
        id="dp-banned-term",
        decision="Generated recommendations must not use the term `seamless`.",
    ),
    Decision(
        id="dp-protected-namespace",
        decision="Keep the package namespace distinct from the product name",
        rules=[Rule(type="FORBID_LITERAL", value="pip install ai-system-architect")],
    ),
]


def test_design_partner_boundaries_distinguish_all_four_tiers():
    """Audit separates: deterministic+protected vs deterministic and
    representable now vs deterministic needing richer modelling vs actual
    guidance — for the Design Partner boundary corpus."""
    report = generate_protection_report(DP_BOUNDARIES)
    by_id = {d.id: d for d in report.decisions}

    # Deterministic but already protected.
    assert by_id["dp-protected-namespace"].protection_tier == "protected"
    # Deterministic and representable now (existing rule type + scope).
    assert by_id["dp-banned-term"].protection_tier == "mneme_ready"
    assert by_id["dp-banned-term"].mneme_guardrail == "FORBID_LITERAL: seamless"
    # Deterministic but requiring richer modelling.
    for decision_id in ("dp-empty-input", "dp-required-fields", "dp-output-contract"):
        assert by_id[decision_id].protection_tier == "requires_modelling"
        assert by_id[decision_id].intent == "deterministic"
        assert by_id[decision_id].mneme_guardrail is None
    # Actual guidance.
    for decision_id in ("dp-pattern-selection", "dp-practical-rule"):
        assert by_id[decision_id].protection_tier == "guidance"
        assert by_id[decision_id].intent == "guidance"

    assert report.protection_relevant == 5
    assert report.protected == 1
    assert report.mneme_ready == 1
    assert report.requires_modelling == 3
    assert report.guidance == 2
    assert report.current_protection_pct == round(1 / 5 * 100, 1)
    assert report.identified_mneme_potential_pct == round(4 / 5 * 100, 1)


# ── Part C.6: Protect / Validate / strict refusal unchanged ─────────────────

MEMORY_REL = Path(".mneme") / "project_memory.json"
BASE_TS = "2026-01-01T00:00:00Z"


def _write_repo(tmp_path: Path, decisions: list[dict]) -> tuple[Path, Path]:
    """Create a temporary repository with the fixture memory."""
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    memory = root / MEMORY_REL
    memory.parent.mkdir(parents=True)
    memory.write_text(json.dumps({
        "meta": {"name": "adr26", "description": "ADR-026 fixture"},
        "items": [],
        "examples": [],
        "decisions": decisions,
    }, indent=2) + "\n", encoding="utf-8")
    return root, memory


def _memory_decisions(memory: Path) -> list[dict]:
    return json.loads(memory.read_text(encoding="utf-8"))["decisions"]


def _raw_record(decision: Decision) -> dict:
    record = {
        "id": decision.id,
        "decision": decision.decision,
        "rationale": "",
        "scope": [],
        "constraints": list(decision.constraints),
        "anti_patterns": list(decision.anti_patterns),
        "rules": [
            {
                "type": r.type,
                "value": r.value,
                "exclude_paths": list(r.exclude_paths),
                **({"include_paths": list(r.include_paths)} if r.include_paths else {}),
            }
            for r in decision.rules
        ],
        "created_at": BASE_TS,
        "updated_at": BASE_TS,
    }
    return record


def test_protect_loop_and_strict_refusal_unchanged(tmp_path, capsys, monkeypatch):
    """Validate → activate → verify and strict-mode refusal behave exactly
    as before under the amended semantics (Part C.6)."""
    from mneme.protection import (
        activate_protection,
        activation_precheck,
        validate_proposal,
    )

    root, memory = _write_repo(
        tmp_path, [_raw_record(d) for d in DP_BOUNDARIES]
    )
    before = memory.read_text(encoding="utf-8")

    # Mneme-ready candidate: eligible, validation passes.
    banned = Decision(
        id="dp-banned-term",
        decision="Generated recommendations must not use the term `seamless`.",
        memory_path=str(memory),
    )
    pre = activation_precheck(banned, repo_root=root)
    assert pre.eligible is True and pre.tier == "mneme_ready"
    assert pre.proposal.value == "seamless"
    assert validate_proposal(banned, pre.proposal, memory_path=memory).status == "valid"

    # Requires-modelling and Guidance are never candidates.
    contract = next(d for d in DP_BOUNDARIES if d.id == "dp-output-contract")
    assert activation_precheck(contract).eligible is False
    assert activation_precheck(contract).tier == "requires_modelling"
    guidance = next(d for d in DP_BOUNDARIES if d.id == "dp-pattern-selection")
    assert activation_precheck(guidance).eligible is False
    assert activation_precheck(guidance).tier == "guidance"

    # Strict refusal: a failed deterministic validation writes nothing.
    import mneme.protection as protection

    real_check = protection.check_prompt

    def blind_check(text, scored, top=3, input_path=None):
        result = real_check(text, scored, top=top, input_path=input_path)
        result.violations = [
            v for v in result.violations if v.kind != "typed_rule"
        ]
        return result

    baseline_report = generate_protection_report(
        [d for d in DP_BOUNDARIES if d.id != "dp-banned-term"]
    )
    monkeypatch.setattr(protection, "check_prompt", blind_check)
    try:
        outcome = activate_protection("dp-banned-term", memory, repo_root=root)
    finally:
        monkeypatch.undo()
    assert outcome.result == "validation_failed"
    assert outcome.rule_installed is False
    assert memory.read_text(encoding="utf-8") == before

    after_refusal = generate_protection_report(
        [d for d in DP_BOUNDARIES if d.id != "dp-banned-term"]
    )
    assert after_refusal.current_protection_pct == baseline_report.current_protection_pct
    assert after_refusal.identified_mneme_potential_pct == (
        baseline_report.identified_mneme_potential_pct
    )

    # Real activation installs the canonical typed rule and verifies.
    capsys.readouterr()
    outcome = activate_protection("dp-banned-term", memory, repo_root=root)
    assert outcome.result == "verified"
    assert outcome.verification_tier == "protected"
    entry = next(
        e for e in _memory_decisions(memory) if e["id"] == "dp-banned-term"
    )
    assert entry["rules"] == [{"type": "FORBID_LITERAL", "value": "seamless"}]

    # A fresh canonical audit independently observes Protected.
    reloaded = [
        Decision(
            id=e["id"],
            decision=e["decision"],
            anti_patterns=list(e.get("anti_patterns", [])),
            constraints=list(e.get("constraints", [])),
            rules=[Rule(type=r["type"], value=r["value"]) for r in e.get("rules", [])],
        )
        for e in _memory_decisions(memory)
    ]
    fresh = generate_protection_report(reloaded)
    assert fresh.protected == 2
    assert fresh.mneme_ready == 0
    assert fresh.current_protection_pct == round(2 / 5 * 100, 1)
