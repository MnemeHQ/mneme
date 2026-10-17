"""Unit + smoke tests for benchmarks/hook_latency/run.py (issue #60)."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_RUN = Path(__file__).resolve().parents[1] / "benchmarks" / "hook_latency" / "run.py"


@pytest.fixture
def harness():
    spec = importlib.util.spec_from_file_location("hook_latency_run", _RUN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_summarize_known_values(harness):
    s = harness.summarize([float(i) for i in range(1, 101)])
    assert s["n"] == 100
    assert s["p50"] == 50.5
    assert s["p95"] == 95.0  # 95.05 rounded to 0.1 ms
    assert s["max"] == 100.0


def test_wrong_exit_code_fails_harness(harness, tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "run_once", lambda python, project, scenario, transport: (10.0, 0, ""))
    out = tmp_path / "o.json"
    rc = harness.main(["--python", sys.executable, "--runs", "2", "--warmup", "0", "--out", str(out)])
    assert rc == 1
    assert not out.exists()


def test_real_smoke_both_transports(harness, tmp_path):
    out = tmp_path / "o.json"
    rc = harness.main(["--python", sys.executable, "--runs", "2", "--warmup", "0", "--out", str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert {
        "edit_allowed/subprocess", "edit_allowed/inprocess",
        "edit_blocked/subprocess", "edit_blocked/inprocess",
        "baseline/python_pass", "baseline/import_hook", "baseline/import_cli",
    } <= set(data["cells"])
    assert data["cells"]["edit_blocked/inprocess"]["summary"]["n"] == 2
