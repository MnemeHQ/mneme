#!/usr/bin/env bash
# H1 (Claude Code) host-output-path channel probes, per the accepted probe scope
# docs/plans/2026-10-17-dg1f-t08-d5-p2-host-path-probe-scope.md (#545).
# Order, per path: control arm first, then emitter arm, then classification.
#   H1a-edit -> model-pin abort -> H1a-bash -> H1b-start -> H1c-stop
#   -> verify -> summary -> H1_DONE.
# Run from the operator's own terminal (Git Bash), never nested inside another
# Claude Code session. Fail closed: any probe failure aborts, writes
# H1_INCOMPLETE with the reason and exits 1. H1_DONE is written only after all
# four outcomes are verified and the summary is written.
set -u
set -o pipefail
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins.env"
PATHS=(H1a-edit H1a-bash H1b-start H1c-stop)
"$PY" -I "$BASE/safe_rmtree.py" check-root || { echo "ABORT: disposable root unsafe"; exit 1; }
mkdir -p "$LIVE" || { echo "ABORT: cannot create $LIVE"; exit 1; }
rm -f "$LIVE/H1_DONE" "$LIVE/H1_INCOMPLETE" "$LIVE/summary_h1.md" || { echo "ABORT: cannot clear batch markers"; exit 1; }
LOGF="$LIVE/run_h1.log"
exec > >(tee "$LOGF") 2>&1

abort() {
  echo "ABORT: $*"
  { date -u +%FT%TZ; echo "$*"; } > "$LIVE/H1_INCOMPLETE"
  exit 1
}

bash "$BASE/preflight.sh" || abort "preflight mismatch"
echo "[h1] harness HEAD: $(git -C "$BASE" rev-parse HEAD)"
if [ -n "$(git -C "$BASE" status --porcelain -- .)" ]; then
  if [ "${H1_SELFTEST:-}" = 1 ]; then echo "[h1] self-test: harness has uncommitted changes"
  else git -C "$BASE" status --short -- .; abort "harness directory has uncommitted changes"; fi
fi
(cd "$BASE" && sha256sum ./*.py ./*.sh pins.env .gitignore README.md selftest/claude selftest/*.py | sed 's/^/[h1] harness sha256: /') \
  || abort "cannot hash harness"

probe() { bash "$BASE/run_h1_probe.sh" "$1" || abort "probe $1 failed (see $LIVE/$1/out/harness_failure.txt)"; }
LIVE_W=$(cygpath -w "$LIVE")
first=1
for p in "${PATHS[@]}"; do
  echo "=== $p-ctl (no-op control)"
  probe "$p-ctl"
  if [ $first = 1 ]; then
    m=$("$PY" -I -c "
import json,sys
for l in open(sys.argv[1],encoding='utf-8'):
    try: e=json.loads(l)
    except ValueError: continue
    if e.get('type')=='system' and e.get('subtype')=='init': print(e.get('model')); break" \
      "$(cygpath -w "$LIVE/$p-ctl/out/events.jsonl")" | tr -d '\r') || abort "cannot read init model"
    [ "$m" = "$PIN_MODEL" ] || abort "init model '$m' != pinned '$PIN_MODEL' (no further probes run)"
    first=0
  fi
  echo "=== $p (emitter)"
  probe "$p"
  lab=$("$PY" -I "$BASE/classify_h1.py" pair "$LIVE_W" "$p" "$PIN_MODEL" | tr -d '\r') || abort "classification of $p failed"
  echo "[h1] $p: $lab"
done
"$PY" -I "$BASE/classify_h1.py" verify "$LIVE_W" || abort "evidence verification failed"
"$PY" -I "$BASE/classify_h1.py" summary "$LIVE_W" summary_h1.md || abort "summary failed"
[ -s "$LIVE/summary_h1.md" ] || abort "summary_h1.md missing"
date -u +%FT%TZ > "$LIVE/H1_DONE" || abort "cannot write H1_DONE"
echo "Done. Evidence under $LIVE ; summary in $LIVE/summary_h1.md"
