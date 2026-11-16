"""Compute the H1 gate (Claude Code) from the accepted, published per-path outcomes.

usage: h1_gate.py <artifacts_dir> [<out_json>]

Gate rule (probe scope section 6, from the charter): H1 passes only when EVERY path is
DELIVERED_TO_AGENT, DELIVERED_TO_USER_ONLY or EVIDENCE_REUSED. Charter section 5 (A2-1):
one gate's paths share one pin, so every path must also record the same host version.

Inputs (accepted records only; nothing is classified here):
  H1a-edit, H1a-bash, H1b-start: live-a2-2026-11-11/<path>/outcome.r1r5.json  (A2 under R1-R5, #800)
  H1c:                           live-a3-2026-11-16/outcome_a1.r1r6.json      (A3 under R1-R6, #807;
                                 screenshot evidence accepted by the owner, record section 8.3)
Fail-closed: a missing file, a missing label or version, or any other label is NOT MET.
"""
import hashlib
import json
import sys
from pathlib import Path

PASSING = ("DELIVERED_TO_AGENT", "DELIVERED_TO_USER_ONLY", "EVIDENCE_REUSED")
INPUTS = {
    "H1a-edit": "live-a2-2026-11-11/H1a-edit/outcome.r1r5.json",
    "H1a-bash": "live-a2-2026-11-11/H1a-bash/outcome.r1r5.json",
    "H1b-start": "live-a2-2026-11-11/H1b-start/outcome.r1r5.json",
    "H1c": "live-a3-2026-11-16/outcome_a1.r1r6.json",
}


def path_record(art, path_id, rel):
    p = Path(art) / rel
    if not p.is_file():
        return {"path": path_id, "file": rel, "problem": "outcome file missing"}
    o = json.loads(p.read_text(encoding="utf-8"))
    version = o.get("host_version") or (o.get("observer") or {}).get("claude_version")
    return {"path": path_id, "file": rel, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "label": o.get("label"), "rules": o.get("rules"), "host_version": version}


def gate(records):
    problems = []
    for r in records:
        if r.get("problem"):
            problems.append(f"{r['path']}: {r['problem']}")
        elif r.get("label") not in PASSING:
            problems.append(f"{r['path']}: label {r.get('label')!r} does not pass")
        if not r.get("problem") and not r.get("host_version"):
            problems.append(f"{r['path']}: host version unrecorded")
    versions = {r.get("host_version") for r in records if r.get("host_version")}
    if len(versions) > 1:
        problems.append("host versions differ: " + ", ".join(sorted(versions)))
    if {r["path"] for r in records} != set(INPUTS):
        problems.append("not every H1 path is included")
    return {"gate": "H1", "result": "PASS" if not problems else "NOT MET", "problems": problems,
            "host_version": versions.pop() if len(versions) == 1 else None, "paths": records,
            "rule": "every path DELIVERED_TO_AGENT, DELIVERED_TO_USER_ONLY or EVIDENCE_REUSED, on one host version"}


def main(argv):
    art = Path(argv[1])
    res = gate([path_record(art, k, v) for k, v in INPUTS.items()])
    text = json.dumps(res, indent=2) + "\n"
    if len(argv) > 2:
        out = Path(argv[2])
        if out.exists():
            raise SystemExit(f"refusing to overwrite {out}")
        out.write_text(text, encoding="utf-8", newline="\n")
    print(f"H1 gate: {res['result']}" + ("" if not res["problems"] else " | " + "; ".join(res["problems"])))
    return 0 if res["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
