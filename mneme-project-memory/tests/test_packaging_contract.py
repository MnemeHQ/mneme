"""Deterministic packaging contract for the ``mneme-hq`` distribution.

Guards the two console scripts that the Claude Code integration depends on:

    mneme      = mneme.cli:main
    mneme-hook = mneme.integrations.claude_code.hook:cli_main

The primary assertion reads the source of truth (``pyproject.toml``
``[project.scripts]``) with no build step, so it runs in the ordinary test
suite. When a built wheel is present under ``dist/`` (i.e. during a release
build) the same two entry points are verified inside the wheel's
``entry_points.txt`` as well, catching any drift between the declared metadata
and the packaged artifact.

Per ADR-009 every text read here pins ``encoding="utf-8"`` explicitly
(``tomllib`` requires binary mode, and the wheel member bytes are decoded with
an explicit codec).
"""
from __future__ import annotations

import tomllib
import zipfile
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parent.parent

# The contract: script name -> entry-point target.
EXPECTED_SCRIPTS = {
    "mneme": "mneme.cli:main",
    "mneme-hook": "mneme.integrations.claude_code.hook:cli_main",
}


def _load_pyproject_scripts() -> dict[str, str]:
    # tomllib.load requires a binary file object; no text encoding applies.
    with (PACKAGE_ROOT / "pyproject.toml").open("rb") as fh:
        data = tomllib.load(fh)
    return data["project"]["scripts"]


def test_pyproject_declares_both_console_scripts():
    scripts = _load_pyproject_scripts()
    for name, target in EXPECTED_SCRIPTS.items():
        assert scripts.get(name) == target, (
            f"[project.scripts] must declare {name} = {target!r}, "
            f"got {scripts.get(name)!r}"
        )


def test_pyproject_declares_no_unexpected_console_scripts():
    # A surprise console script is a packaging regression worth surfacing.
    assert set(_load_pyproject_scripts()) == set(EXPECTED_SCRIPTS)


def _built_wheel() -> Path | None:
    dist = PACKAGE_ROOT / "dist"
    if not dist.is_dir():
        return None
    wheels = sorted(dist.glob("mneme_hq-*.whl"))
    return wheels[-1] if wheels else None


def test_built_wheel_contains_both_console_scripts():
    """Verify the packaged artifact, not just the declaration.

    Skipped unless a wheel has been built into ``dist/`` (release flow).
    """
    wheel = _built_wheel()
    if wheel is None:
        pytest.skip("no built wheel under dist/ (run `python -m build` first)")

    with zipfile.ZipFile(wheel) as zf:
        entry_members = [n for n in zf.namelist() if n.endswith("entry_points.txt")]
        assert entry_members, f"{wheel.name} has no entry_points.txt"
        raw = zf.read(entry_members[0]).decode("utf-8")

    for name, target in EXPECTED_SCRIPTS.items():
        assert f"{name} = {target}" in raw, (
            f"{wheel.name} entry_points.txt is missing {name} = {target!r}\n"
            f"{raw}"
        )
