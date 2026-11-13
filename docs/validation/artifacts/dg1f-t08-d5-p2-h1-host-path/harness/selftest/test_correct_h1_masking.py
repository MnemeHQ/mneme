"""Synthetic tests for correct_h1_masking.py (append-only correction of #553).

The tool must: refuse a classifier whose hash is not the recorded one; key arms to
the recorded live location so the workspace masks; refuse to publish when the
archive-keyed run does not reproduce the accepted outcome; publish a corrected
outcome only for paths that change; and publish nothing when integrity fails.
Synthetic data only; no real evidence is read.
"""
import hashlib
import importlib.util
import json
import types
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("correct_h1_masking", HARNESS / "correct_h1_masking.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)

NONCE = "MNEME-PROBE-0123456789abcdef"


def test_load_pinned_refuses_wrong_hash(tmp_path):
    f = tmp_path / "classify_h1.py"
    f.write_text("RULES_ID = 'x'\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="nothing classified"):
        M.load_pinned(f, "0" * 64)
    good = hashlib.sha256(f.read_bytes()).hexdigest()
    assert M.load_pinned(f, good).RULES_ID == "x"


def test_load_keyed_masks_the_recorded_workspace(tmp_path):
    out = tmp_path / "arch" / "H1a-edit" / "out"
    out.mkdir(parents=True)
    (out / "nonce.txt").write_text(NONCE, encoding="utf-8")
    C = M.R.C
    req = {"file_path": r"C:\dev\d5p2-h1-live\H1a-edit\ws\notes.txt"}
    keyed = M.load_keyed(C, tmp_path / "arch", "H1a-edit", M.LIVE_ROOT)
    assert "<WS>" in C.masked(req, keyed, NONCE)
    as_553 = M.load_keyed(C, tmp_path / "arch", "H1a-edit", None)  # archive keying, as #553 did
    assert "<WS>" not in C.masked(req, as_553, NONCE)


def test_diff_paths_and_perm_summary():
    a = {"label": "X", "permissions": {"comparison": {"equivalent_requests": [],
                                                       "non_equivalent_attempts": {"emitter": [1, 2], "control": [1, 2]}}}}
    b = {"label": "X", "permissions": {"comparison": {"equivalent_requests": [1, 2],
                                                       "non_equivalent_attempts": {"emitter": [], "control": []}}}}
    assert M.diff_paths(a, b) == ["permissions.comparison.equivalent_requests",
                                  "permissions.comparison.non_equivalent_attempts.control",
                                  "permissions.comparison.non_equivalent_attempts.emitter"]
    assert M.diff_paths(a, a) == []
    assert M.perm_summary(b) == {"equivalent_requests": 2, "mismatched_decisions": 0,
                                 "non_equivalent_attempts": {"control": 0, "emitter": 0}}


def _outcome(eq):
    return {"label": "DELIVERED_TO_AGENT", "passes_path": True,
            "permissions": {"comparison": {"equivalent_requests": [["Read", "<WS>"]] * eq,
                                           "mismatched_decisions": [],
                                           "non_equivalent_attempts": {"emitter": [], "control": []}}}}


def _fixture(tmp_path, monkeypatch, repro_ok=True, helper_ok=True, fail_on_verify_call=None):
    pub = tmp_path / "pub"
    pub.mkdir()
    pinned = tmp_path / "pinned.py"
    pinned.write_text("# pinned\n", encoding="utf-8")
    helper = hashlib.sha256((M.HERE / "reclassify_h1.py").read_bytes()).hexdigest()
    (pub / "reclassification.json").write_text(json.dumps({
        "reclassify_tool_sha256": helper if helper_ok else "f" * 64,
        "classifier_sha256": "pinned-hash"}), encoding="utf-8")
    (pub / "MANIFEST.json").write_text("{}", encoding="utf-8")
    accepted = {p: _outcome(0) for p in M.R.PATHS}
    for p in M.R.PATHS:
        (pub / p).mkdir()
        (pub / p / "outcome.r1r3.json").write_text(json.dumps(accepted[p], indent=2) + "\n", encoding="utf-8")
        (pub / p / "outcome.json").write_text(json.dumps(_outcome(2 if p == "H1a-edit" else 0)), encoding="utf-8")
    calls = []

    def verify(*_a):
        calls.append(1)
        bad = fail_on_verify_call is not None and len(calls) == fail_on_verify_call
        return {"problems": ["synthetic tamper"] if bad else []}

    def outcome_text(Cp, archive, p, root, red, red_live):
        if root is None:  # reproduction of #553
            o = accepted[p] if repro_ok else dict(accepted[p], label="OTHER")
        else:             # corrected keying: only H1a-edit changes
            o = _outcome(2) if p == "H1a-edit" else accepted[p]
        return json.dumps(o, indent=2) + "\n"

    monkeypatch.setattr(M.R, "verify", verify)
    monkeypatch.setattr(M, "load_pinned", lambda path, expected: types.SimpleNamespace(RULES_ID="R1-R3"))
    monkeypatch.setattr(M, "outcome_text", outcome_text)
    return pub, (lambda: M.main(["x", str(tmp_path / "arch"), str(pinned), str(pub), "py", "claude", str(pinned)]))


def _new_files(pub):
    return sorted(str(p.relative_to(pub)).replace("\\", "/") for p in pub.rglob("*")
                  if p.is_file() and p.name in ("outcome.r1r3.corrected.json", "masking-correction.json"))


def test_main_publishes_correction_only_for_changed_path(tmp_path, monkeypatch):
    pub, run = _fixture(tmp_path, monkeypatch)
    assert run() == 0
    assert _new_files(pub) == ["H1a-edit/outcome.r1r3.corrected.json", "masking-correction.json"]
    s = json.loads((pub / "masking-correction.json").read_text(encoding="utf-8"))
    e = s["paths"]["H1a-edit"]
    assert e["corrected_differs"] and e["differing_fields"] == ["permissions.comparison.equivalent_requests"]
    assert e["permissions"]["accepted_r1r3"]["equivalent_requests"] == 0
    assert e["permissions"]["corrected_r1r3"]["equivalent_requests"] == 2
    assert e["corrected_permissions_equal_as_run"] and s["labels_unchanged"]
    assert not s["paths"]["H1a-bash"]["corrected_differs"]
    # The accepted files are never modified.
    assert json.loads((pub / "H1a-edit" / "outcome.r1r3.json").read_text(encoding="utf-8")) == _outcome(0)


def test_main_refuses_when_reproduction_differs(tmp_path, monkeypatch):
    pub, run = _fixture(tmp_path, monkeypatch, repro_ok=False)
    with pytest.raises(SystemExit, match="does not reproduce"):
        run()
    assert _new_files(pub) == []


def test_main_refuses_when_helpers_differ_from_553(tmp_path, monkeypatch):
    pub, run = _fixture(tmp_path, monkeypatch, helper_ok=False)
    with pytest.raises(SystemExit, match="differs from the #553 tool"):
        run()
    assert _new_files(pub) == []


@pytest.mark.parametrize("n", [1, 2, 3])  # before, after classification, immediately before the copy
def test_main_publishes_nothing_when_integrity_fails(tmp_path, monkeypatch, n):
    pub, run = _fixture(tmp_path, monkeypatch, fail_on_verify_call=n)
    with pytest.raises(SystemExit):
        run()
    assert _new_files(pub) == []


def test_main_refuses_to_overwrite(tmp_path, monkeypatch):
    pub, run = _fixture(tmp_path, monkeypatch)
    (pub / "masking-correction.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        run()
