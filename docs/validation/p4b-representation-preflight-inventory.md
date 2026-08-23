# P4B — Representation-Change Pre-Flight Inventory (Evidence Note)

Status: **pre-flight evidence capture only — no ADR-016 clarification drafted; no retrieval results
inspected; no memory, ADR, or retriever files modified**
Date: 2026-08-23
Authority: [P4A protocol](p4a-representation-validation-protocol.md) §5 (merged `303ba09d`)
Purpose: freeze the baseline regeneration behavior **before** any representation change is drafted,
so pre-existing import effects cannot be attributed to the later ADR-016 change.

---

## 1. Baseline pin

| Item | Value |
|---|---|
| Canonical `main` | `303ba09ddb794860e6090362f9109ab672626ff8` (#308, P4A lock) |
| Live memory `.mneme/project_memory.json` | sha256 `BBBE873FD697941F172F2683C2EC285DBF67030B12AE2A0F44B704457BE9F9CA` |
| Retriever | unchanged (`mneme/decision_retriever.py`, sha256 `8EA03377…`) |

## 2. Field provenance: compiler-derived vs hand-authored

Established from `mneme/adr_import.py` (`apply_import`, entry-construction block) and
`mneme/adr_compiler.py`, then confirmed by round-trip:

| Memory field | Provenance |
|---|---|
| `id` | ADR frontmatter `id` |
| `decision` | frontmatter `title` |
| `scope` | frontmatter `scope` (**participates in ADR precedence** — see P3 §4A caution) |
| `rationale` | full ADR markdown body |
| `constraints` / `rules` / `anti_patterns` | compiler directives |
| `created_at` / `updated_at` | ADR dates |
| `source.path` / `source.sha256` | computed at import time |

The live `ADR-016` entry carries `source: {type: adr, path: ../docs/adr/ADR-016-site-governance-transfer.md, sha256: 0f460aa1…}`
and is therefore import-born, not hand-authored.

## 3. Exact regeneration commands

```text
# preview (default; no write)
python -m mneme adr import docs/adr --memory <target>

# write; same-id entries replaced in place, position-preserving; atomic via tempfile + replace
python -m mneme adr import docs/adr --memory <target> --apply --update-existing
```

## 4. No-edit round-trip method

1. Copy `.mneme/project_memory.json` to a sibling path at identical directory depth
   (`.mneme/project_memory.roundtrip.json`) so relative source paths resolve identically.
2. Run the apply command against the copy.
3. Diff every field of every record against the untouched original.
4. Delete the copy.

An initial attempt with the copy outside the repository produced spurious
`../../../../../../dev/mneme/...` relative paths on all 13 imported entries; that was an artifact of
the copy's location, discarded, and superseded by the at-depth run below.

## 5. Round-trip results

| Result | Value |
|---|---|
| Record counts | 15 → 15; nothing added or removed |
| **Content-field divergence** | **NONE** — `decision`, `rationale`, `scope`, `constraints`, `anti_patterns` reproduce byte-identically for all 13 ADR-backed entries, including `ADR-016` |
| `rules` key normalization | 7 entries (`ADR-001, -002, -004, -009, -010, -013, -014`): live file omits `rules`; import emits `[]` |
| Stale `source.sha256` | 6 entries: `ADR-005, -016, -017, -018, -019, -020` — stored hash ≠ current ADR-file hash; these ADRs were edited after their last import without re-import |

Stale-hash detail:

| Entry | Stored sha256 | Current sha256 |
|---|---|---|
| ADR-005 | `63974fc08eb363bf…` | `0d48c572ecea0274…` |
| ADR-016 | `0f460aa1b6cc5a76…` | `c6ba79771b0c19b1…` |
| ADR-017 | `d1490a47482ad941…` | `d987457403b4099b…` |
| ADR-018 | `39567c51af97bfc7…` | `e4ca6312b5935e24…` |
| ADR-019 | `8729a12dc4bfa7e2…` | `d70803a160ad12fb…` |
| ADR-020 | `cb44e677358e58d5…` | `38576df32b7f114f…` |

All stored/current hash pairs above verified against `.mneme/project_memory.json` and `docs/adr/`
file contents directly at capture time.

## 6. Disposition of findings

The seven `rules` normalizations and six stale hashes are **baseline evidence and are deliberately
not fixed in P4B**. Re-import during the future representation change will incidentally refresh both;
the change PR must disclose those refreshes as expected regeneration side effects, distinct from the
substantive ADR-016 clarification.

## 7. Conclusion

Pre-flight complete. The import path reproduces all scored and governance fields of the live corpus
exactly from current ADR sources; the only pre-existing drift is provenance metadata. No ADR-016
clarification has been drafted; no retrieval results have been inspected. Next step per P4A §7:
draft exactly one derivable ADR-016 clarification, regenerate/import, then measure B0′ and run the
single-shot evaluation under gates G1–G4.
