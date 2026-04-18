"""
Lesson-reference resolver.

Parses free-text lesson references (e.g. "L5", "Lesson 12", "L1-5 through L1-8",
"Week 3") and maps them to calendar dates via a BaseCalendar.
"""

import re
from datetime import date
from typing import Optional

from core.base_calendar import BaseCalendar


# Matches: L5, L 5, Lesson 5, lesson 5
_LESSON_NUM_RE = re.compile(
    r"\b(?:L|Lesson)\s*(\d{1,3})\b", re.IGNORECASE
)

# Matches: L1-5, L1-12, 1-5 (when near other lesson keywords)
_LESSON_DASH_RE = re.compile(
    r"\bL?(\d{1,2})-(\d{1,3})\b"
)

# Matches: Week 3, Wk 3, Wk3
_WEEK_RE = re.compile(r"\b(?:Week|Wk)\s*(\d{1,2})\b", re.IGNORECASE)


class LessonRef:
    """Parsed lesson reference before date resolution."""

    __slots__ = ("raw", "track", "lesson_number", "week_number")

    def __init__(
        self,
        raw: str,
        track: Optional[int] = None,
        lesson_number: Optional[int] = None,
        week_number: Optional[int] = None,
    ):
        self.raw = raw
        self.track = track
        self.lesson_number = lesson_number
        self.week_number = week_number

    def __repr__(self) -> str:
        return (
            f"LessonRef(raw={self.raw!r}, track={self.track}, "
            f"lesson={self.lesson_number}, week={self.week_number})"
        )


def parse_lesson_refs(text: str, default_track: Optional[int] = None) -> list[LessonRef]:
    """
    Extract all lesson references from a text fragment.

    Returns a list of LessonRef objects, which can then be resolved to dates
    via resolve_ref().
    """
    refs: list[LessonRef] = []
    seen_spans: list[tuple[int, int]] = []

    def _overlaps(start: int, end: int) -> bool:
        return any(s < end and start < e for s, e in seen_spans)

    # Dash range first — more specific than plain lesson number
    for m in _LESSON_DASH_RE.finditer(text):
        if _overlaps(m.start(), m.end()):
            continue
        seen_spans.append((m.start(), m.end()))
        refs.append(
            LessonRef(
                m.group(0),
                track=default_track,
                lesson_number=int(m.group(2)),  # use ending lesson as the target date
            )
        )

    # Plain lesson-number pattern
    for m in _LESSON_NUM_RE.finditer(text):
        if _overlaps(m.start(), m.end()):
            continue
        seen_spans.append((m.start(), m.end()))
        refs.append(LessonRef(m.group(0), track=default_track, lesson_number=int(m.group(1))))

    # Week pattern
    for m in _WEEK_RE.finditer(text):
        if _overlaps(m.start(), m.end()):
            continue
        seen_spans.append((m.start(), m.end()))
        refs.append(LessonRef(m.group(0), track=default_track, week_number=int(m.group(1))))

    return refs


def resolve_ref(ref: LessonRef, calendar: BaseCalendar, track: int) -> Optional[date]:
    """
    Resolve a single LessonRef to a calendar date.

    For lesson-number refs, directly looks up the date.
    For week-number refs, estimates by computing the first Day-N of the given week
    of instruction (week 1 = lessons 1–5, week 2 = lessons 6–10, etc.).
    """
    effective_track = ref.track if ref.track is not None else track

    if ref.lesson_number is not None:
        return calendar.resolve_lesson(effective_track, ref.lesson_number)

    if ref.week_number is not None:
        # Estimate: each week of instruction has ~5 academic days;
        # use the first lesson of that week as the anchor date.
        first_lesson_of_week = (ref.week_number - 1) * 5 + 1
        return calendar.resolve_lesson(effective_track, first_lesson_of_week)

    return None


def resolve_all(
    text: str, calendar: BaseCalendar, track: int
) -> list[tuple[LessonRef, Optional[date]]]:
    """Parse and resolve every lesson reference in text. Returns (ref, date) pairs."""
    refs = parse_lesson_refs(text, default_track=track)
    return [(ref, resolve_ref(ref, calendar, track)) for ref in refs]
