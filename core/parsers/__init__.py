from dataclasses import dataclass, field
from typing import Any


@dataclass
class SheetData:
    """One worksheet with raw (typed) cell values — datetimes preserved."""
    name: str
    rows: list[list[Any]] = field(default_factory=list)


@dataclass
class ParsedDoc:
    """Normalized output from any syllabus parser."""
    paragraphs: list[str] = field(default_factory=list)
    headings: list[tuple[int, str]] = field(default_factory=list)  # (level, text)
    tables: list[list[list[str]]] = field(default_factory=list)    # [table][row][col]
    full_text: str = ""
    is_scan: bool = False       # True when PDF has negligible text yield
    scan_page_count: int = 0    # Number of pages that looked like scans
    sheets: list[SheetData] = field(default_factory=list)  # XLSX only
