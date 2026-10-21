#!/usr/bin/env bash
# Make the golden fixture clone for one fixture phase, then record it.
#
# usage: refresh_golden.sh <ABSENT|AUTHORIZED|REVOKED>
#
# Clones the fixture once over HTTPS into $LIVE/_golden, then runs the read-only
# `mneme availability status` and aborts unless the live baseline is in the
# expected phase. Probes copy this clone locally, so the network block for
# batch U can be applied after this step. Writes $LIVE/_golden.json.
set -u
set -o pipefail
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins.env"
PHASE=${1:-}
case "$PHASE" in ABSENT|AUTHORIZED|REVOKED) ;; *) echo "usage: $0 <ABSENT|AUTHORIZED|REVOKED>"; exit 1;; esac
LIVE_ROOT="${C3_SELFTEST_LIVE:-$LIVE}"
URL="${C3_SELFTEST_REMOTE:-$FIXTURE_URL}"
if [ -n "${C3_SELFTEST_REMOTE:-}" ] && [ "${C3_SELFTEST:-}" != 1 ]; then
  echo "ABORT: C3_SELFTEST_REMOTE is only honored in self-test mode"; exit 1
fi
mkdir -p "$LIVE_ROOT"
"$PY" -E -P "$BASE/safe_rmtree.py" delete _golden || { echo "ABORT: guarded delete refused"; exit 1; }
G="$LIVE_ROOT/_golden"
git -c protocol.file.allow="$([ "${C3_SELFTEST:-}" = 1 ] && echo always || echo never)" \
  clone -q "$URL" "$G" || { echo "ABORT: clone failed"; exit 1; }
TIP=$(git -C "$G" rev-parse HEAD)
# The shipped verifier, as `mneme availability status` runs it. The file
# transport is allowed only in self-test mode.
STATE=$("$PY" -E -P -c "import sys; sys.path.insert(0, sys.argv[1]); from mneme.availability_authority import verify; print(verify(sys.argv[2], allow_file=sys.argv[3] == '1').authorization)" \
        "$MNEME_SRC_W" "$(cygpath -w "$G" 2>/dev/null || echo "$G")" "${C3_SELFTEST:-0}" | tr -d '\r')
WANT=$PHASE; [ "$PHASE" = ABSENT ] && WANT=VERIFIED_ABSENT
[ "$STATE" = "$WANT" ] || { echo "ABORT: baseline is '$STATE', expected '$WANT'"; exit 1; }
printf '{"phase": "%s", "tip": "%s", "url": "%s", "date": "%s"}\n' \
  "$PHASE" "$TIP" "$URL" "$(date -u +%FT%TZ)" > "$LIVE_ROOT/_golden.json"
echo "golden: $G @ $TIP ($PHASE)"
