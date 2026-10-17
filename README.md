# house-me

AWS SAM app that scans rental listings and emails new matches.

## Problem:
Rightmove's filters don't allow you to search the date you want to move. The new UK renter's rights reforms mean people are likely to want to move 2 months in advance of today's date. This service sends you an email per property in your preferred areas every 5 minutes using a Lambda function on AWS (only one email per property total - you don't get spammed).

## What it does

- Scrapes supported property sources for Bristol rentals.
- Filters listings to the configured criteria in the scraper modules.
- Deduplicates seen listings in S3.
- Sends email alerts over Gmail SMTP.

## Current source status

- `rightmove`: enabled by default in AWS.
- `openrent`: code is included, but disabled by default for AWS because OpenRent blocks AWS IP ranges.
- `zoopla`: stubbed out and currently skipped because it is Cloudflare-protected.

## Deploy

Prerequisites:

- AWS CLI configured
- AWS SAM CLI installed
- A Gmail app password stored as an SSM SecureString. The function reads it at
  runtime, so it never passes through CloudFormation:

  ```bash
  aws ssm put-parameter --name /house-me/gmail-app-password \
    --value '<gmail app password>' --type SecureString --region eu-west-2
  ```

Put your settings in a `.env` file in the repo root (gitignored; `deploy.sh`
loads it automatically), or export them in your shell:

```bash
RECIPIENT_EMAIL="you@example.com"
SENDER_EMAIL="you@example.com"
ENABLED_SCRAPERS="rightmove"
```

```bash
./deploy.sh
```

`deploy.sh` defaults to the `services-admin` profile and checks the SSM
parameter exists before deploying. Override with `AWS_PROFILE=... ./deploy.sh`
if you genuinely mean a different account.

If you run outside AWS and have a network path that OpenRent accepts, you can opt in explicitly:

```bash
export ENABLED_SCRAPERS="rightmove,openrent"
```

## Notes

- The Lambda stores seen property IDs in an S3 bucket created by the stack.
- A property is only marked as seen once its email sends, so failed sends are
  retried on the next run rather than lost.

## Monitoring

The handler catches send failures, so the Lambda reports success (and zero
`Errors`) even when no email is going out. Instead, every failed run logs one
`Failed to send email` line, which a log metric filter counts as
`HouseMe/EmailSendFailures`. `EmailFailureAlarm` emails `RecipientEmail` via SNS
when there are 6+ failures in an hour (~half the runs), and again when it
recovers. On a new stack, confirm the SNS subscription email or no alerts arrive.

The function's return value (`scraped` / `found_new` / `sent`) is the quickest
health check: `aws lambda invoke --function-name <fn> out.json && cat out.json`.

## Troubleshooting

### Emails stopped / `Failed to send email` alarm

Most likely the Gmail app password has been revoked. **Changing your Google
account password revokes all app passwords.** This happened on 2026-10-04 and
went unnoticed until 2026-10-17 (before the alarm existed). Gmail tends to
report it as `Connection unexpectedly closed` or `421 Server busy` rather than
a clear auth error.

1. Create a new app password at https://myaccount.google.com/apppasswords.
2. Overwrite the SSM parameter (run in your own terminal so the secret stays
   out of logs and transcripts):

   ```bash
   aws ssm put-parameter --name /house-me/gmail-app-password \
     --value '<new app password>' --type SecureString --overwrite --region eu-west-2
   ```

3. Force a cold start. The password is read once per container, and the
   5-minute schedule keeps containers warm, so the old value sticks until then:

   ```bash
   aws lambda update-function-configuration --function-name <fn> \
     --region eu-west-2 --description "cold start $(date +%s)"
   ```

4. Invoke once and check `sent` matches `found_new`.

### Accounts and credentials

The stack lives in the `personal-services` account, eu-west-2,
deployed via the `services-admin` SSO profile (`aws sso login --profile
services-admin`). Ambient `AWS_ACCESS_KEY_ID`/`AWS_SESSION_TOKEN` env vars take
precedence over `AWS_PROFILE`, so check `aws sts get-caller-identity` before
deploying.

## Future Work:

 - Make SES emails not be picked up as spam
 - Add openrent somehow potentially through proxy just no AWS IP
 - Add zoopla 
 - Add frontend and deploy this properly to a website
 - Add image recognition to filter out worse flats
 - Add text recognition of the summary to filter desired descriptions (garage, floor dimensions, garden, etc.)