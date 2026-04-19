"""Two-pass event extractor.

Pass 1 — lesson-number references near event keywords.
Pass 2 — explicit calendar dates near event keywords.
Both passes run on paragraph text and on structured tables.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from core.base_calendar import BaseCalendar
from core.confidence import ConfidenceFactors
from core.models import Event
from core.parsers import ParsedDoc
from core.resolver import parse_lesson_refs, resolve_ref

_PATTERNS_FILE = Path(__file__).parent.parent.parent / "data" / "event_patterns.json"

# Characters on each side of a keyword match to search for context
_CTX = 180

# ---------------------------------------------------------------------------
# Compiled regexes
# ---------------------------------------------------------------------------

_MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_MONTH_PAT = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)
_DATE_DMY_RE = re.compile(rf"\b(\d{{1,2}})\s+(?P<mon>{_MONTH_PAT})\b", re.IGNORECASE)
_DATE_MDY_RE = re.compile(rf"\b(?P<mon>{_MONTH_PAT})\s+(\d{{1,2}})\b", re.IGNORECASE)
_DATE_SLASH_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")

_WEIGHT_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,2})?)\s*%")
_TITLE_SUFFIX_RE = re.compile(r"(?:\s*)(?:#\s*)?(\d+(?:\.\d+)?|[IVX]{1,4})\b")
_COURSE_CODE_RE = re.compile(r"\b([A-Z]{2,4}\s*\d{3,4}[A-Z]?)\b")

# Table column header patterns
_COL_EVENT_RE = re.compile(r"\b(?:event|type|exam|assignment|graded|item|assessment)\b", re.IGNORECASE)
_COL_DATE_RE = re.compile(r"\b(?:date|due|when|administered|scheduled)\b", re.IGNORECASE)
_COL_LESSON_RE = re.compile(r"\b(?:lesson|lsn|l#|lecture|class)\b", re.IGNORECASE)
_COL_WEIGHT_RE = re.compile(r"\b(?:weight|%|percent|grade|value|pts|points)\b", re.IGNORECASE)
_COL_NAME_RE = re.compile(r"\b(?:name|title|description|topic)\b", re.IGNORECASE)


@dataclass
class _Raw:
    event_type: str
    title: str
    lesson_date: Optional[date] = None
    explicit_date: Optional[date] = None
    lesson_ref: Optional[str] = None
    weight_pct: Optional[float] = None
    course_code_in_ctx: bool = False
    conflict: bool = False

    @property
    def best_date(self) -> Optional[date]:
        return self.lesson_date or self.explicit_date


# ---------------------------------------------------------------------------
# Pattern loading (lazy, cached)
# ---------------------------------------------------------------------------

_kw_map_cache: Optional[dict[str, re.Pattern]] = None


def _kw_map() -> dict[str, re.Pattern]:
    global _kw_map_cache
    if _kw_map_cache is None:
        pats = json.loads(_PATTERNS_FILE.read_text(encoding="utf-8"))
        _kw_map_cache = {}
        for et, keywords in pats["event_type_keywords"].items():
            joined = "|".join(re.escape(k) for k in sorted(keywords, key=len, reverse=True))
            _kw_map_cache[et] = re.compile(rf"\b(?:{joined})\b", re.IGNORECASE)
    return _kw_map_cache


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _resolve_month_day(day: int, month_str: str, calendar: BaseCalendar) -> Optional[date]:
    month = _MONTH_MAP.get(month_str.lower())
    if not month:
        return None
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


def _extract_date(ctx: str, calendar: BaseCalendar) -> Optional[date]:
    for m in _DATE_DMY_RE.finditer(ctx):
        d = _resolve_month_day(int(m.group(1)), m.group("mon"), calendar)
        if d:
            return d
    for m in _DATE_MDY_RE.finditer(ctx):
        d = _resolve_month_day(int(m.group(2)), m.group("mon"), calendar)
        if d:
            return d
    return None


def _extract_weight(ctx: str) -> Optional[float]:
    m = _WEIGHT_RE.search(ctx)
    return float(m.group(1)) if m else None


def _build_title(event_type: str, after_keyword: str) -> str:
    m = _TITLE_SUFFIX_RE.match(after_keyword)
    return f"{event_type} {m.group(1)}" if m else event_type


# ---------------------------------------------------------------------------
# Pass 1+2 on free text
# ---------------------------------------------------------------------------

def _from_text(
    text: str,
    course_code: str,
    course_track: int,
    calendar: BaseCalendar,
) -> list[_Raw]:
    results: list[_Raw] = []
    for et, kw_re in _kw_map().items():
        for m in kw_re.finditer(text):
            start = max(0, m.start() - _CTX)
            end = min(len(text), m.end() + _CTX)
            ctx = text[start:end]
            after = text[m.end(): m.end() + 30]

            # Lesson refs
            lesson_date: Optional[date] = None
            lesson_ref_text: Optional[str] = None
            for ref in parse_lesson_refs(ctx, default_track=course_track):
                d = resolve_ref(ref, calendar, course_track)
                if d:
                    lesson_date = d
                    lesson_ref_text = ref.raw
                    break

            explicit_date = _extract_date(ctx, calendar)
            conflict = bool(lesson_date and explicit_date and lesson_date != explicit_date)
            in_ctx = bool(_COURSE_CODE_RE.search(ctx)) or course_code.upper() in ctx.upper()

            results.append(_Raw(
                event_type=et,
                title=_build_title(et, after),
                lesson_date=lesson_date,
                explicit_date=explicit_date,
                lesson_ref=lesson_ref_text,
                weight_pct=_extract_weight(ctx),
                course_code_in_ctx=in_ctx,
                conflict=conflict,
            ))
    return results


# ---------------------------------------------------------------------------
# Table extraction
# ---------------------------------------------------------------------------

def _col_roles(headers: list[str]) -> dict[str, Optional[int]]:
    roles: dict[str, Optional[int]] = {
        "event": None, "name": None, "date": None, "lesson": None, "weight": None
    }
    for i, h in enumerate(headers):
        if roles["event"] is None and _COL_EVENT_RE.search(h):
            roles["event"] = i
        if roles["name"] is None and _COL_NAME_RE.search(h):
            roles["name"] = i
        if roles["date"] is None and _COL_DATE_RE.search(h):
            roles["date"] = i
        if roles["lesson"] is None and _COL_LESSON_RE.search(h):
            roles["lesson"] = i
        if roles["weight"] is None and _COL_WEIGHT_RE.search(h):
            roles["weight"] = i
    return roles


def _classify(text: str) -> Optional[str]:
    for et, kw_re in _kw_map().items():
        if kw_re.search(text):
            return et
    return None


def _from_tables(
    tables: list[list[list[str]]],
    course_code: str,
    course_track: int,
    calendar: BaseCalendar,
) -> list[_Raw]:
    results: list[_Raw] = []
    for table in tables:
        if len(table) < 2:
            continue
        roles = _col_roles(table[0])
        for row in table[1:]:
            if not any(row):
                continue
            full = " ".join(row)

            et = None
            if roles["event"] is not None and roles["event"] < len(row):
                et = _classify(row[roles["event"]])
            if et is None:
                et = _classify(full)
            if et is None:
                continue

            # Date column
            explicit_date: Optional[date] = None
            if roles["date"] is not None and roles["date"] < len(row):
                explicit_date = _extract_date(row[roles["date"]], calendar)
            if not explicit_date:
                explicit_date = _extract_date(full, calendar)

            # Lesson column
            lesson_date: Optional[date] = None
            lesson_ref_text: Optional[str] = None
            lesson_src = ""
            if roles["lesson"] is not None and roles["lesson"] < len(row):
                lesson_src = row[roles["lesson"]]
            if not lesson_src:
                lesson_src = full
            for ref in parse_lesson_refs(lesson_src, default_track=course_track):
                d = resolve_ref(ref, calendar, course_track)
                if d:
                    lesson_date = d
                    lesson_ref_text = ref.raw
                    break

            conflict = bool(lesson_date and explicit_date and lesson_date != explicit_date)

            weight: Optional[float] = None
            if roles["weight"] is not None and roles["weight"] < len(row):
                weight = _extract_weight(row[roles["weight"]])
            if weight is None:
                weight = _extract_weight(full)

            # Title: prefer name column, then event column, then type
            title = et
            name_col = roles.get("name") or roles.get("event")
            if name_col is not None and name_col < len(row) and row[name_col].strip():
                title = row[name_col].strip()

            results.append(_Raw(
                event_type=et,
                title=title,
                lesson_date=lesson_date,
                explicit_date=explicit_date,
                lesson_ref=lesson_ref_text,
                weight_pct=weight,
                course_code_in_ctx=True,  # table belongs to a known course
                conflict=conflict,
            ))
    return results


# ---------------------------------------------------------------------------
# Deduplication + scoring
# ---------------------------------------------------------------------------

def _dedup(raws: list[_Raw]) -> list[_Raw]:
    seen: set[tuple] = set()
    out: list[_Raw] = []
    for r in raws:
        key = (r.event_type, r.best_date or r.title)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _score(r: _Raw) -> float:
    return ConfidenceFactors(
        has_event_keyword=True,
        has_date_or_lesson=bool(r.best_date),
        has_course_code=r.course_code_in_ctx,
        no_conflict=not r.conflict,
    ).score()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_events(
    doc: ParsedDoc,
    course_code: str,
    course_track: int,
    calendar: BaseCalendar,
) -> list[Event]:
    """Extract graded events from a parsed syllabus, sorted by date.

    Events with no resolvable date are dropped; the caller should surface
    the Copilot handoff panel when many events fall below 0.4 confidence.
    """
    raw = _dedup(_from_text(doc.full_text, course_code, course_track, calendar)
                 + _from_tables(doc.tables, course_code, course_track, calendar))

    events: list[Event] = []
    for r in raw:
        d = r.best_date
        if d is None:
            continue
        events.append(Event(
            course_code=course_code,
            event_type=r.event_type,  # type: ignore[arg-type]
            title=r.title,
            date=d,
            lesson_ref=r.lesson_ref,
            weight_pct=r.weight_pct,
            confidence=_score(r),
            source="parsed",
            notes="Date conflict: lesson ref and explicit date disagree" if r.conflict else None,
        ))

    return sorted(events, key=lambda e: (e.date, e.course_code))
