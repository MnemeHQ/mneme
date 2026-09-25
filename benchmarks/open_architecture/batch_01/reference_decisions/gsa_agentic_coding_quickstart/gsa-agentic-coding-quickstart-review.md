# GSA Agentic Coding Quickstart Reference Decision Review Packet

**Repository:** GSA-TTS/agentic-coding-quickstart  
**Pinned Commit:** 8e6160c63acc35bd48d0a3844e133ea3ad52a464  
**Total Records:** 20  
**Status:** 20/20 human-reviewed

---

## Summary by Sampling Category

| Category | Quota | Selected | Reviewed |
|---|---:|---:|---:|
| clear_explicit | 5 | 5 | 5 |
| scoped | 5 | 5 | 5 |
| lifecycle_or_supersession | 3 | 3 | 3 |
| ambiguous_or_conflicting | 3 | 3 | 3 |
| enforcement_potential | 2 | 2 | 2 |
| unusual_or_difficult | 2 | 2 | 2 |
| **Total** | **20** | **20** | **20** |

## Human-review outcome

Six draft records required taxonomy corrections after independent source review:

- **001 / ADR-0002:** removed `deployment_infrastructure`; the decision governs versioning and release workflow/evidence, not deployment infrastructure.
- **002 / ADR-0006:** added `dependency_technology` and purpose `select`; the ADR explicitly chooses and applies the git-ssh-sign kit.
- **010 / ADR-0029:** removed `testing_quality` and `require_evidence`; test seams support the path-form decision but are not its governed domain or purpose.
- **011 / ADR-0003:** replaced `require_evidence` with `require`; the source requires PR review of generated updates rather than an evidence artifact.
- **013 / ADR-0005:** added purpose `select`; the ADR explicitly chooses pinned remote kits as the replacement delivery model.
- **014 / ADR-0001:** added `api_interface`; the accepted decision explicitly includes the OpenAI-compatible USAi endpoint/authentication interface.

All remaining records were source-validated without taxonomy changes.

## Records

### clear_explicit

| Reference | ADR | Decision focus |
|---|---:|---|
| ref-gsa-agentic-coding-quickstart-001 | 0002 | SemVer, Conventional Commits, release-please |
| ref-gsa-agentic-coding-quickstart-002 | 0006 | Default SSH commit/tag signing |
| ref-gsa-agentic-coding-quickstart-003 | 0010 | acq pluggable-backend boundary |
| ref-gsa-agentic-coding-quickstart-004 | 0025 | bats-core test-suite migration |
| ref-gsa-agentic-coding-quickstart-005 | 0028 | Windows DPAPI-backed secret storage |

### scoped

| Reference | ADR | Decision focus |
|---|---:|---|
| ref-gsa-agentic-coding-quickstart-006 | 0012 | Backend-neutral USAi key rotation |
| ref-gsa-agentic-coding-quickstart-007 | 0014 | Neutral publishedPorts/background vocabulary |
| ref-gsa-agentic-coding-quickstart-008 | 0022 | Neutral custom image selection |
| ref-gsa-agentic-coding-quickstart-009 | 0027 | Neutral disposable clone semantics |
| ref-gsa-agentic-coding-quickstart-010 | 0029 | Windows host/guest path forms |

### lifecycle_or_supersession

| Reference | ADR | Decision focus |
|---|---:|---|
| ref-gsa-agentic-coding-quickstart-011 | 0003 | USAi model sync, superseded |
| ref-gsa-agentic-coding-quickstart-012 | 0004 | Shared playbook submodule, superseded |
| ref-gsa-agentic-coding-quickstart-013 | 0005 | Pinned kits and new trust model, supersedes 0003/0004 |

### ambiguous_or_conflicting

| Reference | ADR | Decision focus |
|---|---:|---|
| ref-gsa-agentic-coding-quickstart-014 | 0001 | Accepted SBX-only execution decision vs later accepted multi-backend architecture |
| ref-gsa-agentic-coding-quickstart-015 | 0017 | In-record restart mechanism corrections and resume-heal extension |
| ref-gsa-agentic-coding-quickstart-016 | 0019 | Egress-only refinement plus changed deprecated-toggle semantics |

### enforcement_potential

| Reference | ADR | Decision focus |
|---|---:|---|
| ref-gsa-agentic-coding-quickstart-017 | 0013 | Per-sandbox GitHub PAT downscoping, warn-not-block |
| ref-gsa-agentic-coding-quickstart-018 | 0018 | Balanced egress deny-default/allowlist |

### unusual_or_difficult

| Reference | ADR | Decision focus |
|---|---:|---|
| ref-gsa-agentic-coding-quickstart-019 | 0020 | Rootless podman OCI compatibility layer |
| ref-gsa-agentic-coding-quickstart-020 | 0021 | Host ssh-agent forwarding through vsock |

## Preserved ontology gaps

- **ADR-0005:** deterministic SHA/fail-safe controls coexist with agent rules/skills explicitly described as advisory context rather than a security boundary.
- **ADR-0006:** deterministic fail-closed signing coexists with an advisory pre-attach warning.
- **ADR-0013:** deterministic credential-storage/permission constraints coexist with a warn-not-block adoption gate.
- **ADR-0017:** later Update sections correct the original mechanism inside the same still-active ADR.
- **ADR-0018 / ADR-0019:** later notes replace individual clauses without whole-ADR supersession.
- **ADR-0020 / ADR-0021:** deterministic sub-controls coexist with fail-soft optional-capability behavior.

## Authority case preserved

ADR-0001 remains `accepted` and says all agents execute in SBX. Later accepted ADR-0010 introduces pluggable backends and ADR-0011 adds msb, but neither explicitly supersedes ADR-0001. The reference corpus therefore preserves ADR-0001 as active/explicitly accepted and records the conflict in human notes rather than inventing a supersession or `conflicts_with` relationship.

## Verification checklist

- [x] 20 unique repo-2 reference IDs
- [x] pinned repository SHA matches Batch 01 manifest/baseline
- [x] source evidence verified against pinned source
- [x] exact frozen O1A vocabulary only
- [x] sampling quota 5/5/3/3/2/2
- [x] authority and lifecycle preserved from source
- [x] unsupported relationships not invented
- [x] current-state in-record updates preserved
- [x] ontology gaps recorded rather than redesigned
- [x] all `human_review_status` values are `reviewed`
- [x] no machine prediction fields added
- [x] no scenarios, repo 3, classifier experiments, ontology redesign, D1B, or semantic execution changes

## Boundary confirmation

This corpus remains research-only benchmark data. It creates no canonical Decision Index authority, accepted proposals, rules, or enforcement evidence.
