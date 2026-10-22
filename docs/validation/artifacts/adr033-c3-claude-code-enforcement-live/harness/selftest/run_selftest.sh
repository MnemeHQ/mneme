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
# The stub host keeps its session transcripts here, outside the live root.
export C3_SELFTEST_CLAUDE_HOME=$(cygpath -w "$ROOT/claude-home" 2>/dev/null || echo "$ROOT/claude-home")
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
  for case in "R-1 Write PASS" "R-2 Edit PASS" "R-3 Edit PASS" "R-4 Edit PASS" \
              "R-5 Edit PASS" "R-6 Write PASS" "R-7 Edit PASS" "P-1 Write PASS" \
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
# C2b §17.5 (F-R2): the UNVERIFIABLE diagnostic counts only when model-bound
# (R1). Host output only (R2) or nothing is a FAIL, a missing transcript is
# EVIDENCE_INCOMPLETE, and a control that shows a diagnostic is a FAIL.
fr2() {  # stub-mode probe tool expected-label outcome-fragment
  C3_STUB_DIAG=$1 run "$2" "$3" "$4"
  grep -qF "$5" "$ROOT/live/$2-$3-1/out/outcome.json" \
    && echo "ok   F-R2 $1 $2 $3: $5" || { echo "FAIL F-R2 $1 $2 $3: no '$5'"; fail=1; }
}
fr2 host       D-2 Edit  PASS                 '"model_delivered": "stub_only"'
fr2 host_only  D-2 Edit  FAIL                 'no R1 hook_additional_context diagnostic (host output only)'
fr2 missing    D-2 Write FAIL                 'F-R2: no R1 hook_additional_context diagnostic"'
# Model-bound but not the R1 attachment (here: the tool_result) never passes.
fr2 tool_result D-2 Edit FAIL                 'no R1 hook_additional_context diagnostic (other model-bound entry only)'
fr2 no_transcript D-2 Edit EVIDENCE_INCOMPLETE 'F-R2 session transcript'
fr2 host       P-1 Write PASS                 '"FR2_absent": "ok"'
fr2 host       D-1 Edit  PASS                 '"FR2_emitted_absent": "ok"'
fr2 inject     P-1 Edit  FAIL                 'F-R2 control: an availability diagnostic appeared'
fr2 no_transcript P-1 Write EVIDENCE_INCOMPLETE 'F-R2 session transcript'
# The FR2 batch gate: BATCH_DONE only when every probe is PASS and every pair
# PAIR_OK. A FAIL ends BATCH_FAILED; missing evidence ends BATCH_INCOMPLETE.
fr2_gate() {  # stub-mode expected-last-line-prefix
  local out rc
  out=$(C3_STUB_DIAG=$1 bash "$BASE/run_c3_batch.sh" FR2 2 < /dev/null 2>&1); rc=$?
  if [ $rc -ne 0 ] && echo "$out" | tail -1 | grep -q "^$2" && ! echo "$out" | grep -q '^BATCH_DONE'; then
    echo "ok   batch FR2 with stub $1 -> $2, exit $rc"
  else
    echo "FAIL batch FR2 with stub $1: exit $rc, last line: $(echo "$out" | tail -1)"; fail=1
  fi
}
fr2_gate host_only     'BATCH_FAILED FR2'
fr2_gate no_transcript 'BATCH_INCOMPLETE FR2'
# The §17.5 batch: D-2 with its paired controls (P-1, D-1), 2 repetitions, and
# the R3 pair comparison of D-2 against each control, same tool and rep.
FR2_OUT=$(echo "stdin that no probe may read" | bash "$BASE/run_c3_batch.sh" FR2 2 2>&1)
FR2_PASS=$(echo "$FR2_OUT" | grep -cE '^(D-2|P-1|D-1) (Write|Edit) [12] headless PASS$')
FR2_PAIR=$(echo "$FR2_OUT" | grep -cE '^PAIR D-2/(P-1|D-1) (Write|Edit) [12] PAIR_OK$')
if echo "$FR2_OUT" | tail -1 | grep -q '^BATCH_DONE FR2$' && [ "$FR2_PASS" = 12 ] && [ "$FR2_PAIR" = 8 ]; then
  echo "ok   batch FR2 x2 -> BATCH_DONE, 12/12 PASS, 8/8 PAIR_OK"
else
  echo "FAIL batch FR2: $FR2_PASS/12 PASS, $FR2_PAIR/8 PAIR_OK"; echo "$FR2_OUT" | tail -5; fail=1
fi
# --recheck re-classifies the same evidence without running a probe.
RECHECK=$(bash "$BASE/run_c3_batch.sh" FR2 2 --recheck < /dev/null 2>&1 | tail -1 | tr -d '\r')
[ "$RECHECK" = "BATCH_DONE FR2" ] && echo "ok   batch FR2 --recheck -> BATCH_DONE" \
  || { echo "FAIL batch FR2 --recheck -> $RECHECK"; fail=1; }
# A pair whose control failed is never PAIR_OK.
C3_STUB_DIAG=inject run P-1 Edit FAIL
PAIR=$("$PY" -E -P "$BASE/classify_c3.py" --pair "$(cygpath -w "$ROOT/live/D-2-Edit-1/out")" \
       "$(cygpath -w "$ROOT/live/P-1-Edit-1/out")" | tr -d '\r')
[ "$PAIR" = PAIR_MISMATCH ] && echo "ok   pair with a failed control -> PAIR_MISMATCH" \
  || { echo "FAIL pair with a failed control -> $PAIR"; fail=1; }
# Scope Amendment 1: a tool missing from the host inventory is N/A.
C3_STUB_DROP_TOOL=Edit run R-2 Edit NOT_OFFERED
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
# The delivery levels must stay separate: self-test E2 and the F-R2 transcript
# are stub-only, and no self-test probe may claim user-visible delivery.
if grep -rq '"model_delivered": "observed"' "$C3_SELFTEST_LIVE" --include=outcome.json    || grep -rq '"user_visible": "observed"' "$C3_SELFTEST_LIVE" --include=outcome.json; then
  echo "FAIL a self-test outcome claims real host or user delivery"; fail=1
else
  echo "ok   delivery levels: self-test E2 stub_only, user_visible not_tested"
fi
# Fails closed (a crashed `grep -rqiF` once read as "no leak"). Each path is
# matched with any run of separators, so every JSON escaping level counts; the
# user name as a whole word, as collect_redacted.py replaces it. The self-test
# root name itself may remain in the file:// remote URL and the stub's
# transcript home, which exist only in a self-test.
if "$PY" -E -P - "$(cygpath -w "$DEST" 2>/dev/null || echo "$DEST")" "$C3_SELFTEST_LIVE" "$HOME" "$(whoami)" <<'PYEOF'
import pathlib, re, sys
dest, live, home, user = sys.argv[1:5]
def any_sep(path):
    parts = [re.escape(p) for p in re.split(r"[\\/]+", path.strip("\\/")) if p]
    return r"[\\/]+".join(parts)
home_w = home if ":" in home else re.sub(r"^/([a-z])/", lambda m: m.group(1) + ":/", home)
patterns = [re.compile(any_sep(live), re.I), re.compile(any_sep(home_w), re.I),
            re.compile(rf"\b{re.escape(user)}\b", re.I)]
files = [p for p in pathlib.Path(dest).rglob("*") if p.is_file()]
hits = [str(p) for p in files
        if any(rx.search(p.read_text(encoding="utf-8", errors="replace")) for rx in patterns)]
print(f"{len(files)} files, {len(hits)} with a live path, home path or user name {hits[:3]}")
raise SystemExit(1 if hits or not files else 0)
PYEOF
then
  echo "ok   collect_redacted: no live paths, home path or user name"
else
  echo "FAIL collect_redacted left a live path, home path or user name"; fail=1
fi
echo "selftest root: $ROOT"
[ $fail -eq 0 ] && echo "SELFTEST OK (not live evidence)" || echo "SELFTEST FAILED"
exit $fail
