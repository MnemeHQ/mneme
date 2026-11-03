#!/usr/bin/env bash
# One C3 probe: one scope §5 row, one tool, one repetition.
#
# usage: run_c3_probe.sh <probe> <Write|Edit|MultiEdit> <rep> [--interactive]
#
# Headless (default): `claude -p ... --output-format stream-json`.
# --interactive (scope Q2, rows R-1 and P-2 only): prepares the probe, prints
# the exact command and prompt for the operator to run in their own terminal
# while recording the screen, waits for Enter, then collects the transcript.
#
# Evidence written to $LIVE/<probe>-<tool>-<rep>[-interactive]/out:
#   observer.txt (E1 before/after hashes, E7 pins), events.jsonl (E2),
#   transcript.jsonl (headless session transcript, C2b §17.5 delivery),
#   hook-log.jsonl (E3, E4 wrapper half), target.before / target.after,
#   outcome.json (classify_c3.py).
#
# Exit status: 0 the probe ran and outcome.json exists; 1 harness failure
# (<out>/harness_failure.txt says which). A failed probe is still exit 0.
set -u
set -o pipefail
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins.env"
PROBE=${1:-}; TOOL=${2:-}; REP=${3:-}; ARM=${4:-headless}
case "$ARM" in headless|--interactive) ;; *) echo "ABORT: unknown option $ARM"; exit 1;; esac
[ "$ARM" = --interactive ] && ARM=interactive
NAME="$PROBE-$TOOL-$REP"; [ "$ARM" = interactive ] && NAME="$NAME-interactive"

if [ "${C3_SELFTEST:-}" = 1 ]; then
  LIVE_ROOT="$C3_SELFTEST_LIVE"; URL="$C3_SELFTEST_REMOTE"
else
  [ -n "${C3_SELFTEST_LIVE:-}${C3_SELFTEST_REMOTE:-}${C3_SELFTEST_CLAUDE_HOME:-}" ] && { echo "ABORT: self-test variables set in a live run"; exit 1; }
  [ -n "${CLAUDECODE:-}" ] && { echo "ABORT: CLAUDECODE set; run from your own terminal"; exit 1; }
  LIVE_ROOT="$LIVE"; URL="$FIXTURE_URL"
fi
CB=$(command -v claude) || { echo "ABORT: claude not found"; exit 1; }
case "$CB" in
  "$BASE/selftest/"*) [ "${C3_SELFTEST:-}" = 1 ] || { echo "ABORT: claude is the self-test stub in a live run"; exit 1; } ;;
  *) [ "${C3_SELFTEST:-}" = 1 ] && { echo "ABORT: C3_SELFTEST=1 but claude is not the stub ($CB)"; exit 1; } ;;
esac

# Row facts from the matrix (also validates probe and tool).
SPEC=$("$PY" -E -P -c "
import json, sys
sys.path.insert(0, sys.argv[1]); import matrix
r = matrix.row(sys.argv[2])
if sys.argv[3] not in r['tools']: raise SystemExit('tool not allowed for this probe')
if sys.argv[4] == 'interactive' and sys.argv[2] not in matrix.INTERACTIVE_ROWS: raise SystemExit('no interactive arm for this probe')
print(json.dumps({'phase': r['phase'], 'needs': r['needs']}))" "$(cygpath -w "$BASE")" "$PROBE" "$TOOL" "$ARM" | tr -d '\r') \
  || { echo "ABORT: $PROBE/$TOOL/$ARM rejected by the matrix"; exit 1; }
PHASE=$(echo "$SPEC" | "$PY" -E -P -c "import json,sys; print(json.load(sys.stdin)['phase'] or '')" | tr -d '\r')
NEEDS=$(echo "$SPEC" | "$PY" -E -P -c "import json,sys; print(' '.join(json.load(sys.stdin)['needs']))" | tr -d '\r')

G="$LIVE_ROOT/_golden"
[ -s "$LIVE_ROOT/_golden.json" ] || { echo "ABORT: run refresh_golden.sh first"; exit 1; }
GPHASE=$("$PY" -E -P -c "import json,sys; print(json.load(open(sys.argv[1]))['phase'])" "$(cygpath -w "$LIVE_ROOT/_golden.json")" | tr -d '\r')
if [ -n "$PHASE" ] && [ "$PHASE" != "$GPHASE" ]; then
  echo "ABORT: $PROBE needs fixture phase $PHASE; golden is $GPHASE"; exit 1
fi

if echo " $NEEDS " | grep -q " network_blocked "; then
  # The operator blocks the forge for Git only (README, batch U). Confirm that an
  # anonymous ls-remote now fails, with a clean Git environment.
  if env -i PATH="$PATH" SYSTEMROOT="${SYSTEMROOT:-}" HOME="$LIVE_ROOT" GIT_CONFIG_NOSYSTEM=1 \
       GIT_TERMINAL_PROMPT=0 timeout 30 git -c credential.helper= ls-remote "$URL" HEAD >/dev/null 2>&1; then
    echo "ABORT: $PROBE needs the forge blocked for Git, but ls-remote succeeded"; exit 1
  fi
fi

P="$LIVE_ROOT/$NAME"
"$PY" -E -P "$BASE/safe_rmtree.py" delete "$NAME" || { echo "ABORT: guarded delete refused"; exit 1; }
mkdir -p "$P/out" || { echo "ABORT: cannot create $P"; exit 1; }
OUT="$P/out"
die() { echo "HARNESS_FAILURE: $*" | tee -a "$OUT/harness_failure.txt"; exit 1; }
w() { cygpath -w "$1" 2>/dev/null || echo "$1"; }

SETUP=$("$PY" -E -P "$BASE/setup_c3_probe.py" "$PROBE" "$TOOL" "$REP" "$(w "$P")" "$(w "$G")" "$URL" \
        "$PY" "$(w "$BASE/hookwrap_c3.py")" "$MNEME_SRC_W" | tr -d '\r') || die "setup_c3_probe.py failed"
jget() { "$PY" -E -P -c "import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8')); print(eval(sys.argv[2], {}, {'d': d}))" "$SETUP" "$1" | tr -d '\r'; }
REPO=$(cygpath -u "$(jget "d['repo']")"); TARGET=$(cygpath -u "$(jget "d['target']")")
PROMPT=$(jget "d['prompt']")
printf '%s\n' "$PROMPT" > "$OUT/prompt.txt" || die "cannot write prompt"
cp "$SETUP" "$OUT/setup.json" && cp "$REPO/.claude/settings.json" "$OUT/hook-registration.json" \
  || die "cannot copy setup"

h() { [ -f "$1" ] && sha256sum < "$1" | cut -d' ' -f1 || echo absent; }
USER_SETTINGS="$HOME/.claude/settings.json"; USER_LOCAL="$HOME/.claude/settings.local.json"
MANAGED="/c/ProgramData/ClaudeCode/managed-settings.json"
snap() {
  echo "$1 target               $(h "$TARGET")"
  echo "$1 app.py               $(h "$REPO/app.py")"
  echo "$1 memory               $(h "$REPO/.mneme/project_memory.json")"
  echo "$1 declaration          $(h "$REPO/.mneme/availability.json")"
  echo "$1 project_settings     $(h "$REPO/.claude/settings.json")"
  echo "$1 project_local        $(h "$REPO/.claude/settings.local.json")"
  echo "$1 user_settings        $(h "$USER_SETTINGS")"
  echo "$1 user_local           $(h "$USER_LOCAL")"
  echo "$1 managed_settings     $(h "$MANAGED")"
}
[ -f "$TARGET" ] && cp "$TARGET" "$OUT/target.before"

LAUNCH_ID=$("$PY" -E -P -c "import uuid; print(uuid.uuid4())" | tr -d '\r')
unset MNEME_MEMORY MNEME_HOOK_MODE CLAUDE_PLUGIN_OPTION_MODE MNEME_HOOK_CHECK_TRANSPORT \
      C3_STALL_CHECK_SECONDS C3_STALL_HOOK_SECONDS
export C3_MNEME_SRC="$MNEME_SRC_W" C3_LOG="$(w "$OUT")\\hook-log.jsonl" C3_LAUNCH_ID="$LAUNCH_ID"
# Per-row operator environment (R-6 MNEME_MEMORY, R-7 / H-2 stalls).
eval "$("$PY" -E -P -c "
import json, shlex, sys
for k, v in json.load(open(sys.argv[1], encoding='utf-8'))['env'].items():
    print(f'export {k}={shlex.quote(v)}')" "$SETUP" | tr -d '\r')" || die "cannot export row env"

{
  echo "probe=$PROBE tool=$TOOL rep=$REP arm=$ARM"
  echo "launch_id=$LAUNCH_ID"
  echo "date=$(date -u +%FT%TZ)"
  [ "${C3_SELFTEST:-}" = 1 ] && echo "SELFTEST=1 (stub claude, local remote; NOT live evidence)"
  echo "fixture=$URL golden_phase=$GPHASE golden=$(cat "$LIVE_ROOT/_golden.json")"
  echo "claude=$(claude --version | tr -d '\r') claude_bin=$CB model_pin=$PIN_MODEL"
  echo "mneme_src=$MNEME_SRC_W head=$(git -C "$MNEME_SRC_U" rev-parse HEAD) mneme_dir_equals_pin=$(git -C "$MNEME_SRC_U" diff --quiet "$PIN_MNEME_BASE" -- mneme/ && echo yes || echo no)"
  echo "harness_head=$(git -C "$BASE" rev-parse HEAD) harness_dirty=$([ -z "$(git -C "$BASE" status --porcelain -- .)" ] && echo no || echo yes)"
  echo "git=$(git --version) os=$(uname -sr)"
  echo "setting_sources=$SOURCES row_env_keys=$(env | cut -d= -f1 | grep -E '^(MNEME_MEMORY|C3_STALL_)' | tr '\n' ' ')"
  echo "network_blocked_required=$(echo " $NEEDS " | grep -q ' network_blocked ' && echo yes || echo no)"
  snap BEFORE
} > "$OUT/observer.txt" || die "cannot write observer.txt"

if [ "$ARM" = headless ]; then
  # stdin closed: `claude -p` treats piped stdin as extra input and waits on a
  # console stdin, so the prompt argument must be its only input.
  (cd "$REPO" && claude -p "$PROMPT" --output-format stream-json --verbose \
     --permission-mode acceptEdits --setting-sources "$SOURCES" --model "$PIN_MODEL") \
     < /dev/null > "$OUT/events.jsonl" 2> "$OUT/claude.stderr"
  echo "claude_exit=$?" >> "$OUT/observer.txt"
  # C2b §17.5: the session transcript is the only model-bound record of a hook's
  # additionalContext. A missing transcript is missing evidence, not a harness failure.
  if "$PY" -E -P "$BASE/collect_transcript.py" --headless "$(w "$OUT")" > /dev/null 2> "$OUT/transcript-collect.stderr"; then
    echo "transcript_collected=yes" >> "$OUT/observer.txt"
  else
    echo "transcript_collected=no" >> "$OUT/observer.txt"
  fi
else
  START=$(date +%s)
  cat <<EOF

=== Interactive arm for $NAME (scope Q2) ===
1. Start your screen recording now.
2. In a NEW Git Bash terminal (not inside Claude Code), run exactly:
     cd '$REPO'
     unset MNEME_MEMORY MNEME_HOOK_MODE CLAUDE_PLUGIN_OPTION_MODE
     export C3_MNEME_SRC='$C3_MNEME_SRC' C3_LOG='$C3_LOG' C3_LAUNCH_ID='$C3_LAUNCH_ID'
     claude --permission-mode acceptEdits --setting-sources $SOURCES --model $PIN_MODEL
3. Paste this prompt, wait for the reply, then exit Claude Code:
-----
$PROMPT
-----
4. Stop the recording and save it as: $(w "$OUT")\\recording.<ext>
5. Write what Claude Code showed you, word for word if possible, in:
     $(w "$OUT")\\operator-attestation.txt
Press Enter here when all five steps are done.
EOF
  read -r _
  echo "interactive_window_start=$START end=$(date +%s)" >> "$OUT/observer.txt"
  "$PY" -E -P "$BASE/collect_transcript.py" "$(w "$REPO")" "$START" "$(w "$OUT")" \
    || die "transcript not found for $REPO"
fi

snap AFTER >> "$OUT/observer.txt" || die "cannot record AFTER hashes"
[ -f "$TARGET" ] && cp "$TARGET" "$OUT/target.after"
"$PY" -E -P "$BASE/classify_c3.py" "$(w "$OUT")" "$PIN_MODEL" > /dev/null || die "classify_c3.py failed"
[ -s "$OUT/outcome.json" ] || die "no outcome.json"
"$PY" -E -P -c "import json,sys; o=json.load(open(sys.argv[1])); print(o['probe'], o['tool'], o['rep'], o['arm'], o['label'])" "$(w "$OUT/outcome.json")"
