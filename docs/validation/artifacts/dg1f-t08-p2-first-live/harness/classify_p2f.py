"""Classify the T-08 P2-first live batch (charter §5.2.7 step 5).

usage: classify_p2f.py <live_root> <probe> [<probe> ...]

Per probe, from ``out/observer.txt`` and ``out/hook-log.jsonl`` (hookwrap_v4):

* relevant hook records = PreToolUse ``Edit|Write|MultiEdit`` records whose
  ``file_path`` is the probe's target. There must be at least one, and every
  one must meet the expectation:
  - the selection's path is repo A's memory (P2-first: the walked memory
    governs, whatever ``MNEME_MEMORY`` says) and its ``reason`` is the
    expected one;
  - the hook exit code is the expected one;
  - stdout: on an expected notice, exactly one PreToolUse ``additionalContext``
    object carrying ``OVERRIDE_IGNORED`` and no ``permissionDecision``;
    otherwise empty (charter §5.2.4 item 3: no notice beside an exit-2 event);
  - on an expected refusal, stderr names A's decision ``T08-DEC``.
* the target file changed (or not) as expected, from the BEFORE/AFTER hashes;
* the host version and the init-event model equal the pins.

Verdicts: PASS, FAIL (a check disagrees), INCONCLUSIVE (no relevant record,
a pin mismatch, a missing file, or a wrapper error sidecar). The batch is PASS
only if every probe is PASS.

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
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(PIN_[A-Z_]+)='([^']*)'", line)
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
    if kv.get("claude") != pinned.get("PIN_CLAUDE_VERSION"):
        res["problems"].append(f"host {kv.get('claude')!r} != pin")
    if kv.get("init_model") != pinned.get("PIN_MODEL"):
        res["problems"].append(f"init model {kv.get('init_model')!r} != pin")
    if kv.get("SELFTEST") or "SELFTEST=1" in obs_p.read_text(encoding="utf-8"):
        res["problems"].append("self-test run (stub claude): not live evidence")
    target, a_mem = kv.get("target"), kv.get("a_memory")
    records = []
    for line in log_p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            if (rec.get("hook_event_name") == "PreToolUse" and rec.get("tool_name") in DIRECT_WRITE
                    and norm(rec.get("file_path")) == norm(target)):
                records.append(rec)
    res["info"]["relevant_hook_records"] = len(records)
    if not records:
        res["problems"].append("no PreToolUse record for the target (the edit was never attempted)")
    if res["problems"]:
        return res

    checks = res["checks"]
    sels = [r.get("selection") or {} for r in records]
    checks["selected_repo_a_memory"] = all(norm(s.get("path")) == norm(a_mem) for s in sels)
    checks["reason"] = all(s.get("reason") == exp["reason"] for s in sels)
    checks["walk_unbounded"] = all(s.get("walk") == "unbounded" for s in sels)
    checks["exit"] = all(r.get("exit") == exp["exit"] for r in records)
    if exp["notice"]:
        checks["notice_in_probed_shape"] = all(notice_ok(r.get("stdout", "")) for r in records)
    else:
        checks["no_stdout"] = all(r.get("stdout", "") == "" for r in records)
    if exp["exit"] == 2:
        checks["refusal_names_T08_DEC"] = all("T08-DEC" in (r.get("stderr") or "") for r in records)
    before, after = snaps.get(("BEFORE", "target")), snaps.get(("AFTER", "target"))
    checks["target_changed_as_expected"] = (before is not None and after is not None
                                            and (before != after) == exp["changed"])
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
