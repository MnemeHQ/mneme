# tests/test_cli_adr_import.py
"""CLI integration tests for `mneme adr import`."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mneme.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def _seed_empty_memory(path: Path) -> None:
    path.write_text(json.dumps({
        "meta": {"name": "test", "description": "test", "version": "1.0.0", "owner": "test", "created": "2026-01-01"},
        "items": [], "examples": [], "decisions": [],
    }), encoding="utf-8")


def test_adr_import_dry_run_prints_preview_and_does_not_write(tmp_path, capsys):
    target = tmp_path / "project_memory.json"
    _seed_empty_memory(target)
    before = target.read_text(encoding="utf-8")

    rc = main([
        "adr", "import",
        str(FIXTURES / "adrs_import_basic"),
        "--memory", str(target),
        "--dry-run",
    ])

    assert rc == 1
    out = capsys.readouterr().out
    assert "ADR import preview" in out
    assert "ADR-101" in out
    assert "no mongodb" in out
    # Target file is byte-for-byte unchanged
    assert target.read_text(encoding="utf-8") == before


def test_adr_import_default_is_dry_run(tmp_path):
    """Without --apply or --dry-run, behavior must match --dry-run."""
    target = tmp_path / "project_memory.json"
    _seed_empty_memory(target)
    before = target.read_text(encoding="utf-8")

    rc = main([
        "adr", "import",
        str(FIXTURES / "adrs_import_basic"),
        "--memory", str(target),
    ])

    assert rc == 1
    assert target.read_text(encoding="utf-8") == before


def test_adr_import_apply_writes_decisions(tmp_path):
    target = tmp_path / "project_memory.json"
    _seed_empty_memory(target)

    rc = main([
        "adr", "import",
        str(FIXTURES / "adrs_import_basic"),
        "--memory", str(target),
        "--apply",
    ])

    assert rc == 0
    persisted = json.loads(target.read_text(encoding="utf-8"))
    ids = [d["id"] for d in persisted["decisions"]]
    assert ids == ["ADR-101", "ADR-102"]


def test_adr_import_apply_refuses_collision_without_update_existing(tmp_path, capsys):
    target = tmp_path / "project_memory.json"
    target.write_text(
        (FIXTURES / "memory_for_import_collision.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    before = target.read_text(encoding="utf-8")

    rc = main([
        "adr", "import",
        str(FIXTURES / "adrs_import_basic"),
        "--memory", str(target),
        "--apply",
    ])

    assert rc == 2
    err = capsys.readouterr().err
    assert "ADR-101" in err
    assert "--update-existing" in err
    # Target is unchanged
    assert target.read_text(encoding="utf-8") == before


def test_adr_import_apply_with_update_existing_overwrites(tmp_path):
    target = tmp_path / "project_memory.json"
    target.write_text(
        (FIXTURES / "memory_for_import_collision.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    rc = main([
        "adr", "import",
        str(FIXTURES / "adrs_import_basic"),
        "--memory", str(target),
        "--apply",
        "--update-existing",
    ])

    assert rc == 0
    persisted = json.loads(target.read_text(encoding="utf-8"))
    by_id = {d["id"]: d for d in persisted["decisions"]}
    assert by_id["ADR-101"]["decision"] == "No MongoDB"


def test_adr_import_apply_refuses_active_active_without_approve(tmp_path, capsys):
    target = tmp_path / "project_memory.json"
    _seed_empty_memory(target)

    rc = main([
        "adr", "import",
        str(FIXTURES / "adrs_import_with_conflicts"),
        "--memory", str(target),
        "--apply",
    ])

    assert rc == 2
    err = capsys.readouterr().err
    assert "active-active" in err.lower() or "Active-active" in err
    assert "--approve-conflicts" in err


def test_adr_import_dry_run_returns_nonzero_on_diagnostics(tmp_path):
    """Dry-run with diagnostics still surfaces a nonzero exit (signals to CI)."""
    target = tmp_path / "project_memory.json"
    _seed_empty_memory(target)

    rc = main([
        "adr", "import",
        str(FIXTURES / "adrs_import_with_conflicts"),
        "--memory", str(target),
        "--dry-run",
    ])
    # 1 = warn (matches existing `mneme check --mode strict` warn convention)
    assert rc == 1


def test_adr_import_apply_with_approve_conflicts_imports_clean_scopes(tmp_path, capsys):
    adr_dir = tmp_path / "adrs"
    adr_dir.mkdir()
    for adr_id, scope in [("ADR-501", "api"), ("ADR-502", "api"), ("ADR-510", "storage")]:
        (adr_dir / f"{adr_id}.md").write_text(
            f"---\nid: {adr_id}\ntitle: {adr_id} title\nstatus: accepted\n"
            f"priority: normal\ndate: 2026-04-15\nscope: {scope}\n---\n\n"
            "## Constraints\n\n- FORBID_LITERAL: mongodb\n",
            encoding="utf-8",
        )
    target = tmp_path / "project_memory.json"
    _seed_empty_memory(target)

    rc = main([
        "adr", "import", str(adr_dir),
        "--memory", str(target),
        "--apply", "--approve-conflicts",
    ])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Wrote 1 decisions" in out
    assert "Skipped conflicting scope 'api': ADR-501, ADR-502" in out
    persisted = json.loads(target.read_text(encoding="utf-8"))
    assert [d["id"] for d in persisted["decisions"]] == ["ADR-510"]


# ── ADR-030 §5 / G11: late retry through the CLI (--expected-predecessor) ────
#
# An unpinned `--apply --update-existing` is a new authority operation whose
# predecessor is the active version when it runs. A late retry of an earlier
# operation carries that operation's predecessor explicitly.


def _write_g11_adr(adr_dir: Path, literal: str, *, priority_note: str = "") -> None:
    (adr_dir / "ADR-520.md").write_text(
        "---\n"
        "id: ADR-520\n"
        "title: ADR-520 title\n"
        "status: accepted\n"
        f"priority: normal{priority_note}\n"
        "date: 2026-04-15\n"
        'scope: "storage"\n'
        "---\n\n"
        f"## Constraints\n\n- FORBID_LITERAL: {literal}\n",
        encoding="utf-8",
    )


def _g11_apply(adr_dir: Path, target: Path, *extra: str) -> int:
    return main([
        "adr", "import", str(adr_dir),
        "--memory", str(target),
        "--apply", "--update-existing",
        *extra,
    ])


def _g11_versions(target: Path) -> tuple[list[str], str]:
    section = json.loads(target.read_text(encoding="utf-8"))["decision_index"]
    versions = [
        row["version_id"] for row in section["versions"]
        if row["decision_id"] == "ADR-520"
    ]
    (logical,) = [
        row for row in section["decisions"] if row["decision_id"] == "ADR-520"
    ]
    return versions, logical["active_version_id"]


@pytest.fixture
def g11_history(tmp_path, capsys):
    """A1 -> B -> A2 -> C through the CLI; returns ids and paths."""
    adr_dir = tmp_path / "adrs"
    adr_dir.mkdir()
    target = tmp_path / "project_memory.json"
    _seed_empty_memory(target)

    _write_g11_adr(adr_dir, "alpha")
    assert main([
        "adr", "import", str(adr_dir), "--memory", str(target), "--apply",
    ]) == 0
    a1 = _g11_versions(target)[1]
    _write_g11_adr(adr_dir, "beta")
    assert _g11_apply(adr_dir, target) == 0
    b = _g11_versions(target)[1]
    _write_g11_adr(adr_dir, "alpha")
    assert _g11_apply(adr_dir, target) == 0
    a2 = _g11_versions(target)[1]
    _write_g11_adr(adr_dir, "gamma")
    assert _g11_apply(adr_dir, target) == 0
    c = _g11_versions(target)[1]
    assert len({a1, b, a2, c}) == 4
    capsys.readouterr()
    return {"adr_dir": adr_dir, "target": target, "a1": a1, "b": b, "a2": a2, "c": c}


def test_cli_pinned_late_retry_reuses_original_occurrence(g11_history):
    h = g11_history
    _write_g11_adr(h["adr_dir"], "alpha")
    before = h["target"].read_bytes()

    code = _g11_apply(
        h["adr_dir"], h["target"], "--expected-predecessor", f"ADR-520={h['b']}"
    )

    assert code == 0
    assert h["target"].read_bytes() == before
    versions, active = _g11_versions(h["target"])
    assert versions == [h["a1"], h["b"], h["a2"], h["c"]]
    assert active == h["c"]


def test_cli_unpinned_same_content_revert_creates_new_occurrence(g11_history):
    h = g11_history
    _write_g11_adr(h["adr_dir"], "alpha")

    assert _g11_apply(h["adr_dir"], h["target"]) == 0

    versions, active = _g11_versions(h["target"])
    assert versions[:4] == [h["a1"], h["b"], h["a2"], h["c"]]
    assert len(versions) == 5
    assert active == versions[4]
    assert active not in {h["a1"], h["a2"]}
    section = json.loads(h["target"].read_text(encoding="utf-8"))["decision_index"]
    (a3,) = [row for row in section["versions"] if row["version_id"] == active]
    assert a3["supersedes_version_id"] == h["c"]


def test_cli_stale_pinned_predecessor_with_new_content_fails_closed(
    g11_history, capsys
):
    h = g11_history
    _write_g11_adr(h["adr_dir"], "delta")
    before = h["target"].read_bytes()

    code = _g11_apply(
        h["adr_dir"], h["target"], "--expected-predecessor", f"ADR-520={h['b']}"
    )

    assert code == 2
    assert "stale version evolution" in capsys.readouterr().err
    assert h["target"].read_bytes() == before


def test_cli_pin_equal_to_active_with_unchanged_adr_is_noop(g11_history):
    h = g11_history
    before = h["target"].read_bytes()

    code = _g11_apply(
        h["adr_dir"], h["target"], "--expected-predecessor", f"ADR-520={h['c']}"
    )

    assert code == 0
    assert h["target"].read_bytes() == before


def test_cli_dry_run_shows_current_predecessor(g11_history, capsys):
    h = g11_history
    code = main([
        "adr", "import", str(h["adr_dir"]), "--memory", str(h["target"]),
        "--dry-run",
    ])
    out = capsys.readouterr().out
    assert code == 1  # same-id collision diagnostic
    assert f"current predecessor: {h['c']}" in out


@pytest.mark.parametrize(
    "extra",
    [
        pytest.param(["--expected-predecessor", "ADR-520"], id="malformed"),
        pytest.param(["--expected-predecessor", "ADR-520=dver-xyz"], id="bad-version"),
        pytest.param(
            ["--expected-predecessor", "ADR-520={b}",
             "--expected-predecessor", "ADR-520={c}"],
            id="duplicate",
        ),
        pytest.param(["--expected-predecessor", "ADR-999={b}"], id="unknown-adr"),
        pytest.param(
            ["--expected-predecessor", "ADR-520=dver-" + "0" * 32],
            id="nonexistent-version",
        ),
    ],
)
def test_cli_expected_predecessor_input_errors_fail_closed(
    g11_history, capsys, extra
):
    h = g11_history
    _write_g11_adr(h["adr_dir"], "alpha")
    before = h["target"].read_bytes()
    args = [arg.format(b=h["b"], c=h["c"]) for arg in extra]

    code = _g11_apply(h["adr_dir"], h["target"], *args)

    assert code == 2
    assert "ERROR" in capsys.readouterr().err
    assert h["target"].read_bytes() == before


def test_cli_expected_predecessor_requires_update_existing(g11_history, capsys):
    h = g11_history
    before = h["target"].read_bytes()

    code = main([
        "adr", "import", str(h["adr_dir"]), "--memory", str(h["target"]),
        "--apply", "--expected-predecessor", f"ADR-520={h['b']}",
    ])

    assert code == 2
    assert "--update-existing" in capsys.readouterr().err
    assert h["target"].read_bytes() == before


def test_cli_expected_predecessor_rejects_new_decision(tmp_path, capsys):
    adr_dir = tmp_path / "adrs"
    adr_dir.mkdir()
    target = tmp_path / "project_memory.json"
    _seed_empty_memory(target)
    _write_g11_adr(adr_dir, "alpha")
    before = target.read_bytes()

    code = _g11_apply(
        adr_dir, target, "--expected-predecessor", "ADR-520=dver-" + "0" * 32
    )

    assert code == 2
    assert "not yet canonical" in capsys.readouterr().err
    assert target.read_bytes() == before


@pytest.mark.parametrize("pinned", [True, False], ids=["pinned-active", "unpinned"])
def test_cli_source_bytes_change_is_a_new_occurrence_even_with_equal_content(
    g11_history, pinned
):
    """The no-op needs content AND source revision to match the active one.

    A frontmatter YAML comment changes the ADR bytes (so source_revision and
    the occurrence source identity) but not the parsed decision content.
    """
    h = g11_history
    _write_g11_adr(h["adr_dir"], "gamma", priority_note="  # reviewed")
    extra = ["--expected-predecessor", f"ADR-520={h['c']}"] if pinned else []

    assert _g11_apply(h["adr_dir"], h["target"], *extra) == 0

    versions, active = _g11_versions(h["target"])
    assert len(versions) == 5
    section = json.loads(h["target"].read_text(encoding="utf-8"))["decision_index"]
    by_id = {row["version_id"]: row for row in section["versions"]}
    new, c = by_id[active], by_id[h["c"]]
    assert new["supersedes_version_id"] == h["c"]
    assert new["content_digest"] == c["content_digest"]
    assert (
        new["source_evidence"][0]["source_revision"]
        != c["source_evidence"][0]["source_revision"]
    )
