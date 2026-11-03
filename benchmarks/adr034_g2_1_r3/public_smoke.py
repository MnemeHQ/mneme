"""Independent verification of R3's separately sealed PUBLIC smoke tar.

Frozen #703 contains 150 concealed cases in one archive and 14 public cases
(one per class) in another. Never merge their manifests. The public tar is
verified against its pre-registered SHA-256, complete internal manifest,
and public-only class inventory before the concealed corpus can claim PASS.
No concealed file or implementation output is involved in this check.
"""

from __future__ import annotations

import hashlib
import json
import re
import tarfile
from pathlib import Path, PurePosixPath

from . import contract as C


def _invalid(reason: str) -> dict:
    return {"verified": False, "reason": reason, "public_cases": 0, "classes": []}


def verify(archive: Path, expected_sha256: str = C.PUBLIC_SMOKE_SHA256) -> dict:
    """Metadata-only attestation, with failure codes and no case contents."""
    archive = Path(archive)
    try:
        archive_digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    except OSError:
        return _invalid("public_tar_missing_or_unreadable")
    if archive_digest != expected_sha256:
        return _invalid("public_tar_digest_mismatch")

    try:
        with tarfile.open(archive, mode="r:") as tf:
            contents: dict[str, bytes] = {}
            roots: set[str] = set()
            for member in tf.getmembers():
                path = member.name.rstrip("/")
                parts = path.split("/")
                if (not path or path.startswith("/") or "\\" in path or
                        any(part in ("", ".", "..") for part in parts) or
                        not (member.isdir() or member.isfile())):
                    return _invalid("public_tar_member_unsafe")
                roots.add(parts[0])
                if member.isfile():
                    if path in contents:
                        return _invalid("public_tar_duplicate_member")
                    stream = tf.extractfile(member)
                    if stream is None:
                        return _invalid("public_tar_unreadable_member")
                    contents[path] = stream.read()
            if len(roots) != 1:
                return _invalid("public_tar_multiple_roots")
            root = next(iter(roots))
            manifest_name = f"{root}/MANIFEST.sha256"
            manifest = contents.pop(manifest_name, None)
            if manifest is None:
                return _invalid("public_manifest_missing")
            try:
                entries = manifest.decode("utf-8").splitlines()
            except UnicodeError:
                return _invalid("public_manifest_invalid")
            checks: dict[str, str] = {}
            for line in entries:
                m = re.fullmatch(r"([0-9a-f]{64}) [ *](.+)", line)
                if not m:
                    return _invalid("public_manifest_invalid")
                digest, name = m.groups()
                bits = name.split("/")
                if (name.startswith("/") or "\\" in name or
                        any(x in ("", ".", "..") for x in bits) or name in checks):
                    return _invalid("public_manifest_invalid")
                checks[name] = digest
            names = {name[len(root)+1:]: blob for name, blob in contents.items()
                     if name.startswith(root + "/")}
            if set(names) != set(checks):
                return _invalid("public_manifest_incomplete_inventory")
            for name, digest in checks.items():
                if hashlib.sha256(names[name]).hexdigest() != digest:
                    return _invalid("public_manifest_digest_mismatch")
            case_names = [name for name in sorted(names) if name.endswith("/case.json")]
            if len(case_names) != len(C.CLASS_FLOORS):
                return _invalid("public_case_count")
            classes: list[str] = []
            ids: list[str] = []
            for name in case_names:
                try:
                    obj = json.loads(names[name].decode("utf-8"))
                except (ValueError, UnicodeError):
                    return _invalid("public_case_invalid")
                if (not isinstance(obj, dict) or obj.get("schema") != C.CASE_SCHEMA or
                        obj.get("visibility") != "public" or
                        not isinstance(obj.get("case_id"), str) or
                        obj.get("cls") not in C.CLASS_FLOORS):
                    return _invalid("public_case_invalid")
                classes.append(obj["cls"])
                ids.append(obj["case_id"])
            if set(classes) != set(C.CLASS_FLOORS) or len(set(ids)) != len(ids):
                return _invalid("public_class_inventory")
            return {"verified": True, "sha256": archive_digest,
                    "public_cases": len(case_names), "classes": sorted(classes)}
    except (tarfile.TarError, EOFError, OSError, ValueError, OverflowError):
        return _invalid("public_tar_invalid")
