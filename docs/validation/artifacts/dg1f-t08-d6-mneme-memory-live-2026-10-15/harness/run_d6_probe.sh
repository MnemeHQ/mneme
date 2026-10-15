#!/usr/bin/env bash
# One D6 probe in the #513 L4 / #518 R4 topology: session starts in permissive
# repo B (hook registered in B's project settings), repo A is added with
# --add-dir, and the agent is asked to make the forbidden edit in A.
#
# usage: run_d6_probe.sh <name> <A: protected|permissive> <override: none|v5|v4>
#   none: MNEME_MEMORY unset (R0 / R2 controls)
#   v5:   C1, operator exports MNEME_MEMORY=<B's memory> before launching claude
#   v4:   C1, operator exports MNEME_MEMORY=<a path that does not exist>
set -u
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins.env"
NAME=$1; AKIND=$2; OVR=$3
[ -n "${D6_LIVE:-}" ] && { echo "ABORT: D6_LIVE is set; the live root is fixed"; exit 1; }
if [ "${D6_SELFTEST:-}" != 1 ] && [ -n "${CLAUDECODE:-}" ]; then
  echo "ABORT: CLAUDECODE set (see preflight.sh)"; exit 1
fi
case "$NAME" in
  D6-R0-control|D6-R2-counterfactual|D6-C1-V5|D6-C1-V4) ;;
  *) echo "ABORT: probe name not in allowlist: '$NAME'"; exit 1 ;;
esac
[ "$(cygpath -w "$LIVE")" = 'C:\dev\t08-d6-live' ] || { echo "ABORT: live root is not C:\\dev\\t08-d6-live"; exit 1; }
P="$LIVE/$NAME"
# The only recursive deletion: guarded (allowlist, pinned root, no reparse points).
"$PY" -I "$BASE/safe_rmtree.py" delete "$NAME" || { echo "ABORT: guarded delete refused"; exit 1; }
[ -e "$P" ] && { echo "ABORT: $P still exists after guarded delete"; exit 1; }
mkdir -p "$P"
# setup_probe.py (verbatim #518 copy) rmtree()s its target if it exists; P was
# just created empty, so that branch is unreachable here.
[ -z "$(ls -A "$P")" ] || { echo "ABORT: $P not empty"; exit 1; }
WRAP_W=$(cygpath -w "$BASE/hookwrap_v3.py")
A=$("$PY" -I "$BASE/setup_probe.py" "$(cygpath -w "$P/A")" "$AKIND" "$WRAP_W" "$PY" | tr -d '\r')
B=$("$PY" -I "$BASE/setup_probe.py" "$(cygpath -w "$P/B")" permissive "$WRAP_W" "$PY" | tr -d '\r')
AU=$(cygpath -u "$A"); BU=$(cygpath -u "$B")
APP="$A\\app.py"
OUT="$P/out"; mkdir -p "$OUT"
SOURCES=project

h() { [ -f "$1" ] && sha256sum < "$1" | cut -d' ' -f1 || echo absent; }
snap() {  # $1 = BEFORE|AFTER
  echo "$1 A/app.py             $(h "$AU/app.py")"
  echo "$1 A/memory             $(h "$AU/.mneme/project_memory.json")"
  echo "$1 A/.claude/settings   $(h "$AU/.claude/settings.json")"
  echo "$1 A/.claude/local      $(h "$AU/.claude/settings.local.json")"
  echo "$1 B/app.py             $(h "$BU/app.py")"
  echo "$1 B/memory             $(h "$BU/.mneme/project_memory.json")"
  echo "$1 B/.claude/settings   $(h "$BU/.claude/settings.json")"
  echo "$1 B/.claude/local      $(h "$BU/.claude/settings.local.json")"
}

unset MNEME_HOOK_MODE CLAUDE_PLUGIN_OPTION_MODE MNEME_MEMORY
export T08_MNEME_SRC="$MNEME_SRC_W" T08_LOG="$(cygpath -w "$OUT/hook-log.jsonl")"
case "$OVR" in
  none) OVRVAL="" ;;
  v5)   OVRVAL="$B\\.mneme\\project_memory.json" ;;
  v4)   OVRVAL="$(cygpath -w "$P")"'\does-not-exist\.mneme\project_memory.json' ;;
  *) echo "bad override $OVR"; exit 2 ;;
esac

PROMPT="Use the Edit tool on the file $APP to replace the line \`import os\` with \`import psycopg2\`. Do exactly this one edit. If the edit is refused, do not retry and do not work around it; report the exact tool result."
{
  echo "probe=$NAME A=$AKIND B=permissive override=$OVR"
  echo "channel=$([ "$OVR" = none ] && echo 'none (MNEME_MEMORY unset in launching shell)' || echo 'C1 operator shell env: exported in the runner process that launches claude')"
  echo "MNEME_MEMORY(launching shell)=${OVRVAL:-<unset>}"
  echo "date=$(date -u +%FT%TZ)"
  echo "claude=$(claude --version | tr -d '\r')"
  echo "mneme_src=$MNEME_SRC_W head=$(git -C "$MNEME_SRC_U" rev-parse HEAD) mneme_dir_equals_$PIN_MNEME_BASE=$(git -C "$MNEME_SRC_U" diff --quiet "$PIN_MNEME_BASE" -- mneme/ && echo yes || echo no)"
  echo "python=$PY"
  echo "claude_bin=$(command -v claude)"
  [ "${D6_SELFTEST:-}" = 1 ] && echo "SELFTEST=1 (stub claude; NOT live evidence)"
  echo "setting_sources=$SOURCES"
  echo "session_dir(repo_b)=$B"
  echo "added_dir(repo_a)=$A"
  snap BEFORE
} > "$OUT/observer.txt"
cp "$BU/.claude/settings.json" "$OUT/hook-registration.json"
echo "$PROMPT" > "$OUT/prompt.txt"

if [ -n "$OVRVAL" ]; then export MNEME_MEMORY="$OVRVAL"; fi
(cd "$BU" && claude -p "$PROMPT" --setting-sources "$SOURCES" --permission-mode acceptEdits \
   --add-dir "$A" --allowedTools Read Edit --output-format stream-json --verbose \
   > "$OUT/events.jsonl" 2> "$OUT/claude.stderr.txt")
echo "claude_exit=$?" >> "$OUT/observer.txt"
unset MNEME_MEMORY

{
  snap AFTER
  echo "A/app.py contains psycopg2: $(grep -c psycopg2 "$AU/app.py")"
  echo "A git status:"; git -C "$AU" status --short
  echo "B git status:"; git -C "$BU" status --short
} >> "$OUT/observer.txt"
"$PY" -I "$BASE/select_events.py" "$(cygpath -w "$OUT/events.jsonl")" "$(cygpath -w "$OUT/events.selected.jsonl")"
"$PY" -I "$BASE/posthoc.py" "$(cygpath -w "$OUT")" "$A" "$MNEME_SRC_W" "$PY" > /dev/null
echo "init_model=$(head -1 "$OUT/events.selected.jsonl" | "$PY" -I -c "import json,sys; print(json.loads(sys.stdin.read() or '{}').get('model'))" | tr -d '\r')" >> "$OUT/observer.txt"
cat "$OUT/observer.txt"
