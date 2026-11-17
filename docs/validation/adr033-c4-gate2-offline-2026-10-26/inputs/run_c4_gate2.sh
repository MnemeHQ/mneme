#!/usr/bin/env bash
# ADR-033 C4 Gate 2 offline validation run. Executes inside ubuntu:24.04
# (/usr/bin/python3.12, the CI1 lab runner's interpreter) with:
#   /in   read-only: preserved evaluator wheel, lab lock file, this script, the replay driver
#   /src  read-only: the MnemeHQ/mneme checkout (cloned here at the pinned commit)
#   /out  evidence output
# Pin checks stop the run; every later step runs and its exit code is recorded.
set -uo pipefail

ADAPTER_COMMIT=c51729f78199203fe12fcbc5c678b89a2c4f7d3e
ADAPTER_PATH=scripts/ci/adr033_c4_gate.py
ADAPTER_BLOB=5feedf60ce1a67b2bb85673354c8b8b367a87d06
ADAPTER_SHA256=afe1d69c1ce4170875989c5866bb2ec7b5089fc895efa699ced826317e3777f9
EVALUATOR_COMMIT=0b74d410b45e7b3efcf08d00ce58e7bd7017b757
WHEEL=/in/mneme_hq-0.10.0-py3-none-any.whl
WHEEL_SHA256=e3fcc769c440ed232ad05117f256739daf233e0c9f6d3d46586adc0de9b48c51
LOCK_SHA256=e4ef9d786fd2a49f0dc76a9d5304278f92f23d8257e2410f0305dca883ecca8b
PY=/usr/bin/python3.12
OUT=/out
W=/work

die() { echo "PIN FAILURE: $*" | tee -a "$OUT/steps.txt"; exit 3; }
step() {  # step <name> <command...>: run, keep full log, record exit code
  local name=$1; shift
  echo "== $name: $*" >> "$OUT/steps.txt"
  "$@" > "$OUT/$name.log" 2>&1
  local rc=$?
  echo "   exit $rc" >> "$OUT/steps.txt"
  return 0
}

mkdir -p "$W"
: > "$OUT/steps.txt"
{
  echo "started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  grep -E '^(PRETTY_NAME|VERSION_ID)=' /etc/os-release
  echo "kernel=$(uname -srm)"
  echo "python=$($PY -c 'import sys; print(sys.version)')"
  echo "git=$(git --version)"
} > "$OUT/environment.txt"

# ── pins ─────────────────────────────────────────────────────────────────────
git config --global --add safe.directory '*'  # /src is a host mount owned by another uid
git clone -q --no-checkout /src "$W/core" || die "clone"
git -C "$W/core" checkout -q --detach "$ADAPTER_COMMIT" || die "checkout $ADAPTER_COMMIT"
[ "$(git -C "$W/core" rev-parse HEAD)" = "$ADAPTER_COMMIT" ] || die "core HEAD"
[ "$(git -C "$W/core" rev-parse "HEAD:$ADAPTER_PATH")" = "$ADAPTER_BLOB" ] || die "adapter blob"
[ "$(git -C "$W/core" ls-tree HEAD -- "$ADAPTER_PATH" | cut -d' ' -f1)" = "100644" ] || die "adapter mode"
[ "$(sha256sum "$W/core/$ADAPTER_PATH" | cut -d' ' -f1)" = "$ADAPTER_SHA256" ] || die "adapter sha256"
[ "$(sha256sum "$WHEEL" | cut -d' ' -f1)" = "$WHEEL_SHA256" ] || die "wheel sha256"
[ "$(sha256sum /in/evaluator-requirements.txt | cut -d' ' -f1)" = "$LOCK_SHA256" ] || die "lock sha256"
[ -z "$(git -C "$W/core" status --porcelain)" ] || die "core checkout not clean"
{
  echo "core_commit=$(git -C "$W/core" rev-parse HEAD)"
  echo "adapter_blob=$ADAPTER_BLOB"
  echo "adapter_sha256=$ADAPTER_SHA256"
  echo "evaluator_commit=$EVALUATOR_COMMIT"
  echo "wheel_sha256=$WHEEL_SHA256"
  echo "lock_sha256=$LOCK_SHA256"
  echo "fixtures_tree_v1=$(git -C "$W/core" rev-parse HEAD:tests/fixtures/adr033_c4_ci/v1)"
  echo "ci1_contract_tree=$(git -C "$W/core" rev-parse HEAD:tests/fixtures/ci1_contract)"
  echo "test_module_blob=$(git -C "$W/core" rev-parse HEAD:tests/test_adr033_c4_ci_gate.py)"
  echo "preflight_blob=$(git -C "$W/core" rev-parse HEAD:scripts/ci1_evaluator_preflight.py)"
  echo "replay_driver_sha256=$(sha256sum /in/c4_gate2_ci1_replay.py | cut -d' ' -f1)"
  echo "run_script_sha256=$(sha256sum /in/run_c4_gate2.sh | cut -d' ' -f1)"
} > "$OUT/pins.txt"
echo "pins verified" >> "$OUT/steps.txt"

# ── evaluator venv, exactly as the CI1 lab workflow installs it ──────────────
$PY -I -m venv "$W/evaluator" || die "evaluator venv"
cp /in/evaluator-requirements.txt "$W/evaluator-req.txt"
echo "$WHEEL --hash=sha256:$WHEEL_SHA256" >> "$W/evaluator-req.txt"
"$W/evaluator/bin/python" -I -m pip install -q --disable-pip-version-check \
  --require-hashes --only-binary=:all: --no-deps -r "$W/evaluator-req.txt" > "$OUT/evaluator-install.log" 2>&1 \
  || die "evaluator install (see evaluator-install.log)"
(cd /tmp && "$W/evaluator/bin/python" -I -c "import importlib.metadata as m, mneme, sys; p = mneme.__file__; assert p.startswith(sys.prefix), p; print(m.version('mneme-hq'), p)") \
  > "$OUT/evaluator-identity.txt" 2>&1 || die "evaluator identity"
"$W/evaluator/bin/python" -I -m pip freeze --all > "$OUT/pip-freeze-evaluator.txt"

# ── harness venv: the pinned checkout plus test tooling (never the evaluator) ─
$PY -I -m venv "$W/harness" || die "harness venv"
"$W/harness/bin/python" -m pip install -q --disable-pip-version-check -e "$W/core[dev]" > "$OUT/harness-install.log" 2>&1 \
  || die "harness install (see harness-install.log)"
"$W/harness/bin/python" -m pip freeze --all > "$OUT/pip-freeze-harness.txt"
git -C "$W/core" status --porcelain > "$OUT/core-status-after-install.txt"

# ── 1. adapter test module, real-evaluator group on the approved evaluator ───
cd "$W/core"
step pytest-adr033-c4 env MNEME_C4_EVALUATOR_PYTHON="$W/evaluator/bin/python" \
  "$W/harness/bin/python" -m pytest tests/test_adr033_c4_ci_gate.py -v -rs -p no:cacheprovider \
  --junitxml="$OUT/junit-adr033-c4.xml"

# ── 2. CI1.2 corpora replay against the approved evaluator ───────────────────
step ci1-replay "$W/harness/bin/python" /in/c4_gate2_ci1_replay.py "$W/core" "$W/evaluator" "$WHEEL" \
  "$W/ci1-replay-work" "$OUT/ci1-replay.json"

# ── 3. existing CI1 contract tests (tree under test, for reference) ──────────
step pytest-ci1-contract "$W/harness/bin/python" -m pytest tests/test_ci1_contract_fixtures.py \
  tests/test_ci1_contract_matrix.py -q -rs -p no:cacheprovider --junitxml="$OUT/junit-ci1-contract.xml"

# ── 4. frozen canonical benchmark: approved evaluator and pinned tree ─────────
step benchmark-evaluator "$W/evaluator/bin/python" -I -m mneme.cli benchmark examples/benchmarks/ \
  --memory examples/project_memory.json
step benchmark-tree "$W/harness/bin/python" -m mneme.cli benchmark examples/benchmarks/ \
  --memory examples/project_memory.json

# ── close ────────────────────────────────────────────────────────────────────
git -C "$W/core" status --porcelain > "$OUT/core-status-end.txt"
echo "finished_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUT/environment.txt"
(cd "$OUT" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
cat "$OUT/steps.txt"
