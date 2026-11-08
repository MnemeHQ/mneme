#!/usr/bin/env bash
# Verify the pinned configuration before any live H1 probe. Exit 1 on mismatch.
# Derived from the D6 C4 preflight.sh (#528); H1 runs no Mneme code (the hook is
# the harness-only emitter), so the Mneme source/version checks are dropped and
# the MNEME_* guard is kept so no Mneme override can reach the session.
set -u
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins.env"
fail=0
say() { echo "[preflight] $*"; }
bad() { echo "[preflight] MISMATCH: $*"; fail=1; }

if [ -f "$BASE/pins.local.env" ]; then
  say "pins.local.env sha256: $(sha256sum < "$BASE/pins.local.env" | cut -d' ' -f1)"
else
  bad "pins.local.env missing (operator paths are placeholders in pins.env)"
fi
case "$PY" in *'<'*) bad "PY is still a placeholder"; echo "[preflight] FAILED"; exit 1;; esac
say "setting sources for every probe: $SOURCES"

v=$(claude --version | tr -d '\r')
[ "$v" = "$PIN_CLAUDE_VERSION" ] && say "claude: $v" || bad "claude '$v' != '$PIN_CLAUDE_VERSION'"

# Guards: never nested inside a Claude Code session; never a redirected live root.
# H1_SELFTEST=1 (stub `claude`, not Claude Code) relaxes only the CLAUDECODE guard
# and marks the run invalid as evidence. H1_LIVE is never honored.
[ -n "${H1_LIVE:-}" ] && bad "H1_LIVE is set; the live root is fixed (no override). Run: unset H1_LIVE"
if [ "${H1_SELFTEST:-}" = 1 ]; then
  say "SELF-TEST MODE (H1_SELFTEST=1): output is NOT live evidence"
else
  [ -n "${CLAUDECODE:-}" ] && bad "CLAUDECODE is set: this shell is inside a Claude Code session; run from your own terminal"
fi
n=$(env | cut -d= -f1 | grep -c '^MNEME_' || true)
say "MNEME_* variables in launching shell: $n (names/values not printed)"
[ "$n" = 0 ] || bad "MNEME_* variables are set in the launching shell; unset them before an H1 run"
say "claude binary: $(command -v claude)"
say "python: $("$PY" -I -c 'import sys; print(sys.version.split()[0])' | tr -d '\r')"

d="$LIVE"; while [ "$d" != "/" ] && [ "$d" != "." ]; do
  [ -e "$d/.mneme" ] && bad "ancestor $d has .mneme"
  [ -e "$d/.git" ] && bad "ancestor $d is a git checkout"
  [ -e "$d/.claude/settings.json" ] && [ "$d" != "$LIVE" ] && bad "ancestor $d has .claude/settings.json (would add hooks)"
  d=$(dirname "$d")
done
say "live root: $LIVE"
say "model pin (checked from the first probe's init event): $PIN_MODEL"
[ $fail -eq 0 ] && say "OK" || say "FAILED"
exit $fail
