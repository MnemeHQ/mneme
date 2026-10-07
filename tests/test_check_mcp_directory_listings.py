"""Tests for the public MCP directory audit."""
from __future__ import annotations

from scripts import check_mcp_directory_listings as audit
from scripts.check_mcp_directory_listings import (
    PROFILE_ID,
    REGISTRY_NAME,
    SERVER_NAME,
    CheckResult,
    apply_policy,
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

    assert result.status == "invalid"
    assert "launch metadata" in result.detail


def test_registry_reports_a_missing_release_as_drift():
    result = validate_registry(_registry_payload(), "0.10.0")

    assert result.status == "drift"
    assert "0.9.2" in result.detail


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
    assert validate_tensorblock(payload, VERSION).status == "drift"


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

    assert result.status == "drift"
    assert "older release" in result.detail


def test_summary_calls_out_intentionally_excluded_paid_listing():
    result = validate_registry(_registry_payload(), VERSION)

    summary = render_summary([apply_policy(result)], VERSION)

    assert "Released package version audited: `0.9.2`" in summary
    assert "mcp.so" in summary
    assert "paid/manual" in summary


def _tensorblock_drift() -> CheckResult:
    payload = {
        "install": {
            "commands": ['uvx --from "mneme-hq[mcp]==0.9.2" mneme decision-mcp']
        }
    }
    return validate_tensorblock(payload, "0.10.0")


def test_policy_fails_any_registry_mismatch_or_outage():
    for status in ("drift", "invalid", "unreachable", "pending"):
        outcome = apply_policy(CheckResult(REGISTRY_NAME, status, "x", "u"))
        assert outcome.severity == "fail", status

    passed = apply_policy(validate_registry(_registry_payload(), VERSION))
    assert passed.severity == "pass"


def test_policy_warns_on_third_party_drift_and_points_to_maintenance():
    drift = _tensorblock_drift()
    assert drift.status == "drift"
    assert drift.detail == "Install metadata is stale for released version 0.10.0."

    outcome = apply_policy(drift)
    assert outcome.severity == "warning"
    assert "issues/463" in outcome.action

    untracked = apply_policy(CheckResult("Glama", "invalid", "x", "u"))
    assert untracked.severity == "warning"
    assert "maintenance owner or issue" in untracked.action


def test_policy_warns_on_http_failure_and_reports_manual_review_pending():
    unreachable = apply_policy(
        audit.unreachable("MCPhq", "u", TimeoutError("timed out"))
    )
    assert unreachable.result.status == "unreachable"
    assert unreachable.severity == "warning"

    pending = apply_policy(validate_punkpeye("# none", {"state": "open"}, VERSION))
    assert pending.severity == "pending"


def test_policy_fails_closed_on_unknown_classification():
    outcome = apply_policy(CheckResult("Glama", "fail", "x", "u"))

    assert outcome.severity == "fail"


def _run_main(monkeypatch, results: list[CheckResult], tmp_path) -> tuple[int, str]:
    monkeypatch.setattr(audit, "run_audit", lambda version: results)
    summary = tmp_path / "summary.md"
    code = audit.main(["--version", "0.10.0", "--summary", str(summary)])
    return code, summary.read_text(encoding="utf-8")


def test_main_does_not_fail_on_tensorblock_drift(monkeypatch, tmp_path, capsys):
    registry = CheckResult(REGISTRY_NAME, "pass", "ok", "u")

    code, summary = _run_main(monkeypatch, [registry, _tensorblock_drift()], tmp_path)

    assert code == 0
    assert "| WARNING | drift |" in summary
    assert "::warning title=TensorBlock::" in capsys.readouterr().out


def test_main_fails_on_registry_mismatch(monkeypatch, tmp_path, capsys):
    registry = validate_registry(_registry_payload(), "0.10.0")

    code, summary = _run_main(monkeypatch, [registry, _tensorblock_drift()], tmp_path)

    assert code == 1
    assert "| FAIL | drift |" in summary
    assert "::error title=Official MCP Registry::" in capsys.readouterr().out
