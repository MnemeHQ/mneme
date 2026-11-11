"""Classify one C3 probe against its matrix row (scope #592 §§5-6).

usage: classify_c3.py <out-dir> <model-pin>
       classify_c3.py --pair <diagnostic-out-dir> <control-out-dir>

Writes ``<out-dir>/outcome.json`` and prints its label. Labels:

  PASS                 every required evidence item agrees with the row
  FAIL                 an evidence item contradicts the row
  EVIDENCE_INCOMPLETE  a required evidence item is missing (never a pass)
  PROTOCOL_DEVIATION   the agent did not make exactly the requested call
  RECORDED             batch H: host behavior recorded, no expectation
  NOT_OFFERED          the host's init tool list lacks the requested tool and
                       no call was made: N/A, neither PASS nor FAIL

Mneme's own output (E3) is never sufficient alone: a refusal needs the
unchanged file (E1) and the host's error result (E2) as well.

F-R2 (C2b charter §17.5). On a headless proceed row whose verifier is
UNVERIFIABLE, the §17.2 diagnostic must be in an R1 session-transcript entry:
a `hook_additional_context` attachment. Text in any other model-bound entry
(a user turn or tool_result) is recorded but does not pass. The
hook's stdout, `hook_success` attachments (R2), stream-json `system` events,
stderr and debug logs are emitted or host output, never delivery. Every other
proceed row is a control and must show no diagnostic at all. A missing
transcript is EVIDENCE_INCOMPLETE. `outcome.json` reports this under
`diagnostic`, apart from the refusal `delivery` levels; `user_visible` is
always `not_tested` (headless).

T-08 G3 rows (charter docs/plans/2026-11-10-t08-g3-host-boundary-live-charter.md
§6) are classified on items 1-6 on top of E1-E4 and get the charter's labels
instead of PASS: REFUSED_MEMORY_PATH_MISMATCH (G3-1) or
RECORDED_FALSE_COMPLETE_PASS (G3-2) when every item holds (item 5 may be
not observed), UNEXPECTED on any contradiction or deviation, and
EVIDENCE_INCOMPLETE when evidence is missing. ``outcome.json`` carries a
``g3`` block that keeps the observed items apart from the replay.

``--pair`` compares a diagnostic probe with a paired control of the same tool
(R3: stream-json `system` subtypes other than init and `thinking_tokens`, and
the permission indicators in them) and writes ``pair-<control>.json`` in the
diagnostic probe's directory. It prints PAIR_OK or PAIR_MISMATCH.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matrix  # noqa: E402

VIOLATION = "architectural decision violated"
ALLOWED_GIT_ENV = {
    "PATH", "SYSTEMROOT", "COMSPEC", "PATHEXT", "WINDIR", "HOME", "USERPROFILE",
    "XDG_CONFIG_HOME", "TMP", "TEMP", "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL",
    "GIT_TERMINAL_PROMPT", "GIT_CEILING_DIRECTORIES",
}


def norm_path(path: str) -> str:
    return str(path).replace("\\", "/").lower().rstrip("/")


def observer_hashes(text: str) -> dict:
    hashes = {}
    for line in text.splitlines():
        match = re.match(r"^(BEFORE|AFTER) (\S+)\s+(\S+)$", line)
        if match:
            hashes[(match.group(1), match.group(2))] = match.group(3)
    return hashes


def walk(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def host_events(out: Path) -> tuple[list[dict], str | None, str, list | None]:
    """tool_use / tool_result blocks, init model and init tool list (E2)."""
    files = [out / "events.jsonl"] if (out / "events.jsonl").exists() else sorted(
        out.glob("transcript-*.jsonl"))
    blocks, model, tools = [], None, None
    transcript = not (out / "events.jsonl").exists()
    for path in files:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            # An interactive session transcript also logs the raw API requests
            # (type api-request-blob, ...), which repeat earlier tool_use and
            # tool_result blocks; only the conversation entries count (the first
            # clean Q2 session showed one Write twice).
            if transcript and event.get("type") not in ("assistant", "user"):
                continue
            if event.get("type") == "system" and event.get("subtype") == "init":
                model = event.get("model")
                if isinstance(event.get("tools"), list):
                    tools = event["tools"]
            for item in walk(event):
                if item.get("type") in ("tool_use", "tool_result"):
                    blocks.append(item)
    source = "stream-json" if (out / "events.jsonl").exists() else (
        "transcript" if files else "none")
    return blocks, model, source, tools


def result_text(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    return "\n".join(item.get("text", "") for item in walk(content) if isinstance(item, dict))


# C2b charter §17.2: the fixed text of the UNVERIFIABLE-proceed diagnostic.
# Copied, not imported: the classifier never loads the runtime it judges.
DIAG_MARKER = "Mneme availability:"
DIAG_MISMATCH = " The effective memory differs from the declared memory."


def diagnostic_text(reason: str, mismatch: bool) -> str:
    text = (f"{DIAG_MARKER} authorization could not be verified "
            f"(AUTHORIZATION_UNVERIFIABLE, reason {reason}). "
            "This edit proceeded without fail-closed availability enforcement.")
    return text + DIAG_MISMATCH if mismatch else text


def diagnostic_expectation(spec: dict) -> str | None:
    """§17.2: every exit-0 proceed under UNVERIFIABLE carries the diagnostic;
    no other proceed does. Refusals and blocks exit 2 and are not checked."""
    if spec["expect"] != "proceed":
        return None
    return "delivered" if (spec["verifier"] or "").startswith("UNVERIFIABLE:") else "absent"


def jsonl_entries(path: Path) -> list[dict]:
    rows = []
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return [r for r in rows if isinstance(r, dict)]


def strings(value, path: str = ""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from strings(item, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from strings(item, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def categorise(source: str, entry: dict, path: str, use_id: str | None,
               emitted_for: set) -> str:
    """The H1 category table with rules R1, R2 and R4 (H1 record §7; #551, #561).

    model_bound   user-role text or a tool_result, or (R1) a transcript
                  `hook_additional_context` attachment for a PreToolUse call whose
                  hook emitted the diagnostic, with the text in `attachment.content`
    echo          text the model produced; agent_reuse: a model tool input
    host_output   a stream-json `system` event, (R2) a `hook_success` attachment
                  (the hook's own stdout), or (R4) a `hook_system_message` attachment
    unclassified  anything else; never delivery

    The R1/R4 narrow conditions are H1's (probed event, emitter invoked, content
    path), plus: an attachment that names a `toolUseID` must name the probed call.
    """
    kind = entry.get("type")
    if source == "transcript" and kind == "attachment":
        att = entry.get("attachment") or {}
        narrow = (att.get("hookEvent") == "PreToolUse" and use_id in emitted_for
                  and att.get("toolUseID", use_id) == use_id
                  and (path == "attachment.content" or path.startswith("attachment.content[")))
        if att.get("type") == "hook_additional_context":  # R1
            return "model_bound" if narrow else "unclassified"
        if att.get("type") == "hook_success":  # R2
            return "host_output"
        if att.get("type") == "hook_system_message":  # R4
            return "host_output" if narrow else "unclassified"
        return "unclassified"
    if kind == "assistant":
        return "agent_reuse" if ".input" in path else "echo"
    if kind == "result":
        return "echo"
    if kind == "user":
        return "model_bound"
    if source == "events" and kind == "system":
        return "host_output"
    return "unclassified"


# R3 (#551): left out of the strict subtype comparison only; still scanned for indicators.
EXCLUDED_FROM_SUBTYPE_COMPARISON = ("thinking_tokens",)
INDICATOR_KEYS = ("decision", "permissionDecision", "permission_decision", "blocked", "block",
                  "retry", "continue", "stopReason", "stop_reason")


def host_system(events: list[dict]) -> dict:
    """Stream-json `system` events except init (R3), for the paired-control comparison."""
    subtypes, indicators = [], {}
    for event in events:
        if event.get("type") != "system" or event.get("subtype") == "init":
            continue
        sub = str(event.get("subtype"))
        if sub not in EXCLUDED_FROM_SUBTYPE_COMPARISON:
            subtypes.append(sub)
        for item in walk(event):
            for key, value in item.items():
                if key in INDICATOR_KEYS:
                    indicators.setdefault(f"{sub}.{key}", set()).add(json.dumps(value, sort_keys=True))
    return {"subtypes": sorted(subtypes),
            "indicators": {k: sorted(v) for k, v in sorted(indicators.items())}}


def expected_after_ok(plan: dict, after: str | None) -> bool:
    if after is None:
        return False
    if plan["tool"] == "Write":
        return after.replace("\r\n", "\n") == plan["content"]
    edits = plan.get("edits") or [{"old_string": plan["old_string"],
                                   "new_string": plan["new_string"]}]
    for edit in edits:
        if edit["new_string"] and edit["new_string"] not in after:
            return False
        if not edit["new_string"] and edit["old_string"].strip() in after:
            return False
    return True


def g3_capture(sni: Path, origin_url: str, selftest: bool) -> tuple[str, str]:
    """G3 E4 OS capture rule (PR #792 review): stricter than the C3 rule.

    Returns ``(state, reason)``; state is ok, contradicts, missing or
    "not required in self-test".

    - absent, empty, or not in the extraction format (host lines, then exactly
      one final "# N other host(s) observed, not published" line): missing;
    - a forbidden host, or a published host outside matrix.G3_E4_HOST_FAMILIES:
      contradicts;
    - the origin's host not observed: missing, never a pass. Two of the
      historical networked C3 captures (P-6-MultiEdit-1, R-1-Edit-2) lacked it,
      so its absence shows a capture gap, not a verifier fault;
    - otherwise ok.
    The capture cannot attribute a host to a process; the verifier's exact
    destinations are the wrapper half (E4_wrapper).
    """
    from urllib.parse import urlparse

    if not sni.exists():
        return ("not required in self-test" if selftest else "missing",
                "netcap-sni.txt absent")
    lines = [ln.strip() for ln in sni.read_text(encoding="utf-8", errors="replace").splitlines()
             if ln.strip()]
    comments = [ln for ln in lines if ln.startswith("#")]
    summary = re.fullmatch(matrix.G3_E4_SUMMARY, lines[-1]) if lines else None
    if not lines or summary is None or len(comments) != 1:
        return "missing", "netcap-sni.txt is empty or not in the G3 extraction format"
    hosts = sorted({ln.lower().rstrip(".") for ln in lines if not ln.startswith("#")})
    forbidden = [h for h in hosts if any(h == f.split(":")[0] for f in matrix.FORBIDDEN_HOSTS)]
    if forbidden:
        return "contradicts", f"forbidden host(s) observed: {forbidden}"
    outside = [h for h in hosts
               if not any(h == fam or h.endswith("." + fam) for fam in matrix.G3_E4_HOST_FAMILIES)]
    if outside:
        return "contradicts", f"published host(s) outside the G3 families: {outside}"
    forge = (urlparse(origin_url).hostname or "").lower()
    if forge not in hosts:
        return "missing", f"forge endpoint {forge!r} not observed in the capture"
    return "ok", f"forge {forge!r} observed; published {hosts}; {summary.group(1)} other host(s) counted"


def _complete(payload, verdict: str) -> bool:
    return (isinstance(payload, dict) and payload.get("verdict") == verdict
            and payload.get("evaluation_complete") is True)


def classify_g3(out: Path, setup: dict, spec: dict, plan: dict, observer: str,
                hashes: dict, mine: list, facts: dict, checks: dict) -> dict:
    """Charter §6 items 1-6 for a G3 row. Returns the ``g3`` outcome block.

    ``observed`` holds what the live run showed (items 1-5); ``replayed`` holds
    the post-hoc replay (item 6). Item 5 may be ``not_observed`` without
    failing the row; the record must then say so (charter §6, §7).
    """
    g3 = setup.get("g3") or {}
    items: dict[str, str] = {}
    fails: list[str] = []
    miss: list[str] = []

    def verdict(name: str, ok: bool | None, why: str) -> None:
        if ok is None:
            items[name] = "missing"
            miss.append(f"G3 {name}: {why}")
        else:
            items[name] = "ok" if ok else "contradicts"
            if not ok:
                fails.append(f"G3 {name}: {why}")

    use_id = facts.get("tool_use_id")
    entry = next((e for e in mine if use_id and e.get("tool_use_id") == use_id), None)
    foreign = norm_path(g3.get("foreign_memory") or "")
    stderr = (entry or {}).get("stderr", "")

    # Item 1: the channel. Hook env from the local file only; file unchanged.
    env_keys = re.search(r"row_env_keys=(.*)$", observer, re.M)
    local_before = hashes.get(("BEFORE", "project_local"))
    local_after = hashes.get(("AFTER", "project_local"))
    if entry is None or env_keys is None or not g3:
        verdict("item1_channel", None, "no hook record for this call, no observer env line, or no setup g3")
    else:
        ok = (entry.get("MNEME_MEMORY") == g3["mneme_memory_value"]
              and env_keys.group(1).strip() == ""
              and local_before == local_after == g3["settings_local_sha256"])
        verdict("item1_channel", ok, f"hook MNEME_MEMORY {entry.get('MNEME_MEMORY')!r}, "
                f"launch env keys {env_keys.group(1).strip()!r}, local file "
                f"{local_before} -> {local_after}")

    # Item 2: the hook's own find_memory call during this Edit (observed).
    calls = (entry or {}).get("find_memory_calls")
    if entry is None or calls is None:
        verdict("item2_selection", None, "no find_memory observation for this call")
    else:
        last = calls[-1] if calls else {}
        ok = (bool(calls) and not last.get("exception")
              and norm_path(last.get("returned") or "") == foreign)
        facts["g3_selected_memory"] = last.get("returned")
        verdict("item2_selection", ok, f"hook find_memory returned {last.get('returned')!r}"
                + (f", raised {last['exception']}" if last.get("exception") else ""))

    # Item 3: availability. G3-1 the SS-3 refusal at the golden tip; G3-2 none.
    if entry is None:
        verdict("item3_availability", None, "no hook record for this call")
    elif spec["verifier"] == "AUTHORIZED":
        golden = re.search(r'"tip": "([0-9a-f]{40})"', observer)
        ok = (checks.get("verifier") == "ok" and golden is not None
              and f"baseline=main@{golden.group(1)[:7]}" in stderr
              and "SS-3 memory path mismatch" in stderr
              and "operational refusal (UNEVALUATED: MEMORY_PATH_MISMATCH)" in stderr)
        verdict("item3_availability", ok, "no verified AUTHORIZED SS-3 mismatch refusal")
    else:
        ok = not entry.get("verifications") and "mneme-hook: availability" not in stderr
        verdict("item3_availability", ok, "the verifier ran or an availability line appeared")

    # Item 4: the host outcome (E1-E3 plus, for a landed edit, the exact bytes).
    base = [checks.get(k) for k in ("E1", "E2", "E3")]
    if None in base:
        verdict("item4_host_outcome", None, "E1, E2 or E3 not established")
    else:
        ok = all(v == "ok" for v in base)
        if ok and spec["expect"] == "proceed":
            before_p, after_p = out / "target.before", out / "target.after"
            if before_p.exists() and after_p.exists():
                b = before_p.read_text(encoding="utf-8").replace("\r\n", "\n")
                a = after_p.read_text(encoding="utf-8").replace("\r\n", "\n")
                ok = a == b.replace(plan["old_string"], plan["new_string"], 1) and a != b
            else:
                ok = False
        verdict("item4_host_outcome", ok, f"E1/E2/E3 {base}, or the change is not exactly "
                "the forbidden replacement")

    # Item 5: the live checker's own result (observed), or not observed.
    checked = (entry or {}).get("check_calls") or []
    payloads = [c for c in checked if isinstance(c.get("payload"), dict)]
    if not payloads:
        items["item5_live_checker"] = "not_observed"
    else:
        c = payloads[-1]
        ok = (len(checked) == 1 and norm_path(c.get("memory") or "") == foreign
              and c.get("returncode") == 0 and _complete(c["payload"], "PASS"))
        verdict("item5_live_checker", ok, f"live check against {c.get('memory')!r}: "
                f"exit {c.get('returncode')}, payload {c.get('payload')}")

    # Item 6: the post-hoc replay (replay, not observation).
    replay_p = out / "replay-g3.json"
    replay = json.loads(replay_p.read_text(encoding="utf-8")) if replay_p.exists() else None
    if replay is None:
        verdict("item6_replay", None, "replay-g3.json missing")
    else:
        f_rec, o_rec = replay.get("foreign") or {}, replay.get("own") or {}
        ok = (f_rec.get("exit") == 0 and _complete(f_rec.get("payload"), "PASS")
              and _complete(o_rec.get("payload"), "FAIL")
              and "C3-DEC" in (o_rec.get("payload") or {}).get("decision_ids", []))
        verdict("item6_replay", ok, f"foreign {f_rec.get('payload')}, own {o_rec.get('payload')}")

    return {
        "charter": "docs/plans/2026-11-10-t08-g3-host-boundary-live-charter.md",
        "items": items,
        "item5": "observed" if items.get("item5_live_checker") == "ok" else
                 "not_observed" if items.get("item5_live_checker") == "not_observed" else
                 "contradicted",
        "observed": {"hook_MNEME_MEMORY": (entry or {}).get("MNEME_MEMORY"),
                     "find_memory_calls": (entry or {}).get("find_memory_calls"),
                     "check_calls": checked},
        "replayed": replay,
        "complete_claim": ("observed" if items.get("item5_live_checker") == "ok"
                           else "replay-confirmed only"),
        "_failures": fails, "_missing": miss,
    }


def main() -> int:
    out, model_pin = Path(sys.argv[1]), sys.argv[2]
    setup = json.loads((out / "setup.json").read_text(encoding="utf-8"))
    observer = (out / "observer.txt").read_text(encoding="utf-8", errors="replace")
    spec, plan = setup["spec"], setup["plan"]
    arm = "interactive" if "arm=interactive" in observer else "headless"
    selftest = "SELFTEST=1" in observer
    expect, verifier_expect = spec["expect"], spec["verifier"]
    checks: dict[str, str] = {}
    failures: list[str] = []
    missing: list[str] = []
    deviations: list[str] = []
    facts: dict = {}

    # E1: outside-observer hashes of the target.
    hashes = observer_hashes(observer)
    before, after = hashes.get(("BEFORE", "target")), hashes.get(("AFTER", "target"))
    after_text = (out / "target.after").read_text(encoding="utf-8", errors="replace") \
        if (out / "target.after").exists() else None
    if before is None or after is None:
        missing.append("E1 before/after hashes")
    else:
        changed = before != after
        facts["target_changed"] = changed
        if expect.startswith("refuse") or expect == "block":
            ok = not changed
        elif expect == "proceed":
            ok = changed and expected_after_ok(plan, after_text)
        else:
            ok = True
        checks["E1"] = "ok" if ok else "contradicts"
        if not ok:
            failures.append(f"E1: target {'changed' if changed else 'unchanged'}")

    # E2: the host's tool_use and matching tool_result.
    blocks, model, source, host_tools = host_events(out)
    facts["e2_source"] = source
    uses = [b for b in blocks if b.get("type") == "tool_use"
            and norm_path((b.get("input") or {}).get("file_path", "")) == norm_path(setup["target"])]
    if source == "none":
        missing.append("E2 host events")
    elif len(uses) != 1 or uses[0].get("name") != plan["tool"]:
        deviations.append(f"E2: {len(uses)} call(s) on the target, "
                          f"tools {[u.get('name') for u in uses]}, expected one {plan['tool']}")
    else:
        use = uses[0]
        results = [b for b in blocks if b.get("type") == "tool_result"
                   and b.get("tool_use_id") == use.get("id")]
        if not results:
            missing.append("E2 tool_result")
        else:
            res = results[0]
            text, is_error = result_text(res), bool(res.get("is_error"))
            facts["tool_result_is_error"] = is_error
            facts["tool_result_excerpt"] = text[:400]
            if expect.startswith("refuse:"):
                category = expect.split(":", 1)[1]
                ok = (is_error and f"UNEVALUATED: {category}" in text and VIOLATION not in text)
            elif expect == "block":
                ok = is_error and VIOLATION in text and "operational refusal" not in text
            elif expect == "proceed":
                ok = not is_error
            else:
                ok = True
            checks["E2"] = "ok" if ok else "contradicts"
            if not ok:
                failures.append(f"E2: tool_result is_error={is_error}, text does not match {expect}")
        facts["tool_use_id"] = use.get("id")

    # E3: the wrapped hook's record for this call.
    log = out / "hook-log.jsonl"
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()
               if line.strip()] if log.exists() else []
    mine = [e for e in entries if norm_path(e.get("file_path") or "") == norm_path(setup["target"])]
    facts["hook_records"] = len(mine)
    if "remove_hook" in spec["mutate"] or "hook_missing_command" in spec["mutate"]:
        checks["E3"] = "ok" if not mine else "contradicts"
        if mine and expect != "record":
            failures.append("E3: the hook ran although it was not registered")
    elif expect == "record":
        checks["E3"] = "recorded"
    elif not mine:
        missing.append("E3 hook record")
    else:
        entry = mine[-1]
        facts["hook_exit"], facts["hook_seconds"] = entry.get("exit"), entry.get("seconds")
        stderr = entry.get("stderr", "")
        if expect.startswith("refuse:"):
            ok = entry.get("exit") == 2 and f"UNEVALUATED: {expect.split(':', 1)[1]}" in stderr
        elif expect == "block":
            ok = entry.get("exit") == 2 and VIOLATION in stderr and "operational refusal" not in stderr
        else:
            ok = entry.get("exit") == 0
        checks["E3"] = "ok" if ok else "contradicts"
        if not ok:
            failures.append(f"E3: hook exit {entry.get('exit')} does not match {expect}")

        # Verifier observation (wrapper) and E4 wrapper half.
        verifications = [v for e in mine for v in e.get("verifications", [])]
        calls = [c for e in mine for c in e.get("verifier_git_calls", [])]
        facts["verifications"] = verifications
        if verifier_expect is None:
            ok = not verifications
        elif not verifications:
            ok = False
        else:
            got = verifications[-1]
            if verifier_expect.startswith("UNVERIFIABLE:"):
                ok = (got["authorization"] == "AUTHORIZATION_UNVERIFIABLE"
                      and got["reason"] in verifier_expect.split(":", 1)[1].split("|"))
            else:
                golden = re.search(r'"tip": "([0-9a-f]{40})"', observer)
                ok = (got["authorization"] == verifier_expect
                      and (golden is None or got["tip"] == golden.group(1)))
        checks["verifier"] = "ok" if ok else "contradicts"
        if not ok:
            failures.append(f"verifier: expected {verifier_expect}, saw "
                            f"{[(v['authorization'], v['reason']) for v in verifications]}")
        if spec.get("e4"):
            urls = {a for c in calls for a in c["argv"] if "://" in a}
            bad_env = {k for c in calls for k in c["env_keys"]} - ALLOWED_GIT_ENV
            expected_url = setup["origin_url"]
            # The local `git config --file` read has no endpoint; only calls
            # naming a URL reach the network.
            needs_network = verifier_expect != "UNVERIFIABLE:VERIFIER_CONFIG_MISSING"
            ok = (not bad_env and urls <= {expected_url}
                  and (bool(urls) == needs_network)
                  and not any(h in a for c in calls for a in c["argv"] for h in matrix.FORBIDDEN_HOSTS))
            checks["E4_wrapper"] = "ok" if ok else "contradicts"
            if not ok:
                failures.append(f"E4: verifier endpoints {sorted(urls)}, env extras {sorted(bad_env)}")
            sni = out / "netcap-sni.txt"
            if matrix.is_g3(setup["probe"]):
                state, why = g3_capture(sni, setup["origin_url"], selftest)
                checks["E4_os_capture"] = state
                if state == "contradicts":
                    failures.append(f"E4 (G3): {why}")
                elif state == "missing":
                    missing.append(f"E4 OS capture (G3): {why}")
                facts["g3_e4_capture"] = why
            elif sni.exists():
                hosts = {line.strip().lower() for line in sni.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()}
                ok = not any(h.split(":")[0] in hosts for h in matrix.FORBIDDEN_HOSTS)
                checks["E4_os_capture"] = "ok" if ok else "contradicts"
                if not ok:
                    failures.append("E4: the OS capture shows a forbidden host")
            elif selftest:
                checks["E4_os_capture"] = "not required in self-test"
            else:
                missing.append("E4 OS capture (netcap-sni.txt)")

    # F-R2 (C2b charter §17.5): the UNVERIFIABLE-proceed diagnostic must reach a
    # model-bound transcript entry (R1). The hook's stdout (emitted), a
    # `hook_success` attachment (R2), stream-json, stderr and debug logs are not
    # delivery. Every other proceed row is a control: no diagnostic anywhere.
    diag_expect = diagnostic_expectation(spec)
    diagnostic: dict | str = "not_applicable"
    if diag_expect is not None and arm == "headless":
        use_id = facts.get("tool_use_id")
        emitted_for = {e.get("tool_use_id") for e in mine if DIAG_MARKER in (e.get("stdout") or "")}
        transcript = out / "transcript.jsonl"
        sources = [("events", e) for e in jsonl_entries(out / "events.jsonl")] + \
                  [("transcript", e) for e in jsonl_entries(transcript)]
        locations = [{"source": src, "entry_type": entry.get("type"),
                      "attachment_type": (entry.get("attachment") or {}).get("type"),
                      "json_path": path, "text": text,
                      "category": categorise(src, entry, path, use_id, emitted_for)}
                     for src, entry in sources for path, text in strings(entry)
                     if DIAG_MARKER in text]
        facts["host_system"] = host_system([e for s, e in sources if s == "events"])
        facts["transcript_collected"] = transcript.exists()
        diagnostic = {"expected": diag_expect, "user_visible": "not_tested",
                      "locations": [{k: v for k, v in loc.items() if k != "text"}
                                    for loc in locations]}
        if diag_expect == "delivered":
            got = [v for e in mine for v in e.get("verifications", [])]
            reason = got[-1].get("reason") if got else None
            text = diagnostic_text(reason, "mneme_memory_env" in spec["mutate"]) if reason else None
            facts["diagnostic_text_expected"] = text
            want = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": text}}
            entry = next((e for e in mine if e.get("tool_use_id") == use_id), None) \
                or (mine[-1] if mine else None)
            if entry is None or text is None:
                diagnostic["emitted"] = "not_tested"
            else:
                lines = [ln for ln in (entry.get("stdout") or "").splitlines() if ln.strip()]
                try:
                    ok = len(lines) == 1 and json.loads(lines[0]) == want
                except ValueError:
                    ok = False
                diagnostic["emitted"] = "observed" if ok else "contradicted"
                checks["FR2_emitted"] = "ok" if ok else "contradicts"
                if not ok:
                    failures.append("F-R2: hook stdout is not exactly the §17.2 object")
            # §17.5 names the proof: an R1 `hook_additional_context` attachment.
            # Other model-bound entries (a user turn, a tool_result) are recorded
            # in `locations` but never establish delivery.
            bound = [loc for loc in locations if loc["category"] == "model_bound"
                     and loc["attachment_type"] == "hook_additional_context"
                     and text is not None and text in loc["text"]]
            hosted = [loc for loc in locations if loc["category"] == "host_output"]
            other = [loc for loc in locations if loc["category"] == "model_bound"
                     and loc not in bound]
            diagnostic["host_output"] = "observed" if hosted else "not_observed"
            if not transcript.exists():
                diagnostic["model_delivered"] = "not_tested"
                missing.append("F-R2 session transcript")
            elif bound:
                diagnostic["model_delivered"] = "stub_only" if selftest else "observed"
                checks["FR2_model_bound"] = "ok"
            else:
                diagnostic["model_delivered"] = "contradicted"
                checks["FR2_model_bound"] = "contradicts"
                failures.append("F-R2: no R1 hook_additional_context diagnostic"
                                + (" (other model-bound entry only)" if other
                                   else " (host output only)" if hosted else ""))
        else:
            noisy = [e for e in mine if (e.get("stdout") or "").strip()]
            diagnostic["emitted"] = "contradicted" if noisy else "absent"
            checks["FR2_emitted_absent"] = "contradicts" if noisy else "ok"
            if noisy:
                failures.append("F-R2 control: the hook wrote stdout on a non-UNVERIFIABLE proceed")
            if not transcript.exists():
                diagnostic["model_delivered"] = "not_tested"
                missing.append("F-R2 session transcript")
            else:
                diagnostic["model_delivered"] = "contradicted" if locations else "absent"
                checks["FR2_absent"] = "contradicts" if locations else "ok"
                if locations:
                    failures.append("F-R2 control: an availability diagnostic appeared")

    # E7: model pin from the init event (headless only).
    if arm == "headless" and source == "stream-json":
        if model is None:
            missing.append("E7 init model")
        elif not str(model).startswith(model_pin):
            failures.append(f"E7: init model {model!r} is not the pin {model_pin!r}")
        facts["init_model"] = model

    # Q2: user-visible delivery, interactive arm only.
    if arm == "interactive":
        recordings = list(out.glob("recording.*"))
        attestation = out / "operator-attestation.txt"
        if not recordings or not attestation.exists() or not attestation.read_text(encoding="utf-8", errors="replace").strip():
            missing.append("Q2 recording and operator attestation")
        else:
            facts["recording_sha256"] = hashlib.sha256(recordings[0].read_bytes()).hexdigest()
            said = attestation.read_text(encoding="utf-8", errors="replace")
            key = (f"UNEVALUATED: {expect.split(':', 1)[1]}" if expect.startswith("refuse:")
                   else VIOLATION)
            ok = key.lower() in said.lower()
            checks["Q2_user_delivery"] = "ok" if ok else "contradicts"
            if not ok:
                failures.append(f"Q2: the operator attestation does not report {key!r}")

    # T-08 G3 (charter §6): items 1-6, observation kept apart from replay.
    g3 = classify_g3(out, setup, spec, plan, observer, hashes, mine, facts, checks) \
        if matrix.is_g3(setup["probe"]) else None
    if g3 is not None:
        failures.extend(g3.pop("_failures"))
        missing.extend(g3.pop("_missing"))

    # Three delivery levels, never merged into one claim (scope §1, §7):
    # emitted = the hook's own output (E3); model_delivered = the host's
    # tool_result (E2); user_visible = the interactive arm (Q2).
    def level(check: str, stub_note: str | None = None) -> str:
        state = checks.get(check)
        if state is None:
            return "not_tested"
        if state != "ok":
            return "contradicted"
        return stub_note or "observed"
    delivery = {"emitted": level("E3"),
                "model_delivered": level("E2", "stub_only" if selftest else None),
                "user_visible": level("Q2_user_delivery")} \
        if expect.startswith("refuse") or expect == "block" else "not_applicable"

    # Scope Amendment 1: a tool absent from the host's own inventory, with no
    # call made, is N/A. Only the host's init tool list can establish this.
    not_offered = (host_tools is not None and plan["tool"] not in host_tools
                   and not uses)
    facts["host_offers_tool"] = None if host_tools is None else plan["tool"] in host_tools
    if not_offered:
        label = "NOT_OFFERED"
    elif expect == "record":
        label = "RECORDED" if not missing else "EVIDENCE_INCOMPLETE"
    elif deviations:
        label = "PROTOCOL_DEVIATION"
    elif failures:
        label = "FAIL"
    elif missing:
        label = "EVIDENCE_INCOMPLETE"
    else:
        label = "PASS"
    if g3 is not None and not not_offered:
        # Charter §6 labels: any contradiction or deviation is UNEXPECTED (stop,
        # report raw); missing evidence stays EVIDENCE_INCOMPLETE, never a label.
        label = ("UNEXPECTED" if deviations or failures
                 else "EVIDENCE_INCOMPLETE" if missing else spec["g3_label"])
    outcome = {
        "probe": setup["probe"], "tool": setup["tool"], "rep": setup["rep"], "arm": arm,
        "selftest": selftest, "expect": expect, "verifier_expect": verifier_expect,
        "label": label, "delivery": delivery, "diagnostic": diagnostic,
        "checks": checks, "failures": failures, "missing": missing,
        "deviations": deviations, "facts": facts,
    }
    if g3 is not None:
        outcome["g3"] = g3
    (out / "outcome.json").write_text(json.dumps(outcome, indent=2) + "\n", encoding="utf-8")
    print(label)
    return 0


def pair(diag_out: Path, control_out: Path) -> int:
    diag = json.loads((diag_out / "outcome.json").read_text(encoding="utf-8"))
    ctl = json.loads((control_out / "outcome.json").read_text(encoding="utf-8"))
    problems = []
    if diag["tool"] != ctl["tool"]:
        problems.append(f"tools differ: {diag['tool']} vs {ctl['tool']}")
    if not isinstance(diag["diagnostic"], dict) or diag["diagnostic"]["expected"] != "delivered":
        problems.append(f"{diag['probe']} is not a diagnostic row")
    if not isinstance(ctl["diagnostic"], dict) or ctl["diagnostic"]["expected"] != "absent":
        problems.append(f"{ctl['probe']} is not a control row")
    for outcome in (diag, ctl):
        if outcome["label"] != "PASS":
            problems.append(f"{outcome['probe']} {outcome['tool']} {outcome['rep']} is {outcome['label']}")
    a, b = diag["facts"].get("host_system"), ctl["facts"].get("host_system")
    if a is None or b is None:
        problems.append("host_system facts missing")
    else:
        if a["subtypes"] != b["subtypes"]:
            problems.append(f"system subtypes differ: {a['subtypes']} vs {b['subtypes']}")
        if a["indicators"] != b["indicators"]:
            problems.append(f"indicators differ: {a['indicators']} vs {b['indicators']}")
    name = f"{ctl['probe']}-{ctl['tool']}-{ctl['rep']}"
    label = "PAIR_MISMATCH" if problems else "PAIR_OK"
    record = {"diagnostic": f"{diag['probe']}-{diag['tool']}-{diag['rep']}", "control": name,
              "rules": "R3 (#551)", "label": label, "problems": problems}
    (diag_out / f"pair-{name}.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(label)
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--pair"]:
        raise SystemExit(pair(Path(sys.argv[2]), Path(sys.argv[3])))
    raise SystemExit(main())
