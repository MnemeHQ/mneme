# adrkit Reference Decision Review Packet

**Repository:** mbeacom/adrkit
**Pinned Commit:** 471457da29638ecca6119b35180c2845bf989cac
**Total Records:** 20
**Status:** All pending human review

---

## Summary by Sampling Category

| Category | Quota | Selected |
|----------|-------|----------|
| clear_explicit | 5 | 5 ✓ |
| scoped | 5 | 5 ✓ |
| lifecycle_or_supersession | 3 | 3 ✓ |
| ambiguous_or_conflicting | 3 | 3 ✓ |
| enforcement_potential | 2 | 2 ✓ |
| unusual_or_difficult | 2 | 2 ✓ |
| **Total** | **20** | **20 ✓** |

---

## Records for Review

### clear_explicit (5)

| ID | ADR | Title | Classification | Authority | Key Decision |
|----|-----|-------|--------------|-----------|--------------|
| ref-adrkit-001 | 0001 | Record architecture decisions in git | prescriptive | explicitly_accepted | One file per decision in docs/adr/NNNN-kebab-title.md with YAML frontmatter |
| ref-adrkit-002 | 0002 | Type frontmatter as MADR superset | prescriptive | explicitly_accepted | Strict MADR superset with governance metadata; Zod schema with JSON Schema emission |
| ref-adrkit-003 | 0003 | Ship as Spec Kit extension + CLI | prescriptive | explicitly_accepted | Dual distribution: Spec Kit extension + standalone CLI, both as thin adapters |
| ref-adrkit-004 | 0004 | Git as source of truth, DB as derived index | prescriptive | explicitly_accepted | Git holds truth; Postgres is derived rebuildable index; no direct DB writes |
| ref-adrkit-005 | 0006 | License Apache-2.0 with DCO in monorepo | prescriptive | explicitly_accepted | Apache-2.0 + DCO; single monorepo with independent versioning; schema also CC0 |

### scoped (5)

| ID | ADR | Title | Classification | Authority | Key Decision |
|----|-----|-------|--------------|-----------|--------------|
| ref-adrkit-006 | 0007 | Isolate integrations as optional adapters | prescriptive | explicitly_accepted | Every integration is optional adapter package; core depends on no adapter; clean clone must build without credentials |
| ref-adrkit-007 | 0008 | Migrate MADR in place, one-way imports with re-import diff | prescriptive | explicitly_accepted | Preserve source status on MADR import; agent logs proposed; plans as draft; MADR in-place; others one-way with fingerprint diff |
| ref-adrkit-008 | 0009 | Pin affects resolution semantics | prescriptive | explicitly_accepted | Resolution is pure function; per-ADR union match; explicit per-type semantics; absent sources inert |
| ref-adrkit-009 | 0010 | Use Bun toolchain with isolated linker | prescriptive | explicitly_accepted | Bun for install/build/test with isolated linker; text lockfile; Node-compatible published output |
| ref-adrkit-010 | 0011 | Host canonical JSON Schema at $id on adrkit.dev | prescriptive | explicitly_accepted | Serve schema at $id via GitHub Pages; byte-match guard; version paths immutable |

### lifecycle_or_supersession (3)

| ID | ADR | Title | Classification | Authority | Lifecycle |
|----|-----|-------|--------------|-----------|-----------|
| ref-adrkit-011 | 0005 | Deterministic-first evaluator (superseded) | prescriptive | superseded by 0027 | superseded |
| ref-adrkit-012 | 0014 | Three-rung validation ladder | prescriptive | active | active |
| ref-adrkit-013 | 0027 | Ratify deterministic evaluator (supersedes 0005) | prescriptive | active | active |

### ambiguous_or_conflicting (3)

| ID | ADR | Title | Classification | Authority | Notes |
|----|-----|-------|--------------|-----------|-------|
| ref-adrkit-014 | 0013 | Reconcile adapter isolation and catalog binding | advisory | explicitly_accepted | Amends ADR-0007/0009; keeps both proposed |
| ref-adrkit-015 | 0015 | Validate descriptors before canonicalizing | prescriptive | explicitly_accepted | Adds admissibility precondition; inadmissible-descriptor trigger |
| ref-adrkit-016 | 0020 | Rescope SC-010 for Backstage catalog adapter | advisory | explicitly_accepted | Rescopes spike criterion; authorizes work; release deferred |

### enforcement_potential (2)

| ID | ADR | Title | Classification | Authority | Enforcement |
|----|-----|-------|--------------|-----------|-------------|
| ref-adrkit-017 | 0016 | Require observed failure per check | prescriptive | explicitly_accepted | deterministic_rule |
| ref-adrkit-018 | 0017 | Keep dependency audit scope explicit | prescriptive | explicitly_accepted | deterministic_rule |

### unusual_or_difficult (2)

| ID | ADR | Title | Classification | Authority | Notes |
|----|-----|-------|--------------|-----------|-------|
| ref-adrkit-019 | 0018 | Adopt MCP SDK v2 dual-era | prescriptive | explicitly_accepted | Dual-era protocol, retired ADR-0017 |
| ref-adrkit-020 | 0019 | Ship Spec Kit extension overriding spike no-go | advisory | explicitly_accepted | Overrides spike no-go; multiple addenda |

---

## Review Instructions

For each record, please:
1. **Accept** — Record is correct and complete
2. **Correct** — Modify specific fields (note which)
3. **Mark Ambiguous** — Record needs clarification
4. **Reject** — Record should not be in reference corpus (state why)

### Key Questions per Record

- Is the `source_location` accurate and verifiable in the pinned commit?
- Does the `normalized_decision` accurately reflect the source evidence?
- Are `classification`, `decision_domains`, `decision_purposes` using exact O1A vocabulary?
- Is `authority_status` correctly assigned per O1A meanings?
- Are `scopes`, `lifecycle`, `relationships` supported by evidence?
- Is `enforcement_potential` classification justified?
- Does `sampling_category` match the intended quota design?
- Any `ONTOLOGY_GAP` concerns?

### Special Cases to Note

1. **ref-adrkit-011 (ADR-0005)**: Marked `superseded` by ADR-0027 — verify supersession evidence
2. **ref-adrkit-013 (ADR-0027)**: Full content not in pinned commit; noted as superseding ADR-0005
3. **ref-adrkit-014 (ADR-0013)**: Amends ADR-0007/0009; both remain `proposed` — verify this is intentional
3. **ref-adrkit-016 (ADR-0020)**: Rescopes spike SC-010; overrides one criterion on proof it cannot be met
4. **ref-adrkit-020 (ADR-0019)**: Overrides spike 008 `no-go` verdict; multiple addenda for pin re-verification and rung-2 verification

---

## Verification Checklist

- [ ] All 20 records present with unique `ref-adrkit-XXX` IDs
- [ ] All source locations point to valid lines in pinned commit
- [ ] All taxonomy fields use exact O1A vocabulary
- [ ] No `cand-*` IDs used as reference IDs
- [ ] All `human_review_status` = "pending"
- [ ] Sampling quota: 5/5/3/3/2/2 = 20 ✓
- [ ] No machine prediction fields present
- [ ] Corpus hash computed (see below)

---

## Draft Corpus Hash

**Content Hash:** `sha256:efdc8c33da235930fb2dbea155ef4bbe02e5ae874aae787c155d3ffa3adda60e`

---

## Files Changed

- `benchmarks/open_architecture/batch_01/reference_decisions/adrkit/ref-adrkit-001.jsonl` through `ref-adrkit-020.jsonl` (20 files)

---

**Please review and return with your decisions for each record.**