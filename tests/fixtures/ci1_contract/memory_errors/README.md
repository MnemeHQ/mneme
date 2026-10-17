# CI1.2.2 fixture: missing or malformed memory

Pins what an adapter sees when `mneme check` cannot load its memory: no
payload at all. Shared rules (classification, contract exit codes) are in the
[index README](../README.md).

## Layout (`v1/`)

| Path | Role |
|---|---|
| `cases.json` | Case manifest. `memory_content` is the exact file content (`null` means the file does not exist) |

The malformed memory files are written to a temporary directory at test time
from `memory_content`, so the repository never carries invalid JSON for other
tools to trip on.

## Invocation contract

Each case runs in both `strict` and `warn` mode from a temporary directory
holding `input.md` and, unless the case is `memory_missing`,
`project_memory.json`:

```bash
python -m mneme.cli check --memory project_memory.json --input input.md --query storage --top 3 --mode <mode> --json
```

## Cases

| Case | Memory | stdout | stderr | Exit (both modes) | Classification |
|---|---|---|---|---|---|
| `memory_missing` | absent | empty | `ERROR: memory file project_memory.json does not exist` | 2 | UNEVALUATED |
| `memory_truncated_json` | invalid JSON | empty | Python traceback | **1** | UNEVALUATED |
| `memory_empty_file` | empty file | empty | Python traceback | **1** | UNEVALUATED |
| `memory_json_array` | `[]` | empty | Python traceback | **1** | UNEVALUATED |
| `memory_missing_required_keys` | no `meta` | empty | Python traceback | **1** | UNEVALUATED |
| `memory_malformed_decision` | decision without `decision` | empty | Python traceback | **1** | UNEVALUATED |

**Current behavior, pinned on purpose.** Only a *missing* memory file goes
through the CLI's `ERROR:` path (exit 2, the strict FAIL code). A memory file
that exists but cannot be loaded raises an uncaught exception: a traceback on
stderr and exit 1, the strict WARN code. In neither case is there a payload,
so only an adapter that requires a parseable `mneme.check/v1` payload
classifies both correctly. An adapter that maps exit codes alone reads a
corrupt memory file as WARN, and in warn mode reads a missing one as FAIL
while every real verdict exits 0.

Turning the malformed-memory crash into a structured `ERROR:` exit is a CLI
change and a contract change. It needs a new fixture version.

## Versioning

`v1` is immutable. A change to any stdout, stderr or exit expectation means
adding `v2/`, not editing `v1/`.
