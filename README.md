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

```bash
export RECIPIENT_EMAIL="you@example.com"
export SENDER_EMAIL="you@example.com"
export ENABLED_SCRAPERS="rightmove"
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

## Future Work:

 - Make SES emails not be picked up as spam
 - Add openrent somehow potentially through proxy just no AWS IP
 - Add zoopla 
 - Add frontend and deploy this properly to a website
 - Add image recognition to filter out worse flats
 - Add text recognition of the summary to filter desired descriptions (garage, floor dimensions, garden, etc.)