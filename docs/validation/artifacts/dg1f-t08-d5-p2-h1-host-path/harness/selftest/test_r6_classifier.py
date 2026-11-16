"""Rule R6 (#805): the Stop systemMessage stream echo left out of the subtype comparison.

R6 leaves exactly one stream event out of host_events()' subtype comparison when all of
S1-S6 hold, and the indicator scan still covers every event. These are the section 7
regression tests of the accepted rule note
(docs/plans/2026-11-16-dg1f-t08-d5-p2-a3-r6-stop-informational-rule.md). Synthetic arms
only, plus a no-effect replay of published H1, A1 and A2 subsets. The A3 archive is NOT
read here: its offline reclassification is a separate step.
"""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parent.parent
ART = HARNESS.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HARNESS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C = _load("classify_h1")
RH = _load("reclassify_h1")

S = "MNEME-PROBE-0123456789abcdef This is a Mneme H1 channel-probe notice."
STOP = {"event": "Stop"}


def _echo(**over):
    e = {"type": "system", "subtype": "informational", "content": "Stop says: " + S,
         "level": "notice", "session_id": "s", "uuid": "u"}
    e.update(over)
    return e


def _arm(events=None, hooks=None):
    """The A3 headless emitter shape: init, assistant (thinking), assistant (text), echo, result."""
    if events is None:
        events = [{"type": "system", "subtype": "init"}, {"type": "assistant"}, {"type": "assistant"},
                  _echo(), {"type": "result", "subtype": "success"}]
    if hooks is None:
        hooks = [{"envelope": {"hook_event_name": "Stop", "stop_hook_active": False},
                  "emitted": json.dumps({"systemMessage": S})}]
    return {"events": list(enumerate(events)), "hooks": hooks, "out": Path("x") / "arm" / "out"}


def _subs(arm, emitter=True, spec=STOP):
    subs, ind, r6 = C.host_events(arm, "MNEME-PROBE-0123456789abcdef", spec, emitter)
    return subs, ind, r6


# ---------------------------------------------------------------- positive

def test_a3_shape_is_excluded_from_the_subtype_comparison():
    assert C.RULES_ID == "as-run table + R1-R6 (#551, #561, #796, #805)"
    subs, ind, r6 = _subs(_arm())
    assert r6 == 3 and subs == [] and ind == {}


# ---------------------------------------------------------------- S1 shape and exact field set

@pytest.mark.parametrize("over", [{"level": "info"}, {"level": None}, {"subtype": "notice"}])
def test_s1_level_or_subtype_mismatch_is_compared(over):
    arm = _arm()
    arm["events"][3] = (3, _echo(**over))
    subs, _, r6 = _subs(arm)
    assert r6 is None and len(subs) == 1


def test_s1_extra_field_is_compared():  # review of #805
    arm = _arm()
    arm["events"][3] = (3, _echo(source="hook"))
    subs, _, r6 = _subs(arm)
    assert r6 is None and subs == ["informational"]


@pytest.mark.parametrize("field", ["session_id", "uuid", "level", "content"])
def test_s1_missing_field_is_compared(field):  # review of #805
    e = _echo()
    del e[field]
    arm = _arm()
    arm["events"][3] = (3, e)
    subs, _, r6 = _subs(arm)
    assert r6 is None and subs == ["informational"]


# ---------------------------------------------------------------- S2 path and arm

def test_s2_control_arm_is_compared():
    subs, _, r6 = _subs(_arm(), emitter=False)
    assert r6 is None and subs == ["informational"]


@pytest.mark.parametrize("event", ["PreToolUse", "SessionStart", None])
def test_s2_other_paths_are_compared(event):
    subs, _, r6 = _subs(_arm(), spec={"event": event})
    assert r6 is None and subs == ["informational"]


# ---------------------------------------------------------------- S3 emitter attribution

def _hook(active=False, emitted=None):
    return {"envelope": {"hook_event_name": "Stop", "stop_hook_active": active},
            "emitted": json.dumps({"systemMessage": S}) if emitted is None else emitted}


@pytest.mark.parametrize("hooks", [
    [],                                              # no Stop record
    [_hook(), _hook()],                              # two Stop records (re-entry)
    [_hook(active=True)],                            # stop_hook_active true
    [_hook(emitted="not json")],
    [_hook(emitted=json.dumps([S]))],                # not an object
    [_hook(emitted=json.dumps({"other": S}))],       # no systemMessage
    [_hook(emitted=json.dumps({"systemMessage": 7}))],  # not a string
    [{"envelope": {"hook_event_name": "Stop"}, "emitted": json.dumps({"systemMessage": S})}],  # flag absent
], ids=["none", "two", "active", "not-json", "list", "no-key", "non-string", "flag-absent"])
def test_s3_attribution_failures_are_compared(hooks):
    subs, _, r6 = _subs(_arm(hooks=hooks))
    assert r6 is None and subs == ["informational"]


# ---------------------------------------------------------------- S4 exact derivation

@pytest.mark.parametrize("content", [
    "Stop says: " + S + " ", "Stop says: " + S[:-1], "Stop said: " + S, "SessionStart says: " + S,
    "Stop says: " + S.replace("0123456789abcdef", "fedcba9876543210"), S, "stop says: " + S])
def test_s4_inexact_content_is_compared(content):
    arm = _arm()
    arm["events"][3] = (3, _echo(content=content))
    subs, _, r6 = _subs(arm)
    assert r6 is None and subs == ["informational"]


# ---------------------------------------------------------------- S5 uniqueness

def test_s5_two_qualifying_events_are_both_compared():
    ev = [{"type": "system", "subtype": "init"}, {"type": "assistant"}, _echo(), _echo(),
          {"type": "result", "subtype": "success"}]
    subs, _, r6 = _subs(_arm(events=ev))
    assert r6 is None and subs == ["informational", "informational"]


# ---------------------------------------------------------------- S6 position

@pytest.mark.parametrize("events", [
    [{"type": "system", "subtype": "init"}, _echo(), {"type": "assistant"}, {"type": "result"}],   # before reply
    [{"type": "system", "subtype": "init"}, {"type": "assistant"}, {"type": "result"}, _echo()],   # after result
    [{"type": "system", "subtype": "init"}, _echo(), {"type": "result"}],                          # no assistant
    [{"type": "system", "subtype": "init"}, {"type": "assistant"}, _echo()],                       # no result
], ids=["before-assistant", "after-result", "no-assistant", "no-result"])
def test_s6_position_failures_are_compared(events):
    subs, _, r6 = _subs(_arm(events=events))
    assert r6 is None and subs == ["informational"]


# ---------------------------------------------------------------- safeguard

def test_indicator_on_the_echo_is_still_scanned_and_compared():
    # An echo carrying an indicator field fails S1 (field set) and stays compared; its
    # indicator is recorded, so a one-sided indicator keeps the strict comparison.
    arm = _arm()
    arm["events"][3] = (3, _echo(**{"continue": True}))
    subs, ind, r6 = _subs(arm)
    assert r6 is None and subs == ["informational"] and ("informational", "continue") in ind


def test_excluded_echo_is_still_scanned_for_indicators(monkeypatch):
    # With S1's exact field set an excluded echo can never carry a real indicator key, so
    # the scan of it is unobservable in production. To pin that the scan still RUNS over
    # the excluded event (R6-3), treat one of its six fields as an indicator key here.
    monkeypatch.setattr(C, "INDICATOR_KEYS", tuple(C.INDICATOR_KEYS) + ("level",))
    subs, ind, r6 = _subs(_arm())
    assert r6 == 3 and subs == [] and ("informational", "level") in ind


# ---------------------------------------------------------------- no effect on earlier evidence

REPLAYS = [
    # (published dir, path_id, model pin, version pin, expected label as last published)
    ("live-a2-2026-11-11", "H1a-edit", "claude-opus-5-5", "2.1.310 (Claude Code)", "DELIVERED_TO_AGENT"),
    ("live-a2-2026-11-11", "H1a-bash", "claude-opus-5-5", "2.1.310 (Claude Code)", "DELIVERED_TO_AGENT"),
    ("live-a2-2026-11-11", "H1b-start", "claude-opus-5-5", "2.1.310 (Claude Code)", "DELIVERED_TO_AGENT"),
    ("live-2026-10-17", "H1c-stop", "claude-opus-4-8[1m]", None, "DELIVERED_WITH_SIDE_EFFECT"),
]


@pytest.mark.parametrize("pub,path_id,model,version,label", REPLAYS, ids=[f"{r[0]}:{r[1]}" for r in REPLAYS])
def test_published_subsets_keep_their_labels_and_r6_never_fires(pub, path_id, model, version, label):
    emit, ctl = RH.subset_arm(ART / pub, path_id), RH.subset_arm(ART / pub, f"{path_id}-ctl")
    spec = C.PATHS[path_id]
    for arm, is_emit in ((emit, True), (ctl, False)):
        assert C.r6_stop_echo(arm, spec, is_emit) is None
    r = C.classify(emit, ctl, path_id, model, version)
    assert r["label"] == label, r.get("reasons")
    assert "r6_excluded" in r["host_events"] and r["host_events"]["r6_excluded"] is None


def test_published_a1_headless_subset_keeps_not_delivered_and_r6_never_fires():
    # Review of #806: the A1 headless run (2026-10-19, Claude Code 2.1.202) is a Stop path
    # too, so R6's S2 path condition holds there; it must still never fire, and the
    # accepted R1-R4 label NOT_DELIVERED must not change.
    A1 = _load("classify_a1")  # registers the H1c-sm path in its own classifier instance
    pub = ART / "live-a1-headless-2026-10-19"
    emit, ctl = RH.subset_arm(pub, "H1c-sm"), RH.subset_arm(pub, "H1c-sm-ctl")
    spec = A1.C.PATHS["H1c-sm"]
    assert spec["event"] == "Stop"
    for arm, is_emit in ((emit, True), (ctl, False)):
        assert A1.C.r6_stop_echo(arm, spec, is_emit) is None
    r = A1.C.classify(emit, ctl, "H1c-sm", "claude-opus-4-8[1m]")
    assert r["label"] == "NOT_DELIVERED", r.get("reasons")
    assert r["host_events"]["r6_excluded"] is None
    assert json.loads((pub / "outcome_a1_headless.r1r4.json").read_text(encoding="utf-8"))["label"] == "NOT_DELIVERED"
