"""D1E6: pinned closeout evidence for ADR-030 G16, G17, and G19.

G16/G17 run the D0 parity assertions (G1-G5) through the D1 load-time path:
a real section-less corpus is read by the pre-D1 loader, migrated with the
production migration command, and read again by the canonical loader. Every
runtime consumer must see identical results. Both corpora are all-``active``,
so the §12 lifecycle-conformance correction is out of scope here; it is
pinned by ``test_r1_migration_removes_non_active_decisions_from_layer1``
(G6 lifecycle parity for the adapters stays in ``tests/test_decision_index.py``).

Corpora (unchanged fixtures):

- ``examples/project_memory.json`` (section-less, legacy items migrate);
- ``tests/fixtures/d1_parity/pre_d1_live_project_memory.json``: the exact
  bytes of this repository's ``.mneme/project_memory.json`` immediately
  before the D1 live-memory cutover (git ``06989a4f^``, #441), pinned by
  SHA-256 below.

G19 serializes migrated memory through the Decision MCP service and transport
and pins rule identity: stable hash rule IDs only, never a positional or dual
ID, the positional ID recoverable from ``sequence``, the additive fields
present, and ``binding_authority`` absent.

The ADR-005 forbidden install literal is assembled at runtime so this file
does not carry it in its own bytes (see ``tests/test_decision_projection.py``).
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from mneme.benchmark import BenchmarkRunner, ScenarioVerdict
from mneme.conflict_detector import ConflictDetector
from mneme.decision_index import decisions_to_canonical
from mneme.decision_index_persistence import (
    apply_memory_migration,
    load_decision_index_from_memory_file,
    plan_memory_migration,
)
from mneme.decision_index_service import DecisionIndexService
from mneme.decision_mcp import get_result_to_transport, trace_to_transport
from mneme.decision_proposal_store import JsonFileDecisionProposalStore
from mneme.decision_retriever import DecisionRetriever
from mneme.enforcer import check_prompt, generate_protection_report
from mneme.memory_store import MemoryStore

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "d1_parity" / "pre_d1_live_project_memory.json"
FIXTURE_SHA256 = "a704745b8972bc7d541c103e40311ddf1db025f0fbc12792a575c435a575afcc"

CORPORA = {
    "examples": REPO_ROOT / "examples" / "project_memory.json",
    "pre-d1-live": FIXTURE,
}

# Assembled at runtime; see module docstring.
_ADR005_LITERAL = "pip " "install mneme"

QUERIES = (
    "storage backend json persistence",
    "retrieval determinism scoring",
    "encoding file writes automation",
    "workflow governance review",
    "edit to mneme/storage.py",
    "edit to docs/adr/ADR-005-brand-vs-package-namespace-enforcement.md",
    "edit to scripts/run_test_battery.py",
    "",
)

INPUTS = (
    _ADR005_LITERAL + "\n",
    "import psycopg2\n",
    "Set-Content -Path out.txt -Value data\n",
    "sqlite storage chosen for simplicity\n",
    "clean compliant response\n",
)

TARGETS = (None, "src/storage.py", "docs/adr/ADR-005-x.md")


@dataclass
class _DecisionSource:
    """Minimal store-shaped wrapper: BenchmarkRunner only calls decisions()."""

    _decisions: list = field(default_factory=list)

    def decisions(self) -> list:
        return list(self._decisions)


@dataclass
class _Migrated:
    path: Path
    pre: list
    post: list


def _migrate(tmp_path: Path, source: Path) -> _Migrated:
    """Pre-D1 load, production migration, canonical load of one corpus."""
    path = tmp_path / ".mneme" / "project_memory.json"
    path.parent.mkdir(parents=True)
    shutil.copyfile(source, path)
    assert "decision_index" not in json.loads(path.read_text(encoding="utf-8"))

    pre = MemoryStore(path).load().decisions
    assert apply_memory_migration(plan_memory_migration(path)) is True
    assert "decision_index" in json.loads(path.read_text(encoding="utf-8"))
    load_decision_index_from_memory_file(path)  # authoritative + snapshot parity
    post = MemoryStore(path).load().decisions
    return _Migrated(path=path, pre=pre, post=post)


@pytest.fixture(params=sorted(CORPORA), ids=sorted(CORPORA))
def migrated(request, tmp_path) -> _Migrated:
    return _migrate(tmp_path, CORPORA[request.param])


def test_pre_d1_live_fixture_is_unchanged():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256


# ── G16: D0 G1 projection parity through the load-time path ────────────────


def test_g16_corpora_are_all_active_so_lifecycle_correction_is_excluded(migrated):
    assert {d.status for d in migrated.pre} == {"active"}


def test_g16_load_time_projection_is_identical(migrated):
    assert migrated.post == migrated.pre
    assert len(migrated.post) > 0


# ── G17: consumer parity pre/post migration ─────────────────────────────────


def test_g17_retrieval_rankings_are_identical(migrated):  # D0 G2
    before = DecisionRetriever(migrated.pre)
    after = DecisionRetriever(migrated.post)
    for query in QUERIES:
        assert [
            (s.decision.id, s.score, s.matches) for s in before.retrieve(query)
        ] == [
            (s.decision.id, s.score, s.matches) for s in after.retrieve(query)
        ], query


def test_g17_strict_enforcement_verdicts_are_identical(migrated):  # D0 G3
    before = DecisionRetriever(migrated.pre)
    after = DecisionRetriever(migrated.post)
    for query in QUERIES:
        for text in INPUTS:
            left = check_prompt(text, before.retrieve(query))
            right = check_prompt(text, after.retrieve(query))
            assert left.verdict == right.verdict, (query, text)
            assert [
                (v.decision_id, v.rule, v.trigger, v.kind, v.severity.value)
                for v in left.violations
            ] == [
                (v.decision_id, v.rule, v.trigger, v.kind, v.severity.value)
                for v in right.violations
            ], (query, text)
            assert left.applicability == right.applicability, (query, text)


def test_g17_enforcement_fires_on_the_real_typed_rule(tmp_path):
    # Guards the verdict comparison against vacuous equality.
    corpus = _migrate(tmp_path, FIXTURE)
    scored = DecisionRetriever(corpus.post).retrieve(QUERIES[5])
    result = check_prompt(_ADR005_LITERAL + "\n", scored)
    assert "ADR-005" in {v.decision_id for v in result.violations}


def test_g17_conflict_detector_is_identical(migrated):  # D0 G4
    detector = ConflictDetector()
    for text in INPUTS:
        for target in TARGETS:
            left = detector.evaluate(text, migrated.pre, target_path=target)
            right = detector.evaluate(text, migrated.post, target_path=target)
            assert left.conflicts == right.conflicts, (text, target)
            assert left.applicability == right.applicability, (text, target)


def test_g17_architecture_audit_is_identical(migrated):  # D0 G5
    for repo_root in (REPO_ROOT, None):
        left = generate_protection_report(migrated.pre, repo_root=repo_root)
        right = generate_protection_report(migrated.post, repo_root=repo_root)
        assert left == right, repo_root
        assert left.total_decisions == len(migrated.pre)


def test_g17_frozen_benchmarks_are_identical(tmp_path):  # D0 G3
    corpus = _migrate(tmp_path, CORPORA["examples"])
    benchmarks = REPO_ROOT / "examples" / "benchmarks"
    before = BenchmarkRunner(_DecisionSource(corpus.pre)).run_suite(benchmarks)
    store = MemoryStore(corpus.path)
    store.load()  # the canonical loader, as runtime consumers use it
    after = BenchmarkRunner(store).run_suite(benchmarks)
    assert after == before
    assert after and all(r.verdict == ScenarioVerdict.PASS for r in after)


# ── G19: MCP rule identity on migrated memory ───────────────────────────────

_STABLE_RULE_ID = re.compile(r"^(?P<decision>.+):(?P<type>[A-Z_]+):[0-9a-f]{32}$")
_POSITIONAL_RULE_ID = re.compile(r":[A-Z_]+:\d{1,6}$")

_MULTI_RULE_MEMORY = {
    "meta": {"name": "g19", "description": "multi-rule migrated memory"},
    "items": [],
    "examples": [],
    "decisions": [
        {
            "id": "D-ONE",
            "decision": "Keep the API layer free of legacy clients",
            "rationale": "migration in progress",
            "scope": ["api"],
            "constraints": [],
            "anti_patterns": [],
            "rules": [
                {
                    "type": "FORBID_LITERAL",
                    "value": "legacy_client",
                    "include_paths": ["src/api/**"],
                    "exclude_paths": ["src/api/generated/**"],
                },
                {"type": "FORBID_LITERAL", "value": "old_sdk"},
                {"type": "FORBID_LITERAL", "value": "raw_socket"},
            ],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        },
        {
            "id": "D-TWO",
            "decision": "Use the message bus",
            "rationale": "",
            "scope": ["messaging"],
            "constraints": [],
            "anti_patterns": [],
            "rules": [{"type": "FORBID_LITERAL", "value": "direct_queue"}],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    ],
}


def _service(tmp_path: Path, memory: Path) -> DecisionIndexService:
    return DecisionIndexService(
        JsonFileDecisionProposalStore(tmp_path / "proposals.json"),
        canonical_index_loader=lambda: load_decision_index_from_memory_file(memory),
    )


def _mcp_payloads(tmp_path: Path, memory: Path) -> dict[str, dict]:
    service = _service(tmp_path, memory)
    index = load_decision_index_from_memory_file(memory)
    payloads = {}
    for record in index.records:
        payloads[record.decision_id] = {
            "get": get_result_to_transport(service.get(record.decision_id)),
            "trace": trace_to_transport(service.trace(record.decision_id)),
        }
    return payloads


def _multi_rule_migrated(tmp_path: Path) -> _Migrated:
    source = tmp_path / "source.json"
    source.write_text(json.dumps(_MULTI_RULE_MEMORY, indent=2) + "\n", encoding="utf-8")
    return _migrate(tmp_path / "corpus", source)


def test_g19_migrated_live_rule_id_golden_vector(tmp_path):
    corpus = _migrate(tmp_path, FIXTURE)
    trace = _mcp_payloads(tmp_path, corpus.path)["ADR-005"]["trace"]
    (rule,) = trace["derived_rules"]
    assert rule["rule_id"] == "ADR-005:FORBID_LITERAL:cbf4d271068507ddb12c33abd765e333"
    assert rule["rule_payload"] == {"value": _ADR005_LITERAL}
    assert trace["canonical_record"]["derived_rule_ids"] == [rule["rule_id"]]


def test_g19_mcp_emits_stable_rule_ids_only_never_positional(tmp_path):
    corpus = _multi_rule_migrated(tmp_path)
    payloads = _mcp_payloads(tmp_path, corpus.path)
    for decision_id, payload in payloads.items():
        record = payload["get"]["canonical_decision"]
        trace = payload["trace"]
        rules = trace["derived_rules"]
        assert rules, decision_id
        for rule in rules:
            match = _STABLE_RULE_ID.match(rule["rule_id"])
            assert match, rule["rule_id"]
            assert match["decision"] == decision_id
            assert match["type"] == rule["rule_type"]
        # derived_rule_ids is the sequence-ordered projection of the bindings.
        assert record["derived_rule_ids"] == [r["rule_id"] for r in rules]
        assert [r["sequence"] for r in rules] == list(range(len(rules)))
        # No dual identity: no positional ID appears anywhere in the payloads.
        for value in _strings(payload):
            assert not _POSITIONAL_RULE_ID.search(value), value


def test_g19_positional_id_is_recoverable_from_sequence(tmp_path):
    corpus = _multi_rule_migrated(tmp_path)
    payloads = _mcp_payloads(tmp_path, corpus.path)
    # The pre-D1 positional IDs, from the D0 adapter over the pre-D1 load.
    positional = {
        rule.rule_id: rule
        for rule in decisions_to_canonical(corpus.pre).rules
    }
    recovered = {}
    for decision_id, payload in payloads.items():
        for rule in payload["trace"]["derived_rules"]:
            old_id = f"{decision_id}:{rule['rule_type']}:{rule['sequence']}"
            recovered[old_id] = rule
    assert set(recovered) == set(positional)
    for old_id, rule in recovered.items():
        assert rule["rule_payload"] == dict(positional[old_id].rule_payload)
        assert rule["applicability"] == dict(positional[old_id].applicability)


def test_g19_additive_fields_present_and_binding_authority_absent(tmp_path):
    corpus = _multi_rule_migrated(tmp_path)
    persisted = json.loads(corpus.path.read_text(encoding="utf-8"))["decision_index"]
    assert {row["binding_authority"] for row in persisted["rules"]} == {"legacy_unknown"}
    for payload in _mcp_payloads(tmp_path, corpus.path).values():
        record = payload["get"]["canonical_decision"]
        assert record["version"] == "1"
        assert record["version_id"].startswith("dver-")
        assert record["decision_version_id"] == record["version_id"]
        assert len(record["content_digest"]) == 64
        for rule in payload["trace"]["derived_rules"]:
            assert rule["decision_version"] == "1"
            assert rule["decision_version_id"] == record["version_id"]
            assert isinstance(rule["sequence"], int)
            assert "binding_authority" not in rule
        assert "binding_authority" not in json.dumps(payload)


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in _strings(item)]
    if isinstance(value, (list, tuple)):
        return [s for item in value for s in _strings(item)]
    return []
