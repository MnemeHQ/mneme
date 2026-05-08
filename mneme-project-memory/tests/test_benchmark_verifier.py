"""Tests for benchmark structured-output verifier (v1.1 Step 2)."""
from mneme.benchmark_schemas import Assertion, StructuredOutput
from mneme.benchmark_verifier import verify


def test_refused_short_circuits_to_pass():
    """refused=True => passed=True; assertions are not inspected."""
    out = StructuredOutput(refused=True, dependencies_added=["sqlalchemy"])
    asserts = [Assertion(type="forbidden_dependency", value="sqlalchemy")]
    result = verify(out, asserts)
    assert result.passed is True
    assert result.refused is True
    # Per locked spec: refusal short-circuits, no per-assertion records.
    assert result.assertion_results == []


def test_forbidden_dependency_fails_when_dep_present_case_insensitive():
    out = StructuredOutput(
        refused=False,
        dependencies_added=["SQLAlchemy", "anthropic"],
    )
    asserts = [Assertion(type="forbidden_dependency", value="sqlalchemy")]
    result = verify(out, asserts)
    assert result.passed is False
    assert len(result.violations) == 1
    assert "SQLAlchemy" in result.violations[0].triggers


def test_forbidden_path_fails_on_substring_match():
    out = StructuredOutput(
        refused=False,
        files_changed=["src/migrations/0001_initial.py", "tests/test_db.py"],
    )
    asserts = [Assertion(type="forbidden_path_pattern", value="migrations/")]
    result = verify(out, asserts)
    assert result.passed is False
    assert "src/migrations/0001_initial.py" in result.violations[0].triggers
    assert "tests/test_db.py" not in result.violations[0].triggers
