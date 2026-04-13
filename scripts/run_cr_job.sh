#!/usr/bin/env bash
set -euo pipefail

# Require jq for JSON parsing (GitHub Actions runners include it by default)
if ! command -v jq >/dev/null 2>&1; then
  echo "[run-job][error] jq is required but not installed. Install jq and retry." >&2
  exit 10
fi

JOB_NAME=${JOB_NAME:-weather-data-uploader}

# Allow first non-flag arg to override job name for convenience
if [[ $# -gt 0 ]]; then
  case "$1" in
    -h|--help)
      echo "Usage: JOB_NAME=<name> REGION=<region> PROJECT_ID=<project> SOURCE=<all|wu|tsi> $0 [job-name]"; exit 0;;
    *) JOB_NAME="$1"; shift;;
  esac
fi
REGION=${REGION:-us-east1}
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
  echo "[run-job][error] Provide either DATE (single) or START_DATE/END_DATE, not both." >&2
  exit 9
fi

if { [ -n "$DATE_START" ] && [ -z "$DATE_END" ]; } || { [ -z "$DATE_START" ] && [ -n "$DATE_END" ]; }; then
  echo "[run-job][error] Both START_DATE and END_DATE must be provided for a range." >&2
  exit 9
fi

make_date_seq() {
  # Args: start end (YYYY-MM-DD) via DSTART/DEND env vars
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

# Build date list — portable (no mapfile, works on bash 3/4/5 and zsh)
DATES_TO_RUN=()
if [ -n "$DATE_SINGLE" ]; then
  DATES_TO_RUN=("$DATE_SINGLE")
elif [ -n "$DATE_START" ]; then
  export DSTART="$DATE_START" DEND="$DATE_END"
  while IFS= read -r _d; do
    DATES_TO_RUN+=("$_d")
  done < <(make_date_seq)
else
  # Default: collect yesterday so the full day's data is available in the TSI/WU APIs.
  # At midnight UTC the current day has only minutes of data; yesterday is complete.
  # Works on both Linux (date -d) and macOS (date -v).
  YESTERDAY=$(date -u -d 'yesterday' +%F 2>/dev/null || date -u -v-1d +%F)
  DATES_TO_RUN=("$YESTERDAY")
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

ANY_FAILURE=0
run_one_execution() {
  local dval="$1"   # YYYY-MM-DD, or empty to use container default

  # Pass the date via INGEST_DATE env var rather than --args.
  # Passing --args replaces the container CMD entirely (including the python interpreter
  # when the image uses CMD ["python", "script.py"] instead of ENTRYPOINT+CMD split),
  # which causes "Application exec likely failed" on images built before Oct 2025.
  # Using --update-env-vars avoids touching CMD/ENTRYPOINT at all.
  local env_pairs=""
  if [ -n "$dval" ]; then
    env_pairs="INGEST_DATE=$dval"
    log "Starting ingestion for date $dval"
  else
    log "Starting ingestion for default date (no override)"
  fi

  if [ "$SOURCE_FILTER" != "all" ]; then
    env_pairs="${env_pairs:+$env_pairs,}SOURCE=$SOURCE_FILTER"
  fi

  # Pass-through optional WU runtime tuning env vars for this execution.
  for wu_var in WU_ENDPOINT_STRATEGY WU_CONCURRENCY WU_MAX_RETRIES WU_RETRY_BASE_DELAY; do
    wu_val="${!wu_var:-}"
    if [ -n "$wu_val" ]; then
      env_pairs="${env_pairs:+$env_pairs,}${wu_var}=${wu_val}"
    fi
  done

  local -a execute_args=()
  if [ -n "$env_pairs" ]; then
    execute_args+=(--update-env-vars="$env_pairs")
  fi

  log "Executing Cloud Run job: $JOB_NAME in $REGION (project: $PROJECT_ID)"
  local exec_id
  exec_id=$(gcloud run jobs execute "$JOB_NAME" \
    --region "$REGION" \
    --project "$PROJECT_ID" \
    "${execute_args[@]}" \
    --format="value(metadata.name)" 2>/dev/null || true)
  if [ -z "$exec_id" ]; then
    err "Failed to start execution (date=${dval:-default})."
    return 1
  fi
  log "Started execution: $exec_id (date=${dval:-default})"

  local elapsed=0
  local run_failed=0
  while true; do
    local exec_json status_val last_msg failed_count succeeded_count active_count
    exec_json=$(gcloud run jobs executions describe "$exec_id" --region "$REGION" --project "$PROJECT_ID" --format="json" 2>/dev/null || echo "{}")
    status_val=$(echo "$exec_json" | jq -r '(.status.conditions[]? | select(.type=="Completed") | .status) // empty')
    last_msg=$(echo "$exec_json" | jq -r '(.status.conditions[]? | select(.type=="Completed") | .message) // empty')
    failed_count=$(echo "$exec_json" | jq -r '.failedCount // 0')
    succeeded_count=$(echo "$exec_json" | jq -r '.succeededCount // 0')
    active_count=$(echo "$exec_json" | jq -r '.runningCount // 0')
    log "Status(date=${dval:-default}): ${status_val:-unknown} ${last_msg} (t=${elapsed}s) failed=${failed_count} succeeded=${succeeded_count} running=${active_count}"
    if [ "$failed_count" -gt 0 ] && [ "$active_count" -eq 0 ] && [ "${status_val:-}" != "True" ]; then
      err "Detected failed tasks early (date=${dval:-default} failedCount=$failed_count)."
      run_failed=1
      break
    fi
    if [ "$status_val" = "True" ]; then
      local final_failed
      final_failed=$(echo "$exec_json" | jq -r '.failedCount // 0')
      if [ "${final_failed:-0}" -gt 0 ]; then
        err "Execution completed with failed tasks (date=${dval:-default} failedCount=$final_failed)."
        run_failed=1
      else
        log "Execution succeeded (date=${dval:-default})."
      fi
      break
    fi
    if [ "$status_val" = "False" ]; then
      err "Execution ended in failure state (date=${dval:-default}): $last_msg"
      run_failed=1
      break
    fi
    if [ $elapsed -ge $MAX_WAIT ]; then
      err "Timed out waiting for completion (date=${dval:-default}, $MAX_WAIT s)."
      run_failed=1
      break
    fi
    sleep $POLL_DELAY; elapsed=$((elapsed+POLL_DELAY))
  done

  log "Fetching last 200 log lines (date=${dval:-default})"
  local logs
  logs=$(gcloud logging read "resource.type=cloud_run_job AND resource.labels.execution_name=$exec_id" --project "$PROJECT_ID" --limit=200 --format="value(textPayload)" 2>/dev/null || true)
  if [ -z "$logs" ]; then
    logs=$(gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=$JOB_NAME" --project "$PROJECT_ID" --limit=50 --format="value(textPayload)" 2>/dev/null || true)
  fi
  if [ -n "$logs" ]; then
    echo "$logs"
  else
    log "No logs retrieved (date=${dval:-default})"
  fi

  # Fallback staging synthesis (only when a specific date was provided)
  if [ -n "${dval}" ]; then
    local date_compact="${dval//-/}"
    : "${BQ_DATASET:=sensors}"
    if [ -z "${GCS_BUCKET:-}" ] || [ -z "${GCS_PREFIX:-}" ]; then
      log "GCS_BUCKET or GCS_PREFIX not set; skipping fallback staging synthesis for $dval"
    else
      local src src_upper table uri
      for src in tsi wu; do
        table="staging_${src}_${date_compact}"
        if ! bq show --project_id="$PROJECT_ID" "${PROJECT_ID}:${BQ_DATASET}.${table}" >/dev/null 2>&1; then
          src_upper=$(echo "$src" | tr '[:lower:]' '[:upper:]')
          uri="gs://${GCS_BUCKET}/${GCS_PREFIX%/}/source=${src_upper}/agg=raw/dt=${dval}/*.parquet"
          log "Staging table ${table} missing; attempting load from ${uri}"
          if bq load \
            --project_id="$PROJECT_ID" \
            --autodetect \
            --source_format=PARQUET \
            "${BQ_DATASET}.${table}" \
            "${uri}" >/dev/null 2>&1; then
            log "Synthesized staging table ${table}"
          else
            log "Failed to synthesize staging table ${table} (URI may be empty)."
          fi
        else
          log "Staging table ${table} already exists; no synthesis needed."
        fi
      done
    fi
  fi

  return "$run_failed"
}

for DVAL in "${DATES_TO_RUN[@]}"; do
  if run_one_execution "$DVAL"; then
    true
  else
    err "Execution failed (date=${DVAL:-default})"
    ANY_FAILURE=1
  fi
done

if [ $ANY_FAILURE -ne 0 ]; then
  err "One or more ingestion executions failed."
  exit 1
fi
log "All ingestion executions completed successfully."
