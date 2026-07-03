"""Deterministic packaging contract for the ``mneme-hq`` distribution.

Two layers:

1. **Source declaration** (always runs, no build): ``pyproject.toml``
   ``[project.scripts]`` declares exactly the two console scripts the Claude
   Code integration depends on::

       mneme      = mneme.cli:main
       mneme-hook = mneme.integrations.claude_code.hook:cli_main

2. **Built-artifact contract** (runs when ``dist/`` holds a build): the wheel
   and sdist are inspected directly. This is the authoritative verification of
   the packaged **name**, **version**, and **entry points** — ``pip show`` only
   reports whatever is installed in the current environment (typically the
   editable source), so it cannot prove what the artifacts contain.

Per ADR-009 every text decoded from an archive here pins ``encoding="utf-8"``
explicitly (``tomllib`` requires binary mode, and archive members are decoded
with an explicit codec).
"""
from __future__ import annotations

import configparser
import email
import tarfile
import tomllib
import zipfile
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = PACKAGE_ROOT / "dist"

PACKAGE_NAME = "mneme-hq"

# The contract: script name -> entry-point target.
EXPECTED_SCRIPTS = {
    "mneme": "mneme.cli:main",
    "mneme-hook": "mneme.integrations.claude_code.hook:cli_main",
}


def _load_pyproject() -> dict:
    # tomllib.load requires a binary file object; no text encoding applies.
    with (PACKAGE_ROOT / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)


def _declared_version() -> str:
    return _load_pyproject()["project"]["version"]


# ── Layer 1: source declaration ──────────────────────────────────────────────

def test_pyproject_declares_both_console_scripts():
    scripts = _load_pyproject()["project"]["scripts"]
    for name, target in EXPECTED_SCRIPTS.items():
        assert scripts.get(name) == target, (
            f"[project.scripts] must declare {name} = {target!r}, "
            f"got {scripts.get(name)!r}"
        )


def test_pyproject_declares_no_unexpected_console_scripts():
    # A surprise console script is a packaging regression worth surfacing.
    assert set(_load_pyproject()["project"]["scripts"]) == set(EXPECTED_SCRIPTS)


# ── Layer 2: built-artifact contract ─────────────────────────────────────────
#
# Skipped unless a matching build is present under dist/ (release flow):
#   cd mneme-project-memory
#   python -m build

def _require_dist() -> None:
    if not DIST_DIR.is_dir():
        pytest.skip("no dist/ directory (run `python -m build` first)")


def _sole_artifact(pattern: str) -> Path:
    _require_dist()
    matches = sorted(DIST_DIR.glob(pattern))
    assert len(matches) == 1, (
        f"expected exactly one artifact matching {pattern!r} under dist/, "
        f"found {[p.name for p in matches]}"
    )
    return matches[0]


def _parse_metadata(raw: str) -> email.message.Message:
    # METADATA / PKG-INFO are RFC 822 headers.
    return email.message_from_string(raw)


def test_wheel_filename_matches_declared_version():
    version = _declared_version()
    wheel = _sole_artifact(f"mneme_hq-{version}-*.whl")
    assert wheel.name.startswith(f"mneme_hq-{version}-")


def test_sdist_filename_matches_declared_version():
    version = _declared_version()
    _sole_artifact(f"mneme_hq-{version}.tar.gz")


def test_wheel_metadata_declares_name_and_version():
    version = _declared_version()
    wheel = _sole_artifact(f"mneme_hq-{version}-*.whl")
    with zipfile.ZipFile(wheel) as zf:
        members = [n for n in zf.namelist() if n.endswith(".dist-info/METADATA")]
        assert len(members) == 1, f"{wheel.name}: expected one METADATA, got {members}"
        meta = _parse_metadata(zf.read(members[0]).decode("utf-8"))
    assert meta.get("Name") == PACKAGE_NAME, f"wheel Name = {meta.get('Name')!r}"
    assert meta.get("Version") == version, f"wheel Version = {meta.get('Version')!r}"


def test_sdist_pkg_info_declares_name_and_version():
    version = _declared_version()
    sdist = _sole_artifact(f"mneme_hq-{version}.tar.gz")
    with tarfile.open(sdist, "r:gz") as tf:
        members = [n for n in tf.getnames() if n.endswith("/PKG-INFO")]
        # The top-level PKG-INFO has the shallowest path.
        members.sort(key=lambda n: n.count("/"))
        assert members, f"{sdist.name}: no PKG-INFO found"
        extracted = tf.extractfile(members[0])
        assert extracted is not None, f"{sdist.name}: cannot read {members[0]}"
        meta = _parse_metadata(extracted.read().decode("utf-8"))
    assert meta.get("Name") == PACKAGE_NAME, f"sdist Name = {meta.get('Name')!r}"
    assert meta.get("Version") == version, f"sdist Version = {meta.get('Version')!r}"


def test_wheel_entry_points_are_exactly_the_two_console_scripts():
    version = _declared_version()
    wheel = _sole_artifact(f"mneme_hq-{version}-*.whl")
    with zipfile.ZipFile(wheel) as zf:
        members = [n for n in zf.namelist() if n.endswith("entry_points.txt")]
        assert len(members) == 1, f"{wheel.name}: expected one entry_points.txt, got {members}"
        raw = zf.read(members[0]).decode("utf-8")

    parser = configparser.ConfigParser()
    parser.optionxform = str  # preserve script-name case (e.g. mneme-hook)
    parser.read_string(raw)
    assert parser.has_section("console_scripts"), (
        f"{wheel.name} entry_points.txt has no [console_scripts]:\n{raw}"
    )
    console_scripts = dict(parser.items("console_scripts"))
    assert console_scripts == EXPECTED_SCRIPTS, (
        f"{wheel.name} console_scripts = {console_scripts!r}, "
        f"expected exactly {EXPECTED_SCRIPTS!r}"
    )
