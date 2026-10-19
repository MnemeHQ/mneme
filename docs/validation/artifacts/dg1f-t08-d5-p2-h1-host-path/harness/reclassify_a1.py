"""Offline reclassification of the A1-headless live evidence under rules R1-R4 (#561, #562).

usage: reclassify_a1.py <archive_dir> <archive_sums> <published_dir> <python_exe> <claude_bin>

No host session runs. Nothing in the archive or in the as-run published files is
modified. This follows the #553 procedure (reclassify_h1.py), whose integrity,
completeness and subset-replay helpers it reuses unchanged:

1. Integrity. <archive_sums> (sha256sum format) must verify against <archive_dir>
   with no unlisted file, every raw file in the #560 <published_dir>/MANIFEST.json
   `raw_not_published` entries must match its SHA-256 and size, and every batch
   file with a `<name>.raw` entry must match too. Any mismatch aborts (exit 1)
   before classification.
2. Authoritative run. The merged classify_a1.headless() (rules R1-R4 through
   classify_h1) runs on the archived RAW evidence.
3. Completeness check (per-entry collector diff, reclassify_h1.completeness) for
   both arms' events.jsonl and transcript.jsonl, plus a nonce scan of each arm's
   claude.stderr.txt. Every omitted hit is published, redacted.
4. Subset replay (supporting only). The same headless() runs on the published
   selected evidence. It is NOT an independent reproduction: it depends on the
   raw completeness check. A difference from step 2 is reported, never reconciled.

Writes, next to the unchanged as-run files:
  <published_dir>/outcome_a1_headless.r1r4.json  authoritative raw-run outcome (redacted)
  <published_dir>/reclassification.json          integrity, labels (as-run, raw, subset),
                                                 completeness, classifier and tool hashes
Refuses to overwrite either.
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = ("H1c-sm", "H1c-sm-ctl")
PIN_MODEL = "claude-opus-4-8[1m]"
LIVE_ROOT = r"C:\dev\d5p2-h1c-a1-live"


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


A1 = load("classify_a1")
R = load("reclassify_h1")
COL = R.COL


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def verify(archive, sums, manifest):
    res = R.verify(archive, sums, manifest)  # archive sums, unlisted files, per-arm raw files
    for key, meta in manifest["batch"].items():
        if not key.endswith(".raw") or meta is None:
            continue
        name = key[:-len(".raw")]
        p = archive / name
        res["manifest_raw_files_checked"] += 1
        if not p.is_file() or sha(p) != meta["sha256"] or p.stat().st_size != meta["bytes"]:
            res["problems"].append(f"{name}: does not match #560 MANIFEST")
    return res


def headless_on(arms):
    """Run classify_a1.headless() on in-memory arms (subset replay), unchanged logic."""
    orig = A1.C.load_arm
    A1.C.load_arm = lambda out: arms[Path(out).parent.name]
    try:
        return A1.headless(Path("<SUBSET>"), PIN_MODEL)
    finally:
        A1.C.load_arm = orig


def main(argv):
    archive, sums, pub, py, cbin = Path(argv[1]), Path(argv[2]), Path(argv[3]), argv[4], argv[5]
    out_path, summary_path = pub / "outcome_a1_headless.r1r4.json", pub / "reclassification.json"
    if out_path.exists() or summary_path.exists():
        raise SystemExit("refusing to overwrite existing reclassification output")
    manifest = json.loads((pub / "MANIFEST.json").read_text(encoding="utf-8"))
    integrity = verify(archive, sums, manifest)
    if integrity["problems"]:
        print(json.dumps(integrity, indent=2))
        raise SystemExit("integrity check failed; nothing classified")

    red = COL.Redactor(archive, HERE, py, cbin)       # archive root -> <LIVE>
    red_live = COL.Redactor(Path(LIVE_ROOT), HERE, py, cbin)  # original live root -> <LIVE>
    as_run = json.loads((pub / "outcome_a1_headless.json").read_text(encoding="utf-8"))

    raw = A1.headless(archive, PIN_MODEL)
    sub = headless_on({a: R.subset_arm(pub, a) for a in ARMS})
    nonce = A1.C.load_arm(archive / "H1c-sm" / "out")["nonce"]
    comp = {}
    for arm in ARMS:
        c = R.completeness(archive, arm, nonce, red_live)
        c["omitted_hits"] = [red.obj(red_live.obj(h)) for h in c["omitted_hits"]]
        err = archive / arm / "out" / "claude.stderr.txt"
        c["stderr"] = {"bytes": err.stat().st_size if err.exists() else None,
                       "nonce_occurrences": err.read_text(encoding="utf-8", errors="replace").count(nonce)
                       if err.exists() else None}
        comp[arm] = c

    COL.write_text(out_path, json.dumps(red.obj(red_live.obj(raw)), indent=2) + "\n", red, {})
    stderr_hits = sum(c["stderr"]["nonce_occurrences"] or 0 for c in comp.values())
    summary = {
        "rules": A1.C.RULES_ID, "a1_rules": A1.A1_ID,
        "classifier_sha256": {"classify_h1.py": sha(HERE / "classify_h1.py"),
                              "classify_a1.py": sha(HERE / "classify_a1.py")},
        "reclassify_tool_sha256": {"reclassify_a1.py": sha(Path(__file__)),
                                   "reclassify_h1.py (helpers)": sha(HERE / "reclassify_h1.py"),
                                   "collect_h1.py (selection)": sha(HERE / "collect_h1.py")},
        "integrity": integrity,
        "label_as_run": as_run["label"], "label_r1r4_raw": raw["label"], "label_r1r4_subset": sub["label"],
        "raw_and_subset_agree": raw["label"] == sub["label"],
        "reasons_r1r4_raw": raw.get("reasons"), "reasons_r1r4_subset": sub.get("reasons"),
        "host_interference_as_run": (as_run.get("a1") or {}).get("host_interference"),
        "host_interference_r1r4_raw": raw["a1"]["host_interference"],
        "nonce_categories_r1r4_raw": sorted({(l["json_path"], l["category"]) for l in raw["nonce_locations"]}),
        "completeness": comp,
        "omitted_material_nonce_hits": sum(c["hits_total"] for c in comp.values()) + stderr_hits,
        "subset_note": ("Subset replay is a supporting check against the published subset only; "
                        "it depends on the raw completeness check and is not an independent reproduction."),
        "h1_gate": "NOT MET (H1c under A1 also needs the A1-interactive run; not run)",
    }
    COL.write_text(summary_path, json.dumps(summary, indent=2) + "\n", red, {})
    print("A1-headless", summary["label_as_run"], "->", summary["label_r1r4_raw"],
          "| subset", summary["label_r1r4_subset"],
          "| interference", summary["host_interference_r1r4_raw"],
          "| omitted-material hits", summary["omitted_material_nonce_hits"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
