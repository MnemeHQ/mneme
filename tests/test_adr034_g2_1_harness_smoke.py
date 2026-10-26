"""Opt-in: the G2-1 scoring harness on the seven public smoke cases.

Runs the full ``score`` protocol (wheel and tree verification, two passes,
G7) with the pinned implementation and baseline environments over a corpus
made only of the public smoke cases, under test pins. Smoke cases are never
in a gate denominator, so this checks the harness against real pinned
builds; it is not validation evidence.

Skipped unless all of these are set:

- ``MNEME_G2H_SMOKE_DIR``: the ``public_smoke/cases`` directory;
- ``MNEME_G2H_IMPL_PYTHON`` / ``MNEME_G2H_IMPL_WHEEL``: the ``6e26c534`` env and wheel;
- ``MNEME_G2H_BASELINE_PYTHON`` / ``MNEME_G2H_BASELINE_WHEEL``: the ``f8591102`` env
  and wheel;
- ``MNEME_G2H_HOST_VERSION`` / ``MNEME_G2H_HOST_SHA256``: the §8.B host identity the
  smoke labels' ``relevant_enforcement_observed`` values assume.

The public smoke cases are not copied into this repository.
"""
from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "adr034_g2_1_harness_smoke", REPO_ROOT / "benchmarks" / "adr034_g2_1" / "harness.py")
h = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = h
_spec.loader.exec_module(h)

_VARS = ("MNEME_G2H_SMOKE_DIR", "MNEME_G2H_IMPL_PYTHON", "MNEME_G2H_IMPL_WHEEL",
         "MNEME_G2H_BASELINE_PYTHON", "MNEME_G2H_BASELINE_WHEEL",
         "MNEME_G2H_HOST_VERSION", "MNEME_G2H_HOST_SHA256")
pytestmark = pytest.mark.skipif(
    not all(os.environ.get(v) for v in _VARS),
    reason="needs the public smoke cases and both pinned environments (" + ", ".join(_VARS) + ")")


def _smoke_corpus(root: Path) -> "h.Pins":
    source = Path(os.environ["MNEME_G2H_SMOKE_DIR"])
    (root / "cases").mkdir(parents=True)
    rows, counts = [], {k: (0, 0) for k in h.CLASSES}
    for directory in sorted(source.iterdir()):
        shutil.copytree(directory, root / "cases" / directory.name)
        expected = json.loads((directory / "expected.json").read_text(encoding="ascii"))
        assert expected["public_smoke"] is True
        rows.append({"case_id": directory.name, "class": expected["class"],
                     "public_smoke": True})
        counts[expected["class"]] = (0, counts[expected["class"]][1] + 1)
    (root / "CASE_INDEX.json").write_text(json.dumps({"cases": rows}), encoding="ascii")
    (root / "PUBLIC_SMOKE.json").write_text(
        json.dumps({"public_smoke_case_ids": [r["case_id"] for r in rows]}), encoding="ascii")
    files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    manifest = "".join(f"{h.sha256_file(root / f)}  {f}\n" for f in files)
    (root / "FILES.sha256").write_text(manifest, encoding="ascii", newline="\n")
    return dataclasses.replace(
        h.G2_PINS, files_sha256_digest=hashlib.sha256(manifest.encode()).hexdigest(),
        files_count=len(files), counts=counts, is_frozen=False)


def test_public_smoke_cases_score_cleanly_on_the_pinned_builds(tmp_path):
    corpus = tmp_path / "corpus"
    pins = _smoke_corpus(corpus)
    final = h.score(
        corpus=corpus, out_dir=tmp_path / "out",
        impl_python=os.environ["MNEME_G2H_IMPL_PYTHON"],
        impl_wheel=Path(os.environ["MNEME_G2H_IMPL_WHEEL"]),
        base_python=os.environ["MNEME_G2H_BASELINE_PYTHON"],
        base_wheel=Path(os.environ["MNEME_G2H_BASELINE_WHEEL"]),
        host_version=os.environ["MNEME_G2H_HOST_VERSION"],
        host_sha256=os.environ["MNEME_G2H_HOST_SHA256"],
        run_root=Path(os.path.realpath(tmp_path)) / "run", pins=pins)
    assert final["result"] in ("PASS", "INCOMPLETE"), final.get("refusal")
    assert final["result"] == ("PASS" if final["symlinks"]["capable"] else "INCOMPLETE")
    assert final["gates"]["G7"]["pass"]
    smoke = final["public_smoke"]
    assert smoke["cases"] == 7
    failing = {g: v["failing_cases"] for g, v in smoke["gates"].items() if not v["pass"]}
    assert failing == {}
    assert smoke["label_conformance_mismatches"] == {}
