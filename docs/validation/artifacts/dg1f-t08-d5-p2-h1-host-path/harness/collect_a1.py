"""Copy A1 headless live evidence into the repository, selected and redacted.

usage: collect_a1.py <live_root> <dest_dir> <python_exe> <claude_bin>

Added AFTER the live A1 headless run (2026-10-19). It is not part of the as-run
harness hashed in run_a1_headless.log, and it never re-classifies:
outcome_a1_headless.json is published exactly as classify_a1.py wrote it, apart
from path redaction.

Selection, redaction and the leak scan are collect_h1.py's (imported, unchanged),
applied to the A1 headless arms H1c-sm-ctl and H1c-sm. One extra redaction: the
H1 live root, which preflight.sh prints in the run log, becomes <H1_LIVE>.
The raw events.jsonl, transcript.jsonl and claude.stderr.txt are not published;
MANIFEST.json records their SHA-256 and size.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_h1 as c  # noqa: E402

ARMS = ("H1c-sm-ctl", "H1c-sm")
COPY = ("observer.txt", "prompt.txt", "probe.json", "hook-registration.json",
        "hook-log.jsonl", "nonce.txt")
BATCH = ("outcome_a1_headless.json", "run_a1_headless.log", "A1_HEADLESS_DONE")
H1_LIVE = r"C:\dev\d5p2-h1-live"


def main(argv):
    live, dest, py, cbin = Path(argv[1]), Path(argv[2]), argv[3], argv[4]
    harness = Path(__file__).resolve().parent
    red = c.Redactor(live, harness, py, cbin)
    # Longest spellings first are already ensured per path; the H1 root is not a
    # prefix of the A1 root, so order between the two does not matter.
    red.subs = [(re.compile(re.escape(f), re.I), "<H1_LIVE>") for f in c.forms(H1_LIVE)] + red.subs
    if dest.exists():
        raise SystemExit(f"destination exists, refusing to overwrite: {dest}")
    published, manifest = {}, {"arms": {}, "batch": {}}
    for arm in ARMS:
        src = live / arm / "out"
        if "selftest=1" in (src / "observer.txt").read_text(encoding="utf-8"):
            raise SystemExit(f"{arm}: self-test output is not evidence")
        red.ids = {}
        entry = {"published": {}, "raw_not_published": {}, "transcript_entries_not_published": {}}
        for name in COPY:
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
        ev = c.select_events(c.read_jsonl(src / "events.jsonl"))
        c.write_text(dest / arm / "events.selected.jsonl", "".join(json.dumps(red.obj(r)) + "\n" for r in ev), red, published)
        entry["published"]["events.selected.jsonl"] = published[str(dest / arm / "events.selected.jsonl")]
        skipped = {}
        tr = c.select_transcript(c.read_jsonl(src / "transcript.jsonl"), skipped)
        c.write_text(dest / arm / "transcript.selected.jsonl", "".join(json.dumps(red.obj(r)) + "\n" for r in tr), red, published)
        entry["published"]["transcript.selected.jsonl"] = published[str(dest / arm / "transcript.selected.jsonl")]
        entry["transcript_entries_not_published"] = skipped
        for name in c.RAW:
            entry["raw_not_published"][name] = c.sha_size(src / name)
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
    manifest["collector"] = {"file": "harness/collect_a1.py",
                             "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                             "reuses": "harness/collect_h1.py",
                             "reuses_sha256": hashlib.sha256(Path(c.__file__).read_bytes()).hexdigest(),
                             "added_after_live_run": True,
                             "reclassified": False}
    body = json.dumps(manifest, indent=2) + "\n"
    c.write_text(dest / "MANIFEST.json", body.replace(str(dest), "<DEST>"), red, published)
    print(f"collected {len(published)} files into {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
