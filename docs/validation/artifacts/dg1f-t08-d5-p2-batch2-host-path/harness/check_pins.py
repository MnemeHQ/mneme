"""Pin check for batch 2 (probe scope section 7). Read-only; installs nothing.

usage:
  check_pins.py antigravity <path-to-Antigravity.exe or a version string>
  check_pins.py hermes <python-executable>

Exit 0 only on an exact match with pins.env. A mismatch is reported, never
"fixed": re-pinning needs a reviewed amendment (probe scope section 7).
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def pins() -> dict:
    out = {}
    for line in (HERE / "pins.env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


def antigravity_version(target: str) -> str:
    p = Path(target)
    if not p.is_file():
        return target.strip()
    # Windows file-version metadata; no host session is started.
    ps = ["powershell", "-NoProfile", "-Command",
          f"(Get-Item -LiteralPath '{p}').VersionInfo.FileVersion"]
    return subprocess.run(ps, capture_output=True, text=True, check=False).stdout.strip()


def hermes_version(python: str) -> str:
    code = ("import importlib.metadata as m\n"
            "try:\n print(m.version('hermes-agent'))\n"
            "except m.PackageNotFoundError:\n print('NOT_INSTALLED')")
    return subprocess.run([python, "-I", "-c", code], capture_output=True,
                          text=True, check=False).stdout.strip()


def normalize(v: str) -> str:
    parts = v.split(".")
    while len(parts) > 3 and parts[-1] == "0":
        parts.pop()
    return ".".join(parts)


def check(host: str, target: str) -> tuple[bool, str]:
    p = pins()
    if host == "antigravity":
        want, got = p["ANTIGRAVITY_VERSION"], normalize(antigravity_version(target))
    elif host == "hermes":
        want, got = p["HERMES_AGENT_VERSION"], hermes_version(target)
    else:
        return False, f"unknown host {host!r}"
    ok = got == want
    return ok, f"{host}: pinned {want}, found {got or 'nothing'}: {'MATCH' if ok else 'MISMATCH'}"


def main(argv) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    ok, msg = check(argv[1], argv[2])
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
