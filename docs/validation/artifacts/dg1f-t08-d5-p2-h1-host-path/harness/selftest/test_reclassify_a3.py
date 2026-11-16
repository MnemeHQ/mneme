"""Synthetic tests for reclassify_a3.py's own logic (its helpers are reclassify_a2's, tested in #800).
No real evidence is read."""
import importlib.util
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("reclassify_a3", HARNESS / "reclassify_a3.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)


def test_status_is_pending_on_any_omitted_hit():
    assert M.status(0) == "COMPLETE" and M.status(1) == M.PENDING == "PENDING_REVIEW"


def test_headless_recorded_keys_arms_to_the_live_root_and_restores_the_loader(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(M.A1.C, "load_arm", lambda out: {"out": Path(out), "events": [], "hooks": []})
    orig = M.A1.C.load_arm

    def fake_headless(live, model, version):
        for a in M.ARMS:
            seen[a] = M.A1.C.load_arm(Path(live) / a / "out")["out"]
        raise RuntimeError("stop")

    monkeypatch.setattr(M.A1, "headless", fake_headless)
    with pytest.raises(RuntimeError):
        M.headless_recorded(tmp_path)
    assert seen == {a: Path(M.LIVE_ROOT) / a / "out" for a in M.ARMS}
    assert M.A1.C.load_arm is orig  # restored even when classification raises


def test_refuses_to_overwrite(tmp_path):
    (tmp_path / "reclassification.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        M.main(["x", str(tmp_path / "arch"), str(tmp_path / "s"), str(tmp_path), "py", "claude"])
