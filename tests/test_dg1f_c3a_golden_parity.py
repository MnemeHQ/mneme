"""DG1F-C3a additional golden-output parity (charter #774 §4, freeze #775).

``tests/fixtures/dg1f_c2/goldens_c3a.json`` was captured from the pre-change
code before any C3a production change. It extends the C2 goldens with
``mneme audit`` and ``protect list`` over ``--repo-root`` evidence,
``mneme setup`` (existing and newly created memory) and the ``protect list``
error paths. Every value must stay byte-identical.
"""
from __future__ import annotations

import json

import pytest

from tests.dg1f_c2_corpus import (
    FORMS,
    GOLDENS_C3A,
    _capture_c3a_error_paths,
    _capture_c3a_form,
    _capture_c3a_new_memory,
)

_GOLDENS = json.loads(GOLDENS_C3A.read_text(encoding="utf-8"))


def test_c3a_goldens_cover_every_form_and_extra_case() -> None:
    assert sorted(_GOLDENS) == sorted([*FORMS, "new_memory", "error_paths"])


def _compare(actual: dict, expected: dict, label: str) -> None:
    assert sorted(actual) == sorted(expected)
    for key in sorted(expected):
        assert actual[key] == expected[key], f"{label}:{key} diverged from golden"


@pytest.mark.parametrize("form", FORMS)
def test_c3a_form_outputs_match_pre_change_goldens(form: str) -> None:
    _compare(_capture_c3a_form(form), _GOLDENS[form], form)


def test_c3a_new_memory_setup_matches_pre_change_golden() -> None:
    _compare(_capture_c3a_new_memory(), _GOLDENS["new_memory"], "new_memory")


def test_c3a_protect_list_error_paths_match_pre_change_golden() -> None:
    _compare(_capture_c3a_error_paths(), _GOLDENS["error_paths"], "error_paths")


def test_c3a_goldens_exercise_the_charter_cases() -> None:
    canonical = _GOLDENS["canonical_v1"]
    assert "evidence: ci:candidate:ci.yml" in canonical["audit_repo_root_text"]["stdout"]
    assert canonical["audit_repo_root"]["exit"] == 1
    assert "Found <WORK>/.mneme/project_memory.json" in canonical["setup_cli"]["stdout"]
    assert "Created <WORK>/.mneme/project_memory.json" in (
        _GOLDENS["new_memory"]["setup_cli"]["stdout"]
    )
    errors = _GOLDENS["error_paths"]
    assert errors["protect_list_missing"]["exit"] == 2
    assert "does not exist" in errors["protect_list_missing"]["stderr"]
    assert errors["protect_list_invalid"]["exit"] == 2
    assert "failed validation" in errors["protect_list_invalid"]["stderr"]
