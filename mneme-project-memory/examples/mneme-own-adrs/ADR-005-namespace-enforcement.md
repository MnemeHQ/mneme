---
id: ADR-005
title: Brand vs Package Namespace Enforcement
status: accepted
priority: foundational
date: "2026-05-04"
scope: code
---

# Context

ADR-004 established that "Mneme HQ" is the brand and `mneme` is the package
namespace. In practice this boundary was violated: a brand rename pass
substituted "Mneme HQ" into code-bearing surfaces, producing invalid import
syntax such as `from Mneme HQ.memory_store import MemoryStore`.

# Decision

Code-bearing surfaces must use the lowercase `mneme` namespace only. The string
"Mneme HQ" is permitted only in prose, headings, meta tags, and JSON-LD name
fields. The camelCase variant `MnemeHQ` and the snake_case variant `mneme_hq`
are both forbidden in import paths and CLI invocations.

| Concept | Correct | Forbidden |
|---|---|---|
| Import root | `mneme` | `mneme_hq`, `MnemeHQ`, `Mneme HQ` |
| CLI entrypoint | `mneme` | `mneme-hq`, `Mneme HQ` |
| Module invocation | `python -m mneme.cli` | `python -m MnemeHQ.cli` |
| PyPI install | `pip install mneme` | `pip install mneme-hq` |

# Enforcement

Any code that imports from `MnemeHQ` or `mneme_hq` is using the wrong package
namespace. The correct import root is `mneme`. This fires as a governance
violation under the architectural constraint system.

## Constraints

- FORBID_DEPENDENCY: MnemeHQ
