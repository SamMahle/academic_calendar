"""CadetCal — Streamlit entry point.

M1: Loads the base academic calendar and displays a status banner.
Full UI is implemented across M2–M5.
"""

import streamlit as st

from core.base_calendar import BaseCalendar

st.set_page_config(
    page_title="CadetCal",
    page_icon="📅",
    layout="wide",
)

st.title("CadetCal")
st.caption("Automated cadet semester calendar builder")

# Load calendar and surface any fallback banner
cal = BaseCalendar.current()
if cal.banner:
    st.warning(cal.banner)
else:
    st.success(f"Loaded academic calendar: **{cal.ay}**")

st.info(
    "Upload functionality coming in M2. "
    f"Track 1 has **{cal.get_lesson_count(1)}** lessons this semester; "
    f"Track 2 has **{cal.get_lesson_count(2)}** lessons."
)
