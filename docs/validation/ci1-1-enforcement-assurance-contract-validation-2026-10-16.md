# CI1.1: Enforcement assurance, contract and trust-boundary validation (read-only)

**Status:** read-only validation record. **Nothing here is changed or
authorized.** No workflow, ruleset, runtime, schema, memory or roadmap change is
made. No live experiment is run. Strict mode is not enabled anywhere. This
record does not stand in for the CI1.3 experiment contract, the G2 C1 charter,
a `[layer1-freeze]` amendment or ADR-033.
**Source anchor:** `MnemeHQ/mneme` `main` @
`ac698985d807910542f1c016a66be1031d479d25` (#528).
**Ruleset anchor:** `rulesets/22196895` (`main-pr-only`), `updated_at`
`2026-09-12T08:51:30-05:00`, read 2026-10-16. Snapshot:
[`ruleset-22196895.json`](artifacts/ci1-1-enforcement-assurance-2026-10-16/ruleset-22196895.json).
**Builds on (does not repeat):**
[G2 CI-consumer coverage audit](../plans/2026-10-14-dg1f-g2-ci-consumer-coverage.md)
(anchored at `1033f24e`),
[consumer trust-boundary inventory](../plans/2026-10-14-dg1f-consumer-trust-boundary-inventory.md),
[blocking-semantics matrix](../plans/2026-10-14-dg1f-adversarial-blocking-semantics-matrix.md),
[ADR-017](../adr/ADR-017-enforcement-scope-vs-retrieval-scope.md),
[ADR-029](../adr/ADR-029-enforcement-evidence-binding-semantics.md),
[ADR-031](../adr/ADR-031-decision-governance-semantics.md).
**Related open items:** #278 (reusable Action as a thin CI adapter, OPEN),
#483 (ADR-033 + C0 charter, draft, proposed).

## 1. Question

CI1 asks whether a violation of an authoritative, enforceable Mneme decision
stops a PR from merging into a protected branch. CI1.1 only establishes the
starting position:

1. Which decision memory and evaluator CI actually trusts today.
2. What the CLI contract gives a CI adapter (verdict, exit code, completeness).
3. Which check the ruleset requires, and how a merge can still go through.
4. Whether a PR can swap out its own policy and still get a green check.
5. What the CI1.3 live experiment needs before anyone authorizes it.
6. Which parts of the contract and CI1.2 fixtures can be reused on CI systems other than GitHub Actions.

## 2. Method

- Re-read `.github/workflows/mneme-check.yml` at the anchor (blob
  `d5fd1f4e`). It is unchanged since G2's anchor (`git diff 1033f24e
  ac698985` is empty for this file), so G2's line numbers still apply.
- Read `mneme/cli.py` `_cmd_check`, `_EXIT_CODES_BY_MODE`, `_error_exit`,
  `_check_payload`, and `mneme/enforcer.py` `_enforcement_scope` /
  `check_prompt`.
- Read `.mneme/project_memory.json` (blob `5002a6c0`) `decision_index`.
- Read the live ruleset through the REST API (`gh api
  repos/MnemeHQ/mneme/rulesets/22196895`).
- Cross-check the repository's [canonical integration support matrix](../integrations/README.md)
  and [#278](https://github.com/MnemeHQ/mneme/issues/278): GitHub Actions
  and GitLab CI have CLI-based reference patterns; a reusable GitHub Action
  remains proposed and is not a second enforcement engine. The portability
  section below is a requirement and platform inventory, not validation.

Nothing was executed against CI. Every claim about how GitHub behaves at merge
time is marked **to prove in CI1.3** unless it comes straight from the ruleset
JSON.

## 3. Confirmed current position (re-verified at the anchor)

G2's findings 1–6 still hold at `ac698985`. In short: the only governance
consumer is `mneme-check.yml`. It runs `--mode warn` with `|| true` (L129).
Missing memory skips the run step (L60–64, L98). No files in scope means
`exit 0` (L113–116). The path filter is `mneme/`, `docs/adr/`, `.mneme/` and
`scripts/` (L82).

## 4. CLI contract available to a CI adapter

| Signal | Source | Value |
|---|---|---|
| Verdict exit codes | `cli.py` `_EXIT_CODES_BY_MODE` | strict: PASS 0, WARN 1, FAIL 2. warn: all 0 |
| Incomplete evaluation | `_cmd_check` | prints `Result: INCOMPLETE` and returns **2 in every mode** (also under `--json`) |
| Pre-execution error (missing `--input` or `--memory` file) | `_error_exit` | `ERROR:` on stderr, empty stdout, returns **2** |
| Uncaught exception | Python | returns **1** |
| Machine verdict | `--json`, `schema: mneme.check/v1` | `verdict`, `mode`, `evaluation_complete`, per-rule `applicability[]` and `violations[]` carrying `rule_id` and `decision_version_id` |
| Default mode | argparse help (L1938) | `strict` |

**Finding F1: exit codes alone are ambiguous.** In strict mode, `2` can mean
FAIL, INCOMPLETE or a pre-execution error, and `1` can mean WARN or a crash.
`_check_payload`'s own docstring says so. A CI gate that keys on `$? != 0`
would happen to block all of these, but it could not tell a governance FAIL
from an unevaluated run. That breaks the CI1 criteria "never represented as a
verified governance PASS" and "clearly reported as unevaluated". An adapter
must instead read `mneme.check/v1` and require `evaluation_complete: true`,
and treat a non-parseable or empty stdout as "no verdict". This is the same
contract #278 Step 0 asks for. CI1 needs no new CLI behavior to use it.

**Finding F2: canonical identifiers exist; complete ADR-029 evidence does not.**
`applicability[]` and `violations[]` carry `rule_id` and `decision_version_id`,
so a CI adapter can preserve the evaluated decision version and rule identity
without inventing its own IDs. Those fields alone do **not** satisfy ADR-029:
CI1.4 must also bind the exact subject/change, applied applicability,
attributable outcome, evaluated configuration, control version and provenance
to the **same** evaluation. These dimensions are not all established by the
current `mneme.check/v1` payload or today's PR comment, which parses only the
human `Result:` line (G2 C3). Any missing binding remains unproven evidence;
CI1.4 must identify how it is observed without asserting a core change is
already unnecessary for *every* evidence field.

## 5. Ruleset and required-check position

From the ruleset snapshot:

| Property | Value | Consequence |
|---|---|---|
| Target | `refs/heads/main`, `enforcement: active` | applies to the protected branch |
| `bypass_actors` | `[]`, `current_user_can_bypass: never` | no ruleset bypass actor is configured |
| Allowed merge methods | `squash` only | n/a |
| `required_approving_review_count` | `0` | **merge needs no human approval** once the required checks pass |
| `require_extra_approval_for_unattributed_changes` | `true` | does not replace an approval count of 0 for the PR author's own changes |
| Required checks | `gate (PR battery)`, `Scan docs/scripts for mojibake + BOM`, `Validate PR execution provenance`, `Verify install commands name mneme-hq`, **`mneme check --mode warn`**, each with `integration_id: 15368` | the governance job is required **by display name** |
| `strict_required_status_checks_policy` | `false` | the PR branch does not have to be up to date with `main` before merging |

**Finding F3: the required context is pinned to the job display name.** The
required context is the literal string `mneme check --mode warn`, which is the
job `name:` at L40. Two consequences follow:

- **F3a (rename trap).** If the job is switched to strict and renamed (for
  example to `mneme check --mode strict`), the required context is never
  reported. The merge then waits on a check that never arrives, until the
  ruleset is changed at the same moment. Changing the mode and changing the
  ruleset are one coordinated change, not two separate ones.
- **F3b (possible check-name substitution; unproven).** The ruleset pins both
  the context name and GitHub Actions `integration_id: 15368`. Whether a
  look-alike job with the same name and app identity can satisfy the
  requirement when the actual governance job is absent or failing is **not
  established** by this snapshot. Test it adversarially in CI1.3; a matching
  name must not be assumed either sufficient or safely disambiguated.

**Finding F4: no review gate sits behind the check.** With 0 required
approvals, the required checks are the entire merge boundary for a PR that
anyone with write access can merge. Every substitution path in §6 therefore
goes straight to a merge, with no reviewer in between.

**Finding F5: the evaluated revision differs from the reported revision.** The
workflow triggers on `pull_request` (L31). The step named "Checkout PR head"
(L43) uses `actions/checkout@v4` with no `ref:`. For `pull_request` that
checks out the synthetic merge commit `refs/pull/<n>/merge` (`GITHUB_SHA`),
not the PR head SHA, while the check run is attached to the head SHA. The
CI1.4 evidence packet must record both SHAs. "Pinned revision" has to say
which one. That a new push leaves no earlier check run counting for the new
head is GitHub's documented behavior, but it is **to prove in CI1.3** (the
"changed PR head" test). With `strict_required_status_checks_policy: false`, a
result computed against an older `main` can still allow a merge after `main`
has moved. That staleness is about the base, separate from the head.

## 6. Policy-substitution analysis

At the anchor, every input that decides the governance result comes from the
PR's own tree:

| # | Vector | Where | Effect today (warn) | Effect if the same workflow were strict |
|---|---|---|---|---|
| S1 | **Edit decision memory.** Remove or weaken the decision or rule in `.mneme/project_memory.json` | `--memory .mneme/project_memory.json` read from the PR checkout (L126) | n/a (advisory) | violation disappears → complete PASS |
| S2 | **Delete decision memory** | `verify-memory` step (L60–64) | run step skipped, job green | still skipped → green, with no verdict at all |
| S3 | **Edit the evaluator.** Change `mneme/` (enforcer, CLI) | `pip install -e .` from the PR checkout (L54) | n/a | the PR's own code decides its verdict |
| S4 | **Edit the workflow.** Change `mneme-check.yml` (for example back to warn, or `exit 0`) | `pull_request` runs the workflow definition from the PR's merge ref | n/a | the gate removes itself |
| S5 | **Add a look-alike job** with the required name (F3b) | any workflow in the PR | n/a | to prove in CI1.3 |
| S6 | **Move files out of scope.** Put the violating text outside the path filter | L82 filter | "No files in scope" → `exit 0` | same (coverage limit, §8) |
| S7 | **Steer retrieval through the PR title** | `query="${PR_TITLE} ${f}"` (L124) | n/a | **prose-tier** rules are retrieval-gated by the query (ADR-017), so the PR author can influence which prose rules are evaluated. **Literal-tier** rules (`FORBID_LITERAL` / literal anti-patterns) are evaluated corpus-wide (`_enforcement_scope`) and do not depend on the query |

**Finding F6: the trust boundary is the PR itself.** The workflow trusts the
PR's own memory (S1, S2), evaluator (S3) and gate definition (S4). Turning on
strict mode in this workflow as it stands would give a gate that the change
under evaluation can switch off. It would not show that the repository host
rejects violations. This is the CI-specific form of the trust-boundary
inventory's T1 gap ("protection against substitution between review/execution
… not established"). A trustworthy CI1 gate needs at minimum:

- the decision memory taken from a trusted ref (the base branch at a recorded
  SHA, or a pinned external source), never from the PR tree;
- the evaluator installed from a pinned, already-released `mneme-hq` version
  or from the base ref, never `pip install -e .` from the PR;
- a gate definition the PR cannot change for its own run. Options include a
  `pull_request_target` workflow that never executes PR code, a required
  workflow ruleset rule, or a CODEOWNERS plus required-review combination.
  The choice is a design decision for the CI1.3 contract and is not made here.
  Each option has its own security trade-offs (in particular,
  `pull_request_target` must not check out and execute PR code).

S7 is why CI1.2 and CI1.3 should use a **literal-tier** rule only. Its verdict
cannot be steered through the query.

## 7. Candidate decision for CI1.2 / CI1.3

`decision_index` at the anchor holds 21 decisions and exactly **one** canonical
rule:

| Field | Value |
|---|---|
| `rule_id` | `ADR-005:FORBID_LITERAL:cbf4d271068507ddb12c33abd765e333` |
| `decision_id` / `decision_version_id` | `ADR-005` / `dver-d6631efda827cdef1e67889e0648a268` (version `1`) |
| `rule_type` / payload | `FORBID_LITERAL` / the unqualified ADR-005 install command for the wrong PyPI distribution (not quoted here, because quoting it would trigger the rule on this file) |
| `applicability` | `{}` (**not path-scoped**; corpus-wide literal tier) |

**Finding F7: there is no path-applicable canonical rule.** The CI1 scope asks
for "a reviewed, path-applicable `FORBID_LITERAL` rule". None exists in this
repository's canonical index. CI1.2 must choose one of:

- (a) use ADR-005's unscoped rule as it is (query-independent, already
  reviewed; the literal matcher's boundary check keeps `pip install mneme-hq`
  from matching). This proves the merge boundary but not path applicability.
  Or
- (b) author a reviewed, path-scoped `FORBID_LITERAL` decision in the
  **isolated test repository** only. Adding one to this repository's
  `.mneme/project_memory.json` is a `[memory]` task and out of CI1 scope.

Recommendation: (b) for the CI1.3 isolated repository, plus (a) as an offline
CI1.2 fixture cross-check. The choice is a CI1.2 decision.

## 8. Coverage limits to carry forward

- Path filter (L82): changes outside `mneme/`, `docs/adr/`, `.mneme/` and
  `scripts/` are never evaluated. An "out-of-scope file" result must be
  reported as a **coverage limit**, not as a PASS.
- The prose tier depends on the query (S7). CI1's claim is scoped to the
  literal tier.
- Missing-memory policy (S2) is open: G3 and ADR-033 (#483, proposed)
  own it. CI1 can only report unavailability, not decide whether it blocks.
- DG1F-C1a applicability labels remain report-only. CI1 does not consume them.
- Literal rules do not tell use from mention. A document that *quotes* a
  forbidden literal FAILs exactly like one that *uses* it (observed while
  drafting this record). CI1 fixtures must not depend on that distinction.

## 9. CI-platform portability and reusable fixture contract (proposed scope)

**Portability invariant:** For identical trusted decision-memory bytes and
version, Mneme package version, evaluated input bytes and target path, query
and supported CLI options, the same Mneme enforcement path must return the same
governance verdict, evaluation completeness, applicability and canonical
decision/rule identity regardless of the CI executor. CI adapters must not
reimplement DecisionRetriever, ConflictDetector, typed-rule evaluation, path
applicability, or verdict semantics (ADR-017/020; #278).

Separate the three boundaries:

1. **Mneme evaluation:** the existing CLI and `mneme.check/v1` govern the
   decision result. Exit codes alone cannot establish a trusted verdict (F1).
2. **Trusted execution:** the adapter must obtain policy memory, evaluator and
   pipeline/gate definition from sources the untrusted proposed change cannot
   substitute; bind the evaluated subject, policy version and revision identity.
   This is a requirement for the experiment, not an existing guarantee (F6).
3. **Host enforcement:** the CI executor reports a result, but the repository
   host or landing/deployment controller must actually reject the operation
   when its independently authorized policy requires it. A failing pipeline
   without a host-side required gate is **not** proof of merge prevention.
   Post-merge validation is not pre-merge blocking evidence.

The adapter may translate a *trusted* CLI outcome to native CI logs, jobs,
statuses or annotations, but any strict/warn handling and availability-blocking
policy must be stated in the experiment contract, not invented by an adapter.
CI1.3's first live proof remains an isolated GitHub repository. Platform
compatibility must not be inferred from that one proof.

### Candidate platform inventory — not a support declaration

| Surface | Current repository evidence | CI1 disposition |
|---|---|---|
| GitHub Actions + GitHub protected branch | Existing `mneme-check.yml` is advisory; GitHub CLI-based pattern documented. #278 proposes a reusable thin Action | **First** CI1.3 live host-blocking proof; no production rollout |
| GitLab CI + GitLab merge controls | CLI-based CI reference pattern recorded in the canonical integration matrix | Reuse CI1.2 contract/fixtures; host enforcement not proven by CI1 |
| Jenkins + protected SCM branch | No validated Mneme Jenkins adapter evidenced here | Proposed parity target; a failed Jenkins stage alone is insufficient without an effective SCM merge gate |
| Azure Pipelines / Azure Repos, Buildkite, CircleCI | No validated Mneme adapters evidenced here | Later parity/host-boundary candidates, not current CI1 deliverables |
| TeamCity, Bitbucket Pipelines, AWS CodeBuild/CodePipeline, Google Cloud Build, Harness, Tekton | No validation established by this record | Inventory only; prioritize separately if evidence warrants |
| Anthropic Scion | Anthropic describes Scion as an **in-house source-control system**, not a CI product; see [engineering account](https://www.anthropic.com/engineering/redesigning-source-control) | Research only. No public Mneme integration, callable API or merge-blocking proof assumed |

**Source-control independence:** A shared CI1 fixture must not require Git,
a pull request, a particular check-run name, or a Git SHA to express the
governance verdict. GitHub-specific evidence *does* record head/merge/base SHAs
and required-check IDs; other source-control systems may use different opaque,
immutable revision identifiers. An adapter must positively bind whatever
revision it evaluated to the attempted merge, landing or deployment operation.
No revision mapping is guessed.

### CI1.2 cross-platform fixture requirements

Keep a single fixture corpus for direct CLI and any later adapter: pinned
Mneme version; trusted memory snapshot and decision/rule version; exact input
bytes/digest; target path; query/options; expected `mneme.check/v1` result;
and explicit coverage/evaluation completeness. Include compliant, violating,
strict WARN, conflicting-decision/core-parity, applicability-excluded, missing
or invalid configuration, contradictory/unparseable output and changed-revision
cases where applicable. A missing verdict is **unevaluated**, not governance
PASS or evidence of a policy violation. Tests of host-specific required checks
and merge rejection sit **on top** of these common fixtures.

For the first isolated live test, use a reviewed path-scoped literal rule in
the test repository (§7) and preserve the existing unscoped ADR-005 rule as an
offline cross-check. No new rule type, JSON schema or runtime path is authorized.
No roadmap priority, claimed support level or CI1.3 experiment permission is
changed by this inventory.

## 10. What the CI1.3 live experiment needs before authorization

| # | Item | Owner |
|---|---|---|
| A1 | An isolated test repository and protected branch, plus a ruleset with the required governance check (exact context name, `integration_id`, `bypass_actors: []`), recorded before and after | CI1.3 contract |
| A2 | A trusted-source design for memory, evaluator and gate definition (F6), stated in the contract | CI1.3 contract |
| A3 | **Proposed experiment policy, not authorized:** success only on a trusted, complete `mneme.check/v1` PASS; distinguish strict WARN, governance FAIL, invalid transport, missing/invalid memory and crash. Do not call UNEVALUATED a governance violation. Approval of whether unavailability blocks belongs to the separate policy/ADR-033 boundary; document it before the experiment | CI1.3 contract, aligned with #278 and #483 |
| A4 | Test matrix: compliant, violating, strict WARN, missing or invalid memory, CLI crash or contradictory output, new head commit, base moved (F5), substitution S1–S5, out-of-scope file | CI1.2 (offline) / CI1.3 (live) |
| A5 | Evidence fields: head SHA **and** evaluated merge SHA, base SHA, `rule_id`, `decision_version_id`, raw `mneme.check/v1` payload, check-run id and conclusion, ruleset snapshot, observed merge-button/API merge result | CI1.4 |
| A6 | Explicit statement that **this repository's** `mneme-check.yml` and `main-pr-only` stay unchanged. Promoting anything to this repository needs the G2 C1 charter + `[layer1-freeze]` amendment (ADR-031 §7) | CI1.4 recommendation |
| A7 | Direct-CLI fixture parity remains CI-platform-independent (§9). GitHub-specific merge and check-run evidence is additive, not part of Mneme's verdict semantics | CI1.2 fixture definition / CI1.3 contract |

## 11. Bottom line

- The CLI contract (`mneme.check/v1` + `evaluation_complete`) supplies the
  common machine verdict and canonical rule identity for CI adapters, provided
  they do not rely on exit codes alone (F1). It does **not**, by itself,
  establish every ADR-029 subject/provenance binding or trusted-source control
  required for CI1.4 (F2, F6).
- The merge boundary today rests on a check required **by name** (F3), with
  **no review gate** behind it (F4), evaluated against inputs **the PR
  controls** (F6). Switching this workflow to strict mode on its own would not
  establish merge-blocking assurance.
- CI1.3 should run only in an isolated repository, use a literal-tier rule
  (F7, S7), and record a trusted-source design (A2) before anything is
  executed. The CI1.2 fixture/verdict contract is portable; Jenkins, GitLab
  and other host-specific merge gates are later proof targets, not assumed
  compatible or implemented (§9).
- This record changes nothing and authorizes nothing.
