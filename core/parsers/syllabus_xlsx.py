"""Structured extractor for XLSX lesson-schedule syllabi.

USMA departments publish syllabi as spreadsheets in a handful of recurring
shapes. This module recognizes them by their headers and pulls events out
row-by-row instead of pattern-matching free text, which is far more accurate:

  - A "lesson schedule" sheet: one row per lesson, with a lesson-number
    column and either a single date column ("7JAN", datetimes) or separate
    "Day 1" / "Day 2" date columns ("Mon, 17 Aug", datetimes).
  - An optional "graded events" sheet: event name, points, and the lesson
    it falls on. Points are converted to weights using the sheet's total.

Dates in the wild are unreliable: cells carry stale years from copied
templates (2017, last AY) and informal strings. Month/day are trusted;
the year is snapped into the selected semester's window. Workbooks often
contain several near-duplicate schedule sheets (instructor copies, prior-AY
relics), so only the sheet whose dates align best with the academic
calendar is used.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from core.base_calendar import BaseCalendar
from core.models import Event
from core.parsers import ParsedDoc, SheetData

# ---------------------------------------------------------------------------
# Header roles
# ---------------------------------------------------------------------------

def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower() if s is not None else ""


_ROLE_PATTERNS: list[tuple[str, re.Pattern]] = [
    # Order matters: more specific first ("Day 1 Date" must not match "date")
    ("day1", re.compile(r"\bday\s*1\b")),
    ("day2", re.compile(r"\bday\s*2\b")),
    ("name", re.compile(r"lesson name|topic|title|subject")),
    ("date", re.compile(r"\bdate\b|\bdue\b")),
    ("lesson", re.compile(r"^(?:lsn|lesson|l)\s*#?$|lesson\s*(?:#|number|no)\b|^lsn\b")),
    ("event", re.compile(r"graded\s*event|assessment|\bexam\b|\bevent\b")),
    ("notes", re.compile(r"\bnotes?\b|remarks")),
    ("weight", re.compile(r"points|pts|weight|%|percent")),
    ("block", re.compile(r"^blo?c?k\b")),
]

_WEEKDAY_NAMES = {"sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"}


def _match_roles(row: list[Any]) -> dict[str, int]:
    roles: dict[str, int] = {}
    for ci, cell in enumerate(_norm(c) for c in row):
        if not cell:
            continue
        for role, pat in _ROLE_PATTERNS:
            if role not in roles and pat.search(cell):
                roles[role] = ci
                break
    return roles


def _find_header(rows: list[list[Any]]) -> Optional[tuple[int, dict[str, int]]]:
    """Locate the header row (within the first 5 rows) and map roles->column."""
    best: Optional[tuple[int, dict[str, int]]] = None
    for ri, row in enumerate(rows[:5]):
        cells = [_norm(c) for c in row]
        # A monthly grid calendar sheet, not a schedule — skip the whole sheet
        if sum(1 for c in cells if c in _WEEKDAY_NAMES) >= 3:
            return None
        roles = _match_roles(row)
        if len(roles) >= 2 and (best is None or len(roles) > len(best[1])):
            best = (ri, roles)
    return best


# ---------------------------------------------------------------------------
# Date coercion
# ---------------------------------------------------------------------------

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))

_WEEKDAY_PREFIX_RE = re.compile(
    r"^\s*(?:mon|tues?|wed(?:nes)?|thur?s?|fri|sat(?:ur)?|sun)(?:day)?\.?,?\s*",
    re.IGNORECASE,
)
_DMY_RE = re.compile(rf"\b(\d{{1,2}})\s*({_MONTH_ALT})\b", re.IGNORECASE)
_MDY_RE = re.compile(rf"\b({_MONTH_ALT})\.?,?\s*(\d{{1,2}})\b", re.IGNORECASE)
_SLASH_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/\d{2,4})?\b")


def snap_to_semester(month: int, day: int, calendar: BaseCalendar) -> Optional[date]:
    """Build a date from month/day, choosing the year from the semester window.

    Stale template years are common, so the year in the source is ignored.
    Returns None when the month/day cannot fall near the semester at all.
    """
    span = sorted(calendar.days())
    if not span:
        return None
    lo, hi = span[0], span[-1]
    for year in {lo.year, hi.year}:
        try:
            cand = date(year, month, day)
        except ValueError:
            continue
        if lo <= cand <= hi:
            return cand
    # Tolerate dates slightly outside the instruction window (e.g. TEE week
    # in a syllabus footer, due dates right after the last lesson)
    for year in {lo.year, hi.year}:
        try:
            cand = date(year, month, day)
        except ValueError:
            continue
        if abs((cand - lo).days) <= 21 or abs((cand - hi).days) <= 21:
            return cand
    return None


def coerce_date(value: Any, calendar: BaseCalendar) -> Optional[date]:
    """Coerce a cell value (datetime, '7JAN', 'Mon, 17 Aug', '9/7') to a date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return snap_to_semester(value.month, value.day, calendar)
    if isinstance(value, date):
        return snap_to_semester(value.month, value.day, calendar)
    text = _WEEKDAY_PREFIX_RE.sub("", str(value).strip())
    if not text:
        return None
    m = _DMY_RE.search(text)
    if m:
        return snap_to_semester(_MONTHS[m.group(2).lower()], int(m.group(1)), calendar)
    m = _MDY_RE.search(text)
    if m:
        return snap_to_semester(_MONTHS[m.group(1).lower()], int(m.group(2)), calendar)
    m = _SLASH_RE.search(text)
    if m:
        return snap_to_semester(int(m.group(1)), int(m.group(2)), calendar)
    return None


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _classify_best(text: str) -> Optional[str]:
    """Best event type for a phrase: the longest keyword match wins, so
    "Final Project" beats TEE's "Final" and "Problem Set" beats "PS"."""
    from core.parsers.event_extractor import _kw_map
    best: tuple[int, Optional[str]] = (0, None)
    for et, kw_re in _kw_map().items():
        for m in kw_re.finditer(text):
            if len(m.group(0)) > best[0]:
                best = (len(m.group(0)), et)
    return best[1]


# Assessment-type events are trustworthy even in topic/lesson-name cells
# ("WPR 1", "Midterm", "Quiz #2" as the lesson title). Generic types (HW,
# Project, Lab) in a topic cell are usually just the lesson subject.
_ASSESSMENT_TYPES = frozenset({"WPR", "TEE", "Quiz", "Writ"})
_ASSESSMENT_HINT_RE = re.compile(
    r"\b(?:wpr|tee|quiz|writ|midterm|exam|graded)\b", re.IGNORECASE)
_DUE_HINT_RE = re.compile(r"\bdue\b", re.IGNORECASE)

_LEADING_INT_RE = re.compile(r"^\s*(\d{1,3})\s*(?:\n|$)")
_DUE_DATE_RE = re.compile(
    rf"due\b[^;]*?(?:(\d{{1,2}})\s*({_MONTH_ALT})|({_MONTH_ALT})\.?\s*(\d{{1,2}}))",
    re.IGNORECASE,
)
_WEIGHT_PCT_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,2})?)\s*%")
_DROP_RE = re.compile(r"^\s*(?:class\s*)?drop\b|class drop|snow day", re.IGNORECASE)
# Phrases that describe prep work or hand-out moments, not graded events
_SKIP_SEGMENT_RE = re.compile(
    r"^(?:read|review|watch|install|complete|see|bring|study|begin|issue[ds]?|"
    r"launch|start|open|\()", re.IGNORECASE,
)


def _cell(row: list[Any], idx: Optional[int]) -> Any:
    if idx is None or idx >= len(row):
        return None
    return row[idx]


def _lesson_number(row: list[Any], roles: dict[str, int]) -> Optional[int]:
    for role in ("lesson", "name"):
        v = _cell(row, roles.get(role))
        if isinstance(v, (int, float)):
            return int(v)
        if isinstance(v, str):
            m = _LEADING_INT_RE.match(v)
            if m:
                return int(m.group(1))
        if role == "lesson" and v is not None:
            return None  # lesson column present but not numeric for this row
    return None


def _segments(text: str) -> list[str]:
    """Split a cell into candidate event phrases."""
    parts = re.split(r"[\n;]+|\s/\s", text)
    return [p.strip() for p in parts if p.strip()]


def _clean_title(segment: str) -> str:
    # Strip trailing due-clauses and platform noise from the title
    t = re.split(r"\b(?:due|due by|due on|on canvas)\b", segment, flags=re.IGNORECASE)[0]
    t = re.sub(r"\s+", " ", t).strip(" -–:;,")
    return t or segment.strip()


# ---------------------------------------------------------------------------
# Schedule sheet processing
# ---------------------------------------------------------------------------

@dataclass
class _ScheduleResult:
    sheet_name: str = ""
    events: list[Event] = field(default_factory=list)
    lesson_dates: dict[int, date] = field(default_factory=dict)
    rows_with_dates: int = 0
    aligned_rows: int = 0

    @property
    def alignment(self) -> tuple[float, int]:
        """Sort key: sheets whose dates land on academic days win.

        Ratio first (a stale-year template sheet scores low), then row count
        as the tiebreak. The +2 smoothing keeps a tiny sheet with one lucky
        date from outranking a full 40-lesson schedule.
        """
        return (self.aligned_rows / (self.rows_with_dates + 2), self.rows_with_dates)


# (role, base confidence, acceptance rule)
_SCAN_SPECS = [
    ("event", 0.95, "all"),
    ("notes", 0.95, "due_or_assessment"),
    ("name", 0.9, "assessment"),
    ("lesson", 0.9, "assessment"),
]


def _accept(rule: str, segment: str, event_type: str) -> bool:
    if rule == "all":
        return True
    if rule == "due_or_assessment":
        return bool(_DUE_HINT_RE.search(segment) or _ASSESSMENT_HINT_RE.search(segment))
    if rule == "assessment":
        return event_type in _ASSESSMENT_TYPES or "graded" in segment.lower()
    return False


def _process_schedule_sheet(
    sheet: SheetData,
    header_row: int,
    roles: dict[str, int],
    course_code: str,
    course_track: int,
    calendar: BaseCalendar,
) -> _ScheduleResult:
    res = _ScheduleResult(sheet_name=sheet.name)

    for row in sheet.rows[header_row + 1:]:
        # Class-drop / snow-day rows still carry due-dates in their event
        # cells, so they are scanned like any other row; the drop marker
        # itself never matches an event keyword.
        lesson = _lesson_number(row, roles)

        # Resolve the row's date for this cadet's track
        row_date: Optional[date] = None
        if "day1" in roles or "day2" in roles:
            track_role = "day1" if course_track == 1 else "day2"
            other_role = "day2" if course_track == 1 else "day1"
            row_date = coerce_date(_cell(row, roles.get(track_role)), calendar)
            if row_date is None:
                row_date = coerce_date(_cell(row, roles.get(other_role)), calendar)
        if row_date is None and "date" in roles:
            row_date = coerce_date(_cell(row, roles.get("date")), calendar)
        if row_date is not None:
            res.rows_with_dates += 1
            meta = calendar.get_day_meta(row_date)
            if meta is not None and meta.is_academic:
                res.aligned_rows += 1
        if row_date is None and lesson is not None:
            row_date = calendar.resolve_lesson(course_track, lesson)

        if lesson is not None and row_date is not None:
            res.lesson_dates.setdefault(lesson, row_date)

        # Scan event-bearing cells; one event per type per row (the same
        # exam often appears in both the topic and graded-event columns)
        types_seen: set[str] = set()
        for role, base_conf, rule in _SCAN_SPECS:
            text = _cell(row, roles.get(role))
            if not isinstance(text, str) or not text.strip():
                continue
            for seg in _segments(text):
                if _SKIP_SEGMENT_RE.match(seg):
                    continue
                et = _classify_best(seg)
                if et is None or et in types_seen or not _accept(rule, seg, et):
                    continue
                # A due-date inside the segment overrides the row date
                due: Optional[date] = None
                m = _DUE_DATE_RE.search(seg)
                if m:
                    if m.group(1):
                        due = snap_to_semester(
                            _MONTHS[m.group(2).lower()], int(m.group(1)), calendar)
                    else:
                        due = snap_to_semester(
                            _MONTHS[m.group(3).lower()], int(m.group(4)), calendar)
                d = due or row_date
                if d is None:
                    continue
                wm = _WEIGHT_PCT_RE.search(seg)
                confidence = base_conf if due is None else 0.9
                if d.weekday() >= 5:
                    confidence = 0.7  # weekend date: probably fine, worth a look
                types_seen.add(et)
                res.events.append(Event(
                    course_code=course_code,
                    event_type=et,  # type: ignore[arg-type]
                    title=_clean_title(seg),
                    date=d,
                    lesson_ref=f"L{lesson}" if lesson is not None else None,
                    weight_pct=float(wm.group(1)) if wm else None,
                    confidence=confidence,
                    source="parsed",
                ))
    return res


# ---------------------------------------------------------------------------
# Graded-events sheet processing
# ---------------------------------------------------------------------------

def _process_graded_events_sheet(
    sheet: SheetData,
    header_row: int,
    roles: dict[str, int],
    course_code: str,
    course_track: int,
    calendar: BaseCalendar,
    lesson_dates: dict[int, date],
) -> list[Event]:
    """Sheet of (lesson, event name, points). Points -> weight via the total row."""
    rows = sheet.rows[header_row + 1:]

    # The points total converts points to percentages. The first total row
    # is the course total; later tables (e.g. instructor points) sub-total.
    total: Optional[float] = None
    for row in rows:
        if any(_norm(c) == "total" for c in row):
            for v in reversed(row):
                if isinstance(v, (int, float)) and v > 1:
                    total = float(v)
                    break
            break

    tee_dates = sorted(d for d, m in calendar.days().items() if m.day_type == "tee")

    events: list[Event] = []
    for row in rows:
        # Sheets often stack several tables; re-map columns at each new header
        new_roles = _match_roles(row)
        if len(new_roles) >= 2 and ("event" in new_roles or "weight" in new_roles):
            roles = new_roles
            continue

        name_val = _cell(row, roles.get("event")) or _cell(row, roles.get("name"))
        if not isinstance(name_val, str) or not name_val.strip():
            continue
        if _norm(name_val) in ("total", "graded event") or _norm(name_val).startswith("drop"):
            continue
        et = _classify_best(name_val) or ("TEE" if "tee" in _norm(name_val) else None)
        lesson_val = _cell(row, roles.get("lesson"))

        d: Optional[date] = None
        notes: Optional[str] = None
        confidence = 0.8
        if isinstance(lesson_val, (int, float)):
            d = lesson_dates.get(int(lesson_val)) or calendar.resolve_lesson(
                course_track, int(lesson_val))
        elif isinstance(lesson_val, str):
            m = re.match(r"^\s*(\d{1,3})\s*$", lesson_val)
            if m:
                d = lesson_dates.get(int(m.group(1))) or calendar.resolve_lesson(
                    course_track, int(m.group(1)))
            elif "tee" in lesson_val.lower():
                et = et or "TEE"
        if et == "TEE" and d is None and tee_dates:
            d = tee_dates[0]
            notes = "TEE week start — check your individual TEE schedule"
            confidence = 0.6
        if et is None:
            continue

        weight: Optional[float] = None
        pts = _cell(row, roles.get("weight"))
        if isinstance(pts, (int, float)) and total:
            weight = round(float(pts) / total * 100, 1)
            if not (0 <= weight <= 100):
                weight = None

        events.append(Event(
            course_code=course_code,
            event_type=et,  # type: ignore[arg-type]
            title=name_val.strip(),
            date=d or date.min,  # placeholder; dateless events handled below
            weight_pct=weight,
            confidence=confidence,
            source="parsed",
            notes=notes,
        ))
    return events


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", t.lower())


def detect_course_code(doc: ParsedDoc, filename: Optional[str] = None) -> Optional[str]:
    """Pull a course code like EM384 from sheet titles, first rows, or filename."""
    candidates: list[str] = [s.name for s in doc.sheets]
    for s in doc.sheets:
        for row in s.rows[:3]:
            candidates.extend(str(c) for c in row if isinstance(c, str))
    if filename:
        candidates.append(filename)
    for text in candidates:
        # Underscores are word characters, so split them out of filenames
        m = re.search(r"\b([A-Z]{2,4}\s?\d{3}[A-Z]?)\b", text.replace("_", " "))
        if m:
            return m.group(1).replace(" ", "")
    return None


def extract_structured(
    doc: ParsedDoc,
    course_code: str,
    course_track: int,
    calendar: BaseCalendar,
) -> Optional[list[Event]]:
    """Try structured extraction. Returns None when no schedule sheet found."""
    schedule_results: list[_ScheduleResult] = []
    graded_sheets: list[tuple[SheetData, int, dict[str, int]]] = []

    for sheet in doc.sheets:
        found = _find_header(sheet.rows)
        if not found:
            continue
        header_row, roles = found
        has_dates = any(r in roles for r in ("date", "day1", "day2"))
        is_graded = ("weight" in roles and "event" in roles and not has_dates) or (
            "graded" in _norm(sheet.name) and "weight" in roles)
        if is_graded:
            graded_sheets.append((sheet, header_row, roles))
        elif has_dates and ("lesson" in roles or "name" in roles):
            # Prefer the sheet matching the cadet's track when a workbook has
            # per-track sheets like "Syllabus (Day 1)" / "Syllabus (Day 2)"
            sname = _norm(sheet.name)
            other_track = 2 if course_track == 1 else 1
            if f"day {other_track}" in sname and any(
                    f"day {course_track}" in _norm(s.name) for s in doc.sheets):
                continue
            schedule_results.append(_process_schedule_sheet(
                sheet, header_row, roles, course_code, course_track, calendar))

    if not schedule_results and not graded_sheets:
        return None

    # Workbooks accumulate near-duplicate schedule sheets (instructor copies,
    # stale prior-AY templates). Keep only the best-aligned one.
    events: list[Event] = []
    lesson_dates: dict[int, date] = {}
    if schedule_results:
        best = max(schedule_results, key=lambda r: r.alignment)
        events = best.events
        lesson_dates = best.lesson_dates

    for sheet, header_row, roles in graded_sheets:
        for ev in _process_graded_events_sheet(
                sheet, header_row, roles, course_code, course_track,
                calendar, lesson_dates):
            # Merge: the same event found in the schedule keeps its date and
            # gains the weight from the graded-events sheet. Titles match by
            # containment ("WPR 1" vs "Wiley Plus 1, WPR 1"); a bare
            # type+date match also needs the same event number so two
            # different quizzes on one day stay separate.
            def _num(t: str) -> Optional[str]:
                m = re.search(r"\d+", t)
                return m.group(0) if m else None

            ev_t = _norm_title(ev.title)
            match = next(
                (e for e in events
                 if (len(ev_t) >= 3 and (t := _norm_title(e.title))
                     and (ev_t in t or t in ev_t))
                 or (e.event_type == ev.event_type and e.date == ev.date
                     and _num(e.title) == _num(ev.title))),
                None,
            )
            if match is not None:
                if match.weight_pct is None and ev.weight_pct is not None:
                    match.weight_pct = ev.weight_pct
            elif ev.date != date.min:
                events.append(ev)

    # Final dedup (same type + date + title across sheets)
    seen: set[tuple] = set()
    out: list[Event] = []
    for e in sorted(events, key=lambda e: (e.date, -e.confidence)):
        key = (e.event_type, e.date, _norm_title(e.title))
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return sorted(out, key=lambda e: (e.date, e.course_code)) if out else None
