"""ICS (RFC 5545) calendar renderer.

One VEVENT per extracted event. Course code is set as CATEGORIES so the file
can be filtered by course inside Outlook or Apple Calendar.
"""

import hashlib
from datetime import date

from icalendar import Calendar, Event as ICalEvent, vText

from core.models import Course, Event


def render_ics(events: list[Event], courses: list[Course], ay: str) -> bytes:
    cal = Calendar()
    cal.add("prodid", "-//CadetCal//EN")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", f"Cadet Calendar {ay}")
    cal.add("x-wr-timezone", "America/New_York")

    course_map: dict[str, Course] = {c.code: c for c in courses}

    for ev in sorted(events, key=lambda e: (e.date, e.course_code)):
        crs = course_map.get(ev.course_code)
        display_name = crs.short_name if crs else ev.course_code
        summary = f"[{display_name}] {ev.title}"

        desc_parts = [
            f"Course: {ev.course_code}",
            f"Type: {ev.event_type}",
        ]
        if ev.weight_pct is not None:
            desc_parts.append(f"Weight: {ev.weight_pct:.0f}%")
        if ev.lesson_ref:
            desc_parts.append(f"Lesson ref: {ev.lesson_ref}")
        if ev.notes:
            desc_parts.append(ev.notes)
        desc_parts.append(f"Confidence: {ev.confidence:.0%}")

        # Deterministic UID so re-imports don't create duplicates
        uid_seed = f"{ev.course_code}-{ev.event_type}-{ev.date.isoformat()}-{ev.title}"
        uid = hashlib.md5(uid_seed.encode()).hexdigest() + "@cadetcal"

        ie = ICalEvent()
        ie.add("summary", summary)
        ie.add("dtstart", ev.date)
        ie.add("dtend", ev.date)
        ie.add("categories", [vText(ev.course_code)])
        ie.add("description", "\n".join(desc_parts))
        ie["uid"] = uid
        cal.add_component(ie)

    return cal.to_ical()
