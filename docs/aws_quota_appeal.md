# AWS Quota Appeal — Case 177954942700187

Paste the block below (between the `---` lines) into the AWS Support
Console reply field at:
https://console.aws.amazon.com/support/home#/case/?displayId=177954942700187

Plain text — AWS strips markdown but renders line breaks fine.

Every factual claim has been verified true at time of drafting:
- AWS Budget `asl-pilot-monthly-cap` exists at $50/mo with email alerts at 80% and 100% forecast (verified via `aws budgets describe-budgets`)
- S3 bucket `asl-net3-data` exists in us-east-1 with PublicAccessBlock fully on (verified via `aws s3api get-public-access-block`)
- The launch script `scripts/aws_launch_net3.sh` sets `InstanceInitiatedShutdownBehavior=terminate` + `Type=one-time` (verified by grep)
- Zero EC2 instances launched on this account to date (verified via `aws ec2 describe-instances`)

---

Hello,

Thank you for the response. I would like to reopen this case with a more detailed use case.

PROJECT CONTEXT

I am building a personal research project: a browser-based American Sign Language (ASL) learning tool for a college ASL 1 class. The training run in question produces a hand-landmark detector (21 keypoints per hand) that will run on student webcams to evaluate sign-language hand shapes during practice. This is a personal/research project, not a commercial product.

SPECIFIC WORKLOAD

- Instance type: single g5.xlarge spot instance (4 vCPU, 1x NVIDIA A10G GPU, 16 GB RAM)
- Quota requested: 8 vCPU for "All G and VT Spot Instance Requests" in us-east-1. This gives headroom for one g5.xlarge plus a small margin. Minimum useful is 4 vCPU.
- Duration: approximately 15-20 hours of compute time, single one-time training run
- Framework: PyTorch training, approximately 250,000 image samples from public hand-pose research datasets (FreiHAND, RHD, InterHand2.6M)
- Storage: S3 bucket asl-net3-data already created in us-east-1 with PublicAccessBlock on; approximately 80 GB EBS attached to the instance for working data

ACCOUNT SAFETY MEASURES ALREADY IN PLACE

- AWS Budget "asl-pilot-monthly-cap" already created at USD 50 per month with email alerts at 80 percent (actual) and 100 percent (forecasted)
- Launch script enforces InstanceInitiatedShutdownBehavior=terminate so the instance self-destroys on shutdown rather than persisting EBS storage
- Launch script uses a one-time spot request type so the request does not auto-relaunch if interrupted
- IAM role asl-net3-spot-role uses minimum scope (only s3:PutObject, s3:GetObject, s3:ListBucket on asl-net3-data); no broader EC2 or IAM permissions on the instance
- Zero EC2 instances have been launched on this account to date; if approved, this would be the first

WHY AWS RATHER THAN A SMALLER ALTERNATIVE

I have intentionally requested the minimum quota for a single small GPU instance, not bulk capacity. I have already deployed two smaller training runs on Modal and Vast.ai for this same project. I only need AWS for this one longer-running job because spot pricing on g5.xlarge in us-east-1 is the most cost-effective option for the workload duration.

REQUEST

I would appreciate reconsideration of the 8 vCPU request. If 8 vCPU is too high for an initial approval, I would also accept 4 vCPU (exactly one g5.xlarge), which would be sufficient for this workload.

Thank you for your time.

Best regards,
Bryann

---

## How to actually send

1. Open the case URL above in browser.
2. Scroll to the bottom of the case where there is a Reply box / Add correspondence button.
3. Paste the block between the `---` markers.
4. Click Send. The case auto-reopens.

## Where the $50 budget lives

- AWS Console: https://us-east-1.console.aws.amazon.com/billing/home#/budgets
- Budget name: `asl-pilot-monthly-cap`
- Email alert goes to bryannalarcon@gmail.com when monthly spend hits 80% ($40) actual or 100% forecasted
