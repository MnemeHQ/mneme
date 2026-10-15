# DG1F T-08: memory selection by payload `cwd` vs. edited target (2026-10-15)

> Evidence record for scenario **T-08** in the
> [`AUTHORIZATION_UNVERIFIABLE` adversarial specification](../plans/2026-10-15-dg1f-authorization-unverifiable-adversarial-spec.md).
> It is evidence only. It changes no runtime behavior, accepts no ADR or
> charter, and does not amend the Layer 1 freeze. Offline reproduction and
> live host confirmation are recorded separately, and neither one stands in
> for the other.

## 1. Question

Do the authoritative rules of the repository **being modified** govern a
direct write, regardless of the session's working-directory context?

**Success criterion (for Mneme):** repository A's rules govern edits to A,
whatever the unrelated `cwd` context.
**Bypass:** the same forbidden edit to A is permitted only because the hook
context resolves other memory.

## 2. Source observation (confirmed by inspection)

On `main` @ `2578a720`, `mneme/integrations/claude_code/hook.py` resolves
memory from the hook payload's `cwd`, never from the target file path:

| Boundary | Call |
|---|---|
| Direct write (`Edit\|Write\|MultiEdit`) | `handle_event`: `find_memory(Path(event.cwd or "."))` (line 1058) |
| Bash class-A preflight | `bash_tool_event`: line 644 |
| SessionStart | line 706 |
| Stop | line 853 |

`find_memory` returns `MNEME_MEMORY` if set. If that file does not exist it
returns `None`. Otherwise it walks up from the start directory to the first
`.mneme/project_memory.json`. The target path is passed to `mneme check` only
as `--target-path`.

## 3. Offline reproduction (hook level)

**Environment:** `main` @ `2578a720a7d418dc4023a701bf5e8bfe0ef43171`, Python
3.12.10, Windows 11. Reproducer:
[`repro_t08.py`](artifacts/dg1f-t08-cwd-memory-selection-2026-10-15/repro_t08.py).
It drives the real `hook.main` and the real `mneme check`, with no mocks, in
disposable directories. Three runs gave identical results
(`offline-run{1,2,3}.txt`, `offline-results.json`; the disposable root is
redacted as `<ENV>`).

**Fixture:**
- `repo_a`: git repo with active decision `T08-DEC`, `FORBID_LITERAL "psycopg2"`.
- `repo_b`: sibling git repo whose memory has one rule-less decision.
- `repo_a/vendor_tools/.mneme/project_memory.json`: the same permissive
  memory, planted inside A.

**Probe:** the identical `Edit` envelope targeting `repo_a/app.py` by absolute
path (`import os` → `import psycopg2`), in strict mode.

| Case | Payload `cwd` / env | Selected memory | Direct `mneme check` | Hook |
|---|---|---|---|---|
| V0 control | `repo_a` | `repo_a` | FAIL, complete, exit 2, `T08-DEC` | **exit 2, blocked**, decision-specific stderr |
| V1 | sibling `repo_b` | `repo_b` | PASS, `evaluation_complete: true`, exit 0 | exit 0, no output: **silent permit** |
| V2 | directory with no memory up the tree | none | not invoked | exit 0, no output: **silent permit** (known S1) |
| V3 | `repo_a/vendor_tools` | planted memory | PASS, complete, exit 0 | exit 0, no output: **silent permit** |
| V4 | `repo_a`, `MNEME_MEMORY` → nonexistent | none | not invoked | exit 0, no output: **silent permit** (known G3 §4.2) |
| V5 | `repo_a`, `MNEME_MEMORY` → `repo_b` memory | `repo_b` | PASS, complete, exit 0 | exit 0, no output: **silent permit** |

**Offline verdict: bypass reproduced at hook level** (V1, V3, V5 new; V2, V4
already documented). The checker returns a **complete, coherent PASS** for a
target outside the selected memory's repository. That passes the #260
coherence check, so nothing marks the result as untrusted or incomplete.

**Limits of the offline result:** it does not show that a live agent can steer
the payload `cwd` or the environment. Target hashes are unchanged in every
case only because the hook never writes, so they are not prevention evidence.

## 4. Live Claude Code probe

Pending. It will be recorded in this section.
