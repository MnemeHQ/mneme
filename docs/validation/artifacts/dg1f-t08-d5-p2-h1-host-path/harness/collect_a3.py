"""Copy Amendment A3 live evidence into the repository, selected and redacted.

usage: collect_a3.py <live_root> <dest_dir> <python_exe> <claude_bin> <local_crops_dir>

Added AFTER the A3 live run (2026-11-16). It is not part of the as-run harness
hashed in run_a1_headless.log, and it never re-classifies: outcome_a1_headless.json,
outcome_a1_interactive.json and outcome_a1.json are published exactly as
classify_a1.py wrote them, apart from path redaction.

Selection, redaction and the leak scan are collect_h1.py's, and the transcript
selection is collect_a2.py's select_transcript_a2 (Claude Code 2.1.310 records), all
imported unchanged, applied to the four A3 arms: the headless pair H1c-sm-ctl and
H1c-sm, and the interactive pair H1c-sm-int-ctl and H1c-sm-int.

A3-specific additions:
  1. The interactive arms also publish observation.json, capture_review.json and
     capture_review.template.json (redacted like every other file).
  2. Screenshot frames (owner decision 2026-11-16: screenshots instead of a screen
     recording) are NEVER published: the originals show the operator's desktop, and
     the pinned ADR-033 C4 trusted gate cannot evaluate binary files (owner decision
     2026-11-16, review of #804: keep the crops local rather than change gate
     policy). Each frame is cropped to the terminal area and the taskbar clock, with
     fixed mask boxes over the operator's user folder in the terminal crop, and the
     crops are written to <local_crops_dir>, which must be OUTSIDE the repository.
     MANIFEST.json records each original frame's SHA-256 (the one the capture review
     is bound to), the crop and mask boxes, and each local crop's SHA-256.
  3. Claude Code's encoded project directory for the live root
     (`C--dev-d5p2-h1c-a3-live`) becomes <LIVE_PROJECT>.

The raw events.jsonl, transcript.jsonl and claude.stderr.txt, the original frames
and the captures are not published; MANIFEST.json records their SHA-256 and size.
"""
import hashlib
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_h1 as c  # noqa: E402
import collect_a2 as a2  # noqa: E402

HEADLESS = ("H1c-sm-ctl", "H1c-sm")
INTERACTIVE = ("H1c-sm-int-ctl", "H1c-sm-int")
COPY = ("observer.txt", "prompt.txt", "probe.json", "hook-registration.json", "hook-log.jsonl", "nonce.txt")
COPY_INT = ("observation.json", "capture_review.json", "capture_review.template.json")
BATCH = ("outcome_a1_headless.json", "run_a1_headless.log", "A1_HEADLESS_DONE",
         "outcome_a1_interactive.json", "outcome_a1.json")
LIVE_PROJECT = re.compile(re.escape("C--dev-d5p2-h1c-a3-live"), re.I)
# (arm, frame) -> terminal crop box, mask boxes inside that crop, clock crop box.
# Boxes are (left, top, right, bottom) in pixels, chosen by inspecting each frame.
FRAMES = {
    ("H1c-sm-int-ctl", "frames/f1.webp"): {"term": (48, 0, 1792, 770), "mask": [(8, 12, 232, 46)],
                                           "clock": (1880, 895, 2000, 954)},
    ("H1c-sm-int-ctl", "frames/f2.webp"): {"term": (33, 66, 1790, 920), "mask": [(8, 92, 232, 126)],
                                           "clock": (1875, 1045, 2000, 1111)},
    ("H1c-sm-int", "frames/f1.webp"): {"term": (45, 38, 1812, 895), "mask": [],
                                       "clock": (1895, 1020, 2000, 1087)},
}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def crop_frames(src, arm, crops, entry):
    from PIL import Image, ImageDraw  # only needed when frames exist
    obs = json.loads((src / "observation.json").read_text(encoding="utf-8"))
    entry["frames"] = []
    for f in obs.get("frames") or []:
        key = (arm, f["file"])
        if key not in FRAMES:
            raise SystemExit(f"{arm}: no crop specification for {f['file']}; refusing to publish it uncropped")
        spec, p = FRAMES[key], src / f["file"]
        raw = p.read_bytes()
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        stem = Path(f["file"]).stem
        rec = {"file": f["file"], "t": f.get("t"), "original_sha256": sha(raw), "original_bytes": len(raw),
               "original_size": list(im.size), "published": False, "local_crops": {}}
        for part in ("term", "clock"):
            crop = im.crop(spec[part])
            if part == "term":
                d = ImageDraw.Draw(crop)
                for box in spec["mask"]:
                    d.rectangle(box, fill=(0, 0, 0))
            buf = io.BytesIO()
            crop.save(buf, format="PNG")
            out = crops / arm / f"{stem}.{part}.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            if out.exists():
                raise SystemExit(f"local crop exists, refusing to overwrite: {out}")
            out.write_bytes(buf.getvalue())
            rec["local_crops"][f"<LOCAL_CROPS>/{arm}/{stem}.{part}.png"] = {
                "sha256": sha(buf.getvalue()), "crop": list(spec[part]),
                "mask": [list(b) for b in spec["mask"]] if part == "term" else []}
        entry["frames"].append(rec)


def main(argv):
    live, dest, py, cbin, crops = Path(argv[1]), Path(argv[2]), argv[3], argv[4], Path(argv[5]).resolve()
    harness = Path(__file__).resolve().parent
    repo = harness.parents[4]
    if crops == repo or repo in crops.parents:
        raise SystemExit(f"local crops directory must be outside the repository: {crops}")
    red = c.Redactor(live, harness, py, cbin)
    red.subs = [(LIVE_PROJECT, "<LIVE_PROJECT>")] + red.subs
    if dest.exists():
        raise SystemExit(f"destination exists, refusing to overwrite: {dest}")
    published, manifest = {}, {"arms": {}, "batch": {}}
    for arm in HEADLESS + INTERACTIVE:
        src = live / arm / "out"
        if "selftest=1" in (src / "observer.txt").read_text(encoding="utf-8"):
            raise SystemExit(f"{arm}: self-test output is not evidence")
        red.ids = {}
        entry = {"published": {}, "raw_not_published": {}, "transcript_entries_not_published": {}}
        for name in COPY + (COPY_INT if arm in INTERACTIVE else ()):
            p = src / name
            if not p.exists():
                entry["published"][name] = None
                continue
            if name.endswith(".jsonl"):
                body = "".join(json.dumps(red.obj(r)) + "\n" for r in c.read_jsonl(p))
            elif name.endswith(".json"):
                body = json.dumps(red.obj(json.loads(p.read_text(encoding="utf-8"))), indent=2) + "\n"
            else:
                body = p.read_text(encoding="utf-8")
            c.write_text(dest / arm / name, body, red, published)
            entry["published"][name] = published[str(dest / arm / name)]
        if (src / "events.jsonl").exists():
            ev = c.select_events(c.read_jsonl(src / "events.jsonl"))
            c.write_text(dest / arm / "events.selected.jsonl",
                         "".join(json.dumps(red.obj(r)) + "\n" for r in ev), red, published)
            entry["published"]["events.selected.jsonl"] = published[str(dest / arm / "events.selected.jsonl")]
        nonce = (src / "nonce.txt").read_text(encoding="utf-8").strip() if (src / "nonce.txt").exists() else None
        skipped = {}
        tr = a2.select_transcript_a2(c.read_jsonl(src / "transcript.jsonl"), skipped, nonce)
        c.write_text(dest / arm / "transcript.selected.jsonl",
                     "".join(json.dumps(red.obj(r)) + "\n" for r in tr), red, published)
        entry["published"]["transcript.selected.jsonl"] = published[str(dest / arm / "transcript.selected.jsonl")]
        entry["transcript_entries_not_published"] = skipped
        for name in c.RAW:
            entry["raw_not_published"][name] = c.sha_size(src / name)
        if arm in INTERACTIVE:
            crop_frames(src, arm, crops, entry)
        manifest["arms"][arm] = entry
    for name in BATCH:
        p = live / name
        if p.exists():
            body = p.read_text(encoding="utf-8")
            if name.endswith(".json"):
                body = json.dumps(red.obj(json.loads(body)), indent=2) + "\n"
            c.write_text(dest / name, body, red, published)
            manifest["batch"][name] = published[str(dest / name)]
            manifest["batch"][name + ".raw"] = c.sha_size(p)
        else:
            manifest["batch"][name] = None
    manifest["collector"] = {"file": "harness/collect_a3.py",
                             "sha256": sha(Path(__file__).read_bytes()),
                             "reuses": ["harness/collect_h1.py", "harness/collect_a2.py (select_transcript_a2)"],
                             "reuses_sha256": {"collect_h1.py": sha(Path(c.__file__).read_bytes()),
                                               "collect_a2.py": sha(Path(a2.__file__).read_bytes())},
                             "added_after_live_run": True,
                             "reclassified": False}
    body = json.dumps(manifest, indent=2) + "\n"
    c.write_text(dest / "MANIFEST.json", body.replace(str(dest), "<DEST>"), red, published)
    print(f"collected {len(published)} text files into {dest}; frame crops kept locally in {crops}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
