#!/bin/bash
# Daily Data Quality Monitoring Cron Job
# Runs check_data_quality.py to validate yesterday's sensor data
# 
# Installation:
#   1. Make executable: chmod +x /path/to/monitor_data_quality.sh
#   2. Add to crontab: crontab -e
#   3. Add this line (runs at 2 AM daily):
#      0 2 * * * /workspaces/durham-environmental-monitoring/scripts/monitor_data_quality.sh >> /workspaces/durham-environmental-monitoring/logs/quality_monitoring.log 2>&1
#
# Alternative: Deploy to Cloud Scheduler for production
#   See cloud_scheduler_config.yaml for Google Cloud setup

set -euo pipefail  # Exit on error

# Configuration
PROJECT_ROOT="/workspaces/durham-environmental-monitoring"
SCRIPT="$PROJECT_ROOT/scripts/check_data_quality.py"
LOG_DIR="$PROJECT_ROOT/logs"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/quality_check_$TIMESTAMP.log"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Set Python path
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# Log start
echo "=====================================" | tee -a "$LOG_FILE"
echo "Data Quality Check - $(date)" | tee -a "$LOG_FILE"
echo "=====================================" | tee -a "$LOG_FILE"

# Run quality check for yesterday's data
# Uses --fail-on-issues to exit with error code if problems found
python3 "$SCRIPT" \
    --days 1 \
    --source both \
    --dataset sensors \
    --fail-on-issues \
    2>&1 | tee -a "$LOG_FILE"

# Check exit status
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Quality check passed" | tee -a "$LOG_FILE"
else
    echo "❌ Quality check failed with exit code $EXIT_CODE" | tee -a "$LOG_FILE"
    
    # Optional: Send alert notification
    # Uncomment one of these based on your notification system:
    
    # Option 1: Email notification (requires sendmail/mail command)
    # echo "Data quality issues detected. Check logs: $LOG_FILE" | mail -s "Alert: Data Quality Check Failed" your-email@example.com
    
    # Option 2: Slack webhook
    # curl -X POST -H 'Content-type: application/json' \
    #   --data "{\"text\":\"⚠️ Data quality check failed. Check logs: $LOG_FILE\"}" \
    #   YOUR_SLACK_WEBHOOK_URL
    
    # Option 3: Microsoft Teams webhook
    # curl -H 'Content-Type: application/json' \
    #   -d "{\"text\":\"⚠️ Data quality check failed. Check logs: $LOG_FILE\"}" \
    #   YOUR_TEAMS_WEBHOOK_URL
fi

# Cleanup old logs (keep last 30 days)
find "$LOG_DIR" -name "quality_check_*.log" -type f -mtime +30 -delete

echo "=====================================" | tee -a "$LOG_FILE"
echo "Check complete - $(date)" | tee -a "$LOG_FILE"
echo "=====================================" | tee -a "$LOG_FILE"

exit $EXIT_CODE
