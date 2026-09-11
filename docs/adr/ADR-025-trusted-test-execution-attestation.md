---
id: ADR-025
title: "Trusted Test-Execution Attestation (Deferred)"
status: proposed
priority: normal
date: 2026-09-11
scope: audit.test_evidence
---

# ADR-025: Trusted Test-Execution Attestation (Deferred)

**Status:** Proposed
**Date:** 2026-09-11
**Deciders:** Theo Valmis

---

## Context

ADR-024 established four test-evidence states: `declared`, `matched_unverified`,
`authenticated_ci_claim`, and a reserved `verified`. The `authenticated_ci_claim`
state — reached through the authenticated GitHub API — proves the repository,
the workflow run, the exact run SHA, and that the evidence artifact belongs to
that run. It deliberately does **not** prove that a test executed: the artifact
*content* is still produced by repository-controlled workflow code, which can
upload `{"outcome": "passed"}` without running the test. Therefore
`authenticated_ci_claim` never reaches Protected, and `verified` remains
unreachable.

This ADR records the design for the first **trusted execution-attestation
producer** — the step that would take an authenticated CI claim to `verified`
and thereby to Protected — and records the decision to **defer** it.

## Threat model

An adversarial or mistaken repository (its workflow code is fully
repository-controlled) can attempt:

| # | Attack | Boundary required |
|---|---|---|
| 1 | Upload a fake `mneme-test-results` JSON claiming "passed" | evidence must be signed by a key the repository does not hold |
| 2 | Invoke the trusted verifier, then replace/modify its artifact | artifact content must be digest-bound to the signed evidence |
| 3 | Run a different test but claim the declared selector | the signed evidence must bind the exact selector |
| 4 | Fabricate "passed" after pytest actually failed | the outcome must derive from the verifier's own test-process exit code, not a workflow input |
| 5 | Copy valid evidence from another SHA | evidence must bind the exact repository SHA |
| 6 | Copy valid evidence from another repository | evidence must bind the repository identity |
| 7 | Copy valid evidence for another selector | evidence must bind the exact selector |
| 8 | A compromised workflow step forges verifier output | the signing identity must be one the workflow cannot impersonate |

The common requirement: evidence whose **authenticity and integrity cannot be
manufactured by ordinary repository workflow code**.

## Evaluated trust options

1. **GitHub Artifact Attestations (Sigstore/SLSA provenance)** — `actions/attest-build-provenance`
   (or the `attest` command) produces a signed DSSE attestation bundle. The
   signing identity is a GitHub Sigstore certificate whose SAN encodes the
   workflow OIDC identity; the statement subject is the artifact SHA-256 digest.
   Fetchable via `GET /repos/{owner}/{repo}/attestations/{digest}`. Verifying the
   signature requires `sigstore-python` (or `gh attestation verify`).
2. **GitHub OIDC tokens** — a workflow can mint a JWT (`id-token: write`) whose
   `sub`/`sha`/`workflow_ref` claims are GitHub-authoritative, verifiable against
   GitHub's OIDC JWKS. This proves *which repository's workflow ran*, but not
   *that a trusted verifier executed the test*: the repository's own workflow is
   the subject.
3. **Mneme-hosted signing service** — a backend the audited repository cannot
   reach/impersonate, holding a Mneme signing key. Correct but not GitHub-native;
   deferred as it requires a Mneme backend.
4. **Trusted reusable workflow identity** — a Mneme-controlled reusable workflow
   (e.g. `mnemehq/verify-tests`), pinned to an immutable tag/SHA, invoked by the
   audited repository via `uses:`. Its OIDC identity (`https://github.com/mnemehq/verify-tests/.github/workflows/verify.yml@refs/tags/v1`)
   is minted by GitHub for the *reusable workflow's* job — an identity the
   calling repository cannot impersonate or modify (the workflow code is Mneme's,
   pinned immutable).

**Selected mechanism (M0, deferred):** GitHub Artifact Attestations **over a
Mneme-controlled reusable workflow** (options 1 + 4). The audited repository can
invoke the verifier but cannot forge its OIDC identity, cannot obtain its signing
identity, and cannot modify the pinned immutable workflow code. This is the same
trust model used by `slsa-github-generator` and trusted-publisher workflows.

## Why repository workflow code cannot forge it

- The repository cannot mint an attestation with the verifier's OIDC identity:
  the OIDC token for the reusable workflow's job is issued by GitHub for
  `mnemehq/verify-tests`, not for the caller.
- The repository cannot alter an attested artifact's content without invalidating
  the digest-bound signature (subject = SHA-256 of the artifact; any byte change
  breaks the signature).
- The repository cannot inject `outcome: passed`: the verifier derives the
  outcome from the test process's actual exit status, and the attestation binds
  that outcome; the workflow has no input channel that writes the outcome.
- Replay (attacks 5–7) is blocked because the predicate/subject binds the exact
  repository, SHA, and selector.

## Verification procedure (future)

```
explicit verification operation
  → authenticated run + artifact (existing authenticated_ci_claim chain)
  → download artifact, compute SHA-256 digest
  → GET /repos/{owner}/{repo}/attestations/{digest}
  → verify DSSE/Sigstore signature (sigstore-python or gh attestation verify)
  → verify certificate SAN == pinned verifier workflow identity
  → verify subject digest == downloaded artifact digest
  → verify predicate binds repository == audited remote, SHA == audited HEAD,
    selector == exact declared selector, outcome == passed (from test exit)
  → private trusted internal result → STATE_VERIFIED → Protected
```

The verifier identity and its pinned immutable version are **configuration**,
not derived from the audited repository. Without a configured trusted verifier
(and a real cryptographic verifier), the `verified` state is unreachable.

## Decision

**Deferred until a real pilot/customer requirement justifies it.** The trusted
execution-attestation producer is not implemented in M0 and is not scheduled as
the next milestone. It requires two capabilities that do not exist in the
repository and cannot be fabricated here: (1) a published Mneme-controlled
reusable workflow (the trusted issuer identity), and (2) a cryptographic
attestation verifier (`sigstore-python` or `gh attestation verify`).
Implementing the structural checks alone — without the cryptographic signature
verification — would create a forgeable "verified" path, which is worse than
leaving `verified` unreachable.

Until then:

- `verified` remains unreachable through test evidence;
- `authenticated_ci_claim` remains the strongest reachable test-evidence state
  and never reaches Protected;
- `mneme audit` remains offline and passive;
- no public API accepts a trust-bearing parameter, and no repository JSON field
  can create trust.

## Consequences

- Protected via test evidence is intentionally not yet achievable; that is
  honest and correct.
- This design is **deferred until a real pilot/customer requirement justifies
  it** — it is not scheduled work and not a next milestone. If and when it is
  needed, the shape is a GitHub-native trusted verifier (a Mneme-controlled
  reusable workflow) plus `gh attestation verify`/`sigstore-python` verification
  gated behind a configured trusted-workflow identity, producing `verified`
  only on successful cryptographic verification.

## Related

- ADR-024: Declared Test-Evidence Ingestion for the Architecture Audit
- GitHub Artifact Attestations / SLSA provenance (`actions/attest-build-provenance`)
- GitHub OIDC identity for reusable workflows
