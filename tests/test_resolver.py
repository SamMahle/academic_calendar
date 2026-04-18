"""Tests for the lesson-reference resolver."""

from datetime import date

import pytest

from core.base_calendar import BaseCalendar, _build_day_map
from core.resolver import LessonRef, parse_lesson_refs, resolve_all, resolve_ref


# ---------------------------------------------------------------------------
# Shared fixture
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
    "special_days": {},
}


@pytest.fixture
def mini_cal():
    return BaseCalendar("TEST", _day_map=_build_day_map(MINIMAL_RAW))


# ---------------------------------------------------------------------------
# parse_lesson_refs
# ---------------------------------------------------------------------------

class TestParseLessonRefs:
    def test_plain_lesson_number(self):
        refs = parse_lesson_refs("WPR on Lesson 5")
        assert len(refs) == 1
        assert refs[0].lesson_number == 5

    def test_abbreviated_lesson(self):
        refs = parse_lesson_refs("HW due L12")
        assert len(refs) == 1
        assert refs[0].lesson_number == 12

    def test_lesson_with_space(self):
        refs = parse_lesson_refs("Quiz at L 7")
        assert len(refs) == 1
        assert refs[0].lesson_number == 7

    def test_dash_range_uses_end_lesson(self):
        refs = parse_lesson_refs("Project covers L1-8")
        assert any(r.lesson_number == 8 for r in refs)

    def test_week_ref(self):
        refs = parse_lesson_refs("PS due Week 3")
        assert len(refs) == 1
        assert refs[0].week_number == 3

    def test_week_abbreviated(self):
        refs = parse_lesson_refs("Wk 2 quiz")
        assert len(refs) == 1
        assert refs[0].week_number == 2

    def test_multiple_refs_in_text(self):
        refs = parse_lesson_refs("WPR 1 at L5; WPR 2 at L10")
        lesson_nums = {r.lesson_number for r in refs}
        assert 5 in lesson_nums
        assert 10 in lesson_nums

    def test_no_refs(self):
        assert parse_lesson_refs("No date or lesson here") == []

    def test_raw_field_preserved(self):
        refs = parse_lesson_refs("Lesson 3 quiz")
        assert refs[0].raw == "Lesson 3"

    def test_default_track_propagated(self):
        refs = parse_lesson_refs("L5", default_track=2)
        assert refs[0].track == 2


# ---------------------------------------------------------------------------
# resolve_ref
# ---------------------------------------------------------------------------

class TestResolveRef:
    def test_lesson_number_resolves_track1(self, mini_cal):
        ref = LessonRef("L1", track=1, lesson_number=1)
        d = resolve_ref(ref, mini_cal, track=1)
        assert d == date(2025, 1, 6)

    def test_lesson_number_resolves_track2(self, mini_cal):
        ref = LessonRef("L1", track=2, lesson_number=1)
        d = resolve_ref(ref, mini_cal, track=2)
        assert d == date(2025, 1, 7)

    def test_week_ref_resolves_to_first_lesson_of_week(self, mini_cal):
        # Week 1, track 1: lessons 1-5; week 2: lessons 6-10
        ref = LessonRef("Week 1", week_number=1)
        d = resolve_ref(ref, mini_cal, track=1)
        expected = mini_cal.resolve_lesson(1, 1)
        assert d == expected

    def test_week2_ref_resolves_to_lesson_6(self, mini_cal):
        ref = LessonRef("Week 2", week_number=2)
        d = resolve_ref(ref, mini_cal, track=1)
        expected = mini_cal.resolve_lesson(1, 6)
        assert d == expected

    def test_out_of_range_returns_none(self, mini_cal):
        ref = LessonRef("L999", lesson_number=999)
        assert resolve_ref(ref, mini_cal, track=1) is None

    def test_ref_track_overrides_default(self, mini_cal):
        ref = LessonRef("L1", track=2, lesson_number=1)
        d = resolve_ref(ref, mini_cal, track=1)  # default track 1, but ref says track 2
        assert d == date(2025, 1, 7)  # track-2 first lesson


# ---------------------------------------------------------------------------
# resolve_all integration
# ---------------------------------------------------------------------------

class TestResolveAll:
    def test_resolves_multiple(self, mini_cal):
        results = resolve_all("WPR at L3, PS at L5", mini_cal, track=1)
        assert len(results) == 2
        for ref, d in results:
            assert d is not None

    def test_empty_text(self, mini_cal):
        assert resolve_all("No references here", mini_cal, track=1) == []
