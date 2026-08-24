# M1e-a analysis — native `Update File` probe (run 20260824T113630Z)

Pinned Codex CLI 0.149.1 / Windows / `codex exec`, trusted logger hooks, no
bypass. Seeded `service.py` (9 lines, known bytes); prompt asked for two
edits: change `existing()` to return 42, append `third()`.

## Observed `Update File` grammar (captured PreToolUse payload)

```
*** Begin Patch
*** Update File: <ABSOLUTE path>          <- absolute path chosen by the model
@@                                         <- bare @@ hunk header, NO line numbers
 def existing():                           <- context: single SPACE prefix
-    return 1                              <- removed: MINUS prefix
+    return 42                             <- added: PLUS prefix
@@
 def second():
     return 2                              <- context lines carry a leading space
+
+
+def third():
+    return 3
*** End Patch
```

Grammar facts:

- Hunk headers are bare `@@` — unlike unified diff there are **no
  line-number ranges**, so anchoring is purely by context-line matching.
- Unchanged lines inside a hunk carry one leading space; removed `-`;
  added `+`.
- **The target path was absolute** here, whereas R0's `Add File` payload used
  a repo-relative path. Both forms must be handled; resolution against the
  payload `cwd` remains deterministic.
- The model made one read-only Bash call *before* patching
  (`Get-Content ... ; git diff`) and another *after* (`git diff --check`).
  PreToolUse fired for those Bash calls too — relevant later for M2 shell
  scope, harmless here.

## Determinism findings

| Question | Result |
|---|---|
| Target path deterministic | YES — resolvable (absolute or cwd-relative), single path |
| Introduced lines derivable per ADR-018 | YES at **content level**: `+` lines minus prefix = added lines; combined with the current-file snapshot, the standard insert/replace diff of (snapshot -> reconstructed final) yields exactly the patch's added lines |
| Byte-exact final state derivable | **NO** — see below |

### The byte-level finding

Reconstructing the expected final text (context kept, `-` dropped, `+`
inserted) and hashing every plausible variant produced exactly ONE match to
the allow-arm recorded sha256 — and it reveals **mixed line endings** in the
resulting file:

- Original seed lines checked out through git (`core.autocrlf=true` global)
  were **CRLF** on disk when patched.
- The applied result is neither all-LF nor all-CRLF: original-region bytes
  keep CRLF while rewritten/inserted regions come out **LF**
  (per-line EOL assignment recovered uniquely by exhaustive search).
- Therefore "allow produces exactly the reconstructed result" holds at the
  line-content level but **not at the byte level**: byte-exact final-state
  prediction requires modeling Codex's internal EOL rewriting, which is
  version-specific behavior we should not encode.

Consequence for Mneme: ADR-018 gate semantics operate on introduced *lines*,
not whole-file bytes, so enforcement is unaffected — but any future audit
logic must never assume the post-patch bytes are a pure function of
(payload + snapshot).

## Deny arm

- Seed file byte-for-byte unchanged (`seed_changed=False`; worktree clean).
- Events: PreToolUse apply_patch -> denied; **no PostToolUse**;
  Stop fired and completed.
- Transcript: `Command blocked by PreToolUse hook: R0 probe deterministic deny`.

Note: this arm proves Codex-level deny semantics for updates (same mechanism
R0 proved for adds). Content-aware denial of updates requires parser support
(M1e-b); today's parser correctly FAIL_OPENs unknown operations instead of
pretending to evaluate them.

## Harness notes

No runner defects this run. One analysis-tooling correction (not a harness
or Codex issue): the live sandbox file must not be read for the allow-arm
byte check because the deny arm legitimately restores the baseline; the
authoritative bytes exist only as the allow-arm recorded hash.

## Exit-gate assessment

1. Trusted PreToolUse fires reproducibly — YES (and deny-arm equivalent).
2. Target path deterministic — YES (both absolute and relative forms occur).
3. Proposed final state / introduced lines reconstructable without ambiguous
   interpretation — **YES at introduced-content level** (ADR-018's level);
   NO at byte level (mixed-EOL rewrite).
4. Deny prevents the update — YES.
5. Allow produces the reconstructed result exactly — **content YES /
   bytes NO**.

Verdict: `Update File` is **pre-interceptable for introduced-content
enforcement**, with an explicit caveat that byte-exact final-state claims are
out of reach on this build/platform. Freezing a characterization fixture
before implementing Update support is justified; the fixture must pin the
observed absolute-path form, bare `@@` hunks, space-context lines, and the
EOL caveat.
