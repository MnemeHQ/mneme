# Verification step 4: independent review of steps 2 and 3

**Date:** 2026-11-09
**Authorization:** owner authorization of Verification step 4 as a read-only
independent review, 2026-11-09, under the
[roadmap Verification slice](../roadmap/README.md) (#579, #768).
**Reviewer:** an agent session separate from the one that produced steps 2 and
3. It treated their harnesses, `results.json` files and records as claims to
test, not as evidence.
**Material under review:**
[step 2 record](verification-step2-negative-controls-2026-11-09.md) and
[artifacts](artifacts/verification-step2-negative-controls/) (#772);
[step 3 record](verification-step3-e2e-fixture-2026-11-09.md) and
[artifacts](artifacts/verification-step3-e2e-fixture/) (#776).
**Type:** review record. No runtime, adapter, CLI, CI configuration, evaluator
pin or benchmark change. Literal-rule evidence is not upgraded. The step 2 and
step 3 records are not edited.

## 1. Result

| # | Requirement | Result |
|---|---|---|
| 1 | Independence | **PASS** |
| 2 | Reproducibility | **PASS**, with three stated limitations (§3.5) |
| 3 | Evidence binding | **PASS** as an assessment; it confirms the steps' ceilings and adds three precision findings (§4) |
| 4 | Negative controls | **PASS**; N-2 confirmed and extended (§5) |
| 5 | CI authority | **PASS** for all five reports; **disagreement** with step 3 on what `verify-report` protects against (§6) |
| 6 | Closure | **Close with conditions** (§9) |

The headline conclusions of steps 2 and 3 hold under independent checking:

- No negative control, at either checkpoint or on the hook path, acquires a
  relevant-enforcement claim.
- Relevant enforcement observed is reachable only on the #761 E-1 path (hook,
  `FORBID_NUMERIC_ABOVE`, new-file `Write`, pinned host). I reproduced it
  through the hook's **shipped default subprocess transport**, which step 2 did
  not use.
- Every literal-rule observation stops at execution observed. Nothing here
  changes that.
- Both fixtures replay **byte-identically** against their pins, and my own
  container replay of the CI checkpoint, written separately from
  `ci_replay.sh`, reproduces all five raw gate reports.

Where I disagree, it is about precision, not about any relevance claim:
`verify-report` does not bind configuration or subject and accepts a
coherently rewritten report (R-1); step 3's A4 is labelled "not executed"
although the checker ran (R-4); and the consumer obligations around
`relevant_enforcement_per_rule` are wider than identity and subject (R-3).

## 2. Independence (requirement 1)

**What I reran (reproducibility only):** the original
[`run_controls.py`](artifacts/verification-step2-negative-controls/run_controls.py)
and [`run_step3.py`](artifacts/verification-step3-e2e-fixture/run_step3.py),
unchanged, against fresh detached checkouts of the pins. Their outputs were
used only for byte comparison (§3). I did not use their assessors, levels or
PASS lines as evidence.

**What I did independently:**
[`independent_checks.py`](artifacts/verification-step4-independent-review/independent_checks.py)
(output: [`checks.json`](artifacts/verification-step4-independent-review/checks.json),
**87 of 87 checks hold**). It imports nothing from the step 2 or step 3 harnesses and does not read their
`results.json`. It:

| Area | Independent method |
|---|---|
| Pins | Resolves every commit, tree and blob from git objects. Unpacks the preserved wheel and compares every `mneme/` file with the `0b74d410` tree by git blob id. Inspects the local image by digest and runs it. |
| Checkpoint A | Drives v0.11.0 `ToolGateMiddleware` with its own handler from a neutral directory; observes the target on disk. |
| CI fixture | Rebuilds the fixture repository with a **different plumbing method** (per-commit index, `update-index` + `write-tree`, instead of `mktree`), using A1's handler output from its own checkpoint A run as B1's content. |
| Raw CI reports | Checks every report's base, head, merge base, path, mode, content digest and memory blob against the rebuilt repository. |
| Evaluator output | Runs a **fresh** `mneme check` with the `0b74d410` code from the approved wheel, with the adapter's exact command shape, and compares with each report's raw `stdout` and exit; runs v0.11.0 on the same inputs. |
| CI decision | Runs the pinned adapter's `verify-report` on every committed report, on the host and inside the pinned image with the gate's own Python; adds tamper probes. |
| CI replay | Its own container script (not `ci_replay.sh`) installs the approved wheel hash-locked and runs `evaluate` + `verify-report` on the rebuilt repository. |
| Hook path | Drives the v0.11.0 hook through the **default `subprocess` transport** (step 2 used the benchmark-only `inprocess` transport), with a different decision set (`S4-LIT`, `S4-NUM`), different content and a different synthetic host pin. Reads each ADR-029 dimension from the raw record with its own reading before comparing with `relevant_enforcement_per_rule`. |

**What is not independent:** the frozen fixture inputs themselves (the ADR-901
memory blob, the file texts, the git author/date and commit messages), because
they determine the commit SHAs under test. I took them from the step 3 record
and harness source. Reading a harness to learn its fixture is not relying on
its conclusions. All runs used the same Windows host as the original runs
(Python 3.12.10, Docker Desktop 29.1.2); the container replay is the only
second environment.

**Correction made during the review, reported for transparency.** My first
full run had 6 mismatches, all traced to my script, not to the material under
review: the container venv path is recorded in each report
(`evaluator.python`), so my `/tmp/ev` broke byte identity (fixed by using the
recorded `/tmp/evaluator`); my literal hook case put the file under the
numeric rule's `src/**`, so the record legitimately carried a numeric entry
(the check now asserts that entry gains no relevance); and the `Edit` case
writes no evidence record at all, which I now assert as an observation.

## 3. Reproducibility (requirement 2)

### 3.1 Pins

All verified from raw objects ([`checks.json`](artifacts/verification-step4-independent-review/checks.json), section `pins`).

| Pin | Claimed | Verified |
|---|---|---|
| Step 2 implementation | `101f3f42`, runtime = v0.11.0 | `101f3f42:mneme` and `619d5405:mneme` are the same tree, `84133a42`; `tests/canonical_fixtures.py` is the same blob `0632b00e` |
| v0.11.0 | `619d5405` | tag `v0.11.0` resolves to `619d5405e80d…` |
| Decision memory | blob `4c669436` | `git hash-object` of the file and `HEAD:` tree entry both `4c669436…` |
| Adapter | `c51729f7`, blob `5feedf60`, sha256 `afe1d69c…` | all three; the adapter, its tests and its fixtures at `619d5405` are the same blobs |
| Evaluator | `0b74d410`, wheel sha256 `e3fcc769…` | preserved wheel hashes to `e3fcc769…`; **all 108 `mneme/` files are byte-identical to the `0b74d410` tree and the file sets match**; metadata version `0.10.0`; preflight record names a commit build of `0b74d410` |
| Container | `ubuntu@sha256:68ee2200…` | local image addressed by that digest; Ubuntu 24.04.5 LTS; **ships no Python** |

The wheel-to-tree comparison goes further than the steps did: they checked the
hash, which proves the wheel is the approved file; this shows the approved file
contains `0b74d410`'s source.

### 3.2 Replays of the original harnesses

| Replay | Runtime | Result |
|---|---|---|
| Step 2 `run_controls.py --runtime-root <101f3f42>` | detached `101f3f42` | 18/18, 98/98; `results.json` **byte-identical** (sha256 `0960d379…`) |
| Step 2 without `--runtime-root` on this branch | `main` + #777 | **refused** (exit 2), naming the 8 runtime files changed since the pin |
| Step 3 `run_step3.py --runtime-root <619d5405> --approved-wheel <preserved>` | detached `619d5405`, approved wheel, pinned image | 13/13; `results.json`, all five `ci-reports/*.gate-report.json` and `pins.txt` **byte-identical** |

Step 2 now refuses for 8 files rather than the 6 its record lists, because #777
landed after it. That is the guard working as designed.

### 3.3 Own CI replay

My container script reproduces all five raw reports **byte-identically**, with
the same adapter exits (B1 0, B2 1, B3 1, B4 1, B5 0) and the same
`verify-report` decisions (§6). The gate Python was 3.12.3 (as in `pins.txt`).

### 3.4 Existing test gates

Run in the detached `619d5405` checkout (whose adapter, adapter tests and
adapter fixtures are the `c51729f7` blobs): the hook evidence and per-rule
attribution tests, `test_dg1e_evidence_identity.py`, the LangChain, Agent SDK
and Claude Code integration suites, and `test_adr033_c4_ci_gate.py`.
**1414 passed, 5 skipped.** The 5 skips are all in
`test_adr033_c4_ci_gate.py:634` ("mneme is not importable under python -I
here"): the adapter's end-to-end evaluator tests need an installed `mneme`
under an isolated interpreter, which this host does not provide. The
container replay (§3.3) exercises that path with the approved evaluator
instead.

My own `checks.json` was byte-identical across two consecutive runs.

### 3.5 Limitations

1. **Unpinned system packages.** The pinned image has no Python or git. Both
   are installed from the live Ubuntu archive at run time. This run got `git
   1:2.43.0-1ubuntu7.4`, `python3.12 3.12.3-1ubuntu0.17`. A future archive
   update can change them; the wheel and adapter hashes still fail closed, but
   the interpreter is not hash-pinned. Already documented for the GitLab lab
   charter; it applies here too.
2. **The approved wheel exists only as a preserved local copy.** It is not
   republished (C4 Gate 2 record). Anyone without that file cannot replay
   checkpoint B; whether the wheel can be rebuilt bit-for-bit from `0b74d410`
   is **NOT VERIFIED**.
3. **Same host.** The original harness replays ran on the same Windows host
   that produced the committed results. Byte identity there shows determinism,
   not portability. The container replay is Linux; the in-process hook and
   pre-mutation checks are Windows only.

## 4. Evidence binding (requirement 3)

Legend: **Mneme** = bound in Mneme's own output for that evaluation;
**adapter** = recorded by the C4 adapter (Mneme's code) around the evaluator
output, not by the evaluator; **harness** = established only by a validation
harness; **absent** = not established.

### 4.1 Step 2 hook path (`FORBID_NUMERIC_ABOVE`, new-file `Write`)

Verified on my own subprocess-transport record (H1 reject, H1b allow).

| # | Dimension | Bound by | Limitation |
|---|---|---|---|
| 1 | control / provenance | **Mneme** (`schema`, `surface`, `mneme_version`, `host`) | The host pair comes from the validation environment variables, and the consumer compares it with the same pin: here it is a fixture value, never a live host. `relevant_enforcement_per_rule` checks `mneme_version` only for being non-empty (R-3). |
| 2 | subject | **Mneme** (`carrier_sha256` = `checker.subject.subject_sha256` = rule `subject_sha256`, `absence_verified`, target path) | Comparison with a claimed subject is the consumer's job (C5a / N-2:stale-subject). |
| 3 | decision | **Mneme** (`decision_version_id` per rule; `decision_id` = `rule_id` prefix) | The function checks the version only for non-emptiness, not even the `dver-` form (R-3). |
| 4 | rule | **Mneme** (`rule_id`) | — |
| 5 | applicability | **Mneme** (`APPLIED`) | An `EXCLUDED` rule leaves no entry; the record cannot show it was considered (step 2 N-5, reproduced). |
| 6 | outcome | **Mneme** (matcher status/outcome, `hook_outcome`, disposition cause, reported violation) | Allow is attributable on this path (H1b), unlike every literal path. |
| – | configuration | **Mneme, per rule** (`rule_id` + `decision_version_id`, §5.1 ruling) | Memory-wide configuration absent (#761 E-4). A changed numeric bound changes `rule_id` but not `decision_version_id` (step 2 V3), so rule configuration rests on `rule_id`. |

A fresh `mneme check --proposed-new-file` on the same memory and content names
the same `rule_id`, `decision_version_id` and subject digest as the hook
record, so dimensions 2-4 agree across two Mneme surfaces.

### 4.2 Step 3 checkpoint A (LangChain middleware, literal, v0.11.0)

| # | Dimension | Bound by | Notes |
|---|---|---|---|
| 1 | control / provenance | **harness** | The payload carries no surface or version (no `subject` record for literal-only checks, #761 E-2). The v0.11.0 runtime is established by the checkout and import checks, not by the output. |
| 2 | subject | **harness** | Payload has no subject (verified: `subject` not in payload keys). The digest is computed from tool arguments. Non-mutation is observed on disk by the harness. |
| 3 | decision | **Mneme** (`decision_id`, `decision_version_id`); empty for A5 | — |
| 4 | rule | **Mneme** (`rule_id`) | — |
| 5 | applicability | **Mneme** (`APPLIED`; `UNKNOWN` for A4) | — |
| 6 | outcome | **partial**: reject attributable by the violation's `rule_id` and `action deny`; allow only as an absent violation (#761 E-3) | Prevention (handler not called) is harness-observed. |
| – | configuration | **absent** | step 3 O-4. |

### 4.3 Step 3 checkpoint B (C4 gate, literal, `0b74d410`)

| # | Dimension | Bound by | Notes |
|---|---|---|---|
| 1 | control / provenance | **adapter** (adapter sha256, evaluator commit and wheel sha256) | Checked by `verify-report` against trusted inputs. |
| 2 | subject | **adapter** (head SHA, per-file sha256) | Head SHA is checked by `verify-report`; the per-file digest is **not** (R-1). Evaluator payload has no subject. |
| 3 | decision | **Mneme** in raw `stdout` (`decision_version_id`); dropped from the adapter's extract (#761 E-6) | Empty for B4. |
| 4 | rule | **Mneme** (`rule_id`) | — |
| 5 | applicability | **Mneme** (`APPLIED`) | B3 has none: classified before evaluation. |
| 6 | outcome | **partial**: per-file classification and aggregate, not per rule | `verify-report` recomputes from classifications, not from `stdout` (R-1). |
| – | configuration | **adapter** (memory blob, source commit, sha256) | Not checked by `verify-report` (R-1). |

### 4.4 Cross-checkpoint correlation

Fixture-level correlation, as step 3 says, and **not** ADR-029 binding. I add
one precision (R-6): the equalities are partly true by construction. B1's
content is A1's handler output fed into the fixture, and B2 is built from the
same text the harness tried at A2. What the digest match does show is that the
handler wrote exactly the attempted bytes and that the adapter hashed the same
bytes at CI. The independent fact is the identity agreement across evaluator
versions: v0.11.0 at A and `0b74d410` at B both give
`(ADR-901, dver-d3d431ff…, ADR-901:FORBID_LITERAL:1eff1b82…)` for this memory,
and fresh v0.11.0 runs on all four evaluated CI subjects agree with the
reports' verdicts, identities and applicability.

## 5. Negative controls (requirement 4)

Through the shipped subprocess transport, with my own fixture:

| Control | Observation | Relevance |
|---|---|---|
| Missing identity (section-less memory, numeric rule) | untrusted record, `rules: []`, write proceeds with cause `fail_open` | none (function `{}`) |
| Excluded rule (`docs/new.py`) | CLI `EXCLUDED`; hook record `rules: []`, cause `no_violation` | none (function `{}`) |
| Incomplete evaluation (`lookup()` value) | `APPLIED`, `MATCHER_UNEVALUATED`; proceeds `fail_open` | none (function `False`) |
| Stale subject (claim about other content) | function **True**; my subject reading fails dimension 2 | none under the consumer rule |
| Wrong version (claim names V2) | function **True**; my identity reading fails dimension 3 | none under the consumer rule |
| Literal violation via the hook | refused, attributed to the literal rule; **no** literal rule entry; the co-applied numeric entry (`MATCHER_UNEVALUATED`, `SOURCE_NOT_FOUND`) gets no relevance | none |
| Numeric content via `Edit` of an existing file | proceeds (exit 0) and **no evidence record is written** | none |

At checkpoint A and B, the step 3 cases (A4/B3 incomplete, A5/B4 missing
identity, B5 later revision) were re-derived from raw output in §3-§4; none
carries a subject record, so none can reach relevance.

**N-2, confirmed and extended (R-3).** On a genuine record,
`relevant_enforcement_per_rule` alone returns `True` for:

- a claim naming another `decision_version_id` of the same rule (as step 2);
- a claim naming a later subject (as step 2);
- a record whose `decision_version_id` was rewritten to `not-a-version-id`
  (new: only non-emptiness is checked, not the `dver-` form);
- a record whose `mneme_version` was rewritten to `0.0.0` (new: provenance
  version is not compared with anything).

It returns `False` when the consumer pins another host, and when the carrier
digest alone is rewritten. Rewritten records are an authenticity question
(ADR-025, out of scope); the point is which comparisons a consumer must do
itself. #761 §5.1 names the identity tuple; step 2 adds the subject digest;
this review adds the `mneme_version` (dimension 1 says "with Mneme version")
and the version form. No runtime change is proposed or authorized here.

## 6. CI authority (requirement 5)

The pinned adapter's own `verify-report` on each committed raw report, with
base and head SHAs from my rebuilt repository and adapter exits from my own
container run, posture `closed`:

| Report | Exit | Problems (exact) | Matches step 3 |
|---|---|---|---|
| B1 allow | 0 | none | yes |
| B2 bypass | 1 | `required check fails: VIOLATION under availability closed` | yes |
| B3 symlink | 1 | `required check fails: UNEVALUATED under availability closed` | yes |
| B4 missing identity | 1 | `required check fails: VIOLATION under availability closed` | yes |
| B5 later revision | 0 | none | yes |

The same results hold on the host (Python 3.12.10) and inside the pinned image
with the gate's `/usr/bin/python3.12`. A fresh `0b74d410` evaluator run on each
evaluated subject reproduces the report's raw `stdout` and exit exactly.

**Disagreement R-1: what `verify-report` protects.** Step 3 §3 says that "a
failure caused by an integrity problem (a tampered report, a pin mismatch)
would add other lines and fail the check". Tamper probes on copies of the
committed reports:

| Probe | `verify-report` |
|---|---|
| B1 report presented for another head SHA | refused |
| B1 report checked under trusted posture `open` | refused (posture mismatch) |
| B1 report claiming another wheel | refused |
| B1 report with a different memory blob | **accepted** |
| B1 report with a different file content digest | **accepted** |
| B2 report rewritten coherently to PASS (classification, aggregate, disposition), raw `stdout` still FAIL | **accepted** |

So `verify-report` catches pin, posture and aggregate/disposition
inconsistencies, exactly as the [C4 gate guide](../integrations/github-actions-c4-gate.md)
describes it, but it does not bind the memory blob or the subject digest and
does not re-derive classifications from evaluator output. A coherently
tampered report passes. Under C4 this is by design: `evaluate` and
`verify-report` run in the same trusted job, and the report is trusted as that
job's own output. The step 3 sentence over-states it. For Verification this
means the CI report's configuration and subject fields are adapter-recorded
and not re-checked by the decision step. They cannot be cited as verified by
`verify-report`.

## 7. Findings

| ID | Finding | Kind |
|---|---|---|
| R-1 | `verify-report` does not bind configuration or subject, and accepts a coherently rewritten report (§6). Step 3 §3's "a tampered report … would add other lines" is over-stated. | disagreement with step 3 §3 |
| R-2 | Step 2 drove the hook with `MNEME_HOOK_CHECK_TRANSPORT=inprocess`, a benchmark-only setting; the shipped default is `subprocess`. Step 2 does not say this. Re-running the positive and negative hook cases through the default transport gives the same outcomes, so step 2's conclusions stand. | omission in step 2 §2; conclusions unaffected |
| R-3 | `relevant_enforcement_per_rule` also accepts a malformed `decision_version_id` and an arbitrary `mneme_version`. Consumer obligations are wider than #761 §5.1 and step 2 N-2 state (§5). | finding, consumer obligation |
| R-4 | Step 3 labels A4 "not executed", but the checker ran: the payload is present, identity complete, applicability `UNKNOWN`, `evaluation_complete: false`. The #769 "fail_open evaluates nothing" rule was derived from materialization failures with no payload. The accurate reading is execution observed with incomplete evaluation (ADR-029: `UNKNOWN` is an operational failure). The label is conservative and changes no relevance conclusion. | disagreement with step 3 §4, minor |
| R-5 | Wheel provenance is stronger than the steps showed: all 108 `mneme/` files equal the `0b74d410` tree. | confirmation |
| R-6 | Cross-checkpoint digest equality is partly true by construction (§4.4). Step 3 already calls it fixture-level correlation; the identity agreement across evaluator versions is the independent fact. | precision |
| R-7 | Numeric content through `Edit` of an existing file proceeds and writes no hook evidence record. Consistent with E-1 being new-file `Write` only; noted because a reader might expect an untrusted record, as for other routed events. | observation |

## 8. Kept observations (documented, not fixed)

- **O-1** (step 3): incomplete pre-mutation evaluation fails open and the write
  proceeds. Reproduced: A4 target outside the policy root, `UNKNOWN`,
  `fail_open`, the forbidden bytes are written, the tool result carries
  `[mneme] UNEVALUATED`. The hook's numeric `fail_open` cases (missing
  identity, undecidable value) behave the same under the default open posture.
- **O-3** (step 3): `python -m mneme` launched from a directory containing a
  `mneme/` package imports that package. Reproduced: with `_child_env()` and
  this repository as the working directory, the checker subprocess imports
  this repository's `mneme/`, not the pinned runtime; from a neutral directory
  it imports the pinned runtime.

## 9. Closure

| # | Requirement | Result | Supporting artifact | Limitation |
|---|---|---|---|---|
| 1 | Independence | **PASS** | `independent_checks.py`, `checks.json` | Fixture inputs shared by necessity; same host |
| 2 | Reproducibility | **PASS** | §3; step 2/3 replays byte-identical; own container replay byte-identical; pinned test gates 1414 passed, 5 skipped (§3.4); `checks.json` `pins`, `R` | Unpinned apt packages; wheel only preserved locally, rebuild NOT VERIFIED; same host for in-process checks |
| 3 | Evidence binding | **PASS** | §4; `checks.json` `A`, `F`, `E`, `H` | Host pin synthetic; no live host, no GitHub Actions |
| 4 | Negative controls | **PASS** | §5; `checks.json` `H`, `A` | N-2 extended (R-3) |
| 5 | CI authority | **PASS** (5/5 exits and problem lists) | §6; `checks.json` `C`, `R` | R-1: `verify-report` does not bind memory or subject |
| 6 | Closure | **Close with conditions** | this table | — |

**Recommendation: close the Verification slice, with conditions.** The slice's
exit evidence exists and reproduces: for each checkpoint the evaluated
decision/rule revision, the evaluator build, the evaluated subject where Mneme
or the adapter records one, the verdict and the control outcome, with the
unproven bindings named. The conditions are scope statements that any citation
of the slice must carry; none is new work:

1. Relevant enforcement observed is claimed only on the E-1 path, and only
   with the consumer comparing the full identity tuple, the subject digest and
   the `mneme_version` (R-3). Literal-rule evidence stays execution observed.
2. CI checkpoint evidence is `0b74d410` evidence. Its memory and subject fields
   are adapter-recorded and not re-checked by `verify-report` (R-1).
3. O-1 and O-3 remain open observations.
4. Nothing here is a live-host, GitHub Actions or attestation claim.

Moving any consumer comparison into `relevant_enforcement_per_rule`, binding
memory or subject in `verify-report`, or hash-pinning the container's
interpreter would each need its own reviewed charter. This review authorizes
none of them.

## 10. Reproduce

```bash
git worktree add --detach ../mneme-619d5405 619d5405
python docs/validation/artifacts/verification-step4-independent-review/independent_checks.py --runtime-root ../mneme-619d5405 --approved-wheel <mneme_hq-0.10.0-py3-none-any.whl> --container
git worktree remove ../mneme-619d5405
```

Needs Docker, network access in the container (apt and the hash-locked pip
install), `langchain` 1.4.0 on the host and the preserved approved wheel.
Without `--container` the image and container checks are skipped. The script
writes `checks.json` and exits 1 on any failed expectation.
