#!/usr/bin/env bash
# D6 batch 2: channel C2 (committed project settings env) with R0/R2 controls,
# V5 and V4, in the #518 R4 topology and in the own-repo topology.
# Run from the operator's own authenticated terminal (Git Bash), never nested
# inside another Claude Code session. Stops after C2 for evidence review.
# Batch-1 (C1) evidence directories in the same root are never touched.
set -u
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins.env"
"$PY" -I "$BASE/safe_rmtree.py" check-root || { echo "ABORT: disposable root unsafe"; exit 1; }
mkdir -p "$LIVE"
"$PY" -I "$BASE/safe_rmtree.py" check-root || { echo "ABORT: disposable root unsafe"; exit 1; }
LOGF="$LIVE/run_d6_c2.log"
exec > >(tee "$LOGF") 2>&1

bash "$BASE/preflight.sh" || { echo "ABORT: preflight mismatch"; exit 1; }

echo "=== D6-C2-R0-control (A protected, no settings env, sources $SOURCES)"
bash "$BASE/run_d6_c2_probe.sh" D6-C2-R0-control protected none r4
m=$(sed -n 's/^init_model=//p' "$LIVE/D6-C2-R0-control/out/observer.txt")
if [ "$m" != "$PIN_MODEL" ]; then
  echo "ABORT: init model '$m' != pinned '$PIN_MODEL' (no further probes run)"; exit 1
fi

echo "=== D6-C2-R2-counterfactual (A permissive, no settings env)"
bash "$BASE/run_d6_c2_probe.sh" D6-C2-R2-counterfactual permissive none r4
echo "=== D6-C2-V5 (B's committed settings env -> B's memory; session in B)"
bash "$BASE/run_d6_c2_probe.sh" D6-C2-V5 protected v5 r4
echo "=== D6-C2-V4 (B's committed settings env -> missing file; session in B)"
bash "$BASE/run_d6_c2_probe.sh" D6-C2-V4 protected v4 r4
echo "=== D6-C2-V5-own (A's own committed settings env -> B's memory; session in A)"
bash "$BASE/run_d6_c2_probe.sh" D6-C2-V5-own protected v5 own
echo "=== D6-C2-V4-own (A's own committed settings env -> missing file; session in A)"
bash "$BASE/run_d6_c2_probe.sh" D6-C2-V4-own protected v4 own

"$PY" -I "$BASE/summarize.py" "$(cygpath -w "$LIVE")" summary_c2.md \
  D6-C2-R0-control D6-C2-R2-counterfactual D6-C2-V5 D6-C2-V4 D6-C2-V5-own D6-C2-V4-own
date -u +%FT%TZ > "$LIVE/C2_DONE"
echo "Done. Evidence under $LIVE ; summary in $LIVE/summary_c2.md"
