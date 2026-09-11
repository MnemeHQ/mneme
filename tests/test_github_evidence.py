"""Authenticated GitHub Actions CI *claim* (ADR-024).

Focused regression tests for the authenticated retrieval path. The GitHub API
is faked by monkeypatching the module's HTTP seams; no real network, no
repository code executes.

Pinned invariants:

- an authenticated run + artifact is a CI *claim* (``authenticated_ci_claim``),
  never ``verified``/Protected — the artifact content is repository-controlled;
- direct construction / caller injection of any authenticated-looking value
  cannot reach Protected through the supported public API;
- forged run_id, wrong repository, SHA mismatch, missing/partial/non-passed
  selector, malformed artifact, and artifact SHA mismatch all fail closed;
- the artifact redirect never forwards the bearer token to a non-API host;
- Guidance is never upgraded; typed-rule / CI-enforcement protection and
  offline passive Audit are unchanged.
"""
import io
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from mneme.cli import main
from mneme.enforcer import (
    assess_protection,
    generate_protection_report,
)
from mneme.github_evidence import (
    GitHubVerificationError,
    audit_with_github_claim,
    verify_github_run,
)
from mneme.schemas import Decision

MEMORY_REL = Path(".mneme") / "project_memory.json"
BASE_TS = "2026-01-01T00:00:00Z"

SELECTOR = "tests/test_boundary.py::test_empty_input_rejected"
DETERMINISTIC_DECISION = "Reject empty input before calling the model."
ADVISORY_DECISION = "Prefer simple architectures where practical."


def _evidence_zip(sha: str, results: list[dict]) -> bytes:
    doc = json.dumps({
        "schema": "mneme.test-evidence/v1",
        "repository_sha": sha,
        "producer": {"type": "github-actions", "run_id": "1"},
        "results": results,
    })
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("evidence.json", doc)
    return buf.getvalue()


class FakeGitHub:
    """Canned GitHub API/artifact responses for one run."""

    def __init__(self, run: dict, artifacts: list[dict], artifact_zip: bytes):
        self.run = run
        self.artifacts = artifacts
        self.artifact_zip = artifact_zip
        self.calls: list[tuple[str, str]] = []

    def api_get_json(self, path, token, base_url, timeout):
        self.calls.append(("api", path))
        if "/artifacts" in path:
            return {"artifacts": self.artifacts}
        return self.run

    def download_artifact(self, path, token, base_url, timeout):
        self.calls.append(("download", path))
        return self.artifact_zip


def _install_fake(monkeypatch, fake: FakeGitHub):
    import mneme.github_evidence as module

    monkeypatch.setattr(module, "_api_get_json", fake.api_get_json)
    monkeypatch.setattr(module, "_download_artifact", fake.download_artifact)
    return fake


def _decision(decision_id: str = "dp-empty-input", text: str = DETERMINISTIC_DECISION):
    return Decision(id=decision_id, decision=text, test_evidence=[{"selector": SELECTOR}])


def _valid_run(sha: str, repo: str = "acme/widgets") -> dict:
    return {
        "id": 42,
        "head_sha": sha,
        "status": "completed",
        "conclusion": "success",
        "head_repository": {"full_name": repo},
    }


def _artifact(artifact_id: int = 1, name: str = "mneme-test-results") -> dict:
    return {"id": artifact_id, "name": name, "expired": False}


def _git_repo(tmp_path) -> tuple[Path, Path, str]:
    """A real git repo with a declared decision; returns (root, memory, sha)."""
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_boundary.py").write_text(
        "def test_empty_input_rejected():\n    assert True\n", encoding="utf-8",
    )
    memory = root / MEMORY_REL
    memory.parent.mkdir(parents=True)
    memory.write_text(json.dumps({
        "meta": {"name": "x", "description": "x"},
        "items": [], "examples": [],
        "decisions": [{
            "id": "dp-empty-input", "decision": DETERMINISTIC_DECISION,
            "rationale": "", "scope": [], "constraints": [], "anti_patterns": [],
            "test_evidence": [{"selector": SELECTOR}],
            "created_at": BASE_TS, "updated_at": BASE_TS,
        }],
    }, indent=2) + "\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=t",
                    "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=t",
                    "commit", "-q", "-m", "f"], cwd=root, check=True)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                         capture_output=True, text=True, check=True).stdout.strip()
    return root, memory, sha


# ── 1+2. Direct construction / injection cannot reach Protected ────────────


def test_direct_construction_cannot_reach_protected(tmp_path, monkeypatch):
    """The supported public API accepts no trust-bearing parameter."""
    root, memory, sha = _git_repo(tmp_path)
    _install_fake(monkeypatch, FakeGitHub(
        _valid_run(sha), [_artifact()],
        _evidence_zip(sha, [{"selector": SELECTOR, "outcome": "passed"}]),
    ))
    claim = verify_github_run(root, 42, sha, token="tok",
                              owner="acme", repo="widgets")

    # No public API accepts the authenticated claim as a trust argument.
    with pytest.raises(TypeError):
        generate_protection_report([_decision()], repo_root=root,
                                   github_verification=claim)
    with pytest.raises(TypeError):
        assess_protection(_decision(), repo_root=root, github_verification=claim)
    with pytest.raises(TypeError):
        generate_protection_report([_decision()], repo_root=root,
                                   test_evidence_results={"x": []})

    # A hand-built "verified" record cannot be injected either.
    from mneme.evidence import TestEvidenceVerification
    forged = TestEvidenceVerification(
        decision_id="dp-empty-input", selector=SELECTOR, state="verified",
        sha=sha, code="x", detail="x",
    )
    with pytest.raises(TypeError):
        assess_protection(_decision(), repo_root=root,
                          test_evidence_results={"dp-empty-input": [forged]})


def test_cannot_fabricate_verified_from_carrier_only(tmp_path, monkeypatch):
    """Even a perfect local carrier never reaches verified via public API."""
    root, memory, sha = _git_repo(tmp_path)
    carrier = json.dumps({
        "schema": "mneme.test-evidence/v1",
        "repository_sha": sha,
        "producer": {"type": "github-actions", "run_id": "1"},
        "results": [{"selector": SELECTOR, "outcome": "passed"}],
    })
    report = generate_protection_report(
        [_decision()], repo_root=root, ci_evidence_document=carrier,
    )
    assert report.decisions[0].protection_tier == "requires_modelling"
    assert report.decisions[0].evidence_sources == [f"test:ci-claim:{SELECTOR}@{sha}"]
    assert report.protected == 0


# ── 3. Authenticated run + arbitrary artifact is a claim, not protection ───


def test_authenticated_run_yields_claim_not_protected(tmp_path, monkeypatch):
    root, memory, sha = _git_repo(tmp_path)
    _install_fake(monkeypatch, FakeGitHub(
        _valid_run(sha), [_artifact()],
        _evidence_zip(sha, [{"selector": SELECTOR, "outcome": "passed"}]),
    ))
    report = audit_with_github_claim(
        [_decision()], root, 42, token="tok", owner="acme", repo="widgets",
    )
    assessment = report.decisions[0]
    assert assessment.protection_tier == "requires_modelling"
    assert assessment.evidence_confidence == "none"
    assert assessment.evidence_sources == [f"test:ci-authenticated:{SELECTOR}@{sha}"]
    assert report.protected == 0
    assert "test:verified:" not in str(assessment.evidence_sources)


# ── 7. forged run / repo / SHA / selector fail closed ──────────────────────


def test_forged_run_id_fails(monkeypatch):
    import mneme.github_evidence as module

    def not_found(path, token, base_url, timeout):
        raise GitHubVerificationError("run 404", status=404)

    monkeypatch.setattr(module, "_api_get_json", not_found)
    with pytest.raises(GitHubVerificationError):
        verify_github_run(Path("x"), 999, "a" * 40, token="tok",
                          owner="acme", repo="widgets")


def test_run_from_other_repository_fails(tmp_path, monkeypatch):
    sha = "a" * 40
    _install_fake(monkeypatch, FakeGitHub(
        _valid_run(sha, repo="evil/corp"), [_artifact()],
        _evidence_zip(sha, [{"selector": SELECTOR, "outcome": "passed"}]),
    ))
    with pytest.raises(GitHubVerificationError):
        verify_github_run(tmp_path, 42, sha, token="tok",
                          owner="acme", repo="widgets")


def test_run_sha_mismatch_fails(tmp_path, monkeypatch):
    _install_fake(monkeypatch, FakeGitHub(
        _valid_run("b" * 40), [_artifact()],
        _evidence_zip("b" * 40, [{"selector": SELECTOR, "outcome": "passed"}]),
    ))
    with pytest.raises(GitHubVerificationError):
        verify_github_run(tmp_path, 42, "a" * 40, token="tok",
                          owner="acme", repo="widgets")


def test_missing_selector_result_fails(tmp_path, monkeypatch):
    sha = "a" * 40
    _install_fake(monkeypatch, FakeGitHub(_valid_run(sha), [], b""))
    with pytest.raises(GitHubVerificationError):
        verify_github_run(tmp_path, 42, sha, token="tok",
                          owner="acme", repo="widgets")


@pytest.mark.parametrize("outcome", ["failed", "skipped", "xfailed", "error"])
def test_non_passed_outcomes_do_not_verify(tmp_path, monkeypatch, outcome):
    root, memory, sha = _git_repo(tmp_path)
    _install_fake(monkeypatch, FakeGitHub(
        _valid_run(sha), [_artifact()],
        _evidence_zip(sha, [{"selector": SELECTOR, "outcome": outcome}]),
    ))
    report = audit_with_github_claim(
        [_decision()], root, 42, token="tok", owner="acme", repo="widgets",
    )
    assert report.decisions[0].protection_tier == "requires_modelling", outcome
    assert report.protected == 0, outcome


def test_substring_selector_does_not_verify(tmp_path, monkeypatch):
    root, memory, sha = _git_repo(tmp_path)
    _install_fake(monkeypatch, FakeGitHub(
        _valid_run(sha), [_artifact()],
        _evidence_zip(sha, [{"selector": "tests/test_boundary.py::test_empty_input", "outcome": "passed"}]),
    ))
    report = audit_with_github_claim(
        [_decision()], root, 42, token="tok", owner="acme", repo="widgets",
    )
    assert report.protected == 0
    assert report.decisions[0].protection_tier == "requires_modelling"


def test_malformed_artifact_fails(tmp_path, monkeypatch):
    sha = "a" * 40
    _install_fake(monkeypatch, FakeGitHub(_valid_run(sha), [_artifact()], b"not a zip"))
    with pytest.raises(GitHubVerificationError):
        verify_github_run(tmp_path, 42, sha, token="tok",
                          owner="acme", repo="widgets")


def test_artifact_sha_mismatch_fails(tmp_path, monkeypatch):
    sha = "a" * 40
    _install_fake(monkeypatch, FakeGitHub(
        _valid_run(sha), [_artifact()],
        _evidence_zip("c" * 40, [{"selector": SELECTOR, "outcome": "passed"}]),
    ))
    with pytest.raises(GitHubVerificationError):
        verify_github_run(tmp_path, 42, sha, token="tok",
                          owner="acme", repo="widgets")


# ── 9. Guidance is never upgraded ──────────────────────────────────────────


def test_guidance_never_upgraded(tmp_path, monkeypatch):
    root, memory, sha = _git_repo(tmp_path)
    _install_fake(monkeypatch, FakeGitHub(
        _valid_run(sha), [_artifact()],
        _evidence_zip(sha, [{"selector": SELECTOR, "outcome": "passed"}]),
    ))
    report = audit_with_github_claim(
        [_decision("dp-guid", ADVISORY_DECISION)], root, 42,
        token="tok", owner="acme", repo="widgets",
    )
    assert report.decisions[0].intent == "guidance"
    assert report.decisions[0].protection_tier == "guidance"
    assert report.protected == 0


# ── 12. typed-rule / CI-enforcement unchanged ──────────────────────────────


def test_typed_rule_and_ci_enforcement_unchanged(tmp_path):
    from mneme.schemas import Rule

    root = tmp_path / "repo"
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "ci.yml").write_text(
        "jobs:\n  guard:\n    steps:\n"
        "      - run: if grep -rq psycopg2 src/; then exit 1; fi\n",
        encoding="utf-8",
    )
    memory = root / MEMORY_REL
    memory.parent.mkdir(parents=True)
    memory.write_text(json.dumps({
        "meta": {"name": "x", "description": "x"},
        "items": [], "examples": [],
        "decisions": [
            {"id": "d1", "decision": "Keep the package namespace distinct",
             "rationale": "", "scope": [], "constraints": [], "anti_patterns": [],
             "rules": [{"type": "FORBID_LITERAL", "value": "sqlite"}],
             "created_at": BASE_TS, "updated_at": BASE_TS},
            {"id": "d2", "decision": "No psycopg2 in the service layer",
             "rationale": "", "scope": [], "constraints": [],
             "anti_patterns": ["psycopg2"],
             "created_at": BASE_TS, "updated_at": BASE_TS},
        ],
    }, indent=2) + "\n", encoding="utf-8")
    from mneme.memory_store import MemoryStore

    store = MemoryStore(memory)
    store.load()
    report = generate_protection_report(store.decisions(), repo_root=root)
    by_id = {d.id: d for d in report.decisions}
    assert by_id["d1"].protection_tier == "protected"
    assert by_id["d2"].protection_tier == "protected"
    assert report.protected == 2


# ── 10. offline Audit performs no GitHub calls ─────────────────────────────


def test_offline_audit_makes_no_github_calls(tmp_path, monkeypatch):
    import mneme.github_evidence as module

    def boom(*a, **k):
        raise AssertionError("GitHub must not be called during offline audit")

    monkeypatch.setattr(module, "_api_get_json", boom)
    monkeypatch.setattr(module, "_download_artifact", boom)
    monkeypatch.setattr(module, "_http_open", boom)

    root, memory, _sha = _git_repo(tmp_path)
    exit_code = main(["audit", "--memory", str(memory), "--repo-root", str(root)])
    assert exit_code == 0
    assert not (root / ".pytest_cache").exists()
    assert not list(root.rglob("__pycache__"))


# ── SECURITY: artifact redirect must not forward the bearer token ──────────


def test_artifact_redirect_does_not_forward_token(monkeypatch):
    import mneme.github_evidence as module

    seen: list[tuple[str, dict[str, str]]] = []

    def fake_open(url, headers, timeout):
        seen.append((url, dict(headers)))
        if "api.github.com" in url:
            return 302, {"location": "https://objects.githubusercontent.com/signed-blob"}, b""
        return 200, {}, b"zip-bytes"

    monkeypatch.setattr(module, "_http_open", fake_open)

    result = module._download_artifact(
        "/repos/acme/widgets/actions/artifacts/1/zip",
        "SECRET-TOKEN", "https://api.github.com", 5.0,
    )
    assert result == b"zip-bytes"

    api_call = next((h for u, h in seen if "api.github.com" in u), None)
    assert api_call is not None
    assert any(k.lower() == "authorization" for k in api_call)

    blob_call = next(
        (h for u, h in seen if "objects.githubusercontent.com" in u), None
    )
    assert blob_call is not None
    assert not any(k.lower() == "authorization" for k in blob_call), blob_call


# ── determinism for identical authenticated inputs ─────────────────────────


def test_deterministic_authenticated_claim(tmp_path, monkeypatch):
    root, memory, sha = _git_repo(tmp_path)
    _install_fake(monkeypatch, FakeGitHub(
        _valid_run(sha), [_artifact()],
        _evidence_zip(sha, [{"selector": SELECTOR, "outcome": "passed"}]),
    ))
    first = audit_with_github_claim(
        [_decision()], root, 42, token="tok", owner="acme", repo="widgets",
    )
    second = audit_with_github_claim(
        [_decision()], root, 42, token="tok", owner="acme", repo="widgets",
    )

    def snapshot(r):
        return (
            r.protected, r.mneme_ready, r.requires_modelling, r.guidance,
            tuple((d.id, d.protection_tier, d.evidence_confidence,
                   tuple(d.evidence_sources)) for d in r.decisions),
        )

    assert snapshot(first) == snapshot(second)
