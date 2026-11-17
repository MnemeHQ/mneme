"""ADR-033 C4: deterministic regressions for the trusted CI availability adapter.

Covers ``scripts/ci/adr033_c4_gate.py`` against the Gate 0 offline matrix
(O1-O12, including O2w, O8s, O9s, O9p, O9n, O10x and the strict and warn O11
mixtures) and the Gate 1 charter §5 controls: payload coherence and parity
with the shipped ``assess_verdict`` (#484), A1 path-first refusal, A2/R1
aggregation, A3 posture fallback, A4 warn-mode exits, and the trusted
decision step's report checks.

Most rows run real git repositories (built with plumbing only, so case
variants, symlinks and submodules are exact) against a stub evaluator that
replays ``tests/fixtures/adr033_c4_ci/v1/payload_cases.json``. A separate
group runs the real ``mneme check`` CLI on the CI1.2.1 corpus when it is
importable under ``python -I``; that group is not Gate 2 evidence.

Fixtures are versioned: a changed expectation means a new ``vN/``.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = REPO_ROOT / "scripts" / "ci" / "adr033_c4_gate.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "adr033_c4_ci" / "v1"
CI1_CORPUS = REPO_ROOT / "tests" / "fixtures" / "ci1_contract" / "path_scoped_forbid_literal" / "v1"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load("adr033_c4_gate", ADAPTER_PATH)
PAYLOAD_CASES = json.loads((FIXTURES / "payload_cases.json").read_text(encoding="utf-8"))["cases"]
CASES_BY_ID = {c["id"]: c for c in PAYLOAD_CASES}
MATRIX = json.loads((FIXTURES / "matrix.json").read_text(encoding="utf-8"))["rows"]
EVALUATOR = {"commit": "0b74d410b45e7b3efcf08d00ce58e7bd7017b757",
             "wheel_sha256": "e3fcc769c440ed232ad05117f256739daf233e0c9f6d3d46586adc0de9b48c51",
             "python": "stub"}


def _stdout(case: dict) -> str:
    return case["stdout"] if "stdout" in case else json.dumps(case["payload"])


# ── git repositories built with plumbing only ────────────────────────────────

def _git(repo: Path, *args: str, stdin: bytes | None = None) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "c4", "GIT_AUTHOR_EMAIL": "c4@example.invalid",
           "GIT_COMMITTER_NAME": "c4", "GIT_COMMITTER_EMAIL": "c4@example.invalid"}
    proc = subprocess.run(["git", "-C", str(repo), *args], input=stdin, capture_output=True, env=env)
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    return proc.stdout.decode().strip()


def _blob(repo: Path, data: bytes) -> str:
    return _git(repo, "hash-object", "-w", "--stdin", stdin=data)


def _add(repo: Path, mode: str, sha: str, path: str) -> None:
    _git(repo, "update-index", "--add", "--cacheinfo", f"{mode},{sha},{path}")


BASE_FILES = {
    ".github/workflows/gate.yml": b"name: gate\n",
    "docs/old.md": b"old\n",
    "docs/other.md": b"other\n",
    "README.md": b"fixture\n",
}


def build_repo(tmp: Path, *, changes: list[dict], base_memory=True,
               base_files: dict[str, bytes] | None = None, memory: bytes = b"{}\n") -> tuple[Path, str, str]:
    repo = tmp / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "core.ignorecase", "false")
    for path, data in (base_files if base_files is not None else BASE_FILES).items():
        _add(repo, "100644", _blob(repo, data), path)
    if base_memory is True:
        _add(repo, "100644", _blob(repo, memory), gate.MEMORY_REL)
    elif base_memory == "symlink":
        _add(repo, "120000", _blob(repo, b"../elsewhere.json"), gate.MEMORY_REL)
    base = _git(repo, "commit-tree", _git(repo, "write-tree"), "-m", "base")
    for ch in changes:
        if ch["op"] == "write":
            _add(repo, "100644", _blob(repo, ch["content"].encode()), ch["path"])
        elif ch["op"] == "delete":
            _git(repo, "update-index", "--force-remove", ch["path"])
        elif ch["op"] == "symlink":
            _add(repo, "120000", _blob(repo, ch["target"].encode()), ch["path"])
        elif ch["op"] == "submodule":
            _add(repo, "160000", base, ch["path"])
        else:  # pragma: no cover - fixture error
            raise AssertionError(ch)
    head = _git(repo, "commit-tree", _git(repo, "write-tree"), "-p", base, "-m", "head")
    return repo, base, head


# ── stub evaluator ───────────────────────────────────────────────────────────

STUB = '''
import json, sys, time
cases = {c["id"]: c for c in json.load(open(sys.argv[3], encoding="utf-8"))["cases"]}
text = open(sys.argv[1], encoding="utf-8").read()
if text.startswith("c4-sleep"):
    time.sleep(60)
case = cases[text.split(":", 1)[1].strip()]
sys.stdout.write(case["stdout"] if "stdout" in case else json.dumps(case["payload"]))
sys.exit(case["exit"])
'''


@pytest.fixture
def stub(tmp_path, monkeypatch):
    script = tmp_path / "stub_evaluator.py"
    script.write_text(STUB, encoding="utf-8")

    def command(venv_python, memory, target, mode, empty_dir):
        assert memory.read_bytes()  # the trusted memory was materialized first
        return [str(venv_python), str(script), str(target), mode, str(FIXTURES / "payload_cases.json")]

    monkeypatch.setattr(gate, "evaluator_command", command)
    return script


def run(tmp: Path, repo: Path, base: str, head: str, *, mode="strict", posture="closed",
        surface=(), venv_python=None, timeout_s=30.0, tag="run") -> dict:
    return gate.run_gate(repo=repo, base_sha=base, head_sha=head, workspace=tmp / f"ws-{tag}",
                         empty_dir=tmp / f"empty-{tag}", venv_python=Path(venv_python or sys.executable),
                         mode=mode, posture_raw=posture, surface_entries=list(surface),
                         evaluator=EVALUATOR, timeout_s=timeout_s)


def expected_pins(report: dict) -> dict:
    return {"base_sha": report["base_sha"], "head_sha": report["head_sha"],
            "requested_mode": report["requested_mode"], "adapter_sha256": gate.adapter_identity()["sha256"],
            "evaluator_commit": EVALUATOR["commit"], "evaluator_wheel_sha256": EVALUATOR["wheel_sha256"]}


def decision(report: dict, posture: str | None, *, adapter_exit=None, summary: str | None = "auto", **override):
    if adapter_exit is None:
        adapter_exit = 0 if report["disposition"] == gate.SUCCESS else 1
    if summary == "auto":
        summary = gate.summary_markdown(report)
    return gate.verify_report(report, adapter_exit=adapter_exit, expected={**expected_pins(report), **override},
                              posture_raw=posture, summary_text=summary)


# ── Gate 0 matrix, every row, both postures, each listed mode ────────────────

MATRIX_PARAMS = [(row["id"], mode, posture) for row in MATRIX for mode in row["modes"] for posture in ("closed", "open")]


@pytest.mark.parametrize("row_id,mode,posture", MATRIX_PARAMS)
def test_gate0_matrix_row(tmp_path, stub, row_id, mode, posture):
    row = next(r for r in MATRIX if r["id"] == row_id)
    repo, base, head = build_repo(tmp_path, changes=row["changes"], base_memory=row["base_memory"])
    if row["head"] == "missing":
        head = "0" * 40
    report = run(tmp_path, repo, base, head, mode=mode, posture=posture, surface=row["trusted_surface"],
                 venv_python=tmp_path / "no-such-python" if row["launch_fail"] else None,
                 timeout_s=1.5 if row_id == "O6t" else 30.0)
    want_agg, want_disp = row["expect"][posture]
    assert (report["aggregate"]["classification"], report["disposition"]) == (want_agg, want_disp), \
        json.dumps(report["files"] + report["gate_conditions"], indent=1)

    # Invariants that hold for every row.
    assert report["posture"]["effective"] == posture and report["posture"]["fallback"] is None
    assert report["requested_mode"] == mode
    if want_agg in (gate.REFUSED, gate.VIOLATION):
        assert want_disp == gate.FAILURE
    problems = decision(report, posture)
    assert (problems == []) == (want_disp == gate.SUCCESS), problems
    if want_agg == gate.UNEVALUATED and want_disp == gate.SUCCESS:
        assert any(a.startswith("::warning") and "UNEVALUATED" in a for a in report["annotations"])
        assert "UNEVALUATED is not a PASS" in gate.summary_markdown(report)
    if want_disp == gate.FAILURE:
        assert any(a.startswith("::error") for a in report["annotations"])


def test_matrix_covers_every_gate0_row():
    ids = {r["id"] for r in MATRIX}
    for required in ("O1", "O2", "O2w", "O3", "O4", "O5", "O6t", "O6l", "O7", "O8", "O8s", "O9", "O9s",
                     "O9n", "O10", "O10x", "O11a", "O11b", "O11c", "O11d", "O11dw", "O11e"):
        assert required in ids, required


def test_symlink_and_submodule_on_protected_paths_are_policy_refusals_not_mode(tmp_path, stub):
    """A1: the CI1 lab gate classed these by file mode first."""
    repo, base, head = build_repo(tmp_path, changes=[
        {"op": "symlink", "path": ".mneme/project_memory.json", "target": "../docs/x.md"},
        {"op": "symlink", "path": ".github/workflows/evil.yml", "target": "../x"},
        {"op": "submodule", "path": "gate/vendor"}])
    report = run(tmp_path, repo, base, head, posture="open", surface=["gate/"])
    kinds = {f["path"]: (f["classification"], f["kind"]) for f in report["files"]}
    assert kinds == {".mneme/project_memory.json": ("REFUSED", "policy"),
                     ".github/workflows/evil.yml": ("REFUSED", "trusted_surface"),
                     "gate/vendor": ("REFUSED", "trusted_surface")}
    assert report["disposition"] == gate.FAILURE


def test_non_regular_entries_outside_the_surface_are_unevaluated_with_reasons(tmp_path, stub):
    repo, base, head = build_repo(tmp_path, changes=[
        {"op": "symlink", "path": "docs/link.md", "target": "../../outside"},
        {"op": "submodule", "path": "docs/vendor"}])
    report = run(tmp_path, repo, base, head, posture="open")
    assert {(f["classification"], f["kind"], f["reason"]) for f in report["files"]} == {
        ("UNEVALUATED", "mode", "not a regular file (symlink)"),
        ("UNEVALUATED", "mode", "not a regular file (submodule)")}


def test_mixed_results_keep_subordinate_detail(tmp_path, stub):
    """Gate 1 §3: a blocking violation plus an unevaluated file is reported as partly unevaluated."""
    row = next(r for r in MATRIX if r["id"] == "O11b")
    repo, base, head = build_repo(tmp_path, changes=row["changes"])
    report = run(tmp_path, repo, base, head, posture="open")
    assert report["aggregate"]["classification"] == gate.VIOLATION
    assert report["aggregate"]["partly_unevaluated"] is True
    assert report["aggregate"]["counts"] == {"VIOLATION": 1, "UNEVALUATED": 1}


def test_excluded_applicability_is_recorded_but_only_a_pass(tmp_path, stub):
    row = next(r for r in MATRIX if r["id"] == "O10x")
    repo, base, head = build_repo(tmp_path, changes=row["changes"])
    report = run(tmp_path, repo, base, head)
    (f,) = report["files"]
    assert f["classification"] == gate.VERIFIED_PASS
    assert [a["outcome"] for a in f["applicability"]] == ["EXCLUDED"]


def test_skip_only_is_never_reported_as_pass(tmp_path, stub):
    repo, base, head = build_repo(tmp_path, changes=[{"op": "delete", "path": "docs/old.md"}])
    report = run(tmp_path, repo, base, head)
    assert report["aggregate"]["classification"] == gate.SKIP
    assert "PASS" not in report["aggregate"]["classification"]
    assert report["memory"] is None  # nothing was evaluated, so memory was not read


def test_report_records_pins_memory_and_surface(tmp_path, stub):
    repo, base, head = build_repo(tmp_path, changes=[{"op": "write", "path": "docs/a.md", "content": "c4-case:strict_pass\n"}])
    report = run(tmp_path, repo, base, head, surface=["gate/", "tools/pin.txt"])
    assert report["schema"] == gate.REPORT_SCHEMA
    assert report["adapter"]["sha256"] == hashlib.sha256(ADAPTER_PATH.read_bytes()).hexdigest()
    assert report["evaluator"] == EVALUATOR
    assert report["merge_base"] == base
    assert report["memory"]["blob"] == _git(repo, "rev-parse", f"{base}:{gate.MEMORY_REL}")
    assert report["trusted_surface"] == {"files": [".gitattributes", ".gitmodules", "tools/pin.txt"],
                                         "dirs": [".github/", "gate/"]}
    assert report["query"] == gate.QUERY


def test_existing_workspace_is_unevaluated_not_reused(tmp_path, stub):
    repo, base, head = build_repo(tmp_path, changes=[{"op": "write", "path": "docs/a.md", "content": "c4-case:strict_pass\n"}])
    (tmp_path / "ws-run").mkdir()
    report = run(tmp_path, repo, base, head, posture="closed")
    (f,) = report["files"]
    assert (f["classification"], f["kind"], report["disposition"]) == ("UNEVALUATED", "workspace", "failure")


@pytest.mark.parametrize("entry", ["../gate/", "gate//", "gate///", "/", "//", "", "gate/../x/", "./gate/",
                                   "gate\\", "/gate/", "gate//x.py", "docs/\udcff/"])
def test_invalid_trusted_surface_entry_refuses(tmp_path, stub, entry):
    """Review finding 2 on #679: ``gate//`` used to pass validation and protect nothing."""
    repo, base, head = build_repo(tmp_path, changes=[{"op": "write", "path": "gate/config.py", "content": "c4-case:strict_pass\n"}])
    report = run(tmp_path, repo, base, head, posture="open", surface=[entry])
    assert (report["aggregate"]["classification"], report["disposition"]) == ("REFUSED", "failure")
    assert report["gate_conditions"][0]["kind"] == "change_list"


@pytest.mark.parametrize("entry,protected", [("gate/", "gate/config.py"), ("tools/pin.txt", "tools/pin.txt"),
                                              ("a/b/", "A/B/c.py")])
def test_valid_trusted_surface_entries_protect_their_paths(entry, protected):
    surface = gate.normalize_surface([entry])
    assert gate.path_refusal(protected, surface)[0] == "trusted_surface"


# ── O9p: unnormalizable paths (git cannot store most of these) ───────────────

SURFACE = gate.normalize_surface(["gate/"])


@pytest.mark.parametrize("path,kind", [
    ("docs\\a.md", "path"), ("/etc/passwd", "path"), ("docs/../.mneme/x", "path"), ("./docs/a.md", "path"),
    ("docs//a.md", "path"), ("docs/a.md/", "path"), ("", "path"), ("docs/a\0.md", "path"),
    ("docs/\udcff.md", "path"),
    (".mneme", "policy"), (".mneme/project_memory.json", "policy"), (".MNEME/x", "policy"), (".Mneme", "policy"),
    (".github", "trusted_surface"), (".GitHub/workflows/x.yml", "trusted_surface"),
    (".gitattributes", "trusted_surface"), (".GITMODULES", "trusted_surface"),
    ("gate", "trusted_surface"), ("Gate/x.py", "trusted_surface"),
])
def test_path_refusals(path, kind):
    assert gate.path_refusal(path, SURFACE)[0] == kind


@pytest.mark.parametrize("path", ["docs/a.md", "docs/.mneme/x", "docs/.github/x", "gateway/x.py", ".mnemeignore",
                                  ".githubx/y", "src/notes.md"])
def test_paths_outside_the_surface_are_not_refused(path):
    assert gate.path_refusal(path, SURFACE) is None


@pytest.mark.parametrize("mode", ["120000", "160000", "100644", "000000"])
@pytest.mark.parametrize("status", ["A", "M", "T", "D"])
def test_unnormalizable_path_is_refused_for_every_status_and_mode(status, mode):
    entry = {"status": status, "old_mode": mode, "mode": mode, "blob": "0" * 40, "path": "docs\\..\\x"}
    (rec,) = gate.classify_entries([entry], SURFACE)
    assert (rec["classification"], rec["kind"]) == ("REFUSED", "path")


def test_a1_order_on_raw_entries():
    entries = [
        {"status": "T", "old_mode": "100644", "mode": "120000", "blob": "1" * 40, "path": ".mneme/project_memory.json"},
        {"status": "D", "old_mode": "100644", "mode": "000000", "blob": "0" * 40, "path": ".github/workflows/g.yml"},
        {"status": "D", "old_mode": "100644", "mode": "000000", "blob": "0" * 40, "path": "docs/old.md"},
        {"status": "A", "old_mode": "000000", "mode": "120000", "blob": "2" * 40, "path": "docs/l.md"},
        {"status": "A", "old_mode": "000000", "mode": "100644", "blob": "3" * 40, "path": "docs/a.md"},
    ]
    got = [(r["classification"], r.get("kind")) for r in gate.classify_entries(entries, SURFACE)]
    assert got == [("REFUSED", "policy"), ("REFUSED", "trusted_surface"), ("SKIP", "deleted"),
                   ("UNEVALUATED", "mode"), (None, None)]


def test_raw_diff_parser_rejects_garbage():
    with pytest.raises(gate.GateError):
        gate.parse_raw_diff(b"not a record\0path\0")


# ── payload coherence (A4) and parity with assess_verdict (#484) ─────────────

@pytest.mark.parametrize("case_id", list(CASES_BY_ID))
def test_payload_case_classification(case_id):
    case = CASES_BY_ID[case_id]
    cls, reason = gate.classify_payload(_stdout(case), case["exit"], case["mode"])
    assert cls == case["expected"], reason


@pytest.mark.parametrize("case_id", list(CASES_BY_ID))
def test_payload_case_parity_with_assess_verdict(case_id):
    """Never trust what the shipped validator rejects; diverge only where ADR-033 §2 requires."""
    from mneme.integrations.claude_code.hook import assess_verdict

    case = CASES_BY_ID[case_id]
    cls, _ = gate.classify_payload(_stdout(case), case["exit"], case["mode"])
    assessed = assess_verdict(_stdout(case), case["exit"], case["mode"])
    shipped_trusted = assessed.payload is not None
    if case["assess"] == "agree":
        assert shipped_trusted and cls != gate.UNEVALUATED
        assert {"PASS": gate.VERIFIED_PASS, "WARN": gate.WARN, "FAIL": gate.VIOLATION}[assessed.payload["verdict"]] == cls
    elif case["assess"] == "untrusted":
        assert not shipped_trusted and cls == gate.UNEVALUATED
    else:  # "stricter": accepted by assess_verdict, deliberately not by the adapter
        assert shipped_trusted and cls == gate.UNEVALUATED


def test_ci1_stub_outputs_are_never_trusted():
    ci1 = _load("ci1_contract_matrix", REPO_ROOT / "tests" / "test_ci1_contract_matrix.py")
    for name, (exit_code, stdout) in ci1.STUBS.items():
        for mode in ("strict", "warn"):
            assert gate.classify_payload(stdout, exit_code, mode)[0] == gate.UNEVALUATED, (name, mode)


def test_adapter_trusts_nothing_the_ci1_classifier_rejects():
    ci1 = _load("ci1_contract_matrix_b", REPO_ROOT / "tests" / "test_ci1_contract_matrix.py")
    for case in PAYLOAD_CASES:
        cls, _ = gate.classify_payload(_stdout(case), case["exit"], case["mode"])
        if cls != gate.UNEVALUATED:
            assert ci1.classify(case["exit"], _stdout(case)) != ci1.UNEVALUATED, case["id"]


def test_exit_status_must_be_an_int():
    stdout = _stdout(CASES_BY_ID["strict_pass"])
    for bad in ("0", None, True, 0.0):
        assert gate.classify_payload(stdout, bad, "strict")[0] == gate.UNEVALUATED


def test_exit_tables_match_the_cli():
    from mneme import cli

    assert {m: {k.value: v for k, v in t.items()} for m, t in cli._EXIT_CODES_BY_MODE.items()} == gate.EXIT_CODES_BY_MODE
    assert cli.CHECK_JSON_SCHEMA == gate.CONTRACT


# ── A2 with R1, and A3 ───────────────────────────────────────────────────────

@pytest.mark.parametrize("classes,mode,agg", [
    (["VERIFIED_PASS"], "strict", "PASS"),
    (["VERIFIED_PASS", "SKIP"], "strict", "PASS"),
    (["SKIP"], "strict", "SKIP"),
    ([], "strict", "SKIP"),
    (["WARN"], "strict", "VIOLATION"),
    (["WARN", "UNEVALUATED"], "strict", "VIOLATION"),
    (["WARN", "UNEVALUATED"], "warn", "UNEVALUATED"),
    (["VIOLATION"], "warn", "WARN"),
    (["WARN", "VERIFIED_PASS"], "warn", "WARN"),
    (["VIOLATION", "UNEVALUATED"], "strict", "VIOLATION"),
    (["VERIFIED_PASS", "UNEVALUATED"], "warn", "UNEVALUATED"),
    (["REFUSED", "VIOLATION", "UNEVALUATED", "VERIFIED_PASS"], "warn", "REFUSED"),
    (["REFUSED", "SKIP"], "strict", "REFUSED"),
])
def test_aggregate_precedence(classes, mode, agg):
    assert gate.aggregate(classes, mode) == agg


@pytest.mark.parametrize("agg,closed,open_", [
    ("PASS", "success", "success"), ("WARN", "success", "success"), ("SKIP", "success", "success"),
    ("UNEVALUATED", "failure", "success"), ("VIOLATION", "failure", "failure"), ("REFUSED", "failure", "failure"),
])
def test_disposition(agg, closed, open_):
    assert (gate.disposition(agg, "closed"), gate.disposition(agg, "open")) == (closed, open_)


@pytest.mark.parametrize("raw", [None, "", "Open", "OPEN", "open ", " closed", "true", "1", "opened"])
def test_o12_missing_or_invalid_posture_is_closed_with_a_warning(raw):
    posture = gate.resolve_posture(raw)
    assert posture["effective"] == "closed" and posture["fallback"]


@pytest.mark.parametrize("raw", ["open", "closed"])
def test_valid_postures(raw):
    assert gate.resolve_posture(raw) == {"effective": raw, "source": "vars.MNEME_CI_AVAILABILITY", "fallback": None}


@pytest.mark.parametrize("raw", [None, "Open"])
def test_o12_end_to_end(tmp_path, stub, raw):
    row = next(r for r in MATRIX if r["id"] == "O3")
    repo, base, head = build_repo(tmp_path, changes=row["changes"])
    report = run(tmp_path, repo, base, head, posture=raw)
    assert (report["aggregate"]["classification"], report["disposition"]) == ("UNEVALUATED", "failure")
    assert report["annotations"][0].startswith("::warning title=ADR-033 C4 posture::")
    assert "Posture warning" in gate.summary_markdown(report)


def test_posture_is_never_passed_to_the_evaluator(monkeypatch):
    monkeypatch.setenv(gate.POSTURE_VAR, "open")
    monkeypatch.setenv("PYTHONPATH", "x")
    env = gate.clean_env()
    assert gate.POSTURE_VAR not in env and "PYTHONPATH" not in env


# ── workflow-command and markdown injection ──────────────────────────────────

def test_annotations_cannot_inject_workflow_commands(tmp_path, stub, monkeypatch):
    # Git for Windows refuses such a path, so the change list is injected directly.
    entry = {"status": "A", "old_mode": "000000", "mode": "120000", "blob": "1" * 40, "path": "docs/x\n::error::fake.md"}
    monkeypatch.setattr(gate, "changed_entries", lambda repo, base, head: (base, [entry]))
    report = run(tmp_path, tmp_path, "a" * 40, "b" * 40, posture="open")
    assert report["aggregate"]["classification"] == gate.UNEVALUATED
    for line in report["annotations"]:
        assert "\n" not in line and "\r" not in line
    summary = gate.summary_markdown(report)
    assert "\n::error::" not in summary


# ── trusted decision step (Gate 1 §4 and §5 item 6) ──────────────────────────

@pytest.fixture
def open_unevaluated(tmp_path, stub):
    row = next(r for r in MATRIX if r["id"] == "O3")
    repo, base, head = build_repo(tmp_path, changes=row["changes"])
    return run(tmp_path, repo, base, head, posture="open")


def test_decision_accepts_a_consistent_open_unevaluated_report(open_unevaluated):
    assert decision(open_unevaluated, "open") == []


@pytest.mark.parametrize("override", [
    {"base_sha": "f" * 40}, {"head_sha": "f" * 40}, {"requested_mode": "warn"},
    {"adapter_sha256": "0" * 64}, {"evaluator_commit": "1" * 40}, {"evaluator_wheel_sha256": "0" * 64},
])
def test_decision_rejects_pin_mismatch(open_unevaluated, override):
    assert decision(open_unevaluated, "open", **override)


def test_decision_rejects_a_report_with_the_wrong_evaluator_commit(open_unevaluated):
    """Review finding 1 on #679: the wheel hash alone is not the evaluator identity."""
    forged = json.loads(json.dumps(open_unevaluated))
    forged["evaluator"]["commit"] = "1" * 40
    assert any("evaluator_commit" in p for p in decision(forged, "open"))


@pytest.mark.parametrize("key", ["base_sha", "head_sha", "requested_mode", "adapter_sha256",
                                 "evaluator_commit", "evaluator_wheel_sha256"])
def test_decision_requires_every_trusted_pin(open_unevaluated, key):
    expected = {**expected_pins(open_unevaluated), key: ""}
    problems = gate.verify_report(open_unevaluated, adapter_exit=0, expected=expected, posture_raw="open",
                                  summary_text=gate.summary_markdown(open_unevaluated))
    assert any(f"no trusted {key}" in p for p in problems)


def test_decision_rejects_a_report_whose_posture_differs_from_the_trusted_posture(open_unevaluated):
    problems = decision(open_unevaluated, "closed")
    assert any("posture" in p for p in problems)


def test_decision_reads_an_invalid_trusted_posture_as_closed(open_unevaluated):
    assert decision(open_unevaluated, "Open")


def test_decision_rejects_missing_summary_or_annotation(open_unevaluated):
    assert any("job-summary" in p for p in decision(open_unevaluated, "open", summary=None))
    tampered = {**open_unevaluated, "annotations": []}
    assert any("annotation" in p for p in decision(tampered, "open"))


def test_decision_rejects_adapter_exit_disagreement(open_unevaluated):
    assert decision(open_unevaluated, "open", adapter_exit=1)
    assert decision(open_unevaluated, "open", adapter_exit="0")


def test_decision_recomputes_aggregate_and_disposition(open_unevaluated):
    forged = json.loads(json.dumps(open_unevaluated))
    forged["files"][0]["classification"] = gate.REFUSED
    problems = decision(forged, "open")
    assert any("aggregate" in p for p in problems) and any("required check fails" in p for p in problems)
    forged = json.loads(json.dumps(open_unevaluated))
    forged["aggregate"]["classification"] = "PASS"
    assert decision(forged, "open")


@pytest.mark.parametrize("report", [None, [], "x", {}, {"schema": "mneme.c4.gate-report/v1"}])
def test_decision_rejects_missing_or_malformed_reports(report):
    assert gate.verify_report(report, adapter_exit=0, expected={}, posture_raw="open", summary_text="UNEVALUATED")


def test_decision_rejects_unknown_file_classification(open_unevaluated):
    forged = json.loads(json.dumps(open_unevaluated))
    forged["files"][0]["classification"] = "PASSISH"
    assert decision(forged, "open")


def test_decision_never_accepts_refused_or_strict_violation(tmp_path, stub):
    for row_id in ("O8", "O2", "O2-R1", "O11d"):
        sub = tmp_path / row_id
        sub.mkdir()
        row = next(r for r in MATRIX if r["id"] == row_id)
        repo, base, head = build_repo(sub, changes=row["changes"])
        report = run(sub, repo, base, head, posture="open")
        assert decision(report, "open", adapter_exit=0)


# ── command line, end to end without a real evaluator ────────────────────────

def _cli(*args: str, env_posture: str | None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != gate.POSTURE_VAR}
    if env_posture is not None:
        env[gate.POSTURE_VAR] = env_posture
    return subprocess.run([sys.executable, "-I", str(ADAPTER_PATH), *args], capture_output=True, text=True,
                          encoding="utf-8", env=env)


@pytest.mark.parametrize("posture,evaluate_exit,decision_exit", [("closed", 1, 1), ("open", 0, 0), (None, 1, 1)])
def test_cli_launch_failure_then_decision(tmp_path, posture, evaluate_exit, decision_exit):
    repo, base, head = build_repo(tmp_path, changes=[{"op": "write", "path": "docs/a.md", "content": "x\n"}])
    report, summary = tmp_path / "out" / "report.json", tmp_path / "out" / "summary.md"
    report.parent.mkdir()
    ev = _cli("evaluate", "--repo", str(repo), "--base-sha", base, "--head-sha", head, "--mode", "strict",
              "--workspace", str(tmp_path / "ws"), "--empty-dir", str(tmp_path / "empty"),
              "--venv-python", str(tmp_path / "missing-python"), "--evaluator-commit", EVALUATOR["commit"],
              "--evaluator-wheel-sha256", EVALUATOR["wheel_sha256"], "--trusted-surface", "gate/",
              "--report", str(report), "--summary", str(summary), env_posture=posture)
    assert ev.returncode == evaluate_exit, ev.stdout + ev.stderr
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["aggregate"]["classification"] == "UNEVALUATED" and data["summary_written"] is True
    assert "UNEVALUATED" in summary.read_text(encoding="utf-8")
    vr = _cli("verify-report", "--report", str(report), "--adapter-exit", str(ev.returncode),
              "--base-sha", base, "--head-sha", head, "--mode", "strict",
              "--adapter-sha256", hashlib.sha256(ADAPTER_PATH.read_bytes()).hexdigest(),
              "--evaluator-commit", EVALUATOR["commit"], "--evaluator-wheel-sha256", EVALUATOR["wheel_sha256"], "--summary", str(summary),
              env_posture=posture)
    assert vr.returncode == decision_exit, vr.stdout + vr.stderr


def test_cli_decision_fails_on_a_missing_report(tmp_path):
    vr = _cli("verify-report", "--report", str(tmp_path / "none.json"), "--adapter-exit", "0",
              "--base-sha", "a", "--head-sha", "b", "--mode", "strict", "--adapter-sha256", "c",
              "--evaluator-commit", "e", "--evaluator-wheel-sha256", "d", env_posture="open")
    assert vr.returncode == 1 and "::error" in vr.stdout


def test_cli_requires_an_explicit_mode(tmp_path):
    ev = _cli("evaluate", "--repo", ".", "--base-sha", "a", "--head-sha", "b", "--workspace", "w",
              "--empty-dir", "e", "--venv-python", "p", "--evaluator-commit", "c",
              "--evaluator-wheel-sha256", "d", "--report", "r", env_posture=None)
    assert ev.returncode == 2 and "--mode" in ev.stderr


# ── adapter identity and boundary ────────────────────────────────────────────

def test_adapter_is_standard_library_only():
    tree = ast.parse(ADAPTER_PATH.read_text(encoding="utf-8"))
    imported = {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    imported |= {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert imported <= {"__future__", "argparse", "hashlib", "json", "os", "subprocess", "sys", "pathlib", "typing"}


def test_adapter_is_outside_the_wheel():
    """Gate 0 A5: the adapter ships by blob hash, not inside ``mneme-hq``."""
    import tomllib

    find = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]["packages"]["find"]
    assert find["include"] == ["mneme*"]
    assert ADAPTER_PATH.relative_to(REPO_ROOT).parts[0] == "scripts"


# ── real evaluator on the CI1.2.1 corpus (when importable under python -I) ───

def _real_evaluator() -> str | None:
    candidate = os.environ.get("MNEME_C4_EVALUATOR_PYTHON") or sys.executable
    try:
        probe = subprocess.run([candidate, "-I", "-c", "import mneme.cli"], capture_output=True,
                               cwd=Path(candidate).parent, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return candidate if probe.returncode == 0 else None


REAL_EVALUATOR = _real_evaluator()
needs_real = pytest.mark.skipif(REAL_EVALUATOR is None, reason="mneme is not importable under python -I here")


@needs_real
@pytest.mark.parametrize("path,source,mode,agg,disp", [
    ("docs/guide.md", "docs/guide_compliant.md", "strict", "PASS", "success"),
    ("docs/guide.md", "docs/guide_violating.md", "strict", "VIOLATION", "failure"),
    ("docs/guide.md", "docs/guide_violating.md", "warn", "WARN", "success"),
    ("docs/history/migration.md", "docs/history/migration.md", "strict", "PASS", "success"),
    ("src/notes.md", "src/notes.md", "strict", "PASS", "success"),
])
def test_real_evaluator_on_ci1_corpus(tmp_path, path, source, mode, agg, disp):
    memory = (CI1_CORPUS / "project_memory.json").read_bytes()
    content = (CI1_CORPUS / source).read_text(encoding="utf-8")
    repo, base, head = build_repo(tmp_path, memory=memory,
                                  changes=[{"op": "write", "path": path, "content": content}])
    report = run(tmp_path, repo, base, head, mode=mode, posture="open", venv_python=REAL_EVALUATOR, timeout_s=120)
    assert (report["aggregate"]["classification"], report["disposition"]) == (agg, disp), \
        json.dumps(report["files"], indent=1)[:3000]
    if path != "docs/guide.md":
        assert [a["outcome"] for a in report["files"][0]["applicability"]] == ["EXCLUDED"]
