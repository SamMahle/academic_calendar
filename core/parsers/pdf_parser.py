"""PDF syllabus parser using pdfplumber.

Scanned PDFs (low text yield per page) are detected and flagged for Copilot
handoff rather than attempted OCR — OCR is too unreliable and complex for v1.
"""

import io
from pathlib import Path
from typing import Union

from core.parsers import ParsedDoc

# Pages with fewer characters than this are considered scanned
_MIN_CHARS_PER_PAGE = 50

try:
    import pdfplumber as _pdfplumber
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


def parse_pdf(source: Union[Path, bytes, io.BytesIO]) -> ParsedDoc:
    """Parse a PDF file and return structured content.

    Returns is_scan=True when pdfplumber is unavailable or the PDF yields
    little text (likely a scan), so the caller can surface the Copilot panel.
    """
    if not _AVAILABLE:
        return ParsedDoc(is_scan=True)

    if isinstance(source, bytes):
        source = io.BytesIO(source)
    elif isinstance(source, Path):
        source = source.open("rb")

    result = ParsedDoc()
    lines: list[str] = []
    scan_pages = 0

    with _pdfplumber.open(source) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if len(text.strip()) < _MIN_CHARS_PER_PAGE:
                scan_pages += 1
                continue
            for line in text.splitlines():
                line = line.strip()
                if line:
                    result.paragraphs.append(line)
                    lines.append(line)
            for tbl in page.extract_tables() or []:
                rows = [[str(c or "").strip() for c in row] for row in tbl]
                result.tables.append(rows)
                for row in rows:
                    joined = "\t".join(c for c in row if c)
                    if joined:
                        lines.append(joined)

    result.full_text = "\n".join(lines)
    result.scan_page_count = scan_pages
    result.is_scan = scan_pages > 0 and not result.paragraphs
    return result
