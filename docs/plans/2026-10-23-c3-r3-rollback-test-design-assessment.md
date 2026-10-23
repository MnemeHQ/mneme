# C3 R-3 rollback test design: assessment and proposed correction (2026-10-23)

**Status:** proposal for review. It changes nothing: no fixture, runtime,
matrix, harness or historical evidence. It authorizes no run. The live R-3
probe stays unauthorized until the correction below is reviewed and its parts
are separately authorized.

**Question (owner, 2026-10-23):** does C3 row R-3 test a genuine rollback,
that is, a valid, nonempty earlier event history that is a strict prefix of
the verified baseline? If not, what correction is needed, and does it require
a fixture-history change?

**Answer:**

- **No.** Against the current fixture, R-3 tests an **empty** event list,
  which is not a valid declaration. It would still refuse as `BEHIND`, so a
  live run could report 4/4 PASS without demonstrating rollback.
- **Yes, a fixture-history change is required.** A valid, nonempty, strict
  prefix of an `AUTHORIZED` baseline exists only once the baseline holds at
  least three events.

## 1. What R-3 compares today

| Element | Today |
|---|---|
| Scope row (#592 §5.1) | R-3: "`L` replaced by an older copy (one event behind)", expect `LOCAL_DECLARATION_TAMPERED` (behind), ADR-033 §4.2 rollback |
| Harness mutation | `setup_c3_probe.py`, step `behind_declaration`: `events = events[:-1]` |
| Fixture baseline | `main@0530b644`: **one** event, `[authorize]` |
| Resulting local copy | `events = []` |

Offline reproduction, using the shipped functions at `mneme/` = `b0dc1a14`:

| Case | Local events | `validate_declaration(local)` | `local_relation` | Refusal |
|---|---|---|---|---|
| **Today** (1-event baseline, `events[:-1]`) | `[]` | **INVALID**: "authority.events must be a nonempty list" | `BEHIND` | `LOCAL_DECLARATION_TAMPERED` |

**Why it is still classed `BEHIND`.** The hook's local read
(`availability.discover_declaration`, C2a) checks only `schema`,
`availability` and `memory_path`, so `problem` stays empty. `local_relation`
then treats `[]` as a strict prefix of every baseline: `base[:0] == []`.

So a live R-3 would show all of the following, while the local copy is not a
valid earlier declaration of this repository:
- verified `AUTHORIZED`;
- exit 2;
- target unchanged;
- the text "(local declaration behind)".

The current offline self-test R-3 PASS is in the same position: its seeded
fixture also has one authorize event. R-3 has never run live (Batch R stopped
at R-1, #601), so **no published record claims a live R-3 result.**

## 2. What a genuine rollback needs

Facts from the C2b charter and the code:

- **Charter §5.2:** `BEHIND` is "**Valid**; equal except that its `events`
  are a strict prefix of the baseline's". ADR-033 §4.4 refuses a declaration
  "rolled back" under `AUTHORIZED`.
- **`validate_events`:** the list must be nonempty, `seq` runs 1..n, `prev`
  chains by event digest, and **ops strictly alternate** (no repeated op).
  The first event is `authorize`.
- **R-3 needs `B = AUTHORIZED`**, so the baseline's last event is
  `authorize`.

Consequences:

| Baseline events | Baseline result | Valid nonempty strict prefixes |
|---|---|---|
| `[authorize]` (today) | AUTHORIZED | none (the only strict prefix is `[]`) |
| `[authorize, revoke]` | REVOKED | not an R-3 baseline (no refusal under REVOKED) |
| `[authorize, revoke, authorize]` | **AUTHORIZED** | `[authorize]`, `[authorize, revoke]` |

**The minimal correct baseline is three events, `authorize → revoke →
authorize`.** With it, the **unchanged** mutation `events[:-1]` yields
`[authorize, revoke]`. That is:
- valid under `validate_declaration`;
- nonempty;
- a strict prefix of the baseline;
- a state the fixture genuinely passed through (the REVOKED phase);
- classed `BEHIND` and refused.

Offline reproduction with a chained 3-event history (`prev` = `event_digest`
of the previous event, as `prepare_event` writes):

| Case | Local events | `validate_declaration(local)` | `local_relation` | Refusal |
|---|---|---|---|---|
| **Proposed** (3-event baseline, `events[:-1]`) | `[authorize, revoke]` | **valid** | `BEHIND` | `LOCAL_DECLARATION_TAMPERED` |
| Also valid (`events[:1]`) | `[authorize]` | valid | `BEHIND` | `LOCAL_DECLARATION_TAMPERED` |
| Control (empty list) | `[]` | INVALID | `BEHIND` | `LOCAL_DECLARATION_TAMPERED` |

The tooling already supports the history:
- `prepare_event` allows `revoke` from AUTHORIZED and `authorize` from
  REVOKED;
- `seed_fixture.sh` has `revoke` and `authorize` steps.

## 3. Proposed correction (each part needs its own authorization)

1. **Fixture history (needs owner authorization; human-merged, E5).** Two
   fixture PRs, prepared locally by `seed_fixture.sh` and pushed and merged by
   a human, each recorded as E5:
   1. `revoke`: baseline becomes **REVOKED**, with `[authorize, revoke]`. This
      is the scope's existing phase 3, so **P-5** (REVOKED proceed) can run
      here as originally planned.
   2. `authorize`: baseline becomes **AUTHORIZED again**, with
      `[authorize, revoke, authorize]`. This is a new phase 4. **R-3** runs
      here.
2. **C3 scope amendment (docs, reviewed).**
   - Add phase 4 "re-AUTHORIZED (3 events)".
   - Define R-3's "older copy" as the baseline minus its last event, which
     must be a valid, nonempty, strict prefix.
   - State that R-1, R-2 and P-1/P-3/P-4 stay validated on the 1-event
     baseline (#620, #622) and are not re-run because of this.
3. **Harness guard (small reviewed PR; no matrix change).**
   - `setup_c3_probe.py` `behind_declaration`: fail the probe as a
     **harness failure** unless the resulting local declaration passes
     `validate_declaration` and is nonempty. R-3 can then never silently fall
     back to the empty case.
   - Record the baseline and local event counts in `setup.json`.
   - Self-test: seed `authorize → revoke → authorize` before R-3, and run P-5
     in the REVOKED phase between.
   - Add a negative self-test: R-3 against a 1-event baseline must end as a
     harness failure, not PASS.
4. **Optional, reviewed separately (would change `matrix.py`):** make the
   classifier require the relation text that the hook already prints, for
   example "(local declaration behind)" for R-3 and "diverges" for R-2. On
   its own this would **not** have caught the empty-prefix case, because the
   runtime labels `[]` as `behind`, so it is no substitute for part 3.

**Order:** 3 (offline, verifiable now), then 2, then 1, then the live R-3
under its own operator script, following the R-1 and R-2 pattern. The
remaining rows R-4 to R-7 do not depend on the event count: R-2's field
change still reads `diverges` against a 3-event baseline. They can run in
phase 4 unchanged.

## 4. Finding for an owner decision (no change proposed here)

**F-R3-1, the local declaration's validity is not checked before the
relation is computed.**

- **Charter §5.2** defines `BEHIND` as a *valid* strict prefix. The runtime
  labels an *invalid* local copy (`events = []`) as `BEHIND`, because the
  C2a local read does not validate `authority.events`.
- **Behavior is fail-closed and unchanged:** the refusal category is the same
  (`LOCAL_DECLARATION_TAMPERED`). Only the diagnostic's relation word differs
  (`behind` instead of `invalid`).
- **Any runtime fix** (validate local events, so an invalid list is
  `INVALID`) would change C2b output at the frozen boundary. It would need a
  charter amendment and a `[layer1-freeze]` amendment. This assessment does
  not propose one; it records the gap.

## 5. Not changed, not claimed

- Fixture, runtime, `matrix.py`, harness and every published record (#601,
  #616, #620, #622) are unchanged.
- No claim is made about a live R-3 result.
- Batch R is not closed. F-R1 is unchanged.
