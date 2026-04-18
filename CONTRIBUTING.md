# Contributing to CadetCal

Thanks for helping. The most impactful low-barrier contribution is improving
event detection patterns — no Python knowledge required.

## Adding event detection patterns

Open `data/event_patterns.json`. Each key under `event_type_keywords` maps an
event type to a list of text strings the extractor will recognize.

To add a new alias (e.g. your department calls WPRs "Periodic Exams"):

```json
"WPR": ["WPR", "Written Partial Review", "Periodic Exam"]
```

Submit a pull request with a one-sentence description of why the new alias is
needed. Link to a sanitized excerpt from the syllabus if possible.

## Adding regex patterns

`lesson_ref_patterns` and `date_patterns` accept Python regex strings. Test
your pattern with `python -c "import re; print(re.findall(r'YOUR_PATTERN', 'test text'))"`.
Include a comment in the PR describing what it matches.

## Fixing a date resolution bug

1. Add a failing test in `tests/test_resolver.py` or `tests/test_base_calendar.py`.
2. Fix the bug in `core/base_calendar.py` or `core/resolver.py`.
3. Confirm all tests pass: `pytest`.

## Updating base calendar data

If you have access to the official USMA Dean's Office academic calendar:

1. Update `data/base_calendars/AY<YY>-<S>.json` with correct dates.
2. Add a `_source` field citing the publication date and URL/document name.
3. Run the test suite to confirm lesson counts are still reasonable.

## Code style

- Python 3.11+
- `pydantic` for data models — don't bypass validators.
- No external AI/ML dependencies; keep it local-first.
- Keep functions short and testable.

## Sanitizing fixture syllabi

Before committing a real syllabus to `tests/fixtures/`:
- Remove instructor name, email, and phone number.
- Remove any student or grade information.
- Replace department-internal URLs with placeholder text.
