"""Public decision-intent assessment API (ADR-028).

``mneme.enforcer.assess_decision_intent`` is the supported external boundary
for ADR-026's intent question. The contract proven here:

- clearly prescriptive text returns prescriptive intent;
- clearly advisory text returns advisory intent;
- mixed advisory + prescriptive wording follows ADR-026 precedence
  (advisory outranks prescriptive markers) *inside the API*, so consumers
  only ever see the authoritative verdict — there is no raw-marker surface
  to misread;
- existing prohibition edge cases remain correct;
- the API is deterministic and side-effect free;
- the text-intent equivalence with ``assess_protection`` is proven ONLY for
  the text-only fixture (no structured enforcement material, no installed
  typed rules), with explicit counterexamples showing the equivalence does
  NOT extend to records carrying enforcement material.

The API must remain additive: no retrieval, enforcement, ConflictDetector,
typed-rule, path-applicability, or benchmark behaviour may change because
of it. The tier suites (test_audit_tier_semantics.py, test_enforcer.py)
remaining green is the regression proof.
"""
import dataclasses
import json

import pytest

from mneme.enforcer import (
    DecisionIntent,
    DecisionIntentAssessment,
    assess_decision_intent,
    assess_protection,
)
from mneme.schemas import Decision, Rule

# Unequivocal requirements and prohibitions (no advisory qualifier).
PRESCRIPTIVE_TEXTS = [
    "The system must reject invalid input.",
    "Generated recommendations must not use the term `seamless`.",
    "No postgres.",
    "Services can't depend on postgres directly.",
    "The pipeline never deploys unvalidated changes.",
    "Reject empty input before calling the model.",
    "Fail closed if the output is missing required sections.",
]

# Advisory wording, qualified prose, preference statements.
ADVISORY_TEXTS = [
    "Prefer simple architectures where practical.",
    "We should consider using SQLite.",
    "Teams may keep this decision probabilistic.",
    "Ideally, validation stays flexible.",
]

# Advisory qualifiers outrank prescriptive markers (ADR-026 precedence).
MIXED_ADVISORY_TEXTS = [
    "We should never use SQLite.",
    "Where practical, services must reject invalid input.",
    "Consider whether this must be enforced.",
]

# Descriptive/explanatory prose carries no intent markers either way.
NEUTRAL_TEXTS = [
    "The application needs a primary relational database for persistent data storage.",
    "The service loads the system prompt and calls the model.",
    "",
    "   ",
]

# The text-only fixture for the assess_protection equivalence: plain
# Decision records with no structured enforcement material and no installed
# typed rules.
TEXT_ONLY_TEXTS = PRESCRIPTIVE_TEXTS + ADVISORY_TEXTS + MIXED_ADVISORY_TEXTS + NEUTRAL_TEXTS


def _intent(text: str) -> DecisionIntent:
    return assess_decision_intent(text).intent


class TestPrescriptiveIntent:
    def test_unequivocal_requirements_are_prescriptive(self):
        for text in PRESCRIPTIVE_TEXTS:
            assert _intent(text) == "prescriptive", text

    def test_explicit_quoted_term_ban_is_prescriptive(self):
        text = "Generated recommendations must not use the term `seamless`."
        assert _intent(text) == "prescriptive"
        # The quoted-ban guardrail derivation itself stays with
        # assess_protection / propose_literal_rule: the same text is
        # Mneme-ready there, while the intent API reports the verdict only.
        report = assess_protection(Decision(id="d", decision=text))
        assert report.protection_tier == "mneme_ready"
        assert report.mneme_guardrail == "FORBID_LITERAL: seamless"


class TestAdvisoryIntent:
    def test_qualified_wording_is_advisory(self):
        for text in ADVISORY_TEXTS:
            assert _intent(text) == "advisory", text

    def test_mixed_advisory_wording_is_advisory(self):
        """ADR-026 precedence is applied INSIDE the API: a prescriptive
        word inside qualified prose never yields a prescriptive verdict,
        and the public surface carries no raw marker a consumer could
        check instead of the precedence-aware answer."""
        for text in MIXED_ADVISORY_TEXTS:
            assessment = assess_decision_intent(text)
            assert assessment.intent == "advisory", text
            assert not hasattr(assessment, "prescriptive"), text
            assert not hasattr(assessment, "advisory"), text


class TestNeutralIntent:
    def test_descriptive_prose_has_no_intent_markers(self):
        for text in NEUTRAL_TEXTS:
            assert _intent(text) == "neutral", repr(text)


class TestContractShape:
    def test_assessment_exposes_only_the_authoritative_verdict(self):
        """ADR-026 makes precedence authoritative: the public contract
        returns exactly one field. Raw lexical-marker booleans are not
        exposed — a consumer checking a raw marker instead of the verdict
        would recreate the bug ADR-026 fixed."""
        assessment = assess_decision_intent("The system must reject invalid input.")
        assert isinstance(assessment, DecisionIntentAssessment)
        assert tuple(f.name for f in dataclasses.fields(assessment)) == ("intent",)

    def test_public_surface_exposes_no_private_helpers(self):
        """External consumers must not need the underscored lexical helpers."""
        import mneme.enforcer as enforcer

        exported = set(enforcer.__all__)
        assert "assess_decision_intent" in exported
        assert "DecisionIntentAssessment" in exported
        assert "DecisionIntent" in exported
        assert "_is_prescriptive_text" not in exported
        assert "_is_advisory_text" not in exported


class TestDeterminismAndPurity:
    def test_identical_input_yields_identical_output(self):
        text = "The deployment must fail closed when validation is missing."
        assert assess_decision_intent(text) == assess_decision_intent(text)

    def test_no_side_effects_on_surrounding_state(self):
        """The API neither mutates input nor carries rule/evidence state,
        and repeated calls are independent of call order."""
        assert _intent(ADVISORY_TEXTS[0]) == "advisory"
        assert _intent(PRESCRIPTIVE_TEXTS[0]) == "prescriptive"
        assert _intent(ADVISORY_TEXTS[0]) == "advisory"
        assert _intent(PRESCRIPTIVE_TEXTS[0]) == "prescriptive"

    def test_serializable_verdict(self):
        assessment = assess_decision_intent("The system must reject invalid input.")
        payload = {"intent": assessment.intent}
        assert json.loads(json.dumps(payload))["intent"] == "prescriptive"


class TestAssessProtectionAgreement:
    """Scope-explicit agreement with the canonical assessor.

    The equivalence

        assess_protection(Decision(decision=t)).intent == "deterministic"
        <=> assess_decision_intent(t).intent == "prescriptive"

    is valid ONLY for the text-only fixture: plain Decision records with no
    structured enforcement material (anti_patterns / "no X" constraints)
    and no installed typed rules. assess_protection intentionally ALSO
    weighs structured enforcement material, and installed typed rules
    outrank prose entirely — those cases are pinned below as explicit
    counterexamples so the equivalence is never mistaken for a global
    invariant.
    """

    @pytest.mark.parametrize("text", TEXT_ONLY_TEXTS)
    def test_text_only_fixture_agrees_with_assess_protection(self, text):
        report = assess_protection(Decision(id="d", decision=text))
        expected = "deterministic" if _intent(text) == "prescriptive" else "guidance"
        assert report.intent == expected, text

    def test_structured_enforcement_material_breaks_the_equivalence(self):
        """Counterexample: neutral text plus structured enforcement material.
        assess_protection weighs the material; the text-only intent API
        cannot see it (and must not)."""
        text = "Plain descriptive text with no markers at all."
        assert _intent(text) == "neutral"
        report = assess_protection(
            Decision(id="d", decision=text, anti_patterns=["sqlite3"])
        )
        assert report.intent == "deterministic"

    def test_installed_typed_rule_breaks_the_equivalence(self):
        """Counterexample: installed deterministic enforcement outranks
        prose entirely (ADR-026 enforcement precedence). The intent API
        keeps reporting the advisory text verdict."""
        text = "We should never use SQLite."
        assert _intent(text) == "advisory"
        report = assess_protection(Decision(
            id="d", decision=text,
            rules=[Rule(type="FORBID_LITERAL", value="sqlite")],
        ))
        assert report.intent == "deterministic"
        assert report.protection_tier == "protected"
