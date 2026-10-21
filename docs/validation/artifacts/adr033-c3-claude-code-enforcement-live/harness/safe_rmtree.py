"""The harness's only recursive deletion, confined to the fixed live root.

usage: safe_rmtree.py delete <name>

``<name>`` must be a single path component matching ``_golden``, ``_seed`` or
``<probe>-<tool>-<rep>`` for a known probe. The target must sit directly
under LIVE_ROOT and contain no reparse points (junctions or symlinks).
Git's read-only object files are made writable before removal.
"""
from __future__ import annotations

import os
import re
import shutil
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matrix  # noqa: E402

LIVE_ROOT = Path(os.environ.get("C3_SELFTEST_LIVE") or r"C:\dev\mneme-c3-live")
NAME = re.compile(r"^(_golden|_seed|(?P<probe>[RPUDH]-\d)-(?P<tool>Write|Edit|MultiEdit)-(?P<rep>[1-9]\d*)"
                  r"(?P<arm>-interactive)?)$")


def _reparse(path: Path) -> bool:
    try:
        attrs = os.lstat(path).st_file_attributes  # type: ignore[attr-defined]
        return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except AttributeError:
        return path.is_symlink()


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] != "delete":
        raise SystemExit(__doc__)
    if os.environ.get("C3_SELFTEST_LIVE") and os.environ.get("C3_SELFTEST") != "1":
        raise SystemExit("C3_SELFTEST_LIVE is only honored in self-test mode")
    name = sys.argv[2]
    match = NAME.match(name)
    if not match or (match.group("probe") and match.group("probe") not in matrix.ROWS):
        raise SystemExit(f"refused: {name!r} is not an allowed probe directory name")
    target = LIVE_ROOT / name
    if target.parent.resolve() != LIVE_ROOT.resolve():
        raise SystemExit("refused: target is not directly under the live root")
    if not target.exists():
        return 0
    for current, dirs, files in os.walk(target):
        for entry in dirs + files:
            if _reparse(Path(current) / entry):
                raise SystemExit(f"refused: reparse point under {target}")

    def retry(function, path, _info):
        os.chmod(path, stat.S_IWRITE)
        function(path)

    if sys.version_info >= (3, 12):
        shutil.rmtree(target, onexc=retry)
    else:
        shutil.rmtree(target, onerror=retry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
