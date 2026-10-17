"""Classify H1 (Claude Code) host-output-path probes per the accepted probe scope (#545).

usage:
  classify_h1.py pair    <live_dir> <path_id> <pin_model>   -> writes <path_id>/out/outcome.json, prints label
  classify_h1.py verify  <live_dir>                          -> exit 1 unless all four outcomes exist
  classify_h1.py summary <live_dir> <summary.md>

Path ids and their path type (scope section 3.1):
  H1a-edit   command hook, tool event       (PreToolUse, Edit matcher)
  H1a-bash   command hook, tool event       (PreToolUse, Bash matcher)
  H1b-start  command hook, lifecycle event  (SessionStart)
  H1c-stop   command hook, lifecycle event  (Stop)
Each path has an emitter arm <path_id> and a paired no-op control arm <path_id>-ctl.

Labels (scope section 6). This headless harness never produces
DELIVERED_TO_USER_ONLY or EVIDENCE_REUSED: developer delivery needs an
operator-observed interactive run, and H1 has no prior evidence to reuse.

Nonce locations. Every occurrence of the emitter-arm nonce in the stream-json
events and the session transcript is recorded with its source, line, entry type
and JSON path, and categorised by the table in CATEGORY RULES below. A location
the table does not recognise is `unclassified`; it never counts as delivery.

Rules R1-R3 (accepted in docs/plans/2026-10-17-dg1f-t08-d5-p2-h1-classifier-rules.md,
#551) are implemented in categorise() (R1, R2) and host_events() (R3).
Extending the table is a reviewed change, and because raw evidence is kept,
the classifier can be re-run on existing evidence without a new probe.
"""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

PATHS = {
    "H1a-edit": {"path_type": "command_tool_event", "event": "PreToolUse", "tool": "Edit"},
    "H1a-bash": {"path_type": "command_tool_event", "event": "PreToolUse", "tool": "Bash"},
    "H1b-start": {"path_type": "command_lifecycle_event", "event": "SessionStart", "tool": None},
    "H1c-stop": {"path_type": "command_lifecycle_event", "event": "Stop", "tool": None},
}
RULES_ID = "as-run table + R1-R3 (#551)"  # recorded in every outcome
PASSING = ("DELIVERED_TO_AGENT", "DELIVERED_TO_USER_ONLY", "EVIDENCE_REUSED")
EDIT_EXPECTED = b"beta\n"
BASH_FILE, BASH_EXPECTED = "bash_out.txt", b"probe-ran\n"  # exact bytes, not a prefix

# ---------------------------------------------------------------- loading


def read_jsonl(p):
    rows = []
    if not p.exists():
        return rows
    for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append((i, json.loads(line)))
        except json.JSONDecodeError:
            rows.append((i, {"_unparsed": line}))
    return rows


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "absent"


def load_arm(out):
    out = Path(out)
    ws = out.parent / "ws"
    obs = {}
    if (out / "observer.txt").exists():
        for line in (out / "observer.txt").read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                obs.setdefault(k, v)
    return {
        "out": out,
        "nonce": (out / "nonce.txt").read_text(encoding="utf-8").strip() if (out / "nonce.txt").exists() else None,
        "events": read_jsonl(out / "events.jsonl"),
        "transcript": read_jsonl(out / "transcript.jsonl"),
        "transcript_collected": (out / "transcript.jsonl").exists(),
        "hooks": [r for _, r in read_jsonl(out / "hook-log.jsonl")],
        "notes_after": (ws / "notes.txt").read_bytes() if (ws / "notes.txt").exists() else None,
        "bash_after": (ws / BASH_FILE).read_bytes() if (ws / BASH_FILE).exists() else None,
        "notes_sha": sha(ws / "notes.txt"),
        "bash_sha": sha(ws / BASH_FILE),
        "observer": obs,
    }

# ---------------------------------------------------------------- stream helpers


def init_event(arm):
    for _, e in arm["events"]:
        if e.get("type") == "system" and e.get("subtype") == "init":
            return e
    return None


def result_event(arm):
    res = None
    for _, e in arm["events"]:
        if e.get("type") == "result":
            res = e
    return res


def content_items(entry):
    msg = entry.get("message") or {}
    c = msg.get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return [i for i in (c or []) if isinstance(i, dict)]


def tool_uses(arm):
    uses = {}
    for _, e in arm["events"]:
        if e.get("type") == "assistant":
            for it in content_items(e):
                if it.get("type") == "tool_use":
                    uses[it.get("id")] = it
    return uses


def tool_results(arm):
    res = {}
    for _, e in arm["events"]:
        if e.get("type") == "user":
            for it in content_items(e):
                if it.get("type") == "tool_result":
                    res[it.get("tool_use_id")] = it
    return res


def denied_ids(arm):
    r = result_event(arm) or {}
    ids = set()
    for d in r.get("permission_denials") or []:
        if isinstance(d, dict):
            ids.add(d.get("tool_use_id"))
    return ids


def masked(value, arm, nonce):
    """JSON text of `value` with this arm's workspace path and the nonce masked, so
    requests from the emitter arm (<id>/ws) and the control arm (<id>-ctl/ws) can be
    compared as equivalent when the agent asked for the same thing."""
    s = json.dumps(value, sort_keys=True)
    ws = arm["out"].parent / "ws"
    variants = {str(ws), str(ws).replace("\\", "\\\\"), ws.as_posix()}
    drive = ws.as_posix()
    if len(drive) > 2 and drive[1] == ":":
        variants.add("/" + drive[0].lower() + drive[2:])  # Git Bash /c/... form
    for v in sorted(variants, key=len, reverse=True):
        s = re.sub(re.escape(v), "<WS>", s, flags=re.I)
    if nonce:
        s = s.replace(nonce, "<NONCE>")
    return s


def permission_attempts(arm, nonce):
    """Per attempted tool request, the host's decision.

    Returns None when the result event exposes no `permission_denials` list
    (equivalence cannot be established). Otherwise:
      by_request:        {(tool name, masked input): sorted set of decisions}
                         decision is denied | executed | error | no_result
      unmatched_denials: denials whose tool_use_id matches no attempted request
    In headless -p with acceptEdits there is no interactive prompt: a prompt the
    host would have shown surfaces as a denial."""
    r = result_event(arm) or {}
    if not isinstance(r.get("permission_denials"), list):
        return None
    uses, results = tool_uses(arm), tool_results(arm)
    denied = {d.get("tool_use_id") for d in r["permission_denials"] if isinstance(d, dict)}
    by_request = {}
    for tid, u in uses.items():
        res = results.get(tid)
        if tid in denied:
            dec = "denied"
        elif res is None:
            dec = "no_result"
        else:
            dec = "error" if res.get("is_error") else "executed"
        key = (u.get("name"), masked(u.get("input"), arm, nonce))
        by_request.setdefault(key, set()).add(dec)
    unmatched = [masked(d, arm, nonce) for d in r["permission_denials"]
                 if not isinstance(d, dict) or d.get("tool_use_id") not in uses]
    return {"by_request": {k: sorted(v) for k, v in by_request.items()}, "unmatched_denials": unmatched}


def compare_permissions(pe, pc):
    """Compare decisions only for equivalent requests (present in both arms).
    Requests present in one arm only were model-chosen: recorded, never attributed."""
    shared = sorted(set(pe["by_request"]) & set(pc["by_request"]))
    mismatched = [{"request": list(k), "emitter": pe["by_request"][k], "control": pc["by_request"][k]}
                  for k in shared if pe["by_request"][k] != pc["by_request"][k]]
    only = {
        "emitter": [{"request": list(k), "decisions": v} for k, v in pe["by_request"].items() if k not in pc["by_request"]],
        "control": [{"request": list(k), "decisions": v} for k, v in pc["by_request"].items() if k not in pe["by_request"]],
    }
    return {"equivalent_requests": [list(k) for k in shared], "mismatched_decisions": mismatched,
            "non_equivalent_attempts": only}


# R3 (#551): left out of the strict subtype comparison only; still scanned for indicators.
EXCLUDED_FROM_SUBTYPE_COMPARISON = ("thinking_tokens",)
INDICATOR_KEYS = ("decision", "permissionDecision", "permission_decision", "blocked", "block",
                  "retry", "continue", "stopReason", "stop_reason")


def host_events(arm, nonce):
    """Every stream-json `system` event except init, NONCE OR NOT (strict rule).
    Returns (sorted subtypes, {(subtype, indicator key): sorted masked values})."""
    subs, indicators = [], {}
    for _, e in arm["events"]:
        if e.get("type") != "system" or e.get("subtype") == "init":
            continue
        sub = str(e.get("subtype"))
        if sub not in EXCLUDED_FROM_SUBTYPE_COMPARISON:
            subs.append(sub)
        stack = [e]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in INDICATOR_KEYS:
                        indicators.setdefault((sub, k), set()).add(masked(v, arm, nonce))
                    stack.append(v)
            elif isinstance(o, list):
                stack.extend(o)
    return sorted(subs), {k: sorted(v) for k, v in indicators.items()}


def hook_calls(arm, event):
    return [h for h in arm["hooks"] if (h.get("envelope") or {}).get("hook_event_name") == event]

# ---------------------------------------------------------------- CATEGORY RULES


def is_leak_use(use):
    """A tool call that could read the nonce outside the channel under test."""
    blob = json.dumps(use.get("input") or {}).lower()
    return "nonce.txt" in blob or "hook-log" in blob


def walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        yield path, obj


def categorise(source, entry, path, probed_event=None, invoked_events=()):
    """CATEGORY RULES. Return one of:
    model_bound    text the host placed in the model's input (user-role text, or a tool_result),
                   or (R1) a transcript `hook_additional_context` attachment for the probed
                   event that the emitter invoked, with the token in `attachment.content`
    echo           text the model produced (assistant text or the final result text)
    agent_reuse    the model put the token into a tool input after receiving it
    host_output    a stream-json `system` event, or (R2) a transcript `hook_success`
                   attachment (the hook's own stdout): output, not model input
    unclassified   anything else (never counted as delivery)
    """
    t = entry.get("type")
    if source == "transcript" and t == "attachment":
        att = entry.get("attachment") or {}
        kind = att.get("type")
        if kind == "hook_additional_context":  # R1, narrow: all three conditions
            ok = (probed_event is not None and att.get("hookEvent") == probed_event
                  and probed_event in invoked_events
                  and (path == "attachment.content" or path.startswith("attachment.content[")))
            return "model_bound" if ok else "unclassified"
        if kind == "hook_success":  # R2
            return "host_output"
        return "unclassified"
    if t == "assistant":
        return "agent_reuse" if ".input" in path else "echo"
    if t == "result":
        return "echo"
    if t == "user":
        return "model_bound"
    if source == "events" and t == "system":
        return "host_output"
    return "unclassified"


def nonce_locations(arm, nonce, probed_event=None):
    locs = []
    if not nonce:
        return locs
    # R1 condition (2): events for which this arm's emitter actually emitted the nonce.
    invoked = {(h.get("envelope") or {}).get("hook_event_name") for h in arm["hooks"]
               if nonce in (h.get("emitted") or "")}
    for source in ("events", "transcript"):
        for line_no, entry in arm[source]:
            for path, s in walk(entry):
                if nonce in s:
                    locs.append({
                        "source": source, "line": line_no, "entry_type": entry.get("type"),
                        "entry_subtype": entry.get("subtype"), "json_path": path,
                        "category": categorise(source, entry, path, probed_event, invoked),
                    })
    return locs

# ---------------------------------------------------------------- path-type controls


def tool_event_control(arm, tool):
    uses = [u for u in tool_uses(arm).values() if u.get("name") == tool]
    results = tool_results(arm)
    denied = denied_ids(arm)
    c = {"tool_use_present": bool(uses)}
    if uses:
        u = uses[0]
        r = results.get(u.get("id")) or {}
        c["tool_result_present"] = bool(r)
        c["tool_result_not_error"] = bool(r) and not r.get("is_error")
        c["not_permission_denied"] = u.get("id") not in denied
    if tool == "Edit":
        c["file_as_expected"] = arm["notes_after"] == EDIT_EXPECTED
    else:
        c["file_as_expected"] = arm["bash_after"] == BASH_EXPECTED
    c["holds"] = all(v for k, v in c.items() if k != "holds")
    return c


def lifecycle_control(arm, event):
    res = result_event(arm) or {}
    calls = hook_calls(arm, event)
    c = {
        "init_present": init_event(arm) is not None,
        "result_success": res.get("subtype") == "success" and res.get("is_error") is False,
        "hook_invocations": len(calls),
    }
    if event == "Stop":
        c["no_stop_reentry"] = not any((h.get("envelope") or {}).get("stop_hook_active") for h in calls)
    c["holds"] = c["init_present"] and c["result_success"] and c.get("no_stop_reentry", True)
    return c


def path_control(arm, spec):
    if spec["path_type"] == "command_tool_event":
        return tool_event_control(arm, spec["tool"])
    return lifecycle_control(arm, spec["event"])

# ---------------------------------------------------------------- classification


def classify(emit, ctl, path_id, pin_model):
    spec = PATHS[path_id]
    reasons = []
    # The rule-set id is set at creation so every outcome, including early
    # NOT_EXECUTED returns, records which rules produced it (review of #552).
    rec = {"path_id": path_id, "path_type": spec["path_type"], "event": spec["event"],
           "developer_also": "not_observed", "harness": "headless (-p, stream-json)",
           "rules": RULES_ID}

    def done(label):
        rec["label"] = label
        rec["passes_path"] = label in PASSING
        rec["reasons"] = reasons
        return rec

    # Preconditions -> NOT_EXECUTED (never a negative result).
    for name, arm in (("emitter", emit), ("control", ctl)):
        ie = init_event(arm)
        if ie is None:
            reasons.append(f"{name}: no init event (no session record)")
        elif ie.get("model") != pin_model:
            reasons.append(f"{name}: init model {ie.get('model')!r} != pinned {pin_model!r}")
        if result_event(arm) is None:
            reasons.append(f"{name}: no result event")
    if reasons:
        return done("NOT_EXECUTED")
    emitted = [h for h in hook_calls(emit, spec["event"]) if emit["nonce"] and emit["nonce"] in (h.get("emitted") or "")]
    if spec["tool"]:
        emitted = [h for h in emitted if (h.get("envelope") or {}).get("tool_name") == spec["tool"]]
    ctl_calls = hook_calls(ctl, spec["event"])
    rec["emitter_invocations"] = len(emitted)
    rec["control_hook_invocations"] = len(ctl_calls)
    if not emitted:
        reasons.append(f"emitter not invoked for {spec['event']} (event did not fire or hook not registered)")
    if not ctl_calls:
        reasons.append(f"control no-op not invoked for {spec['event']}")
    if reasons:
        return done("NOT_EXECUTED")

    # Evidence.
    locs = nonce_locations(emit, emit["nonce"], spec["event"])
    ctl_locs = nonce_locations(ctl, emit["nonce"], spec["event"])
    cats = {l["category"] for l in locs}
    rec["nonce_locations"] = locs
    rec["transcript_collected"] = emit["transcript_collected"]
    rec["echoed"] = "echo" in cats or "agent_reuse" in cats
    res_e, res_c = result_event(emit), result_event(ctl)
    rec["turns"], rec["turns_control"] = res_e.get("num_turns"), res_c.get("num_turns")  # evidence only

    # Controls (scope 3 step 4 and 3.1).
    ce, cc = path_control(emit, spec), path_control(ctl, spec)
    nonce = emit["nonce"]
    perm_e, perm_c = permission_attempts(emit, nonce), permission_attempts(ctl, nonce)
    perm_cmp = compare_permissions(perm_e, perm_c) if perm_e is not None and perm_c is not None else None
    rec["permissions"] = {"emitter": perm_e and {"unmatched_denials": perm_e["unmatched_denials"]},
                          "control": perm_c and {"unmatched_denials": perm_c["unmatched_denials"]},
                          "comparison": perm_cmp}
    subs_e, ind_e = host_events(emit, nonce)
    subs_c, ind_c = host_events(ctl, nonce)
    ind_shared = sorted(set(ind_e) & set(ind_c))
    ind_mismatch = [{"event_subtype": k[0], "field": k[1], "emitter": ind_e[k], "control": ind_c[k]}
                    for k in ind_shared if ind_e[k] != ind_c[k]]
    ind_one_side = sorted(set(ind_e) ^ set(ind_c))
    rec["host_events"] = {"emitter_subtypes": subs_e, "control_subtypes": subs_c,
                          "indicators": {"emitter": {f"{a}.{b}": v for (a, b), v in ind_e.items()},
                                         "control": {f"{a}.{b}": v for (a, b), v in ind_c.items()},
                                         "mismatched": ind_mismatch}}
    common = {
        # Only decisions for EQUIVALENT requests are attributed to the host; requests
        # one arm made alone are model-chosen and only recorded (review of #546).
        "permission_decisions_equal_for_equivalent_requests": perm_cmp is not None and not perm_cmp["mismatched_decisions"],
        # A permission/block/retry indicator present in both arms with different values.
        "host_indicators_equal": not ind_mismatch,
        "result_not_error": res_e.get("is_error") is False,
    }
    if spec["path_type"] == "command_tool_event":
        key = "notes_sha" if spec["tool"] == "Edit" else "bash_sha"
        common["file_matches_control"] = emit[key] == ctl[key]
    if spec["event"] == "Stop":
        common["stop_invocations_equal"] = ce["hook_invocations"] == cc["hook_invocations"]
    rec["controls"] = {"path_type_emitter": ce, "path_type_control_arm": cc, "common": common}
    controls_hold = ce["holds"] and all(common.values())

    # INCONCLUSIVE conditions.
    leaks = [u for u in tool_uses(emit).values() if is_leak_use(u)]
    if leaks:
        reasons.append("an agent tool call could read the nonce outside the channel (leak)")
    if ctl_locs:
        reasons.append("emitter nonce found in the control arm (collision)")
    if not cc["holds"]:
        reasons.append("the control arm's own path-type control failed; differences cannot be attributed")
    if perm_e is None or perm_c is None:
        reasons.append("the host did not expose permission_denials in both arms; permission equivalence cannot be established")
    else:
        for name, p in (("emitter", perm_e), ("control", perm_c)):
            if p["unmatched_denials"]:
                reasons.append(f"{name}: a permission denial matches no attempted request; it cannot be attributed")
    if subs_e != subs_c:
        reasons.append(f"unexplained host-event difference between arms (emitter {subs_e}, control {subs_c})")
    if ind_one_side:
        reasons.append(f"a permission/block/retry indicator appears in one arm only: {[f'{a}.{b}' for a, b in ind_one_side]}")
    # Unclassified-first: an unrecognised nonce location blocks any PASS, even when a
    # model-bound location also exists (review of #546, finding 1).
    if "unclassified" in cats:
        reasons.append("nonce found in locations the category table does not recognise; review needed")
    if reasons:
        return done("INCONCLUSIVE")

    if "model_bound" in cats:
        if controls_hold:
            return done("DELIVERED_TO_AGENT")
        reasons.append("host-induced side-effect control failed")
        return done("DELIVERED_WITH_SIDE_EFFECT")
    if rec["echoed"]:
        reasons.append("echo without recorded model-bound delivery")
        return done("INCONCLUSIVE")
    if not emit["transcript_collected"]:
        reasons.append("no model-bound delivery in stream-json and the session transcript was not collected")
        return done("INCONCLUSIVE")
    rec["side_effect_observed"] = not controls_hold
    return done("NOT_DELIVERED")


def cmd_pair(live, path_id, pin_model):
    if path_id not in PATHS:
        print(f"unknown path id {path_id!r}", file=sys.stderr)
        return 2
    emit = load_arm(Path(live) / path_id / "out")
    ctl = load_arm(Path(live) / f"{path_id}-ctl" / "out")
    rec = classify(emit, ctl, path_id, pin_model)
    rec["observer"] = {k: emit["observer"].get(k) for k in ("claude_version", "selftest", "date")}
    (Path(live) / path_id / "out" / "outcome.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
    print(rec["label"])
    return 0


def cmd_verify(live):
    bad = [p for p in PATHS if not (Path(live) / p / "out" / "outcome.json").is_file()]
    for p in bad:
        print(f"missing outcome: {p}", file=sys.stderr)
    return 1 if bad else 0


def cmd_summary(live, dst):
    rows = ["| Path | Path type | Label | Passes | Audience | Echoed | Reasons |", "|---|---|---|---|---|---|---|"]
    for p in PATHS:
        r = json.loads((Path(live) / p / "out" / "outcome.json").read_text(encoding="utf-8"))
        audience = "agent" if r["label"] == "DELIVERED_TO_AGENT" else "none recorded"
        rows.append(f"| {p} | {r['path_type']} | {r['label']} | {r['passes_path']} | {audience} | "
                    f"{r.get('echoed')} | {'; '.join(r.get('reasons') or []) or '-'} |")
    gate = all(json.loads((Path(live) / p / "out" / "outcome.json").read_text(encoding="utf-8"))["passes_path"]
               for p in PATHS)
    selftest = any(json.loads((Path(live) / p / "out" / "outcome.json").read_text(encoding="utf-8"))
                   .get("observer", {}).get("selftest") for p in PATHS)
    banner = "**SELF-TEST (stub `claude`, not Claude Code): NOT live evidence.**\n\n" if selftest else ""
    text = "# H1 Claude Code host-output-path probe summary\n\n" + banner + "\n".join(rows) + \
        f"\n\nH1 gate (every path passes): **{'PASS' if gate else 'NOT MET'}**\n" + \
        "\nOnly the gate line above decides H1. `H1_DONE` means only that the batch finished " \
        "and every outcome was written; it never means H1 passed.\n"
    (Path(live) / dst).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 4 and a[0] == "pair":
        sys.exit(cmd_pair(a[1], a[2], a[3]))
    if len(a) == 2 and a[0] == "verify":
        sys.exit(cmd_verify(a[1]))
    if len(a) == 3 and a[0] == "summary":
        sys.exit(cmd_summary(a[1], a[2]))
    print(__doc__, file=sys.stderr)
    sys.exit(2)
