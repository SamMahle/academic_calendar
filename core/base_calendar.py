"""
Base academic calendar loader and day-type resolver.

Primary source: USMA online calendar scraper (M6). When the scraper is
unavailable or fails, falls back to bundled JSON files in data/base_calendars/.
"""

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.models import DayMeta, DayType

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent / "data" / "base_calendars"

# Day types that do not count as academic instruction days
_NON_ACADEMIC: frozenset[DayType] = frozenset(
    ["holiday", "break", "R", "tee", "grad", "weekend"]
)


def _iter_dates(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _build_day_map(raw: dict) -> dict[date, DayMeta]:
    """Generate the full day map from a raw JSON calendar dict."""
    start = date.fromisoformat(raw["start_date"])
    end_instruction = date.fromisoformat(raw["end_date"])

    tee_start = date.fromisoformat(raw["tee_start"]) if raw.get("tee_start") else None
    tee_end = date.fromisoformat(raw["tee_end"]) if raw.get("tee_end") else None
    grad_start = date.fromisoformat(raw["grad_start"]) if raw.get("grad_start") else None
    grad_end = date.fromisoformat(raw["grad_end"]) if raw.get("grad_end") else None

    # Last calendar date to include
    last = end_instruction
    if tee_end:
        last = max(last, tee_end)
    if grad_end:
        last = max(last, grad_end)

    specials: dict[date, dict] = {
        date.fromisoformat(k): v
        for k, v in raw.get("special_days", {}).items()
    }

    first_type: DayType = raw.get("first_academic_day_type", "1")
    current_type: DayType = first_type

    day_map: dict[date, DayMeta] = {}

    for d in _iter_dates(start, last):
        # Weekends are always weekends regardless of other overrides
        if d.weekday() >= 5:
            day_map[d] = DayMeta(day_type="weekend")
            continue

        # Special-day overrides (holidays, spring break, etc.)
        if d in specials:
            s = specials[d]
            day_map[d] = DayMeta(day_type=s["day_type"], notes=s.get("notes", []))
            # Non-academic specials don't consume a rotation slot
            continue

        # TEE week
        if tee_start and tee_end and tee_start <= d <= tee_end:
            day_map[d] = DayMeta(day_type="tee", notes=["TEE Week"])
            continue

        # Graduation week
        if grad_start and grad_end and grad_start <= d <= grad_end:
            day_map[d] = DayMeta(day_type="grad", notes=["Graduation Week"])
            continue

        # Reading/break days between end of instruction and TEE
        if d > end_instruction:
            day_map[d] = DayMeta(day_type="R", notes=["Post-instruction reading day"])
            continue

        # Regular academic day — assign current rotation slot and advance
        day_map[d] = DayMeta(day_type=current_type)
        current_type = "2" if current_type == "1" else "1"

    return day_map


class BaseCalendar:
    """
    Loaded academic calendar for a single semester.

    Provides:
      - get_day_meta(date) -> DayMeta
      - resolve_lesson(track, lesson_number) -> date | None
      - get_lesson_count(track) -> int
    """

    def __init__(self, ay: str, *, _day_map: Optional[dict[date, DayMeta]] = None):
        self.ay = ay
        self._banner: Optional[str] = None

        if _day_map is not None:
            self._day_map = _day_map
        else:
            self._day_map = self._load(ay)

        self._lesson_to_date: dict[int, dict[int, date]] = {1: {}, 2: {}}
        self._build_lesson_index()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self, ay: str) -> dict[date, DayMeta]:
        path = _DATA_DIR / f"{ay}.json"
        if not path.exists():
            logger.warning("Calendar file %s not found; searching for fallback", path)
            return self._load_fallback()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            # Try to layer in live scraper data (M6). Import here to avoid
            # a circular import at module load time.
            try:
                from core.scraper import fetch_calendar_updates
                updates = fetch_calendar_updates(ay)
                if updates and "special_days" in updates:
                    raw.setdefault("special_days", {}).update(updates["special_days"])
                    logger.info("Applied %d scraped special days", len(updates["special_days"]))
            except Exception as scrape_exc:
                logger.debug("Scraper skipped: %s", scrape_exc)
            return _build_day_map(raw)
        except Exception as exc:
            logger.error("Failed to parse %s: %s; using fallback", path, exc)
            self._banner = f"Calendar parse error for {ay}; using closest bundled fallback."
            return self._load_fallback()

    def _load_fallback(self) -> dict[date, DayMeta]:
        files = sorted(_DATA_DIR.glob("AY*.json"))
        if not files:
            raise RuntimeError(
                "No bundled calendar files found in data/base_calendars/. "
                "Cannot initialize BaseCalendar."
            )
        chosen = files[-1]
        logger.info("Falling back to bundled calendar: %s", chosen.name)
        if self._banner is None:
            self._banner = (
                f"Using bundled calendar from {chosen.stem}; "
                "online sync unavailable."
            )
        raw = json.loads(chosen.read_text(encoding="utf-8"))
        return _build_day_map(raw)

    # ------------------------------------------------------------------
    # Index
    # ------------------------------------------------------------------

    def _build_lesson_index(self) -> None:
        lesson_counts: dict[int, int] = {1: 0, 2: 0}
        for d in sorted(self._day_map):
            meta = self._day_map[d]
            if meta.is_academic and meta.track is not None:
                t = meta.track
                lesson_counts[t] += 1
                self._lesson_to_date[t][lesson_counts[t]] = d

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_day_meta(self, d: date) -> Optional[DayMeta]:
        return self._day_map.get(d)

    def resolve_lesson(self, course_track: int, lesson_number: int) -> Optional[date]:
        """Return the calendar date for lesson N of the given track (1 or 2).

        Returns None if the lesson number is out of range for this semester.
        """
        return self._lesson_to_date.get(course_track, {}).get(lesson_number)

    def get_lesson_count(self, track: int) -> int:
        return len(self._lesson_to_date.get(track, {}))

    def days(self) -> dict[date, DayMeta]:
        return dict(self._day_map)

    @property
    def banner(self) -> Optional[str]:
        """Non-None when the app should show a warning banner."""
        return self._banner

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def current(cls) -> "BaseCalendar":
        """Load the most appropriate calendar for today's date."""
        today = date.today()
        year = today.year % 100  # e.g. 2026 → 26
        # Semester 1 runs roughly Aug–Dec, semester 2 runs Jan–May
        sem = "1" if today.month >= 8 else "2"
        # AY designation: the year the semester ends in
        ay_year = year if sem == "2" else year + 1
        ay = f"AY{ay_year:02d}-{sem}"
        return cls(ay)
