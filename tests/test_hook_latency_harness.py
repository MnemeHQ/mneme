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


def test_env_never_disables_bytecode(harness, monkeypatch):
    # A caller shell with PYTHONDONTWRITEBYTECODE=1 made every run recompile
    # mneme from source, inflating all import timings (issue #60 correction).
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    assert "PYTHONDONTWRITEBYTECODE" not in harness._env("subprocess", "")
    assert "PYTHONDONTWRITEBYTECODE" not in harness._env(None, "somewhere")


def test_precompile_writes_bytecode_for_package(harness, tmp_path):
    pkg = tmp_path / "pkgx"
    (pkg / "inner").mkdir(parents=True)
    (pkg / "__init__.py").write_text("X = 1\n", encoding="utf-8")
    (pkg / "inner" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "inner" / "mod.py").write_text("Y = 2\n", encoding="utf-8")
    harness.precompile(sys.executable, pkg)
    assert list((pkg / "__pycache__").glob("__init__.*.pyc"))
    assert list((pkg / "inner" / "__pycache__").glob("mod.*.pyc"))


def test_smoke_records_bytecode_setting(harness, tmp_path):
    out = tmp_path / "o.json"
    assert harness.main(["--python", sys.executable, "--runs", "2", "--warmup", "0", "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["settings"]["bytecode"] == "precompiled"


def test_extra_env_applies_to_every_run(harness, monkeypatch):
    monkeypatch.setattr(harness, "_EXTRA_ENV", {"PYTHON_LAZY_IMPORTS": "all"})
    assert harness._env("subprocess", "")["PYTHON_LAZY_IMPORTS"] == "all"
    assert harness._env(None, "somewhere")["PYTHON_LAZY_IMPORTS"] == "all"


def test_extra_env_cannot_override_controlled_variables(harness, tmp_path):
    for key in ("PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "MNEME_HOOK_CHECK_TRANSPORT"):
        with pytest.raises(SystemExit) as exc:
            harness.main(["--python", sys.executable, "--out", str(tmp_path / "o.json"),
                          "--env", f"{key}=1"])
        assert exc.value.code == 2


def test_native_spawn_baseline_and_env_are_recorded(harness, tmp_path):
    out = tmp_path / "o.json"
    rc = harness.main(["--python", sys.executable, "--runs", "2", "--warmup", "0",
                       "--out", str(out), "--env", "MNEME_BENCH_PROBE=1"])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["cells"]["baseline/native_spawn"]["summary"]["n"] == 2
    assert data["settings"]["native_spawn_cmd"]
    assert data["settings"]["env"] == {"MNEME_BENCH_PROBE": "1"}
