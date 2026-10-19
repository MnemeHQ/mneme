#!/usr/bin/env bash
# H1c Amendment A1, HEADLESS pair (probe scope 4.2): no-op control H1c-sm-ctl, then
# emitter H1c-sm (Stop top-level systemMessage), then classify_a1.py headless.
# Run from the operator's own terminal, never nested in Claude Code. Fail closed:
# any failure writes A1_HEADLESS_INCOMPLETE and exits 1. A1_HEADLESS_DONE means
# only that the pair finished; the result is in outcome_a1_headless.json.
set -u
set -o pipefail
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins_a1.env"
"$PY" -I "$BASE/safe_rmtree_a1.py" check-root || { echo "ABORT: disposable root unsafe"; exit 1; }
mkdir -p "$LIVE" || { echo "ABORT: cannot create $LIVE"; exit 1; }
rm -f "$LIVE/A1_HEADLESS_DONE" "$LIVE/A1_HEADLESS_INCOMPLETE" || { echo "ABORT: cannot clear markers"; exit 1; }
exec > >(tee "$LIVE/run_a1_headless.log") 2>&1
abort() { echo "ABORT: $*"; { date -u +%FT%TZ; echo "$*"; } > "$LIVE/A1_HEADLESS_INCOMPLETE"; exit 1; }

bash "$BASE/preflight.sh" || abort "preflight mismatch"
# preflight.sh checks the H1 root's ancestors; check the A1 root's too.
d="$LIVE"; while [ "$d" != "/" ] && [ "$d" != "." ]; do
  [ -e "$d/.mneme" ] && abort "ancestor $d has .mneme"
  [ -e "$d/.git" ] && abort "ancestor $d is a git checkout"
  [ -e "$d/.claude/settings.json" ] && [ "$d" != "$LIVE" ] && abort "ancestor $d has .claude/settings.json"
  d=$(dirname "$d")
done
echo "[a1] harness HEAD: $(git -C "$BASE" rev-parse HEAD)"
if [ -n "$(git -C "$BASE" status --porcelain -- .)" ]; then
  if [ "${H1_SELFTEST:-}" = 1 ]; then echo "[a1] self-test: harness has uncommitted changes"
  else git -C "$BASE" status --short -- .; abort "harness directory has uncommitted changes"; fi
fi
(cd "$BASE" && sha256sum ./*.py ./*.sh ./*.env .gitignore README.md selftest/claude selftest/*.py | sed 's/^/[a1] harness sha256: /') \
  || abort "cannot hash harness"

for arm in H1c-sm-ctl H1c-sm; do
  echo "=== $arm"
  bash "$BASE/run_a1_probe.sh" "$arm" || abort "probe $arm failed (see $LIVE/$arm/out/harness_failure.txt)"
done
m=$("$PY" -I -c "
import json,sys
for l in open(sys.argv[1],encoding='utf-8'):
    try: e=json.loads(l)
    except ValueError: continue
    if e.get('type')=='system' and e.get('subtype')=='init': print(e.get('model')); break" \
  "$(cygpath -w "$LIVE/H1c-sm-ctl/out/events.jsonl")" | tr -d '\r') || abort "cannot read init model"
[ "$m" = "$PIN_MODEL" ] || abort "init model '$m' != pinned '$PIN_MODEL'"
lab=$("$PY" -I "$BASE/classify_a1.py" headless "$(cygpath -w "$LIVE")" "$PIN_MODEL" | tr -d '\r') || abort "classification failed"
echo "[a1] headless: $lab"
date -u +%FT%TZ > "$LIVE/A1_HEADLESS_DONE" || abort "cannot write A1_HEADLESS_DONE"
echo "Headless pair finished (A1_HEADLESS_DONE is not a pass). Result: $LIVE/outcome_a1_headless.json"
