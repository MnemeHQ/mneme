"""DG1F-C3a loader/resolver validation compatibility (charter §3.4).

C3a lets three reporting consumers take their governed set from
``resolve_effective``. The C2 contract forbids catching a resolver
``ValueError``, so the resolver must never reject a canonical index that
``load_persisted_decision_index`` accepts; otherwise a working ``mneme audit``
would become an error. This module pins that property before any production
change (freeze amendment #775, validation gate 1):

(a) every canonical memory file in the repository loads and resolves;
(b) each resolver ``_validate`` condition that can be expressed in a persisted
    document is rejected by the loader first, and the lineage condition is
    impossible by construction (``derived_rule_ids`` is computed by the loader);
(c) seeded random mutations the loader accepts always resolve;
(d) on every canonical golden the effective set equals the projected ids.
"""
from __future__ import annotations

import copy
import json
import random
from pathlib import Path

import pytest

from mneme.decision_governance import GovernanceContext, _validate, resolve_effective
from mneme.decision_index_persistence import (
    DecisionIndexPersistenceError,
    content_digest_of,
    load_persisted_decision_index,
    version_id_of,
)
from mneme.memory_store import MemoryStore

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_MEMORY = ROOT / "tests" / "fixtures" / "dg1f_c2" / "memory"
CANONICAL_GOLDENS = (
    "canonical_v1",
    "canonical_v2_applicability",
    "canonical_conflict",
    "canonical_dangling",
)
_CONTEXTS = (GovernanceContext(), GovernanceContext(labels=()))


def _repository_canonical_documents() -> list[Path]:
    paths = []
    candidates = [ROOT / ".mneme" / "project_memory.json"]
    for top in ("docs", "examples", "tests/fixtures", "validation"):
        candidates.extend((ROOT / top).glob("**/*.json"))
    for path in sorted(set(c for c in candidates if c.is_file())):
        parts = set(path.relative_to(ROOT).parts)
        if parts & {".git", ".worktrees", "node_modules", ".venv", "venv"}:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict) and isinstance(data.get("decision_index"), dict):
            paths.append(path)
    return paths


_DOCUMENTS = _repository_canonical_documents()


def _section(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["decision_index"]


def _golden_section(form: str) -> dict:
    return _section(GOLDEN_MEMORY / form / ".mneme" / "project_memory.json")


def _resolves(section: dict) -> None:
    index = load_persisted_decision_index(section)
    _validate(index)
    for context in _CONTEXTS:
        resolve_effective(index, context)


# ── (a) repository canonical memory ────────────────────────────────────────


def test_a_repository_has_canonical_documents() -> None:
    assert len(_DOCUMENTS) >= 5, [str(p) for p in _DOCUMENTS]


@pytest.mark.parametrize(
    "path", _DOCUMENTS, ids=[p.relative_to(ROOT).as_posix() for p in _DOCUMENTS]
)
def test_a_every_repository_canonical_document_loads_and_resolves(path: Path) -> None:
    _resolves(_section(path))


# ── (b) each _validate condition is rejected by the loader first ───────────


def _rejected(section: dict) -> None:
    with pytest.raises((DecisionIndexPersistenceError, ValueError)):
        load_persisted_decision_index(section)


def test_b_duplicate_decision_id_is_rejected_by_the_loader() -> None:
    section = _golden_section("canonical_v1")
    section["decisions"].append(copy.deepcopy(section["decisions"][0]))
    _rejected(section)


@pytest.mark.parametrize("lifecycle", ["retired", "ACTIVE", "", "proposed"])
def test_b_unknown_lifecycle_is_rejected_by_the_loader(lifecycle: str) -> None:
    section = _golden_section("canonical_v1")
    section["decisions"][0]["lifecycle_status"] = lifecycle
    _rejected(section)


def test_b_rule_naming_an_unknown_decision_is_rejected_by_the_loader() -> None:
    section = _golden_section("canonical_v1")
    rule = next(r for r in section["rules"])
    rule["decision_id"] = "GHOST-404"
    _rejected(section)


def test_b_rule_naming_an_unknown_version_is_rejected_by_the_loader() -> None:
    section = _golden_section("canonical_v1")
    rule = next(r for r in section["rules"])
    rule["decision_version_id"] = "dver-" + "0" * 32
    _rejected(section)


def test_b_duplicate_rule_binding_is_rejected_by_the_loader() -> None:
    section = _golden_section("canonical_v1")
    section["rules"].append(copy.deepcopy(section["rules"][0]))
    _rejected(section)


def _with_new_active_version(section: dict) -> tuple[dict, dict, dict]:
    decision = next(
        d for d in section["decisions"]
        if any(r["decision_id"] == d["decision_id"] for r in section["rules"])
        and d["lifecycle_status"] == "active"
    )
    old = next(v for v in section["versions"] if v["version_id"] == decision["active_version_id"])
    new = copy.deepcopy(old)
    new["statement"] = old["statement"] + " (revised)"
    new["revision"] = str(int(old.get("revision", "1")) + 1)
    new["content_digest"] = content_digest_of(
        new["statement"],
        new.get("rationale", ""),
        new.get("context_scope", []),
        new.get("constraints", []),
        new.get("anti_patterns", []),
    )
    new["supersedes_version_id"] = old["version_id"]
    new["version_id"] = version_id_of(
        new["decision_id"],
        new["content_digest"],
        new["occurrence_source_identity"],
        old["version_id"],
    )
    section["versions"].append(new)
    decision["active_version_id"] = new["version_id"]
    return decision, old, new


def test_b_lineage_rule_bound_only_to_a_non_active_version_loads_and_validates() -> None:
    section = _golden_section("canonical_v1")
    decision, _old, _new = _with_new_active_version(section)
    index = load_persisted_decision_index(section)
    record = next(r for r in index.records if r.decision_id == decision["decision_id"])
    assert record.derived_rule_ids == ()
    assert not index.rules_for_decision(decision["decision_id"])
    _resolves(section)


def test_b_lineage_rule_bound_to_old_and_active_versions_loads_and_validates() -> None:
    section = _golden_section("canonical_v1")
    decision, _old, new = _with_new_active_version(section)
    historical = next(r for r in section["rules"] if r["decision_id"] == decision["decision_id"])
    current = copy.deepcopy(historical)
    current["decision_version_id"] = new["version_id"]
    current["decision_version"] = new["revision"]
    section["rules"].append(current)
    index = load_persisted_decision_index(section)
    record = next(r for r in index.records if r.decision_id == decision["decision_id"])
    bound = tuple(r.rule_id for r in index.rules_for_decision(decision["decision_id"]))
    assert sorted(bound) == sorted(record.derived_rule_ids)
    assert all(
        r.decision_version_id == new["version_id"]
        for r in index.rules_for_decision(decision["decision_id"])
    )
    _resolves(section)


# ── (c) seeded random mutations: loader-accepted ⇒ resolver-accepted ───────


def _mutate(section: dict, rng: random.Random) -> dict:
    s = copy.deepcopy(section)
    op = rng.randrange(10)
    decisions, versions, rules = s["decisions"], s["versions"], s["rules"]
    if op == 0 and decisions:
        rng.choice(decisions)["lifecycle_status"] = rng.choice(
            ["active", "superseded", "deprecated", "inactive", "bogus"]
        )
    elif op == 1 and decisions:
        decisions.append(copy.deepcopy(rng.choice(decisions)))
    elif op == 2 and rules:
        del rules[rng.randrange(len(rules))]
    elif op == 3 and rules:
        rules.append(copy.deepcopy(rng.choice(rules)))
    elif op == 4 and rules and decisions:
        rng.choice(rules)["decision_id"] = rng.choice(decisions)["decision_id"]
    elif op == 5 and rules and versions:
        rng.choice(rules)["decision_version_id"] = rng.choice(versions)["version_id"]
    elif op == 6 and decisions and versions:
        rng.choice(decisions)["active_version_id"] = rng.choice(versions)["version_id"]
    elif op == 7 and len(decisions) > 1:
        a, b = rng.sample(decisions, 2)
        a.setdefault("relationships", []).append(
            {"type": "supersedes", "target_decision_id": b["decision_id"]}
        )
    elif op == 8 and decisions:
        rng.choice(decisions).setdefault("relationships", []).append(
            {"type": "supersedes", "target_decision_id": "GHOST-404"}
        )
    elif op == 9 and versions:
        del versions[rng.randrange(len(versions))]
    return s


@pytest.mark.parametrize("form", CANONICAL_GOLDENS)
def test_c_loader_accepted_mutations_always_resolve(form: str) -> None:
    base = _golden_section(form)
    rng = random.Random(f"dg1f-c3a:{form}")
    accepted = 0
    for _ in range(150):
        section = base
        for _step in range(rng.randint(1, 3)):
            section = _mutate(section, rng)
        try:
            load_persisted_decision_index(section)
        except (DecisionIndexPersistenceError, ValueError):
            continue
        accepted += 1
        _resolves(section)
    assert accepted >= 20, f"{form}: only {accepted} mutations accepted by the loader"


# ── (d) effective set equals projection on every canonical golden ──────────


@pytest.mark.parametrize("form", CANONICAL_GOLDENS)
def test_d_effective_set_equals_projected_ids(form: str) -> None:
    store = MemoryStore(GOLDEN_MEMORY / form / ".mneme" / "project_memory.json")
    store.load()
    assert store.canonical_index is not None
    resolution = resolve_effective(store.canonical_index, GovernanceContext())
    assert sorted(resolution.effective_ids) == sorted(d.id for d in store.decisions())
