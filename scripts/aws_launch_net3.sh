#!/usr/bin/env bash
# Launch a one-time AWS EC2 spot g5.xlarge in us-east-1 to train Net 3.
#
# Reads AWS creds + bucket from the environment. Source .env.local before
# running, or export the same names manually. We never echo secrets and
# fail fast when anything required is missing.
#
# Usage:
#   source .env.local
#   bash scripts/aws_launch_net3.sh                   # default config
#   CONFIG=configs/stage1_v3_landmark_v1.yaml \
#     MAX_PRICE=0.50 \
#     bash scripts/aws_launch_net3.sh
#
# Exits with the spot request ID + instance ID printed to stdout. The
# instance bootstraps itself via user-data — we do not block here.
#
# Safety:
#   - hard fails on missing creds
#   - never prints AWS_SECRET_ACCESS_KEY
#   - traps CTRL+C / ERR and cancels the spot request if interrupted
#     mid-launch, so a CTRL+C never leaves a stuck request paying.
#
# IAM (one-time setup the launcher performs idempotently):
#   - role `asl-net3-spot-role` with EC2 trust policy
#   - inline policy granting s3:PutObject,GetObject,ListBucket on
#     arn:aws:s3:::${BUCKET_NAME} and arn:aws:s3:::${BUCKET_NAME}/*
#   - instance profile of the same name, role attached
# Requires the launching IAM principal to hold iam:CreateRole,
# iam:PutRolePolicy, iam:CreateInstanceProfile, iam:AddRoleToInstanceProfile,
# iam:GetRole, iam:GetInstanceProfile, iam:PassRole on the role ARN. If
# those perms aren't available, pre-create the role out of band and the
# launcher's idempotent block will detect it and continue.
set -euo pipefail
set -o pipefail

# Keep our locally-installed aws CLI ahead of any system one.
export PATH="$HOME/.local/bin:$PATH"

AWS="${AWS_CLI:-$(command -v aws || true)}"
if [ -z "${AWS}" ] || [ ! -x "${AWS}" ]; then
    echo "FATAL: aws CLI not on PATH. Install with: pip install --user awscli" >&2
    exit 2
fi

REGION="${AWS_REGION:-us-east-1}"
INSTANCE_TYPE="${INSTANCE_TYPE:-g5.xlarge}"
MAX_PRICE="${MAX_PRICE:-0.50}"
CONFIG="${CONFIG:-configs/stage1_v3_landmark_v1.yaml}"
BUCKET_NAME="${BUCKET_NAME:-asl-net3-data}"
KEY_NAME="${KEY_NAME:-}"           # optional EC2 keypair for ssh-in
SECURITY_GROUP="${SECURITY_GROUP:-}"  # optional; if set, attached to the launch

# Deep Learning Base GPU AMI (Ubuntu 22.04, NVIDIA drivers preinstalled).
# Specific AMI per region; us-east-1 default is overridable via env.
AMI_ID="${AMI_ID:-ami-0a7d80731ae1b2435}"

required_env=(AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY)
missing=()
for v in "${required_env[@]}"; do
    if [ -z "${!v:-}" ]; then missing+=("$v"); fi
done
if [ "${#missing[@]}" -gt 0 ]; then
    echo "FATAL: missing required env: ${missing[*]}" >&2
    echo "Source .env.local first." >&2
    exit 2
fi
export AWS_DEFAULT_REGION="${REGION}"

if [ ! -f "${CONFIG}" ]; then
    echo "FATAL: config not found: ${CONFIG}" >&2
    exit 2
fi

# Optional: repo zip on S3 the spot instance pulls down. We accept a URI
# or build one on the fly from the current tree. Building on the fly
# keeps the launcher self-contained.
REPO_ZIP_S3="${REPO_ZIP_S3:-s3://${BUCKET_NAME}/bootstrap/repo.zip}"

echo "[launch] region=${REGION} ami=${AMI_ID} type=${INSTANCE_TYPE} max-price=${MAX_PRICE}"
echo "[launch] config=${CONFIG} bucket=${BUCKET_NAME} repo_zip=${REPO_ZIP_S3}"

# Confirm credentials work without echoing them.
caller=$("${AWS}" sts get-caller-identity --query Arn --output text 2>/dev/null || true)
if [ -z "${caller}" ]; then
    echo "FATAL: aws sts get-caller-identity failed; check creds." >&2
    exit 3
fi
echo "[launch] iam=${caller}"

# 1. Bucket — idempotent create. us-east-1 must omit LocationConstraint.
if "${AWS}" s3api head-bucket --bucket "${BUCKET_NAME}" >/dev/null 2>&1; then
    echo "[s3] bucket ${BUCKET_NAME} already exists"
else
    echo "[s3] creating bucket ${BUCKET_NAME}"
    if [ "${REGION}" = "us-east-1" ]; then
        "${AWS}" s3api create-bucket --bucket "${BUCKET_NAME}" --region "${REGION}" >/dev/null
    else
        "${AWS}" s3api create-bucket --bucket "${BUCKET_NAME}" --region "${REGION}" \
            --create-bucket-configuration "LocationConstraint=${REGION}" >/dev/null
    fi
    "${AWS}" s3api put-bucket-versioning --bucket "${BUCKET_NAME}" \
        --versioning-configuration Status=Enabled >/dev/null || true
fi

# Block all public access on the bucket. Idempotent — safe to re-apply.
"${AWS}" s3api put-public-access-block --bucket "${BUCKET_NAME}" \
    --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" >/dev/null

# 1b. IAM role + instance profile so the spot instance can read the repo
# zip and write checkpoints without us embedding AWS keys in user-data
# or the repo zip. Idempotent: each step checks existence first.
ROLE_NAME="${ROLE_NAME:-asl-net3-spot-role}"
PROFILE_NAME="${PROFILE_NAME:-asl-net3-spot-role}"

TRUST_DOC=$(mktemp)
cat > "${TRUST_DOC}" <<'TRUST'
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow",
     "Principal": {"Service": "ec2.amazonaws.com"},
     "Action": "sts:AssumeRole"}
  ]
}
TRUST

S3_DOC=$(mktemp)
cat > "${S3_DOC}" <<S3POLICY
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow",
     "Action": ["s3:PutObject", "s3:GetObject"],
     "Resource": "arn:aws:s3:::${BUCKET_NAME}/*"},
    {"Effect": "Allow",
     "Action": ["s3:ListBucket"],
     "Resource": "arn:aws:s3:::${BUCKET_NAME}"}
  ]
}
S3POLICY

if "${AWS}" iam get-role --role-name "${ROLE_NAME}" >/dev/null 2>&1; then
    echo "[iam] role ${ROLE_NAME} exists"
else
    echo "[iam] creating role ${ROLE_NAME}"
    "${AWS}" iam create-role --role-name "${ROLE_NAME}" \
        --assume-role-policy-document "file://${TRUST_DOC}" >/dev/null
fi

"${AWS}" iam put-role-policy --role-name "${ROLE_NAME}" \
    --policy-name "asl-net3-s3-access" \
    --policy-document "file://${S3_DOC}" >/dev/null

if "${AWS}" iam get-instance-profile --instance-profile-name "${PROFILE_NAME}" >/dev/null 2>&1; then
    echo "[iam] instance profile ${PROFILE_NAME} exists"
else
    echo "[iam] creating instance profile ${PROFILE_NAME}"
    "${AWS}" iam create-instance-profile --instance-profile-name "${PROFILE_NAME}" >/dev/null
fi

# Attach role to profile if not already attached. add-role-to-instance-profile
# errors with LimitExceeded if the profile already has a role, so we check.
ATTACHED_ROLE=$("${AWS}" iam get-instance-profile \
    --instance-profile-name "${PROFILE_NAME}" \
    --query 'InstanceProfile.Roles[0].RoleName' --output text 2>/dev/null || true)
if [ "${ATTACHED_ROLE}" != "${ROLE_NAME}" ]; then
    echo "[iam] attaching role ${ROLE_NAME} to profile ${PROFILE_NAME}"
    "${AWS}" iam add-role-to-instance-profile \
        --instance-profile-name "${PROFILE_NAME}" \
        --role-name "${ROLE_NAME}" >/dev/null
    # IAM is eventually consistent; the spot launch can race the profile
    # propagation. Short sleep beats a launch retry.
    sleep 8
fi

rm -f "${TRUST_DOC}" "${S3_DOC}"

# 2. Repo zip — build and upload if it's missing or older than the working tree.
WORK_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ZIP_TMP="$(mktemp -d)/repo.zip"
trap 'rm -rf "$(dirname "${ZIP_TMP}")"' EXIT

echo "[s3] packaging repo (excluding secrets, data, results, venv, git)"
( cd "${WORK_ROOT}" && zip -qr "${ZIP_TMP}" . \
    -x '.env*' '.env.local' '.env.*.local' \
       '.git/*' 'data/*' 'results/*' \
       '.venv/*' 'venv/*' '*/__pycache__/*' \
       'design/*' 'node_modules/*' '*.pt' '*.pth' \
       'logs/*' 'checkpoints/*' 'costs/*' )
echo "[s3] uploading repo zip ($(du -h "${ZIP_TMP}" | cut -f1)) → ${REPO_ZIP_S3}"
"${AWS}" s3 cp "${ZIP_TMP}" "${REPO_ZIP_S3}" --only-show-errors

# 3. User-data script the spot instance runs on first boot.
# We do NOT inline AWS creds. Instead we use the launch IAM instance
# profile if available, else we drop a minimal credentials file via SSM
# Parameter Store at runtime (admin sets the parameter once, out of band).
USER_DATA_FILE="$(mktemp)"
trap 'rm -f "${USER_DATA_FILE}"; rm -rf "$(dirname "${ZIP_TMP}")"' EXIT

cat > "${USER_DATA_FILE}" <<USERDATA
#!/usr/bin/env bash
set -euo pipefail
exec > /var/log/net3-launch.log 2>&1

REGION="${REGION}"
BUCKET="${BUCKET_NAME}"
REPO_ZIP="${REPO_ZIP_S3}"
CONFIG="${CONFIG}"

apt-get update -y
apt-get install -y -qq unzip awscli python3-pip git curl

mkdir -p /opt/net3 && cd /opt/net3
aws s3 cp "\${REPO_ZIP}" /opt/net3/repo.zip --region "\${REGION}"
unzip -q /opt/net3/repo.zip -d /opt/net3/repo
cd /opt/net3/repo

# Patch the config so S3 sync is on with the right bucket.
python3 - <<'PYEOF'
import os, yaml, pathlib
cfg_path = pathlib.Path(os.environ["CONFIG"])
cfg = yaml.safe_load(cfg_path.read_text()) or {}
cfg.setdefault("train", {})["s3_bucket"] = os.environ["BUCKET"]
cfg["train"].setdefault("s3_prefix", "net3/checkpoints")
cfg["train"].setdefault("s3_sync_every", 10)
cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False))
PYEOF

# Deps.
pip3 install -q -r requirements.txt
pip3 install -q boto3 awscli

# Datasets — uses the existing download script. KAGGLE_* must be set
# via SSM Parameter Store or wired at AMI build time. The repo zip
# intentionally excludes .env* so no credentials ship with the bootstrap.
DATA_DIR=data bash scripts/download_v3_data.sh || true

# Kick training. nohup so the SSM/SSH session can detach.
mkdir -p logs
nohup python3 -u -m src.stage1.train_v3_landmark \
    --config "\${CONFIG}" > logs/train_v3_landmark.log 2>&1 &
echo \$! > /opt/net3/train.pid
USERDATA

# Encode user-data as base64 for the spot request.
USER_DATA_B64=$(base64 -w0 "${USER_DATA_FILE}")

# 4. Build the launch specification.
LAUNCH_SPEC=$(mktemp)
trap 'rm -f "${LAUNCH_SPEC}" "${USER_DATA_FILE}"; rm -rf "$(dirname "${ZIP_TMP}")"' EXIT
cat > "${LAUNCH_SPEC}" <<JSON
{
  "ImageId": "${AMI_ID}",
  "InstanceType": "${INSTANCE_TYPE}",
  "UserData": "${USER_DATA_B64}",
  "InstanceInitiatedShutdownBehavior": "terminate",
  "IamInstanceProfile": {"Name": "${PROFILE_NAME}"},
  "BlockDeviceMappings": [
    {
      "DeviceName": "/dev/sda1",
      "Ebs": {"VolumeSize": 300, "VolumeType": "gp3", "DeleteOnTermination": true}
    }
  ]
JSON
if [ -n "${KEY_NAME}" ]; then
    sed -i 's/]$/],/' "${LAUNCH_SPEC}"
    echo "  ,\"KeyName\": \"${KEY_NAME}\"" >> "${LAUNCH_SPEC}"
fi
if [ -n "${SECURITY_GROUP}" ]; then
    sed -i '$ s/]$/],/' "${LAUNCH_SPEC}" 2>/dev/null || true
    echo "  ,\"SecurityGroupIds\": [\"${SECURITY_GROUP}\"]" >> "${LAUNCH_SPEC}"
fi
echo "}" >> "${LAUNCH_SPEC}"

# 5. Submit the spot request.
SPOT_REQ_ID=""
cleanup_spot() {
    if [ -n "${SPOT_REQ_ID}" ]; then
        echo "" >&2
        echo "[abort] cancelling spot request ${SPOT_REQ_ID}" >&2
        "${AWS}" ec2 cancel-spot-instance-requests \
            --spot-instance-request-ids "${SPOT_REQ_ID}" \
            --region "${REGION}" >/dev/null 2>&1 || true
    fi
}
trap 'cleanup_spot; rm -f "${LAUNCH_SPEC}" "${USER_DATA_FILE}"; rm -rf "$(dirname "${ZIP_TMP}")"' INT ERR

echo "[launch] requesting spot ${INSTANCE_TYPE} (one-time, max=${MAX_PRICE} USD/hr)"
SPOT_REQ_ID=$("${AWS}" ec2 request-spot-instances \
    --region "${REGION}" \
    --spot-price "${MAX_PRICE}" \
    --instance-count 1 \
    --type one-time \
    --launch-specification "file://${LAUNCH_SPEC}" \
    --query 'SpotInstanceRequests[0].SpotInstanceRequestId' \
    --output text)

if [ -z "${SPOT_REQ_ID}" ] || [ "${SPOT_REQ_ID}" = "None" ]; then
    echo "FATAL: spot request did not return an ID" >&2
    exit 4
fi
echo "[launch] spot request: ${SPOT_REQ_ID}"

# 6. Wait briefly for fulfillment so we can print the InstanceId. Cap the
# poll at 60s — if it hasn't matched in a minute, return the request ID
# and let the user check with `aws ec2 describe-spot-instance-requests`.
INSTANCE_ID=""
for i in $(seq 1 30); do
    STATE=$("${AWS}" ec2 describe-spot-instance-requests \
        --region "${REGION}" \
        --spot-instance-request-ids "${SPOT_REQ_ID}" \
        --query 'SpotInstanceRequests[0].[State,Status.Code,InstanceId]' \
        --output text)
    STATUS_CODE=$(echo "${STATE}" | awk '{print $2}')
    INSTANCE_ID=$(echo "${STATE}" | awk '{print $3}')
    if [ "${INSTANCE_ID}" != "None" ] && [ -n "${INSTANCE_ID}" ]; then
        break
    fi
    case "${STATUS_CODE}" in
        capacity-not-available|price-too-low|constraint-not-fulfillable|bad-parameters)
            echo "FATAL: spot request unfulfilled: ${STATUS_CODE}" >&2
            "${AWS}" ec2 cancel-spot-instance-requests \
                --region "${REGION}" \
                --spot-instance-request-ids "${SPOT_REQ_ID}" >/dev/null || true
            exit 5
            ;;
    esac
    sleep 2
done

# Clear the abort trap — past this point the spot is healthy and we don't
# want CTRL+C from a follow-on shell to kill it.
trap 'rm -f "${LAUNCH_SPEC}" "${USER_DATA_FILE}"; rm -rf "$(dirname "${ZIP_TMP}")"' INT ERR EXIT

echo ""
echo "================================================================"
echo "  Spot request: ${SPOT_REQ_ID}"
echo "  Instance:     ${INSTANCE_ID:-<pending>}"
echo "  Region:       ${REGION}"
echo "  Bucket:       s3://${BUCKET_NAME}/net3/checkpoints/"
echo "  Tail logs:    aws ec2 get-console-output --instance-id ${INSTANCE_ID}"
echo "  Cancel:       aws ec2 cancel-spot-instance-requests \\"
echo "                  --spot-instance-request-ids ${SPOT_REQ_ID}"
echo "================================================================"
