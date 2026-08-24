"""Characterization contract for MULTI-OPERATION apply_patch (M1f-b).

Freezes the bundled grammar observed in run 20260824T133347Z-multifile
(pinned Codex CLI 0.149.1, trusted logger hooks, no bypass): one envelope,
two adjacent operations (Update then Add), no delimiter between operations
beyond the next operation header.

Evidence-driven path-form contract (deliberately narrow):

- Update File: absolute (run 20260824T113630Z) AND relative (this run) both
  observed.
- Add File: relative only, observed so far. Absolute Add has NOT been
  observed and must not be described as Codex behavior.

Aggregation precedence decision (settled pre-M1f-c, applies to the future
multi-operation gate):

    DENY > FAIL_OPEN > WARN > PASS/SKIP

A definite violation on any single operation is sufficient to deny the whole
tool call (Codex deny is per-tool-call; partial enforcement is forbidden).
FAIL_OPEN outranks WARN/PASS because unevaluated operations must never be
reported as governed; the DENY reason must disclose which operations were
not evaluated.
"""
import json
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES = TESTS_DIR / "fixtures"
REPO_ROOT = TESTS_DIR.parents[2]
EVIDENCE = REPO_ROOT / "validation" / "codex-cli" / "evidence" / "runs"
SOURCE_RUN = "20260824T133347Z-multifile"

NORMALIZATIONS = {
    "session_id": "NORMALIZED_SESSION_ID",
    "turn_id": "NORMALIZED_TURN_ID",
    "transcript_path": "NORMALIZED_TRANSCRIPT_PATH",
    "tool_use_id": "exec-NORMALIZED_TOOL_USE_ID",
}


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize(payload):
    out = dict(payload)
    for field, placeholder in NORMALIZATIONS.items():
        out[field] = placeholder
    root = chr(92).join(["C:", "dev", "mneme", ".worktrees",
                         "feat-codex-cli-enforcement", "validation",
                         "codex-cli", "probe", "sandbox", "repo"])
    out["cwd"] = payload["cwd"].replace(
        root, chr(92).join(["C:", "codex-probe-sandbox"]))
    return out


def _fixture():
    return _load(FIXTURES / "pretooluse_applypatch_multifile_allow.json")


def _command_lines():
    command = _fixture()["tool_input"]["command"]
    lines = command.splitlines()
    assert lines[0] == "*** Begin Patch"
    assert lines[-1] == "*** End Patch"
    return lines[1:-1]


def test_fixture_is_normalized_copy_of_captured_evidence():
    source_dir = EVIDENCE / SOURCE_RUN / "events-allow" / "events"
    index = [json.loads(l) for l in
             (source_dir / "index.jsonl").read_text(encoding="utf-8").splitlines()]
    entry = next(e for e in index if e["hook_event_name"] == "PreToolUse"
                 and e["tool_name"] == "apply_patch")
    observed = json.loads((source_dir / entry["file"]).read_text(encoding="utf-8"))
    assert _fixture() == _normalize(observed)


def test_one_envelope_contains_two_adjacent_operations():
    body = _command_lines()
    headers = [(i, l) for i, l in enumerate(body)
               if l.startswith("*** Update File:") or l.startswith("*** Add File:")]
    assert len(headers) == 2
    kinds = [l.split(":", 1)[0].strip() for _, l in headers]
    assert kinds == ["*** Update File", "*** Add File"]  # exact source order


def test_no_delimiter_between_operations_beyond_next_header():
    """Everything between the Update header and the Add header is ordinary
    hunk content (bare @@ / prefixes); the next header IS the delimiter."""
    body = _command_lines()
    update_i = next(i for i, l in enumerate(body) if l.startswith("*** Update File:"))
    add_i = next(i for i, l in enumerate(body) if l.startswith("*** Add File:"))
    between = body[update_i + 1:add_i]
    assert between, "update hunk content missing"
    for line in between:
        assert line == "@@" or line[:1] in (" ", "-", "+"), repr(line)


def test_update_relative_and_absolute_both_observed():
    relative_cmd = _fixture()["tool_input"]["command"]
    header = next(l for l in relative_cmd.splitlines()
                  if l.startswith("*** Update File:"))
    path = header.split(":", 1)[1].strip()
    assert not Path(path).is_absolute()

    absolute_fixture = _load(
        FIXTURES / "pretooluse_applypatch_updatefile_allow.json")
    abs_header = next(l for l in
                      absolute_fixture["tool_input"]["command"].splitlines()
                      if l.startswith("*** Update File:"))
    abs_path = abs_header.split(":", 1)[1].strip()
    # Observed form is a Windows-absolute path; assert the grammar directly
    # rather than via platform pathlib semantics (CI runs on Linux too).
    assert abs_path.startswith("C:") and chr(92) in abs_path


def test_add_file_observed_relative_only_across_fixtures():
    add_paths = []
    for name in ("pretooluse_applypatch_addfile_allow.json",
                 "pretooluse_applypatch_addfile_deny.json"):
        cmd = _load(FIXTURES / name)["tool_input"]["command"]
        header = next(l for l in cmd.splitlines()
                      if l.startswith("*** Add File:"))
        add_paths.append(header.split(":", 1)[1].strip())
    # multifile bundle's Add operation:
    cmd = _fixture()["tool_input"]["command"]
    header = next(l for l in cmd.splitlines() if l.startswith("*** Add File:"))
    add_paths.append(header.split(":", 1)[1].strip())
    assert add_paths == ["probe_target.py", "probe_target.py", "helper.py"]


def test_live_outcomes_deny_blocks_whole_call_allow_lands_both():
    summary = _load(EVIDENCE / SOURCE_RUN / "summary.json")
    allow, deny = summary["arms"][0], summary["arms"][1]
    assert allow["arm"] == "allow" and deny["arm"] == "deny"

    # Deny: NEITHER mutation landed.
    assert deny["seed_changed"] is False and deny["helper_added"] is False

    # Allow: BOTH mutations landed.
    assert allow["seed_changed"] is True and allow["helper_added"] is True

    # PostToolUse: present after allow, absent on deny (event indices).
    def patch_events(arm):
        idx = [json.loads(l) for l in
               (EVIDENCE / SOURCE_RUN / f"events-{arm}" / "events" /
                "index.jsonl").read_text(encoding="utf-8").splitlines()]
        return [e["hook_event_name"] for e in idx
                if e["tool_name"] == "apply_patch"]

    # One bundled call: PreToolUse -> (PostToolUse iff allowed); Stop always.
    assert patch_events("allow") == ["PreToolUse", "PostToolUse"]
    assert patch_events("deny") == ["PreToolUse"]


def test_seed_bytes_identical_to_frozen_update_seed():
    a = (FIXTURES / "seed_service.py").read_bytes()
    b = (EVIDENCE / SOURCE_RUN / "seed-service.py").read_bytes()
    assert a == b  # same CRLF bytes as the M1e-b frozen snapshot


def test_eol_caveat_extends_to_multifile_updates():
    """Mixed-EOL output was reproduced identically in this run's Update
    operation; introduced-content semantics remain line-based."""
    analysis = (EVIDENCE / SOURCE_RUN / "analysis-m1fa.md").read_text(
        encoding="utf-8")
    collapsed = " ".join(analysis.replace(">", "").split())
    assert "mixed-EOL" in collapsed or "mixed EOL" in collapsed
