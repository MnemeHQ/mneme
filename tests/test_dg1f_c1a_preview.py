"""DG1F-C1a acceptance: report-only check preview (charter §5a, PRs #493/#494).

Offline; GSA-TTS/agentic-coding-quickstart ADR-0028 is pinned by the
DG1B1 acceptance fixture. These tests do not modify Layer 1 benchmarks.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

import mneme.cli as cli
from mneme.cli import main
from mneme.decision_governance import GovernanceFinding
from mneme.decision_index_persistence import set_decision_applicability
from tests.canonical_fixtures import canonical_document, v1_document

SOURCE = (
    Path(__file__).parent / "fixtures" / "dg1b1_functional_acceptance"
    / "gsa_adr_0028_windows_secret_storage.json"
)
DECISION_ID = "0028-windows-native-secret-storage"
FORBIDDEN = "dpapi-plaintext-export"


def _source_memory() -> dict:
    evidence = json.loads(SOURCE.read_text(encoding="utf-8"))
    assert evidence["repository"] == "GSA-TTS/agentic-coding-quickstart"
    assert (
        evidence["repository_commit_sha"]
        == "8e6160c63acc35bd48d0a3844e133ea3ad52a464"
    )
    return {
        "meta": {"name": "gsa-adr-0028-preview", "description": "offline acceptance"},
        "items": [],
        "examples": [],
        "decisions": [{
            "id": DECISION_ID,
            "decision": "Windows native secret store is gated to Windows hosts (MSYS/MINGW)",
            "rationale": evidence["source_evidence"],
            "scope": ["acq.secret-store.windows"],
            "constraints": [],
            "anti_patterns": [],
            "rules": [{"type": "FORBID_LITERAL", "value": FORBIDDEN}],
            "test_evidence": [],
            "source": {
                "type": "adr",
                "path": evidence["source_file"],
                "sha256": evidence["repository_commit_sha"],
            },
            "created_at": "2026-09-13T00:00:00Z",
            "updated_at": "2026-09-13T00:00:00Z",
            "status": "active",
        }],
    }


def _memory_document(kind: str) -> dict:
    original = _source_memory()
    if kind == "sectionless":
        return original
    canonical = canonical_document(original)
    if kind == "v1":
        return v1_document(canonical)
    if kind == "v2_without_applicability":
        return canonical
    assert kind == "v2"
    with_labels, changed = set_decision_applicability(
        canonical, decision_id=DECISION_ID,
        required_labels=("platform:windows",),
    )
    assert changed
    return with_labels


def _setup(tmp_path: Path, kind: str) -> tuple[list[str], Path]:
    memory = tmp_path / "project_memory.json"
    memory.write_text(json.dumps(_memory_document(kind)), encoding="utf-8")
    target = tmp_path / "input.txt"
    target.write_text(FORBIDDEN + "\n", encoding="utf-8")
    args = [
        "check", "--memory", str(memory),
        "--input", str(target),
        "--query", "store secret",
        "--adr-dir", str(tmp_path / "absent-adr"),
    ]
    return args, memory


def _run(args: list[str], capsys) -> tuple[int, str, str]:
    code = main(args)
    output = capsys.readouterr()
    return code, output.out, output.err


@pytest.mark.parametrize(
    "kind", ["sectionless", "v1", "v2_without_applicability", "v2"]
)
@pytest.mark.parametrize("mode", ["strict", "warn"])
@pytest.mark.parametrize("machine", [False, True], ids=["human", "json"])
def test_default_parity_and_preview_noninterference(
    tmp_path: Path, capsys, kind: str, mode: str, machine: bool
) -> None:
    """§5a(1,2,5): same enforcement, stdout, JSON, mode and exit code."""
    args, memory = _setup(tmp_path, kind)
    original_bytes = memory.read_bytes()
    args += ["--mode", mode]
    if machine:
        args.append("--json")
    base = _run(args, capsys)
    preview = _run(
        args + ["--applicability-preview", "platform:linux"], capsys
    )
    assert preview[:2] == base[:2]
    assert memory.read_bytes() == original_bytes  # Neither mode writes authority.
    assert base[2] == ""
    assert base[0] == (2 if mode == "strict" else 0)
    assert "NON-AUTHORITATIVE" in preview[2]
    if machine:
        assert json.loads(preview[1]) == json.loads(base[1])
        assert json.loads(preview[1])["schema"] == "mneme.check/v1"
    if kind == "sectionless":
        assert "PREVIEW UNAVAILABLE" in preview[2]
    else:
        assert "PREVIEW UNAVAILABLE" not in preview[2]
        if kind == "v2":
            assert f"[{DECISION_ID}] ineffective" in preview[2]
        else:
            assert f"[{DECISION_ID}] effective" in preview[2]
    if kind == "v2":
        assert "cause=not_applicable" in preview[2]


def test_matched_labels_and_repeatability_do_not_create_authority(
    tmp_path: Path, capsys
) -> None:
    """§5a(3,4): matching Windows labels preview effectiveness only."""
    args, _ = _setup(tmp_path, "v2")
    base = _run(args, capsys)
    preview = _run(
        args + [
            "--applicability-preview", "platform:windows",
            "--applicability-preview", "platform:windows",
            "--applicability-preview", "other:assertion",
        ], capsys,
    )
    assert preview[:2] == base[:2]
    assert preview[0] == 2  # A matching preview never grants a waiver.
    assert f"[{DECISION_ID}] effective" in preview[2]
    assert '"other:assertion", "platform:windows"' in preview[2]


@pytest.mark.parametrize("labels", [
    ["platform:linux"],
    ["Platform:Windows"],
    ["platform:linux", "arbitrary:spoofed"],
])
def test_spoofed_labels_never_disable_protection(
    tmp_path: Path, capsys, labels: list[str]
) -> None:
    """§5a(4): excluded *preview* decisions remain enforced."""
    args, _ = _setup(tmp_path, "v2")
    args += ["--mode", "strict", "--json"]
    without = _run(args, capsys)
    flags = [part for label in labels for part in ("--applicability-preview", label)]
    with_preview = _run(args + flags, capsys)
    assert with_preview[:2] == without[:2]
    assert with_preview[0] == 2
    assert "not_applicable" in with_preview[2]
    assert len(json.loads(with_preview[1])["violations"]) >= 1


def test_preview_failure_isolated_from_enforcement(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    """§5a(3): resolution exception cannot change the ordinary check."""
    args, _ = _setup(tmp_path, "v2")
    args += ["--json"]
    base = _run(args, capsys)

    def broken_resolution(*_args, **_kwargs):
        raise RuntimeError("preview computation failed")

    monkeypatch.setattr(cli, "resolve_effective", broken_resolution)
    preview = _run(args + ["--applicability-preview", "platform:linux"], capsys)
    assert preview[:2] == base[:2]
    assert "NON-AUTHORITATIVE" in preview[2]
    assert "PREVIEW UNAVAILABLE" in preview[2]


def test_invalid_caller_label_does_not_change_verdict(
    tmp_path: Path, capsys
) -> None:
    args, _ = _setup(tmp_path, "v2")
    base = _run(args, capsys)
    preview = _run(args + ["--applicability-preview", ""], capsys)
    assert preview[:2] == base[:2]
    assert "PREVIEW UNAVAILABLE" in preview[2]


def test_uses_same_snapshot_as_enforcement_not_second_file_read(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    """C1a must use the validated snapshot, even if the path changes later."""
    args, memory = _setup(tmp_path, "v2")
    base = _run(args, capsys)
    original_load = cli.MemoryStore.load

    def load_then_substitute(self):
        loaded = original_load(self)
        memory.write_text("{ malformed after load", encoding="utf-8")
        return loaded

    monkeypatch.setattr(cli.MemoryStore, "load", load_then_substitute)
    monkeypatch.setattr(cli, "_collect_adr_diagnostics", lambda **kwargs: [])
    preview = _run(
        args + ["--applicability-preview", "platform:linux"], capsys
    )
    assert preview[:2] == base[:2]
    assert "cause=not_applicable" in preview[2]
    assert "PREVIEW UNAVAILABLE" not in preview[2]


def test_governance_findings_make_preview_unavailable_not_enforcement(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    """Incomplete governance resolution must not invent a preview winner."""
    args, _ = _setup(tmp_path, "v2")
    args += ["--json"]
    base = _run(args, capsys)
    original_resolve = cli.resolve_effective

    def resolution_with_finding(index, context):
        value = original_resolve(index, context)
        return replace(value, findings=(GovernanceFinding(
            code="dangling_supersedes", decision_id="dangling-id",
        ),))

    monkeypatch.setattr(cli, "resolve_effective", resolution_with_finding)
    preview = _run(args + ["--applicability-preview", "platform:windows"], capsys)
    assert preview[:2] == base[:2]
    assert "PREVIEW UNAVAILABLE" in preview[2]
    assert "NON-AUTHORITATIVE" in preview[2]
