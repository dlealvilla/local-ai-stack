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
  cleanup.sh <run-name> [--yes]

Without --yes this is a dry run.

Cleanup refuses to remove a run while obvious processes/open files
still reference its namespace.
EOF
}

safe_run_name() {
  [[ "$1" =~ ^[A-Za-z0-9._-]+$ ]] || \
    die "Unsafe run name: $1"
  [[ "$1" != "." && "$1" != ".." ]] || \
    die "Unsafe run name: $1"
}

[[ $# -ge 1 && $# -le 2 ]] || {
  usage
  exit 1
}

RUN_NAME="$1"
CONFIRM="${2:-}"

safe_run_name "$RUN_NAME"

RUN_ROOT="${BASE_ROOT}/${RUN_NAME}"
MARKER="${RUN_ROOT}/.kultrun-acceptance-run"

case "$RUN_ROOT" in
  "${BASE_ROOT}/"*) ;;
  *) die "Unsafe cleanup path: $RUN_ROOT" ;;
esac

[[ "$RUN_ROOT" != "$BASE_ROOT" ]] || \
  die "Refusing to remove the acceptance base root."

[[ -d "$RUN_ROOT" ]] || \
  die "Run does not exist: $RUN_ROOT"

[[ -f "$MARKER" ]] || \
  die "Acceptance safety marker missing."

grep -Fxq \
  "KULTRUN_ACCEPTANCE_RUN=${RUN_NAME}" \
  "$MARKER" || \
  die "Acceptance marker mismatch."

echo
echo "Acceptance run:"
echo "  $RUN_ROOT"
echo

du -sh "$RUN_ROOT" 2>/dev/null || true

PROCESS_MATCHES="$(
  ps -eo pid=,args= 2>/dev/null \
    | grep -F "$RUN_ROOT" \
    | grep -v -F "grep -F" \
    || true
)"

if [[ -n "$PROCESS_MATCHES" ]]; then
  echo
  echo "Live processes reference this acceptance run:"
  echo "$PROCESS_MATCHES"
  echo
  die "Resolve/stop live workloads before cleanup."
fi

if command -v lsof >/dev/null 2>&1; then
  OPEN_FILES="$(lsof +D "$RUN_ROOT" 2>/dev/null || true)"

  if [[ -n "$OPEN_FILES" ]]; then
    echo
    echo "$OPEN_FILES"
    echo
    die "Open files remain in acceptance namespace."
  fi
fi

if [[ "$CONFIRM" != "--yes" ]]; then
  echo
  echo "DRY RUN ONLY."
  echo "Nothing removed."
  echo
  echo "To remove:"
  echo "  $0 '$RUN_NAME' --yes"
  exit 0
fi

if rm --help 2>/dev/null | grep -q -- "--one-file-system"; then
  rm -rf --one-file-system -- "$RUN_ROOT"
else
  rm -rf -- "$RUN_ROOT"
fi

[[ ! -e "$RUN_ROOT" ]] || \
  die "Cleanup incomplete: $RUN_ROOT"

echo
echo "Removed only:"
echo "  $RUN_ROOT"
