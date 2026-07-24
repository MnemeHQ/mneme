# 5-Minute Quickstart

This guide will walk you through setting up Mneme, adding a decision, and checking a prompt in under 5 minutes. No API key is required for this tutorial.

## 1. Install

Install the core Python package:

```bash
pip install mneme-hq
```

Verify the installation:

```bash
mneme --version
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
echo "Add a new JSON config file" > prompt_clean.txt

mneme check \
  --memory .mneme/project_memory.json \
  --input prompt_clean.txt \
  --query "configuration"
```

You should see a `PASS` verdict because the prompt respects the decision.

Now, let's try a prompt that violates our decision:

```bash
echo "Set up a new YAML config file for this module" > prompt_violation.txt

mneme check \
  --memory .mneme/project_memory.json \
  --input prompt_violation.txt \
  --query "configuration"
```

You should see a `FAIL` verdict because the prompt mentions YAML, which we explicitly defined as an anti-pattern.

## Next Steps

You have successfully verified that Mneme can enforce architectural decisions before code generation even begins. 

- **Integrations:** Learn how to enforce these checks automatically in [Claude Code](integrations/claude-code.md), [Cursor](https://mnemehq.com/docs/integrations/cursor), or your CI pipeline.
- **Concepts:** Read more about [Governance before generation](https://mnemehq.com/concepts/governance-before-generation/).
- **Advanced:** Try the [Interactive Demo](../README.md#advanced-demo) to see how Mneme corrects LLM output in real-time.
