---
id: ADR-005
title: "Brand vs Package Namespace Enforcement"
status: accepted
priority: normal
date: 2026-05-04
scope: brand.namespace
---

# ADR-005: Brand vs Package Namespace Enforcement

**Status:** Accepted
**Date:** 2026-05-04
**Deciders:** Theo Valmis
**Supersedes:** none
**Related:** ADR-004 (Brand Rename — Mneme to Mneme HQ)

---

## Context

ADR-004 established that **"Mneme HQ"** is the brand and **`mneme`** is the
package/CLI/import namespace, and that the two must never be conflated. In
practice, that rule has not been enforced. A find-and-replace style brand pass
substituted "Mneme HQ" into code-bearing surfaces, producing snippets that look
authoritative but do not run.

Concrete incident (2026-05-04): the public README and several `site/use-cases/*`
pages render code blocks like:

```python
from Mneme HQ.memory_store import MemoryStore
from Mneme HQ.retriever import Retriever
```

```bash
Mneme HQ list_decisions
python -m Mneme HQ.cli
```

These are syntactically invalid (space in identifier) and contradict the actual
`pyproject.toml` (package `mneme`, CLI `mneme`). Affected files:

- `README.md`
- `site/use-cases/security-compliance-guardrails/index.html`
- `site/use-cases/multi-agent-workflow-governance/index.html`
- `site/use-cases/legacy-codebase-memory/index.html`
- `site/use-cases/design-system-governance/index.html`
- `site/use-cases/data-platform-governance/index.html`
- `site/use-cases/coding-assistant-governance/index.html`
- `site/founder/index.html`

## Decision

Code-bearing surfaces MUST use the lowercase `mneme` namespace. The string
`"Mneme HQ"` is permitted only in prose, headings, meta tags, and JSON-LD
`name` fields.

A surface is "code-bearing" if it contains any of:

- `import` / `from ... import` statements
- A shell prompt invoking the CLI (`mneme ...`, `python -m mneme...`)
- File paths into the package (`mneme/...`, `src/mneme/...`)
- Repo slugs or clone URLs
- `pip install` / `pipx install` lines

In code-bearing contexts, the only acceptable spellings are:

| Concept | Correct | Forbidden |
|---|---|---|
| Import root | `mneme` | `Mneme HQ`, `MnemeHQ`, `mneme_hq` |
| CLI entrypoint | `mneme` | `Mneme HQ`, `mneme-hq` |
| Module invocation | `python -m mneme.cli` | `python -m Mneme HQ.cli` |
| Repo slug | `mnemeHQ/mneme` | `mnemeHQ/mneme-hq` |
| PyPI distribution name | `mneme-hq` | `mneme` (name taken by unrelated package) |
| pip install command | `pip install mneme-hq` | `pip install mneme` |

**Note on distribution name vs import name:** The PyPI distribution name (`mneme-hq`) intentionally diverges from the Python import root and CLI command (both `mneme`). This follows the standard Python packaging pattern where distribution and import names differ (e.g. `pip install scikit-learn` → `import sklearn`, `pip install Pillow` → `import PIL`). The PyPI name `mneme` is occupied by an unrelated note-taking package (mneme 0.201, uploaded 2014). Users install with `pip install mneme-hq` but import and invoke as `mneme`.

## Required Fixes (this ADR's acceptance criteria)

1. README.md code block and CLI examples corrected to `mneme`.
2. All eight files listed above audited and corrected.
3. Grep gate: `grep -rE "Mneme HQ[\.\s]" --include="*.md" --include="*.html" --include="*.py"`
   should return zero hits inside fenced code blocks, `<code>` / `<pre>` blocks,
   and shell prompts.

## Enforcement

- **Pre-publish check:** the deploy script (or a pre-commit hook) should fail
  if `Mneme HQ` appears inside a fenced code block, `<pre>`, `<code>`, or
  immediately after a `$ ` shell prompt in any tracked file.
- **ADR check:** any future ADR or brand pass that proposes editing code
  identifiers must cite ADR-004 + ADR-005 and explicitly justify why the
  package rename is in scope. Default answer: it is not.

## Consequences

- One-time cleanup pass across README and `site/use-cases/*`.
- Future brand changes are safer: prose can move freely, code identity is
  pinned.
- A small lint/grep gate is owed; until it lands, this ADR is the contract
  reviewers cite.
