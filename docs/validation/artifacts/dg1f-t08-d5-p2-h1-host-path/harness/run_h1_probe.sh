#!/usr/bin/env bash
# One H1 probe arm (accepted probe scope #545, sections 3, 3.1, 4 and 7).
#
# usage: run_h1_probe.sh <arm>
#   H1a-edit   | H1a-edit-ctl    PreToolUse (Edit matcher)    command hook, tool event
#   H1a-bash   | H1a-bash-ctl    PreToolUse (Bash matcher)    command hook, tool event
#   H1b-start  | H1b-start-ctl   SessionStart                 command hook, lifecycle event
#   H1c-stop   | H1c-stop-ctl    Stop                         command hook, lifecycle event
# The plain name is the emitter arm; "-ctl" is the paired no-op control.
#
# Steps: guarded delete of <LIVE>/<arm>; setup_probe.py (workspace, hook
# registration for the probed event only, fresh nonce); observer snapshot; one
# headless `claude -p` in the workspace (stream-json); after-snapshot; copy of the
# session transcript named by the hook envelope's transcript_path (or found by
# session_id). Classification is done per pair by run_h1.sh.
# Exit status (fail closed): 0 ran and evidence written; 1 harness failure,
# recorded in <out>/harness_failure.txt.
set -u
set -o pipefail
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins.env"
ARM=$1
case "$ARM" in
  H1a-edit|H1a-edit-ctl|H1a-bash|H1a-bash-ctl|H1b-start|H1b-start-ctl|H1c-stop|H1c-stop-ctl) ;;
  *) echo "ABORT: arm not in allowlist: '$ARM'"; exit 1 ;;
esac
[ -n "${H1_LIVE:-}" ] && { echo "ABORT: H1_LIVE is set; the live root is fixed"; exit 1; }
if [ "${H1_SELFTEST:-}" != 1 ] && [ -n "${CLAUDECODE:-}" ]; then
  echo "ABORT: CLAUDECODE set (see preflight.sh)"; exit 1
fi
[ "$(cygpath -w "$LIVE")" = 'C:\dev\d5p2-h1-live' ] || { echo "ABORT: live root is not C:\\dev\\d5p2-h1-live"; exit 1; }
# The stub may only ever answer a self-test, and a self-test may only ever reach the stub.
CB=$(command -v claude) || { echo "ABORT: claude not found"; exit 1; }
case "$CB" in
  "$BASE/selftest/"*) [ "${H1_SELFTEST:-}" = 1 ] || { echo "ABORT: claude resolves to the self-test stub ($CB) in a live run"; exit 1; } ;;
  *) [ "${H1_SELFTEST:-}" = 1 ] && { echo "ABORT: H1_SELFTEST=1 but claude is not the stub ($CB); refusing a live session"; exit 1; } ;;
esac
P="$LIVE/$ARM"
"$PY" -I "$BASE/safe_rmtree.py" delete "$ARM" || { echo "ABORT: guarded delete refused"; exit 1; }
[ -e "$P" ] && { echo "ABORT: $P still exists after guarded delete"; exit 1; }
mkdir -p "$P" || { echo "ABORT: cannot create $P"; exit 1; }
OUT="$P/out"; WS="$P/ws"
mkdir -p "$OUT" || { echo "ABORT: cannot create $OUT"; exit 1; }
die() { echo "HARNESS_FAILURE: $*" | tee -a "$OUT/harness_failure.txt"; exit 1; }

META=$("$PY" -I "$BASE/setup_probe.py" "$ARM" "$(cygpath -w "$P")" "$PY" "$(cygpath -w "$BASE/emitter.py")" | tr -d '\r') \
  || die "setup_probe.py failed"
field() { "$PY" -I -c "import json,sys; print(json.loads(sys.argv[1])[sys.argv[2]])" "$META" "$1" | tr -d '\r'; }
PROMPT=$(field prompt) || die "cannot read prompt"
TOOLS=$(field tools) || die "cannot read tools"
printf '%s\n' "$PROMPT" > "$OUT/prompt.txt" || die "cannot write prompt.txt"
cp "$WS/.claude/settings.json" "$OUT/hook-registration.json" || die "cannot copy hook registration"
grep -q "MNEME-PROBE-" "$OUT/prompt.txt" && ! grep -qF "$(cat "$OUT/nonce.txt")" "$OUT/prompt.txt" \
  || die "prompt check failed (must mention the MNEME-PROBE- prefix and never the nonce)"
h() { [ -f "$1" ] && sha256sum < "$1" | cut -d' ' -f1 || echo absent; }

{
  echo "arm=$ARM"
  [ "${H1_SELFTEST:-}" = 1 ] && echo "selftest=1 (stub claude; NOT live evidence)"
  echo "claude_version=$(claude --version | tr -d '\r')"
  echo "claude_bin=$CB"
  echo "harness_head=$(git -C "$BASE" rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "sources=$SOURCES"
  echo "tools=$TOOLS"
  echo "notes_before=$(h "$WS/notes.txt")"
  echo "bash_out_before=$(h "$WS/bash_out.txt")"
  echo "settings_sha=$(h "$WS/.claude/settings.json")"
  echo "date=$(date -u +%FT%TZ)"
} > "$OUT/observer.txt" || die "cannot write observer.txt"

# shellcheck disable=SC2086  # TOOLS is a space-separated list on purpose
( cd "$WS" && env -u MNEME_MEMORY -u MNEME_HOOK_MODE -u CLAUDE_PLUGIN_OPTION_MODE \
    claude -p "$PROMPT" --output-format stream-json --verbose \
      --permission-mode acceptEdits --allowedTools $TOOLS --setting-sources "$SOURCES" \
    > "$OUT/events.jsonl" 2> "$OUT/claude.stderr.txt" )
rc=$?
echo "claude_exit=$rc" >> "$OUT/observer.txt"
[ -s "$OUT/events.jsonl" ] || die "no stream-json events (claude exit $rc)"

{
  echo "notes_after=$(h "$WS/notes.txt")"
  echo "bash_out_after=$(h "$WS/bash_out.txt")"
} >> "$OUT/observer.txt" || die "cannot finish observer.txt"

# Session transcript: the path the host gave the hook, else the session id's file.
TP=$("$PY" -I - "$(cygpath -w "$OUT")" <<'PYEOF' | tr -d '\r'
import json, sys, glob, os
out = sys.argv[1]
tp = None
try:
    for line in open(os.path.join(out, "hook-log.jsonl"), encoding="utf-8"):
        tp = tp or (json.loads(line).get("envelope") or {}).get("transcript_path")
except FileNotFoundError:
    pass
if not tp:
    sid = None
    for line in open(os.path.join(out, "events.jsonl"), encoding="utf-8"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "system" and e.get("subtype") == "init":
            sid = e.get("session_id"); break
    home = os.environ.get("H1_STUB_HOME") or os.path.expanduser("~/.claude")
    hits = glob.glob(os.path.join(home, "projects", "*", f"{sid}.jsonl")) if sid else []
    tp = hits[0] if len(hits) == 1 else None
print(tp or "")
PYEOF
)
if [ -n "$TP" ] && [ -f "$(cygpath -u "$TP")" ]; then
  cp "$(cygpath -u "$TP")" "$OUT/transcript.jsonl" || die "cannot copy transcript"
  echo "transcript_collected=yes" >> "$OUT/observer.txt"
else
  echo "transcript_collected=no" >> "$OUT/observer.txt"
fi
cat "$OUT/observer.txt"
exit 0
