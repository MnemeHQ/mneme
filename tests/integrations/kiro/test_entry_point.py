"""Console-script availability for the Kiro hook."""
import tomllib
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[3]


def test_entry_point_target_exposes_cli_main():
    from mneme.integrations.kiro import hook

    assert callable(hook.cli_main)
    assert callable(hook.main)


def test_pyproject_declares_kiro_entry_point():
    with (PACKAGE_ROOT / "pyproject.toml").open("rb") as fh:
        scripts = tomllib.load(fh)["project"]["scripts"]
    assert scripts["mneme-kiro-hook"] == "mneme.integrations.kiro.hook:cli_main"
