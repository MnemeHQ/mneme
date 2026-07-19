---
description: Run mneme check against a file or proposed change
---

Run `mneme check` against the current project memory.

If the user names a file, check that file's contents against
`.mneme/project_memory.json`. Otherwise, ask which file or scope.

Use the Bash tool:
```
mneme check \
  --memory .mneme/project_memory.json \
  --input <path> \
  --query "<scope or task description>" \
  --mode strict
```

**Important:** The `--query` argument controls which decisions are retrieved
for checking — it is not just a label. Use a descriptive phrase that matches
the scope of the change (e.g. "storage layer", "auth middleware") rather than
just the file name. Decisions are matched by keyword overlap between the query
and their scope, id, and text fields.

Report PASS / WARN / FAIL clearly. On FAIL, name the violated decision id and
quote the anti-pattern or constraint that triggered it.
