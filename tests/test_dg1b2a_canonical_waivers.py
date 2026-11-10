"""DG1B2a: canonical waivers (ADR-031 §12; charter #784; freeze amendment #785).

Pins the charter §4 acceptance evidence (items 1-13 and 9a):

- a canonical waiver is persisted only under ``mneme.decision-index/v2`` with
  the declared ``decision_waivers`` feature, in a top-level ``waivers`` array,
  with a frozen ``wvr-`` identity;
- the resolver reports cause ``waived`` only for an active waiver bound to the
  decision's active version, with supplied matching labels and (if
  time-bound) a supplied, parseable ``as_of`` inside the window; every other
  case fails closed to the decision, which stays effective;
- only the explicit CLI authority operations write waivers;
- no authoritative surface changes: projection, ``mneme check``, Audit,
  ``protect list`` and the C3a consumers behave exactly as without waivers.

The CNCF picolibc/Hyperlight licence exception (evidence packet #783) is
modelled with an explicit Mneme decision and version; its policy SHA is
provenance only. The time-bound case is synthetic: no real time-bound case
was found.
"""
from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path

import pytest

import mneme.decision_index_persistence as persistence
from mneme.cli import main
from mneme.decision_governance import (
    CAUSE_LIFECYCLE_SUPERSEDED,
    CAUSE_NOT_APPLICABLE,
    CAUSE_WAIVED,
    CHANGE_BECAME_INEFFECTIVE,
    CHANGE_CAUSE,
    FINDING_DANGLING_WAIVER_TARGET,
    FINDING_SUPERSESSION_LIFECYCLE_CONFLICT,
    FINDING_WAIVER_VERSION_MISMATCH,
    GOVERNANCE_SEMANTICS_VERSION,
    GovernanceContext,
    compare_resolutions,
    governed_runtime_decisions,
    resolve_effective,
)
from mneme.decision_index_persistence import (
    WAIVER_FEATURE,
    DecisionIndexMigrationRequired,
    DecisionIndexPersistenceError,
    DecisionWaiverRefused,
    add_decision_waiver,
    load_persisted_decision_index,
    revoke_decision_waiver,
    set_decision_applicability,
    waiver_id_of,
)
from mneme.decision_mcp import APPROVED_TOOLS
from mneme.decision_projection import project_canonical_index
from mneme.decision_waiver_authority import list_waivers, revoke_waiver, waive
from mneme.memory_store import MemoryStore
from tests.canonical_fixtures import canonical_document, v1_document

LICENCE = "LIC-001"
CSP = "CSP-001"
OLD = "OLD-001"
NEW = "NEW-001"
HYPERLIGHT = "project:hyperlight"
CREATED = "2026-04-22T00:00:00Z"
CNCF = dict(
    requester="cncf-hyperlight-maintainers",
    approver="cncf-governing-board",
    approval_reference="cncf/foundation#1117 (GB email vote 2026-04-22)",
    reason="picolibc licence exception for Hyperlight",
)


# ── fixtures ──────────────────────────────────────────────────────────────


def _decision(decision_id: str, status: str = "active", anti_patterns=None) -> dict:
    return {
        "id": decision_id,
        "decision": f"{decision_id} governs its area",
        "rationale": "",
        "scope": ["general"],
        "constraints": [],
        "anti_patterns": list(anti_patterns or []),
        "rules": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "status": status,
    }


def _section_less() -> dict:
    return {
        "meta": {"name": "dg1b2a", "description": "test"},
        "items": [],
        "examples": [],
        "decisions": [
            _decision(LICENCE, anti_patterns=["GPL-3.0"]),
            _decision(CSP, anti_patterns=["unsafe-inline"]),
            _decision(OLD, status="superseded"),
            _decision(NEW),
        ],
    }


def _base() -> dict:
    """Canonical v2 memory: licence, DfE-modelled CSP carve-out, supersession."""
    document = canonical_document(_section_less())
    for row in document["decision_index"]["decisions"]:
        if row["decision_id"] == NEW:
            row["relationships"] = [
                {"type": "supersedes", "target_decision_id": OLD}
            ]
    document, _ = set_decision_applicability(
        document, decision_id=CSP, required_labels=["service:eyfs"]
    )
    load_persisted_decision_index(document["decision_index"])
    return document


def _waive(document: dict, labels=(HYPERLIGHT,), target=LICENCE, **overrides):
    fields = dict(CNCF)
    fields.update(overrides)
    return add_decision_waiver(
        document,
        target_decision_id=target,
        required_labels=list(labels),
        created_at=CREATED,
        **fields,
    )


def _index(document: dict):
    return load_persisted_decision_index(document["decision_index"])


def _resolution(document: dict, context: GovernanceContext, decision_id=LICENCE):
    result = resolve_effective(_index(document), context)
    return result, next(d for d in result.decisions if d.decision_id == decision_id)


def _waiver_step(decision):
    return next(step for step in decision.trace if step.step == "waiver")


def _labels(*labels: str, as_of: str | None = None) -> GovernanceContext:
    return GovernanceContext(labels=labels, as_of=as_of)


def _write(path: Path, document: dict) -> Path:
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


def _without_waivers(document: dict) -> dict:
    document = copy.deepcopy(document)
    section = document["decision_index"]
    section.pop("waivers", None)
    section["semantic_features"] = [
        f for f in section["semantic_features"] if f != WAIVER_FEATURE
    ]
    return document


# ── 1. positive: CNCF-modelled, label-scoped, untimed ─────────────────────


def test_1_cncf_modelled_waiver_applies_only_with_matching_labels() -> None:
    document, waiver_id = _waive(_base())
    _, waived = _resolution(document, _labels(HYPERLIGHT))
    assert (waived.status, waived.cause) == ("ineffective", CAUSE_WAIVED)
    assert waived.waiver_ids == (waiver_id,)
    assert _waiver_step(waived).outcome == "waived"
    assert waived.lifecycle_status == "active"  # authoritative, unmutated

    for context in (_labels("project:other"), GovernanceContext()):
        _, effective = _resolution(document, context)
        assert (effective.status, effective.cause, effective.waiver_ids) == (
            "effective", None, ()
        )


def test_1_semantics_id_is_bumped_for_dg1b2a() -> None:
    assert GOVERNANCE_SEMANTICS_VERSION == "mneme.governance-semantics/dg1b2a-1"


# ── 2. expiry at a supplied as_of (synthetic) ─────────────────────────────


@pytest.mark.parametrize(
    ("as_of", "status", "reason"),
    [
        ("2026-06-01T00:00:00Z", "ineffective", None),
        ("2026-05-01T00:00:00Z", "ineffective", None),  # valid_from inclusive
        ("2026-04-30T23:59:59Z", "effective", "not_yet_valid"),
        ("2026-07-01T00:00:00Z", "effective", "expired"),  # valid_until exclusive
        (None, "effective", "as_of_missing"),
        ("2026-06-01", "effective", "as_of_invalid"),
        ("2026-06-01T00:00:00+00:00", "effective", "as_of_invalid"),
    ],
)
def test_2_time_bound_waiver_applies_only_inside_window(as_of, status, reason) -> None:
    document, waiver_id = _waive(
        _base(),
        valid_from="2026-05-01T00:00:00Z",
        valid_until="2026-07-01T00:00:00Z",
    )
    _, decision = _resolution(document, _labels(HYPERLIGHT, as_of=as_of))
    assert decision.status == status
    if reason:
        assert _waiver_step(decision).detail == (f"{waiver_id}:{reason}",)
    else:
        assert decision.cause == CAUSE_WAIVED


# ── 3. out-of-scope and not-supplied labels ───────────────────────────────


def test_3_labels_not_matching_or_not_supplied_leave_decision_effective() -> None:
    document, waiver_id = _waive(_base(), labels=(HYPERLIGHT, "licence:bsd"))
    for context, reason in (
        (_labels(HYPERLIGHT), "labels_not_matched"),  # subset is not enough
        (GovernanceContext(), "labels_not_supplied"),
        (GovernanceContext(labels=()), "labels_not_matched"),
    ):
        _, decision = _resolution(document, context)
        assert decision.status == "effective"
        assert _waiver_step(decision).detail == (f"{waiver_id}:{reason}",)
    _, waived = _resolution(document, _labels(HYPERLIGHT, "licence:bsd", "x"))
    assert waived.cause == CAUSE_WAIVED


# ── 4. revoked ────────────────────────────────────────────────────────────


def test_4_revoked_waiver_never_applies_and_is_retained() -> None:
    document, waiver_id = _waive(_base())
    revoked = revoke_decision_waiver(
        document, waiver_id=waiver_id, revoked_by="cncf-governing-board",
        revocation_reference="vote-2", reason="exception withdrawn",
    )
    _, decision = _resolution(revoked, _labels(HYPERLIGHT))
    assert decision.status == "effective"
    assert _waiver_step(decision).detail == (f"{waiver_id}:revoked",)
    (record,) = _index(revoked).waivers
    assert (record.waiver_id, record.status, record.revoked_by) == (
        waiver_id, "revoked", "cncf-governing-board"
    )
    with pytest.raises(DecisionWaiverRefused, match="already revoked"):
        revoke_decision_waiver(
            revoked, waiver_id=waiver_id, revoked_by="b",
            revocation_reference="r", reason="again",
        )


# ── 5. version mismatch ───────────────────────────────────────────────────


def _bind_to_other_version(document: dict, version_id: str) -> tuple[dict, str]:
    document = copy.deepcopy(document)
    row = document["decision_index"]["waivers"][0]
    row["target_decision_version_id"] = version_id
    row["waiver_id"] = waiver_id_of(
        target_decision_id=row["target_decision_id"],
        target_decision_version_id=version_id,
        required_labels=row["scope"]["required_labels"],
        valid_from=row.get("valid_from"),
        valid_until=row.get("valid_until"),
        requester=row["requester"],
        approver=row["approver"],
        approval_reference=row["approval_reference"],
        reason=row["reason"],
    )
    return document, row["waiver_id"]


def test_5_waiver_bound_to_another_version_never_applies_and_is_reported() -> None:
    document, _ = _waive(_base())
    older = "dver-" + "1" * 32
    document, waiver_id = _bind_to_other_version(document, older)
    result, decision = _resolution(document, _labels(HYPERLIGHT))
    assert decision.status == "effective"
    assert _waiver_step(decision).detail == (f"{waiver_id}:version_mismatch",)
    assert [(f.code, f.decision_id, f.detail) for f in result.findings] == [
        (FINDING_WAIVER_VERSION_MISMATCH, LICENCE, (waiver_id, older))
    ]


# ── 6. applicability and supersession negatives ──────────────────────────


def test_6_dfe_applicability_carve_out_needs_no_waiver_semantics() -> None:
    result, decision = _resolution(_base(), _labels("service:other"), CSP)
    assert (decision.status, decision.cause) == ("ineffective", CAUSE_NOT_APPLICABLE)
    assert decision.waiver_ids == ()
    assert all(step.step != "waiver" for step in decision.trace)
    assert result.findings == ()


def test_6_supersession_negative_needs_no_waiver_and_cannot_be_waived() -> None:
    _, decision = _resolution(_base(), _labels(HYPERLIGHT), OLD)
    assert decision.cause == CAUSE_LIFECYCLE_SUPERSEDED
    with pytest.raises(DecisionWaiverRefused, match="lifecycle-active"):
        _waive(_base(), target=OLD)


# ── 7. authority refusals and writer discipline ───────────────────────────


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"requester": ""}, "requester is required"),
        ({"approver": " "}, "approver is required"),
        ({"approval_reference": ""}, "approval reference is required"),
        ({"reason": ""}, "reason is required"),
        ({"approver": CNCF["requester"]}, "must differ"),
        ({"labels": ()}, "at least one label"),
        ({"labels": ("",)}, "non-empty strings"),
        ({"target": "MISSING"}, "does not exist"),
        ({"target": OLD}, "lifecycle-active"),
        ({"target_decision_version_id": "dver-" + "2" * 32}, "not the active version"),
        ({"valid_from": "2026-05-01"}, "RFC 3339"),
        (
            {"valid_from": "2026-07-01T00:00:00Z", "valid_until": "2026-05-01T00:00:00Z"},
            "earlier than",
        ),
    ],
)
def test_7_waive_refusals_change_nothing(overrides, message) -> None:
    base = _base()
    before = copy.deepcopy(base)
    with pytest.raises(DecisionWaiverRefused, match=message):
        _waive(base, **overrides)
    assert base == before


def test_7_v1_and_section_less_memory_refuse_with_migration_message() -> None:
    with pytest.raises(DecisionIndexMigrationRequired, match="--to-v2"):
        _waive(v1_document(_base()))
    with pytest.raises(DecisionIndexMigrationRequired, match="decision-index migrate"):
        _waive(_section_less())


def test_7_invalid_canonical_state_is_refused_not_repaired(tmp_path) -> None:
    document = _base()
    document["decision_index"]["decisions"][0]["lifecycle_status"] = "bogus"
    memory = _write(tmp_path / "project_memory.json", document)
    before = memory.read_bytes()
    with pytest.raises(DecisionIndexPersistenceError):
        waive(memory, target_decision_id=LICENCE, required_labels=[HYPERLIGHT], **CNCF)
    assert memory.read_bytes() == before


def test_7_authority_writes_atomically_and_reload_verifies(tmp_path) -> None:
    memory = _write(tmp_path / "project_memory.json", _base())
    result = waive(
        memory, target_decision_id=LICENCE, required_labels=[HYPERLIGHT],
        clock=lambda: CREATED, **CNCF,
    )
    assert result.waiver.status == "active"
    assert [w.waiver_id for w in list_waivers(memory)] == [result.waiver_id]
    assert list(tmp_path.iterdir()) == [memory]  # no temp file left behind
    revoked = revoke_waiver(
        memory, waiver_id=result.waiver_id, revoked_by="b",
        revocation_reference="r", reason="done",
    )
    assert revoked.waiver_id == result.waiver_id
    assert list_waivers(memory)[0].status == "revoked"


def test_7_concurrent_change_is_refused(tmp_path, monkeypatch) -> None:
    import mneme.decision_waiver_authority as authority

    memory = _write(tmp_path / "project_memory.json", _base())
    real = authority.add_decision_waiver

    def racing(*args, **kwargs):
        out = real(*args, **kwargs)
        memory.write_text(memory.read_text(encoding="utf-8") + " ", encoding="utf-8")
        return out

    monkeypatch.setattr(authority, "add_decision_waiver", racing)
    with pytest.raises(authority.WaiverAuthorityError, match="changed after it was read"):
        waive(memory, target_decision_id=LICENCE, required_labels=[HYPERLIGHT], **CNCF)
    assert "waivers" not in json.loads(memory.read_text(encoding="utf-8"))["decision_index"]


def test_7_cli_waive_revoke_and_list(tmp_path, capsys) -> None:
    memory = _write(tmp_path / "project_memory.json", _base())
    args = [
        "decision", "waive", LICENCE, "--label", HYPERLIGHT,
        "--requester", CNCF["requester"], "--approver", CNCF["approver"],
        "--approval-reference", CNCF["approval_reference"],
        "--reason", CNCF["reason"], "--memory", str(memory),
    ]
    assert main(args) == 0
    out = capsys.readouterr().out
    waiver_id = out.split()[1]
    assert waiver_id.startswith("wvr-")
    assert "do not change what mneme check" in out.replace("\n", " ")
    assert main(args) == 1
    assert "already exists" in capsys.readouterr().err

    assert main(["decision", "waivers", "--memory", str(memory), "--json"]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert listing["schema"] == "mneme.decision-waivers/v1"
    assert [w["waiver_id"] for w in listing["waivers"]] == [waiver_id]

    revoke = [
        "decision", "revoke-waiver", waiver_id, "--revoked-by", "board",
        "--revocation-reference", "r", "--reason", "done", "--memory", str(memory),
    ]
    assert main(revoke) == 0
    capsys.readouterr()
    assert main(revoke) == 1
    assert "already revoked" in capsys.readouterr().err

    v1 = _write(tmp_path / "v1.json", v1_document(_base()))
    assert main([*args[:-1], str(v1)]) == 2
    assert "--to-v2" in capsys.readouterr().err
    assert main([*args[:-1], str(tmp_path / "missing.json")]) == 1


# ── 8. self-authorization safeguards ──────────────────────────────────────


def test_8_mcp_tool_set_has_no_waiver_capability() -> None:
    assert len(APPROVED_TOOLS) == 6
    assert not [tool for tool in APPROVED_TOOLS if "waive" in tool]


def test_8_runtime_surfaces_never_write_waivers(tmp_path, capsys) -> None:
    document, _ = _waive(_base())
    memory = _write(tmp_path / "project_memory.json", document)
    source = tmp_path / "change.py"
    source.write_text("LICENSE = 'GPL-3.0'\n", encoding="utf-8")
    before = memory.read_bytes()
    main(["check", "--memory", str(memory), "--query", "licence", "--input",
          str(source), "--applicability-preview", HYPERLIGHT])
    main(["audit", "--memory", str(memory)])
    main(["protect", "list", "--memory", str(memory)])
    capsys.readouterr()
    assert memory.read_bytes() == before


def test_8_other_authority_writers_preserve_waivers() -> None:
    document, waiver_id = _waive(_base())
    upgraded, changed = set_decision_applicability(
        document, decision_id=NEW, required_labels=["x"]
    )
    assert changed
    assert [w.waiver_id for w in _index(upgraded).waivers] == [waiver_id]


def test_8_proposal_acceptance_writer_preserves_and_never_creates_waivers() -> None:
    document, waiver_id = _waive(_base())
    accepted = persistence.append_initial_canonical_decision(
        document,
        decision_id="ACC-001",
        statement="Accepted proposal",
        rationale="",
        context_scope=["general"],
        lifecycle_status="active",
        created_at=CREATED,
        updated_at=CREATED,
        occurrence_source_identity=["proposal", "dprop-test"],
        source_evidence=[{
            "source_type": "runtime", "source_locator": "",
            "source_revision": "", "observed_at": "", "verification_status": "",
        }],
    )
    accepted = accepted[0] if isinstance(accepted, tuple) else accepted
    index = _index(accepted)
    assert "ACC-001" in {r.decision_id for r in index.records}
    assert [w.waiver_id for w in index.waivers] == [waiver_id]


# ── 9. v2 contract: closed key sets, feature gating ───────────────────────


def _row_mutations():
    def unknown_key(row):
        row["expires"] = "never"

    def scope_unknown(row):
        row["scope"]["paths"] = ["src"]

    def null_window(row):
        row["valid_until"] = None

    def active_with_revocation(row):
        row["revocation"] = {"revoked_by": "a", "revocation_reference": "b", "reason": "c"}

    def revoked_without_revocation(row):
        row["status"] = "revoked"

    def bad_status(row):
        row["status"] = "expired"

    def unsorted_labels(row):
        row["scope"]["required_labels"] = ["z", "a"]

    def empty_scope(row):
        row["scope"]["required_labels"] = []

    def same_identities(row):
        row["approver"] = row["requester"]

    def bad_created(row):
        row["created_at"] = "yesterday"

    def revocation_unknown_key(row):
        row["status"] = "revoked"
        row["revocation"] = {
            "revoked_by": "a", "revocation_reference": "b", "reason": "c", "x": 1,
        }

    return [
        unknown_key, scope_unknown, null_window, active_with_revocation,
        revoked_without_revocation, bad_status, unsorted_labels, empty_scope,
        same_identities, bad_created, revocation_unknown_key,
    ]


@pytest.mark.parametrize("mutate", _row_mutations(), ids=lambda f: f.__name__)
def test_9_malformed_waiver_rows_refuse_the_document(mutate) -> None:
    document, _ = _waive(_base())
    mutate(document["decision_index"]["waivers"][0])
    with pytest.raises(DecisionIndexPersistenceError):
        _index(document)


def _rehash(row: dict) -> None:
    """Recompute ``waiver_id`` so only the guard under test can refuse."""
    row["waiver_id"] = waiver_id_of(
        target_decision_id=row["target_decision_id"],
        target_decision_version_id=row["target_decision_version_id"],
        required_labels=row["scope"]["required_labels"],
        valid_from=row.get("valid_from"),
        valid_until=row.get("valid_until"),
        requester=row["requester"],
        approver=row["approver"],
        approval_reference=row["approval_reference"],
        reason=row["reason"],
    )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda r: r.update(approver=r["requester"]), "must differ from requester"),
        (lambda r: r["scope"].update(required_labels=[]), "must be non-empty"),
        (
            lambda r: r.update(
                valid_from="2026-07-01T00:00:00Z", valid_until="2026-05-01T00:00:00Z"
            ),
            "earlier than valid_until",
        ),
        (lambda r: r.update(reason="   "), "must not be blank"),
        (lambda r: r.update(approver=" "), "must not be blank"),
    ],
    ids=["same-identities", "empty-scope", "inverted-window", "blank-reason",
         "blank-approver"],
)
def test_9_load_guards_hold_even_with_a_consistent_id(mutate, message) -> None:
    document, _ = _waive(_base())
    row = document["decision_index"]["waivers"][0]
    mutate(row)
    _rehash(row)
    with pytest.raises(DecisionIndexPersistenceError, match=message):
        _index(document)


def test_9_waivers_and_feature_declaration_must_agree() -> None:
    document, _ = _waive(_base())
    no_feature = copy.deepcopy(document)
    no_feature["decision_index"]["semantic_features"].remove(WAIVER_FEATURE)
    with pytest.raises(DecisionIndexPersistenceError, match="requires the 'decision_waivers'"):
        _index(no_feature)
    no_array = copy.deepcopy(document)
    del no_array["decision_index"]["waivers"]
    with pytest.raises(DecisionIndexPersistenceError, match="has no waivers array"):
        _index(no_array)
    empty = copy.deepcopy(document)
    empty["decision_index"]["waivers"] = []
    with pytest.raises(DecisionIndexPersistenceError, match="must be non-empty"):
        _index(empty)
    undeclared = _base()
    undeclared["decision_index"]["waivers"] = []
    with pytest.raises(DecisionIndexPersistenceError, match="requires the"):
        _index(undeclared)


def test_9_waivers_never_live_in_decision_rows_or_extensions() -> None:
    document, _ = _waive(_base())
    row = document["decision_index"]["waivers"][0]
    nested = copy.deepcopy(_base())
    nested["decision_index"]["decisions"][0]["waivers"] = [row]
    with pytest.raises(DecisionIndexPersistenceError, match="unsupported fields"):
        _index(nested)
    extension = copy.deepcopy(_base())
    extension["decision_index"]["extensions"] = {"com.example.waivers": [row]}
    assert _index(extension).waivers == ()  # opaque extension, never a waiver


# ── 9a. identity and canonical serialization ──────────────────────────────

_IDENTITY = dict(
    target_decision_id=LICENCE,
    target_decision_version_id="dver-" + "0" * 32,
    required_labels=["b", "a"],
    valid_from=None,
    valid_until=None,
    requester="r",
    approver="a",
    approval_reference="ref",
    reason="why",
)


def test_9a_identity_golden_is_frozen() -> None:
    # Independent derivation of the public contract (charter §3.1.2).
    import hashlib

    payload = [
        LICENCE, "dver-" + "0" * 32, ["a", "b"], None, None, "r", "a", "ref", "why",
    ]
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    assert waiver_id_of(**_IDENTITY) == f"wvr-{digest[:32]}"
    assert waiver_id_of(**_IDENTITY) == "wvr-f253beb57d21c96a73ac155895808ae2"


def test_9a_label_order_and_duplicates_do_not_change_identity() -> None:
    base = waiver_id_of(**_IDENTITY)
    assert waiver_id_of(**{**_IDENTITY, "required_labels": ["a", "b", "a"]}) == base


@pytest.mark.parametrize(
    "field",
    [
        "target_decision_id", "target_decision_version_id", "required_labels",
        "valid_from", "valid_until", "requester", "approver",
        "approval_reference", "reason",
    ],
)
def test_9a_every_creation_field_changes_identity(field) -> None:
    changed = {
        "required_labels": ["c"],
        "valid_from": "2026-01-01T00:00:00Z",
        "valid_until": "2026-12-31T00:00:00Z",
    }.get(field, "changed")
    assert waiver_id_of(**{**_IDENTITY, field: changed}) != waiver_id_of(**_IDENTITY)


def test_9a_status_revocation_and_created_at_do_not_change_identity() -> None:
    first, waiver_id = _waive(_base())
    second, same_id = add_decision_waiver(
        _base(), target_decision_id=LICENCE, required_labels=[HYPERLIGHT],
        created_at="2027-01-01T00:00:00Z", **CNCF,
    )
    assert same_id == waiver_id
    revoked = revoke_decision_waiver(
        first, waiver_id=waiver_id, revoked_by="b",
        revocation_reference="r", reason="done",
    )
    assert _index(revoked).waivers[0].waiver_id == waiver_id


def test_9a_tampered_and_duplicate_ids_refuse_at_load() -> None:
    document, waiver_id = _waive(_base())
    tampered = copy.deepcopy(document)
    tampered["decision_index"]["waivers"][0]["reason"] = "edited"
    with pytest.raises(DecisionIndexPersistenceError, match="identity mismatch"):
        _index(tampered)
    duplicate = copy.deepcopy(document)
    duplicate["decision_index"]["waivers"].append(
        copy.deepcopy(duplicate["decision_index"]["waivers"][0])
    )
    with pytest.raises(DecisionIndexPersistenceError, match="duplicate waiver_id"):
        _index(duplicate)


def test_9a_rows_are_written_sorted_by_id_with_canonical_shape() -> None:
    document = _base()
    ids = []
    for label in ("z-team", "a-team", "m-team"):
        document, waiver_id = _waive(document, labels=(label, "b", "b"))
        ids.append(waiver_id)
    rows = document["decision_index"]["waivers"]
    assert [row["waiver_id"] for row in rows] == sorted(ids)
    assert all(row["scope"]["required_labels"] == sorted(set(row["scope"]["required_labels"]))
               for row in rows)
    assert all("valid_from" not in row and "revocation" not in row for row in rows)
    assert document["decision_index"]["semantic_features"] == sorted(
        document["decision_index"]["semantic_features"]
    )
    with pytest.raises(DecisionWaiverRefused, match="already exists"):
        _waive(document, labels=("a-team", "b"))


def test_9a_reissue_after_revocation_is_refused() -> None:
    document, waiver_id = _waive(_base())
    document = revoke_decision_waiver(
        document, waiver_id=waiver_id, revoked_by="b",
        revocation_reference="r", reason="done",
    )
    with pytest.raises(DecisionWaiverRefused, match="never re-issued"):
        _waive(document)
    renewed, new_id = _waive(document, approval_reference="new vote")
    assert new_id != waiver_id
    assert len(_index(renewed).waivers) == 2


# ── 10. projection and every §3.8 surface unchanged ───────────────────────


def _capture(memory: Path, source: Path, capsys) -> dict:
    out = {}
    for name, argv in {
        "check": ["check", "--memory", str(memory), "--query", "licence",
                  "--input", str(source)],
        "check_json": ["check", "--memory", str(memory), "--query", "licence",
                       "--input", str(source), "--json"],
        "audit": ["audit", "--memory", str(memory)],
        "protect_list": ["protect", "list", "--memory", str(memory)],
    }.items():
        code = main(argv)
        captured = capsys.readouterr()
        out[name] = (code, captured.out.replace(str(memory), "<MEMORY>"))
    return out


def test_10_projection_and_authoritative_surfaces_are_unchanged(tmp_path, capsys) -> None:
    waived, _ = _waive(_base())
    waived, _ = _waive(waived, target=CSP, labels=("service:eyfs",))
    plain = _without_waivers(waived)
    assert project_canonical_index(_index(waived)) == project_canonical_index(_index(plain))

    source = tmp_path / "change.py"
    source.write_text("LICENSE = 'GPL-3.0'\nCSP = 'unsafe-inline'\n", encoding="utf-8")
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    with_memory = _write(tmp_path / "a" / "project_memory.json", waived)
    without_memory = _write(tmp_path / "b" / "project_memory.json", plain)
    assert _capture(with_memory, source, capsys) == _capture(without_memory, source, capsys)

    for memory, reference in ((with_memory, without_memory),):
        store, ref_store = MemoryStore(str(memory)), MemoryStore(str(reference))
        store.load()
        ref_store.load()
        def unbound(decisions):
            return [dataclasses.replace(d, memory_path="") for d in decisions]

        assert unbound(store.decisions()) == unbound(ref_store.decisions())
        assert unbound(governed_runtime_decisions(store)) == unbound(
            governed_runtime_decisions(ref_store)
        )

    not_supplied = resolve_effective(_index(waived), GovernanceContext())
    assert not_supplied.effective_ids == resolve_effective(
        _index(plain), GovernanceContext()
    ).effective_ids


def test_10_waiver_free_resolution_trace_is_unchanged() -> None:
    plain = resolve_effective(_index(_base()), _labels(HYPERLIGHT))
    assert all(step.step != "waiver" for d in plain.decisions for step in d.trace)
    assert all(d.waiver_ids == () for d in plain.decisions)


# ── 11. time and integrity edge cases ─────────────────────────────────────


def test_11_multiple_matching_waivers_are_all_reported_sorted() -> None:
    document, first = _waive(_base())
    document, second = _waive(document, approval_reference="second approval")
    _, decision = _resolution(document, _labels(HYPERLIGHT))
    assert decision.waiver_ids == tuple(sorted((first, second)))


def test_11_waiver_on_superseded_decision_is_not_evaluated() -> None:
    document, _ = _waive(_base(), target=NEW)
    lifecycle = document["decision_index"]["decisions"]
    for row in lifecycle:
        if row["decision_id"] == NEW:
            row["lifecycle_status"] = "deprecated"
    _, decision = _resolution(document, _labels(HYPERLIGHT), NEW)
    assert decision.cause == "lifecycle_deprecated"
    assert _waiver_step(decision).outcome == "not_evaluated"


def test_11_waiver_alongside_supersession_conflict_finding() -> None:
    document, waiver_id = _waive(_base())
    for row in document["decision_index"]["decisions"]:
        if row["decision_id"] == NEW:
            row["relationships"].append(
                {"type": "supersedes", "target_decision_id": LICENCE}
            )
    result, decision = _resolution(document, _labels(HYPERLIGHT))
    assert decision.waiver_ids == (waiver_id,)
    assert FINDING_SUPERSESSION_LIFECYCLE_CONFLICT in {f.code for f in result.findings}


def test_11_not_applicable_decision_is_not_waived() -> None:
    document, _ = _waive(_base(), target=CSP, labels=(HYPERLIGHT,))
    _, decision = _resolution(document, _labels(HYPERLIGHT), CSP)
    assert decision.cause == CAUSE_NOT_APPLICABLE
    assert _waiver_step(decision).outcome == "not_evaluated"


def test_11_dangling_waiver_target_is_a_finding_not_an_error() -> None:
    document, _ = _waive(_base())
    row = document["decision_index"]["waivers"][0]
    row["target_decision_id"] = "GONE-001"
    row["waiver_id"] = waiver_id_of(
        target_decision_id="GONE-001",
        target_decision_version_id=row["target_decision_version_id"],
        required_labels=row["scope"]["required_labels"],
        valid_from=None, valid_until=None,
        requester=row["requester"], approver=row["approver"],
        approval_reference=row["approval_reference"], reason=row["reason"],
    )
    result = resolve_effective(_index(document), _labels(HYPERLIGHT))
    assert [(f.code, f.decision_id) for f in result.findings] == [
        (FINDING_DANGLING_WAIVER_TARGET, "GONE-001")
    ]
    assert LICENCE in result.effective_ids


def test_11_revoked_waiver_on_an_old_version_is_not_a_finding() -> None:
    document, waiver_id = _waive(_base())
    document = revoke_decision_waiver(
        document, waiver_id=waiver_id, revoked_by="b",
        revocation_reference="r", reason="done",
    )
    document, _ = _bind_to_other_version(document, "dver-" + "1" * 32)
    assert resolve_effective(_index(document), _labels(HYPERLIGHT)).findings == ()


def test_11_resolve_change_reports_effect_but_is_not_a_waiver_audit() -> None:
    context = _labels(HYPERLIGHT)
    before = resolve_effective(_index(_base()), context)
    one, _ = _waive(_base())
    after_one = resolve_effective(_index(one), context)
    change = compare_resolutions(before, after_one)
    (entry,) = change.changes
    assert entry.decision_id == LICENCE
    assert {CHANGE_BECAME_INEFFECTIVE, CHANGE_CAUSE} <= set(entry.kinds)

    two, _ = _waive(one, approval_reference="second approval")
    assert not compare_resolutions(
        after_one, resolve_effective(_index(two), context)
    ).changes


# ── 12. C1a preview: informational only ───────────────────────────────────


def _preview(memory: Path, source: Path, capsys, preview: bool):
    argv = ["check", "--memory", str(memory), "--query", "licence",
            "--input", str(source), "--json"]
    if preview:
        argv += ["--applicability-preview", HYPERLIGHT]
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_12_c1a_preview_shows_waived_under_non_authoritative_header(tmp_path, capsys) -> None:
    document, _ = _waive(_base())
    memory = _write(tmp_path / "project_memory.json", document)
    source = tmp_path / "change.py"
    source.write_text("LICENSE = 'GPL-3.0'\n", encoding="utf-8")
    plain = _preview(memory, source, capsys, preview=False)
    shown = _preview(memory, source, capsys, preview=True)
    assert (shown[0], shown[1]) == (plain[0], plain[1])  # stdout, JSON, exit
    assert "NON-AUTHORITATIVE" in shown[2]
    assert f"[{LICENCE}] ineffective (cause=waived;" in shown[2]


def test_12_c1a_preview_is_unavailable_on_waiver_findings(tmp_path, capsys) -> None:
    document, _ = _waive(_base())
    document, _ = _bind_to_other_version(document, "dver-" + "1" * 32)
    memory = _write(tmp_path / "project_memory.json", document)
    source = tmp_path / "change.py"
    source.write_text("LICENSE = 'GPL-3.0'\n", encoding="utf-8")
    plain = _preview(memory, source, capsys, preview=False)
    shown = _preview(memory, source, capsys, preview=True)
    assert (shown[0], shown[1]) == (plain[0], plain[1])
    assert "PREVIEW UNAVAILABLE" in shown[2]


# ── 13. readers without the feature refuse waiver memory ──────────────────


def test_13_reader_without_waiver_feature_refuses_document(monkeypatch) -> None:
    document, _ = _waive(_base())
    monkeypatch.setattr(
        persistence,
        "SUPPORTED_SEMANTIC_FEATURES",
        persistence.SUPPORTED_SEMANTIC_FEATURES - {WAIVER_FEATURE},
    )
    with pytest.raises(DecisionIndexPersistenceError, match="unsupported semantic_features"):
        _index(document)


def test_resolution_dataclass_default_keeps_waiver_ids_empty() -> None:
    field = {f.name: f for f in dataclasses.fields(
        type(resolve_effective(_index(_base())).decisions[0])
    )}["waiver_ids"]
    assert field.default == ()
