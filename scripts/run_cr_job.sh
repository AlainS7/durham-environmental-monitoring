#!/usr/bin/env bash
set -euo pipefail

# Require jq for JSON parsing (GitHub Actions runners include it by default)
if ! command -v jq >/dev/null 2>&1; then
  echo "[run-job][error] jq is required but not installed. Install jq and retry." >&2
  exit 10
fi

JOB_NAME=${JOB_NAME:-sensor-ingestion-job}

# Allow first non-flag arg to override job name for convenience
if [[ $# -gt 0 ]]; then
  case "$1" in
    -h|--help)
      echo "Usage: JOB_NAME=<name> REGION=<region> PROJECT_ID=<project> SOURCE=<all|wu|tsi> $0 [job-name]"; exit 0;;
    *) JOB_NAME="$1"; shift;;
  esac
fi
REGION=${REGION:-us-central1}
DATE_SINGLE=${DATE:-${INGEST_DATE:-}}
DATE_START=${START_DATE:-}
DATE_END=${END_DATE:-}
SOURCE_FILTER=$(echo "${SOURCE:-all}" | tr '[:upper:]' '[:lower:]')

case "$SOURCE_FILTER" in
  all|wu|tsi) ;;
  *)
    echo "[run-job][error] Invalid SOURCE='$SOURCE_FILTER' (expected all|wu|tsi)." >&2
    exit 9
    ;;
esac

if [ -n "$DATE_SINGLE" ] && { [ -n "$DATE_START" ] || [ -n "$DATE_END" ]; }; then
  err "Provide either DATE (single) or START_DATE/END_DATE, not both."
  exit 9
fi

if { [ -n "$DATE_START" ] && [ -z "$DATE_END" ]; } || { [ -z "$DATE_START" ] && [ -n "$DATE_END" ]; }; then
  err "Both START_DATE and END_DATE must be provided for a range."
  exit 9
fi

make_date_seq() {
  # Args: start end (YYYY-MM-DD)
  python3 - <<'PY'
import sys, datetime as dt, os
try:
    start=os.environ['DSTART']; end=os.environ['DEND']
    sd=dt.date.fromisoformat(start); ed=dt.date.fromisoformat(end)
except (KeyError, ValueError):
    print("Invalid or missing START_DATE/END_DATE. Use YYYY-MM-DD format.", file=sys.stderr)
    sys.exit(1)
if ed < sd:
    print(f"END_DATE ({end}) cannot be before START_DATE ({start}).", file=sys.stderr); sys.exit(2)
d=sd
while d<=ed:
    print(d.isoformat())
    d+=dt.timedelta(days=1)
PY
}

if [ -n "$DATE_SINGLE" ]; then
  DATES_TO_RUN=("$DATE_SINGLE")
elif [ -n "$DATE_START" ]; then
  export DSTART="$DATE_START" DEND="$DATE_END"
  mapfile -t DATES_TO_RUN < <(make_date_seq)
else
  # Default: run once for 'today' (no explicit date env passed to job)
  DATES_TO_RUN=("")
fi

# Allow PROJECT_ID to be auto-detected if not explicitly provided
if [ "${PROJECT_ID:-}" = "" ]; then
  AUTO_PROJECT_ID=$(gcloud config get-value project 2>/dev/null || true)
  if [ -n "$AUTO_PROJECT_ID" ] && [ "$AUTO_PROJECT_ID" != "(unset)" ]; then
    PROJECT_ID="$AUTO_PROJECT_ID"
  fi
fi
: "${PROJECT_ID:?PROJECT_ID environment variable must be set (export PROJECT_ID or set gcloud config)}"
POLL_DELAY=5
MAX_WAIT=${MAX_WAIT:-600}

log(){ echo "[run-job] $*"; }
err(){ echo "[run-job][error] $*" >&2; }

# Detect container invocation mode so execution-time --args remain compatible:
# - If job command is python/python3, execution --args overrides existing args, so we must
#   include the script path as the first arg.
# - If image ENTRYPOINT already points to the collector script, we only pass collector flags.
JOB_DESC_JSON=$(gcloud run jobs describe "$JOB_NAME" --region "$REGION" --project "$PROJECT_ID" --format="json" 2>/dev/null || echo "{}")
JOB_CMD0=$(echo "$JOB_DESC_JSON" | jq -r '(
  .spec.template.template.containers[0].command[0] //
  .spec.template.template.spec.containers[0].command[0] //
  .template.template.containers[0].command[0] //
  .template.template.spec.containers[0].command[0] //
  empty
)')
JOB_ARG0=$(echo "$JOB_DESC_JSON" | jq -r '(
  .spec.template.template.containers[0].args[0] //
  .spec.template.template.spec.containers[0].args[0] //
  .template.template.containers[0].args[0] //
  .template.template.spec.containers[0].args[0] //
  empty
)')
NEEDS_SCRIPT_ARG=0
if [[ "$(basename "${JOB_CMD0:-}")" =~ ^python([0-9.]*)?$ ]]; then
  NEEDS_SCRIPT_ARG=1
fi
if [ "$NEEDS_SCRIPT_ARG" -eq 1 ] && [ -z "$JOB_ARG0" ]; then
  JOB_ARG0="${COLLECTOR_SCRIPT_PATH:-src/data_collection/daily_data_collector.py}"
fi
if [ -z "$JOB_ARG0" ]; then
  JOB_ARG0="${COLLECTOR_SCRIPT_PATH:-src/data_collection/daily_data_collector.py}"
fi
log "Job invocation mode: cmd0='${JOB_CMD0:-<entrypoint>}' arg0='${JOB_ARG0:-<none>}' needs_script_arg=$NEEDS_SCRIPT_ARG source=$SOURCE_FILTER"

ANY_FAILURE=0
run_one_execution() {
  local dval="$1"
  local use_script_arg="$2"
  local -a execute_args=()

  if [ -n "$dval" ]; then
    if [ "$use_script_arg" -eq 1 ]; then
      execute_args+=(--args="$JOB_ARG0")
    fi
    execute_args+=(--args="--start=$dval" --args="--end=$dval")
    if [ "$SOURCE_FILTER" != "all" ]; then
      execute_args+=(--args="--source=$SOURCE_FILTER")
    fi
    log "Starting ingestion for date $dval (script_arg_mode=$use_script_arg)"
  else
    if [ "$use_script_arg" -eq 1 ]; then
      execute_args+=(--args="$JOB_ARG0")
    fi
    if [ "$SOURCE_FILTER" != "all" ]; then
      execute_args+=(--args="--source=$SOURCE_FILTER")
    fi
    log "Starting ingestion for 'today' (script_arg_mode=$use_script_arg)"
  fi

  log "Executing Cloud Run job: $JOB_NAME in $REGION (project: $PROJECT_ID)"
  EXEC_ID=$(gcloud run jobs execute "$JOB_NAME" \
    --region "$REGION" \
    --project "$PROJECT_ID" \
    "${execute_args[@]}" \
    --format="value(metadata.name)" 2>/dev/null || true)
  if [ -z "$EXEC_ID" ]; then
    err "Failed to start execution (date=$dval script_arg_mode=$use_script_arg)."
    return 1
  fi
  log "Started execution: $EXEC_ID (date=$dval)"

  local elapsed=0
  local run_failed=0
  while true; do
    EXECUTION_JSON=$(gcloud run jobs executions describe "$EXEC_ID" --region "$REGION" --project "$PROJECT_ID" --format="json" 2>/dev/null || echo "{}")
    STATUS=$(echo "$EXECUTION_JSON" | jq -r '(.status.conditions[]? | select(.type=="Completed") | .status) // empty')
    LASTMSG=$(echo "$EXECUTION_JSON" | jq -r '(.status.conditions[]? | select(.type=="Completed") | .message) // empty')
    FAILED_COUNT=$(echo "$EXECUTION_JSON" | jq -r '.failedCount // 0')
    SUCCEEDED_COUNT=$(echo "$EXECUTION_JSON" | jq -r '.succeededCount // 0')
    ACTIVE_COUNT=$(echo "$EXECUTION_JSON" | jq -r '.runningCount // 0')
    log "Status(date=$dval): ${STATUS:-unknown} ${LASTMSG} (t=${elapsed}s) failed=${FAILED_COUNT} succeeded=${SUCCEEDED_COUNT} running=${ACTIVE_COUNT}"
    if [ "$FAILED_COUNT" -gt 0 ] && [ "$ACTIVE_COUNT" -eq 0 ] && [ "${STATUS:-}" != "True" ]; then
      err "Detected failed tasks early (date=$dval failedCount=$FAILED_COUNT)."
      run_failed=1
      break
    fi
    if [ "$STATUS" = "True" ]; then
      FAILED=$(echo "$EXECUTION_JSON" | jq -r '.failedCount // 0')
      if [ "${FAILED:-0}" -gt 0 ]; then
        err "Execution completed with failed tasks (date=$dval failedCount=$FAILED)."
        run_failed=1
      else
        log "Execution succeeded (date=$dval)."
      fi
      break
    fi
    if [ "$STATUS" = "False" ]; then
      err "Execution ended in failure state (date=$dval): $LASTMSG"
      run_failed=1
      break
    fi
    if [ $elapsed -ge $MAX_WAIT ]; then
      err "Timed out waiting for completion (date=$dval, $MAX_WAIT s)."
      run_failed=1
      break
    fi
    sleep $POLL_DELAY; elapsed=$((elapsed+POLL_DELAY))
  done

  log "Fetching last 200 log lines (date=$dval)"
  LOGS=$(gcloud logging read "resource.type=cloud_run_job AND resource.labels.execution_name=$EXEC_ID" --project "$PROJECT_ID" --limit=200 --format="value(textPayload)" 2>/dev/null || true)
  if [ -z "$LOGS" ]; then
    LOGS=$(gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=$JOB_NAME" --project "$PROJECT_ID" --limit=50 --format="value(textPayload)" 2>/dev/null || true)
  fi
  if [ -n "$LOGS" ]; then
    echo "$LOGS"
  else
    log "No logs retrieved (date=$dval)"
  fi

  # Fallback staging synthesis (only when a specific date provided)
  if [ -n "${dval}" ]; then
    DATE_COMPACT="${dval//-/}"
    : "${BQ_DATASET:=sensors}"  # default dataset if not provided
    if [ -z "${GCS_BUCKET:-}" ] || [ -z "${GCS_PREFIX:-}" ]; then
      log "GCS_BUCKET or GCS_PREFIX not set; skipping fallback staging synthesis for $dval"
    else
      for SRC in tsi wu; do
        TABLE="staging_${SRC}_${DATE_COMPACT}"
        # Only attempt synthesis if table is missing
        if ! bq show --project_id="$PROJECT_ID" "${PROJECT_ID}:${BQ_DATASET}.${TABLE}" >/dev/null 2>&1; then
          SRC_UPPER=$(echo "$SRC" | tr '[:lower:]' '[:upper:]')
          # Remove trailing slash from GCS_PREFIX if present
          GCS_PREFIX_CLEANED="${GCS_PREFIX%/}"
          URI="gs://${GCS_BUCKET}/${GCS_PREFIX_CLEANED}/source=${SRC_UPPER}/agg=raw/dt=${dval}/*.parquet"
          log "Staging table ${TABLE} missing; attempting load from ${URI}"
          if bq load \
            --project_id="$PROJECT_ID" \
            --autodetect \
            --source_format=PARQUET \
            "${BQ_DATASET}.${TABLE}" \
            "${URI}" >/dev/null 2>&1; then
            log "Synthesized staging table ${TABLE}"
          else
            log "Failed to synthesize staging table ${TABLE} (URI may be empty)."
          fi
        else
          log "Staging table ${TABLE} already exists; no synthesis needed."
        fi
      done
    fi
  fi

  return "$run_failed"
}

for DVAL in "${DATES_TO_RUN[@]}"; do
  date_success=0
  ATTEMPT_MODES=("$NEEDS_SCRIPT_ARG")
  if [ "${ENABLE_ARG_MODE_FALLBACK:-1}" = "1" ]; then
    if [ "$NEEDS_SCRIPT_ARG" -eq 1 ]; then
      ATTEMPT_MODES+=(0)
    else
      ATTEMPT_MODES+=(1)
    fi
  fi

  for MODE in "${ATTEMPT_MODES[@]}"; do
    if run_one_execution "$DVAL" "$MODE"; then
      date_success=1
      break
    fi
    err "Execution attempt failed (date=${DVAL:-today} script_arg_mode=$MODE)"
  done

  if [ "$date_success" -ne 1 ]; then
    ANY_FAILURE=1
  fi
done

if [ $ANY_FAILURE -ne 0 ]; then
  err "One or more ingestion executions failed."
  exit 1
fi
log "All ingestion executions completed successfully."

# Optional: trigger BigQuery merge backfill for yesterday (uncomment to enable)
# if command -v python >/dev/null 2>&1; then
#   YESTERDAY=$(date -u -d 'yesterday' +%F)
#   PROJECT_ENV=${BQ_PROJECT:-$PROJECT_ID}
#   if [ -n "${PROJECT_ENV}" ]; then
#     echo "[run-job] (optional) Running merge backfill for $YESTERDAY"
#     python scripts/merge_sensor_readings.py \
#       --project "$PROJECT_ENV" \
#       --dataset sensors \
#       --date "$YESTERDAY" \
#       --auto-detect-staging \
#       --update-only-if-changed || echo "[run-job][warn] merge step failed (non-blocking)"
#   fi
# fi
