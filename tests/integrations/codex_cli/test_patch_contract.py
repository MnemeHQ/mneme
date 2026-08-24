"""Characterization contract for Codex CLI 0.149.1 apply_patch PreToolUse.

M1a freeze: these tests pin the *observed* wire format and the extraction a
future parser must deliver for the one proven case (single-file Add File).
They intentionally contain no parser implementation -- the parser must be
written against this frozen contract, derived from captured R0 evidence
(validation/codex-cli, runs 20260824T100726Z + 20260824T101801Z), never from
assumed unified-diff semantics.

Out of scope by design: Update/Delete/move operations, multi-file patches,
shell surfaces.
"""
import json
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES = TESTS_DIR / "fixtures"
REPO_ROOT = TESTS_DIR.parents[2]
EVIDENCE = REPO_ROOT / "validation" / "codex-cli" / "evidence" / "runs"

NORMALIZATIONS = {
    "session_id": "NORMALIZED_SESSION_ID",
    "turn_id": "NORMALIZED_TURN_ID",
    "transcript_path": "NORMALIZED_TRANSCRIPT_PATH",
    "cwd": "NORMALIZED_CWD",
    "tool_use_id": "exec-NORMALIZED_TOOL_USE_ID",
}

BEGIN = "*** Begin Patch"
END = "*** End Patch"
ADD_FILE = "*** Add File:"
EXPECTED_COMMAND = (
    "*** Begin Patch\n"
    "*** Add File: probe_target.py\n"
    "+def probe_marker() -> int:\n"
    "+    return 42\n"
    "*** End Patch"
)
# The exact extraction any Add File-capable parser must produce from
# EXPECTED_COMMAND. Frozen here so the parser is derived from observation.
FROZEN_CONTRACT = {
    "tool_name": "apply_patch",
    "targets": [
        {
            "path": "probe_target.py",
            "operation": "add",
            "introduced_content": "def probe_marker() -> int:\n    return 42\n",
        }
    ],
}


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize(payload):
    out = dict(payload)
    for field, placeholder in NORMALIZATIONS.items():
        out[field] = placeholder
    return out


def _evidence_payload(run, arm, name):
    path = EVIDENCE / run / f"events-{arm}" / "events" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_fixture_is_normalized_copy_of_captured_evidence():
    """Fixture provenance: fixture == evidence payload modulo documented
    volatile-field normalization."""
    sources = {
        "pretooluse_applypatch_addfile_allow.json": (
            "20260824T100726Z-applypatch",
            "allow",
            "0000-PreToolUse-apply_patch-20260824T100732.json",
        ),
        "pretooluse_applypatch_addfile_deny.json": (
            "20260824T100726Z-applypatch",
            "deny",
            "0000-PreToolUse-apply_patch-20260824T100748.json",
        ),
    }
    for fixture_name, (run, arm, payload_name) in sources.items():
        fixture = _load(FIXTURES / fixture_name)
        observed = _normalize(_evidence_payload(run, arm, payload_name))
        assert fixture == observed, fixture_name


def test_observed_envelope_fields():
    """The event fields the integration may rely on, exactly as observed."""
    payload = _load(FIXTURES / "pretooluse_applypatch_addfile_allow.json")
    assert payload["hook_event_name"] == "PreToolUse"
    assert payload["tool_name"] == "apply_patch"
    assert isinstance(payload["tool_input"], dict)
    assert isinstance(payload["tool_input"]["command"], str)
    # Observed but not relied on for enforcement:
    for optional in ("session_id", "turn_id", "model", "permission_mode"):
        assert optional in payload


def test_observed_patch_grammar_single_file_add():
    """The full patch travels in tool_input.command using Codex's own patch
    script format (not unified diff)."""
    command = (
        _load(FIXTURES / "pretooluse_applypatch_addfile_allow.json")
    )["tool_input"]["command"]
    assert command.startswith(BEGIN)
    assert command.rstrip("\n").endswith(END)
    body = command[len(BEGIN):command.index(END)]
    add_lines = [ln for ln in body.splitlines() if ln.startswith(ADD_FILE)]
    assert len(add_lines) == 1

    target_path = add_lines[0][len(ADD_FILE):].strip()
    introduced = "\n".join(
        ln[1:] for ln in body.splitlines() if ln.startswith("+") and not ln.startswith(ADD_FILE)
    ) + "\n"

    assert target_path == FROZEN_CONTRACT["targets"][0]["path"]
    assert introduced == FROZEN_CONTRACT["targets"][0]["introduced_content"]
    assert command == EXPECTED_COMMAND


def test_allow_and_deny_payloads_carry_identical_command():
    """Same mutation proposal reached the hook in both arms; only the hook's
    decision differed."""
    allow = _load(FIXTURES / "pretooluse_applypatch_addfile_allow.json")
    deny = _load(FIXTURES / "pretooluse_applypatch_addfile_deny.json")
    assert allow["tool_input"]["command"] == deny["tool_input"]["command"]
    assert allow["tool_name"] == deny["tool_name"] == "apply_patch"


def test_malformed_missing_command_is_detectable():
    payload = _load(FIXTURES / "malformed_missing_command.json")
    assert payload["tool_name"] == "apply_patch"
    command = payload["tool_input"].get("command")
    assert command is None or command == ""


def test_malformed_missing_markers_is_detectable():
    payload = _load(FIXTURES / "malformed_missing_markers.json")
    command = payload["tool_input"]["command"]
    assert BEGIN not in command and END not in command and ADD_FILE not in command
