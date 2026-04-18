"""Copilot handoff: prompt template display and markdown-table paste-back parser."""

import re
from datetime import date
from pathlib import Path
from typing import Optional

from core.base_calendar import BaseCalendar
from core.models import Event

_PROMPT_FILE = Path(__file__).parent.parent / "assets" / "copilot_prompt.md"

_MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_VALID_TYPES = {"WPR", "TEE", "Writ", "PS", "HW", "Quiz", "Lab", "Project", "Other"}

_DATE_RE = re.compile(
    r"(\d{1,2})\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"(?:\s+(\d{4}))?",
    re.IGNORECASE,
)
_WEIGHT_RE = re.compile(r"(\d{1,3}(?:\.\d{1,2})?)\s*%")
_LESSON_RE = re.compile(r"\bL(\d{1,3})\b", re.IGNORECASE)


def get_prompt() -> str:
    return _PROMPT_FILE.read_text(encoding="utf-8")


def _parse_date(text: str, calendar: BaseCalendar) -> Optional[date]:
    m = _DATE_RE.search(text)
    if not m:
        return None
    day = int(m.group(1))
    month = _MONTH_MAP.get(m.group(2).lower()[:3])
    if not month:
        return None
    year_str = m.group(3)
    if year_str:
        try:
            return date(int(year_str), month, day)
        except ValueError:
            return None
    # Infer year from calendar range
    cal_dates = sorted(calendar.days())
    if not cal_dates:
        return None
    for year in sorted({d.year for d in cal_dates}):
        try:
            candidate = date(year, month, day)
            if cal_dates[0] <= candidate <= cal_dates[-1]:
                return candidate
        except ValueError:
            pass
    return None


def _normalise_type(raw: str) -> str:
    raw = raw.strip().upper()
    for vt in _VALID_TYPES:
        if raw == vt.upper() or raw.startswith(vt.upper()):
            return vt
    return "Other"


def parse_copilot_table(
    md_text: str,
    course_code: str,
    calendar: BaseCalendar,
) -> list[Event]:
    """Parse a Copilot-generated markdown table and return Events.

    Expected columns (case-insensitive): Event Type | Event Name | Due Date |
    Lesson Reference | Weight (%).  Extra or missing columns are tolerated.
    """
    lines = [ln.strip() for ln in md_text.strip().splitlines()]

    # Find header row
    header_idx: Optional[int] = None
    for i, ln in enumerate(lines):
        if "|" in ln and re.search(r"event", ln, re.IGNORECASE):
            header_idx = i
            break
    if header_idx is None:
        return []

    headers = [h.strip().lower() for h in lines[header_idx].split("|") if h.strip()]

    def _find(keywords: list[str]) -> Optional[int]:
        for kw in keywords:
            for i, h in enumerate(headers):
                if kw in h:
                    return i
        return None

    type_col = _find(["event type", "type"])
    name_col = _find(["event name", "name"])
    date_col = _find(["due date", "date"])
    lesson_col = _find(["lesson", "ref"])
    weight_col = _find(["weight", "%"])

    events: list[Event] = []
    for ln in lines[header_idx + 2:]:  # skip separator
        if "|" not in ln:
            continue
        cells = [c.strip() for c in ln.split("|")]
        # strip empty leading/trailing caused by | at line edges
        cells = [c for c in cells if c != ""] if cells[0] == "" else cells
        if len(cells) < 2:
            continue

        def cell(idx: Optional[int]) -> str:
            if idx is None or idx >= len(cells):
                return ""
            return cells[idx].strip()

        et = _normalise_type(cell(type_col)) if type_col is not None else "Other"
        name = cell(name_col) or et
        raw_date = cell(date_col)
        lesson_ref_text = cell(lesson_col)
        weight_raw = cell(weight_col)

        d = _parse_date(raw_date, calendar) if raw_date and raw_date.upper() != "TBD" else None
        if d is None:
            continue

        weight: Optional[float] = None
        wm = _WEIGHT_RE.search(weight_raw)
        if wm:
            weight = float(wm.group(1))
        elif re.match(r"^\d{1,3}(?:\.\d{1,2})?$", weight_raw):
            # Plain number in weight column (no % sign)
            weight = float(weight_raw)

        lesson_ref: Optional[str] = None
        lm = _LESSON_RE.search(lesson_ref_text)
        if lm:
            lesson_ref = f"L{lm.group(1)}"

        events.append(Event(
            course_code=course_code,
            event_type=et,  # type: ignore[arg-type]
            title=name,
            date=d,
            lesson_ref=lesson_ref,
            weight_pct=weight,
            confidence=0.95,  # human-verified via Copilot
            source="copilot",
        ))

    return events
