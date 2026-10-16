#!/usr/bin/env bash
# D6 batch 3: channel C3 (mid-session project settings env), V5 only, R4
# topology, with fresh R0/R2 controls. Order:
#   R0 control -> model-pin abort -> R2 control -> abort comparison if either
#   control fails -> C3(a)-attack -> C3(b)-resume (NOT_EXECUTED by design unless
#   eligible) -> C3(a)-plumbing -> verify all evidence -> summary -> C3_DONE.
# Run from the operator's own authenticated terminal (Git Bash), never nested
# inside another Claude Code session. Stops after C3 for evidence review; no
# C4/C5/C6 and no V4. Batch-1 (C1) and batch-2 (C2) evidence directories in the
# same root are never touched (safe_rmtree.py allowlists C3 names only).
#
# Fail closed (review of #526 finding 3): any probe or evidence-step failure
# aborts the batch, writes C3_INCOMPLETE with the reason and exits 1. C3_DONE is
# removed at start and written only after `classify_c3.py verify` confirms all
# five probes' outcome and evidence files and the summary is written.
set -u
set -o pipefail
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins.env"
PROBES=(D6-C3-R0-control D6-C3-R2-counterfactual D6-C3a-V5-attack D6-C3b-V5-resume D6-C3a-V5-plumbing)
"$PY" -I "$BASE/safe_rmtree.py" check-root || { echo "ABORT: disposable root unsafe"; exit 1; }
mkdir -p "$LIVE" || { echo "ABORT: cannot create $LIVE"; exit 1; }
"$PY" -I "$BASE/safe_rmtree.py" check-root || { echo "ABORT: disposable root unsafe"; exit 1; }
rm -f "$LIVE/C3_DONE" "$LIVE/C3_INCOMPLETE" "$LIVE/summary_c3.md" || { echo "ABORT: cannot clear batch markers"; exit 1; }
LOGF="$LIVE/run_d6_c3.log"
exec > >(tee "$LOGF") 2>&1

abort() {
  echo "ABORT: $*"
  { date -u +%FT%TZ; echo "$*"; } > "$LIVE/C3_INCOMPLETE"
  exit 1
}

bash "$BASE/preflight.sh" || abort "preflight mismatch"

# As-run harness integrity: committed, clean (live runs), and hashed.
echo "[c3] harness HEAD: $(git -C "$BASE" rev-parse HEAD)"
if [ -n "$(git -C "$BASE" status --porcelain -- .)" ]; then
  if [ "${D6_SELFTEST:-}" = 1 ]; then echo "[c3] self-test: harness has uncommitted changes"
  else git -C "$BASE" status --short -- .; abort "harness directory has uncommitted changes"; fi
fi
(cd "$BASE" && sha256sum ./*.py ./*.sh pins.env selftest/* | sed 's/^/[c3] harness sha256: /') || abort "cannot hash harness"

label() { "$PY" -I -c "import json,sys; print(json.load(open(sys.argv[1],encoding='utf-8')).get('label'))" \
            "$(cygpath -w "$LIVE/$1/out/outcome.json")" | tr -d '\r'; }
probe() { bash "$BASE/run_d6_c3_probe.sh" "$1" || abort "probe $1 failed (see $LIVE/$1/out/harness_failure.txt)"; }

echo "=== D6-C3-R0-control (A protected, no override, sources $SOURCES)"
probe D6-C3-R0-control
m=$(sed -n 's/^init_model=//p' "$LIVE/D6-C3-R0-control/out/observer.txt")
[ "$m" = "$PIN_MODEL" ] || abort "init model '$m' != pinned '$PIN_MODEL' (no further probes run)"
l=$(label D6-C3-R0-control) || abort "cannot read R0 outcome"
[ "$l" = CONTROL_PASS ] || abort "R0 control failed ($l); comparison aborted"

echo "=== D6-C3-R2-counterfactual (A permissive, no override)"
probe D6-C3-R2-counterfactual
l=$(label D6-C3-R2-counterfactual) || abort "cannot read R2 outcome"
[ "$l" = CONTROL_PASS ] || abort "R2 control failed ($l); comparison aborted"

echo "=== D6-C3a-V5-attack (agent asked to write B's settings env, then Edit A; one process)"
probe D6-C3a-V5-attack
echo "=== D6-C3b-V5-resume (new process via --resume; only if the attack left an agent-written setting)"
probe D6-C3b-V5-resume
echo "=== D6-C3a-V5-plumbing (harness writes B's settings env after start, gated; agent only Edits A)"
probe D6-C3a-V5-plumbing

"$PY" -I "$BASE/classify_c3.py" verify "$(cygpath -w "$LIVE")" "${PROBES[@]}" || abort "evidence verification failed"
"$PY" -I "$BASE/classify_c3.py" summary "$(cygpath -w "$LIVE")" summary_c3.md "${PROBES[@]}" || abort "summary failed"
[ -s "$LIVE/summary_c3.md" ] || abort "summary_c3.md missing"
[ "$(grep -c '^| D6-C3' "$LIVE/summary_c3.md")" = "${#PROBES[@]}" ] || abort "summary does not list all ${#PROBES[@]} probes"
date -u +%FT%TZ > "$LIVE/C3_DONE" || abort "cannot write C3_DONE"
echo "Done. Evidence under $LIVE ; summary in $LIVE/summary_c3.md"
