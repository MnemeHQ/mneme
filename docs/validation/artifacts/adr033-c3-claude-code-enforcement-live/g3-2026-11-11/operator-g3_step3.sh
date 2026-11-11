#!/usr/bin/env bash
# T-08 G3 live batch, step 3: attach-once recheck (runs no probe). The gate keeps
# G3-2 at its label and re-classifies G3-1 only because its capture was absent.
set -u
export DISABLE_AUTOUPDATER=1
H=<MNEME_SRC>/docs/validation/artifacts/adr033-c3-claude-code-enforcement-live/harness
LOG="$(dirname "$0")/g3_step3.log"
cd "$H" || { echo "cannot cd to harness"; exit 1; }
{
  echo "=== run_c3_batch.sh G3 1 --recheck ==="
  bash run_c3_batch.sh G3 1 --recheck < /dev/null
  echo "STEP3_RESULT=exit_$?"
} 2>&1 | tee "$LOG"
