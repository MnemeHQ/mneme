#!/usr/bin/env bash
# H1c Amendment A1, INTERACTIVE arm preparation (probe scope 4.2).
# usage: prep_a1_interactive.sh H1c-sm-int-ctl | H1c-sm-int
# Builds the arm's disposable workspace (guarded delete, setup_probe.py, fresh
# nonce, Stop hook registration), writes observer.txt and an observation template,
# and prints the operator's steps. It does NOT start Claude Code: the operator
# launches interactive `claude` in the workspace, records the screen, and then runs
# finish_a1_interactive.sh. Run the control arm first.
set -u
set -o pipefail
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins_a1.env"
ARM=${1:-}
case "$ARM" in H1c-sm-int|H1c-sm-int-ctl) ;; *) echo "ABORT: arm must be H1c-sm-int or H1c-sm-int-ctl"; exit 1 ;; esac
[ -n "${H1_LIVE:-}" ] && { echo "ABORT: H1_LIVE is set; the live root is fixed"; exit 1; }
if [ "${H1_SELFTEST:-}" != 1 ] && [ -n "${CLAUDECODE:-}" ]; then echo "ABORT: CLAUDECODE set (run from your own terminal)"; exit 1; fi
[ "$(cygpath -w "$LIVE")" = 'C:\dev\d5p2-h1c-a1-live' ] || { echo "ABORT: live root is not C:\\dev\\d5p2-h1c-a1-live"; exit 1; }
"$PY" -I "$BASE/safe_rmtree_a1.py" check-root || { echo "ABORT: disposable root unsafe"; exit 1; }
mkdir -p "$LIVE" || exit 1
P="$LIVE/$ARM"
"$PY" -I "$BASE/safe_rmtree_a1.py" delete "$ARM" || { echo "ABORT: guarded delete refused"; exit 1; }
mkdir -p "$P/out" || exit 1
OUT="$P/out"; WS="$P/ws"
die() { echo "HARNESS_FAILURE: $*" | tee -a "$OUT/harness_failure.txt"; exit 1; }
META=$("$PY" -I "$BASE/setup_probe.py" "$ARM" "$(cygpath -w "$P")" "$PY" "$(cygpath -w "$BASE/emitter.py")" | tr -d '\r') || die "setup failed"
"$PY" -I -c "import json,sys; print(json.loads(sys.argv[1])['prompt'])" "$META" > "$OUT/prompt.txt" || die "cannot write prompt"
cp "$WS/.claude/settings.json" "$OUT/hook-registration.json" || die "cannot copy registration"
grep -qF "$(cat "$OUT/nonce.txt")" "$OUT/prompt.txt" && die "prompt contains the nonce"
h() { [ -f "$1" ] && sha256sum < "$1" | cut -d' ' -f1 || echo absent; }
{
  echo "arm=$ARM"; echo "mode=interactive"
  [ "${H1_SELFTEST:-}" = 1 ] && echo "selftest=1 (NOT live evidence)"
  echo "claude_version=$(claude --version | tr -d '\r')"
  echo "harness_head=$(git -C "$BASE" rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "sources=$SOURCES"; echo "settings_sha=$(h "$WS/.claude/settings.json")"
  echo "prepared=$(date -u +%FT%TZ)"
} > "$OUT/observer.txt" || die "cannot write observer.txt"
cat > "$OUT/observation.json" <<'EOF'
{
  "_instructions": "Fill in after the session, from what you saw and the recording. Booleans must be true or false; do not leave null.",
  "notice_visible": null,
  "notice_text_seen": "",
  "returned_to_input_prompt": null,
  "unexpected_prompt": null,
  "notes": "",
  "frames": []
}
EOF
WSW=$(cygpath -w "$WS")
cat <<EOF

Prepared $ARM. Operator steps (PowerShell, your own window, NOT inside Claude Code):
  1. Start a screen recording of the terminal window.
  2. Set-Location "$WSW"
  3. claude --setting-sources $SOURCES --permission-mode acceptEdits --allowedTools Read
  4. Type exactly this prompt, then Enter:
       $(cat "$OUT/prompt.txt")
  5. After the reply, wait at the input prompt for at least 30 seconds. Note any warning/notice text.
  6. Type /exit, then stop the recording. Keep the recording file.
  7. Fill in $(cygpath -w "$OUT/observation.json") (notice_visible, notice_text_seen,
     returned_to_input_prompt, unexpected_prompt, and frames: [{"t": "mm:ss", "file": "<still>.png"}]).
  8. Run: finish_a1_interactive.sh $ARM "<path to recording>"
EOF
