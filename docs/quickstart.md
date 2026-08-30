# 5-Minute Quickstart

This guide shows the smallest working Mneme loop: install the package, create project memory, record one architectural decision, and verify both compliant and prohibited inputs. No API key is required.

Mneme provides architectural drift prevention for the agentic AI SDLC by turning recorded decisions into deterministic guardrails. This quickstart exercises the CLI enforcement surface directly.

## 1. Install

Requires Python 3.11+.

```bash
pip install mneme-hq
```

Verify the CLI:

```bash
mneme --help
```

## 2. Initialize project memory

Create an empty project-local decision corpus:

```bash
mneme init
```

This creates `.mneme/project_memory.json`.

## 3. Add a decision

Record a simple architectural decision: use JSON for configuration files and do not use YAML.

```bash
mneme add_decision \
  --memory .mneme/project_memory.json \
  --id config-format \
  --decision "Use JSON for configuration files" \
  --scope config \
  --constraint "Use JSON only" \
  --anti-pattern "Do not use YAML"
```

## 4. Check a compliant input

Create an input file explicitly as UTF-8:

```bash
python -c "import pathlib; pathlib.Path('prompt_clean.txt').write_text('Add a new JSON config file', encoding='utf-8')"
```

Run the check:

```bash
mneme check \
  --memory .mneme/project_memory.json \
  --input prompt_clean.txt \
  --query configuration
```

Expected result:

```text
Result: PASS
```

The command exits `0`.

## 5. Check a prohibited input

Create an input that contradicts the recorded decision:

```bash
python -c "import pathlib; pathlib.Path('prompt_violation.txt').write_text('Set up a new YAML config file for this module', encoding='utf-8')"
```

Run the same deterministic check:

```bash
mneme check \
  --memory .mneme/project_memory.json \
  --input prompt_violation.txt \
  --query configuration
```

Expected result:

```text
Result: FAIL
```

`mneme check` uses strict mode by default, so this FAIL exits `2`.

## What just happened

The same decision corpus was used for both inputs. Retrieval identified relevant architectural guidance; enforcement evaluated the applicable recorded rule and returned a deterministic verdict.

The CLI is also the common policy surface used by CI patterns and several agent integrations. Each integration documents which mutations it can block before execution and which paths require later audit.

## Next steps

- [Integration support matrix](integrations/README.md)
- [Claude Code integration](integrations/claude-code.md)
- [ADR import](integrations/adr-import.md)
- [Current architecture phase](architecture/current-phase.md)
- [Root README](../README.md)
