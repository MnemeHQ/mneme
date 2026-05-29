# Governance before generation

Canonical concept: https://mnemehq.com/concepts/governance-before-generation/

## Why this note exists

Most AI coding workflows apply governance after code is generated.

That usually means review comments, CI failures, failed tests, or human cleanup. Those checks matter, but they happen after the agent has already moved the system in a direction that may violate architectural intent.

Mneme's position is different: architectural governance should be available before and during generation, not only after review.

## The problem

AI coding agents are fast enough to amplify small architectural mistakes.

A single wrong import, framework boundary violation, storage abstraction bypass, or forbidden dependency can be replicated across files before a reviewer sees it.

Traditional review asks:

```text
Did this change violate our decisions?
```

Governance before generation asks:

```text
What decisions must shape this change before the agent writes it?
```

## Repo-native governance surfaces

Mneme keeps governance close to the repository so it can be used by humans, agents, hooks, and CI:

- ADRs define architectural intent
- `.mneme/project_memory.json` stores enforceable project memory
- context packets give agents relevant constraints
- hooks can run checks before or after tool execution
- CI can verify that generated changes still respect decisions

## Example

An ADR may establish a package boundary:

```text
Use mneme.memory_store.
Do not import from MnemeHQ.memory_store.
```

A conventional documentation system records that decision.

Mneme makes it operational by turning the decision into retrievable context and an enforceable anti-pattern.

## Why this matters

The goal is not to replace review.

The goal is to reduce architectural drift before review becomes the first place the organization notices it.

That is the core difference between documentation, retrieval, review, and governance.
