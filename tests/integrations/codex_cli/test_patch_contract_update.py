"""Characterization contract for Codex CLI 0.149.1 apply_patch **Update File**.

M1e-b freeze: pins the Update File grammar observed in run
20260824T113630Z-updatefile (trusted, no bypass, pinned 0.149.1) before any
parser support exists. The parser must be derived from this contract.

EOL caveat (pinned verbatim in fixtures/README.md):

    Update enforcement is line-content based. The integration does not claim
    byte-exact final-file reconstruction because Codex 0.149.1 on Windows can
    produce mixed EOLs when patching a CRLF checkout.
"""
import json
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES = TESTS_DIR / "fixtures"
REPO_ROOT = TESTS_DIR.parents[2]
EVIDENCE = REPO_ROOT / "validation" / "codex-cli" / "evidence" / "runs"
SOURCE_RUN = "20260824T113630Z-updatefile"

BS = chr(92)
SANDBOX_ROOT_PLACEHOLDER = BS.join(["C:", "codex-probe-sandbox"])
NORMALIZATIONS = {
    "session_id": "NORMALIZED_SESSION_ID",
    "turn_id": "NORMALIZED_TURN_ID",
    "transcript_path": "NORMALIZED_TRANSCRIPT_PATH",
    "tool_use_id": "exec-NORMALIZED_TOOL_USE_ID",
}

BEGIN = "*** Begin Patch"
END = "*** End Patch"
UPDATE_FILE = "*** Update File:"

EXPECTED_INTRODUCED_LINES = [
    "    return 42",   # replacement of `    return 1`
    "",                # appended blank
    "",                # appended blank
    "def third():",
    "    return 3",
]
EXPECTED_REMOVED_LINES = ["    return 1"]


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize(payload):
    out = dict(payload)
    for field, placeholder in NORMALIZATIONS.items():
        out[field] = placeholder
    root = BS.join(["C:", "dev", "mneme", ".worktrees",
                    "feat-codex-cli-enforcement", "validation", "codex-cli",
                    "probe", "sandbox", "repo"])
    out["cwd"] = payload["cwd"].replace(root, SANDBOX_ROOT_PLACEHOLDER)
    out["tool_input"] = {
        "command": payload["tool_input"]["command"].replace(
            root, SANDBOX_ROOT_PLACEHOLDER)
    }
    return out


# --- provenance ---------------------------------------------------------------


def test_fixture_is_normalized_copy_of_captured_evidence():
    source_dir = EVIDENCE / SOURCE_RUN / "events-allow" / "events"
    index = [json.loads(l) for l in
             (source_dir / "index.jsonl").read_text(encoding="utf-8").splitlines()]
    entry = next(e for e in index if e["hook_event_name"] == "PreToolUse"
                 and e["tool_name"] == "apply_patch")
    observed = json.loads((source_dir / entry["file"]).read_text(encoding="utf-8"))
    fixture = _load(FIXTURES / "pretooluse_applypatch_updatefile_allow.json")
    assert fixture == _normalize(observed)


def test_seed_snapshot_frozen_with_known_hashes():
    seed_bytes = (FIXTURES / "seed_service.py").read_bytes()
    import hashlib
    # Fixture bytes are CRLF: the probe's Python write translated LF to the
    # platform newline, matching what Codex actually patched on disk.
    assert b"\r\n" in seed_bytes and b"\n" not in seed_bytes.replace(b"\r\n", b"")
    assert hashlib.sha256(seed_bytes).hexdigest() == (
        "ef3316e7e28adee977970f0a16a32d9057c62d92f4f9f786bd845d5c4fbdad64")
    lf_variant = hashlib.sha256(
        seed_bytes.replace(b"\r\n", b"\n")).hexdigest()
    assert lf_variant == (
        "0d380ddfbc86bc2a94b0f713daa6d2ba7ff3f176f1182aa7dccb41830ae12455")


# --- observed grammar ----------------------------------------------------------


def _payload():
    return _load(FIXTURES / "pretooluse_applypatch_updatefile_allow.json")


def test_tool_name_and_header():
    payload = _payload()
    assert payload["tool_name"] == "apply_patch"
    command = payload["tool_input"]["command"]
    assert command.startswith(BEGIN)
    assert command.rstrip("\n").endswith(END)
    assert UPDATE_FILE in command


def test_observed_absolute_path_form():
    """This capture used an absolute target path; Add File used relative.
    Both forms are observed Codex possibilities and must be recognized."""
    command = _payload()["tool_input"]["command"]
    header = next(l for l in command.splitlines() if l.startswith(UPDATE_FILE))
    path = header.split(":", 1)[1].strip()
    assert path.startswith("C:" + chr(92))          # absolute form observed here
    assert path.endswith(chr(92) + "service.py")
    assert SANDBOX_ROOT_PLACEHOLDER in path         # normalized root only


def test_bare_hunk_headers_without_line_numbers():
    command = _payload()["tool_input"]["command"]
    body = command[len(BEGIN):command.index(END)]
    hunk_lines = [l for l in body.splitlines() if l.strip() == "@@"]
    assert len(hunk_lines) == 2
    for l in body.splitlines():
        if l.startswith("@@"):
            assert l == "@@"  # no -l,c +l,c ranges, unlike unified diff


def test_context_removal_addition_prefix_semantics():
    command = _payload()["tool_input"]["command"]
    body = command[len(BEGIN):command.index(END)].splitlines()
    start = next(i for i, l in enumerate(body) if l.startswith(UPDATE_FILE)) + 1
    hunks, current = [], None
    for line in body[start:]:
        if line == "@@":
            current = []
            hunks.append(current)
        else:
            current.append(line)

    context, removed, added = [], [], []
    for hunk in hunks:
        for line in hunk:
            if line.startswith(" "):
                context.append(line[1:])
            elif line.startswith("-"):
                removed.append(line[1:])
            elif line.startswith("+"):
                added.append(line[1:])
            else:
                raise AssertionError(f"unrecognized prefix: {line!r}")

    assert context == ["def existing():", "def second():", "    return 2"]
    assert removed == EXPECTED_REMOVED_LINES
    assert added == EXPECTED_INTRODUCED_LINES


def test_expected_introduced_lines_exact():
    command = _payload()["tool_input"]["command"]
    plus_lines = [l[1:] for l in command.splitlines() if l.startswith("+")]
    assert plus_lines == EXPECTED_INTRODUCED_LINES


def test_add_file_fixtures_keep_relative_path_form():
    addfile = _load(FIXTURES / "pretooluse_applypatch_addfile_allow.json")
    header = next(l for l in addfile["tool_input"]["command"].splitlines()
                  if l.startswith("*** Add File:"))
    path = header.split(":", 1)[1].strip()
    assert not Path(path).is_absolute()
    assert path == "probe_target.py"


def test_eol_caveat_is_pinned_in_documentation():
    readme = (FIXTURES / "README.md").read_text(encoding="utf-8")
    collapsed = " ".join(readme.replace(">", "").split())
    caveat = ("Update enforcement is line-content based. The integration does "
              "not claim byte-exact final-file reconstruction because Codex "
              "0.149.1 on Windows can produce mixed EOLs when patching a CRLF "
              "checkout.")
    assert caveat in collapsed
