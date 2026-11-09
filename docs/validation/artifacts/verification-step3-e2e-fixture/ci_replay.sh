#!/usr/bin/env bash
# Verification step 3: offline CI checkpoint (Gate 2-style replay).
#
# Runs inside the pinned ubuntu:24.04 container. Installs the APPROVED
# evaluator wheel (0b74d410, sha256 e3fcc769...) hash-locked, verifies the
# C4 adapter pins (c51729f7), then runs `evaluate` and `verify-report`
# exactly as the trusted gate workflow does, once per case, posture closed.
#
# This is an offline replay, NOT a GitHub Actions observation.
#
# Mounts: /fixture (fixture git repo), /in (wheel, requirements, adapter,
# cases.tsv), /out (results).
set -euo pipefail

EVALUATOR_COMMIT=0b74d410b45e7b3efcf08d00ce58e7bd7017b757
APPROVED_WHEEL_SHA256=e3fcc769c440ed232ad05117f256739daf233e0c9f6d3d46586adc0de9b48c51
ADAPTER_SHA256=afe1d69c1ce4170875989c5866bb2ec7b5089fc895efa699ced826317e3777f9
GATE_PYTHON=/usr/bin/python3.12

unset PYTHONPATH
wheel=/in/mneme_hq-0.10.0-py3-none-any.whl
[ "$(sha256sum "$wheel" | cut -d' ' -f1)" = "$APPROVED_WHEEL_SHA256" ] \
  || { echo "evaluator wheel is not the approved build" >&2; exit 3; }
[ "$(sha256sum /in/adr033_c4_gate.py | cut -d' ' -f1)" = "$ADAPTER_SHA256" ] \
  || { echo "adapter is not the pinned file" >&2; exit 3; }

e=/tmp/evaluator
"$GATE_PYTHON" -I -m venv "$e"
req=/tmp/evaluator-requirements.txt
cp /in/evaluator-requirements.txt "$req"
echo "$wheel --hash=sha256:$APPROVED_WHEEL_SHA256" >> "$req"
"$e/bin/python" -I -m pip install -q --disable-pip-version-check \
  --require-hashes --only-binary=:all: --no-deps -r "$req"
"$e/bin/python" -I -c "import importlib.metadata as m, mneme, sys; p = mneme.__file__; assert p.startswith(sys.prefix), p; print(m.version('mneme-hq'))" > /out/evaluator-version.txt

{
  echo "evaluator_commit $EVALUATOR_COMMIT"
  echo "evaluator_wheel_sha256 $(sha256sum "$wheel" | cut -d' ' -f1)"
  echo "evaluator_version $(cat /out/evaluator-version.txt)"
  echo "adapter_sha256 $(sha256sum /in/adr033_c4_gate.py | cut -d' ' -f1)"
  echo "gate_python $("$GATE_PYTHON" -c 'import sys; print(sys.version.split()[0])')"
  echo "os $(. /etc/os-release && echo "$PRETTY_NAME")"
} > /out/pins.txt

git config --global --add safe.directory '*'

while IFS=$'\t' read -r case_id base head; do
  [ -n "$case_id" ] || continue
  d="/out/$case_id"
  mkdir -p "$d"
  set +e
  MNEME_CI_AVAILABILITY=closed "$GATE_PYTHON" -I /in/adr033_c4_gate.py evaluate \
    --repo /fixture --base-sha "$base" --head-sha "$head" --mode strict \
    --workspace "/tmp/ws-$case_id" --empty-dir "/tmp/empty-$case_id" \
    --venv-python "$e/bin/python" --evaluator-commit "$EVALUATOR_COMMIT" \
    --evaluator-wheel-sha256 "$APPROVED_WHEEL_SHA256" \
    --report "$d/gate-report.json" --summary "$d/summary.md" > "$d/evaluate.log" 2>&1
  code=$?
  MNEME_CI_AVAILABILITY=closed "$GATE_PYTHON" -I /in/adr033_c4_gate.py verify-report \
    --report "$d/gate-report.json" --adapter-exit "$code" \
    --base-sha "$base" --head-sha "$head" --mode strict \
    --adapter-sha256 "$ADAPTER_SHA256" --evaluator-commit "$EVALUATOR_COMMIT" \
    --evaluator-wheel-sha256 "$APPROVED_WHEEL_SHA256" --summary "$d/summary.md" \
    > "$d/verify.log" 2>&1
  vcode=$?
  set -e
  printf '{"adapter_exit": %s, "verify_exit": %s}\n' "$code" "$vcode" > "$d/exit.json"
  echo "$case_id adapter=$code verify=$vcode"
done < /in/cases.tsv
