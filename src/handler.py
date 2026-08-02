import logging
import os

import boto3

import dedup
import emailer
import rightmove
import openrent
import zoopla

# Lambda's runtime installs a root handler before user code runs, so
# basicConfig() is a no-op there and every logger.info() call is silently
# dropped. Set the level on the root logger explicitly instead.
logging.basicConfig(level=logging.INFO)
logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger(__name__)

BUCKET = os.environ["DEDUP_BUCKET"]
RECIPIENT = os.environ["RECIPIENT_EMAIL"]
SENDER = os.environ["SENDER_EMAIL"]
AWS_REGION = os.environ.get("AWS_REGION", "eu-west-1")

# Fetched at module level, so this is one SSM call per cold start rather than
# one per invocation. The secret is never passed through CloudFormation, which
# would leave it readable via cloudformation:GetTemplate.
GMAIL_APP_PASSWORD = boto3.client("ssm").get_parameter(
    Name=os.environ["GMAIL_PASSWORD_PARAM"], WithDecryption=True
)["Parameter"]["Value"]

SCRAPERS = {
    "rightmove": rightmove,
    "openrent": openrent,
    "zoopla": zoopla,
}


def _enabled_scrapers() -> list:
    raw = os.environ.get("ENABLED_SCRAPERS", "rightmove")
    names = [name.strip().lower() for name in raw.split(",") if name.strip()]
    enabled = []

    for name in names:
        scraper = SCRAPERS.get(name)
        if scraper is None:
            logger.warning("Unknown scraper '%s' in ENABLED_SCRAPERS, skipping", name)
            continue
        enabled.append(scraper)

    if not enabled:
        logger.warning("No valid scrapers enabled; defaulting to rightmove")
        return [rightmove]

    logger.info("Enabled scrapers: %s", ", ".join(scraper.__name__ for scraper in enabled))
    return enabled


def lambda_handler(event, context):
    seen = dedup.load_seen(BUCKET)
    logger.info("Loaded %d seen property IDs", len(seen))

    scrapers = _enabled_scrapers()
    all_properties = []
    for scraper in scrapers:
        try:
            props = scraper.scrape()
            all_properties.extend(props)
        except Exception as e:
            logger.error("Scraper %s failed: %s", scraper.__name__, e)

    logger.info("Scraped %d properties total", len(all_properties))
    new_properties = dedup.filter_new(all_properties, seen)
    logger.info("Found %d new properties", len(new_properties))

    sent = 0
    for prop in new_properties:
        try:
            emailer.send(prop, sender=SENDER, recipient=RECIPIENT, app_password=GMAIL_APP_PASSWORD)
            seen.add(prop.unique_id)
            sent += 1
        except Exception as e:
            logger.error("Failed to process %s: %s", prop.unique_id, e)

    if sent > 0:
        dedup.save_seen(BUCKET, seen)
        logger.info("Saved updated seen list (%d total)", len(seen))

    # "sent" and "found" are deliberately separate: a failed send leaves the
    # property unsaved, so reporting only the sent count makes a working
    # scraper with broken email look identical to a scraper returning nothing.
    return {
        "scraped": len(all_properties),
        "found_new": len(new_properties),
        "sent": sent,
        "total_seen": len(seen),
    }
