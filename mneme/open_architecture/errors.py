"""
Error Taxonomy for O1A Open Architecture Benchmark.

Bounded representation of the O1A error vocabulary matching merged PR #389.
No new categories in O1A1 unless the current merged schema cannot represent a required case.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class O1AErrorCategory(str, Enum):
    """Bounded error categories for O1A benchmark.

    Do not add new categories in O1A1 unless the current merged schema
    cannot represent a required case. If that occurs, report it instead
    of silently expanding the ontology.
    """

    MISSED_SOURCE = "MISSED_SOURCE"
    NOT_A_DECISION = "NOT_A_DECISION"
    WRONG_INTENT = "WRONG_INTENT"
    WRONG_DOMAIN = "WRONG_DOMAIN"
    WRONG_PURPOSE = "WRONG_PURPOSE"
    WRONG_AUTHORITY = "WRONG_AUTHORITY"
    WRONG_SCOPE = "WRONG_SCOPE"
    WRONG_LIFECYCLE = "WRONG_LIFECYCLE"
    MISSED_SUPERSESSION = "MISSED_SUPERSESSION"
    MISSED_RELATIONSHIP = "MISSED_RELATIONSHIP"
    FALSE_APPLICABILITY = "FALSE_APPLICABILITY"
    MISSED_APPLICABILITY = "MISSED_APPLICABILITY"
    WRONG_RULE_DERIVATION = "WRONG_RULE_DERIVATION"
    AMBIGUOUS_HUMAN_LABEL = "AMBIGUOUS_HUMAN_LABEL"
    ONTOLOGY_GAP = "ONTOLOGY_GAP"


# Frozen set of all valid categories for validation
VALID_ERROR_CATEGORIES: frozenset[str] = frozenset(c.value for c in O1AErrorCategory)

# Human-readable descriptions for each category
ERROR_CATEGORY_DESCRIPTIONS: dict[str, str] = {
    O1AErrorCategory.MISSED_SOURCE.value: "Failed to identify a decision source that should have been detected",
    O1AErrorCategory.NOT_A_DECISION.value: "Classified something as a decision that is not a decision",
    O1AErrorCategory.WRONG_INTENT.value: "Misclassified the intent (prescriptive vs advisory) of a decision",
    O1AErrorCategory.WRONG_DOMAIN.value: "Assigned incorrect decision domain(s)",
    O1AErrorCategory.WRONG_PURPOSE.value: "Assigned incorrect decision purpose(s)",
    O1AErrorCategory.WRONG_AUTHORITY.value: "Assigned incorrect authority level",
    O1AErrorCategory.WRONG_SCOPE.value: "Assigned incorrect scope type(s)",
    O1AErrorCategory.WRONG_LIFECYCLE.value: "Assigned incorrect lifecycle status",
    O1AErrorCategory.MISSED_SUPERSESSION.value: "Failed to detect a supersession relationship",
    O1AErrorCategory.MISSED_RELATIONSHIP.value: "Failed to detect a relationship (derived_from, depends_on, etc.)",
    O1AErrorCategory.FALSE_APPLICABILITY.value: "Predicted applicability where none exists",
    O1AErrorCategory.MISSED_APPLICABILITY.value: "Failed to predict applicability that exists",
    O1AErrorCategory.WRONG_RULE_DERIVATION.value: "Derived incorrect rule from decision (wrong type, value, or selectors)",
    O1AErrorCategory.AMBIGUOUS_HUMAN_LABEL.value: "Human label was ambiguous or inconsistent",
    O1AErrorCategory.ONTOLOGY_GAP.value: "Required case not representable in current ontology",
}


@dataclass(frozen=True)
class O1AError:
    """Structured O1A error record."""

    error_category: O1AErrorCategory
    description: str | None
    candidate_id: str | None
    scenario_id: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.error_category, O1AErrorCategory):
            raise ValueError(f"error_category must be O1AErrorCategory, got {type(self.error_category)}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_category": self.error_category.value,
            "description": self.description,
            "candidate_id": self.candidate_id,
            "scenario_id": self.scenario_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> O1AError:
        return cls(
            error_category=O1AErrorCategory(data["error_category"]),
            description=data.get("description"),
            candidate_id=data.get("candidate_id"),
            scenario_id=data.get("scenario_id"),
        )


def validate_error_category(category: str) -> O1AErrorCategory:
    """Validate and return error category enum.

    Raises:
        ValueError: If category is not a valid O1A error category.
    """
    try:
        return O1AErrorCategory(category)
    except ValueError:
        raise ValueError(
            f"Invalid O1A error category: {category!r}. "
            f"Valid categories: {sorted(VALID_ERROR_CATEGORIES)}"
        )


def get_error_description(category: O1AErrorCategory) -> str:
    """Get human-readable description for an error category."""
    return ERROR_CATEGORY_DESCRIPTIONS.get(category.value, "No description available")