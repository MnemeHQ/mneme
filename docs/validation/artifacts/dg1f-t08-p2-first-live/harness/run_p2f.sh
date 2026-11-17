#!/usr/bin/env bash
# T-08 P2-first live evidence batch (charter §5.2.7 step 5): the D6 C2
# re-run, a notice probe and the planted-marker-plus-override probe, on the
# pinned host and the pinned P2-first hook source. Run from the operator's own
# authenticated terminal (Git Bash), never nested inside a Claude Code session.
set -u
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins.env"
"$PY" -I "$BASE/safe_rmtree.py" check-root || { echo "ABORT: disposable root unsafe"; exit 1; }
[ -e "$LIVE/P2F_DONE" ] && { echo "ABORT: $LIVE/P2F_DONE exists; this batch already ran (archive it first)"; exit 1; }
mkdir -p "$LIVE"
"$PY" -I "$BASE/safe_rmtree.py" check-root || { echo "ABORT: disposable root unsafe"; exit 1; }
LOGF="$LIVE/run_p2f.log"
exec > >(tee "$LOGF") 2>&1

bash "$BASE/preflight.sh" || { echo "ABORT: preflight mismatch"; exit 1; }

PROBES=(P2F-R0-control P2F-V5 P2F-V4 P2F-V5-own P2F-V4-own P2F-V5-notice P2F-planted-marker)
first=1
for n in "${PROBES[@]}"; do
  echo "=== $n"
  bash "$BASE/run_p2f_probe.sh" "$n" || { echo "ABORT: probe $n failed to run (no further probes)"; exit 1; }
  if [ $first = 1 ]; then
    m=$(sed -n 's/^init_model=//p' "$LIVE/$n/out/observer.txt")
    [ "$m" = "$PIN_MODEL" ] || { echo "ABORT: init model '$m' != pinned '$PIN_MODEL' (no further probes run)"; exit 1; }
    first=0
  fi
done

"$PY" -I "$BASE/classify_p2f.py" "$(cygpath -w "$LIVE")" "${PROBES[@]}"
date -u +%FT%TZ > "$LIVE/P2F_DONE"
echo "Done. Evidence under $LIVE ; summary in $LIVE/summary_p2f.md"
