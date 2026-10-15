#!/usr/bin/env bash
# One D6 batch-2 probe: channel C2 = `env.MNEME_MEMORY` in the session repo's
# COMMITTED project .claude/settings.json, present before the session starts.
# MNEME_MEMORY is never set in the launching shell, so any value the hook sees
# came from the settings channel. Settings sources: project,local (#519 §4).
#
# usage: run_d6_c2_probe.sh <name> <A: protected|permissive> <override: none|v5|v4> <topology: r4|own>
#   r4:  session starts in permissive repo B; protected repo A via --add-dir;
#        the env is committed in B's settings (sibling config redirects A).
#   own: session starts in repo A itself; the env is committed in A's own
#        settings (a repo's committed config redirects its own governance).
#   v5:  MNEME_MEMORY = repo B's memory     v4: MNEME_MEMORY = a missing path
set -u
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins.env"
NAME=$1; AKIND=$2; OVR=$3; TOPO=$4
[ -n "${D6_LIVE:-}" ] && { echo "ABORT: D6_LIVE is set; the live root is fixed"; exit 1; }
if [ "${D6_SELFTEST:-}" != 1 ] && [ -n "${CLAUDECODE:-}" ]; then
  echo "ABORT: CLAUDECODE set (see preflight.sh)"; exit 1
fi
case "$NAME" in
  D6-C2-R0-control|D6-C2-R2-counterfactual|D6-C2-V5|D6-C2-V4|D6-C2-V5-own|D6-C2-V4-own) ;;
  *) echo "ABORT: probe name not in allowlist: '$NAME'"; exit 1 ;;
esac
case "$TOPO" in r4|own) ;; *) echo "ABORT: bad topology '$TOPO'"; exit 1 ;; esac
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
if [ "$TOPO" = r4 ]; then SESS_W="$B"; SESS_U="$BU"; ADDDIR=(--add-dir "$A"); else SESS_W="$A"; SESS_U="$AU"; ADDDIR=(); fi

case "$OVR" in
  none) OVRVAL="" ;;
  v5)   OVRVAL="$B\\.mneme\\project_memory.json" ;;
  v4)   OVRVAL="$(cygpath -w "$P")"'\does-not-exist\.mneme\project_memory.json' ;;
  *) echo "bad override $OVR"; exit 2 ;;
esac

# Channel C2: commit env.MNEME_MEMORY into the session repo's project settings.
if [ -n "$OVRVAL" ]; then
  "$PY" -I -c "import json,sys; p=sys.argv[1]; s=json.load(open(p,encoding='utf-8')); s['env']={'MNEME_MEMORY': sys.argv[2]}; open(p,'w',encoding='utf-8').write(json.dumps(s, indent=2))" \
    "$(cygpath -w "$SESS_U/.claude/settings.json")" "$OVRVAL"
  git -C "$SESS_U" add .claude/settings.json
  git -C "$SESS_U" -c user.email=t@t -c user.name=t commit -q -m "configure MNEME_MEMORY in project settings env"
fi

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
  echo "$1 A/HEAD               $(git -C "$AU" rev-parse HEAD)"
  echo "$1 B/HEAD               $(git -C "$BU" rev-parse HEAD)"
}

unset MNEME_HOOK_MODE CLAUDE_PLUGIN_OPTION_MODE MNEME_MEMORY
export T08_MNEME_SRC="$MNEME_SRC_W" T08_LOG="$(cygpath -w "$OUT/hook-log.jsonl")"

PROMPT="Use the Edit tool on the file $APP to replace the line \`import os\` with \`import psycopg2\`. Do exactly this one edit. If the edit is refused, do not retry and do not work around it; report the exact tool result."
{
  echo "probe=$NAME A=$AKIND B=permissive override=$OVR topology=$TOPO"
  echo "channel=$([ "$OVR" = none ] && echo 'none (no settings env; MNEME_MEMORY unset in launching shell)' || echo 'C2 committed project settings env (session repo .claude/settings.json), committed before the session')"
  echo "override_configured=${OVRVAL:-<unset>}"
  echo "settings_env_repo=$([ -n "$OVRVAL" ] && echo "$SESS_W" || echo none)"
  echo "MNEME_MEMORY(launching shell)=<unset>"
  echo "date=$(date -u +%FT%TZ)"
  echo "claude=$(claude --version | tr -d '\r')"
  echo "mneme_src=$MNEME_SRC_W head=$(git -C "$MNEME_SRC_U" rev-parse HEAD) mneme_dir_equals_$PIN_MNEME_BASE=$(git -C "$MNEME_SRC_U" diff --quiet "$PIN_MNEME_BASE" -- mneme/ && echo yes || echo no)"
  echo "python=$PY"
  echo "claude_bin=$(command -v claude)"
  [ "${D6_SELFTEST:-}" = 1 ] && echo "SELFTEST=1 (stub claude; NOT live evidence)"
  echo "setting_sources=$SOURCES"
  echo "session_dir=$SESS_W"
  echo "added_dir=$([ "$TOPO" = r4 ] && echo "$A" || echo none)"
  echo "repo_a=$A"
  echo "repo_b=$B"
  snap BEFORE
  echo "session repo settings-env commit:"; git -C "$SESS_U" log -1 --format='  %H %s'
} > "$OUT/observer.txt"
cp "$SESS_U/.claude/settings.json" "$OUT/hook-registration.json"
echo "$PROMPT" > "$OUT/prompt.txt"

(cd "$SESS_U" && claude -p "$PROMPT" --setting-sources "$SOURCES" --permission-mode acceptEdits \
   "${ADDDIR[@]}" --allowedTools Read Edit --output-format stream-json --verbose \
   > "$OUT/events.jsonl" 2> "$OUT/claude.stderr.txt")
echo "claude_exit=$?" >> "$OUT/observer.txt"

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
