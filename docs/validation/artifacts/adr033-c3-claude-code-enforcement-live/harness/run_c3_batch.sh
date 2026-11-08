#!/usr/bin/env bash
# Run one scope §5 batch: every row, every allowed tool, REPS repetitions.
#
# usage: run_c3_batch.sh <R|P|U|D|H|ABSENT|REVOKED|FR2> [reps=2]
#        run_c3_batch.sh FR2 <reps> --recheck
#
#   R, P, U, D, H  rows of that batch needing the AUTHORIZED phase (P-3/P-4 too)
#   FR2            C2b charter §17.5 live proof (matrix.FR2_ROWS, AUTHORIZED
#                  phase): the D-2 UNVERIFIABLE proceed with its paired controls,
#                  then classify_c3.py --pair for each control, same tool and rep.
#                  BATCH_DONE FR2 only if every probe is PASS and every pair
#                  PAIR_OK; else BATCH_INCOMPLETE FR2 (only missing evidence,
#                  e.g. D-2's netcap-sni.txt not yet added) or BATCH_FAILED FR2,
#                  exit 1. --recheck runs no probe: it re-classifies the existing
#                  evidence (after the operator adds netcap-sni.txt), re-pairs and
#                  re-applies that gate.
#   ABSENT         P-6 (golden must be ABSENT)
#   REVOKED        P-5 (golden must be REVOKED)
#
# Headless only; the interactive arm is run per probe with --interactive.
# Aborts on the first harness failure and never marks a batch done after one.
set -u
set -o pipefail
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins.env"
BATCH=${1:-}; REPS=${2:-2}; MODE=${3:-run}
case "$MODE" in run) ;; --recheck) [ "$BATCH" = FR2 ] || { echo "ABORT: --recheck is for FR2 only"; exit 1; } ;;
  *) echo "ABORT: unknown option $MODE"; exit 1 ;; esac
LIVE_ROOT="${C3_SELFTEST_LIVE:-$LIVE}"
case "$BATCH" in R|P|U|D|H|ABSENT|REVOKED|FR2) ;; *) echo "usage: $0 <R|P|U|D|H|ABSENT|REVOKED|FR2> [reps]"; exit 1;; esac
[ "$REPS" -ge 2 ] 2>/dev/null || { echo "ABORT: E9 needs at least 2 repetitions"; exit 1; }
bash "$BASE/preflight.sh" || { echo "ABORT: preflight failed"; exit 1; }

ROWS=$("$PY" -E -P -c "
import sys; sys.path.insert(0, sys.argv[1]); import matrix
batch = sys.argv[2]
for probe, spec in matrix.ROWS.items():
    phase = spec['phase']
    if batch == 'FR2': ok = probe in matrix.FR2_ROWS
    elif batch == 'ABSENT': ok = phase == 'ABSENT'
    elif batch == 'REVOKED': ok = phase == 'REVOKED'
    else: ok = probe[0] == batch and phase in ('AUTHORIZED', None)
    if ok:
        for tool in spec.get('tools', matrix.TOOLS):
            print(probe, tool)" "$(cygpath -w "$BASE")" "$BATCH" | tr -d '\r')
SUMMARY="$LIVE_ROOT/batch-$BATCH-$(date -u +%Y%m%dT%H%M%SZ).txt"
echo "batch=$BATCH reps=$REPS mode=$MODE harness_head=$(git -C "$BASE" rev-parse HEAD)" > "$SUMMARY"
incomplete=0; failed=0; pairs_bad=0   # FR2 gate only
while read -r probe tool; do
  [ -n "$probe" ] || continue
  for rep in $(seq 1 "$REPS"); do
    if [ "$MODE" = --recheck ]; then
      out="$LIVE_ROOT/$probe-$tool-$rep/out"
      [ -s "$out/setup.json" ] || { echo "ABORT: no evidence for $probe $tool $rep" | tee -a "$SUMMARY"; exit 1; }
      label=$("$PY" -E -P "$BASE/classify_c3.py" "$(cygpath -w "$out")" "$PIN_MODEL" | tr -d '\r') \
        || { echo "ABORT: re-classification failed for $probe $tool $rep" | tee -a "$SUMMARY"; exit 1; }
      line="$probe $tool $rep headless $label"
    else
      # stdin closed: a probe (and the `claude -p` inside it) must never read the
      # row list this loop iterates over (2026-10-21 ABSENT batch defect).
      line=$(bash "$BASE/run_c3_probe.sh" "$probe" "$tool" "$rep" < /dev/null 2>&1 | tail -1 | tr -d '\r')
    fi
    echo "$line" | tee -a "$SUMMARY"
    case "$line" in
      *" PASS") ;;
      *" EVIDENCE_INCOMPLETE") incomplete=$((incomplete + 1)) ;;
      *" FAIL"|*" PROTOCOL_DEVIATION"|*" RECORDED"|*" NOT_OFFERED") failed=$((failed + 1)) ;;
      *) echo "ABORT: harness failure on $probe $tool $rep (see its out/harness_failure.txt)" | tee -a "$SUMMARY"; exit 1 ;;
    esac
  done
done <<< "$ROWS"
if [ "$BATCH" = FR2 ]; then
  # R3 paired comparison: the diagnostic row against each control, same tool and rep.
  DIAG_ROW=$("$PY" -E -P -c "import sys; sys.path.insert(0, sys.argv[1]); import matrix; print(matrix.FR2_ROWS[0])" "$(cygpath -w "$BASE")" | tr -d '\r')
  while read -r probe tool; do
    [ -n "$probe" ] && [ "$probe" != "$DIAG_ROW" ] || continue
    for rep in $(seq 1 "$REPS"); do
      res=$("$PY" -E -P "$BASE/classify_c3.py" --pair "$(cygpath -w "$LIVE_ROOT/$DIAG_ROW-$tool-$rep/out")" \
            "$(cygpath -w "$LIVE_ROOT/$probe-$tool-$rep/out")" | tr -d '\r') \
        || { echo "ABORT: pair classification failed for $probe $tool $rep" | tee -a "$SUMMARY"; exit 1; }
      echo "PAIR $DIAG_ROW/$probe $tool $rep $res" | tee -a "$SUMMARY"
      [ "$res" = PAIR_OK ] || pairs_bad=$((pairs_bad + 1))
    done
  done <<< "$ROWS"
  # §17.5 gate. A pair mismatch while probes are only incomplete stays incomplete:
  # the pair check fails on any non-PASS probe, so --recheck settles it.
  if [ "$failed" -gt 0 ] || { [ "$pairs_bad" -gt 0 ] && [ "$incomplete" -eq 0 ]; }; then
    echo "BATCH_FAILED FR2: $failed probe(s) FAIL or deviating, $pairs_bad pair(s) not PAIR_OK" | tee -a "$SUMMARY"; exit 1
  elif [ "$incomplete" -gt 0 ]; then
    echo "BATCH_INCOMPLETE FR2: $incomplete probe(s) EVIDENCE_INCOMPLETE; add the missing evidence, then run: run_c3_batch.sh FR2 $REPS --recheck" | tee -a "$SUMMARY"; exit 1
  fi
fi
echo "BATCH_DONE $BATCH" | tee -a "$SUMMARY"
