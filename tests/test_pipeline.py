"""End-to-end pipeline: load -> score -> inject top-N -> call LLM -> detect conflicts."""
import json
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


def test_pipeline_strict_mode_raises_when_scoped_rule_is_unevaluated(tmp_path):
    """Regression (adversarial review AR-001): strict mode must not silently
    complete while a scoped typed rule could not be evaluated.

    The CLI treats PATH_APPLICABILITY_UNKNOWN as an operational failure (exit 2,
    never a policy verdict) and ConflictDetector.detect() raises
    PathApplicabilityUnknownError. Pipeline.run() in strict mode did neither:
    the unevaluated scoped rule was skipped, conflicts stayed empty, and the
    call returned normally even though the response contained the forbidden
    literal. ADR-020 sec. 6 forbids unavailable applicability from becoming a
    silent successful evaluation.
    """
    from mneme.conflict_detector import PathApplicabilityUnknownError

    memory = tmp_path / ".mneme" / "project_memory.json"
    memory.parent.mkdir()
    memory.write_text(json.dumps({
        "meta": {"name": "test", "description": "test"},
        "decisions": [{
            "id": "ADR-020",
            "decision": "Legacy client documentation",
            "scope": ["docs"],
            "rules": [{
                "type": "FORBID_LITERAL",
                "value": "install legacy-client",
                "include_paths": ["docs/**"],
            }],
        }],
    }), encoding="utf-8")
    p = Pipeline(memory_path=memory, dry_run=True, enforcement_mode="strict")

    with pytest.raises(PathApplicabilityUnknownError) as excinfo:
        p.run(
            "update docs",
            _override_response="install legacy-client",
        )

    # The error exposes exactly which rule could not be evaluated and why.
    assert any(
        item.outcome.value == "UNKNOWN" and item.rule_value == "install legacy-client"
        for item in excinfo.value.applicability
    )


def test_pipeline_strict_mode_still_raises_conflict_when_target_resolves(tmp_path):
    """The AR-001 fix must not disturb the normal strict-mode contract: with a
    target path that resolves applicability, a violating response still raises
    MnemeConflictError."""
    from mneme.schemas import MnemeConflictError

    memory = tmp_path / ".mneme" / "project_memory.json"
    memory.parent.mkdir()
    memory.write_text(json.dumps({
        "meta": {"name": "test", "description": "test"},
        "decisions": [{
            "id": "ADR-020",
            "decision": "Legacy client documentation",
            "scope": ["docs"],
            "rules": [{
                "type": "FORBID_LITERAL",
                "value": "install legacy-client",
                "include_paths": ["docs/**"],
            }],
        }],
    }), encoding="utf-8")
    p = Pipeline(memory_path=memory, dry_run=True, enforcement_mode="strict")

    with pytest.raises(MnemeConflictError):
        p.run(
            "update docs",
            _override_response="install legacy-client",
            target_path=tmp_path / "docs" / "guide.md",
        )


def test_pipeline_warn_mode_keeps_reporting_unknown_without_raising(tmp_path):
    """warn mode keeps returning a result; the caller inspects
    evaluation_complete. Only strict mode escalates to an operational error."""
    memory = tmp_path / ".mneme" / "project_memory.json"
    memory.parent.mkdir()
    memory.write_text(json.dumps({
        "meta": {"name": "test", "description": "test"},
        "decisions": [{
            "id": "ADR-020",
            "decision": "Legacy client documentation",
            "scope": ["docs"],
            "rules": [{
                "type": "FORBID_LITERAL",
                "value": "install legacy-client",
                "include_paths": ["docs/**"],
            }],
        }],
    }), encoding="utf-8")
    p = Pipeline(memory_path=memory, dry_run=True, enforcement_mode="warn")

    result = p.run("update docs", _override_response="install legacy-client")
    assert not result.evaluation_complete
    assert result.conflicts == []


def test_pipeline_reports_scoped_rule_non_evaluation_and_accepts_target(tmp_path):
    memory = tmp_path / ".mneme" / "project_memory.json"
    memory.parent.mkdir()
    memory.write_text(json.dumps({
        "meta": {"name": "test", "description": "test"},
        "decisions": [{
            "id": "ADR-020",
            "decision": "Legacy client documentation",
            "scope": ["docs"],
            "rules": [{
                "type": "FORBID_LITERAL",
                "value": "install legacy-client",
                "include_paths": ["docs/**"],
            }],
        }],
    }), encoding="utf-8")
    pipeline = Pipeline(memory_path=memory, dry_run=True)

    unknown = pipeline.run(
        "update docs",
        _override_response="install legacy-client",
    )
    applied = pipeline.run(
        "update docs",
        _override_response="install legacy-client",
        target_path=tmp_path / "docs" / "guide.md",
    )

    assert not unknown.evaluation_complete
    assert unknown.conflicts == []
    assert applied.evaluation_complete
    assert len(applied.conflicts) == 1


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
