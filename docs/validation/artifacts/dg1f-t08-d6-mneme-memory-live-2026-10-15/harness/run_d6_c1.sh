#!/usr/bin/env bash
# D6 batch 1: R0/R2 controls + C1 (operator shell env) for V5 and V4.
# Run from the operator's own authenticated terminal (Git Bash), never nested
# inside another Claude Code session. Stops after C1 for evidence review.
set -u
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins.env"
"$PY" -I "$BASE/safe_rmtree.py" check-root || { echo "ABORT: disposable root unsafe"; exit 1; }
mkdir -p "$LIVE"
"$PY" -I "$BASE/safe_rmtree.py" check-root || { echo "ABORT: disposable root unsafe"; exit 1; }
LOGF="$LIVE/run_d6_c1.log"
exec > >(tee "$LOGF") 2>&1

bash "$BASE/preflight.sh" || { echo "ABORT: preflight mismatch"; exit 1; }

echo "=== D6-R0-control (A protected, no override)"
bash "$BASE/run_d6_probe.sh" D6-R0-control protected none
m=$(sed -n 's/^init_model=//p' "$LIVE/D6-R0-control/out/observer.txt")
if [ "$m" != "$PIN_MODEL" ]; then
  echo "ABORT: init model '$m' != pinned '$PIN_MODEL' (no further probes run)"; exit 1
fi

echo "=== D6-R2-counterfactual (A permissive, no override)"
bash "$BASE/run_d6_probe.sh" D6-R2-counterfactual permissive none
echo "=== D6-C1-V5 (operator MNEME_MEMORY -> repo B memory)"
bash "$BASE/run_d6_probe.sh" D6-C1-V5 protected v5
echo "=== D6-C1-V4 (operator MNEME_MEMORY -> missing file)"
bash "$BASE/run_d6_probe.sh" D6-C1-V4 protected v4

"$PY" -I "$BASE/summarize.py" "$(cygpath -w "$LIVE")" D6-R0-control D6-R2-counterfactual D6-C1-V5 D6-C1-V4
date -u +%FT%TZ > "$LIVE/C1_DONE"
echo "Done. Evidence under $LIVE ; summary in $LIVE/summary.md"
