# DG1F-C3b: `audit_with_github_claim` resolver-result feasibility (2026-11-09)

**Status: read-only assessment.** It decides whether the authenticated Audit
API can take its governed decision set from the resolver without weakening its
evidence trust contract, and names the smallest defensible increment. It
authorizes no implementation, schema change, freeze amendment or new
behavior.
**Anchor:** `MnemeHQ/mneme` `main` at `8dcb1ef9` (DG1F-C3a, #777). `mneme/` is
unchanged at `5e252a17`.
**Inputs:** [ADR-024](../adr/ADR-024-declared-test-evidence-ingestion.md),
[ADR-031](../adr/ADR-031-decision-governance-semantics.md) §11, the
[C3 feasibility assessment](2026-11-09-dg1f-c3-resolver-result-feasibility.md)
(#773), the [C3a charter](2026-11-09-dg1f-c3a-audit-resolver-charter.md)
(#774), the C3a freeze amendment (#775) and tracker
[#497](https://github.com/MnemeHQ/mneme/issues/497).

## 0. Answer

- **Feasible with exact parity.** An additive entry point that loads memory
  itself and passes `governed_runtime_decisions(store)` into the unchanged
  authenticated chain produces the same report as the list API given the same
  memory: byte-identical on all six C2 golden forms and on legacy, canonical
  v1 and canonical v2 memory where the authenticated claim is visible (§2).
- **The authority question has a clean answer: add, do not change.** Keep
  `audit_with_github_claim(decisions, …)` exactly as it is, as a
  caller-supplied, non-canonical list API, and add a separate entry point that
  takes a memory path and never accepts a decision list (§3).
- **The evidence trust contract is untouched in substance.** The
  authenticated chain (`verify_github_run`) does not read decisions; the
  decision list only selects which declared selectors are checked. Run head
  SHA binding, artifact checks and the `authenticated_ci_claim` ceiling are
  unchanged on both paths. C3b inherits, unchanged, the existing caller
  overrides for repository identity (`owner`/`repo`, `base_url`) (§4).
- **ADR-024 wording must change.** ADR-024 (§Trust boundary) and
  `github_evidence.py:26` and `:416` name `audit_with_github_claim()` as the
  sole supported authenticated operation. A second entry point needs that
  wording amended to name both, in addition to the charter and freeze
  amendment (§3).
- **Closure must be defined by entry point, not by "Audit family".** Every
  entry point where Mneme loads memory would then use the resolver; the
  list-taking public library APIs (`audit_with_github_claim(decisions, …)`,
  `generate_protection_report`, `assess_protection`, `match_ci_evidence`)
  report on caller lists by contract and stay outside the claim (§6).
- **Recommendation: GO, narrowly, for C3b** (§7), subject to its own charter,
  an ADR-024 wording amendment and a `[layer1-freeze]` amendment. No in-package code calls this API today, so
  the value is completing the Mneme-loaded reporting entry points; priority
  is the owner's call.

## 1. Method

Code reading at `8dcb1ef9` (`mneme/github_evidence.py`, `mneme/evidence.py`,
`mneme/enforcer.py`, ADR-024) and two in-process probes using the existing
fake-GitHub harness in `tests/test_github_evidence.py` (`FakeGitHub`,
`_install_fake`, `_git_repo`; no network):

1. the six C2 golden memory forms in a real git repository, comparing
   `audit_with_github_claim(store.decisions(), …)` with
   `audit_with_github_claim(governed_runtime_decisions(store), …)`;
2. the harness's own deterministic decision with a declared selector, as
   legacy, canonical v2 and canonical v1 memory, where the authenticated
   claim produces a visible evidence source.

## 2. Probe results

| Memory | Canonical index | Reports identical | Authenticated claim visible |
|---|---|---|---|
| C2 canonical v1 / v2 + applicability / conflict / dangling | yes | **yes** | no (the selector-bearing decision is rule-protected) |
| C2 section-less / `items[]` | no | **yes** | no (the selector is rule-protected, and in the section-less form also ambiguous: superseded `C2-OLD` declares it) |
| harness decision, legacy | no | **yes** | yes: `test:ci-authenticated:<selector>@<sha>` |
| harness decision, canonical v2 | yes | **yes** | yes |
| harness decision, canonical v1 | yes | **yes** | yes |

Two consequences for evidence design:

- The C2/C3a corpus cannot show the authenticated claim; C3b goldens need a
  form with a selector-bearing decision that is not otherwise protected (as in
  the harness).
- The commit SHA differs per run (commit timestamps), and it appears in
  evidence sources. Goldens must pin commit identity and dates
  (`GIT_AUTHOR_DATE`, `GIT_COMMITTER_DATE`, fixed user) or normalize the SHA
  as an exact token.

## 3. API contract and authority

**Today.** `audit_with_github_claim(decisions, repo_root, run_id, …)`
(`github_evidence.py:403`) authenticates the run, then calls
`_verify_test_evidence(decisions, repo_root, None, claim)` and
`_build_report(decisions, …)`. The decision list is whatever the caller
passes; `tests/test_github_evidence.py` builds `Decision` objects directly.
No in-package caller exists.

**Options considered.**

| Option | Shape | Verdict |
|---|---|---|
| A. Additive memory-loading entry point | new function, e.g. `audit_with_github_claim_from_memory(memory, repo_root, run_id, …)`, same keyword parameters otherwise | **recommended**: existing signature untouched; the new path never accepts a list, so a caller cannot substitute a non-canonical set |
| B. Keyword `memory=` on the existing function | mutually exclusive with `decisions` | rejected: one function with two authority sources; easy to misuse |
| C. Accept `MemoryStore` in place of the list | union type | rejected: changes an existing parameter's meaning; a caller-built store is not a validated load |

**Authority under option A.**

- The new entry point loads `MemoryStore(memory)` itself with the existing
  validation and derives the set with `governed_runtime_decisions(store)`: one
  validated snapshot, labels not supplied, projection order, resolver errors
  not caught (C3a contract).
- The existing list API keeps its contract and is documented as reporting on
  a caller-supplied, non-canonical list.
- **Open design point for the charter: which memory revision.** Like
  `mneme audit --memory`, option A reads the working-tree file, while the
  authenticated claim is bound to repository HEAD. A working tree with
  uncommitted memory changes would pair HEAD-bound evidence with
  non-HEAD decisions. Binding memory to the audited commit (reading the blob
  at HEAD, or refusing a dirty memory file) is stronger but is new behavior
  that overlaps CI1's trusted-revision work. Recommended for C3b: working-tree
  memory with parity to `mneme audit`, the gap recorded; HEAD binding as a
  separate decision.
- **Also open: memory containment.** Neither path requires the memory file to
  lie inside `repo_root`. Memory from another repository would pair foreign
  decisions with this repository's HEAD-bound claim (selector files resolve
  against `repo_root`). The charter should decide whether the new entry point
  requires containment.
- **Documentation that names a single authenticated operation:** ADR-024
  (§Trust boundary: "reached solely by `audit_with_github_claim()`, which is
  the one supported public authenticated operation"), the
  `github_evidence.py` module docstring (line 26) and the function docstring
  (line 416). The `governed_runtime_decisions` docstring
  (`decision_governance.py:373`) lists its three C3a callers. All four must be
  updated by C3b; the ADR-024 change is an ADR amendment, not only a freeze
  amendment.

## 4. Evidence trust contract

| Element | Where | Affected by C3b? |
|---|---|---|
| repository identity: resolved from the origin remote unless the caller supplies `owner`/`repo` (existing, unpinned override; `head_repository` check skipped when empty; `base_url` caller-chosen; see the `cli.py` trust-boundary TODO) | `verify_github_run` | no: inherited unchanged; pinning is out of scope |
| workflow run exists and belongs to the repository | `verify_github_run` | no |
| run head SHA == repository HEAD | `audit_with_github_claim` → `_repo_head`, `verify_github_run` | no |
| artifact name, expiry, authenticated download | `verify_github_run` | no |
| evidence document schema and `repository_sha` == run head SHA | `verify_github_run` | no |
| `authenticated_ci_claim` ceiling, never `verified` | `_verify_test_evidence` | no |
| which declared selectors are checked, and selector ambiguity | `_verify_test_evidence(decisions, …)` | **input only**: the governed set equals the projected set on canonical memory and is unchanged on legacy memory, so results are identical (§2) |
| no trust-bearing public parameter (ADR-024) | public API | preserved in substance: the new entry point adds no trust-bearing parameter; ADR-024 §Trust boundary and `github_evidence.py:26,416` name `audit_with_github_claim()` as the sole authenticated operation, so C3b must amend that wording (and `decision_governance.py:373`) to name both entry points |
| selector ambiguity ignores lifecycle | `_verify_test_evidence` (`evidence.py:404-415`) | no: unchanged on both paths; on canonical memory non-active decisions are already absent |

## 5. Parity evidence a charter would require

- **Goldens first**, from the pre-change list path: authenticated reports
  over the six C2 forms plus claim-visible forms (legacy, canonical v1,
  canonical v2), with pinned commit identity and dates.
- **After the change:** the list path reproduces its goldens unchanged, and
  the new entry point reproduces the same goldens when given the same memory.
- **Failure paths:** the existing forged-run, wrong-repository, SHA-mismatch
  and artifact tests (`tests/test_github_evidence.py`) run against both entry
  points with identical outcomes; a memory that fails validation is refused by
  the new entry point before any GitHub call, and a resolver `ValueError` is
  never caught.
- **Platforms:** Linux CI plus a local Windows run, as for C2/C3a.

## 6. Closure

After C3b, every entry point where **Mneme loads project memory** to build an
Audit report would use the resolver result:

| Entry point | Loads memory itself | Converged |
|---|---|---|
| `mneme audit` | yes | C3a |
| `mneme setup` readiness | yes | C3a |
| `mneme protect list` | yes | C3a |
| new authenticated memory entry point | yes | C3b |
| `audit_with_github_claim(decisions, …)` | no (caller list) | **outside, by contract** |
| `generate_protection_report`, `assess_protection`, `match_ci_evidence`, `verify_test_evidence`, `find_candidates`, `readiness_counts`, `assess_readiness` | no (caller list) | **outside, by contract** |
| `protect status/validate/activate`, and the public `protection.load_decisions(memory_path)` they use | yes | open (separate decision) |
| enforcement inputs (`check`, hooks, CI gates, MCP) | yes | open (C1b territory) |

The claim C3b supports is "Mneme-loaded Audit-report entry points use the
resolver result", not "the Audit family" or §11.

## 7. Go / no-go

| Candidate | Verdict | Reason |
|---|---|---|
| C3b: additive memory-loading authenticated entry point, parity, labels not supplied | **GO** (charter + freeze amendment) | feasible with exact parity; evidence chain untouched; no trust gap |
| Changing `audit_with_github_claim(decisions, …)` | NO-GO | breaks the existing public contract and its tests |
| HEAD-bound memory for the authenticated path | not in C3b | new behavior; separate decision overlapping CI1 |
| Explanation output, protection paths, enforcement inputs, C1b, DG1B2 | unchanged | deferred as before |

## 8. Non-claims

This assessment changes no code and approves nothing. The probes ran on
Windows with a faked GitHub transport; no live GitHub run was used. Probes
passed `owner`/`repo` explicitly, so origin-remote identity resolution was not
exercised. An independent fact-check re-ran the probes (identical results,
including a superseded decision sharing a selector) and its corrections are
applied: ADR-024 single-operation wording, inherited identity overrides,
memory containment, and the missed public APIs in §6. C2 and C3a remain unreleased.
