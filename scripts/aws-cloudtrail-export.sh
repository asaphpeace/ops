#!/usr/bin/env bash
# Exports real CloudTrail management events (who-did-what against this
# AWS account), for pasting into Engineering > Logs' import screen.
#
# Usage: ./aws-cloudtrail-export.sh <region> [hours-back]
# Example: ./aws-cloudtrail-export.sh eu-west-1 24

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <region> [hours-back]" >&2
  exit 1
fi

REGION="$1"
HOURS_BACK="${2:-24}"

# macOS: swap for `date -u -v-${HOURS_BACK}H` / `date -u`
START=$(date -u -d "-${HOURS_BACK} hours" +%Y-%m-%dT%H:%M:%SZ)
END=$(date -u +%Y-%m-%dT%H:%M:%SZ)

OUT="cloudtrail-export.json"

echo "Exporting CloudTrail events for $REGION (last ${HOURS_BACK}h)..."
aws cloudtrail lookup-events --region "$REGION" \
  --start-time "$START" --end-time "$END" \
  --output json > "$OUT"

echo ""
echo "Done — $OUT"
echo "Paste it into Engineering > Logs, log_type = CloudTrail, log group = a label like '$REGION management events'."
