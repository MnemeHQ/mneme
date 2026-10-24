# ADR-034 / G2-1: Layer 1 behavioral charter (pre-write numeric check, new-file `Write`)

**Date:** 2026-10-24
**Status:** **PROPOSED.** This charter is not accepted. Accepting it would
authorize **no implementation**. Implementation would also need the
separate, reviewed `[layer1-freeze]` amendment in §9.

**Repository baseline examined:** `MnemeHQ/mneme` `main` at
`adf50933d0beac255ac2a134e00ee13d40442302`. Line numbers refer to
`0d367fc6`, where they were verified for the G2 proposal. The files cited
here are unchanged between the two commits.

**Normative anchors:**

- [ADR-034](../adr/ADR-034-static-numeric-upper-bound-typed-rule.md) §6a,
  §7a and owner rulings G2-O1 to G2-O6, as folded in #631 (head `b49b0ba4`).
  **This charter can be accepted only after #631 merges.**
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
| Hook trust validation | `_numeric_trace_problem` / `_numeric_record_problem` check matcher records and subject digest agreement (`hook.py:408-519`). Nothing checks that a `RECOGNIZED` record comes with a complete-source subject kind | Add the kind and join checks (§5) |
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
3. **When a precondition fails, the result is legacy.** The run is
   evaluated exactly as `--input <same carrier> --target-path <same target>`
   would be today, and its output is byte-identical to that.
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
   carrier once, hashes the exact bytes with SHA-256 and evaluates that
   snapshot. It never imports or executes it.
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
  probe never uses `_read_current`.

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

This is an output change, and its scope is limited to events that have a
numeric record.

## 5. Consumer trust (hook)

The following additions to `_verdict_inconsistency` /
`_numeric_record_problem` are required. Each violation makes the result
**untrusted**, so ADR-033 handling applies and it is never a verdict:

1. **Kind/status coherence.** A numeric trace with `matcher_status`
   `RECOGNIZED` or `PARTIAL` requires `subject.input_kind` to be
   `complete_source_file` or `proposed_new_source`.
   - A `RECOGNIZED` or `PARTIAL` record on an `unverified_input` subject is
     contradictory.
   - This rule applies to every hook call, not just routed ones.
2. **Requested-kind coherence.** If the hook sent `--proposed-new-file`, the
   subject kind must be either:
   - `proposed_new_source`, with at least one `APPLIED` numeric trace; or
   - the legacy record (`unverified_input`, or no subject), with no
     `APPLIED` numeric trace that has a non-`INCOMPLETE_SOURCE_INPUT` status.

   Anything else is contradictory.
3. **Digest join.** For `proposed_new_source`, `subject_sha256` must equal
   the SHA-256 of the UTF-8 encoding of the `tool_input["content"]` the hook
   wrote to the carrier. It must also equal every numeric trace's
   `subject_sha256`.
4. **Path join.** For `proposed_new_source`, the subject's `target_path` must
   equal the hook's resolved target (compared under `os.path.normcase`), and
   `absence_verified` must be `true`.

The Agent SDK and LangChain validators are unchanged. They never send the new
input. If one of them receives a `proposed_new_source` payload it did not
request, it must treat that payload as untrusted rather than as a verdict. A
regression test pins this (§8.C.6).

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
  the host version, when the pinned host exposes it.
- **Event:** `tool_name`, `file_path` and `cwd` as received, plus every
  host-supplied event identifier present in the envelope (for example
  `session_id`, and a tool-call id). Which identifiers the pinned host
  supplies is established by the §8.B live test, never assumed.
- **Join:** the SHA-256 of the UTF-8 `tool_input["content"]`. This must equal
  the checker's subject digest (§5.3).
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
  crashes or times out.

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
- what the host does for a missing parent directory.

It must not use the §8.D corpus.

**C. Regression matrix (public, before unblinding):**

1. **Legacy parity.** Golden byte comparisons of stdout and exit code between
   `--proposed-new-file` and `--input` (same carrier and target), for:
   - memory with no numeric rule;
   - numeric rules that are all `EXCLUDED`;
   - numeric rules that are all `UNKNOWN`;
   - any failed precondition (existing file, existing empty file, symlink,
     dangling link, link component, missing parent, out of root, non-`.py`,
     non-UTF-8 carrier).

   Existing `--input` and `--source-file` goldens stay unchanged.
2. **Preconditions.** One positive case and one negative case for each of
   the §3.2 preconditions, including a permission error on `lstat` (it must
   not count as absence), Windows case-insensitive normalization, and a
   missing `--target-path` (an operational error).
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
6. **Consumer trust (§5).** Each of rules 1–4 is violated in turn, giving an
   untrusted result. A `RECOGNIZED` record on an unverified subject is
   rejected on every call. The Agent SDK and LangChain treat an unrequested
   `proposed_new_source` payload as untrusted.
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
   - No diagnostic contains source content.
9. **Untouched surfaces.** Stop, Bash, the Agent SDK and LangChain gate
   paths, `ConflictDetector`, `DecisionRetriever` and the M4 matcher modules
   have no diff.

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
- the evidence record and seam (§6), as ruled.

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
| G2C-O3 | Precondition failure under the new input | Legacy-equivalent evaluation, byte-identical (§3.3), not an operational error |
| G2C-O4 | Missing parent directory | Not routed; stated noncoverage (§3.2, §7) |
| G2C-O5 | Hook diagnostic wording for routed events | Update `format_applicability_reason` only on routed events that have numeric records (§4.3) |

## 11. Review history

- Draft 1 (2026-10-24): PROPOSED, not yet reviewed.
