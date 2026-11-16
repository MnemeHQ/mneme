"""Offline reclassification of the Amendment A3 headless pair under rules R1-R6 (#805, #806).

usage: reclassify_a3.py <archive_dir> <archive_sums> <published_dir> <python_exe> <claude_bin>

No host session runs. Nothing in the archive or in the as-run published files is
modified. It follows #553, #563 and #800, and reuses reclassify_a2.py's integrity,
completeness and fail-closed publication helpers unchanged:

1. Integrity. <archive_sums> must verify against <archive_dir> with no unlisted file;
   every raw file and batch file with a MANIFEST.json `.raw` entry must match (#804).
   Any mismatch aborts before classification.
2. Authoritative run. classify_a1.headless() (rules R1-R6) on the archived RAW headless
   pair, with the A3 pins (Claude Code '2.1.310 (Claude Code)', model 'claude-opus-5-5').
   Each arm is read from the archive but keyed to its recorded live-root location, so
   workspace masking matches the as-run classification (the #800 lesson).
3. Combine. classify_a1.combine() of that headless outcome with the UNCHANGED as-run
   interactive outcome (R6 does not touch the interactive classifier). The interactive
   label stays as run; whether its screenshot capture is accepted is a separate decision
   (#804 section 2.1) and is not made here.
4. Omitted-material completeness check, per headless arm (each arm's own nonce and the
   emitter's): every raw event, transcript entry and stderr line is compared with what
   collect_a3.py publishes (the same selection as collect_a2). Any omitted occurrence
   makes the result PENDING_REVIEW and withholds both outcome files (exit 3).
5. Subset replay of the published headless subset: supporting only.

Writes, next to the unchanged as-run files (refuses to overwrite; staged and published
only after the archive re-verifies):
  <published_dir>/outcome_a1_headless.r1r6.json
  <published_dir>/outcome_a1.r1r6.json
  <published_dir>/reclassification.json
"""
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = ("H1c-sm", "H1c-sm-ctl")
PIN_MODEL = "claude-opus-5-5"
PIN_VERSION = "2.1.310 (Claude Code)"
LIVE_ROOT = r"C:\dev\d5p2-h1c-a3-live"
LIVE_PROJECT = re.compile(re.escape("C--dev-d5p2-h1c-a3-live"), re.I)
PENDING = "PENDING_REVIEW"


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


A2 = load("reclassify_a2")   # verify, completeness, publish, changes (#800)
A1 = load("classify_a1")     # headless, combine; its own classify_h1 instance (R1-R6)
R = A2.R


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def headless_recorded(archive):
    """classify_a1.headless on the archive, each arm keyed to its recorded live location."""
    arms = {}
    for a in ARMS:
        arm = A1.C.load_arm(Path(archive) / a / "out")
        arm["out"] = Path(LIVE_ROOT) / a / "out"
        arms[a] = arm
    orig = A1.C.load_arm
    A1.C.load_arm = lambda out: arms[Path(out).parent.name]
    try:
        return A1.headless(archive, PIN_MODEL, PIN_VERSION)
    finally:
        A1.C.load_arm = orig


def status(hits):
    return PENDING if hits else "COMPLETE"


def main(argv):
    archive, sums, pub, py, cbin = Path(argv[1]), Path(argv[2]), Path(argv[3]), argv[4], argv[5]
    out_h, out_c, out_s = pub / "outcome_a1_headless.r1r6.json", pub / "outcome_a1.r1r6.json", pub / "reclassification.json"
    if any(p.exists() for p in (out_h, out_c, out_s)):
        raise SystemExit("refusing to overwrite existing reclassification output")
    manifest = json.loads((pub / "MANIFEST.json").read_text(encoding="utf-8"))
    sums_before = sha(sums)
    integrity = A2.verify(archive, sums, manifest)
    if integrity["problems"]:
        print(json.dumps(integrity, indent=2))
        raise SystemExit("integrity check failed; nothing classified")

    red = A2.redactor(archive, py, cbin)
    red_live = A2.redactor(LIVE_ROOT, py, cbin)
    for r_ in (red, red_live):
        r_.subs = [(LIVE_PROJECT, "<LIVE_PROJECT>")] + r_.subs

    h = headless_recorded(archive)
    as_run_h = json.loads((archive / "outcome_a1_headless.json").read_text(encoding="utf-8"))
    i = json.loads((archive / "outcome_a1_interactive.json").read_text(encoding="utf-8"))
    as_run_c = json.loads((archive / "outcome_a1.json").read_text(encoding="utf-8"))
    c = A1.combine(h, i)
    sub = A1.C.classify(R.subset_arm(pub, "H1c-sm"), R.subset_arm(pub, "H1c-sm-ctl"), "H1c-sm", PIN_MODEL, PIN_VERSION)

    emit_nonce = (archive / "H1c-sm" / "out" / "nonce.txt").read_text(encoding="utf-8").strip()
    comp = {}
    for arm in ARMS:
        own = (archive / arm / "out" / "nonce.txt").read_text(encoding="utf-8").strip()
        cc = A2.completeness(archive, arm, sorted({emit_nonce, own}), own, red_live)
        cc["omitted_hits"] = [red.obj(red_live.obj(x)) for x in cc["omitted_hits"]]
        comp[arm] = cc
    hits = sum(x["hits_total"] for x in comp.values())
    pending = status(hits) == PENDING

    pub_h, pub_c = red.obj(red_live.obj(h)), red.obj(red_live.obj(c))
    summary = {
        "rules": A1.C.RULES_ID, "a1_rules": A1.A1_ID,
        "pins": {"claude_version": PIN_VERSION, "model": PIN_MODEL},
        "tool_sha256": {"reclassify_a3.py": sha(Path(__file__)), "classify_h1.py": sha(HERE / "classify_h1.py"),
                        "classify_a1.py": sha(HERE / "classify_a1.py"),
                        "reclassify_a2.py (helpers)": sha(HERE / "reclassify_a2.py"),
                        "collect_a3.py (selection)": sha(HERE / "collect_a3.py")},
        "integrity": integrity,
        "headless": {"label_as_run": as_run_h["label"], "label_r1r6_raw": h["label"],
                     "label_r1r6_subset": sub["label"], "raw_and_subset_agree": h["label"] == sub["label"],
                     "reasons_r1r6_raw": h.get("reasons"), "reasons_r1r6_subset": sub.get("reasons"),
                     "r6_excluded": (h.get("host_events") or {}).get("r6_excluded"),
                     "host_interference": (h.get("a1") or {}).get("host_interference"),
                     "changes_from_as_run": A2.changes(as_run_h, pub_h)},
        "interactive": {"label": i["label"], "reclassified": False,
                        "note": ("Unchanged as-run outcome (R6 does not touch the interactive classifier). "
                                 "It is not an accepted protocol-compliant pass until the screenshot evidence "
                                 "decision (#804 section 2.1).")},
        "combined": {"label_as_run": as_run_c["label"], "label_r1r6": c["label"], "reasons": c.get("reasons"),
                     "host_version": c.get("host_version"), "h1c_passes_under_a1": c.get("h1c_passes_under_a1"),
                     "note": ("As classified. Counts as an accepted H1c pass only if the screenshot evidence "
                              "decision accepts the interactive capture. The H1 gate is a separate record.")},
        "completeness": comp, "omitted_material_nonce_hits": hits, "status": status(hits),
        "publication": {"rule": "With any omitted nonce hit the outcome files are withheld (PENDING_REVIEW).",
                        "outcome_files_published": not pending},
        "subset_note": "Subset replay is supporting only; it is not an independent reproduction.",
    }
    integrity_after = A2.verify(archive, sums, manifest)
    summary["integrity_after"] = {"problems": integrity_after["problems"], "archive_sums_unchanged": sha(sums) == sums_before}
    if integrity_after["problems"] or sha(sums) != sums_before:
        raise SystemExit("archive changed during reclassification; nothing published")

    def gate():
        again = A2.verify(archive, sums, manifest)
        return again["problems"] + ([] if sha(sums) == sums_before else ["archive SHA256SUMS changed"])

    files = {} if pending else {out_h: json.dumps(pub_h, indent=2) + "\n", out_c: json.dumps(pub_c, indent=2) + "\n"}
    files[out_s] = json.dumps(summary, indent=2) + "\n"
    A2.publish(files, red, gate)
    print("headless:", as_run_h["label"], "->", h["label"], "| subset", sub["label"], "| r6_excluded",
          summary["headless"]["r6_excluded"], "| omitted hits", hits)
    print("combined:", as_run_c["label"], "->", c["label"], "| reasons", c.get("reasons"), "| host", c.get("host_version"))
    return 3 if pending else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
