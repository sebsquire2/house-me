#!/usr/bin/env bash
set -euo pipefail

REGION="${AWS_REGION:-eu-west-2}"
STACK_NAME="house-me"
RECIPIENT_EMAIL="${RECIPIENT_EMAIL:?Set RECIPIENT_EMAIL in your environment}"
SENDER_EMAIL="${SENDER_EMAIL:-$RECIPIENT_EMAIL}"
ENABLED_SCRAPERS="${ENABLED_SCRAPERS:-rightmove}"
DEPLOY_BUCKET="house-me-deploy-$(aws sts get-caller-identity --query Account --output text)"

echo "==> Ensuring SES email is verified..."
aws ses verify-email-identity \
  --email-address "$SENDER_EMAIL" \
  --region "$REGION" 2>/dev/null || true

echo ""
echo "    Check your inbox and click the verification link from AWS if you haven't already."
echo "    Press Enter to continue once verified..."
read -r

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
  --no-fail-on-empty-changeset

echo ""
echo "==> Done. Stack outputs:"
aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs" \
  --output table
