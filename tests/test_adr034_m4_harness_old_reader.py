"""Opt-in: the ADR-034 M4 harness end to end, including gate 12.

Needs a separate environment with the released ``mneme-hq==0.10.0`` wheel
installed, so it is skipped unless both variables are set:

- ``MNEME_M4_OLD_READER_PYTHON``: that environment's python;
- ``MNEME_M4_OLD_READER_WHEEL``: the ``mneme_hq-0.10.0-py3-none-any.whl`` it
  was installed from.

The corpus is the SYNTHETIC fixture (tests/adr034_m4_synthetic_corpus.py),
never M4 case data.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests import adr034_m4_synthetic_corpus as syn
from tests.test_adr034_m4_harness import BUILD, TEMPLATE, h, synthetic_pins

OLD_PYTHON = os.environ.get("MNEME_M4_OLD_READER_PYTHON")
OLD_WHEEL = os.environ.get("MNEME_M4_OLD_READER_WHEEL")

pytestmark = pytest.mark.skipif(
    not (OLD_PYTHON and OLD_WHEEL),
    reason="needs MNEME_M4_OLD_READER_PYTHON and MNEME_M4_OLD_READER_WHEEL",
)


def test_full_protocol_passes_on_the_synthetic_corpus(tmp_path):
    root = tmp_path / "corpus"
    digests = syn.build(root)
    cases, _ = h.parse_manifest((root / "manifest.jsonl").read_text(encoding="utf-8"))
    final = h.score(corpus=root, template=TEMPLATE, out_dir=tmp_path / "out", build=BUILD,
                    old=h.Interpreter(OLD_PYTHON), old_wheel=Path(OLD_WHEEL),
                    pins=synthetic_pins(digests, cases), work_dir=tmp_path)
    assert final["result"] == "PASS", final["gates"]
    gate = final["gates"]["12"]
    assert gate["value"] == {"control_reader_works": True, "v2_numeric_memory": True,
                             "refused_not_dropped": True}
    assert gate["control"]["literal_rule_id_matches_golden"] is True
    old = final["preconditions"]["old_reader"]
    assert old["distribution_version"] == "0.10.0"
    assert old["wheel_sha256"] == h.sha256_file(Path(OLD_WHEEL))
    assert old["wheel_sha256_matches_g1_record"] is True
