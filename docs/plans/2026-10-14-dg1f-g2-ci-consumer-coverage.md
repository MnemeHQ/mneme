# DG1F — G2: CI-consumer coverage audit (read-only preflight)

**Status:** source-inspected **evidence inventory**, not a charter, approval, or
implementation plan. No CI workflow, runtime, schema, or benchmark change is
authorized or made by this document.
**Source anchor:** `MnemeHQ/mneme` `main` at
`1033f24e83b92b04b85ee9d041635241ad462445` (G4, PR #507).
**Governing contracts:** [ADR-017](../adr/ADR-017-enforcement-scope-vs-retrieval-scope.md),
[ADR-021](../adr/ADR-021-shell-preflight-and-stop-session-delta.md), the merged
[C1 charter](2026-10-14-reliable-enforcement-c1-verdict-consistency-charter.md),
and the [blocking-semantics matrix](2026-10-14-dg1f-adversarial-blocking-semantics-matrix.md)
(whose G2 row this closes).

## 1. Method

- Enumerated `.github/workflows/*.yml` and located every step that invokes Mneme
  (directly `python -m mneme.cli` / `mneme ...`, or indirectly through
  `scripts/run_test_battery.py`).
- Read the branch ruleset (`rulesets/22196895`) to separate **required status
  checks** (merge-blocking) from advisory workflows.

**Required status checks (merge-blocking), current ruleset:**

```
gate (PR battery)
Scan docs/scripts for mojibake + BOM
Validate PR execution provenance
Verify install commands name mneme-hq
mneme check --mode warn
```

## 2. Coverage matrix

`Blocking` = whether a failure of that workflow's check blocks the merge (a
required status check). `Governance?` = whether the workflow runs Mneme's
decision governance (`mneme check`).

| Workflow | Governance? | Blocking? | What it actually runs | Failure / timeout / untrusted / missing-memory behavior |
|---|---|---|---|---|
| `mneme-check.yml` | **Yes** — `mneme check --mode warn` over changed `mneme/`, `docs/adr/`, `.mneme/`, `scripts/` files | **Required check name, but advisory in effect** | `python -m mneme.cli check … --mode warn` per file; posts a sticky PR comment | `--mode warn` exits 0 for **every** verdict (L6-8); the step adds `\|\| true` (L129) and never `exit 1` on FAIL/WARN; UNKNOWN is surfaced as a callout only (L150-152). **Missing memory → the whole step is skipped** (`if: present == 'true'`, L60/L98) and the job passes. No files in scope → `exit 0` (L113-116). |
| `tests.yml` → `gate (PR battery)` | No | **Yes (required)** | `python scripts/run_test_battery.py gate` (pytest gate manifest) | Blocks on any gate-test failure. Tests **code**, not a governance verdict on a target artifact. |
| `tests.yml` → `main` / `pytest-langchain` / `release` | No | No (push/dispatch) | `run_test_battery.py main` / langchain / release | Not run on PRs. |
| `provenance-check.yml` | No | **Yes (required)** | `scripts/check_pr_provenance.py` | Blocks on a missing/malformed Execution provenance block. |
| `encoding-check.yml` | No | **Yes (required)** | `scripts/check_encoding.py` | Blocks on mojibake/BOM in `docs`/`scripts`. |
| `install-command-check.yml` | No | **Yes (required)** | `scripts/check_install_command.py` | Blocks on an unqualified install command naming the wrong distribution (ADR-005). |
| `architecture-docs-check.yml` | No | No (advisory) | `scripts/check_architecture_docs.py` | Runs on PR/push but is **not** in the required set. |
| `mcp-directory-maintenance.yml` | No | No (scheduled/manual) | `check_mcp_directory_listings.py` | Registry hygiene. |
| `release-smoke.yml` | No | No (release/dispatch) | installs the published package, runs `mneme setup` / `--help` | Release smoke; no `mneme check`. |
| `release.yml` / `publish-mcp-registry.yml` | No | No (tag/dispatch) | publish/release | No governance. |

## 3. Findings

1. **The only CI surface that runs Mneme governance is `mneme-check.yml`, and it
   is advisory.** It is deliberately `warn` mode: the CLI returns exit 0 for
   every verdict, the step is wrapped in `|| true`, and no branch exits 1 on a
   FAIL. Its **required-check name does not make a governance FAIL block a
   merge** — only an infrastructure failure of the job itself would.
2. **Missing canonical memory is a silent pass in CI.** When
   `.mneme/project_memory.json` is absent on the branch, the run step is skipped
   (`if: present == 'true'`) and the check passes — consistent with the S1
   silent-skip behavior in the [blocking-semantics matrix](2026-10-14-dg1f-adversarial-blocking-semantics-matrix.md),
   but here it means a PR to a repo with no memory gets no governance signal and
   no diagnostic.
3. **UNKNOWN is surfaced, not enforced.** The workflow counts UNKNOWN verdicts
   and emits a warning callout, but the job still passes (matching ADR-021's
   fail-open transport policy and the C1 charter's "no silent PASS" *visibility*
   intent, without blocking).
4. **No CI workflow enforces a governance verdict as a merge gate.** The
   required checks that do block are repository hygiene (encoding, install,
   provenance) and the test battery; none is a decision-governance gate on the
   PR's artifact.
5. **Path-scoped, so many PRs get no governance check at all.** Only changes
   under `mneme/`, `docs/adr/`, `.mneme/`, `scripts/` are checked; other paths
   produce "No files in scope" and pass.

## 4. Remaining gaps and recommended follow-up (not implemented here)

| ID | Gap | Recommended follow-up |
|---|---|---|
| **C1** | A governance **FAIL** in CI is advisory only; nothing blocks a merge on it. | Decide (separately) whether a strict-mode CI gate for a narrow path set should exist; that is an enforcement-input change and would need its own charter + `[layer1-freeze]` amendment (ADR-031 §7). Not authorized here. |
| **C2** | **Missing memory is a silent CI pass** (step skipped). | An offline test/assertion that a missing-memory CI invocation is reported as *inactive/unavailable*, not silently green. Ties to G3 (missing-memory policy). |
| **C3** | No test pins the workflow's verdict parsing / UNKNOWN handling. | A small test that the `mneme-check.yml` parsing treats a FAIL/UNKNOWN payload as non-blocking and surfaces it (characterization only). |
| **C4** | `architecture-docs-check.yml` runs but is not a required check. | Confirm intent (advisory vs required); no change without a decision. |

## 5. Bottom line

- **CI does not currently block on a governance verdict.** The single
  `mneme check` consumer is explicitly advisory (`warn`, `|| true`, no exit 1),
  and missing memory skips it silently.
- **What CI does block on** is repository hygiene and the test battery — not
  decision enforcement on the PR's artifact.
- This audit changes nothing and authorizes nothing. **G1 (host-harness
  blocking), G3 (missing-memory policy), ADR-033, DG1F-C1b and DG1B2 remain
  outside G2.**
