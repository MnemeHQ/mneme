#!/usr/bin/env bash
# D6 batch 3: channel C3 (mid-session project settings env), V5 only, R4
# topology, with fresh R0/R2 controls. Order:
#   R0 control -> model-pin abort -> R2 control -> abort comparison if either
#   control fails -> C3(a)-attack -> C3(b)-resume (only if eligible) ->
#   C3(a)-plumbing -> summary.
# Run from the operator's own authenticated terminal (Git Bash), never nested
# inside another Claude Code session. Stops after C3 for evidence review; no
# C4/C5/C6 and no V4. Batch-1 (C1) and batch-2 (C2) evidence directories in the
# same root are never touched (safe_rmtree.py allowlists C3 names only).
set -u
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins.env"
"$PY" -I "$BASE/safe_rmtree.py" check-root || { echo "ABORT: disposable root unsafe"; exit 1; }
mkdir -p "$LIVE"
"$PY" -I "$BASE/safe_rmtree.py" check-root || { echo "ABORT: disposable root unsafe"; exit 1; }
LOGF="$LIVE/run_d6_c3.log"
exec > >(tee "$LOGF") 2>&1

bash "$BASE/preflight.sh" || { echo "ABORT: preflight mismatch"; exit 1; }

# As-run harness integrity: committed, clean (live runs), and hashed.
echo "[c3] harness HEAD: $(git -C "$BASE" rev-parse HEAD)"
if [ -n "$(git -C "$BASE" status --porcelain -- .)" ]; then
  if [ "${D6_SELFTEST:-}" = 1 ]; then echo "[c3] self-test: harness has uncommitted changes"
  else echo "ABORT: harness directory has uncommitted changes"; git -C "$BASE" status --short -- .; exit 1; fi
fi
(cd "$BASE" && sha256sum ./*.py ./*.sh pins.env selftest/* | sed 's/^/[c3] harness sha256: /')

label() { "$PY" -I -c "import json,sys; print(json.load(open(sys.argv[1],encoding='utf-8')).get('label'))" \
            "$(cygpath -w "$LIVE/$1/out/outcome.json")" 2>/dev/null | tr -d '\r'; }

echo "=== D6-C3-R0-control (A protected, no override, sources $SOURCES)"
bash "$BASE/run_d6_c3_probe.sh" D6-C3-R0-control
m=$(sed -n 's/^init_model=//p' "$LIVE/D6-C3-R0-control/out/observer.txt")
if [ "$m" != "$PIN_MODEL" ]; then
  echo "ABORT: init model '$m' != pinned '$PIN_MODEL' (no further probes run)"; exit 1
fi
[ "$(label D6-C3-R0-control)" = CONTROL_PASS ] || { echo "ABORT: R0 control failed ($(label D6-C3-R0-control)); comparison aborted"; exit 1; }

echo "=== D6-C3-R2-counterfactual (A permissive, no override)"
bash "$BASE/run_d6_c3_probe.sh" D6-C3-R2-counterfactual
[ "$(label D6-C3-R2-counterfactual)" = CONTROL_PASS ] || { echo "ABORT: R2 control failed ($(label D6-C3-R2-counterfactual)); comparison aborted"; exit 1; }

echo "=== D6-C3a-V5-attack (agent asked to write B's settings env, then Edit A; one process)"
bash "$BASE/run_d6_c3_probe.sh" D6-C3a-V5-attack
echo "=== D6-C3b-V5-resume (new process via --resume; only if the attack left an agent-written setting)"
bash "$BASE/run_d6_c3_probe.sh" D6-C3b-V5-resume
echo "=== D6-C3a-V5-plumbing (harness writes B's settings env after start, gated; agent only Edits A)"
bash "$BASE/run_d6_c3_probe.sh" D6-C3a-V5-plumbing

"$PY" -I "$BASE/classify_c3.py" summary "$(cygpath -w "$LIVE")" summary_c3.md \
  D6-C3-R0-control D6-C3-R2-counterfactual D6-C3a-V5-attack D6-C3b-V5-resume D6-C3a-V5-plumbing
date -u +%FT%TZ > "$LIVE/C3_DONE"
echo "Done. Evidence under $LIVE ; summary in $LIVE/summary_c3.md"
