"""End-to-end pipeline: load -> score -> inject top-N -> call LLM -> detect conflicts."""
from pathlib import Path

from mneme.pipeline import Pipeline, PipelineResult

EXAMPLE = Path(__file__).parent.parent / "examples" / "project_memory.json"


def test_pipeline_runs_in_dry_run():
    p = Pipeline(memory_path=EXAMPLE, dry_run=True, max_decisions=3)
    result = p.run("Should I switch storage to Postgres?")
    assert isinstance(result, PipelineResult)
    # Top-N cap respected.
    assert len(result.injected_decisions) <= 3
    # At least one decision injected for a storage-related query.
    assert len(result.injected_decisions) >= 1
    # The system prompt the adapter built must contain decision injection.
    assert "Mneme decisions applied" in result.system_prompt


def test_pipeline_surfaces_scores_in_debug():
    p = Pipeline(memory_path=EXAMPLE, dry_run=True)
    result = p.run("Should I switch storage to Postgres?")
    assert len(result.scored) >= 1
    # Top result's score must be >= any lower-ranked result.
    scores = [s.score for s in result.scored]
    assert scores == sorted(scores, reverse=True)


def test_pipeline_runs_conflict_detection_after_response():
    """Simulate a violating response by stubbing the adapter in dry_run+response."""
    p = Pipeline(memory_path=EXAMPLE, dry_run=True)
    # Inject a fake LLM response to exercise conflict detection.
    result = p.run(
        "Should I switch storage to Postgres?",
        _override_response="We recommend introducing Postgres next quarter.",
    )
    assert any(
        "postgres" in c.snippet.lower() for c in result.conflicts
    ), f"expected a postgres conflict, got {result.conflicts!r}"


def test_top_n_respected_even_when_more_match():
    p = Pipeline(memory_path=EXAMPLE, dry_run=True, max_decisions=1)
    result = p.run("storage retrieval agents postgres embeddings")
    assert len(result.injected_decisions) == 1


import pytest


def test_pipeline_default_enforcement_mode_is_warn():
    p = Pipeline(memory_path=EXAMPLE, dry_run=True)
    assert p.enforcement_mode == "warn"


def test_pipeline_explicit_strict_mode_construction():
    """Explicit valid 'strict' must round-trip onto the instance unchanged."""
    p = Pipeline(memory_path=EXAMPLE, dry_run=True, enforcement_mode="strict")
    assert p.enforcement_mode == "strict"


def test_pipeline_invalid_enforcement_mode_raises_at_construction():
    with pytest.raises(ValueError, match="enforcement_mode"):
        Pipeline(memory_path=EXAMPLE, dry_run=True, enforcement_mode="bogus")


def test_pipeline_warn_mode_returns_result_even_with_conflicts():
    """warn mode is the existing behavior — surface conflicts, do not raise."""
    p = Pipeline(memory_path=EXAMPLE, dry_run=True, enforcement_mode="warn")
    result = p.run(
        "Should I switch storage to Postgres?",
        _override_response="We recommend introducing Postgres next quarter.",
    )
    assert len(result.conflicts) >= 1


def test_pipeline_strict_mode_raises_when_conflicts_detected():
    from mneme.schemas import MnemeConflictError

    p = Pipeline(memory_path=EXAMPLE, dry_run=True, enforcement_mode="strict")
    with pytest.raises(MnemeConflictError) as excinfo:
        p.run(
            "Should I switch storage to Postgres?",
            _override_response="We recommend introducing Postgres next quarter.",
        )
    err = excinfo.value
    # Exception carries the conflict list...
    assert len(err.conflicts) >= 1
    assert any("postgres" in c.snippet.lower() for c in err.conflicts)
    # ...and the partial result, so callers can inspect what was sent.
    assert err.result is not None
    assert err.result.query.startswith("Should I switch storage")
    assert err.result.system_prompt  # non-empty
    assert err.result.response.content.startswith("We recommend")


def test_pipeline_strict_mode_returns_result_when_no_conflicts():
    """strict mode only raises on conflicts; clean responses still return."""
    p = Pipeline(memory_path=EXAMPLE, dry_run=True, enforcement_mode="strict")
    result = p.run(
        "Should I switch storage to Postgres?",
        # A bland response that does not trigger any constraint match.
        _override_response="Stay with the current local store and revisit later.",
    )
    assert result.conflicts == []
    assert result.response.content.startswith("Stay with")


def test_pipeline_default_min_score_is_zero():
    """Default behavior: only score == 0 is filtered (preserves existing semantics)."""
    p = Pipeline(memory_path=EXAMPLE, dry_run=True)
    assert p.min_score == 0.0


def test_pipeline_min_score_above_zero_filters_low_scores():
    """A min_score above 0 must drop decisions whose score is at or below it."""
    p = Pipeline(memory_path=EXAMPLE, dry_run=True, min_score=10.0)
    result = p.run("Should I switch storage to Postgres?")
    # With a high threshold, no decisions should be injected.
    assert result.injected_decisions == []
    # Also prove min_score was threaded through to format_decisions: with no
    # decisions surviving the threshold, the system_prompt must be empty.
    assert result.system_prompt == ""


def test_pipeline_min_score_negative_raises():
    """A negative threshold makes no sense; reject at construction."""
    with pytest.raises(ValueError, match="min_score"):
        Pipeline(memory_path=EXAMPLE, dry_run=True, min_score=-1.0)
