"""Test-evidence ingestion for the P1.2 audit (ADR-024, passive model).

Regression tests for the declared test-evidence channel under the
passive-Audit security invariant:

    Architecture Audit does not execute code from the audited repository
    unless the user explicitly requests an execution-capable verification
    mode.

Frozen principles pinned here:

- Ordinary `mneme audit` never invokes pytest, conftest, plugins, or any
  other repository-controlled code — verified by an execution sentinel
  (a conftest.py that would create a marker file if imported) and by
  recording every subprocess invocation reachable from the evidence
  module.
- DECLARED is not VERIFIED: a merely declared decision→test linkage
  annotates evidence_sources/diagnostics but never protects. M0 has no
  trusted verification producer (CI-produced exact-SHA + exact-selector
  ingestion is the next task).
- Advisory (Guidance) intent is evidence-independent: declared test
  evidence never upgrades it.
- Every failure mode (missing selector, malformed selector, missing file,
  SHA unavailable, stale SHA pin, ambiguous mapping, declared-but-
  unverified) fails closed with a deterministic diagnostic.
- Existing typed-rule / CI protection paths and the Protect / Validate /
  strict-refusal loop are unchanged.
"""
import json
import subprocess
from pathlib import Path

from mneme.cli import main
from mneme.enforcer import generate_protection_report
from mneme.evidence import (
    REASON_SELECTOR_NOT_FOUND,
    REASON_SHA_MISMATCH,
)
from mneme.protection import (
    activate_protection,
    activation_precheck,
    find_candidates,
)
from mneme.schemas import Decision, Rule

MEMORY_REL = Path(".mneme") / "project_memory.json"
BASE_TS = "2026-01-01T00:00:00Z"

PASSING_TEST = "def test_empty_input_rejected():\n    assert True\n"
UNRELATED_TEST = "def test_markdown_render():\n    assert True\n"
FAILING_TEST = "def test_empty_input_rejected():\n    assert False\n"

DETERMINISTIC_DECISION = "Reject empty input before calling the model."
ADVISORY_DECISION = "Prefer simple architectures where practical."


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
    test_body: str,
    test_file: str = "tests/test_boundary.py",
    decisions: list[dict] | None = None,
    second_commit: bool = False,
    extra_files: dict[str, str] | None = None,
) -> tuple[Path, Path, str]:
    """Create a real git repository with a test file and fixture memory."""
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / test_file).write_text(test_body, encoding="utf-8")
    for name, content in (extra_files or {}).items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    memory = root / MEMORY_REL
    memory.parent.mkdir(parents=True)
    memory.write_text(json.dumps({
        "meta": {"name": "evidence", "description": "ADR-024 fixture"},
        "items": [],
        "examples": [],
        "decisions": decisions or [],
    }, indent=2) + "\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "-c", "user.email=test@example.com", "-c",
         "user.name=tester", "add", "-A")
    _git(root, "-c", "user.email=test@example.com", "-c",
         "user.name=tester", "commit", "-q", "-m", "fixture")
    sha = _git(root, "rev-parse", "HEAD")
    if second_commit:
        (root / "OTHER.txt").write_text("later", encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "-c", "user.email=test@example.com", "-c",
             "user.name=tester", "commit", "-q", "-m", "second")
    return root, memory, sha


def _decision_record(
    decision_id: str,
    text: str,
    selectors: list[dict] | None = None,
) -> dict:
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


# ── 1+12. Passive audit: declared evidence never executes, never protects ───


def test_ordinary_audit_never_executes_repository_code(tmp_path, monkeypatch):
    """Ordinary `mneme audit` must not execute repository-controlled code.

    Belt: a recorded-subprocess guard inside the evidence module proves no
    pytest invocation happens. Brace: a conftest.py execution sentinel —
    a conftest that would create a marker file the moment any pytest run
    imports it — must never appear."""
    import mneme.evidence as evidence_module

    executions: list[list[str]] = []
    real_run = evidence_module.subprocess.run

    def recording_run(command, *args, **kwargs):
        executions.append([str(part) for part in command])
        return real_run(command, *args, **kwargs)

    sentinel_conftest = (
        "from pathlib import Path\n"
        "Path(__file__).resolve().parent / 'EXECUTED.txt'"
        ".write_text('repository code ran')\n"
    )
    root, memory, _sha = _init_repo(
        tmp_path,
        PASSING_TEST,
        extra_files={"conftest.py": sentinel_conftest},
        decisions=[
            _decision_record(
                "dp-empty-input",
                DETERMINISTIC_DECISION,
                [{"selector": "tests/test_boundary.py::test_empty_input_rejected"}],
            ),
        ],
    )
    decisions = [
        Decision(
            id="dp-empty-input",
            decision=DETERMINISTIC_DECISION,
            test_evidence=[
                {"selector": "tests/test_boundary.py::test_empty_input_rejected"},
            ],
        ),
    ]

    monkeypatch.setattr(evidence_module.subprocess, "run", recording_run)
    exit_code = main([
        "audit", "--memory", str(memory),
        "--repo-root", str(root),
    ])
    assert exit_code == 0

    # Every subprocess invocation was the passive git SHA read — never pytest.
    assert executions, "the audit should still pin the repository SHA"
    for command in executions:
        assert command[:3] == ["git", "rev-parse", "HEAD"], command
        assert not any("pytest" in part for part in command), command

    # The conftest execution sentinel was never created: no repository
    # code ran.
    assert not (root / "EXECUTED.txt").exists()
    assert not list(root.rglob("__pycache__"))
    assert not (root / ".pytest_cache").exists()

    # Declared evidence annotates but never protects.
    audit_json = tmp_path / "audit.json"
    exit_code = main([
        "audit", "--memory", str(memory),
        "--repo-root", str(root), "--json", str(audit_json),
    ])
    assert exit_code == 0
    data = json.loads(audit_json.read_text(encoding="utf-8"))
    decision = data["decisions"][0]
    assert decision["protection_tier"] == "requires_modelling"
    assert decision["evidence_confidence"] == "none"
    assert decision["evidence_sources"] == [
        "test:declared:tests/test_boundary.py::test_empty_input_rejected",
    ]
    assert data["summary"]["protected"] == 0
    assert data["summary"]["current_protection_pct"] == 0.0
    assert data["summary"]["identified_mneme_potential_pct"] == 100.0


def test_declared_selector_alone_does_not_protect(tmp_path):
    """A merely DECLARED linkage annotates but classification keeps
    Requires Modelling — declared evidence is not verified evidence."""
    root, memory, _sha = _init_repo(tmp_path, PASSING_TEST, decisions=[
        _decision_record(
            "dp-empty-input",
            DETERMINISTIC_DECISION,
            [{"selector": "tests/test_boundary.py::test_empty_input_rejected"}],
        ),
    ])
    decisions = [
        Decision(
            id="dp-empty-input",
            decision=DETERMINISTIC_DECISION,
            test_evidence=[
                {"selector": "tests/test_boundary.py::test_empty_input_rejected"},
            ],
        ),
    ]
    report = generate_protection_report(decisions, repo_root=root)
    assessment = report.decisions[0]

    assert assessment.intent == "deterministic"
    assert assessment.protection_tier == "requires_modelling"
    assert assessment.evidence_confidence == "none"
    assert assessment.evidence_sources == [
        "test:declared:tests/test_boundary.py::test_empty_input_rejected",
    ]
    assert report.protection_relevant == 1
    assert report.requires_modelling == 1
    assert report.protected == 0
    assert report.current_protection_pct == 0.0
    assert report.identified_mneme_potential_pct == 100.0


# ── 2. Passing unrelated test cannot establish protection ───────────────────


def test_unrelated_passing_test_not_credited(tmp_path):
    """An undeclared passing test is never credited: Mneme performs no
    scanning, no fuzzy matching, no inference."""
    root, memory, _sha = _init_repo(tmp_path, UNRELATED_TEST, decisions=[
        _decision_record("dp-output-contract",
                         "Validate the output contract before showing the draft."),
    ])
    decisions = [
        Decision(
            id="dp-output-contract",
            decision="Validate the output contract before showing the draft.",
        ),
    ]
    report = generate_protection_report(decisions, repo_root=root)
    assessment = report.decisions[0]

    assert assessment.protection_tier == "requires_modelling"
    assert assessment.evidence_confidence == "none"
    assert assessment.evidence_sources == []


def test_wrongly_declared_selector_does_not_protect(tmp_path):
    """A declared linkage whose selector does not correspond to the
    decision's boundary still never protects: M0 has no trusted
    verification producer, so the declaration annotates only."""
    root, memory, _sha = _init_repo(tmp_path, UNRELATED_TEST, decisions=[
        _decision_record(
            "dp-empty-input",
            DETERMINISTIC_DECISION,
            [{"selector": "tests/test_boundary.py::test_markdown_render"}],
        ),
    ])
    decisions = [
        Decision(
            id="dp-empty-input",
            decision=DETERMINISTIC_DECISION,
            test_evidence=[
                {"selector": "tests/test_boundary.py::test_markdown_render"},
            ],
        ),
    ]
    report = generate_protection_report(decisions, repo_root=root)
    assessment = report.decisions[0]

    assert assessment.protection_tier == "requires_modelling"
    assert assessment.evidence_sources == [
        "test:declared:tests/test_boundary.py::test_markdown_render",
    ]
    assert report.protected == 0


# ── 3+8. Missing/malformed selector fails closed ────────────────────────────


def test_missing_selector_file_is_invalid(tmp_path):
    root, memory, _sha = _init_repo(tmp_path, PASSING_TEST, decisions=[
        _decision_record(
            "dp-empty-input",
            DETERMINISTIC_DECISION,
            [{"selector": "tests/test_absent.py::test_empty_input_rejected"}],
        ),
    ])
    decisions = [
        Decision(
            id="dp-empty-input",
            decision=DETERMINISTIC_DECISION,
            test_evidence=[
                {"selector": "tests/test_absent.py::test_empty_input_rejected"},
            ],
        ),
    ]
    report = generate_protection_report(decisions, repo_root=root)
    assessment = report.decisions[0]

    assert assessment.protection_tier == "requires_modelling"
    assert assessment.evidence_confidence == "none"
    assert assessment.evidence_sources == [
        "test:invalid:tests/test_absent.py::test_empty_input_rejected"
        f"@{REASON_SELECTOR_NOT_FOUND}",
    ]


def test_malformed_selector_is_invalid(tmp_path):
    root, memory, _sha = _init_repo(tmp_path, PASSING_TEST, decisions=[
        _decision_record(
            "dp-empty-input",
            DETERMINISTIC_DECISION,
            [{"selector": "no separator here"}],
        ),
    ])
    decisions = [
        Decision(
            id="dp-empty-input",
            decision=DETERMINISTIC_DECISION,
            test_evidence=[{"selector": "no separator here"}],
        ),
    ]
    report = generate_protection_report(decisions, repo_root=root)
    assessment = report.decisions[0]

    assert assessment.protection_tier == "requires_modelling"
    assert "test:invalid:no separator here@malformed-selector" in (
        assessment.evidence_sources
    )


# ── 4. Stale SHA pin refuses protection ─────────────────────────────────────


def test_declared_sha_mismatch_is_stale(tmp_path):
    """A declaration pinned to an old SHA is STALE — it annotates but
    never protects; only a re-pinned, trusted verification could."""
    root, memory, _first_sha = _init_repo(
        tmp_path, PASSING_TEST, second_commit=True, decisions=[
            _decision_record(
                "dp-empty-input",
                DETERMINISTIC_DECISION,
                [{"selector": "tests/test_boundary.py::test_empty_input_rejected",
                  "sha": "0" * 40}],
            ),
        ],
    )
    decisions = [
        Decision(
            id="dp-empty-input",
            decision=DETERMINISTIC_DECISION,
            test_evidence=[
                {"selector": "tests/test_boundary.py::test_empty_input_rejected",
                 "sha": "0" * 40},
            ],
        ),
    ]
    report = generate_protection_report(decisions, repo_root=root)
    assessment = report.decisions[0]

    assert assessment.protection_tier == "requires_modelling"
    assert assessment.evidence_sources == [
        "test:stale:tests/test_boundary.py::test_empty_input_rejected"
        f"@{REASON_SHA_MISMATCH}",
    ]
    assert report.protected == 0


# ── 6+7. Ambiguous mapping and advisory guidance refuse protection ──────────


def test_ambiguous_mapping_protects_neither(tmp_path):
    root, memory, _sha = _init_repo(tmp_path, PASSING_TEST, decisions=[
        _decision_record(
            "dp-empty-input",
            DETERMINISTIC_DECISION,
            [{"selector": "tests/test_boundary.py::test_empty_input_rejected"}],
        ),
        _decision_record(
            "dp-other",
            DETERMINISTIC_DECISION,
            [{"selector": "tests/test_boundary.py::test_empty_input_rejected"}],
        ),
    ])
    decisions = [
        Decision(
            id="dp-empty-input",
            decision=DETERMINISTIC_DECISION,
            test_evidence=[
                {"selector": "tests/test_boundary.py::test_empty_input_rejected"},
            ],
        ),
        Decision(
            id="dp-other",
            decision=DETERMINISTIC_DECISION,
            test_evidence=[
                {"selector": "tests/test_boundary.py::test_empty_input_rejected"},
            ],
        ),
    ]
    report = generate_protection_report(decisions, repo_root=root)
    by_id = {d.id: d for d in report.decisions}

    for assessment in by_id.values():
        assert assessment.protection_tier == "requires_modelling"
        assert assessment.evidence_confidence == "none"
        assert all(
            src.startswith("test:invalid:")
            and src.endswith("@ambiguous-mapping")
            for src in assessment.evidence_sources
        ), assessment.evidence_sources
    assert report.protected == 0


def test_guidance_never_upgraded_by_test_evidence(tmp_path):
    root, memory, _sha = _init_repo(tmp_path, PASSING_TEST, decisions=[
        _decision_record(
            "dp-guidance",
            ADVISORY_DECISION,
            [{"selector": "tests/test_boundary.py::test_empty_input_rejected"}],
        ),
    ])
    decisions = [
        Decision(
            id="dp-guidance",
            decision=ADVISORY_DECISION,
            test_evidence=[
                {"selector": "tests/test_boundary.py::test_empty_input_rejected"},
            ],
        ),
    ]
    report = generate_protection_report(decisions, repo_root=root)
    assessment = report.decisions[0]

    assert assessment.intent == "guidance"
    assert assessment.protection_tier == "guidance"
    assert assessment.evidence_confidence == "none"
    assert assessment.evidence_sources == []
    assert report.protection_relevant == 0
    assert report.guidance == 1


# ── 7. Declared but unverified evidence never upgrades the tier ─────────────


def test_declared_but_unverified_stays_requires_modelling(tmp_path):
    root, memory, _sha = _init_repo(tmp_path, PASSING_TEST, decisions=[
        _decision_record(
            "dp-empty-input",
            DETERMINISTIC_DECISION,
            [{"selector": "tests/test_boundary.py::test_empty_input_rejected"}],
        ),
    ])
    decisions = [
        Decision(
            id="dp-empty-input",
            decision=DETERMINISTIC_DECISION,
            test_evidence=[
                {"selector": "tests/test_boundary.py::test_empty_input_rejected"},
            ],
        ),
    ]

    # No repository context: nothing can be validated, nothing protects.
    report = generate_protection_report(decisions, repo_root=None)
    assert report.decisions[0].protection_tier == "requires_modelling"
    assert report.decisions[0].evidence_sources == []
    assert report.protection_relevant == 1
    assert report.requires_modelling == 1


# ── 8. Deterministic output for identical inputs ────────────────────────────


def test_identical_declared_evidence_deterministic_output(tmp_path):
    root, memory, _sha = _init_repo(tmp_path, PASSING_TEST, decisions=[
        _decision_record(
            "dp-empty-input",
            DETERMINISTIC_DECISION,
            [{"selector": "tests/test_boundary.py::test_empty_input_rejected"}],
        ),
    ])
    decisions = [
        Decision(
            id="dp-empty-input",
            decision=DETERMINISTIC_DECISION,
            test_evidence=[
                {"selector": "tests/test_boundary.py::test_empty_input_rejected"},
            ],
        ),
    ]
    first = generate_protection_report(decisions, repo_root=root)
    second = generate_protection_report(decisions, repo_root=root)

    def _snapshot(report):
        return (
            report.protection_relevant,
            report.protected,
            report.mneme_ready,
            report.requires_modelling,
            report.guidance,
            report.current_protection_pct,
            report.identified_mneme_potential_pct,
            report.protection_gap_pct,
            tuple(
                (d.id, d.intent, d.protection_tier, d.evidence_confidence,
                 tuple(d.evidence_sources))
                for d in report.decisions
            ),
        )

    assert _snapshot(first) == _snapshot(second)

    audit_one = tmp_path / "audit-one.json"
    audit_two = tmp_path / "audit-two.json"
    assert main(["audit", "--memory", str(memory), "--repo-root", str(root),
                 "--json", str(audit_one)]) == 0
    assert main(["audit", "--memory", str(memory), "--repo-root", str(root),
                 "--json", str(audit_two)]) == 0
    assert audit_one.read_text(encoding="utf-8") == audit_two.read_text(
        encoding="utf-8"
    )


# ── 9+10. Existing CI / typed-rule paths remain unchanged ───────────────────


def test_typed_rule_and_ci_paths_unchanged(tmp_path):
    root, memory, _sha = _init_repo(tmp_path, PASSING_TEST, decisions=[
        _decision_record("dp-typed", "Keep the package namespace distinct"),
        _decision_record("dp-ci", "No psycopg2 in the service layer"),
    ])
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        "jobs:\n  guard:\n    steps:\n"
        "      - run: if grep -rq psycopg2 src/; then exit 1; fi\n",
        encoding="utf-8",
    )
    memory.write_text(json.dumps({
        "meta": {"name": "evidence", "description": "ADR-024 fixture"},
        "items": [],
        "examples": [],
        "decisions": [
            {
                "id": "dp-typed",
                "decision": "Keep the package namespace distinct",
                "rationale": "",
                "scope": [],
                "constraints": [],
                "anti_patterns": [],
                "rules": [{"type": "FORBID_LITERAL", "value": "sqlite"}],
                "created_at": BASE_TS,
                "updated_at": BASE_TS,
            },
            {
                "id": "dp-ci",
                "decision": "No psycopg2 in the service layer",
                "rationale": "",
                "scope": [],
                "constraints": [],
                "anti_patterns": ["psycopg2"],
                "created_at": BASE_TS,
                "updated_at": BASE_TS,
            },
        ],
    }, indent=2) + "\n", encoding="utf-8")

    from mneme.memory_store import MemoryStore

    store = MemoryStore(memory)
    store.load()
    report = generate_protection_report(store.decisions(), repo_root=root)
    by_id = {d.id: d for d in report.decisions}

    assert by_id["dp-typed"].protection_tier == "protected"
    assert by_id["dp-typed"].evidence_sources == []
    assert by_id["dp-ci"].protection_tier == "protected"
    assert any(
        src.startswith("ci:verified:") for src in by_id["dp-ci"].evidence_sources
    )
    assert report.protected == 2
    assert report.current_protection_pct == 100.0


# ── 11. Protect / Validate / strict refusal remain unchanged ────────────────


def test_protect_loop_unchanged_with_declared_evidence(tmp_path):
    root, memory, _sha = _init_repo(tmp_path, PASSING_TEST, decisions=[
        _decision_record(
            "dp-empty-input",
            DETERMINISTIC_DECISION,
            [{"selector": "tests/test_boundary.py::test_empty_input_rejected"}],
        ),
        _decision_record("dp-unlinked",
                         "Validate the output contract before showing the draft."),
    ])

    from mneme.memory_store import MemoryStore

    store = MemoryStore(memory)
    store.load()
    discovered = find_candidates(store.decisions(), repo_root=root)

    # A declared-but-unverified decision is Requires Modelling, never a
    # candidate; nothing is protected, nothing is activatable.
    ids = [c.decision_id for c in discovered.candidates]
    assert ids == [], ids
    assert discovered.report.protected == 0
    assert discovered.report.requires_modelling == 2

    declared = Decision(
        id="dp-empty-input",
        decision=DETERMINISTIC_DECISION,
        test_evidence=[
            {"selector": "tests/test_boundary.py::test_empty_input_rejected"},
        ],
    )
    pre = activation_precheck(declared, repo_root=root)
    assert pre.eligible is False and pre.tier == "requires_modelling"
    assert activate_protection(
        "dp-empty-input", memory, repo_root=root
    ).result == "not_eligible"

    # The strict-refusal loop itself is untouched: a Mneme-ready decision
    # whose deterministic validation fails is refused and nothing is written.
    ready_memory = tmp_path / "ready.json"
    ready_memory.parent.mkdir(parents=True, exist_ok=True)
    ready_memory.write_text(json.dumps({
        "meta": {"name": "e", "description": "e"},
        "items": [],
        "examples": [],
        "decisions": [
            {
                "id": "d-ready",
                "decision": "No postgres in the service layer",
                "rationale": "",
                "scope": [],
                "constraints": [],
                "anti_patterns": ["postgres"],
                "created_at": BASE_TS,
                "updated_at": BASE_TS,
            },
        ],
    }, indent=2) + "\n", encoding="utf-8")
    ready = Decision(
        id="d-ready",
        decision="No postgres in the service layer",
        anti_patterns=["postgres"],
        memory_path=str(ready_memory),
    )
    ready_pre = activation_precheck(ready)
    assert ready_pre.eligible is True and ready_pre.tier == "mneme_ready"

    import mneme.protection as protection

    real_check = protection.check_prompt

    def blind_check(text, scored, top=3, input_path=None):
        result = real_check(text, scored, top=top, input_path=input_path)
        result.violations = [
            v for v in result.violations if v.kind != "typed_rule"
        ]
        return result

    before = ready_memory.read_text(encoding="utf-8")
    baseline = generate_protection_report([ready])
    original_check = protection.check_prompt
    try:
        protection.check_prompt = blind_check
        outcome = activate_protection("d-ready", ready_memory)
        assert outcome.result == "validation_failed"
        assert outcome.rule_installed is False
    finally:
        protection.check_prompt = original_check
    assert ready_memory.read_text(encoding="utf-8") == before
    after = generate_protection_report([ready])
    assert after.current_protection_pct == baseline.current_protection_pct
