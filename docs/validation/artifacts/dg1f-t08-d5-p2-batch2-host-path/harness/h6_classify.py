"""Classify H6 arms. H6a and H6b are classified and recorded separately.

usage:
  h6_classify.py pair <live_root> <h6b|h6a-N|h6a-T> [--accept-observer-record]
      -> <arm>/out/outcome.json
  h6_classify.py path <live_root> <H6a|H6b>
      -> <live_root>/outcome.H6a.json or outcome.H6b.json

Path type (probe scope section 3.1): in-process callback. Controls, host
induced only: the probed tool dispatched (a ``post_tool_call`` for
``write_file``/``patch`` with no error, and ``notes.txt`` reads ``beta``),
every turn completed (exit 0), and the control arm passed the same checks.
For H6a candidate T, also: the host's recorded tool result equals the
callback's return, which equals the untransformed result plus the
annotation, so the result is otherwise unchanged (the middleware control,
applied because T rewrites a tool result).

Nonce locations (as-built table; extending it is a reviewed change):

  session record row, role user or tool        -> model_bound (host's own record)
  session record row, role assistant           -> echo
  session record row, any other role or none   -> unclassified
  turn stdout (the final response)             -> echo
  turn stderr                                  -> unclassified
  pre_api_request observer, role user/tool/system -> observer
  pre_api_request observer, role assistant     -> echo

**Observer evidence is recorded, not counted.** On hermes-agent 0.19.0,
``pre_llm_call`` context is documented as "ephemeral -- never persisted to
session DB", so H6b (and H6a candidate N) cannot appear in the host's
session record. The harness's ``pre_api_request`` observer is a plugin
callback the host dispatches, not the host's own session record (section 3
step 2). Whether it may count as recorded delivery is an owner decision
(README, discrepancy D3). Until it is made, the default never counts it:
``--accept-observer-record`` exists only so the decision can be applied by
re-classification, without a re-run.
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


def _load(root: Path, arm: str):
    out = root / arm / "out"
    return (out, common.read_json(out / "probe.json"), common.read_json(out / "arm.json"),
            common.read_jsonl(out / "hook-log.jsonl"))


def _controls(meta, hooks) -> dict:
    dispatched = [h for h in hooks if h.get("hook") == "post_tool_call"
                  and h.get("tool_name") in PROBED_TOOLS]
    return {
        "tool_dispatched": bool(dispatched) and not any(h.get("error_type") for h in dispatched),
        "file_written": meta.get("notes_after") in ("beta\n", "beta"),
        "turns_completed": bool(meta.get("turn_exit_codes"))
        and all(c == 0 for c in meta["turn_exit_codes"]),
    }


def _session_rows(out: Path):
    return [r for r in common.read_jsonl(out / "session.jsonl") if isinstance(r, dict)]


def locations(out: Path, nonce: str, hooks) -> list:
    locs = []
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
                cat = "echo" if role == "assistant" else "observer"
                locs.append({"source": "pre_api_request", "json_path": l.get("json_path"),
                             "role": role, "category": cat})
    return locs


def _transform_preserved(out: Path, hooks, nonce: str) -> bool:
    for h in hooks:
        ret = h.get("returned")
        if h.get("hook") == "transform_tool_result" and isinstance(ret, str):
            suffix = "\n\n" + common.notice(nonce, "H6a")
            if not ret.endswith(suffix):
                return False
            original = ret[: -len(suffix)]
            if hashlib.sha256(original.encode("utf-8")).hexdigest() != h.get("result_sha256"):
                return False
            return any(isinstance(r.get("content"), str) and r["content"] == ret
                       for r in _session_rows(out))
    return False


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
    if probe and not any(h.get("hook") == EMIT_HOOK.get(probe.get("mode"))
                         and h.get("returned") is not None for h in hooks):
        reasons.append("the emitter callback never emitted (precondition, e.g. the probed tool was not called)")
    if not chooks:
        reasons.append("the control plugin was never invoked")
    if reasons:
        res.update(label=common.NOT_EXECUTED, reasons=reasons)
        return res
    nonce = (out / "nonce.txt").read_text(encoding="utf-8").strip()
    res["nonce"] = nonce
    controls = _controls(meta, hooks)
    ctl_controls = _controls(cmeta, chooks)
    if probe["mode"] == "h6a-transform":
        controls["tool_result_otherwise_unchanged"] = _transform_preserved(out, hooks, nonce)
    locs = locations(out, nonce, hooks)
    model_bound = any(l["category"] == "model_bound" for l in locs)
    observer = any(l["category"] == "observer" for l in locs)
    delivered = model_bound or (accept_observer and observer)
    echo = any(l["category"] == "echo" for l in locs)
    ok = all(controls.values())
    res.update(locations=locs, controls=controls, control_arm_controls=ctl_controls,
               accepted_without_side_effect=ok, observer_evidence=observer)
    inconclusive = []
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
        # The nonce is in a model-bound request, so NOT_DELIVERED would be
        # false; but the only record is the uncounted observer (D3).
        inconclusive.append("observer evidence of a model-bound request, not counted "
                            "as recorded delivery: owner decision D3")
    if inconclusive:
        res.update(label=common.INCONCLUSIVE, reasons=inconclusive)
        return res
    if delivered:
        res["label"] = common.DELIVERED_TO_AGENT if ok else common.DELIVERED_WITH_SIDE_EFFECT
    else:
        res["label"] = common.NOT_DELIVERED
    return res


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("pair", "path"))
    ap.add_argument("root")
    ap.add_argument("target")
    ap.add_argument("--accept-observer-record", action="store_true")
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
        res = common.summarize_path("H6a", cands)
    else:
        print("path target must be H6a or H6b", file=sys.stderr)
        return 2
    common.write_json(root / f"outcome.{a.target}.json", res)
    print(f"{a.target}: {res['label']} (bound shape: {res['bound_shape']})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
