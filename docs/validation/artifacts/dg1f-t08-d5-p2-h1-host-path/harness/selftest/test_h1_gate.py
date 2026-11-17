"""Tests for h1_gate.py: the H1 gate over the accepted published outcomes (synthetic + the real files)."""
import importlib.util
import json
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("h1_gate", HARNESS / "h1_gate.py")
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)
V = "2.1.310 (Claude Code)"


def _write(art, labels, versions=None):
    versions = versions or {}
    for k, rel in G.INPUTS.items():
        p = art / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if labels.get(k, "x") is None:
            continue
        o = {"label": labels.get(k, "DELIVERED_TO_AGENT")}
        v = versions.get(k, V)
        if k == "H1c":
            o["host_version"] = v
        else:
            o["observer"] = {"claude_version": v}
        p.write_text(json.dumps(o), encoding="utf-8")


def _run(art):
    return G.gate([G.path_record(art, k, v) for k, v in G.INPUTS.items()])


def test_all_passing_on_one_version_passes(tmp_path):
    _write(tmp_path, {"H1c": "DELIVERED_TO_USER_ONLY"})
    r = _run(tmp_path)
    assert r["result"] == "PASS" and r["host_version"] == V and r["problems"] == []


@pytest.mark.parametrize("label", ["NOT_DELIVERED", "DELIVERED_WITH_SIDE_EFFECT", "INCONCLUSIVE", "NOT_EXECUTED", None])
def test_any_non_passing_or_missing_label_is_not_met(tmp_path, label):
    _write(tmp_path, {"H1c": label} if label else {"H1b-start": None})
    assert _run(tmp_path)["result"] == "NOT MET"


def test_mixed_host_versions_are_not_met(tmp_path):
    _write(tmp_path, {"H1c": "DELIVERED_TO_USER_ONLY"}, {"H1c": "2.1.202 (Claude Code)"})
    r = _run(tmp_path)
    assert r["result"] == "NOT MET" and any("host versions differ" in p for p in r["problems"])


def test_unrecorded_version_is_not_met(tmp_path):
    _write(tmp_path, {"H1c": "DELIVERED_TO_USER_ONLY"}, {"H1a-edit": ""})
    assert _run(tmp_path)["result"] == "NOT MET"


def test_the_published_accepted_outcomes_pass():
    r = _run(HARNESS.parent)
    assert r["result"] == "PASS", r["problems"]
    assert {p["path"]: p["label"] for p in r["paths"]} == {
        "H1a-edit": "DELIVERED_TO_AGENT", "H1a-bash": "DELIVERED_TO_AGENT",
        "H1b-start": "DELIVERED_TO_AGENT", "H1c": "DELIVERED_TO_USER_ONLY"}
