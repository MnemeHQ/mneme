"""Classify H6 arms. H6a and H6b are classified and recorded separately.

usage:
  h6_classify.py pair <live_root> <h6b|h6a-N|h6a-T> [--accept-observer-record]
      -> <arm>/out/outcome.json
  h6_classify.py path <live_root> <H6a|H6b> [--accept-candidate-T]
      -> <live_root>/outcome.H6a.json or outcome.H6b.json

Path type (probe scope section 3.1): in-process callback. The control is
"the host's normal flow continues":
- H6a (tool-call notice): the probed tool (``write_file``/``patch``)
  dispatched with no error;
- H6b (context injection): every planned turn completed (exit 0);
- H6a candidate T also: the model-bound tool result equals the callback's
  return, which equals the untransformed result plus the annotation (the
  middleware rule, since T rewrites a tool result).

**Attribution (section 3 step 4, section 6).** A control failure counts as
host-induced (DELIVERED_WITH_SIDE_EFFECT) only when the control arm made the
identical tool call (same argument hash) and it dispatched cleanly, or when
the host demonstrably altered the annotated result. A failure that cannot be
attributed to the emitter (a failed turn, a different model-chosen call, an
unavailable record) is INCONCLUSIVE, never a failing label.

Nonce locations (as-built table; extending it is a reviewed change). Only
this arm's own nonce counts (the observer records a hash of each match):

  session record row, role user or tool         -> model_bound (host's own record)
  session record row, role assistant            -> echo
  session record row, any other role or none    -> unclassified
  turn stdout (the final response)              -> echo
  turn stderr                                   -> unclassified
  pre_api_request observer, role user/tool/system -> observer
  pre_api_request observer, role assistant      -> echo
  pre_api_request observer, another arm's nonce -> unclassified

**The host's own record covers H6b and N.** On 0.19.0 the injected context is
persisted as the user row's ``api_content`` (README D3, refuted), so a nonce
there is ``model_bound``. Observer evidence is supplementary and never counted
by default; ``--accept-observer-record`` remains only for an owner decision if
the host record is ever missing. NOT_DELIVERED additionally requires that
every request the observer saw carried a non-empty raw ``request_messages``
list; otherwise the absence of the nonce is not evidence, and the arm is
INCONCLUSIVE.

**Candidate T is pending owner decision D4** and is never bound unless
``--accept-candidate-T`` is given; while pending, H6a cannot fail.
"""
import argparse
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import check_pins  # noqa: E402

PROBED_TOOLS = ("write_file", "patch")
EMIT_HOOK = {"h6b-context": "pre_llm_call", "h6a-transform": "transform_tool_result",
             "h6a-next-turn": "pre_llm_call"}
PAIRS = {"h6b": "h6b-ctl", "h6a-N": "h6a-N-ctl", "h6a-T": "h6a-T-ctl"}


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _load(root: Path, arm: str):
    out = root / arm / "out"
    return (out, common.read_json(out / "probe.json"), common.read_json(out / "arm.json"),
            common.read_jsonl(out / "hook-log.jsonl"))


def _dispatches(hooks):
    return [h for h in hooks if h.get("hook") == "post_tool_call"
            and h.get("tool_name") in PROBED_TOOLS]


def _turns_completed(meta) -> bool:
    codes = meta.get("turn_exit_codes") or []
    return len(codes) == meta.get("turns_planned", len(codes)) and bool(codes) \
        and all(c == 0 for c in codes)


def _tool_ok(hooks) -> bool:
    d = _dispatches(hooks)
    return bool(d) and not any(h.get("error_type") for h in d)


def _observer_complete(hooks) -> bool:
    reqs = [h for h in hooks if h.get("hook") == "pre_api_request"]
    return bool(reqs) and all(h.get("messages_complete") is True for h in reqs)


def _session_rows(out: Path):
    return [r for r in common.read_jsonl(out / "session.jsonl") if isinstance(r, dict)]


def locations(out: Path, nonce: str, hooks) -> list:
    locs, nsha = [], _sha(nonce)
    for i, row in enumerate(_session_rows(out)):
        for jp, s in common.walk_strings(row):
            if nonce in s:
                role = str(row.get("role") or "").lower() or None
                cat = ("model_bound" if role in ("user", "tool") else
                       "echo" if role == "assistant" else "unclassified")
                locs.append({"source": "session", "row": i, "table": row.get("_table"),
                             "json_path": jp, "role": role, "category": cat})
    for t in sorted(out.glob("turn*.std*")):
        if nonce in t.read_text(encoding="utf-8", errors="replace"):
            cat = "echo" if t.suffix == ".stdout" else "unclassified"
            locs.append({"source": t.name, "category": cat})
    for h in hooks:
        if h.get("hook") == "pre_api_request":
            for l in h.get("nonce_locations") or []:
                role = str(l.get("role") or "").lower() or None
                if l.get("nonce_sha256") != nsha:
                    cat = "unclassified"
                else:
                    cat = "echo" if role == "assistant" else "observer"
                locs.append({"source": "pre_api_request", "json_path": l.get("json_path"),
                             "role": role, "content_sha256": l.get("content_sha256"),
                             "category": cat})
    return locs


def _transform_preserved(out: Path, hooks, nonce: str, locs):
    """True / False / None (cannot tell)."""
    for h in hooks:
        ret = h.get("returned")
        if h.get("hook") == "transform_tool_result" and isinstance(ret, str):
            suffix = "\n\n" + common.notice(nonce, "H6a")
            if not ret.endswith(suffix) or _sha(ret[: -len(suffix)]) != h.get("result_sha256"):
                return False
            tool_obs = [l for l in locs if l["source"] == "pre_api_request"
                        and l["role"] == "tool" and l["category"] == "observer"]
            if tool_obs:
                return all(l.get("content_sha256") == _sha(ret) for l in tool_obs)
            rows = [r for r in _session_rows(out) if str(r.get("role")).lower() == "tool"
                    and isinstance(r.get("content"), str) and nonce in r["content"]]
            if rows:
                return all(r["content"] == ret for r in rows)
            # The annotation reached no model-bound message. With a complete
            # request record that is non-delivery, with nothing altered to
            # judge; without one, it cannot be told apart from an alteration.
            return True if _observer_complete(hooks) else None
    return None


def classify_pair(root: Path, arm: str, accept_observer: bool = False, pin: str = None) -> dict:
    pin = pin or check_pins.pins()["HERMES_AGENT_VERSION"]
    ctl = PAIRS[arm]
    out, probe, meta, hooks = _load(root, arm)
    cout, cprobe, cmeta, chooks = _load(root, ctl)
    res = {"arm": arm, "control_arm": ctl, "path_type": "in-process callback",
           "rules": common.RULES, "developer_also": "not_observed",
           "observer_record_counted": accept_observer, "accepted_without_side_effect": False}
    if probe:
        res.update(path=probe.get("path"), candidate=probe.get("candidate"))
    reasons = []
    if probe is None or cprobe is None or probe.get("control") or not cprobe.get("control"):
        reasons.append("arm or control not prepared as a pair")
    elif probe.get("path") != cprobe.get("path") or probe.get("candidate") != cprobe.get("candidate"):
        reasons.append("emitter and control arms are for different paths or candidates")
    if meta is None or cmeta is None:
        reasons.append("arm or control not run")
    if probe and meta and not probe.get("selftest"):
        for m, name in ((meta, arm), (cmeta, ctl)):
            if m and m.get("host_version") != pin:
                reasons.append(f"{name}: hermes-agent {m.get('host_version')} differs from pin {pin}")
    for m, name in ((meta, arm), (cmeta, ctl)):
        if m and m.get("notes"):
            reasons += [f"{name}: {n}" for n in m["notes"]]
    if probe and not any(h.get("hook") == EMIT_HOOK.get(probe.get("mode"))
                         and h.get("returned") is not None for h in hooks):
        reasons.append("the emitter callback never emitted (precondition: the probed tool "
                       "was not called, or the second turn was not in the same session)")
    if not chooks:
        reasons.append("the control plugin was never invoked")
    if reasons:
        res.update(label=common.NOT_EXECUTED, reasons=reasons)
        return res
    nonce = (out / "nonce.txt").read_text(encoding="utf-8").strip()
    res["nonce"] = nonce
    is_h6a = probe.get("path") == "H6a"
    locs = locations(out, nonce, hooks)
    controls = {"turns_completed": _turns_completed(meta)}
    ctl_controls = {"turns_completed": _turns_completed(cmeta)}
    if is_h6a:
        controls["tool_dispatched"] = _tool_ok(hooks)
        ctl_controls["tool_dispatched"] = _tool_ok(chooks)
    if probe["mode"] == "h6a-transform":
        controls["tool_result_otherwise_unchanged"] = _transform_preserved(out, hooks, nonce, locs)
    inconclusive, side_effects = [], []
    if not controls["turns_completed"]:
        inconclusive.append("a planned turn failed or did not run; not attributable to the emitter")
    if is_h6a and not controls["tool_dispatched"]:
        same = {h.get("args_sha256") for h in _dispatches(hooks)} & {
            h.get("args_sha256") for h in _dispatches(chooks) if not h.get("error_type")}
        if same:
            side_effects.append("the identical tool call dispatched in the control but not here")
        else:
            inconclusive.append("tool dispatch differs from the control on a different, "
                                "model-chosen call; not attributable")
    t = controls.get("tool_result_otherwise_unchanged", True)
    if t is False:
        side_effects.append("the host altered the annotated tool result")
    elif t is None:
        inconclusive.append("the model-bound tool result could not be compared")
    model_bound = any(l["category"] == "model_bound" for l in locs)
    observer = any(l["category"] == "observer" for l in locs)
    delivered = model_bound or (accept_observer and observer)
    echo = any(l["category"] == "echo" for l in locs)
    accepted = not side_effects and not inconclusive
    res.update(locations=locs, controls=controls, control_arm_controls=ctl_controls,
               accepted_without_side_effect=accepted, observer_evidence=observer,
               observer_complete=_observer_complete(hooks))
    leaked = common.tree_text_contains(root / ctl, nonce)
    if leaked:
        inconclusive.append(f"nonce found in the control arm: {leaked}")
    for m, name in ((meta, arm), (cmeta, ctl)):
        if m.get("credential_leaks"):
            inconclusive.append(f"{name}: credential value found in evidence; do not publish")
    if not all(ctl_controls.values()):
        inconclusive.append("control arm failed its own path-type control")
    if any(l["category"] == "unclassified" for l in locs):
        inconclusive.append("unclassified nonce location")
    if echo and not delivered:
        inconclusive.append("echo without recorded delivery")
    if observer and not delivered:
        inconclusive.append("observer evidence of a model-bound request, not counted "
                            "as recorded delivery: owner decision D3")
    if not delivered and not observer and not res["observer_complete"]:
        inconclusive.append("no complete model-bound request record, so absence is not evidence")
    if inconclusive:
        res.update(label=common.INCONCLUSIVE, reasons=inconclusive + side_effects)
        return res
    if delivered:
        res["label"] = common.DELIVERED_WITH_SIDE_EFFECT if side_effects else common.DELIVERED_TO_AGENT
    else:
        res["label"] = common.NOT_DELIVERED
    if side_effects:
        res["reasons"] = side_effects
    return res


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("pair", "path"))
    ap.add_argument("root")
    ap.add_argument("target")
    ap.add_argument("--accept-observer-record", action="store_true")
    ap.add_argument("--accept-candidate-T", action="store_true")
    a = ap.parse_args(argv[1:])
    root = Path(a.root).resolve()
    if a.action == "pair":
        if a.target not in PAIRS:
            print(f"pair target must be one of {sorted(PAIRS)}", file=sys.stderr)
            return 2
        res = classify_pair(root, a.target, a.accept_observer_record)
        common.write_json(root / a.target / "out" / "outcome.json", res)
        print(f"{res.get('path')} {a.target}: {res['label']}")
        return 0
    if a.target == "H6b":
        o = common.read_json(root / "h6b" / "out" / "outcome.json") or {
            "label": common.NOT_EXECUTED, "reasons": ["h6b not classified"]}
        res = {"path": "H6b", "label": o["label"], "bound_shape": "context"
               if o["label"] in common.PASSING else None, "candidates": [o], "rules": common.RULES}
    elif a.target == "H6a":
        cands = []
        for arm, c in (("h6a-N", "N"), ("h6a-T", "T")):
            cands.append(common.read_json(root / arm / "out" / "outcome.json") or {
                "candidate": c, "label": common.NOT_EXECUTED, "reasons": [f"{arm} not classified"]})
        res = common.summarize_path("H6a", cands, () if a.accept_candidate_T else ("T",))
    else:
        print("path target must be H6a or H6b", file=sys.stderr)
        return 2
    common.write_json(root / f"outcome.{a.target}.json", res)
    print(f"{a.target}: {res['label']} (bound shape: {res['bound_shape']})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
