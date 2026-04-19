#!/usr/bin/env python3
"""
Parse the USMA Buff Card HTML and regenerate AY26-1.json and AY26-2.json.

Usage:
    python data/base_calendars/parse_buff_card.py

Reads:  data/base_calendars/Buff Card Full Year Layout.html
Writes: data/base_calendars/AY26-1.json
        data/base_calendars/AY26-2.json
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("BeautifulSoup4 is required: pip install beautifulsoup4")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = Path(__file__).parent
HTML_FILE = HERE / "Buff Card Full Year Layout.html"

MONTH_MAP = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4,
    "MAY": 5, "JUNE": 6, "JULY": 7, "AUGUST": 8,
    "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
}

# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------

def _cell_text(el) -> str:
    return el.get_text(" ", strip=True) if el else ""


def parse_html(html_path: Path) -> dict[date, dict]:
    """Return {date: {"class_num": str|None, "notes": str, "col": int}} for every cell with a day number."""
    soup = BeautifulSoup(html_path.read_bytes(), "html.parser")

    # Each month is introduced by a <div> with month name then a <table>
    # Strategy: find all text nodes that look like "MONTH YYYY", then grab
    # the next sibling table.
    days: dict[date, dict] = {}

    # Collect (month_div, table) pairs
    month_pattern = re.compile(r"\b([A-Z]+)\s+(\d{4})\b")

    for div in soup.find_all("div", style=lambda s: s and "font-size:20pt" in s):
        text = div.get_text(strip=True)
        m = month_pattern.search(text)
        if not m:
            continue
        month_name, year = m.group(1), int(m.group(2))
        month_num = MONTH_MAP.get(month_name)
        if not month_num:
            continue

        # Next sibling table
        table = div.find_next_sibling("table")
        if not table:
            continue

        rows = table.find_all("tr")
        # First row is the Sun/Mon/.../Sat header — skip it
        for row in rows[1:]:
            cells = row.find_all("td")
            for col_idx, td in enumerate(cells):
                # Day number span: font-size: 10pt; font-weight:bold; color:black
                day_span = td.find("span", style=lambda s: s and "color:black" in s)
                if not day_span:
                    continue
                day_text = day_span.get_text(strip=True)
                if not day_text.isdigit():
                    continue
                day_num = int(day_text)

                try:
                    d = date(year, month_num, day_num)
                except ValueError:
                    continue

                # Inner div holds class number + notes spans
                inner_div = td.find("div")
                class_num: str | None = None
                notes = ""

                if inner_div:
                    spans = inner_div.find_all("span")
                    # Span 0: class number (font-size:10pt bold)
                    # Span 1: second track class number (usually empty)
                    # Span 2: notes (font-size:8pt)
                    if len(spans) >= 1:
                        raw = spans[0].get_text(strip=True)
                        if re.match(r"[12]-\d+", raw):
                            class_num = raw
                    if len(spans) >= 3:
                        notes = spans[2].get_text(strip=True)
                    elif len(spans) >= 2:
                        # sometimes only 2 spans
                        raw2 = spans[-1].get_text(strip=True)
                        if raw2 and not re.match(r"[12]-\d+", raw2):
                            notes = raw2

                days[d] = {"class_num": class_num, "notes": notes, "col": col_idx}

    return days


# ---------------------------------------------------------------------------
# Classify days
# ---------------------------------------------------------------------------

def classify(info: dict) -> str:
    """Return day_type string: '1','2','holiday','tee','break','R','weekend'."""
    col = info["col"]
    notes = info["notes"].lower()
    class_num = info["class_num"]

    # Sunday (col 0) or Saturday (col 6) → weekend
    if col == 0 or col == 6:
        return "weekend"

    if class_num:
        track = class_num.split("-")[0]
        return track  # "1" or "2"

    # No class number — classify by notes
    if "tee" in notes:
        return "tee"
    if "spring break" in notes or "recess" in notes:
        return "break"
    if "reorgy" in notes or "march back" in notes:
        return "R"
    if "no class" in notes or "no classes" in notes or "holiday" in notes:
        return "holiday"
    if "grad" in notes or "graduation" in notes:
        return "grad"
    # Weekday with no class number and no recognisable notes → treat as holiday/break
    return "holiday"


# ---------------------------------------------------------------------------
# Build semester JSON
# ---------------------------------------------------------------------------

def build_semester(
    all_days: dict[date, dict],
    sem_start: date,
    sem_end: date,
    tee_start: date,
    tee_end: date,
    grad_start: date | None,
    grad_end: date | None,
    ay: str,
    semester_label: str,
) -> dict:
    """Build the JSON dict for one semester."""

    # Collect all weekdays in range and determine their types
    from datetime import timedelta
    special_days: dict[str, dict] = {}

    first_type: str | None = None
    instruction_start: date | None = None
    instruction_end: date | None = None

    # First pass: find instruction_start so we can filter special_days correctly
    d = sem_start
    while d <= max(tee_end, grad_end or tee_end):
        if d in all_days:
            info = all_days[d]
            dt = classify(info)
            in_tee = tee_start <= d <= tee_end
            in_grad = (grad_start is not None and grad_end is not None
                       and grad_start <= d <= grad_end)
            if dt in ("1", "2") and not in_tee and not in_grad:
                if instruction_start is None:
                    instruction_start = d
                    first_type = dt
                instruction_end = d
        d += timedelta(days=1)

    # Second pass: collect special_days only within [instruction_start, tee_end/grad_end]
    effective_start = instruction_start or sem_start
    effective_end = grad_end if grad_end else tee_end
    d = effective_start
    while d <= effective_end:
        if d in all_days:
            info = all_days[d]
            dt = classify(info)
            raw_notes = info["notes"]
            is_weekend = (dt == "weekend")
            in_tee = tee_start <= d <= tee_end
            in_grad = (grad_start is not None and grad_end is not None
                       and grad_start <= d <= grad_end)
            is_academic = dt in ("1", "2")
            if not is_academic and not is_weekend and not in_tee and not in_grad:
                special_days[d.isoformat()] = {
                    "day_type": dt,
                    "notes": [raw_notes] if raw_notes else [],
                }
        d += timedelta(days=1)

    return {
        "_comment": f"USMA {ay}. Parsed from official Buff Card (As of 19 Apr 2026).",
        "_source": "https://courses.westpoint.edu/view_full_buff_card.cfm",
        "ay": ay,
        "semester": semester_label,
        "start_date": (instruction_start or sem_start).isoformat(),
        "end_date": (instruction_end or sem_end).isoformat(),
        "tee_start": tee_start.isoformat(),
        "tee_end": tee_end.isoformat(),
        "grad_start": grad_start.isoformat() if grad_start else None,
        "grad_end": grad_end.isoformat() if grad_end else None,
        "first_academic_day_type": first_type or "1",
        "special_days": special_days,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"Parsing {HTML_FILE.name} ...")
    all_days = parse_html(HTML_FILE)
    print(f"  Extracted {len(all_days)} calendar cells.")

    # ---- AY26-1 (Fall 2025) ------------------------------------------------
    ay261 = build_semester(
        all_days,
        sem_start=date(2025, 8, 1),
        sem_end=date(2025, 12, 15),
        tee_start=date(2025, 12, 16),
        tee_end=date(2025, 12, 19),
        grad_start=None,
        grad_end=None,
        ay="AY26-1",
        semester_label="Fall 2025",
    )

    # ---- AY26-2 (Spring 2026) ----------------------------------------------
    ay262 = build_semester(
        all_days,
        sem_start=date(2026, 1, 1),
        sem_end=date(2026, 5, 11),
        tee_start=date(2026, 5, 12),
        tee_end=date(2026, 5, 16),
        grad_start=date(2026, 5, 18),
        grad_end=date(2026, 5, 22),
        ay="AY26-2",
        semester_label="Spring 2026",
    )

    # ---- Write JSON --------------------------------------------------------
    for data, filename in [(ay261, "AY26-1.json"), (ay262, "AY26-2.json")]:
        out = HERE / filename
        out.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"  Wrote {filename}  (start={data['start_date']}, end={data['end_date']}, "
              f"first_type={data['first_academic_day_type']}, "
              f"specials={len(data['special_days'])})")

    print("Done.")


if __name__ == "__main__":
    main()
