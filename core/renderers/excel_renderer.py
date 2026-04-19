"""Week-grid Excel renderer.

Layout (8 columns):
  A         B–H
  Month     Mon Tue Wed Thu Fri Sat Sun

For each calendar week, three row groups are written:
  1. Date-number row  (shows day of month, special fills for TEE/holiday)
  2. Day-type row     (D-1, D-2, HOL, TEE, BRK …)
  3. N event rows     (one per concurrent event in the busiest day of that week)

The month label in column A is merged vertically across all rows of the week
and re-printed each time the month changes.
"""

import io
from datetime import date, timedelta
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from core.base_calendar import BaseCalendar
from core.models import Course, Event

_DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
_MONTH_COL = 1      # column A
_FIRST_DAY_COL = 2  # column B (Monday)


def _thin() -> Border:
    s = Side(style="thin")
    return Border(left=s, right=s, top=s, bottom=s)


def _fill(hex_color: str) -> PatternFill:
    return PatternFill("solid", fgColor=hex_color.lstrip("#"))


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _day_label_and_fills(meta, theme: dict) -> tuple[str, str, str]:
    """Return (label, fill_hex, font_hex) for the day-type row."""
    if meta is None:
        return "", theme["weekend_fill"], theme["weekend_font"]
    dt = meta.day_type
    if dt == "1":
        return "D-1", theme["day1_marker"], "2E75B6"
    if dt == "2":
        return "D-2", theme["day2_marker"], "375623"
    if dt == "holiday":
        return "HOL", theme["holiday_fill"], theme["holiday_font"]
    if dt == "tee":
        return "TEE", theme["tee_fill"], theme["tee_font"]
    if dt == "grad":
        return "GRAD", theme["grad_fill"], theme["grad_font"]
    if dt == "break":
        return "BRK", theme["holiday_fill"], theme["holiday_font"]
    return "", theme["weekend_fill"], theme["weekend_font"]


def render_excel(
    events: list[Event],
    courses: list[Course],
    calendar: BaseCalendar,
    theme: dict,
    ay: str,
) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = ay[:31]

    # Column widths
    ws.column_dimensions[get_column_letter(_MONTH_COL)].width = 7
    for i in range(7):
        ws.column_dimensions[get_column_letter(_FIRST_DAY_COL + i)].width = 13

    # Event lookup
    by_date: dict[date, list[Event]] = {}
    for ev in events:
        by_date.setdefault(ev.date, []).append(ev)

    course_map: dict[str, Course] = {c.code: c for c in courses}

    cal_days = sorted(calendar.days())
    if not cal_days:
        raise ValueError("Calendar has no days")
    start_mon = _monday(cal_days[0])
    last_day = cal_days[-1]

    row = 1

    # ── Title row ──────────────────────────────────────────────────────────
    tc = ws.cell(row=row, column=_MONTH_COL, value=f"Cadet Calendar — {ay}")
    tc.font = Font(bold=True, size=14, color=theme["header_font"])
    tc.fill = _fill(theme["header_fill"])
    tc.alignment = Alignment(horizontal="center", vertical="center")
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
    ws.row_dimensions[row].height = 24
    row += 1

    # ── Day-name header row ────────────────────────────────────────────────
    ws.cell(row=row, column=_MONTH_COL, value="").fill = _fill(theme["day_header_fill"])
    for i, name in enumerate(_DAYS):
        c = ws.cell(row=row, column=_FIRST_DAY_COL + i, value=name)
        c.font = Font(bold=True, color=theme["day_header_font"])
        c.fill = _fill(theme["day_header_fill"])
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = _thin()
    ws.row_dimensions[row].height = 18
    row += 1

    # ── Weeks ──────────────────────────────────────────────────────────────
    week_start = start_mon
    last_month_label: Optional[str] = None

    while week_start <= last_day:
        week = [week_start + timedelta(days=i) for i in range(7)]
        max_events = max(len(by_date.get(d, [])) for d in week)
        n_evt_rows = max(1, max_events)
        total = 2 + n_evt_rows  # date row + type row + event rows

        month_label = week_start.strftime("%b").upper()

        # ── Date-number row ────────────────────────────────────────────────
        date_row = row
        for i, d in enumerate(week):
            col = _FIRST_DAY_COL + i
            meta = calendar.get_day_meta(d) if d <= last_day else None
            dt = meta.day_type if meta else "weekend"

            if dt == "weekend":
                fgc, fnt = theme["weekend_fill"], theme["weekend_font"]
            elif dt == "holiday":
                fgc, fnt = theme["holiday_fill"], theme["holiday_font"]
            elif dt == "break":
                fgc, fnt = theme["holiday_fill"], theme["holiday_font"]
            elif dt == "tee":
                fgc, fnt = theme["tee_fill"], theme["tee_font"]
            elif dt == "grad":
                fgc, fnt = theme["grad_fill"], theme["grad_font"]
            elif dt == "1":
                fgc, fnt = theme["day1_marker"], "000000"
            elif dt == "2":
                fgc, fnt = theme["day2_marker"], "000000"
            else:
                fgc, fnt = "FFFFFF", "000000"

            day_val = d.day if d <= last_day else ""
            note = ""
            if meta and meta.notes:
                note = f"\n{meta.notes[0]}"

            c = ws.cell(row=date_row, column=col, value=f"{day_val}{note}" if note else day_val)
            c.font = Font(bold=True, size=10, color=fnt)
            c.fill = _fill(fgc)
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=bool(note))
            c.border = _thin()
        ws.row_dimensions[date_row].height = 16

        # ── Day-type row ───────────────────────────────────────────────────
        type_row = row + 1
        for i, d in enumerate(week):
            col = _FIRST_DAY_COL + i
            meta = calendar.get_day_meta(d) if d <= last_day else None
            label, fgc, fnt = _day_label_and_fills(meta, theme)
            c = ws.cell(row=type_row, column=col, value=label)
            c.font = Font(size=8, bold=True, color=fnt)
            c.fill = _fill(fgc)
            c.alignment = Alignment(horizontal="center", vertical="center")
            c.border = _thin()
        ws.row_dimensions[type_row].height = 12

        # ── Event rows ─────────────────────────────────────────────────────
        for slot in range(n_evt_rows):
            evt_row = row + 2 + slot
            for i, d in enumerate(week):
                col = _FIRST_DAY_COL + i
                day_evts = by_date.get(d, [])
                meta = calendar.get_day_meta(d) if d <= last_day else None
                dt = meta.day_type if meta else "weekend"

                if slot < len(day_evts):
                    ev = day_evts[slot]
                    crs = course_map.get(ev.course_code)
                    color = crs.color if crs else "CCCCCC"
                    label = f"{ev.course_code} {ev.title}"
                    c = ws.cell(row=evt_row, column=col, value=label)
                    c.fill = _fill(color)
                    c.font = Font(size=8, bold=True, color="000000")
                    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                    c.border = _thin()
                else:
                    c = ws.cell(row=evt_row, column=col, value="")
                    if dt in ("weekend", "R"):
                        c.fill = _fill(theme["weekend_fill"])
                    elif dt in ("holiday", "break"):
                        c.fill = _fill(theme["holiday_fill"])
                    elif dt == "tee":
                        c.fill = _fill(theme["tee_fill"])
                    elif dt == "grad":
                        c.fill = _fill(theme["grad_fill"])
                    c.border = _thin()
            ws.row_dimensions[evt_row].height = 16

        # ── Month label (column A, merged across all rows of this week) ────
        mc = ws.cell(row=row, column=_MONTH_COL)
        if month_label != last_month_label:
            mc.value = month_label
            last_month_label = month_label
        mc.font = Font(bold=True, size=9, color=theme["month_label_font"])
        mc.fill = _fill(theme["month_label_fill"])
        mc.alignment = Alignment(horizontal="center", vertical="center", text_rotation=90)
        mc.border = _thin()
        if total > 1:
            ws.merge_cells(
                start_row=row, start_column=_MONTH_COL,
                end_row=row + total - 1, end_column=_MONTH_COL,
            )

        row += total
        week_start += timedelta(weeks=1)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
