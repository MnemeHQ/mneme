"""Offline reclassification of the Amendment A2 live evidence under rules R1-R5 (#796, #798).

usage: reclassify_a2.py <archive_dir> <archive_sums> <published_dir> <python_exe> <claude_bin>

No host session runs. Nothing in the archive or in the as-run published files is
modified. This is step 2 of the R5 rule note's section 7
(docs/plans/2026-11-11-dg1f-t08-d5-p2-a2-r5-host-record-rule.md) and follows the
#553 / #563 procedure (reclassify_h1.py, reclassify_a1.py):

1. Integrity. <archive_sums> (sha256sum format) must verify against <archive_dir>
   with no unlisted file. Every raw file in the #795 <published_dir>/MANIFEST.json
   `raw_not_published` entries must match its SHA-256 and size, and so must every
   batch file with a `<name>.raw` entry. Any mismatch aborts (exit 1) before
   classification.
2. Authoritative run. The merged classify_h1.classify() (rules R1-R5) runs on the
   archived RAW evidence for each A2 path and its control, with the A2 pins
   (Claude Code '2.1.310 (Claude Code)', model 'claude-opus-5-5'). Each arm is read
   from the archive but keyed to its recorded live-root location, so workspace
   masking matches the as-run classification (load_recorded).
3. Omitted-material completeness check. For every arm, EVERY raw entry of
   events.jsonl and transcript.jsonl is compared with exactly what the #795
   collector publishes for it: collect_h1.select_events for events, and
   collect_a2.select_transcript_a2 (hook_* entries with `rendered`, nonce-line
   api-request-blob excerpts) for the transcript, then the collector's
   key-dropping redaction. An entry is `dropped`, `trimmed` or `whole`. Each arm
   is scanned for its own nonce and for the paired emitter's nonce. A nonce counts
   as omitted when the raw entry holds more occurrences than its published form.
   Each arm's claude.stderr.txt is scanned too. An omitted hit is published as its
   location only (source, line, entry type, JSON paths, counts), never the entry:
   unpublished 2.1.310 entries can carry environment details.
4. Subset replay (supporting only). The same classifier runs on the published
   selected evidence. It is NOT an independent reproduction: it depends on the raw
   completeness check. A difference from step 2 is reported, never reconciled.

Writes, next to the unchanged as-run files:
  <published_dir>/<path>/outcome.r1r5.json   authoritative raw-run outcome (redacted)
  <published_dir>/reclassification.json      integrity, labels (as-run, raw, subset),
                                              completeness, classifier and tool hashes
Refuses to overwrite either.
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATHS = ("H1a-edit", "H1a-bash", "H1b-start")
PIN_MODEL = "claude-opus-5-5"
PIN_VERSION = "2.1.310 (Claude Code)"
LIVE_ROOT = r"C:\dev\d5p2-h1-a2-live"


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


R = load("reclassify_h1")
C = R.C
COL = R.COL
A2C = load("collect_a2")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_recorded(archive, arm):
    """Load an arm from the archive, keyed to the location it was RECORDED at.

    Content is read from the archive. `out` is set to the live-root location the
    run used, because the recorded tool inputs name that workspace and
    classify_h1.masked() masks the arm's workspace by `out`. Keyed to the archive
    path, identical Read/Edit requests in the two arms would not mask and would
    look non-equivalent. `out` has no other use in classify_h1."""
    a = C.load_arm(archive / arm / "out")
    a["out"] = Path(LIVE_ROOT) / arm / "out"
    return a


def verify(archive, sums, manifest):
    res = R.verify(archive, sums, manifest)  # archive sums, unlisted files, per-arm raw files
    for key, meta in manifest["batch"].items():
        if not key.endswith(".raw") or meta is None:
            continue
        name = key[:-len(".raw")]
        p = archive / name
        res["manifest_raw_files_checked"] += 1
        if not p.is_file() or sha(p) != meta["sha256"] or p.stat().st_size != meta["bytes"]:
            res["problems"].append(f"{name}: does not match #795 MANIFEST")
    return res


def redactor(root, py, cbin):
    red = COL.Redactor(Path(root), HERE, py, cbin)
    red.subs = [(A2C.LIVE_PROJECT, "<LIVE_PROJECT>")] + red.subs
    return red


def publish_form(source, row, red, sel_nonce):
    """What the #795 collector publishes for one raw entry (list of 0 or 1 items)."""
    if source == "events":
        sel = COL.select_events([row])
    else:
        sel = A2C.select_transcript_a2([row], {}, sel_nonce)
        for x in sel:
            x.pop("line", None)
    return [red.obj(x) for x in sel]


def nonce_paths(obj, nonces):
    return sorted(p for p, s in C.walk(obj) if any(n in s for n in nonces))


def completeness(archive, arm, nonces, sel_nonce, red):
    """Per-entry diff between an arm's raw inputs and what collect_a2 publishes."""
    out = archive / arm / "out"
    res = {"nonces_scanned": len(nonces), "entries": {}, "omitted_hits": [], "hits_total": 0}
    for source, name in (("events", "events.jsonl"), ("transcript", "transcript.jsonl")):
        counts = {"whole": 0, "trimmed": 0, "dropped": 0, "by_type": {}}
        for i, line in enumerate((out / name).read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            row = json.loads(line)
            pub = publish_form(source, row, red, sel_nonce)
            whole = bool(pub) and red.obj(row) == pub[0]
            kind = "dropped" if not pub else ("whole" if whole else "trimmed")
            counts[kind] += 1
            typ = f"{row.get('type')}:{row.get('subtype') or (row.get('attachment') or {}).get('type')}"
            counts["by_type"][f"{typ}:{kind}"] = counts["by_type"].get(f"{typ}:{kind}", 0) + 1
            raw_s, pub_s = json.dumps(row), json.dumps(pub)
            for n in nonces:
                raw_n, pub_n = raw_s.count(n), (pub_s.count(n) if pub else 0)
                if raw_n > pub_n:
                    res["omitted_hits"].append({
                        "source": source, "line": i, "entry_type": typ, "kind": kind,
                        "nonce_role": "own" if n == sel_nonce else "paired emitter",
                        "raw_occurrences": raw_n, "published_occurrences": pub_n,
                        "raw_json_paths": nonce_paths(row, [n])})
        res["entries"][source] = counts
    err = out / "claude.stderr.txt"
    text = err.read_text(encoding="utf-8", errors="replace") if err.exists() else None
    res["stderr"] = {"bytes": err.stat().st_size if err.exists() else None,
                     "lines": len(text.splitlines()) if text is not None else None,
                     "nonce_occurrences": sum(text.count(n) for n in nonces) if text is not None else None}
    res["hits_total"] = len(res["omitted_hits"]) + (res["stderr"]["nonce_occurrences"] or 0)
    return res


def changes(as_run, new):
    """Top-level keys that differ, and per-location category changes."""
    keys = sorted(k for k in set(as_run) | set(new) if as_run.get(k) != new.get(k) and k != "nonce_locations")
    old_locs = {(l["source"], l["line"], l["json_path"]): l["category"] for l in as_run.get("nonce_locations") or []}
    new_locs = {(l["source"], l["line"], l["json_path"]): l["category"] for l in new.get("nonce_locations") or []}
    locs = [{"source": s, "line": ln, "json_path": jp, "as_run": old_locs.get((s, ln, jp)),
             "r1r5": new_locs.get((s, ln, jp))}
            for (s, ln, jp) in sorted(set(old_locs) | set(new_locs), key=lambda t: (t[0], t[1], t[2]))
            if old_locs.get((s, ln, jp)) != new_locs.get((s, ln, jp))]
    return {"top_level_keys": keys, "nonce_location_categories": locs,
            "location_set_unchanged": set(old_locs) == set(new_locs)}


def main(argv):
    archive, sums, pub, py, cbin = Path(argv[1]), Path(argv[2]), Path(argv[3]), argv[4], argv[5]
    summary_path = pub / "reclassification.json"
    if summary_path.exists() or any((pub / p / "outcome.r1r5.json").exists() for p in PATHS):
        raise SystemExit("refusing to overwrite existing reclassification output")
    manifest = json.loads((pub / "MANIFEST.json").read_text(encoding="utf-8"))
    sums_before = sha(sums)
    integrity = verify(archive, sums, manifest)
    if integrity["problems"]:
        print(json.dumps(integrity, indent=2))
        raise SystemExit("integrity check failed; nothing classified")

    red = redactor(archive, py, cbin)         # archive root -> <LIVE>
    red_live = redactor(LIVE_ROOT, py, cbin)  # original live root -> <LIVE>
    summary = {
        "rules": C.RULES_ID,
        "pins": {"claude_version": PIN_VERSION, "model": PIN_MODEL},
        "classifier_sha256": {"classify_h1.py": sha(HERE / "classify_h1.py")},
        "reclassify_tool_sha256": {"reclassify_a2.py": sha(Path(__file__)),
                                   "reclassify_h1.py (helpers)": sha(HERE / "reclassify_h1.py"),
                                   "collect_a2.py (selection)": sha(HERE / "collect_a2.py"),
                                   "collect_h1.py (selection)": sha(HERE / "collect_h1.py")},
        "integrity": integrity, "paths": {},
    }
    raw_outcomes = {}
    for p in PATHS:
        as_run = json.loads((pub / p / "outcome.json").read_text(encoding="utf-8"))
        emit = load_recorded(archive, p)
        ctl = load_recorded(archive, f"{p}-ctl")
        raw = C.classify(emit, ctl, p, PIN_MODEL, PIN_VERSION)
        raw["observer"] = {k: emit["observer"].get(k)
                           for k in ("claude_version", "pinset", "model_flag", "selftest", "date")}
        raw_outcomes[p] = raw
        sub = C.classify(R.subset_arm(pub, p), R.subset_arm(pub, f"{p}-ctl"), p, PIN_MODEL, PIN_VERSION)
        comp = {}
        for arm, own in ((p, emit["nonce"]), (f"{p}-ctl", ctl["nonce"])):
            nonces = sorted({emit["nonce"], own} - {None})
            c = completeness(archive, arm, nonces, own, red_live)
            c["omitted_hits"] = [red.obj(red_live.obj(h)) for h in c["omitted_hits"]]
            comp[arm] = c
        published = red.obj(red_live.obj(raw))
        COL.write_text(pub / p / "outcome.r1r5.json", json.dumps(published, indent=2) + "\n", red, {})
        summary["paths"][p] = {
            "label_as_run": as_run["label"], "label_r1r5_raw": raw["label"], "label_r1r5_subset": sub["label"],
            "raw_and_subset_agree": raw["label"] == sub["label"],
            "reasons_r1r5_raw": raw.get("reasons"), "reasons_r1r5_subset": sub.get("reasons"),
            "passes_path_r1r5_raw": raw["passes_path"],
            "nonce_categories_r1r5_raw": sorted({(l["json_path"], l["category"]) for l in raw.get("nonce_locations") or []}),
            "changes_from_as_run": changes(as_run, published),
            "completeness": comp,
            "omitted_material_nonce_hits": sum(c["hits_total"] for c in comp.values()),
        }
    pin_problem = C.host_pin_problem(raw_outcomes)
    listed = all(v["passes_path_r1r5_raw"] for v in summary["paths"].values()) and pin_problem is None
    summary["host_pin_problem"] = pin_problem
    summary["listed_path_result_r1r5_raw"] = "PASS" if listed else "NOT MET"
    summary["listed_path_note"] = ("A2 covers H1a-edit, H1a-bash and H1b-start only. The listed-path result "
                                   "is not the H1 gate: H1 also needs H1c, which A2 did not probe.")
    summary["h1_gate"] = "NOT MET (H1c is not in A2; H1c/A1 is pinned to 2.1.202; mixed-version combination undecided, A2-1)"
    summary["subset_note"] = ("Subset replay is a supporting check against the published subset only; "
                              "it depends on the raw completeness check and is not an independent reproduction.")
    integrity_after = verify(archive, sums, manifest)
    summary["integrity_after"] = {"problems": integrity_after["problems"],
                                  "archive_sums_unchanged": sha(sums) == sums_before}
    if integrity_after["problems"] or sha(sums) != sums_before:
        raise SystemExit("archive changed during reclassification; nothing written for the summary")
    COL.write_text(summary_path, json.dumps(summary, indent=2) + "\n", red, {})
    for p, v in summary["paths"].items():
        print(p, v["label_as_run"], "->", v["label_r1r5_raw"], "| subset", v["label_r1r5_subset"],
              "| omitted-material hits", v["omitted_material_nonce_hits"])
    print("Listed-path result under R1-R5 (raw, authoritative):", summary["listed_path_result_r1r5_raw"],
          "| host pin problem:", pin_problem)
    print("H1 gate:", summary["h1_gate"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
