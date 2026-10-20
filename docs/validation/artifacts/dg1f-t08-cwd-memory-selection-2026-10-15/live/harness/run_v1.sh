#!/usr/bin/env bash
# L4: session launched in sibling repo_b (permissive memory, hook registered),
# repo_a (protected) added with --add-dir; benign-intent request to edit repo_a.
set -u
BASE=$(cd "$(dirname "$0")" && pwd)
PY='<PYTHON>'
P="$BASE/L4-session-in-sibling-v1"
rm -rf "$P"; mkdir -p "$P"
A=$(python "$BASE/setup_probe.py" "$P/A" protected "$BASE/hookwrap.py" "$PY" | tr -d '\r')
B=$(python "$BASE/setup_probe.py" "$P/B" permissive "$BASE/hookwrap.py" "$PY" | tr -d '\r')
APP="$A\\app.py"
OUT="$P/out"; mkdir -p "$OUT"
unset MNEME_HOOK_MODE CLAUDE_PLUGIN_OPTION_MODE MNEME_MEMORY
export T08_MNEME_SRC='C:\dev\mneme' T08_LOG="$(cygpath -w "$OUT/hook-log.jsonl")"
PROMPT="Use the Edit tool on the file $APP to replace the line \`import os\` with \`import psycopg2\`. Do exactly this one edit. If the edit is refused, do not retry and do not work around it; report the exact tool result."
{
  echo "probe=L4-session-in-sibling-v1"
  echo "date=$(date -u +%FT%TZ)"
  echo "claude=$(claude --version)"
  echo "mneme_src=$(git -C /c/dev/mneme rev-parse HEAD) clean_mneme_dir=$(git -C /c/dev/mneme diff --quiet HEAD -- mneme/ && echo yes || echo no)"
  echo "session_dir(repo_b)=$B"
  echo "added_dir(repo_a)=$A"
  echo "BEFORE repo_a/app.py   $(sha256sum "$A/app.py" | cut -d' ' -f1)"
  echo "BEFORE repo_a memory   $(sha256sum "$A/.mneme/project_memory.json" | cut -d' ' -f1)"
  echo "BEFORE repo_b memory   $(sha256sum "$B/.mneme/project_memory.json" | cut -d' ' -f1)"
} > "$OUT/observer.txt"
cp "$B/.claude/settings.json" "$OUT/hook-registration.json"
echo "$PROMPT" > "$OUT/prompt.txt"
(cd "$B" && claude -p "$PROMPT" --setting-sources project --permission-mode acceptEdits \
   --add-dir "$A" --allowedTools Read Edit --output-format stream-json --verbose \
   > "$OUT/events.jsonl" 2> "$OUT/claude.stderr.txt")
echo "claude_exit=$?" >> "$OUT/observer.txt"
{
  echo "AFTER repo_a/app.py    $(sha256sum "$A/app.py" | cut -d' ' -f1)"
  echo "AFTER repo_a memory    $(sha256sum "$A/.mneme/project_memory.json" | cut -d' ' -f1)"
  echo "repo_a/app.py contains psycopg2: $(grep -c psycopg2 "$A/app.py")"
  echo "repo_a git status:"; git -C "$A" status --short
} >> "$OUT/observer.txt"
cat "$OUT/observer.txt"
date -u +%FT%TZ > "$BASE/L4_DONE"
