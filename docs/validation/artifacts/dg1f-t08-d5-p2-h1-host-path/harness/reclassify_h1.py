"""Offline reclassification of the H1 live evidence under rules R1-R3 (#551, #552).

usage: reclassify_h1.py <archive_dir> <archive_sums> <published_dir> <python_exe> <claude_bin>

No host session runs. Nothing in the archive or in the as-run published files
is modified. The procedure follows docs/plans/2026-10-17-dg1f-t08-d5-p2-h1-classifier-rules.md §5:

1. Integrity. <archive_sums> (sha256sum format, one line per file) must verify
   against <archive_dir>, and every raw file listed in the #549
   <published_dir>/MANIFEST.json `raw_not_published` entries must match its
   recorded SHA-256 and size. Any mismatch aborts (exit 1) before classification.
2. Authoritative run. The merged classify_h1.classify() (rules R1-R3) runs on
   the archived RAW evidence for each path and its control.
3. Completeness check. For every arm, the material the collector did not
   publish is scanned for the path's emitter nonce: transcript entries outside
   user/assistant/hook_* attachments, thinking blocks (events and transcript),
   omitted init fields and omitted result fields. Counts and hits are recorded,
   and every hit is published redacted.
4. Subset replay (supporting only). The same classifier runs on the published
   selected evidence (*.selected.jsonl, hook-log.jsonl, observer.txt hashes).
   It is NOT an independent reproduction: it depends on the raw completeness
   check. Differences from step 2 are reported, never reconciled.

Writes, next to the unchanged as-run files:
  <published_dir>/<path>/outcome.r1r3.json   authoritative raw-run outcome (redacted)
  <published_dir>/reclassification.json      integrity, labels (as-run, raw, subset),
                                              completeness scan, classifier hash
Refuses to overwrite either.
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATHS = ("H1a-edit", "H1a-bash", "H1b-start", "H1c-stop")
EVENT = {"H1a-edit": "PreToolUse", "H1a-bash": "PreToolUse", "H1b-start": "SessionStart", "H1c-stop": "Stop"}
PIN_MODEL = "claude-opus-4-8[1m]"
SELECTED_INIT = {"type", "subtype", "model", "claude_code_version", "permissionMode", "cwd", "session_id"}


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


C = load("classify_h1")
COL = load("collect_h1")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def verify(archive, sums, manifest):
    bad = []
    lines = [l for l in Path(sums).read_text(encoding="utf-8").splitlines() if l.strip()]
    for l in lines:
        h, name = l.split(None, 1)
        name = name.lstrip("*").removeprefix("./")
        p = archive / name
        if not p.is_file() or sha(p) != h:
            bad.append(f"archive checksum mismatch: {name}")
    listed = {l.split(None, 1)[1].lstrip("*").removeprefix("./") for l in lines}
    present = {p.relative_to(archive).as_posix() for p in archive.rglob("*") if p.is_file()}
    for extra in sorted(present - listed):
        bad.append(f"file in archive not in checksum list: {extra}")
    n = 0
    for arm, e in manifest["arms"].items():
        for name, meta in e["raw_not_published"].items():
            p = archive / arm / "out" / name
            if meta is None:
                if p.exists():
                    bad.append(f"{arm}/{name}: manifest says absent, archive has it")
                continue
            n += 1
            if not p.is_file() or sha(p) != meta["sha256"] or p.stat().st_size != meta["bytes"]:
                bad.append(f"{arm}/{name}: does not match #549 MANIFEST")
    return {"archive_files_listed": len(lines), "archive_sums_sha256": sha(sums),
            "manifest_raw_files_checked": n, "problems": bad}


def completeness(archive, arm, nonce):
    out = archive / arm / "out"
    res = {"omitted_transcript_entries": 0, "omitted_transcript_hits": [],
           "thinking_blocks": 0, "thinking_hits": 0,
           "omitted_init_fields": 0, "omitted_init_hits": [],
           "omitted_result_fields": 0, "omitted_result_hits": []}
    for i, line in enumerate((out / "transcript.jsonl").read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        e = json.loads(line)
        t = e.get("type")
        selected = t in ("user", "assistant") or (
            t == "attachment" and str((e.get("attachment") or {}).get("type", "")).startswith("hook_"))
        if not selected:
            res["omitted_transcript_entries"] += 1
            if nonce in line:
                res["omitted_transcript_hits"].append({"line": i, "entry": e})
        if t == "assistant":
            for it in (e.get("message") or {}).get("content") or []:
                if isinstance(it, dict) and it.get("type") in ("thinking", "redacted_thinking"):
                    res["thinking_blocks"] += 1
                    res["thinking_hits"] += nonce in json.dumps(it)
    for line in (out / "events.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        if e.get("type") == "system" and e.get("subtype") == "init":
            for k, v in e.items():
                if k not in SELECTED_INIT:
                    res["omitted_init_fields"] += 1
                    if nonce in json.dumps(v):
                        res["omitted_init_hits"].append(k)
        elif e.get("type") == "result":
            for k in ("usage", "modelUsage"):
                if k in e:
                    res["omitted_result_fields"] += 1
                    if nonce in json.dumps(e[k]):
                        res["omitted_result_hits"].append(k)
        elif e.get("type") == "assistant":
            for it in (e.get("message") or {}).get("content") or []:
                if isinstance(it, dict) and it.get("type") in ("thinking", "redacted_thinking"):
                    res["thinking_blocks"] += 1
                    res["thinking_hits"] += nonce in json.dumps(it)
    res["hits_total"] = (len(res["omitted_transcript_hits"]) + res["thinking_hits"]
                         + len(res["omitted_init_hits"]) + len(res["omitted_result_hits"]))
    return res


def subset_arm(pub, arm):
    """Load one arm from the PUBLISHED selected evidence (supporting replay only)."""
    d = pub / arm
    obs = {}
    for line in (d / "observer.txt").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            obs.setdefault(k, v)
    expected = {"notes": hashlib.sha256(C.EDIT_EXPECTED).hexdigest(),
                "bash": hashlib.sha256(C.BASH_EXPECTED).hexdigest()}
    return {
        # Workspace masking: published tool inputs carry <LIVE>\<arm>\ws paths.
        "out": Path("<LIVE>") / arm / "out",
        "nonce": (d / "nonce.txt").read_text(encoding="utf-8").strip(),
        "events": C.read_jsonl(d / "events.selected.jsonl"),
        "transcript": C.read_jsonl(d / "transcript.selected.jsonl"),
        "transcript_collected": (d / "transcript.selected.jsonl").exists(),
        "hooks": [r for _, r in C.read_jsonl(d / "hook-log.jsonl")],
        # File content is checked through the observer's after-hashes.
        "notes_after": C.EDIT_EXPECTED if obs.get("notes_after") == expected["notes"] else b"<other>",
        "bash_after": C.BASH_EXPECTED if obs.get("bash_out_after") == expected["bash"] else None,
        "notes_sha": obs.get("notes_after"),
        "bash_sha": obs.get("bash_out_after"),
        "observer": obs,
    }


def main(argv):
    archive, sums, pub, py, cbin = Path(argv[1]), Path(argv[2]), Path(argv[3]), argv[4], argv[5]
    summary_path = pub / "reclassification.json"
    if summary_path.exists() or any((pub / p / "outcome.r1r3.json").exists() for p in PATHS):
        raise SystemExit("refusing to overwrite existing reclassification output")
    manifest = json.loads((pub / "MANIFEST.json").read_text(encoding="utf-8"))
    integrity = verify(archive, sums, manifest)
    if integrity["problems"]:
        print(json.dumps(integrity, indent=2))
        raise SystemExit("integrity check failed; nothing classified")

    red = COL.Redactor(archive, HERE, py, cbin)
    red_live = COL.Redactor(Path(r"C:\dev\d5p2-h1-live"), HERE, py, cbin)
    summary = {"rules": C.RULES_ID, "classifier_sha256": sha(HERE / "classify_h1.py"),
               "reclassify_tool_sha256": sha(Path(__file__)), "integrity": integrity, "paths": {}}
    for p in PATHS:
        as_run = json.loads((pub / p / "outcome.json").read_text(encoding="utf-8"))
        emit = C.load_arm(archive / p / "out")
        ctl = C.load_arm(archive / f"{p}-ctl" / "out")
        raw = C.classify(emit, ctl, p, PIN_MODEL)
        sub = C.classify(subset_arm(pub, p), subset_arm(pub, f"{p}-ctl"), p, PIN_MODEL)
        comp = {arm: completeness(archive, arm, emit["nonce"]) for arm in (p, f"{p}-ctl")}
        for arm, c in comp.items():  # publish every hit, redacted
            c["omitted_transcript_hits"] = [red.obj(red_live.obj(h)) for h in c["omitted_transcript_hits"]]
        body = json.dumps(red.obj(red_live.obj(raw)), indent=2) + "\n"
        COL.write_text(pub / p / "outcome.r1r3.json", body, red, {})
        summary["paths"][p] = {
            "label_as_run": as_run["label"], "label_r1r3_raw": raw["label"], "label_r1r3_subset": sub["label"],
            "raw_and_subset_agree": raw["label"] == sub["label"],
            "subset_reasons": sub.get("reasons"),
            "passes_path_r1r3_raw": raw["passes_path"], "completeness": comp,
        }
    gate = all(v["passes_path_r1r3_raw"] for v in summary["paths"].values())
    summary["h1_gate_r1r3_raw"] = "PASS" if gate else "NOT MET"
    summary["subset_note"] = ("Subset replay is a supporting check against the published subset only; "
                              "it depends on the raw completeness check and is not an independent reproduction.")
    COL.write_text(summary_path, json.dumps(summary, indent=2) + "\n", red, {})
    for p, v in summary["paths"].items():
        print(p, v["label_as_run"], "->", v["label_r1r3_raw"], "| subset", v["label_r1r3_subset"],
              "| omitted-material hits", sum(c["hits_total"] for c in v["completeness"].values()))
    print("H1 gate under R1-R3 (raw, authoritative):", summary["h1_gate_r1r3_raw"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
