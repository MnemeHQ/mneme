---
id: ADR-021
title: "Shell Preflight Reconstruction and Stop Session-Delta Enforcement"
status: accepted
priority: foundational
date: 2026-08-22
scope: enforcement.coverage
---

# ADR-021: Shell Preflight Reconstruction and Stop Session-Delta Enforcement

**Status:** Accepted
**Date:** 2026-08-22
**Deciders:** Theo Valmis

---

## Context

The enforcement architecture is **prevent -> catch -> verify**. After
ADR-017/018/019/020 the prevent stage covers exactly one surface: Claude Code
`PreToolUse` events for `Edit|Write|MultiEdit`. Two gaps follow, and both are
visible to any pilot user:

1. **Shell bypass.** A `Bash` call such as `cat > src/db.py << 'EOF' ... EOF`
   writes repository content without firing a file-edit hook. The plugin
   documentation states this openly: shell writes "are not covered".
2. **No completion boundary.** Whatever escapes interception — an ambiguous
   shell pipeline, a generated file, an indirect script write — is never
   evaluated again before the agent declares the turn finished. CI sees it
   eventually; the agent does not.

Neither gap is governed by an existing ADR. ADR-018 defines introduced-delta
semantics for the edit gate specifically; it neither authorizes nor forbids
applying those semantics at other boundaries. This decision records both
extensions and their claim boundaries.

### What cannot be done

Mneme must not become a shell interpreter. Arbitrary shell semantics —
expansion, substitution, pipelines, control flow — cannot be reconstructed
deterministically from a command string, and guessed semantics produce either
false blocks (blocking commands that would have written compliant content) or
false PASS (checking content that was never going to land). Both are worse
than the gap they close.

A completion-time boundary also faces an attribution problem: a working tree
that was already dirty before the session began contains violations nobody can
blame on the agent. Blocking completion over them recreates the
pre-existing-violation wall ADR-018 removed (#259).

## Decision

### 1. Shell mutations are classified, never interpreted

Every intercepted shell command is placed in exactly one class by a
conservative, deterministic classifier operating on the tool input alone:

- **A — deterministically reconstructable repository mutation.** Only when the
  proposed bytes and the affected repository path are provable from the
  command string alone. The initial grammar is deliberately narrow: a single
  simple `cat` command whose output is redirected (`>` overwrite or `>>`
  append) to one plain path token, reading a here-document with a *quoted*
  delimiter (`<< 'EOF'` or `<< "EOF"`). A quoted delimiter suppresses all
  parameter, command, arithmetic, glob, and escape expansion, so the document
  body is byte-identical to what the shell will write; the body ends at the
  first line equal to the delimiter. Anything else in the command — pipelines,
  `&&`/`;` chains, command or variable substitution, unquoted delimiters,
  `<<-`, multiple redirects — voids class A.
  
  Class A commands are materialized and checked **before execution** using
  the existing edit-gate path: the same introduced-content definition as
  ADR-018, the same `mneme check --target-path` invocation, the same verdict
  trust rules. A trusted blocking verdict exits 2 before the shell runs.

- **B — potentially mutating but not safely reconstructable.** Allowed to
  proceed. Not blocked on guessed semantics. Optionally traced in diagnostics
  as not preflight-reconstructable; the Stop boundary (below) is the
  enforcement surface for this class.

- **C — clearly non-mutating.** Passes through without enforcement work.

Classification defaults to B whenever membership in C cannot be proven. Class
assignment never decides a block by itself; only class A reaches the checker,
and only its trusted verdict can block.

The separately named `PowerShell` tool surface is recorded as the next
coverage item and is not implemented in the first iteration; its resulting
file mutations remain within Stop's reach where session auditing is
available.

### 2. Stop enforces the session delta

A `Stop` hook acts as a second enforcement boundary: **post-mutation /
pre-completion**. It is not pre-generation enforcement, it does not prevent
the original write, and it must never be described as such.

**Session baseline.** A `SessionStart` hook captures, once per session at
`source: startup`, a snapshot of every git-tracked and untracked-but-not-
ignored file under the policy root: SHA-256, size, and UTF-8-decoded content
for files within per-file and total size budgets; hash-only beyond them. The
snapshot lives outside the governed repository (the platform temp directory),
keyed by repository-root hash and Claude `session_id`, so concurrent sessions
in one repository do not collide and no governed content is polluted. Stale
snapshots are garbage-collected opportunistically. `resume`, `clear`,
`compact`, and `fork` sources preserve an existing baseline: compaction must
not launder violations introduced earlier in the same working-tree session.

**Evaluation.** At Stop the hook enumerates the same file set, compares it to
the baseline, and derives, per changed file, the **introduced lines** using
the same deterministic diff definition as ADR-018 (insert/replace opcodes,
baseline as `before`, current as `after`). New files introduce everything;
deleted files introduce nothing and are never blocked (deletion-only
remediation must pass). New files beyond the per-file content budget are not
read or evaluated; they are reported as unevaluated instead.

One exact-content exception applies: a baseline path that has vanished while
byte-identical content reappears at a new path is a move of pre-session
content. Byte identity is **not policy identity**: ADR-020 makes path part
of rule applicability, so a move can carry excluded-path bytes into a
governed path. Such moves are therefore evaluated through the core check
path twice — with the real new target path and with the previous target
path, using an identical query label so retrieval gating is identical. The
move blocks only when a typed rule's violation was not applied at the
previous path but applies at the new one (policy meaning changed in the
restricting direction); legacy rules carry no path dimension and never block
on a move. Typed UNKNOWN outcomes on either side fail open with visible
notes. Provenance is never guessed: when several vanished paths share the
same bytes, no source can be proven, so the target is reported as an
ambiguous, unevaluated delta through Stop feedback, leaving CI as the
backstop. No selector logic is duplicated in the adapter; both evaluations
are ordinary trusted CLI verdicts.

Each candidate is checked through the existing enforcement path with its
real target path, preserving ADR-020 applicability authority end to end.

**Attribution correctness.** Because the baseline is captured at session
start, dirty state that existed beforehand is indistinguishable from
"before", and only the session's inserted/replaced lines are checked. A
pre-existing violation does not block an unrelated session edit; removing a
pre-existing violation introduces nothing; a violation added on top of
pre-existing dirty lines is caught by its own delta.

**Loop safety.** ``stop_hook_active`` is true precisely on the
repair-recheck turn — the one turn that must be evaluated — so it does **not**
bypass the gate. Loop safety comes from determinism instead: the boundary
blocks only on trusted verdicts over the session delta, so a genuine repair
passes on re-evaluation, and Claude Code's documented eight-consecutive-block
cap bounds any unresolvable case. The baseline is *not* refreshed after a
block: the next Stop re-evaluates the same session delta, so repairs converge.

**Explicit operational states.** The gate refuses to fabricate results, and
because Claude never sees stderr from an exit-0 hook (it goes to the debug
log only), every degraded-but-permit state is additionally surfaced to the
agent as non-blocking Stop feedback (`hookSpecificOutput.additionalContext`)
through a single shared emit path:

- No baseline exists (plugin installed mid-session): one is created at Stop,
  a diagnostic records that earlier changes could not be attributed, and the
  turn proceeds. Later Stops in that session enforce normally.
- Baseline capture failure (repository enumeration failure or storage
  error): reported explicitly; no snapshot is persisted, so a transient
  failure can never masquerade as a valid empty baseline and blame the whole
  tree on the session. The same rule holds at SessionStart, whose plain-text
  stdout reaches Claude's context.
- Not a git work tree: the gate reports itself inactive and does not block.
- An artifact unreadable at capture time records a placeholder entry rather
  than being omitted, so if it becomes readable later it is reported as *not
  evaluated* instead of attributed to the session as new.
- A file whose baseline content is unavailable (oversized or binary) but
  which changed during the session is reported as *not evaluated*; it is
  never silently passed and never blocked on guessed content.
- Checker transport failures (crash, timeout, untrusted verdict) fail open
  per file with visible diagnostics, matching the established transport
  failure policy; they never become violations and never become silent PASS.

In strict mode a trusted blocking verdict on session-introduced content
blocks the Stop with actionable reasons naming the file and rule. Warn mode
reports via non-blocking feedback and never blocks, mirroring the edit gate.

### 3. Claim boundaries

Allowed claims, exactly:

- deterministic pre-mutation enforcement for supported direct file tools
  (`Edit`, `Write`, `MultiEdit`);
- deterministic pre-execution enforcement for explicitly supported
  reconstructable shell mutations (the class-A grammar above);
- post-mutation/pre-completion session-delta enforcement through `Stop`;
- final repository verification through CI where configured.

Forbidden claims: that all shell writes are enforced before execution; that
all shell commands are understood; that Stop prevents the original write;
that retrieval quality controls deterministic typed-rule enforcement; or that
every filesystem mutation path is intercepted before execution.

### 4. Boundaries preserved

Retrieval (scoring, weights, thresholds, top-K, role guidance) is untouched;
the shell and Stop surfaces reuse the existing `"edit to <file_path>"` query
construction verbatim. Rule matching, `ConflictDetector`, and path-selector
logic live only in core; the integration layer parses provider events,
classifies operations, reconstructs deterministic proposals, computes the
session delta, and translates trusted verdicts — nothing more. Applicability
remains rule/path based through `--target-path`; there is no
integration-specific applicability mechanism, and
`PATH_APPLICABILITY_UNKNOWN` continues to surface as an operational outcome
rather than a PASS.

## Consequences

- The most common shell-write pattern agents actually emit (quoted heredocs)
  is prevented before execution; the residual shell space is caught at
  completion instead of being invisible until CI.
- Pilot users get an honest coverage table: prevent (direct tools + supported
  shell writes), catch (session delta), verify (CI).
- The Stop boundary depends on git for file discovery and on UTF-8-readable,
  size-capped content for diffing; those limits are surfaced operationally,
  not hidden.
- Session snapshots consume temp-directory space proportional to repository
  text content (bounded by budget) and are cleaned up opportunistically.
- A malicious actor who disables git, floods the tree with oversized files,
  or mutates the temp directory can degrade the catch stage; degradation is
  observable by design. The prevent stage is unaffected.

## Alternatives considered

**Full shell interpretation.** Rejected: unknowable semantics, guaranteed
false positives/negatives, and an unmaintainable parser.

**Blocking all potentially-mutating shell commands.** Rejected: turns every
build, test, and generator invocation into a prompt; pilots would disable the
hook entirely.

**Whole-tree final-state compliance at Stop (naive final `git diff`).**
Rejected: blames pre-existing dirty state on the session, recreating the
ADR-018 wall at a new boundary, and breaks remediation-by-deletion.

**Baseline/suppression ledger in the repository.** Rejected for the same
reason ADR-018 rejected it: a second source of truth that drifts.

**Amending ADR-018 instead of a new ADR.** Rejected: ADR-018 scopes itself to
the edit gate; extending its reach silently would blur which boundaries carry
its guarantees. This ADR references its definition rather than mutating it.

## Related

- ADR-017: Enforcement Scope Is Independent of Retrieval Scope
- ADR-018: Introduced-Delta Enforcement at the Edit Gate (definition reused)
- ADR-019: Typed Literal Rule Contract
- ADR-020: Explicit Path Applicability for Typed Rules
- Issue #251 (repo-wide audit boundary; explicitly out of scope here)
