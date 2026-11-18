"""Offline self-tests for the batch-2 harness. Stub hosts only; never evidence.

Run: python -m pytest docs/validation/artifacts/dg1f-t08-d5-p2-batch2-host-path/harness/selftest -q
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
import common  # noqa: E402
import check_pins  # noqa: E402
import h4a_arm  # noqa: E402
import h4a_classify  # noqa: E402
import h6_arm  # noqa: E402
import h6_classify  # noqa: E402

STUB_AG = HARNESS / "selftest" / "stub_antigravity.py"
ORIG_GUARD = common.guard_live_root
STUB_KNOBS = ("STUB_AG_", "STUB_H_")


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    # The pytest temp root sits under the user's home, whose own .claude
    # settings would trip the live-root guard; it has its own tests below.
    monkeypatch.setattr(common, "guard_live_root", lambda root: [])
    for k in list(os.environ):
        if k.startswith(STUB_KNOBS) or k.startswith("MNEME_"):
            monkeypatch.delenv(k, raising=False)


# ---------------------------------------------------------------- emitters

def _emit(mode, out, payload="{}"):
    return subprocess.run([sys.executable, str(HARNESS / "h4a_emitter.py"), mode, str(out)],
                          input=payload, capture_output=True, text=True)


def test_h4a_emitter_shapes(tmp_path):
    (tmp_path / "nonce.txt").write_text("MNEME-PROBE-0123456789abcdef\n", encoding="utf-8")
    a, b, n = _emit("empty-stderr", tmp_path), _emit("reason-only", tmp_path), _emit("noop", tmp_path)
    assert (a.returncode, b.returncode, n.returncode) == (0, 0, 0)
    assert json.loads(a.stdout) == {} and "MNEME-PROBE-0123456789abcdef" in a.stderr
    assert set(json.loads(b.stdout)) == {"reason"} and "MNEME-PROBE-0123456789abcdef" in b.stdout
    assert json.loads(n.stdout) == {} and n.stderr == ""
    for p in (a, b, n):
        assert "decision" not in p.stdout
    log = common.read_jsonl(tmp_path / "hook-log.jsonl")
    assert [r["mode"] for r in log] == ["empty-stderr", "reason-only", "noop"]


def test_h4a_emitter_misuse_still_emits_one_object(tmp_path):
    p = _emit("allow", tmp_path)
    assert p.returncode == 0 and json.loads(p.stdout) == {}


# ---------------------------------------------------------------- H4a flow

def _h4a_arm(root, arm, monkeypatch, review_over=None):
    assert h4a_arm.prepare(root, arm, True, "") == 0
    d = root / arm
    subprocess.run([sys.executable, str(STUB_AG), str(d)], check=True)
    rec = d / "recording.mp4"
    rec.write_bytes(b"stub recording " + arm.encode())
    assert h4a_arm.finish(root, arm, str(rec), "") == 0
    ui = json.loads((d / "hoststate" / "ui.json").read_text(encoding="utf-8"))
    shown = " ".join(x["text"] for x in ui["shown"])
    review = {"reviewer": "selftest", "recording_sha256": h4a_arm.sha256(rec),
              "host_version_shown": "2.8.1", "agent_ran_tool": ui["tool_allowed"],
              "permission_prompt_shown": ui["permission_prompt_shown"],
              "host_error_or_block_shown": any(x["kind"] == "host_error" for x in ui["shown"]),
              "nonce_seen_in_ui": "MNEME-PROBE-" in shown, "nonce_ui_location": "", "notes": ""}
    review.update(review_over or {})
    common.write_json(d / "out" / "capture_review.json", review)


def _h4a(tmp_path, monkeypatch, cand, review_over=None):
    _h4a_arm(tmp_path, f"h4a-{cand}", monkeypatch, review_over)
    _h4a_arm(tmp_path, f"h4a-{cand}-ctl", monkeypatch)
    return h4a_classify.classify_pair(tmp_path, cand)


def test_h4a_reason_to_agent_passes(tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_AG_REASON_TO", "agent")
    r = _h4a(tmp_path, monkeypatch, "B")
    assert r["label"] == common.DELIVERED_TO_AGENT and r["accepted_without_side_effect"]


def test_h4a_reason_to_user_only(tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_AG_REASON_TO", "user")
    monkeypatch.setenv("STUB_AG_ECHO", "0")
    r = _h4a(tmp_path, monkeypatch, "B")
    assert r["label"] == common.DELIVERED_TO_USER_ONLY


def test_h4a_decision_required_fails_closed_is_not_accepted(tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_AG_DECISION_REQUIRED", "1")
    r = _h4a(tmp_path, monkeypatch, "B")
    # The control's {} is also invalid under this knob, so the control fails
    # its own path-type control: that can never count as a host verdict.
    assert r["label"] == common.INCONCLUSIVE
    assert "control arm failed its own path-type control" in r["reasons"]


def test_h4a_stderr_invisible_is_not_delivered(tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_AG_STDERR_TO", "none")
    r = _h4a(tmp_path, monkeypatch, "A")
    assert r["label"] == common.NOT_DELIVERED and r["accepted_without_side_effect"]


def test_h4a_stderr_shown_to_user(tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_AG_STDERR_TO", "user")
    r = _h4a(tmp_path, monkeypatch, "A")
    assert r["label"] == common.DELIVERED_TO_USER_ONLY


def test_h4a_side_effect(tmp_path, monkeypatch):
    r = _h4a(tmp_path, monkeypatch, "B", {"permission_prompt_shown": True})
    assert r["label"] == common.DELIVERED_WITH_SIDE_EFFECT


def test_h4a_missing_review_is_not_executed(tmp_path, monkeypatch):
    _h4a_arm(tmp_path, "h4a-B", monkeypatch)
    _h4a_arm(tmp_path, "h4a-B-ctl", monkeypatch)
    (tmp_path / "h4a-B" / "out" / "capture_review.json").unlink()
    assert h4a_classify.classify_pair(tmp_path, "B")["label"] == common.NOT_EXECUTED


def test_h4a_live_review_must_bind_recording_and_pin(tmp_path, monkeypatch):
    meta = {"recording_sha256": "aa"}
    p = h4a_classify._review_problems({"reviewer": "x", "recording_sha256": "bb",
                                       "host_version_shown": "2.17.0",
                                       **{k: False for k in h4a_classify.REVIEW_BOOLS}},
                                      meta, "2.8.1")
    assert any("recording" in x for x in p) and any("differs from pin" in x for x in p)


def test_h4a_nonce_in_control_is_inconclusive(tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_AG_REASON_TO", "agent")
    _h4a_arm(tmp_path, "h4a-B", monkeypatch)
    _h4a_arm(tmp_path, "h4a-B-ctl", monkeypatch)
    nonce = (tmp_path / "h4a-B" / "out" / "nonce.txt").read_text(encoding="utf-8")
    (tmp_path / "h4a-B-ctl" / "out" / "stray.txt").write_text(nonce, encoding="utf-8")
    assert h4a_classify.classify_pair(tmp_path, "B")["label"] == common.INCONCLUSIVE


def test_h4a_unclassified_transcript_is_inconclusive(tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_AG_REASON_TO", "agent")
    _h4a_arm(tmp_path, "h4a-B", monkeypatch)
    _h4a_arm(tmp_path, "h4a-B-ctl", monkeypatch)
    out = tmp_path / "h4a-B" / "out"
    t = next(out.glob("transcript.*"))
    nonce = (out / "nonce.txt").read_text(encoding="utf-8").strip()
    t.write_text(t.read_text(encoding="utf-8") + json.dumps({"kind": "x", "v": nonce}) + "\n",
                 encoding="utf-8")
    assert h4a_classify.classify_pair(tmp_path, "B")["label"] == common.INCONCLUSIVE


def test_arm_is_never_reused(tmp_path):
    assert h4a_arm.prepare(tmp_path, "h4a-A", True, "") == 0
    assert h4a_arm.prepare(tmp_path, "h4a-A", True, "") == 1


def test_h4a_live_prepare_refuses_pin_mismatch(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.setattr(common, "antigravity_global_hooks", lambda: [])
    assert h4a_arm.prepare(tmp_path, "h4a-A", False, "2.17.0") == 1
    assert not (tmp_path / "h4a-A").exists()


# ---------------------------------------------------------------- path summary

def _c(label, accepted=True, cand="X"):
    return {"candidate": cand, "label": label, "accepted_without_side_effect": accepted}


def test_summarize_path():
    s = common.summarize_path
    assert s("H4a", [_c(common.NOT_DELIVERED), _c(common.DELIVERED_TO_AGENT, cand="B")])["bound_shape"] == "B"
    assert s("H4a", [_c(common.NOT_DELIVERED, False), _c(common.NOT_DELIVERED, False)])["label"] == \
        common.NO_NONBLOCKING_CHANNEL
    assert s("H4a", [_c(common.NOT_DELIVERED), _c(common.NOT_EXECUTED)])["label"] == common.NOT_EXECUTED
    assert s("H4a", [_c(common.NOT_DELIVERED), _c(common.INCONCLUSIVE)])["label"] == common.INCONCLUSIVE
    assert s("H4a", [_c(common.NOT_DELIVERED), _c(common.NOT_DELIVERED, False)])["label"] == \
        common.NOT_DELIVERED


# ---------------------------------------------------------------- H6 flow

class _A:
    selftest, live = True, False
    hermes = python = model = provider = ""


def _h6_pair(root, arm):
    for a in (arm, h6_classify.PAIRS[arm]):
        assert h6_arm.prepare(root, a, True) == 0
        assert h6_arm.run(root, a, _A()) == 0


def test_h6b_ephemeral_context_is_not_counted_by_default(tmp_path):
    _h6_pair(tmp_path, "h6b")
    r = h6_classify.classify_pair(tmp_path, "h6b")
    assert r["path"] == "H6b" and r["label"] == common.INCONCLUSIVE
    assert r["observer_evidence"] and not any(l["category"] == "model_bound" for l in r["locations"])


def test_h6b_observer_counted_only_on_owner_decision(tmp_path):
    _h6_pair(tmp_path, "h6b")
    assert h6_classify.classify_pair(tmp_path, "h6b", True)["label"] == common.DELIVERED_TO_AGENT


def test_h6b_persisted_context_is_host_record(tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_H_PERSIST_CONTEXT", "1")
    _h6_pair(tmp_path, "h6b")
    assert h6_classify.classify_pair(tmp_path, "h6b")["label"] == common.DELIVERED_TO_AGENT


def test_h6b_no_record_anywhere_is_not_delivered(tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_H_API_MESSAGES", "0")
    monkeypatch.setenv("STUB_H_ECHO", "0")
    _h6_pair(tmp_path, "h6b")
    assert h6_classify.classify_pair(tmp_path, "h6b")["label"] == common.NOT_DELIVERED


def test_h6a_transform_passes_in_host_record(tmp_path):
    _h6_pair(tmp_path, "h6a-T")
    r = h6_classify.classify_pair(tmp_path, "h6a-T")
    assert r["path"] == "H6a" and r["label"] == common.DELIVERED_TO_AGENT
    assert r["controls"]["tool_result_otherwise_unchanged"]


def test_h6a_transform_altered_result_is_side_effect(tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_H_MUTATE_RESULT", "1")
    _h6_pair(tmp_path, "h6a-T")
    r = h6_classify.classify_pair(tmp_path, "h6a-T")
    assert r["label"] == common.DELIVERED_WITH_SIDE_EFFECT


def test_h6a_transform_ignored_is_not_delivered(tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_H_IGNORE_TRANSFORM", "1")
    monkeypatch.setenv("STUB_H_ECHO", "0")
    _h6_pair(tmp_path, "h6a-T")
    assert h6_classify.classify_pair(tmp_path, "h6a-T")["label"] == common.NOT_DELIVERED


def test_h6a_next_turn_spans_two_processes(tmp_path):
    _h6_pair(tmp_path, "h6a-N")
    r = h6_classify.classify_pair(tmp_path, "h6a-N")
    hooks = common.read_jsonl(tmp_path / "h6a-N" / "out" / "hook-log.jsonl")
    assert any(h["hook"] == "pre_llm_call" and h["returned"] for h in hooks)
    assert r["label"] == common.INCONCLUSIVE  # ephemeral context: owner decision D3
    assert h6_classify.classify_pair(tmp_path, "h6a-N", True)["label"] == common.DELIVERED_TO_AGENT


def test_h6_tool_not_called_is_not_executed(tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_H_NO_TOOL", "1")
    _h6_pair(tmp_path, "h6a-T")
    assert h6_classify.classify_pair(tmp_path, "h6a-T")["label"] == common.NOT_EXECUTED


def test_h6_failed_turn_is_side_effect(tmp_path, monkeypatch):
    assert h6_arm.prepare(tmp_path, "h6a-T-ctl", True) == 0
    assert h6_arm.run(tmp_path, "h6a-T-ctl", _A()) == 0
    monkeypatch.setenv("STUB_H_FAIL", "1")
    assert h6_arm.prepare(tmp_path, "h6a-T", True) == 0
    assert h6_arm.run(tmp_path, "h6a-T", _A()) == 0
    r = h6_classify.classify_pair(tmp_path, "h6a-T")
    assert r["label"] == common.DELIVERED_WITH_SIDE_EFFECT
    assert r["controls"]["turns_completed"] is False


def test_h6a_and_h6b_are_separate(tmp_path):
    _h6_pair(tmp_path, "h6b")
    _h6_pair(tmp_path, "h6a-T")
    nb = (tmp_path / "h6b" / "out" / "nonce.txt").read_text(encoding="utf-8")
    na = (tmp_path / "h6a-T" / "out" / "nonce.txt").read_text(encoding="utf-8")
    assert nb != na
    assert not common.tree_text_contains(tmp_path / "h6a-T", nb.strip())
    for target in ("H6a", "H6b"):
        assert h6_classify.main(["x", "path", str(tmp_path), target]) == 0
    a = common.read_json(tmp_path / "outcome.H6a.json")
    b = common.read_json(tmp_path / "outcome.H6b.json")
    assert a["path"] == "H6a" and b["path"] == "H6b"
    assert all(c.get("arm") != "h6b" for c in a["candidates"])


def test_h6_mismatched_pair_is_not_executed(tmp_path):
    for a in ("h6b", "h6a-T-ctl"):
        assert h6_arm.prepare(tmp_path, a, True) == 0
        assert h6_arm.run(tmp_path, a, _A()) == 0
    shutil.copytree(tmp_path / "h6a-T-ctl", tmp_path / "h6b-ctl")
    r = h6_classify.classify_pair(tmp_path, "h6b")
    assert r["label"] == common.NOT_EXECUTED
    assert any("different paths" in x for x in r["reasons"])


def test_h6_live_refuses_stub_and_missing_pins(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    assert h6_arm.prepare(tmp_path, "h6b", False) == 0

    class Live(_A):
        selftest, live = False, True
        hermes = str(h6_arm.STUB)
        python = sys.executable
    assert h6_arm.run(tmp_path, "h6b", Live()) == 1
    assert not (tmp_path / "h6b" / "out" / "arm.json").exists()


def test_h6_selftest_refuses_live_prepared_arm(tmp_path):
    assert h6_arm.prepare(tmp_path, "h6b", False) == 0
    assert h6_arm.run(tmp_path, "h6b", _A()) == 1


# ---------------------------------------------------------------- guards

def test_guard_live_root_detects_loadable_ancestors(tmp_path):
    g = ORIG_GUARD
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents" / "hooks.json").write_text("{}", encoding="utf-8")
    (tmp_path / "live").mkdir()
    assert any(".agents/hooks.json" in p for p in g(tmp_path / "live"))
    (tmp_path / "live" / ".git").mkdir()
    assert any("Git checkout" in p for p in g(tmp_path / "live"))


def test_guard_env():
    assert common.guard_env({"CLAUDECODE": "1", "MNEME_MEMORY": "x"})
    assert common.guard_env({"PATH": "x"}) == []


def test_antigravity_global_hooks(tmp_path):
    assert common.antigravity_global_hooks(tmp_path) == []
    p = tmp_path / ".gemini" / "config" / "plugins" / "x"
    p.mkdir(parents=True)
    (p / "hooks.json").write_text("{}", encoding="utf-8")
    assert common.antigravity_global_hooks(tmp_path)


def test_leak_scan(tmp_path):
    (tmp_path / "a.txt").write_text("key=sk-secret-value-123", encoding="utf-8")
    assert common.leak_scan(tmp_path, ["K"], {"K": "sk-secret-value-123"})
    assert common.leak_scan(tmp_path, ["K"], {"K": "other-value-456"}) == []


def test_check_pins_reports_mismatch_without_fixing():
    ok, msg = check_pins.check("antigravity", "2.17.0.0")
    assert not ok and "MISMATCH" in msg and "2.8.1" in msg
    assert check_pins.check("antigravity", "2.8.1.0")[0]
