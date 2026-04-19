"""Tests for BaseCalendar: day map construction, lesson indexing, fallback."""

from datetime import date

import pytest

from core.base_calendar import BaseCalendar, _build_day_map


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_RAW = {
    "ay": "TEST",
    "semester": "Test",
    "start_date": "2025-01-06",
    "end_date": "2025-01-17",
    "tee_start": "2025-01-20",
    "tee_end": "2025-01-24",
    "grad_start": None,
    "grad_end": None,
    "first_academic_day_type": "1",
    "special_days": {
        "2025-01-15": {"day_type": "holiday", "notes": ["MLK Day"]}
    },
}


@pytest.fixture
def mini_calendar():
    day_map = _build_day_map(MINIMAL_RAW)
    return BaseCalendar("TEST", _day_map=day_map)


# ---------------------------------------------------------------------------
# Day map construction
# ---------------------------------------------------------------------------

class TestBuildDayMap:
    def test_weekends_are_always_weekend(self):
        dm = _build_day_map(MINIMAL_RAW)
        saturday = date(2025, 1, 11)
        sunday = date(2025, 1, 12)
        assert dm[saturday].day_type == "weekend"
        assert dm[sunday].day_type == "weekend"

    def test_holiday_override_applied(self):
        dm = _build_day_map(MINIMAL_RAW)
        mlk = date(2025, 1, 15)
        assert dm[mlk].day_type == "holiday"
        assert "MLK Day" in dm[mlk].notes

    def test_tee_days_marked(self):
        dm = _build_day_map(MINIMAL_RAW)
        tee_monday = date(2025, 1, 20)
        assert dm[tee_monday].day_type == "tee"

    def test_regular_days_alternate(self):
        dm = _build_day_map(MINIMAL_RAW)
        # Mon 2025-01-06 → Day 1, Tue → Day 2, Wed → Day 1, Thu → Day 2, Fri → Day 1
        assert dm[date(2025, 1, 6)].day_type == "1"
        assert dm[date(2025, 1, 7)].day_type == "2"
        assert dm[date(2025, 1, 8)].day_type == "1"
        assert dm[date(2025, 1, 9)].day_type == "2"
        assert dm[date(2025, 1, 10)].day_type == "1"

    def test_week2_continues_rotation_after_weekend(self):
        dm = _build_day_map(MINIMAL_RAW)
        # After Friday Jan 10 (Day 1), Monday Jan 13 should be Day 2
        assert dm[date(2025, 1, 10)].day_type == "1"
        assert dm[date(2025, 1, 13)].day_type == "2"

    def test_holiday_does_not_consume_rotation_slot(self):
        dm = _build_day_map(MINIMAL_RAW)
        # Wed Jan 15 is a holiday; Thu Jan 16 should continue as if Wed was skipped
        # Before holiday: Tue Jan 14 continues normal rotation
        assert dm[date(2025, 1, 15)].day_type == "holiday"
        # Thu Jan 16 should be the next slot after Tue Jan 14
        before_holiday = dm[date(2025, 1, 14)].day_type
        after_holiday = dm[date(2025, 1, 16)].day_type
        # They should be different (rotation continued)
        assert before_holiday != after_holiday

    def test_day_meta_is_academic(self):
        dm = _build_day_map(MINIMAL_RAW)
        assert dm[date(2025, 1, 6)].is_academic is True
        assert dm[date(2025, 1, 11)].is_academic is False  # weekend
        assert dm[date(2025, 1, 15)].is_academic is False  # holiday

    def test_day_meta_track(self):
        dm = _build_day_map(MINIMAL_RAW)
        assert dm[date(2025, 1, 6)].track == 1
        assert dm[date(2025, 1, 7)].track == 2
        assert dm[date(2025, 1, 11)].track is None  # weekend


# ---------------------------------------------------------------------------
# Lesson index
# ---------------------------------------------------------------------------

class TestLessonIndex:
    def test_first_lesson_track1(self, mini_calendar):
        d = mini_calendar.resolve_lesson(1, 1)
        assert d == date(2025, 1, 6)  # first Day-1 academic day

    def test_first_lesson_track2(self, mini_calendar):
        d = mini_calendar.resolve_lesson(2, 1)
        assert d == date(2025, 1, 7)  # first Day-2 academic day

    def test_lesson_count_is_positive(self, mini_calendar):
        assert mini_calendar.get_lesson_count(1) > 0
        assert mini_calendar.get_lesson_count(2) > 0

    def test_out_of_range_returns_none(self, mini_calendar):
        assert mini_calendar.resolve_lesson(1, 9999) is None

    def test_invalid_track_returns_none(self, mini_calendar):
        assert mini_calendar.resolve_lesson(3, 1) is None

    def test_holiday_not_counted_as_lesson(self, mini_calendar):
        # MLK Day (Jan 15) is a holiday so track counts should not include it
        for track in (1, 2):
            count = mini_calendar.get_lesson_count(track)
            for n in range(1, count + 1):
                d = mini_calendar.resolve_lesson(track, n)
                assert d != date(2025, 1, 15), f"Holiday leaked into lesson index track {track} #{n}"

    def test_tee_not_counted_as_lesson(self, mini_calendar):
        for track in (1, 2):
            count = mini_calendar.get_lesson_count(track)
            for n in range(1, count + 1):
                d = mini_calendar.resolve_lesson(track, n)
                assert d is not None
                assert not (date(2025, 1, 20) <= d <= date(2025, 1, 24)), (
                    f"TEE date leaked into lesson index track {track} #{n}"
                )

    def test_lesson_dates_are_in_order(self, mini_calendar):
        for track in (1, 2):
            count = mini_calendar.get_lesson_count(track)
            dates = [mini_calendar.resolve_lesson(track, n) for n in range(1, count + 1)]
            assert dates == sorted(dates), f"Lesson dates out of order for track {track}"


# ---------------------------------------------------------------------------
# AY26 bundled calendars (smoke tests on real data)
# ---------------------------------------------------------------------------

class TestAY26Calendars:
    def test_ay26_1_loads(self):
        cal = BaseCalendar("AY26-1")
        assert cal.get_lesson_count(1) > 30
        assert cal.get_lesson_count(2) > 30

    def test_ay26_2_loads(self):
        cal = BaseCalendar("AY26-2")
        assert cal.get_lesson_count(1) > 30
        assert cal.get_lesson_count(2) > 30

    def test_ay26_1_labor_day_is_holiday(self):
        cal = BaseCalendar("AY26-1")
        meta = cal.get_day_meta(date(2025, 9, 1))
        assert meta is not None
        assert meta.day_type == "holiday"

    def test_ay26_2_mlk_day_is_holiday(self):
        cal = BaseCalendar("AY26-2")
        meta = cal.get_day_meta(date(2026, 1, 19))
        assert meta is not None
        assert meta.day_type == "holiday"

    def test_ay26_2_spring_break_is_break(self):
        # Buff Card: Spring Break Mar 30 – Apr 3, 2026
        cal = BaseCalendar("AY26-2")
        for d in [date(2026, 3, 30), date(2026, 3, 31),
                  date(2026, 4, 1), date(2026, 4, 2), date(2026, 4, 3)]:
            meta = cal.get_day_meta(d)
            assert meta is not None
            assert meta.day_type == "break", f"{d} should be break"

    def test_ay26_1_tee_week(self):
        # Buff Card: TEE Dec 16-19, 2025
        cal = BaseCalendar("AY26-1")
        for day in range(16, 20):
            meta = cal.get_day_meta(date(2025, 12, day))
            if date(2025, 12, day).weekday() < 5:
                assert meta is not None
                assert meta.day_type == "tee", f"2025-12-{day} should be tee"

    def test_ay26_2_grad_week(self):
        cal = BaseCalendar("AY26-2")
        for day in range(18, 23):
            meta = cal.get_day_meta(date(2026, 5, day))
            if date(2026, 5, day).weekday() < 5:
                assert meta is not None
                assert meta.day_type == "grad", f"2026-05-{day} should be grad"

    def test_current_factory(self):
        # Just verifies it doesn't raise; may log a banner if AY doesn't match current date
        cal = BaseCalendar.current()
        assert cal is not None

    def test_unknown_ay_loads_fallback(self):
        cal = BaseCalendar("AY99-9")
        assert cal.banner is not None
        assert cal.get_lesson_count(1) > 0
