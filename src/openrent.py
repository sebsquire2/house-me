import re
import time
import logging
import requests
from datetime import date
from dateutil import parser as date_parser
from typing import Optional

from models import Property

logger = logging.getLogger(__name__)

BASE_URL = "https://www.openrent.co.uk"
SEARCH_URL = BASE_URL + "/properties-to-rent/bristol"
PAGE_SIZE = 20

# OpenRent blocks requests from AWS IP ranges, so this scraper is intended for
# local runs or non-AWS environments where the site is reachable.

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
    "Referer": BASE_URL,
}

SEARCH_PARAMS = {
    "term": "bristol",
    "prices_min": "1000",
    "prices_max": "1500",
    "bedrooms_min": "1",
    "bedrooms_max": "3",
    "isLive": "true",
}

# Target BS6, BS7, BS16 — filter out others (Bristol search returns all of Bristol)
ALLOWED_POSTCODE = re.compile(r"\b(BS6|BS7|BS16)\b", re.IGNORECASE)


def _get(url: str, **kwargs) -> requests.Response:
    resp = requests.get(url, headers=HEADERS, timeout=15, **kwargs)
    resp.raise_for_status()
    return resp


def _parse_cards(html: str) -> list[dict]:
    """Extract basic property data from search result cards."""
    results = []
    # Each property card is an <a> tag with class pli
    for m in re.finditer(
        r'<a\s+href="(/property-to-rent/[^"]+/(\d+))"\s+class="pli[^"]*".*?</a>\s*(?=<a\s+href="/property-to-rent|$)',
        html,
        re.DOTALL,
    ):
        card_html = m.group(0)
        pid = m.group(2)
        url_path = m.group(1)

        # Price
        price_m = re.search(r'&#xA3;([\d,]+)</span>\s*<span[^>]*>per month', card_html)
        price = int(price_m.group(1).replace(",", "")) if price_m else 0

        # Bedrooms from "N Beds" list item
        beds_m = re.search(r"(\d+)\s*Bed", card_html)
        bedrooms = int(beds_m.group(1)) if beds_m else 0

        # Address/title from the card title div
        addr_m = re.search(r'class="fw-medium text-primary fs-3">([^<]+)<', card_html)
        address = addr_m.group(1).strip() if addr_m else ""

        # Postcode check — address usually ends with postcode e.g. "1 Bed Flat, Redland, BS6"
        postcode_m = re.search(r"\b(BS\d{1,2})\b", address, re.IGNORECASE)
        postcode = postcode_m.group(1).upper() if postcode_m else ""

        results.append({
            "id": pid,
            "url": BASE_URL + url_path,
            "price": price,
            "bedrooms": bedrooms,
            "address": address,
            "postcode": postcode,
        })

    return results


def _parse_date(raw: str) -> Optional[date]:
    if not raw:
        return None
    raw = raw.strip()
    if re.search(r"now|immediately|asap", raw, re.IGNORECASE):
        return date.today()
    try:
        return date_parser.parse(raw, dayfirst=True).date()
    except Exception:
        return None


def _get_available_date(property_url: str) -> tuple[Optional[date], str]:
    """Fetch individual property page to get available date."""
    try:
        resp = _get(property_url)
        html = resp.text

        # Look for "Available From" or "Available" label followed by a date
        for pattern in [
            r'[Aa]vailable\s+[Ff]rom[^<]{0,20}<[^>]+>\s*([^<]+)',
            r'[Aa]vailable[^<]{0,30}<[^>]+>\s*([^<]+)',
            r'(?:available|from)[:\s]+(\d{1,2}\s+\w+\s+\d{4}|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})',
        ]:
            m = re.search(pattern, html, re.IGNORECASE)
            if m:
                raw = m.group(1).strip()
                if re.search(r'\d', raw):
                    parsed = _parse_date(raw)
                    if parsed:
                        return parsed, raw

        # Check for "now" / "immediately"
        if re.search(r'[Aa]vailable\s+[Nn]ow|[Ii]mmediately', html):
            return date.today(), "Now"

    except Exception as e:
        logger.debug("Could not fetch available date for %s: %s", property_url, e)

    return None, ""


def _is_available_after_one_month(available: Optional[date]) -> bool:
    if available is None:
        return False
    from dateutil.relativedelta import relativedelta
    return available > date.today() + relativedelta(months=1)


def scrape() -> list[Property]:
    results = []
    seen_ids: set[str] = set()
    skip = 0

    while True:
        params = {**SEARCH_PARAMS, "skip": str(skip)}
        try:
            resp = _get(SEARCH_URL, params=params)
        except Exception as e:
            logger.warning("OpenRent search failed at skip=%d: %s", skip, e)
            break

        cards = _parse_cards(resp.text)
        if not cards:
            break

        for card in cards:
            pid = card["id"]
            if pid in seen_ids:
                continue
            seen_ids.add(pid)

            if not (1000 <= card["price"] <= 1500):
                continue
            if not (1 <= card["bedrooms"] <= 3):
                continue

            # Location filter: must mention BS6, BS7, or BS16 in address
            if not ALLOWED_POSTCODE.search(card["address"]):
                continue

            time.sleep(0.5)
            available_date, available_raw = _get_available_date(card["url"])

            if not _is_available_after_one_month(available_date):
                continue

            results.append(Property(
                source="openrent",
                property_id=pid,
                url=card["url"],
                address=card["address"],
                price_pcm=card["price"],
                bedrooms=card["bedrooms"],
                property_type="Flat",
                available_date=available_date,
                available_date_raw=available_raw,
            ))

        if len(cards) < PAGE_SIZE:
            break
        skip += PAGE_SIZE

    logger.info("OpenRent: %d matching properties", len(results))
    return results
