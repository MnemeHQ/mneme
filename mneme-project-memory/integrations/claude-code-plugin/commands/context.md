---
description: Retrieve relevant decisions from project memory for the current task
---

Use the Bash tool to run:
```
mneme test_query \
  --memory .mneme/project_memory.json \
  --query "<user's task description>"
```

Surface the top decisions and their constraints so the user can see what
governs the current work before making edits.

**Tip:** Use a descriptive query that names the domain of the work (e.g.
"database storage layer", "authentication middleware", "API serialization").
Retrieval is keyword-based — the more specific the query, the more relevant
the decisions returned. A generic query like "edit" will retrieve few or no
decisions.
