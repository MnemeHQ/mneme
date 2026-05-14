# ADR-009: Automation file writes must specify explicit text encodings

**Status:** Accepted  
**Date:** 2026-05-12  
**Deciders:** Theo Valmis

---

## Context

### Incident

During a site-wide footer update (2026-05-12), a bulk automation operation rewrote 49 HTML
files without specifying an encoding. PowerShell 5.1 (`powershell.exe`) defaults to Windows-1252,
not UTF-8. Files containing em dashes (UTF-8 byte sequence `0xE2 0x80 0x94`) were silently
re-encoded as `0x97` — the Windows-1252 em dash byte, which is invalid UTF-8.

No error was surfaced at write time. The corruption was discovered only when `sync_shared.py`
opened the affected files with Python's default `utf-8` codec and crashed:

```
UnicodeDecodeError: 'utf-8' codec can't decode byte 0x97 in position 162
```

Three additional commits were required before a clean deploy could proceed.

### Root cause

The underlying cause is not PowerShell specifically. It is the assumption that a runtime's
default encoding matches the encoding of existing files. That assumption fails across languages
and platforms:

| Runtime | Default encoding | Risk |
|---------|-----------------|------|
| PowerShell 5.1 | Windows-1252 (system codepage) | High |
| Python 2 `open()` | System locale | High |
| Python 3 `open()` | `locale.getpreferredencoding()` — not always UTF-8 | Medium |
| Node.js `fs.writeFileSync()` | utf8 | Low, but `appendFileSync` differs |
| Bash redirection | `$LANG` / container locale | Medium |
| Go text templates | Bytes only — renderer may coerce | Medium |
| CI templating tools | Container locale | Medium |

Any automation that reads a UTF-8 file, processes it, and writes it back without pinning the
encoding risks silent corruption with no error at write time.

---

## Decision

All automation that reads from or writes to text files must specify the encoding explicitly.
The encoding must match the encoding of the target file — UTF-8 for all site, doc, config, and
source files in this repo.

This applies to:

- All scripts under `scripts/`
- All CI steps that write files
- Any AI-generated code that performs file I/O
- Shell one-liners, batch replacements, and ad-hoc operations
- Generated artifacts (sitemaps, rendered templates, JSON outputs)

---

## Required patterns

### PowerShell

```powershell
Set-Content  $path -Encoding utf8 -Value $content
Get-Content  $path -Encoding utf8
```

### Python

```python
open(path, 'r', encoding='utf-8')
open(path, 'w', encoding='utf-8')
open(path, 'w', encoding='utf-8', newline='')   # for files with controlled line endings
```

### Node.js

```js
fs.readFileSync(path, 'utf8')
fs.writeFileSync(path, content, 'utf8')
fs.appendFileSync(path, content, 'utf8')
```

### Bash

```bash
# Pin locale explicitly if writing files with non-ASCII content
LANG=C.UTF-8 some-command > file.html
# Or pipe through iconv when locale is uncertain
iconv -f utf-8 -t utf-8 < input > output
```

---

## Forbidden patterns

- `Set-Content $path -Value $content` — PowerShell without `-Encoding utf8`
- `Get-Content $path` — PowerShell without `-Encoding utf8` when processing non-ASCII content
- `open(path, 'r')` — Python without `encoding=` for text files in this repo
- `open(path, 'w')` — Python without `encoding=` for text files in this repo
- Any file write that relies on OS or runtime default encoding

---

## Enforcement implications

This decision maps to syntactically specific, pre-execution enforcement. A governance check
against proposed automation code should flag:

- `Set-Content` without `-Encoding`
- `open(` without `encoding=` in Python file-write contexts
- `writeFileSync` / `appendFileSync` without an explicit encoding argument in JS

Pre-execution enforcement (flagging the script before it runs) is strictly stronger than
post-execution detection (catching corrupted files after the fact). The forbidden patterns
above do not require semantic analysis — they are reliably matchable by lexical inspection.

---

## Rationale

- **Silent corruption is the worst failure mode.** No error is surfaced; CI passes; Git diffs
  show line-level changes that look correct; the byte-level encoding mismatch is invisible
  until a downstream tool with strict encoding validation opens the file.
- **Default encodings are runtime- and platform-dependent.** They change between language
  versions, between OS locales, and between CI container images. Explicit encodings eliminate
  the variable entirely.
- **The fix is low-cost.** Adding `-Encoding utf8` to a PowerShell call or `encoding='utf-8'`
  to a Python `open()` is a one-word change with no tradeoffs.
- **Pre-execution enforcement is feasible.** The forbidden patterns are syntactically specific
  and do not require understanding program semantics to detect.

---

## Consequences

- All new scripts must use explicit encoding parameters
- PR review (human or AI-assisted) must check for implicit encoding in file I/O
- Existing scripts not yet updated are candidates for a future cleanup sweep (non-blocking)

---

## Related

- Governance Incident 002 — Silent UTF-8 corruption from implicit PowerShell encoding
- ADR-003: Site Publishing Guidelines
- `docs/validation/governance-incident-log.md`
