# CadetCal

Automated USMA cadet semester calendar builder.

Upload your syllabi, review flagged extractions, and download a color-coded
Excel week-grid, `.ics` calendar file, and printable PDF — in minutes instead
of a day.

> **This is a cadet-built tool. It is not an official USMA or US Army product
> and has no affiliation with the Department of the Army or the United States
> Military Academy.**

---

## Quick Start

### Option 1 — Use the web app (no install)

**[Open CadetCal](https://academiccalendar-cadet.streamlit.app/)** ← just click and go

Works in any browser. No account, no install, no setup.

### Option 2 — Run locally (Windows / Mac)

For cadets who prefer to run everything on their own machine.

Requires **Python 3.11+** ([download](https://www.python.org/downloads/) — check "Add Python to PATH" on Windows).

1. [Download the repo as a zip](https://github.com/sammahle/academic_calendar/archive/refs/heads/main.zip) and extract it
2. **Windows:** double-click `run.bat`
3. **Mac:** double-click `run.command` (if blocked, right-click → Open)

First launch installs dependencies automatically (~1 min). After that it starts in seconds.

### Option 3 — Standalone .exe (coming soon)

A pre-built `cadetcal.exe` will be posted in GitHub Releases once tested on a cadet computer.

---

## How it works

1. **Upload** your syllabi (XLSX, DOCX, or PDF) — course code is auto-detected
   where possible; pick your section's track (Day 1 / Day 2) and a color.
2. **Review** the extracted events. Everything is confidence-scored; dates
   with stale template years are corrected automatically against the official
   academic calendar.
3. **Export** a color-coded Excel week-grid, an `.ics` file for Outlook /
   Google Calendar, and a printable PDF.

### Calendar data

Bundled semester calendars carry the exact Day-1/Day-2 class numbers from the
official USMA sources — the rotation is *not* strictly alternating, so lesson
references like "L15" resolve to the true date:

| Semester | Source |
|----------|--------|
| AY26-1 (Fall 2025) | Buff Card (`data/base_calendars/parse_buff_card.py`) |
| AY26-2 (Spring 2026) | Buff Card |
| AY27-1 (Fall 2026) | Dean's calendar grid (`data/base_calendars/parse_ay_grid.py`) |

When a new academic year is published, drop the source file into
`data/base_calendars/sources/` and re-run the matching parser script.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The highest-impact low-barrier
contribution is adding event detection patterns in `data/event_patterns.json`.

## License

MIT — see [LICENSE](LICENSE).
