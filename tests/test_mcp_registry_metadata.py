"""Contract tests for public MCP Registry metadata."""
from __future__ import annotations

import json
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_NAME = "io.github.MnemeHQ/mneme"
SCHEMA_URL = "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"


def _load_server_manifest() -> dict:
    return json.loads((REPO_ROOT / "server.json").read_text(encoding="utf-8"))


def _load_project() -> dict:
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)["project"]


def test_registry_name_matches_pypi_readme_ownership_marker():
    manifest = _load_server_manifest()
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert manifest["$schema"] == SCHEMA_URL
    assert manifest["name"] == SERVER_NAME
    assert f"<!-- mcp-name: {SERVER_NAME} -->" in readme
    assert 1 <= len(manifest["description"]) <= 100


def test_registry_package_identity_and_version_match_project_metadata():
    manifest = _load_server_manifest()
    project = _load_project()

    assert manifest["version"] == project["version"]

    packages = manifest["packages"]
    assert len(packages) == 1
    package = packages[0]

    assert package["registryType"] == "pypi"
    assert package["registryBaseUrl"] == "https://pypi.org"
    assert package["identifier"] == project["name"]
    assert package["version"] == project["version"]
    assert package["transport"] == {"type": "stdio"}


def test_registry_launch_preserves_optional_mcp_extra_and_cli_namespace():
    manifest = _load_server_manifest()
    project = _load_project()
    package = manifest["packages"][0]
    version = project["version"]

    assert package["runtimeHint"] == "uvx"
    assert package["runtimeArguments"] == [
        {
            "type": "named",
            "name": "--from",
            "value": f"mneme-hq[mcp]=={version}",
        }
    ]
    assert package["packageArguments"] == [
        {"type": "positional", "value": "mneme"},
        {"type": "positional", "value": "decision-mcp"},
    ]


def test_registry_manifest_keeps_protocol_separate_from_authority():
    description = _load_server_manifest()["description"].lower()

    assert "non-authoritative" in description
