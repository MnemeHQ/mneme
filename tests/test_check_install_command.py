"""Tests for the ADR-005 install-command gate.

The gate must catch instructions to install the wrong PyPI distribution
without flagging the many legitimate uses of the bare word `mneme`, which is
the import root, the CLI name, and a common local directory name.
"""
import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_install_command.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_install_command", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = _load()


def _flagged(line: str) -> bool:
    match = gate.VIOLATION.search(line)
    if not match:
        return False
    if any(f in gate.EDITABLE_FLAGS for f in match.group("flags").split()):
        return False
    return gate.CORRECT not in line


@pytest.mark.parametrize("line", [
    "pip install mneme",
    "**Install:** `pip install mneme`",
    "pipx install mneme",
    "uv pip install mneme",
    "      - run: pip install mneme",
    "pip install --upgrade mneme",
    "    - pip install mneme",
])
def test_flags_wrong_distribution(line):
    assert _flagged(line), f"should have been flagged: {line!r}"


@pytest.mark.parametrize("line", [
    "pip install mneme-hq",
    'pipx install "mneme-hq>=0.5.0"',
    # Editable installs take a local directory path, not a distribution name.
    "pip install -e mneme   # local checkout",
    "pip install --editable mneme",
    "pipx install ./mneme",
    # ADR-005's own correct-vs-forbidden table must keep naming both forms.
    "| pip install command | `pip install mneme-hq` | `pip install mneme` |",
    # `mneme` as CLI / import root / unrelated identifier.
    "mneme check --mode warn",
    "python -m mneme check",
    "pip install mneme_hq",
    "pip install mnemex",
])
def test_does_not_flag_legitimate_usage(line):
    assert not _flagged(line), f"false positive: {line!r}"


def test_allowlist_covers_historical_plans():
    assert gate.is_allowlisted("docs/plans/2026-05-03-mneme-for-claude-code.md")


def test_allowlist_does_not_cover_user_docs():
    assert gate.is_allowlisted("docs/qa-glossary.md") is None


def test_allowlist_covers_test_fixtures():
    assert gate.is_allowlisted("tests/test_enforcer.py")
    assert gate.is_allowlisted("tests/fixtures/adrs_literal/ADR-201.md")


def test_allowlist_covers_only_the_canonical_policy_memory_file():
    assert gate.is_allowlisted(".mneme/project_memory.json")
    assert gate.is_allowlisted("examples/project_memory.json") is None
    assert gate.is_allowlisted(".mneme/other.json") is None


def test_exact_typed_rule_declaration_is_exempt_only_in_adr_sources():
    line = "- FORBID_LITERAL: pip install mneme"
    match = gate.VIOLATION.search(line)
    assert match is not None
    assert gate.is_declaring_typed_rule("docs/adr/ADR-005.md", line, match)
    assert not gate.is_declaring_typed_rule("README.md", line, match)


def test_typed_rule_declaration_must_match_the_entire_value():
    line = "- FORBID_LITERAL: pip install mneme in tutorials"
    match = gate.VIOLATION.search(line)
    assert match is not None
    assert not gate.is_declaring_typed_rule("docs/adr/ADR-005.md", line, match)


def test_allowlist_covers_the_gate_itself():
    """The gate must name the forbidden form to detect and explain it.

    Regression: this was missed because `git ls-files` skips untracked files,
    so the gate passed locally and only failed once its own source and tests
    were committed.
    """
    assert gate.is_allowlisted("scripts/check_install_command.py")
    assert gate.is_allowlisted("tests/test_check_install_command.py")


def test_repo_is_clean():
    """The gate must pass on the repository as committed."""
    findings = gate.scan(gate.tracked_files())
    assert findings == [], (
        "ADR-005 violations present:\n"
        + "\n".join(f"  {p}:{n}: {ln}" for p, n, ln in findings)
    )
