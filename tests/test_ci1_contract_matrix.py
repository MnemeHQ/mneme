"""CI1.2.2: outcome matrix for the CI-platform-independent check contract.

Extends the CI1.2.1 path-scoped fixture (``test_ci1_contract_fixtures.py``)
with the outcomes a CI adapter must classify besides a clean PASS or FAIL:

- the repository's own global ADR-005 ``FORBID_LITERAL`` rule (regression
  cross-check against the canonical memory, read-only);
- a WARN verdict in strict mode (exit 1) and warn mode (exit 0);
- a missing or malformed memory file (no payload at all);
- incomplete evaluation other than the CI1.2.1 out-of-root case;
- contradictory or unparseable CLI output, classified from stubs.

Every live case runs ``python -m mneme.cli check --json`` as a subprocess, the
boundary any adapter crosses. The corpora live in
``tests/fixtures/ci1_contract/<corpus>/v1``; their READMEs are the contract.
The classification is descriptive (CI1.1 A3), not a blocking policy: whether
UNEVALUATED blocks a merge belongs to ADR-033 (#483), not to this file.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPORA = REPO_ROOT / "tests" / "fixtures" / "ci1_contract"
CONTRACT = "mneme.check/v1"

VERIFIED_PASS = "VERIFIED_PASS"
VIOLATION = "VIOLATION"
UNEVALUATED = "UNEVALUATED"

# The verdict -> exit-code mapping of a *complete* evaluation, as documented
# for `mneme check`. Restated here rather than imported: an adapter only sees
# the CLI boundary, so the contract must not depend on mneme internals.
CONTRACT_EXIT_CODES = {
    "strict": {"PASS": 0, "WARN": 1, "FAIL": 2},
    "warn": {"PASS": 0, "WARN": 0, "FAIL": 0},
}


def _spec(corpus: str) -> tuple[Path, dict]:
    root = CORPORA / corpus / "v1"
    return root, json.loads((root / "cases.json").read_text(encoding="utf-8"))


def _env() -> dict[str, str]:
    # Import the tree under test, not whichever mneme is installed.
    return {**os.environ, "PYTHONPATH": str(REPO_ROOT)}


def _cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "mneme.cli", *args],
        cwd=cwd, env=_env(), capture_output=True, text=True, encoding="utf-8",
    )


def classify(exit_code: int, stdout: str) -> str:
    """Classify one raw `mneme check --json` result (CI1.1 A3, descriptive).

    VERIFIED_PASS is the only class that can let a change through on its own,
    so it requires every signal to agree: a single parseable payload under the
    contract schema, ``evaluation_complete`` exactly ``true``, verdict PASS,
    no violations, and the exit code the contract assigns to that verdict in
    that mode. Anything self-contradictory or unparseable is UNEVALUATED.
    """
    try:
        payload = json.loads(stdout)
    except (TypeError, ValueError):
        return UNEVALUATED
    if not isinstance(payload, dict) or payload.get("schema") != CONTRACT:
        return UNEVALUATED
    # Read evaluation_complete before verdict (CI1.1 F1).
    if payload.get("evaluation_complete") is not True:
        return UNEVALUATED
    verdict = payload.get("verdict")
    expected_exit = CONTRACT_EXIT_CODES.get(payload.get("mode"), {}).get(verdict)
    if expected_exit is None or type(exit_code) is not int or exit_code != expected_exit:
        return UNEVALUATED
    violations = payload.get("violations")
    if not isinstance(violations, list):
        return UNEVALUATED
    if verdict == "PASS":
        return VERIFIED_PASS if not violations else UNEVALUATED
    # WARN and FAIL both report at least one violation record; severity stays
    # in the payload. A verdict that claims a violation but lists none is
    # self-contradictory.
    return VIOLATION if violations else UNEVALUATED


def _canonical(payload: dict) -> dict:
    """Record order follows retrieval ranking, so it is not part of the
    contract; compare applicability and violations keyed by rule identity."""
    out = dict(payload)
    for key in ("applicability", "violations"):
        out[key] = sorted(
            payload[key], key=lambda r: (r.get("rule_id") or "", r["decision_id"]),
        )
    return out


def _run_case(root: Path, spec: dict, case: dict, query: str, top: int):
    args = [
        "check", "--memory", spec["memory"], "--input", case["input"],
        "--query", query, "--top", str(top), "--mode", case["mode"], "--json",
    ]
    if spec["adr_dir"]:
        args += ["--adr-dir", spec["adr_dir"]]
    if case["target_path"]:
        args += ["--target-path", case["target_path"]]
    return _cli(args, root)


# ── 1. ADR-005 global FORBID_LITERAL against the canonical memory ────────────

ADR005_RULE_ID = "ADR-005:FORBID_LITERAL:cbf4d271068507ddb12c33abd765e333"
# Assembled at runtime so no committed file carries the forbidden literal
# (scripts/check_install_command.py and the repository's own ADR-005 rule).
FORBIDDEN_INSTALL = " ".join(["pip", "install", "mneme"])
CANONICAL_MEMORY = REPO_ROOT / ".mneme" / "project_memory.json"


def _adr005_rule() -> dict:
    index = json.loads(CANONICAL_MEMORY.read_text(encoding="utf-8"))["decision_index"]
    [rule] = [r for r in index["rules"] if r["rule_id"] == ADR005_RULE_ID]
    return rule


def _check_canonical(tmp_path: Path, text: str, target: str | None, query: str, top: int):
    artifact = tmp_path / "artifact.md"
    artifact.write_text(text, encoding="utf-8")
    args = [
        "check", "--memory", ".mneme/project_memory.json", "--input", str(artifact),
        "--query", query, "--top", str(top), "--mode", "strict", "--json",
    ]
    if target:
        args += ["--target-path", target]
    proc = _cli(args, REPO_ROOT)
    return proc.returncode, proc.stdout, json.loads(proc.stdout)


def test_adr005_canonical_rule_is_global_forbid_literal():
    rule = _adr005_rule()
    assert rule["decision_id"] == "ADR-005"
    assert rule["rule_type"] == "FORBID_LITERAL"
    assert rule["rule_payload"] == {"value": FORBIDDEN_INSTALL}
    assert rule["applicability"] == {}


ADR005_TARGETS = [None, "README.md", "docs/history/archived.md", "../outside-repo.md"]
ADR005_QUERIES = [("pip install package name", 3), ("unrelated words entirely", 1)]


@pytest.mark.parametrize("target", ADR005_TARGETS)
@pytest.mark.parametrize("query,top", ADR005_QUERIES)
def test_adr005_violation_fails_on_every_path_and_query(tmp_path, target, query, top):
    """A global rule is APPLIED wherever the artifact sits, including paths a
    scoped rule would EXCLUDE or report UNKNOWN, and independent of retrieval
    ranking (ADR-017)."""
    rule = _adr005_rule()
    code, stdout, payload = _check_canonical(
        tmp_path, f"Install with `{FORBIDDEN_INSTALL}`.\n", target, query, top,
    )
    assert payload["schema"] == CONTRACT
    assert payload["verdict"] == "FAIL"
    assert payload["evaluation_complete"] is True
    assert code == 2
    [applied] = [a for a in payload["applicability"] if a["rule_id"] == ADR005_RULE_ID]
    assert applied["outcome"] == "APPLIED"
    assert applied["path_scoped"] is False
    [violation] = [v for v in payload["violations"] if v["rule_id"] == ADR005_RULE_ID]
    assert violation["decision_version_id"] == rule["decision_version_id"]
    assert violation["severity"] == "FAIL"
    assert violation["trigger"] == FORBIDDEN_INSTALL
    assert classify(code, stdout) == VIOLATION


@pytest.mark.parametrize("target", ADR005_TARGETS)
def test_adr005_correct_distribution_name_is_not_flagged(tmp_path, target):
    """`mneme-hq` contains the forbidden literal as a prefix; the rule must
    still not fire on it."""
    code, stdout, payload = _check_canonical(
        tmp_path, f"Install with `{FORBIDDEN_INSTALL}-hq`.\n", target, "pip install", 3,
    )
    assert not [v for v in payload["violations"] if v["rule_id"] == ADR005_RULE_ID]
    [applied] = [a for a in payload["applicability"] if a["rule_id"] == ADR005_RULE_ID]
    assert applied["outcome"] == "APPLIED"
    assert payload["verdict"] == "PASS"
    assert payload["evaluation_complete"] is True
    assert code == 0
    assert classify(code, stdout) == VERIFIED_PASS


# ── 2 and 4. golden corpora: WARN verdict, incomplete evaluation ─────────────

GOLDEN_CORPORA = ["warn_verdict", "incomplete_evaluation"]
GOLDEN_CASES = [
    (corpus, case)
    for corpus in GOLDEN_CORPORA
    for case in _spec(corpus)[1]["cases"]
]
GOLDEN_IDS = [f"{corpus}-{case['id']}" for corpus, case in GOLDEN_CASES]


@pytest.mark.parametrize("corpus,case", GOLDEN_CASES, ids=GOLDEN_IDS)
def test_golden_case_matches_contract(corpus, case):
    root, spec = _spec(corpus)
    expected = json.loads((root / case["expected"]).read_text(encoding="utf-8"))
    for variant in spec["query_variants"]:
        proc = _run_case(root, spec, case, variant["query"], variant["top"])
        assert proc.stderr == ""
        payload = json.loads(proc.stdout)
        assert _canonical(payload) == expected, variant
        assert proc.returncode == case["expected_exit"], variant
        assert classify(proc.returncode, proc.stdout) == case["expected_classification"]


def test_warn_verdict_corpus_is_a_legacy_constraint_rule():
    """The WARN path is the legacy `no X` constraint (tests/test_check_modes.py);
    typed rules have no WARN severity."""
    root, _spec_ = _spec("warn_verdict")
    memory = json.loads((root / "project_memory.json").read_text(encoding="utf-8"))
    assert "decision_index" not in memory
    [decision] = memory["decisions"]
    assert decision["constraints"] == ["no postgres"]


def test_warn_is_exit_1_in_strict_and_exit_0_in_warn_mode():
    root, spec = _spec("warn_verdict")
    cases = {c["id"]: c for c in spec["cases"]}
    variant = spec["query_variants"][0]
    strict = _run_case(root, spec, cases["warn_strict"], variant["query"], variant["top"])
    warn = _run_case(root, spec, cases["warn_warn_mode"], variant["query"], variant["top"])
    strict_payload, warn_payload = json.loads(strict.stdout), json.loads(warn.stdout)
    assert strict_payload["verdict"] == warn_payload["verdict"] == "WARN"
    assert strict_payload["violations"] == warn_payload["violations"]
    assert [v["severity"] for v in strict_payload["violations"]] == ["WARN"]
    assert (strict.returncode, warn.returncode) == (1, 0)
    # Exit 0 in warn mode is not a pass: the payload still reports the WARN.
    assert classify(warn.returncode, warn.stdout) == VIOLATION


def test_incomplete_corpus_memory_regenerates_from_source_adrs(tmp_path):
    root, spec = _spec("incomplete_evaluation")
    shutil.copytree(root / "adr", tmp_path / "adr")
    committed = json.loads((root / "project_memory.json").read_text(encoding="utf-8"))
    seed = {k: committed[k] for k in ("meta", "items", "examples")} | {"decisions": []}
    (tmp_path / "project_memory.json").write_text(json.dumps(seed), encoding="utf-8")

    migrate = _cli(["decision-index", "migrate", "--memory", "project_memory.json", "--apply"], tmp_path)
    assert migrate.returncode == 0, migrate.stderr
    imported = _cli(["adr", "import", "--memory", "project_memory.json", "--apply", "adr"], tmp_path)
    assert imported.returncode == 0, imported.stderr

    regenerated = json.loads((tmp_path / "project_memory.json").read_text(encoding="utf-8"))
    assert regenerated == committed
    rules = [
        {k: r[k] for k in ("rule_id", "decision_id", "decision_version_id", "applicability")}
        for r in committed["decision_index"]["rules"]
    ]
    assert rules == spec["rules"]


def test_incomplete_evaluation_exits_2_even_in_warn_mode():
    """Warn mode maps every complete verdict to exit 0, but an incomplete
    evaluation still exits 2: mode does not hide UNKNOWN applicability."""
    root, spec = _spec("incomplete_evaluation")
    [case] = [c for c in spec["cases"] if c["id"] == "unknown_in_warn_mode"]
    variant = spec["query_variants"][0]
    proc = _run_case(root, spec, case, variant["query"], variant["top"])
    payload = json.loads(proc.stdout)
    assert payload["mode"] == "warn"
    assert payload["verdict"] == "PASS"
    assert payload["evaluation_complete"] is False
    assert proc.returncode == 2
    assert classify(proc.returncode, proc.stdout) == UNEVALUATED


def test_incomplete_evaluation_with_a_confirmed_violation_is_unevaluated():
    """A global rule FAILs while a scoped rule is UNKNOWN. The payload carries
    the FAIL and its violation, yet the evaluation is incomplete, so the
    descriptive class is UNEVALUATED. Whether that blocks is ADR-033's call;
    this pins that the violation is still reported, not dropped."""
    root, spec = _spec("incomplete_evaluation")
    [case] = [c for c in spec["cases"] if c["id"] == "unknown_with_global_fail"]
    variant = spec["query_variants"][0]
    proc = _run_case(root, spec, case, variant["query"], variant["top"])
    payload = json.loads(proc.stdout)
    outcomes = {a["decision_id"]: a["outcome"] for a in payload["applicability"]}
    assert outcomes == {"ADR-921": "APPLIED", "ADR-922": "UNKNOWN"}
    assert [v["decision_id"] for v in payload["violations"]] == ["ADR-921"]
    assert payload["verdict"] == "FAIL"
    assert payload["evaluation_complete"] is False
    assert proc.returncode == 2
    assert classify(proc.returncode, proc.stdout) == UNEVALUATED


# ── 3. missing or malformed memory: no payload at all ────────────────────────

_MEM_ROOT, MEM_SPEC = _spec("memory_errors")
MEM_CASES = [(case, mode) for case in MEM_SPEC["cases"] for mode in MEM_SPEC["modes"]]
MEM_IDS = [f"{case['id']}-{mode}" for case, mode in MEM_CASES]


@pytest.mark.parametrize("case,mode", MEM_CASES, ids=MEM_IDS)
def test_memory_error_emits_no_payload(tmp_path, case, mode):
    (tmp_path / "input.md").write_text(MEM_SPEC["input_text"], encoding="utf-8")
    if case["memory_content"] is not None:
        (tmp_path / "project_memory.json").write_text(case["memory_content"], encoding="utf-8")
    proc = _cli([
        "check", "--memory", "project_memory.json", "--input", "input.md",
        "--query", MEM_SPEC["query"], "--top", str(MEM_SPEC["top"]),
        "--mode", mode, "--json",
    ], tmp_path)
    assert proc.stdout == ""
    assert proc.returncode == case["expected_exit"]
    if case["expected_stderr"] == "error_line":
        assert proc.stderr == "ERROR: memory file project_memory.json does not exist\n"
    else:
        assert proc.stderr.startswith("Traceback (most recent call last):")
        assert not proc.stderr.startswith("ERROR:")
    assert classify(proc.returncode, proc.stdout) == case["expected_classification"]


def test_malformed_memory_exit_code_collides_with_strict_warn():
    """Pinned hazard: a malformed memory file crashes with exit 1, the strict
    WARN code, while a missing one exits 2, the strict FAIL code. Only the
    absence of a payload on stdout identifies either as UNEVALUATED. Changing
    this is a contract change (new fixture version)."""
    by_id = {c["id"]: c for c in MEM_SPEC["cases"]}
    assert by_id["memory_truncated_json"]["expected_exit"] == CONTRACT_EXIT_CODES["strict"]["WARN"]
    assert by_id["memory_missing"]["expected_exit"] == CONTRACT_EXIT_CODES["strict"]["FAIL"]


# ── 5. contradictory or unparseable output never classifies VERIFIED_PASS ────

def _payload(**overrides) -> dict:
    base = {
        "schema": CONTRACT, "verdict": "PASS", "mode": "strict",
        "evaluation_complete": True, "applicability": [], "violations": [],
        "freshness": [],
    }
    return {**base, **overrides}


_VIOLATION_RECORD = {"decision_id": "D", "severity": "FAIL", "rule_id": "D:FORBID_LITERAL:x"}

STUBS = {
    "pass_exit_1": (1, json.dumps(_payload())),
    "pass_exit_2": (2, json.dumps(_payload())),
    "pass_exit_negative": (-11, json.dumps(_payload())),
    "pass_warn_mode_exit_2": (2, json.dumps(_payload(mode="warn"))),
    "pass_with_violations": (0, json.dumps(_payload(violations=[_VIOLATION_RECORD]))),
    "pass_incomplete": (0, json.dumps(_payload(evaluation_complete=False))),
    "pass_complete_missing": (0, json.dumps({k: v for k, v in _payload().items() if k != "evaluation_complete"})),
    "pass_complete_as_string": (0, json.dumps(_payload(evaluation_complete="true"))),
    "pass_complete_as_int": (0, json.dumps(_payload(evaluation_complete=1))),
    "pass_unknown_schema": (0, json.dumps(_payload(schema="mneme.check/v2"))),
    "pass_schema_missing": (0, json.dumps({k: v for k, v in _payload().items() if k != "schema"})),
    "pass_unknown_mode": (0, json.dumps(_payload(mode="advisory"))),
    "pass_violations_not_list": (0, json.dumps(_payload(violations=None))),
    "verdict_lowercase": (0, json.dumps(_payload(verdict="pass"))),
    "verdict_unknown": (0, json.dumps(_payload(verdict="INCOMPLETE"))),
    "verdict_missing": (0, json.dumps({k: v for k, v in _payload().items() if k != "verdict"})),
    "fail_exit_0_strict": (0, json.dumps(_payload(verdict="FAIL", violations=[_VIOLATION_RECORD]))),
    "fail_without_violations": (2, json.dumps(_payload(verdict="FAIL"))),
    "non_json_stdout": (0, "Result: PASS\n"),
    "empty_stdout": (0, ""),
    "whitespace_stdout": (0, "  \n"),
    "payload_then_text": (0, json.dumps(_payload()) + "\nResult: PASS\n"),
    "text_then_payload": (0, "WARN  ADR_UNIMPORTED\n" + json.dumps(_payload())),
    "two_payloads": (0, json.dumps(_payload()) + "\n" + json.dumps(_payload())),
    "truncated_payload": (0, json.dumps(_payload())[:-1]),
    "json_array": (0, json.dumps([_payload()])),
    "json_string": (0, json.dumps("PASS")),
    "json_null": (0, "null"),
    "exit_code_not_int": ("0", json.dumps(_payload())),
}


@pytest.mark.parametrize("name", list(STUBS))
def test_contradictory_or_unparseable_output_is_never_verified_pass(name):
    exit_code, stdout = STUBS[name]
    assert classify(exit_code, stdout) != VERIFIED_PASS


@pytest.mark.parametrize("name", [n for n in STUBS if not n.startswith("fail_exit_0")])
def test_contradictory_or_unparseable_output_is_unevaluated(name):
    exit_code, stdout = STUBS[name]
    assert classify(exit_code, stdout) == UNEVALUATED


def test_fail_payload_with_exit_0_in_strict_mode_is_not_a_violation_either():
    """Self-contradictory in the other direction: neither class is trusted."""
    exit_code, stdout = STUBS["fail_exit_0_strict"]
    assert classify(exit_code, stdout) == UNEVALUATED


@pytest.mark.parametrize("mode,verdict,exit_code,expected", [
    ("strict", "PASS", 0, VERIFIED_PASS),
    ("warn", "PASS", 0, VERIFIED_PASS),
    ("strict", "WARN", 1, VIOLATION),
    ("warn", "WARN", 0, VIOLATION),
    ("strict", "FAIL", 2, VIOLATION),
    ("warn", "FAIL", 0, VIOLATION),
])
def test_consistent_stub_output_classifies(mode, verdict, exit_code, expected):
    violations = [] if verdict == "PASS" else [_VIOLATION_RECORD]
    stdout = json.dumps(_payload(mode=mode, verdict=verdict, violations=violations))
    assert classify(exit_code, stdout) == expected


def test_classifier_agrees_with_ci1_2_1_corpus():
    """The stricter raw-output classifier must reproduce every CI1.2.1 class."""
    root, spec = _spec("path_scoped_forbid_literal")
    variant = spec["query_variants"][0]
    for case in spec["cases"]:
        args = [
            "check", "--memory", spec["memory"], "--input", case["input"],
            "--query", variant["query"], "--top", str(variant["top"]),
            "--mode", case["mode"], "--adr-dir", spec["adr_dir"], "--json",
        ]
        if case["target_path"]:
            args += ["--target-path", case["target_path"]]
        proc = _cli(args, root)
        assert classify(proc.returncode, proc.stdout) == case["expected_classification"], case["id"]
