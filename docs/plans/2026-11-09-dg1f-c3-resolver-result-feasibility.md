# DG1F-C3: ADR-031 §11 resolver-result convergence feasibility (2026-11-09)

**Status: read-only assessment.** It answers whether runtime consumers can act
on the shared resolver result without changing enforcement or observable
behavior, and names the smallest defensible next increment. It authorizes no
implementation, schema change, freeze amendment or new behavior.
**Anchor:** `MnemeHQ/mneme` `main` at `b719dc96` (DG1F-C2, #770).
**Inputs:** [ADR-031](../adr/ADR-031-decision-governance-semantics.md) §6, §7,
§11; [C2 charter](2026-11-08-dg1f-c2-lifecycle-convergence-charter.md) (#764);
the C2 freeze amendment (#767) in
[`layer1-freeze-e73ff7d.md`](../architecture/layer1-freeze-e73ff7d.md);
[DG1 v0.11.0 reconciliation](../validation/dg1-v0110-architecture-reconciliation-2026-11-08.md)
(#762); tracker [#497](https://github.com/MnemeHQ/mneme/issues/497) C2
completion record.

## 0. Answer

- **Feasible with exact parity, on canonical memory, with context not
  supplied.** On every C2 golden canonical form, the resolver's effective set
  under `GovernanceContext()` equals the projected runtime set, and version
  ids align (§2). A consumer can take its decision set from the resolver
  result, from the same validated snapshot, and produce byte-identical output.
- **Parity convergence has no observable effect**, provided
  `resolve_effective` never raises on memory that `MemoryStore.load()`
  accepts (§5). On canonical memory `store.decisions()` already holds only
  lifecycle-active decisions, so the resolver filter removes nothing on any
  golden. It binds consumers to the resolver result, which closes ADR-031 §11
  for those consumers and is the prerequisite for any explanation surface, but
  users see nothing new.
- **The resolver's real added value (causes, `superseded_by`, findings) needs
  an output change.** That is a separate output-contract decision, not part of
  parity convergence.
- **Recommendation: GO, narrowly, for C3a** (§6): `mneme audit`, readiness
  and `protect list` candidates take their governed set from the resolver
  result on canonical memory, with context not supplied, with output pinned
  by goldens. The public `audit_with_github_claim` API is **excluded by
  default** (it receives a caller-supplied decision list, not a store with the
  canonical snapshot); its convergence stays open on #497 unless a charter
  adds a separately reviewed, compatibility-preserving authority contract.
  C3a needs its own charter and `[layer1-freeze]` amendment.
- **NO-GO for now:** protection validate/activate (authority write path),
  enforcement inputs (`mneme check`, hooks, CI, MCP), any supplied-labels
  consumption (that is C1b), and any new explanation output.

## 1. Questions and method

Six questions from the owner's 2026-11-09 brief: consumer boundaries,
canonical authority, legacy compatibility, output parity, trust, and scope.
Method: code reading at `b719dc96`, and an in-process probe over the six
committed C2 golden memory forms (`tests/fixtures/dg1f_c2/memory/`) comparing
`resolve_effective(store.canonical_index, …)` with `store.decisions()` from the
same `MemoryStore.load()`.

## 2. Probe results

| Form | Resolver available | Effective set == projection, labels not supplied | Same, labels supplied empty | Findings | Ineffective (cause) |
|---|---|---|---|---|---|
| canonical v1 | yes | **yes** | yes | none | C2-DEP deprecated; C2-OLD, C2-OLDPICKLE superseded |
| canonical v2 + applicability | yes | **yes** | **no** (C2-LIT dropped as `not_applicable`) | none | same |
| canonical + supersession conflict | yes | **yes** | yes | `supersession_lifecycle_conflict` | same |
| canonical + dangling `supersedes` | yes | **yes** | yes | `dangling_supersedes` | same |
| section-less legacy | **no** (`canonical_index` is `None`) | n/a | n/a | n/a | n/a |
| legacy `items[]` | **no** | n/a | n/a | n/a | n/a |

`decision_version_id` in every effective resolution equals `Decision.version_id`
of the projected runtime decision.

Two consequences:

- Consumers must use the **not-supplied** context. A supplied-empty context
  silently drops applicability-scoped decisions, which ADR-031 §11 forbids an
  adapter to do. C2 made this distinction available.
- Integrity findings do not change the effective set, so a consumer that uses
  only the effective set is unaffected by them (C2 charter §3.4).

## 3. Consumer boundaries

| Consumer | Entry | Decision source today | Resolver-result parity feasible? | Value without output change | Risk |
|---|---|---|---|---|---|
| `mneme audit` | `cli.py:974` → `generate_protection_report` → `_build_report` | `store.decisions()` | **yes** (canonical) | none observable | low: read-only report |
| readiness (setup) | `setup.py:171`, `:276` → `readiness_counts` | `store.decisions()` | **yes**, via the same report | none observable | low |
| `protect list` candidates | `cli.py:1060` → `find_candidates` → report | `cli.py:_require_memory` (1024-1046) → `store.decisions()` | **yes** | none observable | low: read-only |
| `github_evidence` report | `audit_with_github_claim` (`github_evidence.py:403`, library API, no in-package caller) → `_build_report` (`:439`) | caller-supplied list | **yes** | none observable | low, but authenticated-evidence path; keep identical |
| CI evidence matching | `evidence.py` `match_ci_evidence` | caller list | yes | none | low; selector-ambiguity semantics must stay (C2 test 4) |
| `protect status` | `protection.py:823` → `load_decisions` → `assess_protection` | `store.decisions()` | parity yes | none | medium: shares the loader with validate/activate |
| `protect validate` / precheck | `cli.py:1143` `find_decision` → `activation_precheck` | `store.decisions()` | parity yes; a resolver cause instead of "not found" is **a message change** | causes would help users | medium |
| `protect activate` | `protection.py:710` → canonical write; persistence check `decision_index_persistence.py:1341` | raw canonical document | parity yes; acting on findings would **refuse new cases** | refuse activation on integrity findings | **high: authority write path** |
| `mneme check`, hooks, CI gate, MCP | projection → `check_prompt` | `store.decisions()` | parity yes with not-supplied context; anything else is C1b | none | **out of scope: enforcement input** |

The four Audit-family consumers share `_build_report`, but it receives a list
of decisions, so convergence happens at each load site: `_cmd_audit`,
`_require_memory`, `setup._load_validated_decisions`, and callers of
`audit_with_github_claim`. `protection.load_decisions` also feeds
`protect status/validate/activate`, which are out of scope, so C3a must use a
separate loader rather than change it. `audit_with_github_claim` takes
caller-supplied decisions, so converging it changes a public signature; C3a
may instead leave it on the caller's list and record that.

## 4. Authority, legacy, parity and trust

- **Canonical authority: single snapshot is available.** `MemoryStore.load()`
  keeps the validated `canonical_index` next to the projected decisions from
  the same bytes; the C1a preview already reuses it
  (`test_uses_same_snapshot_as_enforcement_not_second_file_read`). C3a must
  take both from one `MemoryStore` load and never reread the file. Gap:
  `protection.load_decisions` and `setup.py:171` return only
  `store.decisions()`, so their signatures must expose the store (or the
  index) to the callers.
- **Lifecycle authority stays single.** Since C2, projection and the resolver
  read the same predicate, so the resolver's lifecycle result and projection
  cannot diverge. C3a adds no lifecycle rule.
- **Legacy compatibility needs an explicit dual path.** The resolver refuses
  section-less memory. On that path consumers keep the C2 behavior (status
  from the file, filtered by `lifecycle_governs`). This is a second *path*, not
  a second *authority*; it must be named in the charter, with a negative test
  that legacy outputs are unchanged. Removing it needs a legacy-memory
  deprecation decision (ADR-030 / ADR-031 §8), not C3.
- **Output parity is only partly pinned today.** The C2 goldens pin
  `mneme audit` (text and JSON), `protect list` and `readiness_counts` across
  all six forms with `repo_root` unset. `github_evidence` is pinned only
  through `_build_report(decisions, None, None)`, not `audit_with_github_claim`
  with authenticated results. `--repo-root` evidence paths and `run_setup` are
  not pinned. C3a must add goldens for these, captured before any code change.
  CI runs on Linux only; the Windows evidence is a local run. Any change to an
  existing golden is a scope violation.
- **Trust.** With context not supplied, no labels are read, so no trusted
  context source, revision verification or anti-substitution control is
  needed. Any consumer that supplies labels inherits every C1b prerequisite
  (charter #493 §3) and is out of scope.

## 5. Risks

| Risk | Where | Control for C3a |
|---|---|---|
| A supplied-empty context drops protective decisions | any consumer | mandate `GovernanceContext()`; mutation test that supplied-empty would change goldens |
| A second file read or snapshot | load paths | one `MemoryStore` load; test that the resolver index is the store's object |
| Findings turned into errors or exclusions | report consumers | consumers use only the effective set; findings ignored, never raised |
| Legacy behavior changed in passing | section-less path | dual path named; C2 legacy goldens unchanged |
| Output drift | the three C3a consumers | C2 goldens byte-identical, both platforms |
| Scope creep into explanations or activation | Audit, protection | charter non-goals; freeze amendment restricted to the three consumers |
| Resolver `ValueError` on memory that loads fine turns a working audit into a crash (the C2 freeze forbids catching it) | report consumers | prove `_validate` (`decision_governance.py`) is implied by `load_persisted_decision_index`, or test mutated indexes the loader accepts |
| Setup with newly created memory has no store and no index (`setup.py`, empty decisions) | readiness | dual path covers it; golden for `run_setup` |
| Unobservable change mistaken for progress | programme | record C3a as §11 closure for the three named consumers only, not the whole Audit family or DG1F |
| Public API left unconverged but claimed as converged | `audit_with_github_claim` | explicit exclusion recorded on #497, or a reviewed authority contract (§6) |

## 6. Smallest defensible next increment: C3a

**C3a: Audit-family resolver-result consumption (parity only).**

- **Scope:** three `_build_report` consumers that load memory themselves:
  `mneme audit`, readiness (setup) and `protect list` candidates. On canonical
  memory, the governed decision set is the projected decisions whose ids are
  in `resolve_effective(store.canonical_index, GovernanceContext()).effective`,
  from the same `MemoryStore` load. Section-less memory keeps the C2 path.
- **`audit_with_github_claim` acceptance condition (explicit).** The C3a
  charter must choose one:
  1. **Exclude it (recommended default).** The public API keeps its
     caller-supplied decision list unchanged, and its resolver-result
     convergence stays an open item on #497. C3a then claims §11 convergence
     for the three consumers above only, never for "the Audit family".
  2. **Include it** only with a separately reviewed, compatibility-preserving
     authority contract (for example an additive entry point that takes the
     validated store or index while the existing signature keeps working),
     plus goldens for the authenticated-results path.
- **Unchanged:** every output byte (C2 goldens), `mneme.audit/v1`, ADR-026
  formulas, enforcement inputs, protection validate/activate, evidence
  matching semantics, C1a preview.
- **Required evidence:** new goldens for `--repo-root` evidence paths and
  `run_setup` (and, only under option 2, `audit_with_github_claim` with
  authenticated results), captured before code; C2 goldens unchanged on Windows and Linux; proof that
  the resolver cannot raise on memory the loader accepts; mutation
  tests showing the consumer follows the resolver result (for example, a
  resolver that excludes a decision changes the report) and that a
  supplied-empty context would be caught; single-snapshot test; legacy
  dual-path test; DG1 tests, full gate battery, benchmark 7/7; independent
  review.
- **Authorization needed:** a C3a behavioral charter and a `[layer1-freeze]`
  amendment. The DG1B1/C1a/C2 amendments prohibit Audit, readiness,
  protection and evidence surfaces from consuming the resolver result.
- **What it buys:** §11 convergence for `mneme audit`, readiness and
  `protect list` candidates, with no observable change; the binding that a
  later explanation surface needs. It does **not** claim full Audit-family
  convergence while `audit_with_github_claim` is unchanged.

**Deferred, each needing its own decision:**

1. **Explanation output** (why a decision is not counted: cause,
   `superseded_by`, findings) in Audit: an output-contract decision
   (`mneme.audit/v1` and ADR-026 boundary), after C3a.
2. **Protection validate/activate on resolver results:** authority write path;
   includes the sixth lifecycle check at `decision_index_persistence.py:1341`.
   Only after C3a, with its own charter.
3. **Enforcement-input consumption:** parity-only would change nothing;
   anything beyond is C1b and stays deferred with its trust prerequisites.

## 7. Go / no-go

| Candidate | Verdict | Reason |
|---|---|---|
| C3a (`mneme audit`, readiness, `protect list`), parity, not-supplied context | **GO** (subject to charter + freeze amendment) | feasible, provable with existing goldens, no trust gap, low risk |
| `audit_with_github_claim` convergence | open; excluded from C3a by default | public API takes caller-supplied decisions; needs a reviewed authority contract |
| Explanation output | NO-GO now | output contract change; needs its own decision after C3a |
| Protection validate/activate | NO-GO now | authority write path; behavior or message changes |
| Enforcement inputs (`check`, hooks, CI, MCP) | NO-GO | no parity value; anything more is C1b |
| Supplied-labels consumption anywhere | NO-GO | requires C1b trust prerequisites |

C1b and DG1B2 stay deferred. DG1F is not complete after C3a: protection,
explanation and enforcement-input convergence remain open under #497.

## 8. Verification of this assessment

An independent read-only check re-ran the §2 probe (identical results),
confirmed every cited entry point and the freeze prohibition, and corrected
three points before publication: golden coverage is partial (§4), convergence
happens per load site rather than once in `_build_report` (§3), and two risks
were missing (resolver errors on loadable memory; setup with new memory, §5).
