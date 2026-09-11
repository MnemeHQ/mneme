"""CI-produced test-evidence parsing and matching (ADR-024).

Focused regression tests for the deterministic, fail-closed parsing and
matching of a CI-produced test-result document against declared test
evidence. A matching document is an **unauthenticated claim**, never a
trust root.

The security invariant:

    `mneme audit` is passive and MUST NOT execute code from the audited
    repository, and MUST NOT auto-trust a JSON file merely present in the
    repository.

These tests pin:

- DECLARED alone does not protect;
- an exact-SHA + exact-selector + "passed" document supplied by a caller is
  at most a MATCHED_UNVERIFIED claim (``test:ci-claim:``), never Protected;
- no producer/type/run_id value, and no self-asserted "verified"/"trusted"/
  "authenticated" JSON field, can create the VERIFIED state;
- an authored "passed": true with no provenance cannot protect;
- SHA/selector/partial-match/suite-only/failed/skipped/malformed/unknown-
  schema/ambiguous cases all fail closed;
- Guidance is never upgraded;
- existing typed-rule and CI-enforcement protection, the Protect/Validate/
  refusal loop, and passive Audit are unchanged.
"""
import json
import subprocess
from pathlib import Path

from mneme.cli import main
from mneme.enforcer import generate_protection_report
from mneme.evidence import (
    CI_EVIDENCE_SCHEMA,
    REASON_MISSING_PROVENANCE,
    REASON_UNKNOWN_SCHEMA,
    match_ci_evidence,
    parse_ci_evidence_document,
)
from mneme.schemas import Decision, Rule

MEMORY_REL = Path(".mneme") / "project_memory.json"
BASE_TS = "2026-01-01T00:00:00Z"

PASSING_TEST = "def test_empty_input_rejected():\n    assert True\n"
DETERMINISTIC_DECISION = "Reject empty input before calling the model."
ADVISORY_DECISION = "Prefer simple architectures where practical."
SELECTOR = "tests/test_boundary.py::test_empty_input_rejected"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


def _init_repo(
    tmp_path: Path,
    decisions: list[dict],
    extra_files: dict[str, str] | None = None,
) -> tuple[Path, Path, str]:
    """A real git repository with a passing test and fixture memory."""
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_boundary.py").write_text(
        PASSING_TEST, encoding="utf-8",
    )
    for name, content in (extra_files or {}).items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    memory = root / MEMORY_REL
    memory.parent.mkdir(parents=True)
    memory.write_text(json.dumps({
        "meta": {"name": "ci-evidence", "description": "fixture"},
        "items": [],
        "examples": [],
        "decisions": decisions,
    }, indent=2) + "\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "-c", "user.email=t@e", "-c", "user.name=t", "add", "-A")
    _git(root, "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-q",
         "-m", "fixture")
    sha = _git(root, "rev-parse", "HEAD")
    return root, memory, sha


def _record(decision_id: str, text: str, selectors: list[dict] | None = None) -> dict:
    record = {
        "id": decision_id,
        "decision": text,
        "rationale": "",
        "scope": [],
        "constraints": [],
        "anti_patterns": [],
        "created_at": BASE_TS,
        "updated_at": BASE_TS,
    }
    if selectors is not None:
        record["test_evidence"] = selectors
    return record


def _declared_decision(decision_id: str = "dp-empty-input") -> Decision:
    return Decision(
        id=decision_id,
        decision=DETERMINISTIC_DECISION,
        test_evidence=[{"selector": SELECTOR}],
    )


def _evidence(sha: str, results: list[dict], schema: str | None = None,
              producer: dict | None = None) -> str:
    return json.dumps({
        "schema": schema if schema is not None else CI_EVIDENCE_SCHEMA,
        "repository_sha": sha,
        "producer": producer if producer is not None else {
            "type": "github-actions", "run_id": "run-123",
        },
        "results": results,
    })


# ── 1. DECLARED alone does not protect ──────────────────────────────────────


def test_declared_alone_does_not_protect(tmp_path):
    root, memory, _sha = _init_repo(tmp_path, [
        _record("dp-empty-input", DETERMINISTIC_DECISION, [{"selector": SELECTOR}]),
    ])
    decisions = [_declared_decision()]
    report = generate_protection_report(decisions, repo_root=root)
    assert report.decisions[0].protection_tier == "requires_modelling"
    assert report.decisions[0].evidence_sources == [f"test:declared:{SELECTOR}"]
    assert report.protected == 0


# ── 2. Valid matching CI document: exact SHA + selector + passed → CLAIM ────


def test_valid_ci_evidence_does_not_protect(tmp_path):
    """A valid, matching caller-supplied CI document is a claim, not proof.

    Exact SHA + exact selector + passed + plausible provenance still only
    yields MATCHED_UNVERIFIED — never Protected — because provenance is not
    authenticated."""
    root, memory, sha = _init_repo(tmp_path, [
        _record("dp-empty-input", DETERMINISTIC_DECISION, [{"selector": SELECTOR}]),
    ])
    decisions = [_declared_decision()]
    doc = _evidence(sha, [{"selector": SELECTOR, "outcome": "passed"}])
    report = generate_protection_report(
        decisions, repo_root=root, ci_evidence_document=doc,
    )
    assessment = report.decisions[0]
    assert assessment.protection_tier == "requires_modelling"
    assert assessment.evidence_confidence == "none"
    assert assessment.evidence_sources == [f"test:ci-claim:{SELECTOR}@{sha}"]
    assert report.protected == 0
    assert report.current_protection_pct == 0.0


def test_fake_producer_does_not_create_verified(tmp_path):
    """Arbitrary producer type/run_id cannot manufacture VERIFIED."""
    root, memory, sha = _init_repo(tmp_path, [
        _record("dp-empty-input", DETERMINISTIC_DECISION, [{"selector": SELECTOR}]),
    ])
    decisions = [_declared_decision()]
    doc = _evidence(sha, [{"selector": SELECTOR, "outcome": "passed"}],
                    producer={"type": "totally-fake", "run_id": "not-a-real-run"})
    report = generate_protection_report(
        decisions, repo_root=root, ci_evidence_document=doc,
    )
    assert report.decisions[0].protection_tier == "requires_modelling"
    assert report.decisions[0].evidence_sources == [
        f"test:ci-claim:{SELECTOR}@{sha}",
    ]
    assert report.protected == 0


def test_no_self_asserted_trust_field(tmp_path):
    """No field inside the JSON can declare the document itself trusted."""
    root, memory, sha = _init_repo(tmp_path, [
        _record("dp-empty-input", DETERMINISTIC_DECISION, [{"selector": SELECTOR}]),
    ])
    decisions = [_declared_decision()]
    doc = json.dumps({
        "schema": CI_EVIDENCE_SCHEMA,
        "repository_sha": sha,
        "producer": {"type": "github-actions", "run_id": "r1"},
        "verified": True,
        "trusted": True,
        "authenticated": True,
        "results": [{"selector": SELECTOR, "outcome": "passed"}],
    })
    report = generate_protection_report(
        decisions, repo_root=root, ci_evidence_document=doc,
    )
    assert report.decisions[0].protection_tier == "requires_modelling"
    assert report.decisions[0].evidence_sources == [
        f"test:ci-claim:{SELECTOR}@{sha}",
    ]
    assert report.protected == 0


# ── 3+4. Authored "passed": true without provenance cannot protect ──────────


def test_user_authored_passed_true_does_not_protect(tmp_path):
    root, memory, sha = _init_repo(tmp_path, [
        _record("dp-empty-input", DETERMINISTIC_DECISION, [{"selector": SELECTOR}]),
    ])
    decisions = [_declared_decision()]

    # A developer-authored flag with no schema/provenance is rejected.
    forged = json.dumps({
        "passed": True,
        "selector": SELECTOR,
        "sha": sha,
    })
    doc, reason = parse_ci_evidence_document(forged)
    assert doc is None
    assert reason == REASON_UNKNOWN_SCHEMA

    # Even a plausible forged document with no provenance is rejected.
    no_provenance = json.dumps({
        "schema": CI_EVIDENCE_SCHEMA,
        "repository_sha": sha,
        "results": [{"selector": SELECTOR, "outcome": "passed"}],
    })
    doc, reason = parse_ci_evidence_document(no_provenance)
    assert doc is None
    assert reason == REASON_MISSING_PROVENANCE


def test_repository_local_evidence_file_never_auto_trusted(tmp_path):
    """A JSON file merely present in the repo is not discovered or trusted."""
    root, memory, sha = _init_repo(
        tmp_path,
        [_record("dp-empty-input", DETERMINISTIC_DECISION, [{"selector": SELECTOR}])],
    )
    # A perfectly-formed evidence file, on disk in the repo, for this SHA.
    (root / ".mneme").mkdir(parents=True, exist_ok=True)
    (root / ".mneme" / "test_evidence.json").write_text(
        _evidence(sha, [{"selector": SELECTOR, "outcome": "passed"}]),
        encoding="utf-8",
    )
    decisions = [_declared_decision()]
    # No ci_evidence_document supplied: the on-disk file is irrelevant.
    report = generate_protection_report(decisions, repo_root=root)
    assert report.decisions[0].protection_tier == "requires_modelling"
    assert report.protected == 0


# ── 5. SHA mismatch fails closed ────────────────────────────────────────────


def test_sha_mismatch_fails_closed(tmp_path):
    root, memory, sha = _init_repo(tmp_path, [
        _record("dp-empty-input", DETERMINISTIC_DECISION, [{"selector": SELECTOR}]),
    ])
    decisions = [_declared_decision()]
    doc = _evidence("0" * 40, [{"selector": SELECTOR, "outcome": "passed"}])
    report = generate_protection_report(
        decisions, repo_root=root, ci_evidence_document=doc,
    )
    assert report.decisions[0].protection_tier == "requires_modelling"
    assert report.protected == 0


# ── 6+7. Selector mismatch / partial match fails closed ─────────────────────


def test_selector_mismatch_fails_closed(tmp_path):
    root, memory, sha = _init_repo(tmp_path, [
        _record("dp-empty-input", DETERMINISTIC_DECISION, [{"selector": SELECTOR}]),
    ])
    decisions = [_declared_decision()]
    doc = _evidence(sha, [
        {"selector": "tests/test_other.py::test_something_else", "outcome": "passed"},
    ])
    report = generate_protection_report(
        decisions, repo_root=root, ci_evidence_document=doc,
    )
    assert report.decisions[0].protection_tier == "requires_modelling"
    assert report.protected == 0


def test_partial_selector_match_fails_closed(tmp_path):
    root, memory, sha = _init_repo(tmp_path, [
        _record("dp-empty-input", DETERMINISTIC_DECISION, [{"selector": SELECTOR}]),
    ])
    decisions = [_declared_decision()]
    # Sub-string / prefix of the declared selector is not an exact match.
    doc = _evidence(sha, [
        {"selector": "tests/test_boundary.py::test_empty_input", "outcome": "passed"},
    ])
    report = generate_protection_report(
        decisions, repo_root=root, ci_evidence_document=doc,
    )
    assert report.decisions[0].protection_tier == "requires_modelling"
    assert report.protected == 0


# ── 8. Global suite pass without selector result fails closed ───────────────


def test_global_suite_pass_without_selector_fails_closed(tmp_path):
    root, memory, sha = _init_repo(tmp_path, [
        _record("dp-empty-input", DETERMINISTIC_DECISION, [{"selector": SELECTOR}]),
    ])
    decisions = [_declared_decision()]
    doc = _evidence(sha, [{"selector": "<whole-suite>", "outcome": "passed"}])
    report = generate_protection_report(
        decisions, repo_root=root, ci_evidence_document=doc,
    )
    assert report.decisions[0].protection_tier == "requires_modelling"
    assert report.protected == 0


# ── 9+10. failed / skipped results fail closed ──────────────────────────────


def test_failed_and_skipped_results_fail_closed(tmp_path):
    root, memory, sha = _init_repo(tmp_path, [
        _record("dp-empty-input", DETERMINISTIC_DECISION, [{"selector": SELECTOR}]),
    ])
    for outcome in ("failed", "skipped", "xfailed", "error"):
        decisions = [_declared_decision()]
        doc = _evidence(sha, [{"selector": SELECTOR, "outcome": outcome}])
        report = generate_protection_report(
            decisions, repo_root=root, ci_evidence_document=doc,
        )
        assert report.decisions[0].protection_tier == "requires_modelling", outcome
        assert report.protected == 0, outcome


# ── 11+12. malformed / unknown-schema evidence fails closed ─────────────────


def test_malformed_evidence_fails_closed(tmp_path):
    root, memory, sha = _init_repo(tmp_path, [
        _record("dp-empty-input", DETERMINISTIC_DECISION, [{"selector": SELECTOR}]),
    ])
    decisions = [_declared_decision()]
    for bad in ("not json", "[", "null", '{"schema": 1}'):
        report = generate_protection_report(
            decisions, repo_root=root, ci_evidence_document=bad,
        )
        assert report.decisions[0].protection_tier == "requires_modelling", bad
        assert report.protected == 0, bad


def test_unknown_schema_fails_closed(tmp_path):
    root, memory, sha = _init_repo(tmp_path, [
        _record("dp-empty-input", DETERMINISTIC_DECISION, [{"selector": SELECTOR}]),
    ])
    decisions = [_declared_decision()]
    doc = _evidence(sha, [{"selector": SELECTOR, "outcome": "passed"}],
                    schema="someone.else/v9")
    report = generate_protection_report(
        decisions, repo_root=root, ci_evidence_document=doc,
    )
    assert report.decisions[0].protection_tier == "requires_modelling"
    assert report.protected == 0


# ── 13. Ambiguous selector declaration fails closed ────────────────────────


def test_ambiguous_selector_fails_closed(tmp_path):
    root, memory, sha = _init_repo(tmp_path, [
        _record("dp-a", DETERMINISTIC_DECISION, [{"selector": SELECTOR}]),
        _record("dp-b", DETERMINISTIC_DECISION, [{"selector": SELECTOR}]),
    ])
    decisions = [
        Decision(id="dp-a", decision=DETERMINISTIC_DECISION,
                 test_evidence=[{"selector": SELECTOR}]),
        Decision(id="dp-b", decision=DETERMINISTIC_DECISION,
                 test_evidence=[{"selector": SELECTOR}]),
    ]
    doc = _evidence(sha, [{"selector": SELECTOR, "outcome": "passed"}])
    report = generate_protection_report(
        decisions, repo_root=root, ci_evidence_document=doc,
    )
    assert report.protected == 0
    assert all(
        d.protection_tier == "requires_modelling" for d in report.decisions
    )


# ── 14. Guidance remains Guidance even with valid evidence ──────────────────


def test_guidance_never_upgraded_even_with_valid_evidence(tmp_path):
    root, memory, sha = _init_repo(tmp_path, [
        _record("dp-guid", ADVISORY_DECISION, [{"selector": SELECTOR}]),
    ])
    decisions = [
        Decision(id="dp-guid", decision=ADVISORY_DECISION,
                 test_evidence=[{"selector": SELECTOR}]),
    ]
    doc = _evidence(sha, [{"selector": SELECTOR, "outcome": "passed"}])
    report = generate_protection_report(
        decisions, repo_root=root, ci_evidence_document=doc,
    )
    assert report.decisions[0].intent == "guidance"
    assert report.decisions[0].protection_tier == "guidance"
    assert report.protected == 0


# ── 15+16. Existing typed-rule / CI-enforcement protection unchanged ────────


def test_typed_rule_and_ci_enforcement_unchanged(tmp_path):
    root, memory, _sha = _init_repo(tmp_path, [
        _record("dp-typed", "Keep the package namespace distinct"),
        _record("dp-ci", "No psycopg2 in the service layer"),
    ])
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        "jobs:\n  guard:\n    steps:\n"
        "      - run: if grep -rq psycopg2 src/; then exit 1; fi\n",
        encoding="utf-8",
    )
    from mneme.memory_store import MemoryStore

    memory.write_text(json.dumps({
        "meta": {"name": "ci-evidence", "description": "fixture"},
        "items": [],
        "examples": [],
        "decisions": [
            {
                "id": "dp-typed", "decision": "Keep the package namespace distinct",
                "rationale": "", "scope": [], "constraints": [],
                "anti_patterns": [],
                "rules": [{"type": "FORBID_LITERAL", "value": "sqlite"}],
                "created_at": BASE_TS, "updated_at": BASE_TS,
            },
            {
                "id": "dp-ci", "decision": "No psycopg2 in the service layer",
                "rationale": "", "scope": [], "constraints": [],
                "anti_patterns": ["psycopg2"],
                "created_at": BASE_TS, "updated_at": BASE_TS,
            },
        ],
    }, indent=2) + "\n", encoding="utf-8")
    store = MemoryStore(memory)
    store.load()
    report = generate_protection_report(store.decisions(), repo_root=root)
    by_id = {d.id: d for d in report.decisions}
    assert by_id["dp-typed"].protection_tier == "protected"
    assert by_id["dp-ci"].protection_tier == "protected"
    assert report.protected == 2


# ── 17. Protect / Validate / strict refusal unchanged ───────────────────────


def test_protect_loop_unchanged(tmp_path):
    from mneme.protection import activation_precheck

    root, memory, _sha = _init_repo(tmp_path, [
        _record("dp-empty-input", DETERMINISTIC_DECISION, [{"selector": SELECTOR}]),
    ])
    # A declared-only decision is not a candidate.
    decision = _declared_decision()
    pre = activation_precheck(decision, repo_root=root)
    assert pre.eligible is False and pre.tier == "requires_modelling"

    # A Mneme-ready decision remains eligible.
    ready = Decision(id="d-ready", decision="No postgres in the service layer",
                     anti_patterns=["postgres"])
    ready_pre = activation_precheck(ready)
    assert ready_pre.eligible is True and ready_pre.tier == "mneme_ready"


# ── 18. Ordinary Audit does not execute repository code ─────────────────────


def test_ordinary_audit_is_passive(tmp_path, monkeypatch):
    import mneme.evidence as evidence_module

    executions: list[list[str]] = []
    real_run = evidence_module.subprocess.run

    def recording_run(command, *args, **kwargs):
        executions.append([str(p) for p in command])
        return real_run(command, *args, **kwargs)

    sentinel = (
        "from pathlib import Path\n"
        "Path(__file__).resolve().parent / 'EXECUTED.txt'"
        ".write_text('ran')\n"
    )
    root, memory, sha = _init_repo(
        tmp_path,
        [_record("dp-empty-input", DETERMINISTIC_DECISION, [{"selector": SELECTOR}])],
        extra_files={"conftest.py": sentinel},
    )

    monkeypatch.setattr(evidence_module.subprocess, "run", recording_run)
    exit_code = main(["audit", "--memory", str(memory), "--repo-root", str(root)])
    assert exit_code == 0
    for command in executions:
        assert command[:3] == ["git", "rev-parse", "HEAD"], command
        assert not any("pytest" in p for p in command), command
    assert not (root / "EXECUTED.txt").exists()
    assert not (root / ".pytest_cache").exists()
    assert not list(root.rglob("__pycache__"))


# ── 19. Deterministic output for identical inputs ──────────────────────────


def test_deterministic_ci_evidence_output(tmp_path):
    root, memory, sha = _init_repo(tmp_path, [
        _record("dp-empty-input", DETERMINISTIC_DECISION, [{"selector": SELECTOR}]),
    ])
    decisions = [_declared_decision()]
    doc = _evidence(sha, [{"selector": SELECTOR, "outcome": "passed"}])
    first = generate_protection_report(decisions, repo_root=root, ci_evidence_document=doc)
    second = generate_protection_report(decisions, repo_root=root, ci_evidence_document=doc)

    def snapshot(r):
        return (
            r.protected, r.mneme_ready, r.requires_modelling, r.guidance,
            r.current_protection_pct, r.identified_mneme_potential_pct,
            tuple(
                (d.id, d.protection_tier, d.evidence_confidence,
                 tuple(d.evidence_sources))
                for d in r.decisions
            ),
        )

    assert snapshot(first) == snapshot(second)


# ── match_ci_evidence is a pure function (no provenance trust, no exec) ────


def test_match_ci_evidence_is_pure_and_requires_sha_and_provenance(tmp_path):
    root, memory, sha = _init_repo(tmp_path, [
        _record("dp-empty-input", DETERMINISTIC_DECISION, [{"selector": SELECTOR}]),
    ])
    decisions = [_declared_decision()]
    valid, _ = parse_ci_evidence_document(_evidence(
        sha, [{"selector": SELECTOR, "outcome": "passed"}],
    ))
    assert valid is not None
    assert match_ci_evidence(decisions, sha, valid) == {
        "dp-empty-input": [SELECTOR],
    }
    # Wrong HEAD SHA → nothing verified.
    assert match_ci_evidence(decisions, "0" * 40, valid) == {}
    # None document → nothing verified.
    assert match_ci_evidence(decisions, sha, None) == {}
