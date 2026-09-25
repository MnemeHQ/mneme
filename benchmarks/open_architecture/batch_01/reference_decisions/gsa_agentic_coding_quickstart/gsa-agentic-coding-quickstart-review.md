# GSA Agentic Coding Quickstart Reference Decision Review Packet

**Repository:** GSA-TTS/agentic-coding-quickstart  
**Pinned Commit:** 8e6160c63acc35bd48d0a3844e133ea3ad52a464  
**Total Records:** 20  
**Status:** Drafted; pending human review

---

## Summary by Sampling Category

| Category | Quota | Selected |
|---|---:|---:|
| clear_explicit | 5 | 5 |
| scoped | 5 | 5 |
| lifecycle_or_supersession | 3 | 3 |
| ambiguous_or_conflicting | 3 | 3 |
| enforcement_potential | 2 | 2 |
| unusual_or_difficult | 2 | 2 |
| **Total** | **20** | **20** |

## Records for Review

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

## Review Rules

For each record:

1. Verify the source location and raw evidence against the pinned commit.
2. Check normalized intent without replacing source-native meaning.
3. Use only frozen O1A taxonomy version 0.1.
4. Do not invent relationships that the source does not support.
5. Preserve accepted/superseded authority exactly as the repository establishes it.
6. Preserve current-state update/addendum semantics while retaining historical text.
7. Keep ontology limitations visible as `ONTOLOGY_GAP` notes rather than redesigning the ontology during Batch 01.
8. Mark the record `reviewed` only after human approval/correction.

## Cases Requiring Particular Attention

- **ADR-0001:** remains `accepted` and states all agents run in SBX, while later accepted ADR-0010/0011 establish multi-backend architecture. No explicit supersession is invented.
- **ADR-0005:** mixes deterministic SHA-pinning controls with a deliberate statement that agent rules/skills are advisory context, exposing the limitation of one scalar enforcement label.
- **ADR-0013:** the GitHub-token governance decision is prescriptive, but its adoption gate is explicitly warn-not-block.
- **ADR-0017:** later Update sections correct the original Decision Outcome in the same accepted ADR; the frozen lifecycle vocabulary has no clause-level amendment state.
- **ADR-0018 / ADR-0019:** later updates replace individual network-policy clauses while the ADRs remain active.
- **ADR-0020 / ADR-0021:** deterministic sub-controls coexist with fail-soft capability behavior; raw evidence and ontology-gap notes retain that distinction.

## Boundary Confirmation

This corpus is research data only. It does not create canonical decisions, accepted proposals, rules, or enforcement evidence.

No frozen semantic execution code is part of this draft.
No scenarios, repository 3 work, classifier experiments, ontology redesign, or D1B work is included.
