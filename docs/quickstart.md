# 5-Minute Quickstart

This guide will walk you through setting up Mneme, adding a decision, and checking a prompt in under 5 minutes. No API key is required for this tutorial.

## 1. Install

Install the core Python package:

```bash
pip install mneme-hq
```



## 2. Initialize Project Memory

Create a new, empty memory file for your project. This is where your architectural decisions will be stored.

```bash
mneme init
```

This creates a file at `.mneme/project_memory.json`.

## 3. Add a Decision

Let's record a simple architectural decision: "Use JSON for configuration files, avoid YAML."

```bash
mneme add_decision \
  --memory .mneme/project_memory.json \
  --id "config-format" \
  --decision "Use JSON for configuration files" \
  --scope "config" \
  --constraint "Use JSON only" \
  --anti-pattern "Do not use YAML"
```

## 4. Check a Prompt

Now, let's pretend an AI coding assistant is about to generate code based on a user prompt. We will use `mneme check` to validate if the prompt violates our recorded decision.

First, let's try a compliant prompt:

```bash
python -c "import pathlib; pathlib.Path('prompt_clean.txt').write_text('Add a new JSON config file', encoding='utf-8')"

mneme check \
  --memory .mneme/project_memory.json \
  --input prompt_clean.txt \
  --query "configuration"
```

You should see a `PASS` verdict because the prompt respects the decision. The command will exit with code `0`.

Now, let's try a prompt that violates our decision:

```bash
python -c "import pathlib; pathlib.Path('prompt_violation.txt').write_text('Set up a new YAML config file for this module', encoding='utf-8')"

mneme check \
  --memory .mneme/project_memory.json \
  --input prompt_violation.txt \
  --query "configuration"
```

You should see a `FAIL` verdict because the prompt mentions YAML, which we explicitly defined as an anti-pattern. The command will exit with code `2`.

## Next Steps

You have successfully verified that Mneme can enforce architectural decisions before code generation even begins. 

- **Integrations:** Learn how to enforce these checks automatically in [Claude Code](integrations/claude-code.md) or your CI pipeline.
