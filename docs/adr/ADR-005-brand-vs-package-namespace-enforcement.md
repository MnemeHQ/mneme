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
| Repo slug | `TheoV823/mneme` | `TheoV823/mneme-hq` |
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

- **Install-command gate (landed 2026-08-06):** `scripts/check_install_command.py`
  fails CI if any tracked file instructs `pip install mneme` not `mneme-hq`
  (or the `pipx` / `uv pip` equivalents). Editable installs
  (`pip install -e mneme`) take a local directory path, not a distribution
  name, and are not flagged; neither is a line that names both the correct and
  forbidden forms, so this ADR's own comparison table stays legal. Wired up as
  `.github/workflows/install-command-check.yml`.
- **Pre-publish check:** the deploy script (or a pre-commit hook) should fail
  if `Mneme HQ` appears inside a fenced code block, `<pre>`, `<code>`, or
  immediately after a `$ ` shell prompt in any tracked file.
- **ADR check:** any future ADR or brand pass that proposes editing code
  identifiers must cite ADR-004 + ADR-005 and explicitly justify why the
  package rename is in scope. Default answer: it is not.

## Amendment 2026-08-06: supply-chain rationale and the cost of the missing gate

The original text framed `pip install mneme` (rather than `mneme-hq`) as a
correctness problem. It is also a **supply-chain problem**, and that is the
stronger reason.

`mneme` on PyPI is an unrelated, abandoned third-party project — a
Flask/MongoDB note-taking application by Risto Stevcev, v0.201, last released
**19 May 2014**, Python 2.7 classifiers only, sdist only. It is unmaintained,
and this project neither owns nor controls that namespace. Publishing
`pip install mneme` in place of `mneme-hq` does not merely give users a broken
command: it directs them to install from a namespace outside our control.

**What the missing gate cost.** The version of this ADR accepted on 2026-05-04
closed with *"A small lint/grep gate is owed; until it lands, this ADR is the
contract reviewers cite."* The gate was never built. By 2026-08-06 the
violation had reached production: `mnemehq.com` served `pip install mneme` not `mneme-hq`
on three pages — `/qa-glossary/`, `/use-cases/ci-governance-for-ai-generated-code/`,
and `/integrations/warp/` — and **three of those occurrences were inside the
JSON-LD `FAQPage` block**, so the wrong command was being syndicated to search
rich results and AI answer engines rather than merely displayed. Fixed in
MnemeHQ/mnemehq-site#7.

The decision was correct and recorded from the start. It still reached
production because nothing enforced it. A recorded decision with no gate is a
preference, not a constraint — which is the failure mode this project exists to
prevent, and worth stating plainly in our own ADR record.

## Consequences

- One-time cleanup pass across README and `site/use-cases/*`.
- Future brand changes are safer: prose can move freely, code identity is
  pinned.
- ~~A small lint/grep gate is owed~~ — **landed 2026-08-06**; see Enforcement.
- The site repository (`MnemeHQ/mnemehq-site`) is a separate repository since
  the website extraction and does **not** inherit this gate. It needs its own
  copy, or the production surface stays unguarded.
