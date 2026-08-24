# M2a analysis — shell mutation classification (run 20260824T210203Z)

Pinned Codex CLI 0.149.1 (binary SHA pinned) / Windows / `codex exec`,
trusted logger PreToolUse hook, no bypass. Four forced shell-write
scenarios, each run allow + deny arms.

## Captured commands (exact `tool_input.command`)

| Scenario | Actual command sent to PreToolUse |
|---|---|
| redirect | `Write-Output 'HELLO_REDIRECT' > .\redirect.txt` + a follow-up read |
| setcontent | `Set-Content -LiteralPath 'setcontent.txt' -Value 'HELLO_SETCONTENT' -NoNewline; Get-Content ...` |
| script_driven | `python -c "open('generated.txt','w').write('GENERATED_BY_PYTHON')"` |
| multi_file_shell | `Set-Content ... 'multi1.txt' ...; Set-Content ... 'multi2.txt' ...` |

## Observed transport facts

- `tool_name` is `"Bash"` for all four (PowerShell runs under the Bash tool
  on this build).
- PreToolUse fired BEFORE mutation in every allow arm, and the full command
  string was present in `tool_input.command`.
- Generic `deny` blocked every scenario before disk mutation: zero files
  landed in any deny arm (`deny_effective_per_scenario` all true), while
  every allow arm produced its expected file(s). The agent's final messages
  confirm it saw the block.
- PostToolUse: present after allowed commands, absent on deny.
- Stop: fired in every arm.
- Target path and content are **embedded in arbitrary command text only** —
  there are no structured target/content fields anywhere in the payload.

## Classification

| Scenario | Classification | Basis |
|---|---|---|
| direct redirection | INTERCEPTABLE-BUT-NOT-RECONSTRUCTABLE | deny works pre-mutation; path+content exist only inside PowerShell text (`>`, `Out-File`, quoting variants unbounded) |
| PowerShell cmdlet write | INTERCEPTABLE-BUT-NOT-RECONSTRUCTABLE | same; `-LiteralPath`/`-Value` ordering, splatting, pipelines |
| script-driven write (python) | STOP-ONLY | content computed inside an interpreter; reconstructing it means executing or fully parsing the script |
| multi-file shell write | INTERCEPTABLE-BUT-NOT-RECONSTRUCTABLE | multiple targets per command line, statement separators |

No scenario qualifies as PRE-INTERCEPTABLE: deriving `(target_path,
introduced_content)` always requires interpreting shell semantics.

## Decision

Shell writes are classified as a **known pre-execution coverage gap**. Mneme
will not add shell parsing — even "simple" redirection is not worth the
slippery slope of maintaining a partial PowerShell interpreter, and the
bundled-command forms already defeat any isolated-syntax shortcut.

The **Stop changed-tree audit** is the designated backstop: Codex exposes
the command before execution and can block pre-mutation, but without
structured mutation metadata the audit boundary (whole-file check over the
session delta) is where shell-written artifacts get governed.

Also noted incidentally: the model appended read-back commands
(`Get-Content`) to verify writes; read-only shell commands fire PreToolUse
too, so any future shell policy must distinguish reads from writes — one
more reason not to parse shell.
