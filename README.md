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

### Option 1 — Hosted (zero install)

Visit the Streamlit Community Cloud link in the Releases section of this repo.
Syllabi are processed in-browser via the Streamlit server — see the privacy note
below if you have concerns about sensitive course materials.

### Option 2 — Local Python

```bash
git clone https://github.com/sammahle/academic_calendar.git
cd academic_calendar
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

### Option 3 — Standalone .exe

Download `cadetcal.exe` from the latest GitHub Release and double-click it.
It launches a local Streamlit server and opens your default browser. No install,
no internet required (uses bundled academic calendar as fallback).

---

## Privacy

- **Option 2 (local):** Nothing leaves your machine.
- **Option 3 (.exe):** Nothing leaves your machine.
- **Option 1 (hosted):** Uploaded files pass through Streamlit Community Cloud
  servers. Do not upload syllabi that contain information you consider sensitive.

---

## Milestones

| # | Description | Status |
|---|-------------|--------|
| M1 | Skeleton, models, base calendar | ✅ |
| M2 | DOCX parser → Excel renderer | 🔲 |
| M3 | Streamlit UI | 🔲 |
| M4 | PDF/XLSX parsers, ICS/PDF renderers | 🔲 |
| M5 | Copilot handoff | 🔲 |
| M6 | USMA calendar scraper | 🔲 |
| M7 | PyInstaller packaging | 🔲 |
| M8 | Polish and fixtures | 🔲 |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The highest-impact low-barrier
contribution is adding event detection patterns in `data/event_patterns.json`.

## License

MIT — see [LICENSE](LICENSE).
