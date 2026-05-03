import logging
from models import Property

logger = logging.getLogger(__name__)

# Zoopla returns Cloudflare bot-detection challenges to non-browser requests.
# Scraping requires a headless browser (Playwright) which significantly increases
# Lambda package size and cold start time. Skipped for now.


def scrape() -> list[Property]:
    logger.info("Zoopla scraper skipped (Cloudflare-protected)")
    return []
