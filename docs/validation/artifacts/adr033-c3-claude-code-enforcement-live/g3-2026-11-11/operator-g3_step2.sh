#!/usr/bin/env bash
# T-08 G3 live batch, step 2: G3-1 once, inside the operator's elevated pktmon
# capture (g3_capture.ps1). Waits for the capture to start, runs the probe,
# then signals the capture script to stop.
set -u
export DISABLE_AUTOUPDATER=1 C3_PINSET=G3
H=<MNEME_SRC>/docs/validation/artifacts/adr033-c3-claude-code-enforcement-live/harness
D=<CAPTURE>
LOG="$(dirname "$0")/g3_step2.log"
cd "$H" || { echo "cannot cd to harness"; exit 1; }
{
  echo "=== waiting for the elevated capture to start ($D/capture.started) ==="
  [ -e "$D/g3-1.done" ] && { echo "STEP2_RESULT=STALE_DONE_MARKER"; exit 1; }
  [ -e "$D/capture.started" ] && { echo "STEP2_RESULT=STALE_STARTED_MARKER"; exit 1; }
  for i in $(seq 1 3600); do [ -e "$D/capture.started" ] && break; sleep 2; done
  [ -e "$D/capture.started" ] || { echo "STEP2_RESULT=CAPTURE_NOT_STARTED"; exit 1; }
  sleep 3
  echo "=== preflight (G3 pin set) ==="
  bash preflight.sh || { touch "$D/g3-1.done"; echo "STEP2_RESULT=PREFLIGHT_FAILED"; exit 1; }
  echo "=== G3-1 Edit 1 ==="
  bash run_c3_probe.sh G3-1 Edit 1
  rc=$?
  sleep 3
  touch "$D/g3-1.done"
  echo "STEP2_RESULT=probe_exit_$rc"
} 2>&1 | tee "$LOG"
