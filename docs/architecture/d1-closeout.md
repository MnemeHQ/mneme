# D1 Closeout: Canonical Decision Persistence

**Status:** architecture, test, and release-gate closeout for
[ADR-030](../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md)
D1 (slice D1E6). It records why D1 is architecturally complete and what the
eventual release must communicate.

This is not a release note. D1 is prepared for release as `mneme-hq` 0.10.0
([release notes](../releases/v0.10.0.md)). The release itself follows
[RELEASING.md](../releases/RELEASING.md) in a separate release-prep change: version bump, `CHANGELOG.md` entry, `docs/releases/vX.Y.Z.md`, the
exact-SHA release battery, artifact validation, tag, and GitHub release.

## Implementation slices (all squash-merged on `main`)

| Slice | What it established | PR |
| --- | --- | --- |
| D1B | Persisted `decision_index`, migration, loader, load-time projection, compatibility snapshot | #424 |
| D1C | Authority write path and Decision MCP read the canonical index | #440 (live cutover #441, containment #444) |
| D1D | Immutable ADR version evolution and cross-id supersession | #443 |
| D1E0 | Binding authority, protection continuity, `cli-add` identity, EventCatalog decision | #447 |
| D1E1 | `mneme decision-index migrate` (sole transition), `binding_authority` plumbing | #448, #449 |
| D1E2 | Protection continuity in version evolution; canonical `protect activate` | #451, #453 |
| D1E3 | Canonical `mneme add_decision` (`["cli-add", id]`) | #454 |
| D1E4 | EventCatalog canonical apply retired for D1 | #456 |
| D1E5 | `mneme init` / `mneme setup` create canonical memory | #458 |
| D1E6 | This closeout: G16/G17/G19 evidence pinned, architecture docs current | this change |

D1F (removal of the `decisions[]` compatibility snapshot) is optional and
separate.

## Validation-gate evidence (ADR-030 §14)

### G16: runtime projection parity

- **Load-time path, real corpora:**
  [`test_d1e6_closeout_parity.py`](../../tests/test_d1e6_closeout_parity.py)
  reads each section-less corpus with the pre-D1 loader, migrates it with the
  production migration command, reads it again with the canonical loader, and
  requires identical runtime `Decision[]`
  (`test_g16_load_time_projection_is_identical`).
- **Corpora (unchanged fixtures):** `examples/project_memory.json`, and
  `tests/fixtures/d1_parity/pre_d1_live_project_memory.json`, the exact bytes
  of this repository's live memory immediately before the D1 cutover
  (`06989a4f^`, #441), pinned by SHA-256
  (`test_pre_d1_live_fixture_is_unchanged`).
- **D0 adapter battery** (unchanged):
  [`test_decision_projection.py`](../../tests/test_decision_projection.py)
  G1-G5, and G6 lifecycle parity in
  [`test_decision_index.py`](../../tests/test_decision_index.py).
- **Persisted-section projection:**
  `test_real_memory_migration_projects_exact_runtime_decisions` in
  [`test_decision_index_persistence.py`](../../tests/test_decision_index_persistence.py).
- **Legacy items:** `examples/project_memory.json` carries legacy
  `rule`/`anti_pattern` items, so migrated item decisions are covered by the
  same equality.

### G17: Audit, enforcement, ConflictDetector, and benchmark parity

All in [`test_d1e6_closeout_parity.py`](../../tests/test_d1e6_closeout_parity.py),
pre-migration versus post-migration on both real corpora:

| Consumer | Test |
| --- | --- |
| Retrieval rankings, scores, matches (D0 G2) | `test_g17_retrieval_rankings_are_identical` |
| Strict verdicts, violations, applicability (D0 G3) | `test_g17_strict_enforcement_verdicts_are_identical`, non-vacuity guard `test_g17_enforcement_fires_on_the_real_typed_rule` |
| ConflictDetector conflicts and applicability (D0 G4) | `test_g17_conflict_detector_is_identical` |
| Architecture Audit report, with and without repo root (D0 G5) | `test_g17_architecture_audit_is_identical` |
| Frozen benchmarks (D0 G3) | `test_g17_frozen_benchmarks_are_identical`, plus `test_real_migrated_projection_preserves_frozen_benchmark_results` |

### G16/G17 scope exception: lifecycle conformance

The §12 lifecycle-conformance correction is excluded from G16/G17 parity by
design. Both real corpora are all-`active`
(`test_g16_corpora_are_all_active_so_lifecycle_correction_is_excluded`). The
correction is pinned by its own fixture,
`test_r1_migration_removes_non_active_decisions_from_layer1` in
[`test_decision_index_persistence.py`](../../tests/test_decision_index_persistence.py):
active decisions keep exact parity, and non-active decisions are retained
canonically but leave projection, the snapshot, retrieval, enforcement, and
the Audit decision set. Audit tier percentages are unchanged.

### G18: migration idempotency and collision failure

| Requirement | Tests |
| --- | --- |
| Migrate twice is byte-identical | `test_migration_is_byte_idempotent`, `test_document_migration_is_side_effect_free_and_structurally_idempotent` ([persistence](../../tests/test_decision_index_persistence.py)); `test_cli_apply_then_rerun_is_byte_identical_noop`, `test_already_canonical_live_memory_is_a_noop` ([D1E1](../../tests/test_d1e1_migration.py)) |
| Item-ID versus canonical-ID collision fails closed | `test_native_and_legacy_item_id_collision_fails_closed` |
| Section-less files load through the legacy path | [`test_memory_store_decisions.py`](../../tests/test_memory_store_decisions.py); canonical readers refuse them (`test_loader_raises_migration_required_for_section_less_memory`) |
| Snapshot corruption is caught | `test_compatibility_snapshot_divergence_fails_closed` |
| Reverse half-states fail closed | `test_proposed_plus_existing_decision_fails_closed` ([authority](../../tests/test_decision_authority.py)); `test_accept_reverse_half_state_surfaces_core_refusal` ([authority CLI](../../tests/test_decision_authority_cli.py)) |
| Migration is lossless or refuses | `test_lossy_legacy_state_refuses_byte_identical`, `test_source_change_between_plan_and_write_refuses` |

### G19: MCP field compatibility

| Requirement | Tests |
| --- | --- |
| Six-tool inventory frozen | `test_approved_inventory_is_the_frozen_contract` ([MCP](../../tests/test_decision_mcp.py)) |
| Stable and additive record/rule fields, exact key order | `test_canonical_record_serialization_preserves_ordering`, `test_rule_serialization_passes_applicability_verbatim` |
| Rule IDs deterministic, golden-vector verified | `test_identity_golden_vectors`, `test_rule_identity_is_stable_under_reordering`, `test_rule_identity_changes_when_semantics_change` ([persistence](../../tests/test_decision_index_persistence.py)); migrated live rule `test_g19_migrated_live_rule_id_golden_vector` |
| Migrated memory through MCP carries stable IDs only, no positional or dual ID | `test_g19_mcp_emits_stable_rule_ids_only_never_positional` |
| Old positional ID recoverable from `sequence` (§13) | `test_g19_positional_id_is_recoverable_from_sequence` |
| Additive fields present; `binding_authority` absent | `test_g19_additive_fields_present_and_binding_authority_absent`, `test_mcp_rule_transport_never_emits_binding_authority` ([D1E1](../../tests/test_d1e1_migration.py)) |

The new G19 tests are in
[`test_d1e6_closeout_parity.py`](../../tests/test_d1e6_closeout_parity.py).

### G20: binding authority and protection continuity

| Requirement | Tests |
| --- | --- |
| No silent loss, including an unrelated ADR edit | `test_unrelated_edit_dropping_continuity_binding_fails_closed` ([D1E2a](../../tests/test_d1e2a_continuity.py)); `test_canonical_protection_is_held_by_continuity_on_adr_edit` ([D1E2b](../../tests/test_d1e2b_canonical_protect.py)) |
| Re-derived identical rule keeps the stronger authority | `test_rederived_rule_keeps_stronger_authority` |
| Explicit preserve | `test_preserve_and_release_with_ordering` |
| Failed revalidation fails closed | `test_preserve_failing_revalidation_fails_closed` |
| Explicit release: downgrade to `version`, or omission | `test_release_of_rederived_rule_downgrades_to_version`; omission in `test_preserve_and_release_with_ordering` |
| Missing field reads `legacy_unknown`, rows byte-identical | `test_rows_without_binding_authority_read_legacy_unknown_unrewritten` ([D1E1](../../tests/test_d1e1_migration.py)) |
| Migration writes `legacy_unknown` | `test_migration_persists_legacy_unknown` |
| Ordering: source-derived first, then preserved | `test_preserve_and_release_with_ordering` |
| Retry consistency; stale predecessor unchanged | `test_retry_with_same_requests_is_noop_and_different_requests_refuse`; `test_d1d_stale_new_occurrence_fails_closed` |
| Accepted-proposal retry after canonical protection | `test_accept_retry_survives_canonical_protection_enrichment` ([D1E2b](../../tests/test_d1e2b_canonical_protect.py)) |
| `cli-add` identity, exact retry, different content | [`test_d1e3_canonical_add_decision.py`](../../tests/test_d1e3_canonical_add_decision.py) |

## Release gate (ADR-030 §15)

| Condition | State |
| --- | --- |
| §12 migration entry point exists | Met (D1E1) |
| No silent loss of `protection`/`legacy_unknown` bindings | Met (D1E2, G20) |
| No released artifact contains D1B/C/D | Met: no tag contains D1B (`9992d727`); the latest tag `v0.9.2` predates it |
| Release notes cover the required subjects | Met in the 0.10.0 release-candidate source by [`v0.10.0.md`](../releases/v0.10.0.md) and the `CHANGELOG.md` entry; see below |

D1 will ship in 0.10.0 only after the remaining
[RELEASING.md](../releases/RELEASING.md) steps on the exact
release-candidate SHA (release battery, artifact validation, tag, GitHub
release).

## Required release communication

The first release that ships D1 must communicate each item below in its
`docs/releases/vX.Y.Z.md` and `CHANGELOG.md` entry.

Required by ADR-030:

1. **Lifecycle-conformance correction.** After migration, only `active`
   decisions take part in Layer 1. Legacy `superseded`, `deprecated`, and
   `inactive` decisions are retained canonically, but they no longer take part
   in retrieval, enforcement (including their typed rules), ConflictDetector,
   benchmark runtime sets, or the Audit decision set. Audit tier percentages
   are unchanged; `total_decisions` and the per-decision list drop those
   entries.
2. **Rule-ID value change.** `rule_id` and `derived_rule_ids` values change
   from positional IDs (`<decision_id>:<RULE_TYPE>:<index>`) to stable
   content-derived IDs (`<decision_id>:<RULE_TYPE>:<32 hex>`). Field names and
   ordering are unchanged, both formats are never emitted together, and the
   old positional ID is `<decision_id>:<RULE_TYPE>:<sequence>`.
3. **EventCatalog canonical apply retired.** `eventcatalog import --apply`
   refuses canonical memory. Because `init`/`setup` now create canonical
   memory, it is unavailable for every new project. Preview remains
   available; existing section-less projects may keep the legacy apply path
   during the compatibility window.
4. **Migration limitation.** Memory containing legacy EventCatalog-imported
   decisions, or other `decisions[]` metadata the canonical index cannot
   represent, cannot migrate in D1 and stays on the section-less
   compatibility path. Migration is lossless or it refuses.
5. **Older binaries.** `mneme-hq` 0.9.2 and earlier write `decisions[]`
   directly through legacy writers, which makes a migrated file fail to load.
   Migrated memory must not be used with those binaries. No in-file version
   marker exists.

Additional user-visible compatibility changes:

6. **New command.** `mneme decision-index migrate --memory <path>` previews
   the migration and `--apply` writes it. It is the only way to convert
   existing memory.
7. **Decision MCP requires canonical memory.** The server refuses to start on
   section-less memory and directs the user to preview, then apply, the
   migration. The pre-D1 proposal-store-only startup mode is gone.
8. **Additive MCP fields.** Canonical records gain `version_id`,
   `decision_version_id`, and `content_digest`; rule payloads gain
   `decision_version_id` and `sequence`; `source_evidence` may gain
   `source_revision` and `observed_at`. Existing fields are unchanged and the
   six-tool inventory is unchanged.
9. **New projects are canonical.** `mneme init` and `mneme setup` create
   memory with an empty `decision_index`; existing files are never converted
   implicitly. `init --force` still resets the file, now to canonical memory.
