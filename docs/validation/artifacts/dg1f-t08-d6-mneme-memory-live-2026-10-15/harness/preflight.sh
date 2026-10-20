#!/usr/bin/env bash
# Verify the pinned configuration before any live probe. Exit 1 on mismatch.
set -u
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins.env"
fail=0
say() { echo "[preflight] $*"; }
bad() { echo "[preflight] MISMATCH: $*"; fail=1; }

v=$(claude --version | tr -d '\r')
[ "$v" = "$PIN_CLAUDE_VERSION" ] && say "claude: $v" || bad "claude '$v' != '$PIN_CLAUDE_VERSION'"

head=$(git -C "$MNEME_SRC_U" rev-parse HEAD)
say "mneme_src HEAD: $head"
git -C "$MNEME_SRC_U" merge-base --is-ancestor "$PIN_MNEME_BASE" "$head" \
  || bad "$PIN_MNEME_BASE is not an ancestor of $head"
git -C "$MNEME_SRC_U" diff --quiet "$PIN_MNEME_BASE" -- mneme/ \
  && say "mneme/ (incl. working tree) identical to $PIN_MNEME_BASE" \
  || bad "mneme/ differs from $PIN_MNEME_BASE"
[ -z "$(git -C "$MNEME_SRC_U" status --porcelain -- mneme/)" ] || bad "mneme/ has uncommitted or untracked changes"

out=$("$PY" -I -c "import sys; sys.path.insert(0, r'$MNEME_SRC_W'); import mneme; from mneme.integrations.claude_code import hook; print(mneme.__version__); print(hook.__file__)" | tr -d '\r')
ver=$(echo "$out" | sed -n 1p); mod=$(echo "$out" | sed -n 2p)
[ "$ver" = "$PIN_MNEME_VERSION" ] && say "mneme $ver from $mod" || bad "mneme version '$ver' != '$PIN_MNEME_VERSION'"
case "$mod" in "$MNEME_SRC_W"*) ;; *) bad "hook module '$mod' not under $MNEME_SRC_W";; esac

for v in MNEME_MEMORY MNEME_HOOK_MODE CLAUDE_PLUGIN_OPTION_MODE; do
  [ -n "${!v:-}" ] && say "note: $v is set in your shell (runners unset it per probe)"
done

# Guards: never nested inside a Claude Code session; never redirected live root.
# D6_SELFTEST=1 (stub `claude`, not Claude Code) relaxes only the CLAUDECODE guard and marks the run invalid as evidence. D6_LIVE is never honored.
[ -n "${D6_LIVE:-}" ] && bad "D6_LIVE is set; the live root is fixed (no override). Run: unset D6_LIVE"
if [ "${D6_SELFTEST:-}" = 1 ]; then
  say "SELF-TEST MODE (D6_SELFTEST=1): output is NOT live evidence"
  [ -n "${CLAUDECODE:-}" ] && say "self-test: CLAUDECODE set, allowed for stub only"
  :
else
  [ -n "${CLAUDECODE:-}" ] && bad "CLAUDECODE is set: this shell is inside a Claude Code session; run from your own terminal"
fi
n=$(env | cut -d= -f1 | grep -c '^MNEME_' || true)
say "MNEME_* variables in launching shell: $n (names/values not printed; hook logs values only for MNEME_MEMORY, MNEME_HOOK_MODE)"
say "claude binary: $(command -v claude)"
say "python: $("$PY" -I -c 'import sys; print(sys.version.split()[0])' | tr -d '\r')"

d="$LIVE"; while [ "$d" != "/" ] && [ "$d" != "." ]; do
  [ -e "$d/.mneme" ] && bad "ancestor $d has .mneme (would shadow parent-walk)"
  [ -e "$d/.git" ] && bad "ancestor $d is a git checkout"
  d=$(dirname "$d")
done
say "live root: $LIVE"
say "model pin (checked from the first probe's init event): $PIN_MODEL"
[ $fail -eq 0 ] && say "OK" || say "FAILED"
exit $fail
