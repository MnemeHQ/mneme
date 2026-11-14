#!/usr/bin/env bash
# H1c Amendment A1, INTERACTIVE arm completion (probe scope 4.2).
# usage: finish_a1_interactive.sh [A3] <arm> <recording_path>
# Records the recording's SHA-256 and size (the recording itself stays local),
# copies the session transcript named by the hook envelope, snapshots the
# workspace, and validates observation.json. After both interactive arms are
# finished, run: classify_a1.py interactive <live> <pin_version> <pin_model>, then
# classify_a1.py combine <live> (the exact commands are printed at the end).
set -u
set -o pipefail
BASE=$(cd "$(dirname "$0")" && pwd)
# The pin set comes only from an optional first argument "A3" (Amendment A3, probe
# scope 4.4); an A1_PINSET already in the environment is refused, never overwritten.
[ -z "${A1_PINSET+set}" ] || { echo "ABORT: A1_PINSET is set in the environment; unset it and pass A3 as the first argument"; exit 1; }
if [ "${1:-}" = A3 ]; then export A1_PINSET=A3; shift; fi
. "$BASE/pins_a1.env"
# Kept evidence is never touched: refuse a finished batch before anything is written.
. "$BASE/guard_finished.sh"
refuse_finished_batch "$LIVE" outcome_a1_interactive.json outcome_a1.json
ARM=${1:-}; REC=${2:-}
case "$ARM" in H1c-sm-int|H1c-sm-int-ctl) ;; *) echo "ABORT: arm must be H1c-sm-int or H1c-sm-int-ctl"; exit 1 ;; esac
refuse_finished_arm "$LIVE/$ARM"
if [ "${A1_PINSET:-}" = A3 ] && [ "${DISABLE_AUTOUPDATER:-}" != 1 ]; then
  echo "ABORT: pin set A3 needs DISABLE_AUTOUPDATER=1 in this shell"; exit 1
fi
OUT="$LIVE/$ARM/out"; WS="$LIVE/$ARM/ws"
[ -d "$OUT" ] || { echo "ABORT: $ARM was not prepared"; exit 1; }
# The arm must have been prepared under the same pin set.
PS0=$(sed -n 's/^pinset=//p' "$OUT/observer.txt" | head -1)
[ "${PS0:-A1}" = "${A1_PINSET:-A1}" ] || { echo "ABORT: $ARM was prepared under pin set '${PS0:-A1}', not '${A1_PINSET:-A1}'"; exit 1; }
[ -n "$REC" ] && [ -f "$REC" ] || { echo "ABORT: recording file not found: $REC"; exit 1; }
# The pin checks refuse WITHOUT writing into the arm (Amendment A3): a finish run
# against the wrong root or an older arm must leave that arm's files untouched.
V=$(claude --version | tr -d '\r')
P0=$(sed -n 's/^claude_version=//p' "$OUT/observer.txt" | head -1)
[ "$V" = "$PIN_CLAUDE_VERSION" ] && [ "$P0" = "$PIN_CLAUDE_VERSION" ] \
  || { echo "ABORT: claude version changed or unpinned (prep '$P0', now '$V', pin '$PIN_CLAUDE_VERSION'); nothing written"; exit 1; }
# observation.json is validated BEFORE anything is written: the recording hash marks
# the arm finished (refuse_finished_arm), so an incomplete observation must leave the
# arm unfinished and finish re-runnable once it is filled in.
"$PY" -I -c "
import json,sys
o=json.load(open(sys.argv[1],encoding='utf-8'))
bad=[k for k in ('notice_visible','returned_to_input_prompt','unexpected_prompt') if not isinstance(o.get(k),bool)]
if bad: sys.exit('observation.json: fill in booleans: '+', '.join(bad))
print('observation.json ok')" "$(cygpath -w "$OUT/observation.json")" \
  || { echo "ABORT: observation.json incomplete; fill it in and run finish again (nothing written)"; exit 1; }
die() { echo "HARNESS_FAILURE: $*" | tee -a "$OUT/harness_failure.txt"; exit 1; }
h() { [ -f "$1" ] && sha256sum < "$1" | cut -d' ' -f1 || echo absent; }
# The recording hash in observer.txt marks the arm FINISHED (refuse_finished_arm), so
# it is written LAST, in one append, only after the transcript copy and the capture
# review template have succeeded (review of #803). Any earlier failure leaves the arm
# unfinished, and finish can be re-run once the cause is fixed.
REC_SHA=$(h "$REC")
REC_BYTES=$(wc -c < "$REC" | tr -d ' ') || die "cannot size the recording"
NOTES_AFTER=$(h "$WS/notes.txt")
TP=$("$PY" -I -c "
import json,sys
tp=None
try:
    for l in open(sys.argv[1],encoding='utf-8'):
        tp = tp or (json.loads(l).get('envelope') or {}).get('transcript_path')
except FileNotFoundError: pass
print(tp or '')" "$(cygpath -w "$OUT/hook-log.jsonl")" | tr -d '\r') || die "cannot read hook-log.jsonl"
if [ -n "$TP" ] && [ -f "$(cygpath -u "$TP")" ]; then
  cp "$(cygpath -u "$TP")" "$OUT/transcript.jsonl" || die "cannot copy transcript"
  TC=yes
else
  TC=no
fi
# Evidence-review template (review of #556): pre-filled with this arm's recording and
# frame hashes; a reviewer other than the classifier must fill in shows_nonce per frame,
# notice_visible and reviewer, from the RECORDING, and save it as capture_review.json.
# The recording hash is passed in (not read back from observer.txt), and the template
# is written atomically (temporary file, then replace).
"$PY" -I - "$(cygpath -w "$OUT")" "$REC_SHA" <<'PYEOF' || die "cannot write capture review template"
import hashlib, json, os, sys
out, rec_sha = sys.argv[1], sys.argv[2]
o = json.load(open(os.path.join(out, "observation.json"), encoding="utf-8"))
frames = []
for f in o.get("frames") or []:
    p = os.path.join(out, f.get("file", ""))
    if os.path.isfile(p):
        frames.append({"file": f["file"], "t": f.get("t"),
                       "sha256": hashlib.sha256(open(p, "rb").read()).hexdigest(), "shows_nonce": None})
tmp = os.path.join(out, "capture_review.template.json.tmp")
json.dump({"_instructions": "Review the recording and each frame; set shows_nonce per frame and notice_visible, name the reviewer, then save as capture_review.json.",
           "reviewer": "", "recording_sha256": rec_sha, "notice_visible": None,
           "frames": frames}, open(tmp, "w", encoding="utf-8"), indent=2)
os.replace(tmp, os.path.join(out, "capture_review.template.json"))
PYEOF
{
  echo "recording_sha256=$REC_SHA"
  echo "recording_bytes=$REC_BYTES"
  echo "finished=$(date -u +%FT%TZ)"
  echo "notes_after=$NOTES_AFTER"
  echo "transcript_collected=$TC"
} >> "$OUT/observer.txt" || die "cannot extend observer.txt"
echo "Finished $ARM. Capture review template: $(cygpath -w "$OUT/capture_review.template.json")"
echo "After both arms are finished and both capture reviews are saved, classify with the active pins:"
echo "  \"$PY\" -I \"$(cygpath -w "$BASE/classify_a1.py")\" interactive \"$(cygpath -w "$LIVE")\" \"$PIN_CLAUDE_VERSION\" \"$PIN_MODEL\""
echo "  \"$PY\" -I \"$(cygpath -w "$BASE/classify_a1.py")\" combine \"$(cygpath -w "$LIVE")\""
