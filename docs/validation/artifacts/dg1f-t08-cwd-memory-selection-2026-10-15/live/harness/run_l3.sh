#!/usr/bin/env bash
BASE=$(cd "$(dirname "$0")" && pwd)
bash "$BASE/run_probe.sh" L3-plumbing-v3 protected plumbing
date -u +%FT%TZ > "$BASE/L3_DONE"
