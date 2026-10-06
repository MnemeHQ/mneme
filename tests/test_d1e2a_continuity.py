"""D1E2a: ADR-030 §9a protection continuity across ADR version evolution.

A ``protection``/``legacy_unknown`` binding never lapses between version
occurrences of a continuing decision without explicit authority:

- the new source re-derives it: one binding keeps the stronger authority,
  or becomes ``version`` under explicit release;
- the new source drops it: explicit preserve (mechanically revalidated)
  carries it, explicit release omits it, neither fails closed.

Bindings get their authority by direct fixture editing here because the
canonical ``protect activate`` writer is D1E2b.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mneme.adr_import import (
    apply_import,
    compile_for_import,
    detect_continuity_effects,
)
from mneme.cli import _preservation_validator, main
from mneme.memory_store import MemoryStore
from tests.canonical_fixtures import migrate_memory_fixture

ADR_ID = "ADR-800"


def _write_adr(adr_dir: Path, *literals: str, adr_id: str = ADR_ID,
               supersedes: tuple[str, ...] = (), path_rule: str = "") -> None:
    supersedes_block = "".join(f"  - {s}\n" for s in supersedes)
    constraints = "".join(f"- FORBID_LITERAL: {lit}\n" for lit in literals)
    (adr_dir / f"{adr_id}.md").write_text(
        "---\n"
        f"id: {adr_id}\n"
        f"title: {adr_id} title\n"
        "status: accepted\n"
        "priority: normal\n"
        "date: 2026-04-15\n"
        f"scope: \"{adr_id.lower().replace('-', '_')}\"\n"
        + (f"supersedes:\n{supersedes_block}" if supersedes else "")
        + "---\n\n"
        f"## Constraints\n\n{constraints}{path_rule}",
        encoding="utf-8",
    )


@pytest.fixture
def env(tmp_path):
    adr_dir = tmp_path / "adrs"
    adr_dir.mkdir()
    memory = tmp_path / "project_memory.json"
    memory.write_text(json.dumps({
        "meta": {"name": "d1e2a", "description": "continuity"},
        "items": [], "examples": [], "decisions": [],
    }) + "\n", encoding="utf-8")
    migrate_memory_fixture(memory)
    return adr_dir, memory


def _section(memory: Path) -> dict:
    return json.loads(memory.read_text(encoding="utf-8"))["decision_index"]


def _active_rules(memory: Path, decision_id: str = ADR_ID) -> list[tuple]:
    section = _section(memory)
    (logical,) = [r for r in section["decisions"] if r["decision_id"] == decision_id]
    return sorted(
        (r["sequence"], r["rule_payload"]["value"], r.get("binding_authority"),
         r["rule_id"])
        for r in section["rules"]
        if r["decision_version_id"] == logical["active_version_id"]
    )


def _set_authority(memory: Path, authorities: dict[str, str | None]) -> dict[str, str]:
    """Set authority by literal on the active version; return literal->rule_id."""
    raw = json.loads(memory.read_text(encoding="utf-8"))
    section = raw["decision_index"]
    active = {r["active_version_id"] for r in section["decisions"]}
    ids: dict[str, str] = {}
    for row in section["rules"]:
        literal = row["rule_payload"]["value"]
        if row["decision_version_id"] in active and literal in authorities:
            ids[literal] = row["rule_id"]
            if authorities[literal] is None:
                row.pop("binding_authority", None)  # predates the field
            else:
                row["binding_authority"] = authorities[literal]
    memory.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    return ids


def _import(adr_dir: Path, memory: Path, **kwargs):
    return apply_import(
        compile_for_import(adr_dir), memory, allow_update=True,
        preservation_validator=_preservation_validator(memory), **kwargs,
    )


def _protected(env, *authorities: tuple[str, str | None]):
    adr_dir, memory = env
    _write_adr(adr_dir, *[lit for lit, _ in authorities])
    apply_import(compile_for_import(adr_dir), memory)
    return _set_authority(memory, dict(authorities))


# ── Silent loss is refused (release blocker) ────────────────────────────────


@pytest.mark.parametrize("authority", ["protection", "legacy_unknown", None])
def test_unrelated_edit_dropping_continuity_binding_fails_closed(env, authority):
    adr_dir, memory = env
    ids = _protected(env, ("alpha_client", authority))
    _write_adr(adr_dir, "gamma_client")  # an edit that no longer derives alpha
    before = memory.read_bytes()

    with pytest.raises(RuntimeError, match="would drop protection/legacy_unknown"):
        _import(adr_dir, memory)

    assert memory.read_bytes() == before
    assert ids["alpha_client"] in str(
        detect_continuity_effects(
            compile_for_import(adr_dir), json.loads(before.decode("utf-8"))
        )[0].message
    )


def test_version_bindings_still_lapse_without_ceremony(env):
    adr_dir, memory = env
    _write_adr(adr_dir, "alpha_client")
    apply_import(compile_for_import(adr_dir), memory)
    _write_adr(adr_dir, "gamma_client")

    _import(adr_dir, memory)

    assert [r[1:3] for r in _active_rules(memory)] == [("gamma_client", "version")]


# ── Source still derives R ──────────────────────────────────────────────────


@pytest.mark.parametrize("authority, expected", [
    ("protection", "protection"),
    ("legacy_unknown", "legacy_unknown"),
    (None, "legacy_unknown"),
])
def test_rederived_rule_keeps_stronger_authority(env, authority, expected):
    adr_dir, memory = env
    _protected(env, ("alpha_client", authority))
    _write_adr(adr_dir, "alpha_client", "gamma_client")

    _import(adr_dir, memory)

    assert [r[1:3] for r in _active_rules(memory)] == [
        ("alpha_client", expected), ("gamma_client", "version"),
    ]


def test_release_of_rederived_rule_downgrades_to_version(env):
    adr_dir, memory = env
    ids = _protected(env, ("alpha_client", "protection"))
    _write_adr(adr_dir, "alpha_client", "gamma_client")

    _import(adr_dir, memory, release_protection=[ids["alpha_client"]])

    assert [r[1:3] for r in _active_rules(memory)] == [
        ("alpha_client", "version"), ("gamma_client", "version"),
    ]


# ── Source drops R ──────────────────────────────────────────────────────────


def test_preserve_and_release_with_ordering(env):
    adr_dir, memory = env
    ids = _protected(
        env,
        ("alpha_client", "protection"),
        ("beta_client", "legacy_unknown"),
        ("delta_client", None),
    )
    _write_adr(adr_dir, "gamma_client")

    _import(
        adr_dir, memory,
        preserve_protection=[ids["delta_client"], ids["alpha_client"]],
        release_protection=[ids["beta_client"]],
    )

    rules = _active_rules(memory)
    assert [r[:3] for r in rules] == [
        (0, "gamma_client", "version"),
        (1, "alpha_client", "protection"),        # previous relative order kept
        (2, "delta_client", "legacy_unknown"),    # absent field -> legacy_unknown
    ]
    assert rules[1][3] == ids["alpha_client"]
    store = MemoryStore(memory)
    store.load()
    (decision,) = store.decisions()
    assert [rule.value for rule in decision.rules] == [
        "gamma_client", "alpha_client", "delta_client",
    ]


def test_preserve_failing_revalidation_fails_closed(env):
    adr_dir, memory = env
    ids = _protected(env, ("alpha_client", "protection"))
    _write_adr(adr_dir, "gamma_client")
    before = memory.read_bytes()

    def reject(decision, rule):
        raise ValueError("deterministic protection validation failed: x")

    with pytest.raises(RuntimeError, match="failed revalidation"):
        apply_import(
            compile_for_import(adr_dir), memory, allow_update=True,
            preserve_protection=[ids["alpha_client"]],
            preservation_validator=reject,
        )
    assert memory.read_bytes() == before


def test_scoped_binding_cannot_be_preserved_only_released(env):
    adr_dir, memory = env
    _write_adr(
        adr_dir, "alpha_client",
        path_rule=(
            "- FORBID_LITERAL:\n"
            "    value: scoped_client\n"
            "    include_paths:\n"
            "      - src/**\n"
        ),
    )
    apply_import(compile_for_import(adr_dir), memory)
    (scoped,) = [r for r in _section(memory)["rules"] if r["applicability"]]
    assert scoped["applicability"] == {"include_paths": ["src/**"]}
    ids = _set_authority(memory, {"scoped_client": "protection"})
    _write_adr(adr_dir, "alpha_client")
    before = memory.read_bytes()

    with pytest.raises(RuntimeError, match="supported only for a global FORBID_LITERAL"):
        _import(adr_dir, memory, preserve_protection=[ids["scoped_client"]])
    assert memory.read_bytes() == before

    _import(adr_dir, memory, release_protection=[ids["scoped_client"]])
    assert [r[1] for r in _active_rules(memory)] == ["alpha_client"]


# ── Input errors ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("case, match", [
    ("both", "both preserved and released"),
    ("unknown", "not protection or legacy_unknown bindings"),
    ("version_authority", "not protection or legacy_unknown bindings"),
    ("preserve_rederived", "preserving them is meaningless"),
    ("other_decision", "does not name a rule of an incoming"),
])
def test_continuity_input_errors_refuse_before_write(env, case, match):
    adr_dir, memory = env
    ids = _protected(env, ("alpha_client", "protection"), ("beta_client", "version"))
    alpha, beta = ids["alpha_client"], ids["beta_client"]
    if case == "preserve_rederived":
        _write_adr(adr_dir, "alpha_client", "gamma_client")
    else:
        _write_adr(adr_dir, "gamma_client")
    requests = {
        "both": {"preserve_protection": [alpha], "release_protection": [alpha]},
        "unknown": {"preserve_protection": [f"{ADR_ID}:FORBID_LITERAL:{'0' * 32}"]},
        "version_authority": {"release_protection": [beta, alpha]},
        "preserve_rederived": {"preserve_protection": [alpha]},
        "other_decision": {"release_protection": ["ADR-999:FORBID_LITERAL:" + "0" * 32]},
    }[case]
    before = memory.read_bytes()

    with pytest.raises(RuntimeError, match=match):
        _import(adr_dir, memory, **requests)
    assert memory.read_bytes() == before


def test_requests_without_update_existing_refuse(env):
    adr_dir, memory = env
    ids = _protected(env, ("alpha_client", "protection"))
    _write_adr(adr_dir, "gamma_client")

    with pytest.raises(RuntimeError, match="pass --update-existing"):
        apply_import(
            compile_for_import(adr_dir), memory,
            release_protection=[ids["alpha_client"]],
        )


# ── Retry consistency ───────────────────────────────────────────────────────


def test_retry_with_same_requests_is_noop_and_different_requests_refuse(env):
    adr_dir, memory = env
    ids = _protected(
        env, ("alpha_client", "protection"), ("beta_client", "legacy_unknown"),
    )
    _write_adr(adr_dir, "gamma_client")
    requests = {
        "preserve_protection": [ids["alpha_client"]],
        "release_protection": [ids["beta_client"]],
    }
    _import(adr_dir, memory, **requests)
    applied = memory.read_bytes()

    _import(adr_dir, memory, **requests)
    assert memory.read_bytes() == applied

    with pytest.raises(RuntimeError, match="rule bindings differ"):
        _import(
            adr_dir, memory,
            release_protection=[ids["alpha_client"], ids["beta_client"]],
        )
    assert memory.read_bytes() == applied


def test_requests_for_a_decision_that_never_evolved_refuse(env):
    adr_dir, memory = env
    ids = _protected(env, ("alpha_client", "protection"))
    before = memory.read_bytes()

    with pytest.raises(RuntimeError, match="not evolving"):
        _import(adr_dir, memory, release_protection=[ids["alpha_client"]])
    assert memory.read_bytes() == before


# ── Supersession: retirement authority, consequence previewed ───────────────


def test_supersession_previews_enforcement_leaving_layer1_without_release(env):
    adr_dir, memory = env
    ids = _protected(env, ("alpha_client", "protection"))
    _write_adr(adr_dir, "omega_client", adr_id="ADR-801", supersedes=(ADR_ID,))
    report = compile_for_import(adr_dir)
    raw = json.loads(memory.read_text(encoding="utf-8"))

    effects = detect_continuity_effects(report, raw)

    (effect,) = [e for e in effects if e.kind == "supersession_enforcement"]
    assert effect.adr_id == ADR_ID
    assert ids["alpha_client"] in effect.message
    assert "ADR-801" in effect.message

    apply_import(report, memory, allow_update=True)  # no per-rule release
    section = _section(memory)
    lifecycle = {r["decision_id"]: r["lifecycle_status"] for r in section["decisions"]}
    assert lifecycle[ADR_ID] == "superseded"
    store = MemoryStore(memory)
    store.load()
    assert [d.id for d in store.decisions()] == ["ADR-801"]


def test_cli_supersession_only_retirement_is_loud_but_writes_nothing(env, capsys):
    """Authorized retirement of protected rules: visible preview, dry-run exit 1.

    The superseded ADR is not active (no collision) and the superseding ADR
    carries a typed rule (no retrieval-only warning), so the supersession
    enforcement effect is the only diagnostic driving the exit code.
    """
    adr_dir, memory = env
    ids = _protected(env, ("alpha_client", "protection"))
    _write_adr(adr_dir, "omega_client", adr_id="ADR-801", supersedes=(ADR_ID,))
    before = memory.read_bytes()

    code = main(["adr", "import", str(adr_dir), "--memory", str(memory)])

    out = capsys.readouterr().out
    assert code == 1
    assert "Supersession enforcement effects:" in out
    assert ids["alpha_client"] in out
    assert "Protection continuity obligations" not in out
    assert "Conflicts vs existing memory" not in out
    assert "Retrieval-only ADR warnings" not in out
    assert memory.read_bytes() == before


# ── CLI surface ─────────────────────────────────────────────────────────────


def test_cli_preview_lists_obligations_and_dry_run_flags_them(env, capsys):
    adr_dir, memory = env
    ids = _protected(env, ("alpha_client", "protection"))
    _write_adr(adr_dir, "gamma_client")

    code = main(["adr", "import", str(adr_dir), "--memory", str(memory)])

    out = capsys.readouterr().out
    assert code == 1
    assert "Protection continuity obligations (ADR-030 §9a):" in out
    assert ids["alpha_client"] in out


def test_cli_preserve_and_release_round_trip(env, capsys):
    adr_dir, memory = env
    ids = _protected(
        env, ("alpha_client", "protection"), ("beta_client", "legacy_unknown"),
    )
    _write_adr(adr_dir, "gamma_client")

    code = main([
        "adr", "import", str(adr_dir), "--memory", str(memory),
        "--apply", "--update-existing",
        "--preserve-protection", ids["alpha_client"],
        "--release-protection", ids["beta_client"],
    ])

    assert code == 0
    assert [r[1:3] for r in _active_rules(memory)] == [
        ("gamma_client", "version"), ("alpha_client", "protection"),
    ]


@pytest.mark.parametrize("extra, match", [
    (["--preserve-protection", "R", "--preserve-protection", "R"], "more than once"),
    (["--preserve-protection", "R", "--release-protection", "R"], "named by both"),
])
def test_cli_flag_errors(env, capsys, extra, match):
    adr_dir, memory = env
    _write_adr(adr_dir, "gamma_client")
    before = memory.read_bytes()

    code = main([
        "adr", "import", str(adr_dir), "--memory", str(memory),
        "--apply", "--update-existing", *extra,
    ])

    assert code == 2
    assert match in capsys.readouterr().err
    assert memory.read_bytes() == before


def test_cli_flags_require_apply_and_update_existing(env, capsys):
    adr_dir, memory = env
    _write_adr(adr_dir, "gamma_client")

    code = main([
        "adr", "import", str(adr_dir), "--memory", str(memory),
        "--release-protection", "R",
    ])

    assert code == 2
    assert "valid only with --apply --update-existing" in capsys.readouterr().err
