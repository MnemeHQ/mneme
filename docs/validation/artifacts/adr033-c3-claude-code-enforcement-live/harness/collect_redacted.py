"""Copy C3 probe evidence into the repository, redacted, with a manifest.

usage: collect_redacted.py <live-root> <dest-dir> [--home <path>] [--mneme-src <path>]

For each probe directory with ``out/outcome.json``, copies the evidence files
listed in FILES, replacing the live root, home directory, user name and Mneme
source path with placeholders. Screen recordings are never copied (their
SHA-256 is in outcome.json); they stay with the operator.

Fails closed: if any published file still contains a credential-shaped string
(GitHub or Anthropic tokens, Authorization headers, private keys) the
collection stops and writes nothing further. Writes ``MANIFEST.json`` with the
source and published SHA-256 of every file and this collector's own hash.
"""
from __future__ import annotations

import getpass
import hashlib
import json
import re
import sys
from pathlib import Path

FILES = ("observer.txt", "prompt.txt", "setup.json", "hook-registration.json",
         "events.jsonl", "hook-log.jsonl", "outcome.json", "target.before",
         "target.after", "operator-attestation.txt", "netcap-sni.txt")
LEAKS = re.compile(r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
                   r"sk-ant-[A-Za-z0-9_\-]{10,}|Authorization:\s*\S+|"
                   r"-----BEGIN [A-Z ]*PRIVATE KEY-----)")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def variants(path: str) -> list[str]:
    p = path.rstrip("\\/")
    out = {p, p.replace("\\", "/"), p.replace("\\", "\\\\"), p.replace("/", "\\")}
    if len(p) > 1 and p[1] == ":":
        out.add("/" + p[0].lower() + p[2:].replace("\\", "/"))
    return sorted(out, key=len, reverse=True)


def main() -> int:
    args = sys.argv[1:]
    live, dest = Path(args[0]), Path(args[1])
    home = args[args.index("--home") + 1] if "--home" in args else str(Path.home())
    src = args[args.index("--mneme-src") + 1] if "--mneme-src" in args else None
    replacements = [(v, "<LIVE>") for v in variants(str(live))]
    if src:
        replacements += [(v, "<MNEME_SRC>") for v in variants(src)]
    replacements += [(v, "<HOME>") for v in variants(home)]
    user = getpass.getuser()
    manifest = {"collector_sha256": sha(Path(__file__).read_bytes()), "files": []}
    dest.mkdir(parents=True, exist_ok=True)
    for outcome in sorted(live.glob("*/out/outcome.json")):
        out = outcome.parent
        probe_dest = dest / out.parent.name
        transcripts = sorted(p.name for p in out.glob("transcript-*.jsonl"))
        for name in (*FILES, *transcripts):
            source = out / name
            if not source.exists():
                continue
            raw = source.read_bytes()
            text = raw.decode("utf-8", errors="replace")
            for old, new in replacements:
                text = text.replace(old, new)
            text = re.sub(rf"\b{re.escape(user)}\b", "<USER>", text)
            if LEAKS.search(text):
                print(f"ABORT: credential-shaped string in {source}; nothing more written",
                      file=sys.stderr)
                return 1
            published = text.encode("utf-8")
            probe_dest.mkdir(parents=True, exist_ok=True)
            (probe_dest / name).write_bytes(published)
            manifest["files"].append({"path": f"{probe_dest.name}/{name}",
                                      "source_sha256": sha(raw),
                                      "published_sha256": sha(published)})
    (dest / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"collected {len(manifest['files'])} files into {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
