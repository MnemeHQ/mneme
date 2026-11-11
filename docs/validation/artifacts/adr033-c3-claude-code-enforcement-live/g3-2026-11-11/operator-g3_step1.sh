#!/usr/bin/env bash
# T-08 G3 live batch, step 1 (owner-authorized 2026-11-11): G3 preflight,
# golden refresh at AUTHORIZED, then G3-2 once. Charter §10 order.
set -u
export DISABLE_AUTOUPDATER=1 C3_PINSET=G3
H=<MNEME_SRC>/docs/validation/artifacts/adr033-c3-claude-code-enforcement-live/harness
LOG="$(dirname "$0")/g3_step1.log"
cd "$H" || { echo "cannot cd to harness"; exit 1; }
{
  echo "=== preflight (G3 pin set) ==="
  bash preflight.sh || { echo "STEP1_RESULT=PREFLIGHT_FAILED"; exit 1; }
  echo "=== refresh_golden AUTHORIZED ==="
  bash refresh_golden.sh AUTHORIZED || { echo "STEP1_RESULT=GOLDEN_FAILED"; exit 1; }
  echo "=== G3-2 Edit 1 ==="
  bash run_c3_probe.sh G3-2 Edit 1
  echo "STEP1_RESULT=probe_exit_$?"
} 2>&1 | tee "$LOG"
