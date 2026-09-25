# Mneme HQ

<!-- mcp-name: io.github.MnemeHQ/mneme -->

**Mneme is an open decision and control layer for agentic software development.**

It turns durable engineering decisions into agent context, deterministic enforcement, and inspectable enforcement results across AI coding agents, repositories, and CI workflows. Architecture is the first supported decision domain: **Mneme prevents architectural drift** by turning architectural decisions and ADRs into deterministic guardrails across coding agents, repository mutations, generated rules, and CI gates.

[![Tests](https://github.com/MnemeHQ/mneme/actions/workflows/tests.yml/badge.svg)](https://github.com/MnemeHQ/mneme/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/mneme-hq.svg)](https://pypi.org/project/mneme-hq/)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://pypi.org/project/mneme-hq/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

> **Where is your architecture actually enforced?** Run the [Architecture Audit](#architecture-audit) to see which decisions are protected, which can become deterministic guardrails, and which still depend on someone remembering the rules. [Try it →](https://mnemehq.com/audit/)

Mneme is the decision layer behind that drift-prevention mechanism. It keeps recorded engineering decisions active as AI coding systems propose and modify code, instead of leaving ADRs as passive documentation.

> **Current phase:** Layer 1 validation. Retrieval, enforcement, and benchmark semantics are governed by the accepted architecture and freeze record. See [Current Phase](docs/architecture/current-phase.md) before changing core behavior.

## What Mneme does

Mneme separates architectural guidance from deterministic enforcement:

- **Records architectural decisions** in a structured, auditable decision corpus.
- **Retrieves relevant decisions** when an agent or model needs architectural guidance.
- **Enforces governed rules deterministically** under explicit applicability semantics.
- **Integrates at the earliest reliable boundary** exposed by each coding workflow.
- **Audits bypassable mutation paths** where pre-change blocking is not technically available.
- **Runs in CI** as a final deterministic gate before incompatible changes are accepted.

The same input and governed decision state produce the same enforcement result. Mneme does not depend on an LLM judge for its core allow/warn/fail decisions.

Mneme is not a general-purpose vector store, conversational memory system, autonomous coding agent, or deployment observability platform.

## Install

Requires Python 3.11+.

```bash
pip install mneme-hq
```

Verify the CLI:

```bash
mneme --help
```

For repository development:

```bash
git clone https://github.com/MnemeHQ/mneme.git
cd mneme
pip install -e ".[dev]"
```

## Decision MCP

Mneme exposes the Decision Index over a local MCP server so MCP-capable clients can propose candidate architectural decisions and query decision state without gaining authority to change that state.

Install the optional MCP dependency:

```bash
pip install "mneme-hq[mcp]"
```

Start the local stdio server with the proposal store enabled:

```bash
mneme decision-mcp
```

Optionally add a canonical ADR corpus. Mneme validates and precedence-resolves the corpus before the server starts; invalid or ambiguous ADR state fails closed rather than serving a degraded authority view.

```bash
mneme decision-mcp --adr-dir path/to/adrs
```

The MCP surface is intentionally frozen to six tools:

- `decision.propose`
- `decision.propose_batch`
- `decision.get`
- `decision.search`
- `decision.applicable_to`
- `decision.trace`

Proposal tools create non-authoritative proposals only. Read tools query proposal and canonical decision state. MCP deliberately exposes no accept, reject, activate, supersede, exception, bypass, or trusted-evidence authority.

Human authority remains explicit through `mneme decision proposals | show | accept | reject`. Accepting a proposal materializes a canonical decision; it does not activate protection or run the Architecture Audit.

See [ADR-027](docs/adr/ADR-027-decision-mcp-proposal-ingestion-and-authority-boundary.md) and the [v0.9.0 release notes](docs/releases/v0.9.0.md) for the authority boundary and release contract.

## Architecture Audit

See where your architecture is actually protected — and where it still depends on people remembering the rules.

Mneme audits your repository and shows which architectural decisions are:

- **Protected** — already enforced mechanically
- **Mneme-ready** — can be turned into a deterministic guardrail
- **Requires modelling** — important, but not yet safe to automate
- **Guidance** — useful context, but not something that should be enforced

Run an audit:

```bash
mneme audit --memory .mneme/project_memory.json --repo-root .
```

For a Mneme-ready decision, validate the proposed protection before enabling it:

```bash
mneme protect validate <decision-id> --memory .mneme/project_memory.json
```

Then explicitly activate it:

```bash
mneme protect activate <decision-id> --memory .mneme/project_memory.json
```

Mneme only reports a decision as **Protected** after it can verify that real enforcement is in place. The full activation contract is documented in [Protection Activation](docs/protect-activation.md).

[Try the Architecture Audit →](https://mnemehq.com/audit/)

## 60-second enforcement example

Initialize a project-local decision corpus:

```bash
mneme init
```

Record one architectural decision:

```bash
mneme add_decision \
  --memory .mneme/project_memory.json \
  --id config-format \
  --decision "Use JSON for configuration files" \
  --scope config \
  --constraint "Use JSON only" \
  --anti-pattern "Do not use YAML"
```

Create a proposed input that violates it:

```bash
python -c "import pathlib; pathlib.Path('prompt.txt').write_text('Set up a new YAML config file', encoding='utf-8')"
```

Run the deterministic check:

```bash
mneme check \
  --memory .mneme/project_memory.json \
  --input prompt.txt \
  --query configuration
```

In strict mode, the prohibited YAML proposal returns a `FAIL` verdict and exit code `2`. A compliant JSON proposal returns `PASS` and exit code `0`.

The CLI is the common enforcement surface. Agent integrations translate their native events into the same Mneme decision and enforcement model.

## Setup mode (no enforcement)

`mneme setup` initializes Mneme in a repository without changing how the team works: it creates or detects project memory, detects supported agent environments, and reports protection readiness — all without enabling any blocking enforcement. Setup never turns warn/observe behavior into blocking behavior; activation of preventive enforcement is always a separate, explicit decision.

```bash
mneme setup
```

Optionally record an opaque Architecture Audit reference so the setup can be attributed back to a saved Audit baseline:

```bash
mneme setup --audit-ref <reference>
```

Setup is idempotent: rerunning it against an existing Mneme project leaves valid configuration untouched.

## How it works

```text
Architectural decisions / ADRs
            |
            v
   structured decision corpus
            |
      +-----+--------------------+
      |                          |
      v                          v
relevant guidance       deterministic enforcement
   retrieval             + applicability checks
      |                          |
      +------------+-------------+
                   |
                   v
       workflow-specific boundary
                   |
      +------------+-------------+
      |            |             |
 pre-change     post-change      CI
   hooks          audit          gate
```

Mneme applies governance at the earliest reliable boundary a workflow exposes:

1. **Before generation** when architectural context can be injected into the model call.
2. **Before supported file mutations** when an agent exposes a blocking pre-tool hook.
3. **After bypassable mutations** through bounded working-tree audits where shell/script writes cannot be inspected safely before execution.
4. **Before merge** through CLI-based CI gates.

These boundaries are complementary. An integration only claims the surfaces that have been implemented and validated for that harness.

### Retrieval is not enforcement

Decision retrieval answers: **which architectural decisions are useful as guidance for this task?**

Enforcement answers: **does the proposed change violate a governed rule that applies here?**

Those concerns are intentionally separated. See [ADR-017](docs/adr/ADR-017-enforcement-scope-vs-retrieval-scope.md), [ADR-019](docs/adr/ADR-019-typed-literal-rule-contract.md), and [ADR-020](docs/adr/ADR-020-explicit-path-applicability-for-typed-rules.md).

## Supported surfaces

The authoritative support matrix lives in [docs/integrations/README.md](docs/integrations/README.md). The labels below are evidence levels, not interchangeable marketing terms.

| Support level | Surface |
| --- | --- |
| Native integration | Claude Code |
| Native integration | Claude Agent SDK |
| Native integration | Google Antigravity |
| Native integration | Codex CLI |
| Native integration | Kiro CLI 3.0 / v3 |
| Validated compatibility | Paperclip — CLI and ACP transports, no adapter required |
| Rules export | Cursor |
| CLI-based CI gate | GitHub Actions, GitLab CI |
| Experimental | OpenCode |
| Planned | Deep Agents middleware POC |

Each integration documents its actual blocking boundary, bypass paths, degraded behavior, and validation evidence. Start with the [integration matrix](docs/integrations/README.md), not assumptions based on another harness.

## ADRs and project memory

Mneme can compile architecture decisions into structured governance records rather than treating ADRs as passive prose.

The repository governance source of truth is `.mneme/project_memory.json`. The ADR import path preserves explicit source provenance where available so typed rules can be inspected and enforced consistently.

See:

- [Architecture overview: ASCII + C4 + ADR map](docs/architecture/README.md)
- [ADR import](docs/integrations/adr-import.md)
- [Accepted ADRs](docs/adr/)
- [Current architecture phase](docs/architecture/current-phase.md)

## Architecture guarantees

Three principles govern the current mechanism:

- **Deterministic > clever.** Enforcement behavior must be reproducible.
- **Auditable > autonomous.** A verdict should be traceable to the decision, rule, applicability state, and evidence that produced it.
- **Prevention before review.** When a reliable pre-change boundary exists, use it; when it does not, surface the limitation and audit later rather than pretending the path is blocked.

The current Layer 1 scope, frozen surfaces, accepted amendments, experimental work, and deferred Layer 2 work are maintained in [docs/architecture/current-phase.md](docs/architecture/current-phase.md).

Do not infer architecture from this README when a linked ADR or architecture document is more specific.

## Benchmark and validation

Mneme's benchmark is a regression and integrity instrument for retrieval and enforcement behavior. It is not a general model-quality benchmark.

The benchmark keeps retrieval and enforcement scoring distinct so changes cannot silently improve one surface while regressing another.

See:

- [Benchmark methodology](https://mnemehq.com/docs/benchmark-methodology/)
- [Public benchmark](https://mnemehq.com/benchmark/)
- [Current phase and freeze](docs/architecture/current-phase.md)
- [Release notes](docs/releases/)

## Demos

- [Governed Python Agent](https://www.youtube.com/watch?v=4Yg43V9amao)
- [ADR Import](https://www.youtube.com/watch?v=lMkq-RoKeD4)
- [Architectural Drift](https://www.youtube.com/watch?v=xkXJqSnXBJ8)
- [GitHub Actions Governance](https://www.youtube.com/watch?v=LaJqeJrKkgg)
- [Dependency Policy](https://www.youtube.com/watch?v=pBJSpN8d9FU)

More examples: [mnemehq.com/demo](https://mnemehq.com/demo/)

## Contributing

Before changing retrieval, enforcement, applicability, conflict handling, or benchmark semantics, read the architecture and ADRs that govern that surface.

- [Contributing](CONTRIBUTING.md)
- [Current architecture phase](docs/architecture/current-phase.md)
- [Security policy](SECURITY.md)
- [Changelog](CHANGELOG.md)

Core behavioral changes may require the repository's charter-amendment procedure. Documentation, tooling, integrations, and examples do not automatically authorize changes to frozen behavior.

## License

MIT. See [LICENSE](LICENSE).
