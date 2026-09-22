"""Tests for the public MCP directory audit."""
from __future__ import annotations

from scripts.check_mcp_directory_listings import (
    PROFILE_ID,
    SERVER_NAME,
    expected_install_command,
    render_summary,
    validate_punkpeye,
    validate_registry,
    validate_tensorblock,
)


VERSION = "0.9.2"


def _registry_payload() -> dict:
    return {
        "servers": [
            {
                "server": {
                    "name": SERVER_NAME,
                    "version": VERSION,
                    "packages": [
                        {
                            "identifier": "mneme-hq",
                            "version": VERSION,
                            "runtimeHint": "uvx",
                            "runtimeArguments": [
                                {
                                    "type": "named",
                                    "name": "--from",
                                    "value": f"mneme-hq[mcp]=={VERSION}",
                                }
                            ],
                            "packageArguments": [
                                {"type": "positional", "value": "mneme"},
                                {"type": "positional", "value": "decision-mcp"},
                            ],
                        }
                    ],
                }
            }
        ]
    }


def test_registry_validation_checks_exact_launch_contract():
    result = validate_registry(_registry_payload(), VERSION)

    assert result.status == "pass"

    payload = _registry_payload()
    payload["servers"][0]["server"]["packages"][0]["packageArguments"].pop()
    result = validate_registry(payload, VERSION)

    assert result.status == "fail"
    assert "launch metadata" in result.detail


def test_tensorblock_accepts_current_or_unpinned_install_and_checks_tools():
    payload = {
        "id": PROFILE_ID,
        "install": {"commands": [expected_install_command(VERSION)]},
        "tools": {"names": []},
    }
    assert validate_tensorblock(payload, VERSION).status == "pass"

    payload["install"]["commands"] = [
        'uvx --from "mneme-hq[mcp]" mneme decision-mcp'
    ]
    assert validate_tensorblock(payload, VERSION).status == "pass"

    payload["install"]["commands"] = [
        'uvx --from "mneme-hq[mcp]==0.9.1" mneme decision-mcp'
    ]
    assert validate_tensorblock(payload, VERSION).status == "fail"


def test_punkpeye_open_submission_is_pending_not_failed():
    result = validate_punkpeye("# no listing yet", {"state": "open"}, VERSION)

    assert result.status == "pending"


def test_punkpeye_detects_a_stale_pinned_entry():
    entry = (
        "- [MnemeHQ/mneme](https://github.com/MnemeHQ/mneme) "
        "[badge](https://glama.ai/mcp/servers/MnemeHQ/mneme) "
        '`uvx --from "mneme-hq[mcp]==0.9.1" mneme decision-mcp`'
    )

    result = validate_punkpeye(entry, None, VERSION)

    assert result.status == "fail"
    assert "older release" in result.detail


def test_summary_calls_out_intentionally_excluded_paid_listing():
    result = validate_registry(_registry_payload(), VERSION)

    summary = render_summary([result], VERSION)

    assert "Released package version audited: `0.9.2`" in summary
    assert "mcp.so" in summary
    assert "paid/manual" in summary
