"""Offline, synthetic tests for the H1c Amendment A1 harness (probe scope 4.2). NOT evidence.

Headless arms are driven by the self-test stub. Interactive arms use the stub only to
produce a session record and hook log; the operator's capture is simulated with a
synthetic observation.json and a recording hash in observer.txt. The stub's
systemMessage behaviour (H1_STUB_SM_MODE) is a test fixture, not a claim about
Claude Code.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parent.parent
STUB = HARNESS / "selftest" / "stub_claude.py"
PIN = "claude-opus-4-8[1m]"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HARNESS / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


A1 = _load("classify_a1")
setup_probe = _load("setup_probe")


def _arm(live, arm, knobs):
    pdir = live / arm
    setup_probe.main(["setup_probe.py", arm, str(pdir), sys.executable, str(HARNESS / "emitter.py")])
    meta = json.loads((pdir / "out" / "probe.json").read_text(encoding="utf-8"))
    env = {k: v for k, v in os.environ.items() if not k.startswith(("H1_STUB_", "MNEME_"))}
    env.update({"H1_STUB_HOME": str(live / "_home" / arm), **knobs})
    with open(pdir / "out" / "events.jsonl", "w", encoding="utf-8") as f:
        subprocess.run([sys.executable, "-I", str(STUB), "-p", meta["prompt"]], cwd=pdir / "ws",
                       env=env, stdout=f, check=True)
    tps = list((live / "_home" / arm).glob("projects/*/*.jsonl"))
    if tps:
        shutil.copy(tps[0], pdir / "out" / "transcript.jsonl")
    return pdir / "out"


def _headless(tmp_path, knobs=None, ctl_knobs=None):
    live = tmp_path / "live"
    _arm(live, "H1c-sm-ctl", ctl_knobs or {})
    _arm(live, "H1c-sm", knobs or {})
    return A1.headless(live, PIN)


def _observe(out, visible, returned=True, prompt=False, recording=True, frames=True):
    if recording:
        with open(out / "observer.txt", "a", encoding="utf-8") as f:
            f.write("recording_sha256=" + "ab" * 32 + "\nrecording_bytes=1234\n")
    (out / "observation.json").write_text(json.dumps({
        "notice_visible": visible, "notice_text_seen": "MNEME-PROBE-..." if visible else "",
        "returned_to_input_prompt": returned, "unexpected_prompt": prompt, "notes": "",
        "frames": [{"t": "00:05", "file": "f1.png"}] if frames else []}), encoding="utf-8")


def _interactive(tmp_path, emit_obs, ctl_obs=None, knobs=None):
    live = tmp_path / "live"
    co = _arm(live, "H1c-sm-int-ctl", {"H1_STUB_SM_MODE": "drop"})
    eo = _arm(live, "H1c-sm-int", {"H1_STUB_SM_MODE": "drop", **(knobs or {})})
    _observe(co, **(ctl_obs or {"visible": False}))
    _observe(eo, **emit_obs)
    return A1.interactive(live)


# ---------------------------------------------------------------- emitter / setup / guards

def test_stop_systemmessage_emitter_shape(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "nonce.txt").write_text("MNEME-PROBE-0123456789abcdef\n", encoding="utf-8")
    p = subprocess.run([sys.executable, "-I", str(HARNESS / "emitter.py"), "stop-systemmessage", str(out)],
                       input=json.dumps({"hook_event_name": "Stop"}), capture_output=True, text=True)
    assert p.returncode == 0
    body = json.loads(p.stdout)
    assert set(body) == {"systemMessage"} and "MNEME-PROBE-0123456789abcdef" in body["systemMessage"]


@pytest.mark.parametrize("arm", ["H1c-sm", "H1c-sm-ctl", "H1c-sm-int", "H1c-sm-int-ctl"])
def test_a1_setup_registers_stop_only_and_hides_nonce(tmp_path, arm):
    pdir = tmp_path / arm
    setup_probe.main(["setup_probe.py", arm, str(pdir), sys.executable, str(HARNESS / "emitter.py")])
    settings = json.loads((pdir / "ws" / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert list(settings["hooks"]) == ["Stop"]
    cmd = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert (" noop " in cmd) == arm.endswith("-ctl") and ("stop-systemmessage" in cmd) != arm.endswith("-ctl")
    nonce = (pdir / "out" / "nonce.txt").read_text(encoding="utf-8").strip()
    assert nonce not in json.loads((pdir / "out" / "probe.json").read_text(encoding="utf-8"))["prompt"]


def test_safe_rmtree_a1_refuses_h1_and_archive_names():
    for name in ("H1c-stop", "H1a-edit", "2026-10-17", "../d5p2-h1-live"):
        p = subprocess.run([sys.executable, "-I", str(HARNESS / "safe_rmtree_a1.py"), "delete", name],
                           capture_output=True, text=True)
        assert p.returncode == 3, name


# ---------------------------------------------------------------- headless

def test_headless_dropped_systemmessage_is_not_delivered_without_interference(tmp_path):
    r = _headless(tmp_path, {"H1_STUB_SM_MODE": "drop"}, {"H1_STUB_SM_MODE": "drop"})
    assert r["label"] == "NOT_DELIVERED", r
    assert r["a1"]["host_interference"] == []


def test_headless_stream_informational_event_hits_strict_rule(tmp_path):
    # Known collision (classify_a1 docstring): an emitter-only stream system event
    # carrying the notice is a strict-rule subtype difference -> INCONCLUSIVE.
    r = _headless(tmp_path, {"H1_STUB_SM_MODE": "stream"}, {"H1_STUB_SM_MODE": "stream"})
    assert r["label"] == "INCONCLUSIVE", r
    assert any("host-event difference" in x for x in r["reasons"])
    assert {l["category"] for l in r["nonce_locations"]} == {"host_output"}


def test_headless_reentry_is_host_interference(tmp_path):
    r = _headless(tmp_path, {"H1_STUB_SM_MODE": "reenter"}, {"H1_STUB_SM_MODE": "reenter"})
    # The notice never reached the model, so the H1 label is NOT_DELIVERED; the
    # re-entry is still recorded as host interference, which fails A1 in combine().
    assert r["label"] == "NOT_DELIVERED", r
    assert "stop_hook_active re-entry" in r["a1"]["host_interference"]
    assert "Stop invocations differ from the control" in r["a1"]["host_interference"]


def test_headless_model_delivery(tmp_path):
    r = _headless(tmp_path, {"H1_STUB_SM_MODE": "model"}, {"H1_STUB_SM_MODE": "model"})
    assert r["label"] == "DELIVERED_TO_AGENT", r


def test_headless_model_reply_difference_is_evidence_only(tmp_path):
    r = _headless(tmp_path, {"H1_STUB_SM_MODE": "drop", "H1_STUB_ECHO_FORCE": "1"}, {"H1_STUB_SM_MODE": "drop"})
    # Echo without delivery is INCONCLUSIVE under the accepted table, but never interference.
    assert r["a1"]["host_interference"] == []


# ---------------------------------------------------------------- interactive

def test_interactive_developer_only_delivery(tmp_path):
    r = _interactive(tmp_path, {"visible": True})
    assert r["label"] == "DELIVERED_TO_USER_ONLY", r
    assert r["passes_run"] is True and r["host_interference"] == []


def test_interactive_notice_not_seen_is_not_delivered(tmp_path):
    r = _interactive(tmp_path, {"visible": False})
    assert r["label"] == "NOT_DELIVERED", r


def test_interactive_no_return_to_prompt_is_side_effect(tmp_path):
    r = _interactive(tmp_path, {"visible": True, "returned": False})
    assert r["label"] == "DELIVERED_WITH_SIDE_EFFECT", r


def test_interactive_unexpected_prompt_is_side_effect(tmp_path):
    r = _interactive(tmp_path, {"visible": True, "prompt": True})
    assert r["label"] == "DELIVERED_WITH_SIDE_EFFECT", r


def test_interactive_reentry_is_side_effect(tmp_path):
    r = _interactive(tmp_path, {"visible": True}, knobs={"H1_STUB_SM_MODE": "reenter"})
    assert r["label"] == "DELIVERED_WITH_SIDE_EFFECT", r


@pytest.mark.parametrize("missing", ["recording", "frames"])
def test_interactive_missing_capture_is_inconclusive(tmp_path, missing):
    r = _interactive(tmp_path, {"visible": True, missing: False})
    assert r["label"] == "INCONCLUSIVE", r


def test_interactive_control_showing_notice_is_inconclusive(tmp_path):
    r = _interactive(tmp_path, {"visible": True}, ctl_obs={"visible": True})
    assert r["label"] == "INCONCLUSIVE", r


def test_interactive_model_reply_difference_is_evidence_only(tmp_path):
    r = _interactive(tmp_path, {"visible": True}, knobs={"H1_STUB_ECHO_FORCE": "1"})
    assert r["host_interference"] == []


# ---------------------------------------------------------------- combine

def test_combine_user_only_with_clean_headless_passes(tmp_path):
    h = _headless(tmp_path / "h", {"H1_STUB_SM_MODE": "drop"}, {"H1_STUB_SM_MODE": "drop"})
    i = _interactive(tmp_path / "i", {"visible": True})
    c = A1.combine(h, i)
    assert c["label"] == "DELIVERED_TO_USER_ONLY" and c["h1c_passes_under_a1"] is True


def test_combine_headless_interference_fails(tmp_path):
    h = _headless(tmp_path / "h", {"H1_STUB_SM_MODE": "reenter"}, {"H1_STUB_SM_MODE": "reenter"})
    i = _interactive(tmp_path / "i", {"visible": True})
    c = A1.combine(h, i)
    assert c["label"] == "DELIVERED_WITH_SIDE_EFFECT" and c["h1c_passes_under_a1"] is False


def test_combine_inconclusive_headless_blocks_pass(tmp_path):
    h = _headless(tmp_path / "h", {"H1_STUB_SM_MODE": "stream"}, {"H1_STUB_SM_MODE": "stream"})
    i = _interactive(tmp_path / "i", {"visible": True})
    c = A1.combine(h, i)
    assert c["label"] == "INCONCLUSIVE" and c["h1c_passes_under_a1"] is False
