#!/usr/bin/env bash
# Prepare one fixture change on a local branch. NEVER pushes or opens a PR.
#
# usage: seed_fixture.sh <activate|authorize|revoke>
#
#   activate   app.py + canonical memory via the real CLI: `mneme init`,
#              `add_decision C3-DEC` (FORBID_LITERAL psycopg2 via anti-pattern),
#              `mneme protect activate C3-DEC`          -> baseline ABSENT
#   authorize  `mneme availability authorize` (interactive, typed by a human)
#                                                       -> baseline AUTHORIZED
#   revoke     `mneme availability revoke` (interactive) -> baseline REVOKED
#
# Each step leaves a commit on branch c3/<step> in $LIVE/_seed and prints the
# push and PR commands. A human opens and merges the PR (ADR-033 §4.5: the
# merge is recorded as human-attested, never as independent review).
set -u
set -o pipefail
BASE=$(cd "$(dirname "$0")" && pwd)
. "$BASE/pins.env"
STEP=${1:-}
case "$STEP" in activate|authorize|revoke) ;; *) echo "usage: $0 <activate|authorize|revoke>"; exit 1;; esac
[ -n "${CLAUDECODE:-}" ] && { echo "ABORT: run from your own terminal, not inside Claude Code"; exit 1; }
"$PY" -E -P "$BASE/safe_rmtree.py" delete _seed || { echo "ABORT: guarded delete refused"; exit 1; }
S="$LIVE/_seed"
git clone -q "$FIXTURE_URL" "$S" || { echo "ABORT: clone failed"; exit 1; }
cd "$S" || exit 1
git switch -q -c "c3/$STEP"
MNEME() { "$PY" -E -P -c "import sys; sys.path.insert(0, sys.argv[1]); from mneme.cli import main; raise SystemExit(main(sys.argv[2:]))" "$MNEME_SRC_W" "$@"; }

case "$STEP" in
  activate)
    [ -e .mneme ] && { echo "ABORT: the fixture already has .mneme/"; exit 1; }
    printf 'import os\n\n\ndef handler():\n    return 1\n' > app.py
    MNEME init || exit 1
    MNEME add_decision --memory .mneme/project_memory.json --id C3-DEC \
      --decision "Do not use psycopg2 in the service layer" --anti-pattern psycopg2 || exit 1
    MNEME protect activate C3-DEC --memory .mneme/project_memory.json || exit 1
    MSG="c3: seed app.py and activate protection for C3-DEC" ;;
  authorize)
    MNEME availability authorize || exit 1
    MSG="c3: authorize fail-closed availability (ADR-033)" ;;
  revoke)
    MNEME availability revoke || exit 1
    MSG="c3: revoke fail-closed availability (ADR-033)" ;;
esac
git add -A && git commit -q -m "$MSG" || { echo "ABORT: commit failed"; exit 1; }
cat <<EOF

Prepared on branch c3/$STEP in $S (nothing pushed):
  $(git log -1 --format='%h %s')
Next, by the owner (or with the owner's explicit go-ahead):
  git -C "$S" push -u origin c3/$STEP
  gh pr create -R MnemeHQ/mneme-claude-code-enforcement-fixture --base main --head c3/$STEP --title "$MSG"
A human then squash-merges the PR. Record who merged it for E5.
EOF
