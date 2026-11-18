"""Classify H4a arms (probe scope section 6) and summarize shape discovery.

usage:
  h4a_classify.py pair <live_root> <candidate A|B>   -> <arm>/out/outcome.json
  h4a_classify.py path <live_root>                   -> <live_root>/outcome.H4a.json

Path type (section 3.1): command hook, tool event. Controls, host-induced
only: the tool executed (the agent ran it and ``notes.txt`` reads
``beta``), the file matches the control arm, the permission prompt behaved
as in the control, and the host showed no error or block. Common criteria
(section 3 step 4) are judged from the reviewed capture.

Nonce locations in the copied host transcript. **Provisional table**: the
Antigravity transcript format is not documented in this repository, and
shape discovery is what reveals it. Extending the table is a reviewed change.

  JSON entry whose role/type is user, tool, function or tool_result -> model_bound
  JSON entry whose role/type is assistant or model                 -> echo
  anything else, including a non-JSON transcript                   -> unclassified

Any unclassified location makes the arm INCONCLUSIVE, even with a
model_bound location, and the raw evidence allows re-classification
without a re-run. Developer delivery comes only from the reviewed capture.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import check_pins  # noqa: E402

MODEL_BOUND_ROLES = {"user", "tool", "function", "tool_result"}
ECHO_ROLES = {"assistant", "model"}
REVIEW_BOOLS = ("agent_ran_tool", "permission_prompt_shown",
                "host_error_or_block_shown", "nonce_seen_in_ui")


def _role(entry):
    for k in ("role", "type", "source", "author"):
        v = entry.get(k)
        if isinstance(v, str):
            return v.lower()
    return None


def transcript_locations(out: Path, nonce: str) -> list:
    locs = []
    for t in sorted(out.glob("transcript.*")):
        text = t.read_text(encoding="utf-8", errors="replace")
        if nonce not in text:
            continue
        entries = None
        try:
            entries = [json.loads(line) for line in text.splitlines() if line.strip()]
        except json.JSONDecodeError:
            try:
                whole = json.loads(text)
                entries = whole if isinstance(whole, list) else [whole]
            except json.JSONDecodeError:
                entries = None
        if entries is None:
            locs.append({"file": t.name, "category": "unclassified", "why": "non-JSON transcript"})
            continue
        for i, e in enumerate(entries):
            if not isinstance(e, dict):
                continue
            for jp, s in common.walk_strings(e):
                if nonce in s:
                    role = _role(e)
                    cat = ("model_bound" if role in MODEL_BOUND_ROLES else
                           "echo" if role in ECHO_ROLES else "unclassified")
                    locs.append({"file": t.name, "entry": i, "json_path": jp,
                                 "role": role, "category": cat})
    return locs


def _arm(root: Path, arm: str):
    out = root / arm / "out"
    return out, common.read_json(out / "probe.json"), common.read_json(out / "arm.json"), \
        common.read_json(out / "capture_review.json"), common.read_jsonl(out / "hook-log.jsonl")


def _review_problems(review, arm_meta, pin) -> list:
    if review is None:
        return ["capture_review.json missing"]
    p = []
    if not str(review.get("reviewer", "")).strip():
        p.append("capture review has no named reviewer")
    for k in REVIEW_BOOLS:
        if not isinstance(review.get(k), bool):
            p.append(f"capture review field {k} is not true/false")
    if not arm_meta or not arm_meta.get("recording_sha256"):
        p.append("no screen recording bound to the arm")
    elif review.get("recording_sha256") != arm_meta.get("recording_sha256"):
        p.append("capture review is not bound to this arm's recording")
    shown = check_pins.normalize(str(review.get("host_version_shown", "")))
    if shown != pin:
        p.append(f"host version {shown or 'unrecorded'} differs from pin {pin}")
    return p


def _controls(review, arm_meta) -> dict:
    return {
        "tool_executed": bool(review.get("agent_ran_tool")) and arm_meta.get("notes_after") == "beta\n",
        "no_host_error_or_block": review.get("host_error_or_block_shown") is False,
    }


def classify_pair(root: Path, cand: str, pin: str = None) -> dict:
    pin = pin or check_pins.pins()["ANTIGRAVITY_VERSION"]
    arm, ctl = f"h4a-{cand}", f"h4a-{cand}-ctl"
    out, probe, meta, review, hooks = _arm(root, arm)
    cout, cprobe, cmeta, creview, chooks = _arm(root, ctl)
    res = {"path": "H4a", "candidate": cand, "arm": arm, "control_arm": ctl,
           "path_type": "command hook, tool event", "rules": common.RULES,
           "developer_also": "not_observed", "accepted_without_side_effect": False}
    reasons = []
    if probe is None or cprobe is None or probe.get("control") or not cprobe.get("control"):
        reasons.append("arm or control not prepared as a pair")
    if probe and cprobe and (probe.get("selftest") != cprobe.get("selftest")):
        reasons.append("emitter and control arms disagree on selftest")
    if probe and not probe.get("selftest"):
        reasons += [f"{arm}: {x}" for x in _review_problems(review, meta, pin)]
        reasons += [f"{ctl}: {x}" for x in _review_problems(creview, cmeta, pin)]
    elif review is None or creview is None:
        reasons.append("capture_review.json missing")
    if probe and not any(h.get("mode") == probe.get("mode") for h in hooks):
        reasons.append("emitter never invoked for PreToolUse")
    if not any(h.get("mode") == "noop" for h in chooks):
        reasons.append("control no-op never invoked")
    if meta is None or cmeta is None:
        reasons.append("arm not finished")
    if reasons:
        res.update(label=common.NOT_EXECUTED, reasons=reasons)
        return res
    nonce = (out / "nonce.txt").read_text(encoding="utf-8").strip()
    res["nonce"] = nonce
    leaked = common.tree_text_contains(root / ctl, nonce)
    ctl_controls = _controls(creview, cmeta)
    controls = _controls(review, meta)
    controls["file_matches_control"] = meta.get("notes_after") == cmeta.get("notes_after")
    controls["permission_prompt_as_control"] = (
        review.get("permission_prompt_shown") == creview.get("permission_prompt_shown"))
    locs = transcript_locations(out, nonce)
    agent = any(l["category"] == "model_bound" for l in locs)
    echo = any(l["category"] == "echo" for l in locs)
    dev = review.get("nonce_seen_in_ui") is True
    ok = all(controls.values())
    res.update(locations=locs, controls=controls, control_arm_controls=ctl_controls,
               accepted_without_side_effect=ok, developer_also=dev if agent else "not_observed")
    inconclusive = []
    if leaked:
        inconclusive.append(f"nonce found in the control arm: {leaked}")
    if not all(ctl_controls.values()):
        inconclusive.append("control arm failed its own path-type control")
    if any(l["category"] == "unclassified" for l in locs):
        inconclusive.append("unclassified nonce location")
    if echo and not (agent or dev):
        inconclusive.append("echo without recorded delivery")
    if not agent and not dev and meta.get("transcript_copied") is None:
        inconclusive.append("no delivery seen and no transcript collected")
    if inconclusive:
        res.update(label=common.INCONCLUSIVE, reasons=inconclusive)
        return res
    if agent or dev:
        label = (common.DELIVERED_WITH_SIDE_EFFECT if not ok else
                 common.DELIVERED_TO_AGENT if agent else common.DELIVERED_TO_USER_ONLY)
    else:
        label = common.NOT_DELIVERED
    res["label"] = label
    return res


def main(argv) -> int:
    if len(argv) == 4 and argv[1] == "pair" and argv[3] in ("A", "B"):
        root = Path(argv[2]).resolve()
        res = classify_pair(root, argv[3])
        common.write_json(root / f"h4a-{argv[3]}" / "out" / "outcome.json", res)
        print(f"H4a candidate {argv[3]}: {res['label']}")
        return 0
    if len(argv) == 3 and argv[1] == "path":
        root = Path(argv[2]).resolve()
        cands = []
        for c in ("A", "B"):
            o = common.read_json(root / f"h4a-{c}" / "out" / "outcome.json")
            cands.append(o or {"candidate": c, "label": common.NOT_EXECUTED,
                               "reasons": ["candidate not classified"]})
        res = common.summarize_path("H4a", cands)
        common.write_json(root / "outcome.H4a.json", res)
        print(f"H4a: {res['label']} (bound shape: {res['bound_shape']})")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
