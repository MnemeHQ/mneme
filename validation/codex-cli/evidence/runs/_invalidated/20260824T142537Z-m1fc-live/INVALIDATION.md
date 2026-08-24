Classification: harness-preflight failure - NOT capability evidence.

run_m1fc_live.py CASES passed hunk bodies WITHOUT their operation header to
prompt_for(): GOOD_UPDATE/BAD_UPDATE began at @@, so every bundled patch was
grammatically invalid ("@@ is not a valid hunk header") and Codex rejected
the apply_patch itself before any meaningful hook evaluation. No Mneme
conclusion possible; all three cases produced no mutation and no block.

Fix: include "*** Update File: service.py" as the first body line of both
update case definitions.
