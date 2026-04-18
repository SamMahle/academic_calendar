"""PDF renderer using ReportLab.

Produces a landscape Letter-size week-grid PDF that mirrors the Excel layout.
ReportLab is preferred over weasyprint for portability (no system GTK/Cairo deps).
"""

import io
from datetime import date, timedelta
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)

from core.base_calendar import BaseCalendar
from core.models import Course, Event

_DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def _hex(s: str) -> colors.HexColor:
    return colors.HexColor(f"#{s.lstrip('#')}")


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def render_pdf(
    events: list[Event],
    courses: list[Course],
    calendar: BaseCalendar,
    theme: dict,
    ay: str,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(LETTER),
        leftMargin=0.4 * inch,
        rightMargin=0.4 * inch,
        topMargin=0.4 * inch,
        bottomMargin=0.4 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title", parent=styles["Heading1"], fontSize=14, spaceAfter=6
    )
    cell_style = ParagraphStyle(
        "cell", fontSize=7, leading=9, wordWrap="CJK"
    )

    by_date: dict[date, list[Event]] = {}
    for ev in events:
        by_date.setdefault(ev.date, []).append(ev)
    course_map = {c.code: c for c in courses}

    cal_days = sorted(calendar.days())
    if not cal_days:
        raise ValueError("Calendar has no days")
    last_day = cal_days[-1]
    week_start = _monday(cal_days[0])

    # Column widths: Month ~0.55", 7 days share the rest
    page_w = landscape(LETTER)[0] - 0.8 * inch  # usable width
    month_w = 0.55 * inch
    day_w = (page_w - month_w) / 7
    col_widths = [month_w] + [day_w] * 7

    story = [Paragraph(f"Cadet Calendar — {ay}", title_style)]

    # Header row
    header = [""] + _DAYS
    tbl_data = [header]
    tbl_style = [
        ("BACKGROUND", (0, 0), (-1, 0), _hex(theme["day_header_fill"])),
        ("TEXTCOLOR", (0, 0), (-1, 0), _hex(theme["day_header_font"])),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
    ]

    row_idx = 1
    last_month: Optional[str] = None

    while week_start <= last_day:
        week = [week_start + timedelta(days=i) for i in range(7)]
        max_evts = max(len(by_date.get(d, [])) for d in week)
        n_evt = max(1, max_evts)

        month_label = week_start.strftime("%b").upper() if week_start.strftime("%b").upper() != last_month else ""
        last_month = week_start.strftime("%b").upper()

        # Date-number row
        date_row: list = [month_label]
        for d in week:
            meta = calendar.get_day_meta(d) if d <= last_day else None
            dt = meta.day_type if meta else "weekend"
            val = str(d.day) if d <= last_day else ""
            note = (meta.notes[0] if meta and meta.notes else "")
            txt = f"{val}\n{note}" if note else val
            date_row.append(Paragraph(txt, cell_style) if txt else "")

        tbl_data.append(date_row)
        r = row_idx

        # Color date cells
        for i, d in enumerate(week):
            col = i + 1
            meta = calendar.get_day_meta(d) if d <= last_day else None
            dt = meta.day_type if meta else "weekend"
            bg = (
                _hex(theme["tee_fill"]) if dt == "tee" else
                _hex(theme["grad_fill"]) if dt == "grad" else
                _hex(theme["holiday_fill"]) if dt in ("holiday", "break") else
                _hex(theme["weekend_fill"]) if dt == "weekend" else
                _hex(theme["day1_marker"]) if dt == "1" else
                _hex(theme["day2_marker"]) if dt == "2" else
                colors.white
            )
            tbl_style.append(("BACKGROUND", (col, r), (col, r), bg))
        row_idx += 1

        # Day-type row
        type_row: list = [""]
        for d in week:
            meta = calendar.get_day_meta(d) if d <= last_day else None
            dt = meta.day_type if meta else "weekend"
            label = (
                "D-1" if dt == "1" else "D-2" if dt == "2" else
                "HOL" if dt == "holiday" else "TEE" if dt == "tee" else
                "GRAD" if dt == "grad" else "BRK" if dt == "break" else ""
            )
            type_row.append(Paragraph(f"<b>{label}</b>", cell_style) if label else "")
        tbl_data.append(type_row)
        r = row_idx
        for i, d in enumerate(week):
            meta = calendar.get_day_meta(d) if d <= last_day else None
            dt = meta.day_type if meta else "weekend"
            bg = (
                _hex(theme["day1_marker"]) if dt == "1" else
                _hex(theme["day2_marker"]) if dt == "2" else
                _hex(theme["tee_fill"]) if dt == "tee" else
                _hex(theme["holiday_fill"]) if dt in ("holiday", "break") else
                _hex(theme["weekend_fill"])
            )
            tbl_style.append(("BACKGROUND", (i + 1, r), (i + 1, r), bg))
        row_idx += 1

        # Merge month cell vertically
        total_rows = 2 + n_evt
        tbl_style.append((
            "SPAN", (0, row_idx - 2), (0, row_idx - 2 + total_rows - 1)
        ))
        tbl_style.append(("BACKGROUND", (0, row_idx - 2), (0, row_idx - 2 + total_rows - 1),
                           _hex(theme["month_label_fill"])))
        tbl_style.append(("TEXTCOLOR", (0, row_idx - 2), (0, row_idx - 2 + total_rows - 1),
                           _hex(theme["month_label_font"])))

        # Event rows
        for slot in range(n_evt):
            evt_row: list = [""]
            for d in week:
                day_evts = by_date.get(d, [])
                meta = calendar.get_day_meta(d) if d <= last_day else None
                dt = meta.day_type if meta else "weekend"
                if slot < len(day_evts):
                    ev = day_evts[slot]
                    crs = course_map.get(ev.course_code)
                    color = crs.color if crs else "CCCCCC"
                    evt_row.append(Paragraph(f"<b>{ev.course_code} {ev.title}</b>", cell_style))
                    tbl_style.append(("BACKGROUND", (len(evt_row) - 1, row_idx), (len(evt_row) - 1, row_idx),
                                      _hex(color)))
                else:
                    evt_row.append("")
                    if dt in ("weekend", "R"):
                        tbl_style.append(("BACKGROUND", (len(evt_row) - 1, row_idx), (len(evt_row) - 1, row_idx),
                                          _hex(theme["weekend_fill"])))
            tbl_data.append(evt_row)
            row_idx += 1

        week_start += timedelta(weeks=1)

    # Row heights
    row_heights = [14]  # header
    for _ in range(row_idx - 1):
        row_heights.append(12)

    tbl = Table(tbl_data, colWidths=col_widths, rowHeights=row_heights)
    tbl.setStyle(TableStyle(tbl_style))
    story.append(tbl)

    doc.build(story)
    return buf.getvalue()
