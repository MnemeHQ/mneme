# Pre-generation Guidance Role R5 Result

**Status:** R5 passed with frozen changed-surface Ruff gate  
**Date:** 2026-08-14  
**Scope:** mechanical validation only  
**Claude trials:** none

## Outcome

Every experiment-validity gate passed. The R5 lint gate is explicitly frozen
to the four R4/R5-changed production and test files. Ruff 0.16.3 reports no
findings on that surface.

The repository has no Ruff configuration and does not declare Ruff in its
development dependencies. The 145 findings produced by a default whole-tree
scan are recorded as pre-existing debt and are excluded from this experiment's
validity gate. R5 does not create a lint policy, waive a new finding in the
changed surface, or authorize repository-wide cleanup.

## Gate evidence

| Gate | Evidence | Result |
|---|---|---:|
| Full test suite | 624 passed, 5 skipped, 52 existing warnings | PASS |
| Python compilation | `python -m compileall -q mneme` | PASS |
| Focused guidance/plugin/package suite | 49 passed, 5 skipped | PASS |
| Claude plugin validation | `claude.cmd plugin validate integrations/claude-code-plugin --strict` | PASS |
| Locked retrieval benchmark | recall gates 1.00; false/low-signal injection 0; K=3 | PASS |
| Locked applicability characterization | 4/4 role/wording matches; selection changes 0 | PASS |
| Guidance determinism | 22/22 cases byte-identical across repeated builds | PASS |
| Character budget | maximum locked-matrix output 1,189; cap remains 8,000 | PASS |
| R1-R4 lock-file hashes | all four match their frozen SHA-256 values | PASS |
| E66 integrity | 547 files; `46B215...F0DE` using the frozen manifest algorithm | PASS |
| Production-effectiveness artifacts | directory absent | PASS |
| External model spend | no Claude trial or A/B run | PASS |
| Ruff, R4 change surface | all checks passed | PASS |
| Ruff, repository default scan | 145 pre-existing findings; no repository configuration exists | RECORDED / EXCLUDED |

The deterministic 22-case guidance matrix has SHA-256
`95D5BA7370280387C17907D0A67E9B079DC2542F292638D007666207CDF04B37`.

## Narrow lint repair

The first R4-surface scan found four import-order findings and one unused
`Decision` import left after the formatter signature changed. Ruff applied only
those five mechanical fixes. No retrieval, classification, wording, budget,
hook, plugin, enforcement, fixture, or experiment behavior changed.

Post-repair candidate hashes are:

| File | SHA-256 |
|---|---|
| `mneme/guidance.py` | `A74C69EA294606F311D7480D654B953F8CAA3B60706E5CC66CC80D2CF9FEABFA` |
| `mneme/guidance_applicability_eval.py` | `A9690E0D2372A9D7031DCF03F1733BA39D66387B7DBACFB1142A46F0572A4B29` |
| `tests/test_guidance.py` | `3E338038F8A1E98014DC708EFE49642CDC812D90273C1D0792BD20E322F9B4BE` |
| `tests/test_guidance_applicability_eval.py` | `30DC822548E44E4C0197B110625ED677AA01AC7E93D080EF0D784E073B8D6A15` |

The immutable R4 lock still verifies at
`49C4ADAA6C812E86594567CE30DE6169D1DE180EB300FD0BE86BE1E3D939B198`;
the post-R4 mechanical candidate hashes above are not written back into that
historical lock.

## Ruff diagnosis

The default whole-tree scan reports:

- 46 import-order findings;
- 23 unused-unpacked-variable findings;
- 20 unused imports;
- 10 implicit collection string-concatenation findings;
- 9 incorrect exception-type findings; and
- 37 findings across other rule groups.

Ninety-one are automatically fixable, while others require judgment. These
findings predate the R4 remediation and are not evidence of a guidance-role
defect.

## Frozen lint exception

For this remediation experiment only, the Ruff gate is:

```text
uvx ruff check \
  mneme/guidance.py \
  mneme/guidance_applicability_eval.py \
  tests/test_guidance.py \
  tests/test_guidance_applicability_eval.py
```

The exact surface is frozen because these are the files changed by R4 and its
R5 mechanical repair. All four must remain clean. Adding a new warning to that
surface fails the gate. The 145 whole-tree findings cannot be used to excuse a
new changed-surface finding, and cleaning them is outside R6.

With that explicit exception, R5 is complete and eligible for R6. Live Claude
spend and the production-effectiveness A/B remain paused until the R6 execution
lock is created and verified.
