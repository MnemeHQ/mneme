"""Tests for benchmark structured-output schemas (v1.1 Step 2)."""
import pytest

from mneme.benchmark_schemas import Assertion, StructuredOutput


def test_structured_output_valid_parse():
    text = (
        '{"refused": false, '
        '"files_changed": ["src/db/session.py"], '
        '"dependencies_added": ["sqlalchemy"]}'
    )
    out = StructuredOutput.from_json(text)
    assert out.refused is False
    assert out.files_changed == ["src/db/session.py"]
    assert out.dependencies_added == ["sqlalchemy"]


def test_structured_output_malformed_json_raises():
    with pytest.raises(ValueError, match="malformed JSON"):
        StructuredOutput.from_json("{not valid json}")


def test_assertion_unknown_type_raises():
    with pytest.raises(ValueError, match="unknown assertion type"):
        Assertion.from_dict({"type": "forbidden_function", "value": "foo"})
