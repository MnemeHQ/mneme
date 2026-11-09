"""DG1F-C3a negative and mutation tests (charter #774 §4, freeze #775).

``mneme audit``, setup readiness and ``protect list`` take their governed set
from ``decision_governance.governed_runtime_decisions``: the resolver result
on canonical memory (labels not supplied, same snapshot), the C2 path on
section-less memory. Outputs are pinned by the C2 and C3a goldens; each test
here fails if its guard is removed. Test 7 (validation compatibility) lives
in ``test_dg1f_c3a_validation_compat.py``.
"""
from __future__ import annotations

import dataclasses
import inspect
import shutil
from pathlib import Path

import pytest

import mneme.decision_governance as governance
from mneme import cli, github_evidence, protection
from mneme.decision_governance import STATUS_INEFFECTIVE, governed_runtime_decisions
from mneme.memory_store import MemoryStore
from mneme.setup import run_setup
from tests.dg1f_c2_corpus import MEMORY_DIR

EXCLUDED = "C2-PICKLE"  # the mneme_ready candidate in every canonical golden


def _repo(tmp_path: Path, form: str) -> Path:
    workdir = tmp_path / "repo"
    shutil.copytree(MEMORY_DIR / form, workdir)
    (workdir / ".git").mkdir()
    return workdir


def _memory(workdir: Path) -> str:
    return str(workdir / ".mneme" / "project_memory.json")


@pytest.fixture
def resolver_excludes(monkeypatch):
    """A resolver that additionally reports EXCLUDED as ineffective."""
    real = governance.resolve_effective

    def fake(index, context=None):
        resolution = real(index, context)
        decisions = tuple(
            dataclasses.replace(d, status=STATUS_INEFFECTIVE, cause="test_exclusion")
            if d.decision_id == EXCLUDED else d
            for d in resolution.decisions
        )
        return dataclasses.replace(resolution, decisions=decisions)

    monkeypatch.setattr(governance, "resolve_effective", fake)


@pytest.fixture
def resolver_calls(monkeypatch):
    """Record (index, context) for every resolver call made by the helper."""
    calls: list[tuple[object, object]] = []
    real = governance.resolve_effective

    def spy(index, context=None):
        calls.append((index, context))
        return real(index, context)

    monkeypatch.setattr(governance, "resolve_effective", spy)
    return calls


def _audit(workdir: Path, capsys) -> str:
    assert cli.main(["audit", "--memory", _memory(workdir)]) == 0
    return capsys.readouterr().out


def _protect_list(workdir: Path, capsys) -> str:
    assert cli.main(["protect", "list", "--memory", _memory(workdir)]) == 0
    return capsys.readouterr().out


# ── 1. the three consumers follow the resolver result ──────────────────────


def test_1_consumers_follow_the_resolver(tmp_path, capsys, resolver_excludes) -> None:
    workdir = _repo(tmp_path, "canonical_v1")
    assert EXCLUDED not in _audit(workdir, capsys)
    assert EXCLUDED not in _protect_list(workdir, capsys)
    outcome = run_setup(root=workdir, pairing=None)
    assert outcome.decision_count == 3
    assert outcome.readiness["mneme_ready"] == 0


def test_1_baseline_without_the_fake_still_lists_the_decision(tmp_path, capsys) -> None:
    workdir = _repo(tmp_path, "canonical_v1")
    assert EXCLUDED in _audit(workdir, capsys)
    assert EXCLUDED in _protect_list(workdir, capsys)
    assert run_setup(root=workdir, pairing=None).decision_count == 4


# ── 2. labels are never supplied ───────────────────────────────────────────


def test_2_every_consumer_resolves_with_labels_not_supplied(
    tmp_path, capsys, resolver_calls
) -> None:
    workdir = _repo(tmp_path, "canonical_v2_applicability")
    _audit(workdir, capsys)
    _protect_list(workdir, capsys)
    run_setup(root=workdir, pairing=None)
    assert len(resolver_calls) >= 3
    assert all(context is not None and context.labels is None for _, context in resolver_calls)


def test_2_supplied_empty_labels_would_drop_the_applicability_decision() -> None:
    store = MemoryStore(MEMORY_DIR / "canonical_v2_applicability" / ".mneme" / "project_memory.json")
    store.load()
    governed = {d.id for d in governed_runtime_decisions(store)}
    supplied_empty = set(
        governance.resolve_effective(
            store.canonical_index, governance.GovernanceContext(labels=())
        ).effective_ids
    )
    assert "C2-LIT" in governed
    assert "C2-LIT" not in supplied_empty


# ── 3. single snapshot, no file read ───────────────────────────────────────


def test_3_resolver_uses_the_stores_own_index(monkeypatch, resolver_calls) -> None:
    store = MemoryStore(MEMORY_DIR / "canonical_v1" / ".mneme" / "project_memory.json")
    store.load()

    def no_reads(*args, **kwargs):
        raise AssertionError("governed_runtime_decisions must not read files")

    monkeypatch.setattr("builtins.open", no_reads)
    monkeypatch.setattr(Path, "read_text", no_reads)
    monkeypatch.setattr(Path, "read_bytes", no_reads)
    governed = governed_runtime_decisions(store)
    monkeypatch.undo()
    assert len(resolver_calls) == 1
    assert resolver_calls[0][0] is store.canonical_index
    assert [d.id for d in governed] == [d.id for d in store.decisions()]


def test_3_each_consumer_loads_memory_once(tmp_path, capsys, monkeypatch) -> None:
    workdir = _repo(tmp_path, "canonical_v1")
    loads: list[object] = []
    real_load = MemoryStore.load

    def counting_load(self):
        loads.append(self)
        return real_load(self)

    monkeypatch.setattr(MemoryStore, "load", counting_load)
    _audit(workdir, capsys)
    assert len(loads) == 1
    loads.clear()
    _protect_list(workdir, capsys)
    assert len(loads) == 1


# ── 4. legacy section-less memory keeps the C2 path ────────────────────────


@pytest.mark.parametrize("form", ["legacy_sectionless", "legacy_items"])
def test_4_legacy_memory_never_reaches_the_resolver(form, resolver_calls) -> None:
    store = MemoryStore(MEMORY_DIR / form / ".mneme" / "project_memory.json")
    store.load()
    assert store.canonical_index is None
    assert governed_runtime_decisions(store) == store.decisions()
    assert resolver_calls == []


# ── 5. excluded surfaces do not use the helper ─────────────────────────────


def test_5_excluded_surfaces_never_call_the_helper(tmp_path, capsys, monkeypatch) -> None:
    workdir = _repo(tmp_path, "canonical_v1")

    def forbidden(store):
        raise AssertionError("excluded surface called governed_runtime_decisions")

    monkeypatch.setattr(governance, "governed_runtime_decisions", forbidden)
    monkeypatch.setattr(cli, "governed_runtime_decisions", forbidden)
    monkeypatch.setattr(protection, "load_governed_decisions", forbidden)
    memory = _memory(workdir)
    assert protection.load_decisions(memory)
    cli.main(["protect", "status", "C2-PICKLE", "--memory", memory])
    cli.main(["protect", "validate", "C2-PICKLE", "--memory", memory])
    capsys.readouterr()
    for function in (
        protection.load_decisions,
        protection.activation_precheck,
        github_evidence.audit_with_github_claim,
        cli._require_memory,
        cli._cmd_check,
        cli._cmd_protect_status,
        cli._cmd_protect_validate,
        cli._cmd_protect_activate,
    ):
        assert "governed_runtime_decisions" not in inspect.getsource(function), function


# ── 6. integrity findings never block ──────────────────────────────────────


@pytest.mark.parametrize("form", ["canonical_conflict", "canonical_dangling"])
def test_6_findings_do_not_change_the_governed_set(form: str) -> None:
    def governed_ids(name: str) -> list[str]:
        store = MemoryStore(MEMORY_DIR / name / ".mneme" / "project_memory.json")
        store.load()
        return [d.id for d in governed_runtime_decisions(store)]

    resolution = governance.resolve_effective_from_memory_file(
        MEMORY_DIR / form / ".mneme" / "project_memory.json"
    )
    assert resolution.findings
    assert governed_ids(form) == governed_ids("canonical_v1")


# ── 3b. resolver errors are never caught, wrapped or turned into a list ────


@pytest.fixture
def resolver_raises(monkeypatch):
    def boom(index, context=None):
        raise ValueError("injected resolver failure")

    monkeypatch.setattr(governance, "resolve_effective", boom)


def test_3b_resolver_errors_propagate_unwrapped(tmp_path, resolver_raises) -> None:
    from mneme.setup import SetupError, _load_validated_decisions

    workdir = _repo(tmp_path, "canonical_v1")
    memory = Path(_memory(workdir))
    store = MemoryStore(memory)
    store.load()
    for call in (
        lambda: governed_runtime_decisions(store),
        lambda: _load_validated_decisions(memory),
        lambda: protection.load_governed_decisions(memory),
    ):
        with pytest.raises(ValueError, match="injected resolver failure") as caught:
            call()
        assert not isinstance(caught.value, (SetupError, protection.ProtectionError))
