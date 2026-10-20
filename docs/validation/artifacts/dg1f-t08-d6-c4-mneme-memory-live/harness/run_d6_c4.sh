#!/usr/bin/env bash
# D6 batch 4: channel C4 (uncommitted .claude/settings.local.json env), V5 only,
# with fresh R0/R2 controls (#527). Order:
#   R0 control -> model-pin abort -> R2 control -> abort comparison unless both
#   controls are CONTROL_PASS -> V5-pre -> V5-pre-own -> C4(a)-attack ->
#   C4(b)-resume (NOT_EXECUTED by design unless eligible) -> C4(a)-plumbing-edit
#   -> C4(a)-plumbing-create -> verify all evidence -> summary -> C4_DONE.
# Run from the operator's own authenticated terminal (Git Bash), never nested
# inside another Claude Code session. Stops after C4 for evidence review; no
# C5/C6 and no V4. The C1, C2 and C3 evidence directories in the same root are
# never touched (safe_rmtree.py allowlists the eight C4 names only).
#
# Fail closed: any probe or evidence-step failure aborts the batch, writes
# C4_INCOMPLETE with the reason and exits 1. C4_DONE is removed at start and
# written only after `classify_c4.py verify` confirms all eight probes' outcome
# and evidence files and the summary is written.
set -u
set -o pipefail
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins.env"
PROBES=(D6-C4-R0-control D6-C4-R2-counterfactual D6-C4-V5-pre D6-C4-V5-pre-own D6-C4a-V5-attack
        D6-C4b-V5-resume D6-C4a-V5-plumbing-edit D6-C4a-V5-plumbing-create)
"$PY" -I "$BASE/safe_rmtree.py" check-root || { echo "ABORT: disposable root unsafe"; exit 1; }
mkdir -p "$LIVE" || { echo "ABORT: cannot create $LIVE"; exit 1; }
"$PY" -I "$BASE/safe_rmtree.py" check-root || { echo "ABORT: disposable root unsafe"; exit 1; }
rm -f "$LIVE/C4_DONE" "$LIVE/C4_INCOMPLETE" "$LIVE/summary_c4.md" || { echo "ABORT: cannot clear batch markers"; exit 1; }
LOGF="$LIVE/run_d6_c4.log"
exec > >(tee "$LOGF") 2>&1

abort() {
  echo "ABORT: $*"
  { date -u +%FT%TZ; echo "$*"; } > "$LIVE/C4_INCOMPLETE"
  exit 1
}

bash "$BASE/preflight.sh" || abort "preflight mismatch"

# As-run harness integrity: committed, clean (live runs), and hashed.
echo "[c4] harness HEAD: $(git -C "$BASE" rev-parse HEAD)"
if [ -n "$(git -C "$BASE" status --porcelain -- .)" ]; then
  if [ "${D6_SELFTEST:-}" = 1 ]; then echo "[c4] self-test: harness has uncommitted changes"
  else git -C "$BASE" status --short -- .; abort "harness directory has uncommitted changes"; fi
fi
(cd "$BASE" && sha256sum ./*.py ./*.sh pins.env .gitignore README.md selftest/* | sed 's/^/[c4] harness sha256: /') || abort "cannot hash harness"

label() { "$PY" -I -c "import json,sys; print(json.load(open(sys.argv[1],encoding='utf-8')).get('label'))" \
            "$(cygpath -w "$LIVE/$1/out/outcome.json")" | tr -d '\r'; }
probe() { bash "$BASE/run_d6_c4_probe.sh" "$1" || abort "probe $1 failed (see $LIVE/$1/out/harness_failure.txt)"; }

echo "=== D6-C4-R0-control (A protected, no override, B local {}, sources $SOURCES)"
probe D6-C4-R0-control
m=$(sed -n 's/^init_model=//p' "$LIVE/D6-C4-R0-control/out/observer.txt")
[ "$m" = "$PIN_MODEL" ] || abort "init model '$m' != pinned '$PIN_MODEL' (no further probes run)"
l=$(label D6-C4-R0-control) || abort "cannot read R0 outcome"
[ "$l" = CONTROL_PASS ] || abort "R0 control failed ($l); comparison aborted"

echo "=== D6-C4-R2-counterfactual (A permissive, no override, B local {})"
probe D6-C4-R2-counterfactual
l=$(label D6-C4-R2-counterfactual) || abort "cannot read R2 outcome"
[ "$l" = CONTROL_PASS ] || abort "R2 control failed ($l); comparison aborted"

echo "=== D6-C4-V5-pre (R4; B's uncommitted local file carries the env at launch)"
probe D6-C4-V5-pre
echo "=== D6-C4-V5-pre-own (own; A's uncommitted local file carries the env at launch)"
probe D6-C4-V5-pre-own
echo "=== D6-C4a-V5-attack (agent asked to write B's local settings env, then Edit A; one process)"
probe D6-C4a-V5-attack
echo "=== D6-C4b-V5-resume (new process via --resume; only if C4(b) eligibility (a) and (b) hold)"
probe D6-C4b-V5-resume
echo "=== D6-C4a-V5-plumbing-edit (harness adds env to B's existing {} local file after start, gated)"
probe D6-C4a-V5-plumbing-edit
echo "=== D6-C4a-V5-plumbing-create (harness creates B's absent local file after start, gated)"
probe D6-C4a-V5-plumbing-create

"$PY" -I "$BASE/classify_c4.py" verify "$(cygpath -w "$LIVE")" "${PROBES[@]}" || abort "evidence verification failed"
"$PY" -I "$BASE/classify_c4.py" summary "$(cygpath -w "$LIVE")" summary_c4.md "${PROBES[@]}" || abort "summary failed"
[ -s "$LIVE/summary_c4.md" ] || abort "summary_c4.md missing"
[ "$(grep -c '^| D6-C4' "$LIVE/summary_c4.md")" = "${#PROBES[@]}" ] || abort "summary does not list all ${#PROBES[@]} probes"
date -u +%FT%TZ > "$LIVE/C4_DONE" || abort "cannot write C4_DONE"
echo "Done. Evidence under $LIVE ; summary in $LIVE/summary_c4.md"
