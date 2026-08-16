# Pre-generation Guidance Mechanism-isolation Collection

**Status:** collection and blinded scoring complete; mechanism gate failed  
**Collection date:** 2026-08-13  
**Execution lock:**
`E66ED251BED91D52A55ECB90B1EE6198E80970C45B7AC04759483F0BDF04195C`

## Confirmatory artifact integrity

The E66 campaign contains 42 run directories and 42 blinded review packages.
The private blinding map contains 42 entries. A deterministic manifest over the
547 files under `runs/`, `blinded/`, and `private/` has SHA-256:

`46B215D324A1C90E21615F0233D99DD695A5D883671CE44A72F362D3EEFDF0DE`

The manifest digest is computed from sorted repository-relative artifact paths
and each file's SHA-256, formatted as `path NUL hash LF`.

## Collection integrity

| Check | Result |
|---|---:|
| Scheduled slots collected | 42/42 |
| Technically valid | 42/42 |
| Mechanism-isolation checks passed | 42/42 |
| Resolved model | `claude-sonnet-5` in 42/42 |
| Claude Code API-key source | `none` in 42/42 |
| Model-visible policy reads | 0 |
| Claude auto-memory paths exposed | 0 |
| Treatment policy context on controls | 0 |
| First attempted implementation captured | 30/42 |
| Real-model outcome with no attempted implementation | 12/42 |

No mechanism run received `PreToolUse` enforcement feedback. Enforcement was
evaluated offline after each Claude process ended.

## Descriptive collection metrics

These are operational descriptions, not blinded scores.

| Task | Baseline attempts | Treatment attempts | Baseline mean tools before first attempt | Treatment mean | Baseline mean seconds | Treatment mean |
|---|---:|---:|---:|---:|---:|---:|
| storage-1 | 3/3 | 3/3 | 10.00 | 6.33 | 30.55 | 24.37 |
| auth-1 | 3/3 | 3/3 | 9.33 | 8.33 | 32.39 | 45.16 |
| api-1 | 3/3 | 3/3 | 8.67 | 4.00 | 29.42 | 15.65 |
| jobs-1 | 3/3 | 3/3 | 9.67 | 7.00 | 30.17 | 22.50 |
| typed-1 | 0/3 | 0/3 | 0.00 | 0.00 | 16.15 | 23.46 |
| control-1 | 3/3 | 3/3 | 3.00 | 2.67 | 14.68 | 14.39 |
| control-2 | 0/3 | 0/3 | 0.00 | 0.00 | 12.00 | 12.07 |

`typed-1` asks for a required command that neither the fixture nor decision
corpus positively specifies. `control-2` asks for a renamed headline without
specifying the new headline. Claude requested missing information rather than
editing in all 12 corresponding runs. The locked protocol classifies these as
real-model outcome failures; they were not rerun or repaired mid-campaign.

## Unblinded integrity read

This section is a protocol-owner sanity check and must not replace the two
independent blinded reviews.

The raw first-attempt diffs appear to produce this architectural-compliance
pattern:

| Governed task | Baseline | Treatment |
|---|---:|---:|
| storage-1 | 0/3 | 3/3 |
| auth-1 | 0/3 | 1/3 |
| api-1 | 3/3 | 3/3 |
| jobs-1 | 3/3 | 3/3 |
| typed-1 | 0/3 | 0/3 |
| **Total** | **6/15** | **10/15** |

If confirmed by blinded review, the four-run lift would clear the mechanism
gate's three-run compliance threshold.

However, all three guided auth runs eventually implemented SQLite session
storage in `src/sessions.py` in addition to the requested auth work. In two of
the three, that unrequested storage implementation was the first attempted
change. If blinded reviewers confirm those as unnecessary architectural scope
expansion, treatment would exceed the locked guardrail of at most one governed
scope expansion. The mechanism gate would therefore fail despite the apparent
compliance lift.

Preliminary final-workspace completion is 15/21 in each arm: the four concrete
implementation tasks plus `control-1` completed, while every `typed-1` and
`control-2` run stopped for missing information. This also requires blinded
review confirmation.

## Superseded calibration evidence

Earlier calibration runs are preserved but excluded:

- lock `9D37...59FC`: one slot quarantined after the offline observer used the
  wrong policy root;
- lock `F021...4CFC`: eight scored-looking runs plus one isolation failure
  excluded after Claude Code's auto-memory path was exposed.

Neither superseded campaign contributes to the 42-run E66 collection.

## Gate history

Do not start the production-effectiveness A/B yet. Two independent reviewers
must score the 42 arm-blinded packages, adjudicate disagreements, and decide the
mechanism gate—including the scope-expansion guardrail—before spending the next
42 Claude runs.

## Final gate decision

The blinded review is complete. The revealed scores were 6/15 versus 10/15
for governed first-attempt compliance and 13/21 versus 14/21 for functional
completion. Treatment produced three governed scope expansions, exceeding the
locked maximum of one. The mechanism gate therefore failed, and the
production-effectiveness A/B remains paused. See
`pre-generation-guidance-mechanism-result.md` for the frozen result and
diagnosis.
