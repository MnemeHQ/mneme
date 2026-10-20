"""Regression: a pre-D1 repository must stay usable across the 0.10 upgrade.

Release 0.10.0 made the decision_index section authoritative (ADR-030 §12).
Every governance write on section-less memory now refuses, and
``mneme decision-index migrate`` is the only transition. That is intended.
What must never happen is a repository whose existing governance pipeline
stops working with no clear way forward.

This was found on mnemehq-site, Mneme's own reference deployment: its CI ran
``mneme adr import ... --apply --update-existing`` on memory written by 0.9.x,
the import refused, and the suggested migration then refused because one
memory-only decision carried a free-text ``source`` note. The refusal named
the field but not a route that keeps the provenance.

The fixture below reproduces that repository's shape. The contract tested:

1. Section-less memory written by earlier releases stays readable.
2. Writers refuse it with a diagnostic that leads to the migration preview,
   and write nothing.
3. A lossy legacy row is refused with a diagnostic that names the record,
   the field, and a lossless route; still no write (ADR-030 §12: no force,
   repair, or loss-acknowledgment option).
4. Following that route migrates cleanly, and repeated imports are
   byte-identical.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mneme.adr_compiler import adrs_to_decisions
from mneme.adr_parser import parse_adr_file
from mneme.cli import main

ADR_001 = """\
---
id: ADR-001
title: "The website repository dogfoods Mneme governance"
status: accepted
priority: foundational
date: 2026-08-20
scope: repo.website_governance
---

# ADR-001: The website repository dogfoods Mneme governance

## Decision

Site changes are checked against tracked repository memory.

## Constraints

- REQUIRE_PATH: site/**
"""

FREE_TEXT_SOURCE = "Visual audit 2026-08-24; integrations hub redesign commit d8b92f02"

MEMORY_ONLY_DECISION = {
    "id": "ADR-003",
    "decision": "Status labels are monochrome; colour is reserved for semantic verdicts",
    "rationale": "# ADR-003: Status labels are monochrome\n\nOne muted style for status tags.\n",
    "scope": ["site/*"],
    "constraints": [
        "Status/support-level tags: DM Mono uppercase, var(--muted)",
        "Non-shipped differentiation via card opacity only",
    ],
    "anti_patterns": [],
    "created_at": "2026-08-24",
    "updated_at": "2026-08-24",
    "source": FREE_TEXT_SOURCE,
}

LEGACY_ITEM = {
    "id": "rule-intent-based-branch-names",
    "type": "rule",
    "title": "Branch names describe the work, not the execution model",
    "content": "Use intent-based branch names such as site/ or fix/.",
    "tags": ["git"],
    "priority": "high",
}


def _adr_row(adr_path: Path) -> dict:
    """The decisions[] row a 0.9.x `mneme adr import` wrote for one ADR file."""
    adr = parse_adr_file(adr_path)
    decision = adrs_to_decisions([adr])[0]
    return {
        "id": decision.id,
        "decision": decision.decision,
        "rationale": decision.rationale,
        "scope": decision.scope,
        "constraints": decision.constraints,
        "anti_patterns": [],
        "rules": [],
        "created_at": decision.created_at,
        "updated_at": decision.updated_at,
        "source": {
            "type": "adr",
            "path": f"../docs/adr/{adr_path.name}",
            "sha256": hashlib.sha256(adr_path.read_bytes()).hexdigest(),
        },
    }


@pytest.fixture
def pre_d1_repo(tmp_path: Path) -> Path:
    """A repository as 0.9.x left it: section-less memory, ADR + memory-only rows."""
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    adr_path = adr_dir / "ADR-001-site-repository-governance.md"
    adr_path.write_text(ADR_001, encoding="utf-8", newline="\n")
    (tmp_path / ".mneme").mkdir()
    memory = tmp_path / ".mneme" / "project_memory.json"
    memory.write_text(json.dumps({
        "meta": {"name": "pre-d1-site", "description": "0.9.x repository memory"},
        "items": [LEGACY_ITEM],
        "examples": [],
        "decisions": [_adr_row(adr_path), dict(MEMORY_ONLY_DECISION)],
    }, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return tmp_path


def _memory(repo: Path) -> Path:
    return repo / ".mneme" / "project_memory.json"


def _adr_dir(repo: Path) -> Path:
    return repo / "docs" / "adr"


def _ci_import(repo: Path) -> int:
    """The exact command mnemehq-site's governance workflow runs."""
    return main([
        "adr", "import", str(_adr_dir(repo)),
        "--memory", str(_memory(repo)),
        "--apply", "--update-existing",
    ])


# ── 1. Readable ──────────────────────────────────────────────────────────────


def test_pre_d1_memory_stays_readable(pre_d1_repo, tmp_path, capsys):
    memory = _memory(pre_d1_repo)
    before = memory.read_bytes()

    assert main(["list_decisions", "--memory", str(memory)]) == 0
    listed = capsys.readouterr().out
    assert "ADR-001" in listed and "ADR-003" in listed

    assert main([
        "test_query", "--memory", str(memory),
        "--query", "status label colours", "--top", "3",
    ]) == 0
    assert "[ADR-003]" in capsys.readouterr().out

    changed = tmp_path / "changed-paths.txt"
    changed.write_text("site/index.html\n", encoding="utf-8")
    assert main([
        "check", "--memory", str(memory), "--input", str(changed),
        "--query", "site publishing governance", "--mode", "strict",
        "--adr-dir", str(_adr_dir(pre_d1_repo)),
    ]) == 0
    assert "Traceback" not in capsys.readouterr().err

    assert memory.read_bytes() == before


# ── 2. Writers refuse with a route to the migration ──────────────────────────


def test_ci_import_on_pre_d1_memory_points_to_migration_preview(pre_d1_repo, capsys):
    memory = _memory(pre_d1_repo)
    before = memory.read_bytes()

    assert _ci_import(pre_d1_repo) == 2

    err = capsys.readouterr().err
    assert "no authoritative decision_index section" in err
    assert err.index(f"mneme decision-index migrate --memory {memory}\n") < err.index(
        f"mneme decision-index migrate --memory {memory} --apply"
    )
    assert "Traceback" not in err
    assert memory.read_bytes() == before


# ── 3. Lossy legacy state: refused, actionable, nothing written ──────────────


@pytest.mark.parametrize("apply", [False, True], ids=["preview", "apply"])
def test_free_text_source_refusal_names_a_lossless_route(pre_d1_repo, capsys, apply):
    memory = _memory(pre_d1_repo)
    before = memory.read_bytes()

    args = ["decision-index", "migrate", "--memory", str(memory)]
    assert main(args + (["--apply"] if apply else [])) == 2

    err = capsys.readouterr().err
    # Names the exact record and field (ADR-030 §12).
    assert "migration must be lossless" in err
    assert "decision 'ADR-003' source is not an object" in err
    # Names a route that keeps the provenance, rather than a dead end.
    assert "ADR file" in err
    assert "mneme adr import" in err
    # Never offers to discard metadata or bypass the check.
    assert "--force" not in err
    assert "Traceback" not in err
    assert memory.read_bytes() == before


# ── 4. Following the route migrates, and import is idempotent ────────────────


def test_documented_route_migrates_and_import_is_idempotent(pre_d1_repo, capsys):
    memory = _memory(pre_d1_repo)

    # Move the memory-only decision into an ADR file, keeping its provenance,
    # under an id that does not collide with other records.
    (_adr_dir(pre_d1_repo) / "ADR-009-monochrome-status-labels.md").write_text(
        "---\n"
        "id: ADR-009\n"
        f'title: "{MEMORY_ONLY_DECISION["decision"]}"\n'
        "status: accepted\n"
        "priority: normal\n"
        "date: 2026-08-24\n"
        "scope: site.status_labels\n"
        "---\n\n"
        "# ADR-009: Status labels are monochrome\n\n"
        "## Provenance\n\n"
        "Moved from project-memory entry ADR-003. Original source note:\n"
        f'"{FREE_TEXT_SOURCE}".\n\n'
        "One muted style for status tags.\n",
        encoding="utf-8", newline="\n",
    )
    raw = json.loads(memory.read_text(encoding="utf-8"))
    raw["decisions"] = [d for d in raw["decisions"] if d["id"] != "ADR-003"]
    memory.write_text(json.dumps(raw, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    assert main(["decision-index", "migrate", "--memory", str(memory), "--apply"]) == 0
    migrated = json.loads(memory.read_text(encoding="utf-8"))
    adr_001_version = next(
        r["active_version_id"] for r in migrated["decision_index"]["decisions"]
        if r["decision_id"] == "ADR-001"
    )

    assert _ci_import(pre_d1_repo) == 0
    first = memory.read_bytes()
    assert _ci_import(pre_d1_repo) == 0
    assert memory.read_bytes() == first
    capsys.readouterr()

    index = json.loads(first)["decision_index"]
    records = {r["decision_id"]: r for r in index["decisions"]}
    assert set(records) == {"ADR-001", "ADR-009", "rule-intent-based-branch-names"}
    assert all(r["lifecycle_status"] == "active" for r in records.values())
    assert records["ADR-001"]["active_version_id"] == adr_001_version
    adr_009 = next(v for v in index["versions"] if v["decision_id"] == "ADR-009")
    assert FREE_TEXT_SOURCE in adr_009["rationale"]
    assert adr_009["created_at"] == "2026-08-24"
