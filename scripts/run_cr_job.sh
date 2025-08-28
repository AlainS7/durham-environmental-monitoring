#!/usr/bin/env bash
set -euo pipefail

# Require jq for JSON parsing (GitHub Actions runners include it by default)
if ! command -v jq >/dev/null 2>&1; then
  echo "[run-job][error] jq is required but not installed. Install jq and retry." >&2
  exit 10
fi

JOB_NAME=${JOB_NAME:-weather-data-uploader}
REGION=${REGION:-us-east1}
DATE_SINGLE=${DATE:-${INGEST_DATE:-}}
DATE_START=${START_DATE:-}
DATE_END=${END_DATE:-}

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
  python - <<'PY'
import sys, datetime as dt, os
start=os.environ['DSTART']; end=os.environ['DEND']
sd=dt.date.fromisoformat(start); ed=dt.date.fromisoformat(end)
if ed < sd:
    print('range-invalid', file=sys.stderr); sys.exit(2)
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

log "Executing Cloud Run job: $JOB_NAME in $REGION (project: $PROJECT_ID)"
EXEC_ID=$(gcloud run jobs execute "$JOB_NAME" --region "$REGION" --project "$PROJECT_ID" --format="value(metadata.name)" 2>/dev/null || true)
if [ -z "$EXEC_ID" ]; then
  err "Failed to start execution (check IAM or job existence)."; exit 1
fi
log "Started execution: $EXEC_ID"

elapsed=0
while true; do
  EXECUTION_JSON=$(gcloud run jobs executions describe "$EXEC_ID" --region "$REGION" --project "$PROJECT_ID" --format="json" 2>/dev/null || echo "{}")
  STATUS=$(echo "$EXECUTION_JSON" | jq -r '(.status.conditions[]? | select(.type=="Completed") | .status) // empty')
  LASTMSG=$(echo "$EXECUTION_JSON" | jq -r '(.status.conditions[]? | select(.type=="Completed") | .message) // empty')
  FAILED_COUNT=$(echo "$EXECUTION_JSON" | jq -r '.failedCount // 0')
  SUCCEEDED_COUNT=$(echo "$EXECUTION_JSON" | jq -r '.succeededCount // 0')
  ACTIVE_COUNT=$(echo "$EXECUTION_JSON" | jq -r '.runningCount // 0')

  log "Status: ${STATUS:-unknown} ${LASTMSG} (t=${elapsed}s) failed=${FAILED_COUNT} succeeded=${SUCCEEDED_COUNT} running=${ACTIVE_COUNT}"
  # Early exit if tasks have failed and no tasks are running anymore but controller hasn't set Completed=False yet
  if [ "$FAILED_COUNT" -gt 0 ] && [ "$ACTIVE_COUNT" -eq 0 ] && [ "${STATUS:-}" != "True" ]; then
    err "Detected failed tasks before controller marked completion (failedCount=$FAILED_COUNT).";
    if [ "${DEBUG_EXECUTION_JSON:-}" = "1" ]; then
      echo "$EXECUTION_JSON" | jq '.' >&2 || true
    fi
    break
  fi
  if [ "$STATUS" = "True" ]; then
    # Check success vs failure count
    FAILED=$(echo "$EXECUTION_JSON" | jq -r '.failedCount // 0')
    if [ "${FAILED:-0}" -gt 0 ]; then
      err "Execution completed with failed tasks (failedCount=$FAILED).";
      if [ "${DEBUG_EXECUTION_JSON:-}" = "1" ]; then
        echo "$EXECUTION_JSON" | jq '.' >&2 || true
      fi
      exit 2
    fi
    log "Execution succeeded."; break
  fi
  if [ "$STATUS" = "False" ]; then
    err "Execution ended in failure state: $LASTMSG";
    if [ "${DEBUG_EXECUTION_JSON:-}" = "1" ]; then
      echo "$EXECUTION_JSON" | jq '.' >&2 || true
    fi
    exit 3
  fi
  if [ $elapsed -ge $MAX_WAIT ]; then
    err "Timed out waiting for completion ($MAX_WAIT s).";
    if [ "${DEBUG_EXECUTION_JSON:-}" = "1" ]; then
      echo "$EXECUTION_JSON" | jq '.' >&2 || true
    fi
    exit 4
  fi
  sleep $POLL_DELAY
  elapsed=$((elapsed+POLL_DELAY))
done

log "Fetching last 200 log lines (if available)"
gcloud logging read "resource.type=cloud_run_job AND resource.labels.execution_name=$EXEC_ID" --project "$PROJECT_ID" --limit=200 --format="value(textPayload)" 2>/dev/null || log "No logs retrieved"

log "Done."
ANY_FAILURE=0
for DVAL in "${DATES_TO_RUN[@]}"; do
  if [ -n "$DVAL" ]; then
    export INGEST_DATE="$DVAL"
    log "Starting ingestion for date $DVAL"
  else
    unset INGEST_DATE
    log "Starting ingestion for 'today' (no explicit date variable)"
  fi
  log "Executing Cloud Run job: $JOB_NAME in $REGION (project: $PROJECT_ID)"
  EXEC_ID=$(gcloud run jobs execute "$JOB_NAME" --region "$REGION" --project "$PROJECT_ID" --format="value(metadata.name)" 2>/dev/null || true)
  if [ -z "$EXEC_ID" ]; then
    err "Failed to start execution (date=$DVAL)."; ANY_FAILURE=1; continue
  fi
  log "Started execution: $EXEC_ID (date=$DVAL)"
  elapsed=0
  while true; do
    EXECUTION_JSON=$(gcloud run jobs executions describe "$EXEC_ID" --region "$REGION" --project "$PROJECT_ID" --format="json" 2>/dev/null || echo "{}")
    STATUS=$(echo "$EXECUTION_JSON" | jq -r '(.status.conditions[]? | select(.type=="Completed") | .status) // empty')
    LASTMSG=$(echo "$EXECUTION_JSON" | jq -r '(.status.conditions[]? | select(.type=="Completed") | .message) // empty')
    FAILED_COUNT=$(echo "$EXECUTION_JSON" | jq -r '.failedCount // 0')
    SUCCEEDED_COUNT=$(echo "$EXECUTION_JSON" | jq -r '.succeededCount // 0')
    ACTIVE_COUNT=$(echo "$EXECUTION_JSON" | jq -r '.runningCount // 0')
    log "Status(date=$DVAL): ${STATUS:-unknown} ${LASTMSG} (t=${elapsed}s) failed=${FAILED_COUNT} succeeded=${SUCCEEDED_COUNT} running=${ACTIVE_COUNT}"
    if [ "$FAILED_COUNT" -gt 0 ] && [ "$ACTIVE_COUNT" -eq 0 ] && [ "${STATUS:-}" != "True" ]; then
      err "Detected failed tasks early (date=$DVAL failedCount=$FAILED_COUNT)."; ANY_FAILURE=1; break
    fi
    if [ "$STATUS" = "True" ]; then
      FAILED=$(echo "$EXECUTION_JSON" | jq -r '.failedCount // 0')
      if [ "${FAILED:-0}" -gt 0 ]; then
        err "Execution completed with failed tasks (date=$DVAL failedCount=$FAILED)."; ANY_FAILURE=1
      else
        log "Execution succeeded (date=$DVAL)."
      fi
      break
    fi
    if [ "$STATUS" = "False" ]; then
      err "Execution ended in failure state (date=$DVAL): $LASTMSG"; ANY_FAILURE=1; break
    fi
    if [ $elapsed -ge $MAX_WAIT ]; then
      err "Timed out waiting for completion (date=$DVAL, $MAX_WAIT s)."; ANY_FAILURE=1; break
    fi
    sleep $POLL_DELAY; elapsed=$((elapsed+POLL_DELAY))
  done
  log "Fetching last 200 log lines (date=$DVAL)"
  gcloud logging read "resource.type=cloud_run_job AND resource.labels.execution_name=$EXEC_ID" --project "$PROJECT_ID" --limit=200 --format="value(textPayload)" 2>/dev/null || log "No logs retrieved (date=$DVAL)"
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
