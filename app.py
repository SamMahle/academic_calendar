"""CadetCal — Streamlit entry point.

Three-step flow:
  1. Upload syllabi + configure courses
  2. Review extracted events (confidence-highlighted, editable)
  3. Export calendar (xlsx / ics / pdf)
"""

import hashlib
import io
import json
import logging
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from core.base_calendar import BaseCalendar
from core.confidence import THRESHOLD_AUTO_ACCEPT, THRESHOLD_COPILOT_HANDOFF
from core.copilot import get_prompt, parse_copilot_table
from core.models import Course, Event
from core.parsers import ParsedDoc
from core.parsers.event_extractor import extract_events

logging.basicConfig(level=logging.WARNING)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="CadetCal",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_THEMES_FILE = Path(__file__).parent / "data" / "themes.json"
_THEMES: dict = json.loads(_THEMES_FILE.read_text())

_DEFAULT_COLORS = _THEMES["classic"]["default_course_colors"]

_AY_OPTIONS = ["AY26-2", "AY26-1"]  # most recent first


def _course_color(code: str, used: list[str]) -> str:
    idx = int(hashlib.md5(code.encode()).hexdigest(), 16) % len(_DEFAULT_COLORS)
    # Try to avoid reusing colors already in use
    for offset in range(len(_DEFAULT_COLORS)):
        c = _DEFAULT_COLORS[(idx + offset) % len(_DEFAULT_COLORS)]
        if c not in used:
            return c
    return _DEFAULT_COLORS[idx]


def _parse_uploaded(file_bytes: bytes, filename: str) -> ParsedDoc:
    ext = Path(filename).suffix.lower()
    if ext == ".docx":
        from core.parsers.docx_parser import parse_docx
        return parse_docx(file_bytes)
    if ext == ".pdf":
        from core.parsers.pdf_parser import parse_pdf
        return parse_pdf(file_bytes)
    if ext in (".xlsx", ".xls"):
        from core.parsers.xlsx_parser import parse_xlsx
        return parse_xlsx(file_bytes)
    return ParsedDoc()  # empty


def _events_df(events: list[Event]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Course": e.course_code,
            "Type": e.event_type,
            "Title": e.title,
            "Date": e.date.isoformat(),
            "Weight %": e.weight_pct,
            "Lesson Ref": e.lesson_ref or "",
            "Confidence": f"{e.confidence:.0%}",
            "Source": e.source,
            "Notes": e.notes or "",
        }
        for e in events
    ])


def _confidence_style(val: str) -> str:
    try:
        pct = float(val.strip("%")) / 100
    except ValueError:
        return ""
    if pct >= THRESHOLD_AUTO_ACCEPT:
        return "background-color: #d4edda"
    if pct >= THRESHOLD_COPILOT_HANDOFF:
        return "background-color: #fff3cd"
    return "background-color: #f8d7da"


def _render_excel(events, courses, cal, theme_name):
    from core.renderers.excel_renderer import render_excel
    return render_excel(events, courses, cal, _THEMES[theme_name], cal.ay)


def _render_ics(events, courses, cal):
    from core.renderers.ics_renderer import render_ics
    return render_ics(events, courses, cal.ay)


def _render_pdf(events, courses, cal, theme_name):
    try:
        from core.renderers.pdf_renderer import render_pdf
        return render_pdf(events, courses, cal, _THEMES[theme_name], cal.ay)
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------

def _init_state():
    defaults = {
        "step": "upload",
        "ay": _AY_OPTIONS[0],
        "calendar": None,
        "uploads": [],        # list of {filename, doc, course_code, short_name, track, color}
        "events": [],         # list of Event (final, after review)
        "courses": [],        # list of Course
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_state()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("📅 CadetCal")
    st.caption("Cadet semester calendar builder")
    st.divider()

    ay_choice = st.selectbox(
        "Academic Year",
        _AY_OPTIONS,
        index=_AY_OPTIONS.index(st.session_state.ay),
        key="ay_selector",
    )
    if ay_choice != st.session_state.ay:
        st.session_state.ay = ay_choice
        st.session_state.calendar = None  # force reload

    if st.session_state.calendar is None or st.session_state.calendar.ay != st.session_state.ay:
        with st.spinner("Loading academic calendar…"):
            st.session_state.calendar = BaseCalendar(st.session_state.ay)

    cal: BaseCalendar = st.session_state.calendar
    if cal.banner:
        st.warning(cal.banner, icon="⚠️")
    else:
        st.success(f"Calendar loaded: **{cal.ay}**", icon="✅")
        st.caption(
            f"Track 1: {cal.get_lesson_count(1)} lessons  |  "
            f"Track 2: {cal.get_lesson_count(2)} lessons"
        )

    st.divider()
    if st.session_state.step != "upload":
        if st.button("← Start Over", use_container_width=True):
            st.session_state.step = "upload"
            st.session_state.uploads = []
            st.session_state.events = []
            st.session_state.courses = []
            st.rerun()

    st.divider()
    st.caption(
        "CadetCal is a cadet-built tool. "
        "Not affiliated with USMA or the US Army."
    )

# ---------------------------------------------------------------------------
# Step indicator
# ---------------------------------------------------------------------------

steps = {"upload": 1, "review": 2, "export": 3}
current = steps.get(st.session_state.step, 1)

col1, col2, col3 = st.columns(3)
for col, label, num in [(col1, "1 · Upload", 1), (col2, "2 · Review", 2), (col3, "3 · Export", 3)]:
    with col:
        if num == current:
            st.markdown(f"**:blue[{label}]**")
        elif num < current:
            st.markdown(f"~~{label}~~ ✓")
        else:
            st.markdown(f"*{label}*")

st.divider()

# ---------------------------------------------------------------------------
# STEP 1 — Upload
# ---------------------------------------------------------------------------

if st.session_state.step == "upload":
    st.header("Upload Syllabi")
    st.write("Upload one file per course. Accepted: PDF, DOCX, XLSX.")

    uploaded = st.file_uploader(
        "Syllabi",
        type=["pdf", "docx", "xlsx"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if uploaded:
        used_colors: list[str] = [u.get("color", "") for u in st.session_state.uploads]
        # Add new uploads (avoid duplicates by filename)
        existing_names = {u["filename"] for u in st.session_state.uploads}
        for f in uploaded:
            if f.name not in existing_names:
                existing_names.add(f.name)
                suggested_code = Path(f.name).stem.upper()[:8]
                st.session_state.uploads.append({
                    "filename": f.name,
                    "bytes": f.read(),
                    "doc": None,
                    "course_code": suggested_code,
                    "short_name": suggested_code,
                    "track": 1,
                    "color": _course_color(suggested_code, used_colors),
                })
                used_colors.append(st.session_state.uploads[-1]["color"])

    if st.session_state.uploads:
        st.subheader("Configure Courses")
        for idx, upload in enumerate(st.session_state.uploads):
            with st.expander(f"📄 {upload['filename']}", expanded=True):
                c1, c2, c3, c4, c5 = st.columns([2, 2, 1, 1, 1])
                with c1:
                    code = st.text_input(
                        "Course Code", value=upload["course_code"],
                        key=f"code_{idx}"
                    ).strip().upper()
                with c2:
                    name = st.text_input(
                        "Short Name", value=upload["short_name"],
                        key=f"name_{idx}"
                    ).strip()
                with c3:
                    track = st.radio(
                        "Track", [1, 2], index=upload["track"] - 1,
                        key=f"track_{idx}", horizontal=True
                    )
                with c4:
                    color = st.color_picker(
                        "Color", value=f"#{upload['color']}",
                        key=f"color_{idx}"
                    ).lstrip("#")
                with c5:
                    if st.button("🗑", key=f"del_{idx}", help="Remove"):
                        st.session_state.uploads.pop(idx)
                        st.rerun()

                st.session_state.uploads[idx].update({
                    "course_code": code, "short_name": name,
                    "track": track, "color": color,
                })

        st.divider()
        if st.button("Extract Events →", type="primary", use_container_width=True):
            all_events: list[Event] = []
            all_courses: list[Course] = []
            scans: list[str] = []

            with st.spinner("Parsing syllabi…"):
                for up in st.session_state.uploads:
                    doc = _parse_uploaded(up["bytes"], up["filename"])
                    if doc.is_scan:
                        scans.append(up["filename"])
                    events = extract_events(doc, up["course_code"], up["track"], cal)
                    all_events.extend(events)
                    all_courses.append(Course(
                        code=up["course_code"],
                        short_name=up["short_name"],
                        track=up["track"],
                        color=up["color"],
                        events=events,
                    ))

            st.session_state.events = all_events
            st.session_state.courses = all_courses
            if scans:
                st.warning(f"Scanned PDF detected: {', '.join(scans)}. Use the Copilot panel in Step 2.")
            st.session_state.step = "review"
            st.rerun()
    else:
        st.info("Upload at least one syllabus to continue.")

# ---------------------------------------------------------------------------
# STEP 2 — Review
# ---------------------------------------------------------------------------

elif st.session_state.step == "review":
    st.header("Review Events")
    events: list[Event] = st.session_state.events
    cal: BaseCalendar = st.session_state.calendar

    if not events:
        st.warning("No events were extracted. Use the Copilot panel below or add events manually.")
    else:
        n_review = sum(1 for e in events if e.confidence < THRESHOLD_AUTO_ACCEPT)
        n_handoff = sum(1 for e in events if e.confidence < THRESHOLD_COPILOT_HANDOFF)
        met1, met2, met3 = st.columns(3)
        met1.metric("Total Events", len(events))
        met2.metric("Need Review", n_review, help="Confidence < 70%")
        met3.metric("Copilot Suggested", n_handoff, help="Confidence < 40%")

        st.caption(
            "🟢 ≥70% auto-accepted · 🟡 40–69% needs review · 🔴 <40% consider Copilot handoff"
        )
        df = _events_df(events)
        styled = df.style.applymap(_confidence_style, subset=["Confidence"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Edit / delete individual events ────────────────────────────────────
    with st.expander("✏️ Edit or delete events"):
        if events:
            for idx, ev in enumerate(list(events)):
                cols = st.columns([3, 2, 2, 1])
                with cols[0]:
                    st.text(f"{ev.course_code} · {ev.title}")
                with cols[1]:
                    st.text(ev.date.isoformat())
                with cols[2]:
                    st.text(f"Conf: {ev.confidence:.0%}")
                with cols[3]:
                    if st.button("🗑", key=f"rm_{idx}"):
                        st.session_state.events.pop(idx)
                        st.rerun()
        else:
            st.info("No events to edit.")

    # ── Add manual event ────────────────────────────────────────────────────
    with st.expander("➕ Add manual event"):
        course_codes = [c.code for c in st.session_state.courses] or [""]
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            m_code = st.selectbox("Course", course_codes, key="m_code")
            m_type = st.selectbox(
                "Type",
                ["WPR", "TEE", "Writ", "PS", "HW", "Quiz", "Lab", "Project", "Other"],
                key="m_type",
            )
        with mc2:
            m_title = st.text_input("Title", key="m_title")
            m_date = st.date_input("Date", key="m_date")
        with mc3:
            m_weight = st.number_input("Weight %", min_value=0.0, max_value=100.0, value=0.0, key="m_weight")
            m_notes = st.text_input("Notes (optional)", key="m_notes")

        if st.button("Add Event", key="add_manual"):
            if m_title and m_code:
                st.session_state.events.append(Event(
                    course_code=m_code,
                    event_type=m_type,  # type: ignore[arg-type]
                    title=m_title,
                    date=m_date,
                    weight_pct=m_weight or None,
                    confidence=1.0,
                    source="manual",
                    notes=m_notes or None,
                ))
                st.success(f"Added: {m_code} {m_title}")
                st.rerun()

    # ── Copilot handoff ─────────────────────────────────────────────────────
    low_conf = [e for e in events if e.confidence < THRESHOLD_COPILOT_HANDOFF]
    scanned_uploads = [u for u in st.session_state.uploads
                       if _parse_uploaded(u["bytes"], u["filename"]).is_scan
                       ] if not events else []

    needs_copilot = bool(low_conf or scanned_uploads)
    with st.expander(
        f"🤖 Copilot Handoff {'⚠️ Recommended' if needs_copilot else '(optional)'}",
        expanded=needs_copilot,
    ):
        if low_conf:
            st.info(f"{len(low_conf)} event(s) have low confidence. Copilot can extract them more reliably.")
        st.subheader("1. Copy this prompt into Microsoft 365 Copilot")
        prompt_text = get_prompt()
        st.code(prompt_text, language="markdown")

        st.subheader("2. Paste Copilot's table output here")
        copilot_course = st.selectbox(
            "Course for pasted events",
            [c.code for c in st.session_state.courses] or [""],
            key="copilot_course",
        )
        pasted = st.text_area("Paste markdown table here", height=200, key="copilot_paste")
        if st.button("Import Copilot Events", key="import_copilot"):
            if pasted.strip():
                new_events = parse_copilot_table(pasted, copilot_course, cal)
                if new_events:
                    st.session_state.events.extend(new_events)
                    st.success(f"Imported {len(new_events)} event(s) from Copilot.")
                    st.rerun()
                else:
                    st.error("Could not parse the table. Check the format and try again.")

    st.divider()
    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("← Back to Upload"):
            st.session_state.step = "upload"
            st.rerun()
    with col_next:
        if st.button("Proceed to Export →", type="primary"):
            st.session_state.step = "export"
            st.rerun()

# ---------------------------------------------------------------------------
# STEP 3 — Export
# ---------------------------------------------------------------------------

elif st.session_state.step == "export":
    st.header("Export Calendar")
    events: list[Event] = st.session_state.events
    courses: list[Course] = st.session_state.courses
    cal: BaseCalendar = st.session_state.calendar

    if not events:
        st.warning("No events to export. Go back and add events.")
    else:
        st.metric("Events to export", len(events))

    theme_name = st.radio(
        "Theme",
        ["classic", "modern", "print"],
        format_func=lambda x: _THEMES[x]["description"],
        horizontal=True,
    )

    st.divider()

    dl1, dl2, dl3 = st.columns(3)

    with dl1:
        st.subheader("📊 Excel (.xlsx)")
        if st.button("Generate Excel", use_container_width=True):
            with st.spinner("Building week-grid…"):
                try:
                    xlsx_bytes = _render_excel(events, courses, cal, theme_name)
                    st.download_button(
                        "⬇ Download .xlsx",
                        data=xlsx_bytes,
                        file_name=f"cadetcal_{cal.ay}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
                except Exception as exc:
                    st.error(f"Excel render failed: {exc}")

    with dl2:
        st.subheader("📆 Calendar (.ics)")
        if st.button("Generate ICS", use_container_width=True):
            with st.spinner("Building calendar file…"):
                try:
                    ics_bytes = _render_ics(events, courses, cal)
                    st.download_button(
                        "⬇ Download .ics",
                        data=ics_bytes,
                        file_name=f"cadetcal_{cal.ay}.ics",
                        mime="text/calendar",
                        use_container_width=True,
                    )
                except Exception as exc:
                    st.error(f"ICS render failed: {exc}")

    with dl3:
        st.subheader("🖨 PDF (.pdf)")
        if st.button("Generate PDF", use_container_width=True):
            with st.spinner("Building PDF…"):
                try:
                    pdf_bytes = _render_pdf(events, courses, cal, theme_name)
                    if pdf_bytes:
                        st.download_button(
                            "⬇ Download .pdf",
                            data=pdf_bytes,
                            file_name=f"cadetcal_{cal.ay}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                        )
                    else:
                        st.warning("PDF renderer unavailable. Install `reportlab` to enable PDF export.")
                except Exception as exc:
                    st.error(f"PDF render failed: {exc}")

    st.divider()
    if st.button("← Back to Review"):
        st.session_state.step = "review"
        st.rerun()
