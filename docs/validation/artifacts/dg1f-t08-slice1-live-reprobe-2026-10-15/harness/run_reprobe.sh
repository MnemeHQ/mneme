#!/usr/bin/env bash
BASE=$(cd "$(dirname "$0")" && pwd)
rm -f "$BASE/REPROBE_DONE"
bash "$BASE/run_probe_v2.sh" R0-control protected control
bash "$BASE/run_probe_v2.sh" R2-counterfactual permissive control
bash "$BASE/run_v1_v2.sh"
date -u +%FT%TZ > "$BASE/REPROBE_DONE"
