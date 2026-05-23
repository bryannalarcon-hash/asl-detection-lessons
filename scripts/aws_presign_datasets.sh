#!/usr/bin/env bash
# Emit bash export lines for S3-presigned dataset URLs, so a launcher can
# inject them into a remote training instance without shipping AWS creds.
#
# Usage:
#   source .env.local
#   eval "$(bash scripts/aws_presign_datasets.sh)"
#   # then start the launcher; it sees RHD_S3_PRESIGNED_URL + EGOHANDS_S3_PRESIGNED_TAR
#
# Expiration is bounded (default 24h) so leaked URLs become useless on
# their own.
set -euo pipefail

: "${AWS_ACCOUNT_ID:?AWS_ACCOUNT_ID not set; source .env.local first}"
BUCKET="${ASL_DATASETS_BUCKET:-asl-pilot-datasets-${AWS_ACCOUNT_ID}}"
EXPIRES="${PRESIGN_EXPIRES:-86400}"

aws_cli="aws"
if ! command -v aws >/dev/null 2>&1; then
    aws_cli="$HOME/.local/bin/aws"
fi

RHD_URL=$("$aws_cli" s3 presign "s3://${BUCKET}/rhd/RHD_published_v2.zip" --expires-in "$EXPIRES" 2>/dev/null || true)
EGOHANDS_URL=$("$aws_cli" s3 presign "s3://${BUCKET}/egohands/egohands_yolo.tar.gz" --expires-in "$EXPIRES" 2>/dev/null || true)

if [ -n "$RHD_URL" ]; then
    echo "export RHD_S3_PRESIGNED_URL='$RHD_URL'"
fi
if [ -n "$EGOHANDS_URL" ]; then
    echo "export EGOHANDS_S3_PRESIGNED_TAR='$EGOHANDS_URL'"
fi
