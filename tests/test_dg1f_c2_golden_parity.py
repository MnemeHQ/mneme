"""DG1F-C2 golden-output parity (charter §4, freeze amendment validation gate).

The goldens in ``tests/fixtures/dg1f_c2/goldens.json`` were captured from the
pre-change build in a commit before any C2 production change. Every consumer
output, for every memory form, must stay byte-identical.
"""
from __future__ import annotations

import json

import pytest

from tests.dg1f_c2_corpus import FORMS, GOLDENS, _capture_form

_GOLDENS = json.loads(GOLDENS.read_text(encoding="utf-8"))


def test_goldens_cover_every_charter_form() -> None:
    assert tuple(sorted(_GOLDENS)) == tuple(sorted(FORMS))


@pytest.mark.parametrize("form", FORMS)
def test_consumer_outputs_match_pre_change_goldens(form: str) -> None:
    actual = _capture_form(form)
    expected = _GOLDENS[form]
    assert sorted(actual) == sorted(expected)
    for key in sorted(expected):
        assert actual[key] == expected[key], f"{form}:{key} diverged from golden"


def test_goldens_pin_the_charter_divergences() -> None:
    """The divergences C2 must preserve (charter §3.3-§3.5) are in the goldens."""
    legacy = _GOLDENS["legacy_sectionless"]
    canonical = _GOLDENS["canonical_v1"]
    # D-1: superseded/deprecated legacy decisions are still enforced by check ...
    assert "C2-OLD" in legacy["check:strict"]["stdout"]
    assert "C2-DEP" in legacy["check:strict"]["stdout"]
    assert legacy["check:strict"]["exit"] == 2
    # ... and still excluded from Audit counts and protection candidates.
    counts = legacy["in_process"]["readiness_counts"]
    assert counts == canonical["in_process"]["readiness_counts"]
    assert "C2-OLDPICKLE" not in legacy["protect_list"]["stdout"]
    # Legacy precheck message vs canonical "not found".
    assert "only active decisions can be activated" in legacy["protect_validate:C2-OLD"]["stdout"]
    assert "not found" in canonical["protect_validate:C2-OLD"]["stderr"]
    # Evidence: a superseded legacy decision sharing a selector is not ambiguity.
    assert legacy["in_process"]["match_ci_evidence"] == {
        "C2-LIT": ["tests/test_storage.py::test_sqlite_only"]
    }
    # Integrity findings and section-less memory make only the preview unavailable.
    for form in ("canonical_conflict", "canonical_dangling", "legacy_sectionless"):
        assert "PREVIEW UNAVAILABLE" in _GOLDENS[form]["check_preview"]["stderr"]
        assert _GOLDENS[form]["check:strict"]["exit"] == 2
