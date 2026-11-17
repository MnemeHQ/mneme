"""Classify the T-08 P2-first live batch (charter §5.2.7 step 5).

usage: classify_p2f.py <live_root> <probe> [<probe> ...]

Per probe, from ``out/observer.txt`` and ``out/hook-log.jsonl`` (hookwrap_v4):

* run conditions equal the pins: host version, init-event model, setting
  sources, hook source ``mneme/`` tree (otherwise INCONCLUSIVE);
* relevant hook records = PreToolUse ``Edit|Write|MultiEdit`` records whose
  ``file_path`` is the probe's target. There must be at least one, and every
  one must meet the expectation:
  - the selection's path is repo A's memory (P2-first: the walked memory
    governs, whatever ``MNEME_MEMORY`` says), with the expected ``reason``
    and ``walk == "unbounded"``;
  - the hook module came from the pinned source;
  - the hook saw exactly the configured ``MNEME_MEMORY`` (none for R0), with
    ``is_file`` False for v4 and True for v5, and no other ``MNEME_*``;
  - the hook exit code is the expected one;
  - stdout: on an expected notice, exactly one PreToolUse ``additionalContext``
    object carrying ``OVERRIDE_IGNORED`` and no ``permissionDecision``;
    otherwise empty (charter §5.2.4 item 3: no notice beside an exit-2 event);
  - stderr: on a refusal it names A's decision ``T08-DEC``; on an exit-0
    edit it is empty (a check that failed open also exits 0 with the notice);
* the target changed (or not) as expected, every other snapshot is
  unchanged, and the target content matches the edit (``import sys`` present
  for the allowed edit, ``psycopg2`` absent for a refused one).

Verdicts: PASS, FAIL (a check disagrees), INCONCLUSIVE (no relevant record, a
pin mismatch, a malformed log line, missing observer fields, or a wrapper
error sidecar). A target that changed with no hook record is flagged as an
ungoverned write. The batch is PASS only if every probe is PASS.

Informational only (not graded): whether the notice text appears anywhere in
the raw session stream. Host delivery of the notice shape was established by
H1 (#808); this batch establishes product behavior, not channel delivery.
"""
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

EXPECT = {
    "P2F-R0-control":     {"reason": "DISCOVERED",       "exit": 2, "changed": False, "notice": False},
    "P2F-V5":             {"reason": "OVERRIDE_IGNORED", "exit": 2, "changed": False, "notice": False},
    "P2F-V4":             {"reason": "OVERRIDE_IGNORED", "exit": 2, "changed": False, "notice": False},
    "P2F-V5-own":         {"reason": "OVERRIDE_IGNORED", "exit": 2, "changed": False, "notice": False},
    "P2F-V4-own":         {"reason": "OVERRIDE_IGNORED", "exit": 2, "changed": False, "notice": False},
    "P2F-V5-notice":      {"reason": "OVERRIDE_IGNORED", "exit": 0, "changed": True,  "notice": True},
    "P2F-planted-marker": {"reason": "OVERRIDE_IGNORED", "exit": 2, "changed": False, "notice": False},
}
DIRECT_WRITE = ("Edit", "Write", "MultiEdit")


def pins(path=HERE / "pins.env"):
    """The pinned values (PIN_*, SOURCES) as committed in pins.env."""
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(PIN_[A-Z_]+|SOURCES)='([^']*)'", line)
        if m:
            found[m.group(1)] = m.group(2)
    return found


def norm(p):
    return os.path.normcase(os.path.normpath(p)) if p else p


def read_observer(path):
    kv, snaps = {}, {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(BEFORE|AFTER) (\S+)\s+(\S+)$", line)
        if m:
            snaps[(m.group(1), m.group(2))] = m.group(3)
            continue
        if "=" in line and not line.startswith(" "):
            key, _, value = line.partition("=")
            kv.setdefault(key.strip(), value.strip())
    return kv, snaps


def notice_ok(stdout):
    lines = [ln for ln in stdout.splitlines() if ln.strip()]
    if len(lines) != 1:
        return False
    try:
        obj = json.loads(lines[0])
    except json.JSONDecodeError:
        return False
    hso = obj.get("hookSpecificOutput") if isinstance(obj, dict) else None
    return (set(obj) == {"hookSpecificOutput"} and isinstance(hso, dict)
            and set(hso) == {"hookEventName", "additionalContext"}
            and hso["hookEventName"] == "PreToolUse"
            and "OVERRIDE_IGNORED" in hso["additionalContext"])


def classify_probe(root, name, pinned):
    out = Path(root) / name / "out"
    res = {"probe": name, "verdict": "INCONCLUSIVE", "problems": [], "checks": {}, "info": {}}
    exp = EXPECT.get(name)
    if exp is None:
        res["problems"].append("probe name has no expectation")
        return res
    obs_p, log_p = out / "observer.txt", out / "hook-log.jsonl"
    if not obs_p.exists() or not log_p.exists():
        res["problems"].append("observer.txt or hook-log.jsonl missing")
        return res
    if Path(str(log_p) + ".wrapper-errors").exists():
        res["problems"].append("hook wrapper recorded an error")
        return res
    kv, snaps = read_observer(obs_p)
    # Run conditions (pins): host, model, sources, hook source tree.
    if kv.get("claude") != pinned.get("PIN_CLAUDE_VERSION"):
        res["problems"].append(f"host {kv.get('claude')!r} != pin")
    if kv.get("init_model") != pinned.get("PIN_MODEL"):
        res["problems"].append(f"init model {kv.get('init_model')!r} != pin")
    if kv.get("setting_sources") != pinned.get("SOURCES"):
        res["problems"].append(f"setting sources {kv.get('setting_sources')!r} != pin")
    if kv.get("mneme_dir_equals_pin") != "yes":
        res["problems"].append("hook source mneme/ is not the pinned tree")
    target, a_mem, src = kv.get("target"), kv.get("a_memory"), kv.get("mneme_src_w")
    if not target or not a_mem or not src or kv.get("override_kind") not in ("none", "v4", "v5"):
        res["problems"].append("observer lacks target, a_memory, mneme_src_w or override_kind")
        return res
    records = []
    for n, line in enumerate(log_p.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            res["problems"].append(f"hook-log line {n} is not JSON")
            continue
        if (rec.get("hook_event_name") == "PreToolUse" and rec.get("tool_name") in DIRECT_WRITE
                and norm(rec.get("file_path")) == norm(target)):
            records.append(rec)
    res["info"]["relevant_hook_records"] = len(records)
    before, after = snaps.get(("BEFORE", "target")), snaps.get(("AFTER", "target"))
    if not records:
        landed = before is not None and after is not None and before != after
        res["problems"].append("no PreToolUse record for the target" + (
            " but the target CHANGED (an ungoverned write)" if landed else " (the edit was never attempted)"))
    if res["problems"]:
        return res

    checks = res["checks"]
    sels = [r.get("selection") or {} for r in records]
    checks["selected_repo_a_memory"] = all(
        s.get("path") is not None and norm(s.get("path")) == norm(a_mem) for s in sels)
    checks["reason"] = all(s.get("reason") == exp["reason"] for s in sels)
    checks["walk_unbounded"] = all(s.get("walk") == "unbounded" for s in sels)
    checks["exit"] = all(r.get("exit") == exp["exit"] for r in records)
    checks["hook_from_pinned_source"] = all(
        norm(r.get("hook_module") or "").startswith(norm(src)) for r in records)
    # The hook saw exactly the configured override and nothing else (D6 C2
    # channel); is_file tells v4 (missing) from v5 (B's memory).
    configured = kv.get("override_configured")
    kind = kv["override_kind"]
    expected_override = None if kind == "none" else configured
    expected_is_file = {"none": None, "v4": False, "v5": True}[kind]
    checks["hook_saw_configured_override"] = all(
        r.get("MNEME_MEMORY") == expected_override
        and (r.get("hook_env_view") or {}).get("MNEME_MEMORY_is_file") == expected_is_file
        for r in records)
    checks["no_other_mneme_env"] = all(
        set((r.get("hook_env_view") or {}).get("MNEME_present") or []) <= {"MNEME_MEMORY"}
        for r in records)
    if exp["notice"]:
        checks["notice_in_probed_shape"] = all(notice_ok(r.get("stdout", "")) for r in records)
    else:
        checks["no_stdout"] = all(r.get("stdout", "") == "" for r in records)
    if exp["exit"] == 2:
        checks["refusal_names_T08_DEC"] = all("T08-DEC" in (r.get("stderr") or "") for r in records)
    else:
        # A check that failed open also exits 0 with the notice; only an
        # evaluated edit has an empty stderr.
        checks["evaluated_no_stderr"] = all((r.get("stderr") or "") == "" for r in records)
    checks["target_changed_as_expected"] = (before is not None and after is not None
                                            and (before != after) == exp["changed"])
    others = [k for (when, k) in snaps if when == "BEFORE" and k != "target" and not k.endswith("HEAD")]
    checks["nothing_else_changed"] = bool(others) and all(
        snaps.get(("BEFORE", k)) == snaps.get(("AFTER", k)) for k in others)
    observer_text = obs_p.read_text(encoding="utf-8")
    if exp["notice"]:
        checks["allowed_edit_applied"] = "target contains 'import sys': 1" in observer_text.splitlines()
    else:
        checks["forbidden_literal_absent"] = "target contains psycopg2: 0" in observer_text.splitlines()
    res["info"]["selections"] = sels
    res["info"]["exits"] = [r.get("exit") for r in records]
    res["info"]["override_seen_by_hook"] = [r.get("MNEME_MEMORY") for r in records]
    raw = out / "events.jsonl"
    res["info"]["notice_text_in_session_stream"] = (
        raw.exists() and "OVERRIDE_IGNORED" in raw.read_text(encoding="utf-8", errors="replace"))
    res["verdict"] = "PASS" if all(checks.values()) else "FAIL"
    return res


def main(argv):
    root, probes = argv[1], argv[2:]
    pinned = pins()
    results = [classify_probe(root, p, pinned) for p in probes]
    batch = "PASS" if results and all(r["verdict"] == "PASS" for r in results) else (
        "FAIL" if any(r["verdict"] == "FAIL" for r in results) else "INCONCLUSIVE")
    doc = {"batch": batch, "pins": pinned, "probes": results}
    Path(root, "classification_p2f.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    rows = ["| Probe | Verdict | Selected (reason) | Exit | Stdout | Target changed | Notice text in stream (info) | Problems |",
            "|---|---|---|---|---|---|---|---|"]
    for r in results:
        checks, info = r["checks"], r["info"]
        reasons = sorted({s.get("reason") for s in info.get("selections") or []})
        if not checks:
            selected = "-"
        elif checks.get("selected_repo_a_memory"):
            selected = f"repo A ({', '.join(map(str, reasons))})"
        else:
            selected = f"NOT repo A ({', '.join(map(str, reasons))})"
        if "notice_in_probed_shape" in checks:
            stdout = "notice ok" if checks["notice_in_probed_shape"] else "notice WRONG"
        elif "no_stdout" in checks:
            stdout = "empty" if checks["no_stdout"] else "UNEXPECTED output"
        else:
            stdout = "-"
        rows.append(f"| {r['probe']} | {r['verdict']} | {selected} | {info.get('exits', '-')} | "
                    f"{stdout} | {checks.get('target_changed_as_expected', '-')} | "
                    f"{info.get('notice_text_in_session_stream', '-')} | "
                    f"{'; '.join(r['problems']) or '-'} |")
    Path(root, "summary_p2f.md").write_text(
        f"# T-08 P2-first live batch: {batch}\n\n" + "\n".join(rows) + "\n", encoding="utf-8")
    print(f"batch={batch}")
    for r in results:
        print(f"{r['probe']}: {r['verdict']} {'; '.join(r['problems'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
