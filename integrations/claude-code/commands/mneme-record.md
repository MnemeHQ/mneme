---
description: Record a new architectural decision into project memory
---

Ask the user for:
- `id` — snake_case identifier (e.g. `auth_001`)
- `decision` — one sentence stating the decision
- `rationale` — why this decision was made
- `scope` — list of keywords describing where this applies (used for retrieval — choose words that will appear in file names or task descriptions)
- `constraints` — list of prohibited approaches
- `anti_patterns` — list of specific strings/tokens to flag as violations

Then run via the Bash tool:
```
mneme add_decision \
  --memory .mneme/project_memory.json \
  --id <id> \
  --decision "<...>" \
  --rationale "<...>" \
  [--scope <keyword> ...] \
  [--constraint "<...>" ...] \
  [--anti-pattern "<...>" ...]
```

Confirm with:
```
mneme list_decisions --memory .mneme/project_memory.json
```

**Scope tip:** Choose scope keywords that will appear in file paths or task
descriptions where this decision applies. The hook query is derived from the
target file name — scope tokens that overlap with file names ensure the
decision is retrieved during enforcement.
