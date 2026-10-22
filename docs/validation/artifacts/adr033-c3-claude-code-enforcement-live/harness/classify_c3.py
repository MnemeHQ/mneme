"""Classify one C3 probe against its matrix row (scope #592 §§5-6).

usage: classify_c3.py <out-dir> <model-pin>

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
    for path in files:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
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
            if sni.exists():
                hosts = {line.strip().lower() for line in sni.read_text().splitlines() if line.strip()}
                ok = not any(h.split(":")[0] in hosts for h in matrix.FORBIDDEN_HOSTS)
                checks["E4_os_capture"] = "ok" if ok else "contradicts"
                if not ok:
                    failures.append("E4: the OS capture shows a forbidden host")
            elif selftest:
                checks["E4_os_capture"] = "not required in self-test"
            else:
                missing.append("E4 OS capture (netcap-sni.txt)")

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
        if not recordings or not attestation.exists() or not attestation.read_text().strip():
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
    outcome = {
        "probe": setup["probe"], "tool": setup["tool"], "rep": setup["rep"], "arm": arm,
        "selftest": selftest, "expect": expect, "verifier_expect": verifier_expect,
        "label": label, "delivery": delivery,
        "checks": checks, "failures": failures, "missing": missing,
        "deviations": deviations, "facts": facts,
    }
    (out / "outcome.json").write_text(json.dumps(outcome, indent=2) + "\n", encoding="utf-8")
    print(label)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
