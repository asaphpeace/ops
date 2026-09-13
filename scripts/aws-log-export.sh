#!/usr/bin/env bash
# Exports real CloudWatch Logs events from one log group, for pasting into
# Engineering > Logs' import screen. Covers application/system logs, RDS
# logs, and VPC Flow Logs — all three are delivered through CloudWatch
# Logs, just to different log groups; pick the right "log_type" dropdown
# value in the UI to match what's actually in the group you export here.
#
# Usage: ./aws-log-export.sh <log-group-name> <region> [hours-back]
# Example: ./aws-log-export.sh /seatrans-prod/app eu-west-1 3

set -euo pipefail

if [ $# -lt 2 ]; then
  echo "Usage: $0 <log-group-name> <region> [hours-back]" >&2
  exit 1
fi

LOG_GROUP="$1"
REGION="$2"
HOURS_BACK="${3:-3}"

# macOS: swap for `date -u -v-${HOURS_BACK}H +%s`
START_MS=$(( $(date -u -d "-${HOURS_BACK} hours" +%s) * 1000 ))

SAFE_NAME=$(echo "$LOG_GROUP" | tr -c 'A-Za-z0-9' '_')
OUT="log-export-${SAFE_NAME}.json"

echo "Exporting events from $LOG_GROUP (last ${HOURS_BACK}h)..."
aws logs filter-log-events --region "$REGION" \
  --log-group-name "$LOG_GROUP" \
  --start-time "$START_MS" \
  --output json > "$OUT"

echo ""
echo "Done — $OUT"
echo "Paste it into Engineering > Logs, log group = '$LOG_GROUP', and pick the matching type (Application / RDS / VPC Flow)."
