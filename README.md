# Mneme HQ

**Architectural decisions, enforced on every AI call.**

[![CI status](https://github.com/MnemeHQ/mneme/actions/workflows/test.yml/badge.svg)](https://github.com/MnemeHQ/mneme/actions)
[![PyPI version](https://img.shields.io/pypi/v/mneme-hq.svg)](https://pypi.org/project/mneme-hq/)
[![Python version](https://img.shields.io/pypi/pyversions/mneme-hq.svg)](https://pypi.org/project/mneme-hq/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

Mneme HQ is the architectural governance layer for AI-assisted development. LLMs start every call from zero, causing them to reintroduce rejected technologies or ignore established architecture. Mneme helps teams prevent [architectural drift](https://mnemehq.com/concepts/architectural-drift/) by encoding your project's technical decisions and automatically enforcing them before AI code generation begins.

<p align="center">
  ▶ <a href="https://www.youtube.com/watch?v=4Yg43V9amao" target="_blank"><b>Governed Python Agent Demo</b></a>
  &nbsp;|&nbsp;
  <a href="https://mnemehq.com/demo/adr-compiler/" target="_blank">ADR Import Demo →</a>
  &nbsp;|&nbsp;
  <a href="https://mnemehq.com/pilot/" target="_blank"><b>Request a pilot →</b></a>
</p>

## Quick Install

```bash
pip install mneme-hq
```

## First Working Command (30 seconds)

You can verify that Mneme is working by running a quick check. No API key is required.

```bash
# 1. Initialize a new project memory file
mneme init

# 2. Add an explicit architectural constraint
mneme add_decision \
  --memory .mneme/project_memory.json \
  --id "config-format" \
  --decision "Use JSON for configuration files" \
  --scope "config" \
  --constraint "Use JSON only" \
  --anti-pattern "Do not use YAML"

# 3. Test a prompt against your constraint
echo "Set up a new YAML config file for this module" > prompt_violation.txt

mneme check \
  --memory .mneme/project_memory.json \
  --input prompt_violation.txt \
  --query "configuration"
```

You will see a `FAIL` verdict because the input explicitly violates the recorded anti-pattern.

## How It Works

Mneme turns architectural decisions into structured context packets injected into every LLM call.

1. **Decision store:** Structured architectural decisions, rules, constraints, and decision records.
2. **Deterministic retrieval:** Selects relevant items based on the input task.
3. **Context packet:** Builds a compact, structured representation of what the model needs to know.
4. **Pre-flight enforcement:** Checks for constraint violations before generation.
5. **Injection:** The context packet is passed as the system prompt to align the output.

This is intentionally simple: no vector database, no long context windows, and no agent loops. The goal is to make the model respect prior decisions.

## Integrations

- **Claude Code:** Enforce constraints automatically on every Edit or Write via a `PreToolUse` hook. See [Claude Code Integration](docs/integrations/claude-code.md).
- **Cursor:** Generate a compatible `.mdc` rules file from your project decisions. See [Cursor Integration](https://mnemehq.com/docs/integrations/cursor).
- **CI / GitHub Actions:** Gate CI pipelines or pre-commit hooks using `mneme check --mode strict`. See [ADR to CI Demo](https://www.youtube.com/watch?v=LaJqeJrKkgg).

## Documentation

- **[5-Minute Quickstart](docs/quickstart.md)**
- **[Architectural Concepts](https://mnemehq.com/concepts/)**
- **[ADR Compiler Guide](docs/integrations/adr-import.md)**
- **[Benchmark Methodology](https://mnemehq.com/docs/benchmark-methodology/)**
- **[Changelog](CHANGELOG.md)**

## Advanced Demo

This repository includes a full demo of the five-stage pipeline that runs locally in under two minutes. It calls the Anthropic API to show the difference in output with and without Mneme governance.

```bash
# Requires an Anthropic API key (.env)
python demo.py
```

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on setting up your development environment, running tests, and our pull request standards. For security issues, refer to [SECURITY.md](SECURITY.md).

## Community

Join the conversation and get support in our [GitHub Discussions](https://github.com/MnemeHQ/mneme/discussions).

## License

MIT License. See [LICENSE](LICENSE) for details.
