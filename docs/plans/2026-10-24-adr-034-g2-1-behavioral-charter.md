# ADR-034 / G2-1: Layer 1 behavioral charter (pre-write numeric check, new-file `Write`)

**Date:** 2026-10-24
**Status:** **ACCEPTED** by the owner on 2026-10-24: G2C-O1 to G2C-O6, as in
`9a0c886a`, after the architecture review of revision 2. The prerequisite
ADR-034 amendment #631 merged as `f0c16773`.

Accepting this charter authorizes **no implementation**. Implementation needs
the separate, reviewed `[layer1-freeze]` amendment in §9.

**Revision 2** (2026-10-24) responds to the architecture review of draft 1,
which was ACCEPT WITH REQUIRED CORRECTIONS:

- **G2C-F1:** strict rules tying the subject kind to each matcher reason,
  plus an explicit expected-input contract for every consumer of
  `assess_verdict` (§5).
- **G2C-F2:** a byte-preserving carrier and an exact byte contract. Invalid
  UTF-8 is an operational error (§3.2, §3.5, §4.1), and CRLF, LF,
  byte-order-mark and non-ASCII cases are pinned (§8.C).
- **G2C-F3:** the pinned host version is mandatory in the host-event record
  (§6.2).

**Repository baseline examined:** `MnemeHQ/mneme` `main` at
`adf50933d0beac255ac2a134e00ee13d40442302`. Line numbers refer to
`0d367fc6`, where they were verified for the G2 proposal. The files cited
here are unchanged between the two commits.

**Normative anchors:**

- [ADR-034](../adr/ADR-034-static-numeric-upper-bound-typed-rule.md) §6a,
  §7a and owner rulings G2-O1 to G2-O6, as folded in #631 (head `b49b0ba4`).
  #631 merged as `f0c16773` before this charter was accepted.
- The [G2 proposal](2026-10-24-adr-034-g2-new-file-write-amendment-proposal.md),
  revision 2, `08e0f9ac`, merged in #630 as `97143065`. Its §6 is the
  validation scope this charter freezes.
- The [G1 behavioral charter](2026-10-22-adr-034-g1-behavioral-charter.md).
  Its §6 result contract and the R1 payload rules apply unchanged unless this
  charter says otherwise.
- ADR-018, ADR-020, ADR-021, ADR-029 and ADR-033.
- [`layer1-freeze-e73ff7d.md`](../architecture/layer1-freeze-e73ff7d.md):
  the G1 entry, including the F2 consequence (lines 939–944) and the parity
  clause (lines 903–904).

## 1. Purpose and scope

The first G2 slice adds one capability. When Claude Code `Write` creates a new
`.py` file whose path the checker has verified absent, that file's complete
proposed source is checked for `FORBID_NUMERIC_ABOVE` before it is written.
This uses the unchanged M4 matcher, and the check happens through the
existing check pipeline and hook.

The slice must:

- block a recognized violation before mutation, in strict mode;
- never turn an unevaluated result into compliance;
- leave every result that involves no applied numeric rule byte-identical
  to today's;
- bind a host-event record to the checker subject (ADR-029), so that
  "relevant enforcement observed" can be claimed. That claim is allowed only
  when this binding exists.

**Not part of this slice:**

- `Write` over an existing file (including an empty one), `Edit`,
  `MultiEdit`, deletion and renames;
- Bash, including class-A heredoc writes that create new files;
- the Stop/session-delta boundary, which is unchanged;
- the Agent SDK, LangChain, MCP and CI;
- any change to the M4 matcher, `numeric_rule.py` semantics,
  `DecisionRetriever`, `ConflictDetector`, `FORBID_LITERAL` semantics, memory
  persistence or rule identity;
- any ADR-033 availability-policy change, exception or new default;
- new numeric forms or other languages;
- activation of `FORBID_NUMERIC_ABOVE` in this repository's memory, or
  import of ADR-034 into it;
- P0-B.

**No claim** is made until the independent validation in §8.D passes.

**Layer 1 boundary.** This changes hook enforcement behavior, adds a CLI
input and adds JSON evidence. Accepting this charter is not a Layer 1 freeze
amendment (§9).

## 2. Verified baseline and hazards

| Surface | Verified | Necessary change / boundary |
|---|---|---|
| CLI inputs | `--input` and `--source-file` are a required mutually exclusive group. `--source-file` is rejected with `--target-path` (`cli.py:599-601`). `--input` with numeric rules binds `SourceSubject.unverified` (`cli.py:626-636`) | Add a third member of the group (§3). Legacy `--input` and `--source-file` stay byte-identical |
| Subject emission | `subject` appears when the input is complete source **or** any numeric trace exists (`cli.py:407-412`). `has_numeric_rules` counts every numeric trace, including `EXCLUDED` ones (`enforcer.py:147-151`) | The new input's subject is relabelled only when a numeric rule is `APPLIED`. Otherwise it emits exactly today's unverified record (§3.5) |
| G1 binding guard | Runs only under `source_file is not None` (`cli.py:646-658`) | The new input has its own guard (§3.4) |
| Hook materialization | `_read_current(missing_ok=True)` collapses "missing", "unreadable" and "not UTF-8" into `""` (`hook.py:93-107`). An empty existing file also diffs as new (`hook.py:156`) | Routing uses a separate absence probe and never relies on `_read_current` (§4.1) |
| Hook memory selection | Starts at `Path(target).resolve().parent` (`hook.py:759-772`) | Unchanged. The probe resolves the same target |
| Hook trust validation | `_numeric_trace_problem` / `_numeric_record_problem` check matcher records and subject digest agreement (`hook.py:408-519`). Nothing checks that a matcher status or reason agrees with the subject kind. The non-source record is required only for input with no target path (`hook.py:399-426`) | Add the kind/reason coherence and join checks (§5) |
| Shared validator | `assess_verdict(stdout, returncode, requested_mode)` (`hook.py:621-647`) has no expected-input parameter. It is imported by the Agent SDK adapter (which LangChain uses), `antigravity`, `codex_cli` (gate and stop audit), `hermes` and `kiro`. Most of these also render `format_applicability_reason` | Add a keyword-only expected-input contract whose default keeps every existing caller's coherent results unchanged (§5). Routed wording is changed only through a caller-side option (§4.3) |
| Hook carrier encoding | The carrier is written in text mode (`NamedTemporaryFile(mode="w", encoding="utf-8")`, `hook.py:794-798`), and `--input` reads it with `read_text` (`cli.py:618`). On Windows, LF becomes CRLF on disk, and a CRLF in the content becomes CR CR LF, which reads back as two newlines. Content containing an unencodable lone surrogate raises inside `_invoke_check` | Routed events use a byte-preserving binary carrier (§4.1). The unrouted path is unchanged. The CRLF doubling is a pre-existing defect, recorded for a separate fix and not changed here (§7) |
| M-a | A trusted, coherent violation stays actionable while evaluation is incomplete (`hook.py:522-533`, `917-923`) | Unchanged |
| Availability | Under an AUTHORIZED declaration, `INCOMPLETE` routes to `EVALUATION_INCOMPLETE` (`availability.py:154-197`) | Unchanged (G2-O5) |
| Benchmark seam precedent | `MNEME_HOOK_CHECK_TRANSPORT` is benchmark-only and unset by default (`hook.py:218-227`) | Model for the §6.3 evidence seam |

**Hazard H1: silent widening.** If routing used `_read_current`'s `""`, an
unreadable or non-UTF-8 existing file would be checked as a new one. A
whole-file numeric result would then be attributed to an existing file,
against ADR-018 and G2-O1. §4.1 prevents this.

**Hazard H2: subject relabelling.** If every routed call reported
`proposed_new_source`, payloads with only `EXCLUDED` numeric rules would
change. That breaks F3 parity. §3.5 prevents this.

**Hazard H3: trust by assertion.** A hook-side absence check must never be
what makes a result complete. Only the checker's own verification counts
(G2-O3). §3.2 and §5 enforce this.

**Hazard H4: digest drift.** A text-mode carrier would make the digest of the
bytes on disk differ from the SHA-256 of the `Write` content, and would
change the text the matcher sees. That breaks the §5 digest join. §4.1
requires a binary carrier.

## 3. Input and invocation contract

```text
mneme check --memory .mneme/project_memory.json \
  --proposed-new-file <tmp-text-file> --target-path src/router_v2.py \
  --query "edit to src/router_v2.py" --mode strict --json
```

1. **Spelling (G2-O6; proposed here).** `--proposed-new-file <path>` becomes
   a third member of the required mutually exclusive input group. It
   **requires** `--target-path`. Without one, it is an operational error
   (`_error_exit`), never a fallback.
   - The file it names is a carrier of text only. Its own path never takes
     part in applicability, identity or evidence.
   - `--source-file` stays incompatible with `--target-path`, and legacy
     `--input` is unchanged.
2. **Checker-established preconditions (ADR-034 §6a, G2-O3).** The checker
   evaluates these at run time against `--target-path`, in this order:
   1. `os.lstat` raises `FileNotFoundError`. Any other result or error fails
      this precondition.
   2. The parent directory resolves strictly. Its lexical and resolved forms
      are equal under `os.path.normcase`.
   3. The target is inside `policy_root(memory)`.
      `normalize_input_path(target, memory)` succeeds and gives the governed
      path.
   4. The suffix is exactly `.py`.
   5. The carrier bytes decode as strict UTF-8.

   **Consequence of precondition 2:** a new file in a directory that does
   not exist yet fails it, so its write stays on the legacy path. This is
   accepted, conservative noncoverage (§7).

   **Precondition 5 is handled separately (G2C-F2, ruling G2C-O6).** If the
   carrier is not valid UTF-8, the result is an **operational error**: an
   `_error_exit`, a non-verdict exit, and no payload, so it is untrusted
   under ADR-033 §2.
   - It is never a legacy fallback and never PASS.
   - This matches `--source-file` (`cli.py:584-586`).
   - The legacy `--input` path has no defined result for undecodable text: it
     raises from `read_text`. So there is no legacy verdict to stay identical
     to.
   - ADR-034 §6a, as reconciled in #631, permits this explicitly for
     precondition 5. It is stricter than "unverified": no complete-source
     claim, and no result.
   - The hook never sends such a carrier (§4.1).
3. **When preconditions 1–4 fail, the result is legacy.** The run is
   evaluated exactly as `--input <same carrier> --target-path <same target>`
   would be today, and its output is byte-identical to that. Text is read
   through the same strict UTF-8, universal-newline decoding as
   `read_text`.
   - Numeric rules become `INCOMPLETE_SOURCE_INPUT` wherever they are
     `APPLIED`.
   - This is not an error. ADR-018 already checks a missing or unreadable
     `Write` target's full content conservatively.
   - It covers a file that appears between the hook's probe and the
     checker's (§4.1) without creating a second fallback path.
4. **Target binding (ADR-034 §6a).** When the preconditions hold:
   - every typed-rule applicability record that carries an `input_path` must
     equal the governed path from precondition 3;
   - a mismatch, or a governed path that cannot be established after
     precondition 3, is an operational error. That means a non-verdict exit
     with no `mneme.check/v1` payload, so the result is untrusted under
     ADR-033 §2.

   This guard is implemented for this input. It is not reached through the
   `source_file` branch.
5. **Subject and legacy parity (ADR-034 §7a).** The checker reads the
   carrier **once, as bytes** (`read_bytes`) and never imports or executes
   it. Both paths below derive from that one read.
   - **Complete-source path** (a numeric rule is `APPLIED`):
     - the subject digest is the SHA-256 of those exact bytes;
     - the evaluated text is their strict UTF-8 decoding, with no newline
       translation and no byte-order-mark stripping, as with G1
       `--source-file`;
     - the matcher and the literal rules both evaluate that same text.
   - **Legacy path** (no numeric rule `APPLIED`, or preconditions 1–4
     failed): the text is decoded exactly as `read_text(encoding="utf-8")`
     would decode it, so the result is byte-identical to `--input` on the
     same carrier.
   - **If at least one `FORBID_NUMERIC_ABOVE` rule is `APPLIED` at the
     governed path,** numeric evaluation uses complete-source semantics, and
     the payload's `subject` record is:

     ```json
     {"input_kind": "proposed_new_source", "subject_sha256": "<hex>",
      "source_path": null, "target_path": "<resolved absolute target>",
      "memory_path": "<resolved memory>", "governed_path": "<policy-relative>",
      "absence_verified": true, "surface": "mneme check",
      "surface_version": "<x.y.z>", "runtime": "<label>"}
     ```

     `target_path` and `absence_verified` are additive keys, and only this
     kind carries them. `target_path_declared` is omitted, as for G1.
   - **If no numeric rule is `APPLIED`** (memory has none, or every numeric
     rule is `EXCLUDED` or `UNKNOWN` there), stdout and exit status must be
     **byte-identical** to the legacy `--input` + `--target-path` run on the
     same carrier and target. That includes the absent or unverified
     `subject` record. Nothing is relabelled.
6. **Outcomes.** These are as in ADR-034 §4 and the G1 charter §6, including
   O2:
   - a new file missing a declared source is `MATCHER_UNEVALUATED` /
     `SOURCE_NOT_FOUND`;
   - a parse failure is `PARSE_FAILURE`;
   - `PARTIAL` is a FAIL with `evaluation_complete=false` and exit 2.

   The exit matrix is unchanged.
7. **What the digest means.** It identifies the evaluated carrier bytes. It
   makes no claim about the bytes the host lands, and no claim about
   time-of-check/time-of-use (TOCTOU) effects.

## 4. Hook routing (Claude Code `PreToolUse`, `Write` only)

### 4.1 Absence probe and routing

The hook routes an event to `--proposed-new-file` **only if all** of the
following hold. Otherwise the event takes today's path unchanged.

- `tool_name == "Write"`;
- `_resolve_target` yields an absolute target;
- the target's suffix is `.py`;
- a dedicated probe, `os.lstat(target)`, raises `FileNotFoundError`. This
  probe never uses `_read_current`;
- `tool_input["content"].encode("utf-8")` succeeds under strict errors.
  Content with a lone surrogate is not routed, and keeps today's behavior on
  the unrouted path unchanged.

**Byte-preserving carrier (G2C-F2).** For a routed event, the hook writes
exactly `content.encode("utf-8")` to the carrier in **binary** mode, with no
newline translation and no added byte-order mark. The SHA-256 of those bytes
is the join digest (§5.2 rule 4, §6.2).

The unrouted path keeps its text-mode carrier byte for byte (§2, §7). On
Windows, a routed event whose content contains CR may therefore see
different text than today's text-mode path would give it. Today's path
doubles CRLF line breaks.

This is an **explicitly authorized, routed-only correction** (ADR-034 §7a,
"Routed carrier encoding", as reconciled in #631).
- **Parity is at the checker level only.** It holds between
  `--proposed-new-file` and `--input` on the same carrier (§3.3, §3.5).
- **No hook-level historical parity claim.** None is made for routed events
  whose content contains CR.
- **Pinned by tests:** §8.C.10.

The hook's probe is advisory: it only selects which call to make. The checker
re-establishes every precondition (§3.2), so the hook's probe never makes a
result trusted (H3).

**Same text either way.** For a routed event, the carrier holds
`tool_input["content"]`. This is exactly today's introduced content for a
missing target (`introduced_between("", content)` returns `content`). The
literal-rule input is therefore identical by construction.

**Single path (G2-O4).** A routed event makes exactly one checker call, with
`--proposed-new-file` in place of `--input`. Every other argument is
unchanged: `--memory`, `--query "edit to {rel}"`, `--mode`, `--json` and
`--target-path`. There is no second call.

### 4.2 Unchanged paths

These keep byte-identical hook behavior, output and exit codes:

- `Edit` and `MultiEdit`;
- `Write` to an existing, empty, unreadable or ambiguous target;
- `Write` to a non-`.py` target;
- Bash (class A, B and C);
- `SessionStart`;
- `Stop`;
- the missing-memory path;
- availability discovery and emission.

### 4.3 Verdict handling

Verdict handling is unchanged: `_run_check`, `assess_verdict`, M-a, strict
and warn, `_emit_defer`, and C2b §17 notes. A trusted
`RECOGNIZED`/`VIOLATION` or `PARTIAL` result blocks with exit 2 in strict
mode, and `format_reason` renders the numeric contract.

The `format_applicability_reason` diagnostic, which currently says
"whole-file audit only", must say what actually happened:

- on a routed event, numeric rules are evaluated on the proposed new file;
- on an unrouted event, it keeps the current text.

`format_applicability_reason` is shared by every integration listed in §2.
The routed wording is therefore selected by a keyword-only caller option,
whose default is today's text. It is never a global replacement. Only the
Claude Code hook's routed calls pass the option, so every other
integration's output stays byte-identical.

## 5. Consumer trust (all `assess_verdict` consumers)

Every rule below makes a result **untrusted**: it is never a verdict, and
ADR-033 handling applies. A payload that already conforms today stays
trusted and unchanged. These rules reject only contradictory payloads.

### 5.1 Expected-input contract (G2C-F1)

`assess_verdict` gains a keyword-only `expected_input` parameter, with values
`"input"` (the default) and `"proposed_new_file"`. Its spelling is fixed in
implementation; the semantics are fixed here.

| `expected_input` | Acceptable `subject.input_kind` |
|---|---|
| `"input"` (default; every existing caller) | no `subject`, or `unverified_input` |
| `"proposed_new_file"` (Claude Code hook, routed events only) | no `subject`, `unverified_input` (legacy result, §3.3/§3.5), or `proposed_new_source` |

**Any other kind is untrusted.** That includes `proposed_new_source` or
`complete_source_file` arriving at a default caller.

**Who uses the default.** No current consumer sends `--source-file` or
`--proposed-new-file`. So the Agent SDK (and LangChain), `antigravity`,
`codex_cli`, `hermes`, `kiro` and the hook's own unrouted, `Stop`, Bash and
rename calls keep the default. They get exactly today's result for every
payload they can legitimately receive.

**Mechanism for unrequested payloads.** An Agent SDK or LangChain caller
that receives an unrequested `proposed_new_source` payload rejects it
through this default. That is the mechanism the draft lacked.

### 5.2 Subject-kind / matcher-reason coherence (G2C-F1)

These rules apply on every call, whatever `expected_input` is. They cover
every `FORBID_NUMERIC_ABOVE` trace with `outcome == "APPLIED"`.

1. **Unverified subject: only the non-source record.** On an
   `unverified_input` subject, every such trace must carry exactly the
   non-source record:
   - `matcher_status` `MATCHER_UNEVALUATED`;
   - `matcher_outcome` `UNEVALUATED`;
   - `primary_reason` `INCOMPLETE_SOURCE_INPUT`;
   - `unknown_sources` exactly
     `[{"kind": "input", "line": null, "reason": "INCOMPLETE_SOURCE_INPUT"}]`.

   That covers both input with a declared target path and input without
   one. It extends today's no-target check (`hook.py:399-426`).

   **What is rejected.** Unverified input can never claim a source-specific
   evaluation. That includes `RECOGNIZED`, `PARTIAL`, and any source-derived
   reason such as `PARSE_FAILURE` or `SOURCE_NOT_FOUND`.
2. **Complete-source subject: `INCOMPLETE_SOURCE_INPUT` is forbidden.** On a
   `complete_source_file` or `proposed_new_source` subject, no trace may
   carry `INCOMPLETE_SOURCE_INPUT`, either as the primary reason or among
   the unknown sources.
3. **Requested-kind coherence.** For `expected_input="proposed_new_file"`:
   - `proposed_new_source` requires at least one `APPLIED` numeric trace;
   - a legacy result (`unverified_input`, or no subject) must satisfy
     rule 1.
4. **Digest join.** For `proposed_new_source`, `subject_sha256` must equal
   the SHA-256 of the exact carrier bytes the hook wrote (§4.1). It must
   also equal every numeric trace's `subject_sha256`.
5. **Path join.** For `proposed_new_source`, `subject.target_path` must equal
   the hook's resolved target under `os.path.normcase`, and
   `absence_verified` must be `true`.

Rules 4 and 5 need hook-side knowledge, so the hook checks them after
`assess_verdict`, on routed events.

## 6. Evidence

### 6.1 Checker evidence

The checker's evidence is the `subject` record (§3.5) plus the existing
per-rule records: `rule_id`, `decision_version_id`, applicability, matcher
status and reason, and outcome. On its own, this is an evaluation of a
hypothetical subject. It never supports "relevant enforcement observed"
(ADR-034 §6a, Evidence class).

### 6.2 Host-event binding (ADR-034 §7a)

The hook builds one record per routed event, covering every field ADR-034
§7a requires:

- **Control:** `surface` (`"claude_code.PreToolUse"`), Mneme version, and
  the **pinned host version, which is mandatory** (G2C-F3, ADR-034 §7a).
  - The event envelope is not relied on to carry the host version.
  - The version comes from the validation context. Before the run, the §8
    harness establishes the pinned Claude Code binary's identity: its
    reported version and the SHA-256 of the executable. The harness supplies
    that identity to the record, for example through a companion
    validation-only variable.
  - The validation report repeats the same identity.
  - If the host identity is missing, cannot be established, or differs from
    the pinned identity, the record **cannot** support "relevant enforcement
    observed". Evidence stays at "execution observed" or below.
  - Recording this identity does not make it an authenticated attestation.
- **Event:** `tool_name`, `file_path` and `cwd` as received, plus every
  host-supplied event identifier present in the envelope (for example
  `session_id`, and a tool-call id). Which identifiers the pinned host
  supplies is established by the §8.B live test, never assumed.
- **Join:** the SHA-256 of the exact carrier bytes, which are
  `tool_input["content"].encode("utf-8")` (§4.1). This must equal the
  checker's subject digest (§5.2 rule 4).
- **Rule and outcome:** for each applied numeric rule, `rule_id`,
  `decision_version_id`, governed path, applicability, matcher status and
  reason, and the hook outcome (`refused` / `proceeded` / `deferred`).

This record is the control's own provenance, not authenticated host
attestation. ADR-025 is not claimed.

### 6.3 Where the record goes

There is no new persistence, telemetry or event system (ADR-029 §3,
ADR-033 §7).

**Proposed:** a validation-only seam, `MNEME_HOOK_EVIDENCE_LOG=<path>`,
modelled on `MNEME_HOOK_CHECK_TRANSPORT`.

- When set, the hook appends the §6.2 record as one JSON line.
- When unset, the default, the hook writes nothing and its behavior, output
  and exit codes are byte-identical.
- It is not a supported user option.
- A write failure is reported on stderr and never changes the hook outcome.

Owner ruling G2C-O2 (§10) decides whether to use this seam or to have the
§8 harness capture the record externally.

**No diagnostics carry content.** Neither the record nor stderr includes the
proposed source.

## 7. Claim boundary and noncoverage

**Claim, after §8.D passes and only then.** On Claude Code `PreToolUse`
(pinned version), a `Write` to a verified-absent `.py` target whose parent
directory exists inside the policy root is refused before mutation, in
strict mode, when the complete proposed source has a recognized
`FORBID_NUMERIC_ABOVE` violation. Such a result is "relevant enforcement
observed" only when §6.2 binds it.

**Noncoverage (stated in every report):**

- **Race:** a file created at the target after the checker's probe and
  before the host's write;
- **Landed bytes:** equality of the checked bytes and the written bytes;
- **New directories:** a new file in a directory that does not exist yet
  (§3.2);
- **Other mutations:** existing-file `Write`, `Edit`, `MultiEdit`, deletion,
  renames and Bash;
- **Other surfaces:** the Agent SDK, LangChain, Stop, CI and MCP;
- **Closed availability:** under an AUTHORIZED closed declaration, a new
  in-scope file that lacks a declared source is still refused as
  `EVALUATION_INCOMPLETE`. The F2 activation restriction stays in force;
- **Hook failure:** what the host does when the hook fails to launch,
  crashes or times out;
- **Unencodable content:** `Write` content with a lone surrogate is not
  routed (§4.1);
- **Pre-existing carrier defect (not fixed here):** on Windows, the unrouted
  path's text-mode carrier doubles CRLF line breaks (§2). It is recorded for
  a separate, reviewed fix, because changing it here would alter legacy
  hook behavior outside this slice.

## 8. Acceptance tests and sequencing

**A. Pre-implementation review.**

- Architecture review of this charter, then owner acceptance.
- Before implementation: #631 merged, and the §9 `[layer1-freeze]` amendment
  approved.

**B. Pinned live host characterization.** Run against a pinned Claude Code
version, under its own scoped authorization, before any support claim.

It establishes:

- which event identifiers the envelope carries;
- that a `Write` to a new path in an existing directory reaches `PreToolUse`
  with the complete `content`;
- that exit 2 leaves the target absent;
- what the host does for a missing parent directory;
- the pinned host identity used by §6.2: its reported version and the
  SHA-256 of the executable.

It must not use the §8.D corpus.

**C. Regression matrix (public, before unblinding):**

1. **Legacy parity.** Golden byte comparisons of stdout and exit code between
   `--proposed-new-file` and `--input` (same carrier and target), for:
   - memory with no numeric rule;
   - numeric rules that are all `EXCLUDED`;
   - numeric rules that are all `UNKNOWN`;
   - any failed precondition (existing file, existing empty file, symlink,
     dangling link, link component, missing parent, out of root, non-`.py`).

   Existing `--input` and `--source-file` goldens stay unchanged.
2. **Preconditions.** One positive case and one negative case for each of
   the §3.2 preconditions, including a permission error on `lstat` (it must
   not count as absence), Windows case-insensitive normalization, and a
   missing `--target-path` (an operational error). An invalid UTF-8 carrier,
   such as a lone continuation byte or an overlong encoding, gives an
   operational error with no payload, never a fallback verdict. Existing
   `--input` and `--source-file` behavior on invalid UTF-8 is unchanged.
3. **Binding guard.** An injected applicability `input_path` mismatch gives a
   non-verdict exit with no payload.
4. **Numeric outcomes on `proposed_new_source`.** `EXCEEDS` → FAIL;
   all `WITHIN` → PASS; missing source → `SOURCE_NOT_FOUND`; unsupported
   form → unevaluated; `PARTIAL` keeps its unknown sources; parse failure; a
   leading byte-order mark is a non-clean result; `EXCLUDED` target → no
   numeric claim, and parity applies.
5. **Hook routing.**
   - Routed versus unrouted events, in every combination from §4.1/§4.2.
   - Exactly one checker invocation per event.
   - Unrouted events are byte-identical to `main`.
   - H1: unreadable or non-UTF-8 existing files are never routed.
   - Race: a file created between the hook's probe and the checker's gives
     the legacy result.
6. **Consumer trust (§5).**
   - **Expected-input contract (§5.1).** Each acceptable and unacceptable
     subject kind, under both `expected_input` values. A
     `proposed_new_source` or `complete_source_file` payload sent to each
     default consumer is untrusted: the Agent SDK, LangChain, `antigravity`,
     `codex_cli` gate and stop audit, `hermes` and `kiro`. Every existing
     coherent payload golden for those consumers is unchanged.
   - **Coherence rules (§5.2).** Rules 1–5 are each violated in turn. On an
     `unverified_input` subject, with and without a declared target,
     `RECOGNIZED`, `PARTIAL`, `PARSE_FAILURE`, `SOURCE_NOT_FOUND`,
     `AMBIGUOUS_BINDING` and `UNRECOGNIZED_FORM` are each rejected. On a
     complete-source subject, `INCOMPLETE_SOURCE_INPUT` is rejected.
7. **Hook outcomes.** Strict mode blocks with exit 2 and the numeric
   contract reason. Warn mode defers. Unevaluated results under availability
   `open` proceed with a diagnostic. Under AUTHORIZED `closed`, the refusal
   is `EVALUATION_INCOMPLETE`. A literal violation together with numeric
   `NO_VIOLATION` still blocks. Literal behavior is otherwise unchanged.
8. **Evidence.**
   - The §6.2 record is complete and joins by digest.
   - Mismatched or missing records never count as relevant enforcement
     observed.
   - The seam is inert when unset (if G2C-O2 adopts it).
   - A record with a missing, unestablished or mismatched host identity never
     supports relevant enforcement observed (§6.2).
   - No diagnostic contains source content.
9. **Untouched surfaces.** These have no diff: Stop, Bash,
   `ConflictDetector`, `DecisionRetriever`, the M4 matcher modules, and the
   adapters of the other integrations. Those integrations change only
   through the shared validator's default-preserving parameter (§5.1) and the
   default-preserving `format_applicability_reason` option (§4.3).
10. **Byte contract (G2C-F2).** Cases, run on Windows and POSIX for both
    `--proposed-new-file` and the routed hook:
    - LF-only, CRLF, a lone CR, and mixed line endings;
    - a leading UTF-8 byte-order mark, which gives `PARSE_FAILURE` on the
      pinned CPython 3.12.10, never a clean result;
    - non-ASCII identifiers, strings and comments;
    - an empty file.

    For each case:
    - the carrier bytes equal `content.encode("utf-8")`;
    - the subject digest equals their SHA-256;
    - the matcher sees the strict decoding with no newline translation;
    - parity cases still match `--input` on the same carrier;
    - content with a lone surrogate is not routed, and its unrouted behavior
      matches `main`;
    - the unrouted text-mode carrier stays byte-identical to `main`.

**D. Independent validation (proposal §6 scope, now frozen here).**

- **Corpus:** a new synthetic corpus of PreToolUse envelopes, run against
  temporary repositories. The sealed M4 corpus is not reused as blind
  evidence.
- **Independence:** the corpus author is independent of the implementer, and
  the implementer has no access to the corpus, its answer key or the
  author's transcripts.
- **Freezing:** source and harness pins are frozen before scoring.

**Required results:**

- zero unsafe passes;
- zero false blocks in supported scenarios, scored under availability
  `open`;
- zero mutations after a block (the target stays absent);
- every unevaluated case gets the correct primary reason;
- 100% legacy parity on the parity class;
- 100% evidence binding;
- two byte-identical runs.

**Failure policy.** Failures are reported honestly, with no tuning against a
revealed holdout. The pre-scoring record states denominators and a failure
policy before unblinding, as M4 did (#625).

**E. Delivery.**

- One bounded change, or a series that cannot route any event until the
  checker, the trust rules and the evidence are all present together.
- No activation in this repository's memory.
- Existing tests stay green.

## 9. `[layer1-freeze]` amendment scope (separate PR and review)

After this charter is accepted, a PR titled
`[layer1-freeze] ADR-034 G2 pre-write numeric check for new-file Write` adds
a bounded authorization.

**It permits only:**

- the `--proposed-new-file` input (§3);
- the hook routing (§4);
- the trust rules (§5);
- the evidence record and seam (§6), as ruled;
- the byte-exact routed carrier, as the authorized routed-only correction of
  today's text-mode line-ending handling (§4.1).

**It pins** this charter and the §8.C regressions.

**It preserves:**

- deterministic retrieval;
- `FORBID_LITERAL` semantics;
- byte-identical legacy results whenever no numeric rule is `APPLIED`;
- the ADR-018 delta gate for every unrouted event;
- the F2 activation restriction.

**It states explicitly** that it does not authorize:

- CI;
- existing-file delta attribution;
- Bash or Stop numeric evaluation;
- Agent SDK or LangChain pre-write coverage;
- ADR-033 changes;
- any enforcement claim before §8.D passes.

## 10. Owner rulings requested

| ID | Question | Proposed answer |
|---|---|---|
| G2C-O1 | Transport spelling (completes G2-O6) | `--proposed-new-file <carrier>`, which requires `--target-path` and is mutually exclusive with `--input` and `--source-file` |
| G2C-O2 | Where the host-event record goes | The validation-only `MNEME_HOOK_EVIDENCE_LOG` seam, inert by default (§6.3). Alternative: capture by an external harness only, with no hook change |
| G2C-O3 | Precondition failure under the new input | For preconditions 1–4: legacy-equivalent evaluation, byte-identical to `--input` on the same carrier (§3.3), not an operational error |
| G2C-O4 | Missing parent directory | Not routed; stated noncoverage (§3.2, §7) |
| G2C-O5 | Hook diagnostic wording for routed events | Update `format_applicability_reason` only on routed events that have numeric records, through a default-preserving caller option (§4.3) |
| G2C-O6 | Invalid UTF-8 carrier (precondition 5) | An operational error with no payload, as for `--source-file`. Never a legacy fallback or PASS (§3.2) |

## 11. Review history

- **Draft 1** (2026-10-24): PROPOSED.
- **Review of draft 1: ACCEPT WITH REQUIRED CORRECTIONS.**
  - G2C-F1: subject-kind and reason coherence; expected-input contract.
  - G2C-F2: byte-preserving carrier; invalid-UTF-8 semantics; pinned byte
    cases.
  - G2C-F3: mandatory pinned host identity.

  Recommended dispositions: G2C-O1, O4 and O5 accept; O2 accept subject to
  F3; O3 accept subject to F2.
- **Revision 2** (2026-10-24): resolves F1–F3, adds G2C-O6, and extends §5.1
  to every `assess_verdict` consumer (`antigravity`, `codex_cli`, `hermes`
  and `kiro`, in addition to the Agent SDK and LangChain). Still PROPOSED.
- **Status review of revision 2:** F1–F3 closed. Two wording conflicts were
  reconciled in one pass, with the ADR text in #631:
  - an invalid UTF-8 carrier is an operational error, explicitly permitted
    by ADR-034 §6a;
  - the routed byte carrier is an authorized, routed-only correction, with
    no hook-level historical parity claim (ADR-034 §7a, §4.1 here).

  Recommended: accept G2C-O1 to G2C-O6 together.
- **Owner acceptance:** 2026-10-24, G2C-O1 to G2C-O6 as in `9a0c886a`,
  recorded after #631 merged. No implementation is authorized.
