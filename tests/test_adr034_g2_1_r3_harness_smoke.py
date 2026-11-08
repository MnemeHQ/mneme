"""Opt-in end-to-end run of the R3 harness against both pinned builds.

Skipped unless every ``MNEME_G2R3_*`` variable is set:

- ``MNEME_G2R3_IMPL_PYTHON`` / ``MNEME_G2R3_BASE_PYTHON``: interpreters of the
  pinned D3 build and the pinned pre-G2 baseline;
- ``MNEME_G2R3_HOST_VERSION`` / ``MNEME_G2R3_HOST_SHA256``: pinned host identity;
- ``MNEME_G2R3_WORK``: an empty, resolved scratch directory;
- ``MNEME_G2R3_PUBLIC_CORPUS``: the released R3 public smoke directory.

Runs the scorer-authored synthetic cases and the public smoke cases. Public
scoring never yields a verdict; it only shows that each case scores clean.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks.adr034_g2_1_r3 import synthetic

_VARS = ("IMPL_PYTHON", "BASE_PYTHON", "HOST_VERSION", "HOST_SHA256", "WORK", "PUBLIC_CORPUS")
ENV = {name: os.environ.get(f"MNEME_G2R3_{name}") for name in _VARS}
REPO = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(not all(ENV.values()), reason="MNEME_G2R3_* variables not set")


def _score(corpus: Path, work: Path, report: Path) -> dict:
    subprocess.run([
        ENV["IMPL_PYTHON"], "-m", "benchmarks.adr034_g2_1_r3", "score",
        "--corpus", str(corpus), "--work", str(work),
        "--impl-python", ENV["IMPL_PYTHON"], "--base-python", ENV["BASE_PYTHON"],
        "--host-version", ENV["HOST_VERSION"], "--host-sha256", ENV["HOST_SHA256"],
        "--scoring", "public", "--report", str(report),
    ], cwd=REPO, check=True)
    return json.loads(report.read_text(encoding="utf-8"))


@pytest.mark.parametrize("which", ["synthetic", "public"])
def test_cases_score_clean(which):
    work = Path(ENV["WORK"]) / which
    if which == "synthetic":
        corpus = work / "corpus"
        synthetic.write(corpus)
    else:
        corpus = Path(ENV["PUBLIC_CORPUS"])
    report = _score(corpus, work / "run", work / "report.json")
    assert report["decision"]["verdict"] == "NO_VERDICT_PUBLIC_SMOKE"
    failed = {c["case_id"]: {g: v["failures"] for g, v in c["gates"].items() if v["failures"]}
              for c in report["cases"] if not c["passed"]}
    assert failed == {}
    assert report["symlink_capability"]["capable"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
