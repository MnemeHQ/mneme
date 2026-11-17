# DG1F-C3a: resolver-result consumption by three reporting consumers (charter)

**Status: PROPOSED.** Behavioral charter for C3a. On merge it fixes the
contract and acceptance evidence. **It authorizes no implementation by
itself.** Implementation also needs a separate `[layer1-freeze]` amendment
(§8) with its own review and approval.
**Anchor:** `MnemeHQ/mneme` `main` at `7af4645a` (C3 feasibility, #773), on
top of DG1F-C2 (`b719dc96`, #770).
**Basis:** [C3 feasibility assessment](2026-11-09-dg1f-c3-resolver-result-feasibility.md)
(#773), [C2 charter](2026-11-08-dg1f-c2-lifecycle-convergence-charter.md)
(#764), the C2 freeze amendment (#767), tracker
[#497](https://github.com/MnemeHQ/mneme/issues/497).
**Governs:** C3a only. Not `audit_with_github_claim`, protection
status/validate/activate, enforcement inputs, explanation output, C1b, DG1B2
or DG1G.

## 1. Governing authority and starting behavior

- [ADR-031](../adr/ADR-031-decision-governance-semantics.md) §11 requires
  runtime consumers to converge on the shared resolver result; §7 requires a
  merged charter where a DG1F step changes enforcement inputs; tracker #497
  requires each consumer to be individually chartered.
- The DG1B1, DG1F-C1a and DG1F-C2 freeze amendments in
  [`layer1-freeze-e73ff7d.md`](../architecture/layer1-freeze-e73ff7d.md)
  prohibit Audit, readiness, protection and evidence surfaces from consuming
  the resolver result. Only the C1a preview may call `resolve_effective`.
- **Starting behavior at the anchor:**
  - `mneme audit` (`cli.py` `_cmd_audit`), setup readiness
    (`setup._load_validated_decisions` → `decision_count`,
    `readiness_counts`) and `protect list` (`cli._require_memory` →
    `protection.load_decisions` → `find_candidates`) all take
    `MemoryStore.decisions()` and filter lifecycle through
    `decision_index.lifecycle_governs` (C2).
  - On canonical memory, `MemoryStore.load()` also keeps the validated
    `canonical_index` from the same bytes; on section-less memory it is `None`.
  - The C3 feasibility probe showed that, with labels not supplied, the
    resolver's effective set equals the projected set on every C2 golden
    canonical form, with matching version ids.

## 2. What C3a is

C3a makes the **resolver result the source of the governed decision set** for
three reporting consumers, on canonical memory, with no observable change.

- **Architectural, not functional.** Users see nothing new. The value is that
  these consumers are bound to the resolver as decision authority, which a
  later explanation surface needs.
- **Not full §11 convergence.** C3a converges exactly three consumers.
  `audit_with_github_claim`, protection status/validate/activate, CI evidence
  matching as a standalone API, and every enforcement input stay unconverged
  and open on #497. No C3a result may be cited as Audit-family, DG1F or DG1
  completion.
- **No verdict or output changes.** Every output byte of the three consumers
  stays identical, including on section-less memory, v2 applicability and
  integrity findings.

## 3. Contract

### 3.1 Consumers in scope

| Consumer | Load site that changes | Must stay unchanged |
|---|---|---|
| `mneme audit` (text and `--json`) | `_cmd_audit` | `mneme.audit/v1`, ADR-026 formulas, exit codes |
| setup readiness | `setup._load_validated_decisions` (feeds `decision_count` and `readiness_counts`) | setup summary, activation record, newly created memory path |
| `protect list` | a **new** list-only loader in place of `_require_memory` → `load_decisions` | `protection.load_decisions` and `_require_memory`, which also feed `protect status/validate/activate`; the new loader keeps `_require_memory`'s missing-file and "failed validation" messages and exit 2 |

### 3.2 Explicitly excluded

- **`audit_with_github_claim`** (`github_evidence.py`): a public API that
  takes a caller-supplied decision list. Its signature and behavior are
  unchanged, and its convergence is recorded as open on #497. Including it
  later needs its own charter with a separately reviewed,
  compatibility-preserving authority contract.
- `protect status`, `protect validate`, `protect activate`, the persistence
  protection-install check, CI evidence matching as called by other paths,
  `mneme check`, hooks, the CI gates, MCP, and the C1a preview.

### 3.3 Deriving the governed set

- One shared helper derives the governed set from a loaded `MemoryStore`:
  - **Canonical memory** (`store.canonical_index` is not `None`): compute
    `resolve_effective(store.canonical_index, GovernanceContext())` with
    labels **not supplied**, and return the projected decisions from
    `store.decisions()` whose ids are in its effective set, **in projection
    order**.
  - **Section-less memory** (`store.canonical_index` is `None`): return
    `store.decisions()` unchanged; consumers keep the C2 behavior.
- **Same snapshot.** The index and the projected decisions come from one
  `MemoryStore.load()`. The helper never reads the memory file.
- **Labels are never supplied.** `GovernanceContext(labels=())` or any
  supplied labels are forbidden in C3a; a test fails if the helper passes
  anything other than the not-supplied context.
- **Errors are never wrapped or swallowed.** The helper is called after the
  load's `try/except`, so a resolver `ValueError` is never converted into
  `SetupError`, `ProtectionError` or an empty result (C2 charter §3.4).
- **Only the effective set is used.** Causes, trace, `superseded_by`,
  findings and applicability details are not surfaced or acted on. Integrity
  findings never exclude a decision and never fail a consumer.

### 3.4 Loader/resolver validation compatibility (gate before implementation)

C2 forbids catching a resolver `ValueError`. If `_validate` in
`decision_governance.py` could reject an index that
`load_persisted_decision_index` accepts, a previously working audit would
become an error. Before any production change:

- Show that every rejection in `_validate` is already enforced by the loader.
  Reading at the anchor suggests it is: the loader rejects duplicate decision
  ids and invalid lifecycle values, rejects rules whose decision or version
  does not resolve, rejects duplicate rule bindings, includes only
  active-version rules in `index.rules`, and builds `derived_rule_ids` from
  exactly those rules. The other raise path in `resolve_effective`
  (`_LIFECYCLE_CAUSES`) is covered by the lifecycle check. A pre-charter probe
  (9 repository documents with a `decision_index`, 834 loader-accepted random
  mutations, two hand-built version-binding cases) found no counterexample.
- Pin it with tests: (a) every canonical fixture in the repository loads and
  resolves without error; (b) duplicate decision ids, unknown lifecycle and
  rules naming an unknown decision or version, injected into a persisted
  document, are rejected by the loader; the lineage condition is shown
  impossible by construction (`derived_rule_ids` is computed by the loader,
  not stored), with tests that rules bound to a non-active version, alone or
  also bound to the active version, load and pass `_validate`; (c) a
  property-style check over the C2 golden forms and their mutations; (d) on
  every canonical golden, the effective set equals the projected ids.
- If any loader-accepted index fails `_validate`, C3a stops. The conflict is
  resolved by its own decision (tightening the loader is a behavior change);
  it is never caught and hidden.

### 3.5 Legacy and newly created memory

- Section-less memory keeps the C2 path (§3.3). This is a second **path**, not
  a second lifecycle **authority**: both paths read `lifecycle_governs`.
- Setup with newly created memory (no store, empty decision list) is
  unchanged.
- Removing the legacy path needs a legacy-memory deprecation decision under
  ADR-030 / ADR-031 §8, not C3a.

## 4. Required acceptance evidence

**Goldens first.** In a separate commit before any production change, extend
the C2 golden capture with:

- `mneme audit` and `protect list` with `--repo-root` pointing at a fixture
  repository that carries CI workflow evidence and declared test evidence;
- `run_setup` over existing memory for each golden form, and over newly
  created memory;
- `protect list` with a missing memory file and with memory that fails
  validation (message and exit 2).

All C2 goldens and the new goldens must reproduce byte for byte after the
change, on Linux CI and on a local Windows run, with captures from the
pre-change code and the C3a code identical.

**Negative and mutation tests** (each must fail when its guard is removed):

1. **Consumers follow the resolver.** With a test double that makes the
   resolver exclude a decision, `mneme audit`, readiness and `protect list`
   drop it; reverting a consumer to `store.decisions()` fails the test.
2. **Labels are not supplied.** The helper uses `GovernanceContext()`;
   switching to `labels=()` makes the v2 applicability golden fail.
3. **Single snapshot.** The index the helper resolves is the store's own
   object; the memory file is read once.
4. **Legacy unchanged.** Section-less and `items[]` goldens are unchanged, and
   the helper returns `store.decisions()` unchanged for them.
5. **Excluded surfaces unchanged.** `protection.load_decisions`,
   `protect status/validate`, `audit_with_github_claim` and `mneme check`
   outputs are byte-identical (existing goldens) and do not call the helper.
6. **Findings never block.** Conflict and dangling-`supersedes` forms produce
   the same output as canonical v1 for the three consumers.
7. **Validation compatibility** (§3.4 tests).

**Regression floor:** all DG1 tests, the full gate battery, the frozen Layer 1
benchmark (7/7), and an independent review against this section.

## 5. Explicit non-goals

C3a does not: change any output, schema, exit code or ADR-026 formula; surface
causes, trace or findings; converge `audit_with_github_claim`, protection
status/validate/activate, evidence matching APIs, `mneme check`, hooks, CI or
MCP; supply labels or read a context declaration; change legacy section-less
semantics or add an in-memory canonical view; tighten the loader; or change
benchmark fixtures or methodology.

## 6. Risks and controls

| Risk | Control |
|---|---|
| Resolver rejects memory the loader accepts | §3.4 gate before implementation; never caught |
| A supplied-empty context drops protective decisions | not-supplied context only; test 2 |
| A second read or snapshot | single `MemoryStore` load; test 3 |
| Output drift, including `--repo-root` and setup | goldens first, both platforms |
| Scope creep into protection writes or explanations | §3.2 exclusions; test 5; freeze amendment limited to the three consumers |
| `audit_with_github_claim` claimed as converged | recorded open on #497; §2 |
| Legacy behavior changed in passing | §3.5; test 4 |

## 7. Recording

After merge of the implementation, a #497 completion record lists the three
converged consumers, the evidence, and keeps open: `audit_with_github_claim`,
protection status/validate/activate, enforcement inputs, explanation output,
C1b, DG1B2 and DG1G.

## 8. Approval sequence

1. This charter: independent review and merge. Authorizes nothing to run.
2. `[layer1-freeze]` amendment: a separate PR authorizing resolver-result
   consumption by exactly the three consumers in §3.1, under §3.3, and
   restating every exclusion in §3.2. Separate approval.
3. Validation-compatibility evidence (§3.4) and goldens commit, then the
   implementation PR, with independent review against §4.
