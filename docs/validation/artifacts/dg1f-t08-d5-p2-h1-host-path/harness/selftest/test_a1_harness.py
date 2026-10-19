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
PIN_VERSION = "2.1.202 (Claude Code)"


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


def _observe(out, visible, returned=True, prompt=False, recording=True, frames=True, text=None,
             frame_file="frames/f1.png", write_frame=True, version=PIN_VERSION):
    """Simulate the operator's capture: observer lines, a frame file and observation.json."""
    with open(out / "observer.txt", "a", encoding="utf-8") as f:
        if version is not None:
            f.write(f"claude_version={version}\n")
        if recording:
            f.write("recording_sha256=" + "ab" * 32 + "\nrecording_bytes=1234\n")
    nonce = (out / "nonce.txt").read_text(encoding="utf-8").strip()
    if write_frame and frames:
        fp = out / "frames" / "f1.png"
        fp.parent.mkdir(exist_ok=True)
        fp.write_bytes(b"PNGSTILL")
    if text is None:
        text = f"Stop hook: {nonce} This is a Mneme H1 channel-probe notice." if visible else ""
    (out / "observation.json").write_text(json.dumps({
        "notice_visible": visible, "notice_text_seen": text,
        "returned_to_input_prompt": returned, "unexpected_prompt": prompt, "notes": "",
        "frames": [{"t": "00:05", "file": frame_file}] if frames else []}), encoding="utf-8")


def _review(out, notice, shows, reviewer="independent reviewer", sha=None, frame_sha=None, skip=False):
    """Simulate the evidence review of one arm's capture (capture_review.json)."""
    if skip:
        return
    import hashlib
    obs = dict(l.split("=", 1) for l in (out / "observer.txt").read_text(encoding="utf-8").splitlines() if "=" in l)
    o = json.loads((out / "observation.json").read_text(encoding="utf-8"))
    frames = []
    for f in o.get("frames") or []:
        fp = out / f["file"]
        h = hashlib.sha256(fp.read_bytes()).hexdigest() if fp.is_file() else "0" * 64
        frames.append({"file": f["file"], "sha256": frame_sha or h, "shows_nonce": shows})
    (out / "capture_review.json").write_text(json.dumps({
        "reviewer": reviewer, "recording_sha256": sha or obs.get("recording_sha256"),
        "notice_visible": notice, "frames": frames}), encoding="utf-8")


def _interactive(tmp_path, emit_obs, ctl_obs=None, knobs=None, ctl_knobs=None, drop_transcript=None,
                 emit_review=None, ctl_review=None):
    live = tmp_path / "live"
    co = _arm(live, "H1c-sm-int-ctl", {"H1_STUB_SM_MODE": "drop", **(ctl_knobs or {})})
    eo = _arm(live, "H1c-sm-int", {"H1_STUB_SM_MODE": "drop", **(knobs or {})})
    _observe(co, **(ctl_obs or {"visible": False}))
    _observe(eo, **emit_obs)
    if drop_transcript:
        (live / drop_transcript / "out" / "transcript.jsonl").unlink()
    _review(eo, **(emit_review or {"notice": True, "shows": True}))
    _review(co, **(ctl_review or {"notice": False, "shows": False}))
    return A1.interactive(live, PIN_VERSION, PIN)


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


# ---------------------------------------------------------------- review of #556: verified delivery

def test_interactive_pass_records_verified_frame_hashes(tmp_path):
    r = _interactive(tmp_path, {"visible": True})
    assert r["label"] == "DELIVERED_TO_USER_ONLY", r
    assert r["frames_verified"] and len(r["frames_verified"][0]["sha256"]) == 64


def test_interactive_observed_text_without_nonce_is_inconclusive(tmp_path):
    r = _interactive(tmp_path, {"visible": True, "text": "some warning without the token"})
    assert r["label"] == "INCONCLUSIVE", r
    assert any("exact nonce" in x for x in r["reasons"])


def test_interactive_control_text_containing_nonce_is_inconclusive(tmp_path):
    live = tmp_path / "live"
    r0 = _interactive(tmp_path, {"visible": True})
    nonce = (live / "H1c-sm-int" / "out" / "nonce.txt").read_text(encoding="utf-8").strip()
    obs = live / "H1c-sm-int-ctl" / "out" / "observation.json"
    o = json.loads(obs.read_text(encoding="utf-8"))
    o["notice_text_seen"] = nonce
    obs.write_text(json.dumps(o), encoding="utf-8")
    r = A1.interactive(live, PIN_VERSION, PIN)
    assert r0["label"] == "DELIVERED_TO_USER_ONLY", r0
    assert r["label"] == "INCONCLUSIVE", r


@pytest.mark.parametrize("frame_file, write", [("frames/f1.png", False), ("../escape.png", True), ("", True)])
def test_interactive_unverifiable_frame_is_inconclusive(tmp_path, frame_file, write):
    r = _interactive(tmp_path, {"visible": True, "frame_file": frame_file, "write_frame": write})
    assert r["label"] == "INCONCLUSIVE", r


@pytest.mark.parametrize("arm", ["H1c-sm-int", "H1c-sm-int-ctl"])
def test_interactive_missing_transcript_is_inconclusive(tmp_path, arm):
    r = _interactive(tmp_path, {"visible": True}, drop_transcript=arm)
    assert r["label"] == "INCONCLUSIVE", r
    assert any("transcript not collected" in x for x in r["reasons"])


# ---------------------------------------------------------------- review of #556: pins enforced

def test_interactive_version_mismatch_is_not_executed(tmp_path):
    r = _interactive(tmp_path, {"visible": True, "version": "2.1.999 (Claude Code)"})
    assert r["label"] == "NOT_EXECUTED", r
    assert any("pin mismatch" in x for x in r["reasons"])


def test_interactive_model_mismatch_is_not_executed(tmp_path):
    r = _interactive(tmp_path, {"visible": True}, knobs={"H1_STUB_TRANSCRIPT_MODEL": "claude-other-1"})
    assert r["label"] == "NOT_EXECUTED", r


def test_interactive_model_unrecorded_is_inconclusive(tmp_path):
    r = _interactive(tmp_path, {"visible": True}, ctl_knobs={"H1_STUB_TRANSCRIPT_MODEL": "none"})
    assert r["label"] == "INCONCLUSIVE", r
    assert any("pin unverifiable" in x for x in r["reasons"])


def test_pinned_model_suffix_is_stripped_for_transcript_comparison():
    assert A1._base_model("claude-opus-4-8[1m]") == "claude-opus-4-8"


# ---------------------------------------------------------------- review of #556 (round 2): capture review

def test_interactive_pass_requires_confirmed_capture_review(tmp_path):
    r = _interactive(tmp_path, {"visible": True})
    assert r["label"] == "DELIVERED_TO_USER_ONLY" and r["capture_review"] == "confirmed", r
    assert r["control_frames_verified"]


@pytest.mark.parametrize("which", ["emitter", "control"])
def test_interactive_missing_capture_review_is_inconclusive(tmp_path, which):
    kw = {"emit_review": {"notice": True, "shows": True, "skip": True}} if which == "emitter" else \
         {"ctl_review": {"notice": False, "shows": False, "skip": True}}
    r = _interactive(tmp_path, {"visible": True}, **kw)
    assert r["label"] == "INCONCLUSIVE", r
    assert any("capture review pending" in x and which in x for x in r["reasons"])


def test_interactive_missing_control_capture_frames_is_inconclusive(tmp_path):
    r = _interactive(tmp_path, {"visible": True}, ctl_obs={"visible": False, "frames": False})
    assert r["label"] == "INCONCLUSIVE", r
    assert any("control" in x and "frames" in x for x in r["reasons"])


def test_interactive_review_not_bound_to_recording_is_inconclusive(tmp_path):
    r = _interactive(tmp_path, {"visible": True}, emit_review={"notice": True, "shows": True, "sha": "cd" * 32})
    assert r["label"] == "INCONCLUSIVE", r


def test_interactive_review_frame_hash_mismatch_is_inconclusive(tmp_path):
    r = _interactive(tmp_path, {"visible": True}, ctl_review={"notice": False, "shows": False, "frame_sha": "ef" * 32})
    assert r["label"] == "INCONCLUSIVE", r


def test_interactive_review_not_showing_nonce_is_inconclusive(tmp_path):
    r = _interactive(tmp_path, {"visible": True}, emit_review={"notice": True, "shows": False})
    assert r["label"] == "INCONCLUSIVE", r
    assert any("does not confirm the nonce" in x for x in r["reasons"])


def test_interactive_control_review_finding_notice_is_inconclusive(tmp_path):
    r = _interactive(tmp_path, {"visible": True}, ctl_review={"notice": False, "shows": True})
    assert r["label"] == "INCONCLUSIVE", r


def test_interactive_review_without_reviewer_is_inconclusive(tmp_path):
    r = _interactive(tmp_path, {"visible": True}, emit_review={"notice": True, "shows": True, "reviewer": " "})
    assert r["label"] == "INCONCLUSIVE", r
