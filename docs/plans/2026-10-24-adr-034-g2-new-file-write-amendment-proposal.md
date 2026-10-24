# ADR-034 G2 amendment proposal: pre-write numeric evaluation of new-file `Write`

**Date:** 2026-10-24
**Status:** **PROPOSED.** Not accepted. Nothing here is normative until the
owner accepts it, and acceptance would be recorded by folding §4 into
ADR-034 as §6a and §7a with an `**Amended:**` line, following the ADR-031 §8a
precedent (#490).

**Revision 2** (2026-10-24), per the architecture review of revision 1
(ACCEPT WITH REQUIRED CORRECTIONS):

- **F1:** a proposed-source checker result is separated from evidence that a
  real host `Write` was governed (§3, §6a "Evidence class", §7a "Host-event
  binding").
- **F2:** the target-binding invariant is stated for the new kind itself,
  rather than inherited from the G1 `--source-file` branch (§6a "Target
  binding").
- **F3:** exact legacy parity applies whenever no numeric rule is `APPLIED`.
  The additive-`subject` exception is withdrawn (§7a "Legacy parity").

This is the G2-0 deliverable: a read-only, source-anchored decision on
whether the Claude Code new-file `Write` path can carry a trusted
proposed-source contract, and the exact boundary of that claim.

**Repository baseline examined:** `MnemeHQ/mneme` `main` at
`0d367fc61316e8af50161f6bc48b8dee1711c807`. Line numbers refer to that commit.

**Normative anchors:**

- accepted [ADR-034](../adr/ADR-034-static-numeric-upper-bound-typed-rule.md),
  blob `6f4ea66d79ce3964d8cfd4b6a2d8e6f0ae2d86e9`, especially §4, §6, §7, §8
  and ruling O2;
- [ADR-018](../adr/ADR-018-introduced-delta-enforcement-at-the-edit-gate.md),
  blob `0747dcb0a80045207e221bd4c8e9218d1ed1ee37`;
- [ADR-033](../adr/ADR-033-opt-in-fail-closed-enforcement.md),
  blob `ea80dafa4e4be821d74881effe7928c9061e7947`, §1–§3 and §6;
- ADR-020 and ADR-029;
- the [G1 behavioral charter](2026-10-22-adr-034-g1-behavioral-charter.md) and
  the G1 entry of
  [`layer1-freeze-e73ff7d.md`](../architecture/layer1-freeze-e73ff7d.md),
  including its recorded operating consequence (F2);
- the M4 results record (#628): 161/161, 12/12 gates, 0 unsafe passes.

## 1. Decision summary

**Feasible, within a narrow boundary.** A Claude Code `Write` whose target is
a *verified-absent* `.py` path inside the policy root can supply a complete
proposed Python source to the unchanged M4 matcher before the file exists.

This needs a **new input kind**. The G1 transport cannot be reused, and
`--input` text cannot be relabelled as complete source.

Everything else stays on today's ADR-018 delta path, and numeric rules stay
`MATCHER_UNEVALUATED` / `INCOMPLETE_SOURCE_INPUT` there:

- `Write` over an existing, empty, unreadable or ambiguous target;
- `Edit` and `MultiEdit`;
- deletions;
- shell commands.

**Recommendation:** accept this proposal as the G2 contract. The next step
would be a G2-1 behavioral charter and a `[layer1-freeze]` amendment, each
separately authorized.

## 2. Verified baseline

| # | Fact | Anchor |
|---|---|---|
| B1 | The hook rebuilds the complete proposed file for `Write`, `Edit` and `MultiEdit` from one snapshot of the current file | `mneme/integrations/claude_code/hook.py:110-146` |
| B2 | The gate sends only introduced lines, via a temporary `--input` file plus `--target-path` | `hook.py:1422`, `hook.py:794-810` |
| B3 | With a numeric rule in memory, any `--input` run binds `SourceSubject.unverified`, so the numeric rule is `MATCHER_UNEVALUATED` / `INCOMPLETE_SOURCE_INPUT` | `mneme/cli.py:626-636`, `mneme/enforcer.py:76-127` |
| B4 | `--source-file` needs the file to exist: it rejects symlinks and link components, resolves strictly, needs a regular `.py` file inside the policy root, and reads its bytes once | `cli.py:530-595` |
| B5 | A `Write` target that is missing, unreadable or not UTF-8 is read as `""`, so it is treated as new | `hook.py:93-107`; ADR-018 Consequences |
| B6 | `introduced_between` returns the whole proposal when `before` is empty, so an existing empty file looks the same as a missing one | `hook.py:149-169` (line 156) |
| B7 | Ruling M-a is already wired: a trusted, coherent violation blocks even when evaluation is incomplete | `hook.py:522-533`, `hook.py:917-923` |
| B8 | Ruling O2: an absent declared source is `UNKNOWN` / `SOURCE_NOT_FOUND`, so a file without every declared source cannot be `NO_VIOLATION` | `mneme/numeric_rule.py:714-717`, `numeric_rule.py:840-844`; ADR-034 §3 |
| B9 | Under an AUTHORIZED closed declaration, `INCOMPLETE` maps to the `EVALUATION_INCOMPLETE` refusal | `mneme/integrations/claude_code/availability.py:154-197` |
| B10 | Typed rules are evaluated against the whole corpus. Retrieval only limits multi-term prose rules | `enforcer.py:318-323` |
| B11 | Layer 1 freeze, F2: on an APPLIED numeric path with closed availability, every nonempty edit is refused today. The rule must not be activated there until G2 is authorized | `layer1-freeze-e73ff7d.md:939-944` |

**Why new-file `Write` comes first.** For a verified-absent target, the
ADR-018 introduced content and the complete proposed file are the same text
(B6). G2 therefore needs no new delta-attribution semantics, and ADR-018 is
neither contradicted nor amended.

## 3. Why a new input kind, and why it is not caller-manufactured trust

ADR-034 §6 allows a clean result only on a complete source "read from a
trusted target path". A file that does not exist yet cannot be read from its
path (B4). The proposed bytes come from the host event instead.

ADR-029 §5 forbids any caller-supplied field from manufacturing trusted
evidence. The new kind satisfies this, because its claim is narrower than the
G1 claim and nearly certifies itself:

> These exact bytes, if they became a new file at governed path P, would or
> would not violate the rule.

- That statement is true for whatever bytes a caller supplies. The checker
  evaluates exactly what it hashes.
- The one precondition the bytes cannot prove is that **P does not exist**.
  The checker must establish that itself. A hook-supplied flag or field must
  never assert it.
- The kind never claims that the bytes will land on disk, or that they did.

**What absence does not prove (F1).** A verified-absent target says nothing
about where the bytes came from. Any caller can submit any bytes for an
absent path.

A `proposed_new_source` result is therefore an evaluation of a hypothetical
subject. On its own, it is never evidence that a real host operation was
governed. ADR-029 keeps these apart:

- **Checker result:** "these bytes, at P, would or would not violate". It is
  valid for any caller.
- **Relevant enforcement observed** (ADR-029 §2): a real Claude Code `Write`
  was evaluated and allowed or refused. This needs the host-event binding of
  §7a, made by the enforcing control itself, and joined to the checker
  subject by digest.

A standalone checker invocation, including a manual or test run of the same
flag, never upgrades to the second claim.

## 4. Proposed amendment text (to become ADR-034 §6a and §7a)

### §6a. Proposed new-file source (amendment, proposed 2026-10-24)

A second complete-source input kind, **`proposed_new_source`**, is
recognized. It is distinct from `complete_source_file` (G1) and never
reported as it.

**Preconditions.** The checker establishes all of these itself, at
evaluation time, from the governed target path. If any one fails, the input
is unverified and §6's `INCOMPLETE_SOURCE_INPUT` applies.

1. **Verified absence.** An `lstat` of the governed target raises "not
   found". Any other outcome is not absence and never becomes a
   `proposed_new_source` subject:
   - the target exists (any file type, including an empty file);
   - the target is a symlink or dangling link;
   - the check raises permission, I/O or other errors.
2. **No link components.** The parent directory resolves strictly. Its
   lexical and resolved forms are equal under `os.path.normcase`, as for G1
   (`cli.py:546-556`).
3. **Inside the policy root.** The target is under the ADR-020 policy root of
   the memory actually loaded, and normalizes to a policy-root-relative
   governed path.
4. **Python file kind.** The target suffix is `.py`. File kind comes from the
   contract and target path, never from whether the bytes parse (§6).
5. **UTF-8.** The proposed text decodes as strict UTF-8.

**Subject.** The subject is the UTF-8 encoding of the complete proposed text,
exactly as the checker received it. Its SHA-256 is the subject digest. It is
evaluated once by the unchanged M4 matcher, without import or execution.

**Target binding (F2).** This invariant belongs to the
`proposed_new_source` kind itself. It is not inherited from the G1
`--source-file` branch, whose guard (`cli.py:646-658`) runs only when
`source_file is not None` and would never run on the new path.

The subject records one governed path: the policy-root-relative
normalization of the absence-verified target from precondition 3. ADR-020
applicability for every typed rule must be evaluated against exactly that
governed path. Every applicability record that carries an `input_path` must
equal it.

Any mismatch, or a governed path that cannot be established, is an
operational error (non-verdict exit, untrusted under ADR-033 §2). It is never
a verdict and never a fallback to unverified input.

**Evidence class (F1).** The subject record names `proposed_new_source` as
its input kind. On its own, it is a checker result under §3, never "relevant
enforcement observed".

**Outcomes.** §4 applies unchanged, including O2:

- a proposed file missing any declared source is `MATCHER_UNEVALUATED` /
  `SOURCE_NOT_FOUND`, never `NO_VIOLATION`;
- a proposed file that does not parse is `PARSE_FAILURE`;
- a recognized `EXCEEDS` alongside an unknown source is `PARTIAL`, which is a
  FAIL.

**Digest scope.** The digest identifies the bytes that were evaluated. It is
not a claim about the bytes the host later writes, which may differ (for
example in line endings or a byte-order mark).

### §7a. Surface: pre-write gate for new-file `Write` (G2, amendment, proposed 2026-10-24)

**Routing.** On the Claude Code `PreToolUse` direct-write surface, a `Write`
event is routed to the `proposed_new_source` input kind when its resolved
target meets the §6a preconditions. That routing is single-path: when it
applies, it replaces the `--input` delta invocation for that event.

**Unchanged events.** Every other direct-write event keeps today's ADR-018
delta path, and its numeric rules stay `INCOMPLETE_SOURCE_INPUT`:

- `Write` to an existing, empty, unreadable or ambiguous target;
- `Edit` and `MultiEdit`.

The hook's "unreadable `Write` target is new" shortcut (B5) stays in force
for literal rules, but it never establishes §6a absence.

**Legacy parity (F3).** The G1 freeze requires byte-identical
`mneme.check/v1` payloads and exit codes for checks with no numeric rule
(`layer1-freeze-e73ff7d.md:903-904`). G2 keeps this guarantee and makes it
stricter: parity holds whenever no `FORBID_NUMERIC_ABOVE` rule is
**`APPLIED`** at the governed target.

In that case, the routed check must produce exactly the stdout payload and
exit status of the legacy invocation: the same text as `--input`, with
`--target-path` set to the same target. This covers each of these cases:

- memory with no numeric rule (no `subject` record, as today);
- numeric rules that are all `EXCLUDED` or `UNKNOWN` at the target (today's
  unverified `subject` record, unchanged).

Unlike G1's `--source-file`, which emits a `subject` record even when no
numeric rule exists (`cli.py:407-412`), the G2 path never adds or relabels a
`subject` record unless a numeric rule is applied.

Literal-rule verdicts are unaffected by construction, because for a
verified-absent target the checked text is identical to today's introduced
content (B6). Any departure from parity would be a separate reviewed
behavioral change. None is proposed.

**Host-event binding (F1).** A claim that a real `Write` was governed needs
one record, made by the hook as the enforcing control, that binds all of the
following:

- **Control provenance:** surface (Claude Code `PreToolUse` hook), Mneme
  version, and the pinned host version.
- **Host event:** `tool_name` `Write`, the `file_path` and `cwd` as received,
  and the host-supplied event identifiers that the pinned host provides (for
  example `session_id`, and a tool-call id where present), as established by
  the live test in §6.
- **Join:** the SHA-256 of the UTF-8 `tool_input.content` the hook passed to
  the checker. It must equal the checker's subject digest.
- **Rule and outcome:** rule ID, decision version, governed path,
  applicability, matcher status, and the hook's allow/refuse outcome.

Without this record, or if any field mismatches, evidence stays at
"execution observed" or below (ADR-029 §2, fail closed).

This record is the control's own provenance, not an authenticated host
attestation. No ADR-025 attestation is claimed. Its representation is left to
the G2-1 charter, with no new persistence, telemetry or event system
(ADR-029 §3, ADR-033 §7).

**Verdict handling.** The existing trust validation (`assess_verdict`), M-a
precedence (B7) and strict/warn behavior apply unchanged:

| Matcher result on `proposed_new_source` | Hook outcome (strict) |
|---|---|
| `RECOGNIZED` / `VIOLATION` | Block before mutation (exit 2), actionable reason |
| `PARTIAL` / `VIOLATION` | Block before mutation; unknown sources reported; never "fully verified" |
| `RECOGNIZED` / `NO_VIOLATION` | Proceed (subject to other rules) |
| `MATCHER_UNEVALUATED` | Unevaluated. ADR-033 availability policy decides; never a compliance PASS |
| Untrusted or crashed checker | Unchanged ADR-033 / #260 handling |

**Availability.** G2 changes no ADR-033 policy. Under default `open`,
unevaluated results proceed with diagnostics. Under AUTHORIZED `closed`, they
are refused as `EVALUATION_INCOMPLETE`.

Because of O2 (B8), an in-scope new file that lacks a declared source (a
helper, a test) is unevaluated, so under `closed` it is refused. G2 narrows
F2 (B11) only for verified-new files that contain every declared source. The
F2 activation restriction stays in force for closed-availability paths.

**Other consumers.** The Agent SDK and LangChain consumers are out of scope.
They keep §7's delta semantics.

## 5. Claim boundary

**Claimed (only after G2-1 independent validation passes).** On Claude Code
`PreToolUse` for a `Write` to a verified-absent `.py` target inside the
policy root, a recognized `FORBID_NUMERIC_ABOVE` violation in the complete
proposed source blocks the write before mutation, in strict mode.

**Explicitly not covered:**

- **Race between evaluation and write.** A file created at P after the
  absence check and before the host writes is overwritten without
  re-evaluation. No atomicity with the host write is claimed.
- **Landed bytes.** No claim that the evaluated bytes equal what lands on
  disk.
- **Other mutations:**
  - existing-file `Write` (any content, including empty);
  - `Edit` and `MultiEdit`;
  - pure deletion;
  - renames;
  - Bash and other shell or script mutations;
  - writes by non-Claude-Code hosts or by the Agent SDK or LangChain.
- **Closed availability.** No narrowing of F2 for files without every
  declared source.
- **Unvalidated host behaviour.** Host behavior when the hook fails to launch,
  crashes or times out (ADR-033 §6) is not covered.
- **Out of scope for this amendment:**
  - CI enforcement;
  - Stop-boundary numeric auditing;
  - real-repository generalization;
  - new numeric forms.

## 6. Proposed G2-1 validation scope (not frozen; for the G2-1 charter)

| Class | Required observation |
|---|---|
| New file exceeds the bound | Blocked before mutation; the target remains absent |
| New file satisfies the bound, all sources present | Proceeds |
| New file without a declared source | `MATCHER_UNEVALUATED` / `SOURCE_NOT_FOUND`; never PASS |
| Unsupported expression | Unevaluated; never PASS |
| Recognized violation plus an unknown source | `PARTIAL`; blocked; unknown sources reported |
| Invalid Python, or a leading byte-order mark | `PARSE_FAILURE`, or another non-clean result; never fabricated compliance |
| Target out of scope (ADR-020 `EXCLUDED`) | No numeric enforcement; applicability recorded |
| Target exists, is empty, unreadable, a symlink, behind a link component, outside the root or not `.py` | Not `proposed_new_source`; today's delta behavior, byte-for-byte |
| Existing `FORBID_LITERAL` rules | No behavioral or payload regression |
| No numeric rule `APPLIED` (none in memory, or all `EXCLUDED` / `UNKNOWN`) | stdout payload and exit status byte-identical to the legacy `--input` + `--target-path` invocation (F3) |
| Applicability evaluated at a path other than the subject's governed path | Operational error; never a verdict, never a fallback (F2) |
| Evidence | rule ID, decision version, subject digest, governed path, input kind and outcome all bound to one evaluation (ADR-029 §2) |
| Host-event binding | Hook record joins host event fields to the checker subject digest. A standalone checker run, or a digest mismatch, never counts as relevant enforcement observed (F1) |

**Proposed acceptance criteria:**

- zero unsafe passes;
- zero false blocks in the supported scenarios, scored under availability
  `open`;
- zero mutations after a block;
- complete evidence binding.

**Proposed process:**

- the validator is independent of the implementing session;
- source and harness pins are fixed before scoring;
- the sealed M4 corpus is not reused as blind evidence.

**Live host test.** The host's write behavior for a new file (byte identity,
and the error a `Write` gets for an absent parent directory) is established
by a pinned live test before any support claim, as in ADR-033 §6.

## 7. Owner rulings requested

| ID | Question | Proposed answer |
|---|---|---|
| G2-O1 | First-slice surface | Verified-absent `Write` only. Existing-empty files excluded (B6) |
| G2-O2 | Input-kind name | `proposed_new_source`, never reported as `complete_source_file` |
| G2-O3 | Who establishes absence | The checker, at evaluation time. Never the caller. Submitted bytes are a hypothetical subject; only the hook's host-event binding supports "enforcement observed" (F1) |
| G2-O4 | Routing | Single path: replaces the delta call for qualifying events, with no double invocation. Exact legacy parity when no numeric rule is `APPLIED` (F3); its own target-binding invariant (F2) |
| G2-O5 | Availability | ADR-033 unchanged. Score under `open`. The F2 restriction stays for `closed` |
| G2-O6 | Flag or payload spelling | Deferred to the G2-1 charter, as ADR-034 §6 deferred the G1 spelling |

## 8. Alternatives considered

- **Relabel the existing `--input` text as complete source.** Rejected. It
  contradicts §6 and lets any caller turn text into a clean result.
- **Reuse `--source-file` on a temporary copy.** Rejected. It would bind the
  temporary path, not the governed path, and would fail the
  applicability-mismatch guard. The G1 claim "read from the trusted target
  path" would be false.
- **Evaluate the whole proposed file for `Edit` and `MultiEdit` as well.**
  Rejected for this slice. A violation already in the file would block
  unrelated edits and their remediation, reopening the #259 deadlock that
  ADR-018 closed. That needs delta attribution: a later milestone.
- **Audit new files at the Stop boundary with the existing `--source-file`.**
  Not a substitute. The bytes on disk are trusted, but the check runs after
  the write and cannot undo it (ADR-033 §6). It may be a later backstop, under
  its own charter.

## 9. What acceptance would and would not authorize

**Acceptance would:**

- fold §4 into ADR-034 as §6a and §7a;
- record G2-O1 to G2-O6.

**Acceptance would not authorize:**

- any hook, CLI, matcher, enforcer, SDK, LangChain or CI change;
- the G2-1 behavioral charter, the `[layer1-freeze]` amendment or a
  validation corpus (each separately authorized);
- any change to the M4 matcher semantics, `DecisionRetriever`,
  `ConflictDetector`, `FORBID_LITERAL` semantics, memory persistence, or
  ADR-018, ADR-020, ADR-029 or ADR-033;
- import of ADR-034 into project memory, or activation of
  `FORBID_NUMERIC_ABOVE` on any path;
- any enforcement or production claim.

## Related

- ADR-017, ADR-018, ADR-019, ADR-020, ADR-021, ADR-029, ADR-033, ADR-034
- [G1 behavioral charter](2026-10-22-adr-034-g1-behavioral-charter.md)
- [M4 validation charter](2026-10-22-adr-034-m4-independent-validation-charter.md)
- [Pre-registered evaluation criteria](2026-10-21-adr-034-pre-registered-evaluation-criteria.md)
- #259, #590, #607, #613, #628
