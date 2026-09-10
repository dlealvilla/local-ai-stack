#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

BASE_ROOT="${KULTRUN_ACCEPTANCE_BASE:-/workspace/kultrun-acceptance}"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage:
  initial_setup.sh <run-name> <wheel-path> <expected-sha256> [extras]

Creates a logically fresh Kultrun acceptance namespace.

Example:
  ./initial_setup.sh \
    stage-1.6L-r4 \
    /workspace/incoming/kultrun-0.1.0-py3-none-any.whl \
    EXPECTED_SHA256 \
    acquisition
EOF
}

safe_run_name() {
  [[ "$1" =~ ^[A-Za-z0-9._-]+$ ]] || \
    die "Unsafe run name: $1"
  [[ "$1" != "." && "$1" != ".." ]] || \
    die "Unsafe run name: $1"
}

sha256_file() {
  python3 - "$1" <<'PY'
import hashlib
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
digest = hashlib.sha256()

with path.open("rb") as f:
    for block in iter(lambda: f.read(1024 * 1024), b""):
        digest.update(block)

print(digest.hexdigest())
PY
}

[[ $# -ge 3 && $# -le 4 ]] || {
  usage
  exit 1
}

RUN_NAME="$1"
WHEEL_SOURCE="$2"
EXPECTED_SHA="$(printf '%s' "$3" | tr '[:upper:]' '[:lower:]')"
# Omit the fourth argument to install [acquisition].
# Pass an empty fourth argument for a core-only wheel install.
EXTRAS="${4-acquisition}"

safe_run_name "$RUN_NAME"

[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{64}$ ]] || \
  die "Expected SHA256 must be 64 hexadecimal characters."

[[ -f "$WHEEL_SOURCE" ]] || \
  die "Wheel not found: $WHEEL_SOURCE"

command -v python3 >/dev/null 2>&1 || \
  die "python3 is required."

RUN_ROOT="${BASE_ROOT}/${RUN_NAME}"
MARKER="${RUN_ROOT}/.kultrun-acceptance-run"

[[ ! -e "$RUN_ROOT" ]] || \
  die "Run already exists: $RUN_ROOT"

mkdir -p \
  "$RUN_ROOT/artifacts" \
  "$RUN_ROOT/state" \
  "$RUN_ROOT/cache/huggingface" \
  "$RUN_ROOT/cache/pip" \
  "$RUN_ROOT/cache/torch" \
  "$RUN_ROOT/cache/xdg" \
  "$RUN_ROOT/cache/pycache" \
  "$RUN_ROOT/config" \
  "$RUN_ROOT/data" \
  "$RUN_ROOT/tmp" \
  "$RUN_ROOT/logs" \
  "$RUN_ROOT/evidence"

cat > "$MARKER" <<EOF
KULTRUN_ACCEPTANCE_RUN=${RUN_NAME}
KULTRUN_ACCEPTANCE_ROOT=${RUN_ROOT}
CREATED_UTC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EOF

chmod 600 "$MARKER"

WHEEL_NAME="$(basename "$WHEEL_SOURCE")"
WHEEL_DEST="${RUN_ROOT}/artifacts/${WHEEL_NAME}"

cp "$WHEEL_SOURCE" "$WHEEL_DEST"

ACTUAL_SHA="$(sha256_file "$WHEEL_DEST")"

if [[ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]]; then
  rm -f "$WHEEL_DEST"
  die "Wheel SHA mismatch.
Expected: $EXPECTED_SHA
Actual:   $ACTUAL_SHA"
fi

cat > "$RUN_ROOT/env.sh" <<EOF
#!/usr/bin/env bash

export KULTRUN_ACCEPTANCE_RUN="${RUN_NAME}"
export KULTRUN_ACCEPTANCE_ROOT="${RUN_ROOT}"

export KULTRUN_STATE_ROOT="${RUN_ROOT}/state"

export HF_HOME="${RUN_ROOT}/cache/huggingface"
export HUGGINGFACE_HUB_CACHE="${RUN_ROOT}/cache/huggingface/hub"

export PIP_CACHE_DIR="${RUN_ROOT}/cache/pip"
export TORCH_HOME="${RUN_ROOT}/cache/torch"

export XDG_CACHE_HOME="${RUN_ROOT}/cache/xdg"
export XDG_CONFIG_HOME="${RUN_ROOT}/config"
export XDG_DATA_HOME="${RUN_ROOT}/data"
export XDG_STATE_HOME="${RUN_ROOT}/state/xdg"

export PYTHONPYCACHEPREFIX="${RUN_ROOT}/cache/pycache"
export PYTHONNOUSERSITE=1

export TMPDIR="${RUN_ROOT}/tmp"
export TEMP="${RUN_ROOT}/tmp"
export TMP="${RUN_ROOT}/tmp"

export KULTRUN_ACCEPTANCE_ARTIFACTS="${RUN_ROOT}/artifacts"
export KULTRUN_ACCEPTANCE_LOGS="${RUN_ROOT}/logs"
export KULTRUN_ACCEPTANCE_EVIDENCE="${RUN_ROOT}/evidence"
export KULTRUN_ACCEPTANCE_WHEEL="${WHEEL_DEST}"
EOF

chmod 600 "$RUN_ROOT/env.sh"

python3 -m venv "$RUN_ROOT/venv"

# shellcheck disable=SC1090
source "$RUN_ROOT/env.sh"

# shellcheck disable=SC1091
source "$RUN_ROOT/venv/bin/activate"

if [[ -n "$EXTRAS" ]]; then
  python -m pip install --no-input \
    "${WHEEL_DEST}[${EXTRAS}]"
else
  python -m pip install --no-input \
    "$WHEEL_DEST"
fi

{
  echo "run=${RUN_NAME}"
  echo "root=${RUN_ROOT}"
  echo "created=$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "hostname=$(hostname)"
  echo "kernel=$(uname -a)"
  echo "wheel=${WHEEL_DEST}"
  echo "sha256=${ACTUAL_SHA}"
  echo "extras=${EXTRAS}"
  echo
  python --version
  python -m pip --version
  python -m pip show kultrun || true
} > "$RUN_ROOT/evidence/install.txt" 2>&1

echo "${ACTUAL_SHA}  ${WHEEL_DEST}" \
  > "$RUN_ROOT/evidence/wheel.sha256"

if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi \
    > "$RUN_ROOT/evidence/nvidia-smi-before.txt" \
    2>&1 || true
fi

echo
echo "============================================================"
echo "KULTRUN ACCEPTANCE SANDBOX READY"
echo "============================================================"
echo
echo "Run:"
echo "  ${RUN_NAME}"
echo
echo "Root:"
echo "  ${RUN_ROOT}"
echo
echo "Activate:"
echo "  source '${RUN_ROOT}/env.sh'"
echo "  source '${RUN_ROOT}/venv/bin/activate'"
echo
echo "State root:"
echo "  ${RUN_ROOT}/state"
echo
echo "Wheel SHA256:"
echo "  ${ACTUAL_SHA}"
echo
echo "CLASSIFICATION:"
echo "  This creates LOGICALLY fresh Kultrun state."
echo "  It does NOT prove the physical host/storage is fresh."
