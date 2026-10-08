"""Audit Mneme's public MCP registry and directory listings.

Validation and policy are separate. Validators report what each listing
truthfully says, as one semantic classification:

- ``pass``: the listing matches the released version and launch contract;
- ``drift``: the listing is valid but describes an older release;
- ``invalid``: the listing is missing or contradicts Mneme's identity/metadata;
- ``pending``: a submission is awaiting manual review upstream;
- ``unreachable``: the listing could not be fetched (HTTP/network error).

``apply_policy`` then decides what blocks. The Official MCP Registry is the
release contract and fails closed on anything but ``pass``. Third-party drift
or invalid metadata is a warning that needs a maintenance owner or issue,
unreachable third-party listings warn, and manual-review listings are pending.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SERVER_NAME = "io.github.MnemeHQ/mneme"
PROFILE_ID = "github-mnemehq-mneme-763aeb8b"
TOOLS = (
    "decision.propose",
    "decision.propose_batch",
    "decision.get",
    "decision.search",
    "decision.applicable_to",
    "decision.trace",
)

PYPI_URL = "https://pypi.org/pypi/mneme-hq/json"
REGISTRY_URL = (
    "https://registry.modelcontextprotocol.io/v0.1/servers?search="
    + urllib.parse.quote(SERVER_NAME, safe="")
)
GLAMA_URL = "https://glama.ai/mcp/servers/MnemeHQ/mneme"
MCPSERVERS_URL = "https://mcpservers.org/servers/mnemehq/mneme"
TENSORBLOCK_URL = f"https://mcp-index.tensorblock.co/v1/servers/{PROFILE_ID}"
MCPHQ_URL = "https://mcphq.ai/mcp/mnemehq-mneme"
MCPREPOSITORY_URL = "https://mcprepository.com/mnemehq/mneme"
MCPNAV_URL = "https://mcpnav.dev/servers/mnemehq/mneme/"
RONINFORGE_URL = (
    "https://roninforge.org/data/state-of-mcp/servers/"
    f"{SERVER_NAME}/"
)
PUNKPEYE_README_URL = (
    "https://raw.githubusercontent.com/punkpeye/awesome-mcp-servers/main/README.md"
)
PUNKPEYE_PR_URL = (
    "https://api.github.com/repos/punkpeye/awesome-mcp-servers/pulls/14788"
)

REGISTRY_NAME = "Official MCP Registry"
# Known third-party maintenance records. A listing without one still warns,
# but its warning asks for an owner or issue to be recorded.
MAINTENANCE_TRACKERS = {
    "TensorBlock": "https://github.com/MnemeHQ/mneme/issues/463",
    "MCPhq": "https://github.com/mcpHQ/awesome-mcp-servers/issues/145",
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str  # semantic classification; see the module docstring
    detail: str
    url: str


@dataclass(frozen=True)
class PolicyOutcome:
    result: CheckResult
    severity: str  # pass | warning | pending | fail
    action: str = ""


def _request(url: str, *, attempts: int = 1, delay: float = 0.0) -> bytes:
    headers = {
        "Accept": "application/json, text/plain, text/html;q=0.9, */*;q=0.8",
        "User-Agent": "Mneme-MCP-directory-audit/1.0",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"

    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=headers), timeout=30
            ) as response:
                return response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(delay)
    assert last_error is not None
    raise last_error


def fetch_json(url: str, *, attempts: int = 1, delay: float = 0.0) -> dict[str, Any]:
    return json.loads(_request(url, attempts=attempts, delay=delay).decode("utf-8"))


def fetch_text(url: str) -> str:
    return _request(url).decode("utf-8", errors="replace")


def expected_install_command(version: str) -> str:
    return f'uvx --from "mneme-hq[mcp]=={version}" mneme decision-mcp'


def _install_is_current(command: str, version: str) -> bool:
    return command in {
        expected_install_command(version),
        'uvx --from "mneme-hq[mcp]" mneme decision-mcp',
    }


def validate_registry(payload: dict[str, Any], version: str) -> CheckResult:
    matches = [
        item["server"]
        for item in payload.get("servers", [])
        if item.get("server", {}).get("name") == SERVER_NAME
    ]
    server = next((item for item in matches if item.get("version") == version), None)
    if server is None:
        versions = ", ".join(sorted({item.get("version", "?") for item in matches}))
        return CheckResult(
            REGISTRY_NAME,
            "drift",
            f"Expected {version}; published versions found: {versions or 'none'}.",
            REGISTRY_URL,
        )

    packages = server.get("packages", [])
    package = next(
        (item for item in packages if item.get("identifier") == "mneme-hq"), None
    )
    if package is None or package.get("version") != version:
        return CheckResult(
            REGISTRY_NAME,
            "invalid",
            "The PyPI package identity or version is missing from the Registry record.",
            REGISTRY_URL,
        )

    runtime_arguments = package.get("runtimeArguments", [])
    package_arguments = package.get("packageArguments", [])
    expected_runtime = [
        {"type": "named", "name": "--from", "value": f"mneme-hq[mcp]=={version}"}
    ]
    expected_package = [
        {"type": "positional", "value": "mneme"},
        {"type": "positional", "value": "decision-mcp"},
    ]
    if (
        package.get("runtimeHint") != "uvx"
        or runtime_arguments != expected_runtime
        or package_arguments != expected_package
    ):
        return CheckResult(
            REGISTRY_NAME,
            "invalid",
            "The Registry launch metadata no longer matches the supported MCP command.",
            REGISTRY_URL,
        )

    return CheckResult(
        REGISTRY_NAME,
        "pass",
        f"Version {version} and its exact uvx launch contract are published.",
        REGISTRY_URL,
    )


def validate_tensorblock(payload: dict[str, Any], version: str) -> CheckResult:
    commands = payload.get("install", {}).get("commands", [])
    if not any(_install_is_current(command, version) for command in commands):
        return CheckResult(
            "TensorBlock",
            "drift",
            f"Install metadata is stale for released version {version}.",
            TENSORBLOCK_URL,
        )

    names = set(payload.get("tools", {}).get("names", []))
    if names and names != set(TOOLS):
        return CheckResult(
            "TensorBlock",
            "invalid",
            "Published tool names differ from Mneme's frozen six-tool MCP surface.",
            TENSORBLOCK_URL,
        )

    detail = f"Install metadata is current for {version}."
    if not names:
        detail += " Tool enrichment is still pending upstream review."
    return CheckResult("TensorBlock", "pass", detail, TENSORBLOCK_URL)


def validate_punkpeye(
    readme: str, pull_request: dict[str, Any] | None, version: str
) -> CheckResult:
    entry = next(
        (line for line in readme.splitlines() if "MnemeHQ/mneme" in line), None
    )
    if entry is None:
        if pull_request and pull_request.get("state") == "open":
            return CheckResult(
                "punkpeye/awesome-mcp-servers",
                "pending",
                "Submission PR #14788 is open and its Glama check has passed.",
                "https://github.com/punkpeye/awesome-mcp-servers/pull/14788",
            )
        return CheckResult(
            "punkpeye/awesome-mcp-servers",
            "invalid",
            "Mneme is absent and submission PR #14788 is not open.",
            "https://github.com/punkpeye/awesome-mcp-servers/pull/14788",
        )

    if 'mneme-hq[mcp]==' in entry and expected_install_command(version) not in entry:
        return CheckResult(
            "punkpeye/awesome-mcp-servers",
            "drift",
            f"The static entry pins an older release than {version}.",
            PUNKPEYE_README_URL,
        )
    if "glama.ai/mcp/servers/MnemeHQ/mneme" not in entry:
        return CheckResult(
            "punkpeye/awesome-mcp-servers",
            "invalid",
            "The Mneme entry is missing its required Glama score badge/link.",
            PUNKPEYE_README_URL,
        )
    return CheckResult(
        "punkpeye/awesome-mcp-servers",
        "pass",
        "The curated-list entry and Glama badge are present.",
        PUNKPEYE_README_URL,
    )


def validate_roninforge(text: str) -> CheckResult:
    return validate_page(
        "RoninForge/Akashi",
        RONINFORGE_URL,
        text,
        (SERVER_NAME,),
    )


def validate_page(name: str, url: str, text: str, fragments: tuple[str, ...]) -> CheckResult:
    missing = [fragment for fragment in fragments if fragment.lower() not in text.lower()]
    if missing:
        return CheckResult(
            name,
            "invalid",
            "Listing loaded but is missing expected identity: " + ", ".join(missing),
            url,
        )
    return CheckResult(name, "pass", "Listing is reachable and identifies Mneme correctly.", url)


def unreachable(name: str, url: str, exc: Exception) -> CheckResult:
    return CheckResult(
        name, "unreachable", f"Could not verify due to external HTTP error: {exc}", url
    )


def apply_policy(result: CheckResult) -> PolicyOutcome:
    """Decide how a validator's classification affects the workflow."""
    if result.status == "pass":
        return PolicyOutcome(result, "pass")
    if result.name == REGISTRY_NAME:
        return PolicyOutcome(
            result,
            "fail",
            "The Official MCP Registry is the release contract; republish server.json.",
        )
    if result.status == "pending":
        return PolicyOutcome(result, "pending", "Awaiting upstream manual review.")
    if result.status == "unreachable":
        return PolicyOutcome(
            result, "warning", "External outage; re-run the audit later."
        )
    if result.status in {"drift", "invalid"}:
        tracker = MAINTENANCE_TRACKERS.get(result.name)
        action = (
            f"Third-party listing; maintenance tracked in {tracker}."
            if tracker
            else "Third-party listing; record a maintenance owner or issue."
        )
        return PolicyOutcome(result, "warning", action)
    # An unknown classification is a bug in this script, so fail closed.
    return PolicyOutcome(
        result, "fail", f"Unknown audit classification: {result.status!r}."
    )


def render_summary(outcomes: list[PolicyOutcome], version: str) -> str:
    lines = [
        "## MCP directory maintenance",
        "",
        f"Released package version audited: `{version}`",
        "",
        "| Listing | Status | Finding | Detail |",
        "| --- | --- | --- | --- |",
    ]
    for outcome in outcomes:
        result = outcome.result
        detail = " ".join(part for part in (result.detail, outcome.action) if part)
        detail = detail.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| [{result.name}]({result.url}) | {outcome.severity.upper()} "
            f"| {result.status} | {detail} |"
        )
    lines.extend(
        [
            "",
            "Policy: an Official MCP Registry mismatch fails; third-party drift or "
            "invalid metadata warns and needs a maintenance owner or issue; HTTP "
            "failures warn; manual-review listings are pending.",
            "",
            "`mcp.so` is intentionally excluded: MnemeHQ has no listing there and its submission path is paid/manual.",
        ]
    )
    return "\n".join(lines) + "\n"


def run_audit(version: str) -> list[CheckResult]:
    results: list[CheckResult] = []

    try:
        results.append(validate_registry(fetch_json(REGISTRY_URL, attempts=6, delay=10), version))
    except Exception as exc:  # apply_policy fails the canonical source closed
        results.append(unreachable(REGISTRY_NAME, REGISTRY_URL, exc))

    try:
        text = fetch_text(GLAMA_URL)
        result = validate_page(
            "Glama", GLAMA_URL, text, ("Mneme Decision MCP", "decision.propose")
        )
        results.append(result)
    except Exception as exc:
        results.append(unreachable("Glama", GLAMA_URL, exc))

    try:
        text = fetch_text(MCPSERVERS_URL)
        results.append(
            validate_page(
                "mcpservers.org", MCPSERVERS_URL, text, ("Mneme Decision MCP",)
            )
        )
    except Exception as exc:
        results.append(unreachable("mcpservers.org", MCPSERVERS_URL, exc))

    try:
        results.append(validate_tensorblock(fetch_json(TENSORBLOCK_URL), version))
    except Exception as exc:
        results.append(unreachable("TensorBlock", TENSORBLOCK_URL, exc))

    try:
        readme = fetch_text(PUNKPEYE_README_URL)
        pull_request: dict[str, Any] | None = None
        if "MnemeHQ/mneme" not in readme:
            try:
                pull_request = fetch_json(PUNKPEYE_PR_URL)
            except Exception:
                pass
        results.append(validate_punkpeye(readme, pull_request, version))
    except Exception as exc:
        results.append(unreachable("punkpeye/awesome-mcp-servers", PUNKPEYE_README_URL, exc))

    try:
        text = fetch_text(MCPHQ_URL)
        result = validate_page("MCPhq", MCPHQ_URL, text, ("Mneme Decision MCP",))
        if result.status == "pass" and expected_install_command(version) not in text:
            result = CheckResult(
                "MCPhq",
                "invalid",
                "Listing is live, but its generated install command omits the MCP extra/subcommand.",
                MCPHQ_URL,
            )
        results.append(result)
    except Exception as exc:
        results.append(unreachable("MCPhq", MCPHQ_URL, exc))

    try:
        text = fetch_text(MCPNAV_URL)
        results.append(
            validate_page(
                "MCPNav",
                MCPNAV_URL,
                text,
                ("Mneme Decision MCP", "MnemeHQ/mneme"),
            )
        )
    except Exception as exc:
        results.append(unreachable("MCPNav", MCPNAV_URL, exc))

    try:
        text = fetch_text(MCPREPOSITORY_URL)
        results.append(
            validate_page(
                "MCP Repository",
                MCPREPOSITORY_URL,
                text,
                ("Mneme", "MnemeHQ"),
            )
        )
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            results.append(
                CheckResult(
                    "MCP Repository",
                    "pending",
                    "The accepted submission is still processing.",
                    MCPREPOSITORY_URL,
                )
            )
        else:
            results.append(unreachable("MCP Repository", MCPREPOSITORY_URL, exc))
    except Exception as exc:
        results.append(unreachable("MCP Repository", MCPREPOSITORY_URL, exc))

    try:
        results.append(validate_roninforge(fetch_text(RONINFORGE_URL)))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            results.append(
                CheckResult(
                    "RoninForge/Akashi",
                    "pending",
                    "Mneme is not present in the latest published State of MCP census yet.",
                    RONINFORGE_URL,
                )
            )
        else:
            results.append(unreachable("RoninForge/Akashi", RONINFORGE_URL, exc))
    except Exception as exc:
        results.append(unreachable("RoninForge/Akashi", RONINFORGE_URL, exc))

    return results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        help="Released mneme-hq version. Defaults to the current PyPI release.",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        help="Append a Markdown report to this file (for GITHUB_STEP_SUMMARY).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    version = args.version
    if not version:
        try:
            version = fetch_json(PYPI_URL, attempts=3, delay=5)["info"]["version"]
        except Exception as exc:
            print(f"::error::Could not determine the released PyPI version: {exc}")
            return 1

    outcomes = [apply_policy(result) for result in run_audit(version)]
    summary = render_summary(outcomes, version)
    print(summary)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as handle:
            handle.write(summary)

    for outcome in outcomes:
        name = outcome.result.name
        message = " ".join(
            part for part in (outcome.result.detail, outcome.action) if part
        )
        if outcome.severity == "fail":
            print(f"::error title={name}::{message}")
        elif outcome.severity == "warning":
            print(f"::warning title={name}::{message}")
        elif outcome.severity == "pending":
            print(f"::notice title={name}::{message}")
    return 1 if any(outcome.severity == "fail" for outcome in outcomes) else 0


if __name__ == "__main__":
    sys.exit(main())
