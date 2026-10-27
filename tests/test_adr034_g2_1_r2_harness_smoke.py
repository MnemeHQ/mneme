"""Opt-in: the G2-1 R2 scoring harness on the 13 public smoke cases.

Runs the full ``score`` protocol (wheel and tree verification, two passes,
G7) with the pinned implementation and baseline environments, over a corpus
made only of the public smoke cases, under test pins. Smoke cases are never
in a gate denominator, so this checks the harness against real pinned
builds; it is not validation evidence.

Skipped unless all of these are set:

- ``MNEME_G2R2_SMOKE_DIR``: the public smoke folder (holding
  ``PUBLIC_FILES.sha256``, ``MANIFEST.json`` and ``cases/``);
- ``MNEME_G2R2_IMPL_PYTHON`` / ``MNEME_G2R2_IMPL_WHEEL``: the ``dbab816f`` env and wheel;
- ``MNEME_G2R2_BASELINE_PYTHON`` / ``MNEME_G2R2_BASELINE_WHEEL``: the ``f8591102`` env
  and wheel;
- ``MNEME_G2R2_HOST_VERSION`` / ``MNEME_G2R2_HOST_SHA256``: the pinned host identity.

The public smoke cases are not copied into this repository.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import os
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "adr034_g2_1_r2_harness_smoke", REPO_ROOT / "benchmarks" / "adr034_g2_1_r2" / "harness.py")
h = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = h
_spec.loader.exec_module(h)

_VARS = ("MNEME_G2R2_SMOKE_DIR", "MNEME_G2R2_IMPL_PYTHON", "MNEME_G2R2_IMPL_WHEEL",
         "MNEME_G2R2_BASELINE_PYTHON", "MNEME_G2R2_BASELINE_WHEEL",
         "MNEME_G2R2_HOST_VERSION", "MNEME_G2R2_HOST_SHA256")
pytestmark = pytest.mark.skipif(
    not all(os.environ.get(v) for v in _VARS),
    reason="needs the R2 public smoke cases and both pinned environments ("
           + ", ".join(_VARS) + ")")


def test_public_smoke_folder_matches_its_pinned_manifest():
    public = Path(os.environ["MNEME_G2R2_SMOKE_DIR"])
    record = h.verify_tree(public, "PUBLIC_FILES.sha256", h.R2_PINS.public_files_sha256_digest,
                           h.R2_PINS.public_files_count, "public_files_sha256")
    assert record["files_verified"] == 57
    cases, findings = h.load_cases(public)
    assert findings == []
    assert len(cases) == 13 and all(c.public_smoke and not c.problems for c in cases)
    assert sorted(c.klass for c in cases) == sorted(h.CLASSES)


def test_public_smoke_cases_score_cleanly_on_the_pinned_builds(tmp_path):
    corpus = tmp_path / "corpus"
    shutil.copytree(os.environ["MNEME_G2R2_SMOKE_DIR"], corpus)
    # Under test pins the smoke folder stands in for the corpus root.
    (corpus / "PUBLIC_FILES.sha256").rename(corpus / "FILES.sha256")
    pins = dataclasses.replace(
        h.R2_PINS, files_sha256_digest=h.R2_PINS.public_files_sha256_digest,
        files_count=h.R2_PINS.public_files_count,
        counts={k: (0, 1) for k in h.CLASSES}, is_frozen=False)
    final = h.score(
        corpus=corpus, out_dir=tmp_path / "out",
        impl_python=os.environ["MNEME_G2R2_IMPL_PYTHON"],
        impl_wheel=Path(os.environ["MNEME_G2R2_IMPL_WHEEL"]),
        base_python=os.environ["MNEME_G2R2_BASELINE_PYTHON"],
        base_wheel=Path(os.environ["MNEME_G2R2_BASELINE_WHEEL"]),
        host_version=os.environ["MNEME_G2R2_HOST_VERSION"],
        host_sha256=os.environ["MNEME_G2R2_HOST_SHA256"],
        run_root=Path(os.path.realpath(tmp_path)) / "run", pins=pins)
    assert final["result"] in ("PASS", "INCOMPLETE"), final.get("refusal")
    assert final["result"] == ("PASS" if final["symlinks"]["capable"] else "INCOMPLETE")
    assert final["builds"]["implementation"]["mneme_tree"] == h.R2_PINS.impl_tree
    assert final["gates"]["G7"]["pass"]
    smoke = final["public_smoke"]
    assert smoke["cases"] == 13
    assert smoke["passes_identical"] is True
    failing = {g: v["failing_cases"] for g, v in smoke["gates"].items() if not v["pass"]}
    assert failing == {}
    assert all(smoke["gates"][g]["applicable"] == 13 for g in ("G1", "G3", "G6", "G8"))
    assert smoke["label_conformance_mismatches"] == {}
    assert smoke["r2_amendment_2"]["applied"] is True
    assert final["r2_amendment_2"]["flagged_cases"] == 0  # no concealed cases here
