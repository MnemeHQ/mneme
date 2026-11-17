# Finished-batch guard, sourced by every runner and probe BEFORE anything is written.
#
# A disposable root that already holds a finished batch is kept evidence, so a new
# run must never touch it: not clear its markers, overwrite its log, or delete an
# arm. On 2026-11-13 a mutation check of #802 let `run_h1.sh A2` start against the
# kept A2 root; it deleted H1_DONE and summary_h1.md and overwrote run_h1.log before
# aborting at the preflight (restored from the archive). This guard runs first and
# refuses instead, changing nothing. To start again, archive the root, then empty it.
#
# usage (after the pins are sourced):
#   . "$BASE/guard_finished.sh"
#   refuse_finished_batch "$LIVE" H1_DONE summary_h1.md
#   refuse_finished_arm "$LIVE/$ARM"
# Each exits 1 from the calling script on a hit, and writes nothing.

refuse_finished_batch() {
  local root=$1 m
  shift
  for m in "$@"; do
    if [ -e "$root/$m" ]; then
      echo "ABORT: $root holds a finished batch ($m). Archive it and empty the root before a new run; nothing was changed."
      exit 1
    fi
  done
}

# An interactive arm is finished once finish_a1_interactive.sh has recorded its
# recording hash. Preparing it again would delete it; finishing it again would
# append to its observer.
refuse_finished_arm() {
  local arm=$1
  if [ -f "$arm/out/observer.txt" ] && grep -q '^recording_sha256=' "$arm/out/observer.txt"; then
    echo "ABORT: $arm is a finished interactive arm (recording recorded). Archive it first; nothing was changed."
    exit 1
  fi
}
