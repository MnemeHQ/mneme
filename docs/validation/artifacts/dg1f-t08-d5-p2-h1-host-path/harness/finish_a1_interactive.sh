#!/usr/bin/env bash
# H1c Amendment A1, INTERACTIVE arm completion (probe scope 4.2).
# usage: finish_a1_interactive.sh <arm> <recording_path>
# Records the recording's SHA-256 and size (the recording itself stays local),
# copies the session transcript named by the hook envelope, snapshots the
# workspace, and validates observation.json. After both interactive arms are
# finished, run: classify_a1.py interactive <live> <pin_version> <pin_model>, then
# classify_a1.py combine <live>.
set -u
set -o pipefail
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins_a1.env"
ARM=${1:-}; REC=${2:-}
case "$ARM" in H1c-sm-int|H1c-sm-int-ctl) ;; *) echo "ABORT: arm must be H1c-sm-int or H1c-sm-int-ctl"; exit 1 ;; esac
OUT="$LIVE/$ARM/out"; WS="$LIVE/$ARM/ws"
[ -d "$OUT" ] || { echo "ABORT: $ARM was not prepared"; exit 1; }
[ -n "$REC" ] && [ -f "$REC" ] || { echo "ABORT: recording file not found: $REC"; exit 1; }
die() { echo "HARNESS_FAILURE: $*" | tee -a "$OUT/harness_failure.txt"; exit 1; }
V=$(claude --version | tr -d '\r')
P0=$(sed -n 's/^claude_version=//p' "$OUT/observer.txt" | head -1)
[ "$V" = "$PIN_CLAUDE_VERSION" ] && [ "$P0" = "$PIN_CLAUDE_VERSION" ] || die "claude version changed or unpinned (prep '$P0', now '$V', pin '$PIN_CLAUDE_VERSION')"
h() { [ -f "$1" ] && sha256sum < "$1" | cut -d' ' -f1 || echo absent; }
{
  echo "recording_sha256=$(h "$REC")"
  echo "recording_bytes=$(wc -c < "$REC" | tr -d ' ')"
  echo "finished=$(date -u +%FT%TZ)"
  echo "notes_after=$(h "$WS/notes.txt")"
} >> "$OUT/observer.txt" || die "cannot extend observer.txt"
TP=$("$PY" -I -c "
import json,sys
tp=None
try:
    for l in open(sys.argv[1],encoding='utf-8'):
        tp = tp or (json.loads(l).get('envelope') or {}).get('transcript_path')
except FileNotFoundError: pass
print(tp or '')" "$(cygpath -w "$OUT/hook-log.jsonl")" | tr -d '\r')
if [ -n "$TP" ] && [ -f "$(cygpath -u "$TP")" ]; then
  cp "$(cygpath -u "$TP")" "$OUT/transcript.jsonl" || die "cannot copy transcript"
  echo "transcript_collected=yes" >> "$OUT/observer.txt"
else
  echo "transcript_collected=no" >> "$OUT/observer.txt"
fi
"$PY" -I -c "
import json,sys
o=json.load(open(sys.argv[1],encoding='utf-8'))
bad=[k for k in ('notice_visible','returned_to_input_prompt','unexpected_prompt') if not isinstance(o.get(k),bool)]
if bad: sys.exit('observation.json: fill in booleans: '+', '.join(bad))
print('observation.json ok')" "$(cygpath -w "$OUT/observation.json")" || die "observation.json incomplete"
# Evidence-review template (review of #556): pre-filled with this arm's recording and
# frame hashes; a reviewer other than the classifier must fill in shows_nonce per frame,
# notice_visible and reviewer, from the RECORDING, and save it as capture_review.json.
"$PY" -I - "$(cygpath -w "$OUT")" <<'PYEOF' || die "cannot write capture review template"
import hashlib, json, os, sys
out = sys.argv[1]
obs = {}
for line in open(os.path.join(out, "observer.txt"), encoding="utf-8"):
    if "=" in line:
        k, v = line.rstrip("\n").split("=", 1)
        obs.setdefault(k, v)
o = json.load(open(os.path.join(out, "observation.json"), encoding="utf-8"))
frames = []
for f in o.get("frames") or []:
    p = os.path.join(out, f.get("file", ""))
    if os.path.isfile(p):
        frames.append({"file": f["file"], "t": f.get("t"),
                       "sha256": hashlib.sha256(open(p, "rb").read()).hexdigest(), "shows_nonce": None})
json.dump({"_instructions": "Review the recording and each frame; set shows_nonce per frame and notice_visible, name the reviewer, then save as capture_review.json.",
           "reviewer": "", "recording_sha256": obs.get("recording_sha256"), "notice_visible": None,
           "frames": frames}, open(os.path.join(out, "capture_review.template.json"), "w", encoding="utf-8"), indent=2)
PYEOF
echo "Finished $ARM. Capture review template: $(cygpath -w "$OUT/capture_review.template.json")"
