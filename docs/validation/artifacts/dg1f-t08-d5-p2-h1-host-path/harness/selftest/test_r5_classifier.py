"""Offline validation of rule R5 (host_record) in classify_h1.py. NOT live evidence.

Rule: docs/plans/2026-11-11-dg1f-t08-d5-p2-a2-r5-host-record-rule.md (#796, #797), §3 and
the §7 regression list, including the wrong-tool cases from the #796 review.

Each case drives the self-test stub in its `hook_r5` delivery mode, which writes the
Claude Code 2.1.310 transcript shape recorded in #795, then (for negative cases)
mutates the emitter arm's transcript or hook log before classifying. The stub's
behaviour is a test fixture, not a claim about Claude Code.
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
ARTIFACTS = HARNESS.parent


def _load(name):
    sys.path.insert(0, str(HARNESS))
    spec = importlib.util.spec_from_file_location(name, HARNESS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C = _load("classify_h1")
setup_probe = _load("setup_probe")
LABEL = {"H1a-edit": "PreToolUse:Edit", "H1a-bash": "PreToolUse:Bash", "H1b-start": "SessionStart"}


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


def _rows(p):
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _write(p, rows):
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _run(tmp_path, path_id, mutate=None):
    """Classify a stub pair in the 2.1.310 shape; mutate(transcript, hooks, nonce) edits the emitter."""
    live = tmp_path / "live"
    _arm(live, f"{path_id}-ctl", {"H1_STUB_DELIVERY": "hook_r5"})
    _arm(live, path_id, {"H1_STUB_DELIVERY": "hook_r5", "H1_STUB_ECHO": "1"})
    out = live / path_id / "out"
    if mutate:
        tr, hl = _rows(out / "transcript.jsonl"), _rows(out / "hook-log.jsonl")
        mutate(tr, hl, (out / "nonce.txt").read_text(encoding="utf-8").strip())
        _write(out / "transcript.jsonl", tr)
        _write(out / "hook-log.jsonl", hl)
    emit = C.load_arm(out)
    ctl = C.load_arm(live / f"{path_id}-ctl" / "out")
    r = C.classify(emit, ctl, path_id, PIN)
    # classify() returns early (INCONCLUSIVE) when the emitter is not attributed, before
    # it records nonce_locations; the categories are always computed directly here.
    spec = C.PATHS[path_id]
    r.setdefault("nonce_locations", C.nonce_locations(emit, emit["nonce"], spec["event"], spec["tool"]))
    return r


def _cat(r, entry_type, prefix):
    cats = [l["category"] for l in r["nonce_locations"]
            if l["entry_type"] == entry_type and l["json_path"].startswith(prefix)]
    assert cats, (entry_type, prefix, r["nonce_locations"])
    return set(cats)


def _hac(tr):
    return next(e for e in tr if (e.get("attachment") or {}).get("type") == "hook_additional_context")


def _blob(tr):
    return next(e for e in tr if e.get("type") == "api-request-blob")


# ---------------------------------------------------------------- positive

@pytest.mark.parametrize("path_id", ["H1a-edit", "H1a-bash", "H1b-start"])
def test_r5_positive_is_host_record_and_r1_still_decides(tmp_path, path_id):
    r = _run(tmp_path, path_id)
    assert r["label"] == "DELIVERED_TO_AGENT", r
    assert _cat(r, "attachment", "rendered[") == {"host_record"}
    assert _cat(r, "api-request-blob", "message.content[") == {"host_record"}
    assert _cat(r, "attachment", "attachment.content") == {"model_bound"}  # R1, unchanged
    assert "unclassified" not in {l["category"] for l in r["nonce_locations"]}
    assert r["rules"] == C.RULES_ID == "as-run table + R1-R5 (#551, #561, #796)"


def test_without_r5_the_same_shape_is_inconclusive(tmp_path, monkeypatch):
    # The as-run (R1-R4) behaviour: R5 off -> both new locations unclassified.
    monkeypatch.setattr(C, "_r5a_rendered", lambda *a: False)
    monkeypatch.setattr(C, "_r5b_blob", lambda *a: False)
    r = _run(tmp_path, "H1a-edit")
    assert r["label"] == "INCONCLUSIVE", r


# ---------------------------------------------------------------- R5a negatives

# A failed R5 condition never yields a pass. The label is INCONCLUSIVE (unclassified-first),
# or NOT_EXECUTED when the existing precondition finds the emitter not invoked for the
# path's event and tool (classify(), unchanged by R5).
NOT_PASS = {"INCONCLUSIVE", "NOT_EXECUTED"}


def _r5a_negative(tmp_path, mutate, path_id="H1a-edit", label="INCONCLUSIVE"):
    r = _run(tmp_path, path_id, mutate)
    assert _cat(r, "attachment", "rendered[") == {"unclassified"}, r["nonce_locations"]
    assert r["label"] == label, r
    return r


def test_r5a_rendered_role_other_than_system(tmp_path):
    _r5a_negative(tmp_path, lambda tr, hl, n: _hac(tr).update(renderedRole="user"))


@pytest.mark.parametrize("edit", [lambda s: s + " ", lambda s: s.replace("<system-reminder>\n", "<system-reminder>"),
                                  lambda s: s.replace(" hook additional context: ", " hook context: ")])
def test_r5a_rendered_not_exact(tmp_path, edit):
    def m(tr, hl, n):
        e = _hac(tr)
        e["rendered"][0]["content"] = edit(e["rendered"][0]["content"])
    _r5a_negative(tmp_path, m)


def test_r5a_rendered_length_mismatch(tmp_path):
    _r5a_negative(tmp_path, lambda tr, hl, n: _hac(tr)["rendered"].append({"content": "extra"}))


def test_r5a_rendered_on_entry_with_wrong_hook_event(tmp_path):
    _r5a_negative(tmp_path, lambda tr, hl, n: _hac(tr)["attachment"].update(hookEvent="PostToolUse"))


def test_r5a_rendered_when_emitter_not_invoked(tmp_path):
    def m(tr, hl, n):
        for h in hl:
            h["emitted"] = ""
    _r5a_negative(tmp_path, m, label="NOT_EXECUTED")


@pytest.mark.parametrize("kind,expected,label", [
    ("hook_system_message", "unclassified", "INCONCLUSIVE"),
    ("environment", "unclassified", "INCONCLUSIVE"),
    # R2 (unchanged) categorises every location of a hook_success entry as host_output;
    # R5 does not apply to it, and it is never host_record.
    ("hook_success", "host_output", "DELIVERED_TO_AGENT"),
])
def test_r5a_rendered_on_other_attachment_types(tmp_path, kind, expected, label):
    def m(tr, hl, n):
        text = f"<system-reminder>\nPreToolUse:Edit hook additional context: {n}\n</system-reminder>"
        tr.append({"type": "attachment", "attachment": {"type": kind, "hookEvent": "PreToolUse"},
                   "rendered": [{"content": text}], "renderedRole": "system"})
    r = _run(tmp_path, "H1a-edit", m)
    added = [l for l in r["nonce_locations"]
             if l["json_path"].startswith("rendered[") and l["line"] == max(x["line"] for x in r["nonce_locations"])]
    assert [l["category"] for l in added] == [expected], r["nonce_locations"]
    assert r["label"] == label, r


# ---------------------------------------------------------------- R5b negatives

def _r5b_negative(tmp_path, mutate, path_id="H1a-edit", label="INCONCLUSIVE"):
    r = _run(tmp_path, path_id, mutate)
    assert "unclassified" in _cat(r, "api-request-blob", "message.content["), r["nonce_locations"]
    assert r["label"] == label, r
    return r


def _set_blob_text(fn):
    def m(tr, hl, n):
        b = _blob(tr)
        b["message"]["content"][0]["text"] = fn(b["message"]["content"][0]["text"], n)
    return m


def test_r5b_role_other_than_system(tmp_path):
    _r5b_negative(tmp_path, lambda tr, hl, n: _blob(tr)["message"].update(role="user"))


@pytest.mark.parametrize("fn", [
    lambda t, n: "x" + t,                                                   # prefix
    lambda t, n: t + " x",                                                  # suffix
    lambda t, n: t.replace("PreToolUse:Edit", "PreToolUse"),                # wrong label
    lambda t, n: f"PreToolUse:Edit hook additional context: {n} other text",  # matches no anchor
    lambda t, n: t + f"\nsomething else {n}",                               # second, non-matching line
])
def test_r5b_text_not_exact(tmp_path, fn):
    _r5b_negative(tmp_path, _set_blob_text(fn))


def test_r5b_without_an_anchor(tmp_path):
    def m(tr, hl, n):
        tr.remove(_hac(tr))
    _r5b_negative(tmp_path, m)


def test_r5b_when_emitter_not_invoked(tmp_path):
    def m(tr, hl, n):
        for h in hl:
            h["emitted"] = ""
    _r5b_negative(tmp_path, m, label="NOT_EXECUTED")


# ---------------------------------------------------------------- wrong tool under the right event (#796 review)

def _wrong_tool(tmp_path, mutate, path_id="H1a-edit", label="INCONCLUSIVE"):
    r = _run(tmp_path, path_id, mutate)
    assert _cat(r, "attachment", "rendered[") == {"unclassified"}, r["nonce_locations"]
    assert "unclassified" in _cat(r, "api-request-blob", "message.content[")
    assert r["label"] == label and r["label"] in NOT_PASS, r
    return r


def test_wrong_tool_hookname_on_edit_path(tmp_path):
    # Still R1-qualifying (event, emitter, content), so R1 alone is not what R5 uses.
    r = _wrong_tool(tmp_path, lambda tr, hl, n: _hac(tr)["attachment"].update(hookName="PreToolUse:Bash"))
    assert _cat(r, "attachment", "attachment.content") == {"model_bound"}


def test_wrong_tool_tooluseid_points_at_read_call(tmp_path):
    def m(tr, hl, n):
        tr.insert(0, {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "toolu_read_1", "name": "Read", "input": {"file_path": "notes.txt"}}]}})
        _hac(tr)["attachment"]["toolUseID"] = "toolu_read_1"
    _wrong_tool(tmp_path, m)


def test_wrong_tool_tooluseid_matches_nothing(tmp_path):
    _wrong_tool(tmp_path, lambda tr, hl, n: _hac(tr)["attachment"].update(toolUseID="toolu_nowhere"))


def test_wrong_tool_hook_log_tool_name(tmp_path):
    # The existing precondition already finds no Edit invocation -> NOT_EXECUTED; R5's
    # own A6 independently refuses both records.
    def m(tr, hl, n):
        for h in hl:
            (h.get("envelope") or {})["tool_name"] = "Bash"
    _wrong_tool(tmp_path, m, label="NOT_EXECUTED")


def test_wrong_tool_blob_label_in_edit_arm(tmp_path):
    def m(tr, hl, n):
        b = _blob(tr)
        b["message"]["content"][0]["text"] = b["message"]["content"][0]["text"].replace(
            "PreToolUse:Edit", "PreToolUse:Bash")
    r = _run(tmp_path, "H1a-edit", m)
    assert _cat(r, "api-request-blob", "message.content[") == {"unclassified"}
    assert _cat(r, "attachment", "rendered[") == {"host_record"}  # the anchor itself is fine
    assert r["label"] == "INCONCLUSIVE", r


def test_lifecycle_anchor_hookname_must_be_bare_event(tmp_path):
    _wrong_tool(tmp_path, lambda tr, hl, n: _hac(tr)["attachment"].update(hookName="SessionStart:startup"),
                path_id="H1b-start")


# ---------------------------------------------------------------- labels

def test_r5_with_a_co_present_unrecognised_location_is_inconclusive(tmp_path):
    def m(tr, hl, n):
        tr.append({"type": "attachment", "attachment": {"type": "hook_notice_unrecognised", "content": n}})
    r = _run(tmp_path, "H1a-edit", m)
    assert _cat(r, "attachment", "rendered[") == {"host_record"}
    assert r["label"] == "INCONCLUSIVE", r


@pytest.mark.parametrize("path_id", ["H1a-edit", "H1a-bash", "H1b-start"])
def test_host_record_always_sits_on_an_r1_anchor(tmp_path, path_id):
    # host_record never stands alone: every R5 location has a model_bound R1 location
    # on its anchor, which is what decides delivery.
    r = _run(tmp_path, path_id)
    hr = [l for l in r["nonce_locations"] if l["category"] == "host_record"]
    mb = [l for l in r["nonce_locations"] if l["category"] == "model_bound"]
    assert hr and mb
    rendered_lines = {l["line"] for l in hr if l["json_path"].startswith("rendered[")}
    assert rendered_lines <= {l["line"] for l in mb}


def test_unit_anchor_conditions():
    nonce = "MNEME-PROBE-0123456789abcdef"
    arm = {"hooks": [{"emitted": nonce, "envelope": {"hook_event_name": "PreToolUse", "tool_name": "Edit"}}],
           "transcript": [
               (0, {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Edit"}]}}),
               (1, {"type": "attachment", "attachment": {"type": "hook_additional_context", "hookEvent": "PreToolUse",
                                                         "hookName": "PreToolUse:Edit", "toolUseID": "t1",
                                                         "content": [nonce + " x"]}})]}
    assert C.r5_anchors(arm, nonce, "PreToolUse", "Edit") == {1: [nonce + " x"]}
    assert C.r5_anchors(arm, nonce, "PreToolUse", "Bash") == {}       # A6 (and A4, A5)
    assert C.r5_anchors(arm, nonce, "SessionStart", None) == {}       # A1, A2
    assert C.r5_wrap("SessionStart", "c") == "<system-reminder>\nSessionStart hook additional context: c\n</system-reminder>"


# ---------------------------------------------------------------- no effect on accepted evidence

@pytest.mark.parametrize("path_id", ["H1a-edit", "H1a-bash", "H1b-start", "H1c-stop"])
def test_h1_published_subset_replay_unchanged(path_id):
    R = _load("reclassify_h1")
    pub = ARTIFACTS / "live-2026-10-17"
    r = C.classify(R.subset_arm(pub, path_id), R.subset_arm(pub, f"{path_id}-ctl"), path_id, PIN)
    expected = json.loads((pub / path_id / "outcome.r1r3.json").read_text(encoding="utf-8"))["label"]
    assert r["label"] == expected, r
    assert "host_record" not in {l["category"] for l in r["nonce_locations"]}


def test_a1_published_subset_replay_unchanged():
    RA = _load("reclassify_a1")
    R = _load("reclassify_h1")
    pub = ARTIFACTS / "live-a1-headless-2026-10-19"
    sub = RA.headless_on({a: R.subset_arm(pub, a) for a in RA.ARMS})
    expected = json.loads((pub / "outcome_a1_headless.r1r4.json").read_text(encoding="utf-8"))["label"]
    assert sub["label"] == expected == "NOT_DELIVERED", sub
