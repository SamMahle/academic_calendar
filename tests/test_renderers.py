"""Tests for Excel, ICS, and Copilot renderers."""

from datetime import date

import pytest

from core.base_calendar import BaseCalendar, _build_day_map
from core.models import Course, Event

_RAW = {
    "ay": "TEST",
    "semester": "Test",
    "start_date": "2026-01-05",
    "end_date": "2026-04-24",
    "tee_start": "2026-04-27",
    "tee_end": "2026-05-08",
    "grad_start": "2026-05-18",
    "grad_end": "2026-05-22",
    "first_academic_day_type": "1",
    "special_days": {
        "2026-01-19": {"day_type": "holiday", "notes": ["MLK Day"]},
    },
}


@pytest.fixture
def mini_cal():
    return BaseCalendar("TEST", _day_map=_build_day_map(_RAW))


@pytest.fixture
def sample_courses():
    return [
        Course(code="MA364", short_name="DiffEq", track=1, color="4ECDC4"),
        Course(code="PH201", short_name="Physics", track=2, color="FF6B6B"),
    ]


@pytest.fixture
def sample_events():
    return [
        Event(course_code="MA364", event_type="WPR", title="WPR 1",
              date=date(2026, 2, 4), confidence=0.9, source="parsed"),
        Event(course_code="MA364", event_type="WPR", title="WPR 2",
              date=date(2026, 3, 11), confidence=0.9, source="parsed"),
        Event(course_code="PH201", event_type="Lab", title="Lab Report 1",
              date=date(2026, 2, 11), weight_pct=10.0, confidence=0.8, source="parsed"),
        Event(course_code="PH201", event_type="TEE", title="TEE",
              date=date(2026, 4, 27), confidence=1.0, source="parsed"),
    ]


# ---------------------------------------------------------------------------
# Excel renderer
# ---------------------------------------------------------------------------

class TestExcelRenderer:
    def test_produces_bytes(self, mini_cal, sample_courses, sample_events):
        from core.renderers.excel_renderer import render_excel
        from data_helpers import classic_theme
        result = render_excel(sample_events, sample_courses, mini_cal, classic_theme(), "TEST")
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_valid_xlsx(self, mini_cal, sample_courses, sample_events):
        from io import BytesIO
        from openpyxl import load_workbook
        from core.renderers.excel_renderer import render_excel
        from data_helpers import classic_theme
        data = render_excel(sample_events, sample_courses, mini_cal, classic_theme(), "TEST")
        wb = load_workbook(BytesIO(data))
        assert wb is not None
        assert wb.active is not None

    def test_empty_events_no_crash(self, mini_cal, sample_courses):
        from core.renderers.excel_renderer import render_excel
        from data_helpers import classic_theme
        result = render_excel([], sample_courses, mini_cal, classic_theme(), "TEST")
        assert isinstance(result, bytes)


# ---------------------------------------------------------------------------
# ICS renderer
# ---------------------------------------------------------------------------

class TestIcsRenderer:
    def test_produces_bytes(self, sample_courses, sample_events):
        from core.renderers.ics_renderer import render_ics
        result = render_ics(sample_events, sample_courses, "TEST")
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_valid_ical(self, sample_courses, sample_events):
        from icalendar import Calendar
        from core.renderers.ics_renderer import render_ics
        data = render_ics(sample_events, sample_courses, "TEST")
        cal = Calendar.from_ical(data)
        vevents = [c for c in cal.walk() if c.name == "VEVENT"]
        assert len(vevents) == len(sample_events)

    def test_uid_deterministic(self, sample_courses, sample_events):
        from icalendar import Calendar
        from core.renderers.ics_renderer import render_ics
        data1 = render_ics(sample_events, sample_courses, "TEST")
        data2 = render_ics(sample_events, sample_courses, "TEST")
        cal1 = Calendar.from_ical(data1)
        cal2 = Calendar.from_ical(data2)
        uids1 = {str(c["uid"]) for c in cal1.walk() if c.name == "VEVENT"}
        uids2 = {str(c["uid"]) for c in cal2.walk() if c.name == "VEVENT"}
        assert uids1 == uids2

    def test_course_code_in_categories(self, sample_courses, sample_events):
        from icalendar import Calendar
        from core.renderers.ics_renderer import render_ics
        data = render_ics(sample_events, sample_courses, "TEST")
        cal = Calendar.from_ical(data)
        all_cats = []
        for c in cal.walk():
            if c.name == "VEVENT":
                cats = c.get("categories")
                if cats:
                    all_cats.extend([str(v) for v in cats.cats])
        assert "MA364" in all_cats or "PH201" in all_cats

    def test_empty_events(self, sample_courses):
        from icalendar import Calendar
        from core.renderers.ics_renderer import render_ics
        data = render_ics([], sample_courses, "TEST")
        cal = Calendar.from_ical(data)
        assert cal is not None


# ---------------------------------------------------------------------------
# Copilot paste-back parser
# ---------------------------------------------------------------------------

class TestCopilotParser:
    _TABLE = """
| Event Type | Event Name | Due Date (DD MMM YYYY) | Lesson Reference | Weight (%) |
|------------|------------|------------------------|------------------|------------|
| WPR | WPR 1 | 04 Feb 2026 | L10 | 20 |
| TEE | TEE | 04 May 2026 | | 30 |
| HW | PS #3 | TBD | L5 | 5 |
"""

    def test_parses_events(self, mini_cal):
        from core.copilot import parse_copilot_table
        events = parse_copilot_table(self._TABLE, "MA364", mini_cal)
        assert len(events) >= 2  # WPR + TEE have valid dates; PS has TBD

    def test_event_types_correct(self, mini_cal):
        from core.copilot import parse_copilot_table
        events = parse_copilot_table(self._TABLE, "MA364", mini_cal)
        types = {e.event_type for e in events}
        assert "WPR" in types
        assert "TEE" in types

    def test_tbd_date_skipped(self, mini_cal):
        from core.copilot import parse_copilot_table
        events = parse_copilot_table(self._TABLE, "MA364", mini_cal)
        # PS #3 has TBD date — should not appear
        assert all(e.title != "PS #3" for e in events)

    def test_weight_parsed(self, mini_cal):
        from core.copilot import parse_copilot_table
        events = parse_copilot_table(self._TABLE, "MA364", mini_cal)
        wpr = next((e for e in events if e.event_type == "WPR"), None)
        assert wpr is not None
        assert wpr.weight_pct == 20.0

    def test_source_is_copilot(self, mini_cal):
        from core.copilot import parse_copilot_table
        events = parse_copilot_table(self._TABLE, "MA364", mini_cal)
        assert all(e.source == "copilot" for e in events)

    def test_empty_input(self, mini_cal):
        from core.copilot import parse_copilot_table
        assert parse_copilot_table("", "MA364", mini_cal) == []

    def test_malformed_input_no_crash(self, mini_cal):
        from core.copilot import parse_copilot_table
        parse_copilot_table("not a table at all", "MA364", mini_cal)
