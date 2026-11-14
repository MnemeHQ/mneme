#!/usr/bin/env bash
# H1c Amendment A1, INTERACTIVE arm preparation (probe scope 4.2).
# usage: prep_a1_interactive.sh [A3] H1c-sm-int-ctl | H1c-sm-int
# Builds the arm's disposable workspace (guarded delete, setup_probe.py, fresh
# nonce, Stop hook registration), writes observer.txt and an observation template,
# and prints the operator's steps. It does NOT start Claude Code: the operator
# launches interactive `claude` in the workspace, records the screen, and then runs
# finish_a1_interactive.sh. Run the control arm first.
# With A3 (Amendment A3, probe scope 4.4): Claude Code 2.1.310, --model
# claude-opus-5-5, the A3 root, DISABLE_AUTOUPDATER=1 required, and operator steps
# that pin the model and check the version in the same window as the session.
set -u
set -o pipefail
BASE=$(cd "$(dirname "$0")" && pwd)
# The pin set comes only from an optional first argument "A3" (Amendment A3, probe
# scope 4.4); an A1_PINSET already in the environment is refused, never overwritten.
[ -z "${A1_PINSET+set}" ] || { echo "ABORT: A1_PINSET is set in the environment; unset it and pass A3 as the first argument"; exit 1; }
if [ "${1:-}" = A3 ]; then export A1_PINSET=A3; shift; fi
. "$BASE/pins_a1.env"
ARM=${1:-}
case "$ARM" in H1c-sm-int|H1c-sm-int-ctl) ;; *) echo "ABORT: arm must be H1c-sm-int or H1c-sm-int-ctl"; exit 1 ;; esac
[ -n "${H1_LIVE:-}" ] && { echo "ABORT: H1_LIVE is set; the live root is fixed"; exit 1; }
if [ "${H1_SELFTEST:-}" != 1 ] && [ -n "${CLAUDECODE:-}" ]; then echo "ABORT: CLAUDECODE set (run from your own terminal)"; exit 1; fi
[ "$(cygpath -w "$LIVE")" = "$A1_LIVE_W" ] || { echo "ABORT: live root is not $A1_LIVE_W"; exit 1; }
if [ "${A1_PINSET:-}" = A3 ] && [ "${DISABLE_AUTOUPDATER:-}" != 1 ]; then
  echo "ABORT: pin set A3 needs DISABLE_AUTOUPDATER=1 in this shell"; exit 1
fi
"$PY" -I "$BASE/$A1_RMTREE" check-root || { echo "ABORT: disposable root unsafe"; exit 1; }
# Host pin enforced before anything is prepared (review of #556).
V=$(claude --version | tr -d '\r')
[ "$V" = "$PIN_CLAUDE_VERSION" ] || { echo "ABORT: claude '$V' != pinned '$PIN_CLAUDE_VERSION'"; exit 1; }
mkdir -p "$LIVE" || exit 1
P="$LIVE/$ARM"
"$PY" -I "$BASE/$A1_RMTREE" delete "$ARM" || { echo "ABORT: guarded delete refused"; exit 1; }
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
  echo "pinset=${A1_PINSET:-A1}"
  [ -n "$PIN_MODEL_FLAG" ] && echo "model_flag=$PIN_MODEL_FLAG"
  echo "claude_version=$V"
  echo "pinned_model=$PIN_MODEL"
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
if [ "${A1_PINSET:-}" = A3 ]; then
# Lessons from the 2026-10-19 A1 attempts: the session started signed out, the
# prompt was sent twice, /model was run in-session, the idle wait was too short,
# and the host auto-updated between prep and launch.
cat <<EOF

Prepared $ARM (pin set A3). Operator steps, in ONE PowerShell window of your own
(NOT inside Claude Code). Do every step in order; run no other claude command between them.
  1. \$env:DISABLE_AUTOUPDATER = "1"
  2. claude --version
     It must print exactly: $PIN_CLAUDE_VERSION   Otherwise STOP and report it.
  3. Set-Location "$WSW"
  4. Start a screen recording of this terminal window.
  5. claude --setting-sources $SOURCES --permission-mode acceptEdits --allowedTools Read --model $PIN_MODEL_FLAG
     If the session is not signed in, STOP: type /exit, stop the recording, sign in
     outside this workspace, and prepare the arm again. Never run /model or /login here.
  6. Type exactly this prompt ONCE, then press Enter (never resend it):
       $(cat "$OUT/prompt.txt")
  7. After the reply, leave the session idle at the input prompt for at least 30
     seconds (count them). Note any warning or notice text.
  8. Type /exit, then stop the recording. Keep the recording file.
  9. Save redacted still frames of the notice area (or where it would appear) into
     $(cygpath -w "$OUT")\frames\ and fill in $(cygpath -w "$OUT/observation.json"):
     notice_visible, notice_text_seen (copy the EXACT text you saw, including the
     MNEME-PROBE- token), returned_to_input_prompt, unexpected_prompt, and
     frames: [{"t": "mm:ss", "file": "frames/<still>.png"}].
 10. In Git Bash, with DISABLE_AUTOUPDATER=1 set:
       finish_a1_interactive.sh A3 $ARM "<path to recording>"
EOF
exit 0
fi
cat <<EOF

Prepared $ARM. Operator steps (PowerShell, your own window, NOT inside Claude Code):
  1. Start a screen recording of the terminal window.
  2. Set-Location "$WSW"
  3. claude --setting-sources $SOURCES --permission-mode acceptEdits --allowedTools Read
  4. Type exactly this prompt, then Enter:
       $(cat "$OUT/prompt.txt")
  5. After the reply, wait at the input prompt for at least 30 seconds. Note any warning/notice text.
  6. Type /exit, then stop the recording. Keep the recording file.
  7. Save redacted still frames of the notice area (or where it would appear) into
     $(cygpath -w "$OUT")\frames\ and fill in $(cygpath -w "$OUT/observation.json"):
     notice_visible, notice_text_seen (copy the EXACT text you saw, including the
     MNEME-PROBE- token), returned_to_input_prompt, unexpected_prompt, and
     frames: [{"t": "mm:ss", "file": "frames/<still>.png"}].
  8. Run: finish_a1_interactive.sh $ARM "<path to recording>"
EOF
