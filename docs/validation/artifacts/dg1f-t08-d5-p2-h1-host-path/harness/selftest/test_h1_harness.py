"""Offline validation of the H1 probe harness. NOT live evidence.

Run:  python -m pytest -q docs/validation/artifacts/dg1f-t08-d5-p2-h1-host-path/harness/selftest

Each case builds an emitter arm and its paired no-op control arm in a temporary
directory with the real setup_probe.py and emitter.py, drives them with the
self-test stub (not Claude Code) under a knob, and checks that classify_h1.py
assigns the scope section 6 label the knob was designed to produce. The stub's
delivery behavior is a test fixture, not a claim about Claude Code.
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
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


classify_h1 = _load("classify_h1")
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


def _run(tmp_path, path_id, knobs=None, ctl_knobs=None, pin=PIN):
    live = tmp_path / "live"
    _arm(live, f"{path_id}-ctl", ctl_knobs or {})
    _arm(live, path_id, knobs or {})
    emit = classify_h1.load_arm(live / path_id / "out")
    ctl = classify_h1.load_arm(live / f"{path_id}-ctl" / "out")
    return classify_h1.classify(emit, ctl, path_id, pin)


@pytest.mark.parametrize("path_id", ["H1a-edit", "H1a-bash", "H1b-start", "H1c-stop"])
def test_user_text_delivery_is_delivered_to_agent(tmp_path, path_id):
    r = _run(tmp_path, path_id)
    assert r["label"] == "DELIVERED_TO_AGENT", r
    assert r["passes_path"] is True
    assert {l["category"] for l in r["nonce_locations"]} >= {"model_bound"}
    assert r["developer_also"] == "not_observed"


def test_tool_result_delivery_counts_as_model_bound(tmp_path):
    r = _run(tmp_path, "H1a-edit", {"H1_STUB_DELIVERY": "tool_result"})
    assert r["label"] == "DELIVERED_TO_AGENT", r


def test_echo_is_recorded_but_not_required(tmp_path):
    r = _run(tmp_path, "H1a-edit", {"H1_STUB_ECHO": "1"})
    assert r["label"] == "DELIVERED_TO_AGENT" and r["echoed"] is True


def test_turn_count_difference_is_evidence_only(tmp_path):
    # Echo changes the reply; turns are recorded, never pass/fail (scope section 3 step 4).
    r = _run(tmp_path, "H1a-bash", {"H1_STUB_ECHO": "1"})
    assert r["label"] == "DELIVERED_TO_AGENT"
    assert "turns" in r and "turns_control" in r


def test_host_block_is_side_effect(tmp_path):
    r = _run(tmp_path, "H1a-edit", {"H1_STUB_BLOCK": "1"})
    assert r["label"] == "DELIVERED_WITH_SIDE_EFFECT", r
    assert r["passes_path"] is False


def test_stop_reentry_is_side_effect(tmp_path):
    r = _run(tmp_path, "H1c-stop", {"H1_STUB_STOP_REENTER": "1"})
    assert r["label"] == "DELIVERED_WITH_SIDE_EFFECT", r


def test_dropped_context_is_not_delivered(tmp_path):
    r = _run(tmp_path, "H1a-edit", {"H1_STUB_DELIVERY": "none"})
    assert r["label"] == "NOT_DELIVERED", r


def test_host_output_event_alone_is_not_delivery(tmp_path):
    r = _run(tmp_path, "H1a-edit", {"H1_STUB_DELIVERY": "host_event"})
    assert r["label"] == "NOT_DELIVERED", r
    assert {l["category"] for l in r["nonce_locations"]} == {"host_output"}


def test_unrecognised_location_is_inconclusive(tmp_path):
    r = _run(tmp_path, "H1a-edit", {"H1_STUB_DELIVERY": "attachment"})
    assert r["label"] == "INCONCLUSIVE", r
    assert any("category table" in x for x in r["reasons"])


def test_echo_without_delivery_is_inconclusive(tmp_path):
    r = _run(tmp_path, "H1a-edit", {"H1_STUB_DELIVERY": "none", "H1_STUB_ECHO_FORCE": "1"})
    assert r["label"] == "INCONCLUSIVE", r


def test_nonce_leak_is_inconclusive(tmp_path):
    r = _run(tmp_path, "H1a-edit", {"H1_STUB_LEAK": "1"})
    assert r["label"] == "INCONCLUSIVE", r
    assert any("leak" in x for x in r["reasons"])


def test_failed_control_arm_is_inconclusive(tmp_path):
    r = _run(tmp_path, "H1a-edit", ctl_knobs={"H1_STUB_FAIL_TOOL": "1"})
    assert r["label"] == "INCONCLUSIVE", r


def test_sessionstart_not_fired_is_not_executed(tmp_path):
    knob = {"H1_STUB_NO_SESSIONSTART": "1"}
    r = _run(tmp_path, "H1b-start", knob, knob)
    assert r["label"] == "NOT_EXECUTED", r


def test_model_pin_mismatch_is_not_executed(tmp_path):
    r = _run(tmp_path, "H1a-edit", pin="some-other-model")
    assert r["label"] == "NOT_EXECUTED", r


def test_no_transcript_and_no_delivery_is_inconclusive(tmp_path):
    knob = {"H1_STUB_DELIVERY": "none", "H1_STUB_NO_TRANSCRIPT": "1"}
    r = _run(tmp_path, "H1a-edit", knob)
    assert r["label"] == "INCONCLUSIVE", r


def test_unclassified_location_blocks_pass_even_with_model_bound(tmp_path):
    # Review of #546, finding 1: unclassified-first.
    r = _run(tmp_path, "H1a-edit", {"H1_STUB_DUAL": "1"})
    cats = {l["category"] for l in r["nonce_locations"]}
    assert {"model_bound", "unclassified"} <= cats
    assert r["label"] == "INCONCLUSIVE", r
    assert r["passes_path"] is False


def test_emitter_only_denial_is_side_effect(tmp_path):
    # Review of #546, finding 2: a demonstrated permission difference.
    r = _run(tmp_path, "H1a-edit", {"H1_STUB_DENY_EXTRA": "1"})
    assert r["controls"]["common"]["permission_outcomes_equal"] is False
    assert r["label"] == "DELIVERED_WITH_SIDE_EFFECT", r


def test_equal_denial_counts_with_different_denials_are_not_equal(tmp_path):
    # Same count (one each), different denial: never treated as equivalent.
    live = tmp_path / "live"
    r = _run(tmp_path, "H1a-edit")
    emit = classify_h1.load_arm(live / "H1a-edit" / "out")
    ctl = classify_h1.load_arm(live / "H1a-edit-ctl" / "out")
    for arm, tool in ((emit, "Write"), (ctl, "Bash")):
        classify_h1.result_event(arm)["permission_denials"] = [
            {"tool_name": tool, "tool_use_id": "x", "tool_input": {}}]
    r = classify_h1.classify(emit, ctl, "H1a-edit", PIN)
    assert r["controls"]["common"]["permission_outcomes_equal"] is False
    assert r["label"] == "DELIVERED_WITH_SIDE_EFFECT", r


@pytest.mark.parametrize("which", ["emitter", "control"])
def test_missing_permission_field_is_inconclusive(tmp_path, which):
    knob = {"H1_STUB_NO_DENIALS_FIELD": "1"}
    r = _run(tmp_path, "H1a-edit", knob if which == "emitter" else None,
             knob if which == "control" else None)
    assert r["label"] == "INCONCLUSIVE", r
    assert any("permission equivalence" in x for x in r["reasons"])


def test_unexplained_host_event_difference_is_inconclusive(tmp_path):
    r = _run(tmp_path, "H1a-edit", {"H1_STUB_EXTRA_SYSTEM": "1"})
    assert r["label"] == "INCONCLUSIVE", r
    assert any("host-event difference" in x for x in r["reasons"])


def test_bash_content_must_match_exactly(tmp_path):
    live = tmp_path / "live"
    _run(tmp_path, "H1a-bash")
    for arm in ("H1a-bash", "H1a-bash-ctl"):
        (live / arm / "ws" / "bash_out.txt").write_bytes(b"probe-ran extra\n")
    emit = classify_h1.load_arm(live / "H1a-bash" / "out")
    ctl = classify_h1.load_arm(live / "H1a-bash-ctl" / "out")
    r = classify_h1.classify(emit, ctl, "H1a-bash", PIN)
    # The control arm now fails its own path-type control, so nothing is attributable.
    assert r["controls"]["path_type_emitter"]["file_as_expected"] is False
    assert r["label"] == "INCONCLUSIVE", r


def test_bash_prompt_has_exact_backticked_command(tmp_path):
    pdir = tmp_path / "H1a-bash"
    setup_probe.main(["setup_probe.py", "H1a-bash", str(pdir), sys.executable, str(HARNESS / "emitter.py")])
    prompt = json.loads((pdir / "out" / "probe.json").read_text(encoding="utf-8"))["prompt"]
    assert "`echo probe-ran > bash_out.txt`" in prompt
    assert "bash_out.txt ." not in prompt


def test_summary_states_done_is_not_pass(tmp_path):
    live = tmp_path / "live"
    for p in classify_h1.PATHS:
        _run(tmp_path, p)
        classify_h1.cmd_pair(str(live), p, PIN)
    classify_h1.cmd_summary(str(live), "summary.md")
    text = (live / "summary.md").read_text(encoding="utf-8")
    assert "Only the gate line above decides H1" in text and "never means H1 passed" in text


def test_emitter_never_emits_permission_decision(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "nonce.txt").write_text("MNEME-PROBE-0123456789abcdef\n", encoding="utf-8")
    for mode in ("pretooluse", "sessionstart", "stop", "noop"):
        p = subprocess.run([sys.executable, "-I", str(HARNESS / "emitter.py"), mode, str(out)],
                           input=json.dumps({"hook_event_name": "X"}), capture_output=True, text=True)
        assert p.returncode == 0
        if mode == "noop":
            assert p.stdout == ""
        else:
            hso = json.loads(p.stdout)["hookSpecificOutput"]
            assert "permissionDecision" not in hso
            assert "MNEME-PROBE-0123456789abcdef" in hso["additionalContext"]


def test_prompt_never_contains_the_nonce(tmp_path):
    for arm in ("H1a-edit", "H1a-bash", "H1b-start", "H1c-stop", "H1a-edit-ctl"):
        pdir = tmp_path / arm
        setup_probe.main(["setup_probe.py", arm, str(pdir), sys.executable, str(HARNESS / "emitter.py")])
        nonce = (pdir / "out" / "nonce.txt").read_text(encoding="utf-8").strip()
        meta = json.loads((pdir / "out" / "probe.json").read_text(encoding="utf-8"))
        assert nonce not in meta["prompt"] and "MNEME-PROBE-" in meta["prompt"]
        settings = (pdir / "ws" / ".claude" / "settings.json").read_text(encoding="utf-8")
        assert nonce not in settings and '"env"' not in settings
