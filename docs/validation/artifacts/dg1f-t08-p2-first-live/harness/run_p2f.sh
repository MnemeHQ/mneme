#!/usr/bin/env bash
# T-08 P2-first live evidence batch (charter §5.2.7 step 5): the D6 C2
# re-run, a notice probe and the planted-marker-plus-override probe, on the
# pinned host and the pinned P2-first hook source. Run from the operator's own
# authenticated terminal (Git Bash), never nested inside a Claude Code session.
#
# One batch per live root. P2F_STARTED is written before the first probe and
# never removed by the harness, so an aborted or finished batch cannot be
# re-rolled in place: archive the live root first. P2F_DONE is written only
# after the classification succeeded and wrote its summary.
set -u
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins.env"
abort() { echo "ABORT: $*"; exit 1; }
[ "$LIVE" = /c/dev/t08-p2first-live ] || abort "LIVE '$LIVE' is not the pinned live root"
"$PY" -I "$BASE/safe_rmtree.py" check-root || abort "disposable root unsafe"
for marker in P2F_STARTED P2F_DONE summary_p2f.md classification_p2f.json run_p2f.log; do
  [ -e "$LIVE/$marker" ] && abort "$LIVE/$marker exists: a batch already started here (archive the live root first)"
done
mkdir -p "$LIVE"
"$PY" -I "$BASE/safe_rmtree.py" check-root || abort "disposable root unsafe"
LOGF="$LIVE/run_p2f.log"
exec > >(tee "$LOGF") 2>&1

bash "$BASE/preflight.sh" || abort "preflight mismatch"
echo "[p2f] harness HEAD: $(git -C "$BASE" rev-parse HEAD)"
if [ -n "$(git -C "$BASE" status --porcelain -- .)" ]; then
  git -C "$BASE" status --short -- .
  abort "harness directory has uncommitted changes"
fi
(cd "$BASE" && sha256sum ./*.py ./*.sh pins.env .gitignore README.md selftest/*.py | sed 's/^/[p2f] harness sha256: /') \
  || abort "cannot hash harness"
date -u +%FT%TZ > "$LIVE/P2F_STARTED"

PROBES=(P2F-R0-control P2F-V5 P2F-V4 P2F-V5-own P2F-V4-own P2F-V5-notice P2F-planted-marker)
first=1
for n in "${PROBES[@]}"; do
  echo "=== $n"
  bash "$BASE/run_p2f_probe.sh" "$n" || abort "probe $n failed to run (no further probes; batch INCOMPLETE)"
  if [ $first = 1 ]; then
    m=$(sed -n 's/^init_model=//p' "$LIVE/$n/out/observer.txt")
    [ "$m" = "$PIN_MODEL" ] || abort "init model '$m' != pinned '$PIN_MODEL' (no further probes; batch INCOMPLETE)"
    first=0
  fi
done

"$PY" -I "$BASE/classify_p2f.py" "$(cygpath -w "$LIVE")" "${PROBES[@]}" \
  || abort "classification failed (batch INCOMPLETE; evidence kept)"
[ -s "$LIVE/summary_p2f.md" ] && [ -s "$LIVE/classification_p2f.json" ] \
  || abort "classification wrote no summary (batch INCOMPLETE; evidence kept)"
date -u +%FT%TZ > "$LIVE/P2F_DONE"
echo "Done. Evidence under $LIVE ; summary in $LIVE/summary_p2f.md"
