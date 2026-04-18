"""USMA academic calendar scraper (M6).

Attempts to fetch and parse the current AY calendar from the Dean's Office
publication. On any failure, returns None so the caller falls back to the
bundled JSON.

The fetch is intentionally non-blocking: a timeout of 8 seconds prevents the
app from hanging on slow or blocked networks (common on cadet networks).
"""

import json
import logging
import re
from datetime import date
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Primary URL — the Dean's Office publications landing page.
# Actual calendar PDFs are linked from here; we look for the AY PDF link.
_BASE_URL = "https://www.westpoint.edu/academics/academic-calendar"
_TIMEOUT = 8  # seconds

_MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def _parse_date(text: str, default_year: int) -> Optional[date]:
    """Parse common date formats found in USMA publications."""
    text = text.strip()
    # DD Mon YYYY or DD Mon
    m = re.search(
        r"(\d{1,2})\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"(?:\s+(\d{4}))?",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None
    day = int(m.group(1))
    month = _MONTH_MAP.get(m.group(2).lower()[:3])
    if not month:
        return None
    year = int(m.group(3)) if m.group(3) else default_year
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _extract_special_days(html: str, ay: str) -> Optional[dict]:
    """
    Try to extract key dates from the HTML page.

    Returns a partial JSON structure compatible with base_calendar._build_day_map,
    or None if extraction fails.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # Attempt to find the AY year from the tag e.g. "AY26"
    ay_match = re.search(r"AY(\d{2})", ay)
    if not ay_match:
        return None
    ay_year = 2000 + int(ay_match.group(1))
    sem = int(ay[-1])  # 1 or 2
    default_year = ay_year - 1 if sem == 1 else ay_year

    special: dict[str, dict] = {}

    # Look for holiday patterns in the text
    holiday_patterns = [
        (r"Labor Day[^\d]*(\d{1,2}\s+\w+(?:\s+\d{4})?)", "Labor Day"),
        (r"Columbus Day[^\d]*(\d{1,2}\s+\w+(?:\s+\d{4})?)", "Columbus Day"),
        (r"Veterans Day[^\d]*(\d{1,2}\s+\w+(?:\s+\d{4})?)", "Veterans Day"),
        (r"Thanksgiving[^\d]*(\d{1,2}\s+\w+(?:\s+\d{4})?)", "Thanksgiving"),
        (r"Martin Luther King[^\d]*(\d{1,2}\s+\w+(?:\s+\d{4})?)", "Martin Luther King Jr. Day"),
        (r"Presidents['']?\s*Day[^\d]*(\d{1,2}\s+\w+(?:\s+\d{4})?)", "Presidents Day"),
    ]

    for pattern, label in holiday_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            d = _parse_date(m.group(1), default_year)
            if d:
                special[d.isoformat()] = {"day_type": "holiday", "notes": [label]}

    if not special:
        return None  # Couldn't extract anything useful

    return {"special_days": special}


def fetch_calendar_updates(ay: str) -> Optional[dict]:
    """
    Try to fetch live calendar data for the given AY string (e.g. "AY26-2").

    Returns a dict of special-day overrides to merge with the bundled JSON,
    or None on any failure (network error, parse error, unexpected HTML).

    Callers MUST handle None gracefully.
    """
    try:
        resp = requests.get(_BASE_URL, timeout=_TIMEOUT, headers={"User-Agent": "CadetCal/1.0"})
        resp.raise_for_status()
        updates = _extract_special_days(resp.text, ay)
        if updates:
            logger.info("Scraped %d special days for %s", len(updates.get("special_days", {})), ay)
        return updates
    except requests.RequestException as exc:
        logger.warning("Calendar scrape failed (%s): %s", type(exc).__name__, exc)
        return None
    except Exception as exc:
        logger.warning("Calendar scrape parse error: %s", exc)
        return None
