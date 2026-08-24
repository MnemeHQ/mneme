"""M1e-c tests: Update File parser support against the frozen contract.

The parser stays pure: the current-file snapshot is always a caller-supplied
string; no filesystem access. Matching is line-content based, so the CRLF
seed works without any EOL claim about Codex output.
"""
import json
from pathlib import Path

import pytest

from mneme.integrations.codex_cli.patch_parser import (
    CodexPatchParseError,
    parse_patch,
    parse_pretooluse_payload,
    parse_update_file,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
UPDATE_FIXTURE = "pretooluse_applypatch_updatefile_allow.json"

# Pinned by test_patch_contract_update.py; restated here as parser expectations.
EXPECTED_INTRODUCED = "    return 42\n\n\ndef third():\n    return 3"


def _fixture():
    return json.loads(
        (FIXTURES / UPDATE_FIXTURE).read_text(encoding="utf-8"))


def _seed_lf():
    raw = (FIXTURES / "seed_service.py").read_bytes()
    return raw.replace(b"\r\n", b"\n").decode("utf-8")


def _seed_crlf():
    return (FIXTURES / "seed_service.py").read_bytes().decode("utf-8")


def _command():
    return _fixture()["tool_input"]["command"]


# --- frozen fixture + frozen seed ----------------------------------------------


def test_frozen_update_fixture_parses_to_pinned_introduced_content():
    path, introduced = parse_update_file(_command(), _seed_crlf())
    BS = chr(92)
    assert path.startswith("C:" + BS)          # observed absolute form
    assert path.endswith(BS + "service.py")
    assert introduced == EXPECTED_INTRODUCED


def test_blank_introduced_lines_survive_exactly():
    """ADR-018 protection: interior blanks must not be stripped or collapsed."""
    _, introduced = parse_update_file(_command(), _seed_lf())
    lines = introduced.split("\n")
    assert lines[0] == "    return 42"
    assert lines[1] == "" and lines[2] == ""
    assert introduced == EXPECTED_INTRODUCED


def test_crlf_seed_matches_via_line_content():
    """Matching is line-content based; EOL style of the snapshot is irrelevant."""
    _, from_crlf = parse_update_file(_command(), _seed_crlf())
    _, from_lf = parse_update_file(_command(), _seed_lf())
    assert from_crlf == from_lf == EXPECTED_INTRODUCED


def test_payload_level_with_snapshot():
    result = parse_pretooluse_payload(_fixture(), current_content=_seed_crlf())
    assert result[0].endswith("service.py")
    assert result[1] == EXPECTED_INTRODUCED


def test_update_without_snapshot_rejected_explicitly():
    with pytest.raises(CodexPatchParseError, match="current-file snapshot"):
        parse_pretooluse_payload(_fixture())


# --- snapshot validation --------------------------------------------------------


def _mutated_seed(old, new):
    seed = _seed_lf()
    assert old in seed
    return seed.replace(old, new)


def test_wrong_current_content_fails():
    snapshot = _mutated_seed("return 1", "return 999")
    with pytest.raises(CodexPatchParseError, match="not found"):
        parse_update_file(_command(), snapshot)


def test_missing_context_fails():
    snapshot = _mutated_seed("def second():\n", "")
    with pytest.raises(CodexPatchParseError, match="not found"):
        parse_update_file(_command(), snapshot)


def test_ambiguous_context_fails_rather_than_guessing():
    seed = _seed_lf()
    doubled = seed + "\n\n" + seed  # every anchor now matches twice
    with pytest.raises(CodexPatchParseError, match="ambiguous"):
        parse_update_file(_command(), doubled)


def test_second_hunk_not_located_after_first_consumes_cursor():
    # Remove only the second hunk's anchor from an otherwise valid snapshot.
    snapshot = _seed_lf().replace("    return 2", "    return two")
    with pytest.raises(CodexPatchParseError):
        parse_update_file(_command(), snapshot)


# --- malformed grammar ------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "*** Update File: x.py\ndef f():  pass",       # content before first @@
        "@@\nno prefix line here",                      # unprefixed hunk line
        "@@\n*weird prefix",                            # unknown prefix
        "@@\n ctx\n+added\n-removed",                   # removal after addition
        "",                                             # no hunks
    ],
)
def test_malformed_hunks_fail(body):
    with pytest.raises(CodexPatchParseError):
        parse_update_file(
            f"*** Begin Patch\n*** Update File: service.py\n{body}\n*** End Patch",
            _seed_lf(),
        )


def test_empty_update_path_rejected():
    command = "*** Begin Patch\n*** Update File: \n@@\n+a\n*** End Patch"
    with pytest.raises(CodexPatchParseError, match="empty target path"):
        parse_update_file(command, "")


def test_relative_traversal_update_path_rejected():
    command = ("*** Begin Patch\n*** Update File: ..\\..\\x.py\n"
               "@@\n+a\n*** End Patch")
    with pytest.raises(CodexPatchParseError, match="traverse"):
        parse_update_file(command, "")


def test_non_string_snapshot_rejected():
    with pytest.raises(CodexPatchParseError, match="string"):
        parse_update_file(_command(), None)
    with pytest.raises(CodexPatchParseError, match="string"):
        parse_update_file(_command(), ["lines"])


# --- unsupported operations remain rejected ---------------------------------------


def test_delete_file_still_rejected_by_both_entrypoints():
    delete_cmd = "*** Begin Patch\n*** Delete File: x.py\n*** End Patch"
    with pytest.raises(CodexPatchParseError, match="Delete File"):
        parse_patch(delete_cmd)
    with pytest.raises(CodexPatchParseError, match="Delete File"):
        parse_update_file(delete_cmd, "anything")


def test_multi_operation_still_rejected():
    multi = ("*** Begin Patch\n*** Add File: a.py\n+x\n"
             "*** Update File: b.py\n@@\n+y\n*** End Patch")
    with pytest.raises(CodexPatchParseError, match="multi-operation"):
        parse_update_file(multi, "")


# --- purity: no filesystem I/O ------------------------------------------------------


def test_parser_is_pure_strings_only(tmp_path, monkeypatch):
    """Parsing succeeds with cwd pointed at an unrelated empty directory and
    no target file present: everything needed arrives via arguments."""
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)
    path, introduced = parse_update_file(_command(), _seed_crlf())
    assert path.endswith("service.py")
    assert introduced == EXPECTED_INTRODUCED
