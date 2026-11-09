"""DG1F-C2 negative and mutation tests (charter §4, freeze amendment #767).

C2 is preparatory lifecycle-authority consolidation: one lifecycle predicate
shared by projection, the resolver and the runtime lifecycle checks, plus a
three-state ``GovernanceContext``. It changes no observable output (pinned by
``test_dg1f_c2_golden_parity.py``). Each test here fails if its guard is
removed.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import re
from pathlib import Path

import pytest

import mneme.decision_index as decision_index
from mneme import decision_projection
from mneme.decision_governance import (
    CAUSE_NOT_APPLICABLE,
    GOVERNANCE_SEMANTICS_VERSION,
    STATUS_EFFECTIVE,
    STATUS_INEFFECTIVE,
    GovernanceContext,
    compare_resolutions,
    resolve_effective,
    resolve_effective_from_memory_file,
)
from mneme.decision_index_persistence import (
    load_decision_index_from_memory_file,
    load_persisted_decision_index,
)
from mneme.decision_retriever import DecisionRetriever
from mneme.enforcer import check_prompt, generate_protection_report
from mneme.evidence import CiEvidenceDocument, match_ci_evidence
from mneme.memory_store import MemoryStore
from mneme.protection import activation_precheck, find_candidates
from tests.dg1f_c2_corpus import (
    APPLICABILITY_DECISION,
    APPLICABILITY_LABELS,
    EVIDENCE_SELECTOR,
    EVIDENCE_SHA,
    GOLDENS,
    MEMORY_DIR,
)

ROOT = Path(__file__).resolve().parent.parent


def _memory(form: str) -> Path:
    return MEMORY_DIR / form / ".mneme" / "project_memory.json"


def _runtime(form: str):
    store = MemoryStore(_memory(form))
    store.load()
    return store.decisions()


def _evidence_document() -> CiEvidenceDocument:
    return CiEvidenceDocument(
        repository_sha=EVIDENCE_SHA,
        producer_type="github-actions",
        producer_run_id="1",
        results=((EVIDENCE_SELECTOR, "passed"),),
    )


@pytest.fixture
def widen_governing_set(monkeypatch):
    """Mutate the single lifecycle authority (and only it) for one test."""
    def apply(statuses: set[str]) -> None:
        monkeypatch.setattr(
            decision_index, "GOVERNING_LIFECYCLE_STATUSES", frozenset(statuses)
        )
    return apply


# ── 1. applicability is never dropped when labels are not supplied ─────────


def test_1_unknown_context_conservatively_includes_and_never_claims_a_match() -> None:
    index = load_decision_index_from_memory_file(_memory("canonical_v2_applicability"))

    not_supplied = resolve_effective(index)  # default: labels not supplied
    assert not not_supplied.labels_supplied
    decision = {d.decision_id: d for d in not_supplied.decisions}[APPLICABILITY_DECISION]
    assert decision.status == STATUS_EFFECTIVE and decision.cause is None
    assert decision.lifecycle_eligible is True
    assert decision.applicability_evaluated is False
    trace = {step.step: step for step in decision.trace}
    assert trace["applicability"].outcome == "context_not_supplied"
    assert trace["applicability"].detail == tuple(APPLICABILITY_LABELS)
    assert all(step.outcome != "matched" for step in decision.trace)
    assert all(not d.applicability_evaluated for d in not_supplied.decisions)

    empty = resolve_effective(index, GovernanceContext(labels=()))
    decision = {d.decision_id: d for d in empty.decisions}[APPLICABILITY_DECISION]
    assert (decision.status, decision.cause) == (STATUS_INEFFECTIVE, CAUSE_NOT_APPLICABLE)
    assert decision.applicability_evaluated is True

    matched = resolve_effective(index, GovernanceContext(labels=tuple(APPLICABILITY_LABELS)))
    decision = {d.decision_id: d for d in matched.decisions}[APPLICABILITY_DECISION]
    assert decision.status == STATUS_EFFECTIVE and decision.applicability_evaluated
    assert {s.step: s.outcome for s in decision.trace}["applicability"] == "matched"


def test_1b_context_states_are_distinct_and_validated() -> None:
    assert GovernanceContext().labels is None
    assert GovernanceContext(labels=()).labels == ()
    assert GovernanceContext() != GovernanceContext(labels=())
    with pytest.raises(ValueError):
        GovernanceContext(labels="windows")  # a bare string is not a label set
    with pytest.raises(ValueError):
        GovernanceContext(labels=("",))


# ── 2. integrity findings never block a consumer ───────────────────────────


@pytest.mark.parametrize("form", ["canonical_conflict", "canonical_dangling"])
def test_2_findings_change_no_consumer_output(form: str) -> None:
    resolution = resolve_effective_from_memory_file(_memory(form))
    assert resolution.findings, "fixture must carry an integrity finding"
    baseline = resolve_effective_from_memory_file(_memory("canonical_v1"))
    assert resolution.effective_ids == baseline.effective_ids

    goldens = json.loads(GOLDENS.read_text(encoding="utf-8"))
    for key in ("runtime_decisions", "readiness_counts", "match_ci_evidence"):
        assert goldens[form]["in_process"][key] == goldens["canonical_v1"]["in_process"][key]
    def runtime_view(name: str):
        return [dataclasses.replace(d, memory_path="") for d in _runtime(name)]

    assert runtime_view(form) == runtime_view("canonical_v1")


# ── 3. legacy D-1 is preserved: check enforces, Audit excludes ─────────────


def test_3_legacy_superseded_still_enforced_by_check_and_excluded_by_audit(
    widen_governing_set,
) -> None:
    decisions = _runtime("legacy_sectionless")
    by_id = {d.id: d for d in decisions}
    assert by_id["C2-OLD"].status == "superseded"

    def violated_ids() -> set[str]:
        scored = DecisionRetriever(decisions).retrieve("edit app.py")
        result = check_prompt("import mysqlclient\n", scored)
        return {v.decision_id for v in result.violations}

    assert "C2-OLD" in violated_ids()
    report = generate_protection_report(decisions)
    assert report.protected == 1  # C2-LIT only; superseded C2-OLD excluded

    # check enforcement does not consult the lifecycle predicate (charter §3.3):
    widen_governing_set(set())
    assert "C2-OLD" in violated_ids()
    assert generate_protection_report(decisions).protected == 0


# ── 4. evidence ambiguity is unchanged ─────────────────────────────────────


def test_4_superseded_legacy_selector_is_not_ambiguity(widen_governing_set) -> None:
    decisions = _runtime("legacy_sectionless")
    owners = [
        d.id for d in decisions
        if any(e.get("selector") == EVIDENCE_SELECTOR for e in d.test_evidence)
    ]
    assert sorted(owners) == ["C2-LIT", "C2-OLD"]
    assert match_ci_evidence(decisions, EVIDENCE_SHA, _evidence_document()) == {
        "C2-LIT": [EVIDENCE_SELECTOR]
    }
    widen_governing_set({"active", "superseded"})
    assert match_ci_evidence(decisions, EVIDENCE_SHA, _evidence_document()) == {}


# ── 5. one lifecycle authority ─────────────────────────────────────────────


def test_5_projection_alias_is_the_single_authority_object() -> None:
    assert (
        decision_projection.PROJECTABLE_LIFECYCLE_STATUSES
        is decision_index.GOVERNING_LIFECYCLE_STATUSES
    )
    assert decision_index.GOVERNING_LIFECYCLE_STATUSES <= decision_index.VALID_LIFECYCLE_STATUSES


def test_5_widening_the_authority_moves_every_consumer(widen_governing_set) -> None:
    canonical = load_decision_index_from_memory_file(_memory("canonical_v1"))
    legacy = _runtime("legacy_sectionless")
    old = next(d for d in legacy if d.id == "C2-OLD")
    old_pickle = next(d for d in legacy if d.id == "C2-OLDPICKLE")

    # Baseline: superseded governs nowhere.
    assert "C2-OLD" not in {d.id for d in decision_projection.project_canonical_index(canonical)}
    assert "C2-OLD" not in resolve_effective(canonical).effective_ids
    assert not activation_precheck(old).eligible
    assert "C2-OLDPICKLE" not in {c.decision_id for c in find_candidates(legacy).candidates}

    widen_governing_set({"active", "superseded"})
    assert "C2-OLD" in {d.id for d in decision_projection.project_canonical_index(canonical)}
    resolution = resolve_effective(canonical)
    assert "C2-OLD" in resolution.effective_ids
    assert {d.decision_id: d for d in resolution.decisions}["C2-OLD"].lifecycle_eligible
    assert generate_protection_report(legacy).protected == 2  # C2-LIT + C2-OLD
    assert "decision status" not in activation_precheck(old).reason
    assert "C2-OLDPICKLE" in {c.decision_id for c in find_candidates(legacy).candidates}
    del old_pickle


_CONSUMER_MODULES = (
    "mneme/decision_projection.py",
    "mneme/decision_governance.py",
    "mneme/enforcer.py",
    "mneme/protection.py",
    "mneme/evidence.py",
)


@pytest.mark.parametrize("module", _CONSUMER_MODULES)
def test_5_no_duplicated_lifecycle_literal_remains(module: str) -> None:
    source = (ROOT / module).read_text(encoding="utf-8")
    code = "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith(("#", "``", "\"", "'"))
    )
    assert not re.search(r"""(==|!=|\bin\b)\s*["']active["']""", code), module
    assert not re.search(r"""frozenset\(\{\s*["']active["']\s*\}\)""", code), module


# ── 6. resolver errors are never swallowed into "no decisions" ─────────────


def test_6_malformed_index_raises_through_every_entry_point(tmp_path: Path) -> None:
    document = json.loads(_memory("canonical_v1").read_text(encoding="utf-8"))
    section = document["decision_index"]
    section["decisions"].append(copy.deepcopy(section["decisions"][0]))
    with pytest.raises(ValueError):
        resolve_effective(load_persisted_decision_index(section))
    path = tmp_path / "project_memory.json"
    path.write_bytes(json.dumps(document).encode("utf-8"))
    with pytest.raises(ValueError):
        resolve_effective_from_memory_file(path)
    with pytest.raises(ValueError):
        resolve_effective_from_memory_file(path, GovernanceContext(labels=()))


# ── 7. cross-semantics and cross-context comparisons are refused ───────────


def test_7_resolutions_from_other_semantics_or_context_states_are_not_comparable() -> None:
    index = load_decision_index_from_memory_file(_memory("canonical_v2_applicability"))
    current = resolve_effective(index)
    assert current.semantics_version == GOVERNANCE_SEMANTICS_VERSION
    assert GOVERNANCE_SEMANTICS_VERSION.endswith("/dg1f-c2-1")

    older = dataclasses.replace(
        current, semantics_version="mneme.governance-semantics/dg1b1-1"
    )
    with pytest.raises(ValueError, match="different governance semantics"):
        compare_resolutions(older, current)

    supplied = resolve_effective(index, GovernanceContext(labels=()))
    with pytest.raises(ValueError, match="different contexts"):
        compare_resolutions(current, supplied)
