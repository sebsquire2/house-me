#!/usr/bin/env bash
set -euo pipefail

# Pinned so a deploy cannot land in whatever account ambient credentials happen
# to point at — which is how this stack ended up in the Production account.
export AWS_PROFILE="${AWS_PROFILE:-services-admin}"

REGION="${AWS_REGION:-eu-west-2}"
STACK_NAME="house-me"
RECIPIENT_EMAIL="${RECIPIENT_EMAIL:?Set RECIPIENT_EMAIL in your environment}"
SENDER_EMAIL="${SENDER_EMAIL:-$RECIPIENT_EMAIL}"
ENABLED_SCRAPERS="${ENABLED_SCRAPERS:-rightmove}"
GMAIL_PASSWORD_PARAM="${GMAIL_PASSWORD_PARAM:-/house-me/gmail-app-password}"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
DEPLOY_BUCKET="house-me-deploy-$ACCOUNT_ID"

echo "==> Deploying to account $ACCOUNT_ID as profile $AWS_PROFILE"

# Fail before the deploy rather than at the first invocation. The secret lives
# in SSM, not in the template, so nothing else checks it exists.
echo "==> Checking $GMAIL_PASSWORD_PARAM exists..."
if ! aws ssm get-parameter --name "$GMAIL_PASSWORD_PARAM" \
     --region "$REGION" >/dev/null 2>&1; then
  echo "ERROR: SSM parameter $GMAIL_PASSWORD_PARAM not found in account $ACCOUNT_ID." >&2
  echo "Create it first:" >&2
  echo "  aws ssm put-parameter --name $GMAIL_PASSWORD_PARAM \\" >&2
  echo "    --value '<gmail app password>' --type SecureString --region $REGION" >&2
  exit 1
fi

echo "==> Creating deploy bucket if needed..."
aws s3 mb "s3://$DEPLOY_BUCKET" --region "$REGION" 2>/dev/null || true

echo "==> Building Lambda package..."
sam build \
  --template-file template.yaml \
  --build-dir .aws-sam/build

echo "==> Deploying stack..."
sam deploy \
  --template-file .aws-sam/build/template.yaml \
  --stack-name "$STACK_NAME" \
  --s3-bucket "$DEPLOY_BUCKET" \
  --region "$REGION" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    RecipientEmail="$RECIPIENT_EMAIL" \
    SenderEmail="$SENDER_EMAIL" \
    EnabledScrapers="$ENABLED_SCRAPERS" \
    GmailPasswordParam="$GMAIL_PASSWORD_PARAM" \
  --no-fail-on-empty-changeset

echo ""
echo "==> Done. Stack outputs:"
aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs" \
  --output table
