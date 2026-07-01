---
description: Review the current diff against project memory
---

Run `git diff` to capture pending changes, then for each modified file
check the new content against project memory.

Steps:
1. Use Bash: `git diff --name-only` to list modified files.
2. For each modified file, use Bash: `git show :0:<file>` or read the file
   directly to get the current content.
3. Run `mneme check` for each file, using a descriptive `--query` that
   names the file's domain (not just its path):

```
mneme check \
  --memory .mneme/project_memory.json \
  --input <file> \
  --query "<domain description for this file>" \
  --mode strict
```

4. Aggregate verdicts and report:
   - Files that PASS
   - Files with violations — include decision id and triggered rule

**Note on retrieval:** Use a meaningful `--query` per file (e.g. "storage
layer" for `db.py`, "auth middleware" for `auth.py`). The file path alone
may not retrieve all relevant decisions — describe the *domain* of the file,
not just its name.
