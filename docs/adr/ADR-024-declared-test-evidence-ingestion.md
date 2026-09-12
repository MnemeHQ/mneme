---
id: ADR-024
title: "Declared Test-Evidence Ingestion for the Architecture Audit"
status: accepted
priority: normal
date: 2026-09-11
scope: audit.test_evidence
---

# ADR-024: Declared Test-Evidence Ingestion for the Architecture Audit

**Status:** Accepted
**Date:** 2026-09-11
**Deciders:** Theo Valmis

---

> **Security amendment (2026-09-11, pre-commit review).** The first draft of
> this ADR had `mneme audit` execute the linked test itself
> (`python -m pytest <selector>` inside the audited repository). Pytest
> invocation is **arbitrary repository-code execution**: conftest.py files,
> collection hooks, plugins, fixtures, imports, and test bodies all run
> inside the audit's subprocess, so an audited repository could execute
> attacker- or author-controlled code during a routine read-only audit.
> The mitigations in that draft (`PYTHONDONTWRITEBYTECODE`,
> `no:cacheprovider`, selector validation, SHA pinning, `cwd` pinning,
> timeout) contain side effects but do NOT contain execution.
>
> This amendment makes **default Architecture Audit passive**:
>
> **Architecture Audit does not execute code from the audited repository
> unless the user explicitly requests an execution-capable verification
> mode.**
>
> Ordinary `mneme audit` never invokes pytest or any other repository-code
> runner. The decision→test declaration model, SHA pinning, deterministic
> linkage, ambiguity handling, and tier semantics are preserved unchanged;
> what changed is that a merely **declared** linkage annotates but never
> protects, and the VERIFIED state now requires a trusted verification
> producer (CI-produced exact-SHA + exact-selector ingestion — the next
> task). Local test execution is an explicit, separately opt-in future
> capability, not part of Audit. The draft's Sagarika Current-Protection
> figure (60%) is intentionally not preserved; under the corrected passive
> model it reverts to 0% until trusted verification arrives. Safety is
> more important than that number.
>
> **CI-evidence parsing/matching (2026-09-11, follow-up).** The parsing and
> matching half of trusted verification is implemented as a library in
> `mneme/evidence.py`: `parse_ci_evidence_document()` parses and validates a
> machine-produced evidence document (schema `mneme.test-evidence/v1`
> carrying `repository_sha`, a `producer` provenance object, and a list of
> `{selector, outcome}` results), and `match_ci_evidence()` computes which
> declared selectors a document **claims** to match when its SHA exactly
> equals the audited repository HEAD, the selector is string-equal to an
> unambiguous declaration, and the outcome is `passed`.
>
> **The document is an evidence carrier, not a trust root.** A matching
> document yields the `matched_unverified` state (annotated
> `test:ci-claim:<selector>@<sha>`), never `verified`. Producer metadata
> contained inside the document is descriptive until Mneme authenticates it
> against the external CI provider. The `verified` state is reserved for a
> future authenticated CI-retrieval producer and is unreachable from the raw
> document parameter, which is UNTRUSTED evidence material. Ordinary
> `mneme audit` never supplies a document and never auto-discovers or
> auto-trusts any repository file. The default Audit remains DECLARED-only;
> no caller input can manufacture Protected.
>
> **Authenticated GitHub Actions CI claim (2026-09-11, follow-up).** The
> authenticated retrieval path is implemented in `mneme/github_evidence.py`.
> `verify_github_run()` authenticates a workflow run and its evidence
> artifact through the GitHub REST API (trust root = `Authorization: Bearer
> <GITHUB_TOKEN>`; external to `project_memory.json`, the carrier, repository
> files, and caller-authored producer metadata).
>
> The authenticated chain validates, fail-closed, that (1) a token is
> present; (2) the audited repository identity resolves from the origin
> remote; (3) the run exists and belongs to exactly that repository; (4) the
> run's `head_sha` equals the audited HEAD exactly; (5) a non-expired
> artifact named `mneme-test-results` exists; (6) the artifact downloads
> (with the bearer token never forwarded to the signed redirect host), parses
> as `mneme.test-evidence/v1`, and its `repository_sha` equals the run
> `head_sha`. Selector results are matched exactly (`outcome == passed`).
>
> **Authenticated artifact provenance is not execution proof.** The artifact
> content is still produced by repository-controlled workflow code, so a
> workflow could upload `{"outcome": "passed"}` without running the test.
> Therefore the authenticated result is the `authenticated_ci_claim` state
> (annotated `test:ci-authenticated:<selector>@<sha>`), NOT `verified`, and it
> never reaches Protected. `verified` remains reserved for a future trusted
> producer — a Mneme-controlled verifier pinned to an approved immutable
> version whose output the repository cannot forge.
>
> **Trust boundary.** No public API accepts a trust-bearing parameter:
> `assess_protection` and `generate_protection_report` take only the
> declaration/carrier inputs and never construct `verified`. The
> authenticated result flows only through the internal, private
> `_verify_test_evidence(..., authenticated_claim=...)` seam, reached solely
> by `audit_with_github_claim()`, which is the one supported public
> authenticated operation and stops at `authenticated_ci_claim`. Default
> `mneme audit` remains offline and never calls GitHub. (Python code in the
> same process can always monkeypatch internals; the guarantee is that the
> supported public API cannot self-certify protection.)

## Context

The first real Design Partner diagnostic (sagarika29/ai-system-architect)
revealed that the target repository already contains deterministic tests
enforcing several of its documented architectural boundaries — blank-input
rejection, invalid-output rejection, API call-parameter assertions,
invalid-enum rejection, approved-stack cleanup — yet Mneme classified the
corresponding decisions as Requires Modelling. There was no deterministic
channel linking test evidence to architectural intent, so the Audit asked
only "what can Mneme itself enforce?" instead of the more valuable
question: "which architectural decisions are actually protected in this
system, regardless of which deterministic mechanism provides that
protection?"

ADR-026 fixed tier semantics (intent from decision text, not record
shape) but left the protection-evidence channels at exactly two: typed
`FORBID_LITERAL` rules and verified CI linkage on literalizable tokens.

## Decision

### Declaration home

Test-evidence declarations live on the **decision record** in
`project_memory.json`, as an optional per-decision field:

```json
"test_evidence": [
  {"selector": "tests/test_validation.py::test_empty_input_rejected",
   "sha": "<40-char repository SHA>"}
]
```

`sha` is optional; when present it pins the repository SHA the evidence
was established for. This is the smallest clean extension consistent with
Mneme's architecture: decisions already carry `rules` on the same record,
protection activation mutates that same file, and declarations follow the
ADR-019 trust model — **explicit, human-authored directives, never
inferred**. Alternatives rejected: ADR frontmatter (covers only ADR-sourced
decisions; Design Partner boundary decisions are not ADRs — documented
follow-up), and a separate evidence-manifest file (a new file format and
discovery path for no additional determinism). No CLI command is added in
M0; declarations are policy, authored deliberately.

### Evidence contract

The audited chain is exactly:

```
Decision → stable decision identifier → declared test evidence
        → test selector / assertion target → verified execution result
        → protection evidence
```

A test MUST NOT count as protection merely because its filename resembles
a decision, test text contains similar words, an LLM believes it
corresponds, the suite passes globally, or code coverage includes
relevant code. Mneme performs no fuzzy semantic matching: the linkage is
the declaration; verification establishes that the declared test passed
against the exact repository SHA, from a trusted provenance source.

**Declaration is not verification.** Declaring a linkage (the decision
record asserting "this test enforces this decision") is one act;
supplying verification evidence ("this exact selector passed at this
exact SHA, established by a trusted source") is a different one. Only the
second can establish protection.

### Verification (M0) — passive

Ordinary `mneme audit` executes **no repository-controlled code** — no
pytest, no conftest, no plugins, no test bodies. Declared evidence is
validated passively, in order —

1. the selector is well-formed (repository-relative pytest node id, no
   whitespace, at least one `::` separator, no drive letter, no leading
   slash, no `..` escape);
2. the mapping is unambiguous (the same selector declared by two or more
   decisions protects neither);
3. the repository HEAD SHA is available, the declared SHA pin (if any)
   matches HEAD exactly, and the selector's file exists inside the
   repository.

A linkage that passes all passive checks reaches the **DECLARED** state:
it is recorded as `test:declared:<selector>` in the decision's evidence
sources and never moves a decision out of Requires Modelling or Guidance.

The **VERIFIED** state — "the exact selector passed against the exact
repository SHA, and the provenance of that result is trusted" — has **no
producer in M0**. Introducing it requires a trustworthy verification
source; the intended one is CI-produced evidence (test results already
generated by the organization's own CI for the exact SHA + selector),
which is the next task. Local execution of the linked test is an explicit,
separately opt-in future capability and is never performed implicitly.

### Protection semantics

- A **deterministic** decision (ADR-026: prescriptive text, or documented
  enforcement fields with non-advisory text) with **trusted verified**
  test evidence is **Protected**: `evidence_confidence: "verified"`,
  evidence sources `test:verified:<selector>@<sha>`. M0 has no trusted
  verification producer, so no decision reaches Protected through test
  evidence in this commit.
- A **declared** linkage annotates `evidence_sources` as
  `test:declared:<selector>` but classification keeps Requires Modelling
  (deterministic intent) or Guidance (advisory intent).
- A **Guidance** decision is never upgraded — declared evidence or not
  (intent classification is evidence-independent).
- A Requires-modelling decision with declared but unverified evidence
  remains Requires Modelling.

### Failure behaviour (fail closed)

| Condition | Result |
|---|---|
| Declared selector malformed | diagnostic `malformed-selector`; no protection |
| Selector declared by multiple decisions | diagnostic `ambiguous-mapping`; neither protected |
| Repository SHA unavailable | diagnostic `sha-unavailable`; no protection |
| Declared SHA ≠ HEAD | diagnostic `stale` (`sha-mismatch`); no protection |
| Selector file missing | diagnostic `selector-not-found`; no protection |
| Declared linkage without trusted verification | state `declared`; never protects |
| Advisory decision + declared evidence | remains Guidance |
| Declared but unverified evidence | tier unchanged |

Evidence failure never silently upgrades protection, and passive Audit
never executes audited-repository code.

### Audit output

`mneme.audit/v1` is unchanged. Declared test evidence appears in the
existing per-decision `evidence_sources` list as
`test:declared:<selector>` (with the pinned SHA when present), and the
CLI prints it under `evidence:` — selector and pin with no runner noise
and no execution. Failure and staleness diagnostics appear as
`test:<state>:<selector>@<code-or-sha>` so the audit always answers why a
declared linkage did not establish protection.

## Consequences

- Mneme now has a deterministic representation for test-backed
  protection: a decision can declare which test enforces it, and Audit
  reports that linkage with its validation state.
- Under the corrected passive model, a **declared** linkage annotates but
  never protects: the Sagarika corpus reverts to Requires Modelling for
  its deterministic boundaries (Current Protection 0%) until trusted
  verification arrives. Reported honestly; safety outranks the number.
- The **VERIFIED** state requires a trusted provenance source. The
  intended producer is CI-produced test results for the exact SHA +
  selector (the next task): it avoids executing untrusted code inside
  Audit and reuses tests organizations already run. Local execution of
  the linked test is an explicit, separately opt-in future capability
  and is never performed implicitly by Audit.
- False protection is guarded on all sides: linkage is never inferred
  (no fuzzy matching, no filename/name similarity, no LLM judgment), the
  suite passing globally or coverage counting proves nothing, and the
  declaration alone is never protection.
- Declaring evidence is deliberate repository-governance work; an audit
  without repository context (`--repo-root` omitted) validates nothing.
- Passive Audit validates declarations without executing anything:
  declaration validation scales linearly with declared evidence entries;
  no repository test execution occurs.
- CI-produced verification ingestion, ADR-frontmatter declarations,
  sandboxed local verification, and additional runner ecosystems are
  documented follow-up work.

## Related

- ADR-019: Typed Literal Rule Contract (explicit-directive trust model)
- ADR-026: Audit Tier Semantics and Mneme Potential
- Design Partner diagnostic repository (read-only fixture):
  `sagarika29/ai-system-architect`
