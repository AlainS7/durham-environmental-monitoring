#!/usr/bin/env bash
# Helper wrapper for merge_backfill_range.py to standardize backfill merges.
# See README section: Per-Source Dated Staging & Backfill Merge
#
# Usage examples:
#   scripts/run_merge_backfill.sh --start 2025-10-05 --end 2025-11-07
#   scripts/run_merge_backfill.sh --start 2025-11-01 --end 2025-11-02 --sources tsi --dry-run
#
# Flags:
#   --start YYYY-MM-DD            (required) Start date inclusive
#   --end YYYY-MM-DD              (required) End date inclusive
#   --sources src1,src2           (default: tsi,wu)
#   --project PROJECT_ID          (default: $BQ_PROJECT or gcloud config)
#   --dataset DATASET             (default: sensors)
#   --update-only-if-changed      (only update existing rows if value changed)
#   --dry-run                     (plan only, no MERGE execution)
#   --no-per-source-dated         (fallback to auto-detect staging mode)
#   --python PYTHON_BIN           (default: python)
#   -h|--help                     Show help
#
# Exit codes:
#   0 success
#   2 missing required args
#   3 invalid date format
#   4 merge script not found
#   >0 underlying python error
set -euo pipefail

COLOR() { local c="$1"; shift; printf "\033[%sm%s\033[0m" "$c" "$*"; }
info() { echo "$(COLOR 36 [INFO]) $*"; }
warn() { echo "$(COLOR 33 [WARN]) $*"; }
err()  { echo "$(COLOR 31 [ERR])  $*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MERGE_SCRIPT="${SCRIPT_DIR}/merge_backfill_range.py"

if [[ ! -f "$MERGE_SCRIPT" ]]; then
  err "merge_backfill_range.py not found at $MERGE_SCRIPT"
  exit 4
fi

START=""; END=""; SOURCES="tsi,wu"; PROJECT="${BQ_PROJECT:-}"; DATASET="sensors"; UPDATE_CHANGED=0; DRY_RUN=0; PER_SOURCE=1; PY_BIN="python"

print_help() {
  sed -n '1,40p' "$0" | grep -E '^#' | sed 's/^# \{0,1\}//'
  cat <<'EOF'
Examples:
  scripts/run_merge_backfill.sh --start 2025-10-05 --end 2025-10-07
  scripts/run_merge_backfill.sh --start 2025-11-01 --end 2025-11-02 --sources tsi --update-only-if-changed
EOF
}

is_date() { [[ "$1" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; }

while (( "$#" )); do
  case "$1" in
    --start) START="$2"; shift 2;;
    --end) END="$2"; shift 2;;
    --sources) SOURCES="$2"; shift 2;;
    --project) PROJECT="$2"; shift 2;;
    --dataset) DATASET="$2"; shift 2;;
    --update-only-if-changed) UPDATE_CHANGED=1; shift;;
    --dry-run) DRY_RUN=1; shift;;
    --no-per-source-dated) PER_SOURCE=0; shift;;
    --python) PY_BIN="$2"; shift 2;;
    -h|--help) print_help; exit 0;;
    *) err "Unknown flag: $1"; print_help; exit 2;;
  esac
done

if [[ -z "$START" || -z "$END" ]]; then
  err "--start and --end required"; print_help; exit 2
fi
if ! is_date "$START" || ! is_date "$END"; then
  err "Invalid date format (expected YYYY-MM-DD): start='$START' end='$END'"; exit 3
fi

if [[ -z "$PROJECT" ]]; then
  PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
  if [[ -z "$PROJECT" ]]; then
    err "Could not determine project (set BQ_PROJECT env or use --project)"; exit 2
  fi
fi

# Activate local virtualenv if present
if [[ -d "${SCRIPT_DIR}/../.venv" && -f "${SCRIPT_DIR}/../.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/../.venv/bin/activate"
fi

ARGS=("$MERGE_SCRIPT" --project "$PROJECT" --dataset "$DATASET" --start "$START" --end "$END")
if (( PER_SOURCE )); then
  ARGS+=(--per-source-dated --sources "$SOURCES")
else
  ARGS+=(--auto-detect-staging)
fi
if (( UPDATE_CHANGED )); then ARGS+=(--update-only-if-changed); fi
if (( DRY_RUN )); then ARGS+=(--dry-run); fi

info "Project: $PROJECT"
info "Dataset: $DATASET"
info "Date range: $START -> $END"
info "Mode: $([[ $PER_SOURCE -eq 1 ]] && echo per-source-dated || echo auto-detect)"
info "Sources: $SOURCES"
info "Update only if changed: $UPDATE_CHANGED"
info "Dry run: $DRY_RUN"

set -x
"$PY_BIN" "${ARGS[@]}"
EXIT_CODE=$?
set +x

if [[ $EXIT_CODE -eq 0 ]]; then
  info "Merge completed successfully."
else
  err "Merge script exited with status $EXIT_CODE"
fi

exit $EXIT_CODE
