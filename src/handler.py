import logging
import os

import dedup
import emailer
import rightmove
import openrent
import zoopla

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BUCKET = os.environ["DEDUP_BUCKET"]
RECIPIENT = os.environ["RECIPIENT_EMAIL"]
SENDER = os.environ["SENDER_EMAIL"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
AWS_REGION = os.environ.get("AWS_REGION", "eu-west-1")

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

    return {"new_properties": sent, "total_seen": len(seen)}
