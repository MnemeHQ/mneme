"""Post-response conflict detection against injected decisions."""
from mneme.conflict_detector import ConflictDetector, Conflict
from mneme.schemas import Decision


def _decisions():
    return [
        Decision(
            id="mneme_001",
            decision="Use JSON storage only",
            rationale="Keep local-first.",
            scope=["storage"],
            constraints=["no postgres", "no external db"],
            anti_patterns=["introduce ORM", "add migration layer"],
        ),
    ]


def test_detects_constraint_violation():
    response = "You should introduce Postgres for durability and scale."
    conflicts = ConflictDetector().detect(response, _decisions())
    assert len(conflicts) >= 1
    c = conflicts[0]
    assert isinstance(c, Conflict)
    assert c.violated_decision_id == "mneme_001"
    assert "postgres" in c.snippet.lower()
    assert c.reason


def test_detects_anti_pattern_violation():
    response = "Let's introduce ORM to clean up the data access layer."
    conflicts = ConflictDetector().detect(response, _decisions())
    assert any("introduce ORM" in c.reason or "ORM" in c.snippet for c in conflicts)


def test_no_violation_returns_empty():
    response = "Keep using JSON files as planned. No schema changes needed."
    conflicts = ConflictDetector().detect(response, _decisions())
    assert conflicts == []


def test_case_insensitive_match():
    response = "MIGRATE to POSTGRES soon."
    conflicts = ConflictDetector().detect(response, _decisions())
    assert any(c.violated_decision_id == "mneme_001" for c in conflicts)


def test_does_not_flag_when_response_negates_the_term():
    """A response that explicitly rejects the forbidden term is not a violation."""
    response = "Do not use Postgres. Stick with JSON."
    conflicts = ConflictDetector().detect(response, _decisions())
    # No positive recommendation → no conflict reported.
    assert conflicts == []


def test_snippet_contains_surrounding_context():
    response = "After careful review we recommend introducing Postgres next quarter."
    conflicts = ConflictDetector().detect(response, _decisions())
    # Snippet must contain the triggering phrase.
    assert any("postgres" in c.snippet.lower() for c in conflicts)
