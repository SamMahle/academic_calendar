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

**[Open CadetCal](https://cadetcal.streamlit.app)** ← just click and go

Works in any browser. No account, no install, no setup.

> ⚠️ Replace the URL above with your Streamlit Community Cloud link after deploying from [share.streamlit.io](https://share.streamlit.io).

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

## Contributing

| # | Description | Status |
|---|-------------|--------|
| M1 | Skeleton, models, base calendar | ✅ |
| M2 | DOCX parser → Excel renderer | ✅ |
| M3 | Streamlit UI | ✅ |
| M4 | PDF/XLSX parsers, ICS/PDF renderers | ✅ |
| M5 | Copilot handoff | ✅ |
| M6 | USMA calendar scraper | ✅ |
| M7 | PyInstaller packaging | ✅ |
| M8 | Polish and fixtures | ✅ |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The highest-impact low-barrier
contribution is adding event detection patterns in `data/event_patterns.json`.

## License

MIT — see [LICENSE](LICENSE).
