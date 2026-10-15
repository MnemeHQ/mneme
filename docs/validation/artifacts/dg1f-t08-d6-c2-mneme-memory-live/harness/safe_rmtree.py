"""The only recursive deletion in the D6 harness, confined to the disposable root.

usage:
  safe_rmtree.py check-root          verify the disposable root is safe to use
  safe_rmtree.py delete <probe>      delete <root>/<probe> (allowlisted names only)

Fails closed (exit 3, nothing deleted) unless every condition holds:
  - <probe> is exactly one of PROBES (no prefix match, no case folding);
  - the root is exactly ROOT and neither it nor any ancestor is a reparse point
    (symlink or junction), so the root cannot be redirected;
  - the target is not itself a reparse point, its real path's parent is the
    root's real path, and it is not inside C:\\dev\\mneme;
  - no entry anywhere under the target is a reparse point (checked before any
    deletion, without following links), so nothing can lead the walk outside.
A missing target is a no-op (exit 0).
"""
import os
import shutil
import stat
import sys

ROOT = r"C:\dev\t08-d6-live"
# D6 batch 2 (C2) probe directories only. The C1 directories (D6-R0-control,
# D6-R2-counterfactual, D6-C1-V5, D6-C1-V4) are deliberately NOT listed, so this
# harness can never delete batch-1 evidence.
PROBES = ("D6-C2-R0-control", "D6-C2-R2-counterfactual", "D6-C2-V5", "D6-C2-V4",
          "D6-C2-V5-own", "D6-C2-V4-own")
PROTECTED = (r"C:\dev\mneme",)
_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def refuse(msg):
    print(f"safe_rmtree: REFUSED: {msg}", file=sys.stderr)
    sys.exit(3)


def norm(p):
    return os.path.normcase(os.path.normpath(p))


def is_reparse(p):
    st = os.lstat(p)
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & _REPARSE)


def within(child, parent):
    child, parent = norm(child), norm(parent)
    return child == parent or child.startswith(parent.rstrip("\\/") + os.sep)


def check_root():
    if norm(os.path.abspath(ROOT)) != norm(ROOT):
        refuse("root is not absolute")
    p = ROOT
    while True:
        if os.path.lexists(p) and is_reparse(p):
            refuse(f"root or ancestor is a reparse point: {p}")
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    if os.path.lexists(ROOT) and norm(os.path.realpath(ROOT)) != norm(ROOT):
        refuse("root real path differs from pinned root")
    for prot in PROTECTED:
        if within(ROOT, prot) or within(prot, ROOT):
            refuse(f"root overlaps protected tree {prot}")


def delete(name):
    if name not in PROBES:
        refuse(f"probe name not in allowlist: {name!r}")
    check_root()
    target = os.path.join(ROOT, name)
    if not os.path.lexists(target):
        return
    if is_reparse(target):
        refuse(f"target is a reparse point: {target}")
    real = os.path.realpath(target)
    if norm(os.path.dirname(real)) != norm(os.path.realpath(ROOT)) or norm(real) != norm(target):
        refuse(f"target resolves outside root: {real}")
    for prot in PROTECTED:
        if within(real, prot):
            refuse(f"target inside protected tree {prot}")
    if not os.path.isdir(target):
        refuse(f"target is not a directory: {target}")
    for dirpath, dirnames, filenames in os.walk(target, followlinks=False):
        for entry in dirnames + filenames:
            if is_reparse(os.path.join(dirpath, entry)):
                refuse(f"reparse point inside target: {os.path.join(dirpath, entry)}")

    def onexc(func, path, exc):  # git object files are read-only on Windows
        if not is_reparse(path) and within(path, target):
            os.chmod(path, stat.S_IWRITE)
            func(path)
        else:
            raise exc

    shutil.rmtree(target, onexc=onexc)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "check-root":
        check_root()
    elif len(sys.argv) == 3 and sys.argv[1] == "delete":
        delete(sys.argv[2])
    else:
        refuse(f"bad arguments: {sys.argv[1:]!r}")
