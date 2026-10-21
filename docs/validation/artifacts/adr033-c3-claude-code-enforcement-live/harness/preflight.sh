#!/usr/bin/env bash
# Verify the pinned configuration before any live probe. Exit 1 on mismatch.
# Read-only, except that it never writes anything at all.
set -u
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins.env"
fail=0
say() { echo "[preflight] $*"; }
bad() { echo "[preflight] MISMATCH: $*"; fail=1; }

if [ "${C3_SELFTEST:-}" = 1 ]; then
  say "self-test: operator pins come from C3_ST_* (pins.local.env not used)"
elif [ -f "$BASE/pins.local.env" ]; then
  say "pins.local.env sha256: $(sha256sum < "$BASE/pins.local.env" | cut -d' ' -f1)"
else
  bad "pins.local.env missing (operator paths are placeholders in pins.env)"
fi
for v in MNEME_SRC_W MNEME_SRC_U PY; do
  case "${!v}" in *'<'*) bad "$v is still a placeholder"; echo "[preflight] FAILED"; exit 1;; esac
done

if [ "${C3_SELFTEST:-}" = 1 ]; then
  say "SELF-TEST MODE (C3_SELFTEST=1): stub claude, local remote; output is NOT live evidence"
else
  [ -n "${CLAUDECODE:-}" ] && bad "CLAUDECODE is set: this shell is inside a Claude Code session; run from your own terminal"
  [ -n "${C3_SELFTEST_LIVE:-}" ] && bad "C3_SELFTEST_LIVE is set outside self-test mode"
  v=$(claude --version | tr -d '\r')
  [ "$v" = "$PIN_CLAUDE_VERSION" ] && say "claude: $v" || bad "claude '$v' != '$PIN_CLAUDE_VERSION'"
  case "$(command -v claude)" in "$BASE/selftest/"*) bad "claude resolves to the self-test stub";; esac
fi

head=$(git -C "$MNEME_SRC_U" rev-parse HEAD)
say "mneme_src HEAD: $head"
git -C "$MNEME_SRC_U" merge-base --is-ancestor "$PIN_MNEME_BASE" "$head" \
  || bad "$PIN_MNEME_BASE is not an ancestor of $head"
git -C "$MNEME_SRC_U" diff --quiet "$PIN_MNEME_BASE" -- mneme/ \
  && say "mneme/ (incl. working tree) identical to $PIN_MNEME_BASE" \
  || bad "mneme/ differs from $PIN_MNEME_BASE"
[ -z "$(git -C "$MNEME_SRC_U" status --porcelain -- mneme/)" ] || bad "mneme/ has uncommitted or untracked changes"

mod=$("$PY" -E -P -c "import sys; sys.path.insert(0, r'$MNEME_SRC_W'); from mneme.integrations.claude_code import hook; print(hook.__file__)" | tr -d '\r')
case "$mod" in "$MNEME_SRC_W"*) say "hook module: $mod";; *) bad "hook module '$mod' not under $MNEME_SRC_W";; esac

n=$(env | cut -d= -f1 | grep -c '^MNEME_' || true)
say "MNEME_* variables in launching shell: $n (runners unset them per probe)"
for v in HTTPS_PROXY HTTP_PROXY ALL_PROXY https_proxy http_proxy all_proxy; do
  [ -n "${!v:-}" ] && say "note: $v is set in your shell (the verifier ignores it; recorded)"
done
say "git: $(git --version)"
say "python: $("$PY" -E -P -c 'import sys; print(sys.version.split()[0])' | tr -d '\r')"
say "os: $(uname -a)"

LIVE_ROOT="${C3_SELFTEST_LIVE:-$LIVE}"
d=$(cygpath -u "$LIVE_ROOT" 2>/dev/null || echo "$LIVE_ROOT")
while :; do
  [ -e "$d/.mneme" ] && bad "ancestor $d has .mneme (would shadow the parent walk)"
  [ -e "$d/.git" ] && bad "ancestor $d is a git checkout"
  parent=$(dirname "$d")
  [ "$parent" = "$d" ] && break   # reached the root ("/" or a drive root)
  d=$parent
done
say "live root: $LIVE_ROOT"
say "fixture: $FIXTURE_URL"
say "model pin (passed as --model, checked in each init event): $PIN_MODEL"
[ $fail -eq 0 ] && say "OK" || say "FAILED"
exit $fail
