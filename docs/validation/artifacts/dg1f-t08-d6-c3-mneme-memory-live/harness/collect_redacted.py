"""Copy D6 C3 live evidence into the repository with local paths and identifiers redacted.

usage: collect_redacted.py <live_root> <artifact_dir> <python_exe> <mneme_src> <claude_bin> <root_files_csv> <probe> [...]

<root_files_csv> names the batch-level files to publish (for C3:
summary_c3.md,run_d6_c3.log,C3_DONE), so one batch never republishes another.

C3 derivative of the C2 collector. Published per probe when present:
observer.txt, prompt.txt, hook-registration.json, hook-log.jsonl,
events.selected.jsonl, posthoc.json, plus the C3 files witness-log.jsonl,
settings.after.json, outcome.json, sync/writer.json (published as
writer.json), the byte copies app.before.py / app.after.py used for the exact
forbidden-change check, and harness_failure.txt if a probe failed. observer.txt and outcome.json are required; the others may be
absent for a NOT_EXECUTED probe, and MANIFEST.json records each absence as
null. Not published: the raw events.jsonl and claude.stderr.txt (SHA-256 in
MANIFEST.json).

Byte-exact copies: app.before.py and app.after.py are published as their
original bytes (CRLF preserved), never decoded and re-encoded, so their
published SHA-256 equals the source SHA-256 and the observer snapshot hashes
(the exact forbidden-change check stays independently reproducible). Before
publication each must decode as UTF-8, pass the leak scan, and contain nothing
the redactor would change; otherwise collection fails (exit 1). Every other
file keeps the normal redaction path.

Provenance: MANIFEST.json records this collector's own SHA-256, the harness
HEAD(s) the live run recorded in observer.txt, and whether this collector is
byte-identical to the as-run collect_redacted.py hashed in run_d6_c3.log. A
re-collection with a newer collector is therefore never presented as the
collector used during the live run.

Self-test output (observer.txt containing SELFTEST) is refused (exit 1) unless
D6_COLLECT_SELFTEST=1, so stub runs can never be published as evidence.

Redactions: live root -> <LIVE>, interpreter -> <PYTHON>, Mneme source tree ->
<MNEME_SRC>, claude binary -> <CLAUDE_BIN>, tool_use ids -> stable per-probe
pseudonyms, session ids -> <SESSION>, pid/ppid -> null. A leak scan fails the
run (exit 1) if any local path or raw identifier survives.
"""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

live, dest, py, src, cbin = (sys.argv[1], Path(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5])
root_files = [f for f in sys.argv[6].split(",") if f]
probes = sys.argv[7:]
PUBLISHED = ["observer.txt", "prompt.txt", "hook-registration.json", "hook-log.jsonl",
             "events.selected.jsonl", "posthoc.json", "witness-log.jsonl", "settings.after.json",
             "outcome.json", "sync/writer.json", "app.before.py", "app.after.py",
             "harness_failure.txt"]
REQUIRED = ("observer.txt", "outcome.json")
BYTE_EXACT = ("app.before.py", "app.after.py")
RAW_ONLY = ["events.jsonl", "claude.stderr.txt"]


def variants(p):
    win = p.replace("/", "\\")
    fwd = win.replace("\\", "/")
    unix = "/" + fwd[0].lower() + fwd[2:] if re.match(r"^[A-Za-z]:", fwd) else fwd
    # C3: a settings Edit carries a JSON-escaped path that the transcript escapes
    # again, so the quadruple-backslash form must be redacted too.
    return {win, win.replace("\\", "\\\\"), win.replace("\\", "\\\\\\\\"), fwd, unix}


SUBS = []
for raw, tag in ((src, "<MNEME_SRC>"), (py, "<PYTHON>"), (cbin, "<CLAUDE_BIN>"), (live, "<LIVE>")):
    for v in sorted(variants(raw), key=len, reverse=True):
        SUBS.append((v, tag))

LEAKS = [re.compile(p, re.I) for p in (r"Users[\\/]+hi\b", r"[A-Za-z]:[\\/]+dev[\\/]", r"/c/dev/",
                                         r"toolu_0[0-9A-Za-z]{10,}", r"AppData", r"WindowsApps")]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def redact(text, idmap, probe):
    for old, new in SUBS:
        text = text.replace(old, new)

    def tid(m):
        return idmap.setdefault(m.group(0), f"toolu_{probe}_{len(idmap) + 1}")
    text = re.sub(r"toolu_[0-9A-Za-z]{10,}", tid, text)
    text = re.sub(r'("session_id": )"[^"]*"', r'\1"<SESSION>"', text)
    text = re.sub(r'("p?pid": )\d+', r"\1null", text)
    return text


manifest = {"live_root": "<LIVE>", "probes": {}, "root_files": {}}
bad = []
for probe in probes:
    out = Path(live) / probe / "out"
    d = dest / probe
    d.mkdir(parents=True, exist_ok=True)
    idmap = {}
    entry = {"published": {}, "raw_not_published": {}}
    if ("SELFTEST" in (out / "observer.txt").read_text(encoding="utf-8")
            and os.environ.get("D6_COLLECT_SELFTEST") != "1"):
        print(f"REFUSED: {probe} is self-test output (stub claude), not evidence")
        sys.exit(1)
    for name in PUBLISHED:
        if not (out / name).exists():
            if name in REQUIRED:
                print(f"REFUSED: {probe}/{name} missing")
                sys.exit(1)
            entry["published"][name] = None
            continue
        pub = Path(name).name
        if name in BYTE_EXACT:
            raw = (out / name).read_bytes()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                bad.append(f"{probe}/{name}: not UTF-8; byte-exact publication refused")
                continue
            bad += [f"{probe}/{name}: {rx.pattern}" for rx in LEAKS if rx.search(text)]
            if redact(text, {}, probe) != text:  # separate idmap: never perturbs pseudonyms
                bad.append(f"{probe}/{name}: contains redactable content; byte-exact publication refused")
                continue
            (d / pub).write_bytes(raw)
            entry["published"][name] = {"source_sha256": sha(out / name), "published_sha256": sha(d / pub),
                                        "byte_exact": True}
            if entry["published"][name]["source_sha256"] != entry["published"][name]["published_sha256"]:
                bad.append(f"{probe}/{name}: published bytes differ from source")
            continue
        text = redact((out / name).read_text(encoding="utf-8"), idmap, probe)
        (d / pub).write_text(text, encoding="utf-8", newline="\n")
        entry["published"][name] = {"source_sha256": sha(out / name), "published_sha256": sha(d / pub)}
        bad += [f"{probe}/{name}: {rx.pattern}" for rx in LEAKS if rx.search(text)]
    for name in RAW_ONLY:
        p = out / name
        entry["raw_not_published"][name] = {"sha256": sha(p), "bytes": p.stat().st_size} if p.exists() else None
    manifest["probes"][probe] = entry
for name in root_files:
    p = Path(live) / name
    text = redact(p.read_text(encoding="utf-8"), {}, "summary")
    (dest / name).write_text(text, encoding="utf-8", newline="\n")
    manifest["root_files"][name] = {"source_sha256": sha(p), "published_sha256": sha(dest / name)}
    bad += [f"{name}: {rx.pattern}" for rx in LEAKS if rx.search(text)]
heads = sorted({line.split("=", 1)[1].split()[0]
                for probe in probes
                for line in (Path(live) / probe / "out" / "observer.txt").read_text(encoding="utf-8").splitlines()
                if line.startswith("harness_head=")})
as_run = None
log = Path(live) / "run_d6_c3.log"
if log.exists():
    m = re.search(r"harness sha256: ([0-9a-f]{64}) \*?\./collect_redacted\.py", log.read_text(encoding="utf-8"))
    as_run = m.group(1) if m else None
mine = sha(__file__)
manifest["provenance"] = {
    "live_run_harness_head": heads,
    "as_run_collect_redacted_sha256": as_run,
    "this_collector_sha256": mine,
    "this_collector_is_as_run_collector": as_run == mine,
    "byte_exact_files": list(BYTE_EXACT),
}
(dest / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
if bad:
    print("LEAK SCAN FAILED:\n  " + "\n  ".join(bad))
    sys.exit(1)
print(f"collected {len(probes)} probes into {dest}; leak scan clean")
