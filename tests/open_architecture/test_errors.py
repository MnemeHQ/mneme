"""Tests for O1A error taxonomy."""

from __future__ import annotations

import pytest

from mneme.open_architecture.errors import (
    O1AErrorCategory,
    O1AError,
    VALID_ERROR_CATEGORIES,
    ERROR_CATEGORY_DESCRIPTIONS,
    validate_error_category,
    get_error_description,
)


class TestO1AErrorCategory:
    def test_all_categories_exist(self):
        expected = {
            "MISSED_SOURCE", "NOT_A_DECISION", "WRONG_INTENT", "WRONG_DOMAIN",
            "WRONG_PURPOSE", "WRONG_AUTHORITY", "WRONG_SCOPE", "WRONG_LIFECYCLE",
            "MISSED_SUPERSESSION", "MISSED_RELATIONSHIP", "FALSE_APPLICABILITY",
            "MISSED_APPLICABILITY", "WRONG_RULE_DERIVATION", "AMBIGUOUS_HUMAN_LABEL",
            "ONTOLOGY_GAP",
        }
        actual = {c.value for c in O1AErrorCategory}
        assert actual == expected

    def test_valid_error_categories_frozenset(self):
        assert isinstance(VALID_ERROR_CATEGORIES, frozenset)
        assert len(VALID_ERROR_CATEGORIES) == 15

    def test_category_descriptions_exist(self):
        for cat in O1AErrorCategory:
            assert cat.value in ERROR_CATEGORY_DESCRIPTIONS
            assert len(ERROR_CATEGORY_DESCRIPTIONS[cat.value]) > 0


class TestValidateErrorCategory:
    def test_valid_category(self):
        cat = validate_error_category("MISSED_SOURCE")
        assert cat == O1AErrorCategory.MISSED_SOURCE

    def test_all_valid_categories(self):
        for cat_str in VALID_ERROR_CATEGORIES:
            cat = validate_error_category(cat_str)
            assert cat.value == cat_str

    def test_invalid_category(self):
        with pytest.raises(ValueError, match="Invalid O1A error category"):
            validate_error_category("INVALID_CATEGORY")

    def test_invalid_category_shows_valid_list(self):
        with pytest.raises(ValueError) as exc_info:
            validate_error_category("INVALID")
        assert "MISSED_SOURCE" in str(exc_info.value)


class TestGetErrorDescription:
    def test_all_categories_have_descriptions(self):
        for cat in O1AErrorCategory:
            desc = get_error_description(cat)
            assert desc
            assert desc != "No description available"

    def test_unknown_category_returns_default(self):
        desc = get_error_description(O1AErrorCategory.MISSED_SOURCE)
        assert "Failed to identify" in desc


class TestO1AError:
    def test_valid_error(self):
        error = O1AError(
            error_category=O1AErrorCategory.MISSED_SOURCE,
            description="Test description",
            candidate_id="cand-123",
            scenario_id="scn-456",
        )
        assert error.error_category == O1AErrorCategory.MISSED_SOURCE
        assert error.description == "Test description"
        assert error.candidate_id == "cand-123"
        assert error.scenario_id == "scn-456"

    def test_error_with_none_fields(self):
        error = O1AError(
            error_category=O1AErrorCategory.ONTOLOGY_GAP,
            description=None,
            candidate_id=None,
            scenario_id=None,
        )
        assert error.error_category == O1AErrorCategory.ONTOLOGY_GAP
        assert error.description is None
        assert error.candidate_id is None
        assert error.scenario_id is None

    def test_invalid_category_type(self):
        with pytest.raises(ValueError, match="error_category must be O1AErrorCategory"):
            O1AError(
                error_category="MISSED_SOURCE",  # String instead of enum
                description="Test",
                candidate_id=None,
                scenario_id=None,
            )

    def test_to_dict(self):
        error = O1AError(
            error_category=O1AErrorCategory.WRONG_DOMAIN,
            description="Domain mismatch",
            candidate_id="cand-abc",
            scenario_id="scn-def",
        )
        d = error.to_dict()
        assert d["error_category"] == "WRONG_DOMAIN"
        assert d["description"] == "Domain mismatch"
        assert d["candidate_id"] == "cand-abc"
        assert d["scenario_id"] == "scn-def"

    def test_from_dict(self):
        d = {
            "error_category": "MISSED_RELATIONSHIP",
            "description": "Missing relationship",
            "candidate_id": "cand-xyz",
            "scenario_id": None,
        }
        error = O1AError.from_dict(d)
        assert error.error_category == O1AErrorCategory.MISSED_RELATIONSHIP
        assert error.description == "Missing relationship"
        assert error.candidate_id == "cand-xyz"
        assert error.scenario_id is None