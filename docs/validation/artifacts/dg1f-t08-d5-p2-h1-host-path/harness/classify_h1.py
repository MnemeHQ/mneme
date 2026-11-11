"""Classify H1 (Claude Code) host-output-path probes per the accepted probe scope (#545).

usage:
  classify_h1.py pair    <live_dir> <path_id> <pin_model> [<pin_version>]
                                                             -> writes <path_id>/out/outcome.json, prints label
  With <pin_version>, each arm's observer claude_version must equal it (else
  NOT_EXECUTED). run_h1.sh passes it under Amendment A2.
  classify_h1.py verify  <live_dir> [paths]                  -> exit 1 unless every selected outcome exists
  classify_h1.py summary <live_dir> <summary.md> [paths]
  [paths] is a comma-separated subset of the path ids below (default: all four).
  Only an all-four summary carries the H1 gate line; a subset summary (Amendment
  A2) carries a listed-path result that says it is not the H1 gate. Either is
  PASS only when every selected outcome records the same host version (A2-1).

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
#551) are implemented in categorise() (R1, R2) and host_events() (R3). Rule R4
(accepted in docs/plans/2026-10-19-dg1f-t08-d5-p2-a1-hook-system-message-rule.md,
#561) is implemented in categorise(). Rule R5 (accepted in
docs/plans/2026-11-11-dg1f-t08-d5-p2-a2-r5-host-record-rule.md, #796/#797) is
implemented in r5_anchors() and categorise(): category host_record, tied to
tool-attributed anchors A1-A6.
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
RULES_ID = "as-run table + R1-R5 (#551, #561, #796)"  # recorded in every outcome
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


R5_CONTEXT = " hook additional context: "
_R5_BLOB_TEXT = re.compile(r"message\.content\[(\d+)\]\.text")


def expected_label(event, tool):
    """R5's L: the probed event, plus ':<tool>' on a tool path."""
    return f"{event}:{tool}" if tool else event


def r5_wrap(label, content):
    """The exact host rendering R5a accepts for one hook_additional_context item."""
    return f"<system-reminder>\n{label}{R5_CONTEXT}{content}\n</system-reminder>"


def r5_anchors(arm, nonce, event, tool):
    """Tool-attributed anchors (R5, A1-A6), as {transcript line: content items}.

    An anchor is a transcript hook_additional_context attachment that meets R1's
    conditions and names the expected tool:
      A1 hookEvent is the probed event;
      A2 this arm's emitter emitted the nonce for that event (hook-log.jsonl);
      A3 the nonce is in attachment.content;
      A4 hookName equals the expected label exactly;
      A5 (tool path) toolUseID is the id of this arm's tool_use for the expected tool;
      A6 (tool path) the emitting hook-log envelope names that event AND tool.
    R1 itself is unchanged: an R1 entry that is not an anchor stays model_bound under
    R1, but R5 never classifies a record against it."""
    if not nonce or event is None:
        return {}
    label = expected_label(event, tool)
    emitted = [h for h in arm["hooks"] if nonce in (h.get("emitted") or "")
               and (h.get("envelope") or {}).get("hook_event_name") == event]           # A2
    if tool:
        emitted = [h for h in emitted if (h.get("envelope") or {}).get("tool_name") == tool]  # A6
    if not emitted:
        return {}
    tool_ids = set()
    if tool:
        for _, e in arm["transcript"]:
            if e.get("type") == "assistant":
                for c in content_items(e):
                    if c.get("type") == "tool_use" and c.get("name") == tool and c.get("id"):
                        tool_ids.add(c["id"])
    anchors = {}
    for line_no, e in arm["transcript"]:
        att = e.get("attachment") or {}
        if e.get("type") != "attachment" or att.get("type") != "hook_additional_context":
            continue
        content = att.get("content")
        if not isinstance(content, list) or not all(isinstance(c, str) for c in content):
            continue
        if (att.get("hookEvent") == event                                   # A1
                and any(nonce in c for c in content)                         # A3
                and att.get("hookName") == label                             # A4
                and (not tool or att.get("toolUseID") in tool_ids)):         # A5
            anchors[line_no] = list(content)
    return anchors


def _r5a_rendered(entry, line_no, r5):
    """R5a: the anchor's own rendered copy, renderedRole system, exact wrapping."""
    if not r5:
        return False
    label, anchors, _ = r5
    content = anchors.get(line_no)
    rendered = entry.get("rendered")
    return (content is not None and entry.get("renderedRole") == "system"
            and isinstance(rendered, list) and len(rendered) == len(content)
            and all(isinstance(r, dict) and r.get("content") == r5_wrap(label, c)
                    for r, c in zip(rendered, content)))


def _r5b_blob(entry, path, r5):
    """R5b: role system, an anchor exists, and every nonce line is an exact anchor line."""
    if not r5:
        return False
    label, anchors, nonce = r5
    m = _R5_BLOB_TEXT.fullmatch(path)
    msg = entry.get("message") or {}
    items = msg.get("content")
    if not (m and anchors and msg.get("role") == "system" and isinstance(items, list)):
        return False
    j = int(m.group(1))
    text = items[j].get("text") if j < len(items) and isinstance(items[j], dict) else None
    if not isinstance(text, str):
        return False
    allowed = {f"{label}{R5_CONTEXT}{c}" for cs in anchors.values() for c in cs}
    lines = [ln for ln in text.split("\n") if nonce in ln]
    return bool(lines) and all(ln in allowed for ln in lines)


def categorise(source, entry, path, probed_event=None, invoked_events=(), line_no=None, r5=None):
    """CATEGORY RULES. Return one of:
    model_bound    text the host placed in the model's input (user-role text, or a tool_result),
                   or (R1) a transcript `hook_additional_context` attachment for the probed
                   event that the emitter invoked, with the token in `attachment.content`
    echo           text the model produced (assistant text or the final result text)
    agent_reuse    the model put the token into a tool input after receiving it
    host_output    a stream-json `system` event, or (R2) a transcript `hook_success`
                   attachment (the hook's own stdout): output, not model input,
                   or (R4) a transcript `hook_system_message` attachment for the probed
                   event that the emitter invoked, with the token in `attachment.content`
                   (never delivery to the agent or the developer)
    host_record    (R5) the host's own record of content an anchor carries: (R5a) the
                   anchor's `rendered[i].content` when renderedRole is system and it equals
                   r5_wrap(L, content[i]) exactly; (R5b) an `api-request-blob` text with
                   role system whose every nonce line is exactly "L hook additional
                   context: C" for an anchor item C. Recorded; never delivery, never
                   sufficient alone, never masking (R1 still decides delivery)
    unclassified   anything else (never counted as delivery)
    """
    t = entry.get("type")
    if source == "transcript" and t == "api-request-blob":  # R5b
        return "host_record" if _r5b_blob(entry, path, r5) else "unclassified"
    if source == "transcript" and t == "attachment":
        att = entry.get("attachment") or {}
        kind = att.get("type")
        if kind == "hook_additional_context" and path.startswith("rendered["):  # R5a
            return "host_record" if _r5a_rendered(entry, line_no, r5) else "unclassified"
        # R1 and R4 share the same three narrow conditions.
        narrow = (probed_event is not None and att.get("hookEvent") == probed_event
                  and probed_event in invoked_events
                  and (path == "attachment.content" or path.startswith("attachment.content[")))
        if kind == "hook_additional_context":  # R1
            return "model_bound" if narrow else "unclassified"
        if kind == "hook_success":  # R2
            return "host_output"
        if kind == "hook_system_message":  # R4
            return "host_output" if narrow else "unclassified"
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


def nonce_locations(arm, nonce, probed_event=None, probed_tool=None):
    locs = []
    if not nonce:
        return locs
    # R1 condition (2): events for which this arm's emitter actually emitted the nonce.
    invoked = {(h.get("envelope") or {}).get("hook_event_name") for h in arm["hooks"]
               if nonce in (h.get("emitted") or "")}
    # R5: tool-attributed anchors for the probed event and tool (A1-A6).
    r5 = (expected_label(probed_event, probed_tool), r5_anchors(arm, nonce, probed_event, probed_tool),
          nonce) if probed_event is not None else None
    for source in ("events", "transcript"):
        for line_no, entry in arm[source]:
            for path, s in walk(entry):
                if nonce in s:
                    locs.append({
                        "source": source, "line": line_no, "entry_type": entry.get("type"),
                        "entry_subtype": entry.get("subtype"), "json_path": path,
                        "category": categorise(source, entry, path, probed_event, invoked,
                                               line_no=line_no, r5=r5),
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


def classify(emit, ctl, path_id, pin_model, pin_version=None):
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
        # Host version pin, when the caller passes one (Amendment A2 always does):
        # the observer records the version checked just before the session.
        if pin_version is not None and arm["observer"].get("claude_version") != pin_version:
            reasons.append(f"{name}: claude_version {arm['observer'].get('claude_version')!r} "
                           f"!= pinned {pin_version!r}")
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
    locs = nonce_locations(emit, emit["nonce"], spec["event"], spec["tool"])
    ctl_locs = nonce_locations(ctl, emit["nonce"], spec["event"], spec["tool"])
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


def cmd_pair(live, path_id, pin_model, pin_version=None):
    if path_id not in PATHS:
        print(f"unknown path id {path_id!r}", file=sys.stderr)
        return 2
    emit = load_arm(Path(live) / path_id / "out")
    ctl = load_arm(Path(live) / f"{path_id}-ctl" / "out")
    rec = classify(emit, ctl, path_id, pin_model, pin_version)
    rec["observer"] = {k: emit["observer"].get(k)
                       for k in ("claude_version", "pinset", "model_flag", "selftest", "date")}
    (Path(live) / path_id / "out" / "outcome.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
    print(rec["label"])
    return 0


def selected_paths(csv=None):
    """The batch's paths, in PATHS order. None means every H1 path.

    A batch may cover a subset (Amendment A2: H1a and H1b only). An unknown,
    duplicate or empty selection is refused rather than guessed."""
    if csv is None:
        return list(PATHS)
    names = [n for n in csv.split(",") if n]
    if not names or len(set(names)) != len(names) or any(n not in PATHS for n in names):
        raise ValueError(f"bad path selection {csv!r}; known paths: {', '.join(PATHS)}")
    return [p for p in PATHS if p in names]


def host_pin_problem(outcomes):
    """None when every outcome records the same non-empty host version, else the reason.

    A gate or listed-path result may only combine paths probed on one pinned host
    (probe scope 4.3, A2-1). Outcomes copied together from batches on different
    versions, or an outcome with no recorded version, never yield PASS."""
    versions = {p: (r.get("observer") or {}).get("claude_version") for p, r in outcomes.items()}
    unrecorded = sorted(p for p, v in versions.items() if not v)
    if unrecorded:
        return f"no recorded claude_version for {', '.join(unrecorded)}"
    distinct = sorted(set(versions.values()))
    if len(distinct) > 1:
        return "mixed host versions: " + "; ".join(
            f"{v} ({', '.join(p for p in outcomes if versions[p] == v)})" for v in distinct)
    return None


def cmd_verify(live, csv=None):
    bad = [p for p in selected_paths(csv) if not (Path(live) / p / "out" / "outcome.json").is_file()]
    for p in bad:
        print(f"missing outcome: {p}", file=sys.stderr)
    return 1 if bad else 0


def cmd_summary(live, dst, csv=None):
    paths = selected_paths(csv)
    outcomes = {p: json.loads((Path(live) / p / "out" / "outcome.json").read_text(encoding="utf-8")) for p in paths}
    rows = ["| Path | Path type | Label | Passes | Audience | Echoed | Host | Reasons |",
            "|---|---|---|---|---|---|---|---|"]
    for p, r in outcomes.items():
        audience = "agent" if r["label"] == "DELIVERED_TO_AGENT" else "none recorded"
        host = (r.get("observer") or {}).get("claude_version")
        rows.append(f"| {p} | {r['path_type']} | {r['label']} | {r['passes_path']} | {audience} | "
                    f"{r.get('echoed')} | {host} | {'; '.join(r.get('reasons') or []) or '-'} |")
    pin_problem = host_pin_problem(outcomes)
    passes = all(r["passes_path"] for r in outcomes.values()) and pin_problem is None
    selftest = any((r.get("observer") or {}).get("selftest") for r in outcomes.values())
    banner = "**SELF-TEST (stub `claude`, not Claude Code): NOT live evidence.**\n\n" if selftest else ""
    pin_note = f"\n**Host pin not established:** {pin_problem}. A result needs every path on one recorded " \
        "host version (probe scope §4.3, A2-1), so it cannot be PASS.\n" if pin_problem else ""
    if paths == list(PATHS):
        result = f"H1 gate (every path passes, one host version): **{'PASS' if passes else 'NOT MET'}**\n" + \
            pin_note + \
            "\nOnly the gate line above decides H1. `H1_DONE` means only that the batch finished " \
            "and every outcome was written; it never means H1 passed.\n"
    else:
        missing = ", ".join(p for p in PATHS if p not in paths)
        result = f"Listed-path result (every listed path passes, one host version): " \
            f"**{'PASS' if passes else 'NOT MET'}**\n" + pin_note + \
            f"\nThis batch covers only the listed paths, so this is **not** the H1 gate. H1 also needs " \
            f"{missing}, which this batch did not probe. `H1_DONE` means only that the batch finished " \
            "and every listed outcome was written; it never means a path passed.\n"
    text = "# H1 Claude Code host-output-path probe summary\n\n" + banner + "\n".join(rows) + "\n\n" + result
    (Path(live) / dst).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) in (4, 5) and a[0] == "pair":
        sys.exit(cmd_pair(*a[1:]))
    if len(a) in (2, 3) and a[0] == "verify":
        sys.exit(cmd_verify(*a[1:]))
    if len(a) in (3, 4) and a[0] == "summary":
        sys.exit(cmd_summary(*a[1:]))
    print(__doc__, file=sys.stderr)
    sys.exit(2)
