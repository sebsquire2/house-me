import re
import time
import logging
import requests
from datetime import date, datetime, timezone
from dateutil import parser as date_parser
from typing import Optional

from models import Property

logger = logging.getLogger(__name__)

BASE_URL = "https://www.rightmove.co.uk"

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
}

# Rightmove OUTCODE IDs for target Bristol postcodes
LOCATIONS = {
    "BS6": 292,
    "BS7": 293,
    "BS16": 265,
}

SEARCH_PARAMS = {
    "minBedrooms": "1",
    "maxBedrooms": "3",
    "minPrice": "1000",
    "maxPrice": "1500",
    "propertyTypes": "flat",
    "sortType": "6",
}


def _get(url: str, **kwargs) -> requests.Response:
    resp = requests.get(url, headers=HEADERS, timeout=15, **kwargs)
    resp.raise_for_status()
    return resp


def _get_build_id() -> Optional[str]:
    # Fetch a concrete search page (BS6) to get the Next.js build ID
    url = (
        f"{BASE_URL}/property-to-rent/find.html"
        "?locationIdentifier=OUTCODE%5E292&minBedrooms=1&maxBedrooms=3"
        "&minPrice=1000&maxPrice=1500&propertyTypes=flat&sortType=6"
    )
    try:
        resp = _get(url)
        m = re.search(r'"buildId"\s*:\s*"([a-zA-Z0-9_-]+)"', resp.text)
        if m:
            return m.group(1)
        # Broader fallback pattern
        m = re.search(r'buildId[\":\s]+([a-zA-Z0-9_-]{10,})', resp.text)
        if m:
            return m.group(1)
        logger.warning("buildId not found in Rightmove HTML (len=%d)", len(resp.text))
    except Exception as e:
        logger.warning("Could not fetch Rightmove build ID: %s", e)
    return None


def _search_page(build_id: str, location_id: int, index: int) -> Optional[dict]:
    url = f"{BASE_URL}/_next/data/{build_id}/property-to-rent/find.html.json"
    params = {
        **SEARCH_PARAMS,
        "locationIdentifier": f"OUTCODE^{location_id}",
        "index": str(index),
    }
    try:
        resp = _get(url, params=params)
        data = resp.json()
        return data.get("pageProps", {}).get("searchResults", {})
    except Exception as e:
        logger.warning("Rightmove search failed (build_id=%s, loc=%d, idx=%d): %s", build_id, location_id, index, e)
        return None


def _parse_available_date_from_page(property_id: int) -> Optional[date]:
    """Fetch individual property page to extract available date when not in search results."""
    url = f"{BASE_URL}/properties/{property_id}"
    try:
        resp = _get(url)
        # Look for letAvailableDate in the Next.js data
        m = re.search(r'"letAvailableDate"\s*:\s*"([^"]+)"', resp.text)
        if m:
            return date_parser.parse(m.group(1)).date()
        # Fallback: look for "Let available date" label in HTML
        m = re.search(r'[Ll]et available date[^<]{0,50}<[^>]+>([^<]+)', resp.text)
        if m:
            return date_parser.parse(m.group(1).strip(), dayfirst=True).date()
    except Exception as e:
        logger.debug("Could not parse available date for property %d: %s", property_id, e)
    return None


def _parse_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    try:
        return date_parser.parse(raw).date()
    except Exception:
        return None


def _is_available_after_one_month(available: Optional[date]) -> bool:
    if available is None:
        return False
    from dateutil.relativedelta import relativedelta
    return available > date.today() + relativedelta(months=1)


def scrape() -> list[Property]:
    build_id = _get_build_id()
    if not build_id:
        logger.error("Rightmove: could not get build ID, skipping")
        return []

    logger.info("Rightmove build ID: %s", build_id)
    results = []
    seen_ids: set[int] = set()

    for outcode, location_id in LOCATIONS.items():
        logger.info("Scraping Rightmove %s (OUTCODE^%d)", outcode, location_id)
        index = 0

        while True:
            sr = _search_page(build_id, location_id, index)
            if not sr:
                break

            properties = sr.get("properties", [])
            if not properties:
                break

            for prop in properties:
                pid = prop.get("id")
                if not pid or pid in seen_ids:
                    continue
                seen_ids.add(pid)

                price = prop.get("price", {}).get("amount", 0)
                bedrooms = prop.get("bedrooms", 0)
                sub_type = prop.get("propertySubType", "").lower()
                address = prop.get("displayAddress", "")
                prop_url = BASE_URL + prop.get("propertyUrl", f"/properties/{pid}")
                prop_url = prop_url.split("#")[0]  # strip fragment

                # Filter here to avoid unnecessary page fetches
                if not (1000 <= price <= 1500):
                    continue
                if not (1 <= bedrooms <= 3):
                    continue
                if sub_type in ("studio",):
                    continue
                if prop.get("students") or prop.get("commercial"):
                    continue

                # Available date
                available_raw = prop.get("letAvailableDate")
                available_date = _parse_date(available_raw)

                if available_date is None:
                    time.sleep(0.5)
                    available_date = _parse_available_date_from_page(pid)

                if not _is_available_after_one_month(available_date):
                    continue

                results.append(Property(
                    source="rightmove",
                    property_id=str(pid),
                    url=prop_url,
                    address=address,
                    price_pcm=price,
                    bedrooms=bedrooms,
                    property_type=prop.get("propertySubType", "Flat"),
                    available_date=available_date,
                    available_date_raw=str(available_date) if available_date else "",
                ))

            pagination = sr.get("pagination", {})
            if not pagination.get("next"):
                break
            index += 24
            time.sleep(0.5)

    logger.info("Rightmove: %d matching properties", len(results))
    return results
