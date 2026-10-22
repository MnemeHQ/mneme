#!/usr/bin/env bash
# Offline self-test of the C3 harness. NOT live evidence.
#
# usage: C3_ST_PY=<python.exe> C3_ST_MNEME_SRC=<windows path of a mneme checkout> \
#          selftest/run_selftest.sh
#
# Builds a local bare "fixture" remote in a temporary live root, seeds it with
# the real CLI (`mneme init`, `add_decision`, `protect activate`), walks it
# through ABSENT -> AUTHORIZED -> REVOKED, and runs probes through the real
# runner with the stub `claude`. The verifier runs for real against the
# file:// remote (allowed only in self-test mode). Batch U (network block),
# H-2 timing and both interactive arms are live-only and not exercised here.
set -u
set -o pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
BASE=$(cd "$HERE/.." && pwd)
: "${C3_ST_PY:?set C3_ST_PY}"; : "${C3_ST_MNEME_SRC:?set C3_ST_MNEME_SRC}"
export C3_SELFTEST=1 PY="$C3_ST_PY"
ROOT=$(mktemp -d)
export C3_SELFTEST_LIVE=$(cygpath -w "$ROOT/live" 2>/dev/null || echo "$ROOT/live")
mkdir -p "$ROOT/live"
REMOTE="$ROOT/remote.git"
export C3_SELFTEST_REMOTE=$("$PY" -E -P -c "import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve().as_uri())" "$(cygpath -w "$REMOTE" 2>/dev/null || echo "$REMOTE")" | tr -d '\r')
export PATH="$HERE/bin:$PATH"
fail=0

GIT() { git -c user.email=t@example.com -c user.name=t -c commit.gpgsign=false -c protocol.file.allow=always "$@"; }
MNEME() { "$PY" -E -P -c "import sys; sys.path.insert(0, sys.argv[1]); from mneme.cli import main; raise SystemExit(main(sys.argv[2:]))" "$C3_ST_MNEME_SRC" "$@"; }
EVENT() {  # $1 = authorize|revoke, in $SEED, via the library (no TTY in a self-test)
  "$PY" -E -P -c "
import sys; sys.path.insert(0, sys.argv[1])
from mneme.availability_authority import Attestation, prepare_event
prepare_event(sys.argv[2], sys.argv[3], Attestation('selftest operator', False, True), allow_file=True)" \
    "$C3_ST_MNEME_SRC" "$(cygpath -w "$SEED" 2>/dev/null || echo "$SEED")" "$1"
}

GIT init -q --bare -b main "$REMOTE"
SEED="$ROOT/seed"; GIT clone -q "$C3_SELFTEST_REMOTE" "$SEED" 2>/dev/null
(cd "$SEED" && printf 'import os\n\n\ndef handler():\n    return 1\n' > app.py \
  && MNEME init >/dev/null \
  && MNEME add_decision --memory .mneme/project_memory.json --id C3-DEC \
       --decision "Do not use psycopg2 in the service layer" --anti-pattern psycopg2 >/dev/null \
  && MNEME protect activate C3-DEC --memory .mneme/project_memory.json >/dev/null \
  && GIT add -A && GIT commit -qm "seed: activated C3-DEC" && GIT push -q origin main) \
  || { echo "selftest: seeding failed"; exit 1; }

run() {  # probe tool expected-label
  local line
  line=$(bash "$BASE/run_c3_probe.sh" "$1" "$2" 1 2>&1 | tail -1 | tr -d '\r')
  case "$line" in
    *" $3") echo "ok   $1 $2 -> $3" ;;
    *) echo "FAIL $1 $2: $line"; fail=1 ;;
  esac
}
phase() {
  bash "$BASE/refresh_golden.sh" "$1" >/dev/null || { echo "FAIL refresh_golden $1"; fail=1; return 1; }
}

phase ABSENT && run P-6 Edit PASS
(cd "$SEED" && EVENT authorize && GIT add -A && GIT commit -qm "authorize" && GIT push -q origin main)
if phase AUTHORIZED; then
  for case in "R-1 Write PASS" "R-2 Edit PASS" "R-3 Edit PASS" "R-4 MultiEdit PASS" \
              "R-5 Edit PASS" "R-6 Write PASS" "R-7 Edit PASS" "P-1 MultiEdit PASS" \
              "P-2 Edit PASS" "P-3 Write PASS" "P-4 Write PASS" "P-7 Edit PASS" \
              "D-1 Write PASS" "D-2 Edit PASS" "D-3 Edit PASS" "D-4 Write PASS" \
              "D-5 Edit PASS" "H-1 Edit RECORDED"; do
    run $case
  done
fi
# Negative controls: the classifier must not pass a host that ignores the hook,
# or an agent that never makes the call. (C3_STUB_* pass through the runner.)
C3_STUB_IGNORE_HOOK=1 run R-1 Write FAIL
C3_STUB_IGNORE_HOOK=1 run P-2 Edit FAIL
C3_STUB_SKIP_CALL=1 run P-1 Edit PROTOCOL_DEVIATION
# One whole batch through the batch runner (D rows, 2 repetitions each). It
# must reach BATCH_DONE with every expected row x tool x rep line PASS: a
# stdin leak (2026-10-21) skipped rows yet still ended in BATCH_DONE. The
# batch runs with a non-empty stdin on purpose, so a leak cannot hide.
BATCH_OUT=$(echo "stdin that no probe may read" | bash "$BASE/run_c3_batch.sh" D 2 2>&1)
WANT=$("$PY" -E -P -c "
import sys; sys.path.insert(0, sys.argv[1]); import matrix
print(2 * sum(len(s.get('tools', matrix.TOOLS)) for p, s in matrix.ROWS.items() if p[0] == 'D'))" \
  "$(cygpath -w "$BASE" 2>/dev/null || echo "$BASE")" | tr -d '\r')
GOT=$(echo "$BATCH_OUT" | grep -cE '^D-[0-9] [A-Za-z]+ [0-9]+ headless PASS$')
if echo "$BATCH_OUT" | tail -1 | grep -q '^BATCH_DONE D$' && [ "$GOT" = "$WANT" ]; then
  echo "ok   batch D x2 -> BATCH_DONE, $GOT/$WANT PASS"
else
  echo "FAIL batch D: $GOT/$WANT PASS lines"; fail=1
fi
(cd "$SEED" && EVENT revoke && GIT add -A && GIT commit -qm "revoke" && GIT push -q origin main)
phase REVOKED && run P-5 Write PASS

# Redacted collection: no live-root, home or user-name strings may survive.
DEST="$ROOT/collected"
"$PY" -E -P "$BASE/collect_redacted.py" "$C3_SELFTEST_LIVE" "$(cygpath -w "$DEST" 2>/dev/null || echo "$DEST")"   --mneme-src "$C3_ST_MNEME_SRC" >/dev/null || { echo "FAIL collect_redacted"; fail=1; }
# The delivery levels must stay separate: self-test E2 is stub-only, and no
# self-test probe may claim user-visible delivery.
if grep -rq '"model_delivered": "observed"' "$C3_SELFTEST_LIVE" --include=outcome.json    || grep -rq '"user_visible": "observed"' "$C3_SELFTEST_LIVE" --include=outcome.json; then
  echo "FAIL a self-test outcome claims real host or user delivery"; fail=1
else
  echo "ok   delivery levels: self-test E2 stub_only, user_visible not_tested"
fi
if grep -rqiF -e "$(basename "$ROOT")" -e "$(whoami)" "$DEST"; then
  echo "FAIL collect_redacted left a live path or user name"; fail=1
else
  echo "ok   collect_redacted: $(find "$DEST" -type f | wc -l) files, no live paths or user name"
fi
echo "selftest root: $ROOT"
[ $fail -eq 0 ] && echo "SELFTEST OK (not live evidence)" || echo "SELFTEST FAILED"
exit $fail
