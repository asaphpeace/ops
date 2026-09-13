#!/usr/bin/env bash
# Exports real EC2/RDS inventory + a CPU health snapshot from one AWS
# account, for pasting into Engineering > Infrastructure's import screen.
#
# Run once per AWS account/profile — "Old" and "New" are two separate
# accounts, so run this twice, switching AWS credentials/profile between
# runs (this script never touches or stores AWS credentials itself; it
# just uses whatever the AWS CLI already has active).
#
# Usage: ./aws-export.sh <old|new> <region>
# Example: AWS_PROFILE=sedna-old ./aws-export.sh old eu-west-1

set -euo pipefail

if [ $# -lt 2 ]; then
  echo "Usage: $0 <old|new> <region>" >&2
  exit 1
fi

ENV_LABEL="$1"
REGION="$2"
OUT="sentinel-aws-export-${ENV_LABEL}"
mkdir -p "$OUT"

echo "Exporting EC2 instances..."
aws ec2 describe-instances --region "$REGION" --output json > "$OUT/ec2.json"

echo "Exporting RDS instances..."
aws rds describe-db-instances --region "$REGION" --output json > "$OUT/rds.json"

echo "Exporting CPU health snapshot (last 3 hours, 5-min datapoints)..."
# macOS: swap the two `date` lines below for the -v-3H form, e.g.
#   START=$(date -u -v-3H +%Y-%m-%dT%H:%M:%S)
START=$(date -u -d '-3 hours' +%Y-%m-%dT%H:%M:%S)
END=$(date -u +%Y-%m-%dT%H:%M:%S)

echo "[" > "$OUT/cloudwatch.json"
FIRST=true

EC2_IDS=$(aws ec2 describe-instances --region "$REGION" \
  --query 'Reservations[].Instances[].InstanceId' --output text)
for iid in $EC2_IDS; do
  $FIRST || echo "," >> "$OUT/cloudwatch.json"
  FIRST=false
  STATS=$(aws cloudwatch get-metric-statistics --region "$REGION" \
    --namespace AWS/EC2 --metric-name CPUUtilization \
    --dimensions Name=InstanceId,Value="$iid" \
    --start-time "$START" --end-time "$END" --period 300 \
    --statistics Average Maximum --output json)
  echo "{\"resource_type\":\"EC2\",\"resource_id\":\"$iid\",\"data\":$STATS}" >> "$OUT/cloudwatch.json"
done

RDS_IDS=$(aws rds describe-db-instances --region "$REGION" \
  --query 'DBInstances[].DBInstanceIdentifier' --output text)
for did in $RDS_IDS; do
  $FIRST || echo "," >> "$OUT/cloudwatch.json"
  FIRST=false
  STATS=$(aws cloudwatch get-metric-statistics --region "$REGION" \
    --namespace AWS/RDS --metric-name CPUUtilization \
    --dimensions Name=DBInstanceIdentifier,Value="$did" \
    --start-time "$START" --end-time "$END" --period 300 \
    --statistics Average Maximum --output json)
  echo "{\"resource_type\":\"RDS\",\"resource_id\":\"$did\",\"data\":$STATS}" >> "$OUT/cloudwatch.json"
done

echo "]" >> "$OUT/cloudwatch.json"

echo ""
echo "Done — 3 files in $OUT/."
echo "Paste them into Engineering > Infrastructure, with environment set to '$ENV_LABEL'."
