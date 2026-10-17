"""Classify the H1c Amendment A1 runs (Stop top-level systemMessage; probe scope 4.2).

usage:
  classify_a1.py headless    <live> <pin_model>   -> <live>/outcome_a1_headless.json
  classify_a1.py interactive <live>               -> <live>/outcome_a1_interactive.json
  classify_a1.py combine     <live>               -> <live>/outcome_a1.json (the H1c result under A1)

Rules (probe scope 4.2, accepted in #555):
- **Failure** is only demonstrated HOST-INDUCED interference: Stop invocations above
  the control's, `stop_hook_active: true`, a different permission decision for an
  equivalent request, an unexpected prompt, a host block or retry, no normal end
  (headless: a `result` event; interactive: the return to the input prompt), or a
  strict host-event or indicator flag (headless, via classify_h1). Model reply text,
  turn counts and model-chosen activity are evidence only.
- **Developer delivery** comes ONLY from the interactive capture: the operator's
  observation.json (`notice_visible`) for the emitter arm, true, and for the control,
  false, backed by a recording whose SHA-256 is in observer.txt and by listed frames.
- A stream-json informational/system event carrying the nonce is `host_output`:
  recorded, never delivery (classify_h1 table, unchanged).
- A model-bound nonce location (classify_h1 table, including R1) is agent delivery.

Known collision (reported, not decided here): if the host surfaces the systemMessage
as a stream-json `system` event that appears in the emitter arm only, the strict
host-event subtype rule (unchanged) makes the headless run INCONCLUSIVE. Any rule
change for that case needs its own review; raw evidence allows reclassification.
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("classify_h1", HERE / "classify_h1.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)

A1_ID = "A1 (#555) on " + C.RULES_ID
C.PATHS.setdefault("H1c-sm", {"path_type": "command_lifecycle_event", "event": "Stop", "tool": None})
PASSING = ("DELIVERED_TO_AGENT", "DELIVERED_TO_USER_ONLY")


def _observer(out):
    obs = {}
    p = Path(out) / "observer.txt"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                obs.setdefault(k, v)
    return obs


# ---------------------------------------------------------------- headless
def headless(live, pin_model):
    emit = C.load_arm(Path(live) / "H1c-sm" / "out")
    ctl = C.load_arm(Path(live) / "H1c-sm-ctl" / "out")
    r = C.classify(emit, ctl, "H1c-sm", pin_model)
    controls = r.get("controls") or {}
    pe, common = controls.get("path_type_emitter") or {}, controls.get("common") or {}
    interference = []
    if pe and not pe.get("no_stop_reentry", True):
        interference.append("stop_hook_active re-entry")
    if common and common.get("stop_invocations_equal") is False:
        interference.append("Stop invocations differ from the control")
    if common and common.get("permission_decisions_equal_for_equivalent_requests") is False:
        interference.append("permission decision differs for an equivalent request")
    if common and common.get("host_indicators_equal") is False:
        interference.append("host indicator differs")
    if pe and pe.get("result_success") is False:
        interference.append("no normal result event")
    r["a1"] = {"run": "headless", "rules": A1_ID, "host_interference": interference}
    return r


# ---------------------------------------------------------------- interactive
def _int_arm(live, arm):
    out = Path(live) / arm / "out"
    a = {"out": out, "observer": _observer(out),
         "hooks": [r for _, r in C.read_jsonl(out / "hook-log.jsonl")],
         "transcript": C.read_jsonl(out / "transcript.jsonl"),
         "transcript_collected": (out / "transcript.jsonl").exists(),
         "events": [], "nonce": (out / "nonce.txt").read_text(encoding="utf-8").strip() if (out / "nonce.txt").exists() else None}
    p = out / "observation.json"
    a["observation"] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    return a


def _transcript_attempts(arm, nonce):
    """Tool requests and decisions from the interactive session transcript."""
    uses, results = {}, {}
    for _, e in arm["transcript"]:
        for it in C.content_items(e):
            if e.get("type") == "assistant" and it.get("type") == "tool_use":
                uses[it.get("id")] = it
            elif e.get("type") == "user" and it.get("type") == "tool_result":
                results[it.get("tool_use_id")] = it
    by = {}
    for tid, u in uses.items():
        res = results.get(tid)
        dec = "no_result" if res is None else ("error" if res.get("is_error") else "executed")
        by.setdefault((u.get("name"), C.masked(u.get("input"), arm, nonce)), set()).add(dec)
    return {k: sorted(v) for k, v in by.items()}


def interactive(live):
    emit, ctl = _int_arm(live, "H1c-sm-int"), _int_arm(live, "H1c-sm-int-ctl")
    nonce = emit["nonce"]
    rec = {"path_id": "H1c-sm-int", "run": "interactive", "rules": A1_ID, "reasons": []}
    reasons = rec["reasons"]

    def done(label):
        rec["label"] = label
        rec["passes_run"] = label in PASSING
        return rec

    emitted = [h for h in emit["hooks"] if (h.get("envelope") or {}).get("hook_event_name") == "Stop"
               and nonce and nonce in (h.get("emitted") or "")]
    ctl_calls = [h for h in ctl["hooks"] if (h.get("envelope") or {}).get("hook_event_name") == "Stop"]
    emit_calls = [h for h in emit["hooks"] if (h.get("envelope") or {}).get("hook_event_name") == "Stop"]
    rec["stop_invocations"] = {"emitter": len(emit_calls), "control": len(ctl_calls)}
    if not emitted:
        reasons.append("emitter did not emit the systemMessage at Stop")
    if not ctl_calls:
        reasons.append("control no-op not invoked at Stop")
    if reasons:
        return done("NOT_EXECUTED")

    # Capture and observation are mandatory for an interactive verdict.
    for name, a in (("emitter", emit), ("control", ctl)):
        o = a["observation"]
        if not a["observer"].get("recording_sha256") or a["observer"].get("recording_sha256") == "absent":
            reasons.append(f"{name}: no recording hash (capture missing)")
        if o is None or not all(isinstance(o.get(k), bool) for k in
                                ("notice_visible", "returned_to_input_prompt", "unexpected_prompt")):
            reasons.append(f"{name}: observation.json missing or incomplete")
    if not reasons and not emit["observation"].get("frames"):
        reasons.append("emitter: no frames listed for the observed notice area")
    if reasons:
        return done("INCONCLUSIVE")
    oe, oc = emit["observation"], ctl["observation"]
    if oc["notice_visible"]:
        reasons.append("control arm reports a visible notice; attribution impossible")

    locs = C.nonce_locations(emit, nonce, "Stop")
    cats = {l["category"] for l in locs}
    rec["nonce_locations"] = locs
    if "unclassified" in cats:
        reasons.append("nonce found in locations the category table does not recognise; review needed")
    if C.nonce_locations(ctl, nonce, "Stop"):
        reasons.append("emitter nonce found in the control arm (collision)")
    if not oc["returned_to_input_prompt"]:
        reasons.append("control did not return to the input prompt; differences cannot be attributed")
    if reasons:
        return done("INCONCLUSIVE")

    interference = []
    if len(emit_calls) > len(ctl_calls):
        interference.append("more Stop invocations than the control")
    if any((h.get("envelope") or {}).get("stop_hook_active") for h in emit_calls):
        interference.append("stop_hook_active re-entry")
    if oe["unexpected_prompt"] and not oc["unexpected_prompt"]:
        interference.append("a prompt appeared that the control lacks")
    if not oe["returned_to_input_prompt"]:
        interference.append("emitter session did not return to the input prompt")
    ae, ac = _transcript_attempts(emit, nonce), _transcript_attempts(ctl, nonce)
    mism = [list(k) for k in set(ae) & set(ac) if ae[k] != ac[k]]
    if mism:
        interference.append("permission/tool decision differs for an equivalent request")
    rec["host_interference"] = interference
    rec["developer_visible"] = oe["notice_visible"]
    rec["evidence_only"] = {"assistant_entries": {
        "emitter": sum(1 for _, e in emit["transcript"] if e.get("type") == "assistant"),
        "control": sum(1 for _, e in ctl["transcript"] if e.get("type") == "assistant")}}
    if interference:
        return done("DELIVERED_WITH_SIDE_EFFECT")
    if "model_bound" in cats:
        rec["developer_also"] = oe["notice_visible"]
        return done("DELIVERED_TO_AGENT")
    if oe["notice_visible"]:
        return done("DELIVERED_TO_USER_ONLY")
    return done("NOT_DELIVERED")


# ---------------------------------------------------------------- combine
def combine(h, i):
    rec = {"path_id": "H1c", "rules": A1_ID, "headless_label": h.get("label"),
           "interactive_label": i.get("label"), "reasons": []}
    for name, r in (("headless", h), ("interactive", i)):
        if r.get("label") in ("NOT_EXECUTED", "INCONCLUSIVE"):
            rec["reasons"].append(f"{name} run is {r['label']}")
    if rec["reasons"]:
        lab = "NOT_EXECUTED" if any(r.get("label") == "NOT_EXECUTED" for r in (h, i)) else "INCONCLUSIVE"
    elif (h.get("a1") or {}).get("host_interference") or i.get("label") == "DELIVERED_WITH_SIDE_EFFECT":
        lab = "DELIVERED_WITH_SIDE_EFFECT"
    elif h.get("label") == "DELIVERED_TO_AGENT" or i.get("label") == "DELIVERED_TO_AGENT":
        lab = "DELIVERED_TO_AGENT"
    elif i.get("label") == "DELIVERED_TO_USER_ONLY":
        lab = "DELIVERED_TO_USER_ONLY"
    else:
        lab = "NOT_DELIVERED"
    rec["label"] = lab
    rec["h1c_passes_under_a1"] = lab in PASSING
    return rec


def _write(live, name, obj):
    (Path(live) / name).write_text(json.dumps(obj, indent=2), encoding="utf-8")
    print(obj["label"])


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 3 and a[0] == "headless":
        _write(a[1], "outcome_a1_headless.json", headless(a[1], a[2]))
    elif len(a) == 2 and a[0] == "interactive":
        _write(a[1], "outcome_a1_interactive.json", interactive(a[1]))
    elif len(a) == 2 and a[0] == "combine":
        h = json.loads((Path(a[1]) / "outcome_a1_headless.json").read_text(encoding="utf-8"))
        i = json.loads((Path(a[1]) / "outcome_a1_interactive.json").read_text(encoding="utf-8"))
        _write(a[1], "outcome_a1.json", combine(h, i))
    else:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
