"""Offline unit tests for the CI1.3 P2 pinned-evaluator preflight.

``scripts/ci1_evaluator_preflight.py`` installs a release from PyPI and is run
by hand (see its validation record); these tests pin its decision logic with
fakes so the battery never touches the network: hash checking, evaluator
identity, RECORD verification, per-case comparison and the replay loop.
"""
import base64
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from scripts import ci1_evaluator_preflight as pf

M = pf.load_matrix_module()
REPO_ROOT = pf.REPO_ROOT


def _proc(code: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], code, stdout, stderr)


# ── hash-checked install ─────────────────────────────────────────────────────

def test_wheel_name_version():
    assert pf.wheel_name_version("mneme_hq-0.10.0-py3-none-any.whl") == ("mneme_hq", "0.10.0")
    assert pf.wheel_name_version("pkg-1.0-1-cp312-cp312-win_amd64.whl") == ("pkg", "1.0")
    with pytest.raises(pf.PreflightError):
        pf.wheel_name_version("mneme_hq-0.10.0.tar.gz")


def _downloads(tmp_path: Path, files: dict[str, bytes]) -> tuple[Path, dict[str, str]]:
    d = tmp_path / "wheels"
    d.mkdir(parents=True)
    digests = {}
    for name, data in files.items():
        (d / name).write_bytes(data)
        digests[name] = hashlib.sha256(data).hexdigest()
    return d, digests


EVAL = "mneme_hq-0.10.0-py3-none-any.whl"
DEP = "PyYAML-6.0.2-cp312-cp312-win_amd64.whl"


def test_verify_downloads_accepts_pypi_matching_and_pinned(tmp_path):
    d, digests = _downloads(tmp_path, {EVAL: b"evaluator", DEP: b"dep"})
    lock = pf.verify_downloads(d, "0.10.0", digests[EVAL], lambda n, v: digests)
    assert {e["filename"]: e["sha256"] for e in lock} == digests
    assert sorted(pf.requirements_text(lock).splitlines()) == [
        f"PyYAML==6.0.2 --hash=sha256:{digests[DEP]}",
        f"mneme_hq==0.10.0 --hash=sha256:{digests[EVAL]}",
    ]


@pytest.mark.parametrize("tamper", ["dep_vs_pypi", "eval_vs_pypi", "eval_vs_pinned", "absent_on_pypi"])
def test_verify_downloads_fails_hard(tmp_path, tamper):
    d, digests = _downloads(tmp_path, {EVAL: b"evaluator", DEP: b"dep"})
    published = dict(digests)
    pinned = digests[EVAL]
    if tamper == "dep_vs_pypi":
        published[DEP] = "0" * 64
    elif tamper == "eval_vs_pypi":
        published[EVAL] = "0" * 64
    elif tamper == "eval_vs_pinned":
        pinned = "0" * 64
    else:
        del published[DEP]
    with pytest.raises(pf.PreflightError):
        pf.verify_downloads(d, "0.10.0", pinned, lambda n, v: published)


def test_verify_downloads_rejects_wrong_version_and_missing_evaluator(tmp_path):
    d, digests = _downloads(tmp_path, {EVAL: b"evaluator"})
    with pytest.raises(pf.PreflightError, match="expected 0.9.0"):
        pf.verify_downloads(d, "0.9.0", digests[EVAL], lambda n, v: digests)
    d2, digests2 = _downloads(tmp_path / "x", {DEP: b"dep"})
    with pytest.raises(pf.PreflightError, match="no mneme-hq wheel"):
        pf.verify_downloads(d2, "0.10.0", "0" * 64, lambda n, v: digests2)


def test_commit_build_evaluator_skips_pypi_but_dependencies_do_not(tmp_path):
    d, digests = _downloads(tmp_path, {EVAL: b"local build", DEP: b"dep"})
    published = {DEP: digests[DEP]}  # the local build is not on PyPI
    lock = pf.verify_downloads(d, "0.10.0", digests[EVAL], lambda n, v: published, evaluator_from_pypi=False)
    assert len(lock) == 2
    with pytest.raises(pf.PreflightError):
        pf.verify_downloads(d, "0.10.0", digests[EVAL], lambda n, v: {}, evaluator_from_pypi=False)


def test_pinned_digest_is_the_published_0_10_0_wheel():
    assert pf.PINNED_WHEEL_SHA256["0.10.0"] == (
        "fc7e0ec7191e243e998055d34e5764e473aa439ecdc40c22a969acf376ec5312"
    )


def test_clean_env_drops_import_redirection(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))
    monkeypatch.setenv("PYTHONHOME", "x")
    env = pf.clean_env()
    assert "PYTHONPATH" not in env and "PYTHONHOME" not in env


# ── evaluator identity ───────────────────────────────────────────────────────

def _probe(venv: Path, work: Path) -> dict:
    purelib = venv / "Lib" / "site-packages"
    return {
        "executable": str(venv / "Scripts" / "python.exe"),
        "prefix": str(venv), "isolated": 1, "cwd": str(work), "python_version": "3.12.10",
        "sys_path": ["", str(venv / "python312.zip"), str(purelib)],
        "purelib": str(purelib),
        "mneme_file": str(purelib / "mneme" / "__init__.py"),
        "mneme_cli_file": str(purelib / "mneme" / "cli.py"),
        "version": "0.10.0",
        "console_scripts": {"mneme": "mneme.cli:main"},
    }


def test_identity_accepts_a_clean_probe(tmp_path):
    venv = tmp_path / "venv"
    assert pf.identity_errors(_probe(venv, tmp_path), venv, REPO_ROOT, "0.10.0") == []


@pytest.mark.parametrize("field,value,needle", [
    ("executable", str(REPO_ROOT / "python.exe"), "interpreter"),
    ("isolated", 0, "isolated"),
    ("mneme_file", str(REPO_ROOT / "mneme" / "__init__.py"), "mneme_file"),
    ("mneme_cli_file", str(REPO_ROOT / "mneme" / "cli.py"), "mneme_cli_file"),
    ("sys_path", [str(REPO_ROOT)], "sys.path"),
    ("cwd", str(REPO_ROOT / "tests"), "working directory"),
    ("version", "0.9.0", "version"),
    ("console_scripts", {"mneme": "elsewhere:main"}, "console script"),
])
def test_identity_mismatch_fails(tmp_path, field, value, needle):
    venv = tmp_path / "venv"
    probe = _probe(venv, tmp_path) | {field: value}
    errors = pf.identity_errors(probe, venv, REPO_ROOT, "0.10.0")
    assert any(needle in e for e in errors), errors


def _record_hash(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def _fake_install(tmp_path: Path) -> tuple[Path, Path]:
    files = {"mneme/__init__.py": b"", "mneme/cli.py": b"def main(): pass\n",
             "mneme_hq-0.10.0.dist-info/METADATA": b"Name: mneme-hq\n"}
    record = "".join(f"{k},{_record_hash(v)},{len(v)}\n" for k, v in files.items())
    record += "mneme_hq-0.10.0.dist-info/RECORD,,\n"
    wheel = tmp_path / EVAL
    with zipfile.ZipFile(wheel, "w") as zf:
        for k, v in files.items():
            zf.writestr(k, v)
        zf.writestr("mneme_hq-0.10.0.dist-info/RECORD", record)
    purelib = tmp_path / "site-packages"
    for k, v in files.items():
        (purelib / k).parent.mkdir(parents=True, exist_ok=True)
        (purelib / k).write_bytes(v)
    installed = record + "mneme_hq-0.10.0.dist-info/INSTALLER,,\n../../Scripts/mneme.exe,sha256=x,1\n"
    (purelib / "mneme_hq-0.10.0.dist-info" / "RECORD").write_text(installed, encoding="utf-8")
    return wheel, purelib


def test_record_verifies_installed_files(tmp_path):
    wheel, purelib = _fake_install(tmp_path)
    assert pf.record_errors(wheel, purelib, "0.10.0") == (3, [])


def test_record_detects_a_modified_installed_file(tmp_path):
    wheel, purelib = _fake_install(tmp_path)
    (purelib / "mneme" / "cli.py").write_text("def main(): return 'patched'\n", encoding="utf-8")
    _verified, errors = pf.record_errors(wheel, purelib, "0.10.0")
    assert any("mneme/cli.py" in e for e in errors)


def test_record_detects_a_module_the_wheel_never_shipped(tmp_path):
    wheel, purelib = _fake_install(tmp_path)
    (purelib / "mneme" / "shadow.py").write_text("", encoding="utf-8")
    _verified, errors = pf.record_errors(wheel, purelib, "0.10.0")
    assert any("mneme/shadow.py" in e for e in errors)


# ── per-case comparison ──────────────────────────────────────────────────────

def _corpus(name: str) -> tuple[Path, dict]:
    root = pf.CORPORA_DIR / name / "v1"
    return root, json.loads((root / "cases.json").read_text(encoding="utf-8"))


def test_compare_golden_accepts_the_golden_itself():
    root, spec = _corpus("path_scoped_forbid_literal")
    case = spec["cases"][1]
    expected = M._canonical(json.loads((root / case["expected"]).read_text(encoding="utf-8")))
    proc = _proc(case["expected_exit"], json.dumps(expected))
    assert pf.compare_golden(M, case, expected, proc, True) == []


def test_compare_golden_names_dropped_identity_fields():
    """The 0.10.0 failure mode: records without rule_id/decision_version_id."""
    root, spec = _corpus("warn_verdict")
    [case] = [c for c in spec["cases"] if c["id"] == "warn_strict"]
    expected = M._canonical(json.loads((root / case["expected"]).read_text(encoding="utf-8")))
    actual = json.loads(json.dumps(expected))
    for record in actual["violations"]:
        del record["rule_id"], record["decision_version_id"]
    diffs = pf.compare_golden(M, case, expected, _proc(1, json.dumps(actual)), True)
    assert any("lack decision_version_id, rule_id" in d for d in diffs), diffs


def test_compare_golden_reports_a_crash():
    root, spec = _corpus("path_scoped_forbid_literal")
    case = spec["cases"][0]
    expected = json.loads((root / case["expected"]).read_text(encoding="utf-8"))
    diffs = pf.compare_golden(M, case, expected, _proc(1, "", "Traceback ...\nBoom: schema\n"), False)
    assert diffs == ["exit 1, stdout is not a single JSON payload (''); stderr ends 'Boom: schema'"]


@pytest.mark.parametrize("field,value", [("exit", 0), ("stderr", "warning\n")])
def test_compare_golden_checks_exit_and_stderr(field, value):
    root, spec = _corpus("warn_verdict")
    [case] = [c for c in spec["cases"] if c["id"] == "warn_strict"]
    expected = M._canonical(json.loads((root / case["expected"]).read_text(encoding="utf-8")))
    proc = _proc(value if field == "exit" else 1, json.dumps(expected), value if field == "stderr" else "")
    assert pf.compare_golden(M, case, expected, proc, True)


def test_compare_memory_error_forms():
    _root, spec = _corpus("memory_errors")
    by_id = {c["id"]: c for c in spec["cases"]}
    missing = _proc(2, "", "ERROR: memory file project_memory.json does not exist\n")
    assert pf.compare_memory_error(M, by_id["memory_missing"], missing, REPO_ROOT) == []
    crash = _proc(1, "", "Traceback (most recent call last):\n  ...\nValueError\n")
    assert pf.compare_memory_error(M, by_id["memory_truncated_json"], crash, REPO_ROOT) == []
    from_checkout = _proc(1, "", f"Traceback (most recent call last):\n  File \"{REPO_ROOT.resolve()}\"\n")
    assert pf.compare_memory_error(M, by_id["memory_truncated_json"], from_checkout, REPO_ROOT)
    assert pf.compare_memory_error(M, by_id["memory_missing"], _proc(2, "{}", missing.stderr), REPO_ROOT)


# ── replay loop, driven by a fake evaluator ──────────────────────────────────

class FakeEvaluator:
    """Answers each `mneme check` with the committed expectation, optionally
    dropping rule identity from every record (the 0.10.0 shape)."""

    def __init__(self, drop_identity: bool = False):
        self.drop_identity = drop_identity

    def run(self, args: list[str], cwd: Path) -> subprocess.CompletedProcess:
        opt = {args[i]: args[i + 1] for i in range(1, len(args) - 1) if args[i].startswith("--")}
        spec = json.loads((cwd / "cases.json").read_text(encoding="utf-8")) if (cwd / "cases.json").exists() \
            else json.loads((cwd.parent.parent / "cases.json").read_text(encoding="utf-8"))
        if "modes" in spec:  # memory_errors
            [case] = [c for c in spec["cases"] if cwd.name.startswith(c["id"] + "-")
                      and cwd.name[len(c["id"]) + 1:] in spec["modes"]]
            if case["expected_stderr"] == "error_line":
                return _proc(2, "", "ERROR: memory file project_memory.json does not exist\n")
            return _proc(case["expected_exit"], "", "Traceback (most recent call last):\nValueError\n")
        [case] = [c for c in spec["cases"] if c["input"] == opt["--input"] and c["mode"] == opt["--mode"]
                  and c["target_path"] == opt.get("--target-path")]
        payload = json.loads((cwd / case["expected"]).read_text(encoding="utf-8"))
        if self.drop_identity:
            for key in ("applicability", "violations"):
                for record in payload[key]:
                    record.pop("rule_id", None)
                    record.pop("decision_version_id", None)
        return _proc(case["expected_exit"], json.dumps(payload))


def test_corpus_versions_cover_every_ci1_corpus():
    found = {(c, v) for c, v, _ in pf.corpus_versions()}
    assert found >= {("path_scoped_forbid_literal", "v1"), ("warn_verdict", "v1"),
                     ("incomplete_evaluation", "v1"), ("memory_errors", "v1")}


def test_replay_reaches_parity_when_the_evaluator_matches(tmp_path):
    results = pf.replay_corpora(M, FakeEvaluator(), tmp_path)
    assert results and all(r["parity"] for r in results), [r for r in results if not r["parity"]]
    expected_runs = 0
    for corpus, _v, source in pf.corpus_versions():
        spec = json.loads((source / "cases.json").read_text(encoding="utf-8"))
        per_case = len(spec["modes"]) if "modes" in spec else len(spec["query_variants"])
        expected_runs += per_case * len(spec["cases"])
    assert len(results) == expected_runs


def test_replay_fails_parity_when_identity_is_dropped(tmp_path):
    results = pf.replay_corpora(M, FakeEvaluator(drop_identity=True), tmp_path)
    failed = {(r["corpus"], r["case"]) for r in results if not r["parity"]}
    assert ("warn_verdict", "warn_strict") in failed
    assert ("path_scoped_forbid_literal", "applied_fail") in failed
    assert not any(c == "memory_errors" for c, _ in failed)
    assert ("warn_verdict", "pass_strict") not in failed  # no records, nothing to drop


def test_replay_never_writes_to_the_committed_corpus(tmp_path):
    before = {p: p.read_bytes() for p in pf.CORPORA_DIR.rglob("*") if p.is_file()}
    pf.replay_corpora(M, FakeEvaluator(), tmp_path)
    after = {p: p.read_bytes() for p in pf.CORPORA_DIR.rglob("*") if p.is_file()}
    assert before == after


# ── checks with no manifest ──────────────────────────────────────────────────

def test_consistent_stub_matrix_matches_the_merged_test():
    [mark] = [mk for mk in M.test_consistent_stub_output_classifies.pytestmark if mk.name == "parametrize"]
    assert pf.CONSISTENT_STUBS == list(mark.args[1])


def test_classifier_checks_cover_every_stub_and_pass():
    results = pf.classifier_checks(M)
    assert len(results) == len(M.STUBS) + len(pf.CONSISTENT_STUBS)
    assert all(r["parity"] for r in results)


def test_rule_record_note_explains_missing_identity():
    records = [{"decision_id": "ADR-005", "outcome": "APPLIED"}]
    note = pf.rule_record_note(records, M.ADR005_RULE_ID)
    assert "none carries rule_id" in note and "decision_version_id, rule_id" in note


# ── guard rails and record ───────────────────────────────────────────────────

def test_work_dir_inside_the_checkout_is_refused():
    with pytest.raises(pf.PreflightError, match="outside the checkout"):
        pf.run_preflight("0.10.0", REPO_ROOT / "build" / "p2")


def test_record_masks_the_scratch_directory(tmp_path):
    work = tmp_path / "work"
    report = {
        "generated_at": "2026-10-17T00:00:00Z", "work_dir": str(work), "version": "0.10.0",
        "source": {"kind": "pypi"}, "host": "test", "passed": False,
        "identity": {
            "wheel_filename": EVAL, "wheel_sha256": "a" * 64, "lock": [], "pip": "pip 25",
            "record_files_verified": 1, "entry_point": ["<venv python>", "-I", "-m", "mneme.cli"],
            "rechecked": True, "probe": _probe(work / "venv", work),
        },
        "corpus_provenance": {"commit": "c", "corpus_tree": "t", "canonical_memory_blob": "b",
                              "matrix_tests_blob": "m", "clean": True},
        "corpus_versions": ["warn_verdict/v1"],
        "sections": {k: {"label": k, "total": 1, "passed": 0, "failed": 1,
                         "results": [{"corpus": "c", "version": "v1", "case": "x", "variant": "v",
                                      "expected": "e", "exit": 1, "classification": "UNEVALUATED",
                                      "check": "k", "parity": False, "diffs": ["boom"]}]}
                     for k in ("replay", "adr005", "regeneration", "classifier")},
    }
    text = pf.render_markdown(report)
    assert "**Verdict: FAIL.**" in text
    assert work.as_posix() not in text and "<work>/venv" in text
    assert "**NO**: boom" in text
