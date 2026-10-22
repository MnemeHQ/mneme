#!/usr/bin/env bash
# Run one scope §5 batch: every row, every allowed tool, REPS repetitions.
#
# usage: run_c3_batch.sh <R|P|U|D|H|ABSENT|REVOKED> [reps=2]
#
#   R, P, U, D, H  rows of that batch needing the AUTHORIZED phase (P-3/P-4 too)
#   ABSENT         P-6 (golden must be ABSENT)
#   REVOKED        P-5 (golden must be REVOKED)
#
# Headless only; the interactive arm is run per probe with --interactive.
# Aborts on the first harness failure and never marks a batch done after one.
set -u
set -o pipefail
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins.env"
BATCH=${1:-}; REPS=${2:-2}
LIVE_ROOT="${C3_SELFTEST_LIVE:-$LIVE}"
case "$BATCH" in R|P|U|D|H|ABSENT|REVOKED) ;; *) echo "usage: $0 <R|P|U|D|H|ABSENT|REVOKED> [reps]"; exit 1;; esac
[ "$REPS" -ge 2 ] 2>/dev/null || { echo "ABORT: E9 needs at least 2 repetitions"; exit 1; }
bash "$BASE/preflight.sh" || { echo "ABORT: preflight failed"; exit 1; }

ROWS=$("$PY" -E -P -c "
import sys; sys.path.insert(0, sys.argv[1]); import matrix
batch = sys.argv[2]
for probe, spec in matrix.ROWS.items():
    phase = spec['phase']
    if batch == 'ABSENT': ok = phase == 'ABSENT'
    elif batch == 'REVOKED': ok = phase == 'REVOKED'
    else: ok = probe[0] == batch and phase in ('AUTHORIZED', None)
    if ok:
        for tool in spec.get('tools', matrix.TOOLS):
            print(probe, tool)" "$(cygpath -w "$BASE")" "$BATCH" | tr -d '\r')
SUMMARY="$LIVE_ROOT/batch-$BATCH-$(date -u +%Y%m%dT%H%M%SZ).txt"
echo "batch=$BATCH reps=$REPS harness_head=$(git -C "$BASE" rev-parse HEAD)" > "$SUMMARY"
while read -r probe tool; do
  [ -n "$probe" ] || continue
  for rep in $(seq 1 "$REPS"); do
    # stdin closed: a probe (and the `claude -p` inside it) must never read the
    # row list this loop iterates over (2026-10-21 ABSENT batch defect).
    line=$(bash "$BASE/run_c3_probe.sh" "$probe" "$tool" "$rep" < /dev/null 2>&1 | tail -1 | tr -d '\r')
    echo "$line" | tee -a "$SUMMARY"
    case "$line" in
      *" PASS"|*" FAIL"|*" EVIDENCE_INCOMPLETE"|*" PROTOCOL_DEVIATION"|*" RECORDED"|*" NOT_OFFERED") ;;
      *) echo "ABORT: harness failure on $probe $tool $rep (see its out/harness_failure.txt)" | tee -a "$SUMMARY"; exit 1 ;;
    esac
  done
done <<< "$ROWS"
echo "BATCH_DONE $BATCH" | tee -a "$SUMMARY"
