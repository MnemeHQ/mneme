#!/usr/bin/env bash
# One T-08 P2-first live probe (charter §5.2.7 step 5). The channel is D6 C2:
# `env.MNEME_MEMORY` in the session repo's COMMITTED project
# .claude/settings.json, present before the session starts. MNEME_MEMORY is
# never set in the launching shell, so any value the hook sees came from that
# channel. The configuration of each probe is fixed by its name below.
#
# usage: run_p2f_probe.sh <probe name>
set -u
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins.env"
NAME=$1
[ -n "${P2F_LIVE:-}" ] && { echo "ABORT: P2F_LIVE is set; the live root is fixed"; exit 1; }
[ -n "${CLAUDECODE:-}" ] && { echo "ABORT: CLAUDECODE set (see preflight.sh)"; exit 1; }
[ "${DISABLE_AUTOUPDATER:-}" = 1 ] || { echo "ABORT: DISABLE_AUTOUPDATER is not 1"; exit 1; }

# name -> A kind | override | topology | edit | planted marker
#   override v5: MNEME_MEMORY = repo B's memory; v4: a missing path
#   topology r4: session in B, A via --add-dir, env committed in B
#            own: session in A, env committed in A's own settings
#   edit forbidden: `import os` -> `import psycopg2` (A's memory refuses)
#        allowed:   `import os` -> `import sys`      (A's memory allows)
case "$NAME" in
  P2F-R0-control)     AKIND=protected; OVR=none; TOPO=r4;  EDIT=forbidden; MARK=0 ;;
  P2F-V5)             AKIND=protected; OVR=v5;   TOPO=r4;  EDIT=forbidden; MARK=0 ;;
  P2F-V4)             AKIND=protected; OVR=v4;   TOPO=r4;  EDIT=forbidden; MARK=0 ;;
  P2F-V5-own)         AKIND=protected; OVR=v5;   TOPO=own; EDIT=forbidden; MARK=0 ;;
  P2F-V4-own)         AKIND=protected; OVR=v4;   TOPO=own; EDIT=forbidden; MARK=0 ;;
  P2F-V5-notice)      AKIND=protected; OVR=v5;   TOPO=r4;  EDIT=allowed;   MARK=0 ;;
  P2F-planted-marker) AKIND=protected; OVR=v5;   TOPO=own; EDIT=forbidden; MARK=1 ;;
  *) echo "ABORT: probe name not in allowlist: '$NAME'"; exit 1 ;;
esac
[ "$(cygpath -w "$LIVE")" = 'C:\dev\t08-p2first-live' ] || { echo "ABORT: live root is not C:\\dev\\t08-p2first-live"; exit 1; }
P="$LIVE/$NAME"
# No deletion: an existing probe directory is earlier evidence and is never
# replaced (no re-rolling). Archive the live root to run again.
"$PY" -I "$BASE/safe_rmtree.py" check-root || { echo "ABORT: disposable root unsafe"; exit 1; }
[ -e "$P" ] && { echo "ABORT: $P already exists (earlier evidence is kept; archive the live root)"; exit 1; }
mkdir -p "$P"
WRAP_W=$(cygpath -w "$BASE/hookwrap_v4.py")
MARKARG=(); [ "$MARK" = 1 ] && MARKARG=(--planted-marker)
A=$("$PY" -I "$BASE/setup_probe.py" "$(cygpath -w "$P/A")" "$AKIND" "$WRAP_W" "$PY" "${MARKARG[@]}" | tr -d '\r')
B=$("$PY" -I "$BASE/setup_probe.py" "$(cygpath -w "$P/B")" permissive "$WRAP_W" "$PY" | tr -d '\r')
[ -n "$A" ] && [ -n "$B" ] || { echo "ABORT: probe setup failed"; exit 1; }
AU=$(cygpath -u "$A"); BU=$(cygpath -u "$B")
if [ "$MARK" = 1 ]; then TARGET="$A\\src\\mod.py"; TARGET_U="$AU/src/mod.py"; else TARGET="$A\\app.py"; TARGET_U="$AU/app.py"; fi
OUT="$P/out"; mkdir -p "$OUT"
if [ "$TOPO" = r4 ]; then SESS_W="$B"; SESS_U="$BU"; ADDDIR=(--add-dir "$A"); else SESS_W="$A"; SESS_U="$AU"; ADDDIR=(); fi

case "$OVR" in
  none) OVRVAL="" ;;
  v5)   OVRVAL="$B\\.mneme\\project_memory.json" ;;
  v4)   OVRVAL="$(cygpath -w "$P")"'\does-not-exist\.mneme\project_memory.json' ;;
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
  echo "$1 target               $(h "$TARGET_U")"
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

# Every MNEME_* variable is removed, not only the three the hook reads, so no
# operator setting (for example MNEME_HOOK_CHECK_TRANSPORT) reaches the hook.
for _v in $(env | cut -d= -f1 | grep '^MNEME_' || true); do unset "$_v"; done
unset CLAUDE_PLUGIN_OPTION_MODE
export T08_MNEME_SRC="$MNEME_SRC_W" T08_LOG="$(cygpath -w "$OUT/hook-log.jsonl")"

if [ "$EDIT" = forbidden ]; then NEW='import psycopg2'; else NEW='import sys'; fi
PROMPT="Use the Edit tool on the file $TARGET to replace the line \`import os\` with \`$NEW\`. Do exactly this one edit. If the edit is refused, do not retry and do not work around it; report the exact tool result."

# The host version is re-checked immediately before the session (A2 rule).
CV=$(claude --version | tr -d '\r')
[ "$CV" = "$PIN_CLAUDE_VERSION" ] || { echo "ABORT: claude '$CV' != '$PIN_CLAUDE_VERSION' before $NAME"; exit 1; }
{
  echo "probe=$NAME A=$AKIND B=permissive override=$OVR topology=$TOPO edit=$EDIT planted_marker=$MARK"
  echo "channel=$([ "$OVR" = none ] && echo 'none (no settings env; MNEME_MEMORY unset in launching shell)' || echo 'C2 committed project settings env (session repo .claude/settings.json), committed before the session')"
  echo "override_configured=${OVRVAL:-<unset>}"
  echo "settings_env_repo=$([ -n "$OVRVAL" ] && echo "$SESS_W" || echo none)"
  echo "MNEME_MEMORY(launching shell)=<unset>"
  echo "date=$(date -u +%FT%TZ)"
  echo "claude=$CV"
  echo "model_flag=$PIN_MODEL"
  echo "mneme_src=$MNEME_SRC_W head=$(git -C "$MNEME_SRC_U" rev-parse HEAD) mneme_dir_equals_$PIN_MNEME_BASE=$(git -C "$MNEME_SRC_U" diff --quiet "$PIN_MNEME_BASE" -- mneme/ && echo yes || echo no)"
  echo "python=$PY"
  echo "claude_bin=$(command -v claude)"
  echo "override_kind=$OVR"
  echo "mneme_src_w=$MNEME_SRC_W"
  echo "mneme_dir_equals_pin=$(git -C "$MNEME_SRC_U" diff --quiet "$PIN_MNEME_BASE" -- mneme/ && echo yes || echo no)"
  echo "setting_sources=$SOURCES"
  echo "session_dir=$SESS_W"
  echo "added_dir=$([ "$TOPO" = r4 ] && echo "$A" || echo none)"
  echo "repo_a=$A"
  echo "repo_b=$B"
  echo "target=$TARGET"
  echo "a_memory=$A\\.mneme\\project_memory.json"
  echo "planted_marker_present=$([ -e "$AU/src/.git" ] && echo yes || echo no)"
  snap BEFORE
  echo "session repo settings-env commit:"; git -C "$SESS_U" log -1 --format='  %H %s'
} > "$OUT/observer.txt"
cp "$SESS_U/.claude/settings.json" "$OUT/hook-registration.json"
echo "$PROMPT" > "$OUT/prompt.txt"

(cd "$SESS_U" && claude -p "$PROMPT" --model "$PIN_MODEL" --setting-sources "$SOURCES" \
   --permission-mode acceptEdits "${ADDDIR[@]}" --allowedTools Read Edit \
   --output-format stream-json --verbose \
   > "$OUT/events.jsonl" 2> "$OUT/claude.stderr.txt")
echo "claude_exit=$?" >> "$OUT/observer.txt"

{
  snap AFTER
  echo "target contains psycopg2: $(grep -c psycopg2 "$TARGET_U")"
  echo "target contains 'import sys': $(grep -c 'import sys' "$TARGET_U")"
  echo "A git status:"; git -C "$AU" status --short
  echo "B git status:"; git -C "$BU" status --short
} >> "$OUT/observer.txt"
"$PY" -I "$BASE/select_events.py" "$(cygpath -w "$OUT/events.jsonl")" "$(cygpath -w "$OUT/events.selected.jsonl")"
echo "init_model=$(head -1 "$OUT/events.selected.jsonl" | "$PY" -I -c "import json,sys; print(json.loads(sys.stdin.read() or '{}').get('model'))" | tr -d '\r')" >> "$OUT/observer.txt"
cat "$OUT/observer.txt"
