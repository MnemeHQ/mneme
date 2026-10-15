#!/usr/bin/env bash
BASE=$(cd "$(dirname "$0")" && pwd)
rm -f "$BASE/ALL_DONE"
bash "$BASE/run_probe.sh" L0-control protected control
bash "$BASE/run_probe.sh" L1-attack-v3 protected attack
bash "$BASE/run_probe.sh" L2-counterfactual permissive control
date -u +%FT%TZ > "$BASE/ALL_DONE"
