"""Tests for the Add File-only Codex apply_patch parser (M1b).

Runs against the frozen R0 fixtures (see test_patch_contract.py) plus focused
malformed cases. The governing invariant: the parser never silently ignores an
operation it does not understand -- unsupported grammar is an explicit
CodexPatchParseError, so a partially parsed proposal can never be treated as
governed.
"""
import json

import pytest

from mneme.integrations.codex_cli.patch_parser import (
    CodexPatchParseError,
    parse_patch,
    parse_pretooluse_payload,
)

FIXTURES = (
    __import__("pathlib").Path(__file__).resolve().parent / "fixtures"
)

EXPECTED = ("probe_target.py", "def probe_marker() -> int:\n    return 42\n")


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# --- Frozen fixtures -------------------------------------------------------


def test_frozen_allow_payload_parses_to_expected():
    assert parse_pretooluse_payload(
        _fixture("pretooluse_applypatch_addfile_allow.json")
    ) == EXPECTED


def test_frozen_deny_payload_parses_identically():
    """Same proposal reached the hook in both arms; extraction must match."""
    assert parse_pretooluse_payload(
        _fixture("pretooluse_applypatch_addfile_deny.json")
    ) == EXPECTED


# --- Contract-mandated rejections ------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["malformed_missing_command.json", "malformed_missing_markers.json"],
)
def test_malformed_fixtures_fail_deterministically(name):
    with pytest.raises(CodexPatchParseError):
        parse_pretooluse_payload(_fixture(name))


# --- Payload-level rejection -------------------------------------------------


def test_missing_tool_input_command_rejected():
    with pytest.raises(CodexPatchParseError, match="no tool_input.command"):
        parse_pretooluse_payload({"tool_name": "apply_patch", "tool_input": {}})


def test_non_apply_patch_tool_rejected():
    with pytest.raises(CodexPatchParseError, match="apply_patch"):
        parse_pretooluse_payload(
            {"tool_name": "Bash", "tool_input": {"command": "*** Begin Patch\n*** End Patch"}}
        )


def test_null_payload_rejected():
    with pytest.raises(CodexPatchParseError):
        parse_pretooluse_payload(None)


# --- Patch-level rejection: unsupported operations ---------------------------


def _wrap(body):
    return f"*** Begin Patch\n{body}\n*** End Patch"


@pytest.mark.parametrize(
    "body,why",
    [
        ("*** Update File: app.py\n@@ context @@", "Update File"),
        ("*** Delete File: app.py", "Delete File"),
        (
            "*** Add File: a.py\n+hi\n*** Add File: b.py\n+there",
            "multi-operation",
        ),
        ("*** Move To: elsewhere.py", "unknown operation"),
    ],
)
def test_unsupported_operations_fail_explicitly(body, why):
    with pytest.raises(CodexPatchParseError):
        parse_patch(_wrap(body))


def test_update_file_error_names_the_operation():
    with pytest.raises(CodexPatchParseError, match="Update File"):
        parse_patch(_wrap("*** Update File: app.py\n@@ -1 +1 @@"))


def test_multi_operation_error_lists_all_operations():
    body = "*** Add File: a.py\n+hi\n*** Delete File: old.py"
    with pytest.raises(CodexPatchParseError, match="multi-operation"):
        parse_patch(_wrap(body))


# --- Patch-level rejection: malformed structure ------------------------------


@pytest.mark.parametrize(
    "command,why",
    [
        ("not a patch at all", "no begin marker"),
        ("*** Begin Patch\nno end marker here", "no end marker"),
        ("*** Begin Patch\n*** End Patch\ngarbage", "trailing content"),
        (_wrap(""), "no operation"),
        (_wrap("*** Add File: \n+x"), "empty path"),
        (_wrap("*** Add File:\n+x"), "missing path"),
        (_wrap("*** Add File:   \n+x"), "blank path"),
        (_wrap("*** Add File: ../escape.py\n+x"), "upward traversal"),
        (_wrap("*** Add File: /abs/path.py\n+x"), "absolute path"),
        (_wrap("*** Add File: C:\\dev\\x.py\n+x"), "windows absolute path"),
        (_wrap("*** Add File: ok.py\ncontext line without plus"), "bad body line"),
        (_wrap("*** Add File: ok.py\n-def removed()"), "minus body line"),
        (None, "command not a string"),
        (42, "command not a string"),
    ],
)
def test_malformed_input_fails_deterministically(command, why):
    with pytest.raises(CodexPatchParseError):
        parse_patch(command)


# --- Content fidelity ---------------------------------------------------------


def test_introduced_content_preserves_lines_exactly():
    command = _wrap("*** Add File: new.py\n+line one\n+\n+  indented")
    path, introduced = parse_patch(command)
    assert path == "new.py"
    # Interior blank line preserved; indentation preserved after '+' removal.
    assert introduced == "line one\n\n  indented\n"


def test_single_line_file_gets_trailing_newline():
    _, introduced = parse_patch(_wrap("*** Add File: x.py\n+only"))
    assert introduced == "only\n"


def test_parse_is_pure_no_filesystem_access():
    """Structural guarantee: parsing works on a bare dict with no cwd/repo."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "apply_patch",
        "tool_input": {"command": _wrap("*** Add File: deep/nested/x.py\n+v")},
    }
    assert parse_pretooluse_payload(payload) == ("deep/nested/x.py", "v\n")
