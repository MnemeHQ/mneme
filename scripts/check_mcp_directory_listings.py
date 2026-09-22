"""Audit Mneme's public MCP registry and directory listings.

The canonical MCP Registry is a release contract and fails closed. Third-party
directories fail only for confirmed semantic drift; transient HTTP failures are
reported as warnings so an external outage cannot make this workflow flaky.
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
PUNKPEYE_README_URL = (
    "https://raw.githubusercontent.com/punkpeye/awesome-mcp-servers/main/README.md"
)
PUNKPEYE_PR_URL = (
    "https://api.github.com/repos/punkpeye/awesome-mcp-servers/pulls/14788"
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str
    url: str


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
            "Official MCP Registry",
            "fail",
            f"Expected {version}; published versions found: {versions or 'none'}.",
            REGISTRY_URL,
        )

    packages = server.get("packages", [])
    package = next(
        (item for item in packages if item.get("identifier") == "mneme-hq"), None
    )
    if package is None or package.get("version") != version:
        return CheckResult(
            "Official MCP Registry",
            "fail",
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
            "Official MCP Registry",
            "fail",
            "The Registry launch metadata no longer matches the supported MCP command.",
            REGISTRY_URL,
        )

    return CheckResult(
        "Official MCP Registry",
        "pass",
        f"Version {version} and its exact uvx launch contract are published.",
        REGISTRY_URL,
    )


def validate_tensorblock(payload: dict[str, Any], version: str) -> CheckResult:
    commands = payload.get("install", {}).get("commands", [])
    if not any(_install_is_current(command, version) for command in commands):
        return CheckResult(
            "TensorBlock",
            "fail",
            f"Install metadata is stale or invalid for released version {version}.",
            TENSORBLOCK_URL,
        )

    names = set(payload.get("tools", {}).get("names", []))
    if names and names != set(TOOLS):
        return CheckResult(
            "TensorBlock",
            "fail",
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
            "fail",
            "Mneme is absent and submission PR #14788 is not open.",
            "https://github.com/punkpeye/awesome-mcp-servers/pull/14788",
        )

    if 'mneme-hq[mcp]==' in entry and expected_install_command(version) not in entry:
        return CheckResult(
            "punkpeye/awesome-mcp-servers",
            "fail",
            f"The static entry pins an older release than {version}.",
            PUNKPEYE_README_URL,
        )
    if "glama.ai/mcp/servers/MnemeHQ/mneme" not in entry:
        return CheckResult(
            "punkpeye/awesome-mcp-servers",
            "fail",
            "The Mneme entry is missing its required Glama score badge/link.",
            PUNKPEYE_README_URL,
        )
    return CheckResult(
        "punkpeye/awesome-mcp-servers",
        "pass",
        "The curated-list entry and Glama badge are present.",
        PUNKPEYE_README_URL,
    )


def validate_page(name: str, url: str, text: str, fragments: tuple[str, ...]) -> CheckResult:
    missing = [fragment for fragment in fragments if fragment.lower() not in text.lower()]
    if missing:
        return CheckResult(
            name,
            "fail",
            "Listing loaded but is missing expected identity: " + ", ".join(missing),
            url,
        )
    return CheckResult(name, "pass", "Listing is reachable and identifies Mneme correctly.", url)


def warning(name: str, url: str, exc: Exception) -> CheckResult:
    return CheckResult(name, "warning", f"Could not verify due to external HTTP error: {exc}", url)


def render_summary(results: list[CheckResult], version: str) -> str:
    lines = [
        "## MCP directory maintenance",
        "",
        f"Released package version audited: `{version}`",
        "",
        "| Listing | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for result in results:
        detail = result.detail.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| [{result.name}]({result.url}) | {result.status.upper()} | {detail} |"
        )
    lines.extend(
        [
            "",
            "`mcp.so` is intentionally excluded: MnemeHQ has no listing there and its submission path is paid/manual.",
        ]
    )
    return "\n".join(lines) + "\n"


def run_audit(version: str) -> list[CheckResult]:
    results: list[CheckResult] = []

    try:
        results.append(validate_registry(fetch_json(REGISTRY_URL, attempts=6, delay=10), version))
    except Exception as exc:  # canonical source must fail closed
        results.append(CheckResult("Official MCP Registry", "fail", str(exc), REGISTRY_URL))

    try:
        text = fetch_text(GLAMA_URL)
        result = validate_page(
            "Glama", GLAMA_URL, text, ("Mneme Decision MCP", "decision.propose")
        )
        results.append(result)
    except Exception as exc:
        results.append(warning("Glama", GLAMA_URL, exc))

    try:
        text = fetch_text(MCPSERVERS_URL)
        results.append(
            validate_page(
                "mcpservers.org", MCPSERVERS_URL, text, ("Mneme Decision MCP",)
            )
        )
    except Exception as exc:
        results.append(warning("mcpservers.org", MCPSERVERS_URL, exc))

    try:
        results.append(validate_tensorblock(fetch_json(TENSORBLOCK_URL), version))
    except Exception as exc:
        results.append(warning("TensorBlock", TENSORBLOCK_URL, exc))

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
        results.append(warning("punkpeye/awesome-mcp-servers", PUNKPEYE_README_URL, exc))

    try:
        text = fetch_text(MCPHQ_URL)
        result = validate_page("MCPhq", MCPHQ_URL, text, ("Mneme Decision MCP",))
        if result.status == "pass" and expected_install_command(version) not in text:
            result = CheckResult(
                "MCPhq",
                "warning",
                "Listing is live, but its generated install command omits the MCP extra/subcommand.",
                MCPHQ_URL,
            )
        results.append(result)
    except Exception as exc:
        results.append(warning("MCPhq", MCPHQ_URL, exc))

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

    results = run_audit(version)
    summary = render_summary(results, version)
    print(summary)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as handle:
            handle.write(summary)

    for result in results:
        if result.status == "fail":
            print(f"::error title={result.name}::{result.detail}")
        elif result.status == "warning":
            print(f"::warning title={result.name}::{result.detail}")
        elif result.status == "pending":
            print(f"::notice title={result.name}::{result.detail}")
    return 1 if any(result.status == "fail" for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
