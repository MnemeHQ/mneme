# ADR-034 G2-1 validation pre-registration (§8.B live host, §8.D blind validation)

**Date:** 2026-10-25
**Amended:** 2026-10-25, Amendment 1 (clarifications from the owner's ambiguity rulings; see the end of this file)
**Status:** PROPOSED. Once merged, this pre-registration is frozen. Changing
it afterwards needs a dated, owner-approved amendment that is merged
**before** decryption. No change is allowed after unblinding.

**Authorization:** on 2026-10-25 the owner authorized G2-1 §8.B (live host
characterization) and §8.D (independent blind validation), in separate
sessions isolated from the implementation session, starting with this
pre-scoring record.

**Revision 2** (2026-10-25) responds to the pre-merge review, which
requested changes. The four corrections tighten the validation contract.
They change neither ADR-034 nor implementation behavior, and none is based
on any case content.

- **G2V-F1:** every case expected to block that is observed proceeding is an
  unsafe pass, whatever its labels (§5 G1).
- **G2V-F2:** symlink capability is required for a full PASS. Without it, the
  result is INCOMPLETE, never a narrowed PASS (§5).
- **G2V-F3:** hook parity includes stderr. The charter's exception for routed
  content containing CR is kept, together with checker-level parity (§5 G5).
- **G2V-F4:** the class floors and the 104 total apply to **concealed, scored**
  cases. Public smoke cases come on top of them (§4).

**What this record is.** The G2-1 charter §8.D requires "a pre-scoring
record [that] states denominators and a failure policy before unblinding, as
M4 did (#625)". This record states them **before any corpus exists**, which
is stricter than M4.

A short **pre-scoring completion record** follows before decryption (§8,
step 5). It adds the harness, build, environment and corpus hashes. It may
not change anything fixed here.

**Normative anchors:**

- [ADR-034](../adr/ADR-034-static-numeric-upper-bound-typed-rule.md) §6a,
  §7a and the G2 amendment;
- the [G2-1 charter](../plans/2026-10-24-adr-034-g2-1-behavioral-charter.md),
  §3–§8, including the §5.1 erratum (G2C-R1);
- the G2-1 entries in
  [`layer1-freeze-e73ff7d.md`](../architecture/layer1-freeze-e73ff7d.md).

## 1. Claim under test

**The claim, if validation passes:**

> On Claude Code `PreToolUse`, a `Write` to a verified-absent `.py` target
> whose parent directory exists inside the policy root is refused before
> mutation, in strict mode, when the complete proposed source has a
> recognized `FORBID_NUMERIC_ABOVE` violation. Unrouted events are unchanged.
> Evidence records bind each outcome to its cause.

**"Relevant enforcement observed"** (ADR-029) may be claimed only for events
a pinned live host produced (§8.B), never for synthetic replay alone (§8.D).

**Not covered:** everything in charter §7.

## 2. Implementation pin

| Item | Value |
|---|---|
| Implementation commit (G2-1, #637 squash) | `6e26c534dd78703f811da7d76168f2e2aaaaa23e` |
| `mneme/` tree at that commit | `34ccbf62b90bac2d6e5e277386a400ac78d86d66` |
| Pre-G2 parity baseline (parent commit) | `f8591102b2693379dabec9b5704862e194eca4ce` |
| Runtime | CPython 3.12.10 |

Scoring uses wheels built from exactly these commits. Their SHA-256 values
go in the completion record.

**Any later fix voids blind status.** If a fix lands after scoring starts,
replays on the same corpus are diagnostic only. A new claim needs a new
held-out corpus (the M4 rule).

## 3. §8.B live host characterization

This is a separate session, and it uses no §8.D material.

- **Host pin:** Claude Code **2.1.310**, as installed on the owner's machine
  on 2026-10-25. The session records the executable's SHA-256 before the
  first run. A different version voids the run.
- **Setup:** a scratch git repository outside `C:/dev/mneme`, with the hook
  installed from a wheel built at the §2 commit, and a memory with one
  `FORBID_NUMERIC_ABOVE` rule. The session writes its own small public
  fixtures; they are not corpus cases.
- **What it must establish** (charter §8.B):
  1. which event identifiers the `PreToolUse` envelope carries;
  2. that a `Write` to a new path in an existing directory reaches the hook
     with the complete `content`;
  3. that exit 2 leaves the target absent;
  4. what the host does for a missing parent directory;
  5. the host identity (version and executable SHA-256) that the evidence
     record carries, set through the validation-only variables.
- **Minimum runs:**
  - a violating new file (strict): refused, target absent;
  - a compliant new file: proceeds, target written;
  - a warn-mode violating new file: deferred;
  - an unrouted existing-file `Write`: unchanged behavior;
  - a missing-parent `Write`: legacy path.

  Each run is repeated twice.
- **Output:** a metadata-only record PR,
  `docs/validation/adr-034-g2-1-live-host-<date>.md`, containing the exact
  commands, host identity, outcomes, and evidence-record digests.

  No source content goes in diagnostics. A non-match is reported as found,
  never adjusted.

## 4. §8.D corpus: classes and minimum counts

Each case is a synthetic scenario. It contains:

- a temporary repository fixture: ADR, memory, and any pre-existing files;
- one Claude Code `PreToolUse` envelope;
- the hook mode, and the expected labels.

Expected labels are written from ADR-034 and the charter only:

- hook exit and disposition;
- routed or unrouted;
- subject kind;
- numeric matcher status, outcome and primary reason;
- whether the target exists after the hook;
- whether an evidence record is expected;
- the expected `relevant_enforcement_observed` value for a valid
  host identity.

**Availability is `open` in every scored class.**

| Class | Scenario | Expected | Min |
|---|---|---|---|
| **V** | Routed, strict, recognized violation | exit 2; `RECOGNIZED`/`VIOLATION`; target absent | 15 |
| **VP** | Routed, strict, violation plus unknown source | exit 2; `PARTIAL`; unknown sources reported | 8 |
| **C** | Routed, all declared sources present and within bound | exit 0; `RECOGNIZED`/`NO_VIOLATION` | 15 |
| **US** | Routed, a declared source absent | exit 0; `MATCHER_UNEVALUATED`/`SOURCE_NOT_FOUND`; never PASS-relevant | 8 |
| **UF** | Routed, unsupported form or ambiguous binding | unevaluated with the correct primary reason | 8 |
| **UP** | Routed, invalid Python, including a leading byte-order mark | `PARSE_FAILURE`; never clean | 6 |
| **X** | Target `EXCLUDED` by ADR-020 | no numeric claim; legacy parity | 6 |
| **L** | Not routed. ≥2 of each: existing file, existing empty file, symlink, dangling symlink, link component, outside the root, non-`.py`, missing parent, lone-surrogate content | legacy behavior, byte-identical to baseline; no G2 evidence record | 18 |
| **LIT** | Routed new file with a `FORBID_LITERAL` violation, with and without a numeric violation | literal block preserved; not credited to the numeric rule unless the numeric rule independently decides | 6 |
| **W** | Warn mode: violation and compliant variants | violation deferred (exit 0); compliant proceeds | 6 |
| **P** | No numeric rule in memory, or all numeric rules `EXCLUDED` | stdout and exit byte-identical to the legacy `--input` run and to the pre-G2 baseline hook | 8 |
| | **Floor total** | | **104** |

**Distribution rules:**

- **The floors count concealed cases only (G2V-F4).** Every class floor and
  the 104 total apply to **concealed, scored** cases. Public smoke cases come
  on top and never count toward a floor.
- The author chooses the exact counts at or above each floor. The freeze
  record states the concealed and public counts per class separately.
- Byte-contract variety (LF, CRLF, lone CR, non-ASCII, empty content) must
  appear across V, C and L, at least 2 cases each where they apply.

**Public versus concealed.**

- At most **10%** of cases, each from a different class, may be
  released to the scorer as **public smoke cases** for harness development.
- They are excluded from gate denominators.
- All other cases stay concealed until decryption.

**Not scored (stated noncoverage):**

- AUTHORIZED closed availability: it needs git-verified authorization, and
  its behavior is already pinned by public tests;
- the race between probe and write;
- the equality of checked bytes and landed bytes.

## 5. Gates (all must pass)

| Gate | Requirement |
|---|---|
| **G1 Unsafe pass** | 0 unsafe passes. Each of these counts as one, **whatever the matcher or evidence labels** (G2V-F1): (a) any case expected to block (every strict V and VP case, and any LIT case expected to block) that is observed with exit 0 or any non-refusing disposition; (b) any case expected to have a non-clean numeric result that is observed with numeric `NO_VIOLATION`; (c) a numeric-attributed relevant evidence claim where none is expected |
| **G2 False block** | 0 cases expected to proceed (C, US, UF, UP, X, L, W, P under open) that are observed with exit 2, except where a `FORBID_LITERAL` violation is expected (LIT) |
| **G3 No mutation** | The target is absent after every observed block. The hook never creates or changes the target in any case |
| **G4 Reasons** | Every unevaluated case (US, UF, UP, VP unknown sources) has the expected primary reason |
| **G5 Parity** | Two levels (G2V-F3). **Hook level:** 100% of P, X and L cases are byte-identical to the pinned pre-G2 baseline hook in **stdout, stderr and exit status**. The only exception is a routed case whose content contains CR: under charter §4.1 / ADR-034 §7a no historical hook-level parity is claimed for it, and it is scored at checker level only. **Checker level:** every routed P and X case gives stdout and exit status byte-identical to `--input` on the same carrier and target (charter §3.3 / §3.5) |
| **G6 Evidence** | Every routed case has a complete record that joins by digest and path, with the expected cause, mode and `relevant_enforcement_observed`. No unrouted case has a G2 record |
| **G7 Determinism** | Two full runs in one environment are byte-identical |
| **G8 Completeness** | Every concealed case is scored. Any operational failure counts as a failure of that case, never as an exclusion |

**Symlink capability is required for PASS (G2V-F2).**

- The scoring environment must be able to create symlinks. The completion
  record must state this and show it with a probe run before decryption.
- If symlinks cannot be created, the run cannot PASS. Symlink-dependent
  cases that cannot run are scored as failures under G8, and the result is
  recorded as **INCOMPLETE** (a validation FAIL).
- The claim is never narrowed to exclude them, and they are never dropped.
- The remedy is to rescore in a capable environment, before any results
  record claims PASS.

## 6. Failure policy

- **Any failure fails G2-1 validation.** A failure of any gate fails G2-1
  validation, and the results record says so plainly. It lists failing cases
  only by opaque `case_id` and class.
- **No tuning.** Nothing is tuned against the revealed corpus. Post-scoring
  fixes are allowed, but their replays on this corpus are diagnostic only.
  A new claim needs a new held-out corpus and a new pre-registration.
- **Harness fixes after decryption.** A harness fix made after decryption
  voids blind status for that run (the M4 R2 rule).

## 7. Roles and isolation

| Role | Who | Constraints |
|---|---|---|
| Owner | The repository owner | Adjudicates the author's sanitized ambiguity brief before sealing. Holds the decryption key (primary `88CE4C9F66A5F3CA7F1C0A484839E24F94E4F796`). Decrypts only after the completion record merges |
| Live host operator (§8.B) | A **new** session | Never sees §8.D material |
| Corpus author (§8.D) | A **new** session | Works only in `C:/dev/mneme-heldout-034-g2/`. Reports metadata only. Stops before sealing |
| Scorer (§8.D) | A **new** session, not the author | Writes and pins the harness from this record and the public smoke cases, before decryption. Runs both passes |
| Orchestrator | The session that drafted this record | Coordinates only. Never authors, scores, or sees case content |

**Barred from authoring and scoring:**

- the G2-1 implementation session (`local_bd4b7cd2`) and its transcript;
- this orchestrator session;
- the archived M4 author and scorer sessions.

**What the corpus author may read:**

- ADR-034 (the whole file, including §6a and §7a);
- the G2-1 charter;
- ADR-018, ADR-020 and ADR-033 as needed;
- this record.

**What the corpus author may not read:**

- `mneme/` source (hook, CLI, enforcer, numeric matcher);
- any `tests/` file for numeric rules or G2 (`tests/test_numeric_upper_bound_*`,
  `tests/integrations/test_numeric_upper_bound_*`,
  `tests/test_adr034_post_m4_source_file_compat.py`);
- the #637 PR body or diff;
- any implementation-session transcript.

The author records an isolation statement listing what was read.

**New ambiguities** go to the owner as a sanitized brief before sealing. A
ruling that would change ADR-034 or the charter stops validation and returns
to architectural review.

## 8. Sequence

1. **This pre-registration** (docs only). Merge.
2. **In parallel:** the §8.B live host run and record PR; §8.D corpus
   authoring, which stops before sealing.
3. **Sealing.** The owner rules on the ambiguity brief. Then:
   - a deterministic tar with `FILES.sha256`;
   - encryption to the owner key;
   - owner verification of the hashes;
   - a metadata-only freeze record PR.
4. **Harness PR** by the new scorer session, built from this record and the
   public smoke cases only.
5. **Pre-scoring completion record:**
   - harness commit and SHA-256;
   - implementation and baseline wheel SHA-256;
   - `pip freeze` SHA-256;
   - OS and symlink capability;
   - the §8.B host identity;
   - corpus anchors from the freeze record;
   - the scoring command.
6. **Scoring.** The owner decrypts. Then two scoring runs, a metadata-only
   results record PR, and custody close (encrypted evidence, plaintext
   shredded).

G2-1 closes only on a PASS results record.

## 9. Not authorized by this record

- Any code change to `mneme/` or to `benchmarks/adr034_m4/`.
- Re-scoring or reuse of M4 or v1 material.
- Any enforcement, "relevant enforcement observed" or production claim
  before step 6 passes.
- Activating `FORBID_NUMERIC_ABOVE` in this repository's memory.

## Amendment 1: clarifications from the owner's ambiguity rulings (2026-10-25)

**Status:** this amendment must merge **before sealing**, and therefore
before any decryption.

**What it does.** It clarifies how the frozen gates apply. No gate is
loosened, and no floor is lowered. It rests on the owner's rulings on the
corpus author's sanitized ambiguity brief (AMB-01 to AMB-13), which were
made without opening any corpus material.

**What came from where.**
- Every rule below comes from those owner rulings, except the
  traceback-frame comparison rule in **A1.4**.
- The orchestrator added the A1.4 rule because a baseline traceback contains
  build-specific paths and line numbers, so a byte-for-byte comparison of
  it could never match. It needs reviewer confirmation before this amendment
  merges.

### A1.1 Routing, trusted source and evidence are three separate facts (AMB-01, AMB-02, AMB-07)

| Fact | Definition |
|---|---|
| **Hook routed** | The hook selected `--proposed-new-file` for the event, under the charter §4.1 conditions, evaluated in the hook's own order. See "When the hook routes" below |
| **Trusted proposed source** | The checker reports `subject.input_kind == "proposed_new_source"`, and at least one numeric rule is `APPLIED` |
| **Relevant enforcement** | Defined in A1.3 |

**When the hook routes.**
- Memory discovery comes first. If there is no memory, the existing
  missing-memory behavior applies: the hook runs no check and writes no
  record.
- The hook then routes only when all of these hold:
  - the event is a `Write`;
  - the target is absolute;
  - the target ends in `.py`;
  - `lstat` raises `FileNotFoundError` for the target;
  - the parent exists and is a directory (G2C-O4, G2I-F1);
  - the content encodes as strict UTF-8;
  - the content has at least one non-blank line (A1.2).

**A checker fallback does not undo routing.** A routed event whose checker
fails its own preconditions and returns the legacy result was still
**routed**.

**How this applies to the classes:**

- **L class: "no trusted proposed source".** Each L case is labelled routed
  or unrouted using the hook conditions above. It must not be assumed
  unrouted just because the checker falls back. A link component, for
  example, can be routed and still fall back in the checker.
- **Missing parent stays unrouted** (G2C-O4).
- **G6, restated.** When the evidence seam is enabled:
  - every **routed** case has exactly one G2 record. That includes routed X,
    P and fallback cases;
  - every unrouted case has none;
  - a routed case with no `APPLIED` numeric rule has a record with
    `relevant_enforcement_observed == false`.
- **G5 hook-level parity** covers both routed and unrouted L, X and P
  cases, keeping the CR exception from revision 2.

### A1.2 Blank content: the legacy skip comes first (AMB-03)

ADR-018 §5's skip for an edit that introduces no non-blank lines comes
**before** G2 routing. The G2-1 charter does not authorize changing that
gate.

For a `Write` whose content has no non-blank line:
- hook exit 0;
- no checker call;
- no G2 record;
- no matcher result from that event.

Calling `--proposed-new-file` directly on the checker with empty, valid
source is a separate checker-level case. If a numeric rule applies, its
missing declared sources give `SOURCE_NOT_FOUND`.

### A1.3 Evidence attribution (AMB-04)

`relevant_enforcement_observed` needs complete ADR-029 bindings **and** an
outcome that can be attributed to the numeric rule:

| Scenario | Expected value |
|---|---|
| Recognized `NO_VIOLATION`, event proceeds | `true` (complete binding) |
| Numeric violation, strict refusal | `true` |
| Numeric violation, warn deferral | `true` |
| `PARTIAL` with an established violation and an attributable refusal or deferral | `true`, without claiming complete source recognition |
| `MATCHER_UNEVALUATED` | `false` |
| Numeric `NO_VIOLATION`, refusal caused only by a literal rule | `false` (not attributable to the numeric rule) |
| No record (unrouted, skipped, or no memory) | `null` as the scoring expectation |

**Synthetic values are not live evidence.** In §8.D the scorer computes
these values using the pinned host identity from §8.B. A synthetic
`true` is never evidence that a live host enforced anything. Only §8.B and
the final claim review can establish that.

### A1.4 Legacy operational behavior and scoring (AMB-08)

This applies to cases outside G2 routing whose legacy behavior is not a
clean proceed, such as content with a lone surrogate.

**Scoring:**
- **The case is executed and scored.** Its expected stdout, stderr and exit
  status are **observed from the pinned pre-G2 baseline**, on the same
  scenario. The corpus does not fix an exit code for it.
- **Gates:**
  - G5 parity applies;
  - G6 expects no record;
  - G2 does **not** apply. An error identical to the baseline's is not a
    false block, and it is not a new numeric block.

**G8, clarified.** Two outcomes must be kept apart:
- **A scoring-process failure** counts as a case failure. Examples: the
  harness crashes, times out, has an environment error, or cannot capture
  the output.
- **A legacy error that was successfully captured and matches the baseline**
  is an observed outcome. It is scored under G5.

**Traceback-frame rule (added by the orchestrator, needs reviewer
confirmation).**
- If the baseline's stderr contains a Python traceback, its frame lines
  (`File "...", line N, in ...`) depend on the build: install path and line
  numbers. They cannot match byte for byte across builds.
- For such cases, G5 requires all of the following to be identical:
  - stdout;
  - exit status;
  - the traceback's final exception line (type and message);
  - every stderr line outside the traceback.
- The scorer records the full raw stderr diff for disclosure.
- This exception applies to traceback frames only.

### A1.5 Confirmed as written

These rulings confirm the author's interpretation:
- **AMB-05:** a warn-mode `PARTIAL` violation defers;
- **AMB-06:** an include selector that doesn't match gives `EXCLUDED`;
- **AMB-09:** the routed CR parity exception applies;
- **AMB-10:** a direct bare-name call inside a function body is a source.

AMB-02 and AMB-07 follow A1.1. AMB-11 to AMB-13 stay as documented
noncoverage or information only.

### A1.6 Reconciliation before sealing

The corpus author reconciles the affected labels against this amendment
(A1.1 lists the affected classes). It then rechecks every concealed class
floor and reports counts only. Sealing waits for this amendment to merge and
for that report.
